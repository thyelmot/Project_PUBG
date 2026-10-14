import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import pandas as pd
import numpy as np

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = Path('E:/NAM_BA/KY_1_NAM_BA/KHAI PHÁ DỮ LIỆU/Project_PUBG').resolve()
sys.path.insert(0, str(ROOT / 'scripts'))
from smoke_test_00_06 import generate_rich_synthetic_data

def run_smoke_test():
    with tempfile.TemporaryDirectory() as tmp_dir:
        workspace = Path(tmp_dir) / "smoke_ws"
        drive_project = workspace / "MyDrive/PUBG_Project/Project_PUBG"
        drive_project.mkdir(parents=True, exist_ok=True)

        shutil.copytree(ROOT / "src", drive_project / "src", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "configs", drive_project / "configs")

        # FIX configs for test
        rq2_yaml = drive_project / "configs" / "rq2.yaml"
        if rq2_yaml.exists():
            cfg_text = rq2_yaml.read_text(encoding="utf-8")
            cfg_text = cfg_text.replace('device: "cuda"', 'device: "cpu"')
            cfg_text = cfg_text.replace('party_size_mapping: null', 'party_size_mapping: {1: "Solo", 2: "Duo", 4: "Squad"}')
            cfg_text = cfg_text.replace('minimum_games_threshold: null', 'minimum_games_threshold: 1')
            cfg_text = cfg_text.replace('selection_reason: null', 'selection_reason: "Mock test"')
            rq2_yaml.write_text(cfg_text, encoding="utf-8")

        generate_rich_synthetic_data(drive_project / "data/raw")

        runner_code = """
import sys
import os
import json
from pathlib import Path
import types

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

os.environ["PYTHONPATH"] = str(Path.cwd())

colab = types.ModuleType("google.colab")
colab.drive = types.SimpleNamespace(mount=lambda path: None)
colab.files = types.SimpleNamespace(download=lambda path: None)
sys.modules["google.colab"] = colab

nb_path = Path(sys.argv[1]).resolve()
root_dir = Path(sys.argv[2]).resolve()
os.chdir(root_dir)

scope = {
    "PUBG_INSTALL_DEPENDENCIES": False,
    "PUBG_STORAGE_MODE": "drive",
    "PUBG_DRIVE_PROJECT_ROOT": str(root_dir),
    "PUBG_RUNTIME_TEMP_DIR": str(root_dir.parent / "temp"),
    "PUBG_REQUIRE_EXISTING_PROJECT": True,
    "__name__": "__main__"
}

with open(nb_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

for idx, cell in enumerate(nb["cells"]):
    if cell["cell_type"] != "code":
        continue
    source = "".join(cell["source"])
    try:
        compiled = compile(source, f"{nb_path.name}-cell-{idx}", "exec")
        exec(compiled, scope)
        if "storage-options" in cell.get("metadata", {}).get("tags", []):
            scope.update(
                PUBG_STORAGE_MODE="drive",
                PUBG_DRIVE_PROJECT_ROOT=str(root_dir),
                PUBG_RUNTIME_TEMP_DIR=str(root_dir.parent / "temp"),
                PUBG_REQUIRE_EXISTING_PROJECT=True,
            )
    except Exception as e:
        print(f"FAILED in {nb_path.name} cell {idx}: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

print(f"SUCCESS: {nb_path.name}")
"""
        runner_path = workspace / "cell_runner.py"
        runner_path.write_text(runner_code, encoding="utf-8")

        notebooks = [
            "00_setup.ipynb",
            "01_download_validate.ipynb",
            "02_data_quality_and_structure.ipynb",
            "03_build_player_match.ipynb",
            "04_combat_timing.ipynb",
            "05_eda.ipynb",
            "06_rq1_analysis.ipynb",
            "07_rq2_clustering.ipynb"
        ]

        for nb_name in notebooks:
            target_nb = ROOT / "notebooks" / nb_name
            result = subprocess.run(
                [sys.executable, str(runner_path), str(target_nb), str(drive_project)],
                cwd=str(drive_project),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180
            )
            if result.returncode != 0:
                print(f"[FAIL] Smoke test thất bại tại {nb_name}!")
                print("STDOUT:\n", result.stdout[-3000:])
                print("STDERR:\n", result.stderr[-3000:])
                sys.exit(1)
            else:
                if nb_name == "07_rq2_clustering.ipynb":
                    print("STDOUT của NB07:\n", result.stdout)

        # Trích xuất bảng kết quả
        print("\n--- RAW ARTIFACTS DUMP ---")
        tables_dir = drive_project / "reports/tables"
        for mode in ['Solo', 'Duo', 'Squad']:
            md_dir = tables_dir / "rq2" / mode
            if md_dir.exists():
                print(f"\n[MODE: {mode}]")
                c_assign = md_dir / "cluster_assignments.csv"
                if c_assign.exists(): print(f"Assignments:\n{pd.read_csv(c_assign).head(2)}")
                c_centers = md_dir / "cluster_centers_standardized.csv"
                if c_centers.exists(): print(f"Centers:\n{pd.read_csv(c_centers).head(2)}")

if __name__ == "__main__":
    run_smoke_test()
