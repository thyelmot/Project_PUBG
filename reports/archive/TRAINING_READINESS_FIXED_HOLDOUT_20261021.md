# Báo cáo kiểm tra trước train dài — 21/10/2026

**Đủ điều kiện kỹ thuật để chuẩn bị train dài cả 7 họ mô hình. Chất lượng dự đoán hiện còn thấp; chưa có cơ sở kỳ vọng 80–90%. Chưa khởi chạy train dài 1 triệu mẫu.**

Báo cáo này thay thế kết luận smoke trước. Kết quả bên dưới dùng holdout nguồn cố định, khác cách chia của pilot cũ; không xem chênh lệch điểm giữa hai cách chia là tác động riêng của việc tăng dữ liệu.

## 1. Lỗi đã sửa và kiểm tra bổ sung

1. **Test có thể đổi vai trò khi tăng cohort:** trước đây GroupShuffleSplit chạy lại trên mỗi cohort. Nay chia trên toàn bộ danh sách match_id của nguồn, lưu `source_match_splits.csv` và tái sử dụng khi lấy mẫu nhỏ/lớn. Giữ 2.294 trận đã dùng trong pilot Kaggle/local ở train/validation, loại chúng khỏi ứng viên test cuối. Dữ liệu chia theo cách cũ bị chặn khi training/evaluation.
2. **Cảnh báo của cấu hình bị loại có thể bị bỏ qua:** lưu mọi lượt fit trong `trials.json` và kiểm tra convergence/RuntimeWarning trên toàn bộ lượt thử, không chỉ cấu hình thắng.
3. **Thiếu victim bị tính nhầm vào self-kill:** sửa mask để được ghi vào đúng nhóm invalid identity; đây là lỗi đếm audit, không phải cách tăng điểm mô hình.
4. **k-NN:** bổ sung đúng mục tùy chọn của plan, giới hạn train 100.000 dòng; tự giảm số láng giềng nếu cohort rất nhỏ. Bản train dài có đủ 7 họ mô hình.

Các kiểm tra còn gồm: làm sạch và đếm dòng, mapping nhãn lạ ngoài cohort, đơn vị khoảng cách và biên time_phase, lấy đủ sự kiện của trận qua chunk, giữ lớp hiếm khi giảm mẫu, train/validation không giao nhau, imputer/scaler/encoder chỉ fit trên train, checksum artifact, pipeline nạp lại tái lập điểm, xác suất hữu hạn/tổng bằng 1 và khóa đánh giá test cuối.

## 2. Kết quả test và nguồn mã

- **Local: 47/47 pass**, không skip. [JUnit local](../local-diagnostic-tests-20261021.xml).
- **Kaggle: 47/47 pass**, không skip. [JUnit Kaggle](../kaggle-validation-tests-20261021.xml).
- **16 lượt fit/tuning chính, 12 pipeline lưu cuối**, bao phủ 7 họ mô hình; tất cả thành công. Có thêm 2 lượt control nhãn thật/xáo nhãn.
- Không có cảnh báo hội tụ/tính toán số trong lượt train thật hoặc diagnostics. Cảnh báo API cũ của image Kaggle trong pytest được phân biệt với lỗi mô hình.
- Hash source/test/mapping/registry của validation, preflight 50.000 trận, bản local và bundle train dài khớp nhau.
- Kiểm tra thực tế: không có trận train/validation của pilot mới nằm trong test của tập 50.000 trận; không có trận thuộc registry development cũ nằm trong test đó. Hash phân hoạch toàn nguồn của hai job đều là `3cd3e1a76c8679b510ee791bbd280a3684a51ffc03676c39ffbcc7466296c8ce`.
- Các đầu vào mô hình thực tế không chứa tên người chơi, match_id, killed_by, target hoặc placement.
- **Test thật chưa được chấm.** Diagnostics chỉ đọc train/validation; đánh giá cuối trong unit test dùng dữ liệu tổng hợp riêng.

[Phiên xác nhận mô hình trên Kaggle](https://www.kaggle.com/code/sangtranminh211/pubg-weapon-validation-20261021), version 1. [Readiness JSON](../kaggle-validation-20261021.json).

## 3. Thử cấu hình đầy đủ trên dữ liệu thật

Dataset: `skihikingkevin/pubg-match-deaths`, deaths chunk 0; đọc toàn nguồn 13.426.348 dòng để kiểm kê nhãn và cố định phân hoạch. Cohort 3.000 trận: 271,395 sự kiện gốc, sau cleaning/chia có 100.000 dòng train, 28,398 validation và 28,082 test được giữ lại.

Các cấu hình được thử đúng chế độ full: RF 200/300 cây; HGB 150/250 vòng, hai learning rate và kích thước cây; các biến thể có/không cân bằng; k-NN 15 láng giềng. Cấu hình thắng từng họ/biến thể được chọn bằng macro-F1 validation.

| Mô hình/biến thể | Macro-F1 validation | Accuracy validation | Macro-F1 trên mẫu train | Chênh lệch train − val |
|---|---:|---:|---:|---:|
| majority_plain_full | 0.0981 | 0.5227 | 0.0985 | 0.0005 |
| logistic_balanced_full | 0.2445 | 0.2683 | 0.2395 | -0.0050 |
| naive_bayes_plain_full | 0.2123 | 0.4275 | 0.2092 | -0.0031 |
| decision_tree_plain_full | 0.2297 | 0.5316 | 0.2991 | 0.0694 |
| decision_tree_balanced_full | 0.2469 | 0.2809 | 0.2915 | 0.0446 |
| random_forest_plain_full | 0.2228 | 0.5448 | 0.4586 | 0.2359 |
| random_forest_balanced_full | 0.3021 | 0.4413 | 0.7226 | 0.4204 |
| hist_gradient_boosting_plain_full | 0.2236 | 0.5460 | 0.3743 | 0.1507 |
| hist_gradient_boosting_balanced_full | 0.2810 | 0.3500 | 0.3883 | 0.1073 |
| knn_plain_full | 0.2429 | 0.5259 | 1.0000 | 0.7571 |

Điểm train tính trên cùng một mẫu có giữ tỷ lệ lớp, tối đa 20.000 dòng từ dữ liệu đã fit; không phải điểm trên toàn bộ train. [Bảng đầy đủ](../tables/validation_all_models.csv), [mọi lượt tuning](../tables/validation_model_trials.csv).

### Phân tích lỗi

Mô hình chọn trên validation: **random_forest_balanced_full**, macro-F1 **0.3021**, accuracy **0.4413**. Các kết quả này chưa phải điểm test cuối.

| Lớp | Precision | Recall | F1 | Số mẫu validation |
|---|---:|---:|---:|---:|
| AR | 0.7088 | 0.5204 | 0.6002 | 14843 |
| DMR | 0.2221 | 0.2163 | 0.2192 | 2321 |
| LMG | 0.0000 | 0.0000 | 0.0000 | 188 |
| Other | 0.4513 | 0.3808 | 0.4131 | 2702 |
| SMG | 0.2060 | 0.1831 | 0.1939 | 3582 |
| SR | 0.2211 | 0.4821 | 0.3032 | 1286 |
| Shotgun | 0.2897 | 0.5757 | 0.3854 | 3476 |

- Random Forest cân bằng có chênh lệch macro-F1 train–validation **0.420**: đây là dấu hiệu overfit cần theo dõi khi tăng dữ liệu, dù nó vẫn thắng theo metric lựa chọn.
- k-NN đạt F1 train 1,000 nhưng validation chỉ khoảng 0,243: khả năng nhớ mẫu train không chuyển thành khả năng dự đoán tốt ở trận mới.
- LMG chỉ có 662 mẫu train và 188 mẫu validation; F1 của mô hình chọn bằng 0. Các mô hình cân bằng khác có F1 LMG thấp, khoảng 0,016–0,024. Không gộp lớp sau khi xem validation để làm đẹp điểm; vẫn giữ quy tắc lớp dưới 0,5% theo train trong plan.
- Khoảng cách giữa các nhóm chồng lấn: median train của AR khoảng 18,85 m, LMG 14,51 m; SMG 7,30 m và Shotgun 4,48 m. Điều này phù hợp với các lỗi nhầm trong bảng dưới, chưa chứng minh một giới hạn điểm tối đa của bài toán.

| Nhầm lẫn | Số mẫu | Khoảng cách trung bình |
|---|---:|---:|
| AR → Shotgun | 2449 | 5.6 m |
| AR → SMG | 1524 | 13.2 m |
| AR → SR | 1417 | 133.3 m |
| SMG → Shotgun | 1348 | 5.3 m |
| AR → DMR | 1187 | 114.9 m |

[Ma trận nhầm lẫn](../figures/validation_confusion.png), [F1 từng lớp cho mọi pipeline](../tables/validation_per_class.csv), [các cặp nhầm](../tables/validation_confused_pairs.csv).

### Kiểm tra tín hiệu nhãn

Cùng cấu hình HGB nhỏ, cùng 20.000 mẫu train và cùng validation:

- Nhãn thật: macro-F1 **0.2607**.
- Nhãn xáo trộn: macro-F1 **0.0993**.

Kết quả cho thấy mô hình học được tín hiệu dự đoán từ đặc trưng. Các phép kiểm tra không phát hiện lỗi kỹ thuật khiến toàn bộ pipeline không học; chất lượng thực tế vẫn hạn chế. Permutation importance trên validation xếp `log_kill_distance`, `kill_distance_m`, `time`, `time_phase`, `map` ở nhóm đầu. [Bảng importance](../tables/validation_feature_importance.csv).

## 4. Thời gian và bộ nhớ

Các số dưới đo trong script, không gồm toàn bộ thời gian cấp máy/đợi Kaggle.

| Họ mô hình | Số lượt fit/tuning | Tổng thời gian fit + predict validation | RSS đỉnh tích lũy của tiến trình | Trạng thái |
|---|---:|---:|---:|---|
| majority | 1 | 0.3 s | 0.57 GiB | PASS |
| logistic | 1 | 5.3 s | 0.57 GiB | PASS |
| naive_bayes | 1 | 0.4 s | 0.57 GiB | PASS |
| decision_tree | 2 | 5.6 s | 0.57 GiB | PASS |
| random_forest | 4 | 234.2 s | 1.24 GiB | PASS |
| hist_gradient_boosting | 6 | 68.3 s | 1.24 GiB | PASS |
| knn | 1 | 1.7 s | 1.24 GiB | PASS |

RSS là mức cao nhất từ đầu tiến trình đến lượt đó, không phải RAM riêng của mô hình; không cộng các hàng lại. Toàn job xác nhận khoảng **9.0 phút**, RSS đỉnh sau diagnostics **2.05 GiB**.

Đã kiểm tra riêng preprocessing ở đúng quy mô dự định: **50.000 trận, 4,525,712 sự kiện gốc**, tạo thành:

- Train: **1.000.000 dòng**.
- Validation: **484,965 dòng**.
- Test giữ lại: **488,107 dòng**.
- Thời gian xử lý khoảng **3.5 phút**, RAM đỉnh **4.59 GiB**.

[Preflight Kaggle](https://www.kaggle.com/code/sangtranminh211/pubg-weapon-data-preflight-20261021), version 2; [JSON bằng chứng](../data-preflight-20261021.json), [bảng cleaning](../tables/full_cleaning_counts.csv). Preflight không fit mô hình hay chấm test.

## 5. Chuẩn bị train dài

Bundle đúng source đã kiểm tra: **`artifacts/kaggle-full-20261021-fixed-holdout/`** trong repo. Các bundle cũ trong artifacts thuộc lịch sử kiểm tra; dùng bundle mới này.

```bash
kaggle kernels push -p artifacts/kaggle-full-20261021-fixed-holdout
kaggle kernels status sangtranminh211/pubg-weapon-full-20261021
kaggle kernels output sangtranminh211/pubg-weapon-full-20261021 -p artifacts/kaggle-full-output
```

Kernel private, CPU, Internet tắt. Cấu hình: 50.000 trận; tối đa 1 triệu dòng train cho các mô hình chính; k-NN giới hạn 100.000 dòng theo plan. Chạy đủ 7 họ, 16 lượt fit/tuning, 12 pipeline và ablation A/B/C; sau đó chẩn đoán validation. **Không tự chấm test cuối.** Chỉ chấm test khi đã chốt quyết định trên validation.

Môi trường xác nhận: Python 3.13.15; numpy 2.1.3, pandas 2.3.3, scikit-learn 1.6.1, pyarrow 23.0.1, matplotlib 3.10.0, pytest 8.4.2. Giữ đúng phiên bản khi tải pipeline joblib về để dự đoán/đánh giá.

### Giới hạn còn lại

- Chưa đo thời gian/RAM fit toàn bộ mô hình trên 1 triệu dòng; mới xác nhận full grid trên 100.000 dòng và preprocessing ở quy mô đầy đủ. Pipeline chưa có checkpoint/resume giữa các lượt fit.
- Điểm hiện tại khoảng 0,302 macro-F1, LMG chưa được nhận diện tốt và RF/k-NN overfit. Train dài là thí nghiệm tiếp theo, không bảo đảm tăng lên 80–90%.
- Placement mặc định bị loại do nguy cơ là thông tin cuối trận. `--with-placement` chỉ dùng cho thí nghiệm hồi cứu có ghi nhãn rõ ràng.
- ROC/AUC, GroupKFold và các boosting library ngoài scikit-learn vẫn là phần tùy chọn chưa triển khai.
