from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import duckdb
import numpy as np
import pandas as pd
from src.data.io import copy_query_to_parquet
from src.utils.logging import get_logger

logger = get_logger("pubg_historical")


def build_historical_features(
    con: duckdb.DuckDBPyConnection,
    player_match_parquet: Path,
    output_historical_parquet: Path,
    chronology_grade: str = "Grade B",
    min_history_threshold: int = 5,
) -> Dict[str, Any]:
    """Construct strictly chronological past player features without target leakage.

    Invariants:
      1. Grade C: Historical prediction blocked. Return blocked status with reason_code.
      2. Grade A: Strict expanding shift(1) by verified timestamp. Current match excluded.
      3. Grade B: Cross-day aggregation. Trận ngày D chỉ dùng dữ liệu ngày < D. Matches on same day excluded from each other's history.
      4. Cold-start players (< min_history_threshold) are flagged with has_sufficient_history = False.
    """
    if chronology_grade not in {"Grade A", "Grade B", "Grade C"}:
        raise ValueError("Unknown chronology grade. Rerun notebook 02 chronology audit.")
    if chronology_grade == "Grade C":
        logger.warning("Historical features blocked: Chronology Grade is C. S2 and P3 tasks disabled.")
        return {
            "status": "blocked",
            "reason_code": "blocked_by_chronology",
            "message": "Chronology lacks reliable timestamps or cross-day separation.",
        }

    output_historical_parquet.parent.mkdir(parents=True, exist_ok=True)
    safe_input = player_match_parquet.resolve().as_posix().replace("'", "''")
    safe_out = output_historical_parquet.resolve().as_posix().replace("'", "''")

    # We build expanding features using DuckDB SQL window functions
    if chronology_grade == "Grade A":
        # Sort strictly by timestamp within player history
        window_clause = "OVER (PARTITION BY player_name ORDER BY epoch_us(CAST(date AS TIMESTAMPTZ)) RANGE BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)"
    else:
        # Grade B: Group prior matches strictly by date < current match date
        # Window ordered by date, excluding current date
        window_clause = "OVER (PARTITION BY player_name ORDER BY CAST(timezone('UTC', CAST(date AS TIMESTAMPTZ)) AS DATE) RANGE BETWEEN UNBOUNDED PRECEDING AND INTERVAL 1 DAY PRECEDING)"

    # Build historical query
    hist_query = f"""
        SELECT
            match_id,
            player_name,
            team_id,
            date,
            -- Current match targets to predict
            player_survive_time AS current_survive_time,
            normalized_placement AS current_normalized_placement,
            -- Strict Historical Features (Prior Completed Matches)
            COUNT(*) {window_clause} AS hist_games_played,
            AVG(player_kills) {window_clause} AS hist_mean_kills,
            AVG(player_dmg) {window_clause} AS hist_mean_damage,
            AVG(player_dist_walk) {window_clause} AS hist_mean_walk,
            AVG(player_dist_ride) {window_clause} AS hist_mean_ride,
            AVG(player_assists) {window_clause} AS hist_mean_assists,
            AVG(player_dbno) {window_clause} AS hist_mean_dbno,
            AVG(player_survive_time) {window_clause} AS hist_mean_survival,
            AVG(normalized_placement) {window_clause} AS hist_mean_placement,
            -- Eligibility flag
            CASE
                WHEN COUNT(*) {window_clause} >= {min_history_threshold} THEN true
                ELSE false
            END AS has_sufficient_history
        FROM read_parquet('{safe_input}')
        WHERE player_name IS NOT NULL AND length(trim(player_name)) > 0
    """

    total_records = copy_query_to_parquet(con, hist_query, output_historical_parquet)
    eligible_records = con.execute(f"SELECT count(*) FROM read_parquet('{safe_out}') WHERE has_sufficient_history = true;").fetchone()[0]

    summary = {
        "status": "completed",
        "chronology_grade": chronology_grade,
        "min_history_threshold": min_history_threshold,
        "total_player_records": total_records,
        "eligible_historical_records": eligible_records,
        "coverage_ratio": float(eligible_records / total_records) if total_records > 0 else 0.0,
    }
    logger.info(f"Historical feature construction completed: {eligible_records}/{total_records} rows eligible (min_history={min_history_threshold}).")
    return summary
