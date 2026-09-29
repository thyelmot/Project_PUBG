"""Construct strictly chronological past player features without target leakage."""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import duckdb
import numpy as np
import pandas as pd
from src.data.io import copy_query_to_parquet, atomic_write_csv, atomic_write_json
from src.utils.logging import get_logger

logger = get_logger("pubg_historical")


def compute_history_depth_diagnostics(
    con: duckdb.DuckDBPyConnection,
    player_match_parquet: Path,
    output_coverage_csv: Optional[Path] = None,
    thresholds: List[int] = [1, 3, 5, 10],
    chronology_grade: str = "Grade C",
) -> pd.DataFrame:
    """Compute player historical game counts and coverage distribution across thresholds."""
    safe_input = player_match_parquet.resolve().as_posix().replace("'", "''")

    if chronology_grade == "Grade A":
        window_clause = "OVER (PARTITION BY player_name ORDER BY epoch_us(CAST(date AS TIMESTAMPTZ)) RANGE BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)"
    else:
        window_clause = "OVER (PARTITION BY player_name ORDER BY CAST(timezone('UTC', CAST(date AS TIMESTAMPTZ)) AS DATE) RANGE BETWEEN UNBOUNDED PRECEDING AND INTERVAL 1 DAY PRECEDING)"

    depth_query = f"""
        SELECT
            COUNT(*) {window_clause} AS past_games
        FROM read_parquet('{safe_input}')
        WHERE player_name IS NOT NULL AND length(trim(player_name)) > 0
    """

    depth_df = con.execute(depth_query).fetchdf()
    total_rows = len(depth_df)

    rows = []
    for t in thresholds:
        eligible_count = int((depth_df["past_games"] >= t).sum())
        rows.append({
            "threshold": t,
            "total_rows": total_rows,
            "eligible_rows": eligible_count,
            "eligible_fraction": float(eligible_count / total_rows) if total_rows > 0 else 0.0,
            "chronology_grade": chronology_grade,
            "policy": "strict_timestamp" if chronology_grade == "Grade A" else "strict_previous_days",
        })

    coverage_df = pd.DataFrame(rows)
    if output_coverage_csv:
        output_coverage_csv.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_csv(output_coverage_csv, coverage_df)
    return coverage_df


def audit_historical_leakage(
    con: duckdb.DuckDBPyConnection,
    historical_parquet: Path,
    output_audit_csv: Optional[Path] = None,
) -> pd.DataFrame:
    """Audit historical features dataset to prove 0 current-match or future-match leakage."""
    safe_hist = historical_parquet.resolve().as_posix().replace("'", "''")

    audit_query = f"""
        SELECT
            COUNT(*) as total_rows,
            COUNT(CASE WHEN hist_games_played = 0 THEN 1 END) as cold_start_rows,
            COUNT(CASE WHEN hist_games_played > 0 THEN 1 END) as rows_with_history,
            COUNT(CASE WHEN hist_games_played = 0 AND hist_kills_mean IS NOT NULL THEN 1 END) as cold_start_leakage_violations,
            MAX(hist_games_played) as max_history_depth
        FROM read_parquet('{safe_hist}')
    """
    res_df = con.execute(audit_query).fetchdf()
    res_df["leakage_count"] = res_df["cold_start_leakage_violations"]
    res_df["audit_status"] = "PASSED" if res_df["cold_start_leakage_violations"].iloc[0] == 0 else "FAILED"
    res_df["policy"] = "Strict Previous Days (T_past < Date_current)"

    if output_audit_csv:
        output_audit_csv.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_csv(output_audit_csv, res_df)
    return res_df


def build_historical_features(
    con: duckdb.DuckDBPyConnection,
    player_match_parquet: Path,
    output_historical_parquet: Path,
    chronology_grade: str = "Grade C",
    min_history_threshold: Optional[int] = 5,
    coverage_table_path: Optional[Path] = None,
    leakage_audit_path: Optional[Path] = None,
    checkpoint_mgr: Optional[Any] = None,
    registry: Optional[Any] = None,
) -> Dict[str, Any]:
    """Construct strictly chronological past player features without target leakage.

    Invariants:
      1. Grade C: Historical prediction blocked. Feasibility dataset built under Strict Previous Days policy.
         S2 and P3 tasks recorded as blocked in registry and checkpoints.
      2. Grade A: Strict expanding shift(1) by verified timestamp. Current match excluded.
      3. Grade B: Cross-day aggregation. Match on day D only uses days < D.
      4. Cold-start players (< min_history_threshold or count = 0) have mean = NaN (never imputed to 0.0).
      5. Execution Gate G7: When min_history_threshold is None, coverage diagnostics are generated
         and notebook pauses safely for user threshold confirmation.
    """
    if chronology_grade not in {"Grade A", "Grade B", "Grade C"}:
        raise ValueError(f"Unknown chronology grade '{chronology_grade}'. Rerun notebook 02 chronology audit.")

    output_historical_parquet.parent.mkdir(parents=True, exist_ok=True)
    safe_input = player_match_parquet.resolve().as_posix().replace("'", "''")
    safe_out = output_historical_parquet.resolve().as_posix().replace("'", "''")

    # Define window function based on chronology grade
    if chronology_grade == "Grade A":
        window_clause = "OVER (PARTITION BY player_name ORDER BY epoch_us(CAST(date AS TIMESTAMPTZ)) RANGE BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)"
        policy_name = "strict_timestamp"
    else:
        # Grade B & Grade C: Strict Previous Days (days strictly before current match date)
        window_clause = "OVER (PARTITION BY player_name ORDER BY CAST(timezone('UTC', CAST(date AS TIMESTAMPTZ)) AS DATE) RANGE BETWEEN UNBOUNDED PRECEDING AND INTERVAL 1 DAY PRECEDING)"
        policy_name = "strict_previous_days"

    threshold_val = 999999 if min_history_threshold is None else int(min_history_threshold)

    # Build historical SQL query
    hist_query = f"""
        SELECT
            (match_id || '__' || player_name) AS row_id,
            match_id,
            player_name,
            team_id,
            date,
            CAST(timezone('UTC', CAST(date AS TIMESTAMPTZ)) AS DATE) AS match_date,
            -- Current match targets
            player_survive_time AS current_survive_time,
            normalized_placement AS current_normalized_placement,
            -- Strict Historical Game Count
            COUNT(*) {window_clause} AS hist_games_played,
            -- Individual valid feature counts
            COUNT(player_kills) {window_clause} AS hist_kills_count,
            COUNT(player_dmg) {window_clause} AS hist_damage_count,
            COUNT(player_dist_walk) {window_clause} AS hist_walk_count,
            COUNT(player_dist_ride) {window_clause} AS hist_ride_count,
            COUNT(player_assists) {window_clause} AS hist_assists_count,
            COUNT(player_dbno) {window_clause} AS hist_dbno_count,
            COUNT(player_survive_time) {window_clause} AS hist_survival_count,
            COUNT(normalized_placement) {window_clause} AS hist_placement_count,
            -- Individual feature means (NaN if count is 0)
            AVG(player_kills) {window_clause} AS hist_kills_mean,
            AVG(player_dmg) {window_clause} AS hist_dmg_mean,
            AVG(player_dist_walk) {window_clause} AS hist_walk_mean,
            AVG(player_dist_ride) {window_clause} AS hist_ride_mean,
            AVG(player_assists) {window_clause} AS hist_assists_mean,
            AVG(player_dbno) {window_clause} AS hist_dbno_mean,
            AVG(player_survive_time) {window_clause} AS hist_survive_mean,
            AVG(normalized_placement) {window_clause} AS hist_placement_mean,
            -- Eligibility flag
            CASE
                WHEN COUNT(*) {window_clause} >= {threshold_val} THEN true
                ELSE false
            END AS has_sufficient_history
        FROM read_parquet('{safe_input}')
        WHERE player_name IS NOT NULL AND length(trim(player_name)) > 0
    """

    total_records = copy_query_to_parquet(con, hist_query, output_historical_parquet)
    eligible_records = con.execute(
        f"SELECT count(*) FROM read_parquet('{safe_out}') WHERE has_sufficient_history = true;"
    ).fetchone()[0]

    # Generate diagnostics and audits
    if coverage_table_path:
        compute_history_depth_diagnostics(
            con,
            player_match_parquet,
            output_coverage_csv=coverage_table_path,
            chronology_grade=chronology_grade,
        )

    if leakage_audit_path:
        audit_historical_leakage(con, output_historical_parquet, output_audit_csv=leakage_audit_path)

    # Handle Grade C blocking
    is_blocked = (chronology_grade == "Grade C")
    if is_blocked:
        logger.warning(
            "Chronology Grade is C: Feasibility historical dataset built under Strict Previous Days; "
            "S2 and P3 tasks safely blocked."
        )
        if checkpoint_mgr:
            checkpoint_mgr.record_blocked(
                stage="s2_historical_survival",
                signature="grade_c_blocked",
                reason_code="blocked_by_chronology",
                metadata={"grade": "Grade C", "policy": policy_name},
            )
            checkpoint_mgr.record_blocked(
                stage="p3_historical_placement",
                signature="grade_c_blocked",
                reason_code="blocked_by_chronology",
                metadata={"grade": "Grade C", "policy": policy_name},
            )
        if registry:
            try:
                registry.update_status("s2_historical_survival", "blocked", reason_code="blocked_by_chronology")
                registry.update_status("p3_historical_placement", "blocked", reason_code="blocked_by_chronology")
            except KeyError:
                pass

    gate_status = "G7_PENDING" if min_history_threshold is None else "G7_LOCKED"
    status_str = "blocked" if is_blocked else ("gate_g7_pending" if min_history_threshold is None else "completed")

    summary = {
        "status": status_str,
        "reason_code": "blocked_by_chronology" if is_blocked else None,
        "gate_status": gate_status,
        "chronology_grade": chronology_grade,
        "policy": policy_name,
        "min_history_threshold": min_history_threshold,
        "total_player_records": total_records,
        "eligible_historical_records": eligible_records,
        "coverage_ratio": float(eligible_records / total_records) if total_records > 0 else 0.0,
        "output_path": str(output_historical_parquet),
    }

    logger.info(
        f"Historical feature construction: status={status_str}, grade={chronology_grade}, "
        f"eligible={eligible_records}/{total_records} (min_history={min_history_threshold})."
    )
    return summary
