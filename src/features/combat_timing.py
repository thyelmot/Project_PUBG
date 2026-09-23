from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import duckdb
import pandas as pd
from src.data.io import atomic_write_json
from src.utils.logging import get_logger

logger = get_logger("pubg_combat_timing")


def extract_and_aggregate_combat_timing(
    con: duckdb.DuckDBPyConnection,
    death_parquet_paths: List[Path],
    match_metadata_parquet: Path,
    output_timing_parquet: Path,
    audit_output_dir: Path,
) -> Dict[str, Any]:
    """Aggregate combat timing from death events grouped by (match_id, killer_name).

    Formulas:
      early_cutoff = 1/3 * duration
      mid_cutoff = 2/3 * duration
      early_kills: time < early_cutoff
      mid_kills: early_cutoff <= time < mid_cutoff
      late_kills: time >= mid_cutoff
      avg_kill_time: sum(time) / count
    """
    output_timing_parquet.parent.mkdir(parents=True, exist_ok=True)
    audit_output_dir.mkdir(parents=True, exist_ok=True)

    safe_deaths = ", ".join("'" + p.resolve().as_posix().replace("'", "''") + "'" for p in death_parquet_paths)
    safe_meta = str(match_metadata_parquet.resolve()).replace("\\", "/")
    safe_out = str(output_timing_parquet.resolve()).replace("\\", "/")

    # Create view over death shards and match metadata
    con.execute(f"CREATE OR REPLACE VIEW raw_deaths_view AS SELECT * FROM read_parquet([{safe_deaths}]);")
    con.execute(f"CREATE OR REPLACE VIEW match_metadata_view AS SELECT * FROM read_parquet('{safe_meta}');")

    total_death_events = con.execute("SELECT count(*) FROM raw_deaths_view;").fetchone()[0]

    # Filter valid enemy kill events: killer exists, not self-kill, positive time
    valid_events_query = """
    CREATE OR REPLACE VIEW valid_kill_events_view AS
    SELECT
        d.match_id,
        trim(d.killer_name) AS killer_name,
        d.time,
        m.estimated_match_duration
    FROM raw_deaths_view d
    JOIN match_metadata_view m ON d.match_id = m.match_id
    WHERE d.killer_name IS NOT NULL
      AND length(trim(d.killer_name)) > 0
      AND d.victim_name IS NOT NULL
      AND trim(d.killer_name) != trim(d.victim_name)
      AND d.time >= 0
      AND m.estimated_match_duration > 0;
    """
    con.execute(valid_events_query)
    valid_enemy_kills = con.execute("SELECT count(*) FROM valid_kill_events_view;").fetchone()[0]

    # Global aggregation per (match_id, killer_name)
    timing_aggregation_query = f"""
    COPY (
        SELECT
            match_id,
            killer_name,
            COUNT(*) AS event_kill_count,
            MIN(time) AS first_kill_time,
            AVG(time) AS avg_kill_time,
            SUM(CASE WHEN time < (1.0/3.0) * estimated_match_duration THEN 1 ELSE 0 END) AS early_kills,
            SUM(CASE WHEN time >= (1.0/3.0) * estimated_match_duration AND time < (2.0/3.0) * estimated_match_duration THEN 1 ELSE 0 END) AS mid_kills,
            SUM(CASE WHEN time >= (2.0/3.0) * estimated_match_duration THEN 1 ELSE 0 END) AS late_kills,
            -- Safe ratios
            CAST(SUM(CASE WHEN time < (1.0/3.0) * estimated_match_duration THEN 1 ELSE 0 END) AS DOUBLE) / COUNT(*) AS early_kill_ratio,
            CAST(SUM(CASE WHEN time >= (1.0/3.0) * estimated_match_duration AND time < (2.0/3.0) * estimated_match_duration THEN 1 ELSE 0 END) AS DOUBLE) / COUNT(*) AS mid_kill_ratio,
            CAST(SUM(CASE WHEN time >= (2.0/3.0) * estimated_match_duration THEN 1 ELSE 0 END) AS DOUBLE) / COUNT(*) AS late_kill_ratio,
            true AS has_kill
        FROM valid_kill_events_view
        GROUP BY match_id, killer_name
    ) TO '{safe_out}' (FORMAT PARQUET, COMPRESSION 'SNAPPY');
    """
    con.execute(timing_aggregation_query)

    unique_killer_matches = con.execute(f"SELECT count(*) FROM read_parquet('{safe_out}');").fetchone()[0]

    audit_summary = {
        "total_death_events": total_death_events,
        "valid_enemy_kills": valid_enemy_kills,
        "excluded_events": total_death_events - valid_enemy_kills,
        "unique_killer_match_pairs": unique_killer_matches,
    }
    pd.DataFrame([audit_summary]).to_csv(audit_output_dir / "event_join_audit.csv", index=False)
    logger.info(f"Combat timing aggregated: {unique_killer_matches} (match, killer) profiles -> {output_timing_parquet.name}")
    return audit_summary


def merge_player_match_and_timing(
    con: duckdb.DuckDBPyConnection,
    cleaned_aggregate_parquet: Path,
    match_metadata_parquet: Path,
    combat_timing_parquet: Path,
    output_player_match_parquet: Path,
    discrepancy_log_path: Path,
) -> int:
    """Perform verified left-join of behavioral base with combat timing.

    Invariants:
      1. Left join preserves exact row count of cleaned aggregate base (no row explosion).
      2. No-kill players (kills == 0) receive event_kill_count = 0, first_kill_time = NaN, has_kill = False.
      3. Discrepancies between aggregate kills and death events are recorded.
    """
    output_player_match_parquet.parent.mkdir(parents=True, exist_ok=True)
    discrepancy_log_path.parent.mkdir(parents=True, exist_ok=True)

    safe_agg = str(cleaned_aggregate_parquet.resolve()).replace("\\", "/")
    safe_meta = str(match_metadata_parquet.resolve()).replace("\\", "/")
    safe_time = str(combat_timing_parquet.resolve()).replace("\\", "/")
    safe_out = str(output_player_match_parquet.resolve()).replace("\\", "/")

    # Check input row count
    initial_rows = con.execute(f"SELECT count(*) FROM read_parquet('{safe_agg}');").fetchone()[0]

    join_query = f"""
    COPY (
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
                WHEN m.observed_team_count > 1 AND a.team_placement >= 1
                THEN 1.0 - (CAST(a.team_placement - 1 AS DOUBLE) / (m.observed_team_count - 1))
                ELSE NULL
            END AS normalized_placement,
            -- Derived Combat / Movement / Support
            CASE WHEN a.player_kills > 0 THEN a.player_dmg / a.player_kills ELSE NULL END AS damage_per_kill,
            (a.player_dist_walk + a.player_dist_ride) AS total_distance,
            CASE WHEN (a.player_dist_walk + a.player_dist_ride) > 0 THEN a.player_dist_walk / (a.player_dist_walk + a.player_dist_ride) ELSE NULL END AS walk_ratio,
            CASE WHEN (a.player_assists + a.player_kills) > 0 THEN CAST(a.player_assists AS DOUBLE) / (a.player_assists + a.player_kills) ELSE NULL END AS assist_ratio,
            -- Timing Features from Left Join
            COALESCE(t.event_kill_count, 0) AS event_kill_count,
            t.first_kill_time,
            t.avg_kill_time,
            COALESCE(t.early_kills, 0) AS early_kills,
            COALESCE(t.mid_kills, 0) AS mid_kills,
            COALESCE(t.late_kills, 0) AS late_kills,
            t.early_kill_ratio,
            t.mid_kill_ratio,
            t.late_kill_ratio,
            COALESCE(t.has_kill, false) AS has_kill,
            -- Diagnostics
            CASE WHEN a.player_survive_time > 0 THEN (a.player_kills / (a.player_survive_time / 60.0)) ELSE NULL END AS kills_per_minute,
            CASE WHEN a.player_survive_time > 0 THEN (a.player_dmg / (a.player_survive_time / 60.0)) ELSE NULL END AS damage_per_minute,
            CASE WHEN a.player_survive_time > 0 THEN (a.player_dist_walk / a.player_survive_time) ELSE NULL END AS walk_velocity,
            CASE WHEN a.player_survive_time > 0 THEN (a.player_dist_ride / a.player_survive_time) ELSE NULL END AS ride_velocity,
            -- Flags
            CASE WHEN t.event_kill_count IS NOT NULL THEN true ELSE false END AS has_event_record,
            ABS(a.player_kills - COALESCE(t.event_kill_count, 0)) AS kill_discrepancy
        FROM read_parquet('{safe_agg}') a
        LEFT JOIN read_parquet('{safe_meta}') m ON a.match_id = m.match_id
        LEFT JOIN read_parquet('{safe_time}') t ON a.match_id = t.match_id AND a.player_name = t.killer_name
    ) TO '{safe_out}' (FORMAT PARQUET, COMPRESSION 'SNAPPY');
    """

    con.execute(join_query)
    final_rows = con.execute(f"SELECT count(*) FROM read_parquet('{safe_out}');").fetchone()[0]

    if final_rows != initial_rows:
        raise ValueError(f"Left join invariant violated! Initial rows: {initial_rows}, Final joined rows: {final_rows}")

    # Generate discrepancy audit
    discrepancy_df = con.execute(f"""
        SELECT
            kill_discrepancy,
            COUNT(*) AS player_count,
            AVG(player_kills) AS avg_agg_kills,
            AVG(event_kill_count) AS avg_event_kills
        FROM read_parquet('{safe_out}')
        GROUP BY kill_discrepancy
        ORDER BY kill_discrepancy ASC
        LIMIT 20;
    """).df()
    discrepancy_df.to_csv(discrepancy_log_path, index=False)

    logger.info(f"Successfully constructed final player_match_features: {final_rows} rows.")
    return final_rows
