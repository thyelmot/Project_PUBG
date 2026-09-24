import shutil
import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.rq1 import run_rq1_analysis
from src.features.profiles import build_player_behavioral_profiles, filter_profiles_by_retention
from src.analysis.clustering import run_k_diagnostics, execute_rq2_clustering
from src.features.historical import build_historical_features
from src.features.registry import FeatureRegistry
from src.models.baselines import TrainMeanRegressor, TrainMedianRegressor
from src.models.linear import LinearModelWrapper
from src.models.training import train_and_predict_experiment
from src.evaluation.metrics import compute_hierarchical_metrics
from src.evaluation.bootstrap import run_paired_match_bootstrap
from src.evaluation.ablation import run_group_ablation_study
from src.evaluation.error_analysis import analyze_prediction_errors
from src.data.io import get_duckdb_connection, atomic_write_parquet


class TestRQ1RQ2RQ3Pipelines(unittest.TestCase):
    def test_k_diagnostics_with_one_sample_per_evaluated_cluster(self):
        from unittest.mock import patch
        with patch("src.analysis.clustering.KMeans") as constructor:
            model = constructor.return_value
            model.fit_predict.return_value = np.array([0, 1, 0, 1])
            model.predict.return_value = np.array([0, 1])
            model.inertia_ = 1.0
            result = run_k_diagnostics(np.arange(8).reshape(4, 2), k_range=[2], sample_size_for_silhouette=2)
        self.assertTrue(np.isnan(result.iloc[0]["silhouette_score"]))

    def setUp(self):
        self.test_dir = Path(__file__).resolve().parent / ".tmp_test_rq"
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.registry = FeatureRegistry()
        self.con = get_duckdb_connection(temp_dir=self.test_dir / "temp")

        # Create multi-player synthetic dataset with matches across 3 days
        np.random.seed(42)
        n_rows = 120
        players = [f"Player_{i%15}" for i in range(n_rows)]
        matches = [f"m_{i%10}" for i in range(n_rows)]
        teams = [f"t_{i%20}" for i in range(n_rows)]
        dates = [f"2017-11-{20 + (i%3):02d}T12:00:00+0000" for i in range(n_rows)]

        kills = np.random.poisson(lam=1.5, size=n_rows)
        survive = np.random.uniform(100.0, 1500.0, size=n_rows)
        dmg = kills * 100.0 + np.random.uniform(0.0, 50.0, size=n_rows)
        walk = np.random.uniform(100.0, 2000.0, size=n_rows)
        ride = np.random.uniform(0.0, 1000.0, size=n_rows)
        assists = np.random.poisson(lam=0.5, size=n_rows)
        dbno = np.random.poisson(lam=0.8, size=n_rows)

        df = pd.DataFrame({
            "match_id": matches,
            "player_name": players,
            "team_id": teams,
            "date": dates,
            "match_mode": "tpp",
            "party_size": 4,
            "observed_team_count": 5,
            "estimated_match_duration": 1500.0,
            "player_kills": kills,
            "player_dmg": dmg,
            "player_dist_walk": walk,
            "player_dist_ride": ride,
            "player_assists": assists,
            "player_dbno": dbno,
            "player_survive_time": survive,
            "team_placement": np.random.randint(1, 6, size=n_rows),
            "normalized_placement": np.random.uniform(0.0, 1.0, size=n_rows),
            "damage_per_kill": np.where(kills > 0, dmg / np.maximum(kills, 1), np.nan),
            "total_distance": walk + ride,
            "walk_ratio": walk / (walk + ride),
            "assist_ratio": np.where(assists + kills > 0, assists / np.maximum(assists + kills, 1), np.nan),
            "event_kill_count": kills,
            "first_kill_time": np.where(kills > 0, np.random.uniform(50.0, 400.0, size=n_rows), np.nan),
            "avg_kill_time": np.where(kills > 0, np.random.uniform(100.0, 600.0, size=n_rows), np.nan),
            "early_kills": np.where(kills > 0, np.random.binomial(kills, 0.3), 0),
            "mid_kills": np.where(kills > 0, np.random.binomial(kills, 0.4), 0),
            "late_kills": np.where(kills > 0, np.random.binomial(kills, 0.3), 0),
            "early_kill_ratio": np.where(kills > 0, 0.3, np.nan),
            "mid_kill_ratio": np.where(kills > 0, 0.4, np.nan),
            "late_kill_ratio": np.where(kills > 0, 0.3, np.nan),
            "has_kill": kills > 0,
            "kills_per_minute": kills / (survive / 60.0),
            "damage_per_minute": dmg / (survive / 60.0),
            "walk_velocity": walk / survive,
            "ride_velocity": ride / survive,
        })

        # Assign split by match
        unique_m = df["match_id"].unique()
        train_m = set(unique_m[:6])
        val_m = set(unique_m[6:8])
        test_m = set(unique_m[8:])
        df["split"] = df["match_id"].map(lambda m: "train" if m in train_m else ("validation" if m in val_m else "test"))

        self.df = df
        self.pq_path = self.test_dir / "player_match_test.parquet"
        atomic_write_parquet(self.pq_path, df)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_rq1_pipeline(self):
        rq1_csv = self.test_dir / "rq1_test.csv"
        rq1_table = run_rq1_analysis(self.df, self.registry, rq1_csv)
        self.assertFalse(rq1_table.empty)

        # Invariant D01: early_kill_ratio / phase timing must NOT be valid primary predictor for player_survive_time
        surv_phase = rq1_table[(rq1_table["target"] == "player_survive_time") & (rq1_table["feature"] == "early_kill_ratio")]
        if not surv_phase.empty:
            self.assertFalse(surv_phase["is_primary_valid"].iloc[0])

    def test_rq2_clustering_pipeline(self):
        profiles, outcomes = build_player_behavioral_profiles(self.df)
        self.assertEqual(len(profiles), 15) # 15 unique players
        self.assertNotIn("games_played", [c for c in profiles.columns if c.startswith("mean_")])
        self.assertNotIn("mean_survive_time", profiles.columns) # Outcome isolated!

        filtered_prof, filtered_out = filter_profiles_by_retention(profiles, outcomes, min_games=2)
        self.assertGreater(len(filtered_prof), 0)

        # Diagnostics & Clustering
        feature_cols = [c for c in filtered_prof.columns if c.startswith("mean_") or c.startswith("avg_")]
        X = filtered_prof[feature_cols].values
        diag_df = run_k_diagnostics(X, k_range=[2, 3])
        self.assertEqual(len(diag_df), 2)

        res = execute_rq2_clustering(filtered_prof, filtered_out, n_clusters=2, output_dir=self.test_dir / "rq2")
        self.assertIn("centers_raw", res)
        self.assertIn("outcome_comparison", res)

    def test_historical_and_rq3_prediction(self):
        # 1. Historical features with Grade B
        hist_pq = self.test_dir / "historical_test.parquet"
        h_res = build_historical_features(self.con, self.pq_path, hist_pq, chronology_grade="Grade B", min_history_threshold=1)
        self.assertEqual(h_res["status"], "completed")

        # Test Grade C blocking (D08)
        c_res = build_historical_features(self.con, self.pq_path, hist_pq, chronology_grade="Grade C")
        self.assertEqual(c_res["status"], "blocked")
        self.assertEqual(c_res["reason_code"], "blocked_by_chronology")

        # 2. RQ3 Model Training: Baselines and Linear
        features = ["player_kills", "player_dmg", "player_dist_walk", "total_distance"]
        target = "normalized_placement"

        # Baseline: Mean
        mean_model = TrainMeanRegressor()
        _, mean_preds = train_and_predict_experiment(self.df, features, target, mean_model, "base_mean")
        self.assertEqual(len(mean_preds), len(self.df))

        # Linear model
        lin_model = LinearModelWrapper(model_type="exact")
        _, lin_preds = train_and_predict_experiment(self.df, features, target, lin_model, "lin_p2")
        self.assertEqual(len(lin_preds), len(self.df))

        # 3. Hierarchical Metrics
        test_lin_preds = lin_preds[lin_preds["split"] == "test"]
        metrics = compute_hierarchical_metrics(test_lin_preds)
        self.assertIn("micro", metrics)
        self.assertIn("match_aware", metrics)
        self.assertIn("team_aware", metrics)
        self.assertGreaterEqual(metrics["micro"]["mae"], 0.0)

        # 4. Paired Bootstrap Test
        test_mean_preds = mean_preds[mean_preds["split"] == "test"]
        boot_res = run_paired_match_bootstrap(test_lin_preds, test_mean_preds, n_replicates=20)
        self.assertIn("delta_mae", boot_res)

        # 5. Ablation Study
        ablation_csv = self.test_dir / "ablation_test.csv"
        abl_df = run_group_ablation_study(self.df, self.registry, features, target, ablation_csv)
        self.assertGreater(len(abl_df), 1)

        # 6. Error Analysis
        error_csv = self.test_dir / "error_test.csv"
        err_df = analyze_prediction_errors(lin_preds, error_csv)
        self.assertFalse(err_df.empty)


if __name__ == "__main__":
    unittest.main()
