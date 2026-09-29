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
    error_flags_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Clean aggregate dataset across shards: audit duplicates, missing keys, and invalid values.

    Implements a strict sequential removal cascade where rows_before - rows_removed = rows_after,
    while maintaining a separate overlapping error flags audit to prevent double-counting.
    """
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
    total_raw_rows = con.execute("SELECT count(*) FROM raw_aggregate_view;").fetchone()[0]

    # --- PART 1: OVERLAPPING ERROR FLAGS AUDIT (Independent diagnostic checks) ---
    exact_duplicates = con.execute("""
        SELECT count(*) - count(DISTINCT (
            match_id, player_name, team_id, date, match_mode, party_size,
            player_kills, player_dmg, player_dist_walk, player_dist_ride,
            player_survive_time, team_placement, game_size, player_assists, player_dbno
        ))
        FROM raw_aggregate_view;
    """).fetchone()[0]

    missing_match_id = con.execute("SELECT count(*) FROM raw_aggregate_view WHERE match_id IS NULL OR length(trim(match_id)) = 0;").fetchone()[0]
    missing_team_id = con.execute("SELECT count(*) FROM raw_aggregate_view WHERE team_id IS NULL OR length(trim(team_id)) = 0;").fetchone()[0]
    missing_player_name = con.execute("SELECT count(*) FROM raw_aggregate_view WHERE player_name IS NULL OR length(trim(player_name)) = 0;").fetchone()[0]

    invalid_domain_rows = con.execute("""
        SELECT count(*) FROM raw_aggregate_view
        WHERE player_kills IS NULL OR player_kills < 0
           OR player_dmg IS NULL OR player_dmg < 0 OR isnan(player_dmg) OR isinf(player_dmg)
           OR player_dist_walk IS NULL OR player_dist_walk < 0 OR isnan(player_dist_walk) OR isinf(player_dist_walk)
           OR player_dist_ride IS NULL OR player_dist_ride < 0 OR isnan(player_dist_ride) OR isinf(player_dist_ride)
           OR player_survive_time IS NULL OR player_survive_time < 0 OR isnan(player_survive_time) OR isinf(player_survive_time)
           OR team_placement IS NULL OR team_placement <= 0;
    """).fetchone()[0]

    # Identity key conflicts: same (match_id, player_name) with distinct stats
    key_conflicts = con.execute("""
        WITH distinct_records AS (
            SELECT DISTINCT * FROM raw_aggregate_view
            WHERE match_id IS NOT NULL AND length(trim(match_id)) > 0
              AND player_name IS NOT NULL AND length(trim(player_name)) > 0
        ),
        counts AS (
            SELECT trim(match_id) AS mid, trim(player_name) AS pname, count(*) as c
            FROM distinct_records
            GROUP BY trim(match_id), trim(player_name)
            HAVING count(*) > 1
        )
        SELECT COALESCE(sum(c), 0) FROM counts;
    """).fetchone()[0]

    # Save overlapping error flags report
    flags_file = error_flags_path or (removal_log_path.parent / "error_flags.csv")
    flags_records = [
        {"flag_name": "exact_duplicates", "affected_rows": exact_duplicates, "note": "All columns 100% identical"},
        {"flag_name": "missing_match_id", "affected_rows": missing_match_id, "note": "Null or empty match identifier"},
        {"flag_name": "missing_team_id", "affected_rows": missing_team_id, "note": "Null or empty team identifier"},
        {"flag_name": "missing_player_name", "affected_rows": missing_player_name, "note": "Null player name (kept for current match/RQ1)"},
        {"flag_name": "invalid_domain_values", "affected_rows": invalid_domain_rows, "note": "Negative or non-finite numeric stats"},
        {"flag_name": "key_conflicts", "affected_rows": key_conflicts, "note": "Same (match, player) with conflicting stats"},
    ]
    atomic_write_csv(flags_file, pd.DataFrame(flags_records))

    # --- PART 2: SEQUENTIAL REMOVAL CASCADE (Zero double-counting) ---
    # Step 1: Remove exact duplicates
    con.execute("CREATE OR REPLACE TEMP VIEW step1_dedup AS SELECT DISTINCT * FROM raw_aggregate_view;")
    n1 = con.execute("SELECT count(*) FROM step1_dedup;").fetchone()[0]
    r1 = total_raw_rows - n1

    # Step 2: Remove missing required identifiers (match_id, team_id)
    con.execute("""
        CREATE OR REPLACE TEMP VIEW step2_valid_keys AS
        SELECT * FROM step1_dedup
        WHERE match_id IS NOT NULL AND length(trim(match_id)) > 0
          AND team_id IS NOT NULL AND length(trim(team_id)) > 0;
    """)
    n2 = con.execute("SELECT count(*) FROM step2_valid_keys;").fetchone()[0]
    r2 = n1 - n2

    # Step 3: Remove invalid numeric values and non-finite constraints
    con.execute("""
        CREATE OR REPLACE TEMP VIEW step3_valid_domain AS
        SELECT * FROM step2_valid_keys
        WHERE player_kills IS NOT NULL AND player_kills >= 0
          AND player_dmg IS NOT NULL AND player_dmg >= 0 AND NOT (isnan(player_dmg) OR isinf(player_dmg))
          AND player_dist_walk IS NOT NULL AND player_dist_walk >= 0 AND NOT (isnan(player_dist_walk) OR isinf(player_dist_walk))
          AND player_dist_ride IS NOT NULL AND player_dist_ride >= 0 AND NOT (isnan(player_dist_ride) OR isinf(player_dist_ride))
          AND player_survive_time IS NOT NULL AND player_survive_time >= 0 AND NOT (isnan(player_survive_time) OR isinf(player_survive_time))
          AND team_placement IS NOT NULL AND team_placement > 0;
    """)
    n3 = con.execute("SELECT count(*) FROM step3_valid_domain;").fetchone()[0]
    r3 = n2 - n3

    # Step 4: Isolate identity key conflicts (quarantine ambiguous duplicate player-matches)
    # When a player has conflicting rows in the same match, do NOT pick 'first' arbitrarily
    con.execute("""
        CREATE OR REPLACE TEMP VIEW step4_resolved_conflicts AS
        WITH conflict_keys AS (
            SELECT trim(match_id) AS mid, trim(player_name) AS pname
            FROM step3_valid_domain
            WHERE player_name IS NOT NULL AND length(trim(player_name)) > 0
            GROUP BY trim(match_id), trim(player_name)
            HAVING count(*) > 1
        )
        SELECT s.* FROM step3_valid_domain s
        LEFT JOIN conflict_keys c
          ON trim(s.match_id) = c.mid AND trim(s.player_name) = c.pname
        WHERE c.mid IS NULL;
    """)
    n4 = con.execute("SELECT count(*) FROM step4_resolved_conflicts;").fetchone()[0]
    r4 = n3 - n4

    # Final Step: Canonicalize identifiers and add task-specific validity flags
    cleaning_query = """
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
            team_placement,
            (player_survive_time IS NOT NULL AND player_survive_time >= 0) AS valid_survival,
            (team_placement IS NOT NULL AND team_placement > 0) AS valid_placement
        FROM step4_resolved_conflicts;
    """

    clean_rows = copy_query_to_parquet(con, cleaning_query, output_cleaned_parquet)
    dropped_rows = total_raw_rows - clean_rows

    # Record removal ledger (reconciliation: rows_before - rows_removed = rows_after)
    removal_records = [
        {"step": 0, "stage": "raw_input", "reason": "initial_raw_records", "rows_before": total_raw_rows, "rows_removed": 0, "rows_after": total_raw_rows, "rows_affected": total_raw_rows},
        {"step": 1, "stage": "cleaning", "reason": "exact_duplicates", "rows_before": total_raw_rows, "rows_removed": r1, "rows_after": n1, "rows_affected": r1},
        {"step": 2, "stage": "cleaning", "reason": "missing_match_or_team_id", "rows_before": n1, "rows_removed": r2, "rows_after": n2, "rows_affected": r2},
        {"step": 3, "stage": "cleaning", "reason": "invalid_domain_values", "rows_before": n2, "rows_removed": r3, "rows_after": n3, "rows_affected": r3},
        {"step": 4, "stage": "cleaning", "reason": "key_conflicts", "rows_before": n3, "rows_removed": r4, "rows_after": n4, "rows_affected": r4},
        {"step": 5, "stage": "cleaning", "reason": "total_dropped_records", "rows_before": total_raw_rows, "rows_removed": dropped_rows, "rows_after": clean_rows, "rows_affected": dropped_rows},
        {"step": 6, "stage": "cleaning", "reason": "validated_clean_records", "rows_before": 0, "rows_removed": 0, "rows_after": clean_rows, "rows_affected": clean_rows},
    ]
    atomic_write_csv(removal_log_path, pd.DataFrame(removal_records))

    summary = {
        "total_raw_rows": total_raw_rows,
        "clean_rows": clean_rows,
        "dropped_rows": dropped_rows,
        "exact_duplicates": exact_duplicates,
        "missing_player_name": missing_player_name,
        "missing_match_id": missing_match_id,
        "missing_team_id": missing_team_id,
        "invalid_domain_rows": invalid_domain_rows,
        "key_conflicts": key_conflicts,
        "step_removals": {"r1_exact": r1, "r2_keys": r2, "r3_domain": r3, "r4_conflicts": r4},
    }
    logger.info(f"Cleaning finished: {clean_rows}/{total_raw_rows} rows retained. Dropped: {dropped_rows}.")
    return summary
