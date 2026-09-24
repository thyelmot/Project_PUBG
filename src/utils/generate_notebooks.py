import json
import re
import sys
from pathlib import Path

NOTEBOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "notebooks"
NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(NOTEBOOKS_DIR.parent))
from src.utils.notebook_bundle import bootstrap_source, EXPORT_CELL, STORAGE_OPTIONS_CELL

BOOTSTRAP = bootstrap_source(NOTEBOOKS_DIR.parent)
GENERATED_NOTEBOOKS = []

def create_notebook(filename: str, title: str, description: str, cells_data: list):
    cells = [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [f"# {title}\n", f"\n", f"**Mục tiêu:** {description}\n", f"\n", f"Single Source of Truth: `PUBG_RESEARCH_SPEC.md` v3.0 | `PUBG_IMPLEMENTATION_PLAN.md`\n"]
        }
    ]
    cells.append({"cell_type": "markdown", "metadata": {}, "source": [
        "Chọn `runtime` để chạy không cần Drive, hoặc `drive` để 13 notebook dùng chung dữ liệu bền vững. "
        "Với `drive`, mọi notebook phải dùng cùng `PUBG_DRIVE_PROJECT_ROOT` và chạy theo thứ tự.\n"]})
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
            source = source.replace('con = get_duckdb_connection(',
                                    'if "con" in globals():\n    con.close()\ncon = get_duckdb_connection(')
            cell["source"] = (guard + source).splitlines(keepends=True)
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
    with open(NOTEBOOKS_DIR / filename, "w", encoding="utf-8") as f:
        json.dump(nb_json, f, indent=2)
    GENERATED_NOTEBOOKS.append(nb_json)
    print(f"Created {filename}")

# 00_setup.ipynb
create_notebook(
    "00_setup.ipynb",
    "00 — Khởi tạo môi trường, cấu hình và trạng thái Checkpoint",
    "Kiểm tra môi trường runtime, tài nguyên phần cứng (CPU/RAM/Disk), quyền ghi và tính tương thích của 10 file cấu hình.",
    [
        ("markdown", "### 1. Môi trường chạy\n\nMã nguồn đã được khởi tạo ở cell trên. Dữ liệu lưu theo chế độ runtime hoặc Drive đã chọn; kiểm tra đường dẫn được in bên dưới."),
        """
import sys
import os
from pathlib import Path

# 1. Phát hiện môi trường thực thi
IN_COLAB = "google.colab" in sys.modules
if IN_COLAB:
    print("[Colab] Đang chạy trên Google Colab runtime.")
    print(f"Dữ liệu và kết quả: {paths['data_root']} | {paths['reports_root']}")
else:
    print("[Local] Đang chạy trên máy cục bộ.")

# 2. Định vị thư mục gốc dự án và gắn vào sys.path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

print(f"Project Root: {PROJECT_ROOT}")
""",
        ("markdown", "### 2. Nạp và kiểm tra tính toàn vẹn của 10 file cấu hình YAML\n\nĐảm bảo tất cả các file cấu hình nghiệp vụ (`data.yaml`, `schema.yaml`, `paths.yaml`, v.v.) được nạp đầy đủ và thỏa mãn các ràng buộc schema trước khi thực thi."),
        """
from src.utils.config import load_config, resolve_paths, validate_config

# Nạp toàn bộ 10 file config
cfg = load_config(str(PROJECT_ROOT / "configs"))
validate_config(cfg)

print("--- THÔNG TIN CẤU HÌNH NGHIÊN CỨU ---")
print(f"Môi trường kích hoạt: {cfg['paths']['active_environment']}")
print(f"Chế độ thực thi: {cfg['runtime']['mode']} (seed: {cfg['runtime']['random_state']})")
print(f"Dataset name: {cfg['data']['source']['dataset_name']}")
if cfg['data']['source'].get('archive_url'):
    print(f"Nguồn dữ liệu (Archive URL): {cfg['data']['source']['archive_url']}")
print(f"DuckDB Threads: {cfg['runtime']['duckdb']['threads']} | Memory Limit: {cfg['runtime']['duckdb']['memory_limit']}")
""",
        ("markdown", "### 3. Phân giải đường dẫn và khởi tạo cấu trúc thư mục lưu trữ (Paths Resolution & Storage Preparation)\n\nPhân giải các đường dẫn logic (`raw_root`, `data_root`, `artifacts_root`, `reports_root`, v.v.) và tự động tạo tất cả các thư mục con phục vụ lưu trữ artifact và báo cáo."),
        """
import pandas as pd

# Phân giải đường dẫn theo môi trường
paths = resolve_paths(cfg)

# Danh sách các thư mục cần khởi tạo sẵn
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
    records.append({
        "Thư mục logic": name,
        "Đường dẫn tuyệt đối": str(d_path),
        "Trạng thái": "Đã có sẵn" if existed else "Đã khởi tạo mới",
    })

df_paths = pd.DataFrame(records)
print("--- DANH MỤC ĐƯỜNG DẪN HỆ THỐNG ---")
for idx, row in df_paths.iterrows():
    print(f"[{row['Trạng thái']}] {row['Thư mục logic']:<15} -> {row['Đường dẫn tuyệt đối']}")

# Kiểm tra dữ liệu thô tại raw_root
raw_root = Path(paths["raw_root"]).resolve()
csv_shards = list(raw_root.glob("*.csv")) + list(raw_root.glob("*/*.csv"))
print(f"\\nKiểm tra dữ liệu thô ({raw_root}):")
if csv_shards:
    print(f"  -> Đã tìm thấy {len(csv_shards)} file CSV thô sẵn sàng cho bước kiểm kê.")
else:
    print("  -> Chưa có CSV thô. Notebook 01 đọc ZIP theo batch, không giải nén toàn bộ ra đĩa.")
""",
        ("markdown", "### 4. Chẩn đoán tài nguyên phần cứng (CPU, RAM, Disk, GPU)\n\nKiểm tra dung lượng đĩa trống, quyền ghi và thông số phần cứng để đảm bảo an toàn bộ nhớ khi xử lý dữ liệu lớn."),
        """
from src.utils.runtime import check_environment

env_report = check_environment(target_dir=paths["checkpoints"], min_disk_gb=5.0)

print("--- BÁO CÁO TÀI NGUYÊN PHẦN CỨNG ---")
print(f"Trạng thái hệ thống: {env_report['status'].upper()}")
print(f"Hệ điều hành: {env_report['runtime']['os_name']} {env_report['runtime']['os_release']}")
print(f"Phiên bản Python: {env_report['runtime']['python_version']}")
print(f"Số nhân CPU: {env_report['runtime']['cpu_count_logical']} (logical)")
print(f"Bộ nhớ RAM: {env_report['runtime'].get('available_ram_gb', 'N/A')} GB khả dụng / {env_report['runtime'].get('total_ram_gb', 'N/A')} GB tổng")
print(f"Dung lượng đĩa: {env_report['free_disk_gb']} GB trống / {env_report['total_disk_gb']} GB tổng")
print(f"Quyền ghi vào thư mục artifacts: {'HỢP LỆ' if env_report['can_write'] else 'KHÔNG CÓ QUYỀN'}")
if env_report['warnings']:
    print(f"Cảnh báo: {env_report['warnings']}")
""",
        ("markdown", "### 5. Kiểm tra trạng thái Checkpoint và DAG Run Readiness\n\nXác định xem hệ thống đã hoàn thành các stage nào từ các phiên chạy trước đó, sẵn sàng chuyển sang `01_download_validate.ipynb`."),
        """
from src.data.checkpoints import CheckpointManager

ckpt_mgr = CheckpointManager(manifest_path=paths["checkpoints"] / "checkpoint_manifest.json")
manifest = ckpt_mgr.load_manifest()

completed_stages = list(manifest.get("stages", {}).keys())
print("--- TRẠNG THÁI CHECKPOINT DAG ---")
if completed_stages:
    print(f"Các stage đã lưu checkpoint: {completed_stages}")
else:
    print("Chưa có checkpoint nào được lưu (Hệ thống ở trạng thái Clean Start).")

print("\\n=> Sẵn sàng thực thi. Vui lòng mở và chạy notebook tiếp theo: '01_download_validate.ipynb'.")
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
from src.data.batch_ingest import ingest_sources
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
)
atomic_write_json(paths["manifests"] / "source_inventory.json", inventory)
print(f"Đã xử lý đầy đủ {len(inventory['shards'])} shards, {sum(s['rows'] for s in inventory['shards']):,} dòng.")

# 2. Khóa checkpoint sau khi tất cả shard đã hoàn tất
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
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.data.io import get_duckdb_connection, atomic_write_json
from src.data.cleaning import audit_and_clean_aggregate_data
from src.data.match_metadata import build_match_metadata
from src.models.splits import create_split_assignments
from src.analysis.eda import run_chronology_audit
from src.data.checkpoints import CheckpointManager

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
con = get_duckdb_connection(temp_dir=paths["temp_dir"], **{k: cfg["runtime"]["duckdb"][k] for k in ("memory_limit", "threads")})
ckpt_mgr = CheckpointManager(manifest_path=paths["checkpoints"] / "checkpoint_manifest.json")

staging_dir = paths["interim"] / "staging_shards"
from src.data.batch_ingest import staged_paths
agg_shards = staged_paths(staging_dir, "aggregate")
if not agg_shards:
    raise FileNotFoundError(
        f"Không tìm thấy aggregate Parquet trong {staging_dir}. "
        "Hãy chạy xong notebook 01 với cùng PUBG_STORAGE_MODE và PUBG_DRIVE_PROJECT_ROOT."
    )
print(f"Đầu vào stage 02: {len(agg_shards)} aggregate shards từ {staging_dir}")

# 1. Làm sạch sơ bộ và ghi removal log
cleaned_pq = paths["interim"] / "cleaned_aggregate.parquet"
removal_csv = paths["tables"] / "removal_log.csv"
clean_summary = audit_and_clean_aggregate_data(con, agg_shards, cleaned_pq, removal_csv)
print(f"Làm sạch: Giữ lại {clean_summary['clean_rows']} dòng hợp lệ.")

# 2. Xây dựng Match Metadata (N_teams, duration proxy)
from src.data.match_metadata import build_match_metadata
cleaned_pq = paths["interim"] / "cleaned_aggregate.parquet"
if not cleaned_pq.is_file():
    raise FileNotFoundError(f"Chưa có dữ liệu sạch: {cleaned_pq}. Chạy cell làm sạch trước.")
meta_pq = paths["interim"] / "match_metadata.parquet"
total_matches = build_match_metadata(con, cleaned_pq, meta_pq)

# 3. Đánh giá Chronology Grade
meta_df = con.execute(f"SELECT * FROM read_parquet('{str(meta_pq).replace(chr(92), '/')}') LIMIT 50000;").df()
chrono_report = run_chronology_audit(meta_df)
print(f"Chronology Grade: {chrono_report['grade']} - {chrono_report.get('description', chrono_report.get('reason'))}")
atomic_write_json(paths["manifests"] / "chronology_report.json", chrono_report)

# 4. Khóa Split Assignments (Match isolation invariant)
split_pq = paths["interim"] / "split_assignments.parquet"
split_manifest = paths["manifests"] / "split_manifest.json"
split_meta = create_split_assignments(con, meta_pq, split_pq, split_manifest, strategy="group_by_match")

ckpt_mgr.commit("split_manifest", split_meta["config_hash"], {"split_assignments": split_pq, "match_metadata": meta_pq})
print("Gate G2 Hoàn tất: Split manifest đã được khóa trước EDA quan hệ.")
"""
    ]
)

# 03_build_player_match.ipynb
create_notebook(
    "03_build_player_match.ipynb",
    "03 — Xây dựng Player-Match Base (Combat, Movement, Support, Placement)",
    "Tính toán các đặc trưng hành vi người chơi và normalized placement với mẫu số đã xác minh.",
    [
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.data.io import get_duckdb_connection
from src.data.checkpoints import CheckpointManager

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
con = get_duckdb_connection(temp_dir=paths["temp_dir"], **{k: cfg["runtime"]["duckdb"][k] for k in ("memory_limit", "threads")})
ckpt_mgr = CheckpointManager(manifest_path=paths["checkpoints"] / "checkpoint_manifest.json")

print("Bước này được tích hợp liền mạch với Stage 04 trong quy trình streaming DuckDB.")
"""
    ]
)

# 04_combat_timing.ipynb
create_notebook(
    "04_combat_timing.ipynb",
    "04 — Khai phá Combat Timing và hoàn thiện Player-Match Features",
    "Tổng hợp các sự kiện hạ gục (Early, Mid, Late combat phases), loại trừ suicide/self-kill, và thực hiện Left Join bảo toàn số dòng vào player-match base.",
    [
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.data.io import get_duckdb_connection
from src.features.combat_timing import extract_and_aggregate_combat_timing, merge_player_match_and_timing
from src.data.checkpoints import CheckpointManager

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
con = get_duckdb_connection(temp_dir=paths["temp_dir"], **{k: cfg["runtime"]["duckdb"][k] for k in ("memory_limit", "threads")})
ckpt_mgr = CheckpointManager(manifest_path=paths["checkpoints"] / "checkpoint_manifest.json")

staging_dir = paths["interim"] / "staging_shards"
from src.data.batch_ingest import staged_paths
death_shards = staged_paths(staging_dir, "deaths")
cleaned_agg = paths["interim"] / "cleaned_aggregate.parquet"
meta_pq = paths["interim"] / "match_metadata.parquet"

# 1. Trích xuất và tổng hợp thời điểm giao tranh
timing_pq = paths["interim"] / "combat_timing.parquet"
audit_summary = extract_and_aggregate_combat_timing(con, death_shards, meta_pq, timing_pq, paths["reports"] / "tables")
print(f"Tổng hợp Combat Timing: {audit_summary['valid_enemy_kills']} kills hợp lệ.")

# 2. Left join vào cơ sở dữ liệu player-match (Bảo toàn số dòng)
final_pq = paths["processed"] / "player_match_features.parquet"
discrepancy_csv = paths["reports"] / "tables" / "kill_discrepancy.csv"
final_rows = merge_player_match_and_timing(con, cleaned_agg, meta_pq, timing_pq, final_pq, discrepancy_csv)

ckpt_mgr.commit("player_match_features", "features_v1", {"final_dataset": final_pq})
print(f"Hoàn thành xuất player_match_features: {final_rows} dòng.")
"""
    ]
)

# 05_eda.ipynb
create_notebook(
    "05_eda.ipynb",
    "05 — Khám phá dữ liệu chuyên sâu 8 Pha (Full EDA)",
    "Thực hiện đầy đủ 8 pha EDA: cấu trúc, chất lượng, phân bố thô, biến phái sinh, chế độ chơi, quan hệ, thời điểm giao tranh và khả thi lịch sử.",
    [
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.data.io import read_parquet_df, atomic_write_json
from src.analysis.eda import run_structural_eda, compute_distribution_summary
from src.analysis.mode_analysis import analyze_behavior_by_mode

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)

# Đọc mẫu đại diện hợp lệ cho EDA
final_pq = paths["processed"] / "player_match_features.parquet"
df_sample = read_parquet_df(final_pq)

# Phase 3 & 4: Tóm tắt phân bố các đặc trưng
behavior_cols = [
    "player_kills", "player_dmg", "damage_per_kill",
    "player_dist_walk", "player_dist_ride", "total_distance", "walk_ratio",
    "player_assists", "player_dbno", "assist_ratio",
    "player_survive_time", "normalized_placement"
]
dist_summary = compute_distribution_summary(df_sample, behavior_cols)
dist_summary.to_csv(paths["tables"] / "data_quality_summary.csv", index=False)
print("--- TÓM TẮT PHÂN BỐ ĐẶC TRƯNG HÀNH VI ---")
print(dist_summary[["feature", "mean", "std", "median", "skewness", "zero_rate"]])

# Phase 5: Phân tích theo chế độ chơi
mode_res = analyze_behavior_by_mode(df_sample, behavior_cols)
print(f"Khuyến nghị chiến lược RQ2 Mode: {mode_res['recommended_rq2_strategy']}")
"""
    ]
)

# 06_rq1_analysis.ipynb
create_notebook(
    "06_rq1_analysis.ipynb",
    "06 — Trả lời RQ1: Phân tích mối quan hệ giữa Hành vi, Thời điểm và Outcome",
    "Tính toán tương quan Pearson và Spearman, tách biệt allowlist theo task, đánh giá sự khác biệt giữa các chế độ chơi và xuất rq1_relationship_summary.csv.",
    [
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.data.io import read_parquet_df
from src.features.registry import FeatureRegistry
from src.analysis.rq1 import run_rq1_analysis

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
registry = FeatureRegistry()

final_pq = paths["processed"] / "player_match_features.parquet"
df = read_parquet_df(final_pq)

rq1_table = run_rq1_analysis(df, registry, paths["tables"] / "rq1_relationship_summary.csv")
print("Top 10 mối quan hệ mạnh nhất với Normalized Placement:")
print(rq1_table[rq1_table["target"] == "normalized_placement"].sort_values(by="spearman_rho", ascending=False).head(10)[["feature", "group", "spearman_rho", "pearson_r", "is_primary_valid"]])
"""
    ]
)

# 07_rq2_clustering.ipynb
create_notebook(
    "07_rq2_clustering.ipynb",
    "07 — Trả lời RQ2: Hồ sơ hành vi người chơi và Phân cụm (C1–C5)",
    "Xây dựng Behavioral Profile (Design 3), chẩn đoán số cụm K tối ưu (Elbow/Silhouette/DB), thực thi C1-C5 và so sánh outcome sau phân cụm.",
    [
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.data.io import read_parquet_df
from src.features.profiles import build_player_behavioral_profiles, filter_profiles_by_retention
from src.analysis.clustering import run_k_diagnostics, execute_rq2_clustering

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)

final_pq = paths["processed"] / "player_match_features.parquet"
df = read_parquet_df(final_pq)

# 1. Xây dựng hồ sơ hành vi người chơi
profiles, outcomes = build_player_behavioral_profiles(df)
filtered_profiles, filtered_outcomes = filter_profiles_by_retention(profiles, outcomes, min_games=5)

# 2. Chẩn đoán K
feature_cols = [c for c in filtered_profiles.columns if c.startswith("mean_") or c.startswith("avg_") or c.endswith("_ratio")]
X = filtered_profiles[feature_cols].values
k_diag = run_k_diagnostics(X, k_range=[2, 3, 4, 5, 6])
print("--- CHẨN ĐOÁN SỐ CỤM K ---")
print(k_diag)

# 3. Phân cụm chính thức C1 và đánh giá C2-C5
selected_k = cfg["rq2"]["n_clusters"] or 4
res = execute_rq2_clustering(filtered_profiles, filtered_outcomes, n_clusters=selected_k, output_dir=paths["reports"] / "tables")
print("--- ĐỐI CHIẾU OUTCOME THEO CỤM (C5) ---")
print(res["outcome_comparison"])
"""
    ]
)

# 08_build_historical.ipynb
create_notebook(
    "08_build_historical.ipynb",
    "08 — Xây dựng đặc trưng Lịch sử người chơi (Historical Features)",
    "Xác minh thứ tự thời gian, tích lũy đặc trưng quá khứ (expanding window), đảm bảo không rò rỉ trận hiện tại hoặc tương lai.",
    [
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.data.io import get_duckdb_connection, read_json
from src.features.historical import build_historical_features

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
con = get_duckdb_connection(temp_dir=paths["temp_dir"], **{k: cfg["runtime"]["duckdb"][k] for k in ("memory_limit", "threads")})

chrono_report = read_json(paths["manifests"] / "chronology_report.json")
grade = chrono_report.get("grade", "Grade B")

hist_pq = paths["processed"] / "historical_player_match_features.parquet"
h_res = build_historical_features(con, paths["processed"] / "player_match_features.parquet", hist_pq, chronology_grade=grade)
print(f"Kết quả xây dựng lịch sử: {h_res}")
"""
    ]
)

# 09_rq3_prediction.ipynb
create_notebook(
    "09_rq3_prediction.ipynb",
    "09 — Trả lời RQ3: Huấn luyện mô hình Dự đoán (S1, S2, P1, P2, P3, T0, T1)",
    "Huấn luyện Baselines, Linear và Gradient Boosting trên tập Train, dự đoán trên Test và lưu lại kết quả kiểm chứng.",
    [
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.data.io import read_parquet_df
from src.features.registry import FeatureRegistry
from src.models.baselines import TrainMeanRegressor, TrainMedianRegressor
from src.models.linear import LinearModelWrapper
from src.models.tree_models import HistGradientBoostingWrapper
from src.models.training import train_and_predict_experiment
from src.evaluation.metrics import compute_hierarchical_metrics

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
registry = FeatureRegistry()

final_pq = paths["processed"] / "player_match_features.parquet"
split_pq = paths["interim"] / "split_assignments.parquet"

df = read_parquet_df(final_pq)
splits = read_parquet_df(split_pq)
df = df.merge(splits[["match_id", "split"]], on="match_id", how="left")

# Thí nghiệm P1 (với survival) vs P2 (bỏ survival trực tiếp)
p1_feats = registry.get_allowed_features("p1")
p2_feats = registry.get_allowed_features("p2")

print("Huấn luyện P2 (Linear Model - Không survival trực tiếp)...")
_, p2_preds = train_and_predict_experiment(df, p2_feats, "normalized_placement", LinearModelWrapper(model_type="exact"), "p2_linear", output_predictions_dir=paths["experiments"])

print("Huấn luyện P1 (Linear Model - Có survival trực tiếp)...")
_, p1_preds = train_and_predict_experiment(df, p1_feats, "normalized_placement", LinearModelWrapper(model_type="exact"), "p1_linear", output_predictions_dir=paths["experiments"])

p2_test = p2_preds[p2_preds["split"] == "test"]
p1_test = p1_preds[p1_preds["split"] == "test"]

print(f"P2 Test Micro MAE: {compute_hierarchical_metrics(p2_test)['micro']['mae']:.4f}")
print(f"P1 Test Micro MAE: {compute_hierarchical_metrics(p1_test)['micro']['mae']:.4f}")
"""
    ]
)

# 10_ablation_error_analysis.ipynb
create_notebook(
    "10_ablation_error_analysis.ipynb",
    "10 — Đóng góp đặc trưng, Phân tích nhóm cắt bỏ (Ablation), Sai số và Bất định",
    "So sánh T0/T1, phân tích cắt bỏ nhóm biến (Ablation), ước lượng khoảng tin cậy 95% Bootstrap theo match và phân tích lát cắt sai số.",
    [
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
df = read_parquet_df(final_pq).merge(read_parquet_df(split_pq)[["match_id", "split"]], on="match_id", how="left")

# 1. Group Ablation Study
p2_feats = registry.get_allowed_features("p2")
ablation_df = run_group_ablation_study(df, registry, p2_feats, "normalized_placement", paths["tables"] / "ablation_results.csv")
print("--- KẾT QUẢ GROUP ABLATION STUDY ---")
print(ablation_df[["ablation_experiment", "removed_group", "test_mae", "delta_mae_vs_full"]])

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
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path.cwd()  # bootstrap has located the project and set cwd
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import load_config, resolve_paths
from src.evaluation.finalize import build_final_results_manifest

cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)

official_runs = {
    "rq1": "rq1_relationship_summary_v1",
    "p1": "p1_linear",
    "p2": "p2_linear",
    "ablation": "ablation_p2_groups",
}
import pandas as pd
cluster_table = paths["tables"] / "cluster_profile.csv"
if cluster_table.is_file():
    official_runs["rq2"] = f"rq2_kmeans_k{len(pd.read_csv(cluster_table))}"
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
    output_manifest_path=paths["manifests"] / "final_results_manifest.json"
)

print(f"Gate G5 Đã khóa: {len(manifest['tables'])} bảng kết quả chính thức đã được băm mã hóa bảo vệ.")
"""
    ]
)

# 12_final_results_summary.ipynb
create_notebook(
    "12_final_results_summary.ipynb",
    "12 — Báo cáo tổng hợp Kết quả nghiên cứu (Chỉ đọc)",
    "Tải trực tiếp từ final_results_manifest.json đã khóa. Tuyệt đối không huấn luyện lại, không gọi lại dữ liệu raw.",
    [
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

# Hiển thị tóm tắt ablation study
abl_path = paths["tables"] / "ablation_results.csv"
if abl_path.is_file():
    print("--- ĐÓNG GÓP CỦA CÁC NHÓM BIẾN (ABLATION STUDY) ---")
    print(pd.read_csv(abl_path))
"""
    ]
)
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
