# Hướng dẫn chi tiết từng cell trong Project PUBG

## 1. Hai cách sử dụng notebook

Dự án có hai cách chạy cùng một pipeline:

- `00_setup.ipynb` đến `12_final_results_summary.ipynb`: 13 notebook theo từng giai đoạn. Cách này thuận tiện để phân công thành viên và kiểm tra từng bước, nhưng các notebook sau cần các tệp đầu ra của notebook trước trong cùng thư mục dự án/runtime.
- `PUBG_COLAB_ALL_IN_ONE.ipynb`: ghép nội dung của 13 notebook vào một notebook 54 cell. Đây là lựa chọn phù hợp nhất trên Colab vì toàn bộ biến và tệp tạm nằm trong cùng runtime. Cell 54 dùng để tải kết quả về trước khi runtime bị xóa.

Các cell Markdown chỉ mô tả mục tiêu hoặc chia phần; chúng không xử lý dữ liệu. Các cell Code mới tạo biến, đọc/ghi tệp hoặc chạy mô hình.

## 2. Cell bootstrap dùng chung

Cell code thứ 3 của mỗi notebook là cell bootstrap. Cell này dài vì chứa một tệp ZIP đã mã hóa Base64 gồm `src/`, `configs/`, `tests/`, `README.md` và `requirements.txt`.

Khi chạy, cell thực hiện lần lượt:

1. Nhận diện Colab qua module `google.colab` hoặc biến môi trường `COLAB_RELEASE_TAG`.
2. Tìm một thư mục dự án đã có sẵn bằng hai dấu hiệu `configs/data.yaml` và `src/utils/config.py`.
3. Nếu chưa có dự án, tạo `/content/Project_PUBG` trên Colab hoặc `./Project_PUBG` trên máy cục bộ, giải nén mã nguồn nhúng vào đó và chặn đường dẫn ZIP bất hợp lệ bằng `is_relative_to`.
4. Chuyển thư mục làm việc sang `PROJECT_ROOT` và thêm nó vào `sys.path` để Python import được package `src`.
5. Trên Colab, cài các thư viện trong `requirements.txt` đúng một lần. Có thể đặt `PUBG_INSTALL_DEPENDENCIES=False` trước khi chạy để bỏ qua việc cài.
6. Nạp cấu hình, phân giải toàn bộ đường dẫn, tạo các thư mục cần dùng và in nơi lưu dữ liệu/kết quả.

Cell này không mount Google Drive, không yêu cầu token và không chứa dữ liệu PUBG. Trên máy đã clone repository, nó dùng trực tiếp mã nguồn hiện có; trên Colab trống, nó tự bung bản mã nguồn nhúng.

## 3. `00_setup.ipynb` — khởi tạo môi trường

### Cell 1 — Markdown: tiêu đề và mục tiêu

Giới thiệu giai đoạn 00: kiểm tra runtime, tài nguyên, quyền ghi và cấu hình. Không tạo dữ liệu.

### Cell 2 — Markdown: hướng dẫn cách chạy

Giải thích notebook không dùng Drive và khuyến nghị dùng bản All-in-One trên Colab. Không tạo dữ liệu.

### Cell 3 — Code: bootstrap

Thực hiện toàn bộ quy trình bootstrap dùng chung ở mục 2. Kết quả quan trọng là các biến `PROJECT_ROOT`, `cfg`, `paths` và mã nguồn `src` sẵn sàng để dùng.

### Cell 4 — Markdown: phần môi trường

Chia phần cho các cell nhận diện môi trường. Không chạy lệnh.

### Cell 5 — Code: import thư viện chuẩn

Import `sys`, `os` và `Path`. Đây là các công cụ để nhận diện runtime và thao tác đường dẫn.

### Cell 6 — Code: nhận diện Colab hay local

Kiểm tra `google.colab` trong `sys.modules`, gán `IN_COLAB`, rồi in runtime đang dùng. Cell chỉ thông báo; không mount hoặc tải gì.

### Cell 7 — Code: xác nhận thư mục dự án

Lấy thư mục hiện hành làm `PROJECT_ROOT`, thêm vào `sys.path` nếu cần và in đường dẫn. Bootstrap đã chuyển đúng thư mục trước đó, nên cell này chủ yếu xác nhận trạng thái.

### Cell 8 — Markdown: phần cấu hình

Giới thiệu việc nạp và kiểm tra 10 tệp YAML.

### Cell 9 — Code: nạp và xác thực cấu hình

Gọi `load_config()` để gộp các YAML trong `configs/`, sau đó gọi `validate_config()` để kiểm tra các khóa bắt buộc và ràng buộc. Cell in môi trường đường dẫn, chế độ chạy, seed, tên dataset, URL tải và cấu hình DuckDB. Nếu config sai, pipeline dừng sớm tại đây thay vì lỗi ở bước xử lý dữ liệu.

### Cell 10 — Markdown: phần đường dẫn lưu trữ

Giới thiệu các thư mục dữ liệu, artifact và báo cáo.

### Cell 11 — Code: tạo cây thư mục

Gọi `resolve_paths(cfg)`, tạo các thư mục `raw`, `interim`, `processed`, `checkpoints`, `experiments`, `manifests`, `models`, `metrics`, `logs`, `tables`, `figures` và `appendix`. Sau đó tìm CSV trong `raw_root` để báo dữ liệu đã tồn tại hay notebook 01 cần tải. Cell chỉ kiểm tra sự hiện diện, chưa kiểm kê schema.

### Cell 12 — Markdown: phần tài nguyên máy

Giới thiệu kiểm tra CPU, RAM, ổ đĩa và quyền ghi.

### Cell 13 — Code: chẩn đoán runtime

Gọi `check_environment()` với yêu cầu tối thiểu 5 GB đĩa trống. Cell in hệ điều hành, Python, CPU logic, RAM, dung lượng đĩa, quyền ghi và cảnh báo. Kết quả nằm trong `env_report`; đây là kiểm tra khả năng chạy chứ không phải benchmark hiệu năng.

### Cell 14 — Markdown: phần checkpoint

Giới thiệu trạng thái các stage đã chạy.

### Cell 15 — Code: đọc checkpoint manifest

Khởi tạo `CheckpointManager`, đọc `checkpoint_manifest.json` và liệt kê stage đã được commit. Nếu chưa có, báo `Clean Start`. Cell không tự tiếp tục hoặc khôi phục biến trong RAM; checkpoint ở đây là nhật ký artifact đã tạo.

## 4. `01_download_validate.ipynb` — tải và chuẩn hóa dữ liệu

### Cell 1 — Markdown: tiêu đề

Mô tả mục tiêu kiểm kê file nguồn, xác thực và chuyển CSV sang Parquet.

### Cell 2 — Markdown: hướng dẫn chạy

Nhắc về bootstrap, không dùng Drive và quan hệ phụ thuộc với bước trước.

### Cell 3 — Code: bootstrap

Chuẩn bị mã nguồn, thư viện, config và đường dẫn như mục 2.

### Cell 4 — Code: khởi tạo stage 01

Import các hàm I/O, kiểm kê, schema và checkpoint; nạp config; mở kết nối DuckDB với giới hạn RAM/số thread từ `runtime.yaml`; tạo `CheckpointManager`. Biến chính được tạo: `con`, `cfg`, `paths`, `ckpt_mgr`.

### Cell 5 — Code: kiểm kê hoặc tải dữ liệu

Đầu tiên gọi `inventory_sources()` để tìm hai nhóm shard: aggregate và death/kill. Nếu chưa có CSV và `archive_url` tồn tại, cell tải archive công khai rồi giải nén vào `raw_root`, sau đó kiểm kê lại. Cell dừng bằng lỗi nếu thiếu một trong hai nhóm hoặc shard không đọc được. Cuối cùng lưu kích thước, số file và trạng thái vào `artifacts/manifests/source_inventory.json`.

`compute_hash=False` nghĩa là bước này chưa tính SHA256 cho từng file raw; nó ưu tiên tốc độ kiểm kê.

### Cell 6 — Code: CSV sang typed Parquet

Duyệt từng aggregate shard và death shard, lấy danh sách cột bắt buộc từ `schema.yaml`, rồi gọi `convert_shard_to_parquet()` để ép kiểu và ghi Parquet Snappy vào `data/interim/staging_shards`. Sau khi hoàn tất, commit checkpoint `schema` và báo Gate G1 hoàn tất.

Đầu ra chính: `agg_*.parquet`, `kill_*.parquet`, `source_inventory.json` và checkpoint manifest.

## 5. `02_data_quality_and_structure.ipynb` — chất lượng, chronology và split

### Cell 1 — Markdown: tiêu đề

Mô tả audit dữ liệu, roster, chronology và khóa train/validation/test.

### Cell 2 — Markdown: hướng dẫn chạy

Nhắc rằng cần output Parquet từ notebook 01.

### Cell 3 — Code: bootstrap

Chuẩn bị môi trường dùng chung.

### Cell 4 — Code: khởi tạo stage 02

Import các hàm làm sạch, metadata, split và chronology; mở DuckDB; tìm toàn bộ `agg_*.parquet` trong staging. Nếu notebook 01 chưa tạo các tệp này, cell sau sẽ không có đầu vào hợp lệ.

### Cell 5 — Code: làm sạch aggregate

Gộp các shard aggregate, đếm bản ghi trùng, thiếu khóa và giá trị âm/placement không hợp lệ. Cell chuẩn hóa khoảng trắng ở ID, loại trùng chính xác và loại dòng vi phạm miền giá trị. Dữ liệu sạch được ghi vào `cleaned_aggregate.parquet`; số dòng bị loại theo lý do được ghi vào `removal_log.csv`.

### Cell 6 — Code: tạo metadata theo trận

Gom theo `match_id` để tính ngày trận, mode phổ biến, party size, game size, số đội/người quan sát được, placement lớn nhất và `estimated_match_duration` bằng thời gian sống lớn nhất. Cờ `is_roster_complete` đánh dấu roster có vẻ đầy đủ. Đầu ra là `match_metadata.parquet`.

### Cell 7 — Code: đánh giá chronology

Đọc tối đa 50.000 trận từ metadata, gọi `run_chronology_audit()` để gán Grade A/B/C theo độ tin cậy của thứ tự thời gian, rồi lưu `chronology_report.json`. Grade này quyết định notebook 08 có được phép tạo đặc trưng lịch sử hay không.

### Cell 8 — Code: khóa split theo match

Gọi `create_split_assignments(..., strategy="group_by_match")`. Do hàm chỉ xử lý riêng `chronological`, giá trị này đi vào nhánh xáo trộn ngẫu nhiên có seed 42, với tỷ lệ mặc định 70/15/15. Mọi người chơi trong cùng `match_id` thuộc cùng một split, tránh rò rỉ một trận qua nhiều tập. Cell ghi `split_assignments.parquet`, `split_manifest.json`, commit checkpoint và đóng Gate G2.

## 6. `03_build_player_match.ipynb` — stage điều phối

### Cell 1 — Markdown: tiêu đề

Nêu mục tiêu xây dựng đặc trưng cấp người chơi–trận.

### Cell 2 — Markdown: hướng dẫn chạy

Mô tả bootstrap và phụ thuộc dữ liệu.

### Cell 3 — Code: bootstrap

Chuẩn bị môi trường dùng chung.

### Cell 4 — Code: mở kết nối và thông báo tích hợp

Nạp config, đường dẫn, mở DuckDB và tạo `CheckpointManager`, sau đó chỉ in rằng bước này được tích hợp với stage 04.

**Thực tế:** notebook 03 hiện không tạo `player_match` và không ghi artifact riêng. Các đặc trưng combat, movement, support và placement được tạo trong phép join ở cell 6 của notebook 04. Vì vậy notebook 03 hiện là điểm đánh dấu kiến trúc, có thể chạy nhưng không bắt buộc để notebook 04 hoạt động.

## 7. `04_combat_timing.ipynb` — thời điểm giao tranh và bảng feature chính

### Cell 1 — Markdown: tiêu đề

Mô tả tổng hợp early/mid/late kill và ghép vào dữ liệu người chơi–trận.

### Cell 2 — Markdown: hướng dẫn chạy

Nhắc phụ thuộc vào đầu ra notebook 01 và 02.

### Cell 3 — Code: bootstrap

Chuẩn bị môi trường dùng chung.

### Cell 4 — Code: khởi tạo stage 04

Nạp config, mở DuckDB, tìm `kill_*.parquet`, và khai báo đường dẫn tới `cleaned_aggregate.parquet` cùng `match_metadata.parquet`.

### Cell 5 — Code: tổng hợp combat timing

Đọc death event, nối với metadata trận, loại event thiếu killer/victim, self-kill, thời gian âm hoặc trận không có duration hợp lệ. Thời gian trận được chia ba phần bằng nhau:

- Early: `time < duration/3`.
- Mid: `duration/3 <= time < 2*duration/3`.
- Late: `time >= 2*duration/3`.

Cell gom theo `(match_id, killer_name)` để tính tổng kill event, kill đầu tiên, thời gian kill trung bình, số và tỷ lệ kill ở từng pha. Đầu ra là `combat_timing.parquet` và `event_join_audit.csv`.

### Cell 6 — Code: tạo `player_match_features.parquet`

Left join aggregate sạch với metadata trận và combat timing. Trong phép join, cell tạo:

- Target/placement: `normalized_placement = 1 - (team_placement - 1)/(observed_team_count - 1)`.
- Combat: `damage_per_kill`.
- Movement: `total_distance`, `walk_ratio`.
- Support: `assist_ratio`.
- Timing: số/tỷ lệ early, mid, late kill; first/average kill time.
- Biến chẩn đoán: kill/damage mỗi phút và vận tốc đi bộ/xe.
- Cờ audit: có event kill và chênh lệch kill giữa hai nguồn.

Cell kiểm tra số dòng sau left join phải bằng số dòng aggregate sạch để phát hiện row explosion. Nó ghi bảng chính `data/processed/player_match_features.parquet`, báo cáo `kill_discrepancy.csv` và checkpoint `player_match_features`.

## 8. `05_eda.ipynb` — EDA hiện có

### Cell 1 — Markdown: tiêu đề

Tiêu đề công bố EDA 8 pha.

### Cell 2 — Markdown: hướng dẫn chạy

Nhắc cần bảng feature từ notebook 04.

### Cell 3 — Code: bootstrap

Chuẩn bị môi trường dùng chung.

### Cell 4 — Code: thống kê phân bố và phân tích mode

Đọc toàn bộ `player_match_features.parquet` vào pandas. Với 12 biến hành vi/target, cell tính thống kê như mean, standard deviation, median, skewness và tỷ lệ bằng 0; lưu vào `data_quality_summary.csv`. Sau đó gọi `analyze_behavior_by_mode()` để so sánh hành vi theo mode và in chiến lược RQ2 được khuyến nghị.

**Giới hạn thực tế:** cell import `run_structural_eda` nhưng không gọi. Notebook hiện chỉ thực thi phần tóm tắt phân bố và phân tích mode, chưa thực hiện đầy đủ 8 pha hoặc tạo toàn bộ biểu đồ như tiêu đề mô tả. Việc đọc toàn bộ Parquet vào pandas cũng có thể cần nhiều RAM.

## 9. `06_rq1_analysis.ipynb` — quan hệ hành vi và outcome

### Cell 1 — Markdown: tiêu đề

Nêu câu hỏi RQ1 về quan hệ giữa hành vi, timing và outcome.

### Cell 2 — Markdown: hướng dẫn chạy

Nhắc phụ thuộc vào bảng feature hoàn chỉnh.

### Cell 3 — Code: bootstrap

Chuẩn bị môi trường dùng chung.

### Cell 4 — Code: chạy toàn bộ RQ1

Đọc bảng feature, khởi tạo `FeatureRegistry` và gọi `run_rq1_analysis()`. Hàm phân tích hai target: `player_survive_time` và `normalized_placement`; dùng allowlist để loại các feature không hợp lệ cho từng task; tính Pearson và Spearman ở toàn bộ dữ liệu và từng mode Solo/Duo/Squad nếu mode có ít nhất 50 dòng.

Kết quả gồm hệ số, p-value, số quan sát, nhóm feature, cờ hợp lệ chính và ghi chú về biến có nguy cơ target leakage. Bảng đầy đủ được ghi vào `rq1_relationship_summary.csv`; cell in 10 quan hệ có Spearman lớn nhất với normalized placement. Đây là phân tích liên hệ, không chứng minh quan hệ nhân quả.

## 10. `07_rq2_clustering.ipynb` — hồ sơ hành vi và phân cụm

### Cell 1 — Markdown: tiêu đề

Nêu câu hỏi RQ2 và bộ thí nghiệm C1–C5.

### Cell 2 — Markdown: hướng dẫn chạy

Nhắc cần output notebook 04.

### Cell 3 — Code: bootstrap

Chuẩn bị môi trường dùng chung.

### Cell 4 — Code: khởi tạo stage 07

Import hàm tạo hồ sơ và clustering, nạp config và đọc toàn bộ `player_match_features.parquet` vào `df`.

### Cell 5 — Code: tạo hồ sơ cấp người chơi

Gom nhiều trận của mỗi `player_name` thành một dòng hồ sơ: số trận, trung bình/độ lệch chuẩn kill và damage, movement, support, tỷ lệ kill theo pha và tỷ lệ trận có early kill. Outcome như survival, placement và win rate được giữ trong dataframe riêng để không đi vào feature clustering. Sau đó chỉ giữ người chơi có ít nhất 5 trận.

### Cell 6 — Code: chẩn đoán số cụm K

Chọn các cột có tiền tố `mean_`, `avg_` hoặc hậu tố `_ratio`, chạy K-Means cho K từ 2 đến 6 và in inertia, silhouette, Davies–Bouldin cùng tỷ lệ cụm nhỏ/lớn. Cell này hỗ trợ chọn K nhưng không tự chọn K tốt nhất.

Lưu ý: dữ liệu đưa vào `run_k_diagnostics()` ở cell này chưa được scale, trong khi quy trình clustering chính ở cell 7 có scale chuẩn. Vì vậy các chỉ số chẩn đoán K có thể bị biến có thang đo lớn chi phối.

### Cell 7 — Code: clustering chính và kiểm tra độ bền

Lấy K từ `rq2.yaml`, mặc định 4 nếu giá trị rỗng. Hàm `execute_rq2_clustering()` chuẩn hóa feature rồi chạy:

- C1: K-Means chính.
- C2: so K-Means với Agglomerative Ward trên tối đa 3.000 mẫu bằng Adjusted Rand Index.
- C3: thêm `games_played` để kiểm tra độ nhạy.
- Kiểm tra seed: chạy K-Means với seed khác.
- C5: sau khi clustering xong mới đối chiếu survival, placement và win rate theo cụm.

Đầu ra gồm `cluster_profile.csv`, `cluster_centers_standardized.csv`, `clustering_robustness.csv` và `c5_outcome_comparison.csv`. Code không có một thí nghiệm C4 riêng dù tiêu đề dùng cách gọi C1–C5.

## 11. `08_build_historical.ipynb` — đặc trưng lịch sử

### Cell 1 — Markdown: tiêu đề

Nêu mục tiêu tạo feature chỉ từ các trận quá khứ.

### Cell 2 — Markdown: hướng dẫn chạy

Nhắc cần chronology report và bảng feature.

### Cell 3 — Code: bootstrap

Chuẩn bị môi trường dùng chung.

### Cell 4 — Code: xây historical feature

Đọc `chronology_report.json`, rồi gọi `build_historical_features()`:

- Grade C: chặn bước lịch sử và trả trạng thái `blocked`.
- Grade A: dùng expanding window theo `date, match_id`, chỉ lấy các dòng trước dòng hiện tại.
- Grade B: chỉ dùng ngày nhỏ hơn ngày hiện tại, tránh các trận cùng ngày nhìn thấy nhau.

Cell tính số trận quá khứ và trung bình lịch sử của kill, damage, di chuyển, assist, DBNO, survival và placement. Người chơi có ít nhất 5 trận lịch sử được gắn `has_sufficient_history=True`. Đầu ra khi được phép là `historical_player_match_features.parquet`.

## 12. `09_rq3_prediction.ipynb` — dự đoán hiện có

### Cell 1 — Markdown: tiêu đề

Tiêu đề liệt kê các task S1, S2, P1, P2, P3, T0 và T1, cùng nhiều họ mô hình.

### Cell 2 — Markdown: hướng dẫn chạy

Nhắc cần bảng feature và split manifest.

### Cell 3 — Code: bootstrap

Chuẩn bị môi trường dùng chung.

### Cell 4 — Code: huấn luyện P1 và P2 bằng Linear Model

Đọc `player_match_features.parquet`, nối `split_assignments.parquet` theo `match_id`, rồi lấy hai allowlist:

- P1: dự đoán normalized placement có dùng survival trực tiếp.
- P2: dự đoán normalized placement không dùng survival trực tiếp.

Cell huấn luyện hai `LinearModelWrapper(model_type="exact")` trên train, tạo dự đoán cho các split, lưu `predictions_p1_linear.parquet` và `predictions_p2_linear.parquet`, sau đó in Micro MAE trên test.

**Giới hạn thực tế:** `TrainMeanRegressor`, `TrainMedianRegressor` và `HistGradientBoostingWrapper` chỉ được import nhưng không được gọi. Notebook hiện chưa chạy S1, S2, P3, T0/T1, baseline, gradient boosting, tuning hay khoảng tin cậy như tiêu đề mô tả.

## 13. `10_ablation_error_analysis.ipynb` — đóng góp feature và sai số

### Cell 1 — Markdown: tiêu đề

Nêu mục tiêu ablation, bootstrap và error analysis.

### Cell 2 — Markdown: hướng dẫn chạy

Nhắc cần output dự đoán P2 từ notebook 09.

### Cell 3 — Code: bootstrap

Chuẩn bị môi trường dùng chung.

### Cell 4 — Code: khởi tạo stage 10

Đọc feature và split rồi nối theo `match_id`; khởi tạo `FeatureRegistry`. Hàm paired bootstrap được import nhưng chưa gọi.

### Cell 5 — Code: group ablation

Dùng feature set P2 và huấn luyện lại Linear Model cho năm trường hợp: đầy đủ, bỏ combat, bỏ movement, bỏ support, bỏ timing. Với mỗi trường hợp, cell tính test MAE, RMSE, R² và `delta_mae_vs_full`. Delta MAE dương nghĩa là bỏ nhóm feature làm mô hình tệ hơn, nên nhóm đó có đóng góp. Kết quả được ghi vào `ablation_results.csv`.

### Cell 6 — Code: phân tích lát cắt sai số

Đọc dự đoán P2, chỉ lấy test, rồi tính MAE/RMSE/R² và residual trung bình theo game mode và các tầng normalized placement. Kết quả được ghi vào `error_analysis.csv`.

**Giới hạn thực tế:** notebook chưa gọi `run_paired_match_bootstrap()`, chưa tạo khoảng tin cậy 95%, và chưa có so sánh T0/T1 dù tiêu đề nhắc đến hai nội dung này.

## 14. `11_finalize_results.ipynb` — khóa kết quả

### Cell 1 — Markdown: tiêu đề

Nêu mục tiêu Gate G5 và checksum.

### Cell 2 — Markdown: hướng dẫn chạy

Nhắc cần hoàn tất các notebook phân tích trước.

### Cell 3 — Code: bootstrap

Chuẩn bị môi trường dùng chung.

### Cell 4 — Code: kiểm tra artifact và tạo manifest

Khai báo các run chính thức RQ1, P1, P2 và ablation; thêm RQ2 nếu `cluster_profile.csv` tồn tại. Cell yêu cầu bốn artifact tối thiểu phải tồn tại, nếu thiếu sẽ dừng bằng `FileNotFoundError`.

Sau đó `build_final_results_manifest()` tính SHA256 và byte size cho mọi CSV trong `reports/tables` và mọi file trong `artifacts/models`, lưu đường dẫn tương đối và danh sách run vào `final_results_manifest.json`.

**Giới hạn thực tế:** phần `figures` được tạo trong JSON nhưng hàm hiện không quét thư mục figures. Các prediction Parquet trong `artifacts/experiments` cũng không được đưa vào checksum; chỉ bảng CSV và model file được khóa.

## 15. `12_final_results_summary.ipynb` — đọc kết quả đã khóa

### Cell 1 — Markdown: tiêu đề

Nêu đây là notebook báo cáo chỉ đọc.

### Cell 2 — Markdown: hướng dẫn chạy

Nhắc cần `final_results_manifest.json` từ notebook 11.

### Cell 3 — Code: bootstrap

Chuẩn bị môi trường dùng chung.

### Cell 4 — Code: xác minh và hiển thị kết quả

Gọi `verify_final_manifest_integrity()` để tính lại SHA256 của các file đã khai báo. Nếu file thiếu hoặc hash khác, cell dừng bằng lỗi; nếu đúng, in thời điểm khóa và các run chính thức. Cuối cùng, nếu có `ablation_results.csv`, cell hiển thị bảng này.

Notebook hiện chưa dựng một báo cáo tổng hợp đầy đủ cho RQ1/RQ2/RQ3; phần hiển thị trực tiếp chỉ tập trung vào manifest và ablation.

## 16. `PUBG_COLAB_ALL_IN_ONE.ipynb` — ý nghĩa từng cell

Notebook này không tạo một pipeline khác. Nó lấy các cell có tác dụng của 13 notebook theo đúng thứ tự, chỉ giữ bootstrap một lần, rồi thêm cell tải kết quả.

| Cell | Loại | Tác dụng |
|---:|---|---|
| 1 | Markdown | Hướng dẫn chạy từ trên xuống, cảnh báo runtime tạm và nhu cầu RAM. |
| 2 | Markdown | Tiêu đề stage 00. |
| 3 | Code | Bootstrap: bung mã nguồn, cài dependency, tạo đường dẫn; không dùng Drive. |
| 4 | Markdown | Mở phần nhận diện môi trường. |
| 5 | Code | Import `sys`, `os`, `Path`. |
| 6 | Code | Nhận diện Colab/local và in trạng thái. |
| 7 | Code | Xác nhận `PROJECT_ROOT` và `sys.path`. |
| 8 | Markdown | Mở phần cấu hình. |
| 9 | Code | Nạp, validate config và in thông tin runtime/dataset. |
| 10 | Markdown | Mở phần đường dẫn lưu trữ. |
| 11 | Code | Tạo cây thư mục và kiểm tra CSV raw. |
| 12 | Markdown | Mở phần tài nguyên phần cứng. |
| 13 | Code | Kiểm tra CPU, RAM, đĩa và quyền ghi. |
| 14 | Markdown | Mở phần checkpoint. |
| 15 | Code | Đọc checkpoint manifest và báo stage đã hoàn tất. |
| 16 | Markdown | Tiêu đề stage 01. |
| 17 | Code | Nạp công cụ stage 01 và mở DuckDB. |
| 18 | Code | Kiểm kê raw; nếu trống thì tải archive công khai; lưu inventory. |
| 19 | Code | Chuyển aggregate/death CSV sang Parquet và commit Gate G1. |
| 20 | Markdown | Tiêu đề stage 02. |
| 21 | Code | Nạp công cụ làm sạch/metadata/split và tìm aggregate shard. |
| 22 | Code | Làm sạch aggregate và ghi removal log. |
| 23 | Code | Tạo metadata cấp trận. |
| 24 | Code | Đánh giá chronology và lưu Grade A/B/C. |
| 25 | Code | Tạo split 70/15/15 cô lập theo match và commit Gate G2. |
| 26 | Markdown | Tiêu đề stage 03. |
| 27 | Code | Mở DuckDB và thông báo stage 03 đã gộp vào stage 04; không tạo artifact. |
| 28 | Markdown | Tiêu đề stage 04. |
| 29 | Code | Chuẩn bị death shard, aggregate sạch và metadata. |
| 30 | Code | Tổng hợp early/mid/late combat timing. |
| 31 | Code | Left join và tạo bảng `player_match_features.parquet`. |
| 32 | Markdown | Tiêu đề stage 05. |
| 33 | Code | Tính thống kê phân bố, lưu data quality summary và phân tích mode. |
| 34 | Markdown | Tiêu đề stage 06. |
| 35 | Code | Chạy RQ1 Pearson/Spearman và lưu bảng quan hệ. |
| 36 | Markdown | Tiêu đề stage 07. |
| 37 | Code | Đọc feature và chuẩn bị hàm profiling/clustering. |
| 38 | Code | Tạo hồ sơ người chơi và lọc người có ít nhất 5 trận. |
| 39 | Code | Chẩn đoán K=2..6. |
| 40 | Code | Chạy clustering chính, robustness và C5 outcome comparison. |
| 41 | Markdown | Tiêu đề stage 08. |
| 42 | Code | Tạo historical features nếu chronology không phải Grade C. |
| 43 | Markdown | Tiêu đề stage 09. |
| 44 | Code | Huấn luyện P1/P2 Linear Model và in test MAE. |
| 45 | Markdown | Tiêu đề stage 10. |
| 46 | Code | Đọc feature/split và chuẩn bị ablation/error analysis. |
| 47 | Code | Chạy ablation theo nhóm feature. |
| 48 | Code | Phân tích sai số P2 theo mode và placement tier. |
| 49 | Markdown | Tiêu đề stage 11. |
| 50 | Code | Kiểm tra artifact bắt buộc và tạo final manifest SHA256. |
| 51 | Markdown | Tiêu đề stage 12. |
| 52 | Code | Xác minh manifest và hiển thị thông tin/ablation. |
| 53 | Markdown | Hướng dẫn tải kết quả về máy. |
| 54 | Code | Tạo `PUBG_results.zip` và tải xuống trên Colab hoặc hiển thị link local. |

### Cell 54 xuất những gì?

Mặc định `INCLUDE_DATA_CHECKPOINTS=False`, ZIP chứa:

- `reports/`: bảng và hình báo cáo hiện có.
- `configs/`: cấu hình dùng cho lần chạy.
- `artifacts/`: manifest, prediction, model và artifact khác.

ZIP không chứa raw/interim/processed để tránh tệp quá lớn. Chỉ đặt `INCLUDE_DATA_CHECKPOINTS=True` khi cần giữ checkpoint dữ liệu để chạy tiếp ở phiên khác và máy có đủ dung lượng.

## 17. Thứ tự phụ thuộc chính

```text
00 setup
   ↓
01 raw CSV → staging Parquet
   ↓
02 cleaned aggregate + match metadata + split + chronology
   ↓
03 marker only
   ↓
04 combat timing + player_match_features
   ├──→ 05 EDA
   ├──→ 06 RQ1
   ├──→ 07 RQ2
   ├──→ 08 historical features
   └──→ 09 P1/P2 predictions
             ↓
          10 ablation + error analysis
             ↓
          11 final manifest
             ↓
          12 integrity check + summary
```

Nếu chạy trên Colab, dùng All-in-One và chạy từ cell 1 đến cell 54. Nếu chạy 13 notebook riêng, các tệp đầu ra phải được giữ nguyên trong cùng `PROJECT_ROOT`; mở một runtime Colab mới sẽ mất dữ liệu tạm nếu chưa xuất ZIP có checkpoint.
