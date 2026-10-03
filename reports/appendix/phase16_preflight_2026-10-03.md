# Giai đoạn 16: chuẩn bị và kiểm tra điều kiện

Ngày 03/10/2026. Phạm vi do người dùng xác nhận: chỉ chuẩn bị và kiểm tra điều kiện, chưa chạy dữ liệu lớn. Đây không phải nghiệm thu RUN, G1-G5 hoặc Colab/Drive/GPU thật.

## I. Kết quả kiểm tra local

| Điều kiện | Quan sát | Kết luận và việc cần làm |
| --- | --- | --- |
| G0 | Cập nhật cuối03/10: QA-01..27 nghiệm thu riêng code/fixture;225tests/413.902s,223đạt/2skip; báo cáo G0 đã lưu | G0 code-ready đạt, không tự mở thực thi: người dùng chỉ cho phép chuẩn bị, chưa cho chạy lớn; G1-G5production chưa xác nhận |
| Notebook | Có 13 file canonical 00-12; sinh từng file bằng --only | Đồng bộ source/config/notebook cùng phiên bản; không chạy All-in-One |
| Cấu hình storage | Cell dùng drive, root /content/drive/MyDrive/PUBG_Project/Project_PUBG, require_existing=True, batch50000 | Không đổi các giá trị đã chốt |
| RQ2/backend | per_mode; RQ2/RQ3 yêu cầu cuda | Cần runtime có backend hỗ trợ; không silent CPU fallback |
| Raw local | ../Data_PUBG có 10 CSV, tổng 20.281.921.579 byte, chỉ đọc metadata filesystem | Chưa hash/parse toàn nguồn; không khẳng định dữ liệu trên Drive giống local |
| Checkpoint local | Manifest hiện hữu chỉ có notebook/01_download_validate.ipynb, trạng thái running, artifacts rỗng | Không reuse hoặc gọi completed; giữ nguyên, xác minh manifest thật trên Drive khi được phép |
| Release local | Không có artifacts/manifests/final_results_manifest.json production | Không lấy release fixture làm kết quả nghiên cứu hoặc đồng bộ vào canonical production |
| Môi trường local | Python 3.13.5, Windows 11; dung lượng volume đo tại thời điểm kiểm tra | Không phải môi trường Colab, VRAM, peak RAM hoặc quota tài khoản Drive |
| Quyền/shortcut/file ID | Chưa truy cập dịch vụ trong đợt này | RUN-01/12/13/14 chưa xác minh; cùng đường dẫn hoặc cùng tên chưa chứng minh cùng file ID |

## II. Các quyết định vẫn chờ bằng chứng

| Trước bước | Quyết định/điều kiện | Nơi ghi |
| --- | --- | --- |
| 01/G1 | Inventory đủ shard, hash/schema/parse/count, download date thật nếu tải nguồn | source_inventory và source metadata; không bịa download date |
| 02/G2 | Chronology theo evidence; train/validation/test ratio vẫn null | preprocessing.yaml chronology; rq3.yaml split; split manifest |
| 04 | event_time_unit_status, enemy_kill_eligibility_status, min_valid_duration_status còn pending | features.yaml combat_timing; evidence nguồn/consistency/roster/cause |
| 07/G3 | party_size_mapping, minimum_games_threshold, K theo Solo/Duo/Squad, selection_reason còn null | rq2.yaml và diagnostics receipt; outcomes không được chọn K/ngưỡng |
| 08 | minimum_history_threshold, reason/hash, evaluation_protocol, availability policy/status/evidence còn pending | rq3.yaml historical; Grade C chặn S2/P3 hợp lệ, không giả history |
| 09/G4 | Features/models/params/comparison/bins/design và reviewer approval đúng phiên bản | rq3_decision và selection lock; không dùng approval fixture |
| 11/G5 | Explicit selection, required matrix, provenance và figures report-ready | finalization_selection; immutable release và canonical manifests |

Null optional như diagnostic sample size/C2 cap không tự động là lỗi. Khi nhánh cần chúng, gate phải yêu cầu evidence và không tự suy ngưỡng. Không chép min_games=1/K=2/split=.6/.2/.2 của fixture vào production.

## III. Quy trình bàn giao khi được phép chạy thật

1. Chốt một người ghi, project folder ID, quyền Editor và shortcut về đúng root. Xác minh source/config/notebooks cùng phiên bản trước bootstrap.
2. Đo RAM/disk/VRAM của runtime thật, kiểm quota Drive riêng; dự trù raw/interim/processed/spill/staging. Không dùng số đo Windows để bảo đảm Colab chạy được.
3. Chạy từng notebook, dừng tại gate chưa chốt. Diagnostics và quyết định của nhóm phải được lưu trước bước final; không hứa Run All một lần.
4. Sau stage thành công: đọc lại artifact, kiểm schema/count/checksum/signature/status. Sau notebook thành công: lưu bản có output và cập nhật đúng file ID trên Drive, thay đúng file local; không tạo hậu tố số, không thay bản tốt bằng bản đang lỗi.
5. Runtime mới chạy storage/bootstrap/init, chỉ reuse compatible completed stages. Khi resource_limited/quota: dừng, giữ committed checkpoint, ghi notebook/cell/stage/path/error và báo người dùng; không lấy mẫu hoặc đổi estimator để ép hoàn tất.
6. NB11 chỉ khóa khi đủ required matrix hoặc exception được protocol cho phép. NB12 đọc release cụ thể, không train/build/select mới. Bàn giao kèm release ID, manifest/hash, scope/N, environment, pending và bước tiếp theo.

Các bản fixture tại reports/appendix/phase15_fixture_* chỉ dành cho kiểm thử; không thay processed/model/checkpoint/release nghiên cứu trên Drive. Không thao tác Drive, không download/upload notebook và không chạy dữ liệu thật trong đợt preflight này.

## IV. Điểm tiếp tục

Cập nhật sau hoàn tất15: xem [báo cáo G0](phase15_G0_code_ready_2026-10-03.md) và [review completion](phase15_completion_audit_2026-10-03.md). Các nhận định G0 pending trước đây là trạng thái lịch sử trước QA-09..27. RUN-01..18 giữ mở; không chạy dữ liệu thật/Drive/GPU trong preflight.

Hoàn tất phần chuẩn bị tài liệu, chưa hoàn thành giai đoạn 16. RUN-01..18 đều giữ mở. QA-01..27/G0 đã khép ở mức code-ready. Bước tiếp theo là người dùng kiểm tra báo cáo và duyệt phạm vi chạy thật nếu muốn; khi được phép, bắt đầu RUN-01 và dừng tại các gate thiếu bằng chứng, không nhảy sang 07 hoặc reuse manifest running local.
