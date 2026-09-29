# PUBG — Hai chế độ chạy notebook trên Google Colab

Mọi thay đổi của dự án được ghi tại [CHANGELOG_FIXES.md](CHANGELOG_FIXES.md). Trước khi sửa phải đối chiếu [đặc tả nghiên cứu](PUBG_RESEARCH_SPEC.md) và [kế hoạch triển khai](PUBG_IMPLEMENTATION_PLAN.md).

## Tài liệu và đợt triển khai hiện hành, cập nhật 29/09/2026

[Kế hoạch thống nhất](PUBG_IMPLEMENTATION_PLAN.md) chứa toàn bộ yêu cầu theo giai đoạn 0-16. Đọc [quy tắc tích theo bằng chứng](PUBG_IMPLEMENTATION_PLAN.md#tracking-rules), rồi kiểm tra từ [giai đoạn 0](PUBG_IMPLEMENTATION_PLAN.md#phase-0). Ô chưa tích nghĩa là chưa được tái nghiệm thu trong bản mới, không có nghĩa code chưa tồn tại.

Hoàn thiện code và kiểm thử toàn bộ notebook 00-12 trước G0, sau đó chạy dữ liệu thật theo thứ tự. Dùng Drive, batch 50000, require-existing true, per_mode và GPU cho huấn luyện có hỗ trợ. Không chạy All-in-One, kể cả test gọi nó; chọn kiểm thử theo [giai đoạn 15](PUBG_IMPLEMENTATION_PLAN.md#phase-15). Hướng dẫn All-in-One và kết quả test cũ bên dưới là lịch sử, không áp dụng như lệnh thực thi của đợt hiện hành.

| Tài liệu | Vai trò |
|---|---|
| Đặc tả nghiên cứu | Mục tiêu và protocol chính thức |
| Kế hoạch triển khai thống nhất | Nguồn kế hoạch duy nhất, công việc và điều kiện nghiệm thu |
| [TEAM_DRIVE.md](TEAM_DRIVE.md) | Chạy nối tiếp, bàn giao và phục hồi |
| [NOTEBOOK_CELL_GUIDE.md](NOTEBOOK_CELL_GUIDE.md) | Giải thích cell |
| [RQ2_RUN_GUIDE.md](RQ2_RUN_GUIDE.md) | Gates và cách chạy RQ2 |
| [GPU_PER_MODE_GUIDE.md](GPU_PER_MODE_GUIDE.md) | Đồng bộ file, per_mode và GPU |
| CHANGELOG_FIXES.md | Lịch sử thay đổi/kiểm thử, chỉ ghi nối tiếp |
| literature_mapping và traceability_matrix | Căn cứ nghiên cứu và truy vết |

Thông tin/test ngày 25/09 bên dưới là lịch sử. K=4/min_games=5 không phải lựa chọn nghiên cứu mặc định; dùng diagnostics và gates theo kế hoạch. Checklist cũ và kết quả synthetic không chứng minh full-data/Drive/GPU đã được xác minh.

## Cách chạy cho nhóm

### Cách 1 — All-in-One, không dùng Drive

1. Mở [PUBG_COLAB_ALL_IN_ONE.ipynb](notebooks/PUBG_COLAB_ALL_IN_ONE.ipynb) bằng **Colab → File → Upload notebook**.
2. Trong cell **Chọn nơi lưu dữ liệu**, giữ `PUBG_STORAGE_MODE = "runtime"`.
3. Chạy các cell từ trên xuống trong cùng notebook và cùng runtime. Bootstrap chỉ cài các thư viện còn thiếu, không cài lại toàn bộ môi trường Colab.
4. Cell cuối tải `PUBG_results.zip` về máy trước khi runtime bị reset.

**Nhóm chỉ cần chia sẻ notebook tổng hợp.** Mỗi người chạy runtime riêng, không truy cập Drive cá nhân của người khác. Notebook chứa snapshot code/config lúc sinh; sau khi sửa code cần chạy lại generator.

### Cách 2 — 13 notebook riêng, dùng chung Google Drive

**Nhiều thành viên chạy nối tiếp trên một thư mục:** xem [TEAM_DRIVE.md](TEAM_DRIVE.md).
Chủ thư mục chia sẻ `PUBG_Project` với quyền Editor; thành viên thêm shortcut vào My Drive và bật `PUBG_REQUIRE_EXISTING_PROJECT = True`.
Cùng một chuỗi đường dẫn chưa đủ: mọi người phải trỏ đến cùng thư mục gốc được chia sẻ, không dùng các bản sao riêng.

1. Upload toàn bộ `Project_PUBG` lên đúng thư mục Drive dùng chung trước khi mở notebook.
2. Mở từng notebook từ `00_setup.ipynb` đến `12_final_results_summary.ipynb`.
3. Trong cell **Chọn nơi lưu dữ liệu**, giữ cấu hình mặc định `drive`, `PUBG_REQUIRE_EXISTING_PROJECT = True`, `PUBG_BATCH_ROWS = 50000` và cùng một `PUBG_DRIVE_PROJECT_ROOT`, mặc định `/content/drive/MyDrive/PUBG_Project/Project_PUBG`.
4. Chấp nhận quyền mount Drive, rồi chạy notebook hiện tại từ trên xuống. Chỉ chuyển sang notebook sau khi notebook trước đã hoàn tất.

Mỗi tab Colab vẫn có biến Python riêng. Dữ liệu nối tiếp qua `data/`, `artifacts/` và `reports/` trong cùng thư mục Drive. Không chạy đồng thời hai notebook ghi vào cùng artifact.

## Dataset public

- Dataset gốc: [PUBG Match Deaths and Statistics](https://www.kaggle.com/datasets/skihikingkevin/pubg-match-deaths/data).
- [ZIP public của nhóm](https://drive.google.com/file/d/1-NpwnrD3VlD-ZGUyyKk2TwobswwF8zAy/view).
- URL tải và checksum: `configs/data.yaml`, mục `source`.

Downloader gửi HTTP request ẩn danh tới file public, bao gồm xác nhận tải file lớn; không gọi OAuth, đọc cookies trình duyệt hoặc xin quyền Drive. Chủ file cần duy trì **Anyone with the link / Viewer** và cho phép tải. Quota vẫn có thể làm tải thất bại; code từ chối HTML đăng nhập/quota thay vì lưu nó thành ZIP.

Ngày 24/09/2026 đã kiểm tra URL tải ẩn danh: HTTP 200, `application/octet-stream`, Content-Length 4.399.919.847 byte và 8 byte đầu có chữ ký ZIP. Chưa tải toàn bộ bản public hoặc kiểm chứng lại SHA256 của bản public trong lần kiểm tra này.

## Lưu kết quả và reset runtime

`configs/paths.yaml` mặc định `active_environment: auto`. Bootstrap thêm môi trường `drive` trong bộ nhớ khi người dùng chọn Drive:

| Dữ liệu | Local | Colab runtime | Colab Drive |
|---|---|---|---|
| Raw | `../Data_PUBG` | `/content/data/raw` | `<PROJECT_ROOT>/data/raw` |
| Interim/processed | `Project_PUBG/data/` | `/content/data/` | `<PROJECT_ROOT>/data/` |
| Artifacts/checkpoints | `Project_PUBG/artifacts/` | `/content/Project_PUBG/artifacts/` | `<PROJECT_ROOT>/artifacts/` |
| Reports | `Project_PUBG/reports/` | `/content/Project_PUBG/reports/` | `<PROJECT_ROOT>/reports/` |
| Figures | `Project_PUBG/figures/` | `/content/Project_PUBG/figures/` | `<PROJECT_ROOT>/figures/` |

DuckDB temp vẫn dùng `/content/temp` trong chế độ Drive để tránh ghi file tạm nặng lên Drive. Dữ liệu raw/interim/processed và kết quả chính thức được lưu bền vững trong dự án Drive.

Đĩa Colab là tạm thời, file có thể mất khi runtime reset/bị thu hồi. Lưu notebook không đồng nghĩa đã lưu dữ liệu máy ảo. [Colab FAQ](https://research.google.com/colaboratory/faq.html).

- ZIP mặc định chứa configs/reports/figures/artifacts; không chứa raw hoặc DuckDB temp.
- Đặt `INCLUDE_DATA_CHECKPOINTS = True` ở cell export nếu cần thêm interim/processed; ZIP có thể rất lớn. Có thể chạy riêng cell export trước khi hoàn tất nghiên cứu.
- ZIP mặc định chia sẻ được kết quả đã có nhưng không đủ phục hồi mọi bước dữ liệu nặng.
- Sau reset ở chế độ runtime: mở lại notebook và chạy lại hoặc phục hồi từ ZIP đã tải. Ở chế độ Drive: mount lại đúng thư mục và chạy notebook tiếp theo.
- Manifest kết quả mới dùng đường dẫn tương đối nên checksum verification hoạt động khi chuyển máy. Checkpoint cũ có absolute paths cần kiểm tra lại; metadata không thay thế dữ liệu thực.

## Chạy local và cập nhật notebook

```bash
cd Project_PUBG
python -m pip install -r requirements.txt
python -m jupyter notebook
```

Bootstrap tìm project từ cwd/thư mục cha và chuyển cwd về project; mở từ `notebooks/` vẫn hoạt động. Local không tự cài lại package mỗi lần chạy.

Sau khi sửa code/config:

```bash
python -m src.utils.generate_notebooks
python -m unittest discover -s tests -v
```

Generator sinh notebook riêng và tổng hợp từ cùng nội dung, chỉ nhúng code/config/tests/README/requirements, không nhúng raw, outputs, `.env` hoặc token. Bootstrap tái sử dụng project hiện có, không ghi đè cấu hình thành viên đã sửa. Muốn dùng snapshot mới trên Colab, dùng runtime sạch hoặc cập nhật code/config hiện có.

## Các bước hiện có

| Bước | Chức năng |
|---|---|
| 00 | Setup, config, paths, resource, checkpoint status |
| 01 | Public download/local input, inventory, typed Parquet |
| 02 | Cleaning, roster metadata, chronology diagnostic, split |
| 03 | Khởi tạo bước base; phép tính đang gộp ở 04 |
| 04 | Combat Timing, player-match features |
| 05 | Distribution summary, mode comparison |
| 06 | RQ1 Pearson/Spearman theo outcome/mode |
| 07 | Profiles, K diagnostics, KMeans, supporting comparisons |
| 08 | Historical features hoặc blocked khi Grade C |
| 09 | P1/P2 linear regression, lưu predictions |
| 10 | Group ablation, error slices |
| 11 | Khóa checksum các bảng/model hiện có |
| 12 | Kiểm tra checksum, xem ablation |
| Cuối | Tải ZIP kết quả về máy |

## Phạm vi và giới hạn hiện tại

RQ1 nghiên cứu hành vi–outcome; RQ2 phân nhóm hành vi; RQ3 dự đoán survival/placement. [Đặc tả](PUBG_RESEARCH_SPEC.md) và [kế hoạch](PUBG_IMPLEMENTATION_PLAN.md) nêu đầy đủ mục tiêu; mã hiện tại **chưa thực hiện toàn bộ** yêu cầu đó.

- Notebook 05 đọc từng feature cùng `party_size`; notebook 06 đọc từng cặp feature–target. Cả hai vẫn dùng đủ dòng và công thức exact, nên bộ nhớ vẫn tăng theo số dòng và thời gian đọc từ Drive có thể tăng.
- Notebook 07, 09–10 còn bước nạp dữ liệu lớn vào pandas hoặc mô hình. Bỏ Drive hay giảm `PUBG_BATCH_ROWS` không giải quyết RAM của các bước này. Không tự lấy mẫu để che giới hạn tài nguyên.
- `runtime.mode: full` mô tả đúng đường chạy hiện tại; key này không tự cắt shard hoặc lấy mẫu.
- Notebook 02 dùng group-by-match split, chronology diagnostic giới hạn 50.000 match; chưa phải audit chronology toàn bộ.
- Notebook 07 đang dùng min-games 5, K mặc định 4 khi K null. Đây là lựa chọn chạy thử có sẵn, chưa phải quyết định theo retention/stability; cần hoàn thiện gates trước final research run.
- Notebook 09 mới chạy P1/P2 linear, chưa orchestration đủ S1/S2/P3/T0/T1 và baselines. Có module không đồng nghĩa đã chạy thí nghiệm.
- Streaming model fallback, đủ tám pha EDA/biểu đồ, experiment registry và tự động resume toàn pipeline cần tiếp tục đối chiếu kế hoạch.
- Bước 11 khóa integrity của file hiện có, không chứng nhận mọi yêu cầu G5. Không còn ghi S1 như run đã chạy khi notebook 09 chưa tạo S1.

Notebook hỗ trợ cả runtime tạm không cần Drive và thư mục Drive dùng chung giữa các stage. Chưa chạy full dataset hoặc tạo metric nghiên cứu thật.

## Config và xử lý lỗi

| Muốn thay | Config/key | Chạy lại từ |
|---|---|---|
| Nguồn | `data.yaml`: `source.archive_url`, `source.archive_sha256` | 01; dùng raw directory riêng nếu đổi nguồn |
| Nơi lưu | `paths.yaml`: `active_environment`, `environments.*` | Bootstrap/setup, chuyển outputs cần thiết trước |
| DuckDB | `runtime.yaml`: `duckdb.memory_limit`, `duckdb.threads` | Bước DuckDB tương ứng |
| K | `rq2.yaml`: `n_clusters` | 07, 11, 12 |
| Feature/model/threshold khác | Kiểm tra YAML và caller | Bước liên quan/downstream; không giả mọi YAML key đã nối vào code |

- Checkpoint metadata tại `artifacts/checkpoints/checkpoint_manifest.json`. Manager có API compatibility/invalidation nhưng notebook chưa tự skip/resume mọi stage.
- **HTML/403/quota:** kiểm tra quyền public/quota hoặc thay URL/checksum; không cần cấp quyền Drive cá nhân.
- **Thiếu CSV:** kiểm tra raw_root; discovery đệ quy cả ZIP có thêm thư mục `Data_PUBG/`.
- **Notebook 01 bị ngắt:** chạy lại cell cấu hình, Bootstrap, khởi tạo rồi cell batch. Manifest dùng lại shard đã hoàn tất đúng checksum; shard đang dở phải chuyển đổi lại.
- **Mất runtime:** chế độ Drive giữ file đã công bố; biến Python và file trong `/content/temp` mất. Chế độ runtime phải chạy lại hoặc phục hồi artifact đã tải về.
- **Hết RAM:** giảm `PUBG_BATCH_ROWS` chỉ giảm RAM khi chuyển CSV sang Parquet ở notebook 01; không sửa RAM của 07, 09–10.
- **Hết disk:** ZIP/CSV/Parquet/temp có thể cùng tồn tại; chỉ dọn file đã sao lưu/tái tạo được, code không tự xóa raw.
- **Missing artifact ở notebook riêng:** dùng notebook tổng hợp hoặc chuyển outputs bước trước vào runtime.
- **Checksum sai:** dừng, xác minh nguồn/backup; không bỏ qua check.
- **Grade C:** history bị chặn; current-match vẫn có thể chạy. Thiếu thứ tự nội ngày không loại history Grade B đã xác minh.

## Kiểm thử

Lần kiểm tra cuối ngày 25/09/2026 chạy `python -m unittest discover -s tests -v`: **60/60 test đạt**. Suite kiểm tra notebook All-in-One trong runtime sạch, 13 notebook ở các process riêng, chạy lại cell, Drive mô phỏng, bàn giao project sang tài khoản thứ hai, ZIP/checksum, publication lỗi và tính tương đương của cách đọc từng cột ở 05/06.

Các tình huống Drive/FUSE là fault injection (mô phỏng lỗi), chưa phải kiểm thử mount Google Drive thật. Synthetic smoke không tải toàn bộ dataset nhiều GB, không đo peak RAM/đĩa trên Colab và không phải kết quả nghiên cứu chính thức.
