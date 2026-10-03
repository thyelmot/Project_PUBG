# Nghiệm thu Giai đoạn 4: Notebook 02

Ngày nghiệm thu: 2026-10-01

## I. Phạm vi

Đợt này rà soát và thực hiện NB02-01 đến NB02-22 theo PUBG_RESEARCH_SPEC.md v3.0, PUBG_IMPLEMENTATION_PLAN.md và Chuẩn Phương án 2. Phạm vi là code và fixture; chưa phải full-data run. Không thay đổi RQ, feature, target, metric hoặc estimator. Split protocol vẫn chronology-first khi Grade A/B và group-by-match khi Grade C.

## II. Lỗ hổng nền tảng đã sửa

1. Exact duplicate trên staged Parquet từng bị source_file/source_row làm business-identical rows thành khác nhau. Cleaning nay partition theo business columns, dùng lineage chỉ để chọn đại diện ổn định và giữ lineage ở output.
2. Cleaning cũ loại toàn dòng khi survival hoặc placement không hợp lệ. Nay target-invalid được giữ cho task khác; valid_survival và valid_placement điều khiển exclusion theo task trong task_exclusion_ledger.csv.
3. Identity conflict không còn chỉ là count. Toàn bộ record xung đột cùng raw lineage và normalized key được lưu tại identity_conflicts.parquet; không dùng keep-first.
4. Removal ledger bổ sung rule, rows_before, rows_removed, rows_after, example_count và version. Error flags và task exclusions tách khỏi phép đối soát dòng.
5. Match metadata không dùng MIN/MODE để che conflict. Canonical metadata là null khi nội match bất nhất; output bổ sung missing_team_id_rows, team_placement_conflict_count, has_metadata_conflict và roster completeness.
6. Chronology report bổ sung UTC normalization, observed resolution, same-day multiplicity, same-player timestamp overlaps, timestamp semantics và statistic-availability evidence. Config chỉ có thể hạ grade, không thể nâng vượt bằng chứng.
7. Chronological split giữ whole-day block cho Grade B và timestamp tie block cho Grade A. Grade C bị chặn khỏi official chronological split.
8. Báo cáo trạng thái config đã sửa đúng tên validation_ratio thay vì val_ratio.

## III. Notebook 02 theo Chuẩn Phương án 2

- cell-004: bối cảnh, câu hỏi kiểm tra, input/output và tiêu chí G2.
- cell-005 đến cell-006: provenance G1, aggregate scope và trạng thái quyết định split.
- cell-007 đến cell-008: identity, duplicate, conflict quarantine, removal cascade, flags và task ledger.
- cell-009 đến cell-010: roster, metadata conflicts và placement consistency.
- cell-011 đến cell-012: chronology evidence và số match theo ngày UTC.
- cell-013 đến cell-014: config split, strategy resolution, match isolation và boundary audit.
- cell-015 đến cell-016: V02-01 đến V02-04 hiển thị inline và lưu PNG canonical.
- cell-017 đến cell-018: expected/actual G2, limitations, checksum và bàn giao.

Notebook render bảng 02-A đến 02-L. Các hình dùng toàn bộ scope, không lấy mẫu, có ID, đơn vị, N, nguồn, caption và cách đọc:

- V02-01: removal cascade, nguồn Bảng 02-B.
- V02-02: phân bố số đội quan sát, nguồn Bảng 02-F1.
- V02-03: số match theo ngày UTC, nguồn Bảng 02-H.
- V02-04: quy mô split theo match và player rows, nguồn Bảng 02-J1.

V02-03 là not_applicable nếu không có ngày hợp lệ; notebook không tạo placeholder.

## IV. Nghiệm thu tích hợp

Notebook 01 rồi Notebook 02 đã chạy hết cell trong workspace runtime cô lập:

- Raw fixture gồm 16 aggregate rows, 6 match trên 5 ngày UTC và 1 death row.
- Fixture có exact duplicate với lineage khác, missing behavior, placement target không hợp lệ và identity conflict.
- Cleaning giữ target-invalid/missing-behavior cho đúng task, cách ly identity conflict và đối soát removal đạt.
- Chronology được xác định Grade B vì có 5 ngày nhưng không có exact-order evidence.
- Ratio 0.50/0.25/0.25 chỉ được ghi vào config của workspace fixture.
- Strategy auto thành chronological; whole UTC day blocks không bị xé.
- Giao train/validation/test bằng 0; checkpoint Notebook 02 completed.
- Tạo đủ 10 core artifacts và 4 PNG; PNG có chữ ký file hợp lệ.

## V. Kiểm thử

- test_w03_cleaning_roster_split.py: 12/12 đạt.
- test_notebook_logic_audit.py: 9/9 đạt.
- test_data_and_features.py: 2/2 đạt.
- test_w04_base_features.py: 7/7 đạt.
- test_no_drive_notebooks.py: 8 đạt, 1 skip All-in-One.
- test_phase_c_historical.py: 5/5 đạt.
- Toàn bộ unittest: 174 đạt, 3 bỏ qua có điều kiện.
- 14 notebook: code-cell syntax hợp lệ, execution_count null, outputs rỗng.

## VI. Giới hạn và điểm dừng

Committed configs/rq3.yaml vẫn để train_ratio, validation_ratio và test_ratio bằng null theo đặc tả: exact proportions phải được chốt sau khi xem inventory/time coverage của dữ liệu thật. Lần chạy Drive/full-data sẽ chủ động dừng tại cell split sau khi render chronology evidence. Nhóm phải chốt ba tỷ lệ có tổng bằng 1 rồi chạy lại từ cell split; notebook không dùng default ẩn.

Chưa chạy full-data, Drive, Colab, GPU hoặc All-in-One. Fixture chứng minh hợp đồng code, không phải kết quả nghiên cứu PUBG.

NB02-01 đến NB02-22 hoàn tất ở mức code và fixture. Task chưa nghiệm thu đầu tiên là NB03-01; đợt này dừng trước Notebook 03.