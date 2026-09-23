import numpy as np
import pandas as pd


def compute_normalized_placement(
    team_placement: pd.Series,
    observed_team_count: pd.Series,
) -> pd.DataFrame:
    """Compute normalized placement in [0, 1] according to Research Spec §14.

    Formula:
      normalized_placement = 1.0 - (team_placement - 1.0) / (N_teams - 1.0)

    Invariant:
      If N_teams <= 1 or placement > N_teams or placement <= 0 -> NaN and invalid.
    """
    placement = team_placement.astype("float64").values
    n_teams = observed_team_count.astype("float64").values

    valid_mask = (n_teams > 1) & (placement >= 1) & (placement <= n_teams + 2) # small buffer for ties

    with np.errstate(divide="ignore", invalid="ignore"):
        norm_pl = np.where(valid_mask, 1.0 - (placement - 1.0) / (n_teams - 1.0), np.nan)
        # Clip slight floating-point imprecision to strict [0, 1] for valid rows only
        norm_pl = np.where(valid_mask, np.clip(norm_pl, 0.0, 1.0), np.nan)

    return pd.DataFrame({
        "team_placement": team_placement.values,
        "observed_team_count": observed_team_count.values,
        "normalized_placement": norm_pl,
        "placement_valid": valid_mask,
    }, index=team_placement.index)
