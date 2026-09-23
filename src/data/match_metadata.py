from pathlib import Path
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
    safe_clean = str(cleaned_aggregate_parquet.resolve()).replace("\\", "/")
    safe_out = str(output_metadata_parquet.resolve()).replace("\\", "/")

    query = f"""
    COPY (
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
        GROUP BY match_id
    ) TO '{safe_out}' (FORMAT PARQUET, COMPRESSION 'SNAPPY');
    """

    con.execute(query)
    count_res = con.execute(f"SELECT count(*) FROM read_parquet('{safe_out}');").fetchone()
    total_matches = int(count_res[0]) if count_res else 0
    logger.info(f"Built match metadata for {total_matches} unique matches -> {output_metadata_parquet.name}")
    return total_matches
