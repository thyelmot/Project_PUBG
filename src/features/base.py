from pathlib import Path
from typing import Any, Dict, Optional
import duckdb
import pandas as pd
import numpy as np

from src.data.io import copy_query_to_parquet, atomic_write_csv
from src.features.registry import FeatureRegistry
from src.utils.logging import get_logger

logger = get_logger("pubg_base_features")


def build_player_match_base(
    con: duckdb.DuckDBPyConnection,
    cleaned_aggregate_parquet: Path,
    match_metadata_parquet: Path,
    output_base_parquet: Path,
    validation_csv_path: Optional[Path] = None,
    dictionary_csv_path: Optional[Path] = None,
) -> int:
    """Build player-match base features: Combat, Movement, Support, Normalized Placement,
    and verified perspective / team size modes.

    Guarantees:
      - 100% row preservation from cleaned_aggregate_parquet (N_base == N_clean).
      - Strict mathematical formulas:
          damage_per_kill = player_dmg / player_kills (NaN if player_kills == 0)
          total_distance = player_dist_walk + player_dist_ride
          walk_ratio = player_dist_walk / total_distance (NaN if total_distance == 0)
          assist_ratio = player_assists / (player_assists + player_kills) (NaN if sum == 0)
          normalized_placement = 1.0 - (team_placement - 1.0) / (N_teams - 1.0)
      - Normalized placement is ONLY computed for roster-complete matches where
        N_teams > 1 and 1 <= team_placement <= N_teams. Out-of-bounds placements
        are set to NULL and valid_placement is False (never clipped to hide errors).
      - Perspective mode and team_size_mode are properly decoupled, with an explicit
        'unknown' category for non-standard party sizes.
      - Exports feature dictionary and validation summary if paths provided.
    """
    if not cleaned_aggregate_parquet.is_file():
        raise FileNotFoundError(f"Cleaned aggregate Parquet not found: {cleaned_aggregate_parquet}")
    if not match_metadata_parquet.is_file():
        raise FileNotFoundError(f"Match metadata Parquet not found: {match_metadata_parquet}")

    output_base_parquet.parent.mkdir(parents=True, exist_ok=True)
    safe_clean = cleaned_aggregate_parquet.resolve().as_posix().replace("'", "''")
    safe_meta = match_metadata_parquet.resolve().as_posix().replace("'", "''")

    initial_rows = con.execute(f"SELECT count(*) FROM read_parquet('{safe_clean}')").fetchone()[0]

    base_query = f"""
        SELECT
            -- Identifiers & contextual attributes
            trim(a.match_id) AS match_id,
            a.player_name,
            trim(a.team_id) AS team_id,
            a.date,
            a.match_mode,
            CASE
                WHEN lower(trim(a.match_mode)) LIKE '%fpp%' THEN 'fpp'
                WHEN lower(trim(a.match_mode)) LIKE '%tpp%' THEN 'tpp'
                ELSE 'unknown'
            END AS perspective_mode,
            a.party_size,
            CASE
                WHEN a.party_size = 1 THEN 'solo'
                WHEN a.party_size = 2 THEN 'duo'
                WHEN a.party_size = 4 THEN 'squad'
                ELSE 'unknown'
            END AS team_size_mode,
            a.game_size,
            m.observed_team_count,
            m.observed_player_count,
            COALESCE(m.is_roster_complete, false) AS is_roster_complete,
            m.estimated_match_duration,

            -- Raw Behavioral Stats
            a.player_kills,
            a.player_dmg,
            a.player_dist_walk,
            a.player_dist_ride,
            a.player_assists,
            a.player_dbno,

            -- Derived Behavioral Stats (Safe division: division by 0 yields NULL / NaN)
            CASE WHEN a.player_kills > 0 THEN a.player_dmg / a.player_kills ELSE NULL END AS damage_per_kill,
            (a.player_dist_walk + a.player_dist_ride) AS total_distance,
            CASE WHEN (a.player_dist_walk + a.player_dist_ride) > 0
                 THEN a.player_dist_walk / (a.player_dist_walk + a.player_dist_ride)
                 ELSE NULL
            END AS walk_ratio,
            CASE WHEN (a.player_assists + a.player_kills) > 0
                 THEN CAST(a.player_assists AS DOUBLE) / (a.player_assists + a.player_kills)
                 ELSE NULL
            END AS assist_ratio,

            -- Outcomes & Task Validity Flags
            a.player_survive_time,
            a.team_placement,
            CASE
                WHEN m.observed_team_count > 1
                 AND a.team_placement BETWEEN 1 AND m.observed_team_count
                 AND COALESCE(m.is_roster_complete, false)
                THEN 1.0 - (CAST(a.team_placement - 1 AS DOUBLE) / (m.observed_team_count - 1))
                ELSE NULL
            END AS normalized_placement,
            (a.player_survive_time IS NOT NULL AND a.player_survive_time >= 0) AS valid_survival,
            (m.observed_team_count > 1
             AND a.team_placement BETWEEN 1 AND m.observed_team_count
             AND COALESCE(m.is_roster_complete, false)) AS valid_placement
        FROM read_parquet('{safe_clean}') a
        LEFT JOIN read_parquet('{safe_meta}') m ON a.match_id = m.match_id
    """

    base_rows = copy_query_to_parquet(con, base_query, output_base_parquet, expected_rows=initial_rows)
    logger.info(f"Built player_match_base: {base_rows} rows -> {output_base_parquet.name}")

    # Export Feature Dictionary if requested
    if dictionary_csv_path:
        registry = FeatureRegistry()
        registry.export_dictionary_csv(Path(dictionary_csv_path))

    # Export Feature Validation Summary if requested
    if validation_csv_path:
        safe_base = output_base_parquet.resolve().as_posix().replace("'", "''")
        val_df = con.execute(f"""
            SELECT
                'player_kills' AS feature_name, 'combat' AS feature_group,
                count(*) AS total_rows, count(player_kills) AS valid_count,
                count(*) - count(player_kills) AS null_count,
                min(player_kills) AS min_val, max(player_kills) AS max_val,
                avg(player_kills) AS mean_val, stddev(player_kills) AS std_val,
                avg(CASE WHEN player_kills = 0 THEN 1.0 ELSE 0.0 END) AS zero_rate
            FROM read_parquet('{safe_base}')
            UNION ALL
            SELECT
                'player_dmg', 'combat', count(*), count(player_dmg),
                count(*) - count(player_dmg), min(player_dmg), max(player_dmg),
                avg(player_dmg), stddev(player_dmg),
                avg(CASE WHEN player_dmg = 0 THEN 1.0 ELSE 0.0 END)
            FROM read_parquet('{safe_base}')
            UNION ALL
            SELECT
                'damage_per_kill', 'combat', count(*), count(damage_per_kill),
                count(*) - count(damage_per_kill), min(damage_per_kill), max(damage_per_kill),
                avg(damage_per_kill), stddev(damage_per_kill),
                avg(CASE WHEN damage_per_kill = 0 THEN 1.0 ELSE 0.0 END)
            FROM read_parquet('{safe_base}')
            UNION ALL
            SELECT
                'player_dist_walk', 'movement', count(*), count(player_dist_walk),
                count(*) - count(player_dist_walk), min(player_dist_walk), max(player_dist_walk),
                avg(player_dist_walk), stddev(player_dist_walk),
                avg(CASE WHEN player_dist_walk = 0 THEN 1.0 ELSE 0.0 END)
            FROM read_parquet('{safe_base}')
            UNION ALL
            SELECT
                'player_dist_ride', 'movement', count(*), count(player_dist_ride),
                count(*) - count(player_dist_ride), min(player_dist_ride), max(player_dist_ride),
                avg(player_dist_ride), stddev(player_dist_ride),
                avg(CASE WHEN player_dist_ride = 0 THEN 1.0 ELSE 0.0 END)
            FROM read_parquet('{safe_base}')
            UNION ALL
            SELECT
                'total_distance', 'movement', count(*), count(total_distance),
                count(*) - count(total_distance), min(total_distance), max(total_distance),
                avg(total_distance), stddev(total_distance),
                avg(CASE WHEN total_distance = 0 THEN 1.0 ELSE 0.0 END)
            FROM read_parquet('{safe_base}')
            UNION ALL
            SELECT
                'walk_ratio', 'movement', count(*), count(walk_ratio),
                count(*) - count(walk_ratio), min(walk_ratio), max(walk_ratio),
                avg(walk_ratio), stddev(walk_ratio),
                avg(CASE WHEN walk_ratio = 0 THEN 1.0 ELSE 0.0 END)
            FROM read_parquet('{safe_base}')
            UNION ALL
            SELECT
                'player_assists', 'support', count(*), count(player_assists),
                count(*) - count(player_assists), min(player_assists), max(player_assists),
                avg(player_assists), stddev(player_assists),
                avg(CASE WHEN player_assists = 0 THEN 1.0 ELSE 0.0 END)
            FROM read_parquet('{safe_base}')
            UNION ALL
            SELECT
                'player_dbno', 'support', count(*), count(player_dbno),
                count(*) - count(player_dbno), min(player_dbno), max(player_dbno),
                avg(player_dbno), stddev(player_dbno),
                avg(CASE WHEN player_dbno = 0 THEN 1.0 ELSE 0.0 END)
            FROM read_parquet('{safe_base}')
            UNION ALL
            SELECT
                'assist_ratio', 'support', count(*), count(assist_ratio),
                count(*) - count(assist_ratio), min(assist_ratio), max(assist_ratio),
                avg(assist_ratio), stddev(assist_ratio),
                avg(CASE WHEN assist_ratio = 0 THEN 1.0 ELSE 0.0 END)
            FROM read_parquet('{safe_base}')
            UNION ALL
            SELECT
                'player_survive_time', 'outcome', count(*), count(player_survive_time),
                count(*) - count(player_survive_time), min(player_survive_time), max(player_survive_time),
                avg(player_survive_time), stddev(player_survive_time),
                avg(CASE WHEN player_survive_time = 0 THEN 1.0 ELSE 0.0 END)
            FROM read_parquet('{safe_base}')
            UNION ALL
            SELECT
                'team_placement', 'outcome', count(*), count(team_placement),
                count(*) - count(team_placement), min(team_placement), max(team_placement),
                avg(team_placement), stddev(team_placement),
                avg(CASE WHEN team_placement = 0 THEN 1.0 ELSE 0.0 END)
            FROM read_parquet('{safe_base}')
            UNION ALL
            SELECT
                'normalized_placement', 'outcome', count(*), count(normalized_placement),
                count(*) - count(normalized_placement), min(normalized_placement), max(normalized_placement),
                avg(normalized_placement), stddev(normalized_placement),
                avg(CASE WHEN normalized_placement = 0 THEN 1.0 ELSE 0.0 END)
            FROM read_parquet('{safe_base}');
        """).df()
        val_df["null_pct"] = (val_df["null_count"] / val_df["total_rows"]) * 100.0
        val_df["status"] = np.where(
            val_df["feature_name"].isin(["normalized_placement", "damage_per_kill", "walk_ratio", "assist_ratio"]),
            "valid_conditional_null",
            np.where(val_df["null_count"] == 0, "valid_complete", "warning_unexpected_null")
        )
        atomic_write_csv(Path(validation_csv_path), val_df)

    return base_rows
