import numpy as np
import pandas as pd


def compute_movement_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute verified Movement features according to Research Spec §7, §13.

    Formulas:
      total_distance = player_dist_walk + player_dist_ride
      walk_ratio = player_dist_walk / total_distance (NaN if total_distance == 0)
    """
    out = pd.DataFrame(index=df.index)
    walk = df["player_dist_walk"].astype("float64").values
    ride = df["player_dist_ride"].astype("float64").values

    total_dist = walk + ride
    with np.errstate(divide="ignore", invalid="ignore"):
        w_ratio = np.where(total_dist > 0, walk / total_dist, np.nan)

    out["player_dist_walk"] = walk
    out["player_dist_ride"] = ride
    out["total_distance"] = total_dist
    out["walk_ratio"] = w_ratio
    return out
