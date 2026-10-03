from datetime import datetime, timezone
import tempfile
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator

from src.data.cohort import ensure_row_id
from src.data.io import atomic_write_parquet, atomic_write_json, publish_file
from src.data.checkpoints import CheckpointManager
from src.evaluation.metrics import compute_hierarchical_metrics
from src.models.baselines import TrainMeanRegressor, TrainMedianRegressor
from src.models.compute import compute_info
from src.models.linear import LinearModelWrapper
from src.models.registry import ExperimentRegistry
from src.utils.hashing import hash_dict
from src.utils.hashing import hash_dataframe
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
    historical_paths: Optional[Dict[str, Path]] = None,
    historical_config: Optional[Dict[str, Any]] = None,
) -> Tuple[BaseEstimator, pd.DataFrame]:
    """Train estimator on train split only, and output unified predictions for train, val, and test.

    Invariants:
      1. Preprocessing and model are fit exclusively on train split.
      2. Missing or non-finite target rows are dropped before training.
      3. Predictions are generated in batches (batch_size) to prevent RAM exhaustion.
      4. Canonical prediction columns include: row_id, match_id, player_name, team_id,
         team_size_mode, task, target, split, actual, predicted, residual, experiment_id.
    """
    if task in {"s2", "p3"}:
        if historical_paths is None or historical_config is None:
            raise ValueError("Historical task requires verified NB08 status, paths and config.")
        from src.features.history_workflow import require_historical_dataset
        require_historical_dataset(historical_paths, historical_config)
    if target_name not in df.columns:
        raise ValueError(f"Target column '{target_name}' not in dataset.")
    if "split" not in df.columns:
        raise ValueError("Dataset missing 'split' column (train/validation/test).")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if "match_id" in df and (df.match_id.isna().any() or (df.groupby("match_id").split.nunique()!=1).any()):
        raise ValueError("Each match must belong to exactly one split")

    invalid_split = ~df["split"].isin(["train", "validation", "test"])
    if invalid_split.any():
        matches = df.loc[invalid_split, "match_id"].nunique(dropna=False) if "match_id" in df else "unknown"
        raise ValueError(
            f"Missing or invalid split assignments: {int(invalid_split.sum())} rows, {matches} matches. "
            "Rebuild notebook 02 for the current dataset; no rows were silently removed."
        )

    # Filter out rows with invalid or non-finite target
    valid_mask = df[target_name].notna() & np.isfinite(df[target_name])
    if target_name in {"player_survive_time","current_survive_time"}:
        valid_mask &= df[target_name]>0
    elif target_name in {"normalized_placement","current_normalized_placement"}:
        valid_mask &= df[target_name].between(0,1)
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

    logger.info(f"Fitting {experiment_id} on {int(train_mask.sum())} train rows ({len(feature_names)} features)...")
    if hasattr(model_instance,"fit_frame"):
        model_instance.fit_frame(valid_df.loc[train_mask],valid_df.loc[val_mask],feature_names,target_name)
    else:
        X_train = valid_df.loc[train_mask, feature_names].values
        y_train = valid_df.loc[train_mask, target_name].values.astype(np.float64)
        model_instance.fit(X_train, y_train)
        del X_train, y_train
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
    y_pred = np.asarray(y_pred,dtype=np.float64).reshape(-1)
    if len(y_pred)!=len(valid_df) or not np.isfinite(y_pred).all():
        raise ValueError("Invalid prediction shape or non-finite predictions; artifacts not published")

    # Build canonical predictions dataframe
    id_cols = [c for c in ["row_id", "match_id", "player_name", "team_id", "team_size_mode", "party_size", "split",
        "hist_games_played", "history_cutoff", "max_history_available_at", "prediction_time"] if c in valid_df.columns]
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
    run_id = experiment_id + "_" + hash_dict({"features":feature_names,
        "params":model_instance.get_params(deep=False), "target":target_name,
        "cohort":hashlib.sha256(pd.util.hash_pandas_object(valid_df, index=False).values.tobytes()).hexdigest()})[:16]
    pred_df["run_id"] = run_id
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
        with tempfile.TemporaryDirectory(prefix="pubg_model_") as directory:
            local_model = Path(directory) / "model.joblib"
            joblib.dump(model_instance, local_model)
            joblib.load(local_model)  # Reject an unreadable pipeline before replacing a good artifact.
            publish_file(local_model, model_file)
        meta_file = output_models_dir / f"meta_{experiment_id}.json"
        model_meta = {
            "experiment_id": experiment_id,
            "task": task,
            "target": target_name,
            "features": feature_names,
            "model_params": model_instance.get_params(deep=False),
            "run_id": run_id,
            "cohort_hash":hash_dataframe(valid_df[["row_id","match_id","split",target_name]].sort_values("row_id").reset_index(drop=True)),
            "n_features": len(feature_names),
            "train_samples": int(train_mask.sum()),
            "val_samples": int(val_mask.sum()),
            "test_samples": int(test_mask.sum()),
            "compute": compute,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        if hasattr(model_instance,"epoch_history_"):
            model_meta["streaming"]={"epochs":model_instance.epoch_history_,"best_epoch":model_instance.best_epoch_,
                "statistics_scope":"train_only_frozen_before_epochs","early_stopping_scope":"external_validation",
                "all_train_rows_each_epoch":True,"batch_size":model_instance.batch_size,"seed":model_instance.random_state}
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


def load_rq3_development_data(paths: Dict[str, Path], historical_config=None, config=None) -> pd.DataFrame:
    """Join verified assignments in SQL; never collect final-test behavior/targets."""
    from src.data.io import get_duckdb_connection
    con = get_duckdb_connection()
    try:
        source_path = paths["processed"] / "player_match_features.parquet"
        if historical_config is not None:
            from src.features.history_workflow import require_historical_dataset
            source_path = require_historical_dataset(paths, historical_config)
        source = source_path.as_posix().replace("'", "''")
        split = (paths["interim"] / "split_assignments.parquet").as_posix().replace("'", "''")
        con.execute(f"CREATE VIEW features AS SELECT * FROM read_parquet('{source}')")
        con.execute(f"CREATE VIEW assignments AS SELECT match_id, split FROM read_parquet('{split}')")
        invalid = con.execute("""
            SELECT count(*) FROM features f LEFT JOIN assignments s USING(match_id)
            WHERE s.split IS NULL OR s.split NOT IN ('train','validation','test')
        """).fetchone()[0]
        duplicates = con.execute("""
            SELECT count(*) FROM (SELECT match_id FROM assignments GROUP BY match_id HAVING count(*) != 1)
        """).fetchone()[0]
        if invalid or duplicates:
            raise ValueError("Missing/invalid split or duplicate match assignments; rebuild NB02.")
        if "split" in [r[0] for r in con.execute("DESCRIBE features").fetchall()]:
            raise ValueError("Features must not embed old split assignments; use canonical NB02 split.")
        eligible = " AND f.has_sufficient_history" if historical_config is not None else ""
        query = f"""
            SELECT f.*, s.split FROM features f JOIN assignments s USING(match_id)
            WHERE s.split IN ('train','validation'){eligible} ORDER BY f.match_id, f.player_name
        """
        from src.utils.config import load_config
        from src.utils.runtime import collect_runtime_info
        cfg = config or historical_config or load_config(str(Path(__file__).resolve().parents[2]/"configs"))
        count = con.execute(f"SELECT count(*) FROM ({query})").fetchone()[0]
        schema = con.execute(f"DESCRIBE ({query})").fetchall()
        # Include actual longest UTF-8 strings and room for cohort/working copies.
        width=0
        for column in schema:
            name=column[0].replace('"','""')
            width += (con.execute(f'SELECT coalesce(max(octet_length(encode("{name}"))),0) FROM ({query})').fetchone()[0]+128) if column[1]=="VARCHAR" else 32
        bytes_estimate = count * width * 4
        free = collect_runtime_info().get("available_ram_gb")
        limit = cfg["models"]["resource_limits"]["max_memory_gb"]
        audit = {"rows":count,"estimated_collect_bytes":bytes_estimate,"available_ram_gb":free,
                 "configured_limit_gb":limit,"scope":"train_validation_only","estimate_not_peak":True}
        audit_path = paths["manifests"] / ("rq3_history_collect_audit.json" if historical_config else "rq3_collect_audit.json")
        atomic_write_json(audit_path,audit)
        if not isinstance(free,(int,float)) or bytes_estimate > min(free,limit)*1024**3:
            CheckpointManager(paths["checkpoints"]/"checkpoint_manifest.json").record_failure(
                "rq3_development_collect",hash_dict(audit),"host RAM budget before collect",resource_limited=True,metadata=audit)
            raise MemoryError("Development collect exceeds host RAM budget; no rows sampled. See " + str(audit_path))
        frame=con.execute(query).df()
        from src.utils.hashing import hash_file
        frame.attrs["source_checksum"]=hash_file(source_path)
        frame.attrs["split_checksum"]=hash_file(paths["interim"]/"split_assignments.parquet")
        return frame
    finally:
        con.close()


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
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Development candidates only. No automatic G4 lock or final-test exposure.

    Verified history, paired timing, ablations and configured candidates remain
    development evidence until an explicit reviewed G4 decision authorizes test.
    """
    from src.features.registry import FeatureRegistry
    from src.models.registry import create_canonical_experiment_matrix, ExperimentDefinition
    from src.data.io import atomic_write_csv
    from src.utils.config import load_config

    cfg = config if config is not None else load_config(str(Path(__file__).resolve().parents[2] / "configs"))
    manager = checkpoint_mgr or CheckpointManager(paths["checkpoints"] / "checkpoint_manifest.json")
    manager.invalidate_descendants("rq3_prediction")
    manager.record_blocked("rq3_prediction", hash_dict(cfg), "pending_G4")
    from src.models.rq3_selection import selection_inputs
    provenance=selection_inputs(paths) if "interim" in paths and (paths["processed"]/"player_match_features.parquet").is_file() else None
    if provenance and df.attrs.get("source_checksum") and (
        df.attrs["source_checksum"]!=provenance["features"]["sha256"] or df.attrs["split_checksum"]!=provenance["split"]["sha256"]):
        raise ValueError("Development inputs changed since SQL collect")
    registry = feature_registry or FeatureRegistry()
    experiments = experiment_registry or create_canonical_experiment_matrix()
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if "split" not in df or not df["split"].isin(["train", "validation", "test"]).all():
        raise ValueError("Missing or invalid split assignments")
    if df["match_id"].isna().any() or (df.groupby("match_id")["split"].nunique() != 1).any():
        raise ValueError("Each match must belong to exactly one split")

    # Caller may supply a fixture containing test; discard it before target/feature inspection.
    development = ensure_row_id(df.loc[df["split"].isin(["train", "validation"])])
    # A test-only mutation can promote a whole pandas column int -> float.
    # Canonical numerical representation prevents irrelevant dtype changes in run IDs.
    for name in development.select_dtypes(include="number").columns:
        development[name]=development[name].astype(np.float64)
    survival = pd.to_numeric(development["player_survive_time"], errors="raise")
    placement = pd.to_numeric(development["normalized_placement"], errors="raise")
    valid_survival = np.isfinite(survival) & (survival > 0)
    valid_placement = np.isfinite(placement) & placement.between(0, 1)
    cohorts = {"s1": development.loc[valid_survival].copy(),
               "p1": development.loc[valid_survival & valid_placement].copy()}
    cohorts["p2"] = cohorts["p1"]
    feature_cfg = cfg["features"]["tasks"]
    features = {"s1": list(feature_cfg["s1_safe_features"]),
                "p1": list(feature_cfg["p1_features"]), "p2": list(feature_cfg["p2_features"])}
    if set(features["p1"]) != set(features["p2"]) | {"player_survive_time"}:
        raise ValueError("D02: P1/P2 must differ only by direct survival")
    for task, names in features.items():
        if len(set(names)) != len(names) or not set(names) <= set(registry.get_allowed_features(task)):
            raise ValueError(f"Feature allowlist violation: {task}")
        closure = registry.compute_dependency_closure(names)
        if task == "s1" and ("player_survive_time" in closure or any(
                registry.get(n) and (registry.get(n).requires_survival or
                                    "survival" in registry.get(n).forbidden_targets) for n in closure)):
            raise ValueError("D01: S1 contains survival-derived inputs")
        if not set(names) <= set(development.columns):
            raise KeyError(f"Configured features missing for {task}: {sorted(set(names)-set(development.columns))}")
        if set(cohorts[task]["split"]) != {"train", "validation"}:
            raise ValueError(f"Empty train/validation cohort: {task}")

    targets = {"s1": "player_survive_time", "p1": "normalized_placement", "p2": "normalized_placement"}
    flags = {"s1": "s1_survival_retrospective", "p1": "p1_placement_retrospective_with_survival",
             "p2": "p2_placement_retrospective_no_survival"}
    linear_ids = {"s1": "s1_retrospective_survival", "p1": "p1_ols_direct_survival",
                  "p2": "p2_ols_no_direct_survival"}
    history_reason = None
    for task, target in [("s2", "current_survive_time"), ("p3", "current_normalized_placement")]:
        for kind in ["mean", "median"]:
            experiments.register(ExperimentDefinition(f"{task}_baseline_{kind}", "rq3", task, target, [],
                kind, status="blocked", reason_code="historical_not_ready", split_scope="development_train_validation"))
    if any(cfg["rq3"]["experiments"][flag] for flag in ["s2_survival_historical", "p3_placement_historical"]):
        try:
            if chronology_grade == "Grade C":
                raise ValueError("blocked_by_chronology")
            history = load_rq3_development_data(paths, historical_config=cfg)
        except (ValueError, FileNotFoundError) as error:
            history_reason = "blocked_by_chronology" if chronology_grade == "Grade C" else str(error)
        else:
            for task, target, flag, exp_id in [
                ("s2", "current_survive_time", "s2_survival_historical", "s2_historical_survival"),
                ("p3", "current_normalized_placement", "p3_placement_historical", "p3_historical_placement")]:
                values = history[target]
                valid = np.isfinite(values) & ((values > 0) if task == "s2" else values.between(0, 1))
                cohorts[task] = history.loc[valid].copy()
                features[task] = registry.get_allowed_features(task)
                targets[task], flags[task], linear_ids[task] = target, flag, exp_id
    if cfg["rq3"]["experiments"]["t0_t1_timing_comparison"] and cfg["rq3"]["experiments"][flags["p2"]]:
        for task, key in [("t0", "t0_base_features"), ("t1", "t1_timing_features")]:
            cohorts[task] = cohorts["p2"]
            features[task] = list(feature_cfg[key])
            if not set(features[task]) <= set(registry.get_allowed_features(task)):
                raise ValueError(f"Timing allowlist violation: {task}")
            if not set(features[task]) <= set(development.columns):
                raise KeyError(f"Configured timing features missing: {task}")
            targets[task], flags[task], linear_ids[task] = targets["p2"], "t0_t1_timing_comparison", f"{task}_timing_ols"
        if set(features["t1"]) != set(features["p2"]) or not set(features["t0"]) <= set(features["t1"]):
            raise ValueError("Timing pair must be T0 subset of T1, T1 anchored to P2")
        # Replace legacy placeholder timing definitions; NB09 is the sole producer.
        for exp in experiments.list_all():
            if exp.task in {"t0", "t1"}:
                experiments.update_status(exp.experiment_id, "blocked", "superseded_by_nb09_timing_recipe")
    model_cfg = cfg["models"]
    if model_cfg["resource_limits"].get("fallback_to_sgd_on_oom"):
        raise ValueError("Automatic SGD/CPU fallback is forbidden; register a separate approved recipe")
    from src.models.rq3_resources import resource_snapshot
    from src.utils.hashing import hash_file
    code_hash = hash_dict({p.name: hash_file(p) for p in Path(__file__).parent.glob("*.py")})
    resource_rows, mode_rows = [], []
    predictions, models, val_metrics, rows, cohort_rows, artifacts = {}, {}, {}, [], [], {}
    for task, cohort in cohorts.items():
        if set(cohort["split"]) != {"train", "validation"}:
            for exp_id in [linear_ids[task], f"{task}_baseline_mean", f"{task}_baseline_median"]:
                experiments.register(ExperimentDefinition(exp_id, "rq3", task, targets[task], features[task],
                    "OLS" if exp_id == linear_ids[task] else "constant", status="blocked",
                    reason_code="no_eligible_train_validation", split_scope="development_train_validation"))
            continue
        for split, group in cohort.groupby("split"):
            cohort_rows.append({"task": task, "split": split, "rows": len(group),
                                "matches": group.match_id.nunique(), "input_rows": int((development.split == split).sum()),
                                "kill_event_rows":int(group.has_kill.fillna(False).astype(bool).sum()) if "has_kill" in group else None,
                                "excluded_rows": int((development.split == split).sum()) - len(group)})
        candidates = [
            (f"{task}_baseline_mean", TrainMeanRegressor, model_cfg["baselines"]["train_mean"]["enabled"], []),
            (f"{task}_baseline_median", TrainMedianRegressor, model_cfg["baselines"]["train_median"]["enabled"], []),
            (linear_ids[task], lambda: LinearModelWrapper(model_type="exact", device=device,
                fit_intercept=model_cfg["linear"]["exact_linear"]["fit_intercept"],
                standardize=cfg["features"]["transforms"]["standardize"],
                add_indicator=cfg["features"]["transforms"].get("add_indicator", False),
                log_indices=tuple(i for i,name in enumerate(names) if name in cfg["features"]["transforms"]["log_transform_features"])),
             model_cfg["linear"]["exact_linear"]["enabled"], features[task]),
        ]
        if task in {"t0", "t1"}:
            candidates = candidates[-1:]  # Same OLS recipe/cohort as P2, not a second baseline population.
        if task == cfg["rq3"]["experiments"]["ablation_full_task"]:
            for group in ["combat","movement","support","timing"]:
                groups = ["combat_timing_absolute","combat_timing_phase"] if group=="timing" else [group]
                remaining = list(features[task])
                for removed in groups:
                    remaining = registry.remove_group_and_descendants(remaining,removed)
                if remaining and remaining!=features[task]:
                    candidates.append((f"{task}_validation_ablation_{group}",candidates[-1][1],
                        model_cfg["linear"]["exact_linear"]["enabled"],remaining))
        if task not in {"t0","t1"}:
            from src.models.streaming import StreamingSGDWrapper
            settings=model_cfg["linear"]["sgd_regressor"]
            params={key:value for key,value in settings.items() if key not in {"enabled","streaming"}}
            candidates.append((f"{task}_sgd_streaming",lambda params=params: StreamingSGDWrapper(**params,
                standardize=cfg["features"]["transforms"]["standardize"],
                add_indicator=cfg["features"]["transforms"].get("add_indicator",False),
                log_indices=tuple(i for i,name in enumerate(names) if name in cfg["features"]["transforms"]["log_transform_features"]),
                batch_size=batch_size),settings["enabled"],features[task]))
        if task == "p2" and run_nonlinear:
            from src.models.tree_models import HistGradientBoostingWrapper, RandomForestWrapper
            for key, cls, exp_id in [
                ("hist_gradient_boosting",HistGradientBoostingWrapper,"p2_hgb_nonlinear_candidate"),
                ("random_forest",RandomForestWrapper,"p2_rf_nonlinear_candidate")]:
                settings = model_cfg["nonlinear_candidates"][key]
                params = {key:value for key,value in settings.items() if key != "enabled"}
                candidates.append((exp_id,lambda cls=cls,params=params: cls(**params),settings["enabled"],features[task]))
        for exp_id, factory, enabled, names in candidates:
            model_type = "SGD_streaming" if "_sgd_" in exp_id else "HistGradientBoosting" if "_hgb_" in exp_id else "RandomForest" if "_rf_" in exp_id else "OLS" if names else exp_id.rsplit("_",1)[1]
            exp = ExperimentDefinition(exp_id, "rq3", task, targets[task], names, model_type,
                                       split_scope="development_train_validation", chronology_grade=chronology_grade,
                                       config_hash=hash_dict(cfg))
            experiments.register(exp)
            if not enabled or not cfg["rq3"]["experiments"][flags[task]]:
                experiments.update_status(exp_id, "blocked", "disabled_by_config")
                continue
            if model_type=="SGD_streaming" and not model_cfg["linear"]["sgd_regressor"]["streaming"]:
                experiments.update_status(exp_id,"blocked","nonstreaming_sgd_recipe_not_registered")
                continue
            if model_type in {"HistGradientBoosting","RandomForest","SGD_streaming"} and device != "cpu":
                experiments.update_status(exp_id,"blocked","requested_gpu_backend_not_supported")
                continue  # Explicit unsupported candidate, never an unlabelled CPU fallback.
            resources = resource_snapshot(cohort, names, device if names else "cpu",
                model_cfg["resource_limits"]["max_memory_gb"])
            resources["experiment_id"] = exp_id
            resource_rows.append(resources)
            artifact_files = {"predictions": paths["experiments"] / f"predictions_{exp_id}.parquet",
                "model": paths["models"] / f"{exp_id}.joblib", "metadata": paths["models"] / f"meta_{exp_id}.json",
                "compute": paths["experiments"] / f"compute_{exp_id}.json"}
            candidate_cfg = {key:value for key,value in cfg.items() if key != "rq3"}
            candidate_cfg["rq3"] = {key:value for key,value in cfg["rq3"].items() if key != "selection"}
            signature = hash_dict({"code":code_hash,"config":candidate_cfg,"task":task,"features":names,
                "device":device if names else "cpu","batch_size":batch_size,
                "cohort":hashlib.sha256(pd.util.hash_pandas_object(cohort, index=False).values.tobytes()).hexdigest()})
            stage = f"rq3_development/{exp_id}"
            exp.signatures = {"recipe":signature}
            if resources["status"] != "ready":
                experiments.update_status(exp_id, resources["status"], resources["reason_code"])
                manager.record_blocked(stage, signature, resources["reason_code"], resources)
                if resources["status"] == "resource_limited":
                    manager.record_failure(stage, signature, resources["reason_code"], resource_limited=True, metadata=resources)
                continue
            if manager.is_compatible(stage, signature):
                model, pred = joblib.load(artifact_files["model"]), pd.read_parquet(artifact_files["predictions"])
                resources["execution"] = "compatible_resume"
            else:
                import time
                started = time.perf_counter()
                try:
                    model, pred = train_and_predict_experiment(
                        cohort, names, targets[task], factory(), exp_id, task=task,
                        output_predictions_dir=paths["experiments"], output_models_dir=paths["models"], batch_size=batch_size,
                        historical_paths=paths if task in {"s2", "p3"} else None,
                        historical_config=cfg if task in {"s2", "p3"} else None)
                except MemoryError as error:
                    experiments.update_status(exp_id,"resource_limited","fit_oom_no_fallback")
                    manager.record_failure(stage,signature,str(error),resource_limited=True,metadata=resources)
                    resource_rows[-1].update(status="resource_limited",reason_code="fit_oom_no_fallback")
                    continue
                except Exception as error:
                    oom=type(error).__name__=="OutOfMemoryError" or any(token in str(error).lower() for token in
                        ["out of memory","cuda_error_out_of_memory","std::bad_alloc"])
                    manager.record_failure(stage,signature,str(error),resource_limited=oom,metadata=resources)
                    if not oom:
                        raise
                    experiments.update_status(exp_id,"resource_limited","gpu_oom_no_fallback")
                    resources.update(status="resource_limited",reason_code="gpu_oom_no_fallback")
                    continue
                resources.update(execution="fit_all_train_rows", elapsed_seconds=time.perf_counter()-started)
                manager.commit(stage,signature,artifact_files,metadata={"scope":"train_validation_only"})
            exp.run_id = pred.run_id.iloc[0]
            exp.model_params=model.get_params(deep=False)
            exp.seed=getattr(model,"random_state",42)
            models[exp_id], predictions[exp_id] = model, artifact_files["predictions"]
            val = pred.loc[pred.split == "validation"]
            metrics = compute_hierarchical_metrics(val, task=task, target_name=targets[task])
            val_metrics[exp_id] = metrics
            row = {"experiment_id": exp_id, "task": task, "target": targets[task],
                   "scope": "validation", "n": len(val), "n_matches": val.match_id.nunique(),
                   "unit": "score [0,1]" if task in {"p1","p2","p3","t0","t1"} else "source time unit (pending verification)",
                   "mae": metrics["micro"]["mae"], "rmse": metrics["micro"]["rmse"],
                   "r2": metrics["micro"]["r2"], "match_mae": metrics["match_aware"]["mae"],
                   "r2_reason":metrics["micro"].get("r2_reason"),
                   "team_mae": metrics["team_aware"]["mae"], "compute_device": pred.compute_device.iloc[0],
                   "selection_status": "pending_G4"}
            rows.append(row)
            for mode,sub in val.groupby("team_size_mode",dropna=False):
                measured=compute_hierarchical_metrics(sub,task=task,target_name=targets[task])
                mode_rows.append({"experiment_id":exp_id,"task":task,"mode":mode,"scope":"validation",
                    "n":len(sub),"n_matches":sub.match_id.nunique(),"unit":row["unit"],
                    "mae":measured["micro"]["mae"],"rmse":measured["micro"]["rmse"],"r2":measured["micro"]["r2"]})
            exp.n_train, exp.n_val, exp.n_test = int((pred.split == "train").sum()), len(val), None
            for kind, file in [("predictions", paths["experiments"] / f"predictions_{exp_id}.parquet"),
                               ("model", paths["models"] / f"{exp_id}.joblib"),
                               ("metadata", paths["models"] / f"meta_{exp_id}.json"),
                               ("compute", paths["experiments"] / f"compute_{exp_id}.json")]:
                artifacts[f"{kind}_{exp_id}"] = file
                exp.artifact_paths[kind] = str(file)
            experiments.update_metrics(exp_id, {f"validation_{k}": row[k] for k in ["mae","rmse","r2"]})
            del val, pred  # Keep canonical paths, not all full-cohort prediction frames in RAM.

    for exp in experiments.list_all():
        if exp.task in {"s2", "p3"} and exp.task not in cohorts:
            experiments.update_status(exp.experiment_id, "blocked",
                history_reason or "disabled_by_config")
        elif exp.task in {"t0", "t1"} and exp.task not in cohorts:
            experiments.update_status(exp.experiment_id, "planned", "pending_paired_timing_recipe")
        elif exp.experiment_id == "p3_historical_expanding":
            experiments.update_status(exp.experiment_id, "blocked", "alias_of_p3_historical_placement")
    if run_nonlinear and model_cfg["nonlinear_candidates"]["xgboost"]["enabled"]:
        exp = ExperimentDefinition("p2_xgboost_nonlinear_candidate", "rq3", "p2", targets["p2"], features["p2"],
                                   "XGBoost", status="blocked", reason_code="backend_not_implemented_no_substitution")
        experiments.register(exp)
    comparison = pd.DataFrame(rows, columns=["experiment_id", "task", "target", "scope", "n", "n_matches",
        "unit", "mae", "rmse", "r2", "r2_reason", "match_mae", "team_mae", "compute_device", "selection_status"])
    coverage = pd.DataFrame(cohort_rows)
    status = pd.DataFrame([vars(exp) for exp in experiments.list_all()])
    resource_table = pd.DataFrame(resource_rows,columns=["experiment_id","measured_at_utc","requested_device","dataframe_bytes",
        "estimated_working_bytes","ram_available_bytes","configured_memory_bytes","vram_free_bytes","vram_total_bytes",
        "status","reason_code","execution","elapsed_seconds"])
    mode_table = pd.DataFrame(mode_rows,columns=["experiment_id","task","mode","scope","n","n_matches","unit","mae","rmse","r2"])
    from src.models.rq3_diagnostics import feature_diagnostics
    for key,file in feature_diagnostics(cohorts if models else {},features,models,paths,registry,max_memory_gb=model_cfg["resource_limits"]["max_memory_gb"]).items():
        artifacts["diagnostics_"+key]=file
    for key, frame, file in [("validation", comparison, "rq3_development_validation.csv"),
                             ("cohorts", coverage, "rq3_development_cohorts.csv"),
                             ("status", status, "rq3_development_status.csv"),
                             ("resources",resource_table,"rq3_development_resources.csv"),
                             ("mode_metrics",mode_table,"rq3_development_mode_metrics.csv")]:
        artifacts[key] = paths["tables"] / file
        atomic_write_csv(artifacts[key], frame)
    artifacts["registry"] = paths["manifests"] / "rq3_development_registry.json"
    atomic_write_json(artifacts["registry"], experiments.to_dict())
    artifacts["gate"] = paths["manifests"] / "rq3_development_gate.json"
    atomic_write_json(artifacts["gate"], {"status": "pending_selection", "final_test_exposed": False,
        "scope": "train_validation_only", "report_ready": False, "reason": "G4 not approved",
        "legacy_test_exposure": "unknown; prior code predicted test before automatic G4; audit previous runs"})
    if provenance:
        if selection_inputs(paths)!=provenance:
            raise ValueError("Development files changed during training; do not lock G4")
        artifacts["inputs"] = paths["manifests"]/"rq3_development_inputs.json"
        atomic_write_json(artifacts["inputs"],provenance)
    if checkpoint_mgr:
        checkpoint_mgr.invalidate_descendants("rq3_prediction")
        checkpoint_mgr.record_blocked("rq3_prediction", hash_dict(cfg), "pending_G4")
    return {"status": "pending_selection", "models": models, "predictions": predictions,
            "val_metrics": val_metrics, "test_metrics": {}, "comparison_table": comparison,
            "validation_selection_table": comparison, "cohort_table": coverage,
            "resource_table":resource_table,
            "mode_table":mode_table,
            "experiment_status_table": status, "artifacts": artifacts}
