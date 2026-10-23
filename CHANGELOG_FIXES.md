# Nhật ký thay đổi local sau khi clone

## 23/10/2026 - Nhập gói kết quả Kaggle đầy đủ

- Yêu cầu: đưa file trong results.zip vào cấu trúc dự án mới nhất.
- Tài liệu đối chiếu: AGENTS.md ở workspace; PUBG_RESEARCH_SPEC.md X-XI và PUBG_IMPLEMENTATION_PLAN.md V trong snapshot ZIP. Bản clone hiện tại đã bỏ các tài liệu này ở gốc; không khôi phục ghi đè lựa chọn đó.
- File thay đổi: thêm results/ nguyên snapshot, tools/import_results.py, tests/test_import_results.py, RESULTS.md và nhật ký này; cập nhật README.md/.gitignore. Ghi nối Project_PUBG/CHANGELOG_FIXES.md theo quy tắc workspace.
- Vị trí kết quả: results/PUBG_Coursework_v511_S09_S10/, gồm data/full, outputs/full, config/code/notebook/manifest của lần chạy. Ảnh xuất bổ sung ở results/__results___files/. Không đè lên src/config/output/report hiện hành.
- Nội dung nhập: 510 file từ ZIP, 17.906.744.339 byte; giữ ZIP gốc. Import vào staging mới, kiểm CRC khi giải nén, đọc lại SHA256 từ đĩa, rồi rename vào results sau khi đạt.
- Kiểm: 3 kiểm thử fixture đạt (nhập nguyên byte và chặn đích có sẵn, sai checksum không publish, path traversal bị chặn). Gói thực: 466 entry handoff khớp SHA256; checkpoint S01-S10 đều completed và khớp handoff; kiểm header42Parquet và inventory1release. Biên nhận results/IMPORT_VERIFICATION.json, thời gian257,79giây.
- Ảnh hưởng: không thay mục tiêu/cohort/feature/target/split/leakage/estimator/metric/checkpoint; chỉ chép và kiểm file. Không chạy lại notebook, deserialize joblib hoặc sửa metadata gốc. Không sửa src/generator nên không sinh lại notebook nghiên cứu.
- Giới hạn: không kiểm lại raw nguồn, không giải mã toàn bộ dữ liệu Parquet hoặc nghiệm thu số học mô hình. results và staging bị Git ignore; chưa commit/push. Lịch sử nhật ký gốc của lần chạy vẫn nằm nguyên trong bằng chứng đã lưu nếu có; nhật ký này chỉ ghi đợt nhập local.

## 23/10/2026 - Dọn bản sao xuất ảnh và văn bản trung gian

- Yêu cầu: dọn file không cần thiết trong Project_PUBG_latest sau nhập results.zip.
- Đối chiếu: SPEC X-XI/PLAN V trong snapshot và AGENTS workspace; giữ nguyên snapshot, release và khả năng truy vết.
- Đã dọn 47file/3.755.100byte: 42PNG xuất kèm Kaggle trong results/__results___files đều có SHA256 trùng ảnh gốc; 5file report/evidence/*.txt chỉ là bản văn bản trung gian từ notebook/PDF (pubg_S00_S06, pubg_S07, pubg_S08, pubg_S09_S10_S11_S12, reference).
- Cách dọn: chuyển từng file vào PUBG_latest_cleanup_recovery_20261023_184153 ngoài dự án; RESTORE_MANIFEST.json ghi vị trí/hash/bản gốc tương ứng. Hash sau chuyển khớp. Lệnh ban đầu có bước xóa thư mục rỗng bị bộ kiểm tra chặn trước khi chạy; phương án hoàn tất chỉ di chuyển file và giữ thư mục rỗng.
- File tài liệu: cập nhật RESULTS.md giải thích số file nhập ban đầu và ảnh xuất trùng đã dọn; ghi nối nhật ký local và Project_PUBG/CHANGELOG_FIXES.md.
- Ảnh hưởng: không sửa data/model/prediction/config/code/checkpoint/manifest trong snapshot; không đổi mục tiêu, cohort hoặc phương pháp. Không chỉnh src/generator nên không tái sinh notebook. Báo cáo, gói ZIP, bằng chứng CSV/index, tests và notebook kết quả được giữ.
- Kiểm: file gốc của 42ảnh còn nguyên; đối chiếu inventory snapshot đủ entry/byte, checkpoint và handoff khớp; phụ thuộc ảnh/bảng LaTeX tồn tại, ZIP CRC đạt. Chưa commit/push.
- Giới hạn: di chuyển có khôi phục không giải phóng dung lượng ổ đĩa; không giải mã hoặc tính lại kết quả nghiên cứu trong lần dọn này.

## 23/10/2026 - Hoàn thiện báo cáo từ bộ kết quả đầy đủ

- Yêu cầu: đọc lại kết quả và hoàn thiện báo cáo sau khi có results.zip.
- Tài liệu đối chiếu: SPEC VI-VIII và PLAN S09-S12 trong snapshot, CSV/manifest đầy đủ; tham khảo tài liệu chính thức scikit-learn về KMeans, OLS và metric. Giữ giảng viên, thành viên/email và bìa căn giữa có khung.
- File thay đổi: Project_PUBG_latest/report/main.tex, README.md, SOURCE_MAP.md, thêm build_full_results.py, evidence/full_results và bảng/hình cập nhật; tái tạo PDF và ZIP báo cáo. Bản trước lưu ở PUBG_report_before_full_results_20261023_184649. Không sửa src/generator notebook nên không tái sinh notebook nghiên cứu.
- Nội dung: chuyển bảng từ preview sang CSV đầy đủ; bổ sung tóm tắt, GradeC và cohort/hash, allowlist19đặc trưng P2, coverage timing, retention development/full, K/ARI và tâm cụm, test đủ7thí nghiệm, sai số theo miền placement, hệ số và đa cộng tuyến, tài liệu tham khảo và truy vết release.
- Kiểm số liệu: đọc81CSV và đối chiếu SHA256 với handoff; model_metrics đủ36dòng/7thí nghiệm; tổng coverage67.369.231; tổng full profiles1.668.136; bản CSV nguồn đính kèm khớp hash. Không chạy lại S, nạp joblib hoặc sửa snapshot.
- Kiểm sản phẩm: XeLaTeX hai lượt đạt, PDF34trang/18bảng/10hình; không overfull/undefined/missing glyph; xem contact sheet toàn34trang và trang chi tiết; đủ phụ thuộc LaTeX và ZIP CRC/nội dung đạt. Các tỷ lệ cải thiện MAE được tính từ số gốc, không từ giá trị đã làm tròn.
- Ảnh hưởng: chỉ phân tích và trình bày kết quả đã lưu; giữ protocol/cohort/feature/target/split/estimator/metric/checkpoint. Không tuyên bố mô hình survival đạt yêu cầu, không đổi K sau xem outcome, chưa có CI.
- Giới hạn: chưa xác minh lại raw hoặc chẩn đoán nguyên nhân survival bất thường; không thay báo cáo bằng một đợt huấn luyện mới. Cập nhật local, chưa commit/push.

## 23/10/2026 - Chuẩn bị commit và xuất bản các thay đổi hiện hành

- Yêu cầu: commit lên GitHub sau khi đổi tên thư mục tài liệu thành `docs`.
- Tài liệu gốc đã đối chiếu: `PUBG_Coursework/docs/PUBG_RESEARCH_SPEC.md`, `PUBG_IMPLEMENTATION_PLAN.md`, `AGENTS.md` và các mục nhật ký nhập kết quả, dọn dẹp, hoàn thiện báo cáo ở trên.
- File thay đổi trong đợt này: thêm `docs/` gồm bốn tài liệu đã tổ chức lại từ `PUBG_Coursework`, cập nhật liên kết README và ghi nhật ký. Giữ nguyên các thay đổi báo cáo, công cụ nhập kết quả và kiểm thử đã thực hiện ở các đợt trước.
- Nội dung xuất bản: mã công cụ nhập, kiểm thử, báo cáo PDF/LaTeX, bằng chứng CSV dùng trong báo cáo, tài liệu và việc dọn các bản trích văn bản trung gian. Không đưa `results/`, ZIP dữ liệu gốc, thư mục khôi phục hoặc tài liệu môn khác lên Git.
- Ảnh hưởng: chỉ tổ chức tài liệu và xuất bản sản phẩm hiện có; không thay mục tiêu, cohort, feature, target, split, leakage rule, estimator, metric, checkpoint hay chạy lại notebook.
- Kiểm thử: bốn tài liệu sao chép vào clone khớp SHA256 nguồn; nhánh local và origin/main cùng điểm trước commit. Kết quả kiểm thử importer, kiểm tra gói báo cáo, danh sách staged và SHA sau push được kiểm tra trong đợt bàn giao.
- Giới hạn: không chạy lại toàn bộ pipeline hoặc mô hình GPU; `results/` chỉ có ở máy local, không có trong bản clone GitHub. Kết quả push và mã commit được báo ở phản hồi bàn giao.
- Kết quả kiểm trước commit: 3/3 kiểm thử importer đạt; PDF đọc được 34 trang, ZIP LaTeX kiểm CRC đạt; 60 file thêm/sửa và 5 bản trích TXT đã dọn được staged, không có snapshot/raw hay file trên 50 MiB. Cảnh báo dòng trống cuối ba tài liệu được giữ nguyên để bảo toàn bản sao; không ảnh hưởng nội dung hoặc thực thi.
