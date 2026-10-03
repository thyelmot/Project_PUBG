from typing import Tuple
import pandas as pd
from src.utils.logging import get_logger

logger = get_logger("pubg_profiles")

PROFILE_AUDIT_COLUMNS = [
    "kill_active_matches", "support_active_matches", "timing_observed_matches",
    "mean_kills_valid_matches", "std_kills_valid_matches",
    "mean_damage_valid_matches", "std_damage_valid_matches",
    "mean_damage_per_kill_valid_matches", "mean_walk_distance_valid_matches",
    "mean_ride_distance_valid_matches", "mean_walk_ratio_valid_matches",
    "mean_assists_valid_matches", "mean_dbno_valid_matches",
    "mean_assist_ratio_valid_matches", "avg_early_kill_ratio_valid_matches",
    "avg_mid_kill_ratio_valid_matches", "avg_late_kill_ratio_valid_matches",
    "early_combat_match_ratio_valid_matches", "std_kills_status", "std_damage_status",
]


PROFILE_MEANS = {'player_kills': 'mean_kills', 'player_dmg': 'mean_damage',
         'damage_per_kill': 'mean_damage_per_kill', 'player_dist_walk': 'mean_walk_distance',
         'player_dist_ride': 'mean_ride_distance', 'walk_ratio': 'mean_walk_ratio',
         'player_assists': 'mean_assists', 'player_dbno': 'mean_dbno', 'assist_ratio': 'mean_assist_ratio'}


def profile_aggregate_expressions():
    """Canonical Design 3 formulas and denominators for small and full-data paths."""
    aggregates = [
        'count(*) AS games_played',
        'count(*) FILTER (WHERE player_kills > 0) AS kill_active_matches',
        'count(*) FILTER (WHERE player_assists > 0 OR player_dbno > 0) AS support_active_matches',
        "count(*) FILTER (WHERE timing_coverage_status = 'confirmed_no_kill_no_event' OR phase_eligible_kill_count > 0) AS timing_observed_matches"
    ]
    for col, alias in PROFILE_MEANS.items():
        aggregates += [f'avg({col}) AS {alias}', f'count({col}) AS {alias}_valid_matches']
    aggregates += ['stddev_samp(player_kills) AS std_kills', 'count(player_kills) AS std_kills_valid_matches',
                   'stddev_samp(player_dmg) AS std_damage', 'count(player_dmg) AS std_damage_valid_matches',
                   "CASE WHEN count(player_kills) < 2 THEN 'insufficient_n' WHEN stddev_samp(player_kills) = 0 THEN 'zero_variance' ELSE 'estimated' END AS std_kills_status",
                   "CASE WHEN count(player_dmg) < 2 THEN 'insufficient_n' WHEN stddev_samp(player_dmg) = 0 THEN 'zero_variance' ELSE 'estimated' END AS std_damage_status"]
    for phase in ('early', 'mid', 'late'):
        condition = f'player_kills > 0 AND phase_eligible_kill_count > 0 AND {phase}_kill_ratio IS NOT NULL'
        aggregates += [f'avg({phase}_kill_ratio) FILTER (WHERE {condition}) AS avg_{phase}_kill_ratio',
                       f'count(*) FILTER (WHERE {condition}) AS avg_{phase}_kill_ratio_valid_matches']
    observed = "timing_coverage_status = 'confirmed_no_kill_no_event' OR phase_eligible_kill_count > 0"
    aggregates += [f'avg(CASE WHEN {observed} THEN CASE WHEN early_kills > 0 THEN 1.0 ELSE 0.0 END ELSE NULL END) AS early_combat_match_ratio',
                   f'count(*) FILTER (WHERE {observed}) AS early_combat_match_ratio_valid_matches',
                   'avg(player_survive_time) AS mean_survive_time',
                   'count(player_survive_time) AS mean_survive_time_valid_matches',
                   'avg(normalized_placement) AS mean_normalized_placement',
                   'count(normalized_placement) AS mean_normalized_placement_valid_matches',
                   'avg(CASE WHEN team_placement IS NOT NULL THEN CASE WHEN team_placement = 1 THEN 1.0 ELSE 0.0 END ELSE NULL END) AS win_rate',
                   'count(team_placement) AS win_rate_valid_matches']
    return aggregates

def profile_keys(frame):
    return ["player_name"] + (["team_size_mode"] if "team_size_mode" in frame else [])


def build_player_behavioral_profiles(
    df: pd.DataFrame,
    group_by_mode: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Construct multi-dimensional Player Behavioral Profiles according to Research Spec §17 (Design 3).

    Returns:
      (behavioral_profile_df, outcome_profile_df)
      Outcomes are strictly isolated in a separate dataframe to prevent leakage during clustering!
    """
    required = {
        "player_name", "player_kills", "player_dmg", "damage_per_kill",
        "player_dist_walk", "player_dist_ride", "walk_ratio", "player_assists",
        "player_dbno", "assist_ratio", "early_kills", "early_kill_ratio",
        "mid_kill_ratio", "late_kill_ratio", "phase_eligible_kill_count",
        "timing_coverage_status", "player_survive_time", "normalized_placement",
        "team_placement",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required profile columns: {sorted(missing)}")
    clean_df = df[df["player_name"].notna() & (df["player_name"].str.strip().str.len() > 0)].copy()

    if group_by_mode and ("team_size_mode" not in clean_df or clean_df["team_size_mode"].isna().any()):
        raise ValueError("Verified team_size_mode is required for mode profiles")
    group_cols = ["player_name", "team_size_mode"] if group_by_mode else ["player_name"]

    # Same SQL as the disk-backed producer; no second formula implementation.
    import duckdb
    from src.analysis.clustering import CORE_PROFILE_FEATURES

    with duckdb.connect(":memory:") as connection:
        connection.register("valid", clean_df)
        query = ("SELECT " + ", ".join(group_cols + profile_aggregate_expressions())
                 + " FROM valid GROUP BY " + ", ".join(group_cols)
                 + " ORDER BY " + ", ".join(group_cols))
        aggregated = connection.execute(query).df()
    profile_features = aggregated[group_cols + ["games_played"] + PROFILE_AUDIT_COLUMNS
                                  + ["mean_damage_per_kill"] + CORE_PROFILE_FEATURES].copy()
    outcome_features = aggregated[group_cols + ["games_played", "mean_survive_time_valid_matches",
        "mean_normalized_placement_valid_matches", "win_rate_valid_matches",
        "mean_survive_time", "mean_normalized_placement", "win_rate"]].copy()
    logger.info(f"Built {len(profile_features)} player behavioral profiles (Design 3).")
    return profile_features, outcome_features


def filter_profiles_by_retention(
    profile_df: pd.DataFrame,
    outcome_df: pd.DataFrame,
    min_games: int = 5,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Filter eligible players who meet the minimum games threshold."""
    eligible_mask = profile_df["games_played"] >= min_games
    filtered_profiles = profile_df[eligible_mask].reset_index(drop=True)

    # Align outcomes
    keys = profile_keys(profile_df)

    filtered_outcomes = filtered_profiles[keys].merge(outcome_df, on=keys, how="left", validate="one_to_one")
    logger.info(f"Retention filter (min_games={min_games}): {len(filtered_profiles)}/{len(profile_df)} profiles retained.")
    return filtered_profiles, filtered_outcomes
