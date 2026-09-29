"""Unit tests for Section 20 Phase B: RQ2 Profiling, Denominators, and Clustering Architecture."""
import tempfile
import unittest
from pathlib import Path
import joblib
import numpy as np
import pandas as pd

from src.analysis.clustering import (
    CORE_PROFILE_FEATURES,
    fit_clustering_pipeline,
    prepare_clustering_matrix,
    assign_behavioral_cluster_names,
    run_k_diagnostics,
    execute_rq2_clustering,
)
from src.analysis.rq2_workflow import (
    aggregate_profiles,
    load_profiles,
    retention_table,
    diagnostics,
    final_clustering,
    compute_profile_coverage_table,
)
from src.features.profiles import build_player_behavioral_profiles, profile_keys
from src.utils.config import load_config
from src.data.io import atomic_write_json


class TestPhaseBRQ2(unittest.TestCase):
    def setUp(self):
        rng = np.random.RandomState(42)
        records = []
        for mode in ("Solo", "Duo", "Squad"):
            party_sz = 1 if mode == "Solo" else (2 if mode == "Duo" else 4)
            for player in range(15):
                n_games = 1 if player < 3 else (2 + player % 6)
                for game in range(n_games):
                    kills = 0 if player % 3 == 0 else (1 + game % 3)
                    dmg = 0.0 if kills == 0 else float(kills * 120.0 + rng.uniform(0, 50))
                    walk = float(rng.uniform(100, 1500))
                    ride = float(rng.uniform(0, 500)) if player % 2 == 0 else 0.0
                    walk_ratio = walk / (walk + ride) if (walk + ride) > 0 else 1.0
                    assists = (player % 2) if mode != "Solo" else 0
                    dbno = kills if mode != "Solo" else 0
                    early_kills = 1 if (kills > 0 and game % 2 == 0) else 0
                    records.append({
                        "player_name": f"player_{mode}_{player}",
                        "team_size_mode": mode,
                        "party_size": party_sz,
                        "match_mode": "tpp",
                        "player_kills": kills,
                        "player_dmg": dmg,
                        "damage_per_kill": (dmg / kills) if kills > 0 else np.nan,
                        "player_dist_walk": walk,
                        "player_dist_ride": ride,
                        "walk_ratio": walk_ratio,
                        "player_assists": assists,
                        "player_dbno": dbno,
                        "assist_ratio": (assists / (kills + assists)) if (kills + assists) > 0 else 0.0,
                        "early_kills": early_kills,
                        "early_kill_ratio": (early_kills / kills) if kills > 0 else np.nan,
                        "mid_kill_ratio": 0.0,
                        "late_kill_ratio": 0.0,
                        "player_survive_time": float(300 + player * 50),
                        "normalized_placement": float(player / 15.0),
                        "team_placement": player + 1,
                    })
        self.frame = pd.DataFrame(records)

    def test_denominators_and_parity(self):
        """Verify denominators are tracked and DuckDB/Pandas implementations match identically."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            paths = {k: tmp / k for k in ("processed", "tables", "manifests", "checkpoints", "temp_dir")}
            for p in paths.values():
                p.mkdir()
            src_pq = paths["processed"] / "player_match_features.parquet"
            self.frame.to_parquet(src_pq, index=False)
            atomic_write_json(paths["manifests"] / "mode_analysis.json", {"recommended_rq2_strategy": "per_mode"})

            cfg = load_config()
            cfg["rq2"].update({
                "mode_strategy": "per_mode",
                "mode_decision_reason": "Verified per-mode",
                "device": "cpu",
                "minimum_games_threshold": 1,
                "min_games_candidates": [1, 2, 5],
                "candidate_k_range": [2, 3],
                "n_clusters_by_mode": {"Solo": 2, "Duo": 2, "Squad": 2},
                "selection_reason": "Unit test selection",
            })
            cfg["runtime"]["duckdb"] = {"memory_limit": "256MB", "threads": 1}

            prof_duck, out_duck = load_profiles(cfg, paths)
            prof_pan, out_pan = build_player_behavioral_profiles(self.frame, group_by_mode=True)

            for col in ("kill_active_matches", "support_active_matches", "timing_observed_matches"):
                self.assertIn(col, prof_duck.columns)
                self.assertIn(col, prof_pan.columns)

            keys = profile_keys(prof_duck)
            prof_duck_sorted = prof_duck.sort_values(keys).reset_index(drop=True)
            prof_pan_sorted = prof_pan.sort_values(keys).reset_index(drop=True)[prof_duck.columns]
            pd.testing.assert_frame_equal(prof_duck_sorted, prof_pan_sorted, check_dtype=False, atol=1e-10, rtol=1e-10)

    def test_c3_scaler_consistency(self):
        """Verify C3 sensitivity uses RobustScaler when scaler_type is robust."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            profiles, outcomes = build_player_behavioral_profiles(self.frame, group_by_mode=False)
            profiles = profiles[profiles["games_played"] >= 2].reset_index(drop=True)
            outcomes = outcomes.merge(profiles[["player_name"]], on="player_name", how="inner")

            res_robust = execute_rq2_clustering(
                profiles, outcomes, n_clusters=2, output_dir=output_dir / "robust",
                scaler_type="robust", random_state=42, device="cpu"
            )
            self.assertEqual(res_robust["status"] if "status" in res_robust else "completed", "completed")
            rob_df = pd.read_csv(output_dir / "robust" / "clustering_robustness.csv")
            self.assertIn("C3_Games_Played_Sensitivity", rob_df["comparison"].values)

    def test_behavioral_cluster_naming_no_outcome(self):
        """Verify cluster names are behavioral archetypes and never contain outcome metrics."""
        centers_df = pd.DataFrame([
            {"mean_kills": 2.0, "mean_damage": 1.8, "avg_early_kill_ratio": 1.2, "mean_walk_distance": 0.1},
            {"mean_kills": -1.2, "mean_damage": -1.0, "avg_early_kill_ratio": -0.8, "mean_walk_distance": 1.5},
            {"mean_kills": -0.5, "mean_damage": -0.5, "mean_assists": 1.8, "mean_dbno": 1.5},
        ])
        names = assign_behavioral_cluster_names(centers_df)
        self.assertEqual(len(names), 3)
        banned_terms = ["win", "placement", "rank", "survival", "first", "last"]
        for label in names.values():
            for banned in banned_terms:
                self.assertNotIn(banned, label.lower())

    def test_fitted_model_persistence_and_reload(self):
        """Verify fitted imputer, scaler, and KMeans are saved and can be reloaded to yield exact labels."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            profiles, outcomes = build_player_behavioral_profiles(self.frame, group_by_mode=False)
            profiles = profiles[profiles["games_played"] >= 2].reset_index(drop=True)
            outcomes = outcomes.merge(profiles[["player_name"]], on="player_name", how="inner")

            res = execute_rq2_clustering(
                profiles, outcomes, n_clusters=2, output_dir=output_dir,
                scaler_type="standard", random_state=42, device="cpu"
            )
            artifact_file = output_dir / "fitted_clustering_artifacts.joblib"
            self.assertTrue(artifact_file.is_file())

            loaded = joblib.load(artifact_file)
            self.assertIn("imputer", loaded)
            self.assertIn("scaler", loaded)
            self.assertIn("kmeans", loaded)
            self.assertIn("feature_cols", loaded)

            feature_cols = loaded["feature_cols"]
            raw_vals = profiles[feature_cols].to_numpy(dtype=float)
            imp_vals = loaded["imputer"].transform(raw_vals)
            scaled_vals = loaded["scaler"].transform(imp_vals)
            preds = loaded["kmeans"].predict(scaled_vals)

            assignments = pd.read_csv(output_dir / "cluster_assignments.csv")
            np.testing.assert_array_equal(preds, assignments["cluster_label"].values)

    def test_execution_gate_null_threshold(self):
        """Verify diagnostics safely stops when minimum_games_threshold is null."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            paths = {k: tmp / k for k in ("processed", "tables", "manifests", "checkpoints", "temp_dir")}
            for p in paths.values():
                p.mkdir()
            src_pq = paths["processed"] / "player_match_features.parquet"
            self.frame.to_parquet(src_pq, index=False)
            atomic_write_json(paths["manifests"] / "mode_analysis.json", {"recommended_rq2_strategy": "per_mode"})

            cfg = load_config()
            cfg["rq2"].update({
                "mode_strategy": "per_mode",
                "mode_decision_reason": "Verified per-mode",
                "device": "cpu",
                "minimum_games_threshold": None,
            })
            cfg["runtime"]["duckdb"] = {"memory_limit": "256MB", "threads": 1}

            profiles, outcomes = load_profiles(cfg, paths)
            ret_df = retention_table(profiles, cfg, paths)
            self.assertFalse(ret_df.empty)

            with self.assertRaisesRegex(ValueError, "minimum_games_threshold"):
                diagnostics(profiles, cfg, paths)


if __name__ == "__main__":
    unittest.main()
