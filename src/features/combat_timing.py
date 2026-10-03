from pathlib import Path
from typing import Any, Dict, List, Optional
import duckdb
import pandas as pd
from src.data.io import copy_query_to_parquet, atomic_write_csv
from src.utils.logging import get_logger

logger = get_logger("pubg_combat_timing")


def _sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def evaluate_combat_timing_research_gate(features_config: Dict[str, Any]) -> Dict[str, Any]:
    """Require explicit evidence before NB04 publishes final research artifacts."""
    timing_cfg = features_config.get("combat_timing", features_config)
    requirements = (
        ("event_time_unit", "event_time_unit_status", "event_time_unit_evidence"),
        ("enemy_kill_eligibility", "enemy_kill_eligibility_status", "enemy_kill_eligibility_evidence"),
        ("min_valid_duration", "min_valid_duration_status", "min_valid_duration_evidence"),
    )
    checks = []
    for parameter, status_key, evidence_key in requirements:
        status = str(timing_cfg.get(status_key, "pending_evidence")).strip().lower()
        raw_evidence = timing_cfg.get(evidence_key, "")
        evidence = raw_evidence.strip() if isinstance(raw_evidence, str) else ""
        checks.append(
            {
                "parameter": parameter,
                "status": status,
                "evidence": evidence,
                "ready": status == "verified" and bool(evidence),
            }
        )
    ready = all(item["ready"] for item in checks)
    return {"ready": ready, "checks": checks, "reason_code": "ready" if ready else "RUN-04"}


def extract_and_aggregate_combat_timing(
    con: duckdb.DuckDBPyConnection,
    death_parquet_paths: List[Path],
    match_metadata_parquet: Path,
    output_timing_parquet: Path,
    audit_output_dir: Path,
    features_config: Optional[Dict[str, Any]] = None,
    player_match_base_parquet: Optional[Path] = None,
) -> Dict[str, Any]:
    """Aggregate combat timing from death events grouped by (match_id, killer_name).

    Formulas and Semantics:
      - Absolute timing:
          first_kill_time = min(time) for credited-killer events with time >= 0, non-self and valid IDs.
          avg_kill_time = sum(time) / event_kill_count.
          has_kill = true.
          Preserved even if time > estimated_match_duration.
      - Phase timing (conditioned on estimated_match_duration >= min_valid_duration_seconds and time <= duration):
          early_cutoff = early_cutoff_ratio * estimated_match_duration (default 1/3)
          mid_cutoff = mid_cutoff_ratio * estimated_match_duration (default 2/3)
          early_kills: 0 <= time < early_cutoff
          mid_kills: early_cutoff <= time < mid_cutoff
          late_kills: mid_cutoff <= time <= estimated_match_duration
          phase_eligible_kills = early_kills + mid_kills + late_kills
          early_kill_ratio = early_kills / phase_eligible_kills (NULL if phase_eligible_kills == 0)
          mid_kill_ratio = mid_kills / phase_eligible_kills (NULL if phase_eligible_kills == 0)
          late_kill_ratio = late_kills / phase_eligible_kills (NULL if phase_eligible_kills == 0)
      - Event key integrity:
          Events are NOT deduplicated by (match_id, killer_name, time). Multiple valid kills in
          the same second are preserved and counted individually.

    Outputs:
      - output_timing_parquet: Parquet dataset of unique (match_id, killer_name) profiles.
      - audit_output_dir / "event_join_audit.csv": Comprehensive event breakdown.
    """
    output_timing_parquet.parent.mkdir(parents=True, exist_ok=True)
    audit_output_dir.mkdir(parents=True, exist_ok=True)
    if not death_parquet_paths:
        raise FileNotFoundError("No death Parquet shards. Complete notebook 01 first.")

    # The numerical rules can run as diagnostics while their real-data evidence remains pending.
    timing_cfg = (features_config or {}).get("combat_timing", {})
    early_cutoff_ratio = float(timing_cfg.get("early_cutoff", 1.0 / 3.0))
    mid_cutoff_ratio = float(timing_cfg.get("mid_cutoff", 2.0 / 3.0))
    min_valid_duration = float(timing_cfg.get("min_valid_duration_seconds", 60.0))
    if not 0.0 < early_cutoff_ratio < mid_cutoff_ratio < 1.0:
        raise ValueError("Combat phase cutoffs must satisfy 0 < early < mid < 1")
    if min_valid_duration <= 0:
        raise ValueError("min_valid_duration_seconds must be positive")
    duration_status = timing_cfg.get("min_valid_duration_status", "pending_real_data_evidence")
    unit_status = timing_cfg.get("event_time_unit_status", "pending_source_or_consistency_evidence")
    enemy_status = timing_cfg.get("enemy_kill_eligibility_status", "pending_team_or_cause_evidence")
    research_gate = evaluate_combat_timing_research_gate(features_config or {})
    enemy_gate_ready = next(
        item["ready"] for item in research_gate["checks"]
        if item["parameter"] == "enemy_kill_eligibility"
    )

    safe_deaths = ", ".join("'" + p.resolve().as_posix().replace("'", "''") + "'" for p in death_parquet_paths)
    safe_meta = _sql_path(match_metadata_parquet)

    # Create views over death shards and match metadata
    con.execute(f"CREATE OR REPLACE VIEW raw_deaths_view AS SELECT * FROM read_parquet([{safe_deaths}]);")
    con.execute(f"CREATE OR REPLACE VIEW match_metadata_view AS SELECT * FROM read_parquet('{safe_meta}');")
    duplicate_matches = con.execute(
        "SELECT count(*) FROM (SELECT trim(CAST(match_id AS VARCHAR)) AS canonical_match_id "
        "FROM match_metadata_view WHERE match_id IS NOT NULL "
        "GROUP BY trim(CAST(match_id AS VARCHAR)) HAVING count(*) > 1)"
    ).fetchone()[0]
    if duplicate_matches:
        raise ValueError(f"match_metadata must have one row per match_id; found {duplicate_matches} duplicate keys")

    death_columns = {
        row[0]
        for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet([{safe_deaths}])").fetchall()
    }
    victim_column_available = "victim_name" in death_columns
    cause_column_available = "killed_by" in death_columns
    source_file_expr = "CAST(d.source_file AS VARCHAR)" if "source_file" in death_columns else "'lineage_unavailable'"
    source_row_expr = "CAST(d.source_row AS BIGINT)" if "source_row" in death_columns else "row_number() OVER ()"
    victim_expr = "CAST(d.victim_name AS VARCHAR)" if victim_column_available else "NULL::VARCHAR"
    cause_expr = "CAST(d.killed_by AS VARCHAR)" if cause_column_available else "NULL::VARCHAR"
    lineage_columns_available = {"source_file", "source_row"}.issubset(death_columns)
    lineage_missing_expr = (
        "CASE WHEN d.source_file IS NULL "
        "OR length(trim(CAST(d.source_file AS VARCHAR))) = 0 "
        "OR d.source_row IS NULL THEN 1 ELSE 0 END"
        if lineage_columns_available
        else "1"
    )
    duplicate_source_identity_expr = (
        "CASE WHEN d.source_file IS NULL "
        "OR length(trim(CAST(d.source_file AS VARCHAR))) = 0 "
        "OR d.source_row IS NULL THEN 0 "
        "WHEN count(*) OVER (PARTITION BY CAST(d.source_file AS VARCHAR), CAST(d.source_row AS BIGINT)) > 1 "
        "THEN 1 ELSE 0 END"
        if lineage_columns_available
        else "0"
    )
    roster_available = bool(player_match_base_parquet and player_match_base_parquet.is_file())
    if roster_available:
        con.execute(
            "CREATE OR REPLACE VIEW timing_roster_view AS SELECT DISTINCT trim(match_id) AS match_id, "
            f"trim(player_name) AS player_name FROM read_parquet('{_sql_path(player_match_base_parquet)}') "
            "WHERE match_id IS NOT NULL AND player_name IS NOT NULL"
        )
    else:
        con.execute(
            "CREATE OR REPLACE VIEW timing_roster_view AS "
            "SELECT NULL::VARCHAR AS match_id, NULL::VARCHAR AS player_name WHERE false"
        )

    # Preserve source identity; potential replayed rows are audited, never silently removed.
    con.execute(f"""
    CREATE OR REPLACE VIEW categorized_death_events_view AS
    SELECT
        {source_file_expr} AS source_file,
        {source_row_expr} AS source_row,
        d.match_id,
        d.killer_name,
        {victim_expr} AS victim_name,
        d.time,
        {cause_expr} AS killed_by,
        m.estimated_match_duration,
        {lineage_missing_expr} AS flag_missing_source_lineage,
        {duplicate_source_identity_expr} AS flag_duplicate_source_identity,
        CASE WHEN d.match_id IS NULL OR length(trim(d.match_id)) = 0 THEN 1 ELSE 0 END AS flag_missing_match_id,
        CASE WHEN d.killer_name IS NULL OR length(trim(d.killer_name)) = 0 THEN 1 ELSE 0 END AS flag_missing_killer,
        CASE WHEN {victim_expr} IS NULL OR length(trim({victim_expr})) = 0 THEN 1 ELSE 0 END AS flag_missing_victim,
        CASE WHEN d.killer_name IS NOT NULL AND {victim_expr} IS NOT NULL AND trim(d.killer_name) = trim({victim_expr}) THEN 1 ELSE 0 END AS flag_self_kill,
        CASE WHEN d.time IS NULL OR d.time < 0 OR NOT isfinite(d.time) THEN 1 ELSE 0 END AS flag_invalid_time,
        CASE WHEN d.match_id IS NOT NULL AND length(trim(d.match_id)) > 0 AND m.match_id IS NULL THEN 1 ELSE 0 END AS flag_unmatched_match,
        CASE WHEN m.estimated_match_duration IS NULL OR NOT isfinite(m.estimated_match_duration) OR m.estimated_match_duration <= 0 THEN 1 ELSE 0 END AS flag_invalid_duration,
        CASE WHEN m.estimated_match_duration > 0 AND m.estimated_match_duration < {min_valid_duration} THEN 1 ELSE 0 END AS flag_below_duration_threshold,
        CASE WHEN m.estimated_match_duration > 0 AND d.time > m.estimated_match_duration THEN 1 ELSE 0 END AS flag_out_of_range,
        CASE WHEN {cause_expr} IS NULL OR length(trim({cause_expr})) = 0 THEN 1 ELSE 0 END AS flag_missing_cause,
        CASE WHEN regexp_matches(lower(coalesce({cause_expr}, '')), 'bluezone|redzone|fall|drown|environment') THEN 1 ELSE 0 END AS flag_environment_cause,
        CASE WHEN d.killer_name IS NULL OR length(trim(d.killer_name)) = 0 THEN NULL WHEN rk.player_name IS NULL THEN 1 ELSE 0 END AS flag_killer_unmatched_roster,
        CASE WHEN {victim_expr} IS NULL OR length(trim({victim_expr})) = 0 THEN NULL WHEN rv.player_name IS NULL THEN 1 ELSE 0 END AS flag_victim_unmatched_roster,
        CASE WHEN count(*) OVER (PARTITION BY d.match_id, d.killer_name, {victim_expr}, d.time, {cause_expr}) > 1 THEN 1 ELSE 0 END AS flag_potential_replay
    FROM raw_deaths_view d
    LEFT JOIN match_metadata_view m ON trim(d.match_id) = trim(m.match_id)
    LEFT JOIN timing_roster_view rk ON trim(d.match_id) = rk.match_id AND trim(d.killer_name) = rk.player_name
    LEFT JOIN timing_roster_view rv ON trim(d.match_id) = rv.match_id AND trim({victim_expr}) = rv.player_name;
    """)

    valid_condition = """
        flag_missing_match_id = 0 AND flag_missing_killer = 0
        AND flag_self_kill = 0 AND flag_invalid_time = 0 AND flag_unmatched_match = 0
    """
    phase_condition = valid_condition + " AND flag_invalid_duration = 0 AND flag_below_duration_threshold = 0 AND flag_out_of_range = 0"
    copy_query_to_parquet(
        con,
        f"SELECT *, CASE WHEN flag_missing_source_lineage = 0 "
        f"THEN concat(source_file, ':', CAST(source_row AS VARCHAR)) "
        f"ELSE concat('pending_unverified_row:', CAST(row_number() OVER () AS VARCHAR)) "
        f"END AS event_source_key, "
        f"CASE WHEN {valid_condition} THEN 1 ELSE 0 END AS absolute_timing_eligible, "
        f"CASE WHEN {phase_condition} THEN 1 ELSE 0 END AS phase_timing_eligible "
        "FROM categorized_death_events_view",
        audit_output_dir / "event_validation_ledger.parquet",
    )

    audit_stats = con.execute("""
    SELECT
        COUNT(*) AS total_death_events,
        SUM(flag_missing_match_id) AS missing_match_id,
        SUM(flag_missing_killer) AS missing_killer,
        SUM(flag_missing_victim) AS missing_victim,
        SUM(flag_self_kill) AS self_kills,
        SUM(flag_invalid_time) AS negative_or_nan_time,
        SUM(flag_unmatched_match) AS unmatched_match,
        SUM(flag_invalid_duration), SUM(flag_below_duration_threshold), SUM(flag_out_of_range),
        SUM(flag_missing_cause), SUM(flag_environment_cause),
        SUM(flag_killer_unmatched_roster), SUM(flag_victim_unmatched_roster), SUM(flag_potential_replay),
        SUM(CASE WHEN flag_missing_match_id = 0 AND flag_missing_killer = 0 AND flag_self_kill = 0 AND flag_invalid_time = 0 AND flag_unmatched_match = 0 THEN 1 ELSE 0 END) AS valid_absolute_events,
        SUM(CASE WHEN flag_missing_match_id = 0 AND flag_missing_killer = 0 AND flag_self_kill = 0 AND flag_invalid_time = 0 AND flag_unmatched_match = 0 AND flag_invalid_duration = 0 AND flag_below_duration_threshold = 0 AND flag_out_of_range = 0 THEN 1 ELSE 0 END) AS valid_phase_events,
        SUM(flag_missing_source_lineage) AS missing_source_lineage_events,
        SUM(flag_duplicate_source_identity) AS duplicate_source_identity_events
    FROM categorized_death_events_view;
    """).fetchone()

    (
        total_death_events, missing_match_id, missing_killer, missing_victim, self_kills,
        invalid_time, unmatched_match, invalid_duration, short_duration_events,
        out_of_range_events, missing_cause, environment_cause, killer_unmatched,
        victim_unmatched, potential_replay, valid_absolute_events, valid_phase_events,
        missing_source_lineage_events,
        duplicate_source_identity_events,
    ) = [int(value or 0) for value in audit_stats]

    match_join_denominator = total_death_events - missing_match_id
    matched_match_events = match_join_denominator - unmatched_match
    named_killer_events = total_death_events - missing_killer
    named_victim_events = total_death_events - missing_victim
    matched_killer_events = named_killer_events - killer_unmatched if roster_available else None
    matched_victim_events = (
        named_victim_events - victim_unmatched
        if roster_available and victim_column_available
        else None
    )
    if duplicate_source_identity_events:
        event_identity_status = "source_lineage_conflict_pending"
    elif not lineage_columns_available:
        event_identity_status = "pending_source_lineage"
    elif missing_source_lineage_events:
        event_identity_status = "partial_source_lineage_pending"
    else:
        event_identity_status = "source_lineage_available"

    # Credited-killer timing view; enemy-kill verification remains a separate evidence gate.
    con.execute("""
    CREATE OR REPLACE VIEW valid_kill_events_view AS
    SELECT
        trim(match_id) AS match_id,
        trim(killer_name) AS killer_name,
        time,
        estimated_match_duration,
        flag_invalid_duration,
        flag_below_duration_threshold,
        flag_out_of_range
    FROM categorized_death_events_view
    WHERE flag_missing_match_id = 0
      AND flag_missing_killer = 0
      AND flag_self_kill = 0
      AND flag_invalid_time = 0
      AND flag_unmatched_match = 0;
    """)

    # Global aggregation per (match_id, killer_name)
    timing_aggregation_query = f"""
    SELECT
        match_id,
        killer_name,
        -- Absolute timing metrics (valid for all valid kill events)
        COUNT(*) AS event_kill_count,
        SUM(time) AS sum_kill_time,
        MIN(time) AS first_kill_time,
        SUM(time) / COUNT(*) AS avg_kill_time,
        true AS has_kill,
        -- Phase timing counts (only valid when match duration >= {min_valid_duration}s and time <= duration)
        SUM(CASE WHEN flag_invalid_duration = 0 AND flag_below_duration_threshold = 0 AND flag_out_of_range = 0 THEN 1 ELSE 0 END) AS phase_eligible_kill_count,
        SUM(CASE WHEN flag_invalid_duration = 0 AND flag_below_duration_threshold = 0 AND flag_out_of_range = 0 AND time < ({early_cutoff_ratio} * estimated_match_duration) THEN 1 ELSE 0 END) AS early_kills,
        SUM(CASE WHEN flag_invalid_duration = 0 AND flag_below_duration_threshold = 0 AND flag_out_of_range = 0 AND time >= ({early_cutoff_ratio} * estimated_match_duration) AND time < ({mid_cutoff_ratio} * estimated_match_duration) THEN 1 ELSE 0 END) AS mid_kills,
        SUM(CASE WHEN flag_invalid_duration = 0 AND flag_below_duration_threshold = 0 AND flag_out_of_range = 0 AND time >= ({mid_cutoff_ratio} * estimated_match_duration) AND time <= estimated_match_duration THEN 1 ELSE 0 END) AS late_kills,
        -- Phase ratios using phase_eligible_kills as denominator (NULL if 0 phase eligible kills)
        CASE
            WHEN SUM(CASE WHEN flag_invalid_duration = 0 AND flag_below_duration_threshold = 0 AND flag_out_of_range = 0 THEN 1 ELSE 0 END) > 0
            THEN CAST(SUM(CASE WHEN flag_invalid_duration = 0 AND flag_below_duration_threshold = 0 AND flag_out_of_range = 0 AND time < ({early_cutoff_ratio} * estimated_match_duration) THEN 1 ELSE 0 END) AS DOUBLE) /
                 SUM(CASE WHEN flag_invalid_duration = 0 AND flag_below_duration_threshold = 0 AND flag_out_of_range = 0 THEN 1 ELSE 0 END)
            ELSE NULL
        END AS early_kill_ratio,
        CASE
            WHEN SUM(CASE WHEN flag_invalid_duration = 0 AND flag_below_duration_threshold = 0 AND flag_out_of_range = 0 THEN 1 ELSE 0 END) > 0
            THEN CAST(SUM(CASE WHEN flag_invalid_duration = 0 AND flag_below_duration_threshold = 0 AND flag_out_of_range = 0 AND time >= ({early_cutoff_ratio} * estimated_match_duration) AND time < ({mid_cutoff_ratio} * estimated_match_duration) THEN 1 ELSE 0 END) AS DOUBLE) /
                 SUM(CASE WHEN flag_invalid_duration = 0 AND flag_below_duration_threshold = 0 AND flag_out_of_range = 0 THEN 1 ELSE 0 END)
            ELSE NULL
        END AS mid_kill_ratio,
        CASE
            WHEN SUM(CASE WHEN flag_invalid_duration = 0 AND flag_below_duration_threshold = 0 AND flag_out_of_range = 0 THEN 1 ELSE 0 END) > 0
            THEN CAST(SUM(CASE WHEN flag_invalid_duration = 0 AND flag_below_duration_threshold = 0 AND flag_out_of_range = 0 AND time >= ({mid_cutoff_ratio} * estimated_match_duration) AND time <= estimated_match_duration THEN 1 ELSE 0 END) AS DOUBLE) /
                 SUM(CASE WHEN flag_invalid_duration = 0 AND flag_below_duration_threshold = 0 AND flag_out_of_range = 0 THEN 1 ELSE 0 END)
            ELSE NULL
        END AS late_kill_ratio
    FROM valid_kill_events_view
    GROUP BY match_id, killer_name;
    """
    unique_killer_matches = copy_query_to_parquet(con, timing_aggregation_query, output_timing_parquet)

    audit_summary = {
        "total_death_events": total_death_events,
        "missing_match_id": missing_match_id,
        "missing_killer": missing_killer,
        "missing_victim": missing_victim,
        "self_kills": self_kills,
        "self_kill_audit_status": "available" if victim_column_available else "column_unavailable",
        "missing_killer_or_victim": missing_killer + missing_victim,
        "negative_or_nan_time": invalid_time,
        "unmatched_match": unmatched_match,
        "matched_match_events": matched_match_events,
        "match_join_denominator": match_join_denominator,
        "match_join_rate": matched_match_events / match_join_denominator if match_join_denominator else None,
        "valid_absolute_events": valid_absolute_events,
        "invalid_duration_events": invalid_duration,
        "below_duration_threshold_events": short_duration_events,
        "short_duration_events": short_duration_events,
        "out_of_range_time_events": out_of_range_events,
        "missing_cause_events": missing_cause,
        "environment_cause_events": environment_cause,
        "environment_cause_audit_status": "available" if cause_column_available else "column_unavailable",
        "killer_unmatched_roster_events": killer_unmatched if roster_available else None,
        "victim_unmatched_roster_events": victim_unmatched if roster_available and victim_column_available else None,
        "matched_killer_roster_events": matched_killer_events,
        "named_killer_event_denominator": named_killer_events,
        "killer_roster_join_rate": matched_killer_events / named_killer_events if roster_available and named_killer_events else None,
        "matched_victim_roster_events": matched_victim_events,
        "named_victim_event_denominator": named_victim_events,
        "victim_roster_join_rate": matched_victim_events / named_victim_events if matched_victim_events is not None and named_victim_events else None,
        "potential_replayed_event_rows": potential_replay,
        "valid_phase_events": valid_phase_events,
        "excluded_events": total_death_events - valid_absolute_events,
        "unique_killer_match_pairs": unique_killer_matches,
        "victim_field_audit_status": "available" if victim_column_available else "column_unavailable",
        "victim_roster_audit_status": (
            "available"
            if roster_available and victim_column_available
            else "column_unavailable"
            if not victim_column_available
            else "roster_unavailable"
        ),
        "source_lineage_columns_available": lineage_columns_available,
        "missing_source_lineage_events": missing_source_lineage_events,
        "duplicate_source_identity_events": duplicate_source_identity_events,
        "event_identity_policy": (
            "source_file+source_row; no content-key deduplication"
            if event_identity_status == "source_lineage_available"
            else "duplicate source identity conflict; rows preserved pending source repair"
            if event_identity_status == "source_lineage_conflict_pending"
            else "partial source lineage; missing rows use explicitly unverified run-local keys"
            if event_identity_status == "partial_source_lineage_pending"
            else "fallback row_number; identity pending/unavailable"
        ),
        "event_identity_status": event_identity_status,
        "enemy_kill_eligibility_status": enemy_status,
        "enemy_kill_eligibility_verified": enemy_gate_ready,
        "event_time_unit_status": unit_status,
        "min_duration_threshold_status": duration_status,
        "roster_match_status": "checked" if roster_available else "not_available",
    }
    atomic_write_csv(audit_output_dir / "event_join_audit.csv", pd.DataFrame([audit_summary]))
    logger.info(
        f"Combat timing aggregated: {unique_killer_matches} (match, killer) profiles -> {output_timing_parquet.name}. "
        f"Valid absolute events: {valid_absolute_events}, Valid phase events: {valid_phase_events}."
    )
    return audit_summary


def merge_player_match_and_timing(
    con: duckdb.DuckDBPyConnection,
    base_or_cleaned_parquet: Path,
    timing_or_meta_parquet: Path,
    output_or_timing_parquet: Optional[Path] = None,
    discrepancy_or_output_path: Optional[Path] = None,
    legacy_discrepancy_log_path: Optional[Path] = None,
) -> int:
    """Perform verified left-join of behavioral base with combat timing.

    Supports both:
      - Clean signature (Stage 03 -> Stage 04):
          merge_player_match_and_timing(con, base_parquet, timing_parquet, output_parquet, discrepancy_csv)
      - Legacy signature (direct from cleaned aggregate):
          merge_player_match_and_timing(con, cleaned_agg, meta_pq, timing_pq, output_pq, discrepancy_csv)

    Invariants:
      1. Left join preserves exact row count of input base (no row explosion or drop).
      2. No-kill players (player_kills == 0 and event_kill_count == 0) receive event_kill_count = 0,
         first_kill_time = NaN, avg_kill_time = NaN, ratios = NaN, has_kill = False.
      3. Discrepancies between aggregate player_kills and event_kill_count are audited completely
         (full discrepancy table saved without truncation).
      4. Generates event_timing_coverage.csv separating zero-kill, exact-match, discrepancy, and missing events.
    """
    if legacy_discrepancy_log_path is not None:
        safe_base = base_or_cleaned_parquet.resolve().as_posix().replace("'", "''")
        safe_meta = timing_or_meta_parquet.resolve().as_posix().replace("'", "''")
        safe_time = output_or_timing_parquet.resolve().as_posix().replace("'", "''")
        output_player_match_parquet = discrepancy_or_output_path
        discrepancy_log_path = legacy_discrepancy_log_path
        is_legacy = True
    else:
        safe_base = base_or_cleaned_parquet.resolve().as_posix().replace("'", "''")
        safe_meta = None
        safe_time = timing_or_meta_parquet.resolve().as_posix().replace("'", "''")
        output_player_match_parquet = output_or_timing_parquet
        discrepancy_log_path = discrepancy_or_output_path
        is_legacy = False

    output_player_match_parquet.parent.mkdir(parents=True, exist_ok=True)
    discrepancy_log_path.parent.mkdir(parents=True, exist_ok=True)
    safe_out = output_player_match_parquet.resolve().as_posix().replace("'", "''")

    duplicate_timing_keys = con.execute(f"""
        SELECT count(*) FROM (
            SELECT match_id, killer_name FROM read_parquet('{safe_time}')
            GROUP BY match_id, killer_name HAVING count(*) > 1
        );
    """).fetchone()[0]
    if duplicate_timing_keys:
        raise ValueError(f"combat_timing must be many-to-one; found {duplicate_timing_keys} duplicate keys")

    initial_rows = con.execute(f"SELECT count(*) FROM read_parquet('{safe_base}');").fetchone()[0]

    if is_legacy:
        join_query = f"""
            SELECT
                a.match_id,
                a.player_name,
                a.team_id,
                a.date,
                a.match_mode,
                a.party_size,
                m.observed_team_count,
                m.estimated_match_duration,
                -- Raw Behavior
                a.player_kills,
                a.player_dmg,
                a.player_dist_walk,
                a.player_dist_ride,
                a.player_assists,
                a.player_dbno,
                -- Targets
                a.player_survive_time,
                a.team_placement,
                -- Derived Placement
                CASE
                    WHEN m.observed_team_count > 1 AND a.team_placement BETWEEN 1 AND m.observed_team_count
                    THEN 1.0 - (CAST(a.team_placement - 1 AS DOUBLE) / (m.observed_team_count - 1))
                    ELSE NULL
                END AS normalized_placement,
                -- Derived Combat / Movement / Support
                CASE WHEN a.player_kills > 0 THEN a.player_dmg / a.player_kills ELSE NULL END AS damage_per_kill,
                (a.player_dist_walk + a.player_dist_ride) AS total_distance,
                CASE WHEN (a.player_dist_walk + a.player_dist_ride) > 0 THEN a.player_dist_walk / (a.player_dist_walk + a.player_dist_ride) ELSE NULL END AS walk_ratio,
                CASE WHEN (a.player_assists + a.player_kills) > 0 THEN CAST(a.player_assists AS DOUBLE) / (a.player_assists + a.player_kills) ELSE NULL END AS assist_ratio,
                -- Timing Absolute Features
                COALESCE(t.event_kill_count, 0) AS event_kill_count,
                t.sum_kill_time,
                t.first_kill_time,
                t.avg_kill_time,
                COALESCE(t.has_kill, false) AS has_kill,
                -- Timing Phase Features
                CASE WHEN t.event_kill_count IS NULL AND a.player_kills > 0 THEN NULL ELSE COALESCE(t.phase_eligible_kill_count, 0) END AS phase_eligible_kill_count,
                CASE WHEN t.event_kill_count IS NULL AND a.player_kills > 0 THEN NULL ELSE COALESCE(t.early_kills, 0) END AS early_kills,
                CASE WHEN t.event_kill_count IS NULL AND a.player_kills > 0 THEN NULL ELSE COALESCE(t.mid_kills, 0) END AS mid_kills,
                CASE WHEN t.event_kill_count IS NULL AND a.player_kills > 0 THEN NULL ELSE COALESCE(t.late_kills, 0) END AS late_kills,
                t.early_kill_ratio,
                t.mid_kill_ratio,
                t.late_kill_ratio,
                -- Target-derived Diagnostics
                CASE WHEN a.player_survive_time > 0 THEN (a.player_kills / (a.player_survive_time / 60.0)) ELSE NULL END AS kills_per_minute,
                CASE WHEN a.player_survive_time > 0 THEN (a.player_dmg / (a.player_survive_time / 60.0)) ELSE NULL END AS damage_per_minute,
                CASE WHEN a.player_survive_time > 0 THEN (a.player_dist_walk / a.player_survive_time) ELSE NULL END AS walk_velocity,
                CASE WHEN a.player_survive_time > 0 THEN (a.player_dist_ride / a.player_survive_time) ELSE NULL END AS ride_velocity,
                -- Flags
                CASE WHEN t.event_kill_count IS NOT NULL THEN true ELSE false END AS has_event_record,
                CASE
                    WHEN a.player_kills = 0 AND t.event_kill_count IS NULL THEN 'confirmed_no_kill_no_event'
                    WHEN a.player_kills = 0 AND t.event_kill_count > 0 THEN 'aggregate_zero_event_present'
                    WHEN a.player_kills > 0 AND t.event_kill_count IS NULL THEN 'aggregate_kill_event_missing'
                    WHEN a.player_kills = t.event_kill_count THEN 'event_count_exact'
                    WHEN t.event_kill_count < a.player_kills THEN 'event_count_partial'
                    ELSE 'event_count_exceeds_aggregate'
                END AS timing_coverage_status,
                a.player_kills - COALESCE(t.event_kill_count, 0) AS kill_discrepancy_signed,
                ABS(a.player_kills - COALESCE(t.event_kill_count, 0)) AS kill_discrepancy
            FROM read_parquet('{safe_base}') a
            LEFT JOIN read_parquet('{safe_meta}') m ON a.match_id = m.match_id
            LEFT JOIN read_parquet('{safe_time}') t ON a.match_id = t.match_id AND a.player_name = t.killer_name
        """
    else:
        join_query = f"""
            SELECT
                b.*,
                -- Timing Absolute Features
                COALESCE(t.event_kill_count, 0) AS event_kill_count,
                t.sum_kill_time,
                t.first_kill_time,
                t.avg_kill_time,
                COALESCE(t.has_kill, false) AS has_kill,
                -- Timing Phase Features
                CASE WHEN t.event_kill_count IS NULL AND b.player_kills > 0 THEN NULL ELSE COALESCE(t.phase_eligible_kill_count, 0) END AS phase_eligible_kill_count,
                CASE WHEN t.event_kill_count IS NULL AND b.player_kills > 0 THEN NULL ELSE COALESCE(t.early_kills, 0) END AS early_kills,
                CASE WHEN t.event_kill_count IS NULL AND b.player_kills > 0 THEN NULL ELSE COALESCE(t.mid_kills, 0) END AS mid_kills,
                CASE WHEN t.event_kill_count IS NULL AND b.player_kills > 0 THEN NULL ELSE COALESCE(t.late_kills, 0) END AS late_kills,
                t.early_kill_ratio,
                t.mid_kill_ratio,
                t.late_kill_ratio,
                -- Target-derived Diagnostics
                CASE WHEN b.player_survive_time > 0 THEN (b.player_kills / (b.player_survive_time / 60.0)) ELSE NULL END AS kills_per_minute,
                CASE WHEN b.player_survive_time > 0 THEN (b.player_dmg / (b.player_survive_time / 60.0)) ELSE NULL END AS damage_per_minute,
                CASE WHEN b.player_survive_time > 0 THEN (b.player_dist_walk / b.player_survive_time) ELSE NULL END AS walk_velocity,
                CASE WHEN b.player_survive_time > 0 THEN (b.player_dist_ride / b.player_survive_time) ELSE NULL END AS ride_velocity,
                -- Flags
                CASE WHEN t.event_kill_count IS NOT NULL THEN true ELSE false END AS has_event_record,
                CASE
                    WHEN b.player_kills = 0 AND t.event_kill_count IS NULL THEN 'confirmed_no_kill_no_event'
                    WHEN b.player_kills = 0 AND t.event_kill_count > 0 THEN 'aggregate_zero_event_present'
                    WHEN b.player_kills > 0 AND t.event_kill_count IS NULL THEN 'aggregate_kill_event_missing'
                    WHEN b.player_kills = t.event_kill_count THEN 'event_count_exact'
                    WHEN t.event_kill_count < b.player_kills THEN 'event_count_partial'
                    ELSE 'event_count_exceeds_aggregate'
                END AS timing_coverage_status,
                b.player_kills - COALESCE(t.event_kill_count, 0) AS kill_discrepancy_signed,
                ABS(b.player_kills - COALESCE(t.event_kill_count, 0)) AS kill_discrepancy
            FROM read_parquet('{safe_base}') b
            LEFT JOIN read_parquet('{safe_time}') t ON b.match_id = t.match_id AND b.player_name = t.killer_name
        """

    final_rows = copy_query_to_parquet(
        con, join_query, output_player_match_parquet, expected_rows=initial_rows
    )

    output_columns = {
        row[0] for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{safe_out}')").fetchall()
    }
    mode_expr = "coalesce(team_size_mode, 'unknown')" if "team_size_mode" in output_columns else "coalesce(match_mode, 'unknown')"

    # Full player-match discrepancy ledger; notebook may display only its largest rows.
    discrepancy_df = con.execute(f"""
        SELECT
            match_id,
            player_name,
            {mode_expr} AS team_size_mode,
            player_kills,
            event_kill_count,
            phase_eligible_kill_count,
            kill_discrepancy_signed,
            kill_discrepancy,
            timing_coverage_status
        FROM read_parquet('{safe_out}')
        ORDER BY kill_discrepancy DESC, match_id, player_name;
    """).df()
    atomic_write_csv(discrepancy_log_path, discrepancy_df)

    # Player-match coverage by mode; event-level eligibility remains in event_join_audit.csv.
    coverage_df = con.execute(f"""
        SELECT
            {mode_expr} AS team_size_mode,
            timing_coverage_status AS category,
            COUNT(*) AS player_match_count,
            ROUND(COUNT(*) * 100.0 / NULLIF({final_rows}, 0), 4) AS all_player_match_percentage,
            SUM(event_kill_count) AS absolute_event_count,
            SUM(COALESCE(phase_eligible_kill_count, 0)) AS phase_eligible_event_count,
            SUM(player_kills) AS aggregate_kill_count
        FROM read_parquet('{safe_out}')
        GROUP BY 1, 2
        ORDER BY 1, player_match_count DESC;
    """).df()
    coverage_path = discrepancy_log_path.parent / "event_timing_coverage.csv"
    atomic_write_csv(coverage_path, coverage_df)

    logger.info(
        f"Successfully merged player_match_features: {final_rows} rows preserved. "
        f"Discrepancy audit -> {discrepancy_log_path.name}, Coverage audit -> {coverage_path.name}."
    )
    return final_rows
