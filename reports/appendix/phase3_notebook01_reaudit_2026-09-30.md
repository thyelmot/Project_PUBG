# Tái nghiệm thu Giai đoạn 3: Notebook 01

## I. Phạm vi

- Chỉ xử lý `01_download_validate.ipynb` và mã nguồn dùng chung trực tiếp phục vụ ingest, inventory, schema, checkpoint.
- Đối chiếu `PUBG_RESEARCH_SPEC.md` v3.0 và `PUBG_IMPLEMENTATION_PLAN.md`, mục NB01-01 đến NB01-13.
- Không chạy Notebook 02, Notebook All-in-One, dữ liệu thật, Google Drive hoặc Colab.

## II. Nội dung đã sửa

- `source_inventory.json` được tạo từ inventory nguồn thật, không còn ghi nhầm bản sao của batch manifest.
- Inventory ghi đường dẫn nguồn, byte, row count, checksum và thuật toán checksum; ngày tải và phiên bản chỉ ghi khi cấu hình có bằng chứng.
- Download hỗ trợ local raw, ZIP public và danh sách URL shard; dùng file `.part`, kiểm tra Content-Length, checksum, HTML giả dữ liệu, tên file an toàn và quy ước discovery.
- Schema kiểm tra required, optional, alias có kiểm soát, alias collision và drift theo từng shard.
- Parse audit tách original missing khỏi parse error, kiểm tra count nguyên và không bỏ dòng parse-error âm thầm.
- Batch manifest có đối soát rows đọc, rows lưu, rows bỏ và policy; resume chỉ tái dùng shard đã xác minh.
- Schema và parse report luôn ghi vào manifests directory; Notebook 01 commit đủ bốn artifact vào checkpoint.
- Notebook trình bày bảng source inventory, row reconciliation, schema theo shard, missing/parse theo cột và trạng thái đơn vị candidate/pending.
- Generator được sửa lỗi escape xuống dòng và tái tạo 13 stage notebook cùng All-in-One; All-in-One không được thực thi.

## III. Bằng chứng kiểm thử

- `test_w02_ingest_schema.py`: 14/14 đạt, gồm bài chạy chính Notebook 01 trong workspace tạm.
- `test_batch_ingest.py`: 3/3 đạt.
- `test_storage_publication.py`: 8/8 đạt.
- Kiểm tra tĩnh: 14 notebook parse Python thành công, output rỗng và execution count là null.
- Toàn bộ suite: 168 test đạt, 3 test bỏ qua có điều kiện, 0 lỗi.
- Fixture Notebook 01: 1 aggregate shard gồm 2 dòng và 1 death shard gồm 1 dòng; `rows_read=3`, row reconciliation đạt; source inventory, schema report, parse report, batch manifest, typed Parquet và checkpoint notebook đều tồn tại.

## IV. Giới hạn và điểm dừng

- Đây là nghiệm thu bằng code và fixture, không phải full-data run.
- Nhánh URL trực tiếp dùng mock, chưa tải qua Internet trong lượt này.
- Dataset date/version để null nếu chưa khai báo bằng chứng; đơn vị time/distance vẫn là candidate/pending và Notebook 01 không thực hiện đổi đơn vị nghiên cứu.
- Chưa xác minh Google Drive shortcut, quota, T4, CUDA/cuML hoặc RAM trên Colab.
- Giai đoạn 3 hoàn tất. Điểm tiếp theo là NB02-01 của Giai đoạn 4, chỉ bắt đầu khi người dùng cho phép.