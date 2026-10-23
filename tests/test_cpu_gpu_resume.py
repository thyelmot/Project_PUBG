"""Real frozen CPU producer and metadata-only GPU simulation; no claim of CUDA execution."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import nbformat
import pandas as pd
from nbclient import NotebookClient

from src.io import Context, digest, read_json, write_json
from src.kaggle_runtime import (CPU_PRODUCER_511, cpu_resume_policy, prepare_handoff,
                                restore_handoff, source_fingerprint, verify_handoff)
from test_data_features import ROOT, fixture, write_config
from tools.build_kaggle_notebook import ENVIRONMENT_SETUP


class CpuGpuResume(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="pubg-cpu-gpu-producer-")
        cls.base = Path(cls.temp.name)
        cls.source = cls.base / "original"; cls.source.mkdir()
        cfg = fixture(cls.source)
        cfg["storage"]["layout"] = "normalized_v1"
        write_config(cls.source, cfg)
        with zipfile.ZipFile(ROOT / "tests/fixtures/audited_cpu_producer_511.zip") as archive:
            for name in archive.namelist():
                if name.startswith("src/"):
                    (cls.source / name).write_bytes(archive.read(name))
        if source_fingerprint(cls.source) != CPU_PRODUCER_511:
            raise AssertionError("Frozen producer differs")
        script = '''import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from src.io import Context
from src.preprocessing import ingest,clean_split
from src.features import base_features,combat_timing
from src.analysis import eda,relationship
from src.kaggle_runtime import prepare_handoff
ctx=Context(Path(sys.argv[1]),'development',progress=lambda _:None)
for s,f in zip(('S01','S02','S03','S04','S05','S06'),(ingest,clean_split,base_features,combat_timing,eda,relationship)):
    ctx.run(s,f)
prepare_handoff(ctx)
'''
        result = subprocess.run([sys.executable, "-B", "-c", script, str(cls.source)], cwd=cls.source,
            env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1","PYTHONUTF8":"1","PYTHONIOENCODING":"utf-8",
                 "OMP_NUM_THREADS":"1","OPENBLAS_NUM_THREADS":"1","MKL_NUM_THREADS":"1"},
            capture_output=True, text=True, encoding="utf-8", timeout=180)
        if result.returncode:raise AssertionError(result.stderr)
        cls.manifest = read_json(cls.source / "handoff_development.json")
        cls.software = cls.manifest["software"]
        cls.gpu_software = {**cls.software, "cuml-cu12":"26.2.0", "cupy-cuda12x":"14.0.1"}
        cls.raw = cls.base / "raw-remount"
        shutil.copytree(cls.source / "raw_fixture", cls.raw)
        cls.source_hashes = cls.tree_hashes(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @staticmethod
    def tree_hashes(root):
        return {p.relative_to(root).as_posix():digest(p) for p in root.rglob("*") if p.is_file()}

    def restore(self, target, raw=None):
        return restore_handoff(self.source, target, "development", raw or self.raw,
            "quangthinng/pubg-v3/versions/4", code_input=ROOT, allow_cpu_gpu=True)

    def test_verified_import_reuses_all_six_without_reexecuting_and_can_be_saved_again(self):
        with tempfile.TemporaryDirectory(prefix="pubg-cpu-gpu-import-") as folder, \
             patch("src.io.software_versions", return_value=self.gpu_software), \
             patch("src.kaggle_runtime.software_versions", return_value=self.gpu_software):
            target = Path(folder) / "project"
            self.restore(target)
            ctx = Context(target, "development", progress=lambda _:None)
            for stage, original in self.manifest["stages"].items():
                ctx.run(stage, lambda _:self.fail("A verified CPU producer was rerun"))
                record = ctx.require(stage)
                for key,value in original.items():
                    if key not in {"signature", "artifacts"}:self.assertEqual(record[key], value, key)
                self.assertEqual(record["producer_import"]["signature"], original["signature"])
                self.assertFalse(record["producer_import"]["recomputed"])
                for artifact in original["artifacts"]:
                    self.assertEqual(digest(target / artifact["path"]), artifact["sha256"])
            # S07 must be able to consume the restored normalized recipes, not just their file hashes.
            from src.analysis import bounded_profiles
            frames = []
            for consumer in (Context(self.source, "development"), ctx):
                with consumer.db() as con:
                    consumer.view(con, "restored", "player_match")
                    self.assertEqual(con.execute("SELECT count(*),count(distinct row_id) FROM restored").fetchone(), (240,240))
                    frames.append(bounded_profiles(con, consumer, True).sort_values(["player_name","team_size_mode"]).reset_index(drop=True))
            pd.testing.assert_frame_equal(frames[0], frames[1], rtol=1e-9, atol=1e-10)
            receipt = read_json(ctx.out / "provenance/cpu_gpu_resume.json")
            self.assertEqual(receipt["producer_software"], self.software)
            self.assertEqual(receipt["current_software"], self.gpu_software)
            self.assertEqual(receipt["recomputed_stages"], [])
            self.assertEqual(receipt["verification"]["verified_stages"], list(self.manifest["stages"]))
            with zipfile.ZipFile(ctx.out / "provenance/cpu_producer_511.zip") as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(archive.read("src/io.py"), (self.source / "src/io.py").read_bytes())
            prepare_handoff(ctx)
            verify_handoff(target, "development", "team/imported/versions/5")
            restored = Path(folder) / "second"
            restore_handoff(target, restored, "development", self.raw, "team/imported/versions/5")
            Context(restored, "development").require("S06")
            self.assertEqual(self.tree_hashes(self.source), self.source_hashes)
            changed = Context(target, "development"); changed.software["cupy-cuda12x"] = "different"
            with self.assertRaisesRegex(RuntimeError, "stale"):changed.require("S06")

    def test_explicit_opt_in_and_new_empty_target_are_required(self):
        with tempfile.TemporaryDirectory(prefix="pubg-cpu-gpu-optin-") as folder, \
             patch("src.kaggle_runtime.software_versions", return_value=self.gpu_software):
            target = Path(folder) / "project"
            with self.assertRaisesRegex(RuntimeError, "version mismatch"):
                restore_handoff(self.source, target, "development", self.raw, "team/book/versions/4")
            self.assertFalse(target.exists())
            with self.assertRaisesRegex(ValueError, "CODE_INPUT"):
                restore_handoff(self.source, target, "development", self.raw, "team/book/versions/4", allow_cpu_gpu=True)
            target.mkdir(); (target / "keep.txt").write_text("user result", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ghi đè"):self.restore(target)
            self.assertEqual((target / "keep.txt").read_text(), "user result")

    def test_actual_s00_uses_updated_code_input_and_restores_without_running_science_cells(self):
        # Actual notebook/kernel and original CPU producer; no CUDA is simulated in this test.
        with tempfile.TemporaryDirectory(prefix="pubg-cpu-gpu-notebook-") as folder:
            target = Path(folder) / "project"
            nb = nbformat.read(ROOT / "notebooks/PUBG_COURSEWORK.ipynb", as_version=4)
            nb.cells = [c for c in nb.cells if c.id in {"parameters", "bootstrap", "section-runner"}]
            nb.cells[0].source += (f"\nCODE_INPUT={str(ROOT)!r}\nRESUME_INPUT={str(self.source)!r}\n"
                f"PUBG_PROJECT_ROOT={str(target)!r}\nSOURCE_DIRECTORY={str(self.raw)!r}\nEXECUTION_MODE='development'\n"
                "SOURCE_VERSION=None\nSOURCE_LICENSE=''\nRUN_GPU_SMOKE=False\nSOURCE_TIME_UNIT_STATUS=''\n"
                "SOURCE_TIME_UNIT_ASSUMPTION_APPROVED=None\nSOURCE_TIME_UNIT_ASSUMPTION_SCOPE=''\n"
                "ALLOW_CPU_GPU_RESUME=True\nALLOW_S07_TSQR_RESUME=False\nSTART_STAGE='S07'\nEND_STAGE='S07'\n")
            executed = NotebookClient(nb, timeout=180, kernel_name="python3",
                resources={"metadata":{"path":folder}}).execute()
            self.assertTrue(all(c.execution_count for c in executed.cells))
            ctx = Context(target, "development")
            ctx.require("S06")
            self.assertEqual(ctx.manifest()["S06"]["producer_import"]["signature"],
                             self.manifest["stages"]["S06"]["signature"])
            self.assertEqual(source_fingerprint(target), source_fingerprint(ROOT))
            self.assertEqual(set(ctx.manifest()), {f"S{i:02d}" for i in range(1,7)})
            self.assertEqual(self.tree_hashes(self.source), self.source_hashes)

    def test_cpu_python_changes_models_partial_and_downstream_producers_are_rejected(self):
        for name in ("python", "numpy", "pandas", "duckdb", "pyarrow", "scikit-learn"):
            with self.subTest(package=name):
                changed = {**self.gpu_software, name:"different"}
                with self.assertRaisesRegex(RuntimeError, "identical Python"):
                    cpu_resume_policy(self.source, ROOT, self.manifest, changed)
        for change in ("partial", "downstream", "missing", "gpu_producer", "model", "reimport"):
            with self.subTest(change=change):
                manifest = copy.deepcopy(self.manifest)
                if change == "partial":manifest["stages"]["S06"]["status"] = "failed"
                elif change == "downstream":manifest["stages"]["S07"] = {"status":"completed"}
                elif change == "missing":del manifest["stages"]["S03"]
                elif change == "gpu_producer":manifest["software"]["cupy-cuda12x"] = "14.0.1"
                elif change == "model":manifest["entries"].append({"path":"outputs/development/models/old.joblib"})
                elif change == "reimport":manifest["stages"]["S01"]["producer_import"] = {"fake":True}
                with self.assertRaises((ValueError, RuntimeError)):
                    cpu_resume_policy(self.source, ROOT, manifest, self.gpu_software)

    def test_actual_s07_only_notebook_reuses_cpu_prefix_and_skips_other_producers(self):
        # Run all canonical cells in a fresh kernel, but use the labelled CPU fixture backend.
        with tempfile.TemporaryDirectory(prefix="pubg-s07-resume-notebook-") as folder:
            target=Path(folder)/"project"
            nb=nbformat.read(ROOT/"notebooks/PUBG_COURSEWORK.ipynb",as_version=4)
            cells={c.id:c for c in nb.cells}
            cells["parameters"].source+=(f"\nCODE_INPUT={str(ROOT)!r}\nRESUME_INPUT={str(self.source)!r}\n"
                f"PUBG_PROJECT_ROOT={str(target)!r}\nSOURCE_DIRECTORY={str(self.raw)!r}\nEXECUTION_MODE='development'\n"
                "SOURCE_VERSION=None\nSOURCE_LICENSE=''\nRUN_GPU_SMOKE=False\nSOURCE_TIME_UNIT_STATUS=''\n"
                "SOURCE_TIME_UNIT_ASSUMPTION_APPROVED=None\nSOURCE_TIME_UNIT_ASSUMPTION_SCOPE=''\n"
                "ALLOW_CPU_GPU_RESUME=True\nALLOW_S07_TSQR_RESUME=False\nSTART_STAGE='S07'\nEND_STAGE='S07'\n")
            cells["s07-execute"].source="S07_OPTIONS={'decision_mode':'auto','minimum_games':1}\nrun_section('S07',S07_OPTIONS)"
            guard=nbformat.v4.new_code_cell("def forbidden_producer(ctx):\n    raise AssertionError('Unexpected stage recomputation')\n"
                "STAGES.update({s:forbidden_producer for s in STAGES if s!='S07'})",id="test-no-recomputation")
            nb.cells.insert(nb.cells.index(cells["section-runner"])+1,guard)
            NotebookClient(nb,timeout=300,kernel_name="python3",resources={"metadata":{"path":folder}}).execute()
            ctx=Context(target,"development")
            ctx.require("S07")
            self.assertEqual(set(ctx.manifest()),{f"S{i:02d}" for i in range(1,8)})
            for stage in self.manifest["stages"]:
                self.assertEqual(ctx.manifest()[stage]["producer_import"]["signature"],self.manifest["stages"][stage]["signature"])
            self.assertEqual(self.tree_hashes(self.source),self.source_hashes)

    def test_notebook_environment_only_installs_missing_auxiliary_packages_and_never_restarts_or_upgrades_cpu_stack(self):
        import importlib.metadata
        original_version = importlib.metadata.version
        ns = {"INSTALL_RESUME_ENVIRONMENT":True,"RESUME_INPUT":str(self.source),
              "EXECUTION_MODE":"development","Path":Path,"sys":sys,"subprocess":subprocess}
        with patch("subprocess.check_call") as install:
            exec(ENVIRONMENT_SETUP, dict(ns))
            install.assert_not_called()
        def versions(name):
            return "0.5.13" if name == "nbclient" else original_version(name)
        with patch("importlib.metadata.version", side_effect=versions), patch("subprocess.check_call") as install:
            exec(ENVIRONMENT_SETUP, dict(ns))
            self.assertEqual(install.call_args.args[0], [sys.executable,"-m","pip","install","nbclient>=0.10,<1"])
        def old_duckdb(name):
            return "1.3.2" if name == "duckdb" else original_version(name)
        with patch("importlib.metadata.version", side_effect=old_duckdb), patch("subprocess.check_call") as install, patch.dict(sys.modules):
            sys.modules.pop("duckdb", None)
            exec(ENVIRONMENT_SETUP, dict(ns))
            self.assertEqual(install.call_args.args[0], [sys.executable,"-m","pip","install","duckdb=="+self.software["duckdb"]])
        with tempfile.TemporaryDirectory(prefix="pubg-resume-environment-") as folder:
            ns["RESUME_INPUT"] = folder
            manifest = copy.deepcopy(self.manifest)
            manifest["software"]["python"] = "0.0.0"
            write_json(manifest, Path(folder) / "handoff_development.json")
            with patch("subprocess.check_call") as install:
                with self.assertRaisesRegex(RuntimeError, "Python khác"):exec(ENVIRONMENT_SETUP, dict(ns))
                install.assert_not_called()
            manifest["software"]["python"] = self.software["python"]
            manifest["software"]["duckdb"] = "0.0.0"
            write_json(manifest, Path(folder) / "handoff_development.json")
            with patch("subprocess.check_call") as install:
                with self.assertRaisesRegex(RuntimeError, "DuckDB cũ còn"):exec(ENVIRONMENT_SETUP, dict(ns))
                install.assert_not_called()
        with patch("subprocess.check_call") as install:
            exec(ENVIRONMENT_SETUP, {**ns,"EXECUTION_MODE":"report_only"})
            install.assert_not_called()

    def test_changed_computational_code_and_untrusted_producer_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="pubg-cpu-gpu-code-") as folder:
            code = Path(folder) / "code"; code.mkdir()
            shutil.copytree(ROOT / "src", code / "src", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copyfile(ROOT / "requirements.txt", code / "requirements.txt")
            with (code / "src/features.py").open("a", encoding="utf-8") as stream:stream.write("\n# altered\n")
            with self.assertRaisesRegex(ValueError, "computational code"):
                cpu_resume_policy(self.source, code, self.manifest, self.gpu_software)
            shutil.copyfile(ROOT / "src/features.py", code / "src/features.py")
            # The exception is an exact audited file, not a waiver for arbitrary profile changes.
            path=code / "src/analysis.py"
            path.write_bytes(path.read_bytes()+b"\n# unaudited profile change\n")
            with self.assertRaisesRegex(ValueError, "computational code"):
                cpu_resume_policy(self.source, code, self.manifest, self.gpu_software)
            with self.assertRaisesRegex(ValueError, "audited 5.11"):
                cpu_resume_policy(ROOT, ROOT, self.manifest, self.gpu_software)

    def test_changed_raw_and_copy_failure_leave_source_unchanged_and_no_partial_target(self):
        with tempfile.TemporaryDirectory(prefix="pubg-cpu-gpu-fail-") as folder, \
             patch("src.io.software_versions", return_value=self.gpu_software), \
             patch("src.kaggle_runtime.software_versions", return_value=self.gpu_software):
            base = Path(folder); raw = base / "raw"
            shutil.copytree(self.raw, raw)
            path = next(raw.glob("agg*.csv"))
            with path.open("ab") as stream:stream.write(b"\n")
            with self.assertRaisesRegex(RuntimeError, "Original CPU checkpoint verification"):
                self.restore(base / "bad-source", raw)
            self.assertFalse((base / "bad-source").exists())
            with patch("src.kaggle_runtime.publish", side_effect=OSError("simulated disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):self.restore(base / "failed-copy")
            self.assertFalse((base / "failed-copy").exists())
            # Source must remain the one verified by the producer even while copying.
            moving_raw = base / "moving-raw"; shutil.copytree(self.raw, moving_raw)
            from src.kaggle_runtime import publish
            mutated = False
            def change_raw_during_copy(source, target, **kwargs):
                nonlocal mutated
                if not mutated:
                    mutated = True
                    with next(moving_raw.glob("agg*.csv")).open("ab") as stream:stream.write(b"\n")
                return publish(source, target, **kwargs)
            with patch("src.kaggle_runtime.publish", side_effect=change_raw_during_copy):
                with self.assertRaisesRegex(RuntimeError, "Raw source changed during CPU import"):
                    self.restore(base / "moving-source", moving_raw)
            self.assertFalse((base / "moving-source").exists())
            self.assertEqual(self.tree_hashes(self.source), self.source_hashes)
            self.assertFalse(list(base.glob("pubg-cpu-resume-*")))


if __name__ == "__main__":unittest.main()
