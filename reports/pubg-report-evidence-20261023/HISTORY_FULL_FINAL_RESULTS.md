# Kết quả cuối: train dài và holdout PUBG với lịch sử nhân quả

Ngày 22/10/2026. **Kaggle version 1 COMPLETE; readiness passed; holdout được đánh giá đúng một lần trong phiên đánh giá cuối.**

Kernel: https://www.kaggle.com/code/sangtranminh211/pubg-loadout-history-full-final-20261022

## Dữ liệu và quy trình đã khóa

- Lấy đủ 50.000 trận: 4.525.712 sự kiện gốc → 3.220.155 sự kiện hợp lệ sau cleaning.
- Train trước cap: 2.255.190 dòng; train thực tế: **1.000.000 dòng / 34.614 trận**. Validation: **480.891 dòng / 7.373 trận**. Test: **484.074 dòng / 7.418 trận**.
- Ngưỡng gộp lớp hiếm 1% chỉ học từ train; LMG gộp vào Other, còn AR/DMR/Other/SMG/SR/Shotgun. Lịch sử tính trên toàn chuỗi trước cap, chỉ từ t'<t trong cùng trận/người chơi; sự kiện cùng giây không thấy nhau.
- Split nguồn giữ nguyên SHA-256 `3cd3e1a76c8679b510ee791bbd280a3684a51ffc03676c39ffbcc7466296c8ce`. Số dòng ít hơn báo cáo C cũ do bổ sung loại placeholder `#unknown`; không đổi holdout hoặc seed.
- Chín biến thể chính trên D; đủ 6 họ, 16 trials, 12 pipeline. Mô hình được chọn bằng Macro-F1 validation trước khi mở test. Không refit train+validation và không chọn lại theo điểm test.
- Cả 65 test Kaggle pass, không failure/error/skip. 34 source hash khớp bundle/local; không cảnh báo hội tụ/tính toán số hoặc thư viện. Hash dataset/selection/experiments/trials và hai marker evaluation_started/evaluation_complete đã được kiểm chứng.

## Mô hình được chọn và kết quả chính

**Random Forest balanced**: 300 cây, max_depth=18, min_samples_leaf=5, max_samples=0.15, class_weight=balanced_subsample. Dùng 17 đặc trưng của cấu hình D.

| Chỉ số | Validation | Holdout test |
|---|---:|---:|
| Macro-F1 | 0,4227 | 0,4219 |
| Accuracy | 49,10% | 48,99% |
| Top-2 Accuracy | 69,23% | 69,15% |
| Weighted-F1 | 0,5102 | 0,5090 |
| Tactical role Macro-F1 | 0,6113 | 0,6103 |
| Tactical role Accuracy | 63,39% | 63,30% |
| CI 95% Macro-F1 | [0,4209; 0,4245] | [0,4201; 0,4236] |

Macro-F1 trên mẫu train stratified 20.000 dòng là **0,4535**; gap train–validation **0,0308**. Validation và test gần nhau (0,4227 / 0,4219). Điểm train là trên mẫu 20.000 dòng, không phải toàn train.

**Accuracy test 48,99% thấp hơn majority 52,65%.** Majority có Macro-F1 chỉ 0,1150. HGB plain và RF plain đạt Accuracy lần lượt 60,18% và 60,03%, nhưng Macro-F1 thấp hơn; mô hình cân bằng được giữ theo tiêu chí chính đã khóa. Không kết luận mô hình chọn tốt hơn baseline ở mọi chỉ số.

## Ablation A → B → C → D trên test

Cùng họ RF, cùng tham số và cân bằng; chỉ đổi tập đặc trưng. CI percentile từ paired cluster bootstrap theo 7.418 trận, 1.000 lần, seed 42.

| Cấu hình | Macro-F1 | CI 95% | Accuracy | Top-2 |
|---|---:|---:|---:|---:|
| A: distance | 0,2865 | [0,2851; 0,2881] | 35,09% | 55,22% |
| B: context | 0,3317 | [0,3301; 0,3333] | 41,70% | 62,57% |
| C: full | 0,3500 | [0,3483; 0,3517] | 43,70% | 64,74% |
| D: loadout_history | 0,4219 | [0,4201; 0,4236] | 48,99% | 69,15% |

| Mức tăng | Hiệu Macro-F1 | CI 95% hiệu số |
|---|---:|---:|
| A->B | +0,0452 | [+0,0439; +0,0466] |
| B->C | +0,0182 | [+0,0170; +0,0195] |
| C->D | +0,0719 | [+0,0705; +0,0734] |

**Q1:** chỉ khoảng cách đạt Macro-F1 0,2865. **Q2:** thêm thời gian và vị trí/bản đồ nâng lên 0,3500. **Q3:** lịch sử nhân quả nâng lên **0,4219**, tăng **+0,071931**, CI 95% **[+0,070459; +0,073394]**; CI không chứa 0. Đây là so sánh C/D cùng sáu lớp và cùng dữ liệu; không so trực tiếp với Macro-F1 7 lớp của báo cáo cũ.

## Nhóm có và không có lịch sử trên test

| Nhóm | Số dòng | C Macro-F1 | D Macro-F1 | C Accuracy | D Accuracy | D Top-2 |
|---|---:|---:|---:|---:|---:|---:|
| Mạng đầu tiên | 262.664 | 0,3365 | 0,3315 | 40,71% | 37,56% | 60,24% |
| Có lịch sử | 221.410 | 0,3356 | 0,5160 | 47,25% | 62,55% | 79,72% |

Nhóm có lịch sử chiếm **45,74%** test. Lợi ích tập trung ở nhóm này: Macro-F1 **0,5160**, Accuracy **62,55%**, Top-2 **79,72%**. Với mạng đầu tiên, D không cải thiện: Macro-F1 và Accuracy đều thấp hơn C. Không diễn giải lịch sử giúp mọi sự kiện.

## Chín mô hình/biến thể chính trên test

| Mô hình | Macro-F1 | CI 95% | Accuracy | Top-2 |
|---|---:|---:|---:|---:|
| majority_plain | 0,1150 | [0,1147; 0,1152] | 52,65% | 64,83% |
| logistic_balanced | 0,3711 | [0,3694; 0,3728] | 41,14% | 63,83% |
| naive_bayes_plain | 0,3182 | [0,3165; 0,3200] | 38,87% | 59,91% |
| decision_tree_plain | 0,3877 | [0,3856; 0,3899] | 59,58% | 77,63% |
| decision_tree_balanced | 0,3901 | [0,3884; 0,3917] | 44,43% | 65,32% |
| random_forest_plain | 0,3972 | [0,3950; 0,3994] | 60,03% | 78,58% |
| random_forest_balanced | 0,4219 | [0,4201; 0,4236] | 48,99% | 69,15% |
| hist_gradient_boosting_plain | 0,4060 | [0,4038; 0,4081] | 60,18% | 78,76% |
| hist_gradient_boosting_balanced | 0,4048 | [0,4032; 0,4065] | 45,51% | 66,49% |

Bảng so sánh cặp có 36 hiệu số và CI dùng chung mẫu bootstrap. Không điều chỉnh đa kiểm định; tránh diễn giải toàn bộ 36 CI thành bảo đảm đồng thời 95%.

## Phân tích lỗi và Q4

| Lớp | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| AR | 0,7859 | 0,5089 | 0,6178 | 254.854 |
| DMR | 0,3083 | 0,3666 | 0,3349 | 37.640 |
| Other | 0,4563 | 0,3958 | 0,4239 | 50.505 |
| SMG | 0,3165 | 0,3488 | 0,3319 | 60.463 |
| SR | 0,2599 | 0,6148 | 0,3654 | 21.662 |
| Shotgun | 0,3485 | 0,6657 | 0,4575 | 58.950 |

Không còn lớp hoạt động nào có F1=0. Nhầm lớn nhất là AR→Shotgun (35.746 sự kiện, trung vị 4,64 m), AR→SMG (31.181, 12,88 m), AR→SR (26.015, 121,09 m) và AR→DMR (22.116, 77,30 m). Cự ly ngắn vẫn khó phân biệt nhóm vũ khí.

**Q4:** Top-2 đạt **69,15%**; khi quy chiếu nhãn dự đoán sang ba vai trò tầm bắn, Accuracy đạt **63,30%**, Macro-F1 **0,6103**. Other/SMG/Shotgun → Close_Range; AR/LMG → Mid_Range; DMR/SR → Long_Range. LMG đã gộp vào Other nên được quy chiếu theo nhãn hiệu lực Other.

Permutation importance trên 2.000 dòng test, 3 lần lặp: `last_weapon_group` có mức giảm Macro-F1 lớn nhất (0,03745 ± 0,00210 SD). Nhiều đặc trưng khác có hiệu ứng nhỏ hoặc âm; đây là phép đo trên mẫu nhỏ và đặc trưng tương quan, không phải bằng chứng nhân quả hay lý do chọn lại đặc trưng sau test.

## Thời gian, tài nguyên và giới hạn

- Runner: **4.345,20 giây / 72,42 phút**, gồm pytest/EDA/preprocessing/train/diagnostics/evaluation, không gồm chờ cấp máy. Lượt fit/predict/proba của RF được chọn: 239,53 giây.
- RSS đỉnh tiến trình cha **5.177,63 MiB / 5,06 GiB**. Đây là high-water RSS tích lũy, không phải RAM riêng từng mô hình hoặc peak toàn máy. Có ghi RSS sau evaluation.
- Kaggle: sklearn 1.6.1, pandas 2.3.3, numpy 2.1.3, pyarrow 23.0.1. Kernel private CPU, Internet tắt, dữ liệu gắn trực tiếp.
- Pilot D đạt validation 0,4306; train dài đạt 0,4227 trên cohort lớn hơn. Không coi tăng dữ liệu là đã nâng điểm pilot; hai cohort khác nhau nên không dùng hiệu số đó làm kiểm định cặp.
- Dữ liệu 2017–2018 và thiên lệch thu thập, chỉ chunk 0; loại Down and Out, không phân biệt đồng đội, Other không đồng nhất. Mô hình cần lịch sử trước đó đúng theo định nghĩa; không dùng nhãn hiện tại/tương lai.

## Bộ bảng và bằng chứng

- [Toàn bộ chỉ số test](main/test/test_metrics.csv), [từng lớp](main/test/per_class_metrics.csv), [ablation](main/test/ablation.csv), [CI mức tăng](main/test/ablation_gains.csv).
- [Hai nhóm lịch sử](main/test/history_subset_metrics.csv), [so sánh cặp](main/test/paired_model_differences.csv), [1.000 bootstrap draws](main/test/bootstrap_macro_f1.csv).
- [Confusion matrix](main/test/confusion_matrix.csv), [cặp nhầm](main/test/confused_pairs.csv), [theo cự ly](main/test/distance_metrics.csv), các bảng `other_*`, [importance](main/test/feature_importance.csv).
- [Hình confusion counts](main/figures/confusion_matrix_counts.png), [hình theo tỷ lệ từng lớp](main/figures/confusion_matrix_row_normalized.png), [importance có SD](main/figures/permutation_importance_with_sd.png). Các hình này được dựng từ CSV đã đóng băng, không chạy lại dự đoán/evaluation.
- [Readiness](main/provenance/readiness.json), [JUnit Kaggle](main/provenance/tests.xml), [kiểm chứng/checksum](main/provenance/history-full-final-verification-20261022.json).

Bản gốc output được giữ tại `artifacts/kaggle-history-full-final-output-20261022/full/`; model/parquet đầy đủ lưu ở Kaggle version 1. Không sửa selection/model hoặc chạy lại test dựa trên số liệu này.
