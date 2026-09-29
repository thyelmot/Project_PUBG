from typing import Optional
import numpy as np
import pandas as pd


def compute_normalized_placement(
    team_placement: pd.Series,
    observed_team_count: pd.Series,
    is_roster_complete: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """Compute normalized placement in [0, 1] according to Research Spec §14.

    Formula:
      normalized_placement = 1.0 - (team_placement - 1.0) / (N_teams - 1.0)

    Conditions:
      Roster verified complete, N_teams > 1, and 1 <= placement <= N_teams.
      If conditions not met, normalized_placement is NaN and placement_valid is False.
      Never clips invalid/out-of-bounds placements to hide errors.
    """
    placement = team_placement.astype("float64").values
    n_teams = observed_team_count.astype("float64").values

    valid_mask = (n_teams > 1) & (placement >= 1) & (placement <= n_teams)
    if is_roster_complete is not None:
        valid_mask = valid_mask & is_roster_complete.astype(bool).values

    with np.errstate(divide="ignore", invalid="ignore"):
        norm_pl = np.where(valid_mask, 1.0 - (placement - 1.0) / (n_teams - 1.0), np.nan)

    return pd.DataFrame({
        "team_placement": team_placement.values,
        "observed_team_count": observed_team_count.values,
        "normalized_placement": norm_pl,
        "placement_valid": valid_mask,
    }, index=team_placement.index)
