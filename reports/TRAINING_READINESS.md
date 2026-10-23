# Kiểm tra theo plan mới — 21/10/2026

Đánh giá xác nhận mới nhất: [RF_READINESS_REVIEW.md](RF_READINESS_REVIEW.md). Đã chạy lại grid hiện tại qua toàn bộ pipeline; lưu ý CI mức tăng RF so với bản cũ chứa 0, OOB chỉ là chẩn đoán train và tốc độ ở 1 triệu dòng chưa được đo.

**Đã sửa và kiểm tra lại phần code bắt buộc của plan mới. Đủ điều kiện kỹ thuật để chuẩn bị train dài 6 họ mô hình; chưa khởi chạy train dài hoặc chấm test thật.**

Bổ sung sau pilot: [xử lý overfitting cho Random Forest trên Kaggle](RF_REGULARIZATION.md) (version 2, 57/57 test pass ở local và Kaggle). Kết hợp sub-bootstrapping (`max_samples = 0,15–0,20, max_depth = 18, min_samples_leaf = 5`) giảm gap train–validation từ `0,4204` xuống `0,0871` (OOB macro-F1 `0,3051`), nâng nhẹ macro-F1 validation lên `0,3058`, accuracy lên `0,4574` và giảm ~4 lần thời gian fit; đã cập nhật vào grid train dài và đóng gói lại bundle `artifacts/kaggle-full-plan-20261021/`.

Báo cáo này thay thế [kết quả trước khi đổi plan](archive/TRAINING_READINESS_FIXED_HOLDOUT_20261021.md). Pilot dưới đây dùng cùng holdout và cùng seed 42; thay đổi báo cáo không làm tăng điểm dự đoán.

## Những phần đã đổi

- Bỏ k-NN theo phạm vi mới: còn 6 họ, 9 biến thể full, 2 ablation bổ sung; **15 lượt fit/tuning, 11 pipeline**. Mọi cấu hình được thử vẫn lưu trong trials.json, kể cả cấu hình bị loại.
- Đánh giá cuối tính **CI 95% macro-F1 bằng bootstrap theo match_id, 1.000 lần, seed 42**. Mọi pipeline dùng chung mẫu lấy lại trận; xuất CI hiệu số từng cặp và mức tăng A→B, B→C. Khoảng hiệu số chứa 0 được ghi inconclusive. Lưu các lần lặp để kiểm chứng, giữ cơ chế khóa đánh giá test một lần và không refit train+validation.
- Cặp nhầm dùng **trung vị** khoảng cách; mỗi bin 0–50, >50–150, >150–300, >300 m có cả accuracy và macro-F1. Bin rỗng ghi số dòng 0 và chỉ số thiếu, không giả định điểm 0.
- Giữ nguyên nhân gốc dưới tên cause_for_audit để phân tích từng thành phần Other (Punch, melee, súng lục, grenade/lửa, xe, Crossbow, vũ khí hiếm bị gộp). Cột này **bị cấm vào X**, như nhãn và định danh. Xuất phân phối khoảng cách theo thành phần/nguồn và tỷ lệ nhầm sang từng lớp.
- EDA thêm tỷ lệ map bất hợp lệ, Down and Out theo map/giai đoạn. Audit nhãn bị loại phân biệt số có mặt ở nguồn/sample, số bị loại ở các bước trước và số bị loại tại bước nhãn, tránh đếm chồng.
- --with-placement thêm **cả ba** placement vào B và C. Run/output riêng; metrics/metadata ghi retrospective. Bài toán chính không dùng placement. Các bước lấy mẫu mặc định đều dùng seed 42; pilot 3.000 trận để có đủ split ngoài registry development cũ.

Dữ liệu processed trước thay đổi thiếu cause_for_audit phải chạy lại preprocessing và training; không dùng model cũ với dữ liệu đã thay đổi checksum. Không khôi phục source cũ đã xóa.

## Bằng chứng kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Local | **57/57 pass**, không skip, không warning; pip check pass |
| Kaggle | **57/57 pass**, không skip; 16 warning deprecation từ thư viện trong image |
| Pilot dữ liệu thật | **15/15 lượt fit/tuning**, 11 pipeline, 6 họ; không warning hội tụ/tính toán số |
| Diagnostics validation | Nạp lại tái lập điểm; xác suất hữu hạn/tổng 1; train/val không trùng trận; không đọc test |
| Bootstrap quy mô lớn | 500.000 sự kiện tổng hợp, 7.500 trận, 11 pipeline, 1.000 lần lặp: **0.80 s**, RSS đỉnh tiến trình 407 MiB, 2 thread |
| Preprocessing đầy đủ | 50.000 trận → train 1 triệu dòng; audit và schema mới pass |

Test bootstrap đối chiếu với việc nhân bản toàn bộ sự kiện của từng trận được lấy lại, gồm trận có kích thước khác nhau, lớp vắng mặt và lặp lại cùng trận. Kiểm tra CI hiệu số dùng đúng các lần lặp chung, trường hợp hai dự đoán giống nhau không được kết luận cao hơn. Luồng đánh giá cuối (CI, ablation, Other, khóa test) được chạy trên **fixture tổng hợp**, gồm cả run hồi cứu riêng.

[JUnit local](local-plan-update-tests-20261021.xml), [JUnit Kaggle](kaggle-plan-update-tests-20261021.xml), [readiness pilot](kaggle-plan-update-20261021.json), [preflight dữ liệu](plan-data-preflight-20261021.json), [benchmark bootstrap](bootstrap-scale-check-20261021.json).

29 file source/test/config trong pilot, preflight và bundle train dài khớp hash với code hiện tại. Holdout nguồn giữ hash `3cd3e1a76c8679b510ee791bbd280a3684a51ffc03676c39ffbcc7466296c8ce`. Không có trận development cũ hoặc train/validation pilot nằm trong test của cohort 50.000 trận.

## Pilot cấu hình đầy đủ, 100.000 dòng train

[Kaggle pilot](https://www.kaggle.com/code/sangtranminh211/pubg-weapon-plan-update-20261021), version 1: 3.000 trận lấy từ toàn bộ chunk 0, 100.000 dòng train, 28.398 validation. RF thử 200/300 cây, HGB 150/250 vòng; cấu hình được chọn bằng macro-F1 validation. Job mất **9.06 phút**, RSS đỉnh sau diagnostics **1.99 GiB**.

| Pipeline | Macro-F1 validation | Accuracy validation | Macro-F1 mẫu train |
|---|---:|---:|---:|
| majority_plain_full | 0.0981 | 0.5227 | 0.0985 |
| logistic_balanced_full | 0.2445 | 0.2683 | 0.2395 |
| naive_bayes_plain_full | 0.2123 | 0.4275 | 0.2092 |
| decision_tree_plain_full | 0.2297 | 0.5316 | 0.2991 |
| decision_tree_balanced_full | 0.2469 | 0.2809 | 0.2915 |
| random_forest_plain_full | 0.2228 | 0.5448 | 0.4586 |
| random_forest_balanced_full | 0.3021 | 0.4413 | 0.7226 |
| hist_gradient_boosting_plain_full | 0.2236 | 0.5460 | 0.3743 |
| hist_gradient_boosting_balanced_full | 0.2810 | 0.3500 | 0.3883 |

Điểm train dùng tối đa 20.000 dòng có giữ tỷ lệ lớp. Mô hình chọn là **random_forest_balanced_full**, macro-F1 **0,3021**; gap train−validation **0,4204** còn lớn. LMG vẫn khó nhận diện (F1 = 0 ở pipeline được chọn). Đây chưa phải điểm test và chưa có kết luận khác biệt có ý nghĩa thống kê giữa các mô hình.

| Ablation | Pipeline | Macro-F1 validation |
|---|---|---:|
| A | hist_gradient_boosting_balanced_distance | 0.2084 |
| B | hist_gradient_boosting_balanced_context | 0.2591 |
| C | hist_gradient_boosting_balanced_full | 0.2810 |

CI trên test thật chỉ được tính ở đánh giá cuối. Control HGB nhỏ với nhãn thật đạt **0,2607**, nhãn xáo đạt **0,0993**; có tín hiệu dự đoán nhưng chất lượng còn hạn chế.

Phân tích Other trên validation cho thấy tỷ lệ đoán đúng khác nhau rõ: Punch **83,36%**, súng lục **24,51%**, grenade/lửa **3,91%**, xe **16,86%**. Đây là thống kê mô tả của pipeline được chọn, không phải khẳng định kiểm định giữa các thành phần. Cặp AR→Shotgun có 2.449 lỗi, khoảng cách **trung vị 4,52 m**.

[Bảng mọi pipeline](tables/plan_validation_validation_diagnostics.csv), [tuning](tables/plan_validation_trials.csv), [F1 từng lớp](tables/plan_validation_per_class_metrics.csv), [cặp nhầm](tables/plan_validation_confused_pairs.csv), [theo khoảng cách](tables/plan_validation_distance_metrics.csv), [Other](tables/plan_validation_other_components.csv), [đích nhầm Other](tables/plan_validation_other_confused_destinations.csv), [ma trận nhầm](figures/plan_validation_confusion.png).

## Xử lý overfitting Random Forest trên Kaggle (100.000 dòng train, 28.398 validation)

[Kaggle RF regularization](https://www.kaggle.com/code/sangtranminh211/pubg-rf-regularization-20261021), version 2 (57/57 test pass): đối chiếu 8 cấu hình trên đúng tập pilot đã đóng băng, kèm OOB macro-F1 và bootstrap CI theo `match_id`:

| Cấu hình | Macro-F1 val (95% CI) | Macro-F1 train | Gap (train−val) | OOB Macro-F1 (OOB−val) | Accuracy val | Số lá TB/cây | Thời gian fit (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `baseline` (`d=20, leaf=5, ms=None, bal`) | 0.3021 `[0.2959, 0.3076]` | 0.7226 | **0.4204** | — | 0.4413 | 7,083.7 | 81.6 |
| `depth12_leaf20` (`d=12, leaf=20, ms=None, bal`) | 0.2799 `[0.2745, 0.2852]` | 0.3450 | 0.0651 | 0.2791 (`-0.0008`) | 0.3552 | 841.6 | 61.5 |
| **`subboot_d18_leaf5_ms015`** (`d=18, leaf=5, ms=0.15, bal`) | **0.3058** `[0.2995, 0.3115]` | 0.3930 | **0.0871** | **0.3051** (`-0.0007`) | **0.4574** | **1,803.4** | **21.0** |
| `subboot_d18_leaf5_ms020` (`d=18, leaf=5, ms=0.20, bal`) | 0.3056 `[0.2994, 0.3112]` | 0.4182 | 0.1127 | 0.3049 (`-0.0006`) | 0.4534 | 2,240.1 | 26.1 |
| `tempered_d18_leaf5_ms020` (`d=18, leaf=5, ms=0.20, α=0.85`) | 0.3038 `[0.2973, 0.3097]` | 0.4168 | 0.1130 | 0.3055 (`+0.0016`) | **0.4829** | 2,180.6 | 24.5 |
| **`tempered_d14_leaf12_ms025`** (`d=14, leaf=12, ms=0.25, α=0.75`) | **0.3036** `[0.2974, 0.3091]` | 0.3567 | **0.0530** | 0.2985 (`-0.0051`) | **0.4742** | **938.5** | **24.1** |
| `tempered_d16_leaf8_ms020` (`d=16, leaf=8, ms=0.20, α=0.80`) | 0.3024 `[0.2960, 0.3082]` | 0.3787 | 0.0763 | 0.3030 (`+0.0005`) | 0.4723 | 1,326.8 | 22.8 |
| `no_pos_d16_leaf8_ms020` (`no_position, d=16, leaf=8, ms=0.20, α=0.80`) | 0.2975 `[0.2916, 0.3027]` | 0.3466 | 0.0491 | 0.2941 (`-0.0034`) | 0.4553 | 1,339.4 | 14.3 |

- **Nguyên nhân cắt tỉa thô (`depth12_leaf20`) làm tụt điểm:** khi lá quá lớn dưới `class_weight='balanced_subsample'`, trọng số lớp thiểu số lấn át lớp đông trong các lá pha trộn, làm recall của `AR` sụt từ 52,0% xuống 31,6% (F1 giảm từ 0,6002 xuống 0,4450).
- **Giải pháp hiệu quả (`subboot_d18_leaf5_ms015` và `tempered_d14_leaf12_ms025`):** dùng sub-bootstrapping (`max_samples=0.15–0.20`) để 80–85% cây trong rừng là out-of-bag đối với mỗi mẫu train, kết hợp giới hạn độ sâu hoặc làm dịu trọng số lớp (`tempered_power`). Kết quả: gap train−validation giảm **4,8–7,9 lần** (từ `0.4204` xuống `0.0871` và `0.0530`), OOB macro-F1 khớp sát validation (`0.3051` so với `0.3058`), macro-F1 validation tăng lên `0.3058`, accuracy tăng lên `0.4574–0.4829`, số lá giảm ~4–7,5 lần và thời gian fit giảm ~4 lần (`81.6s` → `21.0s`).
- Lưới `parameter_grid('random_forest', quick=False)` trong `src/pubg_weapon/training.py` đã được cập nhật sang hai cấu hình `subboot` (`max_depth=18, min_samples_leaf=5, max_samples=0.20/0.15`).

[Bảng validation RF](tables/rf_regularization_validation_metrics.csv), [kiểm định cặp RF](tables/rf_regularization_paired_differences.csv), [F1 từng lớp RF](tables/rf_regularization_per_class_metrics.csv), [readiness RF](kaggle-rf-regularization-20261021.json).

## Dữ liệu ở quy mô train dài

[Kaggle preflight](https://www.kaggle.com/code/sangtranminh211/pubg-weapon-plan-data-preflight-20261021), version 1: đọc chunk 0 gồm 13.426.348 dòng; lấy 50.000 trận với 4.525.712 sự kiện gốc, xử lý **3.61 phút**, RSS đỉnh **5.04 GiB**. Không fit mô hình hoặc chấm test.

- Train: **1.000.000 dòng**; validation: **484.965 dòng**; test giữ lại: **488.107 dòng**.
- Down and Out: 2.310.417 dòng trên nguồn (17,208%); 777.775 dòng trong sample (17,186%). 81.159 dòng bị loại bởi bước trước, 696.616 dòng bị loại ở bước nhãn, tổng khớp số sample.
- Tỷ lệ Down and Out trong sample: early **10,86%**, mid **18,06%**, late **23,12%**. Việc loại nhóm này làm thay đổi phạm vi kết luận, nhất là các pha hạ gục trong chế độ đội.

[Audit cleaning](tables/plan_full_cleaning_counts.csv), [nhãn bị loại](tables/plan_full_excluded_label_counts.csv), [Down and Out theo map](tables/plan_full_down_and_out_by_map.csv), [theo giai đoạn](tables/plan_full_down_and_out_by_phase.csv), [dòng bất hợp lệ](tables/plan_full_quality_audit.csv).

## Bundle train dài đã chuẩn bị

Dùng **artifacts/kaggle-full-plan-20261021/**, private CPU, Internet tắt. Bundle chưa được submit. Nó mặc định chạy 50.000 trận, train tối đa 1 triệu dòng, đủ 6 họ/15 lượt fit/11 pipeline và diagnostics validation; **không tự chấm test thật**.

```bash
kaggle kernels push -p artifacts/kaggle-full-plan-20261021
kaggle kernels status sangtranminh211/pubg-weapon-full-plan-20261021
kaggle kernels output sangtranminh211/pubg-weapon-full-plan-20261021 -p artifacts/kaggle-full-plan-output
```

Không dùng các bundle cũ có k-NN hoặc thiếu bootstrap. Khi đã chốt trên validation, đánh giá test bằng script 04 trong đúng môi trường phiên bản lưu ở metadata.

Chưa chạy fit toàn bộ mô hình trên 1 triệu dòng hoặc chấm test thật; CI thật và tài nguyên huấn luyện dài chưa được xác nhận. Điểm pilot vẫn thấp và RF có dấu hiệu overfit, không bảo đảm train dài đạt 80–90%. Biến thể Melee, hồi cứu trên dữ liệu thật, các mô hình/dữ liệu ngoài phạm vi plan chưa chạy; pipeline chưa có checkpoint/resume. Khi viết báo cáo cần giữ các giới hạn về dữ liệu 2017–2018, cách thu thập mẫu, loại Down and Out, người kết liễu/đồng đội, Other không đồng nhất và chỉ dùng chunk 0.
