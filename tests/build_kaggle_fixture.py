"""Xuất nguồn tổng hợp nhỏ; không đổi cấu hình nghiên cứu thật."""
import csv
import json
import sys
import tempfile
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.io import digest, publish
from test_data_features import fixture


SETUP = '''from pathlib import Path
import json, sys, yaml

sys.dont_write_bytecode = True
code = Path(CODE_INPUT).resolve()
source = Path(FIXTURE_INPUT).resolve()
target = Path(PUBG_PROJECT_ROOT).resolve()
if Path("/kaggle/input").is_dir() and not target.is_relative_to(Path("/kaggle/working").resolve()):
    raise ValueError("Trên Kaggle chỉ chuẩn bị project trong working, không ghi vào Input")
if EXECUTION_MODE != "development" or ALLOW_FULL_DATA:
    raise ValueError("Gói này chỉ dành cho development, không full-data")
if not isinstance(SOURCE_VERSION, int) or SOURCE_VERSION < 1:
    raise ValueError("Nhập số version Dataset fixture đã gắn, không đoán")
if target.exists() and any(target.iterdir()):
    raise ValueError("Chọn working root mới/trống; không ghi đè kết quả hiện có")
sys.path.insert(0, str(code))
from src.io import digest, load_config
from src.kaggle_runtime import prepare_project, safe_file

manifest = json.loads(safe_file(source, "fixture_manifest.json").read_text(encoding="utf-8"))
if manifest.get("fixture_id") != "pubg-synthetic-fixture-v1" or manifest.get("scope") != "development":
    raise ValueError("Không phải gói fixture đã chuẩn bị")
expected = {"fixture_config.yaml", "agg_match_stats_0.csv", "agg_match_stats_1.csv",
            "kill_match_stats_0.csv", "kill_match_stats_1.csv"}
entries = manifest["entries"]
if len(entries) != len(expected) or {e["path"] for e in entries} != expected:
    raise ValueError("Gói fixture thiếu file hoặc có file trùng")
for entry in entries:
    path = safe_file(source, entry["path"])
    if path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
        raise ValueError("Fixture checksum mismatch: " + entry["path"])
cfg = yaml.safe_load(safe_file(source, "fixture_config.yaml").read_text(encoding="utf-8"))
if cfg["source"]["dataset"] != manifest["fixture_id"] or cfg["rq3"]["selection_approved"]:
    raise ValueError("Sai cấu hình fixture hoặc đã mở final test")
prepare_project(code, target)
cfg["source"].update(directory=str(source), version=SOURCE_VERSION)
cfg["storage"]["project_root"] = str(target)
(target / "configs/project.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
load_config(target)
SOURCE_DIRECTORY = str(source)
CODE_INPUT = RESUME_INPUT = ""
ALLOW_DATA_PROCESSING = True
print("Sẵn sàng cho S00/S01-S04, chỉ synthetic fixture:", manifest["expected"])
'''


def build_fixture(archive):
    with tempfile.TemporaryDirectory(prefix="pubg-fixture-export-") as folder:
        project = Path(folder) / "project"
        project.mkdir()
        cfg = fixture(project)
        cfg["source"].update(directory=None, dataset="pubg-synthetic-fixture-v1",
                              version=None, license="Synthetic test data; not PUBG source", download_date=None)
        cfg["storage"]["project_root"] = "/kaggle/working/PUBG_Fixture"
        for key in ("rq2", "rq3"):
            cfg[key]["device"] = "cuda"
        config = project / "raw_fixture/fixture_config.yaml"
        config.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        payload = sorted((project / "raw_fixture").iterdir())
        entries = []
        for path in payload:
            entry = {"path": path.name, "bytes": path.stat().st_size, "sha256": digest(path)}
            if path.suffix == ".csv":
                with path.open(encoding="utf-8", newline="") as stream:
                    reader = csv.reader(stream)
                    entry["columns"] = next(reader)
                    entry["rows"] = sum(1 for _ in reader)
            entries.append(entry)
        manifest = {"fixture_id": "pubg-synthetic-fixture-v1", "scope": "development",
                    "expected": {"aggregate_raw_rows": 241, "clean_player_match_rows": 240,
                                 "event_rows": 360, "matches": 30, "modes": ["Solo", "Duo"],
                                 "split_matches": {"train": 21, "validation": 5, "test": 4}},
                    "note": "Logic fixture only; not a realistic game simulation or research evidence. K/G4 remain pending.",
                    "entries": entries}
        staged = Path(folder) / "fixture.zip"
        with zipfile.ZipFile(staged, "w", zipfile.ZIP_DEFLATED) as z:
            for path in payload:
                z.write(path, path.name)
            z.writestr("fixture_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            z.writestr("setup_fixture.py", SETUP.encode("utf-8"))
        with zipfile.ZipFile(staged) as z:
            if z.testzip() is not None:
                raise IOError("Fixture ZIP CRC mismatch")
        return publish(staged, Path(archive))


if __name__ == "__main__":
    print(build_fixture(ROOT / "kaggle_fixture.zip"))
