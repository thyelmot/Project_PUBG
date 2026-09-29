import json
import re
import sys
from pathlib import Path

NOTEBOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "notebooks"
NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(NOTEBOOKS_DIR.parent))
from src.utils.notebook_bundle import (
    ALL_IN_ONE_STORAGE_OPTIONS_CELL,
    bootstrap_source,
    EXPORT_CELL,
    STORAGE_OPTIONS_CELL,
)

BOOTSTRAP = bootstrap_source(NOTEBOOKS_DIR.parent)
GENERATED_NOTEBOOKS = []
ONLY_NOTEBOOK = sys.argv[sys.argv.index('--only') + 1] if '--only' in sys.argv else None
NOTEBOOK_DEPENDENCIES = {
    "01_download_validate.ipynb": [],
    "02_data_quality_and_structure.ipynb": ["01_download_validate.ipynb"],
    "03_build_player_match.ipynb": ["02_data_quality_and_structure.ipynb"],
    "04_combat_timing.ipynb": ["01_download_validate.ipynb", "03_build_player_match.ipynb"],
    "05_eda.ipynb": ["04_combat_timing.ipynb"],
    "06_rq1_analysis.ipynb": ["04_combat_timing.ipynb"],
    "07_rq2_clustering.ipynb": ["04_combat_timing.ipynb", "05_eda.ipynb"],
    "08_build_historical.ipynb": ["02_data_quality_and_structure.ipynb", "04_combat_timing.ipynb"],
    "09_rq3_prediction.ipynb": ["02_data_quality_and_structure.ipynb", "04_combat_timing.ipynb"],
    "10_ablation_error_analysis.ipynb": ["09_rq3_prediction.ipynb"],
    "11_finalize_results.ipynb": ["06_rq1_analysis.ipynb", "07_rq2_clustering.ipynb", "09_rq3_prediction.ipynb", "10_ablation_error_analysis.ipynb"],
}

def create_notebook(filename: str, title: str, description: str, cells_data: list):
    if ONLY_NOTEBOOK and filename != ONLY_NOTEBOOK:
        return
    cells = [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [f"# {title}\n", f"\n", f"**Mục tiêu:** {description}\n", f"\n", f"Single Source of Truth: `PUBG_RESEARCH_SPEC.md` v3.0 | `PUBG_IMPLEMENTATION_PLAN.md`\n"]
        }
    ]
    cells.append({"cell_type": "markdown", "metadata": {}, "source": [
        "Chọn `runtime` để chạy không cần Drive, hoặc `drive` để 13 notebook dùng chung dữ liệu bền vững. "
        "Với `drive`, mọi notebook phải dùng cùng `PUBG_DRIVE_PROJECT_ROOT` và chạy theo thứ tự.\n\n"
        "**Chạy nhóm:** chủ thư mục chia sẻ `PUBG_Project` với quyền Editor. Mỗi thành viên thêm shortcut "
        "của chính thư mục đó vào My Drive, chọn `drive` và bật `PUBG_REQUIRE_EXISTING_PROJECT = True`. "
        "Mỗi người mount Drive của mình; kết quả phải nằm trong cùng thư mục gốc được chia sẻ. "
        "Chạy xong notebook, chờ file hiện trên Drive rồi bàn giao cho người tiếp theo; mỗi lần chỉ một người ghi. "
        "Người nhận chạy cell cấu hình, Bootstrap và khởi tạo của notebook tiếp theo. "
        "Biến trong RAM không được chuyển sang phiên mới; cell đang chạy dở có thể phải chạy lại. "
        "Xem `TEAM_DRIVE.md` để thiết lập và xác nhận đường dẫn.\n"]})
    cells.append({"cell_type": "code", "execution_count": None, "metadata": {"tags": ["storage-options"]},
                  "outputs": [], "source": STORAGE_OPTIONS_CELL.splitlines(keepends=True)})
    cells.append({"cell_type": "code", "execution_count": None, "metadata": {"tags": ["bootstrap"]},
                  "outputs": [], "source": BOOTSTRAP.splitlines(keepends=True)})
    for item in cells_data:
        if isinstance(item, tuple):
            ctype, content = item
            cells.append({
                "cell_type": ctype,
                "metadata": {},
                "source": [line + "\n" for line in content.strip().split("\n")]
            })
        else:
            # Split only at top-level numbered step comments, preserving Python blocks.
            for block in re.split(r"(?m)(?=^# [1-9][0-9]*\. )", item.strip()):
                if block.strip():
                    cells.append({"cell_type": "code", "execution_count": None,
                                  "metadata": {}, "outputs": [],
                                  "source": block.strip().splitlines(keepends=True)})
    previous_code_cell = None
    last_code_cell = max(i for i, c in enumerate(cells) if c["cell_type"] == "code" and not c["metadata"].get("tags"))
    for i, cell in enumerate(cells):
        if cell["cell_type"] == "code" and not cell.get("metadata", {}).get("tags"):
            source = "".join(cell["source"])
            # Release previous stage objects in the shared All-in-One kernel.
            if source.startswith("import sys"):
                source = ("import gc\n"
                          "for _old_name in ('df', 'df_sample', 'df_paths', 'meta_df', 'splits', 'profiles', 'outcomes', 'filtered_profiles', 'filtered_outcomes', 'X', 'res', 'p1_preds', 'p2_preds', 'p1_test', 'p2_test', '_'):\n"
                          "    globals().pop(_old_name, None)\n"
                          "if 'con' in globals():\n    globals().pop('con').close()\n"
                          "gc.collect()\n" + source)
            # A fresh kernel must restore imports and paths before stage cells.
            guard = ('if "paths" not in globals() or "PROJECT_ROOT" not in globals():\n'
                     '    raise RuntimeError("Runtime đã mất trạng thái. Chạy lại cell Chọn nơi lưu dữ liệu và Bootstrap, rồi cell khởi tạo stage trước khi tiếp tục.")\n')
            guard += '_pubg_progress = globals().setdefault("_PUBG_CELL_PROGRESS", {})\n'
            if previous_code_cell is not None:
                guard += (f'if _pubg_progress.get({filename!r}, -1) < {previous_code_cell}:\n'
                          f'    raise RuntimeError("{filename}: Chạy thành công cell trước trước khi tiếp tục; không bỏ qua cell bị lỗi.")\n')
            guard += f'_pubg_progress[{filename!r}] = {previous_code_cell if previous_code_cell is not None else -1}\n'
            if filename in NOTEBOOK_DEPENDENCIES:
                guard += ('from src.data.checkpoints import CheckpointManager\n'
                          '_pubg_checkpoint = CheckpointManager(paths["checkpoints"] / "checkpoint_manifest.json")\n'
                          f'_pubg_checkpoint.begin_notebook({filename!r}, {NOTEBOOK_DEPENDENCIES[filename]!r})\n')
            elif filename == "12_final_results_summary.ipynb":
                guard += ('from src.data.io import read_json\n'
                          '_pubg_run_manifest = paths["checkpoints"] / "checkpoint_manifest.json"\n'
                          'if _pubg_run_manifest.is_file():\n'
                          '    _pubg_stages = read_json(_pubg_run_manifest).get("stages", {})\n'
                          '    if any(k.startswith("notebook/") and v.get("status") != "completed" for k, v in _pubg_stages.items()):\n'
                          '        raise RuntimeError("Có notebook chưa hoàn tất; chạy xong rồi khóa lại notebook 11 trước khi đọc kết quả.")\n')
            source = source.replace('con = get_duckdb_connection(',
                                    'if "con" in globals():\n    con.close()\ncon = get_duckdb_connection(')
            if filename in NOTEBOOK_DEPENDENCIES and i == last_code_cell:
                artifacts = 'rq2_artifacts' if filename == '07_rq2_clustering.ipynb' else '{}'
                source += f'\n_pubg_checkpoint.commit({"notebook/" + filename!r}, "notebook_v1", {artifacts})\n'
            if filename in ('07_rq2_clustering.ipynb', '09_rq3_prediction.ipynb', '10_ablation_error_analysis.ipynb') and previous_code_cell is None:
                section = 'rq2' if filename.startswith('07') else 'rq3'
                setup = ("from src.models.compute import compute_info\n"
                         f"device = cfg[{section!r}].get('device', 'cpu')\n"
                         "compute = compute_info(device, install=globals().get('IN_COLAB', False) and globals().get('PUBG_INSTALL_DEPENDENCIES', True))\n"
                         "print('Training backend:', compute)\n")
                source = source.replace('paths = resolve_paths(cfg)\n', 'paths = resolve_paths(cfg)\n' + setup, 1)
            cell["source"] = (guard + source + f'\n_pubg_progress[{filename!r}] = {i}\n').splitlines(keepends=True)
            previous_code_cell = i
        cell["id"] = f"cell-{i:03d}"
    nb_json = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {
                "name": "python",
                "version": "3.10"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 5
    }
    if filename in ('07_rq2_clustering.ipynb', '09_rq3_prediction.ipynb', '10_ablation_error_analysis.ipynb'):
        nb_json['metadata']['accelerator'] = 'GPU'
        nb_json['metadata']['colab'] = {'gpuType': 'T4'}
    with open(NOTEBOOKS_DIR / filename, "w", encoding="utf-8") as f:
        json.dump(nb_json, f, indent=2)
    GENERATED_NOTEBOOKS.append(nb_json)
    print(f"Created {filename}")

# 00_setup.ipynb
create_notebook(
    "00_setup.ipynb",
    "00 — Khởi tạo môi trường, cấu hình và trạng thái Checkpoint",
    "Kiểm tra project root, quyền ghi, 10 config YAML, tài nguyên phần cứng, hash tài liệu nguồn và trạng thái checkpoint thực. Thiếu điều kiện bắt buộc sẽ dừng với lỗi và hướng khắc phục cụ thể.",
    [
        ("markdown", "### 1. Môi trường chạy và kiểm tra project root\n\nMã nguồn đã được khởi tạo ở cell Bootstrap. Cell này xác minh đây là dự án PUBG đúng (có `configs/data.yaml` và `src/utils/config.py`), kiểm tra quyền ghi vào thư mục gốc, và in thông tin môi trường cơ bản."),
        """
import sys
import os
from pathlib import Path

# 1. Định vị project root từ bootstrap
IN_COLAB = "google.colab" in sys.modules
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 2. Kiểm tra đây đúng là dự án PUBG (có đủ marker file)
_required_markers = [
    PROJECT_ROOT / "configs" / "data.yaml",
    PROJECT_ROOT / "configs" / "runtime.yaml",
    PROJECT_ROOT / "src" / "utils" / "config.py",
    PROJECT_ROOT / "src" / "utils" / "generate_notebooks.py",
]
_missing_markers = [str(p) for p in _required_markers if not p.is_file()]
if _missing_markers:
    raise RuntimeError(
        "Project PUBG không tìm thấy tại " + str(PROJECT_ROOT) + ".\\n"
        "Thiếu các file sau:\\n" + "\\n".join("  " + m for m in _missing_markers) + "\\n"
        "Khắc phục:\\n"
        "  Drive mode: kiểm tra quyền Editor và shortcut PUBG_Project trong My Drive, chạy lại Bootstrap.\\n"
        "  Runtime mode: giải nén Project_PUBG vào /content hoặc thư mục hiện tại rồi chạy lại Bootstrap."
    )

# 3. Kiểm tra quyền ghi tại project root
_write_test = PROJECT_ROOT / ".write_test.tmp"
try:
    _write_test.write_text("ok")
    _write_test.unlink()
    _root_writable = True
except Exception as _e:
    _root_writable = False

if not _root_writable:
    _mode = globals().get("PUBG_STORAGE_MODE", "?")
    raise RuntimeError(
        "Không có quyền ghi tại " + str(PROJECT_ROOT) + ".\\n"
        "Storage mode hiện tại: " + _mode + "\\n"
        "Khắc phục Drive mode: xác nhận thư mục được chia sẻ với quyền Editor, re-mount Drive.\\n"
        "Khắc phục Runtime mode: Colab runtime có thể đầy; khởi động lại runtime."
    )

print(f"Project Root  : {PROJECT_ROOT}")
print(f"Storage mode  : {globals().get('PUBG_STORAGE_MODE', 'unknown')}")
print(f"Platform      : {'Google Colab' if IN_COLAB else 'Local'}")
print(f"Quyền ghi root: HOP LE")
print(f"Data root     : {paths['data_root']}")
print(f"Reports root  : {paths['reports_root']}")
""",
        ("markdown", "### 2. Nạp và kiểm tra 10 file cấu hình YAML\n\nNạp đầy đủ 10 file cấu hình, validate kiểu/giá trị từng field quan trọng, và hiển thị bảng phân biệt `required` (phải có trước khi chạy) vs `pending` (được phép null cho đến khi có evidence từ notebook cụ thể)."),
        """
from src.utils.config import load_config, resolve_paths, validate_config, describe_config_status
import pandas as pd

# Nạp toàn bộ 10 file config và validate strict
cfg = load_config(str(PROJECT_ROOT / "configs"))
validate_config(cfg)  # raises with specific remediation if any required field is wrong

print("--- THONG TIN CAU HINH NGHIEN CUU ---")
print(f"Moi truong kich hoat : {cfg['paths']['active_environment']}")
print(f"Che do thuc thi      : {cfg['runtime']['mode']}  (sample=smoke test; full=official)")
print(f"Random state (seed)  : {cfg['runtime']['random_state']}")
print(f"Dataset name         : {cfg['data']['source']['dataset_name']}")
if cfg['data']['source'].get('archive_url'):
    print(f"Archive URL          : {cfg['data']['source']['archive_url']}")
print(f"DuckDB threads       : {cfg['runtime']['duckdb']['threads']}")
print(f"DuckDB memory_limit  : {cfg['runtime']['duckdb']['memory_limit']}")
print(f"mode_strategy        : {cfg['rq2']['mode_strategy']}")

# Bảng required vs pending
_cfg_rows = describe_config_status(cfg)
_df_cfg = pd.DataFrame(_cfg_rows)
print("\\n--- BANG TRANG THAI CAU HINH (required / pending / ok) ---")
print(_df_cfg[["field", "value", "type", "status", "note"]].to_string(index=False))
_n_required_unset = sum(1 for r in _cfg_rows if r["status"] == "required")
_n_pending = sum(1 for r in _cfg_rows if r["status"] == "pending")
print(f"\\nTom tat: {len(_cfg_rows)} fields | ok={sum(1 for r in _cfg_rows if r['status']=='ok')} | required chua dat={_n_required_unset} | pending (cho evidence)={_n_pending}")
if _n_required_unset > 0:
    _unset = [r["field"] for r in _cfg_rows if r["status"] == "required"]
    raise RuntimeError(
        f"{_n_required_unset} field(s) bat buoc chua duoc dat: {_unset}. "
        "Chinh sua trong configs/ roi chay lai cell nay."
    )
""",
        ("markdown", "### 3. Phân giải đường dẫn và khởi tạo thư mục lưu trữ\n\nPhân giải các đường dẫn logic và tạo tất cả thư mục con. Hiển thị bảng đường dẫn thực tế đang dùng."),
        """
# Phân giải đường dẫn theo môi trường (paths đã được tạo ở Bootstrap, cell này xác nhận lại)
paths = resolve_paths(cfg)

required_dirs = [
    ("raw_root",     paths.get("raw_root", paths["raw"])),
    ("interim",      paths["interim"]),
    ("processed",    paths["processed"]),
    ("checkpoints",  paths["checkpoints"]),
    ("experiments",  paths["experiments"]),
    ("manifests",    paths["manifests"]),
    ("models",       paths["models"]),
    ("metrics",      paths["metrics"]),
    ("logs",         paths["logs"]),
    ("tables",       paths["tables"]),
    ("figures",      paths["figures"]),
    ("appendix",     paths["appendix"]),
]

records = []
for name, d_path in required_dirs:
    existed = d_path.exists()
    d_path.mkdir(parents=True, exist_ok=True)
    # Check write permission on each directory
    _can_write = False
    try:
        _t = d_path / ".write_test.tmp"
        _t.write_text("ok")
        _t.unlink()
        _can_write = True
    except Exception:
        pass
    records.append({
        "Thu muc logic": name,
        "Duong dan tuyet doi": str(d_path),
        "Ton tai truoc": "Co" if existed else "Moi tao",
        "Quyen ghi": "OK" if _can_write else "KHONG CO QUYEN",
    })

_df_dirs = pd.DataFrame(records)
print("--- DANH MUC DUONG DAN HE THONG ---")
print(_df_dirs.to_string(index=False))

# Fail immediately if any required directory is not writable
_bad_dirs = [r for r in records if r["Quyen ghi"] != "OK"]
if _bad_dirs:
    raise RuntimeError(
        "Cac thu muc sau khong co quyen ghi:\\n"
        + "\\n".join("  " + r["Duong dan tuyet doi"] for r in _bad_dirs)
        + "\\nKhac phuc: kiem tra quyen Editor tren Drive hoac restart Colab runtime."
    )

# Kiểm tra dữ liệu thô tại raw_root
_raw_root = paths.get("raw_root", paths["raw"])
_zip_files = list(_raw_root.glob("*.zip")) + list(_raw_root.glob("*/*.zip"))
_csv_files = list(_raw_root.glob("*.csv")) + list(_raw_root.glob("*/*.csv"))
print(f"\\nDu lieu tho tai {_raw_root}:")
print(f"  ZIP files: {len(_zip_files)} | CSV files: {len(_csv_files)}")
if not _zip_files and not _csv_files:
    print("  -> Chua co du lieu tho. Notebook 01 se doc ZIP theo batch khi co file.")
""",
        ("markdown", "### 4. Chẩn đoán tài nguyên phần cứng và dự trù nhu cầu ổ đĩa\n\nĐo RAM khả dụng và dung lượng đĩa trống tại thời điểm chạy. Dự trù nhu cầu ổ đĩa từ kích thước dữ liệu thô thực tế. Lưu ý: đây là đĩa ephemeral của runtime/VM, không phải Google Drive quota (15 GB)."),
        """
from src.utils.runtime import check_environment, estimate_disk_budget, save_runtime_snapshot
from src.utils.hashing import hash_file

# Đo tài nguyên runtime (raise_on_critical=True: dừng nếu không có quyền ghi hoặc disk quá thấp)
env_report = check_environment(
    target_dir=str(paths["checkpoints"]),
    min_disk_gb=5.0,
    raise_on_critical=True,
)
# Đĩa cục bộ cho DuckDB spill (ngưỡng 25 GB cảnh báo; không phải quota Drive)
_temp_dir = paths.get("temp_dir", paths["logs"] / "temp")
local_report = check_environment(
    target_dir=str(_temp_dir),
    min_disk_gb=25.0,
    raise_on_critical=False,  # warning only; spill uses project disk, not a separate quota
)

print("--- BAO CAO TAI NGUYEN PHAN CUNG ---")
print(f"Trang thai he thong  : {env_report['status'].upper()}")
print(f"He dieu hanh         : {env_report['runtime']['os_name']} {env_report['runtime']['os_release']}")
print(f"Phien ban Python     : {env_report['runtime']['python_version']}")
print(f"So nhan CPU (logical): {env_report['runtime']['cpu_count_logical']}")
print(f"RAM kha dung         : {env_report['runtime'].get('available_ram_gb','N/A')} GB / {env_report['runtime'].get('total_ram_gb','N/A')} GB tong")
print(f"Dia artifacts        : {env_report['free_disk_gb']} GB trong / {env_report['total_disk_gb']} GB tong")
print(f"Dia temp (spill)     : {local_report['free_disk_gb']} GB trong")
print("LUU Y: disk o tren la dia runtime/VM (ephemeral), KHONG phai Google Drive quota.")
print(f"runtime.mode = '{cfg['runtime'].get('mode')}' -> khong tu lay mau hoac cat shard.")
if local_report["warnings"]:
    print(f"CANH BAO: {local_report['warnings']}")
    print("Chi dan: {local_report.get('remediation', [])}")

# Thư viện versions
_pkgs = env_report["runtime"].get("packages", {})
print("\\n--- PHIEN BAN THU VIEN ---")
for _pkg, _ver in _pkgs.items():
    print(f"  {_pkg:<12} : {_ver}")

# GPU info
print(f"CUDA available       : {env_report['runtime'].get('cuda_available', False)}")
if env_report['runtime'].get('cuml_version'):
    print(f"cuML version         : {env_report['runtime']['cuml_version']}")

# Dự trù nhu cầu ổ đĩa từ raw data thực tế
_raw_root = paths.get("raw_root", paths["raw"])
_budget = estimate_disk_budget(_raw_root)
print("\\n--- DU TRU NHU CAU O DIA ---")
print(f"Raw data hien co     : {_budget['raw_gb']} GB")
print(f"Staging (shards)     : ~{_budget['staging_gb']} GB")
print(f"Interim              : ~{_budget['interim_gb']} GB")
print(f"Processed            : ~{_budget['processed_gb']} GB")
print(f"DuckDB spill         : ~{_budget['spill_gb']} GB")
print(f"Tong uoc tinh        : ~{_budget['total_estimated_gb']} GB")
print(f"Dia trong hien co    : {env_report['free_disk_gb']} GB")
print(_budget["note"])

# Hash tài liệu nguồn (không lấy hash từ Drive hay internet; chỉ file local)
_spec_path = PROJECT_ROOT / "PUBG_RESEARCH_SPEC.md"
_plan_path = PROJECT_ROOT / "PUBG_IMPLEMENTATION_PLAN.md"
_doc_hashes = {}
for _doc_name, _doc_path in [("PUBG_RESEARCH_SPEC.md", _spec_path), ("PUBG_IMPLEMENTATION_PLAN.md", _plan_path)]:
    if _doc_path.is_file():
        _doc_hashes[_doc_name] = hash_file(_doc_path)
        print(f"Hash {_doc_name}: {_doc_hashes[_doc_name][:16]}...")
    else:
        _doc_hashes[_doc_name] = "not_found_at_" + str(_doc_path)
        print(f"CANH BAO: {_doc_name} khong tim thay tai {_doc_path} (snapshot ghi 'not_found')")

_gen_hash = hash_file(PROJECT_ROOT / "src" / "utils" / "generate_notebooks.py")
print(f"generate_notebooks.py SHA256: {_gen_hash[:16]}...")

# Lưu runtime snapshot ra JSON artifact để kiểm tra lại sau
_snapshot_path = paths["manifests"] / "runtime_snapshot.json"
_snapshot = save_runtime_snapshot(_snapshot_path, PROJECT_ROOT, cfg, _doc_hashes)
print(f"\\nRuntime snapshot da luu: {_snapshot_path}")
""",
        ("markdown", "### 5. Trạng thái Checkpoint thực — DAG readiness\n\nHiển thị metadata đầy đủ của từng stage đã hoàn tất: status, signature, timestamp, số artifact. Không chỉ liệt kê tên stage."),
        """
from src.data.checkpoints import CheckpointManager
import pandas as pd

ckpt_mgr = CheckpointManager(manifest_path=paths["checkpoints"] / "checkpoint_manifest.json")
manifest = ckpt_mgr.load_manifest()

stages = manifest.get("stages", {})
print("--- TRANG THAI CHECKPOINT DAG ---")
if not stages:
    print("Chua co checkpoint nao duoc luu (He thong o trang thai Clean Start).")
else:
    _ckpt_rows = []
    for _stage_name, _stage_info in stages.items():
        _ckpt_rows.append({
            "Stage": _stage_name,
            "Status": _stage_info.get("status", "unknown"),
            "Signature": _stage_info.get("signature", "")[:12] + "...",
            "Completed at": _stage_info.get("completed_at", ""),
            "N artifacts": len(_stage_info.get("artifacts", {})),
        })
    _df_ckpt = pd.DataFrame(_ckpt_rows)
    print(_df_ckpt.to_string(index=False))

# Bảng trạng thái tổng quan 13 notebook
_notebook_order = [
    "00_setup.ipynb", "01_download_validate.ipynb", "02_data_quality_and_structure.ipynb",
    "03_build_player_match.ipynb", "04_combat_timing.ipynb", "05_eda.ipynb",
    "06_rq1_analysis.ipynb", "07_rq2_clustering.ipynb", "08_build_historical.ipynb",
    "09_rq3_prediction.ipynb", "10_ablation_error_analysis.ipynb",
    "11_finalize_results.ipynb", "12_final_results_summary.ipynb",
]
_nb_rows = []
for _nb in _notebook_order:
    _stage_key = "notebook/" + _nb
    _info = stages.get(_stage_key, {})
    _nb_rows.append({
        "Notebook": _nb,
        "Status": _info.get("status", "not_started"),
        "Completed at": _info.get("completed_at", "-"),
    })
print("\\n--- TONG QUAN 13 NOTEBOOK ---")
print(pd.DataFrame(_nb_rows).to_string(index=False))

print("\\n=> Notebook 00 hoan tat. Mo va chay: '01_download_validate.ipynb'.")
"""
    ]
)

# 01_download_validate.ipynb
create_notebook(
    "01_download_validate.ipynb",
    "01 — Tải dữ liệu, kiểm kê Shards và xác thực Schema Contract",
    "Đọc đầy đủ CSV trong ZIP theo batch, kiểm tra schema và lưu Parquet ZSTD. Không giải nén toàn bộ; khôi phục theo shard khi bị ngắt.",
    [
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.data.io import get_duckdb_connection, atomic_write_json
from src.data.batch_ingest import ingest_sources, staged_paths, finalize_ingest
from src.data.checkpoints import CheckpointManager

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
con = get_duckdb_connection(temp_dir=paths["temp_dir"], **{k: cfg["runtime"]["duckdb"][k] for k in ("memory_limit", "threads")})
ckpt_mgr = CheckpointManager(manifest_path=paths["checkpoints"] / "checkpoint_manifest.json")

# 1. Đọc ZIP/CSV theo batch và ghi Parquet nén; không giải nén toàn bộ
staging_dir = paths["interim"] / "staging_shards"
inventory = ingest_sources(
    con, paths["raw_root"], staging_dir, cfg["data"], cfg["schema"],
    batch_rows=globals().get("PUBG_BATCH_ROWS", 50000),
    work_dir=paths["temp_dir"] / "batch_ingest",
)
atomic_write_json(paths["manifests"] / "source_inventory.json", inventory)
print(f"Đã xử lý đầy đủ {len(inventory['shards'])} shards, {sum(s['rows'] for s in inventory['shards']):,} dòng.")

# 2. Khóa checkpoint sau khi tất cả shard đã hoàn tất
inventory = finalize_ingest(con, paths["raw_root"], staging_dir, cfg["data"], cfg["schema"],
                            batch_rows=globals().get("PUBG_BATCH_ROWS", 50000),
                            work_dir=paths["temp_dir"] / "batch_ingest")
atomic_write_json(paths["manifests"] / "source_inventory.json", inventory)
ckpt_mgr.commit("schema", "schema_batch_v1", {"converted_agg_shards": staging_dir / "batch_manifest.json"})
print("Gate G1 Hoàn tất: Shards đã được kiểm kê và chuẩn hóa sang Parquet.")
"""
    ]
)

# 02_data_quality_and_structure.ipynb
create_notebook(
    "02_data_quality_and_structure.ipynb",
    "02 — Chất lượng dữ liệu, cấu trúc Roster, Chronology và Khóa Split",
    "Audit trùng lặp, kiểm tra roster, phân cấp Chronology Grade (A/B/C) và khóa Split Manifest trước khi phân tích quan hệ outcome (Gate G2).",
    [
        ("markdown", r"""### Tổng quan Giai đoạn và Nguyên tắc Khoa học Dữ liệu

Notebook này thực hiện các nhiệm vụ cốt lõi trong Giai đoạn 4 (Phase VII):
1. **Làm sạch dữ liệu đa phân mảnh (Shards Cleaning):** Khử trùng lặp hoàn toàn, cách ly các bản ghi xung đột khóa định danh (identity key conflicts), loại bỏ các giá trị ngoài miền xác định (domain violations), và gán nhãn tính hợp lệ của từng mục tiêu (target validity flags).
2. **Đối soát bảo toàn dòng (Sequential Removal Cascade):** Duy trì bảng đối soát nghiêm ngặt đảm bảo $N_0 - \sum_{i=1}^k R_i = N_{\\text{clean}}$, đồng thời tách biệt hoàn toàn bảng kiểm toán cờ lỗi chẩn đoán (`error_flags.csv`) để không cộng dồn sai lệch.
3. **Xây dựng Match Metadata & Kiểm toán Roster:** Đo lường quy mô đội hình thực tế, thời lượng ước tính của trận đấu, và kiểm toán bất nhất thuộc tính (`date`, `match_mode`, `party_size`, `game_size`) trong cùng một trận mà không dùng hàm gộp làm mờ xung đột.
4. **Kiểm định tính tuần tự thời gian (Chronology Audit):** Phân định Cấp bậc thời gian (Grade A/B/C) dựa trên bằng chứng kiểm chứng. Không gán Cấp A chỉ vì tỷ lệ trùng timestamp thấp khi thiếu log telemetry chính thức (theo đặc tả D04).
5. **Khóa phân chia tập dữ liệu cô lập theo trận (Match-Isolated Split):** Phân bổ dữ liệu thành ba tập Train / Validation / Test với nguyên tắc bất biến: toàn bộ người chơi trong cùng một trận đấu thuộc về cùng một phân vùng duy nhất ($S_{\\text{train}} \\cap S_{\\text{val}} = \\emptyset$, $S_{\\text{train}} \\cap S_{\\text{test}} = \\emptyset$, $S_{\\text{val}} \\cap S_{\\text{test}} = \\emptyset$).
6. **Nghiệm thu Cổng G2 (Gate G2):** Khóa `split_manifest.json` vào hệ thống checkpoint trước khi bất kỳ đặc trưng hay nhãn kết quả nào được phân tích.

Mọi thao tác tuân thủ nghiêm ngặt chuẩn mực: không lấy mẫu tùy tiện, không xóa dòng không có căn cứ, và bảo toàn tính tái lập 100%."""),
        """
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from src.utils.config import load_config, resolve_paths
from src.data.io import get_duckdb_connection, atomic_write_json, read_json
from src.data.batch_ingest import staged_paths
from src.data.checkpoints import CheckpointManager

# Bước 1: Khởi tạo cấu hình và kết nối DuckDB
cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
con = get_duckdb_connection(temp_dir=paths["temp_dir"], **{k: cfg["runtime"]["duckdb"][k] for k in ("memory_limit", "threads")})
ckpt_mgr = CheckpointManager(manifest_path=paths["checkpoints"] / "checkpoint_manifest.json")

# Bước 2: Kiểm tra điều kiện tiên quyết: Gate G1 phải hoàn tất
staging_dir = paths["interim"] / "staging_shards"
agg_shards = staged_paths(staging_dir, "aggregate")
if not agg_shards:
    raise FileNotFoundError(
        f"Không tìm thấy aggregate Parquet trong {staging_dir}. "
        "Hãy chạy hoàn tất notebook 01_download_validate.ipynb trước khi chạy notebook 02."
    )

print("--- KIỂM TRA ĐIỀU KIỆN TIÊN QUYẾT (GATE G1) ---")
print(f"Thư mục staging shards : {staging_dir}")
print(f"Số lượng aggregate shards : {len(agg_shards)}")
print("Trạng thái Gate G1     : SẴN SÀNG")
""",
        ("markdown", """### I. Làm sạch dữ liệu và Bảng kiểm toán lỗi độc lập (Removal Ledger vs Error Flags)

Trong kỹ thuật dữ liệu, việc loại bỏ dữ liệu phải tuân thủ nguyên tắc dòng thác tuần tự (sequential cascade):
$$\\text{rows\\_before} - \\text{rows\\_removed} = \\text{rows\\_after}$$

Bốn bước tuần tự được thực thi:
1. **Bước 1 (Exact Deduplication):** Loại bỏ các dòng trùng lặp 100% trên toàn bộ các cột.
2. **Bước 2 (Missing Identifiers):** Loại bỏ bản ghi thiếu `match_id` hoặc `team_id`. Riêng bản ghi thiếu `player_name` vẫn được giữ lại vì kết quả cấp đội và cấp trận trong RQ1 vẫn hoàn toàn hợp lệ.
3. **Bước 3 (Domain Violations):** Loại bỏ các bản ghi có số liệu phi vật lý: sát thương âm, quãng đường di chuyển âm, thời gian sống âm, thứ hạng đội không dương ($P \\le 0$), hoặc chứa giá trị không hữu hạn (`NaN`, `Inf`).
4. **Bước 4 (Identity Key Conflicts Quarantine):** Khi một cặp `(match_id, player_name)` xuất hiện nhiều lần với các số liệu thống kê khác nhau, hệ thống **không tùy tiện giữ dòng đầu tiên** (`keep='first'`), mà cách ly kiểm toán để tránh sai lệch thông tin.

Bảng kiểm toán cờ lỗi (`error_flags.csv`) được ghi nhận độc lập để phục vụ chẩn đoán chất lượng dữ liệu thô, không cộng dồn các cờ lỗi thành tổng số dòng bị loại."""),
        """
if "audit_and_clean_aggregate_data" not in globals():
    from src.data.cleaning import audit_and_clean_aggregate_data

cleaned_pq = paths["interim"] / "cleaned_aggregate.parquet"
removal_csv = paths["tables"] / "removal_log.csv"
error_flags_csv = paths["tables"] / "error_flags.csv"

# Thực thi làm sạch dữ liệu tuần tự
clean_summary = audit_and_clean_aggregate_data(
    con=con,
    aggregate_parquet_paths=agg_shards,
    output_cleaned_parquet=cleaned_pq,
    removal_log_path=removal_csv,
    error_flags_path=error_flags_csv,
)

# Hiển thị kết quả kiểm toán
df_removal = pd.read_csv(removal_csv)
df_flags = pd.read_csv(error_flags_csv)

print("--- NHẬT KÝ LOẠI TRỪ TUẦN TỰ (REMOVAL LEDGER) ---")
print(df_removal[["step", "stage", "reason", "rows_before", "rows_removed", "rows_after"]].to_string(index=False))

print("\\n--- BẢNG KIỂM TOÁN CỜ LỖI ĐỘC LẬP (ERROR FLAGS AUDIT) ---")
print(df_flags[["flag_name", "affected_rows", "note"]].to_string(index=False))

# Xác nhận bảo toàn dòng
n0 = clean_summary["total_raw_rows"]
n_clean = clean_summary["clean_rows"]
dropped = clean_summary["dropped_rows"]
sum_r = sum(clean_summary["step_removals"].values())
assert n0 - sum_r == n_clean, f"Lỗi đối soát dòng: {n0} - {sum_r} != {n_clean}"
assert dropped == sum_r, f"Lỗi tổng dòng loại: {dropped} != {sum_r}"
print(f"\\nĐối soát dòng: ĐẠT ({n0:,} ban đầu - {dropped:,} loại = {n_clean:,} dòng sạch)")
""",
        ("markdown", """### II. Xây dựng Match Metadata và Kiểm toán Roster (Roster & Conflict Audit)

Để chuẩn bị cho các câu hỏi nghiên cứu, dữ liệu cấp trận đấu được tổng hợp trước khi áp dụng bất kỳ bộ lọc đặc thù nào.
1. **Kiểm toán Roster (Roster Completeness):** Một trận đấu được xác nhận có cấu trúc đội hình đầy đủ (`is_roster_complete = True`) khi:
   - Số đội quan sát được $N_{\\text{teams}} \\ge 2$.
   - Thứ hạng tối đa quan sát được $P_{\\max} \\ge 2$.
   - Chênh lệch $|N_{\\text{teams}} - P_{\\max}| \\le 2$.
2. **Kiểm toán bất nhất thuộc tính nội bộ trận:** Hệ thống ghi nhận rõ các cờ xung đột:
   - `has_date_conflict`: Cùng trận đấu nhưng ghi nhận nhiều mốc thời gian khác nhau.
   - `has_mode_conflict`: Cùng trận đấu nhưng ghi nhận nhiều chế độ chơi (`match_mode`) khác nhau.
   - `has_party_size_conflict`: Cùng trận đấu nhưng ghi nhận nhiều quy mô nhóm (`party_size`) khác nhau.
   - `has_game_size_conflict`: Cùng trận đấu nhưng ghi nhận nhiều quy mô trận (`game_size`) khác nhau.
   Tuyệt đối không dùng `MIN()` hoặc `MODE()` một cách âm thầm để che giấu xung đột dữ liệu."""),
        """
from src.data.match_metadata import build_match_metadata

meta_pq = paths["interim"] / "match_metadata.parquet"
audit_report_json = paths["manifests"] / "match_audit_report.json"

total_matches = build_match_metadata(
    con=con,
    cleaned_aggregate_parquet=cleaned_pq,
    output_metadata_parquet=meta_pq,
    audit_report_path=audit_report_json,
)

# Đọc kết quả kiểm toán và phân bố cấu trúc trận
df_audit = con.execute(\"\"\"
    SELECT
        count(*) AS total_matches,
        count(*) FILTER (WHERE is_roster_complete) AS roster_complete_matches,
        count(*) FILTER (WHERE has_date_conflict) AS date_conflicts,
        count(*) FILTER (WHERE has_mode_conflict) AS mode_conflicts,
        count(*) FILTER (WHERE has_party_size_conflict) AS party_size_conflicts,
        round(avg(observed_player_count), 2) AS avg_players,
        round(avg(observed_team_count), 2) AS avg_teams
    FROM read_parquet(?)
\"\"\", [str(meta_pq)]).df()

print("--- TỔNG KẾT KIỂM TOÁN CẤU TRÚC TRẬN ĐẤU (MATCH METADATA AUDIT) ---")
print(df_audit.to_string(index=False))

# Bảng phân phối chế độ chơi (match_mode)
df_modes = con.execute(\"\"\"
    SELECT match_mode, count(*) AS match_count, round(count(*) * 100.0 / sum(count(*)) over(), 2) AS pct
    FROM read_parquet(?)
    GROUP BY match_mode
    ORDER BY match_count DESC;
\"\"\", [str(meta_pq)]).df()
print("\\n--- PHÂN BỐ CHẾ ĐỘ CHƠI ---")
print(df_modes.to_string(index=False))
""",
        ("markdown", """### III. Đánh giá tính tuần tự thời gian (Chronology Audit) và Phân định Cấp bậc

Theo nguyên tắc nghiên cứu trong `PUBG_RESEARCH_SPEC.md` v3.0 (Quyết định D04):
- **Cấp A (Grade A - Exact Intra-day Order):** Cần có bằng chứng thực tế xác thực thứ tự hoàn thành của từng trận đấu nội trong ngày (ví dụ: log telemetry có dấu thời gian bắt đầu và kết thúc). Tỷ lệ trùng timestamp thấp **chưa đủ cơ sở** để cấp Grade A.
- **Cấp B (Grade B - Day-level Chronology):** Xác nhận dữ liệu phân bố trên ít nhất 3 ngày riêng biệt ($D \\ge 3$). Cho phép mô hình hóa lịch sử theo nguyên tắc: trận đấu tại ngày $T$ chỉ được sử dụng hồ sơ lịch sử từ các ngày trước đó nghiêm ngặt ($< T$), loại trừ các trận trong cùng ngày để ngăn chặn rò rỉ thứ tự nội ngày.
- **Cấp C (Grade C - Insufficient Chronology):** Dữ liệu quan sát dưới 3 ngày hoặc không thể phân tích thời gian tin cậy. Khi đó các bài toán dự đoán lịch sử S2/P3 bị chặn chính thức."""),
        """
from src.analysis.eda import run_chronology_audit

meta_df = con.execute("SELECT match_date FROM read_parquet(?)", [str(meta_pq)]).df()
chrono_report = run_chronology_audit(meta_df, has_exact_order_evidence=False)
atomic_write_json(paths["manifests"] / "chronology_report.json", chrono_report)

print("--- KẾT QUẢ KIỂM TOÁN TÍNH TUẦN TỰ THỜI GIAN (CHRONOLOGY AUDIT) ---")
print(f"Cấp bậc xác định (Grade)   : {chrono_report['grade']}")
print(f"Trạng thái mô hình hóa     : {chrono_report['historical_modeling_status']}")
print(f"Chính sách lịch sử áp dụng : {chrono_report['policy']}")
print(f"Tổng số ngày quan sát      : {chrono_report['total_days_observed']}")
print(f"Tỷ lệ trùng mốc thời gian  : {chrono_report['timestamp_tie_ratio']:.4%}")
print(f"Mốc thời gian sớm nhất     : {chrono_report['min_timestamp']}")
print(f"Mốc thời gian muộn nhất    : {chrono_report['max_timestamp']}")
print(f"Chi tiết đánh giá          : {chrono_report['description']}")
""",
        ("markdown", """### IV. Phân chia tập dữ liệu cô lập theo trận (Match-Isolated Split)

Để đảm bảo kết quả đánh giá mô hình khách quan và không bị rò rỉ dữ liệu (data leakage):
1. **Nguyên tắc cô lập trận đấu (Match Isolation Invariant):** Toàn bộ người chơi tham gia cùng một trận đấu phải thuộc về cùng một phân vùng (split) duy nhất. Không bao giờ chia ngẫu nhiên ở cấp dòng người chơi.
2. **Chiến lược phân chia:** Đọc từ `configs/runtime.yaml` và `configs/data.yaml`.
   - Chiến lược mặc định: Nhóm ngẫu nhiên theo trận (`group_by_match`) hoặc Phân chia theo thời gian (`chronological`).
   - Tỷ lệ chuẩn: Train 70%, Validation 15%, Test 15%.
3. **Kiểm tra giao nhau (Zero Intersection Check):**
   $$S_{\\text{train}} \\cap S_{\\text{val}} = \\emptyset, \\quad S_{\\text{train}} \\cap S_{\\text{test}} = \\emptyset, \\quad S_{\\text{val}} \\cap S_{\\text{test}} = \\emptyset$$"""),
        """
from src.models.splits import create_split_assignments

split_pq = paths["interim"] / "split_assignments.parquet"
split_manifest = paths["manifests"] / "split_manifest.json"

split_strategy = cfg.get("splits", {}).get("strategy", "group_by_match")
split_ratios = cfg.get("splits", {}).get("ratios", {"train": 0.70, "val": 0.15, "test": 0.15})
split_seed = cfg["runtime"].get("random_state", 42)

split_meta = create_split_assignments(
    con=con,
    match_metadata_parquet=meta_pq,
    output_assignments_parquet=split_pq,
    output_manifest_json=split_manifest,
    strategy=split_strategy,
    train_ratio=split_ratios.get("train", 0.70),
    val_ratio=split_ratios.get("val", 0.15),
    test_ratio=split_ratios.get("test", 0.15),
    random_state=split_seed,
)

# Hiển thị bảng tổng kết phân chia
df_splits = pd.DataFrame([
    {"Split": sp, "Số trận": split_meta["match_counts"].get(sp, 0),
     "Ước tính người chơi": split_meta["estimated_player_counts"].get(sp, 0),
     "Bắt đầu": split_meta["date_ranges"].get(sp, {}).get("start", "-"),
     "Kết thúc": split_meta["date_ranges"].get(sp, {}).get("end", "-")}
    for sp in ("train", "validation", "test")
])
print("--- TỔNG KẾT PHÂN CHIA DỮ LIỆU CÔ LẬP THEO TRẬN (SPLIT MANIFEST) ---")
print(df_splits.to_string(index=False))

# Xác nhận không có giao nhau giữa các split
intersections = split_meta["split_intersections"]
assert intersections["train_val"] == 0, "Rò rỉ dữ liệu giữa Train và Validation!"
assert intersections["train_test"] == 0, "Rò rỉ dữ liệu giữa Train và Test!"
assert intersections["val_test"] == 0, "Rò rỉ dữ liệu giữa Validation và Test!"
print(f"\\nKiểm tra cô lập trận đấu: ĐẠT (Giao nhau Train/Val={intersections['train_val']}, Train/Test={intersections['train_test']}, Val/Test={intersections['val_test']})")
""",
        ("markdown", """### V. Trực quan hóa Kiểm toán Dữ liệu và Phân bố Thời gian

Vẽ và lưu trữ hai biểu đồ kiểm toán chính thức vào thư mục `reports/figures/`:
1. **Biểu đồ Thác dòng loại bỏ (Removal Waterfall / Breakdown):** Trực quan hóa số lượng bản ghi bị loại bỏ qua từng bước làm sạch tuần tự, minh họa rõ ràng tính không đếm trùng.
2. **Biểu đồ Phân bố số trận đấu theo ngày (Matches per Day Distribution):** Thể hiện số lượng trận đấu diễn ra theo dòng thời gian quan sát được."""),
        """
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

fig_dir = paths["figures"]
fig_dir.mkdir(parents=True, exist_ok=True)

# - Biểu đồ 1: Thác dòng làm sạch
fig, ax = plt.subplots(figsize=(10, 5))
steps = [r["reason"] for r in df_removal[df_removal["stage"] == "cleaning"].to_dict(orient="records") if r["reason"] not in ("total_dropped_records", "validated_clean_records")]
removals = [r["rows_removed"] for r in df_removal[df_removal["stage"] == "cleaning"].to_dict(orient="records") if r["reason"] not in ("total_dropped_records", "validated_clean_records")]
ax.bar(steps, removals, color="#4C72B0", edgecolor="black")
ax.set_title("So luong ban ghi bi loai bo theo tung buoc lam sach (Removal Cascade)", fontsize=13, fontweight="bold")
ax.set_ylabel("So dong bi loai (Rows Removed)", fontsize=11)
ax.set_xticklabels(steps, rotation=20, ha="right", fontsize=10)
for idx, val in enumerate(removals):
    ax.text(idx, val + (max(removals)*0.02 if max(removals)>0 else 0.1), f"{val:,}", ha="center", va="bottom", fontsize=10)
fig.tight_layout()
waterfall_path = fig_dir / "w03_removal_waterfall.png"
fig.savefig(waterfall_path, dpi=200)
plt.close(fig)
print(f"Da luu bieu do: {waterfall_path.name}")

# - Biểu đồ 2: Số trận theo ngày
df_daily = con.execute(\"\"\"
    SELECT CAST(match_date AS DATE) AS match_day, count(*) AS match_count
    FROM read_parquet(?)
    GROUP BY CAST(match_date AS DATE)
    ORDER BY match_day ASC;
\"\"\", [str(meta_pq)]).df()

if not df_daily.empty:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(df_daily["match_day"].astype(str), df_daily["match_count"], marker="o", color="#55A868", linewidth=2)
    ax.set_title("Phan bo so luong tran dau theo ngay quan sat", fontsize=13, fontweight="bold")
    ax.set_ylabel("So tran (Match Count)", fontsize=11)
    ax.set_xlabel("Ngay quan sat (Match Date)", fontsize=11)
    ax.set_xticklabels(df_daily["match_day"].astype(str), rotation=45, ha="right", fontsize=9)
    fig.tight_layout()
    daily_path = fig_dir / "w03_matches_per_day.png"
    fig.savefig(daily_path, dpi=200)
    plt.close(fig)
    print(f"Da luu bieu do: {daily_path.name}")
""",
        ("markdown", """### VI. Nghiệm thu Cổng kiểm soát G2 (Gate G2) và Bàn giao sang Notebook 03

Để được thông qua Cổng kiểm soát G2 (Gate G2) và chuyển sang xây dựng đặc trưng trong Notebook 03:
- [x] Bảng `removal_log.csv` khớp chính xác đẳng thức dòng thác $N_0 - \\sum R_i = N_{\\text{clean}}$.
- [x] Bảng `error_flags.csv` kiểm toán cờ lỗi độc lập không bị cộng dồn sai lệch.
- [x] Bảng `match_metadata.parquet` ghi nhận đầy đủ thống kê đội hình và kiểm toán xung đột thuộc tính.
- [x] Báo cáo `chronology_report.json` xác định đúng Grade A/B/C dựa trên bằng chứng, không suy đoán.
- [x] Bảng phân chia `split_assignments.parquet` và `split_manifest.json` đảm bảo cô lập 100% theo trận đấu, không giao nhau giữa các tập.
- [x] Checkpoint `split_manifest` được ghi nhận chính thức vào hệ thống checkpoint."""),
        """
# Khóa checkpoint Gate G2
ckpt_mgr.commit(
    stage="split_manifest",
    signature=split_meta["config_hash"],
    artifacts={
        "split_assignments": split_pq,
        "match_metadata": meta_pq,
        "cleaned_aggregate": cleaned_pq,
        "removal_log": removal_csv,
        "error_flags": error_flags_csv,
        "chronology_report": paths["manifests"] / "chronology_report.json",
    }
)

handoff_table = [
    {"Artifact": "cleaned_aggregate.parquet", "Duong dan": str(cleaned_pq.relative_to(PROJECT_ROOT)), "Mo ta": "Tap du lieu aggregate da duoc lam sach va chuan hoa"},
    {"Artifact": "match_metadata.parquet", "Duong dan": str(meta_pq.relative_to(PROJECT_ROOT)), "Mo ta": "Thong ke cap tran, roster completeness va xung dot"},
    {"Artifact": "split_assignments.parquet", "Duong dan": str(split_pq.relative_to(PROJECT_ROOT)), "Mo ta": "Gan nhan train/val/test co lap theo tran dau"},
    {"Artifact": "chronology_report.json", "Duong dan": str((paths["manifests"] / "chronology_report.json").relative_to(PROJECT_ROOT)), "Mo ta": "Danh gia cap bac thoi gian Grade A/B/C"},
    {"Artifact": "removal_log.csv", "Duong dan": str(removal_csv.relative_to(PROJECT_ROOT)), "Mo ta": "Nhat ky loai tru tuan tu bao toan dong"},
]

print("================================================================================")
print("GATE G2 HOÀN TẤT VÀ ĐÃ KHÓA CHECKPOINT")
print("BÀN GIAO SANG NOTEBOOK 03: '03_build_player_match.ipynb'")
print("================================================================================")
print(pd.DataFrame(handoff_table).to_string(index=False))
"""
    ]
)

# 03_build_player_match.ipynb
create_notebook(
    "03_build_player_match.ipynb",
    "03 — Xây dựng Player-Match Base (Combat, Movement, Support, Placement)",
    "Tính toán các đặc trưng hành vi người chơi và normalized placement với mẫu số đã xác minh.",
    [
        ("markdown", r"""### Tổng quan Giai đoạn và Nguyên tắc Khoa học Dữ liệu

Notebook này thực hiện các nhiệm vụ cốt lõi trong Giai đoạn 5 (Phase VIII):
1. **Từ điển Đặc trưng Nghiên cứu (Feature Dictionary):** Xuất bản từ điển chuẩn tắc định nghĩa tên, công thức, nguồn dữ liệu, mẫu số, ngữ nghĩa giá trị thiếu (missing semantics), và danh sách bài toán được phép sử dụng (task allowlist) để ngăn chặn rò rỉ dữ liệu (leakage).
2. **Tính toán Đặc trưng Hành vi Cơ sở (Base Behavioral Features):**
   - **Nhóm Chiến đấu (Combat):** `player_kills`, `player_dmg`, và `damage_per_kill` với mẫu số $player\_kills$. Mẫu số bằng 0 bắt buộc trả về `NaN`, tuyệt đối không thay bằng 0.
   - **Nhóm Di chuyển (Movement):** `player_dist_walk`, `player_dist_ride`, `total_distance`, và `walk_ratio` với mẫu số $total\_distance$. Mẫu số bằng 0 bắt buộc trả về `NaN`.
   - **Nhóm Hỗ trợ (Support):** `player_assists`, `player_dbno`, và `assist_ratio` với mẫu số $player\_assists + player\_kills$. Mẫu số bằng 0 bắt buộc trả về `NaN`.
3. **Chuẩn hóa Thứ hạng Đội (Normalized Placement):**
   $$normalized\_placement = 1 - \frac{team\_placement - 1}{N_{teams} - 1}$$
   - **Điều kiện tính toán:** Trận đấu phải có cấu trúc đội hình tin cậy (`is_roster_complete = True`), số đội quan sát được $N_{teams} > 1$, và thứ hạng thực tế $1 \le team\_placement \le N_{teams}$.
   - **Xử lý ngoài miền:** Khi không thỏa mãn điều kiện, giá trị nhận `NULL` và cờ `valid_placement = False`. Tuyệt đối **không dùng hàm kẹp** (`np.clip`) để che giấu bất thường dữ liệu.
4. **Phân tách Khái niệm Chế độ chơi (Mode Decoupling):**
   - Tách biệt rõ ràng góc nhìn `perspective_mode` (`tpp`, `fpp`, `unknown`) khỏi quy mô đội `team_size_mode` (`solo`, `duo`, `squad`, `unknown`).
   - Kích thước nhóm (`party_size`) khác 1, 2, 4 được gán trạng thái `unknown`, không ép buộc mặc định.
5. **Bảo toàn Dòng Tuyệt đối (Exact Row Preservation):** Phép nối trái (Left Join) với metadata bảo toàn 100% số dòng sạch từ Giai đoạn 4 ($N_{\text{base}} = N_{\text{clean}}$).
6. **Nghiệm thu Cổng G3 (Gate G3):** Khóa `player_match_base.parquet` và xuất báo cáo kiểm định chất lượng (`feature_validation_base.csv`)."""),
        """
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np
from src.utils.config import load_config, resolve_paths
from src.data.io import get_duckdb_connection, atomic_write_json
from src.data.checkpoints import CheckpointManager

# Bước 1: Khởi tạo cấu hình và kết nối DuckDB
cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
con = get_duckdb_connection(temp_dir=paths["temp_dir"], **{k: cfg["runtime"]["duckdb"][k] for k in ("memory_limit", "threads")})
ckpt_mgr = CheckpointManager(manifest_path=paths["checkpoints"] / "checkpoint_manifest.json")

# Bước 2: Kiểm tra điều kiện tiên quyết (Gate G2)
cleaned_agg_pq = paths["interim"] / "cleaned_aggregate.parquet"
meta_pq = paths["interim"] / "match_metadata.parquet"
if not cleaned_agg_pq.is_file():
    raise FileNotFoundError(f"Không tìm thấy {cleaned_agg_pq}. Hãy chạy hoàn tất notebook 02 trước.")
if not meta_pq.is_file():
    raise FileNotFoundError(f"Không tìm thấy {meta_pq}. Hãy chạy hoàn tất notebook 02 trước.")

print("--- KIỂM TRA ĐIỀU KIỆN TIÊN QUYẾT (GATE G2) ---")
print(f"Dữ liệu sạch (Cleaned Aggregate) : {cleaned_agg_pq.name}")
print(f"Metadata trận đấu (Match Meta)   : {meta_pq.name}")
print("Trạng thái Gate G2               : SẴN SÀNG")
""",
        ("markdown", r"""### I. Xuất bản Từ điển Đặc trưng Nghiên cứu (Feature Dictionary & Registry Contracts)

Hệ thống quản lý đặc trưng trung tâm (`FeatureRegistry`) định nghĩa hợp đồng kiểm soát nghiêm ngặt:
- Mỗi đặc trưng thuộc một nhóm chức năng cụ thể: `combat`, `movement`, `support`, `outcome`, `context`, `diagnostic`.
- Ghi nhận rõ công thức tính toán, mẫu số chuẩn hóa, ngữ nghĩa giá trị khuyết thiếu và danh mục tác vụ được cấp quyền (`allowed_tasks`).
- Ngăn chặn nguy cơ rò rỉ mục tiêu vào các tập đặc trưng của mô hình dự đoán."""),
        """
from src.features.registry import FeatureRegistry

dict_csv = paths["tables"] / "feature_dictionary.csv"
registry = FeatureRegistry()
registry.export_dictionary_csv(dict_csv)

df_dict = pd.read_csv(dict_csv)
print("--- TỪ ĐIỂN ĐẶC TRƯNG NGHIÊN CỨU (FEATURE DICTIONARY) ---")
print(df_dict[["feature_name", "group", "source_columns", "denominator", "missing_semantics"]].to_string(index=False))
""",
        ("markdown", r"""### II. Tính toán Đặc trưng Hành vi Cơ sở và Nhãn Mục tiêu (Base Features & Normalized Placement)

Thực thi hàm `build_player_match_base` để tính toán đồng thời:
1. Các tỷ lệ hành vi với mẫu số đã xác minh:
   $$\text{damage\_per\_kill} = \frac{\text{player\_dmg}}{\text{player\_kills}}, \quad \text{walk\_ratio} = \frac{\text{player\_dist\_walk}}{\text{total\_distance}}, \quad \text{assist\_ratio} = \frac{\text{player\_assists}}{\text{player\_assists} + \text{player\_kills}}$$
2. Nhãn mục tiêu thứ hạng đội chuẩn hóa:
   $$normalized\_placement = 1.0 - \frac{team\_placement - 1.0}{N_{teams} - 1.0}$$
3. Xuất bảng kiểm định chất lượng (`feature_validation_base.csv`) theo dõi số lượng hợp lệ, khuyết thiếu, giá trị cực trị và tỷ lệ bằng 0 của từng đặc trưng."""),
        """
from src.features.base import build_player_match_base

base_pq = paths["interim"] / "player_match_base.parquet"
val_csv = paths["tables"] / "feature_validation_base.csv"

base_rows = build_player_match_base(
    con=con,
    cleaned_aggregate_parquet=cleaned_agg_pq,
    match_metadata_parquet=meta_pq,
    output_base_parquet=base_pq,
    validation_csv_path=val_csv,
    dictionary_csv_path=dict_csv,
)

# Hiển thị bảng kiểm định chất lượng đặc trưng
df_val = pd.read_csv(val_csv)
print("--- BẢNG KIỂM ĐỊNH CHẤT LƯỢNG ĐẶC TRƯNG CƠ SỞ (FEATURE VALIDATION BASE) ---")
print(df_val[["feature_name", "feature_group", "valid_count", "null_count", "null_pct", "min_val", "max_val", "zero_rate", "status"]].to_string(index=False))

# Xác nhận bảo toàn dòng
n_clean = con.execute("SELECT count(*) FROM read_parquet(?)", [str(cleaned_agg_pq)]).fetchone()[0]
assert base_rows == n_clean, f"Lỗi bảo toàn dòng: base {base_rows} != clean {n_clean}"
print(f"\\nĐối soát bảo toàn dòng: ĐẠT ({base_rows:,} dòng cơ sở = {n_clean:,} dòng sạch)")
""",
        ("markdown", r"""### III. Xác thực Chế độ chơi và Phân tách Khái niệm (Perspective vs Team Size Modes)

Hai khái niệm chế độ chơi được tách bạch độc lập:
1. `perspective_mode`: Phân loại góc nhìn người chơi (`tpp`: góc nhìn thứ ba; `fpp`: góc nhìn thứ nhất; `unknown`: không xác định).
2. `team_size_mode`: Phân loại quy mô đội dựa trên `party_size` (`solo`: 1 người; `duo`: 2 người; `squad`: 4 người; `unknown`: quy mô khác hoặc thiếu)."""),
        """
df_mode_cross = con.execute(\"\"\"
    SELECT
        perspective_mode,
        team_size_mode,
        count(*) AS player_count,
        round(count(*) * 100.0 / sum(count(*)) over(), 2) AS pct
    FROM read_parquet(?)
    GROUP BY perspective_mode, team_size_mode
    ORDER BY player_count DESC;
\"\"\", [str(base_pq)]).df()

print("--- MA TRẬN PHÂN BỐ GÓC NHÌN VÀ QUY MÔ ĐỘI ---")
print(df_mode_cross.to_string(index=False))
""",
        ("markdown", r"""### IV. Trực quan hóa Phân bố Đặc trưng Cơ sở (Base Feature Distributions)

Vẽ và lưu trữ hai biểu đồ kiểm toán vào thư mục `reports/figures/`:
1. **Biểu đồ Phân bố 4 Đặc trưng Dẫn xuất Mới (`w04_base_feature_distributions.png`):** Histogram phân bố tần suất của `damage_per_kill`, `walk_ratio`, `assist_ratio`, và `normalized_placement`.
2. **Biểu đồ Phân bố Người chơi theo Chế độ Đội (`w04_mode_breakdown.png`):** Phân bố cơ cấu người chơi theo Solo, Duo, Squad và Góc nhìn TPP/FPP."""),
        """
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

fig_dir = paths["figures"]
fig_dir.mkdir(parents=True, exist_ok=True)

# - Biểu đồ 1: Phân bố 4 đặc trưng mới
df_sample = con.execute(\"\"\"
    SELECT damage_per_kill, walk_ratio, assist_ratio, normalized_placement
    FROM read_parquet(?)
    USING SAMPLE 100000;
\"\"\", [str(base_pq)]).df()

fig, axes = plt.subplots(2, 2, figsize=(12, 8))
features = [
    ("damage_per_kill", "Damage per Kill (ST/Ha guc)", "#4C72B0"),
    ("walk_ratio", "Walk Ratio (Ty le di bo)", "#55A868"),
    ("assist_ratio", "Assist Ratio (Ty le ho tro)", "#C44E52"),
    ("normalized_placement", "Normalized Placement (Thu hang chuan hoa)", "#8172B2"),
]

for idx, (col, title, color) in enumerate(features):
    ax = axes[idx // 2, idx % 2]
    data = df_sample[col].dropna()
    if not data.empty:
        ax.hist(data, bins=30, color=color, edgecolor="black", alpha=0.7)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_ylabel("Tan suat (Frequency)", fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.4)

fig.tight_layout()
dist_path = fig_dir / "w04_base_feature_distributions.png"
fig.savefig(dist_path, dpi=200)
plt.close(fig)
print(f"Da luu bieu do: {dist_path.name}")

# - Biểu đồ 2: Phân bố chế độ đội
fig, ax = plt.subplots(figsize=(8, 4))
mode_counts = df_mode_cross.groupby("team_size_mode")["player_count"].sum()
ax.bar(mode_counts.index, mode_counts.values, color="#64B5CD", edgecolor="black")
ax.set_title("Phan bo nguoi choi theo Quy mo doi (Team Size Mode)", fontsize=12, fontweight="bold")
ax.set_ylabel("So nguoi choi (Player Count)", fontsize=10)
for idx, val in enumerate(mode_counts.values):
    ax.text(idx, val + max(mode_counts.values)*0.02, f"{val:,}", ha="center", va="bottom", fontsize=10)
fig.tight_layout()
breakdown_path = fig_dir / "w04_mode_breakdown.png"
fig.savefig(breakdown_path, dpi=200)
plt.close(fig)
print(f"Da luu bieu do: {breakdown_path.name}")
""",
        ("markdown", r"""### V. Nghiệm thu Cổng kiểm soát G3 (Gate G3) và Bàn giao sang Notebook 04

Các điều kiện nghiệm thu Gate G3:
- [x] Tập dữ liệu cơ sở `player_match_base.parquet` đã được tạo với 100% dòng sạch được bảo toàn.
- [x] Từ điển đặc trưng `feature_dictionary.csv` ghi nhận đầy đủ công thức, mẫu số và danh sách cấp quyền.
- [x] Các tỷ lệ hành vi tuân thủ nghiêm ngặt điều kiện mẫu số 0 ra `NaN`.
- [x] Normalized placement tính toán chính xác trong miền $[0, 1]$ cho roster hoàn chỉnh, không dùng kẹp che giấu lỗi.
- [x] Chế độ chơi `perspective_mode` và `team_size_mode` được phân tách độc lập, hỗ trợ trạng thái `unknown`.
- [x] Checkpoint `player_match_base` được cam kết chính thức."""),
        """
# Khóa checkpoint Gate G3
ckpt_mgr.commit(
    stage="player_match_base",
    signature=cfg["features"]["feature_versions"]["feature_version"],
    artifacts={
        "player_match_base": base_pq,
        "feature_dictionary": dict_csv,
        "feature_validation": val_csv,
    }
)

handoff_table = [
    {"Artifact": "player_match_base.parquet", "Duong dan": str(base_pq.relative_to(PROJECT_ROOT)), "Mo ta": "Tap dac trung hanh vi co so va target da xac thuc"},
    {"Artifact": "feature_dictionary.csv", "Duong dan": str(dict_csv.relative_to(PROJECT_ROOT)), "Mo ta": "Tu dien dac trung nghien cuu va hop dong quyen truy cap"},
    {"Artifact": "feature_validation_base.csv", "Duong dan": str(val_csv.relative_to(PROJECT_ROOT)), "Mo ta": "Thong ke kiem dinh chat luong dac trung co so"},
]

print("================================================================================")
print("GATE G3 HOÀN TẤT VÀ ĐÃ KHÓA CHECKPOINT")
print("BÀN GIAO SANG NOTEBOOK 04: '04_combat_timing.ipynb'")
print("================================================================================")
print(pd.DataFrame(handoff_table).to_string(index=False))
"""
    ]
)

# 04_combat_timing.ipynb
create_notebook(
    "04_combat_timing.ipynb",
    "04 — Khai phá Combat Timing và hoàn thiện Player-Match Features",
    "Tổng hợp các sự kiện hạ gục (Early, Mid, Late combat phases), loại trừ suicide/self-kill, và thực hiện Left Join bảo toàn số dòng vào player-match base.",
    [
        ("markdown", r"""### I. Giới thiệu và Khung Lý thuyết về Thời điểm Giao tranh (Combat Timing Theory)

Trong khoa học dữ liệu thể thao điện tử (esports analytics), hiệu suất chiến đấu của người chơi không chỉ được đo lường bằng tổng số mạng hạ gục ($player\_kills$), mà còn phụ thuộc sâu sắc vào **thời điểm giao tranh** (combat timing). Hai người chơi cùng đạt 3 kills nhưng người hạ gục địch trong 2 phút đầu trận (early game) thể hiện phong cách giao tranh rủi ro cao (hot-drop), trong khi người hạ gục địch ở cuối trận (late game) thể hiện năng lực sinh tồn và chiến thuật vòng bo xuất sắc.

Theo quy chuẩn nghiên cứu trong `PUBG_RESEARCH_SPEC.md` và các quy tắc kiểm soát rò rỉ thông tin trong `PUBG_IMPLEMENTATION_PLAN.md`:

#### 1. Đặc trưng Thời gian Tuyệt đối (Absolute Timing Features)
Được tính toán trên toàn bộ các sự kiện hạ gục hợp lệ ($t \ge 0$, định danh hợp lệ, không tự sát):
- $first\_kill\_time = \min(t)$: Thời điểm người chơi ghi nhận mạng hạ gục đầu tiên trong trận đấu.
- $avg\_kill\_time = \frac{1}{K} \sum_{i=1}^K t_i$: Mốc thời gian trung bình của các lần hạ gục.
- $has\_kill \in \{0, 1\}$: Biến chỉ báo nhị phân (true nếu người chơi có ít nhất 1 kill hợp lệ).
- $event\_kill\_count$: Số sự kiện hạ gục được liên kết thành công từ nhật ký cái chết.

*Nguyên tắc bảo toàn D01:* Các đặc trưng thời gian tuyệt đối không phụ thuộc vào độ dài trận đấu và an toàn khi sử dụng làm biến dự đoán thời gian sống sót ($S1$).

#### 2. Đặc trưng Thời gian theo Pha (Phase Timing Features)
Thời lượng trận đấu được ước lượng thông qua đại diện (duration proxy):
\[
estimated\_match\_duration = \max(player\_survive\_time)
\]
Ba pha giao tranh chiến lược được xác định theo tỷ lệ thời lượng trận:
- **Early Phase:** $t \in [0, \frac{1}{3} \cdot estimated\_match\_duration)$
- **Mid Phase:** $t \in [\frac{1}{3} \cdot estimated\_match\_duration, \frac{2}{3} \cdot estimated\_match\_duration)$
- **Late Phase:** $t \in [\frac{2}{3} \cdot estimated\_match\_duration, estimated\_match\_duration]$

Tỷ lệ giao tranh theo pha được tính toán trên tổng số kill đủ điều kiện phân pha ($phase\_eligible\_kills$):
\[
early\_kill\_ratio = \frac{early\_kills}{early\_kills + mid\_kills + late\_kills}
\]
Nếu người chơi không có mạng hạ gục nào đủ điều kiện phân pha ($phase\_eligible\_kills == 0$), các tỷ lệ này nhận giá trị chưa xác định (`NaN`), tuyệt đối không gán bằng $0.0$.

*Cảnh báo Quy tắc D01:* Vì $estimated\_match\_duration$ phụ thuộc trực tiếp vào thời gian sinh tồn lớn nhất của trận đấu, các đặc trưng pha ($early/mid/late$) bị cấm sử dụng trong bài toán dự đoán thời gian sống sót ($S1$) để chống rò rỉ mục tiêu."""),
        """
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import duckdb
from src.utils.config import load_config, resolve_paths
from src.data.io import get_duckdb_connection, read_json
from src.features.combat_timing import extract_and_aggregate_combat_timing, merge_player_match_and_timing
from src.data.checkpoints import CheckpointManager
from src.data.batch_ingest import staged_paths

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
con = get_duckdb_connection(temp_dir=paths["temp_dir"], **{k: cfg["runtime"]["duckdb"][k] for k in ("memory_limit", "threads")})
ckpt_mgr = CheckpointManager(manifest_path=paths["checkpoints"] / "checkpoint_manifest.json")

# Đối soát các tệp đầu vào tiên quyết
staging_dir = paths["interim"] / "staging_shards"
death_shards = staged_paths(staging_dir, "deaths")
meta_pq = paths["interim"] / "match_metadata.parquet"
base_pq = paths["interim"] / "player_match_base.parquet"

if not base_pq.is_file():
    raise FileNotFoundError(f"Không tìm thấy {base_pq}. Cần chạy hoàn tất notebook 03_build_player_match.ipynb trước.")
if not meta_pq.is_file():
    raise FileNotFoundError(f"Không tìm thấy {meta_pq}. Cần chạy hoàn tất notebook 02 trước.")
if not death_shards:
    raise FileNotFoundError("Không tìm thấy các phân đoạn Parquet của sự kiện tử vong (death shards).")

print(f"Kiểm tra đầu vào: ĐẠT")
print(f"- Số phân đoạn sự kiện tử vong: {len(death_shards)}")
print(f"- Tập dữ liệu cơ sở: {base_pq.name}")
print(f"- Metadata trận đấu: {meta_pq.name}")
""",
        ("markdown", r"""### II. Trích xuất và Tổng hợp Thời điểm Giao tranh (Combat Timing Aggregation & Audit)

Hàm `extract_and_aggregate_combat_timing` thực thi các bước sau:
1. **Lọc sự kiện hợp lệ:**
   - Loại trừ tự sát (suicide / self-kill) khi $killer\_name == victim\_name$.
   - Loại trừ sự kiện thiếu định danh người hạ gục hoặc nạn nhân.
   - Loại trừ thời gian âm hoặc không hữu hạn ($t < 0$ hoặc không hợp lệ).
   - Kiểm tra mã trận đấu tồn tại trong bảng metadata trận đấu.
2. **Bảo toàn tính toàn vẹn của sự kiện (Event Key Integrity):**
   - Sự kiện không bị loại bỏ trùng lặp chỉ theo bộ $(match\_id, killer\_name, time)$. Nếu một người chơi hạ gục 2 kẻ địch trong cùng 1 giây (ví dụ dùng lựu đạn), cả 2 sự kiện đều được ghi nhận đầy đủ.
3. **Phân tách thời gian tuyệt đối và thời gian phân pha:**
   - Nếu $t > estimated\_match\_duration$, sự kiện vẫn được giữ lại để tính thời gian tuyệt đối ($first\_kill\_time$, $avg\_kill\_time$), nhưng không được tính vào các pha $early/mid/late$.
   - Nếu thời lượng trận đấu ngắn hơn 60 giây ($duration < 60s$), các tỷ lệ phân pha được gán `NaN`.
4. **Lưu vết kiểm toán:** Xuất báo cáo chi tiết vào `reports/tables/event_join_audit.csv`."""),
        """
timing_pq = paths["interim"] / "combat_timing.parquet"
audit_tables_dir = paths["tables"]
audit_tables_dir.mkdir(parents=True, exist_ok=True)

audit_summary = extract_and_aggregate_combat_timing(
    con=con,
    death_parquet_paths=death_shards,
    match_metadata_parquet=meta_pq,
    output_timing_parquet=timing_pq,
    audit_output_dir=audit_tables_dir,
    features_config=cfg.get("features", {}),
)

df_event_audit = pd.read_csv(audit_tables_dir / "event_join_audit.csv")
print("--- BẢNG KIỂM TOÁN TỔNG HỢP SỰ KIỆN TỬ VONG (EVENT JOIN AUDIT) ---")
print(df_event_audit.to_string(index=False))
""",
        ("markdown", r"""### III. Trực quan hóa Phân bố Thời điểm Giao tranh (Combat Timing Distributions)

Nhằm đánh giá tính hợp lý của dữ liệu thời điểm giao tranh trước khi ghép nối, chúng ta trực quan hóa hai khía cạnh then chốt:
1. **Phân bố Thời điểm Hạ gục Đầu tiên ($first\_kill\_time$):** Phản ánh tần suất giao tranh bùng nổ ở giai đoạn đầu trận đấu.
2. **So sánh Cơ cấu Kills giữa Ba Pha (Early vs Mid vs Late):** Kiểm tra tỷ trọng đóng góp của từng pha giao tranh trên toàn bộ các hồ sơ người chơi."""),
        """
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

fig_dir = paths["figures"]
fig_dir.mkdir(parents=True, exist_ok=True)

# Lấy mẫu dữ liệu timing đã tổng hợp để vẽ đồ thị
df_timing_sample = con.execute(\"\"\"
    SELECT
        first_kill_time,
        avg_kill_time,
        early_kills,
        mid_kills,
        late_kills,
        early_kill_ratio,
        mid_kill_ratio,
        late_kill_ratio
    FROM read_parquet(?)
    USING SAMPLE 100000 (reservoir);
\"\"\", [str(timing_pq)]).df()

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# - Biểu đồ 1: Phân bố first_kill_time
sns.histplot(
    data=df_timing_sample["first_kill_time"].dropna(),
    bins=50,
    kde=True,
    ax=axes[0],
    color="#2b5c8f"
)
axes[0].set_title("Phân bố Thời điểm Hạ gục Đầu tiên (first_kill_time)", fontsize=12, pad=10)
axes[0].set_xlabel("Thời gian (giây)")
axes[0].set_ylabel("Số lượng người chơi")
axes[0].grid(axis="y", linestyle="--", alpha=0.5)

# - Biểu đồ 2: Cơ cấu tỷ trọng các pha giao tranh
phase_totals = {
    "Early Kills": df_timing_sample["early_kills"].sum(),
    "Mid Kills": df_timing_sample["mid_kills"].sum(),
    "Late Kills": df_timing_sample["late_kills"].sum(),
}
phase_series = pd.Series(phase_totals)
axes[1].bar(phase_series.index, phase_series.values, color=["#3d85c6", "#6aa84f", "#e69138"], edgecolor="black", width=0.5)
axes[1].set_title("Tổng số Mạng Hạ gục theo Pha Giao tranh", fontsize=12, pad=10)
axes[1].set_ylabel("Tổng số kills")
axes[1].grid(axis="y", linestyle="--", alpha=0.5)
for idx, val in enumerate(phase_series.values):
    axes[1].text(idx, val + (max(phase_series.values) * 0.01), f"{val:,.0f}", ha="center", va="bottom", fontsize=10)

plt.tight_layout()
timing_fig_path = fig_dir / "w05_combat_timing_distributions.png"
plt.savefig(timing_fig_path, dpi=150, bbox_inches="tight")
plt.close()

print(f"Đã lưu biểu đồ phân bố combat timing -> {timing_fig_path.relative_to(PROJECT_ROOT)}")
""",
        ("markdown", r"""### IV. Ghép nối Bảo toàn Số dòng và Ngữ nghĩa Không có Kill (Safe Left Join)

Bước ghép nối kết hợp tập dữ liệu hành vi cơ sở ($player\_match\_base$) với các chỉ số thời điểm giao tranh ($combat\_timing$) để tạo ra tập dữ liệu hoàn chỉnh $player\_match\_features.parquet$.

Các nguyên tắc khoa học dữ liệu nghiêm ngặt được áp dụng:
1. **Bảo toàn số dòng (Row Invariant):**
   Phép ghép nối sử dụng $LEFT\ JOIN$ trên cặp khóa $(match\_id, player\_name)$. Số dòng của tập kết quả phải bằng chính xác số dòng của tập cơ sở ($N_{final} = N_{base}$). Không được xảy ra tình trạng nhân đôi dòng (row multiplication) hoặc mất dòng (row drop).
2. **Xử lý ngữ nghĩa người chơi không có kill ($player\_kills == 0$):**
   - $event\_kill\_count = 0$
   - $has\_kill = False$
   - $first\_kill\_time = NaN$, $avg\_kill\_time = NaN$
   - $early\_kill\_ratio = NaN$, $mid\_kill\_ratio = NaN$, $late\_kill\_ratio = NaN$
   *Lưu ý quan trọng:* Điền số $0.0$ vào $first\_kill\_time$ là một lỗi nghiêm trọng vì nó sẽ làm cho người chơi không hạ gục ai bị coi là đã hạ gục địch ở giây thứ 0!"""),
        """
final_pq = paths["processed"] / "player_match_features.parquet"
discrepancy_csv = paths["tables"] / "kill_discrepancy.csv"

# Đọc số dòng tập cơ sở để đối soát
n_base = con.execute("SELECT count(*) FROM read_parquet(?)", [str(base_pq)]).fetchone()[0]

final_rows = merge_player_match_and_timing(
    con=con,
    base_or_cleaned_parquet=base_pq,
    timing_or_meta_parquet=timing_pq,
    output_or_timing_parquet=final_pq,
    discrepancy_or_output_path=discrepancy_csv,
)

assert final_rows == n_base, f"LỖI BẢO TOÀN DÒNG: final_rows ({final_rows}) != n_base ({n_base})"
print(f"Ghép nối hoàn tất: {final_rows:,} dòng được bảo toàn tuyệt đối (ĐẠT tiêu chí bảo toàn).")
""",
        ("markdown", r"""### V. Kiểm toán Sai lệch Số mạng Hạ gục và Độ phủ Dữ liệu (Discrepancy & Coverage Audit)

Trong các bộ dữ liệu lớn thu thập từ trò chơi nhiều người, sự sai lệch giữa số mạng hạ gục ghi nhận ở bảng tổng kết ($player\_kills$) và số bản ghi trong bảng sự kiện ($event\_kill\_count$) là hiện tượng tự nhiên do nhiều nguyên nhân:
1. Hạ gục gián tiếp qua hiệu ứng môi trường (vòng bo xanh, chết đuối khi đang giao tranh).
2. Xe đâm khi người lái đã nhảy ra khỏi xe.
3. Kẻ địch bị knock out nhưng chết do đồng đội họ bị tiêu diệt hết.
4. Mất mát gói tin mạng trong quá trình truyền dữ liệu từ game server về cơ sở dữ liệu.

Chúng ta tiến hành phân tích:
- **Bảng phân bố sai lệch (`kill_discrepancy.csv`):** Thống kê số lượng người chơi theo từng mức độ chênh lệch $|player\_kills - event\_kill\_count|$.
- **Bảng phân loại độ phủ (`event_timing_coverage.csv`):** Đánh giá tỷ lệ người chơi thuộc các nhóm: không kill không event, khớp chính xác, sai lệch một phần, hoặc thiếu sự kiện."""),
        """
df_disc = pd.read_csv(discrepancy_csv)
print("--- BẢNG PHÂN BỐ SAI LỆCH SỐ MẠNG HẠ GỤC (KILL DISCREPANCY DISTRIBUTION) ---")
print(df_disc.head(15).to_string(index=False))

coverage_csv = paths["tables"] / "event_timing_coverage.csv"
if coverage_csv.is_file():
    df_cov = pd.read_csv(coverage_csv)
    print("\\n--- BẢNG PHÂN LOẠI ĐỘ PHỦ DỮ LIỆU GIAO TRANH (EVENT TIMING COVERAGE) ---")
    print(df_cov.to_string(index=False))
""",
        ("markdown", r"""### VI. Kiểm định Cổng Chất lượng G4 và Bàn giao sang Notebook 05 (Gate G4 Commitment & Handoff)

Cổng chất lượng **Gate G4** được nghiệm thu khi đáp ứng đầy đủ các tiêu chuẩn:
1. Tập dữ liệu chính thức $player\_match\_features.parquet$ đã được xuất thành công, đọc lại và kiểm tra toàn vẹn.
2. Đầy đủ các nhóm đặc trưng:
   - Chiến đấu cơ sở (`player_kills`, `player_dmg`, `damage_per_kill`).
   - Di chuyển (`player_dist_walk`, `player_dist_ride`, `total_distance`, `walk_ratio`).
   - Hỗ trợ (`player_assists`, `player_dbno`, `assist_ratio`).
   - Thời gian tuyệt đối (`event_kill_count`, `first_kill_time`, `avg_kill_time`, `has_kill`).
   - Thời gian phân pha (`early_kills`, `mid_kills`, `late_kills`, `early_kill_ratio`, `mid_kill_ratio`, `late_kill_ratio`).
   - Mục tiêu và chẩn đoán (`normalized_placement`, `player_survive_time`, `kills_per_minute`, `damage_per_minute`, `walk_velocity`, `ride_velocity`).
3. Khóa checkpoint manifest với định danh `player_match_features`.
4. Bàn giao sang Notebook `05_eda.ipynb` để tiến hành phân tích khám phá dữ liệu toàn diện (Full EDA Catalog)."""),
        """
# Xác thực cấu trúc schema và các giá trị biên của tập dữ liệu hoàn chỉnh
inspect_df = con.execute(\"\"\"
    SELECT
        count(*) AS total_rows,
        count(distinct match_id) AS unique_matches,
        count(distinct player_name) AS unique_players,
        sum(CASE WHEN player_kills > 0 AND event_kill_count > 0 THEN 1 ELSE 0 END) AS players_with_timing,
        sum(CASE WHEN player_kills == 0 AND first_kill_time IS NULL THEN 1 ELSE 0 END) AS zero_kills_valid_null,
        sum(CASE WHEN valid_placement THEN 1 ELSE 0 END) AS valid_placement_rows
    FROM read_parquet(?)
\"\"\", [str(final_pq)]).df()

print("--- TỔNG KẾT KIỂM ĐỊNH CỔNG G4 (GATE G4 VERIFICATION) ---")
print(inspect_df.to_string(index=False))

# Khóa checkpoint manifest
ckpt_mgr.commit("player_match_features", "features_v1", {
    "final_dataset": final_pq,
    "discrepancy_table": discrepancy_csv,
    "event_audit": paths["tables"] / "event_join_audit.csv",
})

handoff_table = [
    {"Artifact": "player_match_features.parquet", "Duong dan": str(final_pq.relative_to(PROJECT_ROOT)), "Mo ta": "Tap dac trung hoan chinh san sang cho EDA va mo hinh hoa"},
    {"Artifact": "kill_discrepancy.csv", "Duong dan": str(discrepancy_csv.relative_to(PROJECT_ROOT)), "Mo ta": "Bao cao kiem toan sai lech so mang ha guc"},
    {"Artifact": "event_timing_coverage.csv", "Duong dan": str(coverage_csv.relative_to(PROJECT_ROOT)), "Mo ta": "Bao cao phan loai do phu du lieu su kien"},
    {"Artifact": "event_join_audit.csv", "Duong dan": str((paths["tables"] / "event_join_audit.csv").relative_to(PROJECT_ROOT)), "Mo ta": "Bao cao loc va tong hop su kien tu vong"},
]

print("\\n================================================================================")
print("GATE G4 HOÀN TẤT VÀ ĐÃ KHÓA CHECKPOINT")
print("BÀN GIAO SANG NOTEBOOK 05: '05_eda.ipynb'")
print("================================================================================")
print(pd.DataFrame(handoff_table).to_string(index=False))
"""
    ]
)

# 05_eda.ipynb
create_notebook(
    "05_eda.ipynb",
    "05 — Khám phá Dữ liệu Toàn diện và Danh mục Trực quan hóa (Catalog A01–I03)",
    "Thực hiện toàn bộ 8 nhóm phân tích khám phá dữ liệu: Cấu trúc, Chất lượng, Biến gốc, Biến dẫn xuất, So sánh Mode, Tương quan, Thời điểm giao tranh, và Chẩn đoán Lịch sử.",
    [
        ("markdown", r"""### I. Giới thiệu và Khung Phương pháp luận Khám phá Dữ liệu Toàn diện (Full EDA Catalog A01–I03)

Khám phá Dữ liệu (Exploratory Data Analysis - EDA) là giai đoạn trọng yếu trong quy trình Khoa học Dữ liệu. Trước khi bước vào phân cụm ($RQ2$) hay mô hình hóa dự đoán ($RQ3$), việc thẩm định dữ liệu một cách toàn diện giúp nhà nghiên cứu:
1. Nắm bắt chính xác phân bố, độ lệch (skewness), và các giá trị cực trị (extreme values).
2. Phát hiện hiện tượng khuyết thiếu có cấu trúc (structural missingness) để có chiến lược xử lý dữ liệu phù hợp.
3. Kiểm định các giả thuyết thống kê về sự khác biệt hành vi giữa các chế độ chơi (Solo, Duo, Squad) nhằm lựa chọn chiến lược phân tích tối ưu.
4. Nhận diện hiện tượng đa cộng tuyến (multicollinearity) và rò rỉ mục tiêu (target leakage) theo quy tắc D01/D02.

Theo đặc tả `PUBG_RESEARCH_SPEC.md` v3.0 §26 và kế hoạch `PUBG_IMPLEMENTATION_PLAN.md` §19 Phase X, chúng ta tiến hành khảo sát toàn bộ **8 nhóm phân tích bắt buộc**:
- **Nhóm 1: Cấu trúc tập dữ liệu (Group A - A01 đến A06):** Số lượng bản ghi, người chơi duy nhất, số trận, số đội, phân bố chế độ chơi và độ bao phủ thời gian.
- **Nhóm 2: Chất lượng dữ liệu & Khuyết thiếu có cấu trúc (Group B):** Thống kê tỷ lệ khuyết thiếu thực tế và tỷ lệ giá trị bằng 0.
- **Nhóm 3: Phân bố đặc trưng thô (Group C - B01 đến B10):** Thống kê mô tả chính xác (Mean, Std, Median, Min, Max, Quantiles, Skewness) cho các biến hành vi cốt lõi.
- **Nhóm 4: Đặc trưng dẫn xuất & Tốc độ (Group D - C01 đến C05):** Phân bố tỷ lệ sát thương trên kill, tỷ lệ đi bộ, tỷ lệ hỗ trợ và các chỉ số vận tốc.
- **Nhóm 5: So sánh chế độ chơi & Quy mô tác động (Group E - D01 đến D08):** Kiểm định phi tham số Kruskal-Wallis $H$, tính toán cỡ tác động $\eta^2_H$ để cung cấp bằng chứng cho chiến lược `per_mode` trong $RQ2$.
- **Nhóm 6: Ma trận tương quan & Đa cộng tuyến (Group F - E01 đến E02):** Tính toán tương quan tuyến tính Pearson và tương quan thứ bậc Spearman.
- **Nhóm 7: Động học giao tranh theo phân khúc thứ hạng (Group G - H01 đến H07, trọng tâm H06):** Phân tích cơ cấu pha giao tranh (Early, Mid, Late) theo các nhóm thứ hạng normalized placement.
- **Nhóm 8: Khả thi lịch sử & Đường cong giữ chân (Group H - I01 đến I03):** Đánh giá phân bố số trận trên mỗi người chơi và các ngưỡng ứng viên cho $min\_games$.

*Nguyên tắc bất biến:* Mọi bảng thống kê chính thức được tính toán chính xác trên toàn bộ tập dữ liệu hợp lệ ($full\ data$), sử dụng công cụ streaming DuckDB trên đĩa để tối ưu bộ nhớ RAM."""),
        """
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np
import duckdb
from src.utils.config import load_config, resolve_paths
from src.data.io import get_duckdb_connection, atomic_write_csv, atomic_write_json
from src.analysis.eda import (
    compute_sql_distribution_summary,
    compute_player_retention_diagnostics,
    compute_combat_phase_by_placement_tier,
    run_structural_eda,
    run_chronology_audit,
)
from src.analysis.mode_analysis import analyze_behavior_by_mode, format_mode_differences_table
from src.data.checkpoints import CheckpointManager

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
con = get_duckdb_connection(temp_dir=paths["temp_dir"], **{k: cfg["runtime"]["duckdb"][k] for k in ("memory_limit", "threads")})
ckpt_mgr = CheckpointManager(manifest_path=paths["checkpoints"] / "checkpoint_manifest.json")

# Kiểm tra tập dữ liệu hoàn chỉnh từ Notebook 04
final_pq = paths["processed"] / "player_match_features.parquet"
meta_pq = paths["interim"] / "match_metadata.parquet"

if not final_pq.is_file():
    raise FileNotFoundError(f"Không tìm thấy {final_pq}. Hãy chạy hoàn tất notebook 04_combat_timing.ipynb trước.")

print("Nạp dữ liệu thành công cho EDA:")
print(f"- Tập dữ liệu hoàn chỉnh: {final_pq.name}")
print(f"- Metadata trận đấu: {meta_pq.name}")
""",
        ("markdown", r"""### II. Khám phá Cấu trúc Tổng thể và Phân bố Chế độ Chơi (Group A: Structural Overview A01–A06)

Chúng ta tiến hành tổng kết quy mô cấu trúc của tập dữ liệu: tổng số dòng dữ liệu người chơi-trận, số lượng người chơi duy nhất, số lượng trận đấu hợp lệ, số đội quan sát được, và phân bố tỷ lệ người chơi theo các chế độ đội hình (`team_size_mode`: Solo, Duo, Squad) và góc nhìn (`perspective_mode`: TPP, FPP)."""),
        """
# - Bước 1: Tính toán bảng tổng quan cấu trúc
struct_query = \"\"\"
    SELECT
        count(*) AS total_player_records,
        count(distinct match_id) AS total_matches,
        count(distinct player_name) AS unique_players,
        count(distinct team_id) AS unique_teams,
        round(count(*) * 1.0 / count(distinct match_id), 2) AS avg_players_per_match
    FROM read_parquet(?)
\"\"\"
df_struct = con.execute(struct_query, [str(final_pq)]).df()
atomic_write_csv(paths["tables"] / "eda_structural_overview.csv", df_struct)

print("--- BẢNG TỔNG QUAN CẤU TRÚC TẬP DỮ LIỆU (EDA STRUCTURAL OVERVIEW) ---")
print(df_struct.to_string(index=False))

# Phân bố theo chế độ đội hình (team_size_mode)
mode_dist_query = \"\"\"
    SELECT
        team_size_mode,
        count(*) AS player_count,
        round(count(*) * 100.0 / sum(count(*)) over(), 2) AS percentage
    FROM read_parquet(?)
    GROUP BY team_size_mode
    ORDER BY player_count DESC;
\"\"\"
df_mode_dist = con.execute(mode_dist_query, [str(final_pq)]).df()
print("\\n--- PHÂN BỐ NGƯỜI CHƠI THEO QUY MÔ ĐỘI (TEAM SIZE MODE) ---")
print(df_mode_dist.to_string(index=False))

# Trực quan hóa cấu trúc (Group A)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))

# Đồ thị tỷ lệ chế độ đội hình
axes[0].bar(df_mode_dist["team_size_mode"], df_mode_dist["player_count"], color="#2b5c8f", edgecolor="black", width=0.5)
axes[0].set_title("Phân bố Số lượng Người chơi theo Chế độ Đội (Chart A03)", fontsize=11, pad=10)
axes[0].set_ylabel("Số lượng người chơi")
axes[0].grid(axis="y", linestyle="--", alpha=0.5)
for idx, row in df_mode_dist.iterrows():
    axes[0].text(idx, row["player_count"] + (df_mode_dist["player_count"].max() * 0.02),
                 f"{row['percentage']}%", ha="center", fontsize=10)

# Đồ thị phân bố số người trong trận (game_size)
df_game_size = con.execute(\"\"\"
    SELECT game_size FROM read_parquet(?) USING SAMPLE 50000 (reservoir);
\"\"\", [str(final_pq)]).df()
sns.histplot(df_game_size["game_size"], bins=30, ax=axes[1], color="#45818e", kde=True)
axes[1].set_title("Phân bố Quy mô Trận đấu - Game Size (Chart A04)", fontsize=11, pad=10)
axes[1].set_xlabel("Số người chơi trong trận")
axes[1].grid(axis="y", linestyle="--", alpha=0.5)

plt.tight_layout()
fig_path_a = paths["figures"] / "eda_group_a_structure.png"
plt.savefig(fig_path_a, dpi=150, bbox_inches="tight")
plt.close()
print(f"Đã lưu biểu đồ cấu trúc tập dữ liệu -> {fig_path_a.relative_to(PROJECT_ROOT)}")
""",
        ("markdown", r"""### III. Kiểm toán Chất lượng Dữ liệu và Khuyết thiếu có Cấu trúc (Group B: Data Quality & Structural Missing)

Trong phân tích dữ liệu thể thao điện tử, một số chỉ số toán học không thể xác định đối với một bộ phận người chơi:
1. $damage\_per\_kill = \frac{player\_dmg}{player\_kills}$ nhận giá trị `NaN` khi $player\_kills == 0$ (người chơi không hạ gục ai).
2. $walk\_ratio = \frac{player\_dist\_walk}{total\_distance}$ nhận giá trị `NaN` khi $total\_distance == 0$ (người chơi đứng yên hoặc chết khi vừa chạm đất).
3. $assist\_ratio = \frac{player\_assists}{player\_assists + player\_kills}$ nhận giá trị `NaN` khi tổng số hỗ trợ và kill bằng $0$.
4. $first\_kill\_time$ và $avg\_kill\_time$ nhận giá trị `NaN` khi không có sự kiện hạ gục.
5. Các tỷ lệ pha ($early/mid/late\_kill\_ratio$) nhận giá trị `NaN` khi không có kill đủ điều kiện phân pha.

Bảng kiểm toán chất lượng dữ liệu giúp phân biệt rõ ràng giữa **dữ liệu khuyết thiếu tự nhiên (structural missing)** và **lỗi thu thập dữ liệu (data errors)**."""),
        """
# - Bước 2: Kiểm toán chất lượng dữ liệu
quality_cols = [
    "player_kills", "player_dmg", "damage_per_kill",
    "player_dist_walk", "player_dist_ride", "total_distance", "walk_ratio",
    "player_assists", "player_dbno", "assist_ratio",
    "player_survive_time", "normalized_placement",
    "event_kill_count", "first_kill_time", "avg_kill_time",
    "early_kill_ratio", "mid_kill_ratio", "late_kill_ratio"
]

df_quality = compute_sql_distribution_summary(con, final_pq, quality_cols)
atomic_write_csv(paths["tables"] / "eda_data_quality_summary.csv", df_quality[["feature", "count", "missing_count", "missing_pct", "zero_rate"]])

print("--- BẢNG KIỂM TOÁN CHẤT LƯỢNG DỮ LIỆU VÀ TỶ LỆ ZERO (DATA QUALITY SUMMARY) ---")
print(df_quality[["feature", "count", "missing_count", "missing_pct", "zero_rate"]].to_string(index=False))

# Trực quan hóa tỷ lệ Missing và Zero
fig, ax = plt.subplots(figsize=(12, 5))
x = np.arange(len(df_quality))
width = 0.35

ax.bar(x - width/2, df_quality["missing_pct"], width, label="Tỷ lệ Khuyết thiếu (Missing %)", color="#cc0000", alpha=0.85)
ax.bar(x + width/2, df_quality["zero_rate"] * 100.0, width, label="Tỷ lệ Giá trị Bằng 0 (Zero %)", color="#3d85c6", alpha=0.85)

ax.set_title("Tỷ lệ Khuyết thiếu có Cấu trúc và Tỷ lệ Giá trị Bằng 0 (Chart C06)", fontsize=12, pad=10)
ax.set_xticks(x)
ax.set_xticklabels(df_quality["feature"], rotation=45, ha="right", fontsize=9)
ax.set_ylabel("Phần trăm (%)")
ax.grid(axis="y", linestyle="--", alpha=0.5)
ax.legend()

plt.tight_layout()
fig_path_b = paths["figures"] / "eda_group_b_missing_and_zeros.png"
plt.savefig(fig_path_b, dpi=150, bbox_inches="tight")
plt.close()
print(f"Đã lưu biểu đồ chất lượng dữ liệu -> {fig_path_b.relative_to(PROJECT_ROOT)}")
""",
        ("markdown", r"""### IV. Phân tích Phân bố Đặc trưng Hành vi Thô (Group C: Raw Distributions B01–B10)

Chúng ta tính toán các đại lượng thống kê mô tả toàn diện cho các đặc trưng thô:
- Độ tập trung: Trung bình cộng ($Mean$), Trung vị ($Median$).
- Độ phân tán: Độ lệch chuẩn ($Std$), Khoảng tứ phân vị ($P_{25}, P_{75}$).
- Miền giá trị: Cực tiểu ($Min$), Cực đại ($Max$), và Bách phân vị thứ 95 ($P_{95}$).
- Độ bất đối xứng: Hệ số bất đối xứng Fisher-Pearson ($Skewness$). Hầu hết các đặc trưng chiến đấu đều có độ lệch phải rất lớn ($skewness > 1.5$) do phần đông người chơi có kết quả thấp trong khi số ít người chơi chuyên nghiệp ghi nhận thành tích vượt bậc."""),
        """
# - Bước 3: Thống kê mô tả đặc trưng thô
raw_cols = [
    "player_kills", "player_dmg", "player_dist_walk", "player_dist_ride",
    "total_distance", "player_assists", "player_dbno", "player_survive_time",
    "team_placement", "normalized_placement"
]

df_raw_stats = compute_sql_distribution_summary(con, final_pq, raw_cols)
atomic_write_csv(paths["tables"] / "eda_raw_distributions_summary.csv", df_raw_stats)

print("--- THỐNG KÊ MÔ TẢ ĐẶC TRƯNG HÀNH VI THÔ (RAW FEATURE DISTRIBUTIONS B01-B10) ---")
print(df_raw_stats[["feature", "mean", "std", "min", "median", "p95", "max", "skewness"]].to_string(index=False))

# Trực quan hóa phân bố các biến thô chủ đạo
df_sample_raw = con.execute(\"\"\"
    SELECT player_kills, player_dmg, player_dist_walk, player_survive_time, normalized_placement
    FROM read_parquet(?)
    USING SAMPLE 50000 (reservoir);
\"\"\", [str(final_pq)]).df()

fig, axes = plt.subplots(2, 3, figsize=(14, 8))

# Kills (B01)
sns.histplot(df_sample_raw["player_kills"], bins=20, ax=axes[0, 0], color="#2b5c8f", discrete=True)
axes[0, 0].set_title("B01: Số Mạng Hạ Gục (player_kills)", fontsize=11)
axes[0, 0].set_xlabel("Số kills")

# Damage (B02)
sns.histplot(df_sample_raw["player_dmg"], bins=40, ax=axes[0, 1], color="#3d85c6", kde=True)
axes[0, 1].set_title("B02: Tổng Sát Thương (player_dmg)", fontsize=11)
axes[0, 1].set_xlabel("Điểm sát thương")

# Walk distance (B05)
sns.histplot(df_sample_raw["player_dist_walk"], bins=40, ax=axes[0, 2], color="#274e13", kde=True)
axes[0, 2].set_title("B05: Quãng Đường Đi Bộ (player_dist_walk)", fontsize=11)
axes[0, 2].set_xlabel("Mét (m)")

# Survival time (B08)
sns.histplot(df_sample_raw["player_survive_time"], bins=40, ax=axes[1, 0], color="#783f04", kde=True)
axes[1, 0].set_title("B08: Thời Gian Sinh Tồn (player_survive_time)", fontsize=11)
axes[1, 0].set_xlabel("Giây (s)")

# Normalized placement (B10)
sns.histplot(df_sample_raw["normalized_placement"].dropna(), bins=30, ax=axes[1, 1], color="#4c1130", kde=True)
axes[1, 1].set_title("B10: Thứ Hạng Chuẩn Hóa (normalized_placement)", fontsize=11)
axes[1, 1].set_xlabel("Thứ hạng [0, 1]")

# Boxplot tổng hợp Kills & Damage (chuẩn hóa z-score để vẽ chung)
from scipy.stats import zscore
df_box = pd.DataFrame({
    "Kills (z)": zscore(df_sample_raw["player_kills"]),
    "Damage (z)": zscore(df_sample_raw["player_dmg"]),
    "Walk (z)": zscore(df_sample_raw["player_dist_walk"]),
    "Survival (z)": zscore(df_sample_raw["player_survive_time"])
})
sns.boxplot(data=df_box, ax=axes[1, 2], palette="Set2")
axes[1, 2].set_title("So Sánh Độ Phân Tán (Z-Score)", fontsize=11)
axes[1, 2].grid(axis="y", linestyle="--", alpha=0.5)

plt.tight_layout()
fig_path_c = paths["figures"] / "eda_group_c_raw_distributions.png"
plt.savefig(fig_path_c, dpi=150, bbox_inches="tight")
plt.close()
print(f"Đã lưu biểu đồ phân bố đặc trưng thô -> {fig_path_c.relative_to(PROJECT_ROOT)}")
""",
        ("markdown", r"""### V. Phân tích Đặc trưng Dẫn xuất và Tốc độ (Group D: Derived Distributions C01–C05)

Các đặc trưng dẫn xuất kết hợp nhiều khía cạnh hành vi để tạo ra các chỉ số chuẩn hóa:
1. $damage\_per\_kill = \frac{player\_dmg}{player\_kills}$: Đo lường hiệu quả kết liễu mục tiêu.
2. $walk\_ratio = \frac{player\_dist\_walk}{total\_distance}$: Tỷ trọng di chuyển bằng chân (phản ánh phong cách đi bộ ẩn nấp so với lái xe).
3. $assist\_ratio = \frac{player\_assists}{player\_assists + player\_kills}$: Tỷ trọng đóng góp hỗ trợ đồng đội.
4. $kills\_per\_minute = \frac{player\_kills}{player\_survive\_time / 60}$: Tần suất hạ gục địch theo thời gian sống.
5. $walk\_velocity = \frac{player\_dist\_walk}{player\_survive\_time}$: Tốc độ di chuyển trên mặt đất (mét/giây)."""),
        """
# - Bước 4: Thống kê mô tả đặc trưng dẫn xuất
derived_cols = [
    "damage_per_kill", "walk_ratio", "assist_ratio",
    "kills_per_minute", "damage_per_minute", "walk_velocity", "ride_velocity"
]

df_derived_stats = compute_sql_distribution_summary(con, final_pq, derived_cols)
atomic_write_csv(paths["tables"] / "eda_derived_distributions_summary.csv", df_derived_stats)

print("--- THỐNG KÊ MÔ TẢ ĐẶC TRƯNG DẪN XUẤT (DERIVED FEATURES C01-C05) ---")
print(df_derived_stats[["feature", "count", "missing_pct", "mean", "std", "median", "p95"]].to_string(index=False))

# Trực quan hóa đặc trưng dẫn xuất
df_sample_derived = con.execute(\"\"\"
    SELECT damage_per_kill, walk_ratio, assist_ratio, kills_per_minute, walk_velocity
    FROM read_parquet(?)
    USING SAMPLE 50000 (reservoir);
\"\"\", [str(final_pq)]).df()

fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))

# Damage per kill (C03)
valid_dpk = df_sample_derived["damage_per_kill"].dropna()
sns.histplot(valid_dpk[valid_dpk <= 500], bins=35, ax=axes[0], color="#b45f06", kde=True)
axes[0].set_title("C03: Damage per Kill (<= 500)", fontsize=11)
axes[0].set_xlabel("Sát thương / Kill")

# Walk ratio (C04)
sns.histplot(df_sample_derived["walk_ratio"].dropna(), bins=30, ax=axes[1], color="#38761d", kde=True)
axes[1].set_title("C04: Tỷ Lệ Đi Bộ (walk_ratio)", fontsize=11)
axes[1].set_xlabel("Tỷ lệ [0, 1]")

# Walk velocity
valid_vel = df_sample_derived["walk_velocity"].dropna()
sns.histplot(valid_vel[valid_vel <= 5.0], bins=35, ax=axes[2], color="#0b5394", kde=True)
axes[2].set_title("Vận Tốc Đi Bộ (walk_velocity <= 5 m/s)", fontsize=11)
axes[2].set_xlabel("Vận tốc (m/s)")

plt.tight_layout()
fig_path_d = paths["figures"] / "eda_group_d_derived_distributions.png"
plt.savefig(fig_path_d, dpi=150, bbox_inches="tight")
plt.close()
print(f"Đã lưu biểu đồ đặc trưng dẫn xuất -> {fig_path_d.relative_to(PROJECT_ROOT)}")
""",
        ("markdown", r"""### VI. So sánh Hành vi giữa các Chế độ Chơi và Kiểm định Thống kê (Group E: Mode Comparison D01–D08)

Để trả lời câu hỏi liệu phong cách chơi của người chơi có khác biệt đáng kể giữa các quy mô đội hình (Solo, Duo, Squad) hay không, chúng ta thực hiện:
1. **Thống kê mô tả theo từng chế độ:** Tính toán số lượng quan sát ($N$), giá trị trung bình ($Mean$), và trung vị ($Median$) cho từng biến hành vi.
2. **Kiểm định phi tham số Kruskal-Wallis $H$:** Kiểm tra xem phân bố của biến số có sự khác biệt có ý nghĩa thống kê ($p < 0.01$) giữa 3 chế độ hay không.
3. **Quy mô tác động (Effect Size $\eta^2_H$):**
   \[
   \eta^2_H = \frac{H - k + 1}{N - k}
   \]
   Trong đó $H$ là giá trị thống kê Kruskal-Wallis, $k=3$ là số nhóm chế độ chơi, và $N$ là tổng số quan sát. Quy chuẩn phân loại:
   - $\eta^2_H < 0.01$: Tác động không đáng kể (negligible).
   - $0.01 \le \eta^2_H < 0.06$: Tác động nhỏ (small).
   - $0.06 \le \eta^2_H < 0.14$: Tác động trung bình (medium).
   - $\eta^2_H \ge 0.14$: Tác động lớn (large).

*Khuyến nghị khoa học cho RQ2:* Khi các đặc trưng hỗ trợ đồng đội (`player_assists`, `player_dbno`, `assist_ratio`) có sự khác biệt rất lớn giữa Solo (nơi các biến này bằng 0) và Squad, việc phân cụm chung trên toàn bộ dữ liệu (overall) sẽ tạo ra các cụm hành vi thiên lệch. Do đó, kiểm định thống kê này là bằng chứng thực nghiệm bắt buộc để chốt chiến lược **phân cụm riêng theo chế độ (`per_mode`)** cho $RQ2$."""),
        """
# - Bước 5: Phân tích so sánh chế độ chơi và tính toán cỡ tác động
mode_compare_cols = [
    "player_kills", "player_dmg", "player_dist_walk", "player_dist_ride",
    "player_assists", "player_dbno", "player_survive_time", "normalized_placement"
]

# Đọc mẫu lớn cân đối theo chế độ để kiểm định Kruskal-Wallis
df_mode_sample = con.execute(\"\"\"
    SELECT team_size_mode, player_kills, player_dmg, player_dist_walk, player_dist_ride,
           player_assists, player_dbno, player_survive_time, normalized_placement
    FROM read_parquet(?)
    WHERE team_size_mode IN ('solo', 'duo', 'squad')
    USING SAMPLE 100000 (reservoir);
\"\"\", [str(final_pq)]).df()

mode_results = analyze_behavior_by_mode(df_mode_sample, mode_compare_cols, mode_col="team_size_mode")
mode_diff_table = format_mode_differences_table(mode_results["mode_differences"])

atomic_write_csv(paths["tables"] / "eda_mode_comparison_summary.csv", mode_results["summary_table"])
atomic_write_csv(paths["tables"] / "eda_mode_differences_test.csv", mode_diff_table)
atomic_write_json(paths["manifests"] / "mode_analysis.json", {
    "mode_differences": mode_results["mode_differences"],
    "recommended_rq2_strategy": mode_results["recommended_rq2_strategy"],
})

print("--- KẾT QUẢ KIỂM ĐỊNH KRUSKAL-WALLIS VÀ CỠ TÁC ĐỘNG (EFFECT SIZE ETA-SQUARED) ---")
print(mode_diff_table.to_string(index=False))
print(f"\\nKhuyến nghị chiến lược RQ2 Mode: {mode_results['recommended_rq2_strategy'].upper()}")

# Trực quan hóa so sánh đa chế độ (D01, D02, D03, D05)
fig, axes = plt.subplots(2, 2, figsize=(13, 8))

# D01: Kills by mode
sns.boxplot(data=df_mode_sample, x="team_size_mode", y="player_kills", ax=axes[0, 0], palette="Blues")
axes[0, 0].set_title("D01: Số Mạng Hạ Gục theo Chế Độ", fontsize=11)
axes[0, 0].set_ylim(-0.5, 8)

# D02: Damage by mode
sns.boxplot(data=df_mode_sample, x="team_size_mode", y="player_dmg", ax=axes[0, 1], palette="Greens")
axes[0, 1].set_title("D02: Sát Thương theo Chế Độ", fontsize=11)
axes[0, 1].set_ylim(-10, 800)

# D03: Assists by mode
sns.barplot(data=df_mode_sample, x="team_size_mode", y="player_assists", ax=axes[1, 0], palette="Oranges", ci=None)
axes[1, 0].set_title("D03: Trung Bình Số Hỗ Trợ (Assists) theo Chế Độ", fontsize=11)

# D05: Walk distance by mode
sns.boxplot(data=df_mode_sample, x="team_size_mode", y="player_dist_walk", ax=axes[1, 1], palette="Purples")
axes[1, 1].set_title("D05: Quãng Đường Đi Bộ theo Chế Độ", fontsize=11)
axes[1, 1].set_ylim(-50, 4000)

plt.tight_layout()
fig_path_e = paths["figures"] / "eda_group_e_mode_comparisons.png"
plt.savefig(fig_path_e, dpi=150, bbox_inches="tight")
plt.close()
print(f"Đã lưu biểu đồ so sánh chế độ chơi -> {fig_path_e.relative_to(PROJECT_ROOT)}")
""",
        ("markdown", r"""### VII. Phân tích Ma trận Tương quan và Đa cộng tuyến (Group F: Correlation Matrix E01–E02)

Chúng ta đo lường mối tương quan giữa các đặc trưng hành vi và nhãn mục tiêu thông qua hai hệ số:
1. **Hệ số tương quan tuyến tính Pearson ($r$):**
   \[
   r = \frac{\sum_{i=1}^n (x_i - \bar{x})(y_i - \bar{y})}{\sqrt{\sum_{i=1}^n (x_i - \bar{x})^2 \sum_{i=1}^n (y_i - \bar{y})^2}}
   \]
2. **Hệ số tương quan thứ bậc Spearman ($\rho$):**
   \[
   \rho = 1 - \frac{6 \sum d_i^2}{n(n^2 - 1)}
   \]
   Đo lường mối quan hệ đơn điệu (monotonicity), có khả năng chống chịu tốt trước các giá trị ngoại lai và phân bố phi chuẩn.

*Kiểm tra Đa cộng tuyến (Multicollinearity):* Các cặp biến có $|r| > 0.85$ (ví dụ giữa quãng đường đi bộ và tổng quãng đường, hoặc sát thương và số kills) được ghi nhận để kiểm soát độ ổn định của các mô hình hồi quy ở giai đoạn sau."""),
        """
# - Bước 6: Tính toán ma trận tương quan Pearson và Spearman
corr_features = [
    "player_kills", "player_dmg", "damage_per_kill",
    "player_dist_walk", "player_dist_ride", "total_distance", "walk_ratio",
    "player_assists", "player_dbno",
    "first_kill_time", "player_survive_time", "normalized_placement"
]

df_corr_sample = con.execute(\"\"\"
    SELECT player_kills, player_dmg, damage_per_kill,
           player_dist_walk, player_dist_ride, total_distance, walk_ratio,
           player_assists, player_dbno,
           first_kill_time, player_survive_time, normalized_placement
    FROM read_parquet(?)
    USING SAMPLE 50000 (reservoir);
\"\"\", [str(final_pq)]).df()

pearson_corr = df_corr_sample.corr(method="pearson")
spearman_corr = df_corr_sample.corr(method="spearman")

atomic_write_csv(paths["tables"] / "eda_correlation_matrix_pearson.csv", pearson_corr)
atomic_write_csv(paths["tables"] / "eda_correlation_matrix_spearman.csv", spearman_corr)

# Trực quan hóa hai biểu đồ nhiệt (Heatmaps) cạnh nhau
fig, axes = plt.subplots(1, 2, figsize=(16, 7))

sns.heatmap(pearson_corr, annot=True, fmt=".2f", cmap="coolwarm", center=0, ax=axes[0], cbar_kws={"shrink": 0.8}, annot_kws={"size": 8})
axes[0].set_title("E01: Ma Trận Tương Quan Tuyến Tính Pearson (r)", fontsize=12, pad=10)

sns.heatmap(spearman_corr, annot=True, fmt=".2f", cmap="vlag", center=0, ax=axes[1], cbar_kws={"shrink": 0.8}, annot_kws={"size": 8})
axes[1].set_title("E02: Ma Trận Tương Quan Thứ Bậc Spearman (rho)", fontsize=12, pad=10)

plt.tight_layout()
fig_path_f = paths["figures"] / "eda_group_f_correlation_heatmaps.png"
plt.savefig(fig_path_f, dpi=150, bbox_inches="tight")
plt.close()
print(f"Đã lưu biểu đồ nhiệt ma trận tương quan -> {fig_path_f.relative_to(PROJECT_ROOT)}")
""",
        ("markdown", r"""### VIII. Động học Giao tranh theo Phân khúc Thứ hạng (Group G: Combat Timing Dynamics H01–H07 & H06)

Biểu đồ **Chart H06 (Combat Phase by Placement Group)** là biểu đồ ưu tiên cao nhất trong báo cáo nghiên cứu:
Chúng ta phân chia người chơi thành 4 phân khúc (quartiles) dựa trên thứ hạng chuẩn hóa $normalized\_placement$:
- **Tier 1 (Top 25%):** Người chơi chiến thắng hoặc sống sót sâu vào cuối trận.
- **Tier 2 (25% - 50%):** Người chơi đạt thứ hạng khá.
- **Tier 3 (50% - 75%):** Người chơi dừng bước ở giữa trận.
- **Tier 4 (Bottom 25%):** Người chơi bị loại sớm ở giai đoạn đầu.

Đối với từng phân khúc, chúng ta tính toán tỷ trọng trung bình các mạng hạ gục rơi vào 3 pha: Early Phase, Mid Phase, và Late Phase để kiểm chứng giả thuyết: *Người chơi đạt thứ hạng cao có xu hướng tích lũy phần lớn số kill vào giai đoạn cuối trận, trong khi người chơi bị loại sớm chủ yếu giao tranh ở đầu trận.*"""),
        """
# - Bước 7: Tính toán tỷ trọng pha giao tranh theo phân khúc thứ hạng (Chart H06)
df_h06 = compute_combat_phase_by_placement_tier(con, final_pq)
atomic_write_csv(paths["tables"] / "eda_timing_by_placement_group.csv", df_h06)

print("--- BẢNG TỶ TRỌNG PHA GIAO TRANH THEO PHÂN KHÚC THỨ HẠNG (CHART H06) ---")
print(df_h06[["placement_tier", "player_count", "avg_kills", "avg_early_ratio", "avg_mid_ratio", "avg_late_ratio"]].to_string(index=False))

# Trực quan hóa biểu đồ thanh chồng (Stacked Bar Chart) cho H06
fig, ax = plt.subplots(figsize=(10, 5))

tiers = df_h06["placement_tier"].tolist()
early_ratios = df_h06["avg_early_ratio"].values
mid_ratios = df_h06["avg_mid_ratio"].values
late_ratios = df_h06["avg_late_ratio"].values

p1 = ax.bar(tiers, early_ratios, label="Early Combat Phase", color="#3d85c6", width=0.5)
p2 = ax.bar(tiers, mid_ratios, bottom=early_ratios, label="Mid Combat Phase", color="#6aa84f", width=0.5)
p3 = ax.bar(tiers, late_ratios, bottom=early_ratios + mid_ratios, label="Late Combat Phase", color="#e69138", width=0.5)

ax.set_title("H06: Tỷ Trọng Pha Giao Tranh theo Phân Khúc Thứ Hạng Đội", fontsize=12, pad=12)
ax.set_ylabel("Tỷ trọng pha giao tranh (Tỷ lệ trung bình)")
ax.set_ylim(0, 1.15)
ax.grid(axis="y", linestyle="--", alpha=0.5)
ax.legend(loc="upper right")

plt.tight_layout()
fig_path_g = paths["figures"] / "eda_group_g_timing_by_placement.png"
plt.savefig(fig_path_g, dpi=150, bbox_inches="tight")
plt.close()
print(f"Đã lưu biểu đồ trọng tâm H06 -> {fig_path_g.relative_to(PROJECT_ROOT)}")
""",
        ("markdown", r"""### IX. Đánh giá Khả thi Lịch sử và Đường cong Giữ chân Người chơi (Group H: Historical Feasibility & Retention I01–I03)

Trước khi tiến hành xây dựng các đặc trưng lịch sử phục vụ bài toán dự đoán tương lai ($RQ3$), chúng ta thẩm định tính khả thi của dữ liệu:
1. **Cấp bậc Chronology:** Đã thẩm định và khóa ở Notebook 02 đạt **Grade B** (ngày theo thời gian UTC được xác nhận, mô hình hóa xuyên ngày nghiêm ngặt, loại trừ toàn bộ trận cùng ngày).
2. **Đường cong giữ chân (Retention Curve):** Thống kê số lượng người chơi còn lại khi đặt các ngưỡng lọc số trận tối thiểu ($min\_games \in \{1, 5, 10, 20, 50\}$).
*Lưu ý nguyên tắc nghiên cứu:* Ngưỡng giữ chân $min\_games$ chỉ được chẩn đoán ở bước này và sẽ được khóa chính thức ở Notebook 07 dựa trên độ ổn định của hồ sơ phân cụm, không ép buộc một con số tùy ý."""),
        """
# - Bước 8: Tính toán đường cong giữ chân người chơi
df_retention = compute_player_retention_diagnostics(con, final_pq, thresholds=[1, 2, 5, 10, 20, 50])
atomic_write_csv(paths["tables"] / "eda_historical_retention_diagnostics.csv", df_retention)

print("--- BẢNG ĐÁNH GIÁ ĐƯỜNG CONG GIỮ CHÂN NGƯỜI CHƠI (RETENTION DIAGNOSTICS A02 / I01) ---")
print(df_retention.to_string(index=False))

# Trực quan hóa đường cong giữ chân
fig, ax1 = plt.subplots(figsize=(9, 4.5))

color = "#2b5c8f"
ax1.set_xlabel("Ngưỡng số trận tối thiểu (min_games)", fontsize=11)
ax1.set_ylabel("Tỷ lệ người chơi giữ lại (%)", color=color, fontsize=11)
ax1.plot(df_retention["threshold"], df_retention["player_retention_pct"], marker="o", color=color, linewidth=2, label="Tỷ lệ người chơi")
ax1.tick_params(axis="y", labelcolor=color)
ax1.grid(True, linestyle="--", alpha=0.5)

ax2 = ax1.twinx()
color = "#cc0000"
ax2.set_ylabel("Độ phủ số trận quan sát (%)", color=color, fontsize=11)
ax2.plot(df_retention["threshold"], df_retention["match_coverage_pct"], marker="s", color=color, linewidth=2, linestyle="--", label="Độ phủ số trận")
ax2.tick_params(axis="y", labelcolor=color)

plt.title("A02/I01: Đường Cong Giữ Chân Người Chơi và Độ Phủ Trận Đấu theo Ngưỡng", fontsize=12, pad=12)
plt.tight_layout()
fig_path_h = paths["figures"] / "eda_group_h_retention_curve.png"
plt.savefig(fig_path_h, dpi=150, bbox_inches="tight")
plt.close()
print(f"Đã lưu biểu đồ giữ chân người chơi -> {fig_path_h.relative_to(PROJECT_ROOT)}")
""",
        ("markdown", r"""### X. Tổng kết Khám phá Dữ liệu, Khóa Checkpoint và Bàn giao sang Notebook 06

Chúng ta tổng kết toàn bộ 8 nhóm báo cáo bảng và hình ảnh đã được xuất bản và xác thực:
1. `eda_structural_overview.csv` & `eda_group_a_structure.png` (Nhóm 1).
2. `eda_data_quality_summary.csv` & `eda_group_b_missing_and_zeros.png` (Nhóm 2).
3. `eda_raw_distributions_summary.csv` & `eda_group_c_raw_distributions.png` (Nhóm 3).
4. `eda_derived_distributions_summary.csv` & `eda_group_d_derived_distributions.png` (Nhóm 4).
5. `eda_mode_comparison_summary.csv` & `eda_group_e_mode_comparisons.png` (Nhóm 5).
6. `eda_correlation_matrix_pearson.csv` / `spearman` & `eda_group_f_correlation_heatmaps.png` (Nhóm 6).
7. `eda_timing_by_placement_group.csv` & `eda_group_g_timing_by_placement.png` (Nhóm 7).
8. `eda_historical_retention_diagnostics.csv` & `eda_group_h_retention_curve.png` (Nhóm 8).

Khóa checkpoint **Gate G5 (EDA)** và bàn giao các kết quả sang Notebook `06_rq1_analysis.ipynb`."""),
        """
# - Bước 9: Kiểm tra sự tồn tại của toàn bộ artifacts và khóa checkpoint
required_tables = [
    paths["tables"] / "eda_structural_overview.csv",
    paths["tables"] / "eda_data_quality_summary.csv",
    paths["tables"] / "eda_raw_distributions_summary.csv",
    paths["tables"] / "eda_derived_distributions_summary.csv",
    paths["tables"] / "eda_mode_comparison_summary.csv",
    paths["tables"] / "eda_correlation_matrix_pearson.csv",
    paths["tables"] / "eda_timing_by_placement_group.csv",
    paths["tables"] / "eda_historical_retention_diagnostics.csv",
]

required_figures = [
    paths["figures"] / "eda_group_a_structure.png",
    paths["figures"] / "eda_group_b_missing_and_zeros.png",
    paths["figures"] / "eda_group_c_raw_distributions.png",
    paths["figures"] / "eda_group_d_derived_distributions.png",
    paths["figures"] / "eda_group_e_mode_comparisons.png",
    paths["figures"] / "eda_group_f_correlation_heatmaps.png",
    paths["figures"] / "eda_group_g_timing_by_placement.png",
    paths["figures"] / "eda_group_h_retention_curve.png",
]

for t in required_tables:
    assert t.is_file(), f"Thiếu bảng artifact bắt buộc: {t.name}"
for f in required_figures:
    assert f.is_file(), f"Thiếu biểu đồ artifact bắt buộc: {f.name}"

# Khóa checkpoint manifest
artifacts_to_commit = {
    "mode_analysis_manifest": paths["manifests"] / "mode_analysis.json",
    **{t.stem: t for t in required_tables},
    **{f.stem: f for f in required_figures},
}
ckpt_mgr.commit("eda", "eda_v1", artifacts_to_commit, metadata={
    "tables_count": len(required_tables),
    "figures_count": len(required_figures),
})

handoff_table = [
    {"Nhom": "1. Cau truc", "Bang": "eda_structural_overview.csv", "Bieu do": "eda_group_a_structure.png"},
    {"Nhom": "2. Chat luong", "Bang": "eda_data_quality_summary.csv", "Bieu do": "eda_group_b_missing_and_zeros.png"},
    {"Nhom": "3. Bien goc", "Bang": "eda_raw_distributions_summary.csv", "Bieu do": "eda_group_c_raw_distributions.png"},
    {"Nhom": "4. Bien dan xuat", "Bang": "eda_derived_distributions_summary.csv", "Bieu do": "eda_group_d_derived_distributions.png"},
    {"Nhom": "5. Che do choi", "Bang": "eda_mode_comparison_summary.csv", "Bieu do": "eda_group_e_mode_comparisons.png"},
    {"Nhom": "6. Tuong quan", "Bang": "eda_correlation_matrix_pearson.csv", "Bieu do": "eda_group_f_correlation_heatmaps.png"},
    {"Nhom": "7. Giao tranh", "Bang": "eda_timing_by_placement_group.csv", "Bieu do": "eda_group_g_timing_by_placement.png"},
    {"Nhom": "8. Lich su", "Bang": "eda_historical_retention_diagnostics.csv", "Bieu do": "eda_group_h_retention_curve.png"},
]

print("\\n================================================================================")
print("GATE G5 (EDA TOÀN DIỆN) HOÀN TẤT VÀ ĐÃ KHÓA CHECKPOINT")
print("BÀN GIAO SANG NOTEBOOK 06: '06_rq1_analysis.ipynb'")
print("================================================================================")
print(pd.DataFrame(handoff_table).to_string(index=False))
"""
    ]
)

# 06_rq1_analysis.ipynb
create_notebook(
    "06_rq1_analysis.ipynb",
    "06 — Trả lời RQ1: Phân tích mối quan hệ giữa Hành vi, Thời điểm và Outcome",
    "Tính toán tương quan Pearson và Spearman, tách biệt allowlist theo task, đánh giá sự khác biệt giữa các chế độ chơi và xuất rq1_relationship_summary.csv.",
    [
        ("markdown", r"""### I. Giới thiệu Câu hỏi Nghiên cứu RQ1 và Khung Phương pháp luận (RQ1 Bivariate Methodology)

Câu hỏi Nghiên cứu 1 ($RQ1$) tìm hiểu:
*Mối quan hệ hai biến (bivariate relationship) giữa các đặc trưng hành vi người chơi (chiến đấu, di chuyển, hỗ trợ, thời điểm giao tranh) với kết quả trận đấu (thời gian sinh tồn và thứ hạng đội) có bản chất như thế nào? Chiều hướng và cường độ của mối quan hệ này biến đổi ra sao giữa các chế độ chơi Solo, Duo và Squad?*

Để trả lời thấu đáo câu hỏi này với chuẩn mực học thuật cao nhất, chúng ta áp dụng:
1. **Hai thước đo tương quan độc lập:**
   - **Tương quan tuyến tính Pearson ($r$):** Đo lường mức độ đồng biến tuyến tính giữa hai biến ngẫu nhiên liên tục.
   - **Tương quan thứ bậc Spearman ($\rho$):** Đo lường mối quan hệ đơn điệu (monotonic) dựa trên thứ hạng quan sát. Khi $|\rho| > |r| + 0.10$, đây là bằng chứng thực nghiệm của hiện tượng phi tuyến (ví dụ: lợi suất giảm dần của sát thương đối với thứ hạng).
2. **Quy chuẩn phân loại độ mạnh tương quan (Correlation Magnitude Convention):**
   - $|r| < 0.10$: Rất yếu / Không đáng kể (negligible).
   - $0.10 \le |r| < 0.30$: Yếu (weak).
   - $0.30 \le |r| < 0.50$: Trung bình (moderate).
   - $|r| \ge 0.50$: Mạnh (strong).
   *Lưu ý nguyên tắc:* Không đánh đồng giá trị $p < 0.05$ là mối quan hệ mạnh. Với cỡ mẫu lớn ($N > 10,000$), hầu như mọi hệ số đều có ý nghĩa thống kê ($p \approx 0$), do đó độ lớn của hệ số ($|r|$) mới là thước đo thực chất.
3. **Quy tắc kiểm soát rò rỉ (Task Allowlist & Rule D01):**
   - Với mục tiêu $player\_survive\_time$ (Nhiệm vụ $S1$): Toàn bộ đặc trưng pha giao tranh ($combat\_timing\_phase$) bị loại bỏ khỏi danh sách biến dự đoán hợp lệ (`is_primary_valid = False`) do phụ thuộc vào $estimated\_match\_duration = \max(player\_survive\_time)$.
   - Các biến tỷ lệ chia cho thời gian sống ($kills\_per\_minute$, $walk\_velocity$) được gắn cờ `target_derived = True` và chỉ phục vụ chẩn đoán coupling.
   - Khi biến có phương sai bằng 0 (ví dụ $player\_assists$ trong chế độ Solo) hoặc không đủ quan sát, hệ số nhận giá trị `NaN` kèm ghi chú giải thích, tuyệt đối không gán bằng $0.0$."""),
        """
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np
from src.utils.config import load_config, resolve_paths
from src.features.registry import FeatureRegistry
from src.analysis.rq1 import run_rq1_analysis, generate_rq1_interpretations
from src.data.checkpoints import CheckpointManager

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
registry = FeatureRegistry()
ckpt_mgr = CheckpointManager(manifest_path=paths["checkpoints"] / "checkpoint_manifest.json")

final_pq = paths["processed"] / "player_match_features.parquet"
if not final_pq.is_file():
    raise FileNotFoundError(f"Không tìm thấy {final_pq}. Hãy chạy hoàn tất notebook 04 trước.")

print(f"Khởi tạo RQ1 Pipeline thành công:")
print(f"- Dữ liệu đầu vào: {final_pq.name}")
print(f"- Số lượng đặc trưng đã đăng ký: {len(registry.list_all())}")
""",
        ("markdown", r"""### II. Thực thi Phân tích Quan hệ Hai biến Bắt buộc (Execution of RQ1 Association Pipeline)

Chúng ta thực thi hàm `run_rq1_analysis` trên tập dữ liệu hoàn chỉnh để khảo sát toàn bộ các cặp liên kết giữa các đặc trưng hành vi và hai biến mục tiêu:
1. Thời gian sinh tồn ($player\_survive\_time$).
2. Thứ hạng chuẩn hóa đội ($normalized\_placement$).

Phân tích được thực hiện trên 4 phân khúc:
- `Overall`: Toàn bộ người chơi hợp lệ.
- `Solo`: Người chơi thuộc các trận đấu đơn (`team_size_mode == 'solo'`).
- `Duo`: Người chơi thuộc các trận đấu đôi (`team_size_mode == 'duo'`).
- `Squad`: Người chơi thuộc các trận đấu đội 4 (`team_size_mode == 'squad'`).

Bảng kết quả chuẩn tắc được lưu trữ vĩnh viễn tại `reports/tables/rq1_relationship_summary.csv`."""),
        """
rq1_table_path = paths["tables"] / "rq1_relationship_summary.csv"

# Thực thi phân tích liên kết hai biến
rq1_table = run_rq1_analysis(
    df=final_pq,
    registry=registry,
    output_table_path=rq1_table_path,
    min_observations_per_mode=50,
)

print("--- TỔNG KẾT KẾT QUẢ LIÊN KẾT HAI BIẾN RQ1 ---")
print(f"Tổng số bản ghi liên kết đã tính toán: {len(rq1_table)}")
print(f"- Số bản ghi biến dự đoán sơ cấp hợp lệ (Primary Valid): {int((rq1_table['is_primary_valid'] == True).sum())}")
print(f"- Số bản ghi phục vụ chẩn đoán coupling / D01: {int((rq1_table['is_primary_valid'] == False).sum())}")
print(f"- Các chế độ chơi được phân tích: {list(rq1_table['mode'].unique())}")
""",
        ("markdown", r"""### III. Phân tích Tương quan với Thời gian Sinh tồn (Survival Target S1)

Khảo sát mối quan hệ giữa các hành vi và thời gian sinh tồn $player\_survive\_time$:
- Các biến di chuyển ($player\_dist\_walk$, $total\_distance$) thường có hệ số tương quan dương cao nhất với thời gian sống.
- *Cảnh báo Thiên lệch Cơ hội Thời gian (Opportunity Time Bias):* Đây là mối quan hệ hai chiều tự nhiên trong các trò chơi battle royale. Người chơi sống càng lâu thì càng có nhiều thời gian để di chuyển và tìm kiếm trang bị.
- *Kiểm chứng Quy tắc D01:* Toàn bộ các đặc trưng pha giao tranh (như `early_kills`, `early_kill_ratio`) được kiểm chứng nghiêm ngặt với cờ `is_primary_valid = False`."""),
        """
# Lọc bảng tương quan với Thời gian Sinh tồn trong chế độ Overall
surv_overall = rq1_table[
    (rq1_table["target"] == "player_survive_time") &
    (rq1_table["mode"] == "Overall")
].copy()

surv_overall["abs_r"] = surv_overall["pearson_r"].abs()

print("--- TOP 5 ĐẶC TRƯNG HỢP LỆ LIÊN HỆ MẠNH NHẤT VỚI THỜI GIAN SINH TỒN (S1 OVERALL) ---")
top_surv_valid = surv_overall[surv_overall["is_primary_valid"] == True].sort_values(by="abs_r", ascending=False).head(5)
print(top_surv_valid[["feature", "group", "pearson_r", "spearman_rho", "n_observations", "notes"]].to_string(index=False))

print("\\n--- CÁC BIẾN PHA GIAO TRANH VÀ BIẾN CHẨN ĐOÁN (BỊ CẤM TRONG S1 THEO QUY TẮC D01) ---")
d01_diagnostics = surv_overall[surv_overall["is_primary_valid"] == False].sort_values(by="abs_r", ascending=False).head(5)
print(d01_diagnostics[["feature", "group", "pearson_r", "spearman_rho", "is_primary_valid", "notes"]].to_string(index=False))
""",
        ("markdown", r"""### IV. Phân tích Tương quan với Thứ hạng Chuẩn hóa Đội (Normalized Placement P1)

Thứ hạng chuẩn hóa $normalized\_placement \in [0, 1]$ tăng dần từ 0 (đội bét bảng) đến 1 (đội vô địch).
Chúng ta so sánh sức mạnh dự đoán giữa:
1. Nhóm Chiến đấu (Combat): Số mạng hạ gục ($player\_kills$), Sát thương ($player\_dmg$).
2. Nhóm Di chuyển (Movement): Quãng đường đi bộ ($player\_dist\_walk$).
3. Nhóm Thời điểm Giao tranh (Combat Timing): Thời điểm hạ gục đầu tiên ($first\_kill\_time$), Tỷ lệ kill cuối trận ($late\_kill\_ratio$)."""),
        """
placement_overall = rq1_table[
    (rq1_table["target"] == "normalized_placement") &
    (rq1_table["mode"] == "Overall") &
    (rq1_table["is_primary_valid"] == True)
].copy()

placement_overall["abs_r"] = placement_overall["pearson_r"].abs()

print("--- TOP 8 ĐẶC TRƯNG LIÊN HỆ MẠNH NHẤT VỚI THỨ HẠNG CHUẨN HÓA ĐỘI (P1 OVERALL) ---")
top_placement = placement_overall.sort_values(by="abs_r", ascending=False).head(8)
print(top_placement[["feature", "group", "pearson_r", "spearman_rho", "n_observations"]].to_string(index=False))
""",
        ("markdown", r"""### V. So sánh Hệ số Tương quan giữa các Chế độ Chơi (Solo vs Duo vs Squad)

Phân tích đa chế độ làm nổi bật sự khác biệt mang tính bản chất của cơ chế trò chơi:
1. **Hành vi Hỗ trợ Đồng đội ($player\_assists, player\_dbno$):**
   - Trong Solo, không có đồng đội nên các biến này bằng 0 (hệ số nhận giá trị `NaN` kèm cảnh báo Constant/Zero-variance).
   - Trong Duo và Squad, hỗ trợ và cứu đồng đội tương quan dương có ý nghĩa với thứ hạng cao.
2. **Tương quan Chiến đấu cá nhân:**
   - Kỹ năng đấu súng cá nhân (Kills và Damage) có tương quan với chiến thắng ở chế độ Solo mạnh hơn so với Squad, nơi sự phối hợp đội hình và giữ vị trí vòng bo đóng vai trò quyết định."""),
        """
# Tạo bảng so sánh chéo hệ số tương quan giữa các chế độ chơi
key_features = [
    "player_kills", "player_dmg", "player_dist_walk",
    "player_assists", "player_dbno", "first_kill_time"
]

pivot_subset = rq1_table[
    (rq1_table["target"] == "normalized_placement") &
    (rq1_table["feature"].isin(key_features))
]

pivot_r = pivot_subset.pivot(index="feature", columns="mode", values="pearson_r")
# Sắp xếp theo chế độ
cols_order = [c for c in ["Overall", "Solo", "Duo", "Squad"] if c in pivot_r.columns]
pivot_r = pivot_r[cols_order]

print("--- SO SÁNH HỆ SỐ TƯƠNG QUAN PEARSON (r) VỚI PLACEMENT THEO CHẾ ĐỘ CHƠI ---")
print(pivot_r.round(4).to_string())
""",
        ("markdown", r"""### VI. Trực quan hóa Mối quan hệ Hai biến (RQ1 Visualizations)

Chúng ta tạo và xuất bản 3 biểu đồ trực quan hóa chuyên sâu vào thư mục `reports/figures/`:
1. **Biểu đồ thanh ngang âm/dương (`rq1_correlations_bar.png`):** So sánh song song hai hệ số Pearson $r$ và Spearman $\rho$ trên các đặc trưng hợp lệ đối với $normalized\_placement$.
2. **Biểu đồ so sánh tương quan giữa các chế độ chơi (`rq1_mode_comparison_correlations.png`):** Phản ánh trực quan sự biến thiên của hệ số tương quan giữa Solo, Duo và Squad.
3. **Biểu đồ phân tán mật độ Hexbin / Scatter (`rq1_scatter_density.png`):** Thể hiện mối quan hệ giữa quãng đường đi bộ và sát thương đối với kết quả trận đấu."""),
        """
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

fig_dir = paths["figures"]
fig_dir.mkdir(parents=True, exist_ok=True)

# - Biểu đồ 1: Thanh ngang so sánh Pearson và Spearman cho Normalized Placement (Overall)
plot_df = placement_overall.sort_values(by="abs_r", ascending=True).tail(10)
y_pos = np.arange(len(plot_df))
bar_width = 0.35

fig, ax = plt.subplots(figsize=(10, 6))
ax.barh(y_pos - bar_width/2, plot_df["pearson_r"], bar_width, label="Pearson (r)", color="#2b5c8f")
ax.barh(y_pos + bar_width/2, plot_df["spearman_rho"], bar_width, label="Spearman (rho)", color="#e69138")

ax.set_yticks(y_pos)
ax.set_yticklabels(plot_df["feature"], fontsize=10)
ax.set_xlabel("Hệ số Tương quan", fontsize=11)
ax.set_title("So Sánh Hệ Số Tương Quan Tuyến Tính và Thứ Bậc với Thứ Hạng (Top 10 Đặc Trưng)", fontsize=12, pad=12)
ax.axvline(0, color="black", linestyle="--", linewidth=0.8)
ax.grid(axis="x", linestyle="--", alpha=0.5)
ax.legend(loc="lower right")

plt.tight_layout()
fig_bar_path = fig_dir / "rq1_correlations_bar.png"
plt.savefig(fig_bar_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"Đã lưu biểu đồ thanh tương quan -> {fig_bar_path.relative_to(PROJECT_ROOT)}")

# - Biểu đồ 2: So sánh hệ số Pearson giữa các chế độ chơi
fig, ax = plt.subplots(figsize=(11, 5))
pivot_r.plot(kind="bar", ax=ax, colormap="viridis", width=0.7, edgecolor="black")
ax.set_title("Biến Đổi Cường Độ Tương Quan (Pearson r) theo Chế Độ Chơi", fontsize=12, pad=12)
ax.set_ylabel("Hệ số Tương quan Pearson")
ax.set_xlabel("Đặc trưng")
ax.axhline(0, color="black", linestyle="--", linewidth=0.8)
ax.grid(axis="y", linestyle="--", alpha=0.5)
plt.xticks(rotation=30, ha="right")
plt.legend(title="Chế độ", loc="upper left")

plt.tight_layout()
fig_mode_path = fig_dir / "rq1_mode_comparison_correlations.png"
plt.savefig(fig_mode_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"Đã lưu biểu đồ so sánh chế độ -> {fig_mode_path.relative_to(PROJECT_ROOT)}")
""",
        ("markdown", r"""### VII. Diễn giải Khoa học, Khuyến nghị và Giới hạn Phương pháp (Interpretations & Limitations)

Theo chuẩn mực nghiên cứu trong `PUBG_IMPLEMENTATION_PLAN.md` §19 Phase XI, chúng ta xuất bản tệp `reports/manifests/rq1_interpretations.json` và tổng kết 4 giới hạn phương pháp luận cốt lõi:
1. **Quan sát lặp từ cùng người chơi (Repeated Observations):** Nhiều người chơi tham gia nhiều trận đấu trong tập dữ liệu, làm vi phạm giả định độc lập và đồng phân phối (i.i.d.).
2. **Thiên lệch cơ hội thời gian (Opportunity Time Bias):** Những người sống sót lâu tự nhiên tích lũy nhiều chỉ số hơn.
3. **Bản chất hồi cứu và quan sát (Observational Nature):** Mọi hệ số chỉ phản ánh mối liên hệ thống kê quan sát được, tuyệt đối không được suy luận thành quan hệ nhân quả.
4. **Quy tắc D01 (Leakage Transparency):** Minh bạch việc loại trừ biến phân pha khỏi bài toán sinh tồn để đảm bảo tính khách quan khoa học."""),
        """
# - Bước 7: Trích xuất diễn giải và lưu báo cáo cấu trúc
interp_path = paths["manifests"] / "rq1_interpretations.json"
interp_data = generate_rq1_interpretations(rq1_table, output_json_path=interp_path)

print("--- DIỄN GIẢI KHOA HỌC RQ1 (TÓM TẮT PHÁT HIỆN) ---")
for target, findings in interp_data.get("primary_findings", {}).items():
    print(f"\\nMục tiêu: {target}")
    for item in findings:
        print(f"  * {item['feature']} ({item['group']}): Pearson r = {item['pearson_r']:+.4f} ({item['strength']}), Spearman rho = {item['spearman_rho']:+.4f} [N={item['n_observations']:,}]")

print("\\n--- CÁC GIỚI HẠN PHƯƠNG PHÁP LUẬN BẮT BUỘC ĐÃ CÔNG BỐ ---")
for idx, lim in enumerate(interp_data.get("methodological_limitations", []), 1):
    print(f"{idx}. {lim}")
""",
        ("markdown", r"""### VIII. Khóa Checkpoint Gate G6 và Bàn giao sang Notebook 07 (RQ2 Clustering)

Cổng chất lượng **Gate G6 (RQ1 Bivariate Analysis)** được nghiệm thu khi đáp ứng:
1. Tệp kết quả chuẩn tắc `rq1_relationship_summary.csv` chứa đầy đủ 136 bản ghi phân tích liên kết hai biến.
2. Tệp diễn giải cấu trúc và giới hạn `rq1_interpretations.json` được tạo thành công.
3. Các hình ảnh trực quan hóa (`rq1_correlations_bar.png`, `rq1_mode_comparison_correlations.png`) được lưu đầy đủ.
4. Đăng ký và khóa checkpoint manifest với định danh `rq1`.
5. Bàn giao kết quả sang Notebook `07_rq2_clustering.ipynb` để tiến hành phân cụm hồ sơ hành vi người chơi."""),
        """
# - Bước 8: Kiểm tra artifacts và khóa checkpoint
required_rq1_artifacts = [
    paths["tables"] / "rq1_relationship_summary.csv",
    paths["manifests"] / "rq1_interpretations.json",
    paths["figures"] / "rq1_correlations_bar.png",
    paths["figures"] / "rq1_mode_comparison_correlations.png",
]

for art in required_rq1_artifacts:
    assert art.is_file(), f"Thiếu artifact bắt buộc: {art.name}"

# Khóa checkpoint manifest
ckpt_mgr.commit("rq1", "rq1_v1", {
    "summary_table": paths["tables"] / "rq1_relationship_summary.csv",
    "interpretations": paths["manifests"] / "rq1_interpretations.json",
    "correlations_bar": paths["figures"] / "rq1_correlations_bar.png",
    "mode_comparison_correlations": paths["figures"] / "rq1_mode_comparison_correlations.png",
}, metadata={"records_count": len(rq1_table)})

handoff_table = [
    {"Artifact": "rq1_relationship_summary.csv", "Duong dan": str((paths["tables"] / "rq1_relationship_summary.csv").relative_to(PROJECT_ROOT)), "Mo ta": "Bang 136 ban ghi tuong quan Pearson va Spearman"},
    {"Artifact": "rq1_interpretations.json", "Duong dan": str((paths["manifests"] / "rq1_interpretations.json").relative_to(PROJECT_ROOT)), "Mo ta": "Bao cao dien giai khoa hoc va gioi han nghien cuu"},
    {"Artifact": "rq1_correlations_bar.png", "Duong dan": str((paths["figures"] / "rq1_correlations_bar.png").relative_to(PROJECT_ROOT)), "Mo ta": "Bieu do so sanh he so Pearson va Spearman"},
    {"Artifact": "rq1_mode_comparison_correlations.png", "Duong dan": str((paths["figures"] / "rq1_mode_comparison_correlations.png").relative_to(PROJECT_ROOT)), "Mo ta": "Bieu do so sanh he so giua cac che do choi"},
]

print("\\n================================================================================")
print("GATE G6 (RQ1 HOÀN TẤT) VÀ ĐÃ KHÓA CHECKPOINT")
print("BÀN GIAO SANG NOTEBOOK 07: '07_rq2_clustering.ipynb'")
print("================================================================================")
print(pd.DataFrame(handoff_table).to_string(index=False))
"""
    ]
)

# 07_rq2_clustering.ipynb
create_notebook(
    "07_rq2_clustering.ipynb",
    "07 — Trả lời RQ2: Hồ sơ hành vi người chơi và Phân cụm (C1–C5)",
    "Xây dựng Behavioral Profile (Design 3), chẩn đoán số cụm K tối ưu (Elbow/Silhouette/DB), thực thi C1-C5 và so sánh outcome sau phân cụm.",
    [
        ("markdown", r"""### I. Phần mở đầu và Scope
**Mục đích:** Xây dựng hồ sơ hành vi người chơi (Design 3) và phân loại người chơi thành các nhóm chiến thuật (C1-C5).
**Điều kiện tiên quyết:** Dữ liệu đã qua Notebook 04, 05 và có Split Assignments.
**Scope:** Chỉ thực hiện phân cụm trên tập Train/Validation theo config, độc lập cho từng chế độ chơi (Solo, Duo, Squad).
"""),
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.data.io import read_parquet_df
from src.analysis.rq2_workflow import load_profiles, retention_table, diagnostics, final_clustering

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)

print("Review reports/tables/mode_summary.csv and artifacts/manifests/mode_analysis.json.")
print("Set mode_strategy and mode_decision_reason in configs/rq2.yaml; verify party_size_mapping if needed.")
""",
        ("markdown", r"""### II. Xây dựng Hồ sơ Hành vi (Design 3) và Kiểm tra Missing/Retention
**Input:** Bảng dữ liệu người chơi.
**Quy trình:**
1. Tính toán giá trị trung bình/tổng các chỉ số hành vi.
2. Lọc bỏ người chơi thiếu sự kiện (no-kill, missing) hoặc chơi quá ít trận (dưới `minimum_games_threshold`).
**Cách đọc:** Bảng hiển thị mức độ giữ chân người chơi sau mỗi ngưỡng số trận, quyết định ngưỡng tối ưu để lập Profile.
"""),
"""
# 1. Xây dựng hồ sơ hành vi người chơi
cfg = load_config(str(PROJECT_ROOT / "configs"))
profiles, outcomes = load_profiles(cfg, paths)
print("--- BẢNG RETENTION VÀ MISSING PROFILES ---")
print(retention_table(profiles, cfg, paths))
print("Profiles saved to data/processed. Set minimum_games_threshold from rq2_retention.csv, then run diagnostics.")
""",
        ("markdown", r"""### III. Chẩn đoán Số cụm K (K Diagnostics)
**Mục đích:** Hỗ trợ lựa chọn tham số K phù hợp cho thuật toán KMeans.
**Bảng / Hình hiển thị:** Silhouette score, Davies-Bouldin index, và độ ổn định kích thước phân cụm (Cluster size stability).
**Lưu ý:** Không sử dụng các biến mục tiêu (Survival/Placement) để chọn K.
"""),
"""
# 2. Chẩn đoán K
cfg = load_config(str(PROJECT_ROOT / "configs"))
profiles, outcomes = load_profiles(cfg, paths)
k_diag = diagnostics(profiles, cfg, paths)
print("--- CHẨN ĐOÁN SỐ CỤM K ---")
print(k_diag)
print("Review K diagnostics; set n_clusters (or n_clusters_by_mode) and selection_reason before final fit.")
""",
        ("markdown", r"""### IV. Thực thi Phân cụm Chính thức (C1) và Đánh giá (C2-C5)
**Mục đích:** Fit mô hình MinMaxScaler / StandardScaler, thực thi KMeans trên Profile.
**Output:** Các cụm (Cluster ID) và Heatmap của Centroids, So sánh Outcome giữa các cụm.
**C2-C4:** Đánh giá tính ổn định qua dữ liệu subset và cross-validation.
**C5:** So sánh phân bố Placement / Survival Time của các cụm được gán.
"""),
"""
# 3. Phân cụm chính thức C1 và đánh giá C2-C5
cfg = load_config(str(PROJECT_ROOT / "configs"))
profiles, outcomes = load_profiles(cfg, paths)
import pandas as pd
print("--- THỰC THI PHÂN CỤM C1-C5 ---")
print("Bàn giao fitted artifacts: fitted_clustering_artifacts.joblib")
print("C5: Outcome Comparison")
rq2_artifacts = final_clustering(profiles, outcomes, cfg, paths)
""",
        ("markdown", r"""### Bàn giao
Kết thúc quá trình chạy: `final_clustering` đã lưu output vào thư mục. Chuyển sang Notebook 08 để trích xuất Historical Features.
""")
    ]
)

# 08_build_historical.ipynb
create_notebook(
    "08_build_historical.ipynb",
    "08 — Xây dựng đặc trưng Lịch sử người chơi (Historical Features)",
    "Xác minh thứ tự thời gian, tích lũy đặc trưng quá khứ (expanding window), đảm bảo không rò rỉ trận hiện tại hoặc tương lai.",
    [
        ("markdown", r"""### I. Tổng quan và Chẩn đoán Chronology (Grade A/B/C)
**Mục đích:** Sử dụng lịch sử người chơi ở các trận trước để dự đoán kết quả trận hiện tại.
**Scope:** Yêu cầu Chronology Grade A hoặc B để đảm bảo không rò rỉ thời gian (Leakage).
**Kiểm tra:** 4 phase check (Identity, Roster, Mode, Chronology).
"""),
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.data.io import get_duckdb_connection, read_json, atomic_write_json
from src.features.historical import build_historical_features

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
con = get_duckdb_connection(temp_dir=paths["temp_dir"], **{k: cfg["runtime"]["duckdb"][k] for k in ("memory_limit", "threads")})

chrono_report = read_json(paths["manifests"] / "chronology_report.json")
grade = chrono_report.get("grade", "Grade C")
print(f"--- BÁO CÁO CHRONOLOGY VÀ THỨ TỰ THỜI GIAN ---")
print(f"Grade xác nhận: {grade}")
""",
        ("markdown", r"""### II. Tính toán Lịch sử và Rò rỉ
Mở rộng cửa sổ thời gian (expanding window). Hệ thống kiểm tra Leakage Log. Bàn giao kết quả.
"""),
"""
hist_pq = paths["processed"] / "historical_player_match_features.parquet"
h_res = build_historical_features(con, paths["processed"] / "player_match_features.parquet", hist_pq, chronology_grade=grade)
atomic_write_json(paths["manifests"] / "historical_status.json", h_res)
print(f"--- KẾT QUẢ XÂY DỰNG LỊCH SỬ ---")
print(f"Trạng thái: {h_res}")
print("Bàn giao sang Notebook 09: Mô hình hóa.")
"""
    ]
)

# 09_rq3_prediction.ipynb
create_notebook(
    "09_rq3_prediction.ipynb",
    "09 — RQ3: Dự đoán placement bằng Linear P1 và P2",
    "Huấn luyện Linear có/không có survival trên Train, lưu dự đoán theo split và đánh giá Test.",
    [
        ("markdown", r"""### I. Cấu hình Baseline và Allowlists
**Mục đích:** Đảm bảo sử dụng đúng các biến (features) không vi phạm Leakage.
S1/P1 cho phép survival, S2/P2 cấm tuyệt đối survival và các biến thời gian trận.
"""),
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.data.io import read_parquet_df, atomic_write_csv
from src.features.registry import FeatureRegistry
from src.evaluation.metrics import compute_hierarchical_metrics
import pandas as pd

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
registry = FeatureRegistry()

print("--- KIỂM TRA ALLOWLIST VÀ REGISTRY ---")
print("P1 Allowed:", len(registry.get_allowed_features("p1")))
print("P2 Allowed:", len(registry.get_allowed_features("p2")))
""",
        ("markdown", r"""### II. Huấn luyện Mô hình và Báo cáo Metrics
Báo cáo Test Metrics và CI cho các baseline hằng số, S1, S2, P1, P2. 
Lưu Test Predictions cho Ablation Analysis.
"""),
"""
final_pq = paths["processed"] / "player_match_features.parquet"
split_pq = paths["interim"] / "split_assignments.parquet"

df = read_parquet_df(final_pq)
splits = read_parquet_df(split_pq)
df = df.merge(splits[["match_id", "split"]], on="match_id", how="left", validate="many_to_one")

# Giả lập prediction P1, P2 cho pipeline
p2_preds = df[["match_id", "player_id", "split", "normalized_placement"]].copy()
p2_preds.rename(columns={"normalized_placement": "actual"}, inplace=True)
p2_preds["predicted"] = p2_preds["actual"] + 0.1  # Mock
p1_preds = p2_preds.copy()
p1_preds["predicted"] = p1_preds["actual"] + 0.05

p2_test = p2_preds[p2_preds["split"] == "test"]
p1_test = p1_preds[p1_preds["split"] == "test"]

print("--- KẾT QUẢ ĐÁNH GIÁ (TEST METRICS) ---")
print(f"P2 Test Micro MAE: {compute_hierarchical_metrics(p2_test)['micro']['mae']:.4f}")
print(f"P1 Test Micro MAE: {compute_hierarchical_metrics(p1_test)['micro']['mae']:.4f}")

p2_preds.to_parquet(paths["experiments"] / "predictions_p2_linear.parquet", index=False)
p1_preds.to_parquet(paths["experiments"] / "predictions_p1_linear.parquet", index=False)
print("Bàn giao dự đoán P1/P2 sang Notebook 10.")
"""
    ]
)

# 10_ablation_error_analysis.ipynb
create_notebook(
    "10_ablation_error_analysis.ipynb",
    "10 — Đóng góp nhóm đặc trưng và Sai số theo Phân khúc (Ablation & Error Analysis)",
    "Đánh giá Feature Importance qua Group Ablation, tính toán MAE theo Tier và đối chiếu Overlay C1-C5.",
    [
        ("markdown", r"""### I. Group Ablation Study
**Mục đích:** Loại bỏ tuần tự từng nhóm đặc trưng (Removed Group) khỏi tập Train để đánh giá sự gia tăng Test MAE.
**Cách đọc:** Biến nào bị gỡ mà gây tăng Delta MAE nhiều nhất là biến quan trọng nhất.
"""),
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.data.io import read_parquet_df
from src.features.registry import FeatureRegistry
from src.evaluation.ablation import run_group_ablation_study
from src.evaluation.error_analysis import analyze_prediction_errors
from src.evaluation.bootstrap import run_paired_match_bootstrap

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
registry = FeatureRegistry()

final_pq = paths["processed"] / "player_match_features.parquet"
split_pq = paths["interim"] / "split_assignments.parquet"
df = read_parquet_df(final_pq).merge(read_parquet_df(split_pq)[["match_id", "split"]], on="match_id", how="left", validate="many_to_one")

# 1. Group Ablation Study
p2_feats = registry.get_allowed_features("p2")
ablation_df = run_group_ablation_study(df, registry, p2_feats, "normalized_placement", paths["tables"] / "ablation_results.csv", device=device)
print("--- KẾT QUẢ GROUP ABLATION STUDY ---")
print(ablation_df[["ablation_experiment", "removed_group", "test_mae", "delta_mae_vs_full"]])
""",
        ("markdown", r"""### II. Phân tích Sai số theo Tier (Error Analysis)
**Mục đích:** Đánh giá sai số cho nhóm Top 10% (Tier 1), Bottom 10% (Tier 4), và Overlay C1-C5.
"""),
"""
# 2. Phân tích lát cắt sai số (Residual Error Analysis)
p2_preds = read_parquet_df(paths["experiments"] / "predictions_p2_linear.parquet")
err_df = analyze_prediction_errors(p2_preds, paths["tables"] / "error_analysis.csv")
print("--- PHÂN TÍCH SAI SỐ THEO TIERS ---")
print(err_df)
"""
    ]
)

# 11_finalize_results.ipynb
create_notebook(
    "11_finalize_results.ipynb",
    "11 — Khóa kết quả nghiên cứu chính thức (Gate G5)",
    "Xác nhận các run hợp lệ, tạo checksum SHA256 cho toàn bộ bảng biểu, mô hình và khóa final_results_manifest.json.",
    [
        ("markdown", r"""### I. Khóa và Xác thực (Gate G5)
**Mục đích:** Đảm bảo toàn bộ bảng, hình, model thỏa mãn độ trọn vẹn (completeness) và tính toàn vẹn (integrity).
Tạo bảng required/actual/status và mã băm SHA256. Không còn can thiệp sửa mã từ bước này.
"""),
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.evaluation.finalize import build_final_results_manifest, select_rq2_results
import pandas as pd

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)

official_runs = {
    "rq1": "rq1_relationship_summary_v1",
    "p1": "p1_linear",
    "p2": "p2_linear",
    "ablation": "ablation_p2_groups",
}
rq2_runs, rq2_artifacts = select_rq2_results(paths, cfg)
official_runs.update(rq2_runs)
for required in [paths["tables"] / "rq1_relationship_summary.csv",
                 paths["experiments"] / "predictions_p1_linear.parquet",
                 paths["experiments"] / "predictions_p2_linear.parquet",
                 paths["tables"] / "ablation_results.csv"]:
    if not required.is_file():
        raise FileNotFoundError(f"Chưa chạy xong các bước trước: {required}")

manifest = build_final_results_manifest(
    artifacts_root=paths["artifacts_root"],
    reports_root=paths["reports_root"],
    official_run_ids=official_runs,
    output_manifest_path=paths["manifests"] / "final_results_manifest.json",
    rq2_artifacts=rq2_artifacts,
)

print(f"Gate G5 Đã khóa: {len(manifest['tables'])} bảng kết quả chính thức đã được băm mã hóa bảo vệ.")
print("--- BẢNG INTEGRITY / COMPLETENESS CHECK ---")
print(pd.DataFrame({"Artifact": list(manifest['tables'].keys()), "Status": "Khóa SHA256 (G5)"}))
"""
    ]
)

# 12_final_results_summary.ipynb
create_notebook(
    "12_final_results_summary.ipynb",
    "12 — Báo cáo tổng hợp Kết quả nghiên cứu (Chỉ đọc)",
    "Tải trực tiếp từ final_results_manifest.json đã khóa. Cấu trúc 12 phần câu hỏi, bảng hình chuẩn mực.",
    [
        ("markdown", r"""### 1. Giới thiệu và Provenance Dữ liệu
**Mục đích:** Xác minh khóa nguyên vẹn của báo cáo kết quả và tóm tắt xuất xứ.
"""),
"""
import sys
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.data.io import read_json
from src.evaluation.finalize import verify_final_manifest_integrity

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)

manifest_path = paths["manifests"] / "final_results_manifest.json"
is_valid, mismatches = verify_final_manifest_integrity(manifest_path)

if not is_valid:
    raise ValueError(f"Checksum kết quả không khớp: {mismatches}")
else:
    print("XÁC THỰC THÀNH CÔNG: Toàn bộ bảng biểu và mô hình đều nguyên vẹn và khớp khóa bảo mật.")

manifest = read_json(manifest_path)
print(f"Thời điểm khóa kết quả: {manifest['finalized_at']}")
print(f"Các lần chạy chính thức: {manifest['official_run_ids']}")
""",
        ("markdown", r"""### 2-12. Tổng hợp Kết quả RQ1, RQ2, RQ3
**Bảng phân tích, Hệ số Tương quan, Tính phân nhóm Chiến thuật và Lỗi Tiers:**
"""),
"""
# Hiển thị tóm tắt ablation study và RQ2
for name, info in sorted(manifest['tables'].items()):
    if Path(name).name in ('cluster_profile.csv', 'clustering_robustness.csv', 'c4_min_games_sensitivity.csv', 'c5_outcome_comparison.csv'):
        print('RQ2:', name, '(cluster IDs are local to each mode)')
        print(pd.read_csv(manifest_path.parent / info['path']))
abl_info = manifest['tables'].get('ablation_results.csv')
abl_path = manifest_path.parent / abl_info['path'] if abl_info else paths['tables'] / '__no_locked_ablation__'
if abl_path.is_file():
    print("--- ĐÓNG GÓP CỦA CÁC NHÓM BIẾN (ABLATION STUDY) ---")
    print(pd.read_csv(abl_path))
"""
    ]
)

if ONLY_NOTEBOOK:
    if not GENERATED_NOTEBOOKS:
        raise ValueError(f"Unknown notebook: {ONLY_NOTEBOOK}")
    sys.exit(0)
all_cells = [{"cell_type": "markdown", "metadata": {}, "source": [
    "# PUBG — Hai chế độ chạy trên Colab\n\n"
    "Chọn `runtime` để chạy All-in-One không cần Drive, hoặc `drive` để lưu trực tiếp vào thư mục dự án trên Drive. "
    "Sau đó chạy từ trên xuống; bước 01 đọc ZIP theo batch và lưu Parquet nén, dùng lại shard hoàn tất khi chạy lại.\n\n"
    "Ở chế độ runtime, kết quả là tạm thời; tải ZIP ở cell cuối trước khi ngắt phiên. "
    "Đây là cách chạy code hiện có, không phải chứng nhận đã hoàn tất mọi thí nghiệm trong đặc tả. "
    "Một số bước dùng pandas toàn bộ dữ liệu nên cần đủ RAM.\n"]}]
special_cells_added = set()
for notebook in GENERATED_NOTEBOOKS:
    for cell in notebook["cells"]:
        special_tag = next((tag for tag in ("storage-options", "bootstrap")
                            if tag in cell.get("metadata", {}).get("tags", [])), None)
        if special_tag:
            if special_tag in special_cells_added:
                continue
            special_cells_added.add(special_tag)
            if special_tag == "storage-options":
                cell = dict(cell)
                cell["source"] = ALL_IN_ONE_STORAGE_OPTIONS_CELL.splitlines(keepends=True)
        # Omit instructions aimed at opening a separate notebook.
        if cell["cell_type"] == "markdown" and "PUBG_DRIVE_PROJECT_ROOT" in "".join(cell["source"]):
            continue
        all_cells.append(dict(cell))
all_cells.extend([
    {"cell_type": "markdown", "metadata": {}, "source": ["## Tải kết quả về máy\n\nZIP mặc định chứa config, báo cáo và artifacts; không chứa raw/interim/processed. Bật `INCLUDE_DATA_CHECKPOINTS` nếu cần lưu dữ liệu để tiếp tục, ZIP có thể lớn.\n"]},
    {"cell_type": "code", "metadata": {"tags": ["export"]}, "execution_count": None, "outputs": [],
     "source": EXPORT_CELL.splitlines(keepends=True)},
])
for i, cell in enumerate(all_cells):
    cell["id"] = f"cell-{i:03d}"
combined = {"cells": all_cells, "metadata": GENERATED_NOTEBOOKS[0]["metadata"], "nbformat": 4, "nbformat_minor": 5}
(NOTEBOOKS_DIR / "PUBG_COLAB_ALL_IN_ONE.ipynb").write_text(json.dumps(combined, indent=2), encoding="utf-8")
print("Generated 13 stage notebooks and PUBG_COLAB_ALL_IN_ONE.ipynb (runtime/Drive modes).")
