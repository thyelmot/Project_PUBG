from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd

from src.data.io import copy_query_to_parquet, atomic_write_csv
from src.utils.logging import get_logger

logger = get_logger("pubg_cleaning")

BUSINESS_COLUMNS = [
    "match_id", "player_name", "team_id", "date", "match_mode", "party_size",
    "game_size", "player_assists", "player_dbno", "player_dist_ride",
    "player_dist_walk", "player_dmg", "player_kills", "player_survive_time",
    "team_placement",
]


def _quoted(columns: List[str]) -> str:
    return ", ".join(f'"{column}"' for column in columns)


def audit_and_clean_aggregate_data(
    con: duckdb.DuckDBPyConnection,
    aggregate_parquet_paths: List[Path],
    output_cleaned_parquet: Path,
    removal_log_path: Path,
    error_flags_path: Optional[Path] = None,
    identity_conflicts_path: Optional[Path] = None,
    task_exclusion_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Audit and clean aggregate shards without conflating row and task exclusions."""
    if not aggregate_parquet_paths:
        raise FileNotFoundError(
            "No aggregate Parquet shards were provided. Run notebook 01 with the same "
            "PUBG_STORAGE_MODE and PUBG_DRIVE_PROJECT_ROOT before notebook 02."
        )
    output_cleaned_parquet.parent.mkdir(parents=True, exist_ok=True)
    removal_log_path.parent.mkdir(parents=True, exist_ok=True)

    parquet_globs = [path.resolve().as_posix().replace("'", "''") for path in aggregate_parquet_paths]
    paths_sql = ", ".join(f"'{path}'" for path in parquet_globs)
    con.execute(f"CREATE OR REPLACE VIEW raw_aggregate_view AS SELECT * FROM read_parquet([{paths_sql}]);")

    available = [row[0] for row in con.execute("DESCRIBE SELECT * FROM raw_aggregate_view").fetchall()]
    missing = sorted(set(BUSINESS_COLUMNS) - set(available))
    if missing:
        raise ValueError(f"Aggregate data is missing required cleaning columns: {missing}")
    lineage_columns = [column for column in ("source_file", "source_row") if column in available]
    business_sql = _quoted(BUSINESS_COLUMNS)
    total_raw_rows = con.execute("SELECT count(*) FROM raw_aggregate_view").fetchone()[0]

    exact_duplicates = con.execute(
        f"SELECT count(*) - count(DISTINCT ({business_sql})) FROM raw_aggregate_view"
    ).fetchone()[0]
    missing_match_id = con.execute(
        "SELECT count(*) FROM raw_aggregate_view WHERE match_id IS NULL OR length(trim(match_id)) = 0"
    ).fetchone()[0]
    missing_team_id = con.execute(
        "SELECT count(*) FROM raw_aggregate_view WHERE team_id IS NULL OR length(trim(team_id)) = 0"
    ).fetchone()[0]
    missing_player_name = con.execute(
        "SELECT count(*) FROM raw_aggregate_view WHERE player_name IS NULL OR length(trim(player_name)) = 0"
    ).fetchone()[0]

    core_domain_condition = """
        (player_kills IS NOT NULL AND (player_kills < 0 OR player_kills != floor(player_kills)))
        OR (player_assists IS NOT NULL AND (player_assists < 0 OR player_assists != floor(player_assists)))
        OR (player_dbno IS NOT NULL AND (player_dbno < 0 OR player_dbno != floor(player_dbno)))
        OR (party_size IS NOT NULL AND (party_size <= 0 OR party_size != floor(party_size)))
        OR (game_size IS NOT NULL AND (game_size <= 0 OR game_size != floor(game_size)))
        OR (player_dmg IS NOT NULL AND (player_dmg < 0 OR isnan(player_dmg) OR isinf(player_dmg)))
        OR (player_dist_walk IS NOT NULL AND (player_dist_walk < 0 OR isnan(player_dist_walk) OR isinf(player_dist_walk)))
        OR (player_dist_ride IS NOT NULL AND (player_dist_ride < 0 OR isnan(player_dist_ride) OR isinf(player_dist_ride)))
    """
    invalid_domain_rows = con.execute(
        f"SELECT count(*) FROM raw_aggregate_view WHERE {core_domain_condition}"
    ).fetchone()[0]
    missing_behavior_rows = con.execute("""
        SELECT count(*) FROM raw_aggregate_view
        WHERE player_kills IS NULL OR player_assists IS NULL OR player_dbno IS NULL
           OR player_dmg IS NULL OR player_dist_walk IS NULL OR player_dist_ride IS NULL
    """).fetchone()[0]
    invalid_survival_target = con.execute("""
        SELECT count(*) FROM raw_aggregate_view
        WHERE player_survive_time IS NULL OR player_survive_time < 0
           OR isnan(player_survive_time) OR isinf(player_survive_time)
    """).fetchone()[0]
    invalid_placement_target = con.execute("""
        SELECT count(*) FROM raw_aggregate_view
        WHERE team_placement IS NULL OR team_placement <= 0
    """).fetchone()[0]

    key_conflicts = con.execute(f"""
        WITH distinct_records AS (
            SELECT DISTINCT {business_sql}
            FROM raw_aggregate_view
            WHERE match_id IS NOT NULL AND length(trim(match_id)) > 0
              AND player_name IS NOT NULL AND length(trim(player_name)) > 0
        ),
        counts AS (
            SELECT trim(match_id) AS mid, trim(player_name) AS pname, count(*) AS c
            FROM distinct_records
            GROUP BY trim(match_id), trim(player_name)
            HAVING count(*) > 1
        )
        SELECT COALESCE(sum(c), 0) FROM counts
    """).fetchone()[0]

    flags_file = error_flags_path or (removal_log_path.parent / "error_flags.csv")
    flags_records = [
        {"flag_name": "exact_duplicates", "affected_rows": exact_duplicates, "unit": "rows", "note": "Business columns identical; lineage excluded from equality"},
        {"flag_name": "missing_match_id", "affected_rows": missing_match_id, "unit": "rows", "note": "Null or empty match identifier"},
        {"flag_name": "missing_team_id", "affected_rows": missing_team_id, "unit": "rows", "note": "Null or empty team identifier"},
        {"flag_name": "missing_player_name", "affected_rows": missing_player_name, "unit": "rows", "note": "Kept for eligible match/current-row tasks; excluded from player-history tasks"},
        {"flag_name": "missing_behavior_values", "affected_rows": missing_behavior_rows, "unit": "rows", "note": "Retained and handled by task-specific complete-case/imputation policy"},
        {"flag_name": "invalid_domain_values", "affected_rows": invalid_domain_rows, "unit": "rows", "note": "Negative, non-finite or non-integer core behavior values"},
        {"flag_name": "invalid_survival_target", "affected_rows": invalid_survival_target, "unit": "rows", "note": "Retained for tasks not using survival target"},
        {"flag_name": "invalid_placement_target", "affected_rows": invalid_placement_target, "unit": "rows", "note": "Retained for tasks not using placement target"},
        {"flag_name": "key_conflicts", "affected_rows": key_conflicts, "unit": "rows", "note": "Same normalized (match, player) with conflicting business values"},
    ]
    atomic_write_csv(flags_file, pd.DataFrame(flags_records))

    order_sql = _quoted(lineage_columns) if lineage_columns else business_sql
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW step1_dedup AS
        SELECT * EXCLUDE (_dedup_rank)
        FROM (
            SELECT *, row_number() OVER (
                PARTITION BY {business_sql}
                ORDER BY {order_sql}
            ) AS _dedup_rank
            FROM raw_aggregate_view
        )
        WHERE _dedup_rank = 1
    """)
    n1 = con.execute("SELECT count(*) FROM step1_dedup").fetchone()[0]
    r1 = total_raw_rows - n1

    con.execute("""
        CREATE OR REPLACE TEMP VIEW step2_valid_keys AS
        SELECT * FROM step1_dedup
        WHERE match_id IS NOT NULL AND length(trim(match_id)) > 0
          AND team_id IS NOT NULL AND length(trim(team_id)) > 0
    """)
    n2 = con.execute("SELECT count(*) FROM step2_valid_keys").fetchone()[0]
    r2 = n1 - n2

    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW step3_valid_domain AS
        SELECT * FROM step2_valid_keys
        WHERE NOT ({core_domain_condition})
    """)
    n3 = con.execute("SELECT count(*) FROM step3_valid_domain").fetchone()[0]
    r3 = n2 - n3

    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW identity_conflict_keys AS
        WITH distinct_records AS (
            SELECT DISTINCT {business_sql}
            FROM step3_valid_domain
            WHERE player_name IS NOT NULL AND length(trim(player_name)) > 0
        )
        SELECT trim(match_id) AS mid, trim(player_name) AS pname
        FROM distinct_records
        GROUP BY trim(match_id), trim(player_name)
        HAVING count(*) > 1
    """)
    conflict_file = identity_conflicts_path or (removal_log_path.parent / "identity_conflicts.parquet")
    copy_query_to_parquet(con, """
        SELECT s.*,
               trim(s.match_id) AS normalized_match_id,
               trim(s.player_name) AS normalized_player_name
        FROM step3_valid_domain s
        INNER JOIN identity_conflict_keys c
          ON trim(s.match_id) = c.mid AND trim(s.player_name) = c.pname
        ORDER BY normalized_match_id, normalized_player_name
    """, conflict_file)

    con.execute("""
        CREATE OR REPLACE TEMP VIEW step4_resolved_conflicts AS
        SELECT s.* FROM step3_valid_domain s
        LEFT JOIN identity_conflict_keys c
          ON trim(s.match_id) = c.mid AND trim(s.player_name) = c.pname
        WHERE c.mid IS NULL
    """)
    n4 = con.execute("SELECT count(*) FROM step4_resolved_conflicts").fetchone()[0]
    r4 = n3 - n4

    lineage_select = "".join(f', "{column}"' for column in lineage_columns)
    cleaning_query = f"""
        SELECT
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
            {lineage_select},
            (player_survive_time IS NOT NULL AND player_survive_time >= 0
             AND NOT (isnan(player_survive_time) OR isinf(player_survive_time))) AS valid_survival,
            (team_placement IS NOT NULL AND team_placement > 0) AS valid_placement,
            (player_kills IS NULL OR player_assists IS NULL OR player_dbno IS NULL
             OR player_dmg IS NULL OR player_dist_walk IS NULL OR player_dist_ride IS NULL) AS has_behavior_missing
        FROM step4_resolved_conflicts
    """
    clean_rows = copy_query_to_parquet(con, cleaning_query, output_cleaned_parquet)
    dropped_rows = total_raw_rows - clean_rows

    removal_records = [
        {"step": 0, "stage": "raw_input", "rule": "R0", "reason": "initial_raw_records", "rows_before": total_raw_rows, "rows_removed": 0, "rows_after": total_raw_rows, "rows_affected": total_raw_rows, "example_count": 0, "version": "cleaning_v3"},
        {"step": 1, "stage": "cleaning", "rule": "R1", "reason": "exact_duplicates", "rows_before": total_raw_rows, "rows_removed": r1, "rows_after": n1, "rows_affected": r1, "example_count": min(r1, 5), "version": "cleaning_v3"},
        {"step": 2, "stage": "cleaning", "rule": "R2", "reason": "missing_match_or_team_id", "rows_before": n1, "rows_removed": r2, "rows_after": n2, "rows_affected": r2, "example_count": min(r2, 5), "version": "cleaning_v3"},
        {"step": 3, "stage": "cleaning", "rule": "R3", "reason": "invalid_core_behavior_domain", "rows_before": n2, "rows_removed": r3, "rows_after": n3, "rows_affected": r3, "example_count": min(r3, 5), "version": "cleaning_v3"},
        {"step": 4, "stage": "cleaning", "rule": "R4", "reason": "ambiguous_identity_conflicts", "rows_before": n3, "rows_removed": r4, "rows_after": n4, "rows_affected": r4, "example_count": min(r4, 5), "version": "cleaning_v3"},
        {"step": 5, "stage": "cleaning", "rule": "SUMMARY", "reason": "total_dropped_records", "rows_before": total_raw_rows, "rows_removed": dropped_rows, "rows_after": clean_rows, "rows_affected": dropped_rows, "example_count": 0, "version": "cleaning_v3"},
        {"step": 6, "stage": "cleaning", "rule": "SUMMARY", "reason": "validated_clean_records", "rows_before": 0, "rows_removed": 0, "rows_after": clean_rows, "rows_affected": clean_rows, "example_count": 0, "version": "cleaning_v3"},
    ]
    atomic_write_csv(removal_log_path, pd.DataFrame(removal_records))

    task_file = task_exclusion_path or (removal_log_path.parent / "task_exclusion_ledger.csv")
    task_counts = con.execute(f"""
        SELECT
            count(*) AS denominator_rows,
            count(*) FILTER (WHERE NOT valid_survival) AS invalid_survival,
            count(*) FILTER (WHERE NOT valid_placement) AS invalid_placement,
            count(*) FILTER (WHERE player_name IS NULL) AS missing_player_identity,
            count(*) FILTER (WHERE has_behavior_missing) AS missing_behavior
        FROM read_parquet('{output_cleaned_parquet.resolve().as_posix().replace("'", "''")}')
    """).fetchone()
    task_records = [
        {"task": "survival", "exclusion_reason": "invalid_survival_target", "affected_rows": task_counts[1], "denominator_rows": task_counts[0], "scope": "cleaned rows", "policy": "exclude only from tasks requiring survival target"},
        {"task": "placement", "exclusion_reason": "invalid_placement_target", "affected_rows": task_counts[2], "denominator_rows": task_counts[0], "scope": "cleaned rows", "policy": "exclude only from tasks requiring placement target"},
        {"task": "player_profile_history", "exclusion_reason": "missing_player_identity", "affected_rows": task_counts[3], "denominator_rows": task_counts[0], "scope": "cleaned rows", "policy": "exclude only from player-identity tasks; never create UNKNOWN player"},
        {"task": "feature_complete_case", "exclusion_reason": "missing_behavior_value", "affected_rows": task_counts[4], "denominator_rows": task_counts[0], "scope": "cleaned rows", "policy": "retain now; downstream task declares complete-case or train-only imputation"},
    ]
    atomic_write_csv(task_file, pd.DataFrame(task_records))

    summary = {
        "total_raw_rows": total_raw_rows,
        "clean_rows": clean_rows,
        "dropped_rows": dropped_rows,
        "exact_duplicates": exact_duplicates,
        "missing_player_name": missing_player_name,
        "missing_match_id": missing_match_id,
        "missing_team_id": missing_team_id,
        "missing_behavior_rows": missing_behavior_rows,
        "invalid_domain_rows": invalid_domain_rows,
        "invalid_survival_target": invalid_survival_target,
        "invalid_placement_target": invalid_placement_target,
        "key_conflicts": key_conflicts,
        "identity_conflicts_path": str(conflict_file),
        "task_exclusion_path": str(task_file),
        "step_removals": {"r1_exact": r1, "r2_keys": r2, "r3_domain": r3, "r4_conflicts": r4},
    }
    logger.info(f"Cleaning finished: {clean_rows}/{total_raw_rows} rows retained. Dropped: {dropped_rows}.")
    return summary