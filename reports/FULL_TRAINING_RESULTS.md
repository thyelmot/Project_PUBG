# Kết quả train dài PUBG — 21/10/2026

Đã hoàn tất [Kaggle version 1](https://www.kaggle.com/code/sangtranminh211/pubg-weapon-full-plan-20261021): **readiness passed**, chưa đánh giá test (`test_evaluated=false`). RF cân bằng được chọn bằng macro-F1 validation; chưa thay đổi lựa chọn hoặc fit lại train+validation.

## Quy mô và kiểm chứng

- Bundle: `artifacts/kaggle-full-metadata-fixed-20261021/`; đủ 32 source hash khớp snapshot đã gửi.
- Lấy mẫu 50.000 trận / 4.525.712 sự kiện từ chunk 0; sau xử lý còn 49.406 trận có dữ liệu hợp lệ. Split manifest không có match ID lặp giữa các tập.
- Train: 1.000.000 dòng / 34.614 trận; validation: 484.965 dòng / 7.374 trận; test giữ lại: 488.107 dòng / 7.418 trận. Số liệu test là metadata preprocessing, không phải kết quả đánh giá.
- Source SHA-256: `8c40331ba496bdda621bf061b110e9c953a5cd723f0e98a13c4e82b945926e74`.
- Fixed split SHA-256: `3cd3e1a76c8679b510ee791bbd280a3684a51ffc03676c39ffbcc7466296c8ce`.
- Pytest trên Kaggle: **58 pass**, 0 fail/error/skip; 15 trials, 11 pipeline, đủ 6 họ; không dùng quick, placement, tempered weights hoặc no_position.
- Đã đối chiếu checksum dataset manifest, experiments, trials, selection; mọi trial không có convergence/runtime warning hoặc library warning. Diagnostics passed: checksum pipeline, không trùng trận train/validation, nạp lại tái lập macro-F1, xác suất hữu hạn/tổng 1, không đọc test.
- RF ở cả hai chế độ cân bằng thử đúng hai cấu hình: 200 cây / depth 18 / leaf 5 / max_samples 0.20 và 300 cây / depth 18 / leaf 5 / max_samples 0.15. A/B/C cùng cấu hình HGB và chế độ cân bằng.
- Log chuyển notebook sang HTML sau tính toán có SyntaxWarning của mistune/nbconvert; đây không phải cảnh báo fit model và không nằm trong trials.

## Kết quả validation

| Pipeline | Macro-F1 | Weighted-F1 | Accuracy | Train macro-F1 | Gap |
|---|---:|---:|---:|---:|---:|
| majority_plain_full | 0.0986 | 0.3637 | 0.5270 | 0.0985 | -0.0001 |
| logistic_balanced_full | 0.2373 | 0.2648 | 0.2582 | 0.2411 | 0.0038 |
| naive_bayes_plain_full | 0.2153 | 0.4085 | 0.4342 | 0.2160 | 0.0007 |
| decision_tree_plain_full | 0.2165 | 0.4608 | 0.5507 | 0.2365 | 0.0201 |
| decision_tree_balanced_full | 0.2493 | 0.2914 | 0.2787 | 0.2658 | 0.0165 |
| random_forest_plain_full | 0.2107 | 0.4601 | 0.5563 | 0.2333 | 0.0226 |
| random_forest_balanced_full | 0.3020 | 0.4487 | 0.4328 | 0.3551 | 0.0530 |
| hist_gradient_boosting_plain_full | 0.2141 | 0.4615 | 0.5564 | 0.2264 | 0.0122 |
| hist_gradient_boosting_balanced_full | 0.2622 | 0.3102 | 0.2959 | 0.2785 | 0.0163 |
| hist_gradient_boosting_balanced_distance | 0.2134 | 0.2476 | 0.2497 | 0.2209 | 0.0076 |
| hist_gradient_boosting_balanced_context | 0.2499 | 0.2994 | 0.2909 | 0.2605 | 0.0106 |

Điểm train ở bảng dùng cùng cách lấy mẫu stratified 20.000 dòng, không phải toàn bộ 1 triệu dòng. Mô hình được chọn: `random_forest_balanced_full`, 300 cây, depth 18, leaf 5, max_samples 0.15, class_weight=balanced_subsample.

## RF được chọn: từng lớp

| Lớp | Precision | Recall | F1 | Số thật | Số dự đoán |
|---|---:|---:|---:|---:|---:|
| AR | 0.7359 | 0.4753 | 0.5776 | 255,553 | 165,068 |
| DMR | 0.1887 | 0.1737 | 0.1809 | 38,093 | 35,068 |
| LMG | 0.0000 | 0.0000 | 0.0000 | 3,135 | 2 |
| Other | 0.4619 | 0.3841 | 0.4194 | 47,392 | 39,408 |
| SMG | 0.2074 | 0.1923 | 0.1996 | 60,380 | 55,991 |
| SR | 0.2225 | 0.6115 | 0.3262 | 21,600 | 59,378 |
| Shotgun | 0.2981 | 0.6593 | 0.4106 | 58,812 | 130,050 |

**LMG vẫn F1 = 0**: chỉ 2 dự đoán LMG và không có dự đoán đúng trên 3.135 mẫu thật. Recall AR là 47,53%; accuracy của RF cân bằng thấp hơn majority (52,70%) trong khi macro-F1 cao hơn (0,3020 so với 0,0986). Đây là đánh đổi mất cân bằng cần giữ trong báo cáo.

## Ablation và tài nguyên

HGB cân bằng: A chỉ khoảng cách **0.2134**; B thêm thời gian **0.2499**; C full **0.2622**. Hiệu số mô tả A→B **+0.0365**, B→C **+0.0123**; chưa có CI test để kết luận thống kê.

Tổng thời gian đo trong runner: **2193.48 giây (36.56 phút)**, gồm pytest subprocess, EDA, preprocessing, training, diagnostics; không gồm cấp máy/xuất artifact. Tổng thời gian fit + predict validation của 15 trial: **1454.71 giây**. RSS đỉnh tiến trình cha: **5.08 GiB**; đây là high-water tích lũy, không phải RAM riêng mỗi model hoặc toàn bộ máy/subprocess.

Permutation importance trên mẫu validation 2.000 dòng, 3 lần lặp: log_kill_distance và kill_distance_m đứng đầu (0,0326 và 0,0317). Hai đặc trưng tương quan nên không diễn giải importance riêng như đóng góp độc lập. Không phải importance trên test.

## Diễn giải và bước tiếp theo

- Pilot main grid đạt 0,3058 trên 28.398 dòng validation; lượt này đạt 0,3020 trên 484.965 dòng. Cohort validation và kích thước train cùng thay đổi, nên không dùng hai điểm này làm kiểm định tăng/giảm; chưa chứng minh train dài cải thiện điểm.
- Validation đã được dùng để phát triển và chọn mô hình; số liệu hiện tại chưa thay thế test cuối. Chưa tính CI test, chưa chạy đánh giá test, chưa refit train+validation.
- Lượt train theo plan đã hoàn tất. Bước tiếp theo khi người dùng chốt lựa chọn là đánh giá test một lần bằng đúng pipeline version 1 và checksum đã khóa. Không điều chỉnh seed, registry, mapping hoặc chọn lại theo test.
- Giữ các giới hạn dữ liệu 2017–2018/cách lấy mẫu, loại Down and Out, người kết liễu có thể khác người gây knock, thiếu thông tin đồng đội, Other không đồng nhất và chỉ dùng chunk 0.

## Bằng chứng

- [Readiness JSON](kaggle-full-training-20261021.json), [JUnit](kaggle-full-training-tests-20261021.xml), [lượt chạy và checksum output](full-training-run-20261021.json).
- [Điểm và gap](tables/full_validation_diagnostics.csv), [mọi trial](tables/full_validation_trials.csv), [từng lớp](tables/full_validation_per_class_metrics.csv), [importance](tables/full_validation_feature_importance.csv), [theo khoảng cách](tables/full_validation_distance_metrics.csv).
- [Ma trận nhầm lẫn](figures/full_validation_confusion.png). Output nhỏ đã tải tại `artifacts/kaggle-full-metadata-fixed-output-20261021/`; model joblib và parquet vẫn lưu ở output Kaggle version 1, chưa tải toàn bộ về máy.
