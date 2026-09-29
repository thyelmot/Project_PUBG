from pathlib import Path
from typing import Any, Dict, List, Optional
import duckdb
import pandas as pd
from src.data.io import copy_query_to_parquet, atomic_write_csv
from src.utils.logging import get_logger

logger = get_logger("pubg_combat_timing")


def extract_and_aggregate_combat_timing(
    con: duckdb.DuckDBPyConnection,
    death_parquet_paths: List[Path],
    match_metadata_parquet: Path,
    output_timing_parquet: Path,
    audit_output_dir: Path,
    features_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Aggregate combat timing from death events grouped by (match_id, killer_name).

    Formulas and Semantics:
      - Absolute timing:
          first_kill_time = min(time) for all valid kill events (time >= 0, non-self, valid IDs).
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

    # Read configuration parameters with robust defaults
    timing_cfg = (features_config or {}).get("combat_timing", {})
    early_cutoff_ratio = float(timing_cfg.get("early_cutoff", 1.0 / 3.0))
    mid_cutoff_ratio = float(timing_cfg.get("mid_cutoff", 2.0 / 3.0))
    min_valid_duration = float(timing_cfg.get("min_valid_duration_seconds", 60.0))

    safe_deaths = ", ".join("'" + p.resolve().as_posix().replace("'", "''") + "'" for p in death_parquet_paths)
    safe_meta = match_metadata_parquet.resolve().as_posix().replace("'", "''")

    # Create views over death shards and match metadata
    con.execute(f"CREATE OR REPLACE VIEW raw_deaths_view AS SELECT * FROM read_parquet([{safe_deaths}]);")
    con.execute(f"CREATE OR REPLACE VIEW match_metadata_view AS SELECT * FROM read_parquet('{safe_meta}');")

    # Categorize raw death events to audit missing IDs, self-kills, out-of-range, and duration validity
    con.execute(f"""
    CREATE OR REPLACE VIEW categorized_death_events_view AS
    SELECT
        d.match_id,
        d.killer_name,
        d.victim_name,
        d.time,
        m.estimated_match_duration,
        CASE WHEN d.killer_name IS NULL OR length(trim(d.killer_name)) = 0 OR d.victim_name IS NULL OR length(trim(d.victim_name)) = 0 THEN 1 ELSE 0 END AS flag_missing_name,
        CASE WHEN d.killer_name IS NOT NULL AND d.victim_name IS NOT NULL AND trim(d.killer_name) = trim(d.victim_name) THEN 1 ELSE 0 END AS flag_self_kill,
        CASE WHEN d.time IS NULL OR d.time < 0 OR NOT isfinite(d.time) THEN 1 ELSE 0 END AS flag_invalid_time,
        CASE WHEN m.match_id IS NULL THEN 1 ELSE 0 END AS flag_unmatched_match,
        CASE WHEN m.estimated_match_duration IS NULL OR m.estimated_match_duration < {min_valid_duration} THEN 1 ELSE 0 END AS flag_short_duration,
        CASE WHEN d.time > m.estimated_match_duration THEN 1 ELSE 0 END AS flag_out_of_range
    FROM raw_deaths_view d
    LEFT JOIN match_metadata_view m ON trim(d.match_id) = m.match_id;
    """)

    # Compute audit metrics across all raw events
    audit_stats = con.execute("""
    SELECT
        COUNT(*) AS total_death_events,
        SUM(flag_self_kill) AS self_kills,
        SUM(flag_missing_name) AS missing_killer_or_victim,
        SUM(flag_invalid_time) AS negative_or_nan_time,
        SUM(flag_unmatched_match) AS unmatched_match,
        SUM(CASE WHEN flag_missing_name = 0 AND flag_self_kill = 0 AND flag_invalid_time = 0 AND flag_unmatched_match = 0 THEN 1 ELSE 0 END) AS valid_absolute_events,
        SUM(CASE WHEN flag_missing_name = 0 AND flag_self_kill = 0 AND flag_invalid_time = 0 AND flag_unmatched_match = 0 AND flag_short_duration = 1 THEN 1 ELSE 0 END) AS short_duration_events,
        SUM(CASE WHEN flag_missing_name = 0 AND flag_self_kill = 0 AND flag_invalid_time = 0 AND flag_unmatched_match = 0 AND flag_short_duration = 0 AND flag_out_of_range = 1 THEN 1 ELSE 0 END) AS out_of_range_time_events,
        SUM(CASE WHEN flag_missing_name = 0 AND flag_self_kill = 0 AND flag_invalid_time = 0 AND flag_unmatched_match = 0 AND flag_short_duration = 0 AND flag_out_of_range = 0 THEN 1 ELSE 0 END) AS valid_phase_events
    FROM categorized_death_events_view;
    """).fetchone()

    total_death_events = int(audit_stats[0] or 0)
    self_kills = int(audit_stats[1] or 0)
    missing_name = int(audit_stats[2] or 0)
    invalid_time = int(audit_stats[3] or 0)
    unmatched_match = int(audit_stats[4] or 0)
    valid_absolute_events = int(audit_stats[5] or 0)
    short_duration_events = int(audit_stats[6] or 0)
    out_of_range_events = int(audit_stats[7] or 0)
    valid_phase_events = int(audit_stats[8] or 0)

    # Valid kill events view for aggregation (preserves multiple kills in the same second)
    con.execute("""
    CREATE OR REPLACE VIEW valid_kill_events_view AS
    SELECT
        trim(match_id) AS match_id,
        trim(killer_name) AS killer_name,
        time,
        estimated_match_duration,
        flag_short_duration,
        flag_out_of_range
    FROM categorized_death_events_view
    WHERE flag_missing_name = 0
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
        MIN(time) AS first_kill_time,
        AVG(time) AS avg_kill_time,
        true AS has_kill,
        -- Phase timing counts (only valid when match duration >= {min_valid_duration}s and time <= duration)
        SUM(CASE WHEN flag_short_duration = 0 AND flag_out_of_range = 0 AND time < ({early_cutoff_ratio} * estimated_match_duration) THEN 1 ELSE 0 END) AS early_kills,
        SUM(CASE WHEN flag_short_duration = 0 AND flag_out_of_range = 0 AND time >= ({early_cutoff_ratio} * estimated_match_duration) AND time < ({mid_cutoff_ratio} * estimated_match_duration) THEN 1 ELSE 0 END) AS mid_kills,
        SUM(CASE WHEN flag_short_duration = 0 AND flag_out_of_range = 0 AND time >= ({mid_cutoff_ratio} * estimated_match_duration) AND time <= estimated_match_duration THEN 1 ELSE 0 END) AS late_kills,
        -- Phase ratios using phase_eligible_kills as denominator (NULL if 0 phase eligible kills)
        CASE
            WHEN SUM(CASE WHEN flag_short_duration = 0 AND flag_out_of_range = 0 THEN 1 ELSE 0 END) > 0
            THEN CAST(SUM(CASE WHEN flag_short_duration = 0 AND flag_out_of_range = 0 AND time < ({early_cutoff_ratio} * estimated_match_duration) THEN 1 ELSE 0 END) AS DOUBLE) /
                 SUM(CASE WHEN flag_short_duration = 0 AND flag_out_of_range = 0 THEN 1 ELSE 0 END)
            ELSE NULL
        END AS early_kill_ratio,
        CASE
            WHEN SUM(CASE WHEN flag_short_duration = 0 AND flag_out_of_range = 0 THEN 1 ELSE 0 END) > 0
            THEN CAST(SUM(CASE WHEN flag_short_duration = 0 AND flag_out_of_range = 0 AND time >= ({early_cutoff_ratio} * estimated_match_duration) AND time < ({mid_cutoff_ratio} * estimated_match_duration) THEN 1 ELSE 0 END) AS DOUBLE) /
                 SUM(CASE WHEN flag_short_duration = 0 AND flag_out_of_range = 0 THEN 1 ELSE 0 END)
            ELSE NULL
        END AS mid_kill_ratio,
        CASE
            WHEN SUM(CASE WHEN flag_short_duration = 0 AND flag_out_of_range = 0 THEN 1 ELSE 0 END) > 0
            THEN CAST(SUM(CASE WHEN flag_short_duration = 0 AND flag_out_of_range = 0 AND time >= ({mid_cutoff_ratio} * estimated_match_duration) AND time <= estimated_match_duration THEN 1 ELSE 0 END) AS DOUBLE) /
                 SUM(CASE WHEN flag_short_duration = 0 AND flag_out_of_range = 0 THEN 1 ELSE 0 END)
            ELSE NULL
        END AS late_kill_ratio
    FROM valid_kill_events_view
    GROUP BY match_id, killer_name;
    """
    unique_killer_matches = copy_query_to_parquet(con, timing_aggregation_query, output_timing_parquet)

    audit_summary = {
        "total_death_events": total_death_events,
        "self_kills": self_kills,
        "missing_killer_or_victim": missing_name,
        "negative_or_nan_time": invalid_time,
        "unmatched_match": unmatched_match,
        "valid_absolute_events": valid_absolute_events,
        "valid_enemy_kills": valid_absolute_events,  # Backward-compatible alias
        "short_duration_events": short_duration_events,
        "out_of_range_time_events": out_of_range_events,
        "valid_phase_events": valid_phase_events,
        "excluded_events": total_death_events - valid_absolute_events,
        "unique_killer_match_pairs": unique_killer_matches,
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

    # Check input row count
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
                t.first_kill_time,
                t.avg_kill_time,
                COALESCE(t.has_kill, false) AS has_kill,
                -- Timing Phase Features
                COALESCE(t.early_kills, 0) AS early_kills,
                COALESCE(t.mid_kills, 0) AS mid_kills,
                COALESCE(t.late_kills, 0) AS late_kills,
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
                t.first_kill_time,
                t.avg_kill_time,
                COALESCE(t.has_kill, false) AS has_kill,
                -- Timing Phase Features
                COALESCE(t.early_kills, 0) AS early_kills,
                COALESCE(t.mid_kills, 0) AS mid_kills,
                COALESCE(t.late_kills, 0) AS late_kills,
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
                ABS(b.player_kills - COALESCE(t.event_kill_count, 0)) AS kill_discrepancy
            FROM read_parquet('{safe_base}') b
            LEFT JOIN read_parquet('{safe_time}') t ON b.match_id = t.match_id AND b.player_name = t.killer_name
        """

    final_rows = copy_query_to_parquet(
        con, join_query, output_player_match_parquet, expected_rows=initial_rows
    )

    # 1. Full Discrepancy Table (No LIMIT truncation)
    discrepancy_df = con.execute(f"""
        SELECT
            kill_discrepancy,
            COUNT(*) AS player_count,
            ROUND(AVG(player_kills), 4) AS avg_agg_kills,
            ROUND(AVG(event_kill_count), 4) AS avg_event_kills
        FROM read_parquet('{safe_out}')
        GROUP BY kill_discrepancy
        ORDER BY kill_discrepancy ASC;
    """).df()
    atomic_write_csv(discrepancy_log_path, discrepancy_df)

    # 2. Timing Coverage Table (Categorizes 0-kills, missing events, discrepancies)
    coverage_df = con.execute(f"""
        SELECT
            CASE
                WHEN player_kills = 0 AND event_kill_count = 0 THEN 'kills_zero_no_event'
                WHEN player_kills = 0 AND event_kill_count > 0 THEN 'kills_zero_with_event'
                WHEN player_kills > 0 AND event_kill_count = 0 THEN 'kills_pos_missing_event'
                WHEN player_kills > 0 AND player_kills = event_kill_count THEN 'kills_pos_exact_match'
                WHEN player_kills > 0 AND event_kill_count > 0 AND player_kills != event_kill_count THEN 'kills_pos_discrepancy'
                ELSE 'other'
            END AS category,
            COUNT(*) AS player_count,
            ROUND(COUNT(*) * 100.0 / {final_rows}, 4) AS percentage,
            ROUND(AVG(player_kills), 2) AS avg_agg_kills,
            ROUND(AVG(event_kill_count), 2) AS avg_event_kills
        FROM read_parquet('{safe_out}')
        GROUP BY 1
        ORDER BY player_count DESC;
    """).df()
    coverage_path = discrepancy_log_path.parent / "event_timing_coverage.csv"
    atomic_write_csv(coverage_path, coverage_df)

    logger.info(
        f"Successfully merged player_match_features: {final_rows} rows preserved. "
        f"Discrepancy audit -> {discrepancy_log_path.name}, Coverage audit -> {coverage_path.name}."
    )
    return final_rows
