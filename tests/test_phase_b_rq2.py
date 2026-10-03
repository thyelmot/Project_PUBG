"""Unit tests for Section 20 Phase B: RQ2 Profiling, Denominators, and Clustering Architecture."""
import hashlib
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler

from src.analysis.clustering import (
    CORE_PROFILE_FEATURES,
    fit_clustering_pipeline,
    prepare_clustering_matrix,
    assign_behavioral_cluster_names,
    run_k_diagnostics,
    execute_rq2_clustering,
    predict_clusters,
)
from src.analysis.rq2_workflow import (
    aggregate_profiles,
    load_profiles,
    retention_table,
    diagnostics,
    final_clustering,
    compute_profile_coverage_table,
    threshold_sensitivity,
)
from src.features.profiles import build_player_behavioral_profiles, profile_keys
from src.utils.config import load_config
from src.data.io import atomic_write_json, read_json
from src.utils.hashing import hash_file


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
                        "match_id": f"{mode}_{player}_{game}",
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
                        "assist_ratio": (assists / (kills + assists)) if (kills + assists) > 0 else np.nan,
                        "early_kills": early_kills,
                        "early_kill_ratio": (early_kills / kills) if kills > 0 else np.nan,
                        "mid_kill_ratio": 0.0 if kills > 0 else np.nan,
                        "late_kill_ratio": (1.0 - early_kills / kills) if kills > 0 else np.nan,
                        "phase_eligible_kill_count": kills if kills > 0 else np.nan,
                        "timing_coverage_status": "event_count_exact" if kills > 0 else "confirmed_no_kill_no_event",
                        "player_survive_time": float(300 + player * 50),
                        "normalized_placement": float(player / 15.0),
                        "team_placement": player + 1,
                    })
        self.frame = pd.DataFrame(records)

    def test_denominators_and_parity(self):
        """Verify denominators are tracked and DuckDB/Pandas implementations match identically."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            paths = {k: tmp / k for k in ("processed", "interim", "tables", "manifests", "checkpoints", "temp_dir")}
            for p in paths.values():
                p.mkdir()
            src_pq = paths["processed"] / "player_match_features.parquet"
            split_pq = paths["interim"] / "split_assignments.parquet"
            self.frame.to_parquet(src_pq, index=False)
            pd.DataFrame({"match_id": self.frame["match_id"].unique(), "split": "train"}).to_parquet(split_pq, index=False)
            atomic_write_json(paths["manifests"] / "mode_analysis.json", {
                "recommended_rq2_strategy": "per_mode", "scope": "development",
                "source_checksum": hash_file(src_pq), "split_checksum": hash_file(split_pq),
            })

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
            out_duck_sorted = out_duck.sort_values(keys).reset_index(drop=True)
            out_pan_sorted = out_pan.sort_values(keys).reset_index(drop=True)[out_duck.columns]
            pd.testing.assert_frame_equal(out_duck_sorted, out_pan_sorted, check_dtype=False, atol=1e-10, rtol=1e-10)

            evidence_path = paths["manifests"] / "mode_analysis.json"
            evidence = read_json(evidence_path)
            evidence["source_checksum"] = "stale"
            atomic_write_json(evidence_path, evidence)
            with self.assertRaisesRegex(ValueError, "stale"):
                load_profiles(cfg, paths)

    def test_missing_event_and_singleton_semantics(self):
        """Missing events stay unknown; confirmed no-kill is an observed false; singleton std is undefined."""
        base = self.frame.iloc[0].to_dict()
        rows = []
        for kills, early, phase_n, status in (
            (0, 0, np.nan, "confirmed_no_kill_no_event"),
            (2, np.nan, np.nan, "aggregate_kill_event_missing"),
            (1, 1, 1, "event_count_exact"),
        ):
            row = dict(base, player_name="semantic", player_kills=kills, early_kills=early,
                       phase_eligible_kill_count=phase_n, timing_coverage_status=status,
                       damage_per_kill=np.nan if kills == 0 else 100.0,
                       early_kill_ratio=1.0 if phase_n == 1 else np.nan,
                       mid_kill_ratio=0.0 if phase_n == 1 else np.nan,
                       late_kill_ratio=0.0 if phase_n == 1 else np.nan)
            rows.append(row)
        singleton = dict(rows[-1], player_name="singleton")
        profiles, _ = build_player_behavioral_profiles(pd.DataFrame(rows + [singleton]))
        semantic = profiles.set_index("player_name").loc["semantic"]
        self.assertEqual(semantic["timing_observed_matches"], 2)
        self.assertEqual(semantic["early_combat_match_ratio_valid_matches"], 2)
        self.assertEqual(semantic["early_combat_match_ratio"], 0.5)
        self.assertEqual(semantic["avg_early_kill_ratio_valid_matches"], 1)
        self.assertEqual(semantic["avg_early_kill_ratio"], 1.0)
        self.assertEqual(semantic["std_kills_status"], "estimated")
        one = profiles.set_index("player_name").loc["singleton"]
        self.assertTrue(pd.isna(one["std_kills"]))
        self.assertEqual(one["std_kills_status"], "insufficient_n")
        self.assertNotIn("mean_damage_per_kill", CORE_PROFILE_FEATURES)
        self.assertEqual(len(CORE_PROFILE_FEATURES), 14)

    def test_phase_mean_is_not_pooled_kill_ratio(self):
        rows = []
        for kills, early in [(1, 1), (3, 0)]:
            row = dict(self.frame.iloc[0], player_name="unequal", player_kills=kills,
                       early_kills=early, phase_eligible_kill_count=kills,
                       timing_coverage_status="event_count_exact", early_kill_ratio=early / kills,
                       mid_kill_ratio=1 - early / kills, late_kill_ratio=0.)
            rows.append(row)
        profiles, _ = build_player_behavioral_profiles(pd.DataFrame(rows))
        self.assertEqual(profiles.avg_early_kill_ratio.iloc[0], .5)  # mean(1/1, 0/3), not 1/4
        self.assertEqual(profiles.avg_early_kill_ratio_valid_matches.iloc[0], 2)
        self.assertAlmostEqual(profiles.std_kills.iloc[0], np.sqrt(2.))  # ddof=1

    def test_c3_scaler_consistency(self):
        """Verify C3 sensitivity uses RobustScaler when scaler_type is robust."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            profiles, outcomes = build_player_behavioral_profiles(self.frame, group_by_mode=False)
            profiles = profiles[profiles["games_played"] >= 2].reset_index(drop=True)
            outcomes = outcomes.merge(profiles[["player_name"]], on="player_name", how="inner")

            original_transform = RobustScaler.fit_transform
            with patch.object(RobustScaler, "fit_transform", autospec=True,
                    side_effect=original_transform) as transformed:
                res_robust = execute_rq2_clustering(
                    profiles, outcomes, n_clusters=2, output_dir=output_dir / "robust",
                    scaler_type="robust", random_state=42, device="cpu", c2_max_profiles=5,
                )
            c3_inputs = [call.args[1] for call in transformed.call_args_list
                if call.args[1].shape[1] == len(CORE_PROFILE_FEATURES) + 1]
            self.assertEqual(len(c3_inputs), 1)
            np.testing.assert_allclose(c3_inputs[0][:, -1], profiles.games_played.to_numpy(float))
            self.assertEqual(res_robust["status"] if "status" in res_robust else "completed", "completed")
            rob_df = pd.read_csv(output_dir / "robust" / "clustering_robustness.csv")
            self.assertIn("C3_Games_Played_Sensitivity", rob_df["comparison"].values)
            c2 = rob_df.set_index("comparison").loc["C2_Hierarchical_vs_KMeans"]
            indices = np.load(output_dir / "robust" / "c2_sample_indices.npy")
            self.assertEqual(len(indices), 5)
            self.assertEqual(c2["sampling_rule"], "uniform_without_replacement_configured_cap")
            self.assertEqual(c2["scope"], "supporting_validation")
            self.assertEqual(c2["sample_identity_sha256"], hashlib.sha256(indices.tobytes()).hexdigest())
            c3 = rob_df.set_index("comparison").loc["C3_Games_Played_Sensitivity"]
            self.assertEqual(c3["scope"], "supporting_sensitivity_robust")

            c4 = threshold_sensitivity(profiles, {
                "min_games_candidates": [1, 2, 3], "scaler": "robust",
                "device": "cpu", "random_state": 42,
            }, 2)
            self.assertTrue({"n_profiles_a", "n_profiles_b", "n_common",
                             "common_coverage_a", "common_coverage_b"}.issubset(c4.columns))
            self.assertTrue(c4["common_coverage_a"].between(0, 1).all())
            self.assertTrue(c4["common_coverage_b"].between(0, 1).all())

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

            preds = predict_clusters(loaded, profiles)

            assignments = pd.read_csv(output_dir / "cluster_assignments.csv")
            np.testing.assert_array_equal(preds, assignments["cluster_label"].values)
            c5 = pd.read_csv(output_dir / "c5_outcome_comparison.csv")
            self.assertTrue({"survival_valid_players", "placement_valid_players", "win_rate_valid_players",
                             "survival_valid_matches", "placement_valid_matches", "win_rate_valid_matches"}.issubset(c5.columns))

            changed_outcomes = outcomes.copy()
            changed_outcomes["mean_survive_time"] = changed_outcomes["mean_survive_time"] * -10 + 999
            changed_outcomes["mean_normalized_placement"] = 1 - changed_outcomes["mean_normalized_placement"]
            execute_rq2_clustering(profiles, changed_outcomes, 2, output_dir / "outcome_mutation", device="cpu")
            mutated = pd.read_csv(output_dir / "outcome_mutation" / "cluster_assignments.csv")
            np.testing.assert_array_equal(assignments["cluster_label"], mutated["cluster_label"])

    def test_evidence_sensitivities_and_experiment_status(self):
        profiles, outcomes = build_player_behavioral_profiles(self.frame, group_by_mode=False)
        profiles = profiles[profiles["games_played"] >= 2].reset_index(drop=True)
        outcomes = outcomes.merge(profiles[["player_name"]], on="player_name", how="inner")
        flags = {"c1_main_clustering": True, "c2_hierarchical_validation": True,
                 "c3_games_played_sensitivity": True, "c5_outcome_comparison": True}
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir)
            execute_rq2_clustering(
                profiles, outcomes, 2, output, device="cpu", experiments=flags,
                log_transform_features=["mean_damage"],
                timing_exclusion_features=["avg_early_kill_ratio", "avg_mid_kill_ratio",
                                           "avg_late_kill_ratio", "early_combat_match_ratio"],
                sensitivity_scalers=["robust"],
            )
            status = pd.read_csv(output / "clustering_robustness.csv")
            expected = {"C1_Main_KMeans", "C2_Hierarchical_vs_KMeans",
                        "C3_Games_Played_Sensitivity", "C5_Outcome_Comparison",
                        "D01_Timing_Exclusion_Sensitivity", "Scaler_Sensitivity_robust"}
            self.assertTrue(expected.issubset(set(status["comparison"])))
            self.assertTrue((status.loc[status["comparison"].isin(expected), "status"] == "completed").all())
            artifact = joblib.load(output / "fitted_clustering_artifacts.joblib")
            self.assertEqual(artifact["log_transform_features"], ["mean_damage"])
            np.testing.assert_array_equal(predict_clusters(artifact, profiles),
                                          pd.read_csv(output / "cluster_assignments.csv")["cluster_label"])

    def test_execution_gate_null_threshold(self):
        """Verify diagnostics safely stops when minimum_games_threshold is null."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            paths = {k: tmp / k for k in ("processed", "interim", "tables", "manifests", "checkpoints", "temp_dir")}
            for p in paths.values():
                p.mkdir()
            src_pq = paths["processed"] / "player_match_features.parquet"
            split_pq = paths["interim"] / "split_assignments.parquet"
            self.frame.to_parquet(src_pq, index=False)
            pd.DataFrame({"match_id": self.frame["match_id"].unique(), "split": "train"}).to_parquet(split_pq, index=False)
            atomic_write_json(paths["manifests"] / "mode_analysis.json", {
                "recommended_rq2_strategy": "per_mode", "scope": "development",
                "source_checksum": hash_file(src_pq), "split_checksum": hash_file(split_pq),
            })

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
            self.assertFalse((paths["processed"] / "player_profile_features.parquet").exists())
            stability = pd.read_csv(paths["tables"] / "rq2_min_games_stability.csv")
            self.assertTrue({"feature", "profile_coverage", "valid_match_fraction",
                             "feature_mean", "feature_std", "estimated_matrix_mb"}.issubset(stability.columns))
            self.assertFalse(any("surviv" in col or "placement" in col or "win" in col for col in stability.columns))

            with self.assertRaisesRegex(ValueError, "rq2_retention.csv"):
                diagnostics(profiles, cfg, paths)


if __name__ == "__main__":
    unittest.main()
