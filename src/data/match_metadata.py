from pathlib import Path
from tempfile import TemporaryDirectory
import math
from typing import Any, Dict
import duckdb
from src.utils.logging import get_logger

logger = get_logger("pubg_match_metadata")


def build_match_metadata(
    con: duckdb.DuckDBPyConnection,
    cleaned_aggregate_parquet: Path,
    output_metadata_parquet: Path,
) -> int:
    """Build match-level metadata roster statistics and duration proxy before task cohort filtering."""
    output_metadata_parquet.parent.mkdir(parents=True, exist_ok=True)
    safe_clean = cleaned_aggregate_parquet.resolve().as_posix().replace("'", "''")
    # Aggregate one hash bucket at a time: every player in a match stays together.
    rows = con.execute(f"SELECT count(*) FROM read_parquet('{safe_clean}')").fetchone()[0]
    buckets = max(1, math.ceil(rows / 1_000_000))

    aggregate = f"""
        SELECT
            match_id,
            MIN(date) AS match_date,
            MODE(match_mode) AS match_mode,
            MODE(party_size) AS party_size,
            MODE(game_size) AS game_size,
            COUNT(DISTINCT team_id) AS observed_team_count,
            COUNT(*) AS observed_player_count,
            MAX(team_placement) AS max_observed_placement,
            MAX(player_survive_time) AS estimated_match_duration,
            CASE
                WHEN COUNT(DISTINCT team_id) >= 2
                 AND MAX(team_placement) >= 2
                 AND ABS(COUNT(DISTINCT team_id) - MAX(team_placement)) <= 2
                THEN true
                ELSE false
            END AS is_roster_complete
        FROM read_parquet('{safe_clean}')
        WHERE hash(match_id) % {buckets} = {{bucket}}
        GROUP BY match_id
    """

    temp_root = Path(con.execute("SELECT current_setting('temp_directory')").fetchone()[0])
    temp_root.mkdir(parents=True, exist_ok=True)
    pending = output_metadata_parquet.with_suffix(".parquet.partial")
    try:
        with TemporaryDirectory(prefix="metadata_", dir=temp_root) as directory:
            parts = []
            for bucket in range(buckets):
                part = (Path(directory) / f"part_{bucket}.parquet").as_posix().replace("'", "''")
                con.execute(f"COPY ({aggregate.format(bucket=bucket)}) TO '{part}' (FORMAT PARQUET, COMPRESSION 'SNAPPY')")
                parts.append("'" + part + "'")
                logger.info(f"Match metadata: bucket {bucket + 1}/{buckets} completed")
            safe_pending = pending.resolve().as_posix().replace("'", "''")
            con.execute(f"COPY (SELECT * FROM read_parquet([{','.join(parts)}])) TO '{safe_pending}' (FORMAT PARQUET, COMPRESSION 'SNAPPY')")
            total_matches = con.execute(f"SELECT count(*) FROM read_parquet('{safe_pending}')").fetchone()[0]
            pending.replace(output_metadata_parquet)
    finally:
        pending.unlink(missing_ok=True)
    logger.info(f"Built match metadata for {total_matches} unique matches -> {output_metadata_parquet.name}")
    return total_matches
