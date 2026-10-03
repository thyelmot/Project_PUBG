import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.data.checkpoints import CheckpointManager
from src.data.cohort import align_cohort_rows, generate_row_id
from src.evaluation.bootstrap import run_paired_match_bootstrap
from src.utils.hashing import compute_stage_signature
from src.utils.logging import write_figure_metadata, write_handover


ROOT = Path(__file__).resolve().parents[1]


class TestPhase1InfrastructureContract(unittest.TestCase):
    def test_checkpoint_requires_artifacts_and_records_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = CheckpointManager(root / "checkpoint_manifest.json")
            manager.mark_running("stage", "sig", writer_id="alice")
            with self.assertRaises(ValueError):
                manager.commit("stage", "sig", {}, writer_id="alice")

            artifact = root / "result.parquet"
            pd.DataFrame({"value": [1, 2]}).to_parquet(artifact, index=False)
            manager.commit("stage", "sig", {"result": artifact}, writer_id="alice")
            record = manager.load_manifest()["stages"]["stage"]
            self.assertEqual(record["artifact_metadata"]["result"]["row_count"], 2)
            self.assertEqual(record["artifact_metadata"]["result"]["byte_size"], artifact.stat().st_size)
            self.assertTrue(record["artifact_metadata"]["result"]["schema"])
            self.assertTrue(manager.is_compatible("stage", "sig"))

    def test_single_writer_lock_and_takeover(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = CheckpointManager(Path(directory) / "checkpoint_manifest.json")
            manager.begin_notebook("01", [], signature="sig", writer_id="alice")
            with self.assertRaises(RuntimeError):
                manager.begin_notebook("01", [], signature="sig", writer_id="bob")
            manager.begin_notebook("01", [], signature="sig", writer_id="bob", force_takeover=True)
            self.assertEqual(manager.load_manifest()["stages"]["notebook/01"]["writer_id"], "bob")

    def test_row_identity_and_exact_evaluation_alignment(self):
        collision = pd.DataFrame({
            "match_id": ["a__b", "a"],
            "player_name": ["c", "b__c"],
        })
        self.assertEqual(generate_row_id(collision).nunique(), 2)

        anonymous = pd.DataFrame({
            "match_id": ["m1"], "player_name": [None],
            "source_file": ["part.csv"], "source_row": [7],
        })
        self.assertIn("lineage:", generate_row_id(anonymous).iloc[0])

        left = pd.DataFrame({"row_id": ["r1", "r2"], "target": [1.0, 2.0], "split": ["test", "test"]})
        right = pd.DataFrame({"row_id": ["r1"], "target": [1.0], "split": ["test"]})
        with self.assertRaises(ValueError):
            align_cohort_rows([left, right], target_col="target", require_exact=True)

        candidate = pd.DataFrame({
            "row_id": ["r1", "r2"], "match_id": ["m1", "m2"],
            "target_actual": [1.0, 2.0], "target_predicted": [1.1, 2.1],
        })
        reference = candidate.iloc[:1].copy()
        with self.assertRaises(ValueError):
            run_paired_match_bootstrap(candidate, reference, n_replicates=2)

    def test_signature_changes_with_research_components(self):
        with tempfile.TemporaryDirectory() as directory:
            code = Path(directory) / "helper.py"
            code.write_text("VERSION = 1", encoding="utf-8")
            base = compute_stage_signature(
                "stage", code_files=[code], cohort={"rows": 2}, split={"seed": 42},
                registry="r1", feature_set="f1", backend={"device": "cpu"},
            )
            code.write_text("VERSION = 2", encoding="utf-8")
            changed_code = compute_stage_signature(
                "stage", code_files=[code], cohort={"rows": 2}, split={"seed": 42},
                registry="r1", feature_set="f1", backend={"device": "cpu"},
            )
            changed_backend = compute_stage_signature(
                "stage", code_files=[code], cohort={"rows": 2}, split={"seed": 42},
                registry="r1", feature_set="f1", backend={"device": "cuda"},
            )
            self.assertNotEqual(base, changed_code)
            self.assertNotEqual(changed_code, changed_backend)

    def test_notebooks_08_to_11_commit_real_artifacts_and_handover_is_canonical(self):
        for number in range(8, 12):
            path = next((ROOT / "notebooks").glob(f"{number:02d}_*.ipynb"))
            notebook = json.loads(path.read_text(encoding="utf-8"))
            code = "\n".join("".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code")
            self.assertIn("_pubg_stage_artifacts", code)
            self.assertNotIn("_pubg_signature, {})", code)
            self.assertTrue(all(cell.get("execution_count") is None for cell in notebook["cells"] if cell["cell_type"] == "code"))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            figure = root / "chart.png"
            figure.write_bytes(b"png")
            handover = root / "handover.csv"
            catalog = root / "figures.csv"
