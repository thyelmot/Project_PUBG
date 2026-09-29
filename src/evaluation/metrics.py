from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


def compute_regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """Compute base regression metrics with robust NaN handling for degenerate cases."""
    valid_mask = ~np.isnan(y_true) & ~np.isnan(y_pred)
    y = y_true[valid_mask].astype(np.float64)
    y_hat = y_pred[valid_mask].astype(np.float64)
    n = len(y)

    if n == 0:
        return {"mae": np.nan, "rmse": np.nan, "r2": np.nan, "n": 0}

    residuals = y - y_hat
    mae = float(np.mean(np.abs(residuals)))
    rmse = float(np.sqrt(np.mean(residuals ** 2)))

    if n < 2:
        r2 = np.nan
    else:
        sst = np.sum((y - np.mean(y)) ** 2)
        sse = np.sum(residuals ** 2)
        r2 = float(1.0 - (sse / sst)) if sst > 1e-12 else np.nan

    return {"mae": mae, "rmse": rmse, "r2": r2, "n": n}


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

    clean_df = pred_df.dropna(subset=[actual_col, pred_col]).copy()

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
    }

