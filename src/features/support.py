import numpy as np
import pandas as pd


def compute_support_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute verified Support features according to Research Spec §7, §14.

    Formula:
      assist_ratio = player_assists / (player_kills + player_assists)
      (NaN if player_kills + player_assists == 0)
    """
    out = pd.DataFrame(index=df.index)
    assists = df["player_assists"].astype("int64").values
    dbno = df["player_dbno"].astype("int64").values
    kills = df["player_kills"].astype("int64").values

    combat_sum = assists + kills
    with np.errstate(divide="ignore", invalid="ignore"):
        a_ratio = np.where(combat_sum > 0, assists / combat_sum, np.nan)

    out["player_assists"] = assists
    out["player_dbno"] = dbno
    out["assist_ratio"] = a_ratio
    return out
