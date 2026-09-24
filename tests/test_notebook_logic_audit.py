import json
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

import duckdb
import numpy as np
import pandas as pd

from src.data.batch_ingest import staged_paths
from src.data.checkpoints import CheckpointManager
from src.data.io import atomic_write_csv
from src.data.download_data import download_file_with_checksum
from src.evaluation.finalize import build_final_results_manifest, verify_final_manifest_integrity
from src.evaluation.error_analysis import analyze_prediction_errors
from src.analysis.eda import compute_distribution_summary
from src.models.splits import create_split_assignments
from src.models.linear import LinearModelWrapper
from src.utils.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


class TestNotebookLogicAudit(unittest.TestCase):
    def test_interrupted_notebook_blocks_new_runtime_and_invalidates_descendants(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "checkpoint.json"
            manager = CheckpointManager(manifest)
            for name, dependencies in [("01", []), ("02", ["01"]), ("04", ["02"])]:
                manager.begin_notebook(name, dependencies)
                manager.commit("notebook/" + name, "notebook_v1", {})
            manager.begin_notebook("01", [])  # Rerun fails after marking running.
            restored = CheckpointManager(manifest)
            with self.assertRaisesRegex(RuntimeError, "01"):
                restored.begin_notebook("02", ["01"])
            self.assertEqual(restored.load_manifest()["stages"]["notebook/04"]["status"], "stale")
            restored.commit("notebook/01", "notebook_v1", {})
            with self.assertRaisesRegex(RuntimeError, "02"):
                restored.begin_notebook("04", ["02"])
            restored.begin_notebook("02", ["01"])
            restored.commit("notebook/02", "notebook_v1", {})
            restored.begin_notebook("04", ["02"])

    def test_download_uses_local_file_and_rejects_truncated_response(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "data.zip"
            target.write_bytes(b"old archive")
            reply = io.BytesIO(b"short")
            reply.headers = {"Content-Length": "100"}
            with patch("src.data.download_data.urllib.request.urlopen", return_value=reply):
                with self.assertRaisesRegex(ValueError, "Incomplete download"):
                    download_file_with_checksum("https://example.test/data.zip", target)
            self.assertEqual(target.read_bytes(), b"old archive")
            reply = io.BytesIO(b"complete")
            reply.headers = {"Content-Length": "8"}
            from src.data.io import publish_file
            with patch("src.data.download_data.urllib.request.urlopen", return_value=reply), \
                    patch("src.data.download_data.publish_file", wraps=publish_file) as publish:
                download_file_with_checksum("https://example.test/data.zip", target)
            self.assertEqual(target.read_bytes(), b"complete")
            self.assertNotEqual(publish.call_args.args[0].parent, target.parent)

    def test_staging_checks_content_rows_duplicates_and_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shard = root / "agg_test.parquet"
            pd.DataFrame({"id": [1]}).to_parquet(shard)
            record = {"kind": "aggregate", "file": shard.name, "rows": 1, "sha256": hash_file(shard)}
            manifest = root / "batch_manifest.json"
            manifest.write_text(json.dumps({"complete": True, "shards": [record]}))
            self.assertEqual(staged_paths(root, "aggregate"), [shard])
            pd.DataFrame({"id": [2]}).to_parquet(shard)  # Valid footer but wrong data.
            with self.assertRaisesRegex(ValueError, "checksum"):
                staged_paths(root, "aggregate")
            record.update(sha256=hash_file(shard), rows=2)
            manifest.write_text(json.dumps({"complete": True, "shards": [record]}))
            with self.assertRaisesRegex(ValueError, "row count"):
                staged_paths(root, "aggregate")
            record["rows"] = 1
            manifest.write_text(json.dumps({"complete": True, "shards": [record, record]}))
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                staged_paths(root, "aggregate")
            record["file"] = "../outside.parquet"
            manifest.write_text(json.dumps({"complete": True, "shards": [record]}))
            with self.assertRaisesRegex(ValueError, "Invalid"):
                staged_paths(root, "aggregate")

    def test_checkpoint_survives_new_root_but_rejects_changed_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "owner"
            artifact = original / "data/result.csv"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("old")
            manifest = Path("artifacts/checkpoints/checkpoint_manifest.json")
            manager = CheckpointManager(original / manifest)
            manager.commit("stage", "sig", {"data": artifact})
            moved = root / "member"
            shutil.copytree(original, moved)
            manager = CheckpointManager(moved / manifest)
            self.assertTrue(manager.is_compatible("stage", "sig"))
            self.assertEqual(manager.restore("stage")["artifacts"]["data"], str(moved / "data/result.csv"))
            (moved / "data/result.csv").write_text("bad")
            self.assertFalse(manager.is_compatible("stage", "sig"))
            self.assertIsNone(manager.restore("stage"))

    def test_failed_csv_publication_preserves_report_and_empty_run_clears_stale_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "errors.csv"
            atomic_write_csv(output, pd.DataFrame({"old": [1]}))
            before = output.read_bytes()
            with patch("src.data.io.shutil.copyfile", side_effect=PermissionError("not writable")):
                with self.assertRaises(PermissionError):
                    atomic_write_csv(output, pd.DataFrame({"new": [2]}))
            self.assertEqual(output.read_bytes(), before)
            result = analyze_prediction_errors(pd.DataFrame({"split": ["train"]}), output)
            self.assertTrue(result.empty)
            self.assertTrue(pd.read_csv(output).empty)
            summary = compute_distribution_summary(pd.DataFrame({"x": [np.nan]}), ["x"])
            self.assertTrue(summary.empty)
            self.assertIn("feature", summary)

    def test_final_manifest_locks_predictions_and_ignores_incomplete_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            experiments = root / "artifacts/experiments"
            experiments.mkdir(parents=True)
            predictions = experiments / "predictions_p2_linear.parquet"
            pd.DataFrame({"prediction": [0.5]}).to_parquet(predictions)
            models = root / "artifacts/models"
            models.mkdir()
            (models / "model.uploading_123").write_bytes(b"partial")
            manifest = root / "artifacts/manifests/final.json"
            locked = build_final_results_manifest(root / "artifacts", root / "reports", {"p2": "p2_linear"}, manifest)
            self.assertIn(predictions.name, locked["predictions"])
            self.assertFalse(locked["models"])
            self.assertTrue(verify_final_manifest_integrity(manifest)[0])
            predictions.write_bytes(b"broken")
            self.assertFalse(verify_final_manifest_integrity(manifest)[0])

    def test_splits_validate_config_and_use_actual_utc_order(self):
        with tempfile.TemporaryDirectory() as directory, duckdb.connect() as con:
            root = Path(directory) / "team's project"
            root.mkdir()
            source, output, manifest = root / "meta.parquet", root / "split.parquet", root / "split.json"
            data = pd.DataFrame({"match_id": ["early", "later", "latest"], "observed_player_count": [2]*3,
                                 "match_date": ["2017-01-01T07:00:00+0700", "2017-01-01T01:00:00+0000", "2017-01-02"]})
            data.to_parquet(source)
            args = (con, source, output, manifest)
            first = create_split_assignments(*args, train_ratio=1/3, val_ratio=1/3, test_ratio=1/3)
            self.assertEqual(pd.read_parquet(output).set_index("match_id")["split"].to_dict(),
                             {"early": "train", "later": "validation", "latest": "test"})
            second = create_split_assignments(*args, train_ratio=1/3, val_ratio=1/3, test_ratio=1/3)
            self.assertEqual(first["config_hash"], second["config_hash"])
            for kwargs in ({"strategy": "typo"}, {"train_ratio": 0.9}, {"train_ratio": float("nan")}):
                with self.assertRaises(ValueError):
                    create_split_assignments(*args, **kwargs)
            data.loc[1, "match_id"] = "early"
            data.to_parquet(source)
            with self.assertRaisesRegex(ValueError, "one non-null"):
                create_split_assignments(*args)

    def test_linear_all_missing_training_features(self):
        model = LinearModelWrapper()
        model.fit(np.full((3, 2), np.nan), np.array([0., .5, 1.]))
        self.assertTrue(np.isfinite(model.predict(np.array([[1., 2.]]))).all())

    def test_notebooks_block_out_of_order_cells_and_invalidate_success_on_rerun_failure(self):
        for path in (ROOT / "notebooks").glob("*.ipynb"):
            notebook = json.loads(path.read_text(encoding="utf-8"))
            ordinary = [(i, "".join(c["source"])) for i, c in enumerate(notebook["cells"])
                        if c["cell_type"] == "code" and not c["metadata"].get("tags")]
            for _, source in ordinary[1:]:
                # All-in-One includes each stage's initialization; those may run first.
                if "if _pubg_progress.get(" not in source:
                    continue
                with self.subTest(notebook=path.name), self.assertRaisesRegex(RuntimeError, "cell"):
                    exec(source, {"paths": {}, "PROJECT_ROOT": ROOT})

        notebook = json.loads((ROOT / "notebooks/02_data_quality_and_structure.ipynb").read_text(encoding="utf-8"))
        sources = ["".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"]
        clean = next(s for s in sources if "clean_summary =" in s)
        metadata = next(s for s in sources if "total_matches =" in s)
        scope = {"paths": {"interim": ROOT, "tables": ROOT, "checkpoints": ROOT}, "PROJECT_ROOT": ROOT,
                 "_PUBG_CELL_PROGRESS": {"02_data_quality_and_structure.ipynb": 999},
                 "con": Mock(), "agg_shards": [],
                 "audit_and_clean_aggregate_data": Mock(side_effect=OSError("simulated failure"))}
        with patch("src.data.checkpoints.CheckpointManager"), self.assertRaisesRegex(OSError, "simulated"):
            exec(clean, scope)
        with self.assertRaisesRegex(RuntimeError, "cell"):
            exec(metadata, scope)


if __name__ == "__main__":
    unittest.main()
