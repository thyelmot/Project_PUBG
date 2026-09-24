from pathlib import Path
from src.data.io import atomic_write_csv
from typing import Any, Dict, List, Optional
import pandas as pd
from src.evaluation.metrics import compute_regression_metrics
from src.features.registry import FeatureRegistry
from src.models.linear import LinearModelWrapper
from src.models.training import train_and_predict_experiment
from src.utils.logging import get_logger

logger = get_logger("pubg_ablation")


def run_group_ablation_study(
    df: pd.DataFrame,
    registry: FeatureRegistry,
    base_feature_set: List[str],
    target_col: str,
    output_table_path: Path,
) -> pd.DataFrame:
    """Execute ablation experiments: FULL, -Combat, -Movement, -Support, -Timing."""
    output_table_path.parent.mkdir(parents=True, exist_ok=True)

    ablation_recipes = [
        {"name": "ABL-FULL", "group_to_remove": None},
        {"name": "ABL-Combat", "group_to_remove": "combat"},
        {"name": "ABL-Movement", "group_to_remove": "movement"},
        {"name": "ABL-Support", "group_to_remove": "support"},
        {"name": "ABL-Timing", "group_to_remove": "combat_timing_phase"},
    ]

    records = []
    full_mae = None

    for recipe in ablation_recipes:
        exp_name = recipe["name"]
        grp = recipe["group_to_remove"]

        if grp is None:
            features_to_use = list(base_feature_set)
        else:
            features_to_use = registry.remove_group_and_descendants(base_feature_set, grp)

        logger.info(f"Running {exp_name} with {len(features_to_use)} features...")
        model = LinearModelWrapper(model_type="exact")
        _, pred_df = train_and_predict_experiment(
            df=df,
            feature_names=features_to_use,
            target_name=target_col,
            model_instance=model,
            experiment_id=exp_name,
        )

        test_preds = pred_df[pred_df["split"] == "test"]
        metrics = compute_regression_metrics(
            test_preds["target_actual"].values,
            test_preds["target_predicted"].values,
        )

        if exp_name == "ABL-FULL":
            full_mae = metrics["mae"]
            delta_mae = 0.0
        else:
            delta_mae = (metrics["mae"] - full_mae) if full_mae is not None else 0.0

        records.append({
            "ablation_experiment": exp_name,
            "removed_group": grp or "none",
            "features_count": len(features_to_use),
            "test_mae": metrics["mae"],
            "test_rmse": metrics["rmse"],
            "test_r2": metrics["r2"],
            "delta_mae_vs_full": delta_mae,
        })

    ablation_df = pd.DataFrame(records)
    atomic_write_csv(output_table_path, ablation_df)
    logger.info(f"Ablation study saved -> {output_table_path.name}")
    return ablation_df
