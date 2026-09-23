import shutil
import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.hashing import hash_file, hash_dict, hash_dataframe, compute_signature
from src.utils.validation import (
    assert_finite,
    assert_non_negative,
    assert_valid_ratio,
    assert_same_index,
    assert_no_target_in_features,
)
from src.utils.runtime import check_environment
from src.evaluation.finalize import build_final_results_manifest, verify_final_manifest_integrity
from src.evaluation.importance import extract_feature_importance


class TestEvaluationAndUtils(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(__file__).resolve().parent / ".tmp_test_utils"
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_hashing_utilities(self):
        # File hashing
        f_path = self.test_dir / "sample.txt"
        f_path.write_text("PUBG research project 2026", encoding="utf-8")
        h1 = hash_file(f_path)
        self.assertEqual(len(h1), 64)

        # Dict hashing (order invariant)
        d1 = {"b": 2, "a": 1}
        d2 = {"a": 1, "b": 2}
        self.assertEqual(hash_dict(d1), hash_dict(d2))

        # DataFrame hashing
        df = pd.DataFrame({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
        df_hash = hash_dataframe(df)
        self.assertEqual(len(df_hash), 64)

        # Signature
        sig = compute_signature(arg1="val", num=42)
        self.assertEqual(len(sig), 64)

    def test_validation_assertions(self):
        df = pd.DataFrame({
            "a": [1.0, 2.0, 3.0],
            "b": [0.0, 5.0, 10.0],
            "ratio": [0.1, 0.5, 1.0],
        })
        # Should pass
        assert_finite(df, ["a", "b"])
        assert_non_negative(df, ["a", "b"])
        assert_valid_ratio(df, ["ratio"])
        assert_no_target_in_features(["a", "b"], "target_col")

        # Non-negative failure
        df_bad = pd.DataFrame({"neg": [-1.0, 2.0]})
        with self.assertRaises(ValueError):
            assert_non_negative(df_bad, ["neg"])

        # Ratio failure
        df_bad_ratio = pd.DataFrame({"ratio": [1.5, 0.5]})
        with self.assertRaises(ValueError):
            assert_valid_ratio(df_bad_ratio, ["ratio"])

        # Target leakage failure
        with self.assertRaises(ValueError):
            assert_no_target_in_features(["a", "player_survive_time"], "player_survive_time")

    def test_runtime_environment_check(self):
        env_res = check_environment(min_disk_gb=0.1)
        self.assertIn("status", env_res)
        self.assertTrue(env_res["can_write"])
        self.assertIn("runtime", env_res)

    def test_feature_importance_extraction(self):
        class DummyLinearModel:
            coefficients = [0.5, -1.2, 0.8]

        feat_names = ["feat_a", "feat_b", "feat_c"]
        df_imp = extract_feature_importance(DummyLinearModel(), feat_names)
        self.assertEqual(len(df_imp), 3)
        self.assertEqual(df_imp["feature"].iloc[0], "feat_b")  # Highest absolute importance: 1.2
        self.assertEqual(df_imp["absolute_importance"].iloc[0], 1.2)

    def test_finalize_manifest_locking_and_verification(self):
        reports_dir = self.test_dir / "reports"
        tables_dir = reports_dir / "tables"
        tables_dir.mkdir(parents=True, exist_ok=True)
        sample_csv = tables_dir / "rq1_correlations.csv"
        sample_csv.write_text("feature,r,rho\nplayer_kills,0.4,0.5\n", encoding="utf-8")

        artifacts_dir = self.test_dir / "artifacts"
        models_dir = artifacts_dir / "models"
        models_dir.mkdir(parents=True, exist_ok=True)
        sample_mod = models_dir / "p1_model.txt"
        sample_mod.write_text("model_weights", encoding="utf-8")

        manifest_path = self.test_dir / "final_manifest.json"
        manifest = build_final_results_manifest(
            artifacts_root=artifacts_dir,
            reports_root=reports_dir,
            official_run_ids={"rq1": "run_01", "rq3": "run_02"},
            output_manifest_path=manifest_path,
        )
        self.assertIn("rq1_correlations.csv", manifest["tables"])
        self.assertIn("p1_model.txt", manifest["models"])

        # Verify integrity
        valid, mismatches = verify_final_manifest_integrity(manifest_path)
        self.assertTrue(valid)
        self.assertEqual(len(mismatches), 0)

        # Corrupt file and verify detection
        sample_csv.write_text("corrupted content", encoding="utf-8")
        valid_corrupt, mismatches_corrupt = verify_final_manifest_integrity(manifest_path)
        self.assertFalse(valid_corrupt)
        self.assertEqual(len(mismatches_corrupt), 1)


if __name__ == "__main__":
    unittest.main()
