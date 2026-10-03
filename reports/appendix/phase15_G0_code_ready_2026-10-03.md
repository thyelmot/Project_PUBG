# Báo cáo G0: nghiệm thu code và dữ liệu giả lập nhỏ

Ngày: 03/10/2026. Nguồn: PUBG_RESEARCH_SPEC.md v3.0, PUBG_IMPLEMENTATION_PLAN.md, AGENTS.md; nhật ký CHANGELOG_FIXES.md.

## I. Phạm vi và quyết định

Đây là báo cáo code-ready, không phải kết quả nghiên cứu chạy thật. Quyết định G0 cuối nằm ở mục IV, chỉ ghi sau khi QA-01..27 được nghiệm thu riêng. Không tự chuyển sang chạy giai đoạn 16. RUN-01..18, GPU/Drive/full-data và quyết định nghiên cứu phụ thuộc dữ liệu vẫn pending.

## II. Phiên bản và môi trường

- Windows 11 build 26200; Python 3.13.5 AMD64. CPU, không CUDA/cuML thực nghiệm.
- numpy 2.2.6; pandas 2.3.0; DuckDB 1.5.5; scikit-learn 1.7.0; scipy 1.16.0; matplotlib 3.10.3; pyarrow 23.0.1; nbformat 5.11.0; nbconvert 7.17.1; PyYAML 6.0.3. Đây là versions đã đo local, không phải pin được xác minh cho Colab.
- SHA-256 cây src: `1f9d78c1df08cd94436b77d8311df8560b00e7897a1da56a011955a4230b0ad1`.
- SHA-256 cây configs production: `880b57dbea8ec5e77709081a5c6954e947858dc0fdb4d0a0958f12a1240e6463`.
- Hash cây là SHA-256 của JSON sort_keys ánh xạ relative POSIX path sang SHA-256 từng file; src gồm 57 file .py, configs gồm 10 YAML.
- Release fixture cuối `20261003T141330112054Z_3ccd013f`, status fixture_locked, report_ready=False. Đọc lại bằng load_locked_release(allow_fixture=True) đạt. Không dùng release này làm production checkpoint.
- Cả 57 file nguồn trong reproduction khớp byte hiện hành. Sáu YAML fixture khác production có chủ đích: features/models/preprocessing/rq2/rq3/runtime, để gắn evidence giả lập, ngưỡng/K/split nhỏ và CPU; xem cấu hình cụ thể trong `phase15_completion_release_fixture_2026-10-03/release/reproduction/configs`. Không ghi các lựa chọn fixture ngược vào production.
- Bootstrap notebook 00-11 trùng bootstrap_source hiện hành; 12 trùng SUMMARY_BOOTSTRAP. Cell type/source/ID cả 13 notebook hiện hành trùng notebook thực chạy; nbformat hợp lệ, không error output.

## III. Lệnh, kết quả và bằng chứng

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PUBG_PHASE15_EVIDENCE_DIR='reports/appendix/phase15_completion_release_fixture_2026-10-03'
$env:PUBG_HISTORY_EVIDENCE_DIR='reports/appendix/phase15_completion_release_history_2026-10-03'
python scripts/run_phase15_tests.py
```

Lượt cuối: 225 tests/413.902s, 223 đạt, 2 skip có điều kiện, không failure/error. [Log](phase15_completion_release_regression_2026-10-03.log). Runner loại đúng hai method có đường chạy All-in-One; không thực thi hoặc tái tạo notebook tổng hợp.

- QA-01..08: [review tích hợp](phase15_integration_review_2026-10-03.md), kế hoạch ghi từng task/caller/cell/assertion.
- QA-09..27: [review hoàn tất](phase15_completion_audit_2026-10-03.md), nguồn bảng/hình tại II, README tại IV, 13 notebook/10 khối/ba mặt tại V, 15 câu audit tại VI và nghiệm thu riêng tại VIII.
- Actual raw 120 player-match/30 trận đến summary, 13 process; Grade C chặn history chính thức. History A/B/null/C được kiểm riêng. Scope fixture luôn được khai báo, không kết luận về PUBG thật.
- Đã mở 51 PNG và 5 history PNG, đối chiếu số liệu nguồn; mở lại 14 EDA sau sửa layout cuối. Kiểm tồn tại hoặc decode ảnh không được dùng làm chứng nhận đọc/khoa học.
- Tests leakage, null config, stale signature, required artifact, failed publication giữ bản tốt, single writer, reload, train-only, pairing và summary read-only đều đạt. Gate production fail-closed: NB04 pending đơn vị/eligibility dừng trước merge; NB07/08 threshold null dừng trước chọn/fit; G4 thiếu receipt/stale chặn final test; NB11 thiếu matrix/provenance/checksum chặn official release. Fixture approval được đánh dấu riêng, không thay phê duyệt nghiên cứu thật.

## IV. Kết luận cuối

G0 code-ready đạt: QA-01..27 được nghiệm thu riêng bằng code, assertion, tích hợp actual cells và khả năng đọc theo các báo cáo liên kết mục III. Giai đoạn 15 hoàn tất trong phạm vi local/synthetic. 316 task INV/INF/NB đã tích được đối chiếu lại; năm task phụ thuộc bằng chứng dữ liệu NB04-08/14/16, NB05-06, NB08-15 vẫn mở hợp lệ và có gate, không bị bỏ yêu cầu.

Không xác nhận chạy toàn dữ liệu, GPU T4/cuML, file ID/quyền/shortcut/quota Drive hay official G5. Không đưa fixture approval/config/checkpoint vào nghiên cứu thật. RUN-01..18 giữ mở. Người dùng chỉ cho phép chuẩn bị giai đoạn16, nên không chạy thật dù G0 đã đạt. Điểm tiếp tục là rà preflight cùng nhóm, thu bằng chứng và chốt quyết định tại gate tương ứng khi được phép; không tự chuyển notebook/model/config sang giá trị fixture.
