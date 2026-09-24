from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from src.data.io import atomic_write_parquet
from src.utils.logging import get_logger

logger = get_logger("pubg_training")


def train_and_predict_experiment(
    df: pd.DataFrame,
    feature_names: List[str],
    target_name: str,
    model_instance: BaseEstimator,
    experiment_id: str,
    output_predictions_dir: Optional[Path] = None,
) -> Tuple[BaseEstimator, pd.DataFrame]:
    """Train estimator on train split only, and output unified predictions for train, val, and test.

    Invariants:
      1. Preprocessing and model are fit exclusively on train split.
      2. Predictions are saved with match_id and team_id for match-aware and team-aware evaluations.
      3. Missing target rows are dropped before training.
    """
    if target_name not in df.columns:
        raise ValueError(f"Target column '{target_name}' not in dataset.")
    if "split" not in df.columns:
        raise ValueError("Dataset missing 'split' column (train/validation/test).")
    if not df["split"].isin(["train", "validation", "test"]).all():
        raise ValueError("Missing or invalid split assignments. Rebuild notebook 02 for the current dataset.")

    # Filter out rows with invalid target
    valid_df = df[df[target_name].notna()].copy()

    train_mask = valid_df["split"] == "train"
    val_mask = valid_df["split"] == "validation"
    test_mask = valid_df["split"] == "test"

    if train_mask.sum() == 0:
        raise ValueError("Train split is empty!")

    X_train = valid_df.loc[train_mask, feature_names].values
    y_train = valid_df.loc[train_mask, target_name].values.astype(np.float64)

    logger.info(f"Fitting {experiment_id} on {len(X_train)} train rows ({len(feature_names)} features)...")
    model_instance.fit(X_train, y_train)

    # Predict across all splits
    X_all = valid_df[feature_names].values
    y_pred = model_instance.predict(X_all)

    # Build predictions dataframe
    id_cols = [c for c in ["match_id", "player_name", "team_id", "party_size", "split"] if c in valid_df.columns]
    pred_df = valid_df[id_cols].copy()
    pred_df["target_actual"] = valid_df[target_name].values
    pred_df["target_predicted"] = y_pred
    pred_df["residual"] = pred_df["target_actual"] - pred_df["target_predicted"]
    pred_df["experiment_id"] = experiment_id

    if output_predictions_dir:
        output_predictions_dir.mkdir(parents=True, exist_ok=True)
        pred_file = output_predictions_dir / f"predictions_{experiment_id}.parquet"
        atomic_write_parquet(pred_file, pred_df)
        logger.info(f"Saved predictions for {experiment_id} -> {pred_file.name}")

    return model_instance, pred_df
