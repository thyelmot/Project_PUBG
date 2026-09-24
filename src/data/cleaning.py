from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import duckdb
import pandas as pd
from src.data.io import copy_query_to_parquet, atomic_write_csv
from src.utils.logging import get_logger

logger = get_logger("pubg_cleaning")


def audit_and_clean_aggregate_data(
    con: duckdb.DuckDBPyConnection,
    aggregate_parquet_paths: List[Path],
    output_cleaned_parquet: Path,
    removal_log_path: Path,
) -> Dict[str, Any]:
    """Clean aggregate dataset across shards: audit duplicates, missing keys, and invalid values."""
    if not aggregate_parquet_paths:
        raise FileNotFoundError(
            "No aggregate Parquet shards were provided. Run notebook 01 with the same "
            "PUBG_STORAGE_MODE and PUBG_DRIVE_PROJECT_ROOT before notebook 02."
        )
    output_cleaned_parquet.parent.mkdir(parents=True, exist_ok=True)
    removal_log_path.parent.mkdir(parents=True, exist_ok=True)

    # Union all aggregate parquet shards as a single view
    parquet_globs = [p.resolve().as_posix().replace("'", "''") for p in aggregate_parquet_paths]
    paths_sql = ", ".join([f"'{p}'" for p in parquet_globs])

    con.execute(f"CREATE OR REPLACE VIEW raw_aggregate_view AS SELECT * FROM read_parquet([{paths_sql}]);")

    total_rows = con.execute("SELECT count(*) FROM raw_aggregate_view;").fetchone()[0]

    # 1. Exact duplicates count
    exact_duplicates = con.execute("""
        SELECT count(*) - count(DISTINCT (
            match_id, player_name, team_id, date, match_mode, party_size,
            player_kills, player_dmg, player_dist_walk, player_dist_ride,
            player_survive_time, team_placement, game_size, player_assists, player_dbno
        ))
        FROM raw_aggregate_view;
    """).fetchone()[0]

    # 2. Missing core identifiers
    missing_match_id = con.execute("SELECT count(*) FROM raw_aggregate_view WHERE match_id IS NULL OR length(trim(match_id)) = 0;").fetchone()[0]
    missing_team_id = con.execute("SELECT count(*) FROM raw_aggregate_view WHERE team_id IS NULL OR length(trim(team_id)) = 0;").fetchone()[0]
    missing_player_name = con.execute("SELECT count(*) FROM raw_aggregate_view WHERE player_name IS NULL OR length(trim(player_name)) = 0;").fetchone()[0]

    # 3. Invalid domain constraints (negative counts or distance, zero/negative team placement)
    invalid_domain_rows = con.execute("""
        SELECT count(*) FROM raw_aggregate_view
        WHERE player_kills < 0 OR player_dmg < 0 OR player_dist_walk < 0 OR player_dist_ride < 0
           OR player_survive_time < 0 OR team_placement <= 0;
    """).fetchone()[0]

    # 4. Filter clean rows into typed validated aggregate table
    # Canonicalize string identifiers: trim whitespace
    cleaning_query = f"""
        SELECT DISTINCT
            trim(match_id) AS match_id,
            CASE WHEN player_name IS NOT NULL AND length(trim(player_name)) > 0 THEN trim(player_name) ELSE NULL END AS player_name,
            trim(team_id) AS team_id,
            date,
            match_mode,
            party_size,
            game_size,
            player_assists,
            player_dbno,
            player_dist_ride,
            player_dist_walk,
            player_dmg,
            player_kills,
            player_survive_time,
            team_placement
        FROM raw_aggregate_view
        WHERE match_id IS NOT NULL AND length(trim(match_id)) > 0
          AND team_id IS NOT NULL AND length(trim(team_id)) > 0
          AND player_kills >= 0
          AND player_dmg >= 0
          AND player_dist_walk >= 0
          AND player_dist_ride >= 0
          AND player_survive_time >= 0
          AND team_placement > 0
    """

    clean_rows = copy_query_to_parquet(con, cleaning_query, output_cleaned_parquet)
    dropped_rows = total_rows - clean_rows

    # Record removal log
    removal_records = [
        {"stage": "raw_input", "reason": "initial_raw_records", "rows_affected": total_rows},
        {"stage": "cleaning", "reason": "exact_duplicates", "rows_affected": exact_duplicates},
        {"stage": "cleaning", "reason": "missing_match_or_team_id", "rows_affected": missing_match_id + missing_team_id},
        {"stage": "cleaning", "reason": "invalid_domain_values", "rows_affected": invalid_domain_rows},
        {"stage": "cleaning", "reason": "total_dropped_records", "rows_affected": dropped_rows},
        {"stage": "cleaning", "reason": "validated_clean_records", "rows_affected": clean_rows},
    ]
    atomic_write_csv(removal_log_path, pd.DataFrame(removal_records))

    summary = {
        "total_raw_rows": total_rows,
        "clean_rows": clean_rows,
        "dropped_rows": dropped_rows,
        "exact_duplicates": exact_duplicates,
        "missing_player_name": missing_player_name,
        "invalid_domain_rows": invalid_domain_rows,
    }
    logger.info(f"Cleaning finished: {clean_rows}/{total_rows} rows retained. Dropped: {dropped_rows}.")
    return summary
