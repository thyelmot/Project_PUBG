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
        # Placement is a team target: fixture must not assign conflicting player targets.
        self.df["normalized_placement"] = self.df.groupby(["match_id", "team_id"])["normalized_placement"].transform("first")

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

    def development_config(self):
        from src.utils.config import load_config
        cfg = load_config(str(Path(__file__).resolve().parents[1] / "configs"))
        cfg["rq3"]["device"] = "cpu"  # Isolated fixture, not a production fallback.
        return cfg

    def run_development(self, frame=None, **kwargs):
        return run_rq3_prediction_suite(self.df if frame is None else frame, self.paths,
            config=self.development_config(), device="cpu", run_nonlinear=True, batch_size=7, **kwargs)

    def test_run_rq3_prediction_suite_full_workflow(self):
        """Nine real candidates, test closed; old automatic G4 behavior is forbidden."""
        reg = create_canonical_experiment_matrix()
        ckpt = CheckpointManager(self.paths["checkpoints"] / "checkpoint_manifest.json")
        with unittest.mock.patch("src.models.training.lock_selection_recipe",
                                 side_effect=AssertionError("Cannot automatically approve G4")):
            result = self.run_development(experiment_registry=reg, checkpoint_mgr=ckpt)
        self.assertEqual(result["status"], "pending_selection")
        self.assertEqual(result["test_metrics"], {})
        self.assertGreaterEqual(len(result["models"]), 12)
        for task in ["s1", "p1", "p2"]:
            self.assertGreaterEqual(sum(pd.read_parquet(p,columns=["task"]).task.iloc[0] == task for p in result["predictions"].values()), 3)
        for name in ["s2_historical_survival", "p3_historical_placement"]:
            self.assertEqual(reg.get(name).status, "blocked")
            self.assertEqual(reg.get(name).reason_code, "blocked_by_chronology")
            self.assertIsNone(reg.get(name).metrics)
        self.assertEqual(ckpt.load_manifest()["stages"]["rq3_prediction"]["status"], "blocked")
        self.assertFalse((self.paths["manifests"] / "selection_locks").exists())
        for exp_id, pred_path in result["predictions"].items():
            pred=pd.read_parquet(pred_path)
            self.assertEqual(set(pred.split), {"train", "validation"})
            import joblib
            model = joblib.load(self.paths["models"] / f"{exp_id}.joblib")
            meta = json.loads((self.paths["models"] / f"meta_{exp_id}.json").read_text())
            original = self.df.set_index(["match_id","player_name"])
            keys = list(zip(pred.match_id,pred.player_name))
            x = original.loc[keys, meta["features"]].values
            np.testing.assert_allclose(model.predict(x), pred.predicted, atol=1e-10)
            self.assertEqual(meta["test_samples"], 0)
            if meta["features"] and hasattr(model,"pipeline") and model.pipeline is not None and "scaler" in model.pipeline.named_steps:
                train_x=self.df.loc[self.df.split == "train",meta["features"]].to_numpy(dtype=float)
                np.testing.assert_allclose(model.pipeline.named_steps["imputer"].statistics_,
                                           np.nanmean(train_x,axis=0),atol=1e-10)
                np.testing.assert_allclose(model.pipeline.named_steps["scaler"].mean_,
                                           np.nanmean(train_x,axis=0),atol=1e-10)
            if "baseline" in exp_id:
                y = self.df.loc[self.df.split == "train",meta["target"]]
                expected = y.mean() if exp_id.endswith("mean") else y.median()
                np.testing.assert_allclose(pred.predicted,expected)
                self.assertEqual(meta["features"], [])
        saved=json.loads((self.paths["manifests"]/"rq3_development_registry.json").read_text())
        self.assertEqual(saved["experiments"]["p2_baseline_mean"]["split_scope"],"development_train_validation")

    def test_final_test_mutation_does_not_change_development(self):
        first=self.run_development()
        original_predictions={key:pd.read_parquet(path) for key,path in first["predictions"].items()}
        changed=self.df.copy()
        changed.loc[changed.split == "test",["player_survive_time","normalized_placement","player_kills"]]=np.inf
        second=self.run_development(changed)
        pd.testing.assert_frame_equal(first["comparison_table"],second["comparison_table"])
        for exp_id in first["predictions"]:
            pd.testing.assert_frame_equal(original_predictions[exp_id],pd.read_parquet(second["predictions"][exp_id]))

    def test_common_cohort_and_fail_closed_features_split(self):
        frame=self.df.copy()
        frame.loc[0,"player_survive_time"]=np.nan
        frame.loc[1,"normalized_placement"]=1.5
        result=self.run_development(frame)
        p1=pd.read_parquet(result["predictions"]["p1_ols_direct_survival"])
        p2=pd.read_parquet(result["predictions"]["p2_ols_no_direct_survival"])
        self.assertEqual(set(p1.row_id),set(p2.row_id))
        self.assertEqual(len(p1),98)  # 100 development rows minus two invalid targets.
        with self.assertRaisesRegex(KeyError,"Configured features missing"):
            self.run_development(self.df.drop(columns="early_kills"))
        bad=self.df.copy()
        bad.loc[0,"split"]="validation"
        with self.assertRaisesRegex(ValueError,"exactly one split"):
            self.run_development(bad)
        bad=self.df.copy()
        bad.loc[0,"split"]=None
        with self.assertRaisesRegex(ValueError,"invalid split"):
            self.run_development(bad)

    def test_config_disabled_task_and_backend_error_no_fallback(self):
        from unittest.mock import patch
        cfg=self.development_config()
        cfg["rq3"]["experiments"]["p1_placement_retrospective_with_survival"]=False
        cfg["models"]["baselines"]["train_median"]["enabled"]=False
        result=run_rq3_prediction_suite(self.df,self.paths,config=cfg,device="cpu")
        self.assertFalse(any(pd.read_parquet(p,columns=["task"]).task.iloc[0]=="p1" for p in result["predictions"].values()))
        self.assertFalse(any(name.endswith("median") for name in result["models"]))
        self.assertIn("disabled_by_config",result["experiment_status_table"].reason_code.values)
        with patch("src.models.rq3_resources.resource_snapshot",return_value={"status":"ready","reason_code":None}), \
             patch("src.models.linear.make_linear",side_effect=RuntimeError("GPU unavailable")):
            with self.assertRaisesRegex(RuntimeError,"GPU unavailable"):
                run_rq3_prediction_suite(self.df,self.paths,config=self.development_config(),device="cuda")

    def test_real_notebook_cells_development_handoff(self):
        import base64, copy, io, os, shutil
        import nbformat
        from contextlib import redirect_stdout
        from unittest.mock import patch
        from src.models.training import load_rq3_development_data
        project=Path(__file__).resolve().parents[1]
        self.paths["interim"]=self.root/"data/interim"
        self.paths["interim"].mkdir(parents=True)
        self.df.drop(columns="split").to_parquet(self.paths["processed"]/"player_match_features.parquet",index=False)
        self.df[["match_id","split"]].drop_duplicates().to_parquet(self.paths["interim"]/"split_assignments.parquet",index=False)
        loaded=load_rq3_development_data(self.paths)
        self.assertEqual(len(loaded),100)
        self.assertNotIn("test",loaded.split.values)
        ckpt=CheckpointManager(self.paths["checkpoints"]/"checkpoint_manifest.json")
        notebook=nbformat.read(project/"notebooks/09_rq3_prediction.ipynb",as_version=4)
        scope={"paths":self.paths,"PROJECT_ROOT":project}
        displayed=[]
        outputs=[]
        def capture(value):
            displayed.append(value)
            if isinstance(value,pd.DataFrame):
                outputs.append(nbformat.v4.new_output("display_data",data={"text/html":value.to_html(index=False),"text/plain":value.to_string(index=False)}))
            elif value.__class__.__name__=="Image":
                outputs.append(nbformat.v4.new_output("display_data",data={"image/png":base64.b64encode(value.data).decode()}))
            elif value.__class__.__name__=="Markdown":
                outputs.append(nbformat.v4.new_output("display_data",data={"text/markdown":value.data}))
        with patch("src.utils.config.load_config",return_value=self.development_config()), \
             patch("src.utils.config.resolve_paths",return_value=self.paths), \
             patch("IPython.display.display",side_effect=capture):
            for cell in notebook.cells:
                if cell.cell_type != "code" or cell.metadata.get("tags"):
                    continue
                outputs=[]
                stream=io.StringIO()
                with redirect_stdout(stream):
                    exec(compile(cell.source,"NB09-synthetic","exec"),scope)
                cell.outputs=[nbformat.v4.new_output("stream",name="stdout",text=stream.getvalue())]+outputs
                cell.execution_count=1
        stages=ckpt.load_manifest()["stages"]
        self.assertEqual(stages["rq3_development"]["status"],"completed")
        self.assertEqual(stages["notebook/09_rq3_prediction.ipynb"]["status"],"blocked")
        handover=pd.read_csv(self.paths["manifests"] / "notebook_handover.csv")
        self.assertEqual(handover.status.iloc[0],"blocked")
        self.assertIn("pending G4",handover.next_step.iloc[0])
        with self.assertRaisesRegex(RuntimeError,"chưa hoàn tất"):
            ckpt.begin_notebook("10_ablation_error_analysis.ipynb",["09_rq3_prediction.ipynb"])
        expected_images=sum(Path(file).suffix==".png" for file in scope["res"]["artifacts"].values())
        self.assertEqual(sum(v.__class__.__name__=="Image" for v in displayed),expected_images)
        self.assertGreaterEqual(sum(isinstance(v,pd.DataFrame) for v in displayed),7)
        self.assertFalse((self.paths["experiments"]/"predictions_p2_linear.parquet").exists())
        evidence=os.environ.get("PUBG_PREDICTION_EVIDENCE_DIR")
        if evidence:
            dest=Path(evidence)
            dest.mkdir(parents=True,exist_ok=True)
            nbformat.write(notebook,dest/"09_fixture.ipynb")
            from nbconvert import HTMLExporter
            html,_=HTMLExporter().from_notebook_node(notebook)
            (dest/"09_fixture.html").write_text(html,encoding="utf-8")
            for name in ["tables","figures","models","experiments","manifests","checkpoints"]:
                shutil.copytree(self.paths[name],dest/name,dirs_exist_ok=True)

    def test_real_notebook_all_core_tasks_disabled(self):
        import os
        from unittest.mock import patch
        cfg=self.development_config()
        for key in ["s1_survival_retrospective", "p1_placement_retrospective_with_survival",
                    "p2_placement_retrospective_no_survival"]:
            cfg["rq3"]["experiments"][key]=False
        with patch.object(self,"development_config",return_value=cfg), patch.dict(os.environ,{"PUBG_PREDICTION_EVIDENCE_DIR":""}):
            self.test_real_notebook_cells_development_handoff()
        self.assertEqual(len(pd.read_csv(self.paths["tables"] / "rq3_development_validation.csv")),0)


if __name__ == "__main__":
    unittest.main()
