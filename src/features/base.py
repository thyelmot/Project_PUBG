import math
import re
import tempfile
from pathlib import Path
from typing import Dict, Optional

import duckdb
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from src.data.io import atomic_write_csv, atomic_write_json, copy_query_to_parquet, publish_file
from src.features.placement import normalized_placement_sql, placement_valid_sql
from src.features.registry import FeatureRegistry
from src.utils.hashing import hash_file
from src.utils.logging import get_logger

logger = get_logger("pubg_base_features")

DERIVED_SQL = {
    "damage_per_kill": "CASE WHEN a.player_kills > 0 THEN a.player_dmg / a.player_kills ELSE NULL END",
    "total_distance": "(a.player_dist_walk + a.player_dist_ride)",
    "walk_ratio": """CASE WHEN (a.player_dist_walk + a.player_dist_ride) > 0
        THEN a.player_dist_walk / (a.player_dist_walk + a.player_dist_ride) ELSE NULL END""",
    "assist_ratio": """CASE WHEN (a.player_assists + a.player_kills) > 0
        THEN CAST(a.player_assists AS DOUBLE) / (a.player_assists + a.player_kills) ELSE NULL END""",
}


def compute_base_features_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Small-frame adapter over the same SQL formulas as the full-data producer."""
    expressions = {name: expression for name, expression in DERIVED_SQL.items()
        if set(re.findall(r"a\.(\w+)", expression)).issubset(df.columns)}
    if not expressions:
        return pd.DataFrame(index=df.index)
    columns = sorted({column for expression in expressions.values()
        for column in re.findall(r"a\.(\w+)", expression)})
    inputs = df[columns].apply(pd.to_numeric, errors="coerce").astype("float64")
    with duckdb.connect(":memory:") as connection:
        connection.register("a", inputs)
        query = ", ".join(f"{expression} AS {name}" for name, expression in expressions.items())
        result = connection.execute("SELECT " + query + " FROM a").df()
    result.index = df.index
    return result


def _parquet_columns(con: duckdb.DuckDBPyConnection, path: Path) -> set[str]:
    safe = path.resolve().as_posix().replace("'", "''")
    return {row[0] for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{safe}')").fetchall()}


def _optional_column(alias: str, name: str, available: set[str], default: str = "NULL") -> str:
    return f"{alias}.{name} AS {name}" if name in available else f"{default} AS {name}"


def _validate_match_contract(
    con: duckdb.DuckDBPyConnection,
    clean_path: str,
    metadata_path: str,
    split_assignments_parquet: Optional[Path],
) -> None:
    duplicate_meta, null_meta = con.execute(f"""
        SELECT count(*) - count(DISTINCT match_id),
               count(*) FILTER (WHERE match_id IS NULL OR length(trim(match_id)) = 0)
        FROM read_parquet('{metadata_path}')
    """).fetchone()
    if duplicate_meta or null_meta:
        raise ValueError(
            f"match_metadata must contain one non-null row per match: "
            f"duplicate_rows={duplicate_meta}, null_match_ids={null_meta}"
        )
    missing_meta = con.execute(f"""
        SELECT count(DISTINCT a.match_id)
        FROM read_parquet('{clean_path}') a
        LEFT JOIN read_parquet('{metadata_path}') m USING (match_id)
        WHERE m.match_id IS NULL
    """).fetchone()[0]
    if missing_meta:
        raise ValueError(f"Match metadata is missing {missing_meta} cleaned matches")

    if split_assignments_parquet is None:
        return
    split_path = Path(split_assignments_parquet)
    if not split_path.is_file():
        raise FileNotFoundError(f"Split assignments Parquet not found: {split_path}")
    safe_split = split_path.resolve().as_posix().replace("'", "''")
    duplicate_split, null_split = con.execute(f"""
        SELECT count(*) - count(DISTINCT match_id),
               count(*) FILTER (WHERE match_id IS NULL OR split IS NULL)
        FROM read_parquet('{safe_split}')
    """).fetchone()
    if duplicate_split or null_split:
        raise ValueError(
            f"split_assignments must contain one labeled row per match: "
            f"duplicate_rows={duplicate_split}, null_keys_or_labels={null_split}"
        )
    missing_split = con.execute(f"""
        SELECT count(DISTINCT a.match_id)
        FROM read_parquet('{clean_path}') a
        LEFT JOIN read_parquet('{safe_split}') s USING (match_id)
        WHERE s.match_id IS NULL
    """).fetchone()[0]
    if missing_split:
        raise ValueError(f"Split assignments are missing {missing_split} cleaned matches")


def _write_numbered_parts(
    con: duckdb.DuckDBPyConnection,
    base_path: Path,
    output_dir: Path,
    manifest_path: Path,
    target_rows_per_part: int,
) -> Dict[str, object]:
    if target_rows_per_part <= 0:
        raise ValueError("target_rows_per_part must be positive")
    safe_base = base_path.resolve().as_posix().replace("'", "''")
    total_rows = con.execute(f"SELECT count(*) FROM read_parquet('{safe_base}')").fetchone()[0]
    bucket_count = max(1, math.ceil(total_rows / target_rows_per_part))
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_root = Path(con.execute("SELECT current_setting('temp_directory')").fetchone()[0])
    temp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="base_parts_", dir=temp_root) as directory:
        local_parts = []
        for bucket in range(bucket_count):
            local = Path(directory) / f"part_{bucket:05d}.parquet"
            safe_local = local.resolve().as_posix().replace("'", "''")
            con.execute(f"""
                COPY (
                    SELECT * FROM read_parquet('{safe_base}')
                    WHERE hash(row_id) % {bucket_count} = {bucket}
                ) TO '{safe_local}' (FORMAT PARQUET, COMPRESSION 'ZSTD')
            """)
            local_parts.append(local)

        expected_names = {part.name for part in local_parts}
        records = []
        for bucket, local in enumerate(local_parts):
            destination = output_dir / local.name
            publish_file(local, destination)
            records.append({
                "part": destination.name,
                "bucket": bucket,
                "rows": pq.ParquetFile(destination).metadata.num_rows,
                "bytes": destination.stat().st_size,
                "sha256": hash_file(destination),
            })

    for stale in output_dir.glob("part_*.parquet"):
        if stale.name not in expected_names:
            stale.unlink()

    manifest = {
        "schema_version": "player_match_base_parts.v1",
        "source": str(base_path),
        "partition_rule": f"hash(row_id) modulo {bucket_count}",
        "target_rows_per_part": target_rows_per_part,
        "part_count": bucket_count,
        "row_count": total_rows,
        "row_count_from_parts": sum(record["rows"] for record in records),
        "parts": records,
    }
    if manifest["row_count_from_parts"] != total_rows:
        raise ValueError("Partition row reconciliation failed")
    atomic_write_json(manifest_path, manifest)
    return manifest


def _validation_summary(
    con: duckdb.DuckDBPyConnection,
    base_path: Path,
    registry: FeatureRegistry,
) -> pd.DataFrame:
    safe_base = base_path.resolve().as_posix().replace("'", "''")
    groups = {
        "player_kills": "combat", "player_dmg": "combat", "damage_per_kill": "combat",
        "player_dist_walk": "movement", "player_dist_ride": "movement",
        "total_distance": "movement", "walk_ratio": "movement",
        "player_assists": "support", "player_dbno": "support", "assist_ratio": "support",
        "player_survive_time": "outcome", "team_placement": "outcome",
        "normalized_placement": "outcome",
    }
    expected_missing = {
        "damage_per_kill": "player_kills <= 0",
        "walk_ratio": "total_distance <= 0",
        "assist_ratio": "(player_assists + player_kills) <= 0",
        "player_survive_time": "NOT valid_survival",
        "normalized_placement": "NOT valid_placement",
    }
    selects = []
    for name, group in groups.items():
        condition = expected_missing.get(name, "false")
        selects.append(f"""
            SELECT '{name}' AS feature_name, '{group}' AS feature_group,
                   count(*) AS total_rows, count({name}) AS valid_count,
                   count(*) - count({name}) AS null_count,
                   count(*) FILTER (WHERE {name} IS NULL AND ({condition})) AS structural_missing_count,
                   min({name}) AS min_val, max({name}) AS max_val,
                   avg({name}) AS mean_val, stddev({name}) AS std_val,
                   avg(CASE WHEN {name} = 0 THEN 1.0 ELSE 0.0 END) AS zero_rate
            FROM read_parquet('{safe_base}')
        """)
    result = con.execute(" UNION ALL ".join(selects)).df()
    result["other_missing_count"] = (
        result["null_count"] - result["structural_missing_count"]
    ).clip(lower=0)
    result["null_pct"] = np.where(
        result["total_rows"] > 0,
        result["null_count"] * 100.0 / result["total_rows"],
        np.nan,
    )
    definitions = {feature.name: feature for feature in registry.list_all()}
    result["unit"] = result["feature_name"].map(
        lambda name: definitions[name].unit if name in definitions else "rank"
    )
    result["denominator"] = result["feature_name"].map(
        lambda name: definitions[name].aggregation_denominator or "-" if name in definitions else "-"
    )
    result["missing_semantics"] = result["feature_name"].map(
        lambda name: definitions[name].missing_semantics
        if name in definitions else "Raw placement retained; task validity is stored separately."
    )
    result["allowed_tasks"] = result["feature_name"].map(
        lambda name: ", ".join(definitions[name].allowed_tasks) if name in definitions else "audit"
    )
    result["status"] = np.where(result["other_missing_count"] == 0, "valid", "valid_with_reported_other_missing")
    result["scope"] = "all cleaned rows"
    return result


def build_player_match_base(
    con: duckdb.DuckDBPyConnection,
    cleaned_aggregate_parquet: Path,
    match_metadata_parquet: Path,
    output_base_parquet: Path,
    validation_csv_path: Optional[Path] = None,
    dictionary_csv_path: Optional[Path] = None,
    split_assignments_parquet: Optional[Path] = None,
    schema_json_path: Optional[Path] = None,
    partition_dir: Optional[Path] = None,
    partition_manifest_path: Optional[Path] = None,
    target_rows_per_part: int = 1_000_000,
) -> int:
    """Build the canonical player-match base while preserving every cleaned row."""
    clean_path = Path(cleaned_aggregate_parquet)
    metadata_path = Path(match_metadata_parquet)
    output_path = Path(output_base_parquet)
    if not clean_path.is_file():
        raise FileNotFoundError(f"Cleaned aggregate Parquet not found: {clean_path}")
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Match metadata Parquet not found: {metadata_path}")

    clean_columns = _parquet_columns(con, clean_path)
    metadata_columns = _parquet_columns(con, metadata_path)
    required_clean = {
        "match_id", "player_name", "team_id", "date", "match_mode", "party_size",
        "game_size", "player_kills", "player_dmg", "player_dist_walk",
        "player_dist_ride", "player_assists", "player_dbno", "player_survive_time",
        "team_placement",
    }
    required_metadata = {
        "match_id", "observed_team_count", "observed_player_count",
        "estimated_match_duration", "is_roster_complete",
    }
    missing_clean = sorted(required_clean - clean_columns)
    missing_metadata = sorted(required_metadata - metadata_columns)
    if missing_clean or missing_metadata:
        raise ValueError(
            f"Base feature input schema is incomplete: clean_missing={missing_clean}, "
            f"metadata_missing={missing_metadata}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    safe_clean = clean_path.resolve().as_posix().replace("'", "''")
    safe_metadata = metadata_path.resolve().as_posix().replace("'", "''")
    _validate_match_contract(con, safe_clean, safe_metadata, split_assignments_parquet)

    source_file = _optional_column("a", "source_file", clean_columns, "CAST(NULL AS VARCHAR)")
    source_row = _optional_column("a", "source_row", clean_columns, "CAST(NULL AS BIGINT)")
    clean_valid_survival = _optional_column("a", "valid_survival", clean_columns, "CAST(NULL AS BOOLEAN)")
    clean_valid_placement = _optional_column("a", "valid_placement", clean_columns, "CAST(NULL AS BOOLEAN)")
    max_placement = _optional_column("m", "max_observed_placement", metadata_columns, "CAST(NULL AS DOUBLE)")
    missing_team_ids = _optional_column("m", "missing_team_id_rows", metadata_columns, "CAST(NULL AS BIGINT)")
    team_conflicts = _optional_column("m", "team_placement_conflict_count", metadata_columns, "CAST(NULL AS BIGINT)")
    metadata_conflict = _optional_column("m", "has_metadata_conflict", metadata_columns, "false")

    if {"source_file", "source_row"}.issubset(clean_columns):
        row_id = """CASE
            WHEN a.match_id IS NULL OR length(trim(a.match_id)) = 0 THEN NULL
            WHEN a.player_name IS NOT NULL AND length(trim(a.player_name)) > 0 THEN
                concat('match:', length(trim(a.match_id)), ':', trim(a.match_id),
                       '|player:', length(trim(a.player_name)), ':', trim(a.player_name))
            WHEN a.source_file IS NOT NULL AND a.source_row IS NOT NULL THEN
                concat('match:', length(trim(a.match_id)), ':', trim(a.match_id),
                       '|lineage:', length(a.source_file), ':', a.source_file,
                       length(CAST(a.source_row AS VARCHAR)), ':', CAST(a.source_row AS VARCHAR))
            ELSE NULL END"""
    else:
        row_id = """CASE
            WHEN a.match_id IS NOT NULL AND length(trim(a.match_id)) > 0
             AND a.player_name IS NOT NULL AND length(trim(a.player_name)) > 0 THEN
                concat('match:', length(trim(a.match_id)), ':', trim(a.match_id),
                       '|player:', length(trim(a.player_name)), ':', trim(a.player_name))
            ELSE NULL END"""

    placement_expr = normalized_placement_sql("a", "m")
    placement_valid = placement_valid_sql("a", "m")
    base_query = f"""
        SELECT
            {row_id} AS row_id,
            trim(a.match_id) AS match_id,
            a.player_name,
            trim(a.team_id) AS team_id,
            {source_file},
            {source_row},
            a.date,
            a.match_mode,
            CASE
                WHEN lower(trim(a.match_mode)) LIKE '%fpp%' THEN 'fpp'
                WHEN lower(trim(a.match_mode)) LIKE '%tpp%' THEN 'tpp'
                ELSE 'unknown'
            END AS perspective_mode,
            a.party_size,
            CASE
                WHEN a.party_size = 1 THEN 'solo'
                WHEN a.party_size = 2 THEN 'duo'
                WHEN a.party_size = 4 THEN 'squad'
                ELSE 'unknown'
            END AS team_size_mode,
            a.game_size,
            m.observed_team_count,
            m.observed_player_count,
            {max_placement},
            {missing_team_ids},
            {team_conflicts},
            COALESCE(m.is_roster_complete, false) AS is_roster_complete,
            {metadata_conflict},
            m.estimated_match_duration,
            true AS metadata_matched,
            a.player_kills,
            a.player_dmg,
            a.player_dist_walk,
            a.player_dist_ride,
            a.player_assists,
            a.player_dbno,
            {DERIVED_SQL["damage_per_kill"]} AS damage_per_kill,
            {DERIVED_SQL["total_distance"]} AS total_distance,
            {DERIVED_SQL["walk_ratio"]} AS walk_ratio,
            {DERIVED_SQL["assist_ratio"]} AS assist_ratio,
            a.player_survive_time,
            a.team_placement,
            {placement_expr} AS normalized_placement,
            (
                a.player_survive_time IS NOT NULL
                AND a.player_survive_time >= 0
                AND NOT (isnan(a.player_survive_time) OR isinf(a.player_survive_time))
            ) AS valid_survival,
            {placement_valid} AS valid_placement,
            {clean_valid_survival},
            {clean_valid_placement}
        FROM read_parquet('{safe_clean}') a
        LEFT JOIN read_parquet('{safe_metadata}') m USING (match_id)
    """

    grain = con.execute(f"""
        SELECT count(*) AS rows,
               count(*) FILTER (WHERE row_id IS NULL) AS null_row_ids,
               count(*) - count(DISTINCT row_id) AS duplicate_row_ids
        FROM ({base_query})
    """).fetchone()
    if grain[1] or grain[2]:
        raise ValueError(
            f"Invalid player-match grain before publication: rows={grain[0]}, "
            f"null_row_ids={grain[1]}, duplicate_row_ids={grain[2]}"
        )

    base_rows = copy_query_to_parquet(con, base_query, output_path, expected_rows=grain[0])
    registry = FeatureRegistry()
    if dictionary_csv_path:
        registry.export_dictionary_csv(Path(dictionary_csv_path))
    if validation_csv_path:
        atomic_write_csv(Path(validation_csv_path), _validation_summary(con, output_path, registry))

    safe_output = output_path.resolve().as_posix().replace("'", "''")
    schema_rows = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{safe_output}')").fetchall()
    schema_path = Path(schema_json_path) if schema_json_path else output_path.parent / "player_match_base_schema.json"
    atomic_write_json(schema_path, {
        "schema_version": "player_match_base.v1",
        "canonical_path": str(output_path),
        "grain": "one row per cleaned player-match observation",
        "primary_row_key": "row_id",
        "business_key": ["match_id", "player_name"],
        "lineage_fallback": ["source_file", "source_row"],
        "row_count": base_rows,
        "columns": [{"name": row[0], "dtype": row[1]} for row in schema_rows],
    })

    parts_dir = Path(partition_dir) if partition_dir else output_path.parent / "player_match_base_parts"
    parts_manifest = Path(partition_manifest_path) if partition_manifest_path else output_path.parent / "player_match_base_parts_manifest.json"
    _write_numbered_parts(con, output_path, parts_dir, parts_manifest, target_rows_per_part)
    logger.info(f"Built player_match_base: {base_rows} rows -> {output_path.name}")
    return base_rows
