"""NB02 failure recovery must not disable the shared single-writer guard."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import duckdb

from src.data.checkpoints import CheckpointManager


NAME = "02_data_quality_and_structure.ipynb"
STAGE = "notebook/" + NAME
ROOT = Path(__file__).resolve().parents[1]


class TestNB02WriterRecovery(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.manager = CheckpointManager(self.root / "checkpoint.json")
        self.manager.begin_notebook(NAME, ["01"], signature="sig", writer_id="old")
        notebook = json.loads((ROOT / "notebooks" / NAME).read_text(encoding="utf-8"))
        self.clean = "".join(next(cell for cell in notebook["cells"]
                                  if "clean_summary =" in "".join(cell["source"]))["source"])
        self.init = "".join(next(cell for cell in notebook["cells"]
                                 if "_pubg_checkpoint.begin_notebook(" in "".join(cell["source"]))["source"])

    def scope(self, error):
        return {
            "paths": {"interim": self.root, "tables": self.root}, "PROJECT_ROOT": self.root,
            "con": Mock(), "agg_shards": [],
            "audit_and_clean_aggregate_data": Mock(side_effect=error),
            "_PUBG_CELL_PROGRESS": {NAME: 6}, "_pubg_checkpoint": self.manager,
            "_pubg_signature": "sig", "_pubg_writer": "old",
        }

    def test_processing_failures_release_owner_and_require_reinitialization(self):
        for error, status in (
            (OSError("synthetic processing failure"), "failed"),
            (MemoryError("synthetic RAM failure"), "resource_limited"),
            (duckdb.OutOfMemoryException("synthetic DuckDB OOM"), "resource_limited"),
            (KeyboardInterrupt("synthetic user interruption"), "failed"),
        ):
            with self.subTest(error=type(error).__name__):
                self.manager.begin_notebook(NAME, ["01"], signature="sig", writer_id="old", force_takeover=True)
                scope = self.scope(error)
                with self.assertRaises(type(error)):
                    exec(self.clean, scope)
                record = self.manager.load_manifest()["stages"][STAGE]
                self.assertEqual(record["status"], status)
                self.assertEqual(record["writer_id"], "old")
                self.assertEqual(record["dependencies"], ["notebook/01"])
                self.assertFalse(record["artifacts"])
                self.assertEqual(scope["_PUBG_CELL_PROGRESS"][NAME], -1)
                with self.assertRaisesRegex(RuntimeError, "cell"):
                    exec(self.clean, scope)
                self.manager.begin_notebook(NAME, ["01"], signature="sig", writer_id="new")
                self.assertEqual(self.manager.load_manifest()["stages"][STAGE]["writer_id"], "new")

    def test_old_writer_cannot_clear_new_owner_and_takeover_remains_explicit(self):
        before = self.manager.manifest_path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "PUBG_FORCE_STAGE_TAKEOVER=True"):
            self.manager.begin_notebook(NAME, ["01"], signature="sig", writer_id="new")
        self.assertEqual(self.manager.manifest_path.read_bytes(), before)
        self.manager.begin_notebook(NAME, ["01"], signature="sig", writer_id="new", force_takeover=True)
        before = self.manager.manifest_path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "owned by writer"):
            self.manager.record_failure(STAGE, "sig", "late failure", writer_id="old")
        self.assertEqual(self.manager.manifest_path.read_bytes(), before)
        with patch("builtins.print"), self.assertRaisesRegex(OSError, "original failure"):
            exec(self.clean, self.scope(OSError("original failure")))
        self.assertEqual(self.manager.manifest_path.read_bytes(), before)
        self.assertIn("PUBG_FORCE_STAGE_TAKEOVER = False", self.init)

    def test_failed_checkpoint_publication_does_not_mask_processing_error(self):
        before = self.manager.manifest_path.read_bytes()
        with patch.object(self.manager, "record_failure", side_effect=OSError("Drive unavailable")), \
                patch("builtins.print") as warning, self.assertRaisesRegex(MemoryError, "original OOM"):
            exec(self.clean, self.scope(MemoryError("original OOM")))
        warning.assert_called_once()
        self.assertEqual(self.manager.manifest_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
