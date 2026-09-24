from pathlib import Path
from src.data.io import atomic_write_csv
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from src.evaluation.metrics import compute_regression_metrics
from src.utils.logging import get_logger

logger = get_logger("pubg_error_analysis")


def analyze_prediction_errors(
    pred_df: pd.DataFrame,
    output_table_path: Path,
) -> pd.DataFrame:
    """Analyze regression residuals across non-overlapping contextual slices (mode, placement tier, survival)."""
    output_table_path.parent.mkdir(parents=True, exist_ok=True)
    test_df = pred_df[pred_df["split"] == "test"].copy()
    columns = ["slice_category", "slice_value", "n_observations", "mae", "rmse", "r2", "mean_residual"]

    if len(test_df) == 0:
        logger.warning("No test split records found for error analysis.")
        result = pd.DataFrame(columns=columns)
        atomic_write_csv(output_table_path, result)
        return result

    records = []

    # 1. Slice by Game Mode
    if "party_size" in test_df.columns:
        mode_map = {1: "Solo", 2: "Duo", 4: "Squad"}
        test_df["mode_label"] = test_df["party_size"].map(lambda x: mode_map.get(x, f"Other_{x}"))
        for mode, grp in test_df.groupby("mode_label"):
            m = compute_regression_metrics(grp["target_actual"].values, grp["target_predicted"].values)
            records.append({
                "slice_category": "game_mode",
                "slice_value": mode,
                "n_observations": m["n"],
                "mae": m["mae"],
                "rmse": m["rmse"],
                "r2": m["r2"],
                "mean_residual": float(np.mean(grp["residual"])),
            })

    # 2. Slice by Placement Deciles (if target is normalized_placement)
    target_sample = test_df["target_actual"].values
    if (target_sample >= 0.0).all() and (target_sample <= 1.0 + 1e-5).all():
        # Placement bins
        bins = [-0.01, 0.20, 0.50, 0.80, 0.90, 1.01]
        labels = ["Bottom_20% (0.0-0.2)", "Lower_Mid (0.2-0.5)", "Upper_Mid (0.5-0.8)", "Top_10-20% (0.8-0.9)", "Top_10% (0.9-1.0)"]
        test_df["placement_tier"] = pd.cut(test_df["target_actual"], bins=bins, labels=labels)
        for tier, grp in test_df.groupby("placement_tier", observed=False):
            if len(grp) > 0:
                m = compute_regression_metrics(grp["target_actual"].values, grp["target_predicted"].values)
                records.append({
                    "slice_category": "placement_tier",
                    "slice_value": str(tier),
                    "n_observations": m["n"],
                    "mae": m["mae"],
                    "rmse": m["rmse"],
                    "r2": m["r2"],
                    "mean_residual": float(np.mean(grp["residual"])),
                })
    else:
        # Survival time bins in seconds
        bins = [-1.0, 300.0, 600.0, 1200.0, 1800.0, 99999.0]
        labels = ["0-5 min (<300s)", "5-10 min (300-600s)", "10-20 min (600-1200s)", "20-30 min (1200-1800s)", ">30 min (>1800s)"]
        test_df["survival_bin"] = pd.cut(test_df["target_actual"], bins=bins, labels=labels)
        for s_bin, grp in test_df.groupby("survival_bin", observed=False):
            if len(grp) > 0:
                m = compute_regression_metrics(grp["target_actual"].values, grp["target_predicted"].values)
                records.append({
                    "slice_category": "survival_bin",
                    "slice_value": str(s_bin),
                    "n_observations": m["n"],
                    "mae": m["mae"],
                    "rmse": m["rmse"],
                    "r2": m["r2"],
                    "mean_residual": float(np.mean(grp["residual"])),
                })

    error_df = pd.DataFrame(records, columns=columns)
    atomic_write_csv(output_table_path, error_df)
    logger.info(f"Error analysis table saved: {len(error_df)} slice records -> {output_table_path.name}")
    return error_df
