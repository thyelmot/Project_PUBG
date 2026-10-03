# Nghiệm thu NB01-14 theo Chuẩn Phương án 2

Ngày nghiệm thu: 2026-09-30

## I. Phạm vi

Đợt này chỉ sửa và nghiệm thu Notebook 01. Đã đối chiếu PUBG_RESEARCH_SPEC.md v3.0, PUBG_IMPLEMENTATION_PLAN.md, mục Chuẩn Phương án 2 và NB01-14. Không thay đổi mục tiêu nghiên cứu, cohort, feature, target, split, leakage rule, estimator hoặc metric. Không chạy notebook tổng hợp và chưa bắt đầu NB02-01.

## II. Nội dung đã thực hiện

Nguồn canonical src/utils/generate_notebooks.py đã được viết lại cho Notebook 01 bằng tiếng Việt có dấu và đủ các khối:

- cell-004: bối cảnh khoa học, input/output, câu hỏi kiểm tra và tiêu chí G1.
- cell-005 đến cell-006: raw immutability, batch 50.000 mặc định, resume theo shard, missing/parse policy và bảng 01-A.
- cell-007 đến cell-008: provenance, inventory, công thức đối soát và bảng 01-B1, 01-B2, 01-C.
- cell-009 đến cell-010: schema/alias, missing/parse, unit evidence và bảng 01-D, 01-E, 01-F.
- cell-011 đến cell-012: V01-01 quy mô shard và V01-02 missing gốc so với lỗi parse; hiển thị inline rồi lưu PNG canonical.
- cell-013 đến cell-014: diễn giải đúng scope, limitations, expected/actual Gate G1, artifact/checksum và bàn giao trong bảng 01-G, 01-H.

Hai hình dùng toàn bộ shard/cột của lần chạy, không lấy mẫu. Caption nêu nguồn bảng, N, scope, đơn vị và cách đọc. Checkpoint schema vẫn giữ chữ ký schema_batch_v2 và bốn artifact cốt lõi; checkpoint notebook bổ sung hai PNG, nên không thay protocol nghiên cứu.

## III. Nghiệm thu notebook thật trên fixture cô lập

Notebook notebooks/01_download_validate.ipynb đã chạy hết mọi code cell trong workspace runtime tạm:

- 2 shard aggregate, 1 shard deaths, tổng 5 dòng.
- Fixture có một missing gốc ở player_dmg và một lỗi parse ở player_kills.
- Đối soát đạt: rows_read = 5, rows_saved = 5, rows_dropped = 0.
- Render đủ bảng 01-A đến 01-H và hai hình V01-01, V01-02.
- Tạo đủ batch manifest, source inventory, schema report, parse report, typed Parquet và checkpoint completed.
- Hai PNG có chữ ký file hợp lệ và có mặt trong artifact của checkpoint notebook.

## IV. Kiểm thử

- python -m py_compile src/utils/generate_notebooks.py tests/test_w02_ingest_schema.py: đạt.
- test_w02_ingest_schema.py: 14/14 đạt.
- test_batch_ingest.py: 3/3 đạt.
- test_no_drive_notebooks.py: 8 đạt, 1 bỏ qua có điều kiện vì không được phép chạy All-in-One.
- test_notebook_logic_audit.py: 9/9 đạt.
- test_storage_publication.py: 8/8 đạt.
- Toàn bộ unittest: 170 đạt, 3 bỏ qua có điều kiện.
- 14 notebook được đọc lại: cú pháp code cell hợp lệ, execution_count null và outputs rỗng.
- git diff --check chỉ còn cảnh báo trailing whitespace lịch sử trong CHANGELOG_FIXES.md, không phát sinh từ đợt sửa này.

## V. Giới hạn và điểm dừng

Chưa chạy full-data thật, Google Drive, Google Colab hoặc GPU. Version/ngày tải và đơn vị vẫn pending nếu cấu hình nguồn không có bằng chứng. Fixture chứng minh hợp đồng vận hành và cách trình bày, không phải kết quả nghiên cứu PUBG.

NB01-14 hoàn tất. Task chưa nghiệm thu đầu tiên theo kế hoạch là NB02-01; đợt này dừng trước Notebook 02.