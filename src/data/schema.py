from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import duckdb
from src.data.io import atomic_write_json, get_duckdb_connection
from src.utils.logging import get_logger

logger = get_logger("pubg_schema")


def inspect_csv_columns(con: duckdb.DuckDBPyConnection, file_path: Path) -> List[Tuple[str, str]]:
    """Retrieve actual column names and initial parsed types from CSV file."""
    safe_path = str(file_path.resolve()).replace("\\", "/")
    # DESCRIBE statement on CSV
    query = f"DESCRIBE SELECT * FROM read_csv_auto('{safe_path}', header=True, sample_size=2000);"
    res = con.execute(query).fetchall()
    return [(row[0], row[1]) for row in res]


def validate_shard_schema(
    actual_columns: List[str],
    required_columns: Dict[str, str],
    aliases: Dict[str, List[str]],
    optional_columns: Optional[Dict[str, str]] = None,
    units: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Resolve a controlled schema and reject ambiguous alias mappings."""
    actual_by_lower: Dict[str, List[str]] = {}
    for column in actual_columns:
        actual_by_lower.setdefault(column.lower(), []).append(column)

    col_map: Dict[str, str] = {}
    missing_required: List[str] = []
    optional_present: List[str] = []
    optional_missing: List[str] = []
    alias_collisions: Dict[str, List[str]] = {
        f"case:{key}": values for key, values in actual_by_lower.items() if len(values) > 1
    }
    claimed: Dict[str, str] = {}

    def resolve(canonical: str) -> Optional[str]:
        candidates = [canonical, *aliases.get(canonical, [])]
        matches: List[str] = []
        for candidate in candidates:
            for actual in actual_by_lower.get(candidate.lower(), []):
                if actual not in matches:
                    matches.append(actual)
        if len(matches) > 1:
            alias_collisions[canonical] = matches
            return None
        if not matches:
            return None
        actual = matches[0]
        previous = claimed.get(actual)
        if previous and previous != canonical:
            alias_collisions[f"shared:{actual}"] = [previous, canonical]
            return None
        claimed[actual] = canonical
        col_map[actual] = canonical
        return actual

    for canonical in required_columns:
        if resolve(canonical) is None and canonical not in alias_collisions:
            missing_required.append(canonical)

    for canonical in (optional_columns or {}):
        if resolve(canonical) is None:
            if canonical not in alias_collisions:
                optional_missing.append(canonical)
        else:
            optional_present.append(canonical)

    mapped_actual = set(col_map)
    unexpected_columns = [
        column for column in actual_columns
        if column not in mapped_actual and not column.startswith("__pubg_")
    ]
    units_verified = {
        column: unit for column, unit in (units or {}).items()
        if column in col_map.values()
    }
    return {
        "is_valid": not missing_required and not alias_collisions,
        "missing_columns": missing_required,
        "alias_collisions": alias_collisions,
        "column_mapping": col_map,
        "optional_present": optional_present,
        "optional_missing": optional_missing,
        "unexpected_columns": unexpected_columns,
        "actual_columns": list(actual_columns),
        "canonical_columns": sorted(col_map.values()),
        "units_verified": units_verified,
        "total_actual_columns": len(actual_columns),
    }


def generate_schema_report(
    schema_cfg: Dict[str, Any],
    shard_validations: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate comprehensive schema comparison report (expected vs actual contract)."""
    report = {
        "spec_version": schema_cfg.get("version", "3.0"),
        "tables": {},
        "all_shards_valid": True,
        "summary": {
            "total_shards_evaluated": len(shard_validations),
            "valid_shards": 0,
            "invalid_shards": 0,
        },
    }

    for kind in ("aggregate", "deaths"):
        table_cfg = schema_cfg.get(kind, {})
        req = table_cfg.get("required_columns", {})
        opt = table_cfg.get("optional_columns", {})
        aliases = table_cfg.get("aliases", {})
        units = table_cfg.get("units", {})

        report["tables"][kind] = {
            "expected_required_columns": req,
            "expected_optional_columns": opt,
            "configured_aliases": aliases,
            "units_contract": units,
            "candidate_units": table_cfg.get("candidate_units", {}),
            "units_verification_status": table_cfg.get("units_verification_status", "unverified"),
            "units_evidence": table_cfg.get("units_evidence"),
            "shards": {},
        }

    for shard_name, val_result in shard_validations.items():
        is_valid = val_result.get("is_valid", False)
        if is_valid:
            report["summary"]["valid_shards"] += 1
        else:
            report["summary"]["invalid_shards"] += 1
            report["all_shards_valid"] = False

        kind = val_result.get("kind", "aggregate")
        if kind in report["tables"]:
            report["tables"][kind]["shards"][shard_name] = {
                "is_valid": is_valid,
                "missing_required": val_result.get("missing_columns", []),
                "alias_collisions": val_result.get("alias_collisions", {}),
                "actual_columns": val_result.get("actual_columns", []),
                "unexpected_columns": val_result.get("unexpected_columns", []),
                "optional_present": val_result.get("optional_present", []),
                "optional_missing": val_result.get("optional_missing", []),
                "column_mapping": val_result.get("column_mapping", {}),
                "units_verified": val_result.get("units_verified", {}),
            }

    return report


def convert_shard_to_parquet(
    con: duckdb.DuckDBPyConnection,
    csv_path: Path,
    output_parquet_path: Path,
    expected_schema: Dict[str, str],
    column_mapping: Dict[str, str],
) -> int:
    """Convert a CSV shard directly to a typed Parquet file via DuckDB for zero-copy streaming."""
    output_parquet_path.parent.mkdir(parents=True, exist_ok=True)
    safe_csv = str(csv_path.resolve()).replace("\\", "/")
    safe_parquet = str(output_parquet_path.resolve()).replace("\\", "/")

    # Build typed SELECT clause
    select_items = []
    for csv_col, canon_col in column_mapping.items():
        target_type = expected_schema.get(canon_col, "VARCHAR").lower()
        # Map YAML types to DuckDB SQL types
        sql_type = "VARCHAR"
        if "int" in target_type or "bigint" in target_type:
            sql_type = "BIGINT"
        elif "float" in target_type or "double" in target_type:
            sql_type = "DOUBLE"

        select_items.append(f'TRY_CAST("{csv_col}" AS {sql_type}) AS "{canon_col}"')

    select_clause = ", ".join(select_items)
    query = f"""
    COPY (
        SELECT {select_clause}
        FROM read_csv_auto('{safe_csv}', header=True)
    ) TO '{safe_parquet}' (FORMAT PARQUET, COMPRESSION 'SNAPPY');
    """

    con.execute(query)
    count_res = con.execute(f"SELECT count(*) FROM read_parquet('{safe_parquet}');").fetchone()
    rows = int(count_res[0]) if count_res else 0
    logger.info(f"Converted {csv_path.name} -> {output_parquet_path.name}: {rows} rows.")
    return rows
