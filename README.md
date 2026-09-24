# PUBG — Hai chế độ chạy notebook trên Google Colab

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

1. Upload toàn bộ `Project_PUBG` lên Drive hoặc để bootstrap tạo mã nguồn trong thư mục Drive đã chọn.
2. Mở từng notebook từ `00_setup.ipynb` đến `12_final_results_summary.ipynb`.
3. Trong cell **Chọn nơi lưu dữ liệu**, chọn `drive` và dùng cùng một `PUBG_DRIVE_PROJECT_ROOT`, mặc định `/content/drive/MyDrive/PUBG_Project/Project_PUBG`.
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

RQ1 nghiên cứu hành vi–outcome; RQ2 phân nhóm hành vi; RQ3 dự đoán survival/placement. [Đặc tả](../PUBG_RESEARCH_SPEC.md) và [kế hoạch](../PUBG_IMPLEMENTATION_PLAN.md) nêu đầy đủ mục tiêu; mã hiện tại **chưa thực hiện toàn bộ** yêu cầu đó.

- Notebook 05–07, 09–10 còn nạp Parquet vào pandas. Bỏ Drive không giải quyết nhu cầu RAM trên khoảng 20 GB CSV. Không tự giảm mẫu khi thiếu RAM.
- `runtime.mode` chưa nối development cohort trong mọi notebook. Chọn `development` không đảm bảo chỉ xử lý dữ liệu nhỏ; tests dùng synthetic data riêng.
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
- **Hết RAM:** giảm DuckDB memory không sửa bước pandas nạp toàn bảng; cần đủ RAM hoặc triển khai streaming theo kế hoạch.
- **Hết disk:** ZIP/CSV/Parquet/temp có thể cùng tồn tại; chỉ dọn file đã sao lưu/tái tạo được, code không tự xóa raw.
- **Missing artifact ở notebook riêng:** dùng notebook tổng hợp hoặc chuyển outputs bước trước vào runtime.
- **Checksum sai:** dừng, xác minh nguồn/backup; không bỏ qua check.
- **Grade C:** history bị chặn; current-match vẫn có thể chạy. Thiếu thứ tự nội ngày không loại history Grade B đã xác minh.

## Kiểm thử

`tests/test_no_drive_notebooks.py` kiểm tra paths local/Colab, anonymous download/HTML rejection, ZIP/checksum validation, manifest sau di chuyển, notebook syntax và thực thi các cell notebook tổng hợp trong workspace mới với synthetic CSV. Các tests cũ vẫn chạy cùng suite.

Synthetic smoke không tải lại dataset nhiều GB, không đo full-scale Colab và không phải kết quả nghiên cứu chính thức.
