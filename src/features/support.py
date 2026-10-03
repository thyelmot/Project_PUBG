import pandas as pd

from src.features.base import compute_base_features_dataframe


def compute_support_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return raw support columns and the canonical assist-ratio feature."""
    out = pd.DataFrame(index=df.index)
    out["player_assists"] = df["player_assists"].astype("int64")
    out["player_dbno"] = df["player_dbno"].astype("int64")
    out["assist_ratio"] = compute_base_features_dataframe(df)["assist_ratio"]
    return out