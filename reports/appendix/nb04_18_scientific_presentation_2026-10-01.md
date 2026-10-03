# Báo cáo nghiệm thu Giai đoạn 6, Notebook 04

Ngày: 2026-10-01

## I. Phạm vi

Đợt này chỉ kiểm thử và hoàn thiện Notebook 04 theo NB04-01 đến NB04-18. Không sửa Notebook 05 trở đi, không chạy All-in-One, không chạy full-data, Google Drive, Colab hoặc GPU.

Tài liệu đối chiếu:

- `PUBG_RESEARCH_SPEC.md` v3.0, mục 4.2, 15, 27, 28, 37 và 64.
- `PUBG_IMPLEMENTATION_PLAN.md`, D01, D07 và NB04-01 đến NB04-18.
- `AGENTS.md` và Ponytail skill mức full.

## II. Kết quả logic

- Event timing tuyệt đối chỉ loại missing match/killer, self-kill, time âm hoặc không hữu hạn và unmatched match. Missing victim/cause chỉ được audit, không tự loại timing tuyệt đối và không được gọi là enemy-kill đã xác minh.
- Eligibility enemy-kill, đơn vị event time và ngưỡng duration 60 giây đều giữ trạng thái pending cho tới RUN-04 có bằng chứng dữ liệu thật.
- Event identity ưu tiên `(source_file, source_row)`. Khi lineage không có, fallback được ghi `pending_source_lineage`; không tuyên bố deterministic hoặc verified.
- Hai event cùng giây được giữ. Potential replay được gắn cờ, không tự deduplicate.
- Absolute timing được bảo toàn khi event time vượt duration proxy; event đó không tham gia phase timing và không bị clip.
- Global aggregation dùng `SUM(time)`, `COUNT(*)` và `MIN(time)` trên toàn bộ shard; không average chunk means.
- Phase dùng Early `[0,1/3)`, Mid `[1/3,2/3)`, Late `[2/3,1]`; mẫu số là `phase_eligible_kill_count`.
- LEFT JOIN yêu cầu bảng timing duy nhất theo `(match_id, killer_name)` và bảo toàn đúng số player-match.
- D07 được thể hiện bằng các trạng thái riêng: no-kill/no-event, aggregate kill nhưng thiếu event, exact, partial và event vượt aggregate.
- `kill_discrepancy.csv` lưu đủ mọi player-match. Coverage event và coverage player-match có mẫu số riêng.
- Feature Registry ghi timing tuyệt đối bằng đơn vị nguồn đang pending; phase descendants truy vết tới `estimated_match_duration` và bị cấm cho survival.

## III. Khả năng đọc và trực quan

Notebook render bảng 04-A đến 04-M:

- input/provenance và ba quyết định pending;
- event audit, eligibility funnel và toàn bộ cờ join/coverage;
- timing summary toàn scope và ví dụ phase boundary;
- coverage theo mode/trạng thái, discrepancy summary, top rows và ví dụ semantic;
- expected/actual stage check cùng artifact handover có kích thước và checksum.

Notebook tạo ba hình:

- V04-01: phân bố `first_kill_time`; reservoir sample chỉ dùng để vẽ và ghi rõ cỡ mẫu.
- V04-02: tổng event Early/Mid/Late tính trên toàn scope.
- V04-03: coverage theo trạng thái ở grain player-match.

## IV. Bằng chứng kiểm thử

- `python -m unittest discover -s tests -p test_w05_combat_timing.py -v`: 10/10 đạt, gồm chạy toàn bộ cell Notebook 04 trên fixture cô lập.
- Fixture Notebook 04: 4 player-match, 2 match, 6 event; bảo toàn 4/4 dòng; discrepancy 4/4 dòng; 4 absolute event và 2 phase event; 9 artifact; checkpoint `notebook/04_combat_timing.ipynb=completed`; ba file PNG có signature hợp lệ.
- `python -m unittest discover -s tests -p test_w04_base_features.py -q`: 8/8 đạt.
- `python -m unittest discover -s tests -p test_data_and_features.py -q`: 2/2 đạt.
- `python scripts/verify_notebooks_00_06.py`: Notebook 00-06 đều có cấu trúc và cú pháp hợp lệ; Notebook 04 có 16 cell, gồm 8 markdown và 8 code.
- `python -m unittest discover -s tests -v`: 180 test đạt, 3 skip có điều kiện, 0 lỗi.
- `test_no_drive_notebooks.py`: 8 test đạt, 1 skip có chủ đích vì All-in-One không được phép chạy.
- `python -m py_compile ...`: đạt cho module, registry, generator và test đã sửa.
- `git diff --check` trên các file NB04: không có lỗi whitespace mới.

## V. Giới hạn và trạng thái bàn giao

Fixture chỉ chứng minh logic, tích hợp và khả năng đọc; không phải kết quả nghiên cứu. Ba quyết định về đơn vị event time, enemy-kill eligibility và ngưỡng 60 giây vẫn pending. Full-data, Drive, Colab, quota và GPU chưa được kiểm tra. Notebook 04 là bước CPU/I/O, không cần GPU.

Không gọi hoàn tất NB04 là Gate G4. Theo kế hoạch, Gate G4 thuộc giai đoạn modeling sau khi recipe và paired comparisons đã được đăng ký. Kế hoạch chưa được tích trong đợt worker; Codex điều phối sẽ review cuối và quyết định trạng thái task.

## VI. Đính chính sau review vòng 2

Phần nghiệm thu ban đầu đã gọi fixture có ba quyết định còn `pending` là completed. Kết luận đó không đúng với research gate RUN-04 và được đính chính như sau:

- `victim_name` và `killed_by` là cột tùy chọn. Khi thiếu hẳn cột, core timing vẫn chạy bằng `match_id`, `time`, `killer_name`; self-kill, victim-roster và cause audit ghi rõ unavailable thay vì làm notebook lỗi.
- Lineage được kiểm tra ở cả cấp cột và cấp giá trị. Row thiếu `source_file` hoặc `source_row` nhận khóa `pending_unverified_row:*`; toàn stage có trạng thái `partial_source_lineage_pending`, không được gọi verified.
- Metadata được kiểm tra many-to-one trên khóa chuẩn hóa `trim(match_id)`, cùng chuẩn với phép join. Hai khóa `m1` và ` m1` bị chặn như duplicate canonical key.
- Cấu hình production vẫn giữ ba trạng thái pending. Với cấu hình này, Notebook 04 tạo `combat_timing`, event audit, event ledger, V04-01 và V04-02; commit checkpoint `combat_timing_diagnostics`; ghi notebook stage `blocked` với mã `RUN-04`; sau đó dừng trước merge, `player_match_features`, V04-03 và bàn giao NB05.
- Chỉ fixture tạm thời gắn cả `status=verified` và evidence không rỗng cho ba quyết định mới được chạy hết nhánh tích hợp. Fixture không sửa `configs/features.yaml` của dự án và không phải bằng chứng nghiên cứu.

Bằng chứng vòng 2:

- `python -m unittest discover -s tests -p test_w05_combat_timing.py`: 14/14 đạt, gồm cả đường pending expected-stop và đường verified fixture full-commit.
- `python -m unittest discover -s tests -q`: 184 test đạt, 3 skip có điều kiện, 0 lỗi.
- `python scripts/verify_notebooks_00_06.py`: 7/7 notebook đạt cấu trúc và cú pháp; NB04 có 16 cell.
- `python -m py_compile src/features/combat_timing.py src/utils/generate_notebooks.py tests/test_w05_combat_timing.py`: đạt.

Vì ba bằng chứng dữ liệu thật chưa có, trạng thái khoa học hiện tại của NB04 là expected-stop tại RUN-04, chưa phải completed và chưa đủ điều kiện chuyển NB05.

## VII. Đính chính cuối về evidence và event identity

- Research gate chỉ chấp nhận evidence là chuỗi không rỗng. Giá trị YAML `null`, boolean hoặc kiểu dữ liệu khác không được chuyển thành văn bản rồi coi là bằng chứng.
- `enemy_kill_eligibility_verified` dùng đúng kết quả requirement gồm cả `status=verified` và evidence hợp lệ. Chỉ đổi status mà thiếu evidence vẫn cho kết quả `False` và NB04 vẫn dừng RUN-04.
- `(source_file, source_row)` được kiểm tra uniqueness ở cấp giá trị. Các event trùng source identity vẫn được bảo toàn, được gắn `flag_duplicate_source_identity`, đếm trong audit và làm `event_identity_status=source_lineage_conflict_pending`.
- Targeted suite cuối có 16/16 test đạt, bao gồm evidence `None`/`False`, enemy status verified nhưng thiếu evidence và hai event trùng source identity không bị deduplicate. Full suite cuối có 186 test đạt, 3 skip có điều kiện và 0 lỗi.
