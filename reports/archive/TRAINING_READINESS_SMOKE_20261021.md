> Báo cáo smoke lịch sử; xem [báo cáo mới](../TRAINING_READINESS.md) trước khi train dài.

# Kết quả kiểm tra trước train dài — 21/10/2026

**PASS: có thể chuẩn bị train dài.** Chưa khởi chạy bản train dài.

## Bằng chứng

- Local: 37 test, 0 fail. [JUnit local](../local-tests-20261021.xml).
- Kaggle CPU, kernel version 5: 37 test, 0 fail, 0 skip. [JUnit Kaggle](../kaggle-tests-20261021.xml).
- [Phiên Kaggle](https://www.kaggle.com/code/sangtranminh211/pubg-weapon-pilot-20261021): dùng URL kernel; kết quả được xác minh từ output version 5 qua CLI.
- [Readiness JSON](../kaggle-pilot-20261021.json): status passed, source hashes khớp toàn bộ source/test/mapping hiện tại và bundle full.
- Cài đặt local không có dependency xung đột; các CLI hỗ trợ --help; kiểm tra cú pháp và git diff --check pass.
- Các test gồm quy tắc cleaning, nhãn lạ ngoài sample, khoảng cách/biên thời gian, lấy đủ sự kiện của trận qua chunk, chia tập không giao nhau, gộp lớp hiếm từ train, giảm mẫu giữ singleton, sáu họ mô hình, grid full trên dữ liệu tổng hợp, chống đọc test khi training, phát hiện artifact bị thay đổi và khóa đánh giá test một lần.

## Pilot trên dữ liệu thật

- Dataset: skihikingkevin/pubg-match-deaths, chỉ đọc deaths shard 0.
- Đọc toàn bộ **13,426,348 dòng**, kiểm kê **57 tên nhãn**; toàn bộ đều được mapping tường minh.
- Lấy ngẫu nhiên 2.000 trận, seed 42: **180,963 sự kiện gốc**.
- Train sau giảm mẫu: 30.000 dòng; validation: 19.504; test giữ lại: 19.586.
- Các lớp: AR, DMR, LMG, Other, SMG, SR, Shotgun.
- 11 pipeline, gồm baseline, các mô hình cây có/không cân bằng và ablation, đều fit/predict thành công.
- Chọn mô hình bằng macro-F1 validation; không chấm test thật trong pilot. Test đánh giá cuối dùng fixture tổng hợp riêng.
- Không có cảnh báo hội tụ hoặc RuntimeWarning trong huấn luyện thật. Bộ test trên image Kaggle có 15 cảnh báo API cũ từ thư viện; không có test bị bỏ qua.
- Tổng thời gian chạy trong kernel khoảng 161 giây, gồm test và quét dữ liệu. Đây không phải ước lượng thời gian train dài.

| Thí nghiệm | Macro-F1 validation | Accuracy validation |
|---|---:|---:|
| random_forest_balanced_full | 0.2877 | 0.3843 |
| hist_gradient_boosting_balanced_full | 0.2699 | 0.3208 |
| hist_gradient_boosting_balanced_context | 0.2605 | 0.3129 |
| decision_tree_balanced_full | 0.2512 | 0.3205 |
| logistic_balanced_full | 0.2503 | 0.2760 |
| naive_bayes_plain_full | 0.2329 | 0.4361 |
| decision_tree_plain_full | 0.2324 | 0.5187 |
| hist_gradient_boosting_balanced_distance | 0.2080 | 0.2284 |
| random_forest_plain_full | 0.2071 | 0.5535 |
| hist_gradient_boosting_plain_full | 0.2047 | 0.5552 |
| majority_plain_full | 0.0986 | 0.5271 |

Các điểm số trên là **pilot với cấu hình quick**, không phải kết quả cuối hay cơ sở để chọn lại cấu hình theo test. [Bảng đầy đủ](../tables/pilot_validation_metrics.csv).

## Chạy dài khi sẵn sàng

Bundle đã tạo tại `artifacts/kaggle-full-20261021-final/` trong repo. Dùng đúng bundle này để giữ source đã kiểm tra:

```bash
kaggle kernels push -p artifacts/kaggle-full-20261021-final
```

Kernel đích: `sangtranminh211/pubg-weapon-full-20261021`, private, CPU, Internet tắt. Cấu hình: 50.000 trận, tối đa 1.000.000 dòng train; RF 200/300 cây; HGB 150/250 vòng; 15 lượt fit và 11 pipeline cuối. Không bật đánh giá test tự động.

Theo dõi:

```bash
kaggle kernels status sangtranminh211/pubg-weapon-full-20261021
kaggle kernels output sangtranminh211/pubg-weapon-full-20261021 -p artifacts/kaggle-full-output
```

Môi trường Kaggle đã kiểm tra: numpy 2.1.3, pandas 2.3.3, scikit-learn 1.6.1, pyarrow 23.0.1, matplotlib 3.10.0, pytest 8.4.2. Metadata mỗi run lưu phiên bản và checksum; dùng cùng môi trường khi tải pipeline joblib để chạy lại.

## Giới hạn còn lại

- Chưa kiểm tra bộ nhớ/thời gian ở quy mô 50.000 trận. Cleaning giữ cohort trong RAM; chưa có checkpoint/resume giữa các lượt fit. Bản full đã được kiểm tra logic trên dữ liệu tổng hợp, chưa chạy đủ dữ liệu thật.
- Placement mặc định bị loại vì nguy cơ là thứ hạng cuối trận; `--with-placement` chỉ là nhánh thí nghiệm hồi cứu. Cần thống nhất phát biểu bài toán trước khi báo cáo kết quả có placement.
- `Down and Out` và `death.PlayerMale_A_C` không xác định được họ vũ khí, nên loại và thống kê riêng trong inventory; không tự đoán nhãn.
- Các tùy chọn k-NN, ROC/AUC và GroupKFold chưa triển khai.
