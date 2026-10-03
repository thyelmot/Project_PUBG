# Nghiên cứu khai phá dữ liệu PUBG

Cập nhật 03/10/2026, giai đoạn15. [Đặc tả v3.0](PUBG_RESEARCH_SPEC.md) là nguồn quyết định; [kế hoạch](PUBG_IMPLEMENTATION_PLAN.md) và [nhật ký](CHANGELOG_FIXES.md) lưu bằng chứng. Code/fixture không phải kết quả nghiên cứu. G0 chỉ công nhận khi đủ QA; G1-G5 production và giai đoạn16 còn chờ dữ liệu thật.

## I. Mục tiêu, phạm vi và cấu trúc

| Câu hỏi | Đơn vị | Kết quả đọc |
| --- | --- | --- |
| RQ1: hành vi liên hệ survival/placement thế nào? | Người chơi-trận | Pearson/Spearman, N, mode, primary/diagnostic |
| RQ2: những kiểu hành vi nào? | Hồ sơ người chơi-mode | C1-C5, centers/sizes, stability, outcome sau clustering |
| RQ3: dự đoán survival/placement? | Người chơi-trận hoặc history | Baseline mean/median, linear, S/P/T/ablation, lỗi và CI |

Combat Timing là phần mở rộng chính. Current-match là hồi cứu; history chỉ là dự đoán tương lai khi chronology/availability hợp lệ. Association không chứng minh nhân quả, R² không phải accuracy. Không thêm deep learning/ranking/spatial mining hoặc causal inference vào core.

```text
Project_PUBG/
  configs/       cấu hình và quyết định
  notebooks/     00-12, điều phối và trình bày
  src/           công thức, xử lý, huấn luyện, kiểm chứng
  tests/         fixture, leakage, gates và resume
  data/          raw, interim, processed
  artifacts/     checkpoints, manifests, models, experiments, logs
  reports/       tables và appendix
  figures/       theo paths["figures"] đã resolve
```

Tài liệu: [TEAM_DRIVE](TEAM_DRIVE.md), [hướng dẫn cell](NOTEBOOK_CELL_GUIDE.md), [RQ2](RQ2_RUN_GUIDE.md), [GPU](GPU_PER_MODE_GUIDE.md), [literature mapping](reports/appendix/literature_mapping.md). Literature/traceability không cho phép sao metric/ngưỡng từ L1/L2/L3.

## II. Chạy Colab nối tiếp và thứ tự notebook

Không chạy hoặc regenerate All-in-One. Mở từng notebook trong folder chung, chạy cấu hình, bootstrap, khởi tạo và các cell từ trên xuống; không bỏ qua cell đỏ. Một người ghi mỗi stage, các tab không chia sẻ RAM.

```python
PUBG_STORAGE_MODE = "drive"
PUBG_DRIVE_PROJECT_ROOT = "/content/drive/MyDrive/PUBG_Project/Project_PUBG"
PUBG_REQUIRE_EXISTING_PROJECT = True
PUBG_BATCH_ROWS = 50000
```

Chủ thư mục chia sẻ Editor; thành viên thêm shortcut chính thư mục vào My Drive. Cùng tên đường dẫn không chứng minh cùng Drive folder ID. Kiểm marker và đọc/ghi thực theo TEAM_DRIVE. Bootstrap không tạo project khác để che root sai. Đồng bộ source/config liên quan, giữ quyết định nhóm đã duyệt, khởi động lại runtime.

| Notebook | Trách nhiệm và điều kiện |
| --- | --- |
| 00 | Config/paths/packages/hardware/snapshot/checkpoint; chưa đảm bảo tài nguyên full |
| 01 | Public/local source, mọi shard, hash/schema/parse, typed Parquet; G1 |
| 02 | Cleaning/ledger/roster/identity/chronology, split match; G2 trước outcome EDA |
| 03 | Base features/target/dictionary/validation; player_match_base.parquet, không tự đạt G3 |
| 04 | Global count/sum/min, coverage/discrepancy, safe merge; RUN-04 chặn units/eligibility/threshold pending |
| 05 | Catalog A01-I03, tám nhóm EDA; train/validation để chọn, không tự chốt tham số |
| 06 | RQ1 allowlists, coefficients/N/mode, coupling và limitations |
| 07 | Development profiles/retention/stability/K, sau khóa fit full eligible descriptive per_mode; C1-C5/fitted objects |
| 08 | Chronology/availability/threshold/protocol, strict-past history hoặc blocked/pending; feasibility khác completed history |
| 09 | S/P baselines/candidates và T0/T1/ablation validation; nhóm duyệt G4 trước final test |
| 10 | Saved predictions/pairing, ablation/deltas/slices/importance/CI; không train lại |
| 11 | Explicit selection, required matrix, immutable release/final/figure manifests; integrity khác G5 |
| 12 | Chọn release cụ thể, 12 phần chỉ đọc, reasons/findings truy nguồn; không raw/train/new run |

GPU T4/cuML cho KMeans07 và OLS hỗ trợ09. NB10 đánh giá saved predictions, không cần GPU. Constants, Ward, DuckDB/EDA/evaluation CPU. Thiếu CUDA khi device=cuda phải dừng, không silent CPU fallback; fixture CPU chưa chứng minh speedup/GPU thật.

## III. Source, persistent storage và development/full

configs/data.yaml: source.archive_url/archive_sha256 hoặc source.agg_urls/kill_urls và checksums. Raw local có thể trỏ dữ liệu hiện hữu qua paths.yaml, không tải lại. Inventory khám phá mọi shard theo patterns. Downloader kiểm response/size/hash, từ chối HTML/login/quota giả ZIP/CSV; URL public không cấp quyền sửa Drive. Không coi mtime là download date hoặc units candidate là verified.

| Vai trò | Drive | Local/runtime |
| --- | --- | --- |
| Raw | PROJECT_ROOT/data/raw | paths["raw"], local có thể ../Data_PUBG |
| Interim/processed | PROJECT_ROOT/data/{interim,processed} | Paths đã resolve |
| Checkpoints/models/metrics/manifests | PROJECT_ROOT/artifacts | Paths đã resolve, không đoán từ raw_root |
| Tables/figures | PROJECT_ROOT/reports/tables và root hình cấu hình | paths["tables"], paths["figures"] |
| DuckDB spill/temp | Runtime /content/temp | temp_dir của phiên |

runtime.mode=development dùng fixture nhỏ/root riêng/output riêng; sample là alias lịch sử không chính thức. full xử lý đủ cohort hợp lệ đã khai báo, không tự chứng nhận G5. Cùng code/caller, mode không tự lấy mẫu/cắt shard. EDA/RQ1 development loại final test dù runtime=full. Full_descriptive_locked chỉ export sau design/G4 lock ở11, không dùng chọn lại.

Reset mất RAM/temp/model chưa publish; Drive giữ artifacts đã đóng/đọc lại/commit, không bảo đảm file dở. Disk usage đo filesystem/VM, không phải quota Drive. Cộng tác qua shortcut chỉ tiếp tục khi có runtime hợp lệ, không dùng tài khoản khác để vượt giới hạn dịch vụ.

## IV. Thay parameter và giới hạn nghiên cứu

| Muốn thay | File config | Key | Notebook cần chạy lại |
| --- | --- | --- | --- |
| Nguồn/schema | data.yaml, schema.yaml | source.*, discovery.*, schema/aliases/units | 01 rồi02-12, đối soát raw riêng |
| Storage/root | paths.yaml và cell | active_environment, environments.*, PUBG_DRIVE_PROJECT_ROOT | Bootstrap/setup; chuyển và verify artifacts trước bàn giao |
| RAM/temp/batch | runtime.yaml và cell | duckdb.*, chunk_size, PUBG_BATCH_ROWS | Stage tương ứng, giữ mọi row/phép tính |
| Mode mapping | preprocessing.yaml, rq2.yaml | modes.team_size_mapping, party_size_mapping | 02-12 theo dependency |
| Chronology/split | preprocessing.yaml, rq3.yaml | chronology.grade_assignment, split.* | 02 rồi các analyses/models phụ thuộc; không resplit để xóa test exposure |
| Base/timing | features.yaml và src/features | combat_timing.*, groups/tasks/formula | 03 hoặc04 rồi05-12; signatures phải đổi |
| RQ2 min_games/K | rq2.yaml | minimum_games_threshold, n_clusters_by_mode, selection_reason | Diagnostics/final07 rồi11-12; không refit nhánh độc lập compatible |
| RQ2 transform/device | rq2.yaml | scaler, log_transform_features/reason, device | 07 diagnostics/decision/final rồi11-12 |
| History | rq3.yaml | minimum_history_threshold, historical.* | 08 diagnostics/build rồi09-12 |
| Features/model/backend | features.yaml, models.yaml, rq3.yaml | tasks.*, transforms.*, linear.*, nonlinear_candidates.*, device | 09 development/selection, G4 mới rồi10-12 |
| Bootstrap/bins | rq3.yaml và G4 decision | evaluation.bootstrap.*, error_bins | Duyệt trước test, G4/10 rồi11-12 |
| Caption/style | eda.yaml, generator/helpers | catalog/plot policy | Hình/manifest/consumer tương ứng, không refit chỉ để vẽ |

Các ngưỡng min_games/min_history, K, split, units/chronology/availability, log/outlier, final features/model/params/bins chỉ thay sau evidence đúng stage. Null dừng với diagnostics/reason; không K4/min_games5 ngầm. per_mode/batch50000/storage đã được chốt. Mọi YAML option phải kiểm caller; không suy có key là đã hỗ trợ.

Không tự đổi RQ/target/cohort/split/estimator/metric/protocol; không bỏ extreme hợp lệ để đẹp score, sample/fallback OLS sang SGD hoặc KMeans sang MiniBatch trong cùng run. SGD recipe riêng qua RAM gate hiện stream matrix dataframe, chưa raw/disk out-of-core. Median/RobustScaler streaming và XGBoost backend chưa hỗ trợ.

Leakage rules: match không giao split; transforms fit train; outcomes không input clustering/chọn K/threshold; S1 cấm survival descendants kể cả phase-duration proxy; RQ1 target-derived chỉ diagnostic; P1/P2 chỉ khác direct survival và công bố coupling còn lại. Grade B history loại cùng ngày, Grade A loại tie block/availability chưa sẵn sàng. hist_kd chưa confirmed nếu deaths chưa verified. Ablation bỏ descendants/indicators.

## V. Checkpoint, stale, ghi đè và troubleshooting

artifacts/checkpoints/checkpoint_manifest.json: chỉ reuse completed với signature/checksum/schema/count tương thích. Running/failed/blocked không completed; stale nghĩa input/config/code/split/backend liên quan đổi. Chạy lại producer/downstream cần thiết, không đổi filename để bypass. Source hash đổi có thể invalidate nhiều hơn bảng tối thiểu ở trên.

Canonical dùng staging/validate/publish/read-back/commit, không sinh (1)/(2). Locked releases ở artifacts/manifests/releases/<release_id>/ có version có chủ đích, giữ riêng. Drive upload phải cập nhật đúng file ID/version, cùng tên chưa chắc ghi đè. Sau notebook thành công lưu bản có output và thay đúng Drive/local; không thay bản tốt bằng notebook lỗi. Output notebook không thay processed/model artifacts.

| Lỗi | Cần làm |
| --- | --- |
| RAM/VRAM | Resource status, projection/SQL/spill/batch cùng phép tính hoặc runtime phù hợp; không cắt cohort/fallback model |
| Disk/quota | Giữ committed checkpoint, báo stage/cell/path; chỉ dọn file được phép đã kiểm, không xóa raw |
| Reset | Mount đúng root, cấu hình/bootstrap/init rồi notebook dở; reuse compatible shard/mode/experiment, fit dở khởi động lại |
| HTML/403/checksum | Kiểm public source/quota/hash/backup; không bỏ checksum |
| Stale/missing | Kiểm input/config/code/checkpoint, chạy producer cần thiết; file tồn tại chưa đủ |
| Null | Đọc diagnostics, nhóm duyệt evidence/reason/receipt đúng gate, không sao fixture choice |
| Schema/alias/parse | Đọc schema/parse reports, sửa contract có căn cứ, không ép kiểu che lỗi |
| Chronology/history | Grade C S2/P3 blocked/null, current task có điều kiện riêng; A/B cần availability/protocol/threshold |
| Join/coverage | Event ledger/unmatched/discrepancy, không missing-event=no-kill hoặc clip timing |

## VI. Summary, kiểm thử local và generator

PUBG_SUMMARY_MANIFEST chọn snapshot cụ thể artifacts/manifests/releases/<release_id>/final_results_manifest.json hoặc canonical cụ thể và ghi release ID; không latest. Source/dependencies chuẩn bị trước; local có PUBG_SUMMARY_CODE_ROOT. Summary mount/import/read, không mkdir/install/unpack/download/pickle/current config/checkpoint/fit. Đủ12phần, reasons/null/unknown/not_in_release, figures official report_ready và findings source/SHA/run/N/CI. Fixture cần PUBG_SUMMARY_ALLOW_FIXTURE=True, không phải kết quả PUBG.

```bash
cd Project_PUBG
python -m pip install -r requirements.txt
python scripts/run_phase15_tests.py
python src/utils/generate_notebooks.py --only 03_build_player_match.ipynb
```

Runner loại hai method thực thi All-in-One, không dùng toàn suite chưa lọc. GPU thật mặc định skip; mount mock/fault injection không chứng minh Drive thật. Log/report phase15 ở reports/appendix; số test không thay ba mặt logic/tích hợp/khả năng đọc. NB00 lưu môi trường thực; package lock Colab chỉ sau setup thành công, không giả snapshot Windows là Colab.

NB05 lưu `eda_figure_catalog.csv` và `eda_catalog_status.csv` để tra scope/N/n/seed/quy tắc/bảng nguồn. `eda_visualization_sample.csv` là mẫu dùng vẽ, không chứa tên người chơi; hai bảng phân bố số trận/người và số đội/trận cho phép đối chiếu histogram mà không xuất danh sách định danh. Thống kê toàn scope không được thay bằng mẫu này. NB07 lưu chi tiết lấy mẫu theo mode/K và theo nhánh trong `rq2_figure_catalog.csv`, cùng CSV diagnostics/robustness gốc.

Generator dùng --only từng file bị ảnh hưởng, backup bản có output trước sinh; không sửa tay riêng ipynb. Bundle source/config/tests/docs không raw/secrets/outputs, không tự overwrite project hiện hữu. Drive phải đồng bộ source/config trước runtime mới. Không commit raw/token/cookie/artifact lớn hoặc công bố player names không cần thiết. Chưa full dataset/peak-memory/GPU/Drive/quota thật; giai đoạn16 giữ hoãn.
