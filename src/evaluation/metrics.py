from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


def compute_regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
    """Compute base regression metrics with robust NaN handling for degenerate cases."""
    if not np.isfinite(y_pred).all():
        raise ValueError("Non-finite predictions are invalid, not silently dropped")
    valid_mask = np.isfinite(y_true)
    y = y_true[valid_mask].astype(np.float64)
    y_hat = y_pred[valid_mask].astype(np.float64)
    n = len(y)

    if n == 0:
        return {"mae": np.nan, "rmse": np.nan, "r2": np.nan, "n": 0, "r2_reason":"no_valid_targets"}

    residuals = y - y_hat
    mae = float(np.mean(np.abs(residuals)))
    rmse = float(np.sqrt(np.mean(residuals ** 2)))

    if n < 2:
        r2 = np.nan
        reason = "fewer_than_two_observations"
    else:
        sst = np.sum((y - np.mean(y)) ** 2)
        sse = np.sum(residuals ** 2)
        r2 = float(1.0 - (sse / sst)) if sst > 0 else np.nan
        reason = None if sst > 0 else "zero_target_variance"

    return {"mae": mae, "rmse": rmse, "r2": r2, "n": n, "r2_reason":reason,
            "excluded_nonfinite_targets":int((~valid_mask).sum())}


def compute_hierarchical_metrics(
    pred_df: pd.DataFrame,
    task: Optional[str] = None,
    target_name: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Compute micro (player-level), match-aware, and team-aware regression metrics.

    Invariants:
      1. Micro: Each player row has weight 1.
      2. Match-macro: Average of per-match metrics.
      3. Team-aware: Aggregated by (match_id, team_id) to evaluate team placement directly.
         NOTE: Under D01/D03, team-aware is NOT applicable for survival time (S1/S2).
    """
    actual_col = "target_actual" if "target_actual" in pred_df.columns else "actual"
    pred_col = "target_predicted" if "target_predicted" in pred_df.columns else "predicted"

    if actual_col not in pred_df.columns or pred_col not in pred_df.columns:
        raise KeyError(f"Prediction DataFrame must contain '{actual_col}' and '{pred_col}' columns")

    if not np.isfinite(pred_df[pred_col]).all():
        raise ValueError("Non-finite predictions are invalid, not silently dropped")
    clean_df = pred_df.loc[np.isfinite(pred_df[actual_col])].copy()

    # 1. Micro
    micro_res = compute_regression_metrics(
        clean_df[actual_col].values,
        clean_df[pred_col].values,
    )

    # 2. Match-aware
    if "match_id" in clean_df.columns and len(clean_df) > 0:
        residual = clean_df[actual_col] - clean_df[pred_col]
        match_metrics = pd.DataFrame({
            "match_id": clean_df["match_id"],
            "mae": residual.abs(),
            "mse": residual ** 2,
        }).groupby("match_id").mean()
        match_aware_res = {
            "mae": float(match_metrics["mae"].mean()),
            "rmse": float(np.sqrt(match_metrics["mse"].mean())),
            "n_matches": len(match_metrics),
        }
        weights = 1.0 / clean_df.groupby("match_id")[actual_col].transform("size").to_numpy(dtype=float)
        actual = clean_df[actual_col].to_numpy(dtype=np.float64)
        mean = np.average(actual,weights=weights)
        sst = float(np.sum(weights*(actual-mean)**2))
        sse = float(np.sum(weights*residual.to_numpy(dtype=np.float64)**2))
        match_aware_res.update(r2=1-sse/sst if len(actual)>1 and sst>0 else np.nan,
            r2_reason=None if len(actual)>1 and sst>0 else "insufficient_or_constant_target")
    else:
        match_aware_res = {"mae": np.nan, "rmse": np.nan, "n_matches": 0}

    # 3. Team-aware
    # Check if task is survival
    is_survival = False
    if task is not None and task.lower() in ("s1", "s2"):
        is_survival = True
    elif target_name is not None and target_name == "player_survive_time":
        is_survival = True
    elif "target" in clean_df.columns and len(clean_df) > 0 and clean_df["target"].iloc[0] == "player_survive_time":
        is_survival = True
    elif "task" in clean_df.columns and len(clean_df) > 0 and str(clean_df["task"].iloc[0]).lower() in ("s1", "s2"):
        is_survival = True

    if is_survival:
        team_aware_res = {
            "applicable": False,
            "mae": np.nan,
            "rmse": np.nan,
            "r2": np.nan,
            "n": 0,
        }
    elif "match_id" in clean_df.columns and "team_id" in clean_df.columns and len(clean_df) > 0:
        if clean_df[["match_id","team_id"]].isna().any().any():
            raise ValueError("Team-aware placement requires complete match/team keys")
        if (clean_df.groupby(["match_id","team_id"])[actual_col].nunique()>1).any():
            raise ValueError("Conflicting actual placement within a team; cannot aggregate first")
        team_df = clean_df.groupby(["match_id", "team_id"]).agg(
            team_actual=(actual_col, "first"),
            team_predicted=(pred_col, "mean"),
        ).reset_index()
        team_aware_res = compute_regression_metrics(
            team_df["team_actual"].values,
            team_df["team_predicted"].values,
        )
        team_aware_res["applicable"] = True
    else:
        team_aware_res = {"applicable": True, "mae": np.nan, "rmse": np.nan, "r2": np.nan, "n": 0}

    return {
        "micro": micro_res,
        "match_aware": match_aware_res,
        "team_aware": team_aware_res,
        "coverage": {"input_rows":len(pred_df),"valid_rows":len(clean_df),
                     "excluded_nonfinite_targets":len(pred_df)-len(clean_df)},
    }

