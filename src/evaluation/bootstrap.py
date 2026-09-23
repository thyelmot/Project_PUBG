from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from src.evaluation.metrics import compute_regression_metrics


def run_paired_match_bootstrap(
    pred_df_candidate: pd.DataFrame,
    pred_df_reference: pd.DataFrame,
    n_replicates: int = 500,
    random_state: int = 42,
) -> Dict[str, Any]:
    """Execute paired match-level bootstrap to compute 95% Confidence Intervals for metric deltas.

    Delta convention: candidate - reference
      delta_mae < 0: Candidate has lower error (better)
      delta_rmse < 0: Candidate has lower error (better)
      delta_r2 > 0: Candidate explains more variance (better)
    """
    # 1. Assert identical row alignment
    common_idx = pred_df_candidate.index.intersection(pred_df_reference.index)
    if len(common_idx) != len(pred_df_candidate) or len(common_idx) != len(pred_df_reference):
        # Merge on identity keys
        keys = ["match_id", "player_name", "team_id"]
        merged = pd.merge(
            pred_df_candidate[keys + ["target_actual", "target_predicted"]],
            pred_df_reference[keys + ["target_predicted"]],
            on=keys,
            suffixes=("_cand", "_ref"),
        )
    else:
        merged = pd.DataFrame({
            "match_id": pred_df_candidate["match_id"].values,
            "target_actual": pred_df_candidate["target_actual"].values,
            "target_predicted_cand": pred_df_candidate["target_predicted"].values,
            "target_predicted_ref": pred_df_reference["target_predicted"].values,
        })

    # Group records by match_id
    matches = merged["match_id"].unique()
    n_matches = len(matches)
    if n_matches < 2:
        raise ValueError("Cannot perform match-level bootstrap with < 2 matches.")

    match_groups = {m_id: grp for m_id, grp in merged.groupby("match_id")}

    rng = np.random.RandomState(random_state)
    delta_mae_list = []
    delta_rmse_list = []
    delta_r2_list = []

    for _ in range(n_replicates):
        resampled_matches = rng.choice(matches, size=n_matches, replace=True)
        # Concatenate matched rows with multiplicity
        resampled_df = pd.concat([match_groups[m] for m in resampled_matches], ignore_index=True)

        y_true = resampled_df["target_actual"].values
        y_cand = resampled_df["target_predicted_cand"].values
        y_ref = resampled_df["target_predicted_ref"].values

        m_cand = compute_regression_metrics(y_true, y_cand)
        m_ref = compute_regression_metrics(y_true, y_ref)

        delta_mae_list.append(m_cand["mae"] - m_ref["mae"])
        delta_rmse_list.append(m_cand["rmse"] - m_ref["rmse"])
        if not np.isnan(m_cand["r2"]) and not np.isnan(m_ref["r2"]):
            delta_r2_list.append(m_cand["r2"] - m_ref["r2"])

    def get_summary(deltas: List[float], name: str) -> Dict[str, float]:
        arr = np.array(deltas)
        arr = arr[~np.isnan(arr)]
        if len(arr) == 0:
            return {"mean": np.nan, "ci_lower": np.nan, "ci_upper": np.nan}
        return {
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
            "ci_lower": float(np.percentile(arr, 2.5)),
            "ci_upper": float(np.percentile(arr, 97.5)),
        }

    return {
        "n_replicates": n_replicates,
        "n_matches": n_matches,
        "delta_mae": get_summary(delta_mae_list, "mae"),
        "delta_rmse": get_summary(delta_rmse_list, "rmse"),
        "delta_r2": get_summary(delta_r2_list, "r2"),
    }
