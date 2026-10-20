# Chuyển dự án PUBG sang một mục tiêu: normalized_placement

Ngày soạn: 21/10/2026.

**Trạng thái: tài liệu thiết kế chuyển đổi, chưa triển khai.** Yêu cầu của người dùng đã chốt một target duy nhất là thứ hạng đội chuẩn hóa. Tài liệu này cụ thể hóa hướng sửa từ dữ liệu đến báo cáo; không tuyên bố code, notebook hoặc kết quả hiện tại đã chuyển đổi.

## 1. Mục tiêu và cách sử dụng tài liệu

Mục tiêu cuối cùng:

> Xây dựng và đánh giá mô hình học máy ước lượng thứ hạng đội chuẩn hóa từ thống kê hành vi người chơi trong trận PUBG.

Đầu ra duy nhất của mô hình:

```text
y = normalized_placement
```

Không còn mô hình dự đoán `player_survive_time`. Nhiều mô hình hoặc nhiều bộ đặc trưng cùng dự đoán `normalized_placement` vẫn là bài toán một target, không phải đa đầu ra.

### 1.1. Quan hệ với tài liệu đang có

- `PUBG_RESEARCH_SPEC.md` hiện vẫn mô tả survival và placement.
- `PUBG_IMPLEMENTATION_PLAN.md` hiện vẫn là checklist triển khai duy nhất.
- File này là đầu vào để cập nhật hai tài liệu trên ở giai đoạn 0; không chạy hai checklist song song.
- Khi triển khai, chuyển các yêu cầu dưới đây vào task tương ứng của kế hoạch hiện hành, với bằng chứng riêng cho từng task.
- Không đánh dấu task cũ hoàn thành chỉ vì đã viết tài liệu này.
- Tại thời điểm kiểm tra, không tìm thấy `CHANGELOG_FIXES.md` trong checkout. Cần ghi nhận thiếu lịch sử; khôi phục từ nguồn đáng tin nếu có. Nếu tạo mới, ghi rõ là nhật ký bắt đầu từ thời điểm đó, không dựng lại lịch sử.

### 1.2. Điều đã chốt và lựa chọn thiết kế đề xuất

| Nội dung | Trạng thái |
|---|---|
| Chỉ dự đoán `normalized_placement` | Người dùng đã yêu cầu |
| Giữ toàn bộ dữ liệu hợp lệ, không sửa raw | Giữ quy tắc hiện hành |
| Drive, project root, batch 50.000 | Giữ quyết định đã chốt |
| Một dòng/người chơi/trận | Đề xuất giữ kiến trúc hiện tại |
| Current-match retrospective là phạm vi chính | Đề xuất để đơn giản hóa |
| Không dùng survival trực tiếp hoặc đặc trưng phụ thuộc survival trong mô hình chính | Đề xuất thiết kế feature rõ ràng |
| Lịch sử và phân cụm không bắt buộc trong release tối giản | Đề xuất giảm phạm vi, cần ghi quyết định khi cập nhật đặc tả |
| MAE theo đội là tiêu chí chọn model chính | Đề xuất; phải khóa trước huấn luyện lựa chọn |

Chỉ bỏ target survival không tự động có nghĩa bỏ RQ2, bỏ historical placement hoặc bỏ mọi survival feature. Những lựa chọn trên phải được xác nhận trong bản đặc tả chuyển đổi trước khi thực thi phần code phụ thuộc. Không dùng tài liệu này làm lý do âm thầm thu hẹp protocol cũ.

## 2. Bài toán thực sự đang giải

### 2.1. Thời điểm dự đoán

Các cột như tổng kills, damage, quãng đường và thời điểm kill được tổng hợp trong hoặc sau trận. Khi dùng toàn bộ thống kê cuối trận, bài toán là **ước lượng hồi cứu thứ hạng**, không phải dự báo trước khi trận bắt đầu.

Ví dụ đầu vào:

```text
kills = 3
damage = 410
walk_distance = 2400
ride_distance = 800
assists = 1
...
```

Ví dụ đầu ra minh họa:

```text
predicted_normalized_placement = 0.82
```

`0.82` là điểm thứ hạng chuẩn hóa dự đoán, không phải xác suất thắng 82%.

Nếu cần dự đoán trước trận trong tương lai, phải có pipeline strict-past riêng. Không đổi tên mô hình dùng thống kê cuối trận thành mô hình dự đoán trước trận.

### 2.2. Đơn vị dữ liệu và ý nghĩa đầu ra

Giữ một dòng `(match_id, player_name)` với `row_id` ổn định; tên thiếu có thể dùng lineage theo contract hiện tại.

Target là kết quả của đội nên đồng đội cùng trận có cùng nhãn. Mô hình có thể cho các thành viên dự đoán khác nhau vì hành vi khác nhau.

Để hiển thị một kết quả cho đội:

1. Dự đoán từng player row.
2. Nhóm theo `(match_id, team_id)`.
3. Lấy trung bình prediction của các thành viên quan sát được.
4. Ghi số thành viên thực sự đóng góp và cảnh báo coverage trong báo cáo.

Không nhóm chỉ bằng `team_id`, vì ID có thể lặp lại giữa các trận. Không diễn giải đội chỉ quan sát một phần thành đội có roster đầy đủ.

Phương án khác là aggregate feature thành một dòng/đội/trận trước training. Phương án đó đúng về đơn vị outcome nhưng thay đổi schema, feature, weighting và pipeline nhiều hơn; không đưa vào đợt sửa tối giản này.

## 3. Định nghĩa target và mẫu số

Với:

- `r = team_placement`: hạng cuối trận của đội.
- `N = observed_team_count`: số `team_id` phân biệt của trận sau cleaning cơ sở, trước lọc cohort mô hình.

```text
normalized_placement = 1 - (r - 1) / (N - 1)
```

Ví dụ minh họa:

| Số đội | Hạng | Target |
|---:|---:|---:|
| 25 | 1 | 1.00 |
| 25 | 7 | 0.75 |
| 25 | 13 | 0.50 |
| 25 | 25 | 0.00 |

### 3.1. Điều kiện hợp lệ

- `N` hữu hạn, nguyên và lớn hơn 1.
- `r` hữu hạn, nguyên, `1 <= r <= N`.
- Các thành viên cùng đội có placement nhất quán.
- Roster đáp ứng chính sách chất lượng đã khai báo.
- Target tính được hữu hạn và thuộc `[0, 1]`.

Target lỗi để NULL và loại khỏi cohort supervised bằng reason code. Không điền target bằng mean/median; không clip nhãn sai vào `[0,1]`.

### 3.2. Những chỗ cần sửa hoặc kiểm chứng

`src/features/placement.py` đã chứa công thức canonical và điều kiện roster. Cần kiểm tra đồng nhất mọi caller và bổ sung kiểm thử tính nguyên; không để helper nhỏ và production SQL dùng hai tiêu chuẩn khác nhau.

Không truyền mặc định “roster đầy đủ” vào đường chạy chính khi thiếu bằng chứng. Helper dùng fixture phải được phân biệt rõ với dữ liệu thật.

`is_roster_complete` hiện là kết luận dựa trên heuristic kiểm tra roster; không phải bằng chứng nguồn đảm bảo thu đủ mọi đội. Phải mô tả heuristic, tỷ lệ retention và giới hạn này trong báo cáo.

Không thay `N` bằng `game_size` nếu chưa xác minh ý nghĩa cột. Không tính lại `N` sau khi bỏ missing feature hoặc survival lỗi: thao tác đó có thể đổi nhãn của các hàng còn lại.

## 4. Phạm vi nghiên cứu sau chuyển đổi

Đề xuất release tối giản gồm:

1. Chất lượng dữ liệu và phân bố `normalized_placement`.
2. Mối liên hệ giữa hành vi và `normalized_placement`.
3. Huấn luyện các mô hình cùng dự đoán target này.
4. Kiểm tra Combat Timing có bổ sung thông tin hay không.
5. Phân tích sai số, bất định và khóa báo cáo.

Không đặt một ngưỡng MAE/R² tùy ý để gọi là thành công. Mô hình không vượt baseline vẫn là kết quả nghiên cứu hợp lệ nếu thiết kế và đánh giá đúng.

### 4.1. Xử lý các nhánh cũ

| Nhánh | Cách xử lý đề xuất |
|---|---|
| S1, S2 survival | Không thuộc ma trận thí nghiệm mới |
| P1 có survival trực tiếp | Bỏ khỏi release tối giản |
| P2 | Tái sử dụng code phù hợp nhưng cập nhật cohort và feature contract |
| P3 historical placement | Extension riêng, chưa bắt buộc release tối giản |
| T0/T1 | Giữ so sánh có/không Combat Timing trên cùng target |
| RQ2 clustering | Extension riêng, không dùng làm điều kiện khóa release tối giản |

Lưu ý: P2 hiện vẫn có phase features phụ thuộc duration, và dùng cùng cohort survival hợp lệ với P1. Vì vậy không thể chỉ tắt S1/S2 rồi gọi P2 hiện tại là phương án đã sửa.

Giữ source code và kết quả cũ có provenance; không xóa hàng loạt module lịch sử/phân cụm. Nếu vẫn chạy RQ2, giữ `per_mode` và quy tắc hiện hành.

## 5. Sơ đồ pipeline đích

```text
Raw aggregate shards + raw death shards
    -> inventory / checksum / schema / parsing
    -> cleaning cơ sở và audit
    -> match metadata / roster / chronology / split
    -> normalized_placement + behavioral features
    -> absolute Combat Timing + coverage
    -> player_match_features
    -> cohort placement hợp lệ
    -> train / validation theo match
    -> preprocessing fit trên train
    -> baselines + candidate models
    -> chọn model bằng validation / khóa G4
    -> final test + paired comparisons
    -> registry / immutable release G5
    -> notebook tổng hợp chỉ đọc
```

Death data phục vụ Combat Timing. T0 không sử dụng timing; T1 sử dụng timing. Nếu timing chưa đạt yêu cầu, ghi blocker của T1; không tuyên bố hoàn thành toàn bộ ma trận T0/T1 chỉ vì T0 chạy được.

## 6. Tiền xử lý dữ liệu

### 6.1. Ingestion

Tái sử dụng `src/data/batch_ingest.py`, `schema.py`, `inventory.py` và `configs/schema.yaml`.

- Đọc mọi shard, batch 50.000.
- Giữ tên/ID dạng string; không mất số 0 đầu.
- Parse số với báo cáo lỗi, lineage file/row.
- Ghi Parquet theo cơ chế hiện hành.
- Đối soát số dòng đọc, ghi, lỗi parse và checksum.
- Không đọc toàn bộ CSV thành một DataFrame chỉ để thuận tiện.

### 6.2. Cleaning cơ sở

Tái sử dụng `src/data/cleaning.py`, kiểm chứng:

- Exact duplicate theo business columns.
- Missing `match_id` hoặc `team_id`.
- Giá trị âm/không hữu hạn của count, damage, distance.
- Count hoặc placement không nguyên.
- Nhiều bản ghi khác nhau cho cùng identity.
- Placement mâu thuẫn giữa thành viên cùng đội.

Identity conflict cần quarantine và quy tắc loại rõ, không tùy ý giữ hàng đầu. Không loại toàn bộ dòng chỉ vì feature thiếu; phân biệt parse error, structural missing và source missing.

Giữ `player_survive_time` trong dữ liệu trung gian nếu phục vụ audit nguồn. Việc giữ cột trong Parquet không đồng nghĩa cho phép mô hình sử dụng.

### 6.3. Cohort supervised mới

Điều kiện cốt lõi:

```text
cleaning cơ sở hợp lệ
AND identity/row_id hợp lệ
AND placement_valid
AND normalized_placement hữu hạn trong [0,1]
AND có split hợp lệ
```

**Bỏ phụ thuộc `valid_survival` khỏi cohort placement.**

Hiện `src/models/training.py` tạo P1 bằng `valid_survival & valid_placement`, rồi gán P2 bằng P1. Cần sửa cả nơi tạo cohort, loader, comparison, selection receipt và test liên quan.

Test bắt buộc: một player có placement hợp lệ nhưng survival NULL/0/lỗi vẫn được giữ nếu không vi phạm cleaning cơ sở hoặc quy tắc roster khác.

Không yêu cầu mọi feature đều có giá trị. Việc impute feature diễn ra sau split.

### 6.4. Missing và outlier

- `kills = 0` thì `damage_per_kill` không xác định, để NULL.
- Không có kill event thì `first_kill_time` và `avg_kill_time` để NULL.
- Không có event quan sát được chưa đủ kết luận không kill.
- Feature thiếu được xử lý bằng preprocessing đã fit trên train.
- Không tự động dùng IQR để xóa dòng hoặc winsorize mọi cột.
- Quyết định log-transform/capping cần evidence development và được khóa trước test.
- Không sửa giá trị survival bất thường để tạo cảm giác dữ liệu đã sạch khi survival không còn thuộc model chính.

Mọi bước loại phải có số dòng trước/sau, số match/đội ảnh hưởng và reason code.

## 7. Feature contract

### 7.1. T0 — hành vi cơ sở

```text
player_kills
player_dmg
damage_per_kill
player_dist_walk
player_dist_ride
total_distance
walk_ratio
player_assists
player_dbno
assist_ratio
```

Công thức giữ thống nhất:

```text
damage_per_kill = player_dmg / player_kills           khi kills > 0
total_distance = player_dist_walk + player_dist_ride
walk_ratio = player_dist_walk / total_distance       khi total_distance > 0
assist_ratio = player_assists / (assists + kills)     khi assists + kills > 0
```

Không thay NULL bằng 0 trong công thức nếu làm thay đổi ý nghĩa.

### 7.2. T1 — T0 cộng absolute Combat Timing

```text
first_kill_time
avg_kill_time
has_kill
```

Giữ `event_kill_count` và coverage trong audit; không tự đưa vào input chỉ vì cột tồn tại. Có thể đề xuất nó như một feature bổ sung trong một recipe riêng đã đăng ký.

T0/T1 phải dùng cùng row IDs, nhãn, split và cách đánh giá. T1 không được chỉ giữ người có kill rồi so trực tiếp với T0 trên toàn cohort.

### 7.3. Các cột không thuộc input mô hình chính

| Nhóm | Ví dụ | Lý do |
|---|---|---|
| Target và bản sao | `normalized_placement`, `team_placement` | Rò rỉ trực tiếp |
| Outcome trong death data | `killer_placement`, `victim_placement` | Chứa kết quả cuối trận |
| Survival trực tiếp | `player_survive_time` | Ngoài feature contract đề xuất |
| Rate phụ thuộc survival | `kills_per_minute`, `damage_per_minute`, vận tốc dùng survival | Loại phụ thuộc survival |
| Phase/duration | early/mid/late counts, ratios, `estimated_match_duration` | Phase hiện phụ thuộc max survival |
| Định danh | tên player, match/team ID, row ID | Dùng join/split/audit, không làm số đo hành vi |
| Metadata outcome/roster audit | max placement, placement validity | Không tự đưa thông tin tạo nhãn vào X |

Mode giữ cho stratified evaluation. Nếu thêm mode làm feature, phải đăng ký context recipe và cách encoding riêng; không âm thầm bổ sung vào T0/T1.

Loại survival feature là lựa chọn thiết kế nhằm giảm phụ thuộc và dễ giải thích; không khẳng định survival luôn là leakage đối với placement trong mọi bài toán retrospective.

### 7.4. Chống leakage theo dependency

Sửa `src/features/registry.py` và `configs/features.yaml`:

- Allowlist rõ cho placement task.
- Khai báo dependency cho derived features.
- Kiểm tra closure để chặn target, target descendants và nhóm survival bị loại.
- Pipeline chỉ chọn cột theo allowlist, không dùng “mọi cột số trừ y”.
- Giữ `y` một chiều, shape `(n_rows,)`; X có shape `(n_rows, n_features)`.

Không chỉ đổi tên `s1_safe_features` thành placement: phải kiểm tra semantics từng cột và từng caller.

## 8. Combat Timing sau khi bỏ survival khỏi input

Giữ nguồn death data và logic absolute timing của `src/features/combat_timing.py`.

1. Match/killer hợp lệ và join được.
2. Loại self-kill theo quy tắc đã chốt.
3. Event time hữu hạn, không âm.
4. Tổng hợp qua mọi shard bằng sum/count/min toàn cục.
5. `avg_kill_time = global_sum / global_count`, không trung bình các chunk mean.
6. Merge không làm tăng số player rows.
7. Lưu discrepancy giữa aggregate kills và observed event count.

Giữ quyết định credited-killer non-self đã có evidence; không đổi nhãn thành enemy-only. Không loại same-team hoặc unknown-team âm thầm.

Trong release đề xuất, phase timing không thuộc required model feature. Nếu vẫn tính phase để diagnostic, không để sự thiếu phase ngăn training T0/T1 absolute. Phải tách dependency/gate của absolute và phase theo chức năng thực sự cần.

Unit event time và coverage vẫn phải được audit. Loại phase không tự giải quyết mọi bất thường của absolute timestamps.

## 9. Split và tập test

Giữ tỷ lệ match mục tiêu 70% train, 15% validation, 15% test và seed 42.

- Grade A: chia theo chronology, không tách block timestamp trùng.
- Grade B: chia theo ngày, không chia cùng ngày qua hai split.
- Grade C: group split theo match và ghi rõ giới hạn chronology.
- Mọi player và đội trong cùng match phải cùng split.
- Tỷ lệ row thực tế có thể khác 70/15/15 do block chronology và kích thước match.

Khóa split manifest trước outcome-dependent EDA. Không stratify hoặc chọn split lại để metric đẹp hơn.

Trong thiết kế hiện tại, một player có thể xuất hiện ở nhiều split. Vì vậy kết quả không chứng minh khả năng tổng quát sang hoàn toàn người chơi mới. Không thêm player-disjoint split vào phạm vi chính mà không đăng ký thiết kế mới.

Final test không dùng để:

- Chọn feature, log-transform, ngưỡng outlier.
- Chọn model hoặc hyperparameter.
- Chọn clipping hoặc cách gộp prediction theo đội.
- Chọn các nhóm phân tích sai số sau khi nhìn kết quả.

Nếu test đã được dùng để quyết định thiết kế trong lịch sử, ghi test-exposure history và giới hạn; không gọi tập đó là holdout chưa từng xem.

## 10. Preprocessing trong mô hình

Fit mọi transformer bằng train; validation/test chỉ transform.

| Model | Preprocessing đề xuất |
|---|---|
| Train mean / median | Chỉ học constant từ y_train |
| Linear regression | Mean imputation, scaling train-only |
| SGDRegressor | Train-only imputation/scaler; streaming khi cần |
| Histogram gradient boosting | Native missing nếu backend hiện có hỗ trợ đúng contract |
| Random Forest | Mean imputation; không bắt buộc scaling |

Giữ giải pháp đang có trong `linear.py`, `streaming.py`, `tree_models.py` nếu đã đúng.

Feature hoàn toàn NULL trong train cần chính sách deterministic và báo cáo; không lấy mean từ validation để cứu cột đó. Nếu thêm missing indicators, phải khóa recipe và lưu feature order sau transform.

Không thêm thư viện. `requirements.txt` hiện có NumPy, pandas, PyArrow, DuckDB, SciPy, scikit-learn và PyYAML. Backend GPU cần kiểm tra môi trường thực, không suy ra chỉ từ file requirements.

## 11. Ma trận mô hình và chính sách tài nguyên

### 11.1. Ma trận tối giản đề xuất

| Thí nghiệm | Feature | Target | Vai trò |
|---|---|---|---|
| Baseline mean | Không | normalized_placement | Mốc so sánh |
| Baseline median | Không | normalized_placement | Mốc so sánh |
| Linear T0 | T0 | normalized_placement | Mô hình chính cơ sở |
| Linear T1 | T1 | normalized_placement | So sánh giá trị timing |
| SGD T0/T1 | T0/T1 | normalized_placement | Candidate có đăng ký, phù hợp streaming |
| Nonlinear T0/T1 | T0/T1 | normalized_placement | Candidate nếu backend/tài nguyên cho phép |

Không bắt buộc chạy mọi candidate để gọi là một target. Required matrix tối thiểu phải được khóa rõ; optional failed không được biến thành metric 0.

### 11.2. GPU và CPU

`configs/rq3.yaml` hiện đặt `device: cuda`, trong khi không phải mọi wrapper hỗ trợ GPU. Không giữ một cờ chung rồi đánh dấu các candidate CPU là đã chạy GPU.

Đề xuất routing tường minh theo estimator:

- Backend GPU đã hỗ trợ: dùng GPU và lưu device/version bằng chứng thật.
- Estimator chỉ hỗ trợ CPU: khai báo CPU trong recipe trước run.
- Yêu cầu GPU nhưng backend không có: `blocked`, không silent fallback.
- Không đổi estimator sau OOM dưới cùng run ID.

CPU cho estimator không có GPU phải nhất quán với quy tắc “GPU khi estimator/backend hỗ trợ” và được ghi trong đặc tả cập nhật. GPU mock trên local không nghiệm thu GPU thật.

### 11.3. Selection

Đề xuất chọn bằng **validation team-aware MAE**: gộp prediction từng đội rồi mỗi đội đóng góp một absolute error. Train vẫn ở player-row level; phải công bố khác biệt weighting này.

Tie-break được khai báo trước: metric bằng nhau trong tolerance đã định thì ưu tiên model đơn giản/tốn ít tài nguyên hơn.

Không refit train+validation mặc định. Phiên bản đơn giản giữ model fit train đã chọn để đánh giá test. Nếu muốn refit, đăng ký riêng quy trình preprocessing và model refit trước G4.

## 12. Prediction và đánh giá

### 12.1. Prediction

Giữ `prediction_raw` là đầu ra thật của estimator. Một số regressor có thể trả giá trị ngoài `[0,1]`.

Nếu sản phẩm cần điểm trong `[0,1]`, có thể xuất thêm `prediction_clipped`, nhưng phải đăng ký trước G4 và báo metric raw/clipped riêng. Không clip sau khi nhìn test rồi chỉ công bố con số tốt hơn.

Không ép predictions trong mỗi trận thành permutation/rank để cải thiện metric nếu chưa có protocol riêng.

### 12.2. Metrics

- MAE: sai số tuyệt đối trung bình.
- RMSE: nhạy hơn với sai số lớn.
- R²: so với biến thiên target; có thể âm, không phải accuracy.

MAE 0.05 là sai số trung bình 0.05 trên thang chuẩn hóa; không đồng nghĩa luôn lệch một số hạng cố định.

Ba mức báo cáo:

1. **Micro:** mọi player row có trọng số như nhau.
2. **Team-aware:** mean prediction trong `(match_id, team_id)`, một target nhất quán/đội, tính metric trên đội.
3. **Match-aware:** giữ định nghĩa canonical trong `src/evaluation/metrics.py`, ghi rõ weighting và công thức; không đánh tráo với metric từ trung bình cả trận.

Kiểm tra đội có nhiều target khác nhau phải fail/audit trước khi gộp, không lấy mean target để che conflict.

### 12.3. Paired comparisons

- T0 và T1 cùng cohort/split/target.
- Model chính và baseline cùng tập đánh giá.
- Bootstrap theo match, mặc định hiện có 500 lần, seed 42.
- Khi bootstrap một match nhiều lần, giữ multiplicity; không group theo ID gốc rồi vô tình loại các lần lặp.
- CI phải ghi số match, số replicate hợp lệ và metric delta.

Ví dụ quy ước:

```text
delta_mae = MAE(T1) - MAE(T0)
delta_mae < 0: T1 có sai số thấp hơn
```

Không khẳng định timing hữu ích trước khi có kết quả.

### 12.4. Error analysis

Đăng ký trước G4:

- Solo/Duo/Squad; FPP/TPP nếu đủ dữ liệu.
- Bins target và match size đã định trước.
- Missing/coverage timing.
- Nhóm ít/nhiều kills theo ngưỡng development.

Mỗi bảng có số row, đội, match và phạm vi split. Nhóm quá ít dữ liệu phải có limitation. Importance không được diễn giải là nhân quả.

## 13. Những file cần sửa

| File hoặc nhóm file | Thay đổi phải thực hiện |
|---|---|
| `PUBG_RESEARCH_SPEC.md` | Target duy nhất, RQ/phạm vi mới, cohort, feature, metric, required matrix |
| `PUBG_IMPLEMENTATION_PLAN.md` | Checklist chuyển đổi theo thứ tự, khởi động lại ở INV-01 khi reset |
| `configs/rq3.yaml` | Bỏ survival tasks khỏi scope mới; selection, historical status và device routing rõ |
| `configs/features.yaml` | T0/T1 placement allowlists, loại survival/phase khỏi recipe chính |
| `configs/models.yaml` | Required/optional candidates và tài nguyên tương thích |
| `configs/eda.yaml` | Outcome chính chỉ placement; scope train/validation |
| `configs/preprocessing.yaml` | Đối chiếu domain/missing/placement contract |
| `src/data/cleaning.py`, `cohort.py`, `match_metadata.py` | Target validity, roster và cohort không phụ thuộc survival |
| `src/features/placement.py`, `base.py` | Công thức canonical, tính nguyên, NULL, row invariants |
| `src/features/registry.py` | Allowlist và dependency closure |
| `src/features/combat_timing.py` | Absolute timing, coverage; tách optional phase dependencies |
| `src/models/training.py` | Loại hard-code S/P matrix cũ, cohort mới, chỉ một target |
| `src/models/registry.py` | Matrix placement-only; không đăng ký survival run bắt buộc |
| `src/models/rq3_selection.py`, `rq3_diagnostics.py`, `rq3_resources.py` | Selection receipt, resource estimates, provenance theo recipe mới |
| `src/models/compute.py`, wrappers | Device/backend routing, preprocessing train-only |
| `src/evaluation/comparisons.py`, `ablation.py`, `importance.py`, `error_analysis.py` | Bỏ yêu cầu P1/P2 survival; T0/T1 và feature-removal closure |
| `src/evaluation/metrics.py`, `bootstrap.py` | Team/match-aware contract, bootstrap giữ multiplicity |
| `src/evaluation/finalize.py`, `summary.py` | Required matrix/release/summary một target |
| `src/analysis/rq1.py`, `eda.py`, `correlation.py`, `mode_analysis.py` | Nội dung chính tập trung placement |
| `src/utils/generate_notebooks.py` | Caller, dependencies, output, caption và artifact expressions |
| `src/utils/notebook_bundle.py` | Bundle/config cùng phiên bản source |
| `tests/` | Thay assumption multi-target, bổ sung regression tests |
| `README.md` và hướng dẫn vận hành liên quan | Pipeline, một target, retrospective và limitations |

Đây là bản đồ truy vết, không phải yêu cầu viết lại tất cả file. Nếu code đã đáp ứng contract thì giữ và kiểm chứng.

## 14. Sửa notebook từ đầu tới cuối

Giữ tên/số notebook hiện tại để tránh đổi đường dẫn không cần thiết.

| Notebook | Nội dung sau chuyển đổi |
|---|---|
| 00 | Môi trường, config, storage và manifest placement-only |
| 01 | Inventory/ingestion/schema đầy đủ |
| 02 | Cleaning, roster, chronology, split; bảng retention placement |
| 03 | Target duy nhất, ví dụ công thức, feature cơ sở, NULL semantics |
| 04 | Absolute Combat Timing, coverage, merge; phase optional |
| 05 | EDA development của feature và placement, không mở test để lựa chọn |
| 06 | Quan hệ hành vi với placement, không kết luận nhân quả |
| 07 | Extension clustering; không required cho release tối giản nếu scope đã được duyệt |
| 08 | Extension historical; không required cho release tối giản nếu scope đã được duyệt |
| 09 | Baselines/model T0/T1, một y, selection và G4 |
| 10 | So sánh, bootstrap, error analysis và importance placement |
| 11 | Chọn registry run tương thích, kiểm required matrix mới và khóa G5 |
| 12 | Chỉ đọc locked release, đủ nội dung có bảng/hình thật |

Hiện generator còn khai báo notebook 09 phụ thuộc 08; notebook 11 phụ thuộc 07; artifact notebook 09 còn có P1/P2. Phải sửa các dependency và artifact expressions này cùng workflow. Tắt flag training mà không sửa dependency sẽ vẫn gây blocker sai.

Notebook extension ngoài scope không được tạo checkpoint `completed` với `{}` để vượt gate. Ghi trạng thái ngoài scope ở manifest cấp dự án, giữ lịch sử của run cũ.

Notebook 12 có thể giữ 12 phần, phân bổ lại thành: nguồn dữ liệu; chất lượng/retention; target/roster; split; feature/missing; EDA; quan hệ hành vi; mô hình; timing comparison; sai số/CI; reproducibility; limitations. Không giữ lời hứa về kết quả survival/clustering/history chưa chạy.

Mỗi notebook cần bảng/hình thật, đơn vị, scope/mode/N, caption và hướng dẫn đọc; markdown mô tả không thay nghiệm thu output.

## 15. Trình tự triển khai và nghiệm thu

Các bước dưới ánh xạ vào giai đoạn 0–16 của kế hoạch hiện hành. Mỗi lượt chỉ xử lý một giai đoạn rồi báo bàn giao.

| Giai đoạn | Công việc chuyển đổi | Bằng chứng tối thiểu |
|---:|---|---|
| 0 | INV-01: kiểm kê, chốt phạm vi đề xuất, cập nhật spec/plan | Decision record, mapping tác động, checklist mới chưa tích trước |
| 1 | Registry/checkpoint/config compatibility | Old signature bị từ chối; new matrix không yêu cầu survival |
| 2 | Notebook 00 | Fixture config/môi trường và output hiển thị |
| 3 | Notebook 01 | Shard counts, schema, parse, receipt/recovery |
| 4 | Notebook 02 | Cleaning/roster/split invariants và retention |
| 5 | Notebook 03 | Công thức target và cases invalid, feature audit |
| 6 | Notebook 04 | Global timing, coverage, merge không tăng dòng |
| 7 | Notebook 05 | EDA development, quyết định transform có evidence |
| 8 | Notebook 06 | Bảng/hình placement, kết luận truy nguồn |
| 9 | Notebook 07 | Xử lý scope extension đúng spec, không fake completed |
| 10 | Notebook 08 | Xử lý scope extension; gỡ dependency core tương ứng |
| 11 | Notebook 09 | Model thật, preprocessing train-only, registry và selection |
| 12 | Notebook 10 | Paired cohort, metric recomputation, bootstrap/CI |
| 13 | Notebook 11 | Manifest hợp lệ, immutable release; reject stale runs |
| 14 | Notebook 12 | Chạy chỉ đọc release, đủ bảng/hình và limitations |
| 15 | Tích hợp và G0 | Notebook fixture end-to-end + tài liệu đồng nhất |
| 16 | Full-data Colab/Drive | G1–G5 bằng dữ liệu thật, backend thật, bàn giao |

G0 là code/fixture ready, không phải bằng chứng full-data. G1 source; G2 cohort/split; G3 quyết định nghiên cứu; G4 quyền truy cập test sau selection; G5 khóa kết quả. Không tạo Gate G7.

Task phải có đủ logic, tích hợp qua notebook và khả năng đọc. Chạy lại generator hoặc syntax pass không đủ.

## 16. Test bắt buộc

| Nhóm | Ca kiểm thử và expected |
|---|---|
| Target chuẩn | N=25: hạng 1 -> 1; hạng 13 -> 0.5; hạng 25 -> 0 |
| Target lỗi | N<=1, rank=0, rank>N, NULL/Inf, rank không nguyên -> invalid |
| Roster | Roster không đạt hoặc thiếu evidence ở caller production -> không tạo nhãn hợp lệ âm thầm |
| Denominator | Bỏ một row vì feature thiếu không làm đổi N/target của hàng khác |
| Team consistency | Đồng đội khác placement -> audit/fail theo contract, không average target |
| Cohort | Placement hợp lệ, survival NULL/0/bất thường -> không tự loại do survival |
| Dependency | X chứa target/raw rank/survival descendant bị cấm -> fail |
| Independence | Thay riêng survival sau khi cố định metadata/target không đổi X/cohort/prediction của recipe mới |
| Split | Không match nào xuất hiện ở hai split; timestamp/day blocks không bị tách |
| Preprocessing | Đổi validation/test extremes không đổi mean/scaler đã fit train |
| Timing | Kết quả sum/count/min không phụ thuộc cách chia chunk |
| Coverage | No-kill khác missing-event; T1 giữ same cohort với T0 |
| Comparison | Khác row IDs/labels/split/recipe -> reject paired comparison |
| Baseline | Constant chỉ tính từ train |
| Prediction | Test labels không được truyền vào logic tạo prediction |
| Metric | Recompute từ saved predictions khớp bảng báo cáo |
| Bootstrap | Resample whole match, giữ multiplicity và cặp T0/T1 |
| Device | Backend unsupported -> blocked; không ghi GPU từ CPU fixture |
| Checkpoint | Thiếu artifact hoặc signature cũ -> reject reuse |
| Finalization | Release mới không nhận run survival/old cohort như placement run mới |
| Notebook 12 | Không truy cập raw, download, build hoặc train |
| Bundle | Config/code embedded khớp source đã khóa về nội dung |

Sửa test kỳ vọng thiết kế cũ bằng contract mới; không xóa assertion chỉ để test xanh. Fixture riêng không ghi vào output nghiên cứu.

## 17. Artifact và versioning

Mỗi model run tối thiểu lưu:

- Run ID, target, feature recipe và thứ tự cột.
- Source/config/code/data signatures.
- Cohort receipt và split checksum.
- Backend/device/version, hyperparameters, seed.
- Fitted model và preprocessing state.
- Validation/test predictions theo scope được phép.
- Metrics micro/team/match-aware và status/reason.
- Thời gian, tài nguyên và đường dẫn/checksum artifact.

Prediction table cần `row_id`, `match_id`, `team_id`, `split`, actual target, `prediction_raw`, model/run ID; thêm clipped prediction nếu có recipe đăng ký.

Không reuse model P2 cũ chỉ vì cùng tên target. Cohort và feature set mới đã thay đổi ý nghĩa run.

Tăng version/signature đúng phạm vi thay đổi. Raw/ingestion có thể reuse khi source/schema/receipt tương thích; feature/model/comparison/release cũ phải được xét dependency trước khi reuse.

Không ghi đè immutable release. Canonical output chỉ cập nhật an toàn sau khi bản mới xác minh, không xóa bản tốt trước.

## 18. Môi trường và lệnh hỗ trợ

Giữ các giá trị:

```python
PUBG_STORAGE_MODE = "drive"
PUBG_DRIVE_PROJECT_ROOT = "/content/drive/MyDrive/PUBG_Project/Project_PUBG"
PUBG_REQUIRE_EXISTING_PROJECT = True
PUBG_BATCH_ROWS = 50000
```

Lệnh PowerShell kiểm tra trạng thái trước/sau sửa:

```powershell
Set-Location 'C:\Users\PC\Desktop\Project_PUBG'
git status --short
git diff --stat
git diff --check
```

Tìm các dependency cũ để phân loại, không thay thế toàn bộ bằng regex:

```powershell
rg -n 's1_|s2_|p1_|p2_|p3_|player_survive_time|current_survive_time' configs src tests README.md PUBG_RESEARCH_SPEC.md PUBG_IMPLEMENTATION_PLAN.md
```

Sau khi sửa source/generator, sinh riêng notebook bị ảnh hưởng bằng cơ chế đang có:

```powershell
python src/utils/generate_notebooks.py --only 09_rq3_prediction.ipynb
```

Lặp tương ứng cho các notebook có bundle hoặc caller thay đổi. Không chạy generator không tham số nếu không muốn nó sinh All-in-One. Không chạy notebook All-in-One.

Ví dụ test chọn lọc, chỉ chạy sau khi sửa expectation và môi trường có dependencies phù hợp:

```powershell
python -m unittest discover -s tests -p "test_w04_base_features.py"
python -m unittest discover -s tests -p "test_phase_d_prediction.py"
python -m unittest discover -s tests -p "test_phase12_comparisons.py"
python -m unittest discover -s tests -p "test_phase13_finalization.py"
python -m unittest discover -s tests -p "test_phase14_summary.py"
```

Đây là lệnh hướng dẫn, không phải kết quả test đã chạy cho bản chuyển đổi. Test mới nên đặt cùng module theo trách nhiệm hoặc bổ sung module khi thực sự cần. Unit test phải đi cùng chạy notebook fixture qua code path thực.

Không cài dependency mới hoặc giả định GPU khả dụng. Thiếu thư viện/môi trường thì ghi blocker và xử lý theo quyền đã được cấp.

## 19. Checklist bàn giao cuối

Chỉ đưa checklist này vào kế hoạch hiện hành khi bắt đầu triển khai; mọi mục dưới đây hiện chưa được nghiệm thu cho thiết kế mới.

- Mọi run trong required matrix có target duy nhất `normalized_placement`.
- Không còn yêu cầu survival model để training, evaluation hoặc finalize thành công.
- Cohort placement không phụ thuộc survival hợp lệ.
- Feature contract và dependency closure thống nhất source/config/bundle.
- N_teams được tính trước task filtering; target validation và roster limitation có báo cáo.
- T0/T1 cùng cohort và không bắt buộc phase features.
- Split theo match, preprocessing train-only, test được khóa đúng thời điểm.
- Chọn model bằng metric/weighting đã đăng ký.
- Metric recompute khớp predictions; paired bootstrap có CI thật.
- Không có placeholder prediction/metric hoặc nhãn test tham gia prediction.
- Mọi required notebook có output đã xem và artifact đọc lại được.
- Extension ngoài scope không bị báo giả là completed.
- Checkpoint/release cũ không bị reuse sai protocol.
- Full-data, Drive và GPU được chứng minh tại run tương ứng.
- README và báo cáo nói rõ hồi cứu, đơn vị player/team và giới hạn roster.
- Không sửa raw, không silent sample, không commit/push ngoài yêu cầu.

## 20. Mẫu bàn giao sau mỗi giai đoạn

```text
Giai đoạn / task ID:
Yêu cầu và dependency:
File, hàm, notebook/cell:
Thay đổi và ảnh hưởng protocol:
Lệnh thực chạy:
Fixture hoặc full-data scope:
Expected / actual:
Notebook output đã xem:
Artifact / report / checksum:
Task nghiệm thu:
Task còn mở / blocker:
Điều kiện và bước tiếp theo:
```

Đợt soạn tài liệu ngày 21/10/2026 chỉ tạo file này, đối chiếu cấu hình, target/cohort code, generator và kế hoạch hiện có. Chưa sửa protocol chính thức, source, config hoặc notebook; chưa chạy training/full-data. Bước triển khai đầu tiên là giai đoạn 0, INV-01: đưa quyết định một target và các lựa chọn phạm vi được chấp nhận vào đặc tả cùng kế hoạch hiện hành.
