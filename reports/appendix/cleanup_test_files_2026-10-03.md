# Rà soát và dọn file tạm kiểm thử

Ngày: 03/10/2026. Nguồn đối chiếu: AGENTS.md, PUBG_RESEARCH_SPEC.md v3.0, PUBG_IMPLEMENTATION_PLAN.md, CHANGELOG_FIXES.md và báo cáo nghiệm thu từng giai đoạn.

## I. Nguyên tắc

Chỉ loại khỏi dự án file tạm không tham gia pipeline hoặc output trung gian đã được bản nghiệm thu thay thế. Không xóa code/config/tests/notebooks, raw, checkpoint, model, manifest hoặc snapshot nghiên cứu. Giữ báo cáo và mọi log đạt/lỗi, không xóa lịch sử nghiệm thu. Không sửa thuật toán, protocol hoặc trạng thái QA/RUN; không commit/push trong đợt dọn này.

Cache Python/pytest có thể tái tạo, được xóa trực tiếp. Script vá tạm/file rỗng và output cũ được chuyển có thể khôi phục tới thư mục ngoài repository nhưng trong workspace: `../_PUBG_TEST_CLEANUP_RECOVERY_20261003`. Đường dẫn tương đối bên trong được giữ nguyên. Đây là dọn repository, không phải giải phóng toàn bộ dung lượng đĩa.

## II. Mục được loại khỏi dự án

Các mục sau không được Git theo dõi và không phải dependency của code/test hiện hành. Mười hai thư mục output không có tham chiếu tên đầy đủ từ code, tests, kế hoạch hoặc báo cáo Markdown hiện hành; giữ lại bằng chứng nghiệm thu được chọn và các bản frozen/layout đã dùng review, kể cả khi báo cáo chỉ gọi tắt.

- patch.py: script replace một lần vào rq2_workflow, không là implementation canonical.
- temp_cell9.py: bản trích cell ingest cũ, có chuỗi print lỗi; không notebook hoặc module được import.
- scripts/cleaning_patch.py: bản vá cleaning cũ, không entry point hoặc module pipeline.
- scratch/patch_nb07_12.py: rỗng.
- scripts/apply_all_replaces.py
- scripts/audit_notebooks_detail.py
- scripts/check_conversation_modifications.py
- scripts/check_generator_escapes.py
- scripts/fix_notebook_newlines.py
- scripts/fix_parquet_file_key.py
- scripts/inspect_bundle.py
- scripts/inspect_pyc.py
- scripts/inspect_replaces.py
- scripts/inspect_splits_cleaning_replaces.py
- scripts/replay_src_edits.py
- scripts/restore_all_src_from_transcript.py
- scripts/restore_test_files.py
- scripts/test_exec_nb00.py

Các script từ apply_all_replaces đến test_exec_nb00 đều 0 byte. Giữ các script kiểm thử/kiểm chứng có nội dung, bao gồm smoke_test_07_real.py chưa được commit, vì không lấy untracked làm tiêu chí rác.

Thư mục output cũ trong reports/appendix được chuyển:

- phase13_fixture_2026-10-03
- phase13_fixture_final_2026-10-03
- phase13_fixture_final_review_2026-10-03
- phase13_fixture_verified_2026-10-03
- phase14_fixture_2026-10-03
- phase15_completion_current_fixture_2026-10-03
- phase15_completion_current_history_2026-10-03
- phase15_completion_final_fixture_2026-10-03
- phase15_completion_fixture_2026-10-03
- phase15_completion_verified_fixture_2026-10-03
- phase15_fixture_2026-10-03
- phase15_fixture_verified_2026-10-03

## III. Mục được giữ

Giữ các acceptance fixture giai đoạn10..15; history A/B/null/C; release fixture cuối; frozen/layout fixture và tờ xem; các output/tờ xem được báo cáo completion tham chiếu. Giữ archive kế hoạch, mọi .md/.csv/.log nghiệm thu, proposal Antigravity chưa rõ vai trò, ZIP chuyển giao và bản sao notebook/recovery ở workspace cha. Không đụng Data_PUBG, Paper, tài liệu học tập hoặc repository cha.

Fingerprint trước dọn, SHA-256 JSON sort_keys của relative path sang SHA-256 từng file, bỏ cache Python:

| Phần được bảo vệ | File | Hash |
| --- | --- | --- |
| src |57|1f9d78c1df08cd94436b77d8311df8560b00e7897a1da56a011955a4230b0ad1|
| configs |10|880b57dbea8ec5e77709081a5c6954e947858dc0fdb4d0a0958f12a1240e6463|
| notebooks, cả bản tổng hợp đang có thay đổi cũ |14|5faa16c47775f4ac49ecfa49ee9d2e2823ab1c9a16ed5ece71c46e297d8cd257|
| tests |30|a84fb49d5fcf91e1ab8312a8b1de4e6d3fa50f11b23236d3387b19355316b0b9|
| data trong repository |2|bae91f8bd9003155fce7a38ec6ecc46ba4319dd253d11d52c80c03483759271d|
| artifacts |35|3df358945f25e4a17acb251564061259a95c3018a9153a2f349d0236d9a07589|

## IV. Kiểm chứng sau dọn

Chưa thực hiện tại thời điểm lập danh sách. Kết quả sẽ nối sau khi chuyển/xóa an toàn và đối chiếu hashes, nbformat, release và đường dẫn bằng chứng.

Kết quả sau thực hiện ngày03/10/2026:

- Chuyển đúng30mục (18script/file và12thư mục output), gồm3.328file/216.402.768byte, khoảng206,38MiB. Bản khôi phục có đủ3.328file; không ghi đè mục có sẵn. Đây là di chuyển trên cùng workspace, không giảm dung lượng toàn ổ đĩa.
- Xóa9thư mục cache Python/pytest, gồm93file/1.608.710byte (khoảng1,53MiB). Cache không có bản khôi phục, nhưng Python/pytest tự tạo lại khi cần. Xóa hai thư mục rỗng .tmp vàscratch trong Project_PUBG.
- Đã validate toàn bộ source/destination absolute paths trước thao tác, nằm dưới đúng root chỉ định, không reparse point; mọi mục chuyển đều untracked. Không dùng git clean/reset hoặc xóa đệ quy root dự án.
- Hash và số file của src/configs/notebooks/tests/data/artifacts sau dọn khớp hoàn toàn bảngIII. Không có tracked deletion. Notebook tổng hợp có thay đổi cũ vẫn giữ byte nguyên trạng, không chạy/sinh lại.
- 13regular notebooks nbformat hợp lệ. Đọc lại release20261003T141330112054Z_3ccd013f với allow_fixture=True thành công, fixture_locked/report_ready=False;15namespace nghiệm thu/review được kiểm còn nguyên, cùng tờ xem vàlog. Không coi kiểm này là full-data/GPU/Drive test.
- Không chạy lại225tests vì không thay source/config/tests/notebooks hoặc artifact hoạt động; kiểm trực tiếp nội dung/hash, schema và release thay vì tạo thêm output kiểm thử không cần thiết. Không tạo cache mới trong kiểm chứng bằng python -B.
- reports/appendix giảm từ khoảng707,77MiB xuống501,41MiB, phần đã chuyển vẫn nằm trong recovery. Git chỉ thêm báo cáo dọn và nối nhật ký; không commit/push.

Khôi phục nếu cần: tìm đúng relative path ở `../_PUBG_TEST_CLEANUP_RECOVERY_20261003`, chuyển lại về Project_PUBG cùng relative path sau khi kiểm tra đích chưa tồn tại; không ghi đè file mới. Không cần khôi phục cache để chạy dự án.
