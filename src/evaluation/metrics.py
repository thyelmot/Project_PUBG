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


def compute_hierarchical_metrics(pred_df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Compute micro (player-level), match-aware, and team-aware regression metrics.

    Invariants:
      1. Micro: Each player row has weight 1.
      2. Match-macro: Average of per-match metrics.
      3. Team-aware: Aggregated by (match_id, team_id) to evaluate team placement directly.
    """
    clean_df = pred_df.dropna(subset=["target_actual", "target_predicted"]).copy()

    # 1. Micro
    micro_res = compute_regression_metrics(
        clean_df["target_actual"].values,
        clean_df["target_predicted"].values,
    )

    # 2. Match-aware
    if "match_id" in clean_df.columns:
        match_metrics = clean_df.groupby("match_id")[["target_actual", "target_predicted"]].apply(
            lambda g: pd.Series({
                "mae": np.mean(np.abs(g["target_actual"] - g["target_predicted"])),
                "mse": np.mean((g["target_actual"] - g["target_predicted"]) ** 2),
            }),
        )
        match_aware_res = {
            "mae": float(match_metrics["mae"].mean()),
            "rmse": float(np.sqrt(match_metrics["mse"].mean())),
            "n_matches": len(match_metrics),
        }
    else:
        match_aware_res = {"mae": np.nan, "rmse": np.nan, "n_matches": 0}

    # 3. Team-aware
    if "match_id" in clean_df.columns and "team_id" in clean_df.columns:
        team_df = clean_df.groupby(["match_id", "team_id"]).agg(
            target_actual=("target_actual", "first"),
            target_predicted=("target_predicted", "mean"),
        ).reset_index()
        team_aware_res = compute_regression_metrics(
            team_df["target_actual"].values,
            team_df["target_predicted"].values,
        )
    else:
        team_aware_res = {"mae": np.nan, "rmse": np.nan, "r2": np.nan, "n": 0}

    return {
        "micro": micro_res,
        "match_aware": match_aware_res,
        "team_aware": team_aware_res,
    }
