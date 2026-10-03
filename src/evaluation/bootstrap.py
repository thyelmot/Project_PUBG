from typing import Any, Dict
import numpy as np
import pandas as pd
from src.data.cohort import align_cohort_rows
from src.evaluation.metrics import compute_regression_metrics


def pair_predictions(candidate, reference):
    """Exact one-to-one pairing. Identity/target mismatches never shrink a cohort."""
    for frame in (candidate, reference):
        for column in ["row_id", "match_id", "target_actual", "target_predicted"]:
            if column not in frame:
                raise KeyError(column)
        if frame.match_id.isna().any():
            raise ValueError("Missing match identity")
    candidate, reference = align_cohort_rows([candidate, reference], target_col="target_actual", require_exact=True)
    for column in ["match_id", "player_name", "team_id", "split", "target", "recipe_hash", "team_size_mode", "hist_games_played"]:
        if (column in candidate) != (column in reference):
            raise ValueError(f"Identity schema mismatch: {column}")
        if column in candidate and not candidate[column].equals(reference[column]):
            raise ValueError(f"Identity mismatch: {column}")
    if not np.array_equal(candidate.target_actual.to_numpy(), reference.target_actual.to_numpy(), equal_nan=True):
        raise ValueError("Target mismatch: exact saved targets required")
    for frame in (candidate, reference):
        if not np.isfinite(frame.target_actual).all() or not np.isfinite(frame.target_predicted).all():
            raise ValueError("Non-finite paired targets/predictions; repair source, do not change cohort")
    return candidate, reference


def run_paired_match_bootstrap(
    pred_df_candidate: pd.DataFrame,
    pred_df_reference: pd.DataFrame,
    n_replicates: int = 500,
    random_state: int = 42,
    max_memory_gb: float = 8.0,
) -> Dict[str, Any]:
    """Execute paired match-level bootstrap to compute 95% Confidence Intervals for metric deltas.

    Delta convention: candidate - reference
      delta_mae < 0: Candidate has lower error (better)
      delta_rmse < 0: Candidate has lower error (better)
      delta_r2 > 0: Candidate explains more variance (better)
    """
    if isinstance(n_replicates, bool) or not isinstance(n_replicates, int) or n_replicates < 1:
        raise ValueError("replicates must be a positive integer")
    candidate, reference = pair_predictions(pred_df_candidate, pred_df_reference)
    n_matches = candidate.match_id.nunique()
    if n_matches < 2:
        raise ValueError("Cannot perform match-level bootstrap with < 2 matches.")

    info = {"n_replicates": n_replicates, "n_matches": n_matches, "n_rows": len(candidate),
            "seed": random_state, "level": "match", "confidence": .95,
            "max_memory_gb": max_memory_gb, "sampled_rows": False, "delta_convention": "candidate-reference"}
    from src.utils.runtime import collect_runtime_info
    free = collect_runtime_info().get("available_ram_gb")
    estimate = (candidate.memory_usage(deep=True).sum() + reference.memory_usage(deep=True).sum()) * 4 + n_matches*128 + n_replicates*24
    info["estimated_bytes"] = int(estimate)
    empty = {"mean": np.nan, "ci_lower": np.nan, "ci_upper": np.nan, "valid_replicates": 0}
    if not isinstance(free, (float, int)) or estimate > min(free, max_memory_gb)*1024**3:
        return {**info, "status": "resource_limited", "reason": "bootstrap_memory_budget", **{f"delta_{key}":dict(empty) for key in ["mae","rmse","r2"]}}
    # Center once for stable SST with large-offset targets. Aggregate once, not per replicate.
    y = candidate.target_actual.to_numpy(dtype=np.float64)
    z = y-y.mean()
    c = y-candidate.target_predicted.to_numpy(dtype=np.float64)
    r = y-reference.target_predicted.to_numpy(dtype=np.float64)
    contributions = pd.DataFrame({"match": candidate.match_id, "n": 1., "z": z, "zz": z*z,
        "ac": abs(c), "sc": c*c, "ar": abs(r), "sr": r*r}).groupby("match", sort=True).sum().to_numpy(dtype=np.float64)
    rng = np.random.RandomState(random_state)
    delta_mae_list = []
    delta_rmse_list = []
    delta_r2_list = []

    for _ in range(n_replicates):
        indices = rng.choice(n_matches, size=n_matches, replace=True)
        n, sy, syy, ac, sc, ar, sr = contributions[indices].sum(axis=0)
        delta_mae_list.append((ac-ar)/n)
        delta_rmse_list.append(np.sqrt(sc/n)-np.sqrt(sr/n))
        sst = max(0., syy-sy*sy/n)
        if n >= 2 and sst > 0:
            delta_r2_list.append((sr-sc)/sst)

    def get_summary(deltas, name):
        arr = np.array(deltas)
        arr = arr[~np.isnan(arr)]
        if len(arr) == 0:
            return {**empty, "reason": "undefined_global_r2"}
        return {
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
            "ci_lower": float(np.percentile(arr, 2.5)),
            "ci_upper": float(np.percentile(arr, 97.5)),
            "valid_replicates": len(arr),
            "reason": None,
        }

    return {
        **info, "status": "completed", "reason": None,
        "delta_mae": get_summary(delta_mae_list, "mae"),
        "delta_rmse": get_summary(delta_rmse_list, "rmse"),
        "delta_r2": get_summary(delta_r2_list, "r2"),
    }
