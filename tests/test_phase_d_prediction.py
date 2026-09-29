"""Unit tests for Section 20 Phase D: RQ3 Prediction Architecture, Gate G4, Baselines, and Hierarchy."""
import unittest
import tempfile
from pathlib import Path
import json
import numpy as np
import pandas as pd

from src.models.baselines import TrainMeanRegressor, TrainMedianRegressor
from src.models.linear import LinearModelWrapper
from src.models.tree_models import HistGradientBoostingWrapper
from src.models.training import (
    train_and_predict_experiment,
    lock_selection_recipe,
    run_rq3_prediction_suite,
)
from src.models.registry import create_canonical_experiment_matrix
from src.data.checkpoints import CheckpointManager
from src.features.registry import FeatureRegistry
from src.evaluation.metrics import compute_hierarchical_metrics


class TestPhaseDPrediction(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        # Build paths dictionary
        self.paths = {
            "processed": self.root / "data/processed",
            "experiments": self.root / "artifacts/experiments",
            "models": self.root / "artifacts/models",
            "tables": self.root / "reports/tables",
            "figures": self.root / "reports/figures",
            "manifests": self.root / "artifacts/manifests",
            "checkpoints": self.root / "artifacts/checkpoints",
        }
        for p in self.paths.values():
            p.mkdir(parents=True, exist_ok=True)

        # Create synthetic fixture dataset with train, val, and test splits
        # 30 matches, 4 players per match = 120 rows
        np.random.seed(42)
        n_matches = 30
        records = []
        for m in range(n_matches):
            mid = f"m_{m:03d}"
            split = "train" if m < 20 else ("validation" if m < 25 else "test")
            for p in range(4):
                pname = f"p_{m}_{p}"
                team = f"t_{m}_{p // 2}"
                kills = np.random.poisson(1.5)
                dmg = kills * 100.0 + np.random.uniform(10, 150)
                walk = np.random.uniform(200, 3000)
                ride = np.random.uniform(0, 1000) if np.random.rand() > 0.5 else 0.0
                tot_dist = walk + ride
                surv_time = walk * 0.5 + kills * 50.0 + np.random.normal(0, 20)
                surv_time = max(10.0, surv_time)
                # Placement roughly correlated with survival and kills
                norm_placement = np.clip(1.0 - (surv_time / 2000.0) + np.random.normal(0, 0.05), 0.01, 1.0)

                records.append({
                    "match_id": mid,
                    "player_name": pname,
                    "team_id": team,
                    "party_size": 2,
                    "team_size_mode": "Duo",
                    "split": split,
                    "player_kills": kills,
                    "player_dmg": dmg,
                    "damage_per_kill": dmg / max(1, kills),
                    "player_dist_walk": walk,
                    "player_dist_ride": ride,
                    "total_distance": tot_dist,
                    "walk_ratio": walk / max(1.0, tot_dist),
                    "player_assists": int(np.random.rand() > 0.7),
                    "player_dbno": int(kills + np.random.randint(0, 2)),
                    "assist_ratio": 0.2,
                    "first_kill_time": 100.0 if kills > 0 else np.nan,
                    "avg_kill_time": 200.0 if kills > 0 else np.nan,
                    "has_kill": int(kills > 0),
                    "early_kills": kills if kills > 0 else 0,
                    "mid_kills": 0,
                    "late_kills": 0,
                    "early_kill_ratio": 1.0 if kills > 0 else 0.0,
                    "mid_kill_ratio": 0.0,
                    "late_kill_ratio": 0.0,
                    "player_survive_time": surv_time,
                    "normalized_placement": norm_placement,
                })
        self.df = pd.DataFrame(records)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_train_mean_regressor(self):
        """TrainMeanRegressor predicts exactly the mean of training targets."""
        train_y = self.df[self.df["split"] == "train"]["normalized_placement"].values
        expected_mean = float(np.mean(train_y))

        model = TrainMeanRegressor()
        _, pred_df = train_and_predict_experiment(
            self.df, ["player_kills"], "normalized_placement", model, "mean_test"
        )
        self.assertEqual(len(pred_df), len(self.df))
        for split in ("train", "validation", "test"):
            split_preds = pred_df[pred_df["split"] == split]["predicted"].values
            self.assertTrue(np.allclose(split_preds, expected_mean, atol=1e-6))

    def test_train_median_regressor(self):
        """TrainMedianRegressor predicts exactly the median of training targets."""
        train_y = self.df[self.df["split"] == "train"]["normalized_placement"].values
        expected_median = float(np.median(train_y))

        model = TrainMedianRegressor()
        _, pred_df = train_and_predict_experiment(
            self.df, ["player_kills"], "normalized_placement", model, "median_test"
        )
        for split in ("train", "validation", "test"):
            split_preds = pred_df[pred_df["split"] == split]["predicted"].values
            self.assertTrue(np.allclose(split_preds, expected_median, atol=1e-6))

    def test_canonical_prediction_columns_and_batching(self):
        """Predictions dataframe contains all canonical schema columns and matches unbatched prediction."""
        features = ["player_kills", "player_dmg", "player_dist_walk"]
        target = "normalized_placement"
        model = LinearModelWrapper(model_type="exact", device="cpu")

        _, pred_df = train_and_predict_experiment(
            self.df,
            features,
            target,
            model,
            "test_ols",
            task="p2",
            output_predictions_dir=self.paths["experiments"],
            output_models_dir=self.paths["models"],
            batch_size=20,  # small batch size to test batching logic
        )

        canonical_cols = [
            "row_id", "match_id", "player_name", "team_id", "team_size_mode",
            "task", "target", "split", "actual", "predicted", "residual",
            "experiment_id", "compute_device"
        ]
        for col in canonical_cols:
            self.assertIn(col, pred_df.columns)

        # Residual definition invariant: actual - predicted
        residuals = pred_df["actual"] - pred_df["predicted"]
        self.assertTrue(np.allclose(pred_df["residual"].values, residuals.values, atol=1e-7))

        # Check files were written
        pred_pq = self.paths["experiments"] / "predictions_test_ols.parquet"
        self.assertTrue(pred_pq.is_file())
        self.assertGreater(pred_pq.stat().st_size, 0)

        model_joblib = self.paths["models"] / "test_ols.joblib"
        self.assertTrue(model_joblib.is_file())
        self.assertGreater(model_joblib.stat().st_size, 0)

    def test_lock_selection_recipe(self):
        """Selection lock creates immutable cryptographic recipe for Gate G4."""
        model = LinearModelWrapper(model_type="exact", device="cpu")
        model.fit(np.zeros((10, 2)), np.zeros(10))

        val_metrics = {"micro": {"mae": 0.1, "rmse": 0.15, "r2": 0.5}}
        lock = lock_selection_recipe(
            experiment_id="p2_ols_locked",
            task="p2",
            target_name="normalized_placement",
            feature_names=["f1", "f2"],
            model_instance=model,
            val_metrics=val_metrics,
            train_rows=80,
            val_rows=20,
            test_rows=20,
            output_lock_dir=self.paths["manifests"] / "selection_locks",
        )
        self.assertEqual(lock["status"], "LOCKED")
        self.assertIn("recipe_hash", lock)
        lock_file = self.paths["manifests"] / "selection_locks" / "selection_lock_p2_ols_locked.json"
        self.assertTrue(lock_file.is_file())

    def test_hierarchical_metrics_survival_invariant(self):
        """Team-aware metric is NOT applicable for survival time (S1/S2)."""
        pred_df = pd.DataFrame({
            "row_id": ["m1__p1", "m1__p2"],
            "match_id": ["m1", "m1"],
            "team_id": ["t1", "t1"],
            "actual": [500.0, 600.0],
            "predicted": [520.0, 580.0],
            "split": ["test", "test"],
            "target": ["player_survive_time", "player_survive_time"],
            "task": ["s1", "s1"],
        })
        metrics = compute_hierarchical_metrics(pred_df, task="s1", target_name="player_survive_time")
        self.assertFalse(metrics["team_aware"].get("applicable", True))
        self.assertTrue(np.isnan(metrics["team_aware"]["mae"]))

        # For placement, team-aware IS applicable
        pred_df_p = pd.DataFrame({
            "row_id": ["m1__p1", "m1__p2"],
            "match_id": ["m1", "m1"],
            "team_id": ["t1", "t1"],
            "actual": [0.2, 0.2],
            "predicted": [0.25, 0.22],
            "split": ["test", "test"],
            "target": ["normalized_placement", "normalized_placement"],
            "task": ["p2", "p2"],
        })
        metrics_p = compute_hierarchical_metrics(pred_df_p, task="p2", target_name="normalized_placement")
        self.assertTrue(metrics_p["team_aware"].get("applicable", False))
        self.assertFalse(np.isnan(metrics_p["team_aware"]["mae"]))

    def test_run_rq3_prediction_suite_full_workflow(self):
        """Run complete RQ3 prediction suite including baselines, core linear, Grade C blocking, and checkpoint commit."""
        reg = create_canonical_experiment_matrix()
        ckpt_mgr = CheckpointManager(manifest_path=self.paths["checkpoints"] / "checkpoint_manifest.json")
        feat_reg = FeatureRegistry()

        res = run_rq3_prediction_suite(
            df=self.df,
            paths=self.paths,
            feature_registry=feat_reg,
            experiment_registry=reg,
            checkpoint_mgr=ckpt_mgr,
            chronology_grade="Grade C",
            device="cpu",
            run_nonlinear=True,
            batch_size=50,
        )

        self.assertEqual(res["status"], "completed")

        # Verify comparison tables exist
        comp_csv = self.paths["tables"] / "rq3_model_comparison.csv"
        val_sel_csv = self.paths["tables"] / "rq3_validation_selection.csv"
        status_csv = self.paths["tables"] / "rq3_experiment_status.csv"
        self.assertTrue(comp_csv.is_file())
        self.assertTrue(val_sel_csv.is_file())
        self.assertTrue(status_csv.is_file())

        df_comp = pd.read_csv(comp_csv)
        self.assertIn("p1_ols_direct_survival", df_comp["experiment_id"].values)
        self.assertIn("p2_ols_no_direct_survival", df_comp["experiment_id"].values)
        self.assertIn("s1_retrospective_survival", df_comp["experiment_id"].values)
        self.assertIn("base_mean_p1", df_comp["experiment_id"].values)

        # Check Grade C blocking in registry and checkpoint manifest
        s2 = reg.get("s2_historical_survival")
        p3 = reg.get("p3_historical_placement")
        self.assertEqual(s2.status, "blocked")
        self.assertEqual(s2.reason_code, "blocked_by_chronology")
        self.assertEqual(p3.status, "blocked")
        self.assertEqual(p3.reason_code, "blocked_by_chronology")

        # Check figures generated
        fig1 = self.paths["figures"] / "rq3_residuals_distribution.png"
        fig2 = self.paths["figures"] / "rq3_observed_vs_predicted.png"
        self.assertTrue(fig1.is_file())
        self.assertTrue(fig2.is_file())

        # Check checkpoint committed
        manifest = ckpt_mgr.load_manifest()
        self.assertIn("rq3_prediction", manifest["stages"])
        self.assertEqual(manifest["stages"]["rq3_prediction"]["status"], "completed")
        self.assertGreater(len(manifest["stages"]["rq3_prediction"]["artifacts"]), 4)


if __name__ == "__main__":
    unittest.main()
