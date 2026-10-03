import sys
import unittest
from pathlib import Path
import tempfile
import json
import subprocess

# Add Project_PUBG to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.config import load_config, resolve_paths, validate_config, describe_config_status
from src.utils.runtime import check_environment, estimate_disk_budget, save_runtime_snapshot
from src.features.registry import FeatureRegistry


class TestW00Setup(unittest.TestCase):
    def setUp(self):
        self.config_dir = Path(__file__).resolve().parent.parent / "configs"
        self.cfg = load_config(str(self.config_dir))

    def test_load_and_validate_config(self):
        self.assertIn("data", self.cfg)
        self.assertIn("schema", self.cfg)
        self.assertIn("features", self.cfg)
        self.assertIn("runtime", self.cfg)
        validate_config(self.cfg)

    def test_resolve_paths(self):
        paths = resolve_paths(self.cfg)
        self.assertIn("raw", paths)
        self.assertIn("interim", paths)
        self.assertIn("processed", paths)
        self.assertIn("checkpoints", paths)

    def test_environment_check(self):
        env = check_environment()
        self.assertIn(env["status"], ["healthy", "warning"])
        self.assertTrue(env["can_write"])

    def test_feature_registry_contracts(self):
        reg = FeatureRegistry()
        s1 = reg.get_allowed_features("s1")
        p1 = reg.get_allowed_features("p1")
        p2 = reg.get_allowed_features("p2")

        # Invariant D01: Phase timing and survival rate features MUST NOT be in S1
        self.assertNotIn("early_kills", s1)
        self.assertNotIn("kills_per_minute", s1)
        self.assertNotIn("player_survive_time", s1)

        # Invariant D02: P1 contains direct survival; P2 excludes direct survival
        self.assertIn("player_survive_time", p1)
        self.assertNotIn("player_survive_time", p2)

        # Ablation test: removing 'combat' group also removes 'damage_per_kill'
        t1 = reg.get_allowed_features("t1")
        ablated = reg.remove_group_and_descendants(t1, "combat")
        self.assertNotIn("player_kills", ablated)
        self.assertNotIn("player_dmg", ablated)
        self.assertNotIn("damage_per_kill", ablated)


# --- New tests for notebook 00 checklist (Phase V, Section 19) ---

class TestW00ConfigValidation(unittest.TestCase):
    """Checklist item 2: validate_config checks required field types/values."""

    def setUp(self):
        self.config_dir = Path(__file__).resolve().parent.parent / "configs"
        self.cfg = load_config(str(self.config_dir))

    def test_random_state_is_int(self):
        self.assertIsInstance(self.cfg["runtime"]["random_state"], int,
                              "runtime.random_state must be int")

    def test_mode_is_valid(self):
        self.assertIn(self.cfg["runtime"]["mode"], ("full", "development", "sample"),
                      "runtime.mode must be full/development (legacy sample is nonofficial)")

    def test_development_mode_preserves_explicit_nonofficial_scope(self):
        cfg = {**self.cfg, "runtime": {**self.cfg["runtime"], "mode": "development"}}
        validate_config(cfg)
        self.assertEqual(cfg["runtime"]["mode"], "development")
        self.assertEqual(cfg["runtime"]["chunk_size"], self.cfg["runtime"]["chunk_size"])

    def test_chunk_size_positive_int(self):
        cs = self.cfg["runtime"]["chunk_size"]
        self.assertIsInstance(cs, int)
        self.assertGreater(cs, 0)

    def test_duckdb_threads_positive_int(self):
        t = self.cfg["runtime"]["duckdb"]["threads"]
        self.assertIsInstance(t, int)
        self.assertGreater(t, 0)

    def test_duckdb_memory_limit_string(self):
        ml = self.cfg["runtime"]["duckdb"]["memory_limit"]
        self.assertIsInstance(ml, str)
        self.assertTrue(len(ml) > 0)

    def test_rq2_mode_strategy_locked_to_per_mode(self):
        ms = self.cfg["rq2"]["mode_strategy"]
        self.assertEqual(ms, "per_mode",
                         "rq2.mode_strategy must be 'per_mode' per project decision")

    def test_rq2_mode_decision_reason_nonempty(self):
        reason = self.cfg["rq2"].get("mode_decision_reason", "")
        self.assertTrue(reason and isinstance(reason, str),
                        "rq2.mode_decision_reason must be a non-empty string")

    def test_rq2_device_declared(self):
        device = self.cfg["rq2"].get("device")
        self.assertIn(device, ("cuda", "cpu"),
                      "rq2.device must be 'cuda' or 'cpu'")

    def test_rq3_device_declared(self):
        device = self.cfg["rq3"].get("device")
        self.assertIn(device, ("cuda", "cpu"),
                      "rq3.device must be 'cuda' or 'cpu'")

    def test_validate_config_raises_on_bad_random_state(self):
        """validate_config must raise ValueError when random_state is not int."""
        bad_cfg = {k: v for k, v in self.cfg.items()}
        bad_cfg["runtime"] = {**self.cfg["runtime"], "random_state": "bad"}
        with self.assertRaises(ValueError):
            validate_config(bad_cfg)

    def test_validate_config_raises_on_bad_mode(self):
        bad_cfg = {k: v for k, v in self.cfg.items()}
        bad_cfg["runtime"] = {**self.cfg["runtime"], "mode": "unknown"}
        with self.assertRaises(ValueError):
            validate_config(bad_cfg)

    def test_validate_config_raises_on_bad_mode_strategy(self):
        bad_cfg = {k: v for k, v in self.cfg.items()}
        bad_cfg["rq2"] = {**self.cfg.get("rq2", {}), "mode_strategy": "overall",
                          "mode_decision_reason": "x"}
        # "overall" is technically valid but we only test it reaches validation;
        # we use a truly invalid value here to confirm the guard works.
        bad_cfg["rq2"]["mode_strategy"] = "invalid_strategy"
        with self.assertRaises(ValueError):
            validate_config(bad_cfg)

    def test_validate_config_raises_on_bad_device_and_paths(self):
        bad_device = {**self.cfg, "rq2": {**self.cfg["rq2"], "device": "auto"}}
        with self.assertRaises(ValueError):
            validate_config(bad_device)
        bad_paths = {**self.cfg, "paths": {**self.cfg["paths"], "active_environment": "missing"}}
        with self.assertRaises(ValueError):
            validate_config(bad_paths)

    def test_describe_config_status_returns_list(self):
        rows = describe_config_status(self.cfg)
        self.assertIsInstance(rows, list)
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertIn("field", row)
            self.assertIn("status", row)
            self.assertIn(row["status"], ("ok", "required", "pending"))

    def test_describe_config_status_required_fields_ok(self):
        """All 'required' fields must be 'ok' in the committed config."""
        rows = describe_config_status(self.cfg)
        not_ok = [r for r in rows if r["status"] == "required"]
        self.assertEqual(not_ok, [],
                         "These required fields are unset: " + str([r["field"] for r in not_ok]))


class TestW00EnvironmentCheck(unittest.TestCase):
    """Checklist items 5, 6, 7: environment check, disk budget, raise_on_critical."""

    def test_check_environment_returns_expected_keys(self):
        env = check_environment()
        for key in ("status", "can_write", "free_disk_gb", "total_disk_gb",
                    "warnings", "remediation", "runtime"):
            self.assertIn(key, env, f"check_environment() must return key '{key}'")

    def test_check_environment_remediation_is_list(self):
        env = check_environment()
        self.assertIsInstance(env["remediation"], list)

    def test_check_environment_rejects_wrong_project_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(RuntimeError) as error:
                check_environment(
                    target_dir=tmpdir,
                    min_disk_gb=0.0,
                    raise_on_critical=True,
                    required_files=["configs/data.yaml", "src/utils/config.py"],
                )
            self.assertIn("configs/data.yaml", str(error.exception))

    def test_check_environment_raise_on_critical_when_unwritable(self):
        """raise_on_critical=True must raise RuntimeError for a non-writable dir."""
        if sys.platform == "win32":
            self.skipTest("chmod cannot make directories read-only on Windows")
        with tempfile.TemporaryDirectory() as tmpdir:
            no_write = Path(tmpdir) / "readonly"
            no_write.mkdir()
            import stat
            no_write.chmod(stat.S_IREAD | stat.S_IXUSR)
            try:
                with self.assertRaises(RuntimeError):
                    check_environment(target_dir=str(no_write), raise_on_critical=True)
            finally:
                no_write.chmod(stat.S_IREAD | stat.S_IWRITE | stat.S_IXUSR)

    def test_check_environment_no_raise_when_not_critical(self):
        """raise_on_critical=True must not raise when environment is healthy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = check_environment(target_dir=tmpdir, min_disk_gb=0.0, raise_on_critical=True)
            self.assertIn(result["status"], ("healthy", "warning"))

    def test_estimate_disk_budget_returns_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            budget = estimate_disk_budget(Path(tmpdir))
            for key in ("raw_gb", "staging_gb", "interim_gb", "processed_gb",
                        "spill_gb", "total_estimated_gb", "note"):
                self.assertIn(key, budget)

    def test_estimate_disk_budget_note_clarifies_not_drive_quota(self):
        """The note must explicitly clarify this is runtime disk, not Drive quota."""
        with tempfile.TemporaryDirectory() as tmpdir:
            budget = estimate_disk_budget(Path(tmpdir))
            note = budget["note"].lower()
            self.assertIn("not", note)
            self.assertIn("drive", note)

    def test_estimate_disk_budget_totals_sum_correctly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            budget = estimate_disk_budget(Path(tmpdir))
            expected = round(
                budget["staging_gb"] + budget["interim_gb"] +
                budget["processed_gb"] + budget["spill_gb"], 3
            )
            self.assertAlmostEqual(budget["total_estimated_gb"], expected, places=2)


class TestW00RuntimeSnapshot(unittest.TestCase):
    """Checklist item 3: save_runtime_snapshot records required fields."""

    def setUp(self):
        self.config_dir = Path(__file__).resolve().parent.parent / "configs"
        self.cfg = load_config(str(self.config_dir))
        self.project_root = Path(__file__).resolve().parent.parent

    def test_snapshot_saves_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "runtime_snapshot.json"
            snap = save_runtime_snapshot(out, self.project_root, self.cfg, {})
            self.assertTrue(out.is_file())
            loaded = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("snapshot_at", loaded)
            self.assertIn("runtime", loaded)
            self.assertIn("config_summary", loaded)
            self.assertIn("config", loaded)
            self.assertIn("source_hashes", loaded)
            self.assertIn("doc_hashes", loaded)

    def test_snapshot_config_summary_has_mode_strategy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "s.json"
            snap = save_runtime_snapshot(out, self.project_root, self.cfg, {})
            self.assertEqual(snap["config_summary"]["mode_strategy"],
                             self.cfg["rq2"]["mode_strategy"])

    def test_snapshot_source_hash_is_full_sha256(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "s.json"
            snap = save_runtime_snapshot(out, self.project_root, self.cfg, {})
            gh = snap["source_hashes"].get("src/utils/generate_notebooks.py", "")
            # SHA-256 hex = 64 chars
            self.assertEqual(len(gh), 64,
                             "generate_notebooks.py hash must be full SHA-256 (64 hex chars)")

    def test_snapshot_hashes_all_source_modules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            snap = save_runtime_snapshot(Path(tmpdir) / "s.json", self.project_root, self.cfg, {})
            self.assertIn("src/utils/runtime.py", snap["source_hashes"])
            self.assertIn("src/utils/config.py", snap["source_hashes"])

    def test_snapshot_doc_hashes_stored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "s.json"
            snap = save_runtime_snapshot(out, self.project_root, self.cfg,
                                         {"PUBG_RESEARCH_SPEC.md": "abc123"})
            self.assertEqual(snap["doc_hashes"]["PUBG_RESEARCH_SPEC.md"], "abc123")


class TestNotebook00ScientificPresentation(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self.notebook = self.root / "notebooks" / "00_setup.ipynb"
        self.data = json.loads(self.notebook.read_text(encoding="utf-8"))

    def test_scientific_notes_and_tables_are_present(self):
        markdown = "\n".join("".join(c.get("source", [])) for c in self.data["cells"] if c["cell_type"] == "markdown")
        code = "\n".join("".join(c.get("source", [])) for c in self.data["cells"] if c["cell_type"] == "code")
        for heading in (
            "Bối cảnh khoa học, phạm vi và tiêu chí thành công",
            "Xác minh project root và provenance đầu vào",
            "Tài nguyên, phiên bản và snapshot tái lập",
            "Kết luận vận hành, giới hạn và bàn giao",
        ):
            self.assertIn(heading, markdown)
        for table_id in ("BẢNG 00-A", "BẢNG 00-B", "BẢNG 00-C", "BẢNG 00-G", "BẢNG 00-J", "BẢNG 00-K"):
            self.assertIn(table_id, code)
        self.assertNotIn("BAO CAO TAI NGUYEN PHAN CUNG", code)
        self.assertNotIn("Notebook 00 hoan tat", code)

    def test_actual_notebook_runs_in_isolated_runtime_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            program = '''import json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
nb = json.load(open(sys.argv[1], encoding="utf-8"))
scope = {"PUBG_INSTALL_DEPENDENCIES": False, "__name__": "__main__"}
for index, cell in enumerate(nb["cells"]):
    if cell["cell_type"] == "code":
        exec(compile("".join(cell["source"]), f"notebook00-cell-{index}", "exec"), scope)
        if "storage-options" in cell.get("metadata", {}).get("tags", []):
            scope.update(PUBG_STORAGE_MODE="runtime", PUBG_REQUIRE_EXISTING_PROJECT=False)
'''
            run = subprocess.run(
                [sys.executable, "-c", program, str(self.notebook)], cwd=workspace,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            for table_id in ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K"):
                self.assertIn(f"BẢNG 00-{table_id}", run.stdout)
            snapshot = next(workspace.rglob("runtime_snapshot.json"))
            checkpoint = json.loads(next(workspace.rglob("checkpoint_manifest.json")).read_text(encoding="utf-8"))
            self.assertTrue(snapshot.is_file())
            self.assertEqual(checkpoint["stages"]["notebook/00_setup.ipynb"]["status"], "completed")
if __name__ == "__main__":
    unittest.main()

