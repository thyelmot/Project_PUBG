"""Regression checks for portable notebooks and anonymous downloads."""

import io
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

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.download_data import download_file_with_checksum, download_and_extract_archive, _DownloadForm
from src.utils.config import load_config, resolve_paths
from src.evaluation.finalize import build_final_results_manifest, verify_final_manifest_integrity


class TestNoDriveNotebooks(unittest.TestCase):
    def test_local_and_colab_paths_without_drive(self):
        cfg = load_config(str(ROOT / "configs"))
        for environment in ["local", "colab"]:
            cfg["paths"]["active_environment"] = environment
            paths = resolve_paths(cfg)
            self.assertEqual(paths["raw"], paths["raw_root"])
            self.assertEqual(paths["reports"], paths["reports_root"])
            self.assertEqual(paths["figures"], paths["figures_root"])
            self.assertTrue(all("/drive/" not in p.as_posix() for p in paths.values()))
        cfg["paths"]["active_environment"] = "auto"
        with patch.dict(sys.modules, {"google.colab": object()}):
            self.assertEqual(resolve_paths(cfg)["raw_root"].as_posix(), Path("/content/data/raw").resolve().as_posix())

    def test_anonymous_download_routing_and_html_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "data.zip"
            for host in ["drive.google.com", "drive.usercontent.google.com"]:
                response = io.BytesIO(b"public data")
                response.headers = {"Content-Type": "application/octet-stream"}
                with patch("src.data.download_data._resolve_google_drive_stream", return_value=response) as resolver:
                    download_file_with_checksum(f"https://{host}/download?id=public", target)
                    resolver.assert_called_once()
                    self.assertEqual(target.read_bytes(), b"public data")
            html_response = io.BytesIO(b"<html>Sign in</html>")
            html_response.headers = {"Content-Type": "text/html"}
            with patch("src.data.download_data._resolve_google_drive_stream", return_value=html_response):
                with self.assertRaisesRegex(ValueError, "HTML"):
                    download_file_with_checksum("https://drive.usercontent.google.com/download?id=x", target)
            self.assertEqual(target.read_bytes(), b"public data")
            self.assertFalse(target.with_suffix(".zip.part").exists())

    def test_confirmation_form_and_archive_validation(self):
        form = _DownloadForm()
        form.feed('<form action="https://accounts.google.com/login"><input type="hidden" name="token" value="secret"></form>'
                  '<form action="https://drive.usercontent.google.com/download">'
                  '<input value="a&amp;b" name="id" type="hidden"></form>')
        self.assertEqual(form.fields, {"id": "a&b"})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "test.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("../escaped.txt", "bad")
            with self.assertRaisesRegex(ValueError, "Unsafe ZIP"):
                download_and_extract_archive("unused", root / "raw", archive_filename="test.zip")
            self.assertFalse((root / "escaped.txt").exists())
            with self.assertRaisesRegex(ValueError, "Checksum"):
                download_and_extract_archive("unused", root / "raw", expected_checksum="0" * 64, archive_filename="test.zip")

    def test_manifest_survives_moving_results(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original"
            table = original / "reports/tables/example.csv"
            table.parent.mkdir(parents=True)
            table.write_text("value\n1\n", encoding="utf-8")
            manifest_rel = Path("artifacts/manifests/final_results_manifest.json")
            build_final_results_manifest(original / "artifacts", original / "reports", {}, original / manifest_rel)
            moved = Path(directory) / "moved"
            original.rename(moved)
            self.assertEqual(verify_final_manifest_integrity(moved / manifest_rel), (True, []))

    def test_generated_notebooks_offer_runtime_and_drive_modes(self):
        import nbformat
        for path in sorted((ROOT / "notebooks").glob("*.ipynb")):
            nb = nbformat.read(path, as_version=4)
            nbformat.validate(nb)
            storage_cells = [cell for cell in nb.cells if "storage-options" in cell.metadata.get("tags", [])]
            bootstrap_cells = [cell for cell in nb.cells if "bootstrap" in cell.metadata.get("tags", [])]
            self.assertEqual(len(storage_cells), 1, path.name)
            self.assertEqual(len(bootstrap_cells), 1, path.name)
            self.assertIn('PUBG_STORAGE_MODE = "runtime"', storage_cells[0].source)
            self.assertIn('drive.mount("/content/drive")', bootstrap_cells[0].source)
            for index, cell in enumerate(nb.cells):
                if cell.cell_type != "code":
                    continue
                self.assertNotIn("auth.authenticate_user", cell.source)
                compile(cell.source, f"{path.name}:cell{index}", "exec")

    def test_drive_mode_uses_shared_project_root(self):
        notebook = ROOT / "notebooks/00_setup.ipynb"
        with tempfile.TemporaryDirectory() as directory:
            drive_project = Path(directory) / "MyDrive/Project_PUBG"
            program = '''import json, sys, types
nb = json.load(open(sys.argv[1], encoding="utf-8"))
drive = types.ModuleType("google.colab.drive")
drive.mount = lambda path: print("MOUNT", path)
colab = types.ModuleType("google.colab")
colab.drive = drive
google = types.ModuleType("google")
google.colab = colab
sys.modules.update({"google": google, "google.colab": colab, "google.colab.drive": drive})
scope = {"PUBG_INSTALL_DEPENDENCIES": False, "PUBG_STORAGE_MODE": "drive",
         "PUBG_DRIVE_PROJECT_ROOT": sys.argv[2], "PUBG_RUNTIME_TEMP_DIR": sys.argv[3],
         "__name__": "__main__"}
cell = next(c for c in nb["cells"] if "bootstrap" in c.get("metadata", {}).get("tags", []))
exec(compile("".join(cell["source"]), "bootstrap", "exec"), scope)
print(scope["PROJECT_ROOT"])
print(scope["paths"]["data_root"])
'''
            run = subprocess.run([sys.executable, "-c", program, str(notebook), str(drive_project),
                                  str(Path(directory) / "runtime-temp")],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("MOUNT /content/drive", run.stdout)
            self.assertTrue((drive_project / "src/utils/config.py").is_file())
            self.assertTrue((drive_project / "data").is_dir())
            self.assertIn(str(drive_project / "data"), run.stdout)

    def test_bootstrap_installs_only_missing_runtime_packages(self):
        notebook = ROOT / "notebooks/00_setup.ipynb"
        with tempfile.TemporaryDirectory() as directory:
            program = '''import importlib.util, json, subprocess, sys
nb = json.load(open(sys.argv[1], encoding="utf-8"))
real_find_spec = importlib.util.find_spec
importlib.util.find_spec = lambda name: None if name == "duckdb" else real_find_spec(name)
subprocess.check_call = lambda command: print("PIP_COMMAND", command)
scope = {"PUBG_INSTALL_DEPENDENCIES": True, "PUBG_STORAGE_MODE": "runtime", "__name__": "__main__"}
cell = next(c for c in nb["cells"] if "bootstrap" in c.get("metadata", {}).get("tags", []))
exec(compile("".join(cell["source"]), "bootstrap", "exec"), scope)
'''
            run = subprocess.run([sys.executable, "-c", program, str(notebook)], cwd=directory,
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            pip_line = next(line for line in run.stdout.splitlines() if line.startswith("PIP_COMMAND"))
            self.assertIn("duckdb>=0.9.0", pip_line)
            self.assertNotIn("xgboost", pip_line)
            self.assertNotIn("jupyter", pip_line)

    def test_all_cells_on_synthetic_data_in_fresh_workspace(self):
        """Execute the actual distributed notebook, not a second mini pipeline."""
        notebook = ROOT / "notebooks/PUBG_COLAB_ALL_IN_ONE.ipynb"
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            raw = workspace / "Data_PUBG"
            (raw / "aggregate").mkdir(parents=True)
            (raw / "deaths").mkdir()
            aggregate, deaths = [], []
            for match in range(20):
                for player in range(12):
                    kills = (player + match) % 4
                    aggregate.append({
                        "date": f"2017-11-{1 + match:02d}T12:00:00+0000",
                        "game_size": 12, "match_id": f"m{match}", "match_mode": "tpp",
                        "party_size": 1, "player_assists": player % 2, "player_dbno": kills,
                        "player_dist_ride": 5.0 * player, "player_dist_walk": 100.0 + 20 * player + match,
                        "player_dmg": kills * 100.0 + player, "player_kills": kills,
                        "player_name": f"p{player}", "player_survive_time": 1200.0 - player * 80,
                        "team_id": str(player), "team_placement": player + 1,
                    })
                    for kill in range(kills):
                        deaths.append({"match_id": f"m{match}", "time": 30.0 + kill * 100,
                                       "killer_name": f"p{player}", "victim_name": f"p{(player+kill+1)%12}",
                                       "killed_by": "M416"})
            pd.DataFrame(aggregate).to_csv(raw / "aggregate/agg_match_stats_0.csv", index=False)
            pd.DataFrame(deaths).to_csv(raw / "deaths/kill_match_stats_final_0.csv", index=False)
            # No project folder exists: the bootstrap must unpack its embedded source.
            program = '''import json, sys
sys.stdout.reconfigure(encoding="utf-8")
nb = json.load(open(sys.argv[1], encoding="utf-8"))
scope = {"PUBG_INSTALL_DEPENDENCIES": False, "__name__": "__main__"}
for i, cell in enumerate(nb["cells"]):
    if cell["cell_type"] == "code":
        print("EXECUTING CELL", i, flush=True)
        exec(compile("".join(cell["source"]), f"notebook-cell-{i}", "exec"), scope)
'''
            environment = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", LOKY_MAX_CPU_COUNT="2")
            environment.pop("COLAB_RELEASE_TAG", None)
            run = subprocess.run([sys.executable, "-c", program, str(notebook)], cwd=workspace,
                                 env=environment, capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=120)
            self.assertEqual(run.returncode, 0, (run.stdout + run.stderr)[-10000:])
            project = workspace / "Project_PUBG"
            self.assertTrue((project / "PUBG_results.zip").is_file())
            with zipfile.ZipFile(project / "PUBG_results.zip") as archive:
                self.assertIn("reports/tables/ablation_results.csv", archive.namelist())
                self.assertFalse(any(name.startswith("data/") for name in archive.namelist()))

            # Fresh processes emulate separate Colab tabs: only Drive files survive.
            drive_program = '''import json, os, sys, types
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
colab = types.ModuleType("google.colab")
colab.drive = types.SimpleNamespace(mount=lambda path: None)
colab.files = types.SimpleNamespace(download=lambda path: None)
sys.modules["google.colab"] = colab
scope = {"PUBG_INSTALL_DEPENDENCIES": False, "__name__": "__main__"}
nb = json.load(open(sys.argv[1], encoding="utf-8"))
root = Path(sys.argv[2]).resolve()
for i, cell in enumerate(nb["cells"]):
    if cell["cell_type"] != "code":
        continue
    print("EXECUTING", sys.argv[1], i, flush=True)
    exec(compile("".join(cell["source"]), f"cell-{i}", "exec"), scope)
    if "storage-options" in cell.get("metadata", {}).get("tags", []):
        scope.update(PUBG_STORAGE_MODE="drive", PUBG_DRIVE_PROJECT_ROOT=str(root),
                     PUBG_RUNTIME_TEMP_DIR=str(root.parent / "temp"))
    if "paths" in scope:
        for key in ["raw", "interim", "processed", "tables", "manifests", "experiments"]:
            assert scope["paths"][key].is_relative_to(root), (i, key, scope["paths"][key])
        from src.utils.config import load_config, resolve_paths
        assert resolve_paths(load_config())["data_root"] == root / "data"
'''
            for mode in ["separate", "combined"]:
                drive_project = workspace / mode / "MyDrive/PUBG_Project/Project_PUBG"
                shutil.copytree(raw, drive_project / "data/raw")
                notebooks = (sorted((ROOT / "notebooks").glob("[0-1][0-9]_*.ipynb"))
                             if mode == "separate" else [notebook])
                for current in notebooks:
                    with self.subTest(mode=mode, notebook=current.name):
                        run = subprocess.run(
                            [sys.executable, "-c", drive_program, str(current), str(drive_project)],
                            cwd=workspace, env=environment, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=120)
                        self.assertEqual(run.returncode, 0, (run.stdout + run.stderr)[-10000:])
                        if run.returncode:
                            break
                self.assertTrue((drive_project / "artifacts/manifests/final_results_manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
