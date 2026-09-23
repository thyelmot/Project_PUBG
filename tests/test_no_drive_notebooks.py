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

    def test_generated_notebooks_compile_without_drive_auth(self):
        import nbformat
        for path in sorted((ROOT / "notebooks").glob("*.ipynb")):
            nb = nbformat.read(path, as_version=4)
            nbformat.validate(nb)
            for index, cell in enumerate(nb.cells):
                if cell.cell_type != "code":
                    continue
                self.assertNotIn("drive.mount(", cell.source)
                self.assertNotIn("auth.authenticate_user", cell.source)
                compile(cell.source, f"{path.name}:cell{index}", "exec")

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


if __name__ == "__main__":
    unittest.main()
