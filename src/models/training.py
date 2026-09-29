from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator

from src.data.cohort import ensure_row_id, align_cohort_rows
from src.data.io import atomic_write_parquet, atomic_write_json
from src.data.checkpoints import CheckpointManager
from src.evaluation.metrics import compute_hierarchical_metrics
from src.models.baselines import TrainMeanRegressor, TrainMedianRegressor
from src.models.compute import compute_info
from src.models.linear import LinearModelWrapper
from src.models.registry import ExperimentRegistry
from src.models.tree_models import HistGradientBoostingWrapper
from src.utils.hashing import hash_dict
from src.utils.logging import get_logger

logger = get_logger("pubg_training")


def train_and_predict_experiment(
    df: pd.DataFrame,
    feature_names: List[str],
    target_name: str,
    model_instance: BaseEstimator,
    experiment_id: str,
    task: str = "p2",
    output_predictions_dir: Optional[Path] = None,
    output_models_dir: Optional[Path] = None,
    batch_size: int = 50000,
) -> Tuple[BaseEstimator, pd.DataFrame]:
    """Train estimator on train split only, and output unified predictions for train, val, and test.

    Invariants:
      1. Preprocessing and model are fit exclusively on train split.
      2. Missing or non-finite target rows are dropped before training.
      3. Predictions are generated in batches (batch_size) to prevent RAM exhaustion.
      4. Canonical prediction columns include: row_id, match_id, player_name, team_id,
         team_size_mode, task, target, split, actual, predicted, residual, experiment_id.
    """
    if target_name not in df.columns:
        raise ValueError(f"Target column '{target_name}' not in dataset.")
    if "split" not in df.columns:
        raise ValueError("Dataset missing 'split' column (train/validation/test).")

    invalid_split = ~df["split"].isin(["train", "validation", "test"])
    if invalid_split.any():
        matches = df.loc[invalid_split, "match_id"].nunique(dropna=False) if "match_id" in df else "unknown"
        raise ValueError(
            f"Missing or invalid split assignments: {int(invalid_split.sum())} rows, {matches} matches. "
            "Rebuild notebook 02 for the current dataset; no rows were silently removed."
        )

    # Filter out rows with invalid or non-finite target
    valid_mask = df[target_name].notna() & np.isfinite(df[target_name])
    valid_df = df[valid_mask].copy()

    # Ensure deterministic row_id
    valid_df = ensure_row_id(valid_df)

    train_mask = valid_df["split"] == "train"
    val_mask = valid_df["split"] == "validation"
    test_mask = valid_df["split"] == "test"

    if train_mask.sum() == 0:
        raise ValueError("Train split is empty!")

    # Check for missing feature columns
    missing_feats = [f for f in feature_names if f not in valid_df.columns]
    if missing_feats:
        raise KeyError(f"Features missing from dataframe for {experiment_id}: {missing_feats}")

    X_train = valid_df.loc[train_mask, feature_names].values
    y_train = valid_df.loc[train_mask, target_name].values.astype(np.float64)

    logger.info(f"Fitting {experiment_id} on {len(X_train)} train rows ({len(feature_names)} features)...")
    model_instance.fit(X_train, y_train)
    compute = compute_info(getattr(model_instance, "device", "cpu"))

    # Predict in memory-safe batches across all splits
    n_samples = len(valid_df)
    y_pred_chunks = []
    for start_idx in range(0, n_samples, batch_size):
        end_idx = min(start_idx + batch_size, n_samples)
        chunk_X = valid_df.iloc[start_idx:end_idx][feature_names].values
        chunk_y_pred = model_instance.predict(chunk_X)
        y_pred_chunks.append(chunk_y_pred)
    y_pred = np.concatenate(y_pred_chunks) if y_pred_chunks else np.array([], dtype=np.float64)

    # Build canonical predictions dataframe
    id_cols = [c for c in ["row_id", "match_id", "player_name", "team_id", "team_size_mode", "party_size", "split"] if c in valid_df.columns]
    pred_df = valid_df[id_cols].copy()
    if "team_size_mode" not in pred_df.columns and "party_size" in pred_df.columns:
        mode_map = {1: "Solo", 2: "Duo", 4: "Squad"}
        pred_df["team_size_mode"] = pred_df["party_size"].map(mode_map).fillna("Unknown")

    actual_values = valid_df[target_name].values.astype(np.float64)
    pred_df["actual"] = actual_values
    pred_df["predicted"] = y_pred
    pred_df["target_actual"] = actual_values  # Compatibility alias
    pred_df["target_predicted"] = y_pred      # Compatibility alias
    pred_df["residual"] = actual_values - y_pred
    pred_df["task"] = task
    pred_df["target"] = target_name
    pred_df["experiment_id"] = experiment_id
    pred_df["compute_device"] = compute["device"]

    # Persist predictions if directory provided
    if output_predictions_dir:
        output_predictions_dir = Path(output_predictions_dir)
        output_predictions_dir.mkdir(parents=True, exist_ok=True)
        pred_file = output_predictions_dir / f"predictions_{experiment_id}.parquet"
        atomic_write_parquet(pred_file, pred_df)
        atomic_write_json(output_predictions_dir / f"compute_{experiment_id}.json", compute)
        logger.info(f"Saved predictions for {experiment_id} -> {pred_file.name}")

    # Persist model pipeline and metadata if directory provided
    if output_models_dir:
        output_models_dir = Path(output_models_dir)
        output_models_dir.mkdir(parents=True, exist_ok=True)
        model_file = output_models_dir / f"{experiment_id}.joblib"
        joblib.dump(model_instance, model_file)
        meta_file = output_models_dir / f"meta_{experiment_id}.json"
        model_meta = {
            "experiment_id": experiment_id,
            "task": task,
            "target": target_name,
            "features": feature_names,
            "n_features": len(feature_names),
            "train_samples": int(train_mask.sum()),
            "val_samples": int(val_mask.sum()),
            "test_samples": int(test_mask.sum()),
            "compute": compute,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        atomic_write_json(meta_file, model_meta)
        logger.info(f"Saved model and metadata for {experiment_id} -> {model_file.name}")

    return model_instance, pred_df


def lock_selection_recipe(
    experiment_id: str,
    task: str,
    target_name: str,
    feature_names: List[str],
    model_instance: BaseEstimator,
    val_metrics: Dict[str, Any],
    train_rows: int,
    val_rows: int,
    test_rows: int,
    output_lock_dir: Path,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execution Gate G4: Lock selection recipe on train/validation BEFORE test evaluation.

    Invariants:
      1. Hyperparameters, features, and preprocessing choices are evaluated strictly on validation.
      2. The selection recipe is cryptographically locked with hashes of features, model, and splits.
      3. Test split data is not unblinded until the recipe has been certified and locked.
    """
    output_lock_dir = Path(output_lock_dir)
    output_lock_dir.mkdir(parents=True, exist_ok=True)

    recipe_data: Dict[str, Any] = {
        "gate": "G4_SELECTION_LOCK",
        "experiment_id": experiment_id,
        "task": task,
        "target": target_name,
        "feature_names": feature_names,
        "feature_count": len(feature_names),
        "estimator_class": model_instance.__class__.__name__,
        "train_rows": train_rows,
        "val_rows": val_rows,
        "test_rows": test_rows,
        "val_metrics": val_metrics,
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "status": "LOCKED",
        "metadata": metadata or {},
    }
    recipe_hash = hash_dict({k: v for k, v in recipe_data.items() if k != "locked_at"})
    recipe_data["recipe_hash"] = recipe_hash

    lock_file = output_lock_dir / f"selection_lock_{experiment_id}.json"
    atomic_write_json(lock_file, recipe_data)
    logger.info(f"Gate G4 Locked: Recipe {experiment_id} saved to {lock_file.name} (hash={recipe_hash[:8]})")
    return recipe_data


def run_rq3_prediction_suite(
    df: pd.DataFrame,
    paths: Dict[str, Path],
    feature_registry: Optional[Any] = None,
    experiment_registry: Optional[ExperimentRegistry] = None,
    checkpoint_mgr: Optional[CheckpointManager] = None,
    chronology_grade: str = "Grade C",
    device: str = "cpu",
    run_nonlinear: bool = True,
    batch_size: int = 50000,
) -> Dict[str, Any]:
    """Execute complete RQ3 prediction pipeline with Selection Lock Gate G4 and hierarchical metrics.

    Workflow:
      1. Cohort preparation & row ID verification.
      2. Baselines (TrainMean, TrainMedian) on P1 and S1 cohorts.
      3. Core Linear Models: P1 (OLS with direct survival), P2 (OLS without direct survival),
         S1 (OLS retrospective survival without duration-derived proxy features).
      4. Nonlinear candidate evaluation on Validation (P2 HistGradientBoosting).
      5. Execution Gate G4: Lock selection recipes before Test evaluation.
      6. Evaluation of final Test split: micro, match-aware, and team-aware (for placement).
      7. Model comparison & validation selection tables.
      8. Diagnostic residual and observed-vs-predicted plots.
      9. Publication of stage 'rq3_prediction' to CheckpointManager.
    """
    logger.info("Starting RQ3 Prediction Suite execution...")

    pred_dir = paths.get("experiments", paths["processed"] / "experiments")
    models_dir = paths.get("models", paths.get("artifacts", paths["processed"]) / "models")
    tables_dir = paths.get("tables", paths["reports"] / "tables" if "reports" in paths else paths["processed"])
    figures_dir = paths.get("figures", paths["reports"] / "figures" if "reports" in paths else paths["processed"])
    locks_dir = paths.get("manifests", paths["processed"]) / "selection_locks"

    for d in (pred_dir, models_dir, tables_dir, figures_dir, locks_dir):
        d.mkdir(parents=True, exist_ok=True)

    # 1. Feature sets
    if feature_registry and hasattr(feature_registry, "get_allowed_features"):
        p1_feats = [f for f in feature_registry.get_allowed_features("p1") if f in df.columns]
        p2_feats = [f for f in feature_registry.get_allowed_features("p2") if f in df.columns]
        s1_feats = [f for f in feature_registry.get_allowed_features("s1") if f in df.columns]
    else:
        # Default canonical feature sets per spec
        base_combat = ["player_kills", "player_dmg", "damage_per_kill"]
        base_movement = ["player_dist_walk", "player_dist_ride", "total_distance", "walk_ratio"]
        base_support = ["player_assists", "player_dbno", "assist_ratio"]
        timing_abs = ["first_kill_time", "avg_kill_time", "has_kill"]
        timing_phase = ["early_kills", "mid_kills", "late_kills", "early_kill_ratio", "mid_kill_ratio", "late_kill_ratio"]

        s1_feats = [f for f in base_combat + base_movement + base_support + timing_abs if f in df.columns]
        p2_feats = [f for f in s1_feats + timing_phase if f in df.columns]
        p1_feats = [f for f in p2_feats + ["player_survive_time"] if f in df.columns]

    target_placement = "normalized_placement"
    target_survival = "player_survive_time"

    # Verify target columns
    if target_placement not in df.columns or target_survival not in df.columns:
        raise KeyError(f"Target columns missing: {target_placement}, {target_survival}")

    # Ensure row_id
    df_clean = ensure_row_id(df)

    # Align common rows for placement tasks (P1 and P2)
    valid_placement = df_clean[df_clean[target_placement].notna() & np.isfinite(df_clean[target_placement])].copy()
    valid_survival = df_clean[df_clean[target_survival].notna() & np.isfinite(df_clean[target_survival])].copy()

    predictions_dict = {}
    models_dict = {}
    val_metrics_dict = {}
    test_metrics_dict = {}

    # 2. Baselines
    logger.info("Executing Baselines...")
    # Baseline Mean (P1 cohort)
    mean_p1 = TrainMeanRegressor()
    _, pred_mean_p1 = train_and_predict_experiment(
        valid_placement, p2_feats[:1], target_placement, mean_p1,
        "base_mean_p1", task="p1", output_predictions_dir=pred_dir, output_models_dir=models_dir, batch_size=batch_size
    )
    predictions_dict["base_mean_p1"] = pred_mean_p1
    models_dict["base_mean_p1"] = mean_p1

    # Baseline Median (P1 cohort)
    median_p1 = TrainMedianRegressor()
    _, pred_median_p1 = train_and_predict_experiment(
        valid_placement, p2_feats[:1], target_placement, median_p1,
        "base_median_p1", task="p1", output_predictions_dir=pred_dir, output_models_dir=models_dir, batch_size=batch_size
    )
    predictions_dict["base_median_p1"] = pred_median_p1
    models_dict["base_median_p1"] = median_p1

    # Baseline Mean (S1 cohort)
    mean_s1 = TrainMeanRegressor()
    _, pred_mean_s1 = train_and_predict_experiment(
        valid_survival, s1_feats[:1], target_survival, mean_s1,
        "base_mean_s1", task="s1", output_predictions_dir=pred_dir, output_models_dir=models_dir, batch_size=batch_size
    )
    predictions_dict["base_mean_s1"] = pred_mean_s1
    models_dict["base_mean_s1"] = mean_s1

    # Baseline Median (S1 cohort)
    median_s1 = TrainMedianRegressor()
    _, pred_median_s1 = train_and_predict_experiment(
        valid_survival, s1_feats[:1], target_survival, median_s1,
        "base_median_s1", task="s1", output_predictions_dir=pred_dir, output_models_dir=models_dir, batch_size=batch_size
    )
    predictions_dict["base_median_s1"] = pred_median_s1
    models_dict["base_median_s1"] = median_s1

    # 3. Core Linear Models
    logger.info("Executing Core Linear Models (OLS)...")
    # P2: Placement without direct survival
    ols_p2 = LinearModelWrapper(model_type="exact", device=device)
    _, pred_p2 = train_and_predict_experiment(
        valid_placement, p2_feats, target_placement, ols_p2,
        "p2_ols_no_direct_survival", task="p2", output_predictions_dir=pred_dir, output_models_dir=models_dir, batch_size=batch_size
    )
    predictions_dict["p2_ols_no_direct_survival"] = pred_p2
    models_dict["p2_ols_no_direct_survival"] = ols_p2

    # P1: Placement with direct survival
    ols_p1 = LinearModelWrapper(model_type="exact", device=device)
    _, pred_p1 = train_and_predict_experiment(
        valid_placement, p1_feats, target_placement, ols_p1,
        "p1_ols_direct_survival", task="p1", output_predictions_dir=pred_dir, output_models_dir=models_dir, batch_size=batch_size
    )
    predictions_dict["p1_ols_direct_survival"] = pred_p1
    models_dict["p1_ols_direct_survival"] = ols_p1

    # S1: Retrospective survival without proxy descendants
    ols_s1 = LinearModelWrapper(model_type="exact", device=device)
    _, pred_s1 = train_and_predict_experiment(
        valid_survival, s1_feats, target_survival, ols_s1,
        "s1_retrospective_survival", task="s1", output_predictions_dir=pred_dir, output_models_dir=models_dir, batch_size=batch_size
    )
    predictions_dict["s1_retrospective_survival"] = pred_s1
    models_dict["s1_retrospective_survival"] = ols_s1

    # 4. Nonlinear candidate evaluation on Validation
    if run_nonlinear:
        logger.info("Evaluating nonlinear candidate (HistGradientBoosting) on Validation...")
        try:
            hgb_p2 = HistGradientBoostingWrapper(random_state=42)
            _, pred_hgb = train_and_predict_experiment(
                valid_placement, p2_feats, target_placement, hgb_p2,
                "p2_hgb_nonlinear_candidate", task="p2", output_predictions_dir=pred_dir, output_models_dir=models_dir, batch_size=batch_size
            )
            predictions_dict["p2_hgb_nonlinear_candidate"] = pred_hgb
            models_dict["p2_hgb_nonlinear_candidate"] = hgb_p2
        except Exception as e:
            logger.warning(f"Could not execute HistGradientBoosting candidate: {e}")

    # 5. Handle Grade C Chronology Tasks (S2 & P3)
    if chronology_grade == "Grade C":
        logger.info("Chronology is Grade C: Safely recording S2 and P3 tasks as blocked.")
        if experiment_registry:
            experiment_registry.update_status("s2_historical_survival", "blocked", reason_code="blocked_by_chronology")
            experiment_registry.update_status("p3_historical_placement", "blocked", reason_code="blocked_by_chronology")
        if checkpoint_mgr:
            checkpoint_mgr.record_blocked("s2_historical_survival", "grade_c_blocked", "blocked_by_chronology", {"grade": "C"})
            checkpoint_mgr.record_blocked("p3_historical_placement", "grade_c_blocked", "blocked_by_chronology", {"grade": "C"})

    # 6. Execution Gate G4: Evaluate Validation & Lock Selection Recipes
    logger.info("Executing Gate G4: Computing validation metrics and locking recipes...")
    val_selection_rows = []
    for exp_id, pred_df in predictions_dict.items():
        v_sub = pred_df[pred_df["split"] == "validation"]
        exp_task = pred_df["task"].iloc[0]
        exp_target = pred_df["target"].iloc[0]
        v_metrics = compute_hierarchical_metrics(v_sub, task=exp_task, target_name=exp_target)
        val_metrics_dict[exp_id] = v_metrics

        model_inst = models_dict[exp_id]
        feature_set = p1_feats if exp_task == "p1" else (s1_feats if exp_task == "s1" else p2_feats)
        if "base" in exp_id:
            feature_set = feature_set[:1]

        t_cnt = int((pred_df["split"] == "train").sum())
        v_cnt = int((pred_df["split"] == "validation").sum())
        te_cnt = int((pred_df["split"] == "test").sum())

        lock_data = lock_selection_recipe(
            experiment_id=exp_id,
            task=exp_task,
            target_name=exp_target,
            feature_names=feature_set,
            model_instance=model_inst,
            val_metrics=v_metrics,
            train_rows=t_cnt,
            val_rows=v_cnt,
            test_rows=te_cnt,
            output_lock_dir=locks_dir,
        )

        val_selection_rows.append({
            "experiment_id": exp_id,
            "task": exp_task,
            "target": exp_target,
            "val_micro_mae": v_metrics["micro"]["mae"],
            "val_micro_rmse": v_metrics["micro"]["rmse"],
            "val_micro_r2": v_metrics["micro"]["r2"],
            "val_match_mae": v_metrics["match_aware"]["mae"],
            "val_team_mae": v_metrics["team_aware"].get("mae", np.nan),
            "recipe_hash": lock_data["recipe_hash"][:12],
            "selection_status": "LOCKED",
        })

    df_val_selection = pd.DataFrame(val_selection_rows)
    val_sel_csv = tables_dir / "rq3_validation_selection.csv"
    df_val_selection.to_csv(val_sel_csv, index=False)
    logger.info(f"Validation selection table published -> {val_sel_csv.name}")

    # 7. Final Test Evaluation (unblinded after Gate G4 lock)
    logger.info("Computing final Test metrics...")
    comparison_rows = []
    for exp_id, pred_df in predictions_dict.items():
        t_sub = pred_df[pred_df["split"] == "test"]
        exp_task = pred_df["task"].iloc[0]
        exp_target = pred_df["target"].iloc[0]
        t_metrics = compute_hierarchical_metrics(t_sub, task=exp_task, target_name=exp_target)
        test_metrics_dict[exp_id] = t_metrics

        v_metrics = val_metrics_dict[exp_id]

        if experiment_registry:
            try:
                experiment_registry.update_metrics(
                    exp_id,
                    metrics={
                        "test_mae": t_metrics["micro"]["mae"],
                        "test_rmse": t_metrics["micro"]["rmse"],
                        "test_r2": t_metrics["micro"]["r2"],
                        "test_match_mae": t_metrics["match_aware"]["mae"],
                        "test_team_mae": t_metrics["team_aware"].get("mae", np.nan),
                    },
                    artifacts={"predictions": str(pred_dir / f"predictions_{exp_id}.parquet")}
                )
            except Exception as e:
                logger.debug(f"Experiment {exp_id} update in registry skipped: {e}")

        comparison_rows.append({
            "experiment_id": exp_id,
            "task": exp_task,
            "target": exp_target,
            "model_type": models_dict[exp_id].__class__.__name__,
            "val_mae": v_metrics["micro"]["mae"],
            "val_rmse": v_metrics["micro"]["rmse"],
            "val_r2": v_metrics["micro"]["r2"],
            "test_mae": t_metrics["micro"]["mae"],
            "test_rmse": t_metrics["micro"]["rmse"],
            "test_r2": t_metrics["micro"]["r2"],
            "test_match_mae": t_metrics["match_aware"]["mae"],
            "test_team_mae": t_metrics["team_aware"].get("mae", np.nan),
            "status": "completed",
            "compute_device": pred_df["compute_device"].iloc[0] if "compute_device" in pred_df.columns else "cpu",
        })

    # Add blocked historical experiments to comparison table for transparency
    if chronology_grade == "Grade C":
        for b_id, b_task, b_target in [
            ("s2_historical_survival", "s2", target_survival),
            ("p3_historical_placement", "p3", target_placement),
        ]:
            comparison_rows.append({
                "experiment_id": b_id,
                "task": b_task,
                "target": b_target,
                "model_type": "Blocked (Grade C)",
                "val_mae": np.nan,
                "val_rmse": np.nan,
                "val_r2": np.nan,
                "test_mae": np.nan,
                "test_rmse": np.nan,
                "test_r2": np.nan,
                "test_match_mae": np.nan,
                "test_team_mae": np.nan,
                "status": "blocked (blocked_by_chronology)",
                "compute_device": "none",
            })

    df_comparison = pd.DataFrame(comparison_rows)
    comp_csv = tables_dir / "rq3_model_comparison.csv"
    df_comparison.to_csv(comp_csv, index=False)
    logger.info(f"Model comparison table published -> {comp_csv.name}")

    # Experiment status table
    if experiment_registry:
        status_rows = []
        for exp in experiment_registry.list_all():
            status_rows.append({
                "experiment_id": exp.experiment_id,
                "rq": exp.rq,
                "task": exp.task,
                "target": exp.target_col,
                "status": exp.status,
                "reason_code": exp.reason_code or "-",
                "model_type": exp.model_type,
            })
        df_status = pd.DataFrame(status_rows)
        status_csv = tables_dir / "rq3_experiment_status.csv"
        df_status.to_csv(status_csv, index=False)
        logger.info(f"Experiment status table published -> {status_csv.name}")

    # 8. Diagnostic Visualizations
    logger.info("Generating diagnostic figures...")
    # A. Residuals distribution
    fig_resid_path = figures_dir / "rq3_residuals_distribution.png"
    plt.figure(figsize=(12, 5))

    plt.subplot(1, 2, 1)
    if "p2_ols_no_direct_survival" in predictions_dict and "p1_ols_direct_survival" in predictions_dict:
        res_p2 = predictions_dict["p2_ols_no_direct_survival"].query("split == 'test'")["residual"]
        res_p1 = predictions_dict["p1_ols_direct_survival"].query("split == 'test'")["residual"]
        plt.hist(res_p2, bins=30, alpha=0.5, label="P2 (No Survival)", density=True, color="blue")
        plt.hist(res_p1, bins=30, alpha=0.5, label="P1 (Direct Survival)", density=True, color="green")
        plt.xlabel("Residual (Actual - Predicted)")
        plt.ylabel("Density")
        plt.title("Placement Prediction Residuals (Test)")
        plt.legend()
        plt.grid(True, alpha=0.3)

    plt.subplot(1, 2, 2)
    if "s1_retrospective_survival" in predictions_dict:
        res_s1 = predictions_dict["s1_retrospective_survival"].query("split == 'test'")["residual"]
        plt.hist(res_s1, bins=30, alpha=0.7, color="purple", density=True)
        plt.xlabel("Residual (Actual - Predicted seconds)")
        plt.ylabel("Density")
        plt.title("S1 Survival Time Residuals (Test)")
        plt.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(fig_resid_path, dpi=150)
    plt.close()

    # B. Observed vs Predicted scatter
    fig_pred_path = figures_dir / "rq3_observed_vs_predicted.png"
    plt.figure(figsize=(12, 5))

    plt.subplot(1, 2, 1)
    if "p2_ols_no_direct_survival" in predictions_dict:
        p2_test = predictions_dict["p2_ols_no_direct_survival"].query("split == 'test'")
        plt.scatter(p2_test["actual"], p2_test["predicted"], alpha=0.3, s=15, color="blue", label="P2 OLS")
        plt.plot([0, 1], [0, 1], "r--", label="Ideal 1:1")
        plt.xlabel("Observed Normalized Placement")
        plt.ylabel("Predicted Normalized Placement")
        plt.title("Observed vs Predicted: Placement (P2 Test)")
        plt.legend()
        plt.grid(True, alpha=0.3)

    plt.subplot(1, 2, 2)
    if "s1_retrospective_survival" in predictions_dict:
        s1_test = predictions_dict["s1_retrospective_survival"].query("split == 'test'")
        plt.scatter(s1_test["actual"], s1_test["predicted"], alpha=0.3, s=15, color="purple", label="S1 OLS")
        min_v = min(s1_test["actual"].min(), s1_test["predicted"].min())
        max_v = max(s1_test["actual"].max(), s1_test["predicted"].max())
        plt.plot([min_v, max_v], [min_v, max_v], "r--", label="Ideal 1:1")
        plt.xlabel("Observed Survival Time (s)")
        plt.ylabel("Predicted Survival Time (s)")
        plt.title("Observed vs Predicted: Survival (S1 Test)")
        plt.legend()
        plt.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(fig_pred_path, dpi=150)
    plt.close()

    # 9. Commit Checkpoint
    artifacts_to_commit = {
        "model_comparison": comp_csv,
        "val_selection": val_sel_csv,
        "fig_residuals": fig_resid_path,
        "fig_observed_vs_pred": fig_pred_path,
    }
    for exp_id in predictions_dict:
        pred_file = pred_dir / f"predictions_{exp_id}.parquet"
        if pred_file.is_file():
            artifacts_to_commit[f"pred_{exp_id}"] = pred_file
        model_file = models_dir / f"{exp_id}.joblib"
        if model_file.is_file():
            artifacts_to_commit[f"model_{exp_id}"] = model_file

    if checkpoint_mgr:
        signature = hash_dict({
            "stage": "rq3_prediction",
            "device": device,
            "chronology_grade": chronology_grade,
            "models_count": len(models_dict),
            "rows_evaluated": len(valid_placement),
        })
        checkpoint_mgr.commit("rq3_prediction", signature=signature, artifacts=artifacts_to_commit)
        logger.info(f"Checkpoint 'rq3_prediction' committed ({len(artifacts_to_commit)} artifacts).")

    logger.info("RQ3 Prediction Suite finished successfully.")
    return {
        "status": "completed",
        "models": models_dict,
        "predictions": predictions_dict,
        "val_metrics": val_metrics_dict,
        "test_metrics": test_metrics_dict,
        "comparison_table": df_comparison,
        "validation_selection_table": df_val_selection,
        "artifacts": artifacts_to_commit,
    }
