# Bộ minh chứng thực nghiệm để viết báo cáo PUBG

Phụ lục C và các thí nghiệm chính đã hoàn tất, kiểm chứng ngày 23/10/2026. Đây là bộ bảng/hình và nguồn số liệu; bản Báo cáo tổng kết ở Bước 6 chưa viết.

## Bắt đầu

- [Kế hoạch và toàn bộ kết quả](plan.md).
- [Kết quả test chính đã khóa](HISTORY_FULL_FINAL_RESULTS.md).
- [Diễn giải Phụ lục C](APPENDIX_C_RESULTS.md).
- [Manifest SHA-256 của mọi tệp](MANIFEST_SHA256.json). Checksum của ZIP được cung cấp ở tệp `reports/report-evidence-package-20261023.json` bên ngoài gói để tránh vòng lặp checksum.

## Dữ liệu và phạm vi

50.000 trận; train 1.000.000 dòng/34.614 trận, validation 480.891 dòng/7.373 trận; test 484.074 dòng/7.418 trận. Main dùng lịch sử nhân quả t'<t và không có placement. Tập test chỉ chấm một lần trước các phân tích phụ lục, không được mở/chấm lại khi hoàn thiện bộ này.

| Mục trong báo cáo | Nguồn trong gói | Phạm vi |
|---|---|---|
| Hiệu năng mô hình chính | [test_metrics.csv](main/test/test_metrics.csv) | Test đã khóa |
| Ablation A→B→C→D, hiệu số và CI | [ablation](main/test/ablation.csv), [gains](main/test/ablation_gains.csv) | Test đã khóa |
| Nhóm có/không lịch sử | [history_subset_metrics.csv](main/test/history_subset_metrics.csv) | Test đã khóa |
| Chẩn đoán lỗi | [báo cáo và danh mục](main/README.md) | Test đã khóa |
| RF GridSearchCV | [12 tổ hợp](appendix-c/appendix_rf_gridsearch_cv.csv), [refit validation](appendix-c/appendix_rf_cv_best_validation.csv) | GroupKFold train; validation |
| HGB GridSearchCV | [12 tổ hợp](appendix-c/appendix_hgb_gridsearch_cv.csv), [refit validation](appendix-c/appendix_hgb_cv_best_validation.csv) | GroupKFold train; validation |
| Đánh đổi α và Minority Recall | [12 điểm đủ chỉ số](appendix-c/appendix_alpha_tradeoff.csv), [Pareto](appendix-c/appendix_alpha_tradeoff.png) | Validation |
| Kiểm chứng recall | [72 recall từng lớp](appendix-c/appendix_alpha_class_recall.csv), [432 confusion cells](appendix-c/appendix_alpha_confusion.csv), [đồ thị](appendix-c/appendix_alpha_minority_recall.png) | Validation |
| Placement hậu nghiệm | [D/D+placement](appendix-c/appendix_placement_comparison.csv), [gains và CI](appendix-c/appendix_history_placement_gains.csv) | Validation |

Mô hình chính RF balanced đạt test Macro-F1 0,421898, CI 95% [0,420147; 0,423602], Accuracy 48,99%, Top-2 69,15%. RF α=.65 và HGB α=.50 tối ưu Macro-F1 trong lưới α của mỗi họ trên validation: 0,440113 và 0,441691; đây không phải điểm test mới và không thay lựa chọn chính.

## Cách diễn giải bắt buộc

- Phụ lục được phân tích sau khi mô hình/test chính đã khóa. Không dùng validation hậu nghiệm để chọn lại mô hình rồi báo như kết quả test chính.
- Minority được định nghĩa trước lượt replay bằng tỷ lệ train <1/K, K=6: DMR, Other, SMG, SR, Shotgun. Minority Recall là trung bình không trọng số của 5 recall validation, không pooled/weighted và không suy nhóm từ validation. Recall TP/(TP+FN), zero_division=0.
- α=1 cho Minority Recall cao nhất trong 6 điểm thử (RF 0,477945; HGB 0,502308), nhưng không tối ưu Macro-F1 và làm giảm Accuracy. Không ghép các chỉ số tốt nhất của những α khác nhau thành một mô hình.
- Chỉ khảo sát 6 mức α rời rạc, không chứng minh tối ưu trên miền liên tục. SD trong bảng CV là độ lệch chuẩn giữa 3 fold, không phải CI 95%.
- RF CV dùng α=1 với trọng số lớp cố định học trong fold, khác balanced_subsample của RF chính. α replay giữ tham số main balanced D; không dùng tham số RF/HGB tối ưu từ CV cho đường cong α.
- Placement là thông tin cuối trận; C2 chỉ là đối chiếu hậu nghiệm trên validation, không đưa vào hệ thống chính hoặc dùng để khẳng định mọi dạng rò rỉ khác đều bị triệt tiêu.

## Tái lập và kiểm chứng

Thiết kế gốc gồm 87 fits, thêm 12 replay α để bổ sung recall. Replay tái lập đúng 12 điểm cũ, params/weights/Pareto và 7 chỉ số (max delta 0); [reference check](appendix-c/alpha_recall_reference_check.json). RF/HGB dùng cùng fold audit. [Status hoàn tất](provenance/appendix-c-status-20261022.json); các submission/verification và snapshot code đóng gói ở `provenance/`. Main giữ nguyên bytes và manifest gốc tại `main/`. Không chứa model joblib hay dữ liệu parquet lớn. Các đường dẫn workspace ghi trong JSON provenance là dấu vết lịch sử, không phải liên kết cần chạy.
