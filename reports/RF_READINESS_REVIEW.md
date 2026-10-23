# Đánh giá lại Random Forest và khả năng train dài — 21/10/2026

**Pipeline train chính hiện đủ điều kiện kỹ thuật để chạy thí nghiệm dài theo plan. Đã chạy lại đúng grid mới trên dữ liệu pilot thật; chưa khởi chạy train 1 triệu dòng hoặc đánh giá test cuối.**

## Phạm vi và kết quả xác nhận mới

Đọc lại models.py, training.py, rf_experiment.py, schema, tests, plan và các report mới. Kết quả 8 cấu hình trước có source training.py khác grid chính hiện tại, nên lần này xác nhận lại qua run_training và run_diagnostics thay vì chỉ dựa vào báo cáo cũ.

[Kaggle xác nhận grid hiện tại](https://www.kaggle.com/code/sangtranminh211/pubg-rf-readiness-review-20261021), version 1, private CPU, Internet tắt. Input là artifact đóng băng của pilot version 1; **100.000 dòng train, 28.398 dòng validation thuộc 434 trận**. Giữ seed 42, không placement, không đổi nhãn hoặc split. Có guard cấm đọc test.parquet trong toàn bộ lượt training/diagnostics/so sánh bootstrap.

- **Local: 57/57 pass**, không skip/failure/error; pip check và git diff --check pass.
- **Kaggle: 57/57 pass**, không skip/failure/error. Warning deprecation thư viện trong image được phân biệt với lỗi mô hình.
- **15 lượt fit/tuning, 11 pipeline, đủ 6 họ thuật toán**, không warning hội tụ/tính toán số ở các lượt fit và diagnostics.
- Cả hai cấu hình RF mới được thử có/không cân bằng; mọi lượt đều lưu trong trials.json.
- Pipeline nạp lại tái lập đúng điểm validation; xác suất hữu hạn/tổng 1; không giao match_id train/validation; test thật không được đọc.
- Source/test/config của bundle train dài hiện có (**32 file**) khớp mã đang dùng và mã của lượt xác nhận này.

## Grid RF chính đã được chạy thật

Giữ max_depth=18, min_samples_leaf=5. Cột cân bằng True dùng balanced_subsample; False không cân bằng.

| Cân bằng | Số cây | max_samples | Macro-F1 validation | Fit + predict validation (s) |
|---|---:|---:|---:|---:|
| False | 200 | 0.2 | 0.2117 | 13.8 |
| False | 300 | 0.15 | 0.2080 | 16.0 |
| True | 200 | 0.2 | 0.3045 | 14.7 |
| True | 300 | 0.15 | 0.3058 | 16.2 |

RF cân bằng được chọn có **300 cây, max_samples=0.15**, macro-F1 **0.305811**, accuracy **0.457427**. Macro-F1 trên cùng mẫu train 20.000 dòng là **0.392954**, gap **0.087143**, so với gap cũ **0,420435**. Các con số tái lập kết quả sub-bootstrapping đã lưu trước.

Grid chính hiện **chỉ dùng balanced_subsample và full features** cho RF cân bằng. Tempered weights và no_position là các đối chiếu trong script 06, chưa được tự động áp dụng vào mô hình chính. Không gộp các kết quả này thành một cấu hình đã triển khai.

## So sánh các họ trong lượt xác nhận

| Pipeline | Macro-F1 validation | Accuracy validation | Macro-F1 mẫu train | Gap |
|---|---:|---:|---:|---:|
| majority_plain_full | 0.0981 | 0.5227 | 0.0985 | 0.0005 |
| logistic_balanced_full | 0.2445 | 0.2683 | 0.2395 | -0.0050 |
| naive_bayes_plain_full | 0.2123 | 0.4275 | 0.2092 | -0.0031 |
| decision_tree_plain_full | 0.2297 | 0.5316 | 0.2991 | 0.0694 |
| decision_tree_balanced_full | 0.2469 | 0.2809 | 0.2915 | 0.0446 |
| random_forest_plain_full | 0.2117 | 0.5474 | 0.2618 | 0.0501 |
| random_forest_balanced_full | 0.3058 | 0.4574 | 0.3930 | 0.0871 |
| hist_gradient_boosting_plain_full | 0.2236 | 0.5460 | 0.3743 | 0.1507 |
| hist_gradient_boosting_balanced_full | 0.2810 | 0.3500 | 0.3883 | 0.1073 |

RF cân bằng được chọn bằng macro-F1 validation. HGB vẫn là mô hình đối chiếu. LMG ở RF được chọn có F1 **0.0000**; việc đủ điều kiện train dài không có nghĩa chất lượng mọi lớp đã tốt.

## Những kết luận cần giới hạn

1. **Chưa chứng minh tăng macro-F1 so với RF cũ.** Bootstrap paired theo match_id, 1.000 lần, cho hiệu số mới−cũ **+0.003675**, CI 95% **[-0.000259, +0.007373]**, chứa 0. Có thể mô tả điểm ước lượng cao hơn và gap thấp hơn; chưa kết luận RF mới vượt RF cũ có ý nghĩa thống kê. Đây còn là validation đã dùng chọn cấu hình, không thay test cuối.
2. **OOB là chẩn đoán trên các dòng train.** Nó không giữ nguyên cả match_id bên ngoài mỗi cây; sự kiện khác cùng trận có thể nằm trong bootstrap. Vì vậy OOB gần validation không chứng minh đã hết overfit hoặc thay được validation theo trận. [Sklearn: định nghĩa OOB](https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.RandomForestClassifier.html), [đánh giá dữ liệu theo nhóm](https://scikit-learn.org/1.6/modules/cross_validation.html#cross-validation-iterators-for-grouped-data).
3. **Chưa đo fit RF ở 1 triệu dòng.** Với max_samples dạng tỷ lệ, 0,15 lấy 15.000 lượt dòng/cây ở pilot 100.000, nhưng 150.000 lượt dòng/cây ở train 1 triệu. Chưa thể chuyển tỷ lệ tăng tốc ở pilot thành bảo đảm tốc độ/RAM ở quy mô dài. Định nghĩa tham số: [sklearn max_samples](https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.RandomForestClassifier.html).
4. **Có lỗi mô tả baseline phụ trong script 06.** candidate_specs ghi cứng baseline depth=20/min_leaf=5/max_samples mặc định, trong khi model thực tế được nạp từ baseline_run. Khi tái sử dụng script với run RF mới, dòng baseline có thể ghi sai params/weight_scheme. Kết quả pilot cũ hợp lệ vì baseline thực tế đúng cấu hình đó. Lỗi này không ảnh hưởng run_training, run_diagnostics, grid hay lượt xác nhận mới; nên sửa trước khi dùng script 06 với baseline mới. Review này không sửa mã nguồn.

Các diễn giải trước về trọng số làm mọi lá bị lớp hiếm áp đảo, hoặc các đặc trưng vị trí không có giá trị, là giả thuyết từ thống kê quan sát; các phép thử hiện tại chưa xác minh cơ chế ở từng lá hoặc chứng minh bỏ tọa độ cải thiện chất lượng.

## Quyết định train dài

**Có thể chuyển sang train dài theo plan hiện tại**: 50.000 trận, tối đa 1 triệu dòng train, đủ 6 họ/15 lượt fit/11 pipeline; RF dùng grid mới, chọn bằng macro-F1 validation. Dừng dò tham số trên pilot để tránh tiếp tục thích nghi vào cùng validation. Tiếp tục giữ test đến khi toàn bộ lựa chọn đã chốt.

Bundle đã xác nhận: **artifacts/kaggle-full-plan-20261021/**. Mặc định không đánh giá test. Không cần thêm tempered/no_position vào grid chỉ vì chúng giảm gap. Lỗi metadata phụ của script 06 không nằm trong đường chạy bundle này.

Lượt model/diagnostics xác nhận mất **3.36 phút**, RSS đỉnh tích lũy **1.36 GiB**, chưa gồm cấp máy và pytest. Preprocessing 50.000 trận đã được kiểm tra riêng trước đó (~5,04 GiB), nhưng đó không phải số đo RAM fit mô hình ở 1 triệu dòng.

[Bằng chứng JSON](rf-readiness-review-20261021.json), [JUnit local](local-rf-review-tests-20261021.xml), [JUnit Kaggle](kaggle-rf-review-tests-20261021.xml), [các lượt tuning](tables/rf_review_validation_metrics.csv), [diagnostics](tables/rf_review_validation_diagnostics.csv), [F1 từng lớp](tables/rf_review_per_class_metrics.csv).

Chưa chạy train dài/test thật; không bảo đảm điểm tăng lên 80–90%. Review giữ nguyên code và bundle bạn vừa cập nhật; kết luận áp dụng cho snapshot khớp hash trong JSON.

## Cập nhật sau review: đã sửa metadata baseline

Script 06 hiện lấy toàn bộ tham số và class_weight trực tiếp từ model baseline đã nạp, thay vì mô tả cấu hình cũ cố định. Test hồi quy kiểm tra cả baseline quick và baseline depth 18/max_samples 0.15, đối chiếu JSON metadata, điểm baseline và checksum các file run gốc. **58/58 test local pass**; bằng chứng: [JUnit metadata fix](local-rf-metadata-fix-tests-20261021.xml).

Không train lại dữ liệu thật, không sửa artifact/checksum đã đóng băng. Bundle mới chứa bản sửa là **artifacts/kaggle-full-metadata-fixed-20261021/**, chưa submit; chỉ rf_experiment.py và test liên quan khác bundle trước. Grid và cách huấn luyện chính giữ nguyên. Phần ghi nhận lỗi ở trên mô tả snapshot trước khi sửa.
