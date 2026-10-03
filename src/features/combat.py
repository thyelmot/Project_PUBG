import pandas as pd

from src.features.base import compute_base_features_dataframe


def compute_combat_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return raw combat columns and the canonical damage-per-kill feature."""
    out = pd.DataFrame(index=df.index)
    out["player_kills"] = df["player_kills"].astype("int64")
    out["player_dmg"] = df["player_dmg"].astype("float64")
    out["damage_per_kill"] = compute_base_features_dataframe(df)["damage_per_kill"]
    return out