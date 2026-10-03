"""Tests for Phase A infrastructure: row_ids, cohort alignment, registry, and checkpoints."""
import unittest
import tempfile
from pathlib import Path
import pandas as pd
import numpy as np

from src.data.cohort import generate_row_id, ensure_row_id, align_cohort_rows, summarize_cohort
from src.models.registry import ExperimentRegistry, ExperimentDefinition, create_canonical_experiment_matrix
from src.data.checkpoints import CheckpointManager
from src.utils.hashing import hash_source_files, compute_stage_signature


class TestPhaseAInfrastructure(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generate_row_id_valid_and_duplicate(self):
        df = pd.DataFrame({
            "match_id": ["m1", "m1", "m2"],
            "player_name": ["p1", "p2", "p1"]
        })
        row_ids = generate_row_id(df)
        self.assertEqual(list(row_ids), ["match:2:m1|player:2:p1", "match:2:m1|player:2:p2", "match:2:m2|player:2:p1"])

        df_dup = pd.DataFrame({
            "match_id": ["m1", "m1"],
            "player_name": ["p1", "p1"]
        })
        with self.assertRaises(ValueError):
            generate_row_id(df_dup, raise_on_duplicate=True)

    def test_generate_row_id_nulls(self):
        df_null = pd.DataFrame({
            "match_id": ["m1", ""],
            "player_name": ["p1", "p2"]
        })
        with self.assertRaises(ValueError):
            generate_row_id(df_null)

    def test_ensure_row_id(self):
        df = pd.DataFrame({
            "match_id": ["m1", "m2"],
            "player_name": ["p1", "p2"]
        })
        ensured = ensure_row_id(df)
        self.assertIn("row_id", ensured.columns)
        self.assertEqual(ensured["row_id"].tolist(), ["match:2:m1|player:2:p1", "match:2:m2|player:2:p2"])

        ensured2 = ensure_row_id(ensured)
        self.assertEqual(ensured2["row_id"].tolist(), ["match:2:m1|player:2:p1", "match:2:m2|player:2:p2"])

    def test_align_cohort_rows(self):
        df1 = pd.DataFrame({
            "row_id": ["k1", "k2", "k3"],
            "target": [1.0, 2.0, 3.0],
            "split": ["train", "train", "test"]
        })
        df2 = pd.DataFrame({
            "row_id": ["k2", "k3", "k4"],
            "target": [2.0, 3.0, 4.0],
            "split": ["train", "test", "test"]
        })

        aligned1, aligned2 = align_cohort_rows([df1, df2], target_col="target", split_col="split")
        self.assertEqual(aligned1["row_id"].tolist(), ["k2", "k3"])
        self.assertEqual(aligned2["row_id"].tolist(), ["k2", "k3"])
        self.assertTrue((aligned1["target"].values == aligned2["target"].values).all())

        df3 = pd.DataFrame({
            "row_id": ["k2", "k3"],
            "target": [99.0, 3.0],
            "split": ["train", "test"]
        })
        with self.assertRaises(ValueError):
            align_cohort_rows([df1, df3], target_col="target", split_col="split")

    def test_summarize_cohort(self):
        df = pd.DataFrame({
            "row_id": ["m1__p1", "m1__p2", "m2__p3"],
            "match_id": ["m1", "m1", "m2"],
            "team_id": ["t1", "t1", "t2"],
            "player_name": ["p1", "p2", "p3"],
            "split": ["train", "train", "test"],
            "team_size_mode": ["Squad", "Squad", "Solo"]
        })
        summary = summarize_cohort(df)
        self.assertEqual(len(summary), 2)
        self.assertIn("rows_count", summary.columns)
        self.assertIn("matches_count", summary.columns)

    def test_experiment_registry_lifecycle_and_canonical(self):
        reg = create_canonical_experiment_matrix()
        p1 = reg.get("p1_ols_direct_survival")
        self.assertIsNotNone(p1)
        self.assertEqual(p1.status, "planned")
        self.assertIsNone(p1.metrics)

        reg.update_metrics("p1_ols_direct_survival", {"rmse": 0.08, "r2": 0.92})
        self.assertEqual(p1.status, "completed")
        self.assertEqual(p1.metrics["r2"], 0.92)

        reg.update_status("s2_historical_survival", "blocked", reason_code="blocked_by_chronology")
        s2 = reg.get("s2_historical_survival")
        self.assertEqual(s2.status, "blocked")
        self.assertEqual(s2.reason_code, "blocked_by_chronology")

        save_path = self.root / "experiments.json"
        reg.save(save_path)
        self.assertTrue(save_path.is_file())

        reg2 = ExperimentRegistry(save_path)
        self.assertEqual(reg2.get("s2_historical_survival").status, "blocked")

    def test_checkpoint_record_blocked(self):
        manifest_path = self.root / "checkpoint_manifest.json"
        mgr = CheckpointManager(manifest_path=manifest_path)
        mgr.record_blocked("s2_task", "sig_s2", "blocked_by_chronology", {"grade": "C"})

        manifest = mgr.load_manifest()
        self.assertIn("s2_task", manifest["stages"])
        self.assertEqual(manifest["stages"]["s2_task"]["status"], "blocked")
        self.assertEqual(manifest["stages"]["s2_task"]["reason_code"], "blocked_by_chronology")

    def test_hashing_helpers(self):
        f1 = self.root / "test1.txt"
        f2 = self.root / "test2.txt"
        f1.write_text("hello", encoding="utf-8")
        f2.write_text("world", encoding="utf-8")

        digest = hash_source_files([f1, f2])
        self.assertEqual(len(digest), 64)

        stage_sig = compute_stage_signature("test_stage", [f1], {"lr": 0.01}, [f2])
        self.assertEqual(len(stage_sig), 64)


if __name__ == "__main__":
    unittest.main()
