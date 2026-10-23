# Kế hoạch bài tập lớn khai phá dữ liệu (Bản nâng cấp tăng chất lượng mô hình)

## Dự đoán loại vũ khí gây chết trong PUBG từ ngữ cảnh không gian - thời gian và lịch sử hạ gục nhân quả trong trận

Dataset: PUBG Match Deaths and Statistics (Kaggle, tác giả skihikingkevin)
Phần dữ liệu dùng: deaths (hơn 65 triệu sự kiện chết, khoảng 720 nghìn trận; khai thác trên chunk 0 gồm 13.426.348 dòng)

---

## I. Phát biểu bài toán và động lực nâng cấp

- **Loại bài toán:** phân loại đa lớp có giám sát.
- **Mỗi mẫu:** một sự kiện hạ gục hợp lệ giữa hai người chơi (một dòng trong bảng `deaths`).
- **Đầu vào:** thông tin đã biết tại đúng thời điểm pha hạ gục xảy ra ($t$), gồm hai tầng:
  1. **Ngữ cảnh không gian - thời gian tức thời (Event Context):** khoảng cách giữa killer và victim, thời điểm trong trận, giai đoạn trận, vị trí chuẩn hóa trên bản đồ, khoảng cách tới tâm bản đồ, loại bản đồ.
  2. **Lịch sử trang bị nhân quả của killer trong cùng trận (Causal In-Match Loadout History, $t' < t$):** số mạng killer đã hạ gục trước thời điểm $t$ trong cùng trận, nhóm vũ khí và khoảng cách của pha hạ gục gần nhất trước đó ($t' < t$), khoảng thời gian kể từ pha hạ gục trước đó.
- **Đầu ra:** nhóm vũ khí gây ra cái chết (`weapon_group`), suy từ cột `killed_by`.
- **Động lực nâng cấp (rút ra từ kết quả validation trên 1.000.000 dòng train, trước khi mở tập test):**
  - Khi chỉ dùng ngữ cảnh tức thời của một sự kiện đơn lẻ, việc tăng dữ liệu huấn luyện gấp 10 lần (từ 100.000 lên 1.000.000 dòng) giữ nguyên Macro-F1 validation ở mức `0,3020` (so với `0,3021` ở pilot). Nguyên nhân là 78% pha giao tranh diễn ra ở cự ly 0–50 m, nơi mọi nhóm súng đều có thể gây hạ gục, cộng thêm lớp `LMG` quá thưa (`0,65%`) đạt `F1 = 0,000`.
  - Trong thực tế PUBG, mỗi người chơi mang cố định 1–2 vũ khí xuyên suốt trận đấu. Vũ khí mà người đó đã dùng ở các pha hạ gục **trước đó** ($t' < t$) trong cùng trận là thông tin có thật tại thời điểm $t$ (không rò rỉ tương lai), giúp phá vỡ trần thông tin của bối cảnh đơn lẻ.

### Câu hỏi nghiên cứu

- **Q1 (Tầm bắn cơ sở):** Khoảng cách hạ gục quyết định loại vũ khí ở mức nào? Nếu chỉ dùng một đặc trưng này (Cấu hình A) thì mô hình đạt Macro-F1 bao nhiêu?
- **Q2 (Đóng góp của ngữ cảnh không gian - thời gian):** Thêm thời gian (Cấu hình B) và toàn bộ ngữ cảnh bản đồ/vị trí (Cấu hình C) cải thiện được bao nhiêu so với chỉ dùng khoảng cách, và trần thông tin của ngữ cảnh đơn lẻ nằm ở đâu?
- **Q3 (Đóng góp của lịch sử trang bị nhân quả trong trận):** Khi bổ sung lịch sử hạ gục nhân quả ($t' < t$) của killer trong cùng trận (Cấu hình D), Macro-F1 và Accuracy tăng lên bao nhiêu trên toàn tập và riêng trên nhóm sự kiện mà killer đã có mạng trước đó (`prior_kills >= 1`)?
- **Q4 (Quy luật nhầm lẫn và vai trò tầm bắn):** Các nhóm vũ khí nào bị nhầm lẫn với nhau nhiều nhất, sự nhầm lẫn đó có tuân theo quy luật tầm bắn không, và nếu quy chiếu về 3 vai trò tầm bắn (`Close` / `Mid` / `Long`) hoặc xét `Top-2 Accuracy` thì mức độ chính xác đạt bao nhiêu?

### Kết quả thực nghiệm đã xác minh (cập nhật 22/10/2026)

**Bài chính đã hoàn tất và khóa** tại [Kaggle full-final version 1](https://www.kaggle.com/code/sangtranminh211/pubg-loadout-history-full-final-20261022). Mô hình chọn bằng Macro-F1 validation là **Random Forest balanced** (`300` cây, `max_depth=18`, `min_samples_leaf=5`, `max_samples=0.15`, `class_weight=balanced_subsample`). Không đổi mô hình chính theo các thí nghiệm phụ lục sau đó.

| Chỉ số | Validation (480.891 dòng / 7.373 trận) | Holdout Test (484.074 dòng / 7.418 trận) |
|---|---:|---:|
| Macro-F1 | **0,422652** | **0,421898** |
| CI 95% Macro-F1 | [0,420887; 0,424483] | [0,420147; 0,423602] |
| Accuracy | 49,10% | 48,99% |
| Weighted-F1 | 0,510177 | 0,509038 |
| Top-2 Accuracy | 69,23% | 69,15% |
| Tactical Role Macro-F1 | 0,611282 | 0,610254 |
| Tactical Role Accuracy | 63,39% | 63,30% |

- Macro-F1 trên mẫu train stratified 20.000 dòng: `0,453455`; gap train–validation: **`0,030803`**. Đây là điểm trên mẫu train, không phải toàn bộ 1 triệu dòng.
- Majority baseline trên test: Accuracy **52,65%**, Macro-F1 `0,114966`. RF balanced được chọn theo Macro-F1 và **không vượt majority về Accuracy toàn tập**. HGB plain đạt Accuracy `60,18%`, Top-2 `78,76%`, Macro-F1 `0,405971`; RF plain đạt Accuracy `60,03%`, Top-2 `78,58%`, Macro-F1 `0,397204`. Không gộp các chỉ số này thành kết quả của cùng một mô hình.

| Ablation trên test (cùng RF / tham số / cân bằng lớp) | Macro-F1 | Accuracy | Top-2 Accuracy |
|---|---:|---:|---:|
| A — distance | 0,286523 | 35,09% | 55,22% |
| B — context | 0,331741 | 41,70% | 62,57% |
| C — full | 0,349967 | 43,70% | 64,74% |
| D — loadout_history | **0,421898** | **48,99%** | **69,15%** |

C→D trên test tăng **`+0,071931` Macro-F1**, paired cluster bootstrap theo `match_id` 1.000 lần, CI 95% **`[+0,070459; +0,073394]`**. A→B tăng `+0,045218` (CI `[+0,043938; +0,046612]`); B→C tăng `+0,018226` (CI `[+0,016979; +0,019541]`).

| Nhóm test của mô hình D | Số dòng | Macro-F1 | Accuracy | Top-2 Accuracy |
|---|---:|---:|---:|---:|
| Mạng đầu tiên (`has_prior_kill=0`) | 262.664 | 0,331470 | 37,56% | 60,24% |
| Có lịch sử (`has_prior_kill=1`) | 221.410 (45,74%) | **0,516019** | **62,55%** | **79,72%** |

Lợi ích tập trung ở nhóm có lịch sử. Trên mạng đầu tiên, C đạt Macro-F1 `0,336545` và Accuracy `40,71%`, cao hơn D; không kết luận lịch sử giúp mọi sự kiện.

Bằng chứng: [báo cáo chính](HISTORY_FULL_FINAL_RESULTS.md), [bảng test](main/test/test_metrics.csv), [ablation](main/test/ablation.csv), [CI mức tăng](main/test/ablation_gains.csv), [hai nhóm lịch sử](main/test/history_subset_metrics.csv). Kaggle **65/65 test pass**, không cảnh báo mô hình; runner `4.345,20 s` (~72,42 phút), RSS đỉnh tiến trình cha `5.177,63 MiB` (~5,06 GiB, high-water tích lũy).

### Kỳ vọng trước khi chạy full (lưu để đối chiếu, không phải số liệu cuối)

- **Cấu hình A (chỉ khoảng cách):** Macro-F1 khoảng `0,21–0,25`.
- **Cấu hình C (toàn bộ ngữ cảnh không gian - thời gian, 6 lớp sau khi gộp lớp hiếm < 1%):** Macro-F1 khoảng `0,34–0,35`, Top-2 Accuracy khoảng `66%`.
- **Cấu hình D (thêm lịch sử nhân quả $t' < t$ trong trận):**
  - Trên toàn bộ sự kiện: Macro-F1 tăng lên khoảng **`0,40–0,42`**, Accuracy đạt **`~51–55%`**, Top-2 Accuracy đạt **`~70%`**.
  - Trên nhóm sự kiện mà killer đã có ít nhất 1 mạng trước đó trong trận (~46% tổng số sự kiện): Macro-F1 đạt **`~0,47–0,48`**, Accuracy đạt **`~62–63%`** (vượt xa mốc Majority baseline `52,7%`), Top-2 Accuracy đạt **`~79%`**.

---

## II. Định nghĩa nhãn và quy tắc gộp lớp hiếm

Cột `killed_by` trong chunk 0 có 57 giá trị phân biệt, được ánh xạ tường minh tại `configs/label_mapping.json` (gặp nhãn lạ pipeline dừng ngay):

| Nhóm nhãn | Thành phần (đã đối chiếu với 57 giá trị thật trong chunk 0) |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `AR`      | AKM, M16A4, M416, SCAR-L, AUG, Groza                                                                                                       |
| `DMR`     | SKS, Mini 14 (và alias Mini14), Mk14, SLR, VSS                                                                                             |
| `SR`      | Kar98k, M24, AWM, Win94                                                                                                                    |
| `SMG`     | Micro UZI, UMP9, Tommy Gun, Vector                                                                                                         |
| `Shotgun` | S686, S1897, S12K, Sawed-off (`death.WeapSawnoff_C`)                                                                                       |
| `Other`   | Súng lục (P92, P1911, P18C, R1895, R45), cận chiến (Punch, Pan, Sickle, Crowbar, Machete), Crossbow, lựu đạn, bom xăng/lửa, xe cộ các loại |
| `LMG`     | DP-28, M249 (chiếm ~0,65% sau làm sạch — thuộc diện lớp cực hiếm dưới ngưỡng 1,0%)                                                         |

### Quy tắc gộp lớp hiếm (nâng cấp từ thực nghiệm 1 triệu dòng)

- Tỉ lệ từng nhóm được tính **chỉ trên tập train sau làm sạch** để không rò thông tin từ validation/test.
- **Nâng ngưỡng gộp lớp hiếm `MIN_CLASS_FRACTION` từ `0,5%` lên `1,0%` (`0,01`):**
  - Ở lần chạy 1 triệu dòng, `LMG` chiếm `0,669%` (vượt nhẹ ngưỡng 0,5% cũ) nhưng có cơ chế bắn tự động tầm trung trùng lấp hoàn toàn với `AR`, dẫn đến `F1 = 0,000` ở hầu hết các mô hình và kéo Macro-F1 trung bình 7 lớp tụt một cách cơ học.
  - Với ngưỡng `1,0%` tính trên tập train, `LMG` được gộp tự động vào `Other` (hoặc lưu trong `effective_label_mapping.json` thành 6 lớp hoạt động: `AR`, `DMR`, `SR`, `SMG`, `Shotgun`, `Other`), vẫn được tách riêng trong bảng phân tích thành phần `other_components.csv`.
- **Ánh xạ phụ sang 3 vai trò tầm bắn (`tactical_role`) ở bước đánh giá:**
  - `Close_Range`: `Shotgun`, `SMG`, `Other` (chiếm ~34%).
  - `Mid_Range`: `AR` (và `LMG`, chiếm ~54%).
  - `Long_Range`: `DMR`, `SR` (chiếm ~12%).

### Nhãn bị loại khỏi bài toán (ánh xạ thành `null`, thống kê riêng trong `excluded_label_counts.csv`)

| Nhãn | Số dòng trong chunk 0 | Tỉ lệ | Lý do loại |
| ---- | ---: | ---: | ---- |
| `Down and Out` | 2.310.417 | 17,21% | Nạn nhân chết vì mất máu sau khi bị knock (duo/squad); dữ liệu không ghi vũ khí gây knock ban đầu |
| `Bluezone`, `RedZone`, `death.RedZoneBomb_C` | ~675.221 | ~5,03% | Chết do môi trường, không có killer hợp lệ |
| `Falling`, `Drown` | ~201.731 | ~1,50% | Chết do môi trường |
| `death.PlayerMale_A_C` | 1 | ~0,00% | Mã đối tượng nhân vật lỗi, không xác định được vũ khí |

---

## III. Dữ liệu và lấy mẫu

- **Nguồn dữ liệu:** `kill_match_stats_final_0.csv` (13.426.348 dòng, 12 cột gốc).
- **Holdout Test cố định trên toàn nguồn:** 15% tổng số `match_id` của chunk 0 (loại trừ 2.294 trận trong `configs/development_matches.csv`) đã được khóa bằng mã băm SHA-256 (`3cd3e1a76c8679b510ee791bbd280a3684a51ffc03676c39ffbcc7466296c8ce`). Holdout được giữ kín đến lần đánh giá cuối ngày **22/10/2026**, đã chấm **đúng một lần** và khóa. Các thí nghiệm phụ lục chỉ dùng train/CV/validation, không mở lại holdout.
- **Lấy mẫu theo trận (`match_id`):** chọn ngẫu nhiên 50.000 trận (`seed = 42`) cho bản train dài (tương ứng 4.525.712 sự kiện gốc, sau làm sạch còn 3.220.155 sự kiện hợp lệ), và 3.000 trận cho bản pilot/validation nhanh.
- **Giữ nguyên toàn bộ sự kiện của mỗi trận khi tính đặc trưng lịch sử trong trận:**
  - Bước tính đặc trưng lịch sử nhân quả (`in_match_history`) phải được thực hiện trên **toàn bộ sự kiện hợp lệ của trận** sau khi làm sạch, **trước khi** rút gọn tập train xuống tối đa 1.000.000 dòng (`cap_train`). Nhờ vậy chuỗi sự kiện trong mỗi trận không bị đứt quãng do bước giảm mẫu.
- **Giảm mẫu tập train (`cap_train`):** chỉ giảm mẫu tập train xuống tối đa 1.000.000 dòng (`34.614` trận, giữ nguyên tỉ lệ lớp); tập validation (`480.891` dòng / `7.373` trận) và tập test (`484.074` dòng / `7.418` trận) giữ nguyên 100% sự kiện.

---

## IV. Tiền xử lý (Cleaning tuần tự)

Áp dụng theo đúng thứ tự trên toàn bộ sự kiện của các trận đã lấy mẫu, lưu bảng kiểm toán `cleaning_counts.csv` và `excluded_label_counts.csv`:

1. `missing_killer`: loại dòng có `killer_name` rỗng hoặc thuộc danh sách giữ chỗ (`#unknown`, `unknown`, `none`, `null`, `nan`).
2. `self_kill`: loại dòng tự hạ gục (`killer_name == victim_name`).
3. `zero_coordinates`: loại dòng có tọa độ killer hoặc victim bằng `(0, 0)`.
4. `invalid_coordinates_or_time`: loại dòng có tọa độ ngoài `[0, 800000]` hoặc `time` không thuộc `(0, 2700]`.
5. `exact_duplicate`: loại dòng trùng lặp hoàn toàn trên toàn bộ mẫu.
6. `invalid_identity_or_map`: loại dòng thiếu `match_id`, thiếu `victim_name`, hoặc `map` không thuộc `{ERANGEL, MIRAMAR}`.
7. `environment_or_unknown_weapon`: ánh xạ `killed_by` sang `weapon_group`, loại các dòng có nhãn `null` (`Down and Out`, môi trường).

---

## V. Thiết kế đặc trưng (Feature Engineering) và Chống rò rỉ

### 1. Nhóm đặc trưng khoảng cách (`DISTANCE_FEATURES` — Cấu hình A)
- `kill_distance_m`: khoảng cách Euclid giữa killer và victim đổi ra mét (chia cho 100).

### 2. Nhóm đặc trưng ngữ cảnh thời gian (`CONTEXT_FEATURES` — Cấu hình B)
- `kill_distance_m` + `time` (giây kể từ đầu trận).

### 3. Nhóm đặc trưng ngữ cảnh không gian - thời gian đầy đủ (`FULL_CONTEXT_FEATURES` — Cấu hình C)
- `kill_distance_m`, `log_kill_distance` ($\ln(1 + \text{distance})$).
- `time`, `time_phase` (`early`: $< 300\text{s}$, `mid`: $300\text{--}1200\text{s}$, `late`: $> 1200\text{s}$).
- `map` (`ERANGEL`, `MIRAMAR`).
- `killer_x_norm`, `killer_y_norm`, `victim_x_norm`, `victim_y_norm` (tọa độ chia 800.000).
- `killer_center_dist`, `victim_center_dist` (khoảng cách tới tâm bản đồ `(0.5, 0.5)`).

### 4. Nhóm đặc trưng lịch sử trang bị nhân quả trong trận (`HISTORY_FEATURES` — bổ sung vào Cấu hình D)
Với mỗi sự kiện $i$ của `(match_id, killer_name)` tại thời điểm $t_i$, chỉ tổng hợp từ tập các sự kiện hợp lệ $E_{\text{prior}}(i) = \{j \mid \text{match\_id}_j = \text{match\_id}_i,\; \text{killer\_name}_j = \text{killer\_name}_i,\; t_j < t_i\}$:
- `has_prior_kill`: biến nhị phân (`1` nếu $|E_{\text{prior}}(i)| \ge 1$, `0` nếu là mạng đầu tiên của killer trong trận).
- `prior_kills_in_match`: số lượng sự kiện trong $E_{\text{prior}}(i)$ (số mạng killer đã hạ gục ở các giây trước đó $t' < t$).
- `last_weapon_group`: nhóm vũ khí (`weapon_group` sau khi áp dụng quy tắc gộp lớp hiếm của tập train) ở sự kiện gần nhất có $t' < t$; nhận giá trị `'NONE'` nếu $E_{\text{prior}}(i) = \emptyset$. Nếu tại thời điểm $t'$ gần nhất có nhiều hơn một sự kiện cùng giây (ví dụ lựu đạn/xe hạ nhiều người), lấy nhóm vũ khí xuất hiện nhiều nhất ở giây $t'$ đó.
- `last_kill_distance_m`: khoảng cách hạ gục trung bình của sự kiện gần nhất tại $t' < t$ (`0,0` khi `has_prior_kill == 0`).
- `time_since_last_kill`: $t_i - \max_{j \in E_{\text{prior}}(i)} t_j$ (nhận `-1,0` khi `has_prior_kill == 0`).
- `dominant_prior_weapon`: nhóm vũ khí được killer sử dụng nhiều nhất trong toàn bộ $E_{\text{prior}}(i)$ (`'NONE'` nếu $E_{\text{prior}}(i) = \emptyset$).

### 5. Quy tắc chống rò rỉ nghiêm ngặt cho đặc trưng lịch sử
- **Chỉ tính trong phạm vi một trận (`match_id`):** tuyệt đối không nối lịch sử người chơi qua nhiều trận khác nhau, và vì phép chia train/validation/test tách rời theo `match_id`, không có bất kỳ sự kiện nào của trận validation/test giao với trận train.
- **Ràng buộc nhân quả chặt ($t' < t$):** nếu hai sự kiện của cùng một killer có cùng timestamp ($t_1 = t_2$), sự kiện này **không** được nhìn thấy nhãn hay khoảng cách của sự kiện kia.
- **Áp dụng bảng nhãn hiệu lực từ tập train:** các cột `last_weapon_group` và `dominant_prior_weapon` phải được ánh xạ qua `effective_label_mapping` (đã gộp lớp hiếm dựa trên tập train) để không bao giờ lộ tên vũ khí thô hay lớp hiếm chưa gộp.
- **Danh sách đặc trưng cấm đưa vào mô hình (`FORBIDDEN_FEATURES`):** `killed_by`, `cause_for_audit`, `weapon_group`, `match_id`, `killer_name`, `victim_name`, và 3 cột `placement` trong bài toán chính.

---

## VI. Mô hình và Xử lý mất cân bằng

So sánh 6 họ mô hình trên cùng tập dữ liệu:
1. **Majority class (`DummyClassifier`):** đoán lớp đông nhất (`AR`).
2. **Logistic Regression:** `StandardScaler` + `OneHotEncoder`, `class_weight='balanced'`.
3. **Gaussian Naive Bayes:** mốc tham chiếu xác suất.
4. **Decision Tree:** `max_depth = 12, min_samples_leaf = 5`, so sánh không cân bằng (`plain`) và có cân bằng (`balanced`).
5. **Random Forest:** so sánh `plain` và `balanced`, sử dụng cấu hình chống overfitting đã kiểm chứng trên Kaggle (`n_estimators = 200/300, max_depth = 18, min_samples_leaf = 5, max_samples = 0.20/0.15`), mục tiêu kiểm soát gap train–validation dưới `0,09`. Full D hiện tại đạt gap `0,030803` trên mẫu train 20.000 dòng; mốc `0,053` và mức giảm thời gian ở thí nghiệm C trước đó là kết quả lịch sử, không phải số đo của full D.
6. **HistGradientBoosting:** `max_iter = 150/250, learning_rate = 0.1/0.05, max_leaf_nodes = 31/15`, so sánh `plain` và `balanced` (`sample_weight`).

### Ma trận thí nghiệm trong một lần chạy (`run_training`)
- **9 mô hình/biến thể trên cấu hình chính (`loadout_history` — Cấu hình D, hoặc `full` tùy chế độ):** giúp chọn ra mô hình mạnh nhất cho bài toán.
- **Chuỗi Ablation 4 bậc (A $\to$ B $\to$ C $\to$ D) trên cùng mô hình tốt nhất (hoặc cố định cả trên HistGradientBoosting và Random Forest):**
  - **A (`distance`):** chỉ `kill_distance_m`.
  - **B (`context`):** `kill_distance_m + time`.
  - **C (`full`):** toàn bộ ngữ cảnh không gian - thời gian đơn lẻ (11 đặc trưng).
  - **D (`loadout_history`):** ngữ cảnh không gian - thời gian + lịch sử trang bị nhân quả $t' < t$ trong trận (17 đặc trưng).

### Thí nghiệm Phụ lục (Bước C — Chỉ chạy trên Cross-Validation / Validation, không chạm tập Holdout Test đã khóa)
1. **Phụ lục C1 — Tìm kiếm lưới siêu tham số (`GridSearchCV` + `GroupKFold` theo `match_id`) & Đường cong đánh đổi trọng số lớp ($\alpha$):**
   - **Lưới siêu tham số trên `GroupKFold(n_splits=3)` theo `match_id`:**
     - `RandomForest`: duyệt tổ hợp `max_depth` $\in \{14, 18, 22\}$, `min_samples_leaf` $\in \{5, 10\}$, `max_samples` $\in \{0.15, 0.25\}$ (xuất `appendix_rf_gridsearch_cv.csv`).
     - `HistGradientBoosting`: duyệt tổ hợp `learning_rate` $\in \{0.05, 0.10\}$, `max_leaf_nodes` $\in \{15, 31, 63\}$, `min_samples_leaf` $\in \{20, 50\}$ (xuất `appendix_hgb_gridsearch_cv.csv`).
   - **Đường cong Pareto giữa `Macro-F1` và `Accuracy` theo hệ số điều hòa trọng số lớp (`tempered_class_weights`):**
     - Duyệt $\alpha \in \{0.00\text{ (plain)}, 0.35, 0.50, 0.65, 0.80, 1.00\text{ (balanced)}\}$ với công thức $w_c(\alpha) = \left(\frac{N}{K \cdot N_c}\right)^\alpha$ trên cả `RandomForest` và `HistGradientBoosting` (xuất `appendix_alpha_tradeoff.csv`).
     - Kiểm chứng trực quan mức đánh đổi theo $\alpha$ và xác định các điểm Pareto từ số liệu thực. Các mốc $\alpha=0$ cho Accuracy khoảng `60,2%`, $\alpha=1$ cho Macro-F1 khoảng `0,423`, hoặc $\alpha \in [0.50,0.65]$ đạt đồng thời Accuracy `>55%` và Macro-F1 `>0,415` là **kỳ vọng trước khi chạy**, không phải kết luận. Số liệu đã xác minh bên dưới cho thấy α=1 không tối ưu Macro-F1; đo Majority trên chính validation dùng cho đường cong.
2. **Phụ lục C2 — Đối chiếu bài toán chính (tiền nghiệm) với chế độ hậu nghiệm (`--with-placement`):**
   - So sánh trực tiếp cấu hình `D (loadout_history, không placement)` với cấu hình `D + placement (killer_placement, victim_placement, placement_gap)` trên tập Validation (xuất `appendix_placement_comparison.csv`).
   - Định lượng $\Delta\text{Macro-F1}$ và $\Delta\text{Accuracy}$ của D→D+placement, rồi đối chiếu với C→D trên cùng validation. Loại `placement` giúp tránh riêng nguồn thông tin thứ hạng cuối trận; thí nghiệm này không tự chứng minh mọi dạng rò rỉ khác đều bị triệt tiêu. Chỉ kết luận lịch sử đóng góp lớn hơn placement khi số đo thực nghiệm hỗ trợ.

### Kết quả và trạng thái Phụ lục C (kiểm tra 09:54 ngày 23/10/2026, giờ Việt Nam)

Các job dùng đúng **1.000.000 dòng train / 34.614 trận** và **480.891 dòng validation / 7.373 trận** của main run đã khóa. Đã hoàn tất thiết kế **87 fits + 12 lượt replay α** để xuất recall (không tính các phiên thử lỗi); **không đọc lại holdout** và không cập nhật lựa chọn mô hình bài chính.

| Phần | Trạng thái phiên Kaggle | Số liệu đã xác minh |
|---|---|---|
| C1.1 — RF GridSearchCV | **v1 COMPLETE; readiness passed** | 12 tổ hợp × 3 GroupKFold + 1 refit; 73/73 test Kaggle pass |
| C1.1 — HGB GridSearchCV | **v3 COMPLETE; readiness passed** | Đủ 12 tổ hợp × 3 GroupKFold + 1 refit; 76/76 test Kaggle pass; đã xác minh |
| C1.2 — α tradeoff | **Bảng gốc và recall v1 COMPLETE; readiness passed** | Đủ 12 điểm có Minority Recall; 72 recall từng lớp, 432 confusion cells; 80/80 test pass |
| C2 — D và D+placement | **v1 COMPLETE; readiness passed** | D→D+placement tăng +0,001339 Macro-F1 trên validation; 73/73 test Kaggle pass |

**RF CV đã hoàn tất:** `n_estimators=300` cố định; grid đúng `max_depth={14,18,22}`, `min_samples_leaf={5,10}`, `max_samples={0.15,0.25}`. Trọng số dùng $\alpha=1$, học lại bên trong từng fold; preprocessing cũng fit trong fold.

| Cấu hình RF CV tốt nhất | Macro-F1 CV trung bình | SD giữa 3 fold | Accuracy CV trung bình |
|---|---:|---:|---:|
| depth=22, min leaf=5, max_samples=0.15 | **0,432913** | **0,000628** | 51,45% |

Sau khi chọn bằng Macro-F1 CV và refit trên toàn bộ 1 triệu dòng train, mô hình này đạt trên validation: **Macro-F1 `0,431908`**, Accuracy **`51,20%`**, Weighted-F1 `0,527984`, Top-2 **`70,67%`**, Tactical Role Macro-F1 `0,624714`, Tactical Role Accuracy `65,01%`.

- `0,000628` là **SD giữa các fold**, không phải CI 95%. CV dùng trọng số cố định theo lớp $w_c=N/(K N_c)$, khác `balanced_subsample` của RF bài chính. Không quy toàn bộ chênh lệch validation cho riêng `max_depth`, và không thay mô hình/test đã khóa bằng RF CV này.
- Đã đối chiếu 38 source hash, hash train/validation/metadata, đủ 12 tổ hợp và mean/std từ 3 fold. Audit có 34.614 trận, tổng 1.000.000 dòng, mỗi trận thuộc đúng một fold validation CV; guard chỉ ghi nhận đọc `train.parquet` và `validation.parquet`.
- Báo cáo RF: [bảng 12 tổ hợp](appendix-c/appendix_rf_gridsearch_cv.csv), [điểm refit trên validation](appendix-c/appendix_rf_cv_best_validation.csv), [fold audit](appendix-c/appendix_rf_cv_match_folds.csv), [kiểm chứng](provenance/appendix-c-rf_grid-verification-20261022.json).
- Kernel: [RF CV](https://www.kaggle.com/code/sangtranminh211/pubg-appendix-rf-cv-20261022), [HGB CV](https://www.kaggle.com/code/sangtranminh211/pubg-appendix-hgb-cv-20261022), [α + placement](https://www.kaggle.com/code/sangtranminh211/pubg-appendix-alpha-placement-20261022). Mọi trạng thái trong bảng là snapshot lúc kiểm tra; không khởi chạy lại các phiên đã hoàn tất và xác minh.
- Module/script thực tế: `src/pubg_weapon/appendix.py`, `scripts/07_appendix.py`, `scripts/build_appendix_kaggle.py`, `kaggle/appendix_runner.py`; local bản gửi đầu **73/73 test pass**, bản retry HGB **76/76 test pass**, bản bổ sung recall **80/80 test pass local từ archive và trên Kaggle**. Báo cáo tiến độ: [APPENDIX_C_RESULTS.md](APPENDIX_C_RESULTS.md).
- **Minority Recall đã hoàn tất và kiểm chứng** từ dự đoán validation của 12 cấu hình α; không suy ngược từ Macro-F1/Accuracy. Các điểm α cũ tái lập chính xác (max delta của 7 chỉ số = 0). [Provenance](provenance/appendix-c-alpha-recall-submission-20261023.json), [kiểm chứng recall](provenance/appendix-c-alpha_recall-verification-20261023.json).

#### C1.1 — HGB GridSearchCV v3 đã hoàn tất và xác minh

**COMPLETE; readiness passed**, kiểm tra lúc **08:50 ngày 23/10/2026 (giờ Việt Nam)**. Đủ **12 tổ hợp × 3 GroupKFold + 1 refit**, `max_iter=150` và α=1 cố định; preprocessing và trọng số được học bên trong từng fold. Chọn theo Macro-F1 CV, không theo validation hoặc holdout.

| learning_rate | max_leaf_nodes | min_samples_leaf | Macro-F1 CV trung bình | SD giữa 3 fold | Accuracy CV trung bình |
|---|---:|---:|---:|---:|---:|
| 0.10 | 63 | 50 | 0,408334 | 0,001025 | 45,85% |
| 0.10 | 63 | 20 | 0,408297 | 0,000775 | 45,89% |
| 0.05 | 63 | 50 | 0,407269 | 0,000707 | 45,72% |
| 0.05 | 63 | 20 | 0,407249 | 0,000603 | 45,72% |
| 0.10 | 31 | 50 | 0,407081 | 0,000612 | 45,68% |
| 0.10 | 31 | 20 | 0,406647 | 0,000680 | 45,66% |
| 0.10 | 15 | 20 | 0,405781 | 0,000517 | 45,64% |
| 0.10 | 15 | 50 | 0,405615 | 0,000434 | 45,61% |
| 0.05 | 31 | 20 | 0,405566 | 0,000543 | 45,53% |
| 0.05 | 31 | 50 | 0,405417 | 0,000559 | 45,52% |
| 0.05 | 15 | 50 | 0,403930 | 0,000304 | 45,43% |
| 0.05 | 15 | 20 | 0,403874 | 0,000134 | 45,44% |

Cấu hình tốt nhất: **learning_rate=0.10, max_leaf_nodes=63, min_samples_leaf=50**, 150 vòng. Macro-F1 CV **0,408334 ± 0,001025 SD**; Accuracy CV **45,85%**. SD là độ lệch chuẩn giữa 3 fold, **không phải CI 95%**. Cấu hình này có Macro-F1 CV cao nhất; không nhất thiết cao nhất về Accuracy.

Sau refit trên 1.000.000 dòng train, đánh giá trên cùng 480.891 dòng validation: Macro-F1 **0,407183**, Accuracy **45,78%**, Weighted-F1 **0,479228**, Top-2 **66,75%**, Tactical Role Macro-F1 **0,585816**, Tactical Role Accuracy **60,61%**.

- Kaggle **76/76 test pass**; đã đối chiếu **39 source hash**, frozen input/metadata/library versions, đủ grid và tính lại mean/std từ 3 fold. Fold audit HGB **giống hệt RF về nội dung và SHA-256**: 34.614 trận, tổng 1.000.000 dòng; mỗi trận chỉ ở một fold validation CV. Guard ghi nhận đúng `train.parquet`, `validation.parquet`; không đọc test, không đổi lựa chọn mô hình chính.
- Thời gian section **77.08 phút**; RSS đỉnh tiến trình cha **1735.21 MiB**. Source SHA và Docker digest trên server khớp bundle; toàn bộ 34 main runtime hash giữ nguyên.
- Báo cáo HGB: [bảng đủ 12 tổ hợp](appendix-c/appendix_hgb_gridsearch_cv.csv), [điểm refit validation](appendix-c/appendix_hgb_cv_best_validation.csv), [fold audit](appendix-c/appendix_hgb_cv_match_folds.csv), [readiness](appendix-c/hgb_grid_readiness.json), [kiểm chứng v3](provenance/appendix-c-hgb_grid-v3-verification-20261023.json), [provenance v3](provenance/appendix-c-hgb-retry-v3-submission-20261023.json).
- RF CV đạt Macro-F1 CV `0,432913`, validation `0,431908`, cao hơn HGB CV trong thiết lập α=1 đang so sánh. HGB α=0,50 đạt validation `0,441691` ở thí nghiệm α riêng với tham số cố định khác; không gộp các cấu hình hoặc dùng chúng để thay kết quả test chính đã khóa.
- Lịch sử lỗi: v1 trả log `[]`, chưa rõ nguyên nhân ([bằng chứng](provenance/linked/reports/appendix-c-hgb_grid-error-20261023.json)); v2 thiếu builder trong bundle nên fail test trước khi đọc dữ liệu thật ([bằng chứng](provenance/linked/reports/appendix-c-hgb_grid-v2-error-20261023.json)). V3 đã bổ sung builder, ghim image, giới hạn luồng trước import và lưu progress/traceback. Lịch theo dõi đã xóa sau khi tải/xác minh thành công; không cần chạy lại HGB CV này.

#### C1.2 — Kết quả α tradeoff đã xác minh trên validation

**Bổ sung Minority Recall đã COMPLETE và xác minh lúc 09:54 ngày 23/10/2026 (giờ Việt Nam):** [kernel](https://www.kaggle.com/code/sangtranminh211/pubg-appendix-alpha-recall-20261023), version 1; **80/80 test Kaggle pass**, **40 source hash** khớp, frozen input/metadata/library versions khớp, guard chỉ đọc train/validation. Chỉ replay 12 alpha fits, không chạy lại CV/C2 hoặc chấm lại test. Toàn bộ 12 điểm cũ tái lập đúng params/weights/Pareto và 7 chỉ số (max absolute delta **0**, ngưỡng kiểm tra `1e-12`).

Định nghĩa cố định trước replay: lớp minority có tỷ lệ **trong train** dưới `1/K` (K=6, ngưỡng 16,6667%); gồm **DMR, Other, SMG, SR, Shotgun**, không gồm AR. **Minority Recall = trung bình không trọng số của 5 recall trên validation**, không phải recall gộp theo số mẫu và không chọn nhóm từ phân bố validation. Mỗi recall là `TP/(TP+FN)`, quy ước 0 khi support bằng 0. Nếu không có lớp minority thì chỉ số để trống, không tự gán 0.

Đã xuất và tính lại độc lập từ **72 dòng recall từng lớp** và **432 ô confusion matrix**: recall, Macro-F1, Weighted-F1 và Accuracy đều khớp bảng. [Recall từng lớp](appendix-c/appendix_alpha_class_recall.csv), [confusion cells](appendix-c/appendix_alpha_confusion.csv), [đồ thị recall](appendix-c/appendix_alpha_minority_recall.png), [đối chiếu bảng cũ](appendix-c/alpha_recall_reference_check.json), [kiểm chứng](provenance/appendix-c-alpha_recall-verification-20261023.json). Replay **40.18 phút**, RSS đỉnh tiến trình cha **2671.14 MiB**.

Giữ nguyên tham số của biến thể balanced D trong main run: RF 300 cây / depth 18 / min leaf 5 / max_samples 0.15; HGB 150 vòng / learning_rate 0.10 / 31 lá / min leaf 20. Mỗi mô hình fit trên cùng 1 triệu dòng train và chấm cùng 480.891 dòng validation. Trọng số đúng công thức $(N/(K N_c))^\alpha$, không normalize/clip. Majority Accuracy validation **52,6762%**.

| Họ mô hình | α | Macro-F1 | Accuracy | Top-2 Accuracy | Minority Recall (macro 5 lớp) | Pareto trong họ |
|---|---:|---:|---:|---:|---:|---|
| RF | 0,00 | 0,396265 | 60,03% | 78,50% | 0,253267 | Có |
| RF | 0,35 | 0,430938 | 59,09% | 77,48% | 0,337038 | Có |
| RF | 0,50 | 0,438282 | 57,74% | 75,91% | 0,375964 | Có |
| RF | 0,65 | 0,440113 | 55,71% | 74,17% | 0,412053 | Có |
| RF | 0,80 | 0,435822 | 53,07% | 72,21% | 0,444869 | Không |
| RF | 1,00 | 0,422055 | 49,05% | 69,21% | 0,477945 | Không |
| HGB | 0,00 | 0,406042 | 60,22% | 78,65% | 0,265113 | Có |
| HGB | 0,35 | 0,440114 | 58,50% | 77,09% | 0,367320 | Có |
| HGB | 0,50 | 0,441691 | 56,42% | 75,17% | 0,407648 | Có |
| HGB | 0,65 | 0,437051 | 53,69% | 73,13% | 0,443794 | Không |
| HGB | 0,80 | 0,426279 | 50,27% | 70,59% | 0,475945 | Không |
| HGB | 1,00 | 0,405150 | 45,57% | 66,54% | 0,502308 | Không |

- Trong 6 mức đã thử, RF đạt Macro-F1 cao nhất ở **α=0,65: 0,440113**, Accuracy **55,71%**; HGB cao nhất ở **α=0,50: 0,441691**, Accuracy **56,42%**. **Kỳ vọng “α=1 tối ưu Macro-F1” không được số liệu ủng hộ** trong thiết lập này.
- Minority Recall tăng theo α ở cả hai họ trong 6 mức đã thử: RF **0,253267 → 0,477945**, HGB **0,265113 → 0,502308** từ α=0 đến α=1. α=1 cao nhất về Minority Recall trong lưới này, đồng thời giảm Accuracy và không tối ưu Macro-F1. Tại điểm Macro-F1 tốt nhất, RF α=0,65 có Minority Recall **0,412053**, HGB α=0,50 có **0,407648**; không gộp các chỉ số tốt nhất từ các α khác nhau.
- α=0 đạt Accuracy cao nhất trong mỗi họ: RF **60,03%**, HGB **60,22%**. Các điểm Pareto thực nghiệm là RF `{0; 0,35; 0,50; 0,65}` và HGB `{0; 0,35; 0,50}`.
- Điều kiện đồng thời Accuracy `>55%` và Macro-F1 `>0,415` đạt ở RF α=`0,35/0,50/0,65`, HGB α=`0,35/0,50`. HGB α=0,65 **không** vượt 55% Accuracy; không khái quát rằng cả khoảng `[0,50;0,65]` đều đạt cho mọi họ.
- Đây là điểm ước lượng trên validation, không phải điểm test hay bằng chứng tối ưu cho mọi cấu hình. RF α=1 dùng trọng số lớp cố định và đạt Macro-F1 `0,422055`, khác RF chính `balanced_subsample` (`0,422652`).
- Nguồn: [appendix_alpha_tradeoff.csv](appendix-c/appendix_alpha_tradeoff.csv), [đồ thị Pareto](appendix-c/appendix_alpha_tradeoff.png), [kiểm chứng α/C2](provenance/appendix-c-alpha_placement-verification-20261022.json).

#### C2 — Kết quả placement hậu nghiệm đã xác minh trên validation

Cùng RF/params/balancing của mô hình chính; C/D được nạp lại và tái lập đúng điểm validation. Chỉ D+placement được fit thêm ba cột thứ hạng; không sử dụng mô hình RF depth=22 của GridSearch cho phép so sánh này.

| Cấu hình | Macro-F1 | CI 95% Macro-F1 | Accuracy | Top-2 Accuracy |
|---|---:|---:|---:|---:|
| D | 0,422652 | [0,420887; 0,424483] | 49,10% | 69,23% |
| D+placement | 0,423991 | [0,422248; 0,425853] | 49,45% | 69,53% |

| Bổ sung đặc trưng | ΔMacro-F1 | CI 95% hiệu số | ΔAccuracy (điểm phần trăm) |
|---|---:|---:|---:|
| C→D | +0,070987 | [+0,069443; +0,072463] | +5,1783 |
| D→D+placement | +0,001339 | [+0,000610; +0,002051] | +0,3541 |

Hiệu **(mức tăng lịch sử) − (mức tăng placement)** là **+0,069648 Macro-F1**, CI 95% **[+0,067729; +0,071428]**, từ 1.000 paired cluster bootstrap theo 7.373 trận validation. Lịch sử đóng góp lớn hơn rõ rệt trong thiết lập này; placement có mức tăng dương nhưng nhỏ. Không đưa placement vào bài toán tiền nghiệm hoặc chấm lại holdout.

Nguồn: [appendix_placement_comparison.csv](appendix-c/appendix_placement_comparison.csv), [C/D/D+placement](appendix-c/appendix_context_history_placement.csv), [hiệu số và CI](appendix-c/appendix_history_placement_gains.csv), [bootstrap draws](appendix-c/appendix_placement_bootstrap.csv).


---

## VII. Đánh giá và Kiểm định thống kê

- **Chỉ số chính:** **Macro-F1** kèm khoảng tin cậy 95% tính bằng **paired cluster bootstrap theo `match_id`** (1.000 lần lặp, `seed = 42`).
- **Chỉ số phụ toàn diện:**
  - `Accuracy` và `Weighted-F1`.
  - **`Top-2 Accuracy`**: tỉ lệ mẫu mà nhãn thật nằm trong 2 lớp có xác suất dự đoán cao nhất.
  - **`Tactical Role Macro-F1` và `Tactical Role Accuracy` (3 lớp `Close` / `Mid` / `Long`):** đo độ chính xác khi quy chiếu dự đoán về vai trò tầm bắn.
  - **Bảng phân tách theo `has_prior_kill` (`history_subset_metrics.csv`):** báo cáo riêng Macro-F1, Accuracy và Top-2 Accuracy cho hai nhóm:
    1. Mạng đầu tiên của killer trong trận (`has_prior_kill == 0`, chỉ có ngữ cảnh không gian - thời gian).
    2. Các mạng tiếp theo của killer trong trận (`has_prior_kill == 1`, có lịch sử trang bị $t' < t$).
- **Kiểm định cặp (`paired_model_differences.csv` và `ablation_gains.csv`):** tính CI 95% của hiệu số Macro-F1 giữa mọi cặp mô hình và giữa các bậc Ablation `A -> B`, `B -> C`, `C -> D`.
- **Phân tích lỗi chuyên sâu:**
  - Ma trận nhầm lẫn (`confusion_matrix.csv` / `.png`).
  - Các cặp nhầm lẫn lớn nhất kèm **khoảng cách trung vị** (`confused_pairs.csv`).
  - Độ chính xác và Macro-F1 theo 4 khoảng cự ly `0–50 m`, `>50–150 m`, `>150–300 m`, `>300 m` (`distance_metrics.csv`).
  - Phân tích riêng các thành phần của lớp `Other` (`other_components.csv`, `other_confused_destinations.csv`).

---

## VIII. Lộ trình thực hiện cụ thể (Trạng thái & Các bước tiếp theo)

1. **[x] Bước 1 — Cập nhật mã nguồn (`src/pubg_weapon/` và `tests/`) [ĐÃ HOÀN THÀNH]:**
   - Nâng `MIN_CLASS_FRACTION = 0.01` trong `config.py` để tự động gộp lớp cực hiếm `< 1%` (`LMG`) trên tập train.
   - Bổ sung hàm tính đặc trưng lịch sử nhân quả chặt ($t' < t$) trong `features.py` (gọi trong `preprocessing.py` trước khi `cap_train`), đảm bảo hai sự kiện cùng giây không nhìn thấy nhau.
   - Thêm tập đặc trưng `'loadout_history'` (Cấu hình D) vào `schema.py` và `models.py`; cập nhật chuỗi Ablation trong `training.py` và `evaluation.py` thành 4 bậc `A -> B -> C -> D`.
   - Bổ sung các chỉ số `top_2_accuracy`, `tactical_role_macro_f1`, `tactical_role_accuracy` và bảng phân tách `history_subset_metrics.csv` vào `diagnostics.py` và `evaluation.py`.
   - Bản full-final đã qua 65/65 test; sau khi thêm phụ lục, local đạt 73/73 test. Bộ test kiểm tra tính nhân quả $t' < t$, ngưỡng lớp hiếm và chuỗi Ablation `A -> B -> C -> D`.
2. **[x] Bước 2 — Chạy kiểm chứng Pilot trên Kaggle (3.000 trận, 100.000 dòng train, chỉ đo trên validation) [ĐÃ HOÀN THÀNH]:**
   - Đã chạy và lưu báo cáo tại `reports/HISTORY_UPGRADE.md` (RF balanced cùng cấu hình: Macro-F1 validation **`0,352375`** ở C → **`0,430621`** ở D; CI 95% của hiệu số **`[+0,071723; +0,085446]`**, trên 28.165 dòng validation / 434 trận).
3. **[x] Bước 3 — Chạy Train dài trên Kaggle (50.000 trận, 1.000.000 dòng train) [ĐÃ HOÀN THÀNH]:**
   - Đã huấn luyện toàn bộ 6 họ mô hình và chuỗi Ablation `A -> B -> C -> D` trên `1.000.000` dòng train (`34.614` trận), xuất đầy đủ bảng chẩn đoán trên `480.891` dòng validation (`7.373` trận).
4. **[x] Bước 4 — Mở khóa và chấm Tập Test Holdout đúng một lần duy nhất (`04_evaluation.py`) [ĐÃ HOÀN THÀNH & KHÓA]:**
   - Đã chấm đúng một lần trên **484.074 dòng / 7.418 trận**; khóa tại [evaluation_complete.json](main/models/evaluation_complete.json), báo cáo [HISTORY_FULL_FINAL_RESULTS.md](HISTORY_FULL_FINAL_RESULTS.md). RF balanced được chọn theo validation đạt test Macro-F1 **0,421898**, Accuracy **48,99%**, Top-2 **69,15%**; nhóm có lịch sử đạt Macro-F1 **0,516019**, Accuracy **62,55%**, Top-2 **79,72%**. HGB plain là một mô hình khác, đạt Accuracy **60,18%** và Top-2 **78,76%**.
5. **[x] Bước 5 — Phụ lục C [ĐÃ HOÀN TẤT & XÁC MINH, GỒM MINORITY RECALL]:**
   - Đã có `src/pubg_weapon/appendix.py`, CLI `scripts/07_appendix.py`, builder/runner Kaggle và unit test. Dùng nguyên train/validation đã khóa, không mở lại Test. Trạng thái từng bảng:
     1. **Bảng C1.1:** RF **đã hoàn tất và xác minh** tại [appendix_rf_gridsearch_cv.csv](appendix-c/appendix_rf_gridsearch_cv.csv); HGB v3 **đã hoàn tất và xác minh** tại [appendix_hgb_gridsearch_cv.csv](appendix-c/appendix_hgb_gridsearch_cv.csv). Cả hai dùng GroupKFold 3 theo `match_id` trên D.
     2. **Bảng C1.2 (`appendix_alpha_tradeoff.csv`):** Đã có đủ 12 điểm của 2 họ × 6 mức α với Macro-F1, Accuracy, Top-2 và Pareto; xem [bảng](appendix-c/appendix_alpha_tradeoff.csv). Đường cong gồm **6 điểm rời rạc** cho mỗi họ, không phải khảo sát α liên tục. **Minority Recall đã bổ sung đủ 12 điểm và kiểm chứng**, kèm recall từng lớp và confusion cells; C1.2 đã đủ yêu cầu.
     3. **Bảng C2 (`appendix_placement_comparison.csv`):** Đã hoàn tất và xác minh [bảng D/D+placement](appendix-c/appendix_placement_comparison.csv), cùng hiệu số/CI trên validation. Placement tăng `+0,001339` Macro-F1, nhỏ hơn mức tăng lịch sử `+0,070987`.
   - Đã có báo cáo tiến độ tại `reports/APPENDIX_C_RESULTS.md`; đã có [biểu đồ Pareto](appendix-c/appendix_alpha_tradeoff.png). **Bước 5 đã hoàn tất**. Bộ minh chứng phục vụ viết báo cáo: [thư mục có manifest](README.md), [mục lục bộ minh chứng](README.md). Bước 6 là phần viết báo cáo, chưa đánh dấu hoàn tất.
6. **[ ] Bước 6 — Tổng hợp Báo cáo đồ án hoàn chỉnh & Đóng gói nộp bài:**
   - Hợp nhất toàn bộ kết quả thực nghiệm chính và phụ lục Bước 5 thành tài liệu Báo cáo tổng kết đồ án Khai phá dữ liệu hoàn chỉnh.

---

## IX. Checklist tự kiểm trước khi nộp

- [x] Đã chia tập theo `match_id`, giữ cố định tập test holdout trên toàn nguồn, không trận nào nằm ở hai tập.
- [x] Đặc trưng lịch sử trong trận tuân thủ tuyệt đối ràng buộc nhân quả chặt ($t' < t$) trong phạm vi cùng `(match_id, killer_name)`, không dùng sự kiện cùng giây ($t' = t$) hoặc tương lai ($t' > t$).
- [x] Không đưa `killer_name`, `victim_name`, `match_id`, `killed_by`, `cause_for_audit` hay `placement` vào ma trận đặc trưng $X$ của bài toán chính.
- [x] Ngưỡng gộp lớp hiếm (`1,0%`) và bảng ánh xạ nhãn hiệu lực được xác định hoàn toàn trên tập train.
- [x] Chuỗi Ablation 4 bậc (`A -> B -> C -> D`) cô lập rõ đóng góp của khoảng cách, thời gian, vị trí và lịch sử trang bị trong trận.
- [x] Báo cáo đầy đủ Macro-F1 (kèm 95% CI bootstrap), Accuracy, Top-2 Accuracy, Tactical Role Macro-F1 (3 lớp) và bảng tách theo `has_prior_kill`.
- [x] Tập test chỉ được mở và chấm đúng một lần duy nhất ở Bước 4 (`evaluation_complete.json`).
- [x] Hoàn thành và kiểm chứng RF GridSearchCV: 12 tổ hợp × 3 GroupKFold, refit và chấm validation, không đọc lại holdout.
- [x] Hoàn thành và kiểm chứng HGB GridSearchCV v3: 12 tổ hợp × 3 GroupKFold + 1 refit; 76/76 test Kaggle pass, không đọc lại holdout.
- [x] Hoàn thành và kiểm chứng 12 điểm α tradeoff, biểu đồ Pareto và Minority Recall.
- [x] Bổ sung và kiểm chứng Minority Recall trong Bảng C1.2: 80/80 test pass, 72 class recalls và 432 confusion cells; tái lập 12 điểm cũ.
- [x] Hoàn thành bảng D/D+placement và kiểm định chênh lệch trên validation; không đọc lại holdout.
- [ ] Hoàn thành bản Báo cáo tổng kết đồ án cuối cùng ở Bước 6.
