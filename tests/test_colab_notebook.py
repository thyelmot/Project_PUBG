"""Colab adapter tests: external GPU/network/Drive are simulated, never actual cloud acceptance."""
import ast
import asyncio
import base64
import copy
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch, Mock
import zipfile

import nbformat
from nbclient import NotebookClient

from src.io import Context, digest, read_json
from src.preprocessing import ingest
from test_data_features import ROOT, write_config
import test_pipeline_acceptance as acceptance
from tools import colab_runtime as support
from tools.build_colab_notebook import build, DATA

if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class ColabNotebook(unittest.TestCase):
    def test_generated_notebook_scientific_sections_and_embedded_bytes(self):
        path = ROOT / "notebooks/PUBG_COURSEWORK_COLAB.ipynb"
        before = path.read_bytes()
        self.assertEqual(build().read_bytes(), before)
        notebook = nbformat.read(path, as_version=4)
        original = nbformat.read(ROOT / "notebooks/PUBG_COURSEWORK.ipynb", as_version=4)
        nbformat.validate(notebook)
        self.assertEqual(len(notebook.cells), 50)
        self.assertEqual(sum(c.cell_type == "code" for c in notebook.cells), 18)
        cells = {c.id: c for c in notebook.cells}
        for cell in notebook.cells:
            if cell.cell_type == "code":
                ast.parse(cell.source)
                self.assertEqual(cell.outputs, [])
                self.assertIsNone(cell.execution_count)
        for cell in original.cells:
            if cell.id.startswith(tuple(f"s{i:02d}" for i in range(1, 11))):
                a, b = cell.source, cells[cell.id].source
                if cell.cell_type == "code":
                    self.assertEqual(ast.dump(ast.parse(a)), ast.dump(ast.parse(b)), cell.id)
                else:
                    self.assertEqual(a, b, cell.id)
        tree = ast.parse(cells["colab-environment"].source)
        values = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  and isinstance(n.targets[0], ast.Name) and n.targets[0].id in {"BUNDLED_CODE", "BUNDLED_CODE_SHA256"}}
        data = base64.b64decode(values["BUNDLED_CODE"])
        self.assertEqual(hashlib.sha256(data).hexdigest(), values["BUNDLED_CODE_SHA256"])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = {p.relative_to(ROOT).as_posix() for p in (ROOT / "src").glob("*.py")}
            names.update({"configs/project.yaml", "requirements.txt", "PUBG_RESEARCH_SPEC.md"})
            self.assertEqual(set(z.namelist()), names)
            self.assertEqual(len(names), 15)
            for name in names:
                self.assertEqual(z.read(name), (ROOT / name).read_bytes())
        self.assertEqual(notebook.metadata.pubg_colab.source_sha256,
                         "4e3f9a191e589c963727c12bbf00ec656ee6bf17de0621ca6a6f520b3641dd3c")
        with tempfile.TemporaryDirectory(prefix="pubg-colab-code-") as folder:
            target = Path(folder) / "code"
            support.unpack_code(values["BUNDLED_CODE"], values["BUNDLED_CODE_SHA256"], target)
            support.unpack_code(values["BUNDLED_CODE"], values["BUNDLED_CODE_SHA256"], target)
            io_file = target / "src/io.py"
            io_file.write_bytes(b"user change")
            with self.assertRaisesRegex(RuntimeError, "different files"):
                support.unpack_code(values["BUNDLED_CODE"], values["BUNDLED_CODE_SHA256"], target)
            self.assertEqual(io_file.read_bytes(), b"user change")
            with self.assertRaisesRegex(ValueError, "checksum"):
                support.unpack_code(values["BUNDLED_CODE"], "0" * 64, target)

    def test_pinned_download_cache_and_no_token_output(self):
        with tempfile.TemporaryDirectory(prefix="pubg-colab-download-") as folder:
            root = Path(folder)
            cfg = acceptance.acceptance_fixture(root / "source")
            cache = root / "cache"
            api = types.SimpleNamespace(dataset_download=Mock(return_value=cfg["source"]["directory"]), login=Mock())
            with patch.dict(sys.modules, {"kagglehub": api}), patch.dict(os.environ, {"KAGGLEHUB_CACHE": str(cache.resolve())}), patch("builtins.print") as output:
                self.assertEqual(support.download_source("skihikingkevin/pubg-match-deaths", 3, cache, 0), cfg["source"]["directory"])
                api.dataset_download.assert_called_once_with("skihikingkevin/pubg-match-deaths/versions/3")
                api.login.assert_not_called()
                self.assertNotIn("KAGGLE_API_TOKEN", str(output.call_args_list))
            with self.assertRaises(ValueError):
                support.download_source("another/dataset", 3, cache, 0)
            with self.assertRaises(ValueError):
                support.download_source("skihikingkevin/pubg-match-deaths", True, cache, 0)
            with patch("tools.colab_runtime.shutil.disk_usage", return_value=types.SimpleNamespace(free=0)):
                with self.assertRaises(MemoryError):
                    support.download_source("skihikingkevin/pubg-match-deaths", 3, cache)

    def test_environment_alignment_install_restart_and_no_fallback(self):
        real = support.importlib.metadata.version
        def versions(name):
            if name == "cudf-cu12":
                return "26.2.0"
            if name in {"cuml-cu12", "cudf-cu13", "cuml-cu13", "cupy-cuda13x", "cupy-cuda12x", "kagglehub"}:
                raise support.importlib.metadata.PackageNotFoundError(name)
            return real(name)
        with patch("tools.colab_runtime.importlib.metadata.version", side_effect=versions):
            requirements, missing = support.environment_requirements(ROOT, "cu12")
            self.assertIn("cuml-cu12==26.2.*", requirements)
            self.assertIn("cudf-cu12==26.2.*", requirements)
            self.assertIn("cuml-cu12==26.2.*", missing)
            with patch.object(support.sys, "platform", "linux"), patch("tools.colab_runtime.shutil.which", return_value=None), patch("tools.colab_runtime.subprocess.run"), patch("tools.colab_runtime.subprocess.check_call") as install:
                with self.assertRaisesRegex(RuntimeError, "Restart session"):
                    support.setup_environment(ROOT, "cu12")
                self.assertIn("cuml-cu12==26.2.*", install.call_args.args[0])
                install.reset_mock()
                with self.assertRaisesRegex(RuntimeError, "Enable INSTALL"):
                    support.setup_environment(ROOT, "cu12", install=False)
                install.assert_not_called()
        with patch("tools.colab_runtime.importlib.metadata.version", return_value="26.2.0"):
            with self.assertRaisesRegex(RuntimeError, "Conflicting CUDA family"):
                support.environment_requirements(ROOT, "cu12")
        with patch.object(support.sys, "platform", "linux"), patch("tools.colab_runtime.subprocess.run"), patch("tools.colab_runtime.shutil.which", return_value="nvcc"), patch("tools.colab_runtime.subprocess.check_output", return_value="Cuda compilation tools, release 13.0, V13"), patch("tools.colab_runtime.subprocess.check_call") as install:
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                support.setup_environment(ROOT, "cu12")
            install.assert_not_called()

    def test_config_resume_preserves_science_and_rejects_stale_without_writing(self):
        with tempfile.TemporaryDirectory(prefix="pubg-colab-config-") as folder:
            base = Path(folder)
            cfg = acceptance.acceptance_fixture(base / "source")
            target = support.configure_project(ROOT, base / "project", cfg["source"]["directory"], [0], "development")
            ctx = Context(target, "development")
            self.assertEqual(ctx.cfg["rq2"]["gpu_ids"], [0])
            self.assertEqual(ctx.cfg["rq3"]["device"], "cuda")
            self.assertEqual(ctx.cfg["storage"]["layout"], "normalized_v1")
            self.assertFalse(ctx.temp.is_relative_to(target))
            ctx.run("S01", ingest)
            config_hash = digest(target / "configs/project.yaml")
            support.configure_project(ROOT, target, cfg["source"]["directory"], [0], "development")
            self.assertEqual(digest(target / "configs/project.yaml"), config_hash)
            changed = base / "source/raw_fixture/agg_match_stats_0.csv"
            changed.write_bytes(changed.read_bytes().replace(b"300", b"301", 1) + b"\n")
            with self.assertRaisesRegex(RuntimeError, "stale"):
                support.configure_project(ROOT, target, cfg["source"]["directory"], [0], "development")
            self.assertEqual(digest(target / "configs/project.yaml"), config_hash)
            for ids in ([0, 1], [False]):
                with self.assertRaises(ValueError):
                    support.configure_project(ROOT, target, cfg["source"]["directory"], ids, "development")

    def test_report_only_transport_mounts_without_download_install_or_gpu(self):
        mount = Mock()
        module = types.ModuleType("google.colab")
        module.drive = types.SimpleNamespace(mount=mount)
        namespace = {"EXECUTION_MODE": "report_only", "USE_GOOGLE_DRIVE": True,
                     "PUBG_PROJECT_ROOT": "/content/drive/MyDrive/test_colab_project", "Path": Path}
        with patch.dict(sys.modules, {"google.colab": module}):
            exec(DATA, namespace)
        mount.assert_called_once_with("/content/drive")
        self.assertNotIn("SOURCE_DIRECTORY", namespace)

    def test_actual_cells_runall_reuse_and_report_only_simulated_external_services(self):
        review = Path(tempfile.mkdtemp(prefix="pubg-colab-review-"))
        with tempfile.TemporaryDirectory(prefix="pubg-colab-cells-") as folder:
            base = Path(folder)
            cfg = acceptance.acceptance_fixture(base / "source")
            source, target, code_root = cfg["source"]["directory"], base / "project", base / "code"
            template = nbformat.read(ROOT / "notebooks/PUBG_COURSEWORK_COLAB.ipynb", as_version=4)
            def execute(mode="development", release=""):
                notebook = copy.deepcopy(template)
                cells = {c.id: c for c in notebook.cells}
                cells["parameters"].source += (f"\nEXECUTION_MODE={mode!r}\nUSE_GOOGLE_DRIVE=False\nPUBG_PROJECT_ROOT={str(target)!r}\nCODE_ROOT={str(code_root)!r}\nKAGGLE_CACHE_ROOT={str(base/'cache')!r}\nRUN_GPU_SMOKE=False\nRELEASE_MANIFEST={release!r}\n")
                # Test substitutions only: CPU estimator, fake external download, no pip/Drive/CUDA access.
                env = cells["colab-environment"].source
                env = env.replace('cfg[section].update(device="cuda", gpu_ids=gpu_ids)', 'cfg[section].update(device="cpu", gpu_ids=gpu_ids)')
                env = env.replace("    setup_environment(CODE_ROOT, CUDA_FAMILY, INSTALL_COLAB_DEPENDENCIES)", "    print('TEST ONLY: GPU/network installer simulated on CPU')")
                env += f'''\nimport types
def download_source(*args, **kwargs):
    assert args[0:2] == ("skihikingkevin/pubg-match-deaths", 3)
    return {source!r}
subprocess.check_call = lambda *args, **kwargs: None
real_configure = configure_project
def configure_project(*args):
    result = real_configure(*args)
    if not (result/"outputs/development/checkpoints/stages.json").exists():
        from src.io import load_config
        import yaml
        cfg = load_config(result)
        cfg["timing"]["partitions"] = 2
        cfg["timing"]["unit_evidence"] = "Synthetic CPU fixture; no actual source unit validation"
        cfg["preprocessing"]["mode_evidence"] = "Synthetic three-mode fixture only"
        cfg["rq2"].update(minimum_games=1, threshold_candidates=[1,2], candidate_k=[2,3])
        (result/"configs/project.yaml").write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding="utf-8")
    return result
'''
                cells["colab-environment"].source = env
                NotebookClient(notebook, timeout=180, kernel_name="python3", resources={"metadata": {"path": str(base)}}).execute()
                nbformat.write(notebook, review / (mode + ".ipynb"))
            execute()
            ctx = Context(target, "development")
            self.assertEqual(len(ctx.manifest()), 10)
            self.assertTrue(all(r["status"] == "completed" for r in ctx.manifest().values()))
            model_hashes = {p.name: digest(p) for p in ctx.path("models").glob("*.joblib")}
            self.assertTrue(support.verify_colab_handoff(target, "development")["readback_verified"])
            execute()
            self.assertEqual(model_hashes, {p.name: digest(p) for p in ctx.path("models").glob("*.joblib")})
            before = acceptance.tree_hashes(target)
            pointer = read_json(ctx.path("manifests/final_results.json"))
            execute("report_only", str(target / pointer["manifest"]))
            self.assertEqual(before, acceptance.tree_hashes(target))
            receipt = target / "handoff_development.json"
            data = read_json(receipt)
            data["entries"].append(data["entries"][0])
            receipt.write_text(__import__("json").dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                support.verify_colab_handoff(target, "development")
        print("COLAB_CPU_REVIEW_ROOT=" + str(review))
