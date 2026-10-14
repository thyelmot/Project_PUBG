# NB03: kiểm tra giải nén Parquet trước bàn giao

Ngày 2026-10-04. Kiểm thử local/tổng hợp; chưa chạy dữ liệu thật hoặc sửa file Drive.

## I. Lỗi quan sát

Notebook03 được người dùng lưu có Error: ZSTD Decompression failure tại cell012, truy vấn grain trên player_match_base.parquet. File dữ liệu thật không có trong lượt kiểm tra này, nên chưa xác định được lỗi byte nguồn, storage/cache hay reader runtime cụ thể. Không gọi đây là lỗi RAM hoặc đổi codec để che lỗi.

Backup nguyên notebook có traceback: nb03_parquet_fix_2026-10-04/03_before_fix_with_error.ipynb.

## II. Thay đổi

- copy_query_to_parquet trước đây chỉ kiểm footer/số dòng, còn checksum publication chỉ bảo đảm bản sao khớp nguồn. Hai kiểm tra đó không chứng minh compressed pages đọc được.
- validate_parquet_file đọc toàn cột theo batch50000 với PyArrow single-thread; DuckDB quét full columns bằng bit_xor(hash(COLUMNS(*))), không collect vào pandas. COUNT(*) có thể dùng footer nên không đủ. Kiểm số decoded rows với footer/expected.
- Kiểm file local trước công bố và file đích sau công bố. Không thay output tốt nếu local decode thất bại. Nếu lỗi xuất hiện sau publication, stage dừng, không commit thành công; chưa có rollback tự động của bản đã công bố.
- Parts NB03 dùng row group50000 và kiểm tất cả local parts trước thay bất kỳ part, đối soát decoded rows, kiểm lại destination trước manifest. Không đổi số dòng, schema, codec ZSTD, công thức, targets, split hoặc cohort.
- NB03 dùng failure handler như NB02: ghi failed/resource_limited nếu còn là writer owner, giữ lỗi gốc, reset progress bắt khởi tạo lại. Không tự takeover owner khác, hard-kill/mất Drive vẫn có thể giữ running.
- Sinh 13regular để embedded source đồng nhất, không sinh/chạy All-in-One. Không sửa configs/rq3.yaml người dùng đã chọn70/15/15; bundle giữ config hiện hành.

## III. Kiểm chứng

- Fixture ZSTD frame hỏng nhưng footer đọc được: validator từ chối. Fixture sửa byte giữa frame ban đầu không luôn gây decompression failure; thay bằng phá magic frame để lỗi xác định. Đây không phải chứng minh checksum codec phát hiện mọi dạng hỏng.
- Mô phỏng DuckDB consumer giải nén lỗi với PyArrow/footer đọc được: không gọi publication, output tốt cũ giữ nguyên.
- File empty, multicolumn/NULL và batch-boundary50003rows: giải nén và số dòng đạt.
- Thực thi cell012 NB03 với lỗi decoder: ghi failed, không commit artifacts và chặn retry nếu chưa khởi tạo lại.
- Suite tập trung20tests/15,325s đạt, bao gồm thực thi NB03 và consumer NB04, feature formulas, edge-case publication và writer recovery. Log: nb03_parquet_fix_2026-10-04/regression.log.
- Suite shared IO9tests/29,735s đạt: cleaning, data/features pipeline và fixture300000rows dưới DuckDB128MB vẫn giữ300000/300000rows. Log: nb03_parquet_fix_2026-10-04/shared_io_regression.log.
- 13regular nbformat/AST đạt, git diff --check đạt; All-in-One hash không đổi trong lần sinh. Không chạy lại toàn bộ suite lịch sử.

## IV. Chạy lại tối thiểu

1. Đồng bộ source mới, tối thiểu src/data/io.py, src/features/base.py, src/utils/generate_notebooks.py và notebook03; bảo đảm src/data/checkpoints.py đã có writer guard từ bản sửa trước. Mở runtime mới để không dùng module cũ.
2. Chạy cấu hình Drive, Bootstrap, khởi tạo NB03. Nếu writer running cũ: chỉ takeover khi runtime cũ đã ngắt và không ai khác đang ghi.
3. Chạy registry, tạo player_match_base, rồi grain/schema/parts và các cell sau theo thứ tự. Producer tạo lại base/parts đúng tên; không dùng file lỗi làm input NB04. Không xóa/sửa manifest tay.
4. Không cần chạy lại NB01/NB02 nếu upstream còn completed và artifacts được xác minh; nếu đầu vào lỗi/stale phải sửa đúng producer đó, không bỏ gate.

Full decode tăng I/O/thời gian nhưng không tính lại nghiên cứu. Có thể vẫn lỗi storage/codec/reader sau sửa; giữ traceback mới để đối chiếu. Chưa xác minh file lỗi production được khôi phục, chưa upload/commit/push.
