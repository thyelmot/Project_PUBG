import pandas as pd

from src.features.base import compute_base_features_dataframe


def compute_movement_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return raw movement columns and canonical distance features."""
    out = pd.DataFrame(index=df.index)
    out["player_dist_walk"] = df["player_dist_walk"].astype("float64")
    out["player_dist_ride"] = df["player_dist_ride"].astype("float64")
    derived = compute_base_features_dataframe(df)
    out["total_distance"] = derived["total_distance"]
    out["walk_ratio"] = derived["walk_ratio"]
    return out