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

ROOT = Path(__file__).resolve().parents[1]

def generate_rich_synthetic_data(raw_dir: Path):
    raw_dir.mkdir(parents=True, exist_ok=True)
    agg_csv = raw_dir / "agg_match_stats_0.csv"
    kill_csv = raw_dir / "kill_match_stats_0.csv"

    # Create 9 matches: 3 solo, 3 duo, 3 squad across 3 dates
    # with enough players to satisfy splits, roster completeness, and EDA
    agg_rows = []
    kill_rows = []

    match_configs = [
        # (match_id, date, party_size, team_size_mode, n_teams, team_size)
        ("m_solo_1", "2017-10-01T10:00:00+0000", 1, "solo", 5, 1),
        ("m_solo_2", "2017-10-02T10:00:00+0000", 1, "solo", 5, 1),
        ("m_solo_3", "2017-10-03T10:00:00+0000", 1, "solo", 5, 1),
        ("m_duo_1", "2017-10-01T11:00:00+0000", 2, "duo", 4, 2),
        ("m_duo_2", "2017-10-02T11:00:00+0000", 2, "duo", 4, 2),
        ("m_duo_3", "2017-10-03T11:00:00+0000", 2, "duo", 4, 2),
        ("m_squad_1", "2017-10-01T12:00:00+0000", 4, "squad", 3, 4),
        ("m_squad_2", "2017-10-02T12:00:00+0000", 4, "squad", 3, 4),
        ("m_squad_3", "2017-10-03T12:00:00+0000", 4, "squad", 3, 4),
    ]

    p_idx = 0
    for match_id, m_date, party_size, mode, n_teams, team_size in match_configs:
        duration = 1200.0
        for t in range(1, n_teams + 1):
            team_id = f"team_{t}"
            placement = t  # 1 to n_teams
            for member in range(team_size):
                p_idx += 1
                player_name = f"player_{p_idx % 20}"  # some repeated players across matches
                kills = 2 if placement == 1 else (1 if placement == 2 else 0)
                dmg = kills * 120.0 + 35.0
                assists = 1 if team_size > 1 and placement <= 2 else 0
                dbno = 1 if team_size > 1 and kills > 0 else 0
                walk = 500.0 + (n_teams - placement) * 400.0
                ride = 200.0 if placement <= 2 else 0.0
                survive = duration - (placement - 1) * 200.0

                agg_rows.append([
                    match_id, player_name, team_id, m_date, "tpp", party_size, n_teams * team_size,
                    assists, dbno, ride, walk, dmg, kills, survive, placement
                ])

                # Add some kill events
                if kills > 0:
                    victim = f"victim_{p_idx}"
                    # early kill
                    kill_rows.append([match_id, 150.0, player_name, victim, "M416", 1])
                    if kills > 1:
                        # mid kill
                        kill_rows.append([match_id, 500.0, player_name, f"victim_{p_idx}_b", "AKM", 1])

    agg_cols = [
        "match_id", "player_name", "team_id", "date", "match_mode", "party_size", "game_size",
        "player_assists", "player_dbno", "player_dist_ride", "player_dist_walk",
        "player_dmg", "player_kills", "player_survive_time", "team_placement"
    ]
    kill_cols = ["match_id", "time", "killer_name", "victim_name", "killed_by", "killer_placement"]

    pd.DataFrame(agg_rows, columns=agg_cols).to_csv(agg_csv, index=False)
    pd.DataFrame(kill_rows, columns=kill_cols).to_csv(kill_csv, index=False)
    print(f"Created synthetic raw data: {len(agg_rows)} agg rows, {len(kill_rows)} kill rows.")

def run_smoke_test():
    print("=== BẮT ĐẦU SMOKE TEST NOTEBOOKS 00 ĐẾN 06 TRÊN WORKSPACE TẠM ===")
    with tempfile.TemporaryDirectory() as tmp_dir:
        workspace = Path(tmp_dir) / "smoke_ws"
        drive_project = workspace / "MyDrive/PUBG_Project/Project_PUBG"
        drive_project.mkdir(parents=True, exist_ok=True)

        # Copy source code and configs
        shutil.copytree(ROOT / "src", drive_project / "src", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "configs", drive_project / "configs")
        for f in ["requirements.txt", "README.md", "TEAM_DRIVE.md"]:
            if (ROOT / f).exists():
                shutil.copy2(ROOT / f, drive_project / f)

        # Generate synthetic raw data in data/raw
        generate_rich_synthetic_data(drive_project / "data/raw")

        # Driver script to execute notebook cells
        runner_code = """
import sys
import os
import json
from pathlib import Path
import types

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

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
        ]

        for nb_name in notebooks:
            target_nb = ROOT / "notebooks" / nb_name
            print(f"\n--> Đang thực thi Smoke Test: {nb_name}...")
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
                print(f"[PASS] {nb_name} chạy thành công trọn vẹn mọi cell!")
                # Print last few lines of stdout
                lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
                if lines:
                    print(f"       Kết quả cell cuối: {lines[-1]}")

        print("\n=======================================================")
        print("=> TOÀN BỘ 7 NOTEBOOK TỪ 00 ĐẾN 06 ĐÃ VƯỢT QUA SMOKE TEST.")
        print("=======================================================")

if __name__ == "__main__":
    run_smoke_test()
