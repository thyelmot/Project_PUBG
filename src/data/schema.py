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
) -> Dict[str, Any]:
    """Verify that required columns are present or resolve via controlled aliases."""
    col_map = {}
    missing_required = []

    actual_lower = {c.lower(): c for c in actual_columns}

    for req_col in required_columns:
        if req_col in actual_columns:
            col_map[req_col] = req_col
        elif req_col.lower() in actual_lower:
            col_map[actual_lower[req_col.lower()]] = req_col
        else:
            # Check aliases
            alias_list = aliases.get(req_col, [])
            found = False
            for alias in alias_list:
                if alias in actual_columns:
                    col_map[alias] = req_col
                    found = True
                    break
                elif alias.lower() in actual_lower:
                    col_map[actual_lower[alias.lower()]] = req_col
                    found = True
                    break
            if not found:
                missing_required.append(req_col)

    return {
        "is_valid": len(missing_required) == 0,
        "missing_columns": missing_required,
        "column_mapping": col_map,
        "total_actual_columns": len(actual_columns),
    }


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
