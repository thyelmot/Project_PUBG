# Xử lý Overfitting cho Random Forest trên Validation — 21/10/2026

**Kết hợp sub-bootstrapping (`max_samples = 0,15–0,20`) và làm dịu trọng số lớp (`tempered_class_weights`) đã giảm chênh lệch train–validation từ 4,8 đến 7,9 lần (`0,4204` xuống `0,0871` và `0,0530`), giảm số lá trung bình 3,9–7,5 lần và giảm thời gian huấn luyện ~4 lần, đồng thời giữ nguyên hoặc nâng nhẹ macro-F1 validation (`0,3021` → `0,3058`) và accuracy (`0,4413` → `0,4574–0,4829`). Lưới `parameter_grid('random_forest', quick=False)` đã được cập nhật cho bundle train dài.**

## Điều kiện so sánh

- Dùng lại đúng artifact đóng băng của [pilot trước, version 1](https://www.kaggle.com/code/sangtranminh211/pubg-weapon-plan-update-20261021), không lấy mẫu hay chia tập lại: **100.000 dòng train, 28.398 dòng validation thuộc 434 trận**.
- Giữ nguyên **300 cây**, seed 42, preprocessing học trên train.
- RF cũ (`baseline`) được nạp lại và tái lập đúng macro-F1 validation `0,3021361210235184`. Hash dataset manifest, metadata và pipeline gốc khớp lượt trước; phiên bản thư viện được kiểm tra khớp trước khi nạp model.
- Điểm train dùng cùng mẫu 20.000 dòng giữ tỷ lệ lớp như chẩn đoán trước; ngoài ra các cấu hình mới còn tính thêm **OOB macro-F1** (`oob_score=True`) trên toàn bộ 100.000 dòng train. **Không đọc test thật.**

## Nguyên nhân cắt tỉa lá thô (`depth12_leaf20`) làm tụt điểm

- Khi tăng `min_samples_leaf` lên `20–50` và giảm `max_depth` xuống `10–12` dưới trọng số `class_weight='balanced_subsample'` ($w_c = \frac{N}{K \cdot N_c}$), mỗi lá chứa trung bình ~119 mẫu pha trộn nhiều nhóm vũ khí.
- Vì trọng số của các lớp thiểu số lớn gấp `4,2×` đến `87×` trọng số của `AR` (`0,27`), bất kỳ lá thô nào có pha trộn mẫu thiểu số đều bị trọng số lớp thiểu số áp đảo. Hệ quả là recall của `AR` sụt từ **52,04% xuống 31,58%** (F1 của `AR` rơi từ `0,6002` xuống `0,4450`), và `DMR` bị `SR` lấn át (`F1` giảm từ `0,2192` xuống `0,1645`).

## Giải pháp đã triển khai và đối chiếu (8 cấu hình)

1. **Sub-bootstrapping (`subboot_d18_leaf5_ms015`, `subboot_d18_leaf5_ms020`):** Giới hạn mỗi cây chỉ lấy mẫu ngẫu nhiên `15%` hoặc `20%` số dòng train (`max_samples = 0,15 / 0,20`), giữ `max_depth = 18, min_samples_leaf = 5`. Khi đó 80%–85% số cây trong rừng là out-of-bag đối với mỗi mẫu train, ngăn rừng cây học thuộc lòng điểm train mà vẫn giữ lá đủ mịn để bảo toàn recall của `AR` và `DMR`.
2. **Làm dịu trọng số lớp (`tempered_d18_leaf5_ms020`, `tempered_d16_leaf8_ms020`, `tempered_d14_leaf12_ms025`):** Dùng trọng số lũy thừa dưới tuyến tính $w_c \propto (\frac{N}{K \cdot N_c})^\alpha$ với $\alpha \in \{0,75; 0,80; 0,85\}$ và trần `max_ratio = 10–12`, cho phép tăng `min_samples_leaf` lên `8–12` và giảm `max_depth` xuống `14–16` mà không làm sập recall lớp `AR`.
3. **Lược bỏ tọa độ (`no_pos_d16_leaf8_ms020`):** Bỏ 6 đặc trưng vị trí có permutation importance âm (`feature_set = 'no_position'`), chỉ giữ khoảng cách, log khoảng cách, thời gian, giai đoạn trận và bản đồ.

## Kết quả thực nghiệm trên Kaggle (version 2)

| Cấu hình | Đặc trưng | Trọng số | Macro-F1 val (95% CI) | Macro-F1 train | Gap (train−val) | OOB Macro-F1 (OOB−val) | Accuracy val | Số lá TB/cây | Fit (s) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| `baseline` (`d=20, leaf=5, ms=None`) | `full` | `balanced_subsample` | 0.3021 `[0.2959, 0.3076]` | 0.7226 | **0.4204** | — | 0.4413 | 7,083.7 | 81.6 |
| `depth12_leaf20` (`d=12, leaf=20, ms=None`) | `full` | `balanced_subsample` | 0.2799 `[0.2745, 0.2852]` | 0.3450 | 0.0651 | 0.2791 (`-0.0008`) | 0.3552 | 841.6 | 61.5 |
| **`subboot_d18_leaf5_ms015`** | `full` | `balanced_subsample` | **0.3058** `[0.2995, 0.3115]` | 0.3930 | **0.0871** | **0.3051** (`-0.0007`) | **0.4574** | **1,803.4** | **21.0** |
| `subboot_d18_leaf5_ms020` | `full` | `balanced_subsample` | 0.3056 `[0.2994, 0.3112]` | 0.4182 | 0.1127 | 0.3049 (`-0.0006`) | 0.4534 | 2,240.1 | 26.1 |
| `tempered_d18_leaf5_ms020` ($\alpha=0,85$) | `full` | `tempered_power` | 0.3038 `[0.2973, 0.3097]` | 0.4168 | 0.1130 | 0.3055 (`+0.0016`) | **0.4829** | 2,180.6 | 24.5 |
| **`tempered_d14_leaf12_ms025`** ($\alpha=0,75$) | `full` | `tempered_power` | **0.3036** `[0.2974, 0.3091]` | 0.3567 | **0.0530** | 0.2985 (`-0.0051`) | **0.4742** | **938.5** | **24.1** |
| `tempered_d16_leaf8_ms020` ($\alpha=0,80$) | `full` | `tempered_power` | 0.3024 `[0.2960, 0.3082]` | 0.3787 | 0.0763 | 0.3030 (`+0.0005`) | 0.4723 | 1,326.8 | 22.8 |
| `no_pos_d16_leaf8_ms020` ($\alpha=0,80$) | `no_position` | `tempered_power` | 0.2975 `[0.2916, 0.3027]` | 0.3466 | 0.0491 | 0.2941 (`-0.0034`) | 0.4553 | 1,339.4 | 14.3 |

## Kiểm định cặp Bootstrap trên Validation (1.000 lần lặp theo `match_id`, seed 42)

| Cặp đối chiếu (`after − before`) | Hiệu số Macro-F1 | CI 95% | Kết luận |
|---|---:|---|---|
| `depth12_leaf20 − baseline` | -0.0222 | `[-0.0267, -0.0173]` | `before_higher` (cắt tỉa thô làm giảm điểm) |
| `subboot_d18_leaf5_ms015 − baseline` | +0.0037 | `[-0.0003, +0.0074]` | `inconclusive` (điểm tương đương/nhỉnh hơn nhẹ, gap giảm 4,8×) |
| `subboot_d18_leaf5_ms020 − baseline` | +0.0034 | `[-0.0004, +0.0069]` | `inconclusive` (điểm tương đương/nhỉnh hơn nhẹ, gap giảm 3,7×) |
| `tempered_d14_leaf12_ms025 − baseline` | +0.0015 | `[-0.0028, +0.0054]` | `inconclusive` (điểm tương đương, gap giảm 7,9×, số lá giảm 7,5×) |
| `subboot_d18_leaf5_ms015 − depth12_leaf20` | +0.0259 | `[+0.0209, +0.0309]` | `after_higher` (vượt trội có ý nghĩa thống kê so với cắt tỉa thô) |
| `tempered_d14_leaf12_ms025 − depth12_leaf20` | +0.0237 | `[+0.0186, +0.0283]` | `after_higher` (vượt trội có ý nghĩa thống kê so với cắt tỉa thô) |

## F1 từng lớp trên Validation

| Cấu hình | AR | DMR | LMG | Other | SMG | SR | Shotgun |
|---|---:|---:|---:|---:|---:|---:|---:|
| `baseline` | 0.6002 | 0.2192 | 0.0000 | 0.4131 | 0.1939 | 0.3032 | 0.3854 |
| `depth12_leaf20` | 0.4450 | 0.1645 | 0.0185 | 0.4065 | 0.2153 | 0.3022 | 0.4073 |
| **`subboot_d18_leaf5_ms015`** | **0.6188** | **0.2171** | 0.0000 | **0.4144** | 0.1878 | 0.3016 | **0.4010** |
| `subboot_d18_leaf5_ms020` | 0.6127 | 0.2127 | 0.0000 | 0.4162 | 0.1910 | 0.3077 | 0.3986 |
| `tempered_d18_leaf5_ms020` | 0.6529 | 0.1919 | 0.0000 | 0.4147 | 0.1636 | 0.3051 | 0.3986 |
| **`tempered_d14_leaf12_ms025`** | **0.6392** | 0.1829 | 0.0000 | 0.4119 | 0.1578 | **0.3262** | **0.4074** |
| `tempered_d16_leaf8_ms020` | 0.6392 | 0.1831 | 0.0000 | 0.4148 | 0.1617 | 0.3158 | 0.4022 |
| `no_pos_d16_leaf8_ms020` | 0.6187 | 0.2065 | 0.0000 | 0.3879 | 0.1602 | 0.3032 | 0.4057 |

## Quyết định cập nhật vào Pipeline chính

- Cập nhật `parameter_grid('random_forest', quick=False)` trong [`src/pubg_weapon/training.py`](../src/pubg_weapon/training.py) sang hai cấu hình sub-bootstrapping (`n_estimators = 200, max_depth = 18, min_samples_leaf = 5, max_samples = 0.2` và `n_estimators = 300, max_depth = 18, min_samples_leaf = 5, max_samples = 0.15`).
- Các cấu hình này giữ nguyên hoặc cải thiện nhẹ Macro-F1 validation (`0,3058`), thu hẹp gap train–validation xuống `0,0871` (nhỏ hơn cả gap `0,1073` của HistGradientBoosting), đồng thời giảm ~4 lần số lá và thời gian fit khi chạy full 1 triệu dòng train.

## Kiểm tra và tái lập

- **Local: 57/57 pass**, không skip/failure/error ([`local-rf-regularization-tests-20261021.xml`](local-rf-regularization-tests-20261021.xml)).
- **Kaggle: 57/57 pass**, không skip/failure/error ([`kaggle-rf-regularization-tests-20261021.xml`](kaggle-rf-regularization-tests-20261021.xml)).
- [Kernel thử RF](https://www.kaggle.com/code/sangtranminh211/pubg-rf-regularization-20261021), version 2, private CPU, Internet tắt. [Readiness JSON](rf-regularization-20261021.json).
- Bảng dữ liệu: [validation metrics](tables/rf_regularization_validation_metrics.csv), [CI hiệu số](tables/rf_regularization_paired_differences.csv), [F1 từng lớp](tables/rf_regularization_per_class_metrics.csv), [các lần bootstrap](tables/rf_regularization_bootstrap_macro_f1.csv).

```bash
python scripts/06_rf_regularization.py \
  --processed PATH_TO_FROZEN_PILOT/full/processed \
  --baseline-run PATH_TO_FROZEN_PILOT/full/models \
  --output reports/rf-comparison-new
```
