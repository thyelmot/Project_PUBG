from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from src.utils.logging import get_logger

logger = get_logger("pubg_profiles")


def build_player_behavioral_profiles(
    df: pd.DataFrame,
    group_by_mode: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Construct multi-dimensional Player Behavioral Profiles according to Research Spec §17 (Design 3).

    Returns:
      (behavioral_profile_df, outcome_profile_df)
      Outcomes are strictly isolated in a separate dataframe to prevent leakage during clustering!
    """
    clean_df = df[df["player_name"].notna() & (df["player_name"].str.strip().str.len() > 0)].copy()

    group_cols = ["player_name", "match_mode"] if group_by_mode and "match_mode" in clean_df.columns else ["player_name"]

    # 1. Base aggregations per player
    grouped = clean_df.groupby(group_cols)

    # Core games count
    games_played = grouped.size().rename("games_played")

    # Combat metrics
    mean_kills = grouped["player_kills"].mean().rename("mean_kills")
    std_kills = grouped["player_kills"].std(ddof=1).fillna(0.0).rename("std_kills")
    mean_dmg = grouped["player_dmg"].mean().rename("mean_damage")
    std_dmg = grouped["player_dmg"].std(ddof=1).fillna(0.0).rename("std_damage")
    mean_dpk = grouped["damage_per_kill"].mean().rename("mean_damage_per_kill")

    # Movement metrics
    mean_walk = grouped["player_dist_walk"].mean().rename("mean_walk_distance")
    mean_ride = grouped["player_dist_ride"].mean().rename("mean_ride_distance")
    mean_walk_ratio = grouped["walk_ratio"].mean().rename("mean_walk_ratio")

    # Support metrics
    mean_assists = grouped["player_assists"].mean().rename("mean_assists")
    mean_dbno = grouped["player_dbno"].mean().rename("mean_dbno")
    mean_assist_ratio = grouped["assist_ratio"].mean().rename("mean_assist_ratio")

    # Timing metrics: average ratios on kill-active matches
    kill_active_df = clean_df[clean_df["player_kills"] > 0]
    kill_grouped = kill_active_df.groupby(group_cols)
    avg_early_ratio = kill_grouped["early_kill_ratio"].mean().rename("avg_early_kill_ratio")
    avg_mid_ratio = kill_grouped["mid_kill_ratio"].mean().rename("avg_mid_kill_ratio")
    avg_late_ratio = kill_grouped["late_kill_ratio"].mean().rename("avg_late_kill_ratio")

    # Early combat match ratio: proportion of matches with >= 1 early kill
    early_match_count = clean_df[clean_df["early_kills"] > 0].groupby(group_cols).size()
    early_combat_ratio = (early_match_count / games_played).fillna(0.0).rename("early_combat_match_ratio")

    # Assemble behavioral features
    profile_features = pd.concat([
        games_played,
        mean_kills, std_kills, mean_dmg, std_dmg, mean_dpk,
        mean_walk, mean_ride, mean_walk_ratio,
        mean_assists, mean_dbno, mean_assist_ratio,
        avg_early_ratio, avg_mid_ratio, avg_late_ratio,
        early_combat_ratio,
    ], axis=1).reset_index()

    # Fill NaN ratios for non-combat players with 0.0 for clustering feature space
    ratio_cols = ["mean_damage_per_kill", "mean_walk_ratio", "mean_assist_ratio", "avg_early_kill_ratio", "avg_mid_kill_ratio", "avg_late_kill_ratio"]
    profile_features[ratio_cols] = profile_features[ratio_cols].fillna(0.0)

    # 2. Assemble Isolated Outcome Profile (For C5 evaluation only)
    mean_survival = grouped["player_survive_time"].mean().rename("mean_survive_time")
    mean_placement = grouped["normalized_placement"].mean().rename("mean_normalized_placement")
    win_rate = (grouped["team_placement"].apply(lambda s: (s == 1).mean())).rename("win_rate")

    outcome_features = pd.concat([
        games_played,
        mean_survival,
        mean_placement,
        win_rate,
    ], axis=1).reset_index()

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
    if "match_mode" in profile_df.columns:
        keys = ["player_name", "match_mode"]
    else:
        keys = ["player_name"]

    filtered_outcomes = outcome_df.merge(filtered_profiles[keys], on=keys, how="inner")
    logger.info(f"Retention filter (min_games={min_games}): {len(filtered_profiles)}/{len(profile_df)} profiles retained.")
    return filtered_profiles, filtered_outcomes
