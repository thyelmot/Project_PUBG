import ast
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
    SUMMARY_BOOTSTRAP,
)

BOOTSTRAP = bootstrap_source(NOTEBOOKS_DIR.parent)
GENERATED_NOTEBOOKS = []
ONLY_NOTEBOOK = sys.argv[sys.argv.index('--only') + 1] if '--only' in sys.argv else None
NOTEBOOK_DEPENDENCIES = {
    "00_setup.ipynb": [],
    "01_download_validate.ipynb": [],
    "02_data_quality_and_structure.ipynb": ["01_download_validate.ipynb"],
    "03_build_player_match.ipynb": ["02_data_quality_and_structure.ipynb"],
    "04_combat_timing.ipynb": ["01_download_validate.ipynb", "03_build_player_match.ipynb"],
    "05_eda.ipynb": ["02_data_quality_and_structure.ipynb", "04_combat_timing.ipynb"],
    "06_rq1_analysis.ipynb": ["02_data_quality_and_structure.ipynb", "04_combat_timing.ipynb", "05_eda.ipynb"],
    "07_rq2_clustering.ipynb": ["04_combat_timing.ipynb", "05_eda.ipynb"],
    "08_build_historical.ipynb": ["02_data_quality_and_structure.ipynb", "04_combat_timing.ipynb"],
    "09_rq3_prediction.ipynb": ["02_data_quality_and_structure.ipynb", "04_combat_timing.ipynb", "08_build_historical.ipynb"],
    "10_ablation_error_analysis.ipynb": ["09_rq3_prediction.ipynb"],
    "11_finalize_results.ipynb": ["06_rq1_analysis.ipynb", "07_rq2_clustering.ipynb", "09_rq3_prediction.ipynb", "10_ablation_error_analysis.ipynb"],
}

NOTEBOOK_ARTIFACT_EXPRESSIONS = {
    "00_setup.ipynb": '{"runtime_snapshot": paths["manifests"] / "runtime_snapshot.json"}',
    "01_download_validate.ipynb": '{"batch_manifest": staging_dir / "batch_manifest.json", "source_inventory": paths["manifests"] / "source_inventory.json", "schema_report": paths["manifests"] / "schema_report.json", "parse_report": paths["manifests"] / "schema_parse_report.json", "shard_scale_figure": _fig_shards, "missing_parse_figure": _fig_parse}',
    "02_data_quality_and_structure.ipynb": "_nb02_artifacts",
    "03_build_player_match.ipynb": "_nb03_artifacts",
    "04_combat_timing.ipynb": "_nb04_artifacts",
    "05_eda.ipynb": "artifacts_to_commit",
    "06_rq1_analysis.ipynb": '{"summary": paths["tables"] / "rq1_relationship_summary.csv", "interpretations": paths["manifests"] / "rq1_interpretations.json", "correlations": paths["figures"] / "rq1_correlations_bar.png", "mode_comparison": paths["figures"] / "rq1_mode_comparison_correlations.png", "density": paths["figures"] / "rq1_scatter_density.png"}',
    "07_rq2_clustering.ipynb": "rq2_artifacts",
    "08_build_historical.ipynb": 'history_artifacts',
    "09_rq3_prediction.ipynb": '{"p1_predictions": paths["experiments"] / "predictions_p1_linear.parquet", "p2_predictions": paths["experiments"] / "predictions_p2_linear.parquet"}',
    "10_ablation_error_analysis.ipynb": 'evaluation_artifacts',
    "11_finalize_results.ipynb": 'finalization_artifacts',
}
NOTEBOOK_NEXT = {name: (list(NOTEBOOK_DEPENDENCIES)[i + 1] if i + 1 < len(NOTEBOOK_DEPENDENCIES) else "12_final_results_summary.ipynb")
                 for i, name in enumerate(NOTEBOOK_DEPENDENCIES)}

def inline_saved_outputs(source: str) -> str:
    """Preserve scientific code/comments; display existing tables and saved PNGs."""
    # Display the canonical file once, including in non-interactive fixture runners.
    source = source.replace('plt.show()', 'None').replace('display(fig)', 'None').rstrip() + '\n'
    lines = source.splitlines(keepends=True)
    additions = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        value = None
        if isinstance(node.func, ast.Name) and node.func.id == 'print':
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == 'to_string':
                    value = 'display(' + ast.get_source_segment(source, child.func.value) + ')'
                    if node.args and isinstance(node.args[0], ast.IfExp):
                        value += ' if ' + ast.get_source_segment(source, node.args[0].test) + ' else None'
                    break
        elif isinstance(node.func, ast.Attribute) and node.func.attr == 'savefig' and node.args:
            value = 'display(Image(filename=str(' + ast.get_source_segment(source, node.args[0]) + ')))'
        if value:
            indent = re.match(r'\s*', lines[node.lineno - 1]).group()
            additions.setdefault(node.end_lineno, []).append(indent + value + '\n')
    for line_number in sorted(additions, reverse=True):
        lines[line_number:line_number] = list(dict.fromkeys(additions[line_number]))
    return 'from IPython.display import display, Image\n' + ''.join(lines)


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
    options = STORAGE_OPTIONS_CELL
    if filename == '12_final_results_summary.ipynb':
        options += '\n# @markdown Chọn đúng manifest snapshot hoặc canonical cụ thể; không tìm latest.\nPUBG_SUMMARY_MANIFEST = ""  # @param {type:"string"}\n# Chỉ bật cho fixture, không dùng làm approval kết quả nghiên cứu.\nPUBG_SUMMARY_ALLOW_FIXTURE = False  # @param {type:"boolean"}\n'
    cells.append({"cell_type": "code", "execution_count": None, "metadata": {"tags": ["storage-options"]},
                  "outputs": [], "source": options.splitlines(keepends=True)})
    cells.append({"cell_type": "code", "execution_count": None, "metadata": {"tags": ["bootstrap"]},
                  "outputs": [], "source": (SUMMARY_BOOTSTRAP if filename == '12_final_results_summary.ipynb' else BOOTSTRAP).splitlines(keepends=True)})
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
            stage_setup = ''
            if previous_code_cell is None:
                stage_setup = '_pubg_figure_details = {}\n'
            # Release previous stage objects in the shared All-in-One kernel.
            if source.startswith("import sys"):
                source = ("import gc\n"
                          "for _old_name in ('df', 'df_sample', 'df_paths', 'meta_df', 'splits', 'profiles', 'outcomes', 'filtered_profiles', 'filtered_outcomes', 'X', 'res', 'p1_preds', 'p2_preds', 'p1_test', 'p2_test', '_'):\n"
                          "    globals().pop(_old_name, None)\n"
                          "if 'con' in globals():\n    globals().pop('con').close()\n"
                          "gc.collect()\n" + source)
            # A fresh kernel must restore imports and paths before stage cells.
            guard = ('if '+ ('"manifest_path"' if filename == '12_final_results_summary.ipynb' else '"paths"') + ' not in globals() or "PROJECT_ROOT" not in globals():\n'
                     '    raise RuntimeError("Runtime đã mất trạng thái. Chạy lại cell Chọn nơi lưu dữ liệu và Bootstrap, rồi cell khởi tạo stage trước khi tiếp tục.")\n')
            guard += '_pubg_progress = globals().setdefault("_PUBG_CELL_PROGRESS", {})\n'
            if previous_code_cell is not None:
                guard += (f'if _pubg_progress.get({filename!r}, -1) < {previous_code_cell}:\n'
                          f'    raise RuntimeError("{filename}: Chạy thành công cell trước trước khi tiếp tục; không bỏ qua cell bị lỗi.")\n')
            guard += f'_pubg_progress[{filename!r}] = {previous_code_cell if previous_code_cell is not None else -1}\n'
            if filename in NOTEBOOK_DEPENDENCIES and previous_code_cell is None:
                stage_setup += ('from src.data.checkpoints import CheckpointManager\n'
                          'from src.utils.hashing import compute_stage_signature, hash_file\n'
                          '_pubg_checkpoint = CheckpointManager(paths["checkpoints"] / "checkpoint_manifest.json")\n'
                          '_pubg_manifest = _pubg_checkpoint.load_manifest()\n'
                          f'_pubg_dependencies = {NOTEBOOK_DEPENDENCIES[filename]!r}\n'
                          '_pubg_dependency_records = {name: {"signature": _pubg_manifest.get("stages", {}).get("notebook/" + name, {}).get("signature"), "checksums": _pubg_manifest.get("stages", {}).get("notebook/" + name, {}).get("checksums", {})} for name in _pubg_dependencies}\n'
                          '_pubg_code_files = sorted((PROJECT_ROOT / "src").rglob("*.py"))\n'
                          '_pubg_config_files = sorted((PROJECT_ROOT / "configs").glob("*.yaml"))\n'
                          f'_pubg_signature = compute_stage_signature({filename!r}, data_files=_pubg_config_files, config={{"dependencies": _pubg_dependency_records}}, code_files=_pubg_code_files, cohort=_pubg_dependency_records, split=cfg.get("rq3", {{}}).get("split"), registry=hash_file(PROJECT_ROOT / "src/models/registry.py"), feature_set=hash_file(PROJECT_ROOT / "configs/features.yaml"), backend={{"rq2": cfg.get("rq2", {{}}).get("device"), "rq3": cfg.get("rq3", {{}}).get("device")}})\n'
                          f'_pubg_checkpoint.begin_notebook({filename!r}, _pubg_dependencies, signature=_pubg_signature, writer_id=globals().get("PUBG_WRITER_ID") or None, force_takeover=bool(globals().get("PUBG_FORCE_STAGE_TAKEOVER", False)))\n'
                          f'_pubg_writer = _pubg_checkpoint.load_manifest()["stages"][{("notebook/" + filename)!r}]["writer_id"]\n')
            source = source.replace('con = get_duckdb_connection(',
                                    'if "con" in globals():\n    con.close()\ncon = get_duckdb_connection(')
            if filename in NOTEBOOK_DEPENDENCIES and i == last_code_cell and filename != '09_rq3_prediction.ipynb':
                artifacts = NOTEBOOK_ARTIFACT_EXPRESSIONS[filename]
                source += (f'\n_pubg_stage_artifacts = {artifacts}\n'
                           'from src.utils.logging import write_handover, write_figure_metadata\n'
                           f'_pubg_checkpoint.commit({("notebook/" + filename)!r}, _pubg_signature, _pubg_stage_artifacts, writer_id=_pubg_writer)\n'
                           f'write_handover(paths["manifests"] / "notebook_handover.csv", stage={filename!r}, artifacts=_pubg_stage_artifacts, status="completed", writer_id=_pubg_writer, version=_pubg_signature, next_step={NOTEBOOK_NEXT[filename]!r})\n'
                           f'write_figure_metadata(paths["manifests"] / "figure_metadata.csv", stage={filename!r}, artifacts=_pubg_stage_artifacts, details=globals().get("_pubg_figure_details", {{}}))\n')
            if filename == '07_rq2_clustering.ipynb' and previous_code_cell is None:
                section = 'rq2' if filename.startswith('07') else 'rq3'
                setup = ("from src.models.compute import compute_info\n"
                         f"device = cfg[{section!r}].get('device', 'cpu')\n"
                         "compute = compute_info(device, install=globals().get('IN_COLAB', False) and globals().get('PUBG_INSTALL_DEPENDENCIES', True))\n"
                         "print('Training backend:', compute)\n")
                source = source.replace('paths = resolve_paths(cfg)\n', 'paths = resolve_paths(cfg)\n' + setup, 1)
            if int(filename[:2]) <= 7:
                source = inline_saved_outputs(source)
            cell["source"] = (guard + source + '\n' + stage_setup + f'\n_pubg_progress[{filename!r}] = {i}\n').splitlines(keepends=True)
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
    if filename in ('07_rq2_clustering.ipynb', '09_rq3_prediction.ipynb'):
        nb_json['metadata']['accelerator'] = 'GPU'
        nb_json['metadata']['colab'] = {'gpuType': 'T4'}
    with open(NOTEBOOKS_DIR / filename, "w", encoding="utf-8") as f:
        json.dump(nb_json, f, indent=2)
    GENERATED_NOTEBOOKS.append(nb_json)
    print(f"Created {filename}")

# 00_setup.ipynb
create_notebook(
    "00_setup.ipynb",
    "00 — Khởi tạo môi trường, cấu hình và trạng thái checkpoint",
    "Xác minh môi trường, cấu hình, tài nguyên, provenance và checkpoint trước khi xử lý dữ liệu; chưa tạo kết quả trả lời RQ.",
    [
        ("markdown", r"""### 0. Bối cảnh khoa học, phạm vi và tiêu chí thành công

Notebook 00 là **cổng tiền điều kiện vận hành**, không phải bước phân tích dữ liệu và không trả lời trực tiếp RQ1-RQ3. Mục tiêu là chứng minh phiên chạy hiện tại có đúng mã nguồn, cấu hình, đường dẫn và khả năng ghi để các notebook sau tạo kết quả có thể tái lập.

Các câu hỏi kiểm tra:

1. `PROJECT_ROOT` có đúng dự án và có quyền ghi không?
2. Các cấu hình bắt buộc có hợp lệ không; quyết định nào vẫn đang `pending` vì cần bằng chứng dữ liệu?
3. Mọi đường dẫn canonical có trỏ vào đúng storage root và ghi được không?
4. RAM, đĩa runtime, đĩa spill và GPU thực tế là gì? Các con số này chỉ mô tả phiên chạy hiện tại, không phải quota Google Drive.
5. Phiên bản package, hash tài liệu, hash mã nguồn và checkpoint có đủ để truy vết lần chạy không?

**Input:** mã nguồn hiện tại, 10 file YAML, biến storage/runtime và checkpoint manifest nếu đã tồn tại. Ở stage này chưa có cohort, split, target hay metric; số dòng/match/player là không áp dụng.

**Output:** `runtime_snapshot.json`, các bảng kiểm toán môi trường/cấu hình/đường dẫn/tài nguyên/checkpoint và checkpoint `notebook/00_setup.ipynb`.

**Tiêu chí chuyển bước:** không còn lỗi chặn về project root, quyền ghi, cấu hình required hoặc dung lượng artifacts tối thiểu; snapshot được ghi và đọc lại. Trạng thái `pending` có lý do không chặn Notebook 00 nhưng phải được giải quyết tại đúng gate sau."""),
        ("markdown", r"""### 1. Xác minh project root và provenance đầu vào

Cell này dùng marker file để chứng minh thư mục hiện tại là đúng dự án, sau đó kiểm tra quyền ghi. Đây là kiểm tra fail-fast: sai root hoặc không ghi được sẽ dừng trước khi tạo artifact.

**Cách đọc bảng:** mỗi dòng là một thuộc tính của phiên chạy. `Đạt` phải là `Có` đối với marker và quyền ghi. Storage mode cho biết dữ liệu bền vững nằm ở Drive hay chỉ tồn tại trong runtime."""),
        """
import sys
import os
from pathlib import Path

IN_COLAB = "google.colab" in sys.modules
PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.runtime import check_environment
_required_markers = [
    "configs/data.yaml",
    "configs/runtime.yaml",
    "src/utils/config.py",
    "src/utils/generate_notebooks.py",
]
_project_report = check_environment(
    target_dir=str(PROJECT_ROOT),
    min_disk_gb=0.0,
    raise_on_critical=True,
    required_files=_required_markers,
)
_root_writable = _project_report["can_write"]

_root_rows = [
    {"Thuộc tính": "Project root", "Giá trị thực tế": str(PROJECT_ROOT), "Kỳ vọng": "Đúng thư mục Project_PUBG", "Trạng thái": "Đạt"},
    {"Thuộc tính": "Marker bắt buộc", "Giá trị thực tế": f"{len(_required_markers)}/{len(_required_markers)} có mặt", "Kỳ vọng": "Đủ marker", "Trạng thái": "Đạt"},
    {"Thuộc tính": "Quyền ghi root", "Giá trị thực tế": "Có" if _root_writable else "Không", "Kỳ vọng": "Có", "Trạng thái": "Đạt" if _root_writable else "Chặn"},
    {"Thuộc tính": "Storage mode", "Giá trị thực tế": globals().get("PUBG_STORAGE_MODE", "unknown"), "Kỳ vọng": "runtime hoặc drive", "Trạng thái": "Thông tin"},
    {"Thuộc tính": "Nền tảng", "Giá trị thực tế": "Google Colab" if IN_COLAB else "Local", "Kỳ vọng": "Không giới hạn", "Trạng thái": "Thông tin"},
]
import pandas as pd
_df_root = pd.DataFrame(_root_rows)
print("--- BẢNG 00-A: PROJECT ROOT VÀ PROVENANCE PHIÊN CHẠY ---")
print(_df_root.to_string(index=False))
print(f"Data root   : {paths['data_root']}")
print(f"Reports root: {paths['reports_root']}")
""",
        ("markdown", r"""### 2. Nạp và kiểm tra cấu hình nghiên cứu

Cấu hình là hợp đồng tái lập của pipeline. `required` là lỗi chặn phải sửa ngay; `pending` là quyết định được phép để trống cho tới notebook có đủ bằng chứng; `ok` là giá trị đã sẵn sàng cho phạm vi hiện tại. Notebook không tự điền ngưỡng, K, split hoặc backend để vượt gate.

**Cách đọc bảng:** cột `status` quyết định khả năng tiếp tục. Không được hiểu `pending` là đã xác minh hoặc lấy số liệu fixture để chốt quyết định cho full-data."""),
        """
from src.utils.config import load_config, resolve_paths, validate_config, describe_config_status

cfg = load_config(str(PROJECT_ROOT / "configs"))
validate_config(cfg)

_cfg_rows = describe_config_status(cfg)
_df_cfg = pd.DataFrame(_cfg_rows)
print("--- BẢNG 00-B: TRẠNG THÁI CẤU HÌNH NGHIÊN CỨU ---")
print(_df_cfg[["field", "value", "type", "status", "note"]].to_string(index=False))
_n_required_unset = sum(1 for r in _cfg_rows if r["status"] == "required")
_n_pending = sum(1 for r in _cfg_rows if r["status"] == "pending")
_n_ok = sum(1 for r in _cfg_rows if r["status"] == "ok")
print(f"\\nTóm tắt: {len(_cfg_rows)} trường | ok={_n_ok} | required chưa đạt={_n_required_unset} | pending={_n_pending}")
print(f"Môi trường={cfg['paths']['active_environment']} | runtime.mode={cfg['runtime']['mode']} | seed={cfg['runtime']['random_state']} | mode_strategy={cfg['rq2']['mode_strategy']}")
print(f"DuckDB: threads={cfg['runtime']['duckdb']['threads']}, memory_limit={cfg['runtime']['duckdb']['memory_limit']}")
if _n_required_unset > 0:
    _unset = [r["field"] for r in _cfg_rows if r["status"] == "required"]
    raise RuntimeError(
        f"{_n_required_unset} trường bắt buộc chưa được đặt: {_unset}. "
        "Sửa file tương ứng trong configs/ rồi chạy lại cell này."
    )
""",
        ("markdown", r"""### 3. Phân giải đường dẫn và kiểm tra nơi lưu trữ

Mỗi loại artifact có một đường dẫn canonical. Cell này tạo thư mục còn thiếu, kiểm tra quyền ghi từng nơi và thống kê raw hiện có mà không sửa, xóa hoặc giải nén dữ liệu.

**Invariant:** mọi thư mục bắt buộc phải ghi được. Việc chưa có raw ở Notebook 00 là trạng thái thông tin, không phải bằng chứng nguồn đã sẵn sàng; Gate G1 thuộc Notebook 01."""),
        """
paths = resolve_paths(cfg)
required_dirs = [
    ("raw_root", paths.get("raw_root", paths["raw"])),
    ("interim", paths["interim"]),
    ("processed", paths["processed"]),
    ("checkpoints", paths["checkpoints"]),
    ("experiments", paths["experiments"]),
    ("manifests", paths["manifests"]),
    ("models", paths["models"]),
    ("metrics", paths["metrics"]),
    ("logs", paths["logs"]),
    ("tables", paths["tables"]),
    ("figures", paths["figures"]),
    ("appendix", paths["appendix"]),
]

records = []
for name, d_path in required_dirs:
    existed = d_path.exists()
    d_path.mkdir(parents=True, exist_ok=True)
    _can_write = False
    try:
        _t = d_path / ".write_test.tmp"
        _t.write_text("ok", encoding="utf-8")
        _t.unlink()
        _can_write = True
    except Exception:
        pass
    records.append({
        "Thư mục logic": name,
        "Đường dẫn tuyệt đối": str(d_path),
        "Trạng thái ban đầu": "Đã có" if existed else "Mới tạo",
        "Quyền ghi": "Đạt" if _can_write else "Chặn",
    })

_df_dirs = pd.DataFrame(records)
print("--- BẢNG 00-C: ĐƯỜNG DẪN CANONICAL VÀ QUYỀN GHI ---")
print(_df_dirs.to_string(index=False))
_bad_dirs = [r for r in records if r["Quyền ghi"] != "Đạt"]
if _bad_dirs:
    raise RuntimeError(
        "Các thư mục sau không có quyền ghi:\\n"
        + "\\n".join("  " + r["Đường dẫn tuyệt đối"] for r in _bad_dirs)
        + "\\nKhắc phục: kiểm tra quyền Editor trên Drive hoặc chọn lại project root."
    )

_raw_root = paths.get("raw_root", paths["raw"])
_zip_files = list(_raw_root.glob("*.zip")) + list(_raw_root.glob("*/*.zip"))
_csv_files = list(_raw_root.glob("*.csv")) + list(_raw_root.glob("*/*.csv"))
_df_raw_presence = pd.DataFrame([
    {"Loại nguồn": "ZIP", "Số file quan sát": len(_zip_files), "Ý nghĩa": "Nguồn archive; Notebook 01 đọc streaming nếu được cấu hình"},
    {"Loại nguồn": "CSV", "Số file quan sát": len(_csv_files), "Ý nghĩa": "Raw shard; Notebook 01 kiểm kê và xác thực schema"},
])
print("\\n--- BẢNG 00-D: SỰ HIỆN DIỆN CỦA RAW INPUT ---")
print(_df_raw_presence.to_string(index=False))
""",
        ("markdown", r"""### 4. Tài nguyên, phiên bản và snapshot tái lập

Notebook đo tài nguyên của đúng volume đang dùng. Dự trù đĩa là ước lượng vận hành:

$$D_{peak} \approx D_{raw} + D_{staging} + D_{interim} + D_{processed} + D_{spill}.$$

Đây không phải phép đo peak RAM, không phải quota Google Drive và không bảo đảm full-data sẽ vừa bộ nhớ. GPU chỉ được ghi nhận nếu runtime thực sự phát hiện thiết bị; Notebook 00 không dùng GPU để tính toán.

**Cách đọc bảng:** so sánh `Tổng ước tính` với `Đĩa artifacts còn trống`, đồng thời xem cảnh báo spill. Các hệ số dự trù là planning assumption; full run phải ghi actual peak riêng."""),
        """
from src.utils.runtime import check_environment, estimate_disk_budget, save_runtime_snapshot
from src.utils.hashing import hash_file

env_report = check_environment(
    target_dir=str(paths["checkpoints"]),
    min_disk_gb=5.0,
    raise_on_critical=True,
)
_temp_dir = paths.get("temp_dir", paths["logs"] / "temp")
local_report = check_environment(
    target_dir=str(_temp_dir),
    min_disk_gb=25.0,
    raise_on_critical=False,
)

_runtime = env_report["runtime"]
_df_hardware = pd.DataFrame([
    {"Thành phần": "Hệ điều hành", "Giá trị": f"{_runtime['os_name']} {_runtime['os_release']}", "Đơn vị": "-", "Phạm vi": "runtime hiện tại"},
    {"Thành phần": "Python", "Giá trị": _runtime["python_version"], "Đơn vị": "version", "Phạm vi": "runtime hiện tại"},
    {"Thành phần": "CPU logic", "Giá trị": _runtime["cpu_count_logical"], "Đơn vị": "core", "Phạm vi": "runtime hiện tại"},
    {"Thành phần": "RAM khả dụng", "Giá trị": _runtime.get("available_ram_gb", "N/A"), "Đơn vị": "GB", "Phạm vi": "thời điểm kiểm tra"},
    {"Thành phần": "RAM tổng", "Giá trị": _runtime.get("total_ram_gb", "N/A"), "Đơn vị": "GB", "Phạm vi": "runtime hiện tại"},
    {"Thành phần": "Đĩa artifacts còn trống", "Giá trị": env_report["free_disk_gb"], "Đơn vị": "GB", "Phạm vi": "volume artifacts, không phải Drive quota"},
    {"Thành phần": "Đĩa spill còn trống", "Giá trị": local_report["free_disk_gb"], "Đơn vị": "GB", "Phạm vi": "volume temp/spill"},
    {"Thành phần": "CUDA khả dụng", "Giá trị": _runtime.get("cuda_available", False), "Đơn vị": "boolean", "Phạm vi": "runtime hiện tại"},
    {"Thành phần": "GPU", "Giá trị": _runtime.get("cuda_device_name") or "Không phát hiện", "Đơn vị": "device", "Phạm vi": "runtime hiện tại"},
    {"Thành phần": "VRAM tổng", "Giá trị": _runtime.get("cuda_vram_gb") or "Không áp dụng", "Đơn vị": "GB", "Phạm vi": "runtime hiện tại"},
])
print("--- BẢNG 00-E: TÀI NGUYÊN PHẦN CỨNG QUAN SÁT ĐƯỢC ---")
print(_df_hardware.to_string(index=False))
if local_report["warnings"]:
    print(f"Cảnh báo spill: {local_report['warnings']}")
    print(f"Cách khắc phục: {local_report.get('remediation', [])}")

_pkgs = _runtime.get("packages", {})
_df_packages = pd.DataFrame([{"Package": name, "Phiên bản": version} for name, version in _pkgs.items()])
print("\\n--- BẢNG 00-F: PHIÊN BẢN THƯ VIỆN ---")
print(_df_packages.to_string(index=False))

_budget = estimate_disk_budget(_raw_root)
_df_budget = pd.DataFrame([
    {"Thành phần": "Raw hiện có", "Dung lượng ước tính (GB)": _budget["raw_gb"], "Loại": "quan sát từ file"},
    {"Thành phần": "Staging shards", "Dung lượng ước tính (GB)": _budget["staging_gb"], "Loại": "ước lượng"},
    {"Thành phần": "Interim", "Dung lượng ước tính (GB)": _budget["interim_gb"], "Loại": "ước lượng"},
    {"Thành phần": "Processed", "Dung lượng ước tính (GB)": _budget["processed_gb"], "Loại": "ước lượng"},
    {"Thành phần": "DuckDB spill", "Dung lượng ước tính (GB)": _budget["spill_gb"], "Loại": "ước lượng"},
    {"Thành phần": "Tổng peak dự kiến", "Dung lượng ước tính (GB)": _budget["total_estimated_gb"], "Loại": "planning estimate"},
    {"Thành phần": "Đĩa artifacts còn trống", "Dung lượng ước tính (GB)": env_report["free_disk_gb"], "Loại": "quan sát runtime"},
])
print("\\n--- BẢNG 00-G: DỰ TRÙ DUNG LƯỢNG ---")
print(_df_budget.to_string(index=False))
print(f"Giới hạn diễn giải: {_budget['note']}")

_spec_path = PROJECT_ROOT / "PUBG_RESEARCH_SPEC.md"
_plan_path = PROJECT_ROOT / "PUBG_IMPLEMENTATION_PLAN.md"
_doc_hashes = {}
for _doc_name, _doc_path in [("PUBG_RESEARCH_SPEC.md", _spec_path), ("PUBG_IMPLEMENTATION_PLAN.md", _plan_path)]:
    if _doc_path.is_file():
        _doc_hashes[_doc_name] = hash_file(_doc_path)
    else:
        _doc_hashes[_doc_name] = "not_found_at_" + str(_doc_path)
_gen_hash = hash_file(PROJECT_ROOT / "src" / "utils" / "generate_notebooks.py")
_snapshot_path = paths["manifests"] / "runtime_snapshot.json"
_snapshot = save_runtime_snapshot(_snapshot_path, PROJECT_ROOT, cfg, _doc_hashes)
print(f"\\nSnapshot tái lập đã lưu: {_snapshot_path}")
print(f"Đã băm {len(_snapshot['source_hashes'])} module Python; generator SHA256={_gen_hash[:16]}...")
""",
        ("markdown", r"""### 5. Trạng thái checkpoint và quan hệ phụ thuộc

Checkpoint là bằng chứng một stage đã hoàn tất với artifact cụ thể, không chỉ là tên file còn tồn tại. Bảng DAG cho biết stage, chữ ký, thời điểm và số artifact; bảng 13 notebook giúp thành viên mới biết chính xác điểm tiếp tục.

**Cách đọc:** `completed` chỉ hợp lệ khi artifact và checksum còn tương thích. `running`, `failed`, `blocked`, `invalidated_stale` hoặc `not_started` không được dùng như đầu vào hoàn tất."""),
        """
from src.data.checkpoints import CheckpointManager

ckpt_mgr = CheckpointManager(manifest_path=paths["checkpoints"] / "checkpoint_manifest.json")
manifest = ckpt_mgr.load_manifest()
stages = manifest.get("stages", {})
_ckpt_rows = []
for _stage_name, _stage_info in stages.items():
    _ckpt_rows.append({
        "Stage": _stage_name,
        "Trạng thái": _stage_info.get("status", "unknown"),
        "Chữ ký": _stage_info.get("signature", "")[:12] + "...",
        "Hoàn tất lúc": _stage_info.get("completed_at", "-"),
        "Số artifact": len(_stage_info.get("artifacts", {})),
    })
_df_ckpt = pd.DataFrame(_ckpt_rows, columns=["Stage", "Trạng thái", "Chữ ký", "Hoàn tất lúc", "Số artifact"])
print("--- BẢNG 00-H: CHECKPOINT DAG HIỆN TẠI ---")
print(_df_ckpt.to_string(index=False) if not _df_ckpt.empty else "Chưa có checkpoint hoàn tất; đây là clean start.")

_notebook_order = [
    "00_setup.ipynb", "01_download_validate.ipynb", "02_data_quality_and_structure.ipynb",
    "03_build_player_match.ipynb", "04_combat_timing.ipynb", "05_eda.ipynb",
    "06_rq1_analysis.ipynb", "07_rq2_clustering.ipynb", "08_build_historical.ipynb",
    "09_rq3_prediction.ipynb", "10_ablation_error_analysis.ipynb",
    "11_finalize_results.ipynb", "12_final_results_summary.ipynb",
]
_nb_rows = []
for _nb in _notebook_order:
    _info = stages.get("notebook/" + _nb, {})
    _nb_rows.append({
        "Notebook": _nb,
        "Trạng thái": _info.get("status", "not_started"),
        "Hoàn tất lúc": _info.get("completed_at", "-"),
        "Có thể dùng tiếp": "Có" if _info.get("status") == "completed" else "Không",
    })
_df_notebooks = pd.DataFrame(_nb_rows)
print("\\n--- BẢNG 00-I: TRẠNG THÁI 13 NOTEBOOK ---")
print(_df_notebooks.to_string(index=False))
""",
        ("markdown", r"""### 6. Kết luận vận hành, giới hạn và bàn giao

Notebook 00 chỉ kết luận **môi trường hiện tại đủ điều kiện bắt đầu ingest** khi mọi kiểm tra chặn đạt. Nó không kết luận dữ liệu đã đầy đủ, đơn vị đã xác minh, RAM đủ cho full-data, Drive còn bao nhiêu quota hoặc GPU sẽ làm mọi bước nhanh hơn.

Không vẽ biểu đồ ở notebook này vì các quan hệ cần kiểm tra là trạng thái và đường dẫn rời rạc; bảng expected/actual truyền đạt chính xác hơn. Biểu đồ tài nguyên chỉ được bổ sung khi có chuỗi đo theo thời gian hoặc nhiều runtime để so sánh.

Bảng nghiệm thu dưới đây là nguồn đọc nhanh. Sau khi cell kết thúc, wrapper chung sẽ commit `runtime_snapshot.json`, ghi handover và đổi checkpoint Notebook 00 thành `completed`."""),
        """
_snapshot_exists = _snapshot_path.is_file()
_dirs_ok = not _bad_dirs
_gate_checks = [
    {"Kiểm tra": "Đúng project root", "Kỳ vọng": "Marker đầy đủ", "Thực tế": "Đạt", "Mức": "Chặn", "Kết luận": "Đạt"},
    {"Kiểm tra": "Quyền ghi root", "Kỳ vọng": "Có", "Thực tế": "Có" if _root_writable else "Không", "Mức": "Chặn", "Kết luận": "Đạt" if _root_writable else "Không đạt"},
    {"Kiểm tra": "Config required", "Kỳ vọng": "0 trường chưa đặt", "Thực tế": str(_n_required_unset), "Mức": "Chặn", "Kết luận": "Đạt" if _n_required_unset == 0 else "Không đạt"},
    {"Kiểm tra": "Config pending", "Kỳ vọng": "Có lý do và gate sau", "Thực tế": str(_n_pending), "Mức": "Thông tin", "Kết luận": "Theo dõi" if _n_pending else "Đạt"},
    {"Kiểm tra": "Đường dẫn canonical", "Kỳ vọng": "Tất cả ghi được", "Thực tế": f"{len(required_dirs) - len(_bad_dirs)}/{len(required_dirs)}", "Mức": "Chặn", "Kết luận": "Đạt" if _dirs_ok else "Không đạt"},
    {"Kiểm tra": "Runtime snapshot", "Kỳ vọng": "Ghi và đọc được", "Thực tế": str(_snapshot_path), "Mức": "Chặn", "Kết luận": "Đạt" if _snapshot_exists else "Không đạt"},
    {"Kiểm tra": "Raw input", "Kỳ vọng": "Không bắt buộc tại NB00", "Thực tế": f"ZIP={len(_zip_files)}, CSV={len(_csv_files)}", "Mức": "Thông tin", "Kết luận": "Kiểm tra ở NB01"},
]
_df_gate = pd.DataFrame(_gate_checks)
print("--- BẢNG 00-J: EXPECTED / ACTUAL VÀ ĐIỀU KIỆN CHUYỂN BƯỚC ---")
print(_df_gate.to_string(index=False))
_blocking_ok = all(row["Kết luận"] == "Đạt" for row in _gate_checks if row["Mức"] == "Chặn")
if not _blocking_ok:
    raise RuntimeError("Notebook 00 còn kiểm tra chặn chưa đạt; không mở Notebook 01.")

try:
    _snapshot_display_path = str(_snapshot_path.relative_to(PROJECT_ROOT))
except ValueError:
    _snapshot_display_path = str(_snapshot_path)
_df_handover = pd.DataFrame([{
    "Stage": "00_setup.ipynb",
    "Phạm vi": "Môi trường/cấu hình; chưa có cohort hoặc metric",
    "Input": "10 YAML + code + research spec + implementation plan",
    "Output canonical": _snapshot_display_path,
    "Phiên bản": _pubg_signature[:12] + "...",
    "Trạng thái": "Sẵn sàng commit sau cell",
    "Consumer": "01_download_validate.ipynb",
    "Điều kiện tiếp tục": "Bảng 00-J không có mục Chặn/Không đạt",
}])
print("\\n--- BẢNG 00-K: BÀN GIAO NOTEBOOK 00 ---")
print(_df_handover.to_string(index=False))
print("\\nNotebook 00 đủ điều kiện vận hành. Tiếp theo: mở 01_download_validate.ipynb; Notebook 01 phải tự xác minh Gate G1.")
""",
    ],
)
# 01_download_validate.ipynb
create_notebook(
    "01_download_validate.ipynb",
    "01 — Nạp dữ liệu, kiểm kê shard và xác thực schema",
    "Đọc toàn bộ shard aggregate/event theo batch, bảo toàn raw, đối soát dòng và xuất provenance/schema/parse manifests có thể kiểm chứng tại Gate G1.",
    [
        ("markdown", r"""### 0. Bối cảnh khoa học, phạm vi và tiêu chí thành công

Notebook 01 là **cổng nguồn dữ liệu G1**, chưa trả lời trực tiếp RQ1-RQ3. Nhiệm vụ là chứng minh raw được nhận diện, băm, đọc và chuyển kiểu có kiểm soát trước khi làm sạch hoặc xây đặc trưng.

Các câu hỏi kiểm tra:

1. Mọi shard aggregate và deaths theo pattern cấu hình có được kiểm kê với byte, số dòng và checksum không?
2. Schema bắt buộc, cột tùy chọn và alias có hợp lệ trên từng shard không?
3. Missing gốc có được tách khỏi lỗi parse; lỗi parse có được giữ thành null và kiểm toán thay vì làm mất dòng không?
4. Đối soát có thỏa $N_{read}=N_{saved}+N_{dropped}$ không?
5. Artifact typed và manifest có đủ để phiên khác resume mà không sửa raw không?

**Input:** raw CSV/ZIP hoặc URL công khai theo configs/data.yaml; schema và đơn vị ứng viên theo configs/schema.yaml; batch_rows của phiên chạy. Phạm vi là toàn bộ shard phát hiện được, không lấy mẫu.

**Output:** typed Parquet theo shard, batch_manifest.json, source_inventory.json, schema_report.json, schema_parse_report.json và hai hình kiểm toán.

**Tiêu chí G1:** ingest hoàn tất; mọi shard hợp lệ; đối soát dòng đạt; bốn manifest cốt lõi tồn tại và đọc được. Đơn vị candidate vẫn là pending nếu chưa có bằng chứng nguồn, nên notebook không tự đổi đơn vị."""),
        ("markdown", r"""### 1. Phương pháp ingest, bảo toàn raw và resume

Cell này phát hiện shard bằng pattern cấu hình, đọc CSV theo batch và ghi Parquet ZSTD vào staging. Raw là dữ liệu bất biến: notebook không sửa, đổi tên hoặc xóa CSV/ZIP. Một shard chỉ được tái sử dụng khi định danh nguồn, checksum, byte, số dòng và artifact staged còn tương thích; nếu không, đúng shard đó được xử lý lại.

PUBG_BATCH_ROWS chỉ điều khiển kích thước batch, không thay đổi cohort. Giá trị mặc định là 50.000 dòng. Resume diễn ra theo shard đã xác minh, không dựa vào việc file cùng tên tình cờ tồn tại.

**Missing policy:** chuỗi thiếu gốc được ghi là original_missing; giá trị không thiếu nhưng không ép được về kiểu đích được ghi là parse_error và giữ thành null. Cả hai không bị tính thành dòng bị loại tại ingest.

**Điều kiện chặn:** thiếu shard, schema sai, alias collision, staged file hỏng hoặc đối soát không đạt phải dừng trước G1."""),
        """
import sys
from pathlib import Path
import pandas as pd
PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths, validate_config
from src.data.io import get_duckdb_connection, atomic_write_json, read_json
from src.data.batch_ingest import ingest_sources, finalize_ingest
from src.data.inventory import inventory_sources, update_inventory_with_staged_counts
from src.data.checkpoints import CheckpointManager

cfg = load_config(str(PROJECT_ROOT / "configs"))
validate_config(cfg)
paths = resolve_paths(cfg)
con = get_duckdb_connection(
    temp_dir=paths["temp_dir"],
    **{k: cfg["runtime"]["duckdb"][k] for k in ("memory_limit", "threads")},
)
ckpt_mgr = CheckpointManager(manifest_path=paths["checkpoints"] / "checkpoint_manifest.json")
staging_dir = paths["interim"] / "staging_shards"
_batch_rows = globals().get("PUBG_BATCH_ROWS", 50000)

batch_manifest = ingest_sources(
    con, paths["raw_root"], staging_dir, cfg["data"], cfg["schema"],
    batch_rows=_batch_rows,
    work_dir=paths["temp_dir"] / "batch_ingest",
    manifests_dir=paths["manifests"],
)
batch_manifest = finalize_ingest(
    con, paths["raw_root"], staging_dir, cfg["data"], cfg["schema"],
    batch_rows=_batch_rows,
    work_dir=paths["temp_dir"] / "batch_ingest",
    manifests_dir=paths["manifests"],
)
_staging_rows = [{
    "Shard": s.get("source"),
    "Loại": s.get("kind"),
    "Số dòng": s.get("rows"),
    "Số batch": s.get("batches"),
    "Trạng thái": s.get("status", "completed"),
    "Typed Parquet": s.get("file"),
} for s in batch_manifest.get("shards", [])]
print("--- BẢNG 01-A: TRẠNG THÁI STAGING THEO SHARD ---")
print(pd.DataFrame(_staging_rows).to_string(index=False))
print(f"\\nPhạm vi: toàn bộ {len(_staging_rows)} shard phát hiện được; batch_rows={_batch_rows:,}; không lấy mẫu.")
""",
        ("markdown", r"""### 2. Provenance, inventory và đối soát dòng

source_inventory.json là hồ sơ provenance của raw, không phải bản sao batch manifest. Bảng 01-B1 ghi metadata đúng như cấu hình; trường chưa biết giữ pending, không suy đoán version hoặc ngày tải từ thời gian sửa file. Bảng 01-B2 ghi từng shard, checksum nguồn và typed artifact.

Đối soát dùng công thức:

$$N_{read}=N_{saved}+N_{dropped}$$

Trong chính sách ingest hiện tại, mọi record CSV đọc được đều được giữ; ô parse lỗi trở thành null và được đếm riêng. Vì vậy kỳ vọng $N_{dropped}=0$, nhưng điều này không có nghĩa dữ liệu không có missing hoặc parse error."""),
        """
if "batch_manifest" not in globals():
    batch_manifest = read_json(staging_dir / "batch_manifest.json")
if not batch_manifest.get("complete"):
    raise RuntimeError("Notebook 01 ingest chưa hoàn tất; không được công bố Gate G1.")

source_inventory = inventory_sources(
    raw_root=paths["raw_root"],
    agg_patterns=cfg["data"]["discovery"]["agg_patterns"],
    kill_patterns=cfg["data"]["discovery"]["kill_patterns"],
    con=con,
    compute_hash=True,
    data_cfg=cfg["data"],
)
source_inventory = update_inventory_with_staged_counts(source_inventory, batch_manifest)
source_inventory["row_reconciliation"] = batch_manifest["row_reconciliation"]
atomic_write_json(paths["manifests"] / "source_inventory.json", source_inventory)

schema_report = read_json(paths["manifests"] / "schema_report.json")
parse_report = read_json(paths["manifests"] / "schema_parse_report.json")
if not schema_report.get("all_shards_valid"):
    raise RuntimeError("Schema có shard không hợp lệ. Sửa nguồn hoặc schema trước khi tiếp tục.")
if not batch_manifest["row_reconciliation"].get("is_reconciled"):
    raise RuntimeError("Đối soát dòng không đạt. Không được tiếp tục sang Notebook 02.")

_source_info = source_inventory.get("source_info", {})
_provenance_rows = [{
    "Tập dữ liệu": _source_info.get("dataset_name"),
    "Slug": _source_info.get("dataset_slug"),
    "Nguồn URL": _source_info.get("source_url") or "pending/nguồn local",
    "Phiên bản": _source_info.get("version") if _source_info.get("version") is not None else "pending",
    "Ngày tải": _source_info.get("download_date") or "pending",
    "Định dạng lưu": _source_info.get("storage_format"),
    "Raw root": source_inventory.get("raw_root"),
    "Phạm vi": "toàn bộ shard phát hiện được",
}]
print("--- BẢNG 01-B1: PROVENANCE NGUỒN RAW ---")
print(pd.DataFrame(_provenance_rows).to_string(index=False))

shard_rows = []
for kind, key in (("aggregate", "aggregate_shards"), ("deaths", "death_shards")):
    for shard in source_inventory.get(key, []):
        shard_rows.append({
            "kind": kind,
            "source": shard.get("relative_path"),
            "bytes": shard.get("byte_size"),
            "source_checksum": shard.get("checksum") or shard.get("sha256"),
            "algorithm": shard.get("checksum_algorithm"),
            "rows": shard.get("row_count"),
            "status": shard.get("status"),
            "typed_file": shard.get("staged_file"),
        })
_df_inventory = pd.DataFrame(shard_rows).rename(columns={
    "kind": "Loại", "source": "Nguồn raw", "bytes": "Kích thước (byte)",
    "source_checksum": "Checksum nguồn", "algorithm": "Thuật toán",
    "rows": "Số dòng", "status": "Trạng thái", "typed_file": "Typed Parquet",
})
print("\\n--- BẢNG 01-B2: SOURCE INVENTORY THEO SHARD ---")
print(_df_inventory.to_string(index=False))

_reconciliation = batch_manifest["row_reconciliation"]
_df_reconciliation = pd.DataFrame([{
    "N đọc": _reconciliation.get("rows_read"),
    "N lưu": _reconciliation.get("rows_saved"),
    "N loại": _reconciliation.get("rows_dropped"),
    "Ô parse lỗi giữ null": _reconciliation.get("parse_error_cells_retained_as_null"),
    "Ô missing gốc": _reconciliation.get("original_missing_cells"),
    "N đọc = N lưu + N loại": _reconciliation.get("is_reconciled"),
    "Chính sách": _reconciliation.get("policy"),
}])
print("\\n--- BẢNG 01-C: ĐỐI SOÁT DÒNG ---")
print(_df_reconciliation.to_string(index=False))
print("Cách đọc: tổng dòng tính theo record; missing/parse tính theo ô và không cộng vào số dòng bị loại.")
""",
        ("markdown", r"""### 3. Schema, alias, missing/parse và bằng chứng đơn vị

Schema được kiểm tra riêng trên từng shard. missing_required hoặc alias_collisions là lỗi chặn; optional_missing chỉ vô hiệu hóa khả năng phụ thuộc cột đó. Notebook không tự ánh xạ alias mơ hồ.

Bảng 01-E dùng mẫu số total_rows của từng cột: $missing\\_rate=original\\_missing/total\\_rows$ và $parse\\_error\\_rate=parse\\_errors/total\\_rows$. Ví dụ parse được giới hạn trong manifest để tránh xuất dữ liệu định danh không cần thiết.

Đơn vị chỉ được gọi là verified khi có bằng chứng trong schema contract. candidate_unit là giả thuyết kỹ thuật, không phải giấy phép đổi đơn vị hoặc diễn giải ý nghĩa nghiên cứu."""),
        """
schema_rows = []
for kind, table in schema_report.get("tables", {}).items():
    for source_name, result in table.get("shards", {}).items():
        schema_rows.append({
            "kind": kind,
            "source": source_name,
            "valid": result.get("is_valid"),
            "missing_required": ", ".join(result.get("missing_required", [])) or "-",
            "alias_collisions": str(result.get("alias_collisions", {})) if result.get("alias_collisions") else "-",
            "optional_missing": ", ".join(result.get("optional_missing", [])) or "-",
            "actual_columns": len(result.get("actual_columns", [])),
        })
_df_schema = pd.DataFrame(schema_rows).rename(columns={
    "kind": "Loại", "source": "Shard", "valid": "Hợp lệ",
    "missing_required": "Thiếu cột bắt buộc", "alias_collisions": "Xung đột alias",
    "optional_missing": "Thiếu cột tùy chọn", "actual_columns": "Số cột thực tế",
})
print("--- BẢNG 01-D: SCHEMA KỲ VỌNG VÀ THỰC TẾ THEO SHARD ---")
print(_df_schema.to_string(index=False))

parse_rows = [{"column": column, **stats} for column, stats in parse_report.get("column_summary", {}).items()]
_df_parse = pd.DataFrame(parse_rows).drop(columns=["sample_parse_errors"], errors="ignore").rename(columns={
    "column": "Cột", "total_rows": "Mẫu số ô", "valid": "Ô hợp lệ",
    "original_missing": "Missing gốc", "parse_errors": "Lỗi parse",
    "missing_rate": "Tỷ lệ missing", "parse_error_rate": "Tỷ lệ parse lỗi",
})
print("\\n--- BẢNG 01-E: MISSING GỐC VÀ LỖI PARSE THEO CỘT ---")
print(_df_parse.to_string(index=False))

unit_rows = []
for kind, table in schema_report.get("tables", {}).items():
    for column, unit in table.get("candidate_units", {}).items():
        unit_rows.append({
            "Loại": kind,
            "Cột": column,
            "Đơn vị ứng viên": unit,
            "Trạng thái xác minh": table.get("units_verification_status"),
            "Bằng chứng": table.get("units_evidence") or "pending",
        })
_df_units = pd.DataFrame(unit_rows)
print("\\n--- BẢNG 01-F: TRẠNG THÁI ĐƠN VỊ VÀ BẰNG CHỨNG ---")
print(_df_units.to_string(index=False))
""",
        ("markdown", r"""### 4. Trực quan kiểm toán nguồn và lỗi chuyển kiểu

Hình V01-01 so sánh quy mô từng shard bằng hai đại lượng khác đơn vị: số dòng và byte raw. Hình V01-02 so sánh số ô missing gốc với số ô parse lỗi theo cột. Cả hai dùng toàn bộ shard/cột của lần chạy, không lấy mẫu và không dùng để suy luận nhân quả.

**Cách đọc V01-01:** thanh dài hơn nghĩa là shard có nhiều record hoặc byte hơn; hai panel không được so độ dài trực tiếp vì khác đơn vị. Chênh lệch không tự chứng minh shard thiếu hoặc hỏng.

**Cách đọc V01-02:** hai loại ô lỗi đặt cạnh nhau theo cột. Giá trị 0 chỉ nói không quan sát lỗi trong phạm vi nguồn hiện tại, không bảo đảm nguồn tương lai sạch."""),
        """
import matplotlib.pyplot as plt
from IPython.display import display

_plot_inventory = pd.DataFrame(shard_rows)
if _plot_inventory.empty:
    raise RuntimeError("Không có shard để trực quan hóa; Gate G1 không thể hoàn tất.")
_plot_inventory["label"] = _plot_inventory["kind"] + ":" + _plot_inventory["source"].map(lambda value: Path(str(value)).name)
_plot_inventory = _plot_inventory.sort_values(["kind", "source"]).reset_index(drop=True)

_fig_shards = paths["figures"] / "nb01_shard_scale.png"
_fig_shards.parent.mkdir(parents=True, exist_ok=True)
fig, axes = plt.subplots(2, 1, figsize=(11, max(6, 0.55 * len(_plot_inventory) + 3)), constrained_layout=True)
axes[0].barh(_plot_inventory["label"], _plot_inventory["rows"], color="#35618D", edgecolor="black")
axes[0].set_title("Số dòng theo shard")
axes[0].set_xlabel("Số dòng (record)")
axes[0].set_ylabel("Shard")
axes[0].grid(axis="x", alpha=0.25)
axes[1].barh(_plot_inventory["label"], _plot_inventory["bytes"], color="#C77832", edgecolor="black", hatch="//")
axes[1].set_title("Kích thước raw theo shard")
axes[1].set_xlabel("Kích thước (byte)")
axes[1].set_ylabel("Shard")
axes[1].grid(axis="x", alpha=0.25)
fig.suptitle(f"V01-01 — Quy mô {len(_plot_inventory)} shard raw; toàn bộ nguồn phát hiện được")
fig.savefig(_fig_shards, dpi=160, bbox_inches="tight")
display(fig)
plt.close(fig)
print(f"HÌNH V01-01 đã lưu: {_fig_shards}")
print("Nguồn: Bảng 01-B2. Scope: toàn bộ shard; N shard=" + str(len(_plot_inventory)) + "; không lấy mẫu.")

_plot_parse = pd.DataFrame(parse_rows)
if _plot_parse.empty:
    raise RuntimeError("Parse report không có cột để trực quan hóa; kiểm tra schema report.")
_plot_parse["audit_cells"] = _plot_parse["original_missing"] + _plot_parse["parse_errors"]
_plot_parse = _plot_parse.sort_values(["audit_cells", "column"], ascending=[False, True])
_fig_parse = paths["figures"] / "nb01_missing_vs_parse.png"
fig, ax = plt.subplots(figsize=(12, max(5, 0.38 * len(_plot_parse) + 2)), constrained_layout=True)
_positions = list(range(len(_plot_parse)))
_width = 0.38
ax.barh([p - _width / 2 for p in _positions], _plot_parse["original_missing"], height=_width,
        label="Missing gốc", color="#35618D", edgecolor="black")
ax.barh([p + _width / 2 for p in _positions], _plot_parse["parse_errors"], height=_width,
        label="Lỗi parse", color="#C77832", edgecolor="black", hatch="//")
ax.set_yticks(_positions, _plot_parse["column"])
ax.invert_yaxis()
ax.set_xlabel("Số ô")
ax.set_ylabel("Cột")
ax.set_title(f"V01-02 — Missing gốc và lỗi parse; {parse_report.get('total_rows', 0):,} record qua {parse_report.get('total_shards', 0)} shard")
ax.legend()
ax.grid(axis="x", alpha=0.25)
fig.savefig(_fig_parse, dpi=160, bbox_inches="tight")
display(fig)
plt.close(fig)
print(f"HÌNH V01-02 đã lưu: {_fig_parse}")
print("Nguồn: Bảng 01-E. Scope: toàn bộ cột đã parse; đơn vị=số ô; không lấy mẫu.")
""",
        ("markdown", r"""### 5. Gate G1, diễn giải khoa học, giới hạn và bàn giao

Gate G1 chỉ xác nhận nguồn đã được ingest và kiểm toán theo contract hiện tại. Nó không chứng minh dữ liệu đại diện cho toàn bộ người chơi PUBG, không xác nhận quan hệ nhân quả, không thay thế làm sạch ở Notebook 02 và không bảo đảm RAM/đĩa của mọi Colab đủ cho full-data.

Các giới hạn phải giữ khi bàn giao:

- Version/ngày tải/metadata nguồn còn pending nếu không có bằng chứng trực tiếp.
- Đơn vị ứng viên chưa được đổi hoặc diễn giải như đơn vị đã xác minh.
- Missing và parse error mô tả đúng nguồn hiện tại; dữ liệu mới phải chạy lại audit.
- Hình là kiểm toán mô tả trên toàn bộ shard/cột, không phải kết quả RQ.

Cell cuối kiểm tra expected/actual, commit checkpoint schema cốt lõi và render bảng artifact. Wrapper chung sau đó commit checkpoint notebook gồm hai PNG và ghi handover canonical."""),
        """
_manifest_paths = {
    "batch_manifest": staging_dir / "batch_manifest.json",
    "source_inventory": paths["manifests"] / "source_inventory.json",
    "schema_report": paths["manifests"] / "schema_report.json",
    "parse_report": paths["manifests"] / "schema_parse_report.json",
}
_gate_rows = [
    {"Kiểm tra": "Ingest hoàn tất", "Kỳ vọng": "complete=True", "Thực tế": batch_manifest.get("complete"), "Kết luận": "Đạt" if batch_manifest.get("complete") else "Không đạt"},
    {"Kiểm tra": "Schema mọi shard", "Kỳ vọng": "all_shards_valid=True", "Thực tế": schema_report.get("all_shards_valid"), "Kết luận": "Đạt" if schema_report.get("all_shards_valid") else "Không đạt"},
    {"Kiểm tra": "Đối soát dòng", "Kỳ vọng": "N đọc=N lưu+N loại", "Thực tế": _reconciliation.get("is_reconciled"), "Kết luận": "Đạt" if _reconciliation.get("is_reconciled") else "Không đạt"},
    {"Kiểm tra": "Manifest cốt lõi", "Kỳ vọng": "4/4 tồn tại", "Thực tế": f"{sum(path.is_file() for path in _manifest_paths.values())}/4", "Kết luận": "Đạt" if all(path.is_file() for path in _manifest_paths.values()) else "Không đạt"},
    {"Kiểm tra": "Hình kiểm toán", "Kỳ vọng": "2/2 PNG tồn tại", "Thực tế": f"{sum(path.is_file() for path in (_fig_shards, _fig_parse))}/2", "Kết luận": "Đạt" if _fig_shards.is_file() and _fig_parse.is_file() else "Không đạt"},
]
_df_gate = pd.DataFrame(_gate_rows)
print("--- BẢNG 01-G: EXPECTED / ACTUAL CỦA GATE G1 ---")
print(_df_gate.to_string(index=False))
if any(row["Kết luận"] != "Đạt" for row in _gate_rows):
    raise RuntimeError("Gate G1 chưa đạt; sửa mục Không đạt trước khi mở Notebook 02.")

ckpt_mgr.commit("schema", "schema_batch_v2", _manifest_paths)
_handover_rows = []
for _name, _path in {**_manifest_paths, "shard_scale_figure": _fig_shards, "missing_parse_figure": _fig_parse}.items():
    try:
        _relative = str(_path.relative_to(PROJECT_ROOT))
    except ValueError:
        _relative = str(_path)
    _handover_rows.append({
        "Artifact": _name,
        "Đường dẫn": _relative,
        "SHA256": hash_file(_path)[:16] + "...",
        "Trạng thái": "Sẵn sàng",
        "Consumer": "02_data_quality_and_structure.ipynb" if _name in _manifest_paths else "Báo cáo kiểm toán NB01",
    })
print("\\n--- BẢNG 01-H: ARTIFACT VÀ BÀN GIAO ---")
print(pd.DataFrame(_handover_rows).to_string(index=False))
print("\\nGate G1 hoàn tất. Resume point: mở Notebook 02, chạy cell storage, Bootstrap và cell khởi tạo; không ingest lại shard còn tương thích.")
"""
    ]
)
# 02_data_quality_and_structure.ipynb
create_notebook(
    "02_data_quality_and_structure.ipynb",
    "02 — Chất lượng dữ liệu, roster, chronology và khóa split",
    "Kiểm toán identity, làm sạch không đếm trùng, xây roster, phân cấp chronology và khóa split cô lập theo trận tại Gate G2.",
    [
        ("markdown", r"""### 0. Bối cảnh khoa học, phạm vi và tiêu chí thành công

Notebook 02 là **cổng chất lượng dữ liệu và phân chia G2**. Đây là stage tiền xử lý và diagnostics; notebook chưa trả lời RQ1-RQ3 và không được dùng test split để chọn feature, threshold, K hoặc model.

Các câu hỏi kiểm tra:

1. Identity người chơi-trận có được chuẩn hóa mà vẫn giữ raw lineage; exact duplicate có được tách khỏi conflict cùng khóa khác nội dung không?
2. Removal cascade có thỏa $N_0-\sum_iR_i=N_{clean}$ mà không cộng các cờ lỗi chồng lặp không?
3. Một target lỗi có chỉ loại dòng khỏi task tương ứng, thay vì xóa dòng khỏi mọi phân tích không?
4. Roster và metadata trong cùng trận có đầy đủ, nhất quán hay có conflict cần công bố?
5. Timestamp hỗ trợ Grade A, B hay C; cùng ngày/tie có được giữ nguyên khối khi split không?
6. Mọi match có nằm đúng một split và ba tập có giao nhau bằng 0 không?

**Input:** typed aggregate Parquet và manifests đã qua G1; cấu hình split trong configs/rq3.yaml; seed trong configs/runtime.yaml. Phạm vi là toàn bộ aggregate shard staged, không lấy mẫu.

**Output:** cleaned aggregate, identity conflicts, error flags, removal ledger, task-exclusion ledger, match metadata/audit, chronology report, split assignments/manifest và các hình kiểm toán.

**Tiêu chí G2:** đối soát dòng đạt; conflict được lưu riêng; metadata và chronology có bằng chứng; split ratio đã được chốt rõ trong config; match isolation và chronology boundary đạt; mọi artifact được ghi, băm và checkpoint."""),
        ("markdown", r"""### 1. Tiền điều kiện, provenance và trạng thái quyết định split

Cell này chỉ đọc output canonical của Notebook 01. Nếu không có aggregate Parquet hoặc checkpoint G1 chưa hoàn tất, notebook dừng trước khi tạo output mới.

Exact split proportions là quyết định nghiên cứu chưa được phép suy đoán. Nếu train_ratio, validation_ratio hoặc test_ratio còn null, các cell cleaning/roster/chronology vẫn cung cấp bằng chứng, nhưng cell split sẽ dừng và yêu cầu nhóm chốt config rồi chạy tiếp từ cell đó. Strategy auto được phân giải: Grade A/B dùng chronological; Grade C dùng group_by_match."""),
        """
import sys
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths, validate_config
from src.data.io import get_duckdb_connection, atomic_write_json, read_json
from src.data.batch_ingest import staged_paths
from src.data.checkpoints import CheckpointManager
from src.utils.hashing import hash_file

cfg = load_config(str(PROJECT_ROOT / "configs"))
validate_config(cfg)
paths = resolve_paths(cfg)
con = get_duckdb_connection(
    temp_dir=paths["temp_dir"],
    **{key: cfg["runtime"]["duckdb"][key] for key in ("memory_limit", "threads")},
)
ckpt_mgr = CheckpointManager(paths["checkpoints"] / "checkpoint_manifest.json")
staging_dir = paths["interim"] / "staging_shards"
agg_shards = staged_paths(staging_dir, "aggregate")
if not agg_shards:
    raise FileNotFoundError(
        f"Không có aggregate Parquet tại {staging_dir}. "
        "Chạy hoàn tất 01_download_validate.ipynb với cùng storage root."
    )
_upstream = ckpt_mgr.load_manifest().get("stages", {}).get("notebook/01_download_validate.ipynb", {})
if _upstream.get("status") != "completed":
    raise RuntimeError("Checkpoint Notebook 01 chưa completed; không được mở Gate G2.")

_source_inventory_path = paths["manifests"] / "source_inventory.json"
_parse_report_path = paths["manifests"] / "schema_parse_report.json"
_source_inventory = read_json(_source_inventory_path)
_parse_report = read_json(_parse_report_path)
_split_cfg = cfg.get("rq3", {}).get("split", {})
_input_rows = sum(int(shard.get("row_count") or 0) for key in ("aggregate_shards",) for shard in _source_inventory.get(key, []))
_df_input = pd.DataFrame([
    {"Thuộc tính": "Checkpoint upstream", "Giá trị": _upstream.get("status"), "Nguồn": "checkpoint manifest", "Trạng thái": "Đạt"},
    {"Thuộc tính": "Aggregate shards", "Giá trị": len(agg_shards), "Nguồn": str(staging_dir), "Trạng thái": "Đạt"},
    {"Thuộc tính": "Aggregate rows", "Giá trị": _input_rows, "Nguồn": "source_inventory.json", "Trạng thái": "Thông tin"},
    {"Thuộc tính": "Parse-error cells", "Giá trị": sum(v.get("parse_errors", 0) for v in _parse_report.get("column_summary", {}).values()), "Nguồn": "schema_parse_report.json", "Trạng thái": "Thông tin"},
    {"Thuộc tính": "Split strategy", "Giá trị": _split_cfg.get("strategy"), "Nguồn": "configs/rq3.yaml", "Trạng thái": "Chờ chronology" if _split_cfg.get("strategy") == "auto" else "Đã cấu hình"},
    {"Thuộc tính": "Split ratios", "Giá trị": [_split_cfg.get("train_ratio"), _split_cfg.get("validation_ratio"), _split_cfg.get("test_ratio")], "Nguồn": "configs/rq3.yaml", "Trạng thái": "Pending" if any(_split_cfg.get(key) is None for key in ("train_ratio", "validation_ratio", "test_ratio")) else "Đã chốt"},
])
print("--- BẢNG 02-A: INPUT, PROVENANCE VÀ TIỀN ĐIỀU KIỆN G2 ---")
print(_df_input.to_string(index=False))
""",
        ("markdown", r"""### 2. Identity, duplicate/conflict và removal cascade

Identity người chơi không được coi là account ID bất biến. Khóa chẩn đoán là cặp normalized (match_id, player_name); dòng thiếu player_name vẫn được giữ cho task cấp dòng/trận nếu các trường khác hợp lệ và dùng source lineage ở stage cần row ID.

Hai khái niệm không được trộn:

- **Exact duplicate:** toàn bộ business columns giống nhau; source_file/source_row không làm hai bản sao trở thành khác dữ liệu. Chỉ một đại diện được giữ.
- **Identity conflict:** cùng normalized key nhưng business values khác nhau. Không lấy first; tất cả bản ghi xung đột được cách ly vào identity_conflicts.parquet cùng raw lineage.

Removal cascade chỉ loại exact duplicate, thiếu match/team key, vi phạm miền của behavior cốt lõi và identity mơ hồ. Missing behavior được giữ để task sau khai báo complete-case hoặc train-only imputation. Survival/placement không hợp lệ được giữ cho task không dùng target đó.

Bảng flags là diagnostics có thể chồng lặp; tổng affected_rows của flags không phải số dòng bị loại. Task exclusions nằm ở ledger riêng."""),
        """
if "audit_and_clean_aggregate_data" not in globals():
    from src.data.cleaning import audit_and_clean_aggregate_data

cleaned_pq = paths["interim"] / "cleaned_aggregate.parquet"
removal_csv = paths["tables"] / "removal_log.csv"
error_flags_csv = paths["tables"] / "error_flags.csv"
identity_conflicts_pq = paths["interim"] / "identity_conflicts.parquet"
task_exclusion_csv = paths["tables"] / "task_exclusion_ledger.csv"

clean_summary = audit_and_clean_aggregate_data(
    con,
    agg_shards,
    cleaned_pq,
    removal_csv,
    error_flags_csv,
    identity_conflicts_pq,
    task_exclusion_csv,
)
df_removal = pd.read_csv(removal_csv)
df_flags = pd.read_csv(error_flags_csv)
df_task_exclusions = pd.read_csv(task_exclusion_csv)

print("--- BẢNG 02-B: REMOVAL CASCADE BEFORE / REMOVED / AFTER ---")
print(df_removal[["step", "rule", "reason", "rows_before", "rows_removed", "rows_after", "example_count", "version"]].to_string(index=False))
print("\\n--- BẢNG 02-C: CỜ LỖI CHỒNG LẶP, KHÔNG DÙNG ĐỂ CỘNG DÒNG LOẠI ---")
print(df_flags.to_string(index=False))
print("\\n--- BẢNG 02-D: TASK-EXCLUSION LEDGER ---")
print(df_task_exclusions.to_string(index=False))

_cleaning_steps = df_removal[
    (df_removal["stage"] == "cleaning")
    & (~df_removal["reason"].isin(["total_dropped_records", "validated_clean_records"]))
]
n0 = int(clean_summary["total_raw_rows"])
n_clean = int(clean_summary["clean_rows"])
sum_removed = int(_cleaning_steps["rows_removed"].sum())
assert n0 - sum_removed == n_clean
assert int(clean_summary["dropped_rows"]) == sum_removed
print(f"\\nĐối soát: {n0:,} - {sum_removed:,} = {n_clean:,} dòng. Flags được báo riêng, không cộng vào phép tính này.")
""",
        ("markdown", r"""### 3. Roster, metadata conflict và tính nhất quán placement trong đội

Metadata được xây trên cleaned rows trước task-specific filtering. Mỗi match lưu observed player/team count, maximum observed placement, missing team-ID rows và số đội có nhiều placement khác nhau.

Canonical date/mode/party_size/game_size chỉ được ghi khi toàn bộ dòng trong match thống nhất. Nếu có conflict, giá trị canonical là null và cờ conflict là true; notebook không dùng MIN hoặc MODE để che bất nhất.

Roster complete yêu cầu ít nhất hai đội, placement quan sát hợp lý so với số đội, không thiếu team ID và không có placement conflict trong cùng đội. Đây là kiểm tra completeness của dữ liệu quan sát, không chứng minh roster nguồn là hoàn hảo."""),
        """
from src.data.match_metadata import build_match_metadata

meta_pq = paths["interim"] / "match_metadata.parquet"
audit_report_json = paths["manifests"] / "match_audit_report.json"
total_matches = build_match_metadata(con, cleaned_pq, meta_pq, audit_report_json)

df_audit = con.execute(\"\"\"
    SELECT
        count(*) AS total_matches,
        count(*) FILTER (WHERE is_roster_complete) AS roster_complete,
        count(*) FILTER (WHERE has_metadata_conflict) AS metadata_conflicts,
        count(*) FILTER (WHERE team_placement_conflict_count > 0) AS placement_conflicts,
        sum(missing_team_id_rows) AS missing_team_id_rows,
        round(avg(observed_player_count), 2) AS avg_players,
        round(avg(observed_team_count), 2) AS avg_teams
    FROM read_parquet(?)
\"\"\", [str(meta_pq)]).df()
df_roster = con.execute(\"\"\"
    SELECT
        observed_team_count AS observed_teams,
        count(*) AS match_count,
        sum(observed_player_count) AS player_rows,
        count(*) FILTER (WHERE is_roster_complete) AS complete_matches
    FROM read_parquet(?)
    GROUP BY observed_team_count
    ORDER BY observed_team_count
\"\"\", [str(meta_pq)]).df()
df_conflicts = con.execute(\"\"\"
    SELECT
        match_id,
        has_date_conflict,
        has_mode_conflict,
        has_party_size_conflict,
        has_game_size_conflict,
        team_placement_conflict_count,
        is_roster_complete
    FROM read_parquet(?)
    WHERE has_metadata_conflict OR team_placement_conflict_count > 0 OR NOT is_roster_complete
    ORDER BY match_id
    LIMIT 20
\"\"\", [str(meta_pq)]).df()

print("--- BẢNG 02-E: TỔNG KẾT ROSTER VÀ METADATA ---")
print(df_audit.to_string(index=False))
print("\\n--- BẢNG 02-F1: PHÂN BỐ SỐ ĐỘI QUAN SÁT ---")
print(df_roster.to_string(index=False))
print("\\n--- BẢNG 02-F2: TỐI ĐA 20 MATCH CÓ CONFLICT/ROSTER CHƯA ĐỦ ---")
print(df_conflicts.to_string(index=False) if not df_conflicts.empty else "Không quan sát conflict hoặc roster chưa đủ trong phạm vi hiện tại.")
print(f"Scope: toàn bộ {total_matches:,} match; Bảng 02-F2 chỉ giới hạn hiển thị, artifact metadata giữ đầy đủ.")
""",
        ("markdown", r"""### 4. Chronology audit và bằng chứng Grade A/B/C

Timestamp được parse và chuẩn hóa UTC. Audit ghi null count, số timestamp/ngày, tie ratio, resolution quan sát, ngày có nhiều match và same-player overlaps. Trường source timestamp semantics và thời điểm statistic sẵn sàng vẫn pending nếu nguồn không có tài liệu trực tiếp.

Grade A cần bằng chứng source về exact intra-day completion order; tie ratio thấp không đủ. Grade B chỉ cho phép lịch sử từ ngày nhỏ hơn ngày hiện tại. Grade C chặn S2/P3 chính thức và chỉ cho retrospective group split.

chronology_report.json là nguồn có thẩm quyền. Config chỉ có thể hạ mức tin cậy, không được nâng grade vượt bằng chứng."""),
        """
from src.analysis.eda import run_chronology_audit

meta_dates = con.execute("SELECT match_id, match_date FROM read_parquet(?)", [str(meta_pq)]).df()
player_times = con.execute(
    "SELECT match_id, player_name, date FROM read_parquet(?)",
    [str(cleaned_pq)],
).df()
chrono_report = run_chronology_audit(
    meta_dates,
    has_exact_order_evidence=False,
    player_match_df=player_times,
    config_grade=cfg["preprocessing"]["chronology"].get("grade_assignment"),
)
chronology_path = paths["manifests"] / "chronology_report.json"
from src.utils.hashing import hash_file
chrono_report["metadata_checksum"] = hash_file(meta_pq)
atomic_write_json(chronology_path, chrono_report)

_chrono_fields = [
    "grade", "evidence_grade", "policy", "historical_modeling_status",
    "total_matches", "total_days_observed", "null_date_count",
    "unique_timestamps", "timestamp_tie_ratio", "observed_resolution_seconds",
    "same_day_multi_match_days", "same_player_timestamp_overlap_count",
    "timezone_normalized", "source_timestamp_semantics", "statistic_availability",
]
df_chronology = pd.DataFrame([
    {"Bằng chứng": field, "Giá trị": chrono_report.get(field)}
    for field in _chrono_fields
])
df_daily = con.execute(\"\"\"
    SELECT cast(match_date AS DATE) AS match_day, count(*) AS match_count
    FROM read_parquet(?)
    WHERE match_date IS NOT NULL
    GROUP BY cast(match_date AS DATE)
    ORDER BY match_day
\"\"\", [str(meta_pq)]).df()

print("--- BẢNG 02-G: CHRONOLOGY EVIDENCE VÀ GRADE ---")
print(df_chronology.to_string(index=False))
print("\\n--- BẢNG 02-H: SỐ MATCH THEO NGÀY UTC ---")
print(df_daily.to_string(index=False) if not df_daily.empty else "Không có ngày hợp lệ; biểu đồ theo ngày là not_applicable và Grade C phải được giữ.")
print(f"Diễn giải: {chrono_report['description']}")
""",
        ("markdown", r"""### 5. Khóa split theo config và chronology

Cell này đọc duy nhất configs/rq3.yaml và runtime.random_state. Không dùng default ratio ẩn. Nếu ratio còn null, dừng ở đây sau khi đã tạo đủ evidence để nhóm chốt quyết định.

Với Grade B, toàn bộ match cùng ngày UTC là một boundary block và không bị xé qua split. Với Grade A, các match có cùng timestamp là một tie block. Với Grade C, strategy auto chuyển sang group_by_match và không được gọi là future prediction.

Invariant bắt buộc:

$$S_{train}\cap S_{validation}=S_{train}\cap S_{test}=S_{validation}\cap S_{test}=\emptyset$$"""),
        """
from src.models.splits import create_split_assignments

_ratio_keys = ("train_ratio", "validation_ratio", "test_ratio")
if any(_split_cfg.get(key) is None for key in _ratio_keys):
    raise RuntimeError(
        "Split ratios còn pending trong configs/rq3.yaml. "
        "Dựa trên Bảng 02-H và chronology report, chốt train_ratio, validation_ratio, test_ratio "
        "sao cho tổng bằng 1; sau đó chạy lại từ cell split. Không dùng default ẩn."
    )
_requested_strategy = _split_cfg.get("strategy", "auto")
if _requested_strategy == "auto":
    split_strategy = "chronological" if chrono_report["grade"] in ("Grade A", "Grade B") else "group_by_match"
else:
    split_strategy = _requested_strategy
if split_strategy == "chronological" and chrono_report["grade"] == "Grade C":
    raise RuntimeError("Grade C không được dùng chronological split chính thức; chọn auto hoặc group_by_match.")

split_ratios = {
    "train": float(_split_cfg["train_ratio"]),
    "validation": float(_split_cfg["validation_ratio"]),
    "test": float(_split_cfg["test_ratio"]),
}
split_seed = int(_split_cfg.get("random_state", cfg["runtime"]["random_state"]))
df_split_config = pd.DataFrame([
    {"Tham số": "strategy configured", "Giá trị": _requested_strategy, "Nguồn": "configs/rq3.yaml"},
    {"Tham số": "strategy resolved", "Giá trị": split_strategy, "Nguồn": "chronology report"},
    {"Tham số": "chronology grade", "Giá trị": chrono_report["grade"], "Nguồn": "chronology_report.json"},
    {"Tham số": "train/validation/test", "Giá trị": str(split_ratios), "Nguồn": "configs/rq3.yaml"},
    {"Tham số": "random_state", "Giá trị": split_seed, "Nguồn": "configs/rq3.yaml"},
])
print("--- BẢNG 02-I: CẤU HÌNH SPLIT ĐƯỢC DÙNG ---")
print(df_split_config.to_string(index=False))

split_pq = paths["interim"] / "split_assignments.parquet"
split_manifest = paths["manifests"] / "split_manifest.json"
split_meta = create_split_assignments(
    con,
    meta_pq,
    split_pq,
    split_manifest,
    strategy=split_strategy,
    train_ratio=split_ratios["train"],
    val_ratio=split_ratios["validation"],
    test_ratio=split_ratios["test"],
    random_state=split_seed,
    chronology_grade=chrono_report["grade"],
)
df_splits = pd.DataFrame([
    {
        "Split": split,
        "Số match": split_meta["match_counts"].get(split, 0),
        "Ước tính player rows": split_meta["estimated_player_counts"].get(split, 0),
        "Tỷ lệ thực tế": split_meta["actual_ratios"].get(split, 0),
        "Ngày bắt đầu": split_meta["date_ranges"].get(split, {}).get("start", "-"),
        "Ngày kết thúc": split_meta["date_ranges"].get(split, {}).get("end", "-"),
    }
    for split in ("train", "validation", "test")
])
df_intersections = pd.DataFrame([
    {"Cặp split": pair, "Số match giao nhau": count}
    for pair, count in split_meta["split_intersections"].items()
])
print("\\n--- BẢNG 02-J1: QUY MÔ VÀ KHOẢNG NGÀY THEO SPLIT ---")
print(df_splits.to_string(index=False))
print("\\n--- BẢNG 02-J2: KIỂM TRA GIAO NHAU VÀ BOUNDARY ---")
print(df_intersections.to_string(index=False))
print(f"Boundary policy={split_meta['boundary_policy']} | tie blocks bị xé={split_meta['tie_blocks_split']}")
assert split_meta["match_isolation_verified"]
assert not split_meta["tie_blocks_split"]
""",
        ("markdown", r"""### 6. Trực quan kiểm toán G2

Bốn hình dưới đây chỉ mô tả full valid scope của stage, không lấy mẫu:

- V02-01: số dòng bị loại và số dòng còn lại sau từng rule; nguồn Bảng 02-B.
- V02-02: phân bố số đội quan sát theo match; nguồn Bảng 02-F1.
- V02-03: số match theo ngày UTC; nguồn Bảng 02-H. Nếu không có ngày hợp lệ, hình là not_applicable và không tạo placeholder.
- V02-04: số match và ước tính player rows theo split trên hai panel khác đơn vị; nguồn Bảng 02-J1.

Cách đọc: thanh removal không được cộng với flags. Roster chart phản ánh dữ liệu quan sát, không phải roster thật tuyệt đối. Daily/split charts mô tả coverage và protocol, không chứng minh xu hướng hành vi hoặc nhân quả."""),
        """
import matplotlib.pyplot as plt
from IPython.display import display

_figures = {}
_fig_removal = paths["figures"] / "nb02_removal_waterfall.png"
_plot_removal = _cleaning_steps.copy()
fig, ax1 = plt.subplots(figsize=(11, 5), constrained_layout=True)
positions = list(range(len(_plot_removal)))
bars = ax1.bar(positions, _plot_removal["rows_removed"], color="#C77832", edgecolor="black", hatch="//", label="Dòng bị loại")
ax1.set_xticks(positions, _plot_removal["rule"] + ": " + _plot_removal["reason"], rotation=20, ha="right")
ax1.set_ylabel("Số dòng bị loại")
ax1.set_title(f"V02-01 — Removal cascade; N ban đầu={n0:,}, N sạch={n_clean:,}")
ax2 = ax1.twinx()
ax2.plot(positions, _plot_removal["rows_after"], color="#35618D", marker="o", label="Dòng còn lại")
ax2.set_ylabel("Số dòng còn lại")
for bar, value in zip(bars, _plot_removal["rows_removed"]):
    ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{int(value):,}", ha="center", va="bottom")
fig.savefig(_fig_removal, dpi=160, bbox_inches="tight")
display(fig)
plt.close(fig)
_figures["removal_waterfall"] = _fig_removal
print(f"HÌNH V02-01: {_fig_removal} | N={n0:,} raw rows | nguồn=Bảng 02-B | không lấy mẫu.")

_fig_roster = paths["figures"] / "nb02_roster_distribution.png"
fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
ax.bar(df_roster["observed_teams"].astype(str), df_roster["match_count"], color="#35618D", edgecolor="black")
ax.set_xlabel("Số đội quan sát trong match")
ax.set_ylabel("Số match")
ax.set_title(f"V02-02 — Phân bố roster; N={total_matches:,} match")
ax.grid(axis="y", alpha=0.25)
fig.savefig(_fig_roster, dpi=160, bbox_inches="tight")
display(fig)
plt.close(fig)
_figures["roster_distribution"] = _fig_roster
print(f"HÌNH V02-02: {_fig_roster} | nguồn=Bảng 02-F1 | đơn vị=match | không lấy mẫu.")

if not df_daily.empty:
    _fig_daily = paths["figures"] / "nb02_matches_per_day.png"
    fig, ax = plt.subplots(figsize=(11, 5), constrained_layout=True)
    ax.plot(df_daily["match_day"].astype(str), df_daily["match_count"], marker="o", color="#2F7D32", linewidth=2)
    ax.set_xlabel("Ngày UTC")
    ax.set_ylabel("Số match")
    ax.set_title(f"V02-03 — Coverage theo ngày; N={int(df_daily['match_count'].sum()):,} match")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(alpha=0.25)
    fig.savefig(_fig_daily, dpi=160, bbox_inches="tight")
    display(fig)
    plt.close(fig)
    _figures["matches_per_day"] = _fig_daily
    print(f"HÌNH V02-03: {_fig_daily} | nguồn=Bảng 02-H | timezone=UTC | không lấy mẫu.")
else:
    print("HÌNH V02-03: not_applicable vì không có match_date hợp lệ; không tạo hình placeholder.")

_fig_split = paths["figures"] / "nb02_split_distribution.png"
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
_colors = ["#35618D", "#C77832", "#2F7D32"]
axes[0].bar(df_splits["Split"], df_splits["Số match"], color=_colors, edgecolor="black")
axes[0].set_title("Số match theo split")
axes[0].set_ylabel("Số match")
axes[1].bar(df_splits["Split"], df_splits["Ước tính player rows"], color=_colors, edgecolor="black", hatch="//")
axes[1].set_title("Player rows ước tính theo split")
axes[1].set_ylabel("Số player rows")
fig.suptitle(f"V02-04 — Split cô lập theo match; N={split_meta['total_matches']:,} match")
fig.savefig(_fig_split, dpi=160, bbox_inches="tight")
display(fig)
plt.close(fig)
_figures["split_distribution"] = _fig_split
print(f"HÌNH V02-04: {_fig_split} | nguồn=Bảng 02-J1 | strategy={split_strategy} | không lấy mẫu.")
""",
        ("markdown", r"""### 7. Gate G2, giới hạn và bàn giao

G2 xác nhận dữ liệu đã được kiểm toán và split đã khóa theo bằng chứng hiện có. Nó không chứng minh player_name là account ID, roster quan sát là roster thật hoàn chỉnh, timestamp có semantics completion-time, hoặc dữ liệu đại diện cho mọi người chơi PUBG.

Không được kết luận causal từ các bảng/hình này. Grade B không cho phép thứ tự nội ngày. Grade C không cho phép gọi S2/P3 là future prediction. Tỷ lệ split là protocol đã cấu hình, không được đổi sau khi xem test performance.

Cell cuối kiểm tra expected/actual, commit split_manifest stage và tạo bảng artifact có checksum. Wrapper chung commit checkpoint Notebook 02. Resume point của thành viên tiếp theo là Notebook 03 sau khi tất cả kiểm tra chặn đạt."""),
        """
_core_artifacts = {
    "cleaned": cleaned_pq,
    "identity_conflicts": identity_conflicts_pq,
    "removal_log": removal_csv,
    "error_flags": error_flags_csv,
    "task_exclusions": task_exclusion_csv,
    "match_metadata": meta_pq,
    "match_audit": audit_report_json,
    "chronology": chronology_path,
    "split_assignments": split_pq,
    "split_manifest": split_manifest,
}
_gate_rows = [
    {"Kiểm tra": "Bảo toàn dòng", "Kỳ vọng": "N0-sum(Ri)=Nclean", "Thực tế": f"{n0}-{sum_removed}={n_clean}", "Kết luận": "Đạt" if n0 - sum_removed == n_clean else "Không đạt"},
    {"Kiểm tra": "Identity conflicts", "Kỳ vọng": "Lưu riêng, không keep first", "Thực tế": clean_summary["key_conflicts"], "Kết luận": "Đạt" if identity_conflicts_pq.is_file() else "Không đạt"},
    {"Kiểm tra": "Task exclusions", "Kỳ vọng": "Ledger riêng removal", "Thực tế": len(df_task_exclusions), "Kết luận": "Đạt" if task_exclusion_csv.is_file() else "Không đạt"},
    {"Kiểm tra": "Chronology evidence", "Kỳ vọng": "Grade A/B/C có policy", "Thực tế": f"{chrono_report['grade']} / {chrono_report['policy']}", "Kết luận": "Đạt" if chrono_report["grade"] in ("Grade A", "Grade B", "Grade C") else "Không đạt"},
    {"Kiểm tra": "Match isolation", "Kỳ vọng": "Mọi intersection=0", "Thực tế": str(split_meta["split_intersections"]), "Kết luận": "Đạt" if split_meta["match_isolation_verified"] else "Không đạt"},
    {"Kiểm tra": "Chronology boundary", "Kỳ vọng": "Không xé day/tie block", "Thực tế": split_meta["tie_blocks_split"], "Kết luận": "Đạt" if not split_meta["tie_blocks_split"] else "Không đạt"},
    {"Kiểm tra": "Artifact cốt lõi", "Kỳ vọng": "10/10 tồn tại", "Thực tế": f"{sum(path.is_file() for path in _core_artifacts.values())}/10", "Kết luận": "Đạt" if all(path.is_file() for path in _core_artifacts.values()) else "Không đạt"},
]
df_gate = pd.DataFrame(_gate_rows)
print("--- BẢNG 02-K: EXPECTED / ACTUAL GATE G2 ---")
print(df_gate.to_string(index=False))
if any(row["Kết luận"] != "Đạt" for row in _gate_rows):
    raise RuntimeError("Gate G2 chưa đạt; sửa mục Không đạt trước khi mở Notebook 03.")

ckpt_mgr.commit("split_manifest", split_meta["config_hash"], _core_artifacts)
_nb02_artifacts = {**_core_artifacts, **_figures}
_handover = []
for name, path in _nb02_artifacts.items():
    try:
        relative_path = str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        relative_path = str(path)
    _handover.append({
        "Artifact": name,
        "Đường dẫn": relative_path,
        "SHA256": hash_file(path)[:16] + "...",
        "Trạng thái": "Sẵn sàng",
        "Consumer": "03_build_player_match.ipynb" if name in _core_artifacts else "Báo cáo kiểm toán NB02",
    })
print("\\n--- BẢNG 02-L: ARTIFACT VÀ BÀN GIAO ---")
print(pd.DataFrame(_handover).to_string(index=False))
print("\\nGate G2 hoàn tất. Tiếp theo: mở 03_build_player_match.ipynb với cùng storage root; không thay split sau khi xem test.")
"""
    ]
)
# 03_build_player_match.ipynb
create_notebook(
    "03_build_player_match.ipynb",
    "03 — Xây dựng đặc trưng cơ sở và target ở cấp người chơi-trận",
    "Tạo player_match_base có grain, lineage, công thức, target validity, dictionary, schema và partition manifest được kiểm chứng.",
    [
        ("markdown", r"""### 0. Bối cảnh khoa học, phạm vi và tiêu chí thành công

Notebook 03 chuyển dữ liệu sạch ở cấp người chơi-trận thành tập đặc trưng cơ sở dùng chung cho RQ1, RQ2 và RQ3. Đây là bước xây dữ liệu, chưa phải bước chứng minh quan hệ, phân cụm hay huấn luyện mô hình.

Đơn vị quan sát là một người chơi trong một trận. row_id là khóa kỹ thuật chống va chạm; khóa nghiệp vụ là (match_id, player_name). Nếu tên người chơi không khả dụng, lineage (source_file, source_row) chỉ dùng để truy vết, không biến một danh tính chưa biết thành người chơi đã xác minh.

Các mục tiêu kiểm chứng:

1. Bảo toàn đúng số dòng từ cleaned_aggregate.parquet, không join explosion.
2. Tính một lần các đặc trưng combat, movement và support tại nguồn canonical.
3. Giữ raw outcome, target chuẩn hóa và cờ hợp lệ riêng biệt.
4. Không che placement lỗi bằng clipping; không biến structural missing thành 0.
5. Tách team_size_mode khỏi perspective_mode; mode chưa xác minh nhận unknown.
6. Xuất dictionary, validation summary, schema và numbered parts có đối soát.
7. Chứng minh allowlist chặn feature target-derived khỏi task không phù hợp.

Notebook không lấy mẫu để tạo số liệu chính thức. Lấy mẫu có seed chỉ dùng cho hình phân bố và luôn ghi rõ N. Kết quả mô tả là association, không phải quan hệ nhân quả."""),
        ("markdown", r"""### 1. Tiền điều kiện, provenance và phạm vi dữ liệu

Notebook 03 yêu cầu ba hợp đồng từ Notebook 02: dữ liệu sạch, metadata roster và split đã khóa. Split chỉ được kiểm tra coverage ở bước này; dữ liệu base chưa dùng test để lựa chọn feature hay mô hình.

Cách đọc Bảng 03-A: mỗi artifact phải tồn tại, có kích thước lớn hơn 0 và checksum. Nếu thiếu, chạy lại Notebook 02 thay vì tự tạo dữ liệu thay thế."""),
        """
import sys
from pathlib import Path

PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import json
import pandas as pd
import numpy as np
from src.utils.config import load_config, resolve_paths
from src.data.io import get_duckdb_connection, read_json
from src.data.checkpoints import CheckpointManager
from src.utils.hashing import hash_file

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
con = get_duckdb_connection(
    temp_dir=paths["temp_dir"],
    **{key: cfg["runtime"]["duckdb"][key] for key in ("memory_limit", "threads")},
)
ckpt_mgr = CheckpointManager(paths["checkpoints"] / "checkpoint_manifest.json")

cleaned_agg_pq = paths["interim"] / "cleaned_aggregate.parquet"
meta_pq = paths["interim"] / "match_metadata.parquet"
split_pq = paths["interim"] / "split_assignments.parquet"
_required_inputs = {
    "cleaned_aggregate": cleaned_agg_pq,
    "match_metadata": meta_pq,
    "split_assignments": split_pq,
}
_missing_inputs = [name for name, path in _required_inputs.items() if not path.is_file()]
if _missing_inputs:
    raise FileNotFoundError(
        f"Thiếu đầu vào Gate G2: {_missing_inputs}. Chạy hoàn tất Notebook 02 trước."
    )

_input_rows = []
for _name, _path in _required_inputs.items():
    _input_rows.append({
        "Artifact": _name,
        "Đường dẫn": str(_path.relative_to(PROJECT_ROOT)),
        "Bytes": _path.stat().st_size,
        "SHA256": hash_file(_path)[:16] + "...",
        "Phạm vi": "full cleaned data" if _name == "cleaned_aggregate" else "match-level contract",
        "Trạng thái": "Đạt",
    })
_df_inputs = pd.DataFrame(_input_rows)
print("--- BẢNG 03-A: TIỀN ĐIỀU KIỆN VÀ PROVENANCE ---")
print(_df_inputs.to_string(index=False))
""",
        ("markdown", r"""### 2. Feature Registry và hợp đồng chống leakage

Feature Registry là từ điển có thẩm quyền. Mỗi feature ghi tên, nhóm, nguồn, cấp dữ liệu, công thức, đơn vị, kiểu dữ liệu, mẫu số, missing semantics, allowlist và cấm theo target.

Ba quy tắc quan trọng:

- ride_ratio không tồn tại như main feature vì gần bằng 1 - walk_ratio.
- dbno_ratio và feature tổng hợp cấp đội không tự động vào core.
- Rate chứa player_survive_time chỉ dùng diagnostic; không dùng cho chính survival target.

Bảng 03-B kiểm kê 26 feature không historical cùng các khai báo lịch sử dành cho NB08;
khai báo trong dictionary không có nghĩa feature lịch sử đã được tính ở NB03.
Bảng 03-C tập trung vào công thức cơ sở; Bảng 03-D cho biết task nào được phép dùng từng feature."""),
        """
from src.features.registry import FeatureRegistry

dict_csv = paths["tables"] / "feature_dictionary.csv"
registry = FeatureRegistry()
registry.export_dictionary_csv(dict_csv)
df_dict = pd.read_csv(dict_csv)

_df_registry_summary = (
    df_dict.groupby(["group", "status"], dropna=False)
    .size().reset_index(name="Số feature")
    .sort_values(["group", "status"])
)
print("--- BẢNG 03-B: KIỂM KÊ FEATURE REGISTRY ---")
print(_df_registry_summary.to_string(index=False))
print(f"Tổng số feature đăng ký: {len(df_dict)}")

_core_names = [
    "damage_per_kill", "total_distance", "walk_ratio", "assist_ratio",
    "player_survive_time", "normalized_placement",
]
_df_core_dictionary = df_dict[df_dict["feature_name"].isin(_core_names)][[
    "feature_name", "source_columns", "formula", "unit", "denominator",
    "missing_semantics", "allowed_tasks", "forbidden_targets",
]]
print("\\n--- BẢNG 03-C: CÔNG THỨC, ĐƠN VỊ VÀ MISSING SEMANTICS ---")
print(_df_core_dictionary.to_string(index=False))

_tasks = ["rq1_survival", "rq1_placement", "rq2", "s1", "p1", "p2", "diagnostic"]
_allowlist_rows = []
for _task in _tasks:
    _allowed = registry.get_allowed_features(_task)
    _allowlist_rows.append({
        "Task": _task,
        "Số feature được phép": len(_allowed),
        "Danh sách": ", ".join(_allowed),
        "Có rate theo survival": any(name in _allowed for name in ("kills_per_minute", "damage_per_minute")),
    })
_df_allowlists = pd.DataFrame(_allowlist_rows)
print("\\n--- BẢNG 03-D: TASK ALLOWLIST VÀ KIỂM SOÁT LEAKAGE ---")
print(_df_allowlists.to_string(index=False))
""",
        ("markdown", r"""### 3. Tạo player_match_base và báo cáo validation

Các công thức:

[
damage_per_kill = rac{player_dmg}{player_kills},
qquad
walk_ratio = rac{player_dist_walk}{player_dist_walk+player_dist_ride},
]

[
assist_ratio = rac{player_assists}{player_assists+player_kills},
qquad
normalized_placement =
1-rac{team_placement-1}{N_{teams}-1}.
]

Mẫu số bằng 0 tạo structural missing (NULL), không dùng epsilon và không gán 0. Placement chỉ được tính khi roster hoàn chỉnh, N_teams > 1 và placement thuộc [1,N_teams].

Output canonical là player_match_base.parquet. Thư mục numbered parts hỗ trợ đọc theo phần nhưng không tạo thư mục riêng cho từng player hoặc match."""),
        """
from src.features.base import build_player_match_base

base_pq = paths["interim"] / "player_match_base.parquet"
val_csv = paths["tables"] / "feature_validation_base.csv"
schema_json = paths["manifests"] / "player_match_base_schema.json"
parts_dir = paths["interim"] / "player_match_base_parts"
parts_manifest_json = paths["manifests"] / "player_match_base_parts_manifest.json"

base_rows = build_player_match_base(
    con=con,
    cleaned_aggregate_parquet=cleaned_agg_pq,
    match_metadata_parquet=meta_pq,
    output_base_parquet=base_pq,
    validation_csv_path=val_csv,
    dictionary_csv_path=dict_csv,
    split_assignments_parquet=split_pq,
    schema_json_path=schema_json,
    partition_dir=parts_dir,
    partition_manifest_path=parts_manifest_json,
)

df_val = pd.read_csv(val_csv)
print("--- BẢNG 03-E: VALIDATION VÀ PHÂN LOẠI GIÁ TRỊ THIẾU ---")
print(df_val[[
    "feature_name", "feature_group", "total_rows", "valid_count", "null_count",
    "structural_missing_count", "other_missing_count", "null_pct", "unit", "status",
]].to_string(index=False))

_n_clean = con.execute("SELECT count(*) FROM read_parquet(?)", [str(cleaned_agg_pq)]).fetchone()[0]
_reconciliation = pd.DataFrame([
    {"Đại lượng": "Rows cleaned đầu vào", "Kỳ vọng": _n_clean, "Thực tế": _n_clean, "Kết luận": "Đạt"},
    {"Đại lượng": "Rows player_match_base", "Kỳ vọng": _n_clean, "Thực tế": base_rows, "Kết luận": "Đạt" if base_rows == _n_clean else "Không đạt"},
])
print("\\n--- BẢNG 03-F: ĐỐI SOÁT BẢO TOÀN DÒNG ---")
print(_reconciliation.to_string(index=False))
if base_rows != _n_clean:
    raise RuntimeError(f"Join explosion hoặc mất dòng: base={base_rows}, clean={_n_clean}")
""",
        ("markdown", r"""### 4. Grain, schema và numbered parts

row_id phải không null và duy nhất. Một player name rỗng chỉ được giữ khi có lineage đầy đủ; điều này bảo toàn truy vết nhưng không xác nhận danh tính.

Schema manifest khóa tên và kiểu cột. Parts manifest ghi partition rule, số dòng, bytes và checksum từng part. Tổng số dòng của các part phải đúng bằng file canonical."""),
        """
_schema = read_json(schema_json)
_parts = read_json(parts_manifest_json)
_grain = con.execute('''
    SELECT
        count(*) AS rows,
        count(DISTINCT row_id) AS unique_row_ids,
        count(*) FILTER (WHERE row_id IS NULL) AS null_row_ids,
        count(DISTINCT match_id) AS matches,
        count(DISTINCT player_name) AS named_players,
        count(*) FILTER (WHERE player_name IS NULL OR length(trim(player_name)) = 0) AS lineage_fallback_rows
    FROM read_parquet(?)
''', [str(base_pq)]).df()
print("--- BẢNG 03-G1: GRAIN VÀ KHÓA DÒNG ---")
print(_grain.to_string(index=False))

_df_schema = pd.DataFrame(_schema["columns"])
print("\\n--- BẢNG 03-G2: SCHEMA PLAYER_MATCH_BASE ---")
print(_df_schema.to_string(index=False))

_df_parts = pd.DataFrame(_parts["parts"])
print("\\n--- BẢNG 03-G3: NUMBERED PARTS VÀ CHECKSUM ---")
print(_df_parts.to_string(index=False))
print(
    f"Đối soát parts: canonical={_parts['row_count']:,}, "
    f"tổng parts={_parts['row_count_from_parts']:,}, số parts={_parts['part_count']}"
)
""",
        ("markdown", r"""### 5. Ví dụ tính tay và kiểm tra target validity

Bảng 03-H đối chiếu công thức tính tay với output. Sai số phải gần 0. Các dòng có mẫu số 0 có kỳ vọng NULL.

Bảng 03-I không loại toàn bộ một dòng chỉ vì một target lỗi. valid_survival và valid_placement tạo hai cohort task-specific. Raw outcome vẫn được giữ để kiểm toán."""),
        """
_examples = con.execute('''
    SELECT
        row_id, player_kills, player_dmg, damage_per_kill,
        CASE WHEN player_kills > 0 THEN player_dmg / player_kills ELSE NULL END AS damage_manual,
        total_distance, player_dist_walk, walk_ratio,
        CASE WHEN total_distance > 0 THEN player_dist_walk / total_distance ELSE NULL END AS walk_manual,
        player_assists, assist_ratio,
        CASE WHEN player_assists + player_kills > 0
             THEN CAST(player_assists AS DOUBLE) / (player_assists + player_kills)
             ELSE NULL END AS assist_manual,
        team_placement, observed_team_count, normalized_placement,
        CASE WHEN valid_placement
             THEN 1.0 - CAST(team_placement - 1 AS DOUBLE) / (observed_team_count - 1)
             ELSE NULL END AS placement_manual
    FROM read_parquet(?)
    ORDER BY row_id
    LIMIT 8
''', [str(base_pq)]).df()
for _stored, _manual, _error in (
    ("damage_per_kill", "damage_manual", "damage_abs_error"),
    ("walk_ratio", "walk_manual", "walk_abs_error"),
    ("assist_ratio", "assist_manual", "assist_abs_error"),
    ("normalized_placement", "placement_manual", "placement_abs_error"),
):
    _examples[_error] = (_examples[_stored] - _examples[_manual]).abs()
print("--- BẢNG 03-H: ĐỐI CHIẾU TÍNH TAY VỚI OUTPUT ---")
print(_examples.to_string(index=False))

_task_coverage = con.execute('''
    SELECT
        count(*) AS all_cleaned_rows,
        count(*) FILTER (WHERE valid_survival) AS survival_eligible_rows,
        count(*) FILTER (WHERE valid_placement) AS placement_eligible_rows,
        count(*) FILTER (WHERE valid_survival AND valid_placement) AS eligible_both,
        count(*) FILTER (WHERE valid_survival AND NOT valid_placement) AS survival_only,
        count(*) FILTER (WHERE valid_placement AND NOT valid_survival) AS placement_only,
        count(*) FILTER (WHERE NOT valid_survival AND NOT valid_placement) AS eligible_neither
    FROM read_parquet(?)
''', [str(base_pq)]).df()
print("\\n--- BẢNG 03-I: COVERAGE VÀ VALIDITY THEO TASK ---")
print(_task_coverage.to_string(index=False))
""",
        ("markdown", r"""### 6. Mode audit và giới hạn diễn giải

perspective_mode mô tả góc nhìn; team_size_mode mô tả quy mô đội. Hai khái niệm không được gộp thành game_mode mơ hồ.

Quy tắc hiện tại chỉ ánh xạ party_size đã xác minh: 1 là solo, 2 là duo, 4 là squad. Giá trị khác hoặc thiếu nhận unknown; Notebook 05 sẽ dùng EDA dữ liệu thật để quyết định chiến lược mode. Tỷ lệ mode chỉ mô tả cohort, không chứng minh mode gây ra khác biệt outcome."""),
        """
_df_modes = con.execute('''
    SELECT
        party_size, team_size_mode, perspective_mode,
        count(*) AS rows,
        count(DISTINCT match_id) AS matches,
        round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS row_pct
    FROM read_parquet(?)
    GROUP BY party_size, team_size_mode, perspective_mode
    ORDER BY rows DESC, party_size
''', [str(base_pq)]).df()
print("--- BẢNG 03-J: PARTY SIZE, TEAM SIZE MODE VÀ PERSPECTIVE ---")
print(_df_modes.to_string(index=False))
""",
        ("markdown", r"""### 7. Trực quan kiểm toán

- V03-01: phân bố bốn feature dẫn xuất; chỉ dùng reservoir sample có seed 42, tối đa 100.000 dòng.
- V03-02: số dòng theo team_size_mode và perspective_mode trên toàn bộ dữ liệu.
- V03-03: coverage full-data của hai target; mẫu số là toàn bộ cleaned rows.

Histogram không chứng minh quan hệ nhân quả. Giá trị cực trị hợp lệ không bị xóa chỉ để hình đẹp; trục ghi đúng đơn vị và N."""),
        """
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig_dir = paths["figures"]
fig_dir.mkdir(parents=True, exist_ok=True)
_sample_n = min(base_rows, 100000)
_df_sample = con.execute(f'''
    SELECT damage_per_kill, walk_ratio, assist_ratio, normalized_placement
    FROM read_parquet(?)
    USING SAMPLE {_sample_n} ROWS (reservoir, 42)
''', [str(base_pq)]).df()

_fig, _axes = plt.subplots(2, 2, figsize=(12, 8))
_feature_plot_meta = [
    ("damage_per_kill", "Damage trên mỗi kill", "đơn vị sát thương nguồn / kill; chưa xác minh"),
    ("walk_ratio", "Tỷ lệ quãng đường đi bộ", "tỷ lệ [0,1]"),
    ("assist_ratio", "Tỷ lệ hỗ trợ", "tỷ lệ [0,1]"),
    ("normalized_placement", "Thứ hạng chuẩn hóa", "điểm [0,1]"),
]
for _ax, (_column, _title, _unit) in zip(_axes.flat, _feature_plot_meta):
    _values = _df_sample[_column].dropna()
    if len(_values):
        _ax.hist(_values, bins=30, color="#4C72B0", edgecolor="white")
    _ax.set_title(_title)
    _ax.set_xlabel(_unit)
    _ax.set_ylabel("Số dòng trong mẫu")
    _ax.grid(axis="y", alpha=0.25)
_fig.suptitle(f"V03-01. Phân bố feature cơ sở; reservoir sample N={len(_df_sample):,}, seed=42")
_fig.tight_layout()
_fig_features = fig_dir / "nb03_feature_distributions.png"
_pubg_figure_details = {_fig_features.name: {"source_table": str(base_pq), "scope": "base descriptive",
    "sample_n": len(_df_sample), "sample_seed": 42, "sampling_rule": "DuckDB reservoir; visualization only",
    "caption": f"V03-01: n={len(_df_sample)}, N base={base_rows}; missing bị loại từng panel, không loại khỏi dữ liệu."}}
_fig.savefig(_fig_features, dpi=180, bbox_inches="tight")
plt.close(_fig)
print(f"HÌNH V03-01: {_fig_features.name} | N mẫu={len(_df_sample):,} | chỉ dùng cho trực quan")

_mode_plot = _df_modes.pivot_table(
    index="team_size_mode", columns="perspective_mode", values="rows",
    aggfunc="sum", fill_value=0,
)
_fig, _ax = plt.subplots(figsize=(9, 5))
_mode_plot.plot(kind="bar", stacked=True, ax=_ax)
_ax.set_title(f"V03-02. Phân bố mode trên toàn bộ base; N={base_rows:,}")
_ax.set_xlabel("Team size mode")
_ax.set_ylabel("Số dòng người chơi-trận")
_ax.legend(title="Perspective mode")
_ax.grid(axis="y", alpha=0.25)
_fig.tight_layout()
_fig_modes = fig_dir / "nb03_mode_distribution.png"
_fig.savefig(_fig_modes, dpi=180, bbox_inches="tight")
plt.close(_fig)
print(f"HÌNH V03-02: {_fig_modes.name} | N base={base_rows:,} | runtime.mode={cfg['runtime']['mode']}; không tự chứng nhận full-data")

_cov = _task_coverage.iloc[0]
_cov_names = ["survival_eligible_rows", "placement_eligible_rows", "eligible_both"]
_fig, _ax = plt.subplots(figsize=(9, 5))
_bars = _ax.bar(
    ["Survival hợp lệ", "Placement hợp lệ", "Cả hai hợp lệ"],
    [_cov[name] for name in _cov_names],
    color=["#4C72B0", "#55A868", "#8172B2"],
)
_ax.set_title(f"V03-03. Coverage target theo cùng mẫu số N={base_rows:,}")
_ax.set_ylabel("Số dòng người chơi-trận")
_ax.set_ylim(0, max(base_rows, 1) * 1.12)
for _bar in _bars:
    _ax.text(_bar.get_x() + _bar.get_width()/2, _bar.get_height(), f"{int(_bar.get_height()):,}", ha="center", va="bottom")
_ax.grid(axis="y", alpha=0.25)
_fig.tight_layout()
_fig_coverage = fig_dir / "nb03_task_coverage.png"
_fig.savefig(_fig_coverage, dpi=180, bbox_inches="tight")
plt.close(_fig)
print(f"HÌNH V03-03: {_fig_coverage.name} | mẫu số={base_rows:,} cleaned rows")
""",
        ("markdown", r"""### 8. Kiểm tra hoàn tất NB03, giới hạn và bàn giao

NB03 hoàn tất khi row count được bảo toàn, row_id duy nhất, schema và parts đối soát, dictionary đủ metadata, công thức tính tay khớp và allowlist không chứa rate survival-derived trong S1. Đây không phải Gate G3: G3 dành cho quyết định nghiên cứu sau diagnostics/EDA, không được chứng nhận chỉ bằng kiểm tra base features.

Giới hạn:

- Đây là nghiệm thu code và fixture; bảng full-data chỉ hình thành khi chạy trên Drive.
- Mode unknown cần Notebook 05 mô tả trước khi chốt chiến lược phân tầng.
- Missing ngoài structural missing được giữ và báo cáo, không tự động điền 0.
- Notebook này dùng CPU và DuckDB; GPU không mặc định làm các phép SQL nhanh hơn.
- Notebook 04 chỉ nối timing vào base đã khóa, không tính lại feature cơ sở."""),
        """
_error_columns = ["damage_abs_error", "walk_abs_error", "assist_abs_error", "placement_abs_error"]
_finite_errors = []
for _column in _error_columns:
    _finite_errors.extend(_examples[_column].dropna().tolist())
_max_manual_error = max(_finite_errors) if _finite_errors else 0.0
_grain_row = _grain.iloc[0]
_banned_main = {"ride_ratio", "dbno_ratio", "team_kills", "team_damage", "team_assists", "team_avg_survival"}
_registry_names = set(df_dict["feature_name"])
_base_dictionary = df_dict[df_dict["group"] != "historical"]
_gate_rows = [
    {"Kiểm tra": "Bảo toàn dòng", "Kỳ vọng": _n_clean, "Thực tế": base_rows, "Kết luận": "Đạt" if base_rows == _n_clean else "Không đạt"},
    {"Kiểm tra": "row_id không null", "Kỳ vọng": 0, "Thực tế": int(_grain_row["null_row_ids"]), "Kết luận": "Đạt" if int(_grain_row["null_row_ids"]) == 0 else "Không đạt"},
    {"Kiểm tra": "row_id duy nhất", "Kỳ vọng": base_rows, "Thực tế": int(_grain_row["unique_row_ids"]), "Kết luận": "Đạt" if int(_grain_row["unique_row_ids"]) == base_rows else "Không đạt"},
    {"Kiểm tra": "Đối soát numbered parts", "Kỳ vọng": base_rows, "Thực tế": int(_parts["row_count_from_parts"]), "Kết luận": "Đạt" if int(_parts["row_count_from_parts"]) == base_rows else "Không đạt"},
    {"Kiểm tra": "Feature Registry cơ sở", "Kỳ vọng": "26 feature không historical, đủ metadata", "Thực tế": f"{len(_base_dictionary)} cơ sở; {len(df_dict)-len(_base_dictionary)} khai báo historical cho NB08", "Kết luận": "Đạt" if len(_base_dictionary) == 26 and not _base_dictionary[["formula", "unit", "missing_semantics", "allowed_tasks"]].isna().any().any() else "Không đạt"},
    {"Kiểm tra": "Không có feature core bị cấm", "Kỳ vọng": "Không có", "Thực tế": ", ".join(sorted(_registry_names & _banned_main)) or "Không có", "Kết luận": "Đạt" if not (_registry_names & _banned_main) else "Không đạt"},
    {"Kiểm tra": "S1 không chứa rate theo survival", "Kỳ vọng": "False", "Thực tế": str(bool({"kills_per_minute", "damage_per_minute"} & set(registry.get_allowed_features("s1")))), "Kết luận": "Đạt" if not ({"kills_per_minute", "damage_per_minute"} & set(registry.get_allowed_features("s1"))) else "Không đạt"},
    {"Kiểm tra": "Đối chiếu công thức", "Kỳ vọng": "Sai số <= 1e-12", "Thực tế": _max_manual_error, "Kết luận": "Đạt" if _max_manual_error <= 1e-12 else "Không đạt"},
    {"Kiểm tra": "Ba hình PNG", "Kỳ vọng": "3/3", "Thực tế": sum(path.is_file() for path in (_fig_features, _fig_modes, _fig_coverage)), "Kết luận": "Đạt" if all(path.is_file() for path in (_fig_features, _fig_modes, _fig_coverage)) else "Không đạt"},
]
_df_gate = pd.DataFrame(_gate_rows)
print("--- BẢNG 03-K: KỲ VỌNG / THỰC TẾ HOÀN TẤT NB03 ---")
print(_df_gate.to_string(index=False))
if (_df_gate["Kết luận"] != "Đạt").any():
    raise RuntimeError("Kiểm tra NB03 chưa đạt; sửa các dòng Không đạt trước khi mở Notebook 04.")

_core_stage_artifacts = {
    "player_match_base": base_pq,
    "feature_dictionary": dict_csv,
    "feature_validation": val_csv,
    "base_schema": schema_json,
    "parts_manifest": parts_manifest_json,
}
ckpt_mgr.commit(
    stage="player_match_base",
    signature=cfg["features"]["feature_versions"]["feature_version"],
    artifacts=_core_stage_artifacts,
)

_nb03_artifacts = {
    **_core_stage_artifacts,
    "feature_distributions": _fig_features,
    "mode_distribution": _fig_modes,
    "task_coverage": _fig_coverage,
}
_handover = []
for _name, _path in _nb03_artifacts.items():
    _handover.append({
        "Artifact": _name,
        "Đường dẫn": str(_path.relative_to(PROJECT_ROOT)),
        "Bytes": _path.stat().st_size,
        "SHA256": hash_file(_path)[:16] + "...",
        "Consumer": "04_combat_timing.ipynb" if _name == "player_match_base" else "Kiểm toán và báo cáo",
    })
print("\\n--- BẢNG 03-L: ARTIFACT VÀ BÀN GIAO ---")
print(pd.DataFrame(_handover).to_string(index=False))
print("\\nKiểm tra NB03 hoàn tất, chưa chứng nhận G3. Tiếp theo: mở 04_combat_timing.ipynb; không tính lại base features.")
"""
    ]
)
# 04_combat_timing.ipynb
create_notebook(
    "04_combat_timing.ipynb",
    "04 — Khai phá Combat Timing và hoàn thiện Player-Match Features",
    "Tổng hợp sự kiện được ghi công theo thời gian, kiểm toán eligibility/coverage và LEFT JOIN bảo toàn số dòng vào player-match base.",
    [
        ("markdown", r"""### I. Giới thiệu và Khung Lý thuyết về Thời điểm Giao tranh (Combat Timing Theory)

Notebook 04 xây lớp đặc trưng Combat Timing phục vụ RQ1-RQ3, nhưng đây là bước xử lý và chẩn đoán, chưa phải kết quả nghiên cứu. Thời điểm sự kiện chỉ mô tả dữ liệu quan sát; không tự chứng minh phong cách, kỹ năng, chiến thuật hay quan hệ nhân quả.

**Câu hỏi kiểm tra:**
1. Sự kiện nào đủ điều kiện cho thời gian tuyệt đối và sự kiện nào đủ điều kiện phân pha?
2. Hai kill thật cùng giây có được giữ, còn bản ghi có khả năng phát lại có được gắn cờ mà không tự xóa không?
3. Không kill, thiếu event và event chỉ hợp lệ một phần có được phân biệt không?
4. Phép ghép có cardinality many-to-one và bảo toàn $N_{final}=N_{base}$ không?
5. Đơn vị thời gian, điều kiện enemy-kill và ngưỡng 60 giây đang verified hay pending?

Theo quy chuẩn nghiên cứu trong `PUBG_RESEARCH_SPEC.md` và các quy tắc kiểm soát rò rỉ thông tin trong `PUBG_IMPLEMENTATION_PLAN.md`:

#### 1. Đặc trưng Thời gian Tuyệt đối (Absolute Timing Features)
Được tính trên các sự kiện có match, killer và thời gian hợp lệ, không self-kill. `victim_name` và `killed_by` là bằng chứng kiểm toán tùy chọn: thiếu chúng không tự loại timing tuyệt đối, nhưng cũng chưa cho phép gọi sự kiện là enemy-kill đã xác minh.
- $first\_kill\_time = \min(t)$: Thời điểm người chơi ghi nhận mạng hạ gục đầu tiên trong trận đấu.
- $avg\_kill\_time = \frac{1}{K} \sum_{i=1}^K t_i$: Mốc thời gian trung bình của các lần hạ gục.
- $has\_kill \in \{0, 1\}$: Biến chỉ báo nhị phân (true nếu người chơi có ít nhất 1 kill hợp lệ).
- $event\_kill\_count$: Số sự kiện hạ gục được liên kết thành công từ nhật ký cái chết.

*Nguyên tắc D01:* Timing tuyệt đối không dùng duration proxy. Tuy nhiên eligibility enemy-kill và đơn vị thời gian vẫn phải qua gate dữ liệu thật trước khi gọi là đã khóa.

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

*Cảnh báo D01:* Vì $estimated\_match\_duration$ phụ thuộc trực tiếp vào survival, các đặc trưng pha bị cấm trong S1. Ngưỡng 60 giây hiện chỉ là cơ chế chẩn đoán có trạng thái `pending_real_data_evidence`, không phải quyết định nghiên cứu đã chốt."""),
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
from src.features.combat_timing import evaluate_combat_timing_research_gate, extract_and_aggregate_combat_timing, merge_player_match_and_timing
from src.data.checkpoints import CheckpointManager
from src.data.batch_ingest import staged_paths
from src.utils.hashing import hash_file

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

_base_rows = con.execute("SELECT count(*) FROM read_parquet(?)", [str(base_pq)]).fetchone()[0]
_event_rows = con.execute("SELECT count(*) FROM read_parquet(?)", [[str(p) for p in death_shards]]).fetchone()[0]
_meta_rows = con.execute("SELECT count(*) FROM read_parquet(?)", [str(meta_pq)]).fetchone()[0]
_timing_cfg = cfg["features"]["combat_timing"]
_research_gate = evaluate_combat_timing_research_gate(cfg["features"])
_input_table = pd.DataFrame([
    {"Nguồn": "player_match_base", "Đường dẫn": str(base_pq.relative_to(PROJECT_ROOT)), "Số dòng": _base_rows, "Grain": "player-match", "Đơn vị thời gian": "candidate: giây", "Trạng thái": "upstream completed"},
    {"Nguồn": "death events", "Đường dẫn": f"{len(death_shards)} staged shards", "Số dòng": _event_rows, "Grain": "source event row", "Đơn vị thời gian": _timing_cfg["event_time_unit_status"], "Trạng thái": "pending unit evidence"},
    {"Nguồn": "match_metadata", "Đường dẫn": str(meta_pq.relative_to(PROJECT_ROOT)), "Số dòng": _meta_rows, "Grain": "match", "Đơn vị thời gian": "duration proxy", "Trạng thái": _timing_cfg["min_valid_duration_status"]},
])
print("\\n--- BẢNG 04-A: INPUT VÀ PROVENANCE ---")
print(_input_table.to_string(index=False))

_gate_table = pd.DataFrame(_research_gate["checks"])
_gate_table = _gate_table.rename(columns={
    "parameter": "Quyết định", "status": "Trạng thái",
    "evidence": "Bằng chứng", "ready": "Đủ điều kiện xuất bản",
})
print("\\n--- BẢNG 04-B: RESEARCH GATE RUN-04 ---")
print(_gate_table.to_string(index=False))
""",
        ("markdown", r"""### II. Trích xuất và Tổng hợp Thời điểm Giao tranh (Combat Timing Aggregation & Audit)

Hàm `extract_and_aggregate_combat_timing` thực thi các bước sau:
1. **Điều kiện timing tuyệt đối:**
   - Loại self-kill khi cả hai tên có mặt và $killer\_name == victim\_name$.
   - Loại sự kiện thiếu `match_id`, thiếu `killer_name`, thời gian âm/không hữu hạn hoặc match không có trong metadata.
   - Thiếu `victim_name`/`killed_by`, nguyên nhân môi trường và killer/victim không khớp roster được gắn cờ riêng; không tự suy diễn enemy-kill.
2. **Bảo toàn tính toàn vẹn của sự kiện (Event Key Integrity):**
   - Sự kiện không bị loại bỏ trùng lặp chỉ theo bộ $(match\_id, killer\_name, time)$. Nếu một người chơi hạ gục 2 kẻ địch trong cùng 1 giây (ví dụ dùng lựu đạn), cả 2 sự kiện đều được ghi nhận đầy đủ.
3. **Phân tách thời gian tuyệt đối và thời gian phân pha:**
   - Nếu $t > estimated\_match\_duration$, sự kiện vẫn được giữ lại để tính thời gian tuyệt đối ($first\_kill\_time$, $avg\_kill\_time$), nhưng không được tính vào các pha $early/mid/late$.
   - Nếu duration thấp hơn ngưỡng chẩn đoán 60 giây, phase không được tính; ngưỡng này vẫn `pending_real_data_evidence`.
4. **Lưu vết kiểm toán:** Lưu mọi row vào `event_validation_ledger.parquet`; không deduplicate potential replay trước khi nguồn cho bằng chứng."""),
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
    player_match_base_parquet=base_pq,
)

event_audit_csv = audit_tables_dir / "event_join_audit.csv"
event_ledger_pq = audit_tables_dir / "event_validation_ledger.parquet"
df_event_audit = pd.read_csv(audit_tables_dir / "event_join_audit.csv")
print("--- BẢNG 04-C: KIỂM TOÁN EVENT VÀ CÁC GATE PENDING ---")
print(df_event_audit.to_string(index=False))
""",
        ("markdown", r"""### III. Event ledger, phase boundary và trực quan timing

`event_validation_ledger.parquet` giữ một dòng cho mỗi dòng nguồn. `absolute_timing_eligible` và `phase_timing_eligible` là hai điều kiện khác nhau. Cột `event_source_key` chỉ là định danh đã xác minh khi lineage nguồn có sẵn; fallback được ghi `pending_source_lineage`, không gọi deterministic.

Hình V04-01 chỉ dùng reservoir sample cố định để vẽ phân bố, còn thống kê bảng và tổng pha được tính trên toàn bộ dữ liệu hợp lệ. Hình V04-02 dùng tổng toàn scope, không dùng tổng từ sample. Các hình chỉ mô tả dữ liệu quan sát, không chứng minh pha giao tranh gây ra survival hay placement."""),
        """
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig_dir = paths["figures"]
fig_dir.mkdir(parents=True, exist_ok=True)

df_event_ledger = con.execute("SELECT * FROM read_parquet(?)", [str(event_ledger_pq)]).df()
_event_funnel = pd.DataFrame([
    {"Tầng": "Dòng event nguồn", "Số event": len(df_event_ledger), "Mẫu số": len(df_event_ledger)},
    {"Tầng": "Timing tuyệt đối đủ điều kiện", "Số event": int(df_event_ledger["absolute_timing_eligible"].sum()), "Mẫu số": len(df_event_ledger)},
    {"Tầng": "Timing phase đủ điều kiện", "Số event": int(df_event_ledger["phase_timing_eligible"].sum()), "Mẫu số": len(df_event_ledger)},
])
_event_funnel["Tỷ lệ (%)"] = (_event_funnel["Số event"] * 100 / _event_funnel["Mẫu số"].replace(0, pd.NA)).round(2)
print("--- BẢNG 04-D: EVENT ELIGIBILITY FUNNEL ---")
print(_event_funnel.to_string(index=False))

_flag_cols = [column for column in df_event_ledger.columns if column.startswith("flag_")]
_flag_table = pd.DataFrame({
    "Cờ kiểm toán": _flag_cols,
    "Số event": [int(df_event_ledger[column].sum()) for column in _flag_cols],
})
_flag_table["Tỷ lệ trên event nguồn (%)"] = (_flag_table["Số event"] * 100 / max(len(df_event_ledger), 1)).round(2)
print("\\n--- BẢNG 04-E: CỜ EVENT, JOIN VÀ COVERAGE ---")
print(_flag_table.to_string(index=False))

_timing_summary = con.execute(\"\"\"
    SELECT count(*) AS killer_match_pairs,
           sum(event_kill_count) AS absolute_event_count,
           sum(phase_eligible_kill_count) AS phase_eligible_event_count,
           min(first_kill_time) AS min_first_time,
           avg(first_kill_time) AS mean_first_time,
           max(first_kill_time) AS max_first_time
    FROM read_parquet(?)
\"\"\", [str(timing_pq)]).df()
print("\\n--- BẢNG 04-F: TỔNG HỢP TIMING TOÀN SCOPE ---")
print(_timing_summary.to_string(index=False))

_boundary_examples = pd.DataFrame([
    {"relative_event_time": 0.0, "Pha": "Early", "Khoảng": "[0, 1/3)"},
    {"relative_event_time": 1 / 3, "Pha": "Mid", "Khoảng": "[1/3, 2/3)"},
    {"relative_event_time": 2 / 3, "Pha": "Late", "Khoảng": "[2/3, 1]"},
    {"relative_event_time": 1.0, "Pha": "Late", "Khoảng": "[2/3, 1]"},
    {"relative_event_time": 1.01, "Pha": "Không đủ điều kiện", "Khoảng": "> 1, không clip"},
])
print("\\n--- BẢNG 04-G: VÍ DỤ RANH GIỚI PHA ---")
print(_boundary_examples.to_string(index=False))

df_timing_sample = con.execute(\"\"\"
    SELECT first_kill_time, avg_kill_time
    FROM read_parquet(?)
    USING SAMPLE 100000 (reservoir, 42)
\"\"\", [str(timing_pq)]).df()
_phase_totals = con.execute(\"\"\"
    SELECT sum(early_kills) AS Early, sum(mid_kills) AS Mid, sum(late_kills) AS Late
    FROM read_parquet(?)
\"\"\", [str(timing_pq)]).df().iloc[0]

fig, ax = plt.subplots(figsize=(8, 4.8))
ax.hist(df_timing_sample["first_kill_time"].dropna(), bins=40, color="#2b5c8f", edgecolor="white")
ax.set(title="V04-01. Phân bố first_kill_time", xlabel="Event time, đơn vị candidate (chưa verified)", ylabel="Killer-match trong sample")
ax.grid(axis="y", alpha=0.25)
fig.text(0.5, 0.01, f"Reservoir sample để vẽ: n={len(df_timing_sample):,}; seed=42; không thay thống kê toàn scope.", ha="center", fontsize=9)
fig.tight_layout(rect=(0, 0.05, 1, 1))
timing_hist_path = fig_dir / "nb04_absolute_timing_distribution.png"
_pubg_figure_details = {timing_hist_path.name: {"source_table": str(timing_pq), "scope": "killer-match descriptive",
    "sample_n": len(df_timing_sample), "sample_seed": 42, "sampling_rule": "DuckDB reservoir; visualization only",
    "caption": "V04-01: event time chưa xác minh đơn vị; missing loại từng panel, không biến no-kill thành t=0."}}
fig.savefig(timing_hist_path, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"HÌNH V04-01 -> {timing_hist_path.relative_to(PROJECT_ROOT)}")

fig, ax = plt.subplots(figsize=(7.5, 4.8))
_phase_names = list(_phase_totals.index)
_phase_values = [int(value or 0) for value in _phase_totals.values]
ax.bar(_phase_names, _phase_values, color=["#3d85c6", "#6aa84f", "#e69138"])
ax.set(title="V04-02. Event đủ điều kiện theo pha", xlabel="Pha", ylabel="Số event trên toàn scope")
ax.grid(axis="y", alpha=0.25)
for index, value in enumerate(_phase_values):
    ax.text(index, value, f"{value:,}", ha="center", va="bottom")
fig.tight_layout()
phase_fig_path = fig_dir / "nb04_phase_event_counts.png"
fig.savefig(phase_fig_path, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"HÌNH V04-02 -> {phase_fig_path.relative_to(PROJECT_ROOT)}")

# Luôn lưu diagnostics, nhưng không công bố dataset cuối khi ba quyết định RUN-04 chưa có bằng chứng.
_diagnostic_artifacts = {
    "combat_timing": timing_pq,
    "event_audit": event_audit_csv,
    "event_ledger": event_ledger_pq,
    "absolute_timing_figure": timing_hist_path,
    "phase_counts_figure": phase_fig_path,
}
ckpt_mgr.commit(
    "combat_timing_diagnostics", _pubg_signature, _diagnostic_artifacts,
    metadata={"research_gate": _research_gate},
)
if not _research_gate["ready"]:
    _pubg_checkpoint.record_blocked(
        "notebook/04_combat_timing.ipynb", _pubg_signature, "RUN-04",
        metadata={
            "message": "Bổ sung status=verified và evidence không rỗng cho event time unit, enemy eligibility và min duration.",
            "research_gate": _research_gate,
            "diagnostic_stage": "combat_timing_diagnostics",
        },
    )
    print("RUN-04: Đã lưu diagnostics. NB04 dừng dự kiến; chưa tạo player_match_features và chưa bàn giao NB05.")
    raise RuntimeError("RUN-04_BLOCKED: khóa ba tham số bằng bằng chứng dữ liệu thật trước khi chạy tiếp.")
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

Sai lệch giữa `player_kills` và `event_kill_count` là bằng chứng cần kiểm tra, không phải lỗi phải ép về 0. Các khả năng như join failure, source semantics, unnamed/environment event hoặc replay chỉ là giả thuyết cho tới khi audit dữ liệu thật xác nhận.

`kill_discrepancy.csv` lưu đủ mọi player-match, không chỉ dòng sai lệch hay top N. `event_timing_coverage.csv` dùng mẫu số player-match; `event_join_audit.csv` dùng mẫu số event. Hai tỷ lệ không được trộn. Trạng thái `aggregate_kill_event_missing` khác về bản chất với `confirmed_no_kill_no_event`."""),
        """
df_disc = pd.read_csv(discrepancy_csv)
_disc_summary = (df_disc.groupby("timing_coverage_status", dropna=False)
                 .agg(player_match_count=("match_id", "size"),
                      aggregate_kills=("player_kills", "sum"),
                      absolute_events=("event_kill_count", "sum"),
                      absolute_discrepancy=("kill_discrepancy", "sum"))
                 .reset_index())
print("--- BẢNG 04-I: SAI LỆCH THEO TRẠNG THÁI COVERAGE ---")
print(_disc_summary.to_string(index=False))
print("\\n--- BẢNG 04-J: TOP 15 PLAYER-MATCH SAI LỆCH, FILE CSV VẪN GIỮ TOÀN BỘ ---")
print(df_disc.head(15).to_string(index=False))

coverage_csv = paths["tables"] / "event_timing_coverage.csv"
if coverage_csv.is_file():
    df_cov = pd.read_csv(coverage_csv)
    print("\\n--- BẢNG 04-H: COVERAGE PLAYER-MATCH THEO MODE VÀ TRẠNG THÁI ---")
    print(df_cov.to_string(index=False))

_examples = con.execute(\"\"\"
    SELECT match_id, player_name, player_kills, event_kill_count,
           phase_eligible_kill_count, first_kill_time, timing_coverage_status
    FROM read_parquet(?)
    QUALIFY row_number() OVER (PARTITION BY timing_coverage_status ORDER BY match_id, player_name) = 1
    ORDER BY timing_coverage_status
\"\"\", [str(final_pq)]).df()
print("\\n--- BẢNG 04-K: VÍ DỤ NO-KILL, MISSING, PARTIAL VÀ EXACT ---")
print(_examples.to_string(index=False))

_coverage_plot = df_cov.groupby("category", as_index=False)["player_match_count"].sum().sort_values("player_match_count")
fig, ax = plt.subplots(figsize=(9, max(4.5, 0.55 * len(_coverage_plot))))
ax.barh(_coverage_plot["category"], _coverage_plot["player_match_count"], color="#5b7c99")
ax.set(title="V04-03. Coverage Combat Timing ở grain player-match", xlabel="Số player-match", ylabel="Trạng thái")
ax.grid(axis="x", alpha=0.25)
for index, value in enumerate(_coverage_plot["player_match_count"]):
    ax.text(value, index, f" {int(value):,}", va="center")
fig.tight_layout()
coverage_fig_path = fig_dir / "nb04_player_match_coverage.png"
fig.savefig(coverage_fig_path, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"HÌNH V04-03 -> {coverage_fig_path.relative_to(PROJECT_ROOT)}")
""",
        ("markdown", r"""### VI. Kiểm tra hoàn tất stage NB04 và bàn giao

Đây là kiểm tra hoàn tất Notebook 04, không phải Gate G4 của dự án. Theo kế hoạch, Gate G4 chỉ được mở sau khi recipe/model/paired comparisons đã được đăng ký ở giai đoạn modeling. NB04 chỉ được bàn giao khi:
1. Tập dữ liệu chính thức $player\_match\_features.parquet$ đã được xuất thành công, đọc lại và kiểm tra toàn vẹn.
2. Đầy đủ các nhóm đặc trưng:
   - Chiến đấu cơ sở (`player_kills`, `player_dmg`, `damage_per_kill`).
   - Di chuyển (`player_dist_walk`, `player_dist_ride`, `total_distance`, `walk_ratio`).
   - Hỗ trợ (`player_assists`, `player_dbno`, `assist_ratio`).
   - Thời gian tuyệt đối (`event_kill_count`, `first_kill_time`, `avg_kill_time`, `has_kill`).
   - Thời gian phân pha (`early_kills`, `mid_kills`, `late_kills`, `early_kill_ratio`, `mid_kill_ratio`, `late_kill_ratio`).
   - Mục tiêu và chẩn đoán (`normalized_placement`, `player_survive_time`, `kills_per_minute`, `damage_per_minute`, `walk_velocity`, `ride_velocity`).
3. Khóa checkpoint manifest với định danh `player_match_features`.
4. Ba quyết định đơn vị/eligibility/ngưỡng phải có `status=verified` và bằng chứng không rỗng. Nếu còn `pending`, notebook chỉ lưu diagnostics, ghi `RUN-04` và dừng trước khi tạo dataset cuối hay bàn giao NB05."""),
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

print("--- BẢNG 04-L: EXPECTED / ACTUAL STAGE NB04 ---")
print(inspect_df.to_string(index=False))

_expected_actual = pd.DataFrame([
    {"Kiểm tra": "Bảo toàn dòng many-to-one", "Kỳ vọng": n_base, "Thực tế": final_rows, "Kết luận": "Đạt" if final_rows == n_base else "Không đạt"},
    {"Kiểm tra": "Discrepancy đủ mọi player-match", "Kỳ vọng": final_rows, "Thực tế": len(df_disc), "Kết luận": "Đạt" if len(df_disc) == final_rows else "Không đạt"},
    {"Kiểm tra": "Event ledger đủ dòng nguồn", "Kỳ vọng": _event_rows, "Thực tế": len(df_event_ledger), "Kết luận": "Đạt" if len(df_event_ledger) == _event_rows else "Không đạt"},
    {"Kiểm tra": "Phase counts = phase denominator", "Kỳ vọng": "Bằng nhau", "Thực tế": int((_phase_totals.sum() or 0)), "Kết luận": "Đạt" if int(_phase_totals.sum() or 0) == int(_timing_summary.iloc[0]["phase_eligible_event_count"] or 0) else "Không đạt"},
    {"Kiểm tra": "Ba quyết định dữ liệu thật", "Kỳ vọng": "verified kèm evidence", "Thực tế": f"{sum(_gate_table['Đủ điều kiện xuất bản'])}/3", "Kết luận": "Đạt" if _research_gate["ready"] else "Không đạt"},
    {"Kiểm tra": "Ba hình PNG", "Kỳ vọng": "3/3", "Thực tế": sum(path.is_file() for path in (timing_hist_path, phase_fig_path, coverage_fig_path)), "Kết luận": "Đạt" if all(path.is_file() for path in (timing_hist_path, phase_fig_path, coverage_fig_path)) else "Không đạt"},
])
print(_expected_actual.to_string(index=False))
if (_expected_actual["Kết luận"] != "Đạt").any():
    raise RuntimeError("Stage NB04 chưa đạt; sửa các dòng Không đạt trước khi bàn giao.")

# Khóa checkpoint manifest
_feature_version = cfg["features"]["feature_versions"]["feature_version"]
ckpt_mgr.commit("player_match_features", f"feature-v{_feature_version}", {
    "final_dataset": final_pq,
    "combat_timing": timing_pq,
    "discrepancy_table": discrepancy_csv,
    "timing_coverage": coverage_csv,
    "event_audit": event_audit_csv,
    "event_ledger": event_ledger_pq,
})

_nb04_artifacts = {
    "player_match_features": final_pq,
    "combat_timing": timing_pq,
    "kill_discrepancy": discrepancy_csv,
    "timing_coverage": coverage_csv,
    "event_audit": event_audit_csv,
    "event_ledger": event_ledger_pq,
    "absolute_timing_figure": timing_hist_path,
    "phase_counts_figure": phase_fig_path,
    "player_match_coverage_figure": coverage_fig_path,
}
_handover = []
for _name, _path in _nb04_artifacts.items():
    _handover.append({
        "Artifact": _name,
        "Đường dẫn": str(_path.relative_to(PROJECT_ROOT)),
        "Bytes": _path.stat().st_size,
        "SHA256": hash_file(_path)[:16] + "...",
        "Consumer": "05-09" if _name == "player_match_features" else "kiểm toán/báo cáo",
    })
print("\\n--- BẢNG 04-M: ARTIFACT VÀ BÀN GIAO ---")
print(pd.DataFrame(_handover).to_string(index=False))
print("\\nStage NB04 hoàn tất ở scope hiện tại. Tiếp theo: Notebook 05; không gọi đây là Gate G4.")
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

*Phạm vi thực thi:* fixture/development chỉ xác minh logic, bảng, hình và đường truyền config; không phải kết quả nghiên cứu. Khi chạy chính thức, các bảng thống kê được tính trên toàn bộ scope hợp lệ bằng DuckDB. Mẫu chỉ phục vụ trực quan hoặc chẩn đoán và phải công bố $n$, seed và quy tắc lấy mẫu."""),
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
    compute_sql_correlation_matrices,
    compute_player_retention_diagnostics,
    compute_combat_phase_by_placement_tier,
    run_structural_eda,
    run_chronology_audit,
)
from src.analysis.mode_analysis import analyze_behavior_by_mode, format_mode_differences_table
from src.analysis.correlation import compute_vif_summary
from src.data.checkpoints import CheckpointManager

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
con = get_duckdb_connection(temp_dir=paths["temp_dir"], **{k: cfg["runtime"]["duckdb"][k] for k in ("memory_limit", "threads")})
ckpt_mgr = CheckpointManager(manifest_path=paths["checkpoints"] / "checkpoint_manifest.json")
eda_cfg = cfg["eda"]
viz_sample_size = int(eda_cfg["sampling"]["viz_sample_size"])
diagnostic_sample_size = int(eda_cfg["sampling"]["diagnostic_sample_size"])
sampling_seed = int(eda_cfg["sampling"]["random_state"])
runtime_mode = cfg["runtime"].get("mode", "development")

# Kiểm tra tập dữ liệu hoàn chỉnh từ Notebook 04 và split khóa từ Notebook 02
source_pq = paths["processed"] / "player_match_features.parquet"
meta_pq = paths["interim"] / "match_metadata.parquet"
split_pq = paths["interim"] / "split_assignments.parquet"

if not source_pq.is_file():
    raise FileNotFoundError(f"Không tìm thấy {source_pq}. Hãy chạy hoàn tất notebook 04_combat_timing.ipynb trước.")

scope_cfg = eda_cfg["scope"]
analysis_scope = scope_cfg["analysis_scope"]
if analysis_scope == "development":
    if not split_pq.is_file():
        raise FileNotFoundError(f"Thiếu {split_pq}; NB05 development không được mở final test và cần split từ NB02.")
    allowed_splits = list(scope_cfg["allowed_development_splits"])
    if not allowed_splits or "test" in allowed_splits:
        raise ValueError("eda.scope.allowed_development_splits phải không rỗng và không chứa test")
    final_pq = paths["temp_dir"] / "eda_development_scope.parquet"
    safe_source = source_pq.resolve().as_posix().replace("'", "''")
    safe_split = split_pq.resolve().as_posix().replace("'", "''")
    safe_scope = final_pq.resolve().as_posix().replace("'", "''")
    split_sql = ", ".join("'" + item.replace("'", "''") + "'" for item in allowed_splits)
    con.execute(f\"\"\"
        COPY (
            SELECT f.* FROM read_parquet('{safe_source}') f
            INNER JOIN read_parquet('{safe_split}') s USING (match_id)
            WHERE s.split IN ({split_sql})
        ) TO '{safe_scope}' (FORMAT PARQUET, COMPRESSION ZSTD)
    \"\"\")
elif analysis_scope == "full_descriptive_locked" and bool(scope_cfg["full_descriptive_locked"]):
    final_pq = source_pq
else:
    raise RuntimeError("EDA scope chưa hợp lệ: dùng development hoặc khóa full_descriptive_locked có chủ đích.")

print("Nạp dữ liệu thành công cho EDA:")
print(f"- Nguồn: {source_pq.name}; scope phân tích: {analysis_scope}; file làm việc: {final_pq.name}")
print(f"- Metadata trận đấu: {meta_pq.name}")
print(f"- Runtime mode: {runtime_mode}; mọi sample dùng reservoir seed={sampling_seed}")
print("- Cảnh báo: fixture/development chỉ kiểm thử logic, không phải kết quả nghiên cứu chính thức.")
eda_figure_rows = []
eda_scope_n = int(con.execute("SELECT count(*) FROM read_parquet(?)", [str(final_pq)]).fetchone()[0])

def eda_figure_caption(figure, file, n_plot, rule, source_tables, sampled=False):
    caption = (f"Scope={analysis_scope}; N player-match={eda_scope_n}; n biểu diễn={n_plot}; "
               f"seed={sampling_seed if sampled else 'không áp dụng'}; {rule}")
    sources = ";".join(source_tables)
    figure.text(0.01, 0.01, caption + "\\nNguồn: " + sources +
                "\\nĐơn vị vật lý chưa xác minh; placement [0,1]. Association không chứng minh nhân quả.", fontsize=8)
    figure.tight_layout(rect=(0, 0.18, 1, 0.94))
    eda_figure_rows.append({"figure_id": file.stem, "path": str(file), "source_table": sources,
        "scope": analysis_scope, "n_scope": eda_scope_n, "sample_n": n_plot,
        "sample_seed": sampling_seed if sampled else None, "sampling_rule": rule,
        "sampled": sampled, "caption": caption, "report_ready": False})
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
df_game_size = con.execute(f\"\"\"
    SELECT game_size FROM read_parquet(?)
    USING SAMPLE reservoir({viz_sample_size} ROWS) REPEATABLE ({sampling_seed});
\"\"\", [str(final_pq)]).df()
sns.histplot(df_game_size["game_size"], bins=30, ax=axes[1], color="#45818e", kde=True)
axes[1].set_title("Phân bố Quy mô Trận đấu - Game Size (Chart A04)", fontsize=11, pad=10)
axes[1].set_xlabel("Số người chơi trong trận")
axes[1].grid(axis="y", linestyle="--", alpha=0.5)

plt.tight_layout()
fig_path_a = paths["figures"] / "eda_group_a_structure.png"
eda_figure_caption(fig, fig_path_a, len(df_game_size), "A03 toàn scope; A04 reservoir visualization only", ["eda_structural_overview.csv"], True)
plt.savefig(fig_path_a, dpi=150, bbox_inches="tight")
plt.show()
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
eda_figure_caption(fig, fig_path_b, eda_scope_n, "Toàn scope; tỷ lệ missing/zero theo từng feature", ["eda_data_quality_summary.csv"])
plt.savefig(fig_path_b, dpi=150, bbox_inches="tight")
plt.show()
plt.close()
print(f"Đã lưu biểu đồ chất lượng dữ liệu -> {fig_path_b.relative_to(PROJECT_ROOT)}")
""",
        ("markdown", r"""### IV. Phân tích Phân bố Đặc trưng Hành vi Thô (Group C: Raw Distributions B01–B10)

Chúng ta tính toán các đại lượng thống kê mô tả toàn diện cho các đặc trưng thô:
- Độ tập trung: Trung bình cộng ($Mean$), Trung vị ($Median$).
- Độ phân tán: Độ lệch chuẩn ($Std$), Khoảng tứ phân vị ($P_{25}, P_{75}$).
- Miền giá trị: Cực tiểu ($Min$), Cực đại ($Max$), và Bách phân vị thứ 95 ($P_{95}$).
- Độ bất đối xứng: Hệ số bất đối xứng Fisher-Pearson ($Skewness$). Chiều và độ lớn chỉ được diễn giải sau khi đọc bảng sinh ra ở scope hiện tại; notebook không hard-code kết luận phân bố."""),
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
df_sample_raw = con.execute(f\"\"\"
    SELECT player_kills, player_dmg, player_dist_walk, player_survive_time, normalized_placement
    FROM read_parquet(?)
    USING SAMPLE reservoir({viz_sample_size} ROWS) REPEATABLE ({sampling_seed});
\"\"\", [str(final_pq)]).df()

fig, axes = plt.subplots(2, 3, figsize=(14, 8))

# Kills (B01)
sns.histplot(df_sample_raw["player_kills"], bins=20, ax=axes[0, 0], color="#2b5c8f", discrete=True)
axes[0, 0].set_title("B01: Số Mạng Hạ Gục (player_kills)", fontsize=11)
axes[0, 0].set_xlabel("Số kills")

# Damage (B02)
sns.histplot(df_sample_raw["player_dmg"], bins=40, ax=axes[0, 1], color="#3d85c6", kde=True)
axes[0, 1].set_title("B02: Tổng Sát Thương (player_dmg)", fontsize=11)
axes[0, 1].set_xlabel("Sát thương (đơn vị nguồn chưa xác minh)")

# Walk distance (B05)
sns.histplot(df_sample_raw["player_dist_walk"], bins=40, ax=axes[0, 2], color="#274e13", kde=True)
axes[0, 2].set_title("B05: Quãng Đường Đi Bộ (player_dist_walk)", fontsize=11)
axes[0, 2].set_xlabel("Khoảng cách - đơn vị nguồn chưa xác minh")

# Survival time (B08)
sns.histplot(df_sample_raw["player_survive_time"], bins=40, ax=axes[1, 0], color="#783f04", kde=True)
axes[1, 0].set_title("B08: Thời Gian Sinh Tồn (player_survive_time)", fontsize=11)
axes[1, 0].set_xlabel("Thời gian - đơn vị nguồn chưa xác minh")

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
eda_figure_caption(fig, fig_path_c, len(df_sample_raw), "Reservoir visualization only; histogram/z-score", ["eda_raw_distributions_summary.csv"], True)
plt.savefig(fig_path_c, dpi=150, bbox_inches="tight")
plt.show()
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
df_sample_derived = con.execute(f\"\"\"
    SELECT damage_per_kill, walk_ratio, assist_ratio, kills_per_minute, walk_velocity
    FROM read_parquet(?)
    USING SAMPLE reservoir({viz_sample_size} ROWS) REPEATABLE ({sampling_seed});
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
axes[2].set_title("Vận Tốc Đi Bộ (walk_velocity <= 5 đơn vị nguồn)", fontsize=11)
axes[2].set_xlabel("Khoảng cách / thời gian nguồn; đơn vị chưa xác minh")

plt.tight_layout()
fig_path_d = paths["figures"] / "eda_group_d_derived_distributions.png"
eda_figure_caption(fig, fig_path_d, len(df_sample_derived), "Reservoir visualization only; dpk <=500, velocity <=5 chỉ giới hạn hình", ["eda_derived_distributions_summary.csv"], True)
plt.savefig(fig_path_d, dpi=150, bbox_inches="tight")
plt.show()
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

*Quy tắc quyết định cho RQ2:* Chỉ khuyến nghị `per_mode` khi các biến hành vi, không gồm survival hoặc placement, cho thấy khác biệt mode có cỡ tác động đủ lớn. Kết quả fixture chỉ kiểm tra cơ chế và không khóa quyết định nghiên cứu."""),
        """
# - Bước 5: Phân tích so sánh chế độ chơi và tính toán cỡ tác động
mode_compare_cols = [
    "player_kills", "player_dmg", "player_dist_walk", "player_dist_ride",
    "player_assists", "player_dbno"
]

# Đọc mẫu lớn cân đối theo chế độ để kiểm định Kruskal-Wallis
df_mode_sample = con.execute(f\"\"\"
    SELECT * FROM (
        SELECT team_size_mode, player_kills, player_dmg, player_dist_walk, player_dist_ride,
               player_assists, player_dbno
        FROM read_parquet(?)
        WHERE lower(team_size_mode) IN ('solo', 'duo', 'squad')
    ) AS eligible_modes
    USING SAMPLE reservoir({diagnostic_sample_size} ROWS) REPEATABLE ({sampling_seed})
\"\"\", [str(final_pq)]).df()

mode_results = analyze_behavior_by_mode(df_mode_sample, mode_compare_cols, mode_col="team_size_mode")
mode_diff_table = format_mode_differences_table(mode_results["mode_differences"])

atomic_write_csv(paths["tables"] / "eda_mode_comparison_summary.csv", mode_results["summary_table"])
atomic_write_csv(paths["tables"] / "eda_mode_differences_test.csv", mode_diff_table)
atomic_write_json(paths["manifests"] / "mode_analysis.json", {
    "mode_differences": mode_results["mode_differences"],
    "recommended_rq2_strategy": mode_results["recommended_rq2_strategy"],
    "scope": analysis_scope,
    "source_checksum": hash_file(source_pq),
    "split_checksum": hash_file(split_pq),
    "analysis_input_checksum": hash_file(final_pq),
    "sample_n": int(len(df_mode_sample)),
    "sample_seed": sampling_seed,
    "sampling_rule": "DuckDB reservoir; diagnostic only",
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
eda_figure_caption(fig, fig_path_e, len(df_mode_sample), "Reservoir diagnostic; không gọi kiểm định này full-data", ["eda_mode_comparison_summary.csv", "eda_mode_differences_test.csv"], True)
plt.savefig(fig_path_e, dpi=150, bbox_inches="tight")
plt.show()
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
# - Bước 6: Tính chính xác Pearson, Spearman với average ranks cho ties và N từng cặp
corr_features = [
    "player_kills", "player_dmg", "damage_per_kill",
    "player_dist_walk", "player_dist_ride", "total_distance", "walk_ratio",
    "player_assists", "player_dbno",
    "first_kill_time", "player_survive_time", "normalized_placement"
]

pearson_corr, spearman_corr, correlation_pair_n = compute_sql_correlation_matrices(
    con, final_pq, corr_features
)

atomic_write_csv(paths["tables"] / "eda_correlation_matrix_pearson.csv", pearson_corr.rename_axis("feature").reset_index())
atomic_write_csv(paths["tables"] / "eda_correlation_matrix_spearman.csv", spearman_corr.rename_axis("feature").reset_index())
atomic_write_csv(paths["tables"] / "eda_correlation_pair_n.csv", correlation_pair_n.rename_axis("feature").reset_index())

# VIF là chẩn đoán trên mẫu tái lập, không tự động loại feature.
vif_predictors = ["player_kills", "player_dmg", "player_dist_walk", "player_dist_ride", "player_assists", "player_dbno"]
df_vif_source = con.execute(f\"\"\"
    SELECT {', '.join(vif_predictors)} FROM read_parquet(?)
    USING SAMPLE reservoir({diagnostic_sample_size} ROWS) REPEATABLE ({sampling_seed})
\"\"\", [str(final_pq)]).df()
vif_summary = compute_vif_summary(df_vif_source, vif_predictors)
atomic_write_csv(paths["tables"] / "eda_vif_diagnostics.csv", vif_summary)

# Trực quan hóa hai biểu đồ nhiệt (Heatmaps) cạnh nhau
fig, axes = plt.subplots(1, 2, figsize=(16, 7))

sns.heatmap(pearson_corr, annot=True, fmt=".2f", cmap="coolwarm", center=0, ax=axes[0], cbar_kws={"shrink": 0.8}, annot_kws={"size": 8})
axes[0].set_title("E01: Ma Trận Tương Quan Tuyến Tính Pearson (r)", fontsize=12, pad=10)

sns.heatmap(spearman_corr, annot=True, fmt=".2f", cmap="vlag", center=0, ax=axes[1], cbar_kws={"shrink": 0.8}, annot_kws={"size": 8})
axes[1].set_title("E02: Ma Trận Tương Quan Thứ Bậc Spearman (rho)", fontsize=12, pad=10)

plt.tight_layout()
fig_path_f = paths["figures"] / "eda_group_f_correlation_heatmaps.png"
eda_figure_caption(fig, fig_path_f, eda_scope_n, "Toàn scope; N hợp lệ theo từng cặp trong bảng pair_n", ["eda_correlation_matrix_pearson.csv", "eda_correlation_matrix_spearman.csv", "eda_correlation_pair_n.csv"])
plt.savefig(fig_path_f, dpi=150, bbox_inches="tight")
plt.show()
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

Đối với từng phân khúc, chúng ta tính tỷ trọng trung bình các mạng hạ gục ở ba pha Early, Mid và Late. Hình chỉ mô tả mối liên hệ quan sát được; không giả định trước chiều kết quả và không suy diễn nhân quả."""),
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
eda_figure_caption(fig, fig_path_g, eda_scope_n, "Toàn scope; conditional mean trên kill-active rows", ["eda_timing_by_placement_group.csv"])
plt.savefig(fig_path_g, dpi=150, bbox_inches="tight")
plt.show()
plt.close()
print(f"Đã lưu biểu đồ trọng tâm H06 -> {fig_path_g.relative_to(PROJECT_ROOT)}")
""",
        ("markdown", r"""### IX. Đánh giá Khả thi Lịch sử và Đường cong Giữ chân Người chơi (Group H: Historical Feasibility & Retention I01–I03)

Trước khi tiến hành xây dựng các đặc trưng lịch sử phục vụ bài toán dự đoán tương lai ($RQ3$), chúng ta thẩm định tính khả thi của dữ liệu:
1. **Cấp bậc Chronology:** Đọc từ artifact kiểm toán của Notebook 02; fixture không được dùng để tự khóa Grade A/B/C cho dữ liệu thật.
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
eda_figure_caption(fig, fig_path_h, eda_scope_n, "Toàn scope; số hồ sơ và coverage theo ngưỡng", ["eda_historical_retention_diagnostics.csv"])
plt.savefig(fig_path_h, dpi=150, bbox_inches="tight")
plt.show()
plt.close()
print(f"Đã lưu biểu đồ giữ chân người chơi -> {fig_path_h.relative_to(PROJECT_ROOT)}")
""",
        ("markdown", r"""### IX-A. Bổ sung catalog A01-I03 và biên nhận quyết định

Các hình bổ sung dưới đây bao phủ những ID chưa xuất hiện trong tám hình tổng hợp phía trên. Mọi scatter chỉ dùng visualization sample tái lập; bảng thống kê và hệ số vẫn lấy từ toàn bộ scope đã khóa. I02 và I03 được ghi rõ là `deferred` vì thuộc kiểm toán lịch sử/chronology ở Notebook 08 và Notebook 02, không được bịa kết quả trong NB05."""),
        """
# - Bước 9: Render các mục catalog còn thiếu và xuất catalog status/decision receipt
available_cols = set(con.execute("SELECT * FROM read_parquet(?) LIMIT 0", [str(final_pq)]).df().columns)
catalog_sample_cols = [
    "player_kills", "player_dmg", "player_assists", "player_dbno",
    "player_dist_walk", "player_dist_ride", "total_distance",
    "player_survive_time", "team_placement", "normalized_placement",
    "kills_per_minute", "damage_per_minute", "assist_ratio",
    "first_kill_time", "early_kill_ratio", "mid_kill_ratio", "late_kill_ratio",
    "team_size_mode", "date",
]
catalog_sample_cols = [column for column in catalog_sample_cols if column in available_cols]
df_catalog_sample = con.execute(f\"\"\"
    SELECT {', '.join(catalog_sample_cols)} FROM read_parquet(?)
    USING SAMPLE reservoir({viz_sample_size} ROWS) REPEATABLE ({sampling_seed})
\"\"\", [str(final_pq)]).df()
atomic_write_csv(paths["tables"] / "eda_visualization_sample.csv", df_catalog_sample)
scope_rows = int(df_struct.iloc[0]["total_player_records"])
plot_caption = (f"Scope={analysis_scope}; N scope={scope_rows}; n vẽ={len(df_catalog_sample)}; "
                f"seed={sampling_seed}; reservoir, chỉ để trực quan; không suy nhân quả")
survival_unit = cfg["schema"]["aggregate"].get("units", {}).get("player_survive_time", "đơn vị nguồn chưa xác minh")
event_unit = cfg["schema"]["deaths"].get("units", {}).get("time", "đơn vị nguồn chưa xác minh")

# A01, A05, A06
fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
games_per_player = con.execute("SELECT count(*) games FROM read_parquet(?) WHERE player_name IS NOT NULL AND trim(player_name) <> '' GROUP BY player_name", [str(final_pq)]).df()
teams_per_match = con.execute("SELECT count(distinct team_id) teams FROM read_parquet(?) GROUP BY match_id", [str(final_pq)]).df()
games_distribution = games_per_player.groupby("games").size().reset_index(name="players")
teams_distribution = teams_per_match.groupby("teams").size().reset_index(name="matches")
atomic_write_csv(paths["tables"] / "eda_matches_per_player_distribution.csv", games_distribution)
atomic_write_csv(paths["tables"] / "eda_teams_per_match_distribution.csv", teams_distribution)
sns.histplot(games_per_player["games"], discrete=True, ax=axes[0], color="#2b5c8f")
axes[0].set(title="A01: Số trận mỗi người chơi", xlabel="Số trận", ylabel="Số người chơi")
sns.histplot(teams_per_match["teams"], discrete=True, ax=axes[1], color="#45818e")
axes[1].set(title="A05: Số đội mỗi trận", xlabel="Số đội", ylabel="Số trận")
if "date" in df_catalog_sample:
    dates = pd.to_datetime(df_catalog_sample["date"], errors="coerce", utc=True).dropna().dt.floor("D").value_counts().sort_index()
    axes[2].plot(dates.index, dates.values, color="#274e13")
    axes[2].tick_params(axis="x", rotation=30)
    axes[2].set(title="A06: Độ phủ ngày thi đấu", xlabel="Ngày UTC", ylabel="Số player-match")
    a06_status = "rendered"
else:
    axes[2].text(0.5, 0.5, "Không có cột date trong scope", ha="center", va="center")
    axes[2].set(title="A06: not_applicable trong scope")
    a06_status = "not_applicable_missing_date"
plt.tight_layout()
fig_path_a_extra = paths["figures"] / "eda_group_a_catalog_supplement.png"
eda_figure_caption(fig, fig_path_a_extra, len(df_catalog_sample), "A01/A05 toàn scope, A01 loại tên thiếu; A06 reservoir visualization only", ["eda_matches_per_player_distribution.csv", "eda_teams_per_match_distribution.csv", "eda_visualization_sample.csv"], True)
plt.savefig(fig_path_a_extra, dpi=150, bbox_inches="tight"); plt.show(); plt.close()

# B03, B04, B06, B07, B09 và C01, C02, C05
supplement_specs = [
    ("B03", "player_assists"), ("B04", "player_dbno"), ("B06", "player_dist_ride"),
    ("B07", "total_distance"), ("B09", "team_placement"), ("C01", "kills_per_minute"),
    ("C02", "damage_per_minute"), ("C05", "assist_ratio"),
]
fig, axes = plt.subplots(2, 4, figsize=(16, 8))
for ax, (chart_id, column) in zip(axes.flat, supplement_specs):
    sns.histplot(df_catalog_sample[column].dropna(), bins=25, ax=ax, color="#3d85c6")
    ax.set(title=f"{chart_id}: {column}", xlabel=column, ylabel="Số quan sát")
plt.tight_layout()
fig_path_bc_extra = paths["figures"] / "eda_groups_bc_catalog_supplement.png"
eda_figure_caption(fig, fig_path_bc_extra, len(df_catalog_sample), "Reservoir visualization only; histogram", ["eda_visualization_sample.csv"], True)
plt.savefig(fig_path_bc_extra, dpi=150, bbox_inches="tight"); plt.show(); plt.close()

# D04, D06, D07, D08: mô tả outcome theo mode, không dùng để chọn representation RQ2.
fig, axes = plt.subplots(2, 2, figsize=(12, 8))
for ax, (chart_id, column) in zip(axes.flat, [
    ("D04", "player_dbno"), ("D06", "player_dist_ride"),
    ("D07", "player_survive_time"), ("D08", "normalized_placement"),
]):
    sns.boxplot(data=df_catalog_sample, x="team_size_mode", y=column, ax=ax)
    ax.set(title=f"{chart_id}: {column} theo mode", xlabel="Team-size mode", ylabel=column)
plt.tight_layout()
fig_path_d_extra = paths["figures"] / "eda_group_d_catalog_supplement.png"
eda_figure_caption(fig, fig_path_d_extra, len(df_catalog_sample), "Reservoir visualization only; boxplot theo mode", ["eda_visualization_sample.csv"], True)
plt.savefig(fig_path_d_extra, dpi=150, bbox_inches="tight"); plt.show(); plt.close()

# F01-F07 và G01-G06: visualization sample only; không thay thế exact correlation tables.
behavior_cols = ["player_kills", "player_dmg", "player_assists", "player_dbno", "player_dist_walk", "player_dist_ride", "total_distance"]
for prefix, target, selected in (("F", "player_survive_time", behavior_cols), ("G", "normalized_placement", behavior_cols[:6])):
    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    for number, (ax, column) in enumerate(zip(axes.flat, selected), start=1):
        pair = df_catalog_sample[[column, target]].replace([np.inf, -np.inf], np.nan).dropna()
        density = ax.hexbin(pair[column], pair[target], gridsize=22, mincnt=1, cmap="viridis")
        fig.colorbar(density, ax=ax, label="Số player-match/ô")
        ax.set(title=f"{prefix}{number:02d}: {column}; n hợp lệ={len(pair)}", xlabel=column,
               ylabel=f"Survival ({survival_unit})" if prefix == "F" else "Placement chuẩn hóa [0,1]")
    for ax in axes.flat[len(selected):]: ax.axis("off")
    fig.suptitle(plot_caption, fontsize=10)
    plt.tight_layout(rect=(0, 0, 1, 0.94))
    output = paths["figures"] / f"eda_group_{prefix.lower()}_behavior_vs_outcome.png"
    eda_figure_caption(fig, output, len(df_catalog_sample), "Reservoir visualization only; finite pairs; hexbin count", ["eda_visualization_sample.csv"], True)
    plt.savefig(output, dpi=150, bbox_inches="tight"); plt.show(); plt.close()

# H01-H05 và H07; H06 đã render từ bảng exact ở trên.
fig, axes = plt.subplots(2, 3, figsize=(15, 8))
phase_means = df_catalog_sample[["early_kill_ratio", "mid_kill_ratio", "late_kill_ratio"]].mean()
axes[0, 0].bar(["Early", "Mid", "Late"], phase_means.values); axes[0, 0].set(title="H01-H02: Tỷ trọng pha", ylabel="Tỷ lệ trung bình")
sns.histplot(df_catalog_sample["first_kill_time"].dropna(), bins=25, ax=axes[0, 1]); axes[0, 1].set(title="H03: Thời điểm kill đầu", xlabel=event_unit)
for ax, target, title in [(axes[0, 2], "player_survive_time", "H04: Kill đầu và survival"), (axes[1, 0], "normalized_placement", "H05: Kill đầu và placement")]:
    pair = df_catalog_sample[["first_kill_time", target]].replace([np.inf, -np.inf], np.nan).dropna()
    density = ax.hexbin(pair["first_kill_time"], pair[target], gridsize=20, mincnt=1)
    fig.colorbar(density, ax=ax, label="Số player-match/ô")
    ax.set(title=f"{title}; n hợp lệ={len(pair)}", xlabel=event_unit,
           ylabel=survival_unit if target == "player_survive_time" else "Placement chuẩn hóa [0,1]")
sns.boxplot(data=df_catalog_sample, x="team_size_mode", y="first_kill_time", ax=axes[1, 1]); axes[1, 1].set(title="H07: Timing theo mode", xlabel="Mode", ylabel=event_unit)
axes[1, 2].axis("off")
fig.suptitle(plot_caption, fontsize=10)
plt.tight_layout(rect=(0, 0, 1, 0.94))
fig_path_h_extra = paths["figures"] / "eda_group_h_timing_catalog_supplement.png"
eda_figure_caption(fig, fig_path_h_extra, len(df_catalog_sample), "Reservoir visualization only; finite/kill-active rows", ["eda_visualization_sample.csv"], True)
plt.savefig(fig_path_h_extra, dpi=150, bbox_inches="tight"); plt.show(); plt.close()

group_artifacts = {
    "structural": "eda_group_a_structure.png;eda_group_a_catalog_supplement.png;eda_group_h_retention_curve.png",
    "raw_distributions": "eda_group_c_raw_distributions.png;eda_groups_bc_catalog_supplement.png",
    "derived_ratios": "eda_group_d_derived_distributions.png;eda_group_b_missing_and_zeros.png;eda_groups_bc_catalog_supplement.png",
    "mode_comparison": "eda_group_e_mode_comparisons.png;eda_group_d_catalog_supplement.png",
    "correlation": "eda_group_f_correlation_heatmaps.png",
    "behavior_vs_survival": "eda_group_f_behavior_vs_outcome.png",
    "behavior_vs_placement": "eda_group_g_behavior_vs_outcome.png",
    "combat_timing": "eda_group_g_timing_by_placement.png;eda_group_h_timing_catalog_supplement.png",
    "historical": "eda_group_h_retention_curve.png",
}
group_sources = {
    "structural": "eda_structural_overview.csv;eda_matches_per_player_distribution.csv;eda_teams_per_match_distribution.csv;eda_visualization_sample.csv;eda_historical_retention_diagnostics.csv",
    "raw_distributions": "eda_raw_distributions_summary.csv;eda_visualization_sample.csv",
    "derived_ratios": "eda_derived_distributions_summary.csv;eda_data_quality_summary.csv;eda_visualization_sample.csv",
    "mode_comparison": "eda_mode_comparison_summary.csv;eda_mode_differences_test.csv;eda_visualization_sample.csv",
    "correlation": "eda_correlation_matrix_pearson.csv;eda_correlation_matrix_spearman.csv;eda_correlation_pair_n.csv",
    "behavior_vs_survival": "eda_visualization_sample.csv",
    "behavior_vs_placement": "eda_visualization_sample.csv",
    "combat_timing": "eda_timing_by_placement_group.csv;eda_visualization_sample.csv",
    "historical": "eda_historical_retention_diagnostics.csv",
}
catalog_rows = []
for group, charts in eda_cfg["catalog"].items():
    for chart in charts:
        deferred = chart["id"] in {"I02", "I03"}
        status = "deferred_to_nb08_or_nb02" if deferred else (a06_status if chart["id"] == "A06" else "rendered")
        catalog_rows.append({
            "chart_id": chart["id"], "group": group, "name": chart["name"], "status": status,
            "scope": analysis_scope, "sample_n": int(len(df_catalog_sample)), "sample_seed": sampling_seed,
            "sampling_rule": "visualization reservoir; statistics use complete selected analysis scope",
            "source_table": group_sources[group],
            "caption": plot_caption,
            "how_to_read": "Đọc n hợp lệ ở từng panel; màu đậm biểu thị nhiều quan sát, không phải tác động nhân quả.",
            "artifact": group_artifacts[group],
            "reason": "I02 cần historical features; I03 đọc chronology audit" if deferred else "",
        })
catalog_status = pd.DataFrame(catalog_rows)
atomic_write_csv(paths["tables"] / "eda_catalog_status.csv", catalog_status)
atomic_write_csv(paths["tables"] / "eda_figure_catalog.csv", pd.DataFrame(eda_figure_rows))
_pubg_figure_details = {Path(row["path"]).name: row for row in eda_figure_rows}
print("--- BẢNG 05-FIGURE: NGUỒN VÀ PHẠM VI TỪNG HÌNH ---")
print(pd.DataFrame(eda_figure_rows).to_string(index=False))

decision_receipt = pd.DataFrame([
    {"decision": "analysis_scope", "status": "verified_config", "value": analysis_scope, "evidence": "split-filtered working parquet"},
    {"decision": "mode_strategy", "status": "user_selected_with_fixture_mechanism", "value": cfg["rq2"]["mode_strategy"], "evidence": cfg["rq2"]["mode_decision_reason"]},
    {"decision": "log_transform", "status": eda_cfg["decisions"]["log_transform_status"], "value": str(eda_cfg["decisions"]["log_transform_features"]), "evidence": eda_cfg["decisions"]["log_transform_reason"]},
    {"decision": "outlier_policy", "status": "verified_config", "value": eda_cfg["decisions"]["outlier_policy"], "evidence": "full distribution tables retained; plot limits do not alter cohort"},
])
atomic_write_csv(paths["tables"] / "eda_decision_receipt.csv", decision_receipt)
print("--- BẢNG 05-CATALOG: TRẠNG THÁI A01-I03 ---")
print(catalog_status.to_string(index=False))
print("\\n--- BẢNG 05-DECISION: BIÊN NHẬN QUYẾT ĐỊNH ---")
print(decision_receipt.to_string(index=False))
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

Checkpoint này chỉ ghi nhận hoàn tất stage NB05 trong scope hiện tại. Nó không phải Gate G5; G5 chỉ đạt sau khi artifact full-data hợp lệ và final manifest được khóa."""),
        """
# - Bước 9: Kiểm tra sự tồn tại của toàn bộ artifacts và khóa checkpoint
required_tables = [
    paths["tables"] / "eda_matches_per_player_distribution.csv",
    paths["tables"] / "eda_teams_per_match_distribution.csv",
    paths["tables"] / "eda_figure_catalog.csv",
    paths["tables"] / "eda_visualization_sample.csv",
    paths["tables"] / "eda_structural_overview.csv",
    paths["tables"] / "eda_data_quality_summary.csv",
    paths["tables"] / "eda_raw_distributions_summary.csv",
    paths["tables"] / "eda_derived_distributions_summary.csv",
    paths["tables"] / "eda_mode_comparison_summary.csv",
    paths["tables"] / "eda_correlation_matrix_pearson.csv",
    paths["tables"] / "eda_correlation_matrix_spearman.csv",
    paths["tables"] / "eda_correlation_pair_n.csv",
    paths["tables"] / "eda_vif_diagnostics.csv",
    paths["tables"] / "eda_timing_by_placement_group.csv",
    paths["tables"] / "eda_historical_retention_diagnostics.csv",
    paths["tables"] / "eda_catalog_status.csv",
    paths["tables"] / "eda_decision_receipt.csv",
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
    paths["figures"] / "eda_group_a_catalog_supplement.png",
    paths["figures"] / "eda_groups_bc_catalog_supplement.png",
    paths["figures"] / "eda_group_d_catalog_supplement.png",
    paths["figures"] / "eda_group_f_behavior_vs_outcome.png",
    paths["figures"] / "eda_group_g_behavior_vs_outcome.png",
    paths["figures"] / "eda_group_h_timing_catalog_supplement.png",
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
    {"Nhóm": "1. Cấu trúc", "Bảng": "eda_structural_overview.csv", "Biểu đồ": "eda_group_a_structure.png"},
    {"Nhóm": "2. Chất lượng", "Bảng": "eda_data_quality_summary.csv", "Biểu đồ": "eda_group_b_missing_and_zeros.png"},
    {"Nhóm": "3. Biến gốc", "Bảng": "eda_raw_distributions_summary.csv", "Biểu đồ": "eda_group_c_raw_distributions.png"},
    {"Nhóm": "4. Biến dẫn xuất", "Bảng": "eda_derived_distributions_summary.csv", "Biểu đồ": "eda_group_d_derived_distributions.png"},
    {"Nhóm": "5. Chế độ chơi", "Bảng": "eda_mode_comparison_summary.csv", "Biểu đồ": "eda_group_e_mode_comparisons.png"},
    {"Nhóm": "6. Tương quan", "Bảng": "eda_correlation_matrix_pearson.csv", "Biểu đồ": "eda_group_f_correlation_heatmaps.png"},
    {"Nhóm": "7. Giao tranh", "Bảng": "eda_timing_by_placement_group.csv", "Biểu đồ": "eda_group_g_timing_by_placement.png"},
    {"Nhóm": "8. Lịch sử", "Bảng": "eda_historical_retention_diagnostics.csv", "Biểu đồ": "eda_group_h_retention_curve.png"},
]

print("\\n================================================================================")
print(f"STAGE NB05 HOÀN TẤT TRONG SCOPE {analysis_scope.upper()}; KHÔNG PHẢI GATE G5")
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
   - **Tương quan thứ bậc Spearman ($\rho$):** Đo lường mối quan hệ đơn điệu (monotonic) dựa trên thứ hạng quan sát. Khi $|\rho-r| \ge 0.10$, notebook chỉ gắn cờ để kiểm tra phi tuyến, ngoại lệ và ties; không tự kết luận nguyên nhân.
2. **Quy chuẩn phân loại độ mạnh tương quan (Correlation Magnitude Convention):**
   - $|r| < 0.10$: Rất yếu / Không đáng kể (negligible).
   - $0.10 \le |r| < 0.30$: Yếu (weak).
   - $0.30 \le |r| < 0.50$: Trung bình (moderate).
   - $|r| \ge 0.50$: Mạnh (strong).
   *Lưu ý nguyên tắc:* Không đánh đồng giá trị $p < 0.05$ là mối quan hệ mạnh. Khi $N$ lớn, một effect nhỏ vẫn có thể cho p-value nhỏ; vì vậy phải đọc đồng thời độ lớn, chiều, $N$, mode và giới hạn thiết kế.
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
from src.data.io import get_duckdb_connection

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
registry = FeatureRegistry()
ckpt_mgr = CheckpointManager(manifest_path=paths["checkpoints"] / "checkpoint_manifest.json")
con = get_duckdb_connection(temp_dir=paths["temp_dir"], **{k: cfg["runtime"]["duckdb"][k] for k in ("memory_limit", "threads")})

source_pq = paths["processed"] / "player_match_features.parquet"
split_pq = paths["interim"] / "split_assignments.parquet"
if not source_pq.is_file():
    raise FileNotFoundError(f"Không tìm thấy {source_pq}. Hãy chạy hoàn tất notebook 04 trước.")

scope_cfg = cfg["eda"]["scope"]
analysis_scope = scope_cfg["analysis_scope"]
if analysis_scope == "development":
    if not split_pq.is_file():
        raise FileNotFoundError(f"Thiếu {split_pq}; NB06 không được mở final test khi chưa có split khóa từ NB02.")
    allowed_splits = list(scope_cfg["allowed_development_splits"])
    if not allowed_splits or "test" in allowed_splits:
        raise ValueError("eda.scope.allowed_development_splits phải không rỗng và không chứa test")
    final_pq = paths["temp_dir"] / "rq1_development_scope.parquet"
    safe_source = source_pq.resolve().as_posix().replace("'", "''")
    safe_split = split_pq.resolve().as_posix().replace("'", "''")
    safe_scope = final_pq.resolve().as_posix().replace("'", "''")
    split_sql = ", ".join("'" + item.replace("'", "''") + "'" for item in allowed_splits)
    con.execute(f\"\"\"
        COPY (
            SELECT f.* FROM read_parquet('{safe_source}') f
            INNER JOIN read_parquet('{safe_split}') s USING (match_id)
            WHERE s.split IN ({split_sql})
        ) TO '{safe_scope}' (FORMAT PARQUET, COMPRESSION ZSTD)
    \"\"\")
elif analysis_scope == "full_descriptive_locked" and bool(scope_cfg["full_descriptive_locked"]):
    final_pq = source_pq
else:
    raise RuntimeError("RQ1 scope chưa hợp lệ: dùng development hoặc khóa full_descriptive_locked có chủ đích.")

print(f"Khởi tạo RQ1 Pipeline thành công:")
print(f"- Dữ liệu nguồn: {source_pq.name}; scope phân tích: {analysis_scope}; file làm việc: {final_pq.name}")
print(f"- Số lượng đặc trưng đã đăng ký: {len(registry.list_all())}")
""",
        ("markdown", r"""### II. Thực thi Phân tích Quan hệ Hai biến Bắt buộc (Execution of RQ1 Association Pipeline)

Chúng ta thực thi hàm `run_rq1_analysis` trên toàn bộ **scope phân tích đã chọn**. Mặc định development chỉ gồm train và validation từ split đã khóa; final test không được dùng để chọn hoặc diễn giải quan hệ:
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
    analysis_scope=analysis_scope,
)

print("--- TỔNG KẾT KẾT QUẢ LIÊN KẾT HAI BIẾN RQ1 ---")
print(f"Tổng số bản ghi liên kết đã tính toán: {len(rq1_table)}")
print(f"- Số bản ghi biến dự đoán sơ cấp hợp lệ (Primary Valid): {int((rq1_table['is_primary_valid'] == True).sum())}")
print(f"- Số bản ghi phục vụ chẩn đoán coupling / D01: {int((rq1_table['is_primary_valid'] == False).sum())}")
print(f"- Các chế độ chơi được phân tích: {list(rq1_table['mode'].unique())}")
""",
        ("markdown", r"""### III. Phân tích Tương quan với Thời gian Sinh tồn (Survival Target S1)

Khảo sát mối quan hệ giữa các hành vi và thời gian sinh tồn $player\_survive\_time$:
- Bảng bên dưới xếp theo $|r|$ nhưng vẫn giữ dấu để đọc đúng chiều liên hệ; không định sẵn feature mạnh nhất trước khi chạy.
- *Cảnh báo Thiên lệch Cơ hội Thời gian (Opportunity Time Bias):* Người sống lâu có thêm thời gian tích lũy di chuyển, sát thương và kill, nên association không chứng minh tác động nhân quả.
- *Kiểm chứng Quy tắc D01:* Các đặc trưng pha giao tranh hoặc chia trực tiếp cho survival chỉ được trình bày như diagnostic với `is_primary_valid = False`."""),
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

Phân tích đa chế độ kiểm tra tính nhất quán của chiều và độ lớn association, không định sẵn mode nào mạnh hơn:
1. Các biến hỗ trợ có thể là hằng số trong Solo; khi đó hệ số phải là `NaN` với status `constant_variable`, không được thay bằng 0.
2. Chỉ diễn giải khác biệt giữa Solo, Duo và Squad khi mỗi mode đủ $N$ và bảng thực sinh cho thấy chênh lệch; đây vẫn là association hồi cứu, không phải cơ chế nhân quả."""),
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
3. **Biểu đồ phân tán mật độ Hexbin / Scatter (`rq1_scatter_density.png`):** Thể hiện mối quan hệ giữa quãng đường đi bộ và sát thương đối với kết quả trận đấu.

Mỗi hình công bố scope và $N$ tương ứng. Notebook không vẽ khoảng tin cậy vì chưa thực hiện bootstrap theo cụm match/player; do đó không được đọc các thanh như ước lượng có uncertainty đã hiệu chỉnh."""),
        """
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
pair_n_min = int(plot_df["n_observations"].min()) if len(plot_df) else 0
pair_n_max = int(plot_df["n_observations"].max()) if len(plot_df) else 0
ax.set_title(
    f"Pearson và Spearman với placement (Top 10)\\nscope={analysis_scope}, pair N={pair_n_min:,}-{pair_n_max:,}",
    fontsize=12, pad=12,
)
ax.axvline(0, color="black", linestyle="--", linewidth=0.8)
ax.grid(axis="x", linestyle="--", alpha=0.5)
ax.legend(loc="lower right")

plt.tight_layout()
fig_bar_path = fig_dir / "rq1_correlations_bar.png"
plt.savefig(fig_bar_path, dpi=150, bbox_inches="tight")
plt.show()
plt.close()
print(f"Đã lưu biểu đồ thanh tương quan -> {fig_bar_path.relative_to(PROJECT_ROOT)}")

# - Biểu đồ 2: So sánh hệ số Pearson giữa các chế độ chơi
fig, ax = plt.subplots(figsize=(11, 5))
pivot_r.plot(kind="bar", ax=ax, colormap="viridis", width=0.7, edgecolor="black")
mode_n = pivot_subset.groupby("mode")["n_observations"].agg(["min", "max"])
mode_n_text = ", ".join(f"{mode}={int(row['min']):,}-{int(row['max']):,}" for mode, row in mode_n.iterrows())
ax.set_title(f"Pearson r theo chế độ\\nscope={analysis_scope}; pair N theo mode: {mode_n_text}", fontsize=12, pad=12)
ax.set_ylabel("Hệ số Tương quan Pearson")
ax.set_xlabel("Đặc trưng")
ax.axhline(0, color="black", linestyle="--", linewidth=0.8)
ax.grid(axis="y", linestyle="--", alpha=0.5)
plt.xticks(rotation=30, ha="right")
plt.legend(title="Chế độ", loc="upper right")

plt.tight_layout()
fig_mode_path = fig_dir / "rq1_mode_comparison_correlations.png"
plt.savefig(fig_mode_path, dpi=150, bbox_inches="tight")
plt.show()
plt.close()
print(f"Đã lưu biểu đồ so sánh chế độ -> {fig_mode_path.relative_to(PROJECT_ROOT)}")

# - Biểu đồ 3: Mật độ hai biến trên reservoir sample chỉ phục vụ trực quan
viz_n = int(cfg["eda"]["sampling"]["viz_sample_size"])
viz_seed = int(cfg["eda"]["sampling"]["random_state"])
scatter_sample = con.execute(f\"\"\"
    SELECT * FROM (
        SELECT player_dist_walk, player_dmg, normalized_placement
        FROM read_parquet(?)
        WHERE normalized_placement IS NOT NULL
    ) AS eligible_rq1_density
    USING SAMPLE reservoir({viz_n} ROWS) REPEATABLE ({viz_seed})
\"\"\", [str(final_pq)]).df()

fig, axes = plt.subplots(1, 2, figsize=(12, 5))
for ax, feature, label in zip(axes, ["player_dist_walk", "player_dmg"], ["Quãng đường đi bộ", "Sát thương"]):
    valid = scatter_sample[[feature, "normalized_placement"]].dropna()
    hb = ax.hexbin(valid[feature], valid["normalized_placement"], gridsize=30, mincnt=1, cmap="viridis")
    ax.set(xlabel=label, ylabel="Normalized placement", title=f"{label} và placement")
    fig.colorbar(hb, ax=ax, label="Số quan sát trong ô")
fig.suptitle(f"RQ1 density sample: scope={analysis_scope}, N={len(scatter_sample):,}, reservoir seed={viz_seed}")
plt.tight_layout()
fig_density_path = fig_dir / "rq1_scatter_density.png"
_pubg_figure_details = {fig_density_path.name: {"source_table": str(final_pq), "scope": analysis_scope,
    "sample_n": len(scatter_sample), "sample_seed": viz_seed, "sampling_rule": "DuckDB reservoir among valid placement; visualization only",
    "caption": "RQ1 density: count trong ô; hệ số/N primary tính riêng trên toàn scope hợp lệ, không suy nhân quả."}}
plt.savefig(fig_density_path, dpi=150, bbox_inches="tight")
plt.show()
plt.close()
print(f"Đã lưu biểu đồ mật độ mẫu -> {fig_density_path.relative_to(PROJECT_ROOT)}")
""",
        ("markdown", r"""### VII. Diễn giải Khoa học, Khuyến nghị và Giới hạn Phương pháp (Interpretations & Limitations)

Theo chuẩn mực nghiên cứu trong `PUBG_IMPLEMENTATION_PLAN.md`, chúng ta xuất bản tệp `reports/manifests/rq1_interpretations.json` và tổng kết các giới hạn phương pháp luận bắt buộc:
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

mode_variations = pd.DataFrame(interp_data.get("mode_variations", []))
print("\\n--- CHÊNH LỆCH ĐỘ LỚN PEARSON GIỮA CÁC MODE, CHỈ ĐỂ DIỄN GIẢI ASSOCIATION ---")
print(mode_variations.sort_values("absolute_magnitude_gap", ascending=False).head(10).to_string(index=False) if not mode_variations.empty else "Không đủ ít nhất hai mode hợp lệ để so sánh.")
""",
        ("markdown", r"""### VIII. Nghiệm thu Stage NB06 và Bàn giao sang Notebook 07 (RQ2 Clustering)

Cổng bàn giao **Stage NB06 (RQ1 Bivariate Analysis)** được nghiệm thu khi đáp ứng; đây không phải một gate mới ngoài G0-G5:
1. Tệp kết quả chuẩn tắc `rq1_relationship_summary.csv` chứa số bản ghi phát sinh từ feature/mode đủ điều kiện, không dùng con số hard-code.
2. Tệp diễn giải cấu trúc và giới hạn `rq1_interpretations.json` được tạo thành công.
3. Ba hình trực quan hóa được lưu và hiển thị inline; hình mật độ công bố rõ scope, N và seed lấy mẫu.
4. Đăng ký và khóa checkpoint manifest với định danh `rq1`.
5. Bàn giao kết quả sang Notebook `07_rq2_clustering.ipynb` để tiến hành phân cụm hồ sơ hành vi người chơi."""),
        """
# - Bước 8: Kiểm tra artifacts và khóa checkpoint
required_rq1_artifacts = [
    paths["tables"] / "rq1_relationship_summary.csv",
    paths["manifests"] / "rq1_interpretations.json",
    paths["figures"] / "rq1_correlations_bar.png",
    paths["figures"] / "rq1_mode_comparison_correlations.png",
    paths["figures"] / "rq1_scatter_density.png",
]

for art in required_rq1_artifacts:
    assert art.is_file(), f"Thiếu artifact bắt buộc: {art.name}"

# Khóa checkpoint manifest
from uuid import uuid4
rq1_run_id = "rq1_" + uuid4().hex
ckpt_mgr.commit("rq1", _pubg_signature, {
    "summary_table": paths["tables"] / "rq1_relationship_summary.csv",
    "interpretations": paths["manifests"] / "rq1_interpretations.json",
    "correlations_bar": paths["figures"] / "rq1_correlations_bar.png",
    "mode_comparison_correlations": paths["figures"] / "rq1_mode_comparison_correlations.png",
    "scatter_density": paths["figures"] / "rq1_scatter_density.png",
}, metadata={"records_count": len(rq1_table), "analysis_scope": analysis_scope, "run_id": rq1_run_id})

handoff_table = [
    {"Artifact": "rq1_relationship_summary.csv", "Đường dẫn": str((paths["tables"] / "rq1_relationship_summary.csv").relative_to(PROJECT_ROOT)), "Mô tả": f"Bảng {len(rq1_table)} bản ghi Pearson/Spearman; scope={analysis_scope}"},
    {"Artifact": "rq1_interpretations.json", "Đường dẫn": str((paths["manifests"] / "rq1_interpretations.json").relative_to(PROJECT_ROOT)), "Mô tả": "Báo cáo diễn giải khoa học và giới hạn nghiên cứu"},
    {"Artifact": "rq1_correlations_bar.png", "Đường dẫn": str((paths["figures"] / "rq1_correlations_bar.png").relative_to(PROJECT_ROOT)), "Mô tả": "Biểu đồ so sánh hệ số Pearson và Spearman"},
    {"Artifact": "rq1_mode_comparison_correlations.png", "Đường dẫn": str((paths["figures"] / "rq1_mode_comparison_correlations.png").relative_to(PROJECT_ROOT)), "Mô tả": "Biểu đồ so sánh hệ số giữa các chế độ chơi"},
    {"Artifact": "rq1_scatter_density.png", "Đường dẫn": str((paths["figures"] / "rq1_scatter_density.png").relative_to(PROJECT_ROOT)), "Mô tả": "Mật độ mẫu có công bố N, seed và scope"},
]

print("\\n================================================================================")
print(f"STAGE NB06 HOÀN TẤT TRONG SCOPE {analysis_scope.upper()}; KHÔNG PHẢI GATE MỚI")
print("BÀN GIAO SANG NOTEBOOK 07: '07_rq2_clustering.ipynb'")
print("================================================================================")
print(pd.DataFrame(handoff_table).to_string(index=False))
"""
    ]
)

# 07_rq2_clustering.ipynb
create_notebook(
    "07_rq2_clustering.ipynb",
    "07 - RQ2: Hồ sơ hành vi người chơi và phân cụm C1-C5",
    "Khóa threshold/K trên development, fit mô tả full eligible và công bố đầy đủ diagnostics, sensitivity, outcome cùng giới hạn.",
    [
        ("markdown", r"""## I. Bối cảnh khoa học, câu hỏi và phạm vi

Notebook trả lời RQ2: các hồ sơ hành vi nào xuất hiện trong dữ liệu PUBG. Đơn vị phân tích là hồ sơ người chơi theo `mode_strategy`; với `per_mode`, ID cụm chỉ có nghĩa trong từng mode.

Development gồm train/validation và chỉ dùng để chọn representation, minimum games, transform và K. Full descriptive chỉ được fit sau khi quyết định đã khóa. Đây là phân tích mô tả hồi cứu, không phải suy rộng heldout hay quan hệ nhân quả. Survival/placement không được dùng làm input, chọn threshold/K hoặc đặt tên cụm; chúng chỉ xuất hiện ở C5 sau khi assignments đã khóa."""),
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.data.io import read_parquet_df, read_json, atomic_write_csv
from src.features.profiles import profile_keys
from src.analysis.clustering import CORE_PROFILE_FEATURES
from src.analysis.rq2_workflow import load_profiles, retention_table, diagnostics, final_clustering
from src.models.compute import compute_info

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
paths["figures"].mkdir(parents=True, exist_ok=True)
rq2_visual_artifacts = {}

config_table = pd.DataFrame([
    {"Thành phần": "Scope chọn quyết định", "Giá trị": "development: train + validation"},
    {"Thành phần": "Mode strategy", "Giá trị": cfg["rq2"]["mode_strategy"]},
    {"Thành phần": "Scaler chính", "Giá trị": cfg["rq2"]["scaler"]},
    {"Thành phần": "Thuật toán", "Giá trị": cfg["rq2"]["algorithm"]},
    {"Thành phần": "Thiết bị/backend", "Giá trị": str(compute_info(cfg["rq2"]["device"]))},
])
print("BẢNG 07-A. CẤU HÌNH VÀ PHẠM VI")
print(config_table.to_string(index=False))
""",
        ("markdown", r"""## II. Design 3, missing semantics, coverage và retention

Design 3 có 14 biến hành vi. `games_played` chỉ dùng cho reliability filter và C3. Standard deviation dùng $ddof=1$; singleton là `insufficient_n`, không phải biến thiên bằng 0. Trung bình phase chỉ dùng kill-active matches có timing hợp lệ; thiếu event không tự động biến thành no-kill. Imputation chỉ xảy ra trong fitted pipeline.

Với threshold $t$, hồ sơ được giữ khi $games\_played \ge t$. Threshold phải dựa trên retention, feature reliability/stability và compute, không dựa trên outcome.

- Mục đích: kiểm toán cohort, missing semantics và độ tin cậy profile.
- Đầu vào: development profiles và coverage artifact.
- Đầu ra: dictionary, valid counts, retention table và Hình 07-01.
- Cách đọc: so sánh trong từng mode; tỷ lệ giữ lại thấp là cảnh báo reliability/compute, không phải bằng chứng outcome."""),
"""
cfg = load_config(str(PROJECT_ROOT / "configs"))
profiles, outcomes = load_profiles(cfg, paths)
feature_groups = {"Combat": CORE_PROFILE_FEATURES[:4], "Movement": CORE_PROFILE_FEATURES[4:7],
                  "Support": CORE_PROFILE_FEATURES[7:10], "Combat timing": CORE_PROFILE_FEATURES[10:]}
dictionary = pd.DataFrame([{"Nhóm": group, "Feature": feature,
                            "Mẫu số": ("kill-active có timing hợp lệ" if "kill_ratio" in feature else
                                      "matches xác định early status" if feature == "early_combat_match_ratio" else
                                      "valid matches của feature"),
                            "Vai trò": "C1 behavioral input"}
                           for group, features in feature_groups.items() for feature in features])
retention = retention_table(profiles, cfg, paths)
coverage = pd.read_csv(paths["tables"] / "rq2_profile_coverage.csv")
print("BẢNG 07-B. TỪ ĐIỂN DESIGN 3"); print(dictionary.to_string(index=False))
print("\\nBẢNG 07-C. VÍ DỤ MISSING/NO-KILL/SINGLETON")
semantics = pd.DataFrame([
    {"Tình huống": "missing", "Giá trị kỳ vọng": "NaN trước pipeline", "Không được hiểu là": "0"},
    {"Tình huống": "no-kill đã xác nhận", "Giá trị kỳ vọng": "kill_active_matches=0", "Không được hiểu là": "event missing"},
    {"Tình huống": "event missing", "Giá trị kỳ vọng": "timing không xác định", "Không được hiểu là": "no-kill"},
    {"Tình huống": "singleton", "Giá trị kỳ vọng": "std=NaN; status=insufficient_n", "Không được hiểu là": "zero variance"},
])
print(semantics.to_string(index=False))
audit_cols = [c for c in ["games_played", "kill_active_matches", "support_active_matches",
                           "timing_observed_matches", "std_kills", "std_kills_status"] if c in profiles]
print(profiles[audit_cols].head(8).to_string(index=False))
print("\\nBẢNG 07-D. RETENTION"); print(retention.to_string(index=False))
print("\\nBẢNG 07-E. COVERAGE VÀ VALID COUNTS"); print(coverage.to_string(index=False))

fig, ax = plt.subplots(figsize=(8, 5))
for mode, group in retention.groupby("mode"):
    ax.plot(group["min_games"], group["retained_fraction"], marker="o", label=mode)
ax.set(title=f"Hình 07-01. Retention trên development; N={len(profiles)} hồ sơ", xlabel="Số trận tối thiểu", ylabel="Tỷ lệ hồ sơ được giữ")
ax.set_ylim(0, 1.05); ax.grid(alpha=.3); ax.legend(title="Mode")
retention_figure = paths["figures"] / "rq2_retention_curve.png"
fig.tight_layout(); fig.savefig(retention_figure, dpi=150); plt.show(); plt.close(fig)
rq2_visual_artifacts["figure/retention"] = retention_figure
print("Cách đọc: đường giảm nhanh cho thấy threshold loại nhiều hồ sơ. Outcome không tham gia quyết định này.")
""",
        ("markdown", r"""## III. Chẩn đoán K và decision receipt

K được đánh giá bằng inertia, Silhouette, Davies-Bouldin, cluster shares và ARI qua seed. Mẫu diagnostic, nếu có, phải công bố N, population, seed, rule và digest; KMeans chính vẫn fit toàn bộ eligible profiles. Không chọn K chỉ từ một metric và không dùng survival/placement.

- Mục đích: khóa K từ development mà không rò rỉ outcome.
- Đầu vào: profiles sau threshold và resource audit.
- Đầu ra: bảng K diagnostics, decision receipt và Hình 07-02.
- Cách đọc: đối chiếu đồng thời separation, compactness, size và stability; giá trị pending không được tự suy diễn thành quyết định."""),
"""
cfg = load_config(str(PROJECT_ROOT / "configs"))
profiles, outcomes = load_profiles(cfg, paths)
k_diag = diagnostics(profiles, cfg, paths)
print("BẢNG 07-F. K DIAGNOSTICS"); print(k_diag.to_string(index=False))
print("\\nBẢNG 07-G. QUYẾT ĐỊNH ĐÃ KHÓA")
print(pd.DataFrame([{"minimum_games": cfg["rq2"].get("minimum_games_threshold"),
                     "K theo mode": str(cfg["rq2"].get("n_clusters_by_mode")),
                     "lý do": cfg["rq2"].get("selection_reason"), "outcome_used": False}]).to_string(index=False))

metrics = [("inertia", "Inertia"), ("silhouette_score", "Silhouette"),
           ("davies_bouldin_score", "Davies-Bouldin"), ("seed_stability_ari", "ARI qua seed")]
fig, axes = plt.subplots(2, 2, figsize=(11, 8))
for ax, (column, label) in zip(axes.flat, metrics):
    for mode, group in k_diag.groupby("mode"):
        ax.plot(group["k"], group[column], marker="o", label=mode)
    ax.set(xlabel="K", ylabel=label, title=label); ax.grid(alpha=.3)
axes[0, 0].legend(title="Mode")
fig.suptitle("Hình 07-02. Chẩn đoán K trên development, không dùng outcome")
fig.text(.01, .01, "N/seed/quy tắc theo từng mode và K: xem k_diagnostics.csv; không suy nhân quả.", fontsize=9)
k_figure = paths["figures"] / "rq2_k_diagnostics.png"
fig.tight_layout(rect=(0,.05,1,1)); fig.savefig(k_figure, dpi=150); plt.show(); plt.close(fig)
rq2_visual_artifacts["figure/k_diagnostics"] = k_figure
print("Cách đọc: cân bằng compactness, separation, size và stability; không tối ưu theo C5.")
""",
        ("markdown", r"""## IV. C1-C5, tài nguyên và khả năng tái lập

C1 dùng KMeans + StandardScaler trên full eligible sau khóa. C2 hierarchical là supporting validation. C3 chỉ thêm `games_played`. C4 tính ARI trên common profile keys và công bố coverage. C5 mô tả outcome sau khóa assignments. Mọi flag có status/reason; nhánh sensitivity chỉ chạy khi có evidence cấu hình.

Workflow ghi RAM/VRAM và ước lượng ma trận trước fit, xử lý mode tuần tự và chặn C2 khi pairwise estimate quá lớn mà chưa có cap có căn cứ.

- Mục đích: fit C1 và chạy các nhánh C2-C5 đúng flag.
- Đầu vào: quyết định đã khóa và full eligible profiles.
- Đầu ra: assignments, centers, fitted pipeline, robustness, C4/C5 và resource receipt.
- Cách đọc: `status/reason` phân biệt completed, skipped và unsupported; supporting sensitivity không thay thế C1."""),
"""
cfg = load_config(str(PROJECT_ROOT / "configs"))
profiles, outcomes = load_profiles(cfg, paths)
rq2_artifacts = final_clustering(profiles, outcomes, cfg, paths)
resource = read_json(paths["manifests"] / "rq2_resource_audit.json")
decisions = read_json(paths["manifests"] / "rq2_decisions.json")
print("BẢNG 07-H. RESOURCE AUDIT"); print(pd.DataFrame(resource["full_descriptive_fit"]["modes"]).to_string(index=False))
print("\\nBẢNG 07-I. DECISION RECEIPT")
print(pd.DataFrame([{"selection_scope": decisions["selection_scope"], "fit_scope": decisions["fit_scope"],
                     "claim_scope": decisions["claim_scope"], "backend": decisions["compute"]["backend"]}]).to_string(index=False))
""",
        ("markdown", r"""## V. Kết quả từng mode, centers, sensitivity và C5

Tên cụm chỉ dựa trên tâm hành vi, không dựa vào thắng/thua, survival hay placement. Heatmap đọc theo z-score trong từng mode. Cluster ID không được so trực tiếp giữa các mode. Outcome plot là mô tả hậu nghiệm sau khi assignments đã khóa.

- Mục đích: chuyển artifacts thành bảng/hình có thể kiểm toán.
- Đầu vào: artifacts C1-C5 của từng mode.
- Đầu ra: raw/standardized centers, sizes, sensitivity và outcome distributions.
- Cách đọc: chỉ so sánh cluster trong cùng mode; C5 chỉ mô tả sau khóa."""),
"""
figure_rows = [
    {"figure_id": "07-01", "mode": "All", "path": str(retention_figure),
     "source": "rq2_retention.csv", "caption": "Retention theo minimum games; outcome không tham gia chọn threshold.",
     "scope": "development", "how_to_read": "So sánh tỷ lệ giữ lại theo threshold trong từng mode.",
     "n_profiles": len(profiles), "runtime_mode": cfg["runtime"]["mode"],
     "sampling_rule": "all development profiles; threshold grid", "sample_seed": None,
     "limitation": "Fixture chỉ kiểm tra logic, không phải phát hiện khoa học."},
    {"figure_id": "07-02", "mode": "All", "path": str(k_figure),
     "source": "k_diagnostics.csv", "caption": "K diagnostics trên development; không dùng outcome.",
     "scope": "development", "how_to_read": "Cân bằng compactness, separation, cluster size và stability qua seed.",
     "n_profiles": len(profiles), "runtime_mode": cfg["runtime"]["mode"],
     "sampling_rule": "per-mode/K diagnostic N and rule in k_diagnostics.csv", "sample_seed": cfg["rq2"]["random_state"],
     "sampling_details": k_diag.to_json(orient="records", force_ascii=False),
     "limitation": "Fixture chỉ kiểm tra logic, không phải phát hiện khoa học."},
]
full_outcomes = read_parquet_df(paths["processed"] / "player_profile_outcomes.parquet")
mode_names = sorted(profiles["team_size_mode"].dropna().unique()) if cfg["rq2"]["mode_strategy"] == "per_mode" else ["Overall"]
for mode in mode_names:
    target = paths["tables"] / "rq2" / mode if cfg["rq2"]["mode_strategy"] == "per_mode" else paths["tables"]
    fig_dir = paths["figures"] / "rq2" / mode; fig_dir.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(target / "cluster_profile.csv")
    standardized = pd.read_csv(target / "cluster_centers_standardized.csv")
    assignments = pd.read_csv(target / "cluster_assignments.csv")
    robustness = pd.read_csv(target / "clustering_robustness.csv")
    c4 = pd.read_csv(target / "c4_min_games_sensitivity.csv")
    c5 = pd.read_csv(target / "c5_outcome_comparison.csv")
    print(f"\\nBẢNG 07-J [{mode}]. RAW CENTERS/SIZES"); print(raw.to_string(index=False))
    print(f"\\nBẢNG 07-K [{mode}]. STATUS C1-C5"); print(robustness.to_string(index=False))
    print(f"\\nBẢNG 07-L [{mode}]. C4 COMMON KEYS/COVERAGE"); print(c4.to_string(index=False))
    print(f"\\nBẢNG 07-M [{mode}]. C5 OUTCOME/VALID N"); print(c5.to_string(index=False))

    columns = [c for c in CORE_PROFILE_FEATURES if c in standardized]
    matrix = standardized[columns].to_numpy(float)
    bound = max(1.0, float(np.nanmax(np.abs(matrix))))
    fig, ax = plt.subplots(figsize=(12, max(3, len(standardized) * .8)))
    image = ax.imshow(matrix, aspect="auto", cmap="coolwarm", vmin=-bound, vmax=bound)
    ax.set(xticks=range(len(columns)), xticklabels=columns, yticks=range(len(standardized)),
           yticklabels=standardized.get("behavioral_name", standardized.index),
           title=f"Hình 07-03. Tâm chuẩn hóa - {mode}; N={len(assignments)} hồ sơ")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right"); fig.colorbar(image, ax=ax, label="z-score")
    heatmap = fig_dir / "cluster_centers_heatmap.png"; fig.tight_layout(); fig.savefig(heatmap, dpi=150); plt.show(); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4)); ax.bar(raw["behavioral_name"], raw["profile_count"], color="#2b6f9c")
    ax.set(title=f"Hình 07-04. Kích thước cụm - {mode}; N={len(assignments)} hồ sơ", ylabel="Số hồ sơ"); plt.setp(ax.get_xticklabels(), rotation=25, ha="right")
    sizes = fig_dir / "cluster_sizes.png"; fig.tight_layout(); fig.savefig(sizes, dpi=150); plt.show(); plt.close(fig)

    ari = robustness[(robustness["metric"] == "Adjusted_Rand_Index") & robustness["value"].notna()]
    fig, ax = plt.subplots(figsize=(8, 4)); ax.bar(ari["comparison"], ari["value"], color="#5a8f5a")
    ax.set(title=f"Hình 07-05. Robustness/sensitivity - {mode}", ylabel="ARI", ylim=(-.05, 1.05)); plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    fig.text(.01, .01, f"N full eligible={len(assignments)}; N chung/mẫu, seed và quy tắc từng nhánh: clustering_robustness.csv và c4_min_games_sensitivity.csv.", fontsize=8)
    robust_fig = fig_dir / "robustness_sensitivity.png"; fig.tight_layout(rect=(0,.06,1,1)); fig.savefig(robust_fig, dpi=150); plt.show(); plt.close(fig)

    merged = assignments.merge(full_outcomes, on=profile_keys(assignments), how="left", validate="one_to_one")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, column, label in zip(axes, ["mean_survive_time", "mean_normalized_placement"], ["Survival (đơn vị nguồn chưa xác minh)", "Placement score [0,1]"]):
        labels = sorted(merged["cluster_label"].unique())
        ax.boxplot([merged.loc[merged["cluster_label"] == cluster, column].dropna() for cluster in labels],
                   tick_labels=[str(v) for v in labels])
        ax.set(xlabel="Cluster ID", ylabel=label, title=f"N hợp lệ={merged[column].notna().sum()}")
    fig.suptitle(f"Hình 07-06. Outcome sau khóa assignments - {mode}; N={len(assignments)} hồ sơ")
    outcome_fig = fig_dir / "outcome_distributions.png"; fig.tight_layout(); fig.savefig(outcome_fig, dpi=150); plt.show(); plt.close(fig)

    for figure_id, path, source, caption in [
        ("07-03", heatmap, "cluster_centers_standardized.csv", "Tâm hành vi chuẩn hóa; không chứa outcome."),
        ("07-04", sizes, "cluster_profile.csv", "Số hồ sơ full eligible từng cụm."),
        ("07-05", robust_fig, "clustering_robustness.csv", "ARI cho supporting/sensitivity có status và reason."),
        ("07-06", outcome_fig, "cluster_assignments.csv + player_profile_outcomes.parquet", "Outcome hậu nghiệm; không dùng chọn hoặc đặt tên cụm."),
    ]:
        rq2_visual_artifacts[f"figure/{mode}/{figure_id}"] = path
        figure_rows.append({"figure_id": figure_id, "mode": mode, "path": str(path), "source": source,
                            "caption": caption, "scope": decisions["claim_scope"],
                            "n_profiles": len(assignments), "runtime_mode": cfg["runtime"]["mode"],
                            "sample_seed": cfg["rq2"]["random_state"] if figure_id == "07-05" else None,
                            "sampling_rule": "branch-specific N/seed/rule in clustering_robustness.csv; C4 common keys in c4_min_games_sensitivity.csv" if figure_id == "07-05" else "all full eligible profiles; valid outcomes only for C5",
                            "sampling_details": robustness.to_json(orient="records", force_ascii=False) if figure_id == "07-05" else "not sampled",
                            "how_to_read": "Đọc trong mode; không đồng nhất cluster ID giữa modes.",
                            "limitation": "Fixture chỉ kiểm tra logic, không phải phát hiện khoa học."})
""",
        ("markdown", r"""## VI. Diễn giải, giới hạn và bàn giao

Có thể mô tả khác biệt hành vi giữa các cụm trong cùng mode và độ nhạy theo representation/threshold. Không thể kết luận cụm nào tốt hơn, không suy nhân quả và không gọi fixture là kết quả nghiên cứu.

Notebook 08 chỉ được mở sau khi profiles, diagnostics, decision receipt, assignments, centers, fitted pipelines, C1-C5 status và figure catalog đã được checkpoint. GPU thật được nghiệm thu riêng ở RUN-06; fixture CPU chỉ chứng minh logic và routing.

- Mục đích: công bố claim scope, giới hạn và điều kiện bàn giao.
- Đầu vào: toàn bộ bảng/hình đã sinh trong notebook.
- Đầu ra: figure catalog và checkpoint bàn giao sang Notebook 08.
- Cách đọc: mục `limitation` đi cùng từng hình; không nâng fixture thành kết quả full-data."""),
"""
figure_catalog = pd.DataFrame(figure_rows)
catalog_path = paths["tables"] / "rq2_figure_catalog.csv"
atomic_write_csv(catalog_path, figure_catalog)
rq2_artifacts.update(rq2_visual_artifacts)
rq2_artifacts["figure_catalog"] = catalog_path
print("BẢNG 07-N. CATALOG HÌNH/CAPTION"); print(figure_catalog.to_string(index=False))
print("\\nBẢNG 07-O. BÀN GIAO")
print(pd.DataFrame([
    {"Artifact": "Development profiles + diagnostics", "Status": "completed", "Consumer": "decision audit"},
    {"Artifact": "Full assignments/centers", "Status": "completed", "Consumer": "RQ2 interpretation"},
    {"Artifact": "C1-C5 status + sensitivity", "Status": "completed_or_explicitly_skipped", "Consumer": "robustness audit"},
    {"Artifact": "Fitted pipelines + figures", "Status": "completed", "Consumer": "Notebook 11-12"},
]).to_string(index=False))
print("Điểm tiếp tục: Notebook 08. Không tuyên bố full-data hoặc GPU thật từ fixture này.")
""",
    ]
)

# 08_build_historical.ipynb
create_notebook(
    "08_build_historical.ipynb",
    "08 — Xây dựng đặc trưng Lịch sử người chơi (Historical Features)",
    "Xác minh thứ tự thời gian, tích lũy đặc trưng quá khứ (expanding window), đảm bảo không rò rỉ trận hiện tại hoặc tương lai.",
    [
        ("markdown", r"""### 0. Câu hỏi khoa học, phạm vi và tiêu chí

Notebook này chuẩn bị dữ liệu cho S2 (survival) và P3 (placement) của RQ3:
trước trận hiện tại, người chơi có bao nhiêu lịch sử đã hoàn thành và có thể sử dụng?
Không huấn luyện mô hình ở đây, không biến dữ liệu sau trận hiện tại thành dự đoán trước trận.

**Input:** player_match_features, match_metadata, chronology_report và split đã khóa.
**Output:** bảng feasibility/development, receipt quyết định G3, dataset lịch sử hoặc blocked status,
leakage audit, coverage và hình diagnostic. Storage dùng `paths`, không tạo hậu tố số.
`player_name` không phải ID tài khoản bất biến; người thiếu tên bị loại riêng khỏi history.
Không dùng profile RQ2 toàn thời gian. Cold start là chưa có quá khứ, khác mean bằng 0.

**Tiêu chí:** nguồn chronology khớp metadata và toàn bộ match/date input; availability có evidence;
ngưỡng chưa chốt vẫn null; source availability phải nhỏ hơn cutoff; mean/count có mẫu số riêng.
Fixture chỉ chứng minh logic, không phải kết quả full-data hoặc xác minh Drive/GPU.

### 1. Cấu hình, nguồn chronology và availability

Grade A: loại toàn khối timestamp đồng thời, chỉ dùng thống kê đã sẵn sàng trước prediction time.
Grade B: gom tổng/count theo ngày availability UTC và loại toàn ngày hiện tại.
Grade C: không xây dataset prediction; S2/P3 blocked, current-match tasks không bị đổi protocol.
Timestamp có giây hoặc tỷ lệ tie thấp không đủ cấp Grade A.

Availability cần bằng chứng độc lập: cột prediction/available timestamp được tài liệu nguồn xác nhận,
hoặc match-start cộng duration của trận đã xác minh đơn vị giây. Không dùng thời gian sống của từng
người chơi làm thời điểm hoàn thành trận. Nếu duration là proxy, cần evidence chứng minh policy an toàn;
không tự suy từ tên cột. Config mặc định vẫn pending, không giả đã xác minh.
Metadata checksum được NB02 ghi; không khớp thì chạy lại NB02, không sửa grade bằng tay."""),
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.data.io import get_duckdb_connection, read_json
from src.features.history_workflow import diagnostics, publish, create_figures, illustrative_history, FEATURES
import pandas as pd
from IPython.display import display, Markdown, Image

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
con = get_duckdb_connection(temp_dir=paths["temp_dir"], **{k: cfg["runtime"]["duckdb"][k] for k in ("memory_limit", "threads")})

print("BẢNG 08-A: CẤU HÌNH THỰC DÙNG")
display(pd.DataFrame([{"Trường": key, "Giá trị": str(value)} for key,value in cfg["rq3"].items()]))
print("BẢNG 08-B: Ý NGHĨA GRADE VÀ TRẠNG THÁI S2/P3")
display(pd.DataFrame([
    {"Grade":"A", "Quá khứ":"Availability strictly earlier, loại tie block", "S2/P3":"Chỉ khi availability và G3 đã đạt"},
    {"Grade":"B", "Quá khứ":"Availability ngày UTC trước, không cùng ngày", "S2/P3":"Chỉ khi availability và G3 đã đạt"},
    {"Grade":"C", "Quá khứ":"Không chứng nhận", "S2/P3":"blocked_by_chronology"},
]))
chrono_report = read_json(paths["manifests"] / "chronology_report.json")
print("BẢNG 08-C: CHRONOLOGY REPORT NGUỒN (SẼ ĐƯỢC ĐỐI SOÁT)")
display(pd.DataFrame([{"Bằng chứng":key,"Giá trị":str(value)} for key,value in chrono_report.items()]))
""",
        ("markdown", r"""### 2. Công thức và ví dụ tính tay, tách khỏi dữ liệu nghiên cứu

Với tập trận quá khứ đã sẵn sàng \(H_i\), mỗi feature có mean riêng:
\[
\bar{x}_{i}=\frac{\sum_{j\in H_i,\ x_j\ valid}x_j}{N_{i,x}},\quad
N_{i,x}=\sum_{j\in H_i}\mathbf{1}(x_j\ valid).
\]
Nếu \(N_{i,x}=0\), mean missing, không fill 0. `hist_games_played` đếm trận, không thay valid count.
Expanding là tích lũy toàn quá khứ hợp lệ, không chỉ last 5/10. Rolling/same-mode/timing history
không bật trong core. `hist_kd` candidate, chưa xác minh số deaths nên không làm input.

**Bảng 08-D minh họa synthetic, duration=0:** hai trận đầu cùng timestamp có kills 2 và 4;
Grade A cả hai có count=0, trận thứ ba thấy count=2, mean=3; Grade B cả ba trận cùng ngày có
count=0, ngày sau thấy count=3, mean=14/3. Đây là expected tính tay để kiểm chứng code,
không phải thống kê từ dữ liệu PUBG. Trận thực chỉ được cập nhật sau availability đã xác minh."""),
"""
print("BẢNG 08-D: VÍ DỤ TÍNH TAY SYNTHETIC, KHÔNG PHẢI KẾT QUẢ NGHIÊN CỨU")
display(illustrative_history(con, paths["temp_dir"]))
print("BẢNG 08-E: DICTIONARY CORE HISTORICAL")
display(pd.DataFrame([{"Feature":mean,"Nguồn quá khứ":raw,"Đơn vị":unit,
    "Mẫu số":f"hist_{key}_count","Missing":"valid count=0: missing, không phải 0"}
    for key,(raw,mean,unit) in FEATURES.items()]))
""",
        ("markdown", r"""### 3. Chẩn đoán trước quyết định: coverage, stability và tài nguyên

Scope dùng chốt ngưỡng chỉ là train+validation. Final test không tham gia chọn ngưỡng,
kể cả dùng survival/placement để lựa chọn. Các ngưỡng 1/3/5/10 là ứng viên, không default đã chốt.
Retention = số eligible / tổng dòng development có identity. Độ ổn định mô tả là thay đổi mean
giữa hai cutoff liên tiếp của cùng người; không dùng current/future outcome hay mean survival/placement.
`valid_transitions=0` thì stability missing, không gán 0 hoặc coi là ổn định tốt.
Đọc từng feature theo đơn vị riêng; between-row std không phải within-player stability.

DuckDB aggregate/spill, pandas chỉ giữ summary. Dự trù spill 4x file bytes là ước lượng vận hành,
không chứng minh peak RAM/disk hay quota Drive. `measured_at_utc` cho biết thời điểm audit;
receipt tương thích có thể được dùng lại, nhưng build mới luôn kiểm tra lại disk còn trống.
Thiếu resource thì dừng, không sample full-data.
Identity exclusions và collision tables là feasibility toàn input; không dùng để tune outcome.
Nếu Grade C/availability pending thì không sinh depth/stability giả; chỉ lưu audit và lý do."""),
"""
history_receipt, history_diagnostic_artifacts = diagnostics(con, cfg, paths)
print("BẢNG 08-F: IDENTITY, COLLISION VÀ RESOURCE AUDITS")
for _name,_path in history_diagnostic_artifacts.items():
    if _path.suffix==".csv":
        print(_name)
        display(pd.read_csv(_path))
print("BẢNG 08-G: DIAGNOSTICS RECEIPT VÀ NGƯỠNG ĐANG CHỜ")
display(pd.DataFrame([{"Trường":key,"Giá trị":str(value)} for key,value in history_receipt.items()]))
print("Cách đọc: bảng history_coverage/history_stability là development, chưa chốt ngưỡng.")
""",
        ("markdown", r"""### 4. G3: khóa quyết định và protocol; 5. Build strict-past

Sau khi đọc coverage/stability, nhóm điền `minimum_history_threshold`,
`historical.threshold_decision_reason` và `historical.threshold_diagnostics_hash` từ receipt hiện hành.
Thay nguồn/split/availability/code/bảng diagnostics buộc chạy lại diagnostics, không reuse receipt cũ.
`evaluation_protocol` phải được nhóm chốt trước G4; core hỗ trợ `walk_forward_fixed_model`:
mô hình NB09 fit train và giữ cố định, history được cập nhật khi trận đã hoàn thành, kể cả
validation/test đã diễn ra. Không refit bằng test. Frozen-history nếu mở là sensitivity/run riêng,
không tự fallback hoặc trộn vào core. Production vẫn null đến khi có bằng chứng.

Pending/blocked vẫn có feasibility checkpoint, nhưng không có completed historical model checkpoint.
File dataset cũ được giữ nhưng stale; consumer bắt buộc đọc status/checksum/code/config.
Grade C ghi blocked đúng S2/P3, không ghi metric=0, không chặn S1/P1/P2 theo lý do history.
`eligible=0` là blocked/no_eligible_history, không chứng minh đủ dữ liệu train."""),
"""
from src.models.registry import create_canonical_experiment_matrix
history_registry = create_canonical_experiment_matrix()
history_status, history_artifacts = publish(con, cfg, paths, history_receipt, _pubg_checkpoint, history_registry)
print("BẢNG 08-H: TRẠNG THÁI DATASET VÀ QUYẾT ĐỊNH")
display(pd.DataFrame([{"Trường":key,"Giá trị":str(value)} for key,value in history_status.items()]))
print("BẢNG 08-I: MA TRẬN HISTORICAL VÀ CURRENT TASKS")
display(pd.DataFrame([{"Task":experiment.task,"Trạng thái":experiment.status,
    "Lý do":experiment.reason_code} for experiment in history_registry.list_all()
    if experiment.task in ("s1","s2","p1","p2","p3")]))
""",
        ("markdown", r"""### 6. Leakage audit; 7. Coverage và trực quan

Audit kiểm tra max_history_available_at < history_cutoff, cold-start của mọi mean và non-finite.
Expected violations=0; FAILED chặn publish. Đây là kiểm tra theo evidence nguồn và metadata,
không tự chứng minh semantics của timestamp. Kiểm thử fixture bổ sung đổi current/future/same-day
outcome, shuffle, ties và timezone; không gọi riêng cold-start check là bằng chứng hết leakage.

Coverage model sau G3 chia ba nhóm loại trừ nhau: cold start, under threshold, eligible;
tổng ba nhóm bằng total_rows theo split/mode/ngày. Test coverage là mô tả sau khóa, không tune ngược.
Hình 08-01/02/03 từ development, 08-04 feasibility toàn input, 08-05 model coverage sau quyết định.
Grade C/pending không có hình model giả. Mỗi hình ghi source/caption/cách đọc/limitation trong catalog.
CSV giữ đủ dòng; hình chỉ aggregate exact counts, không lấy mẫu điểm."""),
"""
print("BẢNG 08-J: LEAKAGE VÀ MODEL COVERAGE (NẾU ĐƯỢC XÂY)")
for _name in ("leakage_audit","model_coverage"):
    if _name in history_artifacts:
        display(pd.read_csv(history_artifacts[_name]))
    else:
        print(_name, "not_applicable:", history_status["reason_code"])
history_artifacts = create_figures(paths, history_receipt, history_status, history_artifacts)
_catalog = pd.read_csv(history_artifacts["figure_catalog"])
for _,_figure in _catalog.iterrows():
    display(Image(filename=_figure["path"]))
    display(Markdown(f"**Hình {_figure['figure_id']}.** {_figure['caption']}\\n\\nCách đọc: {_figure['how_to_read']}\\n\\nGiới hạn: {_figure['limitation']}"))
""",
        ("markdown", r"""### 8. Diễn giải, giới hạn và 9. Bàn giao

Không suy coverage tốt thành mô hình tốt, không gọi association là nhân quả. Tên người có thể đổi,
availability evidence có thể chưa đủ, repeated players và chronology ngày là giới hạn nghiên cứu.
Units chưa xác minh giữ source unit; không tự gọi distance là mét hay time là giây.
Hist K/D chưa có deaths verified; optional rolling/mode/timing history chưa được bật.

Đọc Bảng 08-H để biết dataset có dùng được không. Feasibility completed chỉ nghĩa audit đã chạy;
S2/P3 không có metric và vẫn blocked/pending nếu thiếu chronology/availability/quyết định.
Phần huấn luyện và kiểm tra model không refit test thuộc NB09, chưa được chứng nhận bởi NB08.
Bảng 08-K chỉ liệt kê artifact của nhánh hiện hành, không scan file cũ. Paths resolved khi drive
sẽ trỏ project root được chọn; checkpoint/checksum phục vụ thành viên khác tiếp tục.
Không ghi notebook fixture là bản full-data đã chạy. Notebook 08 dùng CPU/đĩa, không cần GPU."""),
"""
from src.utils.hashing import hash_file
print("BẢNG 08-K: ĐƯỜNG DẪN, CHECKSUM VÀ ĐIỀU KIỆN TIẾP TỤC")
display(pd.DataFrame([{"Artifact":name,"Resolved path":str(path),"SHA-256":hash_file(path),
    "Model status":history_status["status"],"Version":history_status["signature"]}
    for name,path in history_artifacts.items()]))
print("Kết luận theo phiên chạy:", history_status["status"], history_status["reason_code"],
      "; eligible=", history_status["eligible_historical_records"])
print("Tiếp tục: NB09 current tasks theo điều kiện riêng. S2/P3 chỉ khi require_historical_dataset xác minh completed.")
con.close()
""",
    ]
)

# 09_rq3_prediction.ipynb
create_notebook(
    "09_rq3_prediction.ipynb",
    "09 — RQ3: huấn luyện ứng viên trên train, đánh giá validation",
    "Phát triển S1/P1/P2 bằng mô hình thật; chưa mở final test hoặc tự khóa G4.",
    [
        ("markdown", r"""### 0. Bối cảnh và câu hỏi khoa học
RQ3 phân biệt hồi quy hồi cứu với dự đoán trước trận. S1 dùng hành vi trong trận để giải thích survival; P1/P2 giải thích placement trong chính trận đó. Đây không phải dự báo trực tiếp thời gian thực và không chứng minh quan hệ nhân quả.

Notebook thực thi ứng viên S1/P1/P2, S2/P3 khi receipt NB08 hợp lệ, cặp T0/T1 và các ablation trên validation. Mọi lựa chọn đặc trưng và mô hình vẫn phải được phê duyệt trước G4; không dùng bảng development làm kết quả nghiên cứu chính thức."""),
        ("markdown", r"""### 1. Đầu vào, provenance và đơn vị phân tích
Đầu vào là player-match features từ NB04 và split_assignments từ NB02; chronology/history status từ NB08 chỉ dùng xác định điều kiện lịch sử. Một dòng là một player-match, nhưng người chơi cùng trận không độc lập. Mọi người trong cùng match phải thuộc cùng split.

Cấu hình từ YAML quyết định task bật/tắt và danh sách đặc trưng; không tự điền các quyết định còn null. Backend GPU phải có thật, lỗi GPU không được đổi ngầm sang CPU. Fixture nghiệm thu dùng CPU riêng, không chứng nhận T4."""),
        """
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display, Image, Markdown
from src.utils.config import load_config, resolve_paths
from src.data.io import read_json
from src.features.registry import FeatureRegistry
from src.models.registry import create_canonical_experiment_matrix
from src.models.training import load_rq3_development_data, run_rq3_prediction_suite
cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
device = cfg["rq3"]["device"]
registry = FeatureRegistry()
display(pd.DataFrame([{"Cấu hình": "device", "Giá trị": cfg["rq3"]["device"]},
                      {"Cấu hình": "evaluation scope", "Giá trị": "train + validation; final test closed"},
                      {"Cấu hình": "historical protocol", "Giá trị": str(cfg["rq3"]["historical"]["evaluation_protocol"])}]))
""",
        ("markdown", r"""### 2. Nạp dữ liệu development, không mở final test
Join được thực hiện bằng DuckDB trước khi đưa dữ liệu vào pandas. Chỉ train và validation được nạp: không đọc target hoặc hành vi của final test vào dataframe. Kiểm tra toàn bộ khóa match/split chỉ sử dụng metadata, không dùng kết quả test để chọn mô hình.

Bảng 09-A cho biết N dòng, N trận theo split. Không lấy mẫu hoặc giảm số dòng rồi gọi là full-data. Có ngân sách host RAM trước collect và đo RAM/VRAM trước từng fit. Ước lượng không phải peak đã đo hay bảo đảm quota; thiếu tài nguyên phải ghi resource_limited, không đổi thuật toán."""),
        """
df = load_rq3_development_data(paths,config=cfg)
display(Markdown("Bảng 09-A. Quy mô đầu vào development, nguồn NB04 + NB02."))
display(df.groupby("split").agg(rows=("match_id","size"), matches=("match_id","nunique")).reset_index())
""",
        ("markdown", r"""### 3. Cohort, target và leakage
S1 chỉ giữ survival hữu hạn và lớn hơn 0. P1/P2 cùng giữ placement trong [0,1] và survival hợp lệ, để so sánh không bị thay đổi tập người chơi. Dòng loại được thống kê riêng, không xóa dữ liệu nguồn.

D01 cấm target survival và mọi hậu duệ dùng duration trong S1. D02 yêu cầu P1/P2 chỉ khác survival trực tiếp; timing theo phase vẫn có coupling với duration, vì vậy P2 không đồng nghĩa với hoàn toàn không chứa thông tin thời lượng. ID/match/player/team/mode không phải predictor.

Allowlist được đọc đúng từ configs/features.yaml, kiểm bằng registry và closure (toàn bộ phụ thuộc). Thiếu đặc trưng phải lỗi, không âm thầm bớt feature."""),
        """
display(pd.DataFrame([{"Task": task, "Features": ", ".join(cfg["features"]["tasks"][key])}
    for task,key in [("s1","s1_safe_features"),("p1","p1_features"),("p2","p2_features")]]))
""",
        ("markdown", r"""### 4. Phương pháp, baseline và train-only preprocessing
Mỗi task có train-mean, train-median và OLS. Hai baseline không có predictor, chỉ học trung bình/trung vị target của train. OLS dùng mean imputation và chuẩn hóa fit trên train, giữ thứ tự cột; validation không được dùng để fit.

Với train-mean: $\hat y_i=\frac{1}{n_{train}}\sum_{j\in train}y_j$. OLS cực tiểu $\sum_{j\in train}(y_j-\beta_0-x_j^T\beta)^2$. Không tự thay OLS bằng SGD khi thiếu bộ nhớ, không refit train+validation. Pipeline được lưu joblib qua staging và xác minh trước khi thay file canonical."""),
        """
history_status_file = paths["manifests"] / "historical_status.json"
history_status = read_json(history_status_file) if history_status_file.is_file() else {}
grade = history_status.get("grade", history_status.get("chronology_grade", "unverified"))
res = run_rq3_prediction_suite(df, paths, feature_registry=registry,
    experiment_registry=create_canonical_experiment_matrix(), checkpoint_mgr=_pubg_checkpoint,
    chronology_grade=grade, device=device, run_nonlinear=True,
    batch_size=cfg["models"]["resource_limits"]["chunk_batch_size"], config=cfg)
display(Markdown("Bảng 09-B. Cohort thực dùng theo task/split; excluded_rows đối chiếu đầu vào development."))
display(res["cohort_table"])
""",
        ("markdown", r"""### 5. Kiểm tra trạng thái và điều kiện S2/P3
Bảng 09-C giữ cả thí nghiệm không chạy và reason. Grade C chặn lịch sử; A/B không tự chứng nhận dữ liệu sẵn sàng. S2/P3 chỉ nạp historical rows đủ ngưỡng sau kiểm status/scope/hash/checkpoint NB08. Thiếu receipt, stale hoặc không có train/validation đủ điều kiện thì blocked, metric null. Features chỉ là strict-past, không chứa outcome trận hiện tại.

T0/T1 cùng cohort P2, target, split và recipe OLS; T1 là P2 timing set, T0 bỏ timing. NB09 là nguồn duy nhất của cặp development. Phi tuyến có gate/config; HGB/RF CPU chỉ khi yêu cầu CPU rõ ràng, GPU chưa hỗ trợ ghi blocked, không đổi ngầm backend. completed ở registry có split_scope development_train_validation chỉ chứng nhận ứng viên train/validation, không chứng nhận final test hoặc notebook hoàn tất."""),
        """
display(Markdown("Bảng 09-C. Trạng thái thực nghiệm và lý do chưa chạy."))
display(res["experiment_status_table"][["experiment_id","task","status","reason_code","split_scope"]])
display(Markdown("Bảng 09-F. RAM/VRAM đo thực tế, estimated working bytes và fit/resume. Source: rq3_development_resources.csv. Ước lượng không bảo đảm peak."))
display(res["resource_table"])
""",
        ("markdown", r"""### 6. Đọc kết quả validation
Bảng 09-D có MAE (sai số tuyệt đối trung bình), RMSE (nhạy với sai số lớn) và $R^2$ (mức giải thích biến thiên). MAE/RMSE thấp hơn là tốt; $R^2$ có thể âm và không xác định khi target hằng hoặc N<2, không thay bằng 0.

Placement có đơn vị score [0,1]; survival giữ đơn vị thời gian nguồn chưa xác minh, không mặc định là giây. Micro tính trên player rows; match_mae cho mỗi trận trọng số như nhau; team_mae chỉ áp dụng placement và không áp dụng S1. Không so sánh MAE survival trực tiếp với MAE placement. N là validation rows, n_matches là số trận thực."""),
        """
display(Markdown("Bảng 09-D. So sánh ứng viên trên validation; chưa phải final test."))
display(res["comparison_table"])
display(Markdown("Bảng 09-G. Validation theo mode: chỉ so sánh cùng task/đơn vị. Source: rq3_development_mode_metrics.csv."))
display(res["mode_table"])
display(Markdown("Bảng 09-H. Variance/missing/VIF chỉ từ train; VIF diagnostic, không xóa máy móc. Source: rq3_features_diagnostics.csv."))
display(pd.read_csv(res["artifacts"]["diagnostics_features"]))
display(Markdown("Bảng 09-I. Permutation importance toàn validation: MAE tăng sau xáo trộn, mean/std qua 3 lần, seed42; tương quan feature ảnh hưởng diễn giải."))
display(pd.read_csv(res["artifacts"]["diagnostics_importance"]))
display(Markdown("Bảng 09-J. Coefficients từ pipeline train-only; nhãn standardized chỉ khi scaler thật sự bật. Không suy ra quan hệ nhân quả."))
display(pd.read_csv(res["artifacts"]["diagnostics_coefficients"]))
""",
        ("markdown", r"""### 7. Trực quan kết quả và cách đọc
Hình 09-01 gồm một panel mỗi task, nguồn rq3_development_validation.csv. Trục ngang là ứng viên, trục dọc MAE validation đúng đơn vị target, N và số trận ghi trong title. Không chọn mô hình chỉ từ cột thấp nhất: còn cần độ ổn định, diễn giải và chi phí trước G4.

Hình 09-02 dùng toàn bộ validation predictions của OLS P2, không lấy mẫu: hexbin biểu diễn số player rows theo ô, đường chéo là dự đoán đúng. Residual = actual - predicted: dương là dự đoán thấp, âm là dự đoán cao. Không clip dự đoán ngoài [0,1] để làm đẹp metric. Giới hạn: hình chưa có CI hoặc kiểm định ablation, sẽ bổ sung đúng giai đoạn."""),
        """
plot_tasks=["s1","p1","p2"]+[task for task in ["s2","p3"] if task in set(res["comparison_table"].task)]
fig, axes = plt.subplots(1,len(plot_tasks),figsize=(5*len(plot_tasks),5))
for ax,task in zip(axes,plot_tasks):
    sub=res["comparison_table"].query("task == @task")
    sub=sub[~sub.experiment_id.str.contains("ablation")]
    if sub.empty:
        ax.set_title(task.upper()+": disabled by config")
        ax.axis("off")
        continue
    ax.bar(sub.experiment_id.str.replace(task+"_","",regex=False),sub.mae)
    ax.set_title(f"{task.upper()} validation: N={int(sub.n.iloc[0])}, matches={int(sub.n_matches.iloc[0])}")
    ax.set_ylabel("MAE: "+sub.unit.iloc[0])
    ax.tick_params(axis="x",labelrotation=35)
fig.tight_layout()
fig_path=paths["figures"]/"rq3_development_mae.png"
fig.savefig(fig_path,dpi=130); plt.close(fig)
res["artifacts"]["validation_mae_figure"]=fig_path
display(Image(filename=str(fig_path)))
if "p2_ols_no_direct_survival" in res["predictions"]:
    p2_val=pd.read_parquet(res["predictions"]["p2_ols_no_direct_survival"],filters=[("split","==","validation")])
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    hexplot=axes[0].hexbin(p2_val.actual,p2_val.predicted,gridsize=25,mincnt=1)
    colorbar=fig.colorbar(hexplot,ax=axes[0],label="Player rows")
    if hexplot.get_array().min() == hexplot.get_array().max():
        colorbar.set_ticks([hexplot.get_array()[0]])
    axes[0].plot([0,1],[0,1],color="red")
    axes[0].set(xlabel="Actual placement [0,1]",ylabel="Predicted placement (unclipped)",title=f"P2 validation N={len(p2_val)}")
    axes[1].hist(p2_val.residual,bins=20)
    axes[1].set(xlabel="Residual: actual - predicted (score)",ylabel="Player rows",title="P2 validation residuals")
    fig.tight_layout()
    fig_path=paths["figures"]/"rq3_development_p2_diagnostics.png"
    fig.savefig(fig_path,dpi=130); plt.close(fig)
    res["artifacts"]["p2_validation_figure"]=fig_path
    display(Image(filename=str(fig_path)))
else:
    display(Markdown("Hình 09-02 không tạo: P2 OLS bị tắt hoặc blocked, không có prediction để vẽ."))
""",
        ("markdown", r"""### 7.1. Cặp timing, contribution và mode

Hình 09-03 dùng validation của T0/T1 và các nhánh ablation, không dùng test. Delta MAE = candidate - full OLS; dương nghĩa là bỏ nhóm làm tăng lỗi, âm nghĩa là nhánh bỏ nhóm tốt hơn ở tập validation này. Cùng row IDs/target/split, nhưng mỗi nhánh fit imputer/scaler riêng trên train. Không có CI tại đây; chưa kết luận nhóm quan trọng chắc chắn.

Hình 09-04 dùng bảng mode metrics, mỗi panel một task với đúng đơn vị target và N từ bảng 09-G. Không so sánh trực tiếp độ cao cột S1 với placement, không coi mode ít quan sát là ổn định."""),
        """
def _save_rq3_figure(fig,key,filename):
    fig.tight_layout()
    file=paths["figures"]/filename
    fig.savefig(file,dpi=130)
    plt.close(fig)
    res["artifacts"][key]=file
    display(Image(filename=str(file)))

comparison=res["comparison_table"]
anchor=cfg["rq3"]["experiments"]["ablation_full_task"]
anchor_id={"p2":"p2_ols_no_direct_survival","p1":"p1_ols_direct_survival","s1":"s1_retrospective_survival"}.get(anchor)
base=comparison[comparison.experiment_id==anchor_id]
ablation=comparison[comparison.experiment_id.str.contains("validation_ablation")].copy()
timing=comparison[comparison.task.isin(["t0","t1"])]
if not base.empty and not ablation.empty:
    ablation["delta_mae"]=ablation.mae-float(base.mae.iloc[0])
    display(Markdown("Bảng 09-K. Ablation validation delta MAE, candidate - reference; source rq3_development_validation.csv."))
    display(ablation[["experiment_id","n","unit","mae","delta_mae"]])
    fig,axes=plt.subplots(1,2,figsize=(12,4))
    axes[0].barh(ablation.experiment_id.str.rsplit("_",n=1).str[-1],ablation.delta_mae)
    axes[0].axvline(0,color="black")
    axes[0].set(xlabel="Delta MAE: candidate - full ("+str(base.unit.iloc[0])+")",title=anchor.upper()+" validation group ablation")
    if not timing.empty:
        axes[1].bar(timing.task,timing.mae)
        axes[1].set(ylabel="MAE placement score",title=f"Timing validation N={int(timing.n.iloc[0])}")
    else:
        axes[1].axis("off")
        axes[1].set_title("Timing disabled or blocked")
    _save_rq3_figure(fig,"ablation_timing_figure","rq3_validation_ablation_timing.png")
else:
    display(Markdown("Hình 09-03 chưa có: anchor OLS/nhánh ablation không chạy; không vẽ delta giả."))

if not res["mode_table"].empty:
    fig,axes=plt.subplots(1,3,figsize=(14,4))
    for ax,task,exp_id in zip(axes,["s1","p1","p2"],["s1_retrospective_survival","p1_ols_direct_survival","p2_ols_no_direct_survival"]):
        sub=res["mode_table"].query("experiment_id == @exp_id")
        if sub.empty:
            ax.axis("off"); ax.set_title(task+": blocked")
            continue
        ax.bar(sub["mode"].astype(str),sub.mae)
        ax.set(title=task.upper()+f" validation N={int(sub.n.sum())}",ylabel="MAE: "+sub.unit.iloc[0])
    _save_rq3_figure(fig,"mode_mae_figure","rq3_validation_mode_mae.png")
""",
        ("markdown", r"""### 7.2. Tài nguyên và bằng chứng chọn feature

Hình 09-05 so working-memory estimate với RAM trống đo trước fit; trục GiB, không phải RAM peak. VRAM chỉ có giá trị khi CUDA kiểm tra được, CPU là không áp dụng, không phải 0 GB GPU. Bảng 09-F ghi backend được yêu cầu và fit/resume; model không hỗ trợ GPU có reason trong bảng 09-C.

Hình 09-06 là train Pearson correlation của P2, nguồn rq3_correlations_diagnostics.csv. Ô xám là undefined/missing/constant, không phải correlation=0. Các feature deterministic descendants có thể tương quan mạnh; dùng thêm VIF trên raw suitable subset và permutation/ablation trên validation trước khi nhóm quyết định final features. Không tự xóa feature theo một ngưỡng VIF."""),
        """
resources=res["resource_table"]
if not resources.empty:
    measured=resources.dropna(subset=["estimated_working_bytes","ram_available_bytes"])
    if not measured.empty:
        fig,axes=plt.subplots(1,2,figsize=(14,5))
        short=measured.experiment_id.str.replace("_ols_no_direct_survival","_OLS",regex=False)
        axes[0].barh(short,measured.estimated_working_bytes/(1024**3))
        axes[0].set(xlabel="Bộ nhớ làm việc ước lượng (GiB)",title="Ước lượng, không phải bộ nhớ đỉnh đo được")
        axes[1].plot(range(len(measured)),measured.ram_available_bytes/(1024**3),label="RAM máy chủ còn trống")
        gpu=measured.dropna(subset=["vram_free_bytes"])
        if not gpu.empty:
            axes[1].plot(gpu.index,gpu.vram_free_bytes/(1024**3),label="VRAM free")
        axes[1].set(xlabel="Thứ tự thí nghiệm",ylabel="GiB",title="Đo trước huấn luyện hoặc tiếp tục")
        axes[1].legend()
        _save_rq3_figure(fig,"resource_figure","rq3_development_resources.png")

correlations=pd.read_csv(res["artifacts"]["diagnostics_correlations"])
if "task" in correlations:
    pearson=correlations[(correlations.task=="p2") & (correlations.method=="pearson")]
    if not pearson.empty:
        names=cfg["features"]["tasks"]["p2_features"]
        matrix=pd.DataFrame(float("nan"),index=names,columns=names)
        for row in pearson.itertuples():
            matrix.loc[row.left,row.right]=row.correlation
            matrix.loc[row.right,row.left]=row.correlation
        stats=pd.read_csv(res["artifacts"]["diagnostics_features"])
        for row in stats[(stats.task=="p2") & ~stats.constant_observed & ~stats.all_missing].itertuples():
            matrix.loc[row.feature,row.feature]=1.
        fig,ax=plt.subplots(figsize=(10,8))
        cmap=plt.get_cmap("coolwarm").copy(); cmap.set_bad("lightgray")
        image=ax.imshow(matrix.to_numpy(),vmin=-1,vmax=1,cmap=cmap)
        ax.set_xticks(range(len(names)),names,rotation=90,fontsize=8)
        ax.set_yticks(range(len(names)),names,fontsize=8)
        ax.set_title("Pearson P2 trên train: ô xám là không xác định")
        fig.colorbar(image,ax=ax,label="Hệ số Pearson")
        _save_rq3_figure(fig,"correlation_figure","rq3_train_p2_correlation.png")
""",
        ("markdown", r"""### 8. G4, prior exposure và giới hạn hiện tại
Không tự tạo selection_lock và không predict/evaluate test. Receipt development ghi final_test_exposed=false cho phiên này, không khẳng định các phiên cũ chưa xem test: code cũ từng dự đoán test trước auto-lock, cần audit run cũ.

G4 đã có cơ chế kiểm tra recipe, hash dữ liệu/split/model/config, thứ tự đặc trưng, diagnostics và comparisons. Nhóm phải phê duyệt file artifacts/manifests/rq3_selection_decision.json sau khi xem validation; không tự sinh approved=true. File cần approved_by, fit_protocol=fit_train_only, selected_experiments, features_by_experiment, registry_hash, validation_hash, diagnostics_hash, error_bins (survival/placement), comparisons (reference/candidate) và selection_reasons (performance/generalization/interpretability/stability/compute). Thiếu hoặc stale thì không đọc final test và không mở NB10. Không sửa YAML null chỉ để vượt gate.

SGD là ứng viên CPU riêng, không thay OLS khi OOM. Mean imputer và scaler được fit qua các pass train rồi giữ cố định; mỗi epoch đi qua mọi train row, chỉ validation ngoài dùng early stopping. Batch order/seed và số dòng từng epoch được lưu trong model. Không triển khai median/RobustScaler streaming khi chưa có exact train quantiles disk-backed; cấu hình hiện tại dùng mean và StandardScaler."""),
        """
from src.models.rq3_selection import lock_rq3_selection, evaluate_locked_test
from src.data.io import atomic_write_json
from src.utils.hashing import hash_file
figure_sources={
    "validation_mae_figure":("validation","Validation MAE; thấp hơn tốt hơn, không tự chọn model; đơn vị theo target."),
    "p2_validation_figure":("predictions_p2_ols_no_direct_survival","P2 validation observed/predicted và residual; không clip, màu là số player rows."),
    "ablation_timing_figure":("validation","Delta MAE candidate - full; cùng cohort, chưa có CI, không kết luận nhân quả."),
    "mode_mae_figure":("mode_metrics","Validation OLS theo mode; N và đơn vị theo task, không gộp các thang đo."),
    "resource_figure":("resources","GiB dự trù và RAM/VRAM đo trước experiment; không phải peak memory."),
    "correlation_figure":("diagnostics_correlations","P2 train Pearson; xám là undefined/constant, không thay bằng zero; không tự xóa feature.")}
catalog=[]
for key,(source_key,caption) in figure_sources.items():
    if key in res["artifacts"]:
        source=res["artifacts"][source_key]
        catalog.append({"figure":str(res["artifacts"][key]),"sha256":hash_file(res["artifacts"][key]),
            "source":str(source),"source_sha256":hash_file(source),"caption":caption,
            "cohort_counts_source":str(res["artifacts"]["cohorts"]),"scope":"development_train_validation",
            "sampled":False,"report_ready":False})
catalog_file=paths["manifests"] / "rq3_figure_catalog.json"
atomic_write_json(catalog_file,{"figures":catalog,"limitation":"Development figures; not a locked final release."})
res["artifacts"]["figure_catalog"]=catalog_file
display(pd.DataFrame(catalog))
development_artifacts=dict(res["artifacts"])
selection_lock = lock_rq3_selection(paths,cfg)
if selection_lock is None:
    display(Markdown("G4 pending: cần rq3_selection_decision.json do nhóm phê duyệt, gắn registry/validation/diagnostics hash, final feature order, reasons và error bins/comparisons. Không tự chọn hoặc mở final test."))
else:
    display(Markdown("G4 LOCKED: chỉ predict từ model train-only đã lưu; không fit lại. Bảng final test tách khỏi development."))
    final_table,final_artifacts=evaluate_locked_test(paths,cfg,selection_lock,batch_size=cfg["models"]["resource_limits"]["chunk_batch_size"])
    display(final_table)
    res["artifacts"].update({"final_"+key:value for key,value in final_artifacts.items()})
    res["artifacts"]["selection_lock"]=paths["manifests"] / "rq3_selection_lock.json"
    res["status"]="completed"
""",
        ("markdown", r"""### 9. Lưu trữ, bàn giao và điều kiện chạy tiếp
Model/prediction development nằm dưới artifacts/models và artifacts/experiments; bảng dưới reports/tables; hình dưới reports/figures; gate/registry dưới artifacts/manifests, tất cả cùng storage root đã cấu hình. File canonical được thay thế, không thêm số thứ tự.

Bảng 09-E liệt kê đường dẫn thật. Checkpoint rq3_development chứng nhận artifact ứng viên. Khi chưa có G4 hợp lệ, notebook09 blocked và NB10 chưa được chạy; sau khóa được phê duyệt, final-test predictions và comparison được lưu tách biệt, chỉ predict từ pipeline train-only. Kiểm thử fixture không phải bằng chứng full-data/GPU/Drive. T4 chỉ hỗ trợ model có backend GPU tương ứng, không tăng RAM của máy chủ."""),
        """
display(Markdown("Bảng 09-E. Artifact development và trạng thái bàn giao."))
display(pd.DataFrame([{"Artifact":k,"Path":str(v)} for k,v in res["artifacts"].items()]))
_pubg_checkpoint.commit("rq3_development", _pubg_signature, development_artifacts, metadata={"scope":"train_validation_only","report_ready":False})
if selection_lock is None:
    _pubg_checkpoint.record_blocked("notebook/09_rq3_prediction.ipynb",_pubg_signature,"pending_G4",
        metadata={"development_stage":"rq3_development","report_ready":False})
else:
    _pubg_checkpoint.commit("rq3_prediction",selection_lock["recipe_hash"],res["artifacts"],metadata={"gate":"G4","scope":"locked_test"})
    _pubg_checkpoint.commit("notebook/09_rq3_prediction.ipynb",_pubg_signature,res["artifacts"],writer_id=_pubg_writer)
from src.utils.logging import write_handover, write_figure_metadata
_pubg_stage_artifacts=res["artifacts"]
write_handover(paths["manifests"] / "notebook_handover.csv",stage="09_rq3_prediction.ipynb",
    artifacts=_pubg_stage_artifacts,status="blocked" if selection_lock is None else "completed",writer_id=_pubg_writer,version=_pubg_signature,
    next_step="09_rq3_prediction.ipynb: pending G4 and remaining Phase 11 tasks" if selection_lock is None else "10_ablation_error_analysis.ipynb")
write_figure_metadata(paths["manifests"] / "figure_metadata.csv",stage="09_rq3_prediction.ipynb",artifacts=_pubg_stage_artifacts)
print("Development artifacts saved. Notebook09 blocked pending G4; do not run NB10 yet." if selection_lock is None else "G4 locked and test artifacts saved; NB10 handoff completed.")
"""
    ]
)

# 10_ablation_error_analysis.ipynb
create_notebook(
    "10_ablation_error_analysis.ipynb",
    "10 - So sánh đã khóa, đóng góp nhóm và phân tích sai số",
    "RQ3: đọc saved predictions sau G4; không huấn luyện lại, không chọn feature từ test.",
    [
        ("markdown", r"""## 0. Câu hỏi nghiên cứu và phạm vi
Timing có giá trị dự đoán bổ sung không? Bỏ nhóm Combat, Movement, Support hoặc Timing làm thay đổi lỗi bao nhiêu?
Đây là so sánh hồi cứu, không phải bằng chứng nhân quả. G4 phải đăng ký các nhánh và cặp so sánh trước test.
Notebook 09 là nguồn huấn luyện duy nhất. Notebook 10 chỉ đọc mô hình/dự đoán đã khóa; không mở raw, không refit hoặc thay split.
Fixture nhỏ chỉ kiểm chứng logic, không phải kết quả PUBG chính thức. Test từng được xem trong code cũ phải công bố, không gọi là untouched.
"""),
        ("markdown", r"""## 1. Đầu vào, provenance và điều kiện G4
Đọc rq3_selection_lock.json và checkpoint rq3_prediction. Kiểm hash code/config/input/split/model/evidence trước đọc dự đoán.
File có trên Drive chưa đủ: phải committed, completed và compatible. Thiếu G4 hoặc artifact hỏng thì dừng, quay lại Notebook 09 để kiểm.
CPU đủ cho phép tính đánh giá; không cài GPU chỉ để vẽ. Mô hình đã train GPU vẫn giữ backend gốc, không chuyển hoặc train lại.
"""),
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0,str(PROJECT_ROOT))
import pandas as pd
from IPython.display import display, Markdown, Image
from src.utils.config import load_config, resolve_paths
from src.data.io import read_json
from src.evaluation.comparisons import comparison_context, run_locked_comparisons
cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
""",
"""
context = comparison_context(paths,cfg)
recipe=context["recipe"]
display(Markdown("Bảng 10-A. Recipe G4, người duyệt, scope và prior test exposure; fixture approval không duyệt nghiên cứu thật."))
display(pd.DataFrame([{"gate":recipe["gate"],"recipe_hash":recipe["recipe_hash"],"approved_by":recipe["decision"]["approved_by"],"fit_protocol":recipe["decision"]["fit_protocol"],"prior_test_exposure":recipe["prior_test_exposure"]}]))
display(Markdown("Bảng 10-B. Các cặp đã đăng ký trước test và khoảng chia sai số. Không thêm cặp theo kết quả test."))
display(pd.DataFrame(recipe["decision"]["comparisons"]))
display(pd.DataFrame([{"task":key,"edges":str(value),"boundary":"[left,right); final right included"} for key,value in recipe["decision"]["error_bins"].items()]))
""",
        ("markdown", r"""## 2. Phương pháp so sánh công bằng và ablation closure
P1/P2 cùng cohort, chỉ khác survival trực tiếp (D02). T1 neo đúng P2; T0 bỏ timing nhưng giữ cohort, target và model recipe.
ABL-T bỏ cả timing tuyệt đối, phase và descendants. Combat/Movement/Support cũng bỏ derived/ratio/indicator phụ thuộc.
Các nhánh đã fit train riêng với cùng policy imputer/scaler/seed. Không lấy scaler đầy đủ rồi cắt cột.
Recipe table lưu giữ/bỏ feature, counts, cohort/model hash và run ID. Survival không dùng phase/duration descendants (D01).
Ghép theo row_id một-một và exact identity/target/split; duplicate, missing, extra hoặc mismatch phải dừng, không dùng giao nhỏ hơn.
"""),
        ("markdown", r"""## 3. Hợp đồng metric và bất định
Với residual $e_i=y_i-\hat y_i$: $MAE=N^{-1}\sum|e_i|$, $RMSE=\sqrt{N^{-1}\sum e_i^2}$,
$R^2=1-\sum e_i^2/\sum(y_i-\bar y)^2$. Tính float64; $N<2$ hoặc SST=0 trả undefined có lý do.
Micro mỗi player-match trọng số 1; match-aware mỗi trận tổng trọng số bằng nhau và R² weighted toàn cục, không average R² từng trận.
Team placement đòi actual nhất quán trong đội rồi mean prediction; survival không áp dụng team metric. Không clip prediction.
$\Delta=metric_{candidate}-metric_{reference}$: MAE/RMSE âm tốt hơn, R² dương tốt hơn.
Bootstrap lấy mẫu cả trận có hoàn lại, cùng multiplicity cho hai nhánh, aggregate sum/count và recompute metric toàn cục.
CI percentile 95% chỉ cho micro đã đăng ký. Counts/seed/replicates/budget/valid replicates lưu receipt; không vẽ CI giả.
CI chứa 0 không chứng minh có cải thiện; bootstrap theo trận chưa loại phụ thuộc player lặp qua nhiều trận.
"""),
"""
evaluation = run_locked_comparisons(paths,cfg,context)
evaluation_artifacts=evaluation["artifacts"]
display(Markdown("Bảng 10-C. Features và artifact của từng nhánh: giữ/bỏ, recipe, cohort, train/validation/test N; không refit."))
display(pd.read_csv(evaluation_artifacts["features"]))
display(Markdown("Bảng 10-D. Metric micro/match-aware/team-aware từ saved predictions; R² thiếu là undefined, không bằng 0."))
display(pd.read_csv(evaluation_artifacts["metrics"]))
display(Markdown("Bảng 10-E. Paired delta candidate-reference, exact pairing, N/trận/scope và CI micro nếu đã tính."))
display(pd.read_csv(evaluation_artifacts["comparisons"]))
""",
        ("markdown", r"""## 4. T0/T1, P1/P2, baselines và ablation
Đọc delta cùng N và recipe, không so số lỗi giữa survival và placement vì khác đơn vị.
Ablation đo contribution có điều kiện trên feature/model hiện tại, không xếp hạng nhân quả.
Forest plot chấm là observed delta, đoạn là CI 95%; CI chứa 0 cần diễn giải thận trọng.
CI match/team-aware chưa đăng ký được ghi not_requested, không suy từ CI micro.
"""),
"""
display(Markdown("Bảng 10-F. Đầy đủ ablation và bootstrap metadata từng cặp."))
display(pd.read_csv(evaluation_artifacts["ablation"]))
display(pd.DataFrame([{"pair":key,**{k:v for k,v in read_json(file).items() if not k.startswith("delta_")}} for key,file in evaluation_artifacts.items() if key.startswith("bootstrap_")]))
figure_catalog=read_json(evaluation_artifacts["figure_catalog"])
for name in ["comparisons","ablation","forest"]:
    if name in figure_catalog:
        item=figure_catalog[name]
        display(Markdown(f"Hình 10-{name}. {item['caption']} Scope={item['scope']}; nguồn={item['source']}; N/trận trên hình và bảng 10-E."))
        display(Image(filename=item["path"]))
    else:
        display(Markdown(f"Hình {name}: không tạo khi nhánh/CI chưa có; xem status trong bảng."))
""",
        ("markdown", r"""## 5. Sai số theo lát cắt và coverage
Mode dùng team_size_mode canonical, không suy từ party_size 1/2/4. Target đọc metadata, không đoán vì actual nằm trong [0,1].
Placement/survival regions và history depth theo bins G4. Khoảng [a,b), khoảng cuối gồm b; ngoài range/missing có dòng riêng.
Mỗi chiều chia độc lập toàn cohort: không cộng counts giữa mode, target region và history vì sẽ đếm trùng.
N rows/matches, coverage, mean residual và R² reason luôn đi kèm; slice trống là insufficient, ít trận là unstable_small_slice.
Ngưỡng 2 trận chỉ là mức tối thiểu tính toán, không chứng nhận độ tin cậy khoa học; không xếp hạng chắc chắn nhóm ít quan sát.
"""),
"""
display(Markdown("Bảng 10-G. Sai số đầy đủ theo mode, target region, history depth nếu áp dụng; đơn vị/scope/N và trạng thái."))
display(pd.read_csv(evaluation_artifacts["errors"]))
display(Markdown("Bảng 10-H. Histogram residual toàn cohort; tổng counts mỗi model khớp test N."))
display(pd.read_csv(evaluation_artifacts["residuals"]))
for name in ["error","coverage","residual"]:
    if name in figure_catalog:
        item=figure_catalog[name]
        display(Markdown(f"Hình 10-{name}. {item['caption']} N/scope ở bảng 10-G/H; nguồn={item['source']}."))
        display(Image(filename=item["path"]))
""",
        ("markdown", r"""## 6. Importance và giới hạn diễn giải
Coefficients đọc fitted artifact train; chỉ gọi standardized khi scaler thực đã dùng. Indicator là feature sau transformation.
Regression tree dùng nhãn impurity decrease, không Gini classification. HGB không có native importance thì không bịa bảng.
Permutation tái sử dụng validation đã tính trước G4: MAE tăng, mean/std, repeats/seed/N và sampled=false. Std không phải CI 95%.
Feature tương quan chia sẻ hoặc che contribution; group ablation là bằng chứng chính. Không diễn giải causal.
Final-test permutation không được yêu cầu ở recipe hiện tại: không tính và không quay lại chọn feature; muốn tính phải đăng ký trước test.
"""),
"""
display(Markdown("Bảng 10-I. Coefficients/importance của fitted train artifacts; không fit lại."))
display(pd.read_csv(evaluation_artifacts["importance"]))
display(Markdown("Bảng 10-J. Permutation validation đã duyệt, uncertainty và status; failed không bị bỏ âm thầm."))
display(pd.read_csv(evaluation_artifacts["validation_importance"]))
display(Markdown("Bảng 10-K. Correlation train và pair N: hỗ trợ diễn giải importance, không tự xóa feature."))
display(pd.read_csv(evaluation_artifacts["validation_correlations"]))
if "importance" in figure_catalog:
    item=figure_catalog["importance"]
    display(Markdown(f"Hình 10-importance. {item['caption']} N/repeats/seed trên hình; nguồn={item['source']}."))
    display(Image(filename=item["path"]))
""",
        ("markdown", r"""## 7. Kết quả kỳ vọng, quan sát và kiểm chứng
Kỳ vọng: exact pairing và recipe checks đạt; identical predictions có delta=0; shuffle không đổi kết quả.
Quan sát lấy bảng 10-D/E, không ghi số hay kết luận định sẵn. Kiểm thử còn bao gồm missing/extra/duplicate/target/team conflict,
constant target, multiplicity, RAM budget, corrupt checkpoint và compatible resume.
Trước báo cáo đối chiếu CSV, source checksum, N và caption. Fixture có output thật không phải kết quả nghiên cứu thật.
"""),
        ("markdown", r"""## 8. Hạn chế và những gì chưa chứng nhận
Chưa full-data, GPU T4/cuML, Drive replacement/shortcut/quota hoặc peak RAM thực. Runtime/Parquet estimate không phải quota hay peak guarantee.
Chronology/history decisions và G4 production vẫn phải nhóm duyệt. Prior exposure unknown không được gọi untouched.
Match bootstrap chưa mô hình hóa dependence của player lặp giữa trận; slice nhỏ và feature correlation hạn chế diễn giải.
CI không tính hoặc undefined phải giữ missing/reason. Không thay estimator, lấy mẫu hoặc chọn lại thiết kế để làm đẹp test.
"""),
        ("markdown", r"""## 9. Lưu canonical, resume và bàn giao Notebook 11
Mỗi cặp lưu CSV và bootstrap JSON riêng/checkpoint signature; resume chỉ cặp compatible completed. Các file cùng tên được thay thế qua verified IO.
Checkpoint ablation_error chứa bảng/hình/catalog/receipt với hash recipe/input/model/predictions/code/config. Output lỗi không được gọi completed.
Thành viên sau dùng cùng root Drive và cùng source/config/notebook version, không cần RAM phiên trước. Receipt/figure catalog ghi report_ready=false cho tới G5.
Notebook 11 phải kiểm required matrix và immutable release; hoàn tất NB10 không tự chứng nhận G5.
"""),
"""
display(Markdown("Bảng 10-L. Artifact và bàn giao: canonical path; scope/recipe/source hash trong receipt."))
display(pd.DataFrame([{"artifact":key,"path":str(file)} for key,file in evaluation_artifacts.items()]))
display(pd.DataFrame([{"status":evaluation["status"],"compatible_resume":evaluation["reused"],"signature":context["signature"],"scope":"locked_test","report_ready":False,"next_notebook":"11_finalize_results.ipynb"}]))
print("Notebook 10 đã hoàn thành phân tích từ saved predictions; không train/refit. Chưa chứng nhận G5/full-data.")
"""
    ]
)

# 11_finalize_results.ipynb
create_notebook(
    "11_finalize_results.ipynb",
    "11 - Đối soát và khóa phiên bản kết quả nghiên cứu",
    "Chọn artifact theo registry/checkpoint, kiểm completeness và provenance trước G5; lưu release bất biến, không huấn luyện hoặc chọn lại mô hình.",
    [
        ("markdown", r"""### 0. Bối cảnh khoa học và giới hạn phạm vi

Notebook 11 không trả lời RQ mới. Nó xác định tập kết quả nào đủ bằng chứng để dùng cho báo cáo, tránh đọc nhầm file cũ hoặc bản thử nghiệm. Tính toàn vẹn (integrity) nghĩa là nội dung còn khớp SHA-256; độ đầy đủ (completeness) nghĩa là đủ nhiệm vụ, phạm vi và nguồn gốc theo đặc tả. Hai điều kiện độc lập: băm đúng một bảng thiếu vẫn không đạt G5.

Không tính lại metric, refit, chọn model, thay split hay mở test để tune. Receipt giả lập chỉ tạo `fixture_locked`, luôn `report_ready=False`; không in G5 production đạt."""),
        ("markdown", r"""### 1. Mục tiêu và các câu hỏi kiểm tra

RQ1, C1-C5 từng mode, baselines/S/P khả thi, T0/T1, ablation, sai số, importance và CI có đầy đủ không? Mỗi kết quả có actual run ID, scope, cohort/split và checksum không? Grade C có evidence chặn S2/P3, thay vì bỏ chúng khỏi báo cáo không? Release cũ có đọc được sau ghi đè canonical không?

Điều kiện thành công: selected checkpoints tương thích; schema, required matrix và receipts hợp lệ; snapshot đọc lại đúng; hình có caption và bảng nguồn đã chọn. Quyết định nghiên cứu chưa có bằng chứng phải giữ pending."""),
        ("markdown", r"""### 2. Đầu vào và bằng chứng lựa chọn

Nguồn vào là `finalization_selection.json`, G4 lock, registry NB09, checkpoint NB06/07/09/10 và artifact được chỉ định tường minh. Receipt cần người duyệt, config/G4 hashes, stage signatures, năm nhóm artifact, figure metadata và provenance. Không tự duyệt, không quét mọi CSV/model và không lấy latest.

Bảng 11-A mô tả input. N ở notebook này là số task/artifact, không phải số người chơi; N player/match nằm trong bảng cohort đã khóa. Đơn vị time chưa xác minh không được tự gọi là giây.

Nếu cần xuất RQ1 mô tả toàn bộ, đặt `PUBG_EXPORT_LOCKED_DESCRIPTIVE=True` trước cell này. Hàm chỉ cho phép khi `descriptive_design` đã đăng ký trong G4 trước test; chạy xong phải rà soát/cập nhật selection receipt theo artifact mới. RQ2 đã fit full eligible sau decision lock ở NB07, không fit lại tại đây. Mặc định không tự chạy export."""),
        """
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
import pandas as pd
from IPython.display import display, Markdown, Image
from src.utils.config import load_config, resolve_paths
from src.data.io import read_json
from src.evaluation.finalize import inspect_finalization, publish_final_release, verify_final_manifest_integrity, export_locked_rq1
cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
selection_path = paths["manifests"] / "finalization_selection.json"
PUBG_EXPORT_LOCKED_DESCRIPTIVE = globals().get("PUBG_EXPORT_LOCKED_DESCRIPTIVE", False)
if PUBG_EXPORT_LOCKED_DESCRIPTIVE:
    exported_rq1 = export_locked_rq1(paths, cfg)
    display(pd.DataFrame([{"Artifact mô tả":key,"Path":str(path),"Scope":"Thiết kế đã khóa trong G4, không chọn lại"} for key,path in exported_rq1.items()]))
display(pd.DataFrame([{"Nguồn":str(selection_path),"Tồn tại":selection_path.is_file(),"Scope runtime":cfg["runtime"]["mode"],"Vai trò":"Lựa chọn do nhóm duyệt; không tự tạo approval"}]))
""",
        ("markdown", r"""### 3. Phương pháp kiểm định trước khóa

Đối chiếu signature và checksum của producer; xác nhận run registry thực thi, schema/count và required matrix; kiểm nguồn hình/bảng, scope và decision receipts. Với artifact \(a\), điều kiện integrity là \(SHA256(a)=h_{locked}\), không suy ra thống kê đúng hay causal.

Missing, stale, failed và resource_limited chặn nhiệm vụ bắt buộc, không điền metric 0. Baseline hằng số không có native importance là not_applicable có lý do; S2/P3 chỉ ngoại lệ nếu chronology Grade C được xác minh. Không tự chấp nhận thất bại C1-C5 hoặc CI thiếu."""),
        """
try:
    inspected = inspect_finalization(paths, cfg)
except (ValueError, OSError, KeyError) as error:
    display(pd.DataFrame([{"Cổng":"G5","Trạng thái":"blocked","Nguyên nhân":str(error),"Tiếp tục":"Sửa producer/receipt theo bằng chứng; không đổi hash để ép pass"}]))
    _pubg_checkpoint.record_blocked("finalization", "pending_G5", str(error))
    raise
display(Markdown("Bảng 11-B. Nhiệm vụ bắt buộc/điều kiện và trạng thái thực"))
display(pd.DataFrame(inspected["matrix"]))
display(Markdown("Bảng 11-C. Artifact được chọn, scope và checksum"))
display(pd.DataFrame(inspected["artifact_rows"]))
""",
        ("markdown", r"""### 4. Đối soát và cách đọc kết quả

Mỗi dòng B là một task/run: completed không đồng nghĩa kết quả tốt; blocked conditional không có score. C liệt kê đúng file được khóa, scope và upstream signature. Đọc reason trước khi đọc metric. Số bảng lớn không chứng minh coverage đầy đủ; required matrix quyết định.

Bảng 11-D nối ba tầng provenance: nguồn/cohort, quyết định nghiên cứu và kết quả. Seed, feature order, fitted preprocessing/models, config, code/packages, history/split và prior test exposure phải được giữ trong snapshot. Không tuyên bố test chưa từng xem nếu lịch sử là unknown."""),
        """
display(pd.DataFrame([{"Thành phần":key,"Artifact metadata":value,"Phạm vi":inspected["selection"]["data_scope"]} for key,value in inspected["selection"]["provenance"].items()]))
display(pd.DataFrame([{"Thí nghiệm":key,"Run thực tế":value} for key,value in inspected["run_ids"].items()]))
""",
        ("markdown", r"""### 5. Công bố phiên bản bất biến

Sao chép duy nhất file được chọn sang `manifests/releases/<release_id>/`, đọc lại size/schema/checksum, ghi final/figure manifest rồi mới thay canonical và commit finalization. Tên canonical không có hậu tố (1)/(2); release ID là phiên bản tái lập có chủ đích.

Không sửa/xóa release cũ. Khi lỗi ghi, giữ bản đã khóa trước và trạng thái failed; staging chưa commit không phải kết quả chính thức. Một người ghi cùng stage tại một thời điểm."""),
        """
manifest, release_manifest_path = publish_final_release(paths, cfg, inspected)
valid, mismatches = verify_final_manifest_integrity(release_manifest_path)
if not valid:
    raise ValueError(str(mismatches))
display(pd.DataFrame([{"Release ID":manifest["release_id"],"Scope":manifest["data_scope"],"Trạng thái":manifest["status"],"Report ready":manifest["report_ready"],"Đọc lại checksum/schema":valid,"Manifest bất biến":str(release_manifest_path)}]))
print("G5 production đạt" if manifest["report_ready"] else "Chỉ khóa fixture kiểm thử; G5 production chưa được chứng nhận.")
""",
        ("markdown", r"""### 6. Hình đã khóa và bảng nguồn

Bảng 11-E giữ ID/RQ/source experiment/table, purpose, caption, scope, sampling và version. Chỉ preview file từ release, không dựng lại hình từ dữ liệu/model. Hình development/synthetic không được xuất thành official. Sampling phải có n/seed/rule; phần tính thống kê và mẫu vẽ phải phân biệt.

Cách đọc: đối chiếu caption với N/đơn vị/scope ở bảng nguồn; CI chứa 0 không đủ khẳng định chiều cải thiện. Importance và association không chứng minh quan hệ nhân quả."""),
        """
figure_rows = [{"ID":key,**{field:item[field] for field in ["research_question","source_table","source_experiment","purpose","caption","scope","sampling","report_ready","version"]}} for key,item in manifest["figures"].items()]
display(pd.DataFrame(figure_rows))
for key,item in manifest["figures"].items():
    if item["report_ready"] or manifest["status"]=="fixture_locked":
        display(Markdown(key + ": " + item["caption"]))
        display(Image(filename=str(release_manifest_path.parent / item["path"])))
""",
        ("markdown", r"""### 7. Diễn giải khoa học trong đúng phạm vi

Khóa thành công chỉ xác nhận release có bằng chứng theo protocol; không chứng minh mô hình chính xác, dự đoán trước trận hoặc causal. RQ1/RQ2 full descriptive theo design đã duyệt không được quay lại chọn K/features từ outcome. S1/P1/P2 là hồi cứu; historical chỉ có claim theo chronology/availability đã khóa.

Bảng 11-F giúp đối soát số lượng file mỗi nhóm và số task. Giá trị metric vẫn ở bảng được khóa, không copy số hoặc chọn winner tại đây."""),
        """
display(pd.DataFrame([{"Nhóm":category,"N artifact đã khóa":len(manifest[category]),"Mẫu số":"Tập selected, không toàn thư mục","Scope":manifest["data_scope"]} for category in ["tables","figures","models","predictions","metadata"]]))
""",
        ("markdown", r"""### 8. Hạn chế và quyết định còn mở

Fixture không nghiệm thu full-data, Colab/T4, quota, Drive shortcut hoặc remote atomicity. SHA-256 không kiểm scientific validity thay nhóm nghiên cứu. Source units, thresholds/K/history, chronology và test exposure cần evidence thật. Thiếu điều kiện sẽ dừng trước publication; không đổi cohort, thuật toán hoặc cắt sample để ép đạt.

Release tự chứa artifact phục vụ đọc; tái huấn luyện cần raw/processed và môi trường tương thích riêng. Manifest không biến model pickle thành định dạng portable giữa mọi package/GPU."""),
        ("markdown", r"""### 9. Artifact và bàn giao sang Notebook 12

Bảng 11-G ghi path tương đối trong release, path bền vững theo storage hiện hành, checksum/version/status và consumer. Thành viên tiếp theo chọn đúng manifest release ID, xác minh rồi đọc bảng/hình, không dựa vào RAM của phiên trước. Canonical là lối vào hiện hành, không thay nội dung release cũ.

Chỉ kết quả report_ready chính thức dùng viết báo cáo; bản fixture phục vụ kiểm thử logic. Notebook 12 được hoàn thiện ở giai đoạn 14, không tự coi summary skeleton đã nghiệm thu."""),
        """
handover = []
for category in ["tables","figures","models","predictions","metadata"]:
    for key,item in manifest[category].items():
        handover.append({"Nhóm":category,"Artifact":key,"Relative path":item["path"],"Persistent path":str(release_manifest_path.parent/item["path"]),"SHA256":item["sha256"],"Version":manifest["release_id"],"Trạng thái":manifest["status"],"Consumer":"12_final_results_summary.ipynb"})
display(pd.DataFrame(handover))
finalization_artifacts = {"release_manifest":release_manifest_path,"final_results_manifest":paths["manifests"]/"final_results_manifest.json","figure_manifest":release_manifest_path.parent/"figure_manifest.json"}
"""
    ]
)


# 12_final_results_summary.ipynb
summary_sections = [
    ('Tóm tắt dữ liệu', 'Release phân tích nguồn và population nào?',
     'Đọc source inventory, cohort và cohort ledger đã khóa. N dòng, trận, người chơi khác nhau; không suy số người từ số dòng.',
     'Đối chiếu source/version, mode, khoảng thời gian và counts theo split; unknown/null là chưa có evidence, không bằng 0.',
     'Full nghĩa toàn cohort hợp lệ của từng task; nguồn cũ hoặc scope fixture không đại diện toàn PUBG.'),
    ('Chất lượng dữ liệu', 'Missing, exclusions, join/roster và chronology có evidence nào?',
     'Chỉ đọc audit selected. Flags có thể chồng lặp; removal cascade mới là số loại tuần tự. Structural missing khác parse/error/unavailable.',
     'Đọc tử số/mẫu số, coverage và status trước tỷ lệ. not_in_release không có nghĩa không có lỗi; thiếu audit hiện công khai.',
     'Checksum đúng không chứng minh DQ tốt. Không tải raw hoặc tính lại audit để lấp chỗ trống.'),
    ('Kết quả RQ1', 'Hành vi liên hệ survival/placement trong mode và scope nào?',
     'Đọc Pearson/Spearman/N/status/primary validity đã tính. Pearson đo liên hệ tuyến tính; Spearman đo liên hệ đơn điệu theo thứ hạng.',
     'Giữ dấu hệ số; so cùng target/mode/N. NA do constant/insufficient không là hệ số 0; p nhỏ không thay effect size.',
     'Target-derived và phase-survival coupling chỉ diagnostic; association không nhân quả, chưa có CI nếu producer chưa tính.'),
    ('Kết quả RQ2', 'Những profile hành vi và độ ổn định C1-C5 được quan sát ra sao?',
     'Đọc centers/sizes/retention/K/robustness/C5 của KMeans đã khóa. Standardized center là theo scaler fit; outcome chỉ dùng post-hoc sau assignment.',
     'Cluster ID cục bộ trong từng mode; không so cluster0 Solo với cluster0 Duo. ARI đo mức nhất quán assignments, không đo chiến thuật tốt.',
     'Duration proxy, representation, K và minimum games ảnh hưởng profile; diagnostics sample không là full clustering hoặc heldout generalization.'),
    ('RQ3: thời gian sống sót', 'S1/S2 so với train mean/median đạt các số đo nào?',
     'Đọc micro/match-aware metric và feature/cohort records. MAE/RMSE là sai số cùng đơn vị target; R2 không phải accuracy.',
     'So cùng population/split/recipe. Đơn vị time pending không tự gọi giây; R2 undefined có reason, không gán 0.',
     'S1 hồi cứu sau trận; S2 chỉ future claim theo chronology/availability đã khóa. Grade C phải hiện blocked, không có score giả.'),
    ('RQ3: thứ hạng chuẩn hóa', 'P1/P2/P3 và baselines được đánh giá trong scope nào?',
     'Normalized placement trong [0,1], 1 là đầu, 0 là cuối; target đội lặp trên player rows. Đọc micro/match/team-aware và N riêng.',
     'P1 có survival trực tiếp; P2 bỏ cột đó nhưng có thể còn survival-derived descendants theo D02. Không gọi P2 độc lập mọi thông tin survival.',
     'P1/P2 là hồi cứu, không dự đoán trước trận. P3 conditional Grade A/B; team dependence không biến mất khi N player lớn.'),
    ('Đóng góp Combat Timing T0/T1', 'Thêm timing thay đổi sai số trên cùng cohort thế nào?',
     'Đọc paired comparisons T1-T0, same rows/split/model/preprocessing và coverage đã khóa. Không bootstrap lại hoặc chọn estimator từ test.',
     'Delta MAE/RMSE âm nghĩa candidate sai số thấp hơn; delta R2 dương khác ý nghĩa. CI chứa0 chưa chứng minh chiều cải thiện.',
     'Placement neo P2; survival nếu đăng ký chỉ timing subset an toàn D01. Missing event có thể đổi population, cần đọc coverage.'),
    ('Loại nhóm đặc trưng và importance', 'Bỏ Combat/Movement/Support/Timing thay đổi kết quả ra sao?',
     'Đọc ablation và importance đã khóa. Removal gồm raw/derived descendants/indicators; không chạy selection mới. Native/permutation importance có ý nghĩa khác nhau.',
     'Candidate là nhánh đã bỏ nhóm, reference là full; delta và CI theo cùng recipe. N và feature list cho thấy removal thực tế.',
     'Importance/correlation không chứng minh causal. Collinearity khiến importance chia sẻ giữa biến; group ablation là evidence nhóm.'),
    ('Phân tích sai số', 'Mode/history depth/target regions nào có sai số và coverage đáng chú ý?',
     'Đọc slices/residual summaries/bins đã đăng ký trước test. Residual=y-prediction; MAE/RMSE và signed residual không đồng nghĩa.',
     'Đọc n_observations/n_matches/coverage/status/unit; low-N/empty/outside bins phải hiện reason, không xếp hạng chắc chắn.',
     'Không chọn lại bins từ test hoặc suy metric thiếu. Slice population khác nhau không phải so sánh nhân quả giữa mode.'),
    ('Độ bất định', 'CI được tính bằng resampling unit, seed và budget nào?',
     'Đọc saved comparisons/bootstrap receipts và hình đã khóa. Match paired bootstrap dùng cùng match indices có lặp cho hai nhánh; CI percentile95%.',
     'Đối chiếu confidence, valid replicates, seed, N và reason. N mô phỏng bootstrap không phải N độc lập tăng thêm.',
     'CI thiếu giữ null/reason, không tự vẽ mới. Match bootstrap chưa giải quyết hoàn toàn player lặp xuyên trận; time/compute budgets chưa là peak proof.'),
    ('Phát hiện chính có truy nguồn', 'Mỗi phát biểu có số đo, scope, N, run và bảng nguồn nào?',
     'Chép giá trị từ summary rows đã khóa thành phát biểu trung tính, không tính metric mới hoặc chọn overall winner. Findings đọc mọi summary chunk, không chọn từ preview100dòng.',
     'Mỗi dòng gồm số đo, CI hoặc cảnh báo thiếu, mode/population, run, SHA và source table; mở bảng nguồn trước khi đưa vào báo cáo.',
     'Fixture findings không là kết quả PUBG. Không dùng từ gây ra/giúp thắng; effect không đồng nghĩa mức độ tác động nhân quả.'),
    ('Hạn chế và ghi chú bàn giao', 'Những exclusions, giới hạn và quyết định còn mở nào phải giữ khi viết báo cáo?',
     'Đọc required matrix locked: blocked/resource_limited/failed/reason, hình diagnostic và prior test exposure. Không dùng trạng thái notebook latest để thay lịch sử release.',
     'Không giấu S2/P3 Grade C hoặc optional failures. unknown exposure không đồng nghĩa chưa từng xem test; report_ready không phải chứng nhận mọi kết luận đúng.',
     'Dữ liệu quan sát/hồi cứu; identity name không bất biến; event mismatch, proxy duration, chronology granularity/ties, repeated teams/players, K sensitivity, dataset age và unobserved gameplay. Colab/GPU/Drive/full-data thật chưa chứng minh từ fixture.'),
]
summary_cells = [
    ('markdown', '''### 0. Bối cảnh, mục tiêu và kiểm soát chỉ đọc

Notebook này nối RQ-phương pháp-kết quả-hạn chế để nhóm viết báo cáo từ đúng một release đã khóa. Nó không chạy raw, download, build, train, chọn model hoặc sinh metric/hình mới. Đầu vào là `PUBG_SUMMARY_MANIFEST`; điền path snapshot cụ thể hoặc canonical cụ thể. Không scan latest.

Bootstrap chỉ mount Drive nếu cần và chuẩn bị imports trong RAM; không tạo thư mục, giải nén bundle, sửa config, cài packages hoặc ghi checkpoint. Cần đồng bộ source hiện hành/dependencies từ trước. Không cần raw/processed hoặc RAM phiên trước. Một notebook khác đang running/stale không chặn snapshot hợp lệ.

Hai kiểm tra khác nhau: integrity đối chiếu bytes/SHA/schema từng file; completeness đối chiếu required tasks/selected executions và conditional exceptions. Legacy integrity inventory không phải release hoàn chỉnh. Mọi lỗi phải dừng trước báo cáo, không sửa hash để ép pass.

Fixture chỉ được mở khi `PUBG_SUMMARY_ALLOW_FIXTURE=True`; hiển thị nhãn kiểm thử và không biến hình fixture thành report-ready. N artifact khác N dòng/người/trận. Bảng xem giới hạn100dòng có disclosure, artifact lưu vẫn đầy đủ; không công bố player identifiers không cần thiết.'''),
    '''import pandas as pd
from IPython.display import display, Markdown
from src.evaluation.finalize import load_locked_release
from src.evaluation.summary import render_summary_section
release = load_locked_release(manifest_path, allow_fixture=PUBG_SUMMARY_ALLOW_FIXTURE)
display(Markdown("Kiểm thử logic, không phải kết quả PUBG chính thức." if release['fixture'] else "Đọc release report-ready đã khóa; không tạo run mới."))
display(pd.DataFrame(release['audit']))
display(pd.DataFrame(release['manifest']['required_matrix']))
display(pd.DataFrame([{'Thí nghiệm': key, 'Run đã xác minh': value} for key,value in release['manifest']['official_run_ids'].items()]))
summary_views = []'''
]
for number, (title, question, method, reading, limit) in enumerate(summary_sections, 1):
    summary_cells.extend([
        ('markdown', f'### {number}. {title}\n\nCâu hỏi: {question}\n\nInput/phương pháp: {method}\n\nCách đọc: {reading}\n\nKết luận và giới hạn: chỉ dùng số đo/source hiện ngay dưới; {limit}\n\nKiểm soát chất lượng: thiếu selected artifact hiện not_in_release/pending hoặc status/reason; không suy diễn số hay đọc file ngoài manifest.'),
        f'summary_views.append(render_summary_section(release, {number}))'
    ])
summary_cells.extend([
    ('markdown', '''### Bàn giao phiên bản đã đọc

Bảng dưới nối relative path, persistent path, checksum và release ID để thành viên tiếp theo mở đúng bản. Các file thuộc snapshot không bị ghi đè; canonical chỉ là lối vào đã chọn. Notebook không ghi handover/checkpoint mới. Sau khi lưu notebook có output bằng thao tác riêng, không gọi việc đó là chạy lại pipeline.

Tái huấn luyện vẫn cần raw/processed, môi trường và approvals tương thích; đọc release không cần chúng. Dừng tại báo cáo này; các kiểm tra G0/toàn pipeline và môi trường thật thuộc giai đoạn15/16, không tự chứng nhận từ summary.'''),
    '''display(pd.DataFrame([{**row, 'Persistent path': str(release['root']/row['path']),
    'Release': release['manifest']['release_id'], 'Consumer': 'Báo cáo nhóm, không chạy tiếp thí nghiệm'} for row in release['audit']]))
display(pd.DataFrame(summary_views))'''
])
create_notebook('12_final_results_summary.ipynb', '12 - Tổng hợp kết quả nghiên cứu chỉ đọc',
    'Đủ 12 phần từ manifest cụ thể; truy nguồn bảng/hình/run, giải thích và giới hạn; không tạo kết quả mới.', summary_cells)

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
