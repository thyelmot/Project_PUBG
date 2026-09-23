import numpy as np
import pandas as pd


def compute_combat_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute verified Combat features according to Research Spec §7, §12.

    Formula:
      damage_per_kill = player_dmg / player_kills (NaN if player_kills == 0)
    """
    out = pd.DataFrame(index=df.index)
    out["player_kills"] = df["player_kills"].astype("int64")
    out["player_dmg"] = df["player_dmg"].astype("float64")

    # Safe division for damage_per_kill
    kills = out["player_kills"].values
    dmg = out["player_dmg"].values
    with np.errstate(divide="ignore", invalid="ignore"):
        dpk = np.where(kills > 0, dmg / kills, np.nan)

    out["damage_per_kill"] = dpk
    return out
