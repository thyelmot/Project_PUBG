# Tái nghiệm thu Notebook 03 theo Chuẩn Phương án 2

Ngày nghiệm thu: 2026-10-01

## I. Phạm vi

Đợt này xử lý Giai đoạn 5, từ NB03-01 đến NB03-15. Phạm vi là code và fixture, chưa phải full-data run. Notebook 04 và các giai đoạn sau chưa được bắt đầu.

Tài liệu đối chiếu:

- PUBG_RESEARCH_SPEC.md v3.0.
- PUBG_IMPLEMENTATION_PLAN.md, Giai đoạn 5.
- Quy tắc feature, target, structural missing, mode, leakage và checkpoint.

Không thay đổi RQ, cohort khoa học, target, split đã khóa, estimator hoặc metric.

## II. Lỗ hổng trước khi sửa

1. Công thức damage_per_kill, walk_ratio và assist_ratio tồn tại song song trong các module pandas và câu SQL của base pipeline.
2. Feature Dictionary chưa lưu đầy đủ formula, unit, dtype, level, allowed_targets, forbidden_targets, leakage_reason và các cờ phụ thuộc outcome.
3. player_match_base chưa có row_id và lineage trong schema đầu ra; chưa kiểm tra split coverage trước khi xuất bản.
4. Chưa có schema manifest và numbered-parts manifest để kiểm tra grain, kiểu cột, checksum và tổng số dòng.
5. Validation chỉ gắn nhãn null chung, chưa tách structural missing khỏi missing khác.
6. Notebook 03 cũ trình bày ngắn, một số nhãn hình không dấu, checklist Gate G3 mang tính khẳng định tĩnh và chưa chạy notebook thật để kiểm tra output.

## III. Thay đổi đã thực hiện

- Tập trung công thức cơ sở tại src/features/base.py; combat.py, movement.py và support.py chỉ còn wrapper mỏng.
- Tập trung công thức và predicate hợp lệ của normalized placement tại src/features/placement.py.
- Mở rộng FeatureRegistry thành từ điển 26 feature với metadata khoa học và allowlist tường minh.
- Bổ sung row_id chống collision, bảo toàn source_file/source_row và fail-fast nếu grain không hợp lệ.
- Kiểm tra match metadata và split assignments có một dòng mỗi match, không null và phủ đủ match sạch trước khi xuất bản.
- Giữ raw outcome, normalized_placement, valid_survival, valid_placement và cờ validity từ cleaning thành các trường riêng.
- Xuất player_match_base_schema.json và player_match_base_parts_manifest.json; numbered parts dùng hash(row_id), không tạo thư mục theo player hoặc match.
- Tách structural_missing_count và other_missing_count trong feature_validation_base.csv.
- Viết lại Notebook 03 bằng tiếng Việt có dấu, có công thức, cách đọc, expected/actual, giới hạn và bàn giao.

## IV. Bảng và hình được nghiệm thu

Notebook render:

- Bảng 03-A đến 03-F.
- Bảng 03-G1, 03-G2 và 03-G3.
- Bảng 03-H đến 03-L.
- V03-01: phân bố bốn feature dẫn xuất, reservoir sample tối đa 100.000 dòng, seed 42.
- V03-02: phân bố team-size mode và perspective mode trên toàn bộ base.
- V03-03: coverage target theo cùng mẫu số cleaned rows.

Mọi hình ghi scope, N hoặc sampling rule. Hình không được dùng thay bảng full-data và không diễn giải nhân quả.

## V. Bằng chứng thực thi

Fixture cô lập có:

- 8 dòng người chơi-trận.
- 4 trận.
- Solo, Duo, Squad và party_size chưa xác minh.
- TPP, FPP và perspective chưa xác định.
- Dòng có player_name thiếu nhưng lineage đầy đủ.
- Trường hợp kills = 0, total_distance = 0 và kills + assists = 0.
- Một survival target không hợp lệ và một placement target ngoài miền.

Kết quả:

- 8/8 dòng được bảo toàn.
- row_id không null và duy nhất.
- Feature Registry có đúng 26 feature.
- Tổng rows của numbered parts bằng 8.
- Đối chiếu tính tay có sai số tối đa không vượt 1e-12.
- Ba hình là tệp PNG hợp lệ.
- Checkpoint notebook/03_build_player_match.ipynb ở trạng thái completed và chứa 8 artifact.
- Notebook 04 đọc được player_match_base mà không tính lại base feature.

## VI. Kiểm thử

- test_w04_base_features.py: 8/8 đạt, gồm thực thi chính Notebook 03.
- test_notebook_logic_audit.py: 9/9 đạt.
- test_w00_env.py: 33 đạt, 1 skip có điều kiện trên Windows.
- test_data_and_features.py: 2/2 đạt.
- test_no_drive_notebooks.py: 8 đạt, 1 skip All-in-One.
- Toàn bộ suite: 175 test đạt, 3 skip có điều kiện, 0 lỗi.

## VII. Giới hạn và điểm tiếp tục

Chưa chạy dữ liệu thật, Google Drive, Google Colab, GPU hoặc notebook All-in-One. Notebook 03 là xử lý DuckDB/CPU nên không được gắn GPU chỉ để có accelerator.

Các phân bố và coverage từ fixture chỉ chứng minh logic, không phải kết quả nghiên cứu full-data. Mode unknown phải được mô tả bằng dữ liệu thật trước khi quyết định phân tầng.

Giai đoạn 5 hoàn tất ở mức code và fixture. Mục tiếp theo là NB04-01; chưa sửa nội dung Notebook 04 trong đợt này.