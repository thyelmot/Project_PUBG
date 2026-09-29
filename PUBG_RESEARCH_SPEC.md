# PUBG_RESEARCH_SPEC.md
## Đặc tả nghiên cứu và triển khai chính thức — PUBG Data Mining

**Phiên bản:** 3.0  
**Ngày:** 24/09/2026  
**Trạng thái:** Thiết kế đã hoàn thiện trước triển khai (`code-first, execute-later`)  
**Môi trường mục tiêu:** Google Colab / cloud notebook  
**Nguồn dữ liệu:** Kaggle — *PUBG Match Deaths and Statistics* (`skihikingkevin/pubg-match-deaths`)  
**Tài liệu này là nguồn sự thật chính (single source of truth) cho việc triển khai.**

Kế hoạch hiện hành duy nhất: [PUBG_IMPLEMENTATION_PLAN.md](PUBG_IMPLEMENTATION_PLAN.md). Đọc [quy tắc thực hiện và tích theo bằng chứng](PUBG_IMPLEMENTATION_PLAN.md#tracking-rules), sau đó thực hiện [giai đoạn 0](PUBG_IMPLEMENTATION_PLAN.md#phase-0) đến [giai đoạn 16](PUBG_IMPLEMENTATION_PLAN.md#phase-16). Việc hợp nhất chỉ tổ chức lại triển khai; không thay đổi RQ, feature, target, split, metric hoặc protocol. Lịch sử nằm trong CHANGELOG_FIXES.md; bảng truy vết ở cuối kế hoạch.

> Nếu tài liệu này mâu thuẫn với các kế hoạch cũ như `kh.md`, `IMPLEMENT_GUIDE.md`, ghi chú notebook cũ hoặc prompt cũ, **tài liệu này được ưu tiên**. Không được tự động trộn thiết kế cũ vào thiết kế mới.

---

# 0. Mục đích của tài liệu

Tài liệu này mô tả toàn bộ thiết kế nghiên cứu, kiến trúc dữ liệu, quy tắc chống rò rỉ dữ liệu, chiến lược feature engineering (kỹ thuật tạo đặc trưng), EDA (phân tích dữ liệu khám phá), clustering (phân cụm), prediction (dự đoán), evaluation (đánh giá), Colab execution (thực thi trên Colab), checkpoint/versioning (điểm lưu/phiên bản), reproducibility (khả năng tái lập), cấu trúc notebook và yêu cầu README.

Mục tiêu của file là để một coding agent như Codex/Claude có thể:

1. hiểu chính xác bài toán nghiên cứu;
2. không tự thay đổi mục tiêu hoặc thêm bớt RQ;
3. triển khai toàn bộ code trước khi chạy full workflow;
4. không gây target leakage (rò rỉ biến mục tiêu);
5. xử lý được toàn bộ dữ liệu hợp lệ;
6. chạy tuần tự trên Google Colab;
7. có checkpoint/resume;
8. tạo đầy đủ artifact để người dùng tự viết báo cáo cuối.

---

# 1. Kết quả rà soát toàn bộ thiết kế

Sau khi đối chiếu toàn bộ luồng thảo luận và kế hoạch cũ, thiết kế mới được giữ nguyên về hướng nghiên cứu chính nhưng cần làm rõ/correct một số điểm để tránh lỗi khi triển khai.

## 1.1. Các điểm đã đúng và được giữ nguyên

- Dùng **toàn bộ dữ liệu hợp lệ**, không dùng sample làm kết quả nghiên cứu chính.
- Có thể dùng sample nhỏ chỉ cho:
  - smoke test;
  - debugging;
  - visualization (trực quan hóa);
  - diagnostic computation (tính toán chẩn đoán) nếu full computation quá đắt và được ghi rõ.
- Có ba RQ chính:
  - RQ1 — yếu tố hành vi liên hệ với survival/placement;
  - RQ2 — player types (kiểu người chơi);
  - RQ3 — prediction.
- Combat Timing (thời điểm giao tranh) là extension chính từ event/death data.
- RQ2 clustering ở **aggregated player profile level**.
- RQ3 có current-match retrospective modeling và historical prediction.
- Historical feature phải dùng quá khứ, không được chứa current match.
- Split chính ưu tiên chronology nếu chronology đáng tin.
- Notebook chỉ là orchestration layer (lớp điều phối); logic chính nằm trong `src/`.
- Cloud-first, ưu tiên Google Colab.
- Checkpoint/versioning/logging/config/reproducibility là phần bắt buộc.
- Báo cáo cuối do người dùng tự tổng hợp; project cung cấp notebook tổng hợp kết quả.

## 1.2. Các điểm cần sửa hoặc bổ sung

### A. Phải kiểm tra đủ các shard/file dữ liệu, không giả định chỉ có hai file
Dataset có hai **nhóm** dữ liệu chính (`agg_match_stats` và `kill_match_stats`) nhưng có thể gồm nhiều shard CSV.

Pipeline phải:
- inventory (kiểm kê) mọi file;
- xử lý mọi shard;
- ghi checksum, kích thước, số dòng;
- không giả định chỉ tồn tại một `agg_match_stats.csv` và một `kill_match_stats.csv`.

### B. Bổ sung cột thời gian vào schema contract
Historical modeling phụ thuộc chronology. Vì vậy các cột như `date`/timestamp nếu tồn tại phải được coi là cột quan trọng ngay từ giai đoạn schema inspection.

Không được viết historical pipeline trước rồi mới phát hiện dataset không có thứ tự thời gian đủ chi tiết.

### C. Phân biệt team-size mode và perspective/match mode
Không dùng một biến `game_mode` mơ hồ cho mọi ý nghĩa.

Nên chuẩn hóa:
- `team_size_mode`: Solo / Duo / Squad, ưu tiên suy ra từ `party_size` hoặc field tương đương đã xác minh.
- `perspective_mode`: TPP/FPP hoặc `match_mode` nếu dataset có.
- Các mode khác chỉ giữ nếu schema thật xác nhận.

### D. Target-derived feature không chỉ bị cấm trong prediction mà còn phải bị hạn chế trong RQ1
Ví dụ:

`kills_per_minute = kills / survival_time`

Nếu dùng biến này để phân tích quan hệ với `survival_time`, mối quan hệ bị tạo ra một phần bởi chính công thức.

Do đó:
- target-derived feature bị **cấm trong predictive model của target đó**;
- đồng thời **không được dùng làm bằng chứng chính cho RQ1 với chính target xuất hiện trong công thức**;
- có thể giữ làm diagnostic hoặc phân tích với target khác.

### E. Chronology phải được phân cấp, không chỉ pass/fail
Cần `chronology_grade`:

- **Grade A:** có exact timestamp/order đủ tin cậy → được dùng `sort → expanding → shift(1)`.
- **Grade B:** chỉ có date/day, không biết thứ tự nội ngày → historical feature của trận ngày D chỉ dùng dữ liệu có ngày `< D`; **không dùng trận cùng ngày**.
- **Grade C:** không có chronology đáng tin → S2/P3 không được gọi là future prediction; mặc định disable historical prediction chính thức.

Đây là điểm chống leakage quan trọng.

### F. Placement là team outcome nhưng dữ liệu modeling có thể ở player-match level
`team_placement` giống nhau giữa đồng đội.

Nếu RQ3 placement sử dụng một dòng/player-match:
- estimand phải ghi rõ là **player-level observation of team placement**;
- mọi row trong cùng `match_id` phải nằm cùng split;
- evaluation phải có thêm match/team-aware aggregation hoặc uncertainty;
- không được giả định các player-row độc lập hoàn toàn.

### G. RQ2 có nguy cơ bị game-mode confounding
Một player chơi nhiều Solo và một player chơi nhiều Squad có thể khác profile chỉ vì mode.

Quy tắc:
- chạy mode EDA trước;
- nếu khác biệt mode đáng kể, clustering chính phải:
  - chạy theo từng `team_size_mode`, hoặc
  - xây profile theo `(player_name, team_size_mode)`.
- chỉ dùng overall player profile nếu EDA cho thấy cách gộp hợp lý.
- không chọn cách xử lý mode dựa trên outcome sau clustering.

### H. Hierarchical Clustering không được bắt buộc chạy full nếu dữ liệu quá lớn
Hierarchical Clustering thường có chi phí bộ nhớ/thời gian lớn.

Vì vậy:
- K-Means là main method;
- Hierarchical là supporting validation;
- nếu full hierarchical không khả thi, dùng reproducible diagnostic subset hoặc cluster centroids;
- phải ghi rõ đây là diagnostic/supporting, không giả vờ là full-data clustering.

### I. Cần full-data scalable fallback cho modeling
Random Forest/XGBoost có thể tốn tài nguyên.

Project phải có ít nhất:
- constant baseline;
- scalable linear baseline;
- nonlinear candidate khi khả thi.

Không được:
- train model trên sample rồi gắn nhãn là full-data result;
- im lặng loại full-data experiment do RAM;
- gán `0` cho experiment failed.

### J. Structural missing phải có semantics
Ví dụ:
- không kill → `first_kill_time` missing theo định nghĩa;
- không kill → `damage_per_kill` missing;
- kills+assists=0 → `assist_ratio` missing.

Không được tự động fill 0 nếu 0 mang ý nghĩa khác.

### K. Combat Timing aggregation phải chính xác qua chunk
Đối với `avg_kill_time`:
- lưu `sum_kill_time`;
- lưu `kill_count`;
- cuối cùng `avg = sum / count`.

Không average các chunk means.

`first_kill_time` dùng global minimum.

### L. Nên có uncertainty cho các comparison chính
Do player rows cùng match phụ thuộc nhau, các delta chính nên có match-level paired bootstrap CI nếu tài nguyên cho phép.

Ưu tiên:
- P1 vs P2;
- T0 vs T1;
- ablation group comparisons;
- model chính vs baseline.

### M. Cần schema contract + alias mapping
Vì code được viết trước khi execution:
- không hard-code giả định schema một cách im lặng;
- có `configs/schema.yaml`;
- khai báo required/optional columns;
- hỗ trợ alias có kiểm soát;
- fail fast nếu schema không đáp ứng contract.

### N. Cần notebook khóa kết quả trước notebook summary
Bổ sung:

`11_finalize_results.ipynb`

Notebook này:
- kiểm tra run hợp lệ;
- khóa final run;
- tạo `final_results_manifest.json`;
- tạo report tables;
- tạo figure manifest.

Sau đó:

`12_final_results_summary.ipynb`

chỉ đọc artifact đã khóa.

### O. Những extension cũ không còn thuộc core scope
Các ý sau **không phải core requirement** trừ khi người dùng mở rộng sau:
- Association Rule Mining;
- spatial kill/death map mining sâu;
- Elo/Glicko/TrueSkill;
- NDCG ranking;
- deep learning;
- classification Top-N;
- causal inference.

Combat Timing là event extension chính đã chốt.

---

# 2. Research Problem (Vấn đề nghiên cứu)

**Phân tích hành vi người chơi và các yếu tố ảnh hưởng/liên hệ đến khả năng sống sót và thứ hạng trong PUBG bằng phân tích dữ liệu và Machine Learning (học máy).**

Lưu ý ngôn ngữ khoa học:

- Dữ liệu phần lớn là thống kê sau trận.
- Các phân tích current-match là retrospective (hồi cứu).
- Không được dùng từ “gây ra”, “làm tăng”, “chiến thuật này giúp” nếu chỉ có association (mối liên hệ).
- Khi không có causal design (thiết kế nhân quả), kết luận phải ở mức:
  - “liên hệ với”;
  - “đồng biến/nghịch biến”;
  - “cung cấp thông tin dự đoán”;
  - “được quan sát trong dataset”.

---

# 3. Research Questions (RQ)

## RQ1 — Behavioral Relationships

**Những đặc trưng hành vi, bao gồm các đặc trưng thời gian từ event/death data (dữ liệu sự kiện hạ gục/bị hạ), có mối liên hệ mạnh nhất với survival time (thời gian sống sót) và placement (thứ hạng cuối trận)?**

Mục tiêu:
- Discover (khám phá);
- xác định các nhóm hành vi đáng chú ý;
- phân tích Overall và theo mode khi cần.

Không được:
- biến correlation thành causality;
- dùng target-derived feature như bằng chứng chính với chính target đó.

## RQ2 — Player Types

**Có thể phân nhóm người chơi thành các kiểu hành vi khác nhau dựa trên các đặc trưng gameplay (thống kê hành vi trong trận) hay không, và các nhóm này khác nhau thế nào về khả năng sống sót và thứ hạng?**

Mục tiêu:
- Understand (hiểu các kiểu hành vi);
- clustering không dùng survival/placement làm input;
- outcome chỉ được dùng **sau clustering** để profiling/interpretation.

## RQ3 — Prediction

**Có thể sử dụng các đặc trưng hành vi để dự đoán survival time (thời gian sống sót) và placement (thứ hạng) của người chơi hay không?**

Bao gồm:
- current-match retrospective prediction;
- historical future-match prediction nếu chronology đủ tin cậy.

---

# 4. Dataset và nguồn dữ liệu

## 4.1. Dataset

Kaggle:
`skihikingkevin/pubg-match-deaths`

Tên:
**PUBG Match Deaths and Statistics**

## 4.2. Hai nhóm dữ liệu

### `agg_match_stats`
Một dòng dự kiến đại diện một player trong một match.

Candidate columns cần kiểm tra thực tế:

- `date` hoặc timestamp tương đương;
- `match_id`;
- `player_name`;
- `team_id`;
- `party_size`;
- `game_size`;
- `match_mode` nếu có;
- `player_kills`;
- `player_dmg`;
- `player_assists`;
- `player_dbno`;
- `player_dist_walk`;
- `player_dist_ride`;
- `player_survive_time`;
- `team_placement`.

### `kill_match_stats`
Event-level data.

Cần inspect schema để xác định ít nhất:
- `match_id`;
- event time (`time`/`event_time`);
- `killer_name`;
- `victim_name`;
- killer/victim placement nếu có;
- map;
- killer/victim coordinates nếu có;
- kill cause/weapon nếu có.

Combat Timing core chỉ yêu cầu:
- `match_id`;
- event time;
- `killer_name`.

Các cột event khác là optional/future work.

## 4.3. Inventory bắt buộc

Pipeline phải tự phát hiện và ghi:

- tất cả aggregate shards;
- tất cả kill/death shards;
- file name;
- byte size;
- row count;
- column names;
- schema/dtype;
- checksum;
- source URL;
- download date;
- dataset version nếu xác định được.

Output:
`artifacts/manifests/source_inventory.json`

## 4.4. Quy tắc source

Raw input có thể đến từ:
- public Google Drive URL;
- direct HTTP URL;
- Kaggle-export/public mirror nếu được phép.

Không yêu cầu ChatGPT/Colab phải có quyền đọc Drive cá nhân chỉ để lấy raw data.

`configs/data.yaml` phải hỗ trợ:
- `archive_url`;
- hoặc danh sách `agg_urls` / `kill_urls`;
- checksum nếu có;
- file pattern.

---

# 5. “Dùng toàn bộ dữ liệu” nghĩa là gì?

Official analysis dùng **toàn bộ dữ liệu hợp lệ sau preprocessing**.

Không có official research sampling để giảm cohort vì RAM.

Được phép:
- development sample;
- smoke-test sample;
- visualization sample;
- diagnostic sample cho thuật toán có chi phí không phù hợp full data, ví dụ hierarchical/silhouette.

Mọi sample diagnostic phải ghi:
- lý do;
- n;
- seed;
- sampling rule;
- không được dùng thay official full-data statistics/model nếu output được gọi là full-data.

Full-data không có nghĩa:
- giữ dữ liệu lỗi;
- giữ duplicate;
- giữ missing target không sử dụng được;
- dùng mọi cột làm feature;
- bỏ train/test separation.

---

# 6. Units of Analysis (Đơn vị phân tích)

## RQ1
**Player-match level**

Một row:
`(match_id, player_name)`

## RQ2
**Aggregated player profile level**

Main conceptual unit:
`player_name`

Tuy nhiên sau mode EDA có thể chuyển thành:
`(player_name, team_size_mode)`

nếu mode confounding rõ.

## RQ3 — Current match
**Player-match level**

Target placement là team-level outcome được quan sát trên player row.

## RQ3 — Historical
**Player-history-to-current-match level**

Một row:
historical behavior của player trước match hiện tại → outcome của current match.

## Event data
Event-level chỉ là intermediate source để tạo Combat Timing.

---

# 7. Target Definition

## 7.1. Survival target

`player_survive_time`

Unit phải được verify từ data/documentation trước modeling.

Validation:
- finite;
- `>= 0`;
- hợp lý so với estimated match duration.

## 7.2. Placement target

Raw:
`team_placement`

Không ưu tiên dùng raw placement trực tiếp vì số team mỗi match khác nhau.

### Number of teams

\[
N_{teams} = \text{nunique}(team\_id)
\]

trong `match_id`, sau validation.

### Normalized placement

\[
normalized\_placement
=
1 -
\frac{team\_placement - 1}
{N_{teams} - 1}
\]

Ý nghĩa:
- 1 = hạng nhất;
- 0 = hạng cuối.

### Validation
- `N_teams > 1`;
- `team_placement ∈ [1, N_teams]`;
- `normalized_placement ∈ [0,1]`.

`N_teams = 1`:
- không dùng công thức bình thường;
- flag riêng;
- quyết định include/exclude sau Data Quality EDA.

---

# 8. Game Mode Definition

Không dùng tên `game_mode` nếu chưa rõ nghĩa.

## 8.1. `team_size_mode`
Ưu tiên:
- `party_size = 1` → Solo;
- `party_size = 2` → Duo;
- `party_size >= 3` → Squad;

chỉ sau khi schema/data distribution xác nhận quy tắc này hợp lý.

Nếu dataset có mode label đáng tin hơn, ưu tiên label nguồn.

## 8.2. `perspective_mode`
Nếu `match_mode` chứa TPP/FPP hoặc tương đương:
- giữ riêng;
- không gộp với team-size mode.

## 8.3. Mode EDA quyết định analysis strategy

Sau EDA:
- joint analysis;
- stratified analysis;
- hoặc mode context feature.

Không quyết định trước khi xem dữ liệu.

---

# 9. Core Data Architecture

Ba processed datasets chính:

## 9.1. `player_match_features`
Single source of truth ở player-match level.

Bao gồm:
- identity keys;
- date/time;
- match metadata;
- behavior raw;
- derived features;
- Combat Timing;
- outcomes;
- validation flags.

## 9.2. `player_profile_features`
Dùng cho RQ2.

Một row:
- player hoặc player-mode profile.

## 9.3. `historical_player_match_features`
Dùng cho S2/P3.

Một row:
- historical state trước current match;
- current target;
- chronology metadata.

---

# 10. Data Preprocessing Architecture

Logical modules:

```text
download
→ inventory
→ schema_validation
→ cleaning
→ match_metadata
→ behavioral_features
→ combat_timing
→ merge
→ validation
→ processed parquet
```

Không chỉnh sửa raw source trực tiếp.

## 10.1. Cleaning rules

Kiểm tra:
- duplicate;
- missing keys;
- invalid numeric;
- negative count/distance/time;
- placement invalid;
- impossible ratio;
- join explosion;
- schema mismatch.

## 10.2. Removal log

Mỗi removal step phải ghi:

- step;
- rule;
- rows_before;
- rows_removed;
- rows_after;
- reason;
- example count;
- version.

File:
`artifacts/logs/removal_log.csv`

Không cần lưu mọi row bị loại nếu quá lớn, nhưng cần:
- aggregate counts;
- optional quarantine sample;
- nếu khả thi lưu partition các invalid rows với reason code.

## 10.3. Missing categories

### Structural missing
Missing đúng theo định nghĩa hành vi.

Ví dụ:
- không kill → `first_kill_time` missing.

### Data-error missing
Missing do:
- key lỗi;
- parse lỗi;
- source thiếu bất thường.

Hai loại không được xử lý giống nhau.

---

# 11. Feature Architecture

Mọi feature phải nằm trong **Feature Registry**.

Metadata tối thiểu:

- `name`;
- `group`;
- `source`;
- `level`;
- `formula`;
- `dtype`;
- `missing_semantics`;
- `allowed_rq`;
- `allowed_targets`;
- `forbidden_targets`;
- `leakage_reason`;
- `status`;
- `requires_current_outcome`;
- `requires_survival`;
- `requires_placement`;
- `version`.

Status:
- `candidate`;
- `confirmed`;
- `optional`;
- `excluded`.

---

# 12. Combat Behavior Features

Raw:
- `player_kills`;
- `player_dmg`.

Derived candidates:

\[
kills\_per\_minute =
\frac{player\_kills}{player\_survive\_time / 60}
\]

\[
damage\_per\_minute =
\frac{player\_dmg}{player\_survive\_time / 60}
\]

\[
damage\_per\_kill =
\frac{player\_dmg}{player\_kills}
\]

Rules:
- survival <= 0 → rate invalid/missing;
- kills=0 → `damage_per_kill = NaN`;
- không epsilon nếu epsilon làm đổi semantics.

### Forbidden
`kills_per_minute`, `damage_per_minute`:
- forbidden for survival prediction;
- forbidden as primary RQ1 evidence against survival.

---

# 13. Movement Behavior Features

Raw:
- `player_dist_walk`;
- `player_dist_ride`.

Derived:

\[
total\_distance =
player\_dist\_walk + player\_dist\_ride
\]

\[
walking\_velocity =
\frac{player\_dist\_walk}{player\_survive\_time}
\]

\[
riding\_velocity =
\frac{player\_dist\_ride}{player\_survive\_time}
\]

\[
walk\_ratio =
\frac{player\_dist\_walk}{total\_distance}
\]

Do not keep `ride_ratio` simultaneously as main feature because approximately:

\[
ride\_ratio \approx 1-walk\_ratio
\]

Rules:
- total_distance=0 → `walk_ratio` structural missing hoặc rule do EDA quyết định;
- không tự fill 0;
- velocity forbidden for survival prediction và không dùng làm primary association với survival.

---

# 14. Support Behavior Features

Raw:
- `player_assists`;
- `player_dbno`.

Derived:

\[
assist\_ratio =
\frac{assists}{kills+assists}
\]

khi denominator > 0.

Main:
- assists;
- DBNO;
- assist_ratio.

Excluded from main:
- dbno_ratio.

Team-level candidates chỉ optional:
- team_kills;
- team_damage;
- team_assists;
- team_avg_survival.

Không đưa team features vào main model nếu chưa có experiment riêng và leakage review.

---

# 15. Combat Timing

## 15.1. Mục tiêu

Từ kill/death events, mô tả **thời điểm player thực hiện kill**.

Main features:
- `first_kill_time`;
- `avg_kill_time`;
- `early_kill_count`;
- `mid_kill_count`;
- `late_kill_count`;
- `early_kill_ratio`;
- `mid_kill_ratio`;
- `late_kill_ratio`;
- `has_kill`.

Candidate profile helper:
- `kill_active_match_ratio`.

## 15.2. Match duration proxy

Primary proxy:

\[
estimated\_match\_duration =
\max(player\_survive\_time)
\]

within `match_id`.

Đây là proxy, không gọi là exact official match duration.

Validation:
- >0;
- finite;
- compare event time range;
- compare distribution;
- inspect abnormal cases.

## 15.3. Relative event time

\[
relative\_event\_time =
\frac{event\_time}
{estimated\_match\_duration}
\]

Primary phase split:

- Early: `[0, 1/3)`
- Mid: `[1/3, 2/3)`
- Late: `[2/3, 1]`

Out-of-range event:
- không silently clip;
- flag;
- audit;
- quyết định sau validation.

## 15.4. No-kill semantics

Nếu player có 0 kill:
- `has_kill = 0`;
- first/avg kill time = NaN;
- early/mid/late ratios = NaN.

Không biến NaN thành 0 trước khi semantics được bảo toàn.

## 15.5. Chunk-safe aggregation

Partial states:

- `kill_count`;
- `sum_kill_time`;
- `first_kill_time_partial = min`;
- early/mid/late counts.

Final:

\[
avg\_kill\_time =
sum\_kill\_time / kill\_count
\]

Không average partial means.

## 15.6. Kill-event vs aggregate kills

Không yêu cầu `event_kill_count == player_kills` tuyệt đối.

Phải audit:
- match rate;
- discrepancy distribution;
- unnamed/environment kills;
- join failure;
- source semantics.

Không fail pipeline chỉ vì có discrepancy trước khi hiểu nguyên nhân.

---

# 16. Historical Features

Core candidates:
- `hist_games_played`;
- `hist_avg_kills`;
- `hist_avg_damage`;
- `hist_avg_survival`;
- `hist_avg_walk`;
- `hist_avg_ride`;
- `hist_avg_assists`;
- `hist_avg_dbno`;
- `hist_kd`;
- `hist_avg_normalized_placement`.

Optional:
- same-mode historical versions;
- rolling last 5;
- rolling last 10;
- Combat Timing historical features.

Core default:
**expanding history**, không rolling.

## 16.1. Chronology validation

Function:
`validate_chronology()`

Output:
- available time columns;
- granularity;
- monotonic feasibility;
- duplicate timestamps;
- same-day multiplicity;
- null rate;
- chronology grade.

## 16.2. Grade A

Exact trustworthy ordering:

```text
groupby(player)
→ sort(time)
→ expanding
→ shift(1)
```

Current match không được nằm trong history.

## 16.3. Grade B

Chỉ có day/date:

Historical features cho match ngày D dùng:

\[
\{matches: date < D\}
\]

Không dùng `date == D`.

Điều này tránh việc arbitrary file order tạo fake chronology.

## 16.4. Grade C

Không có trustworthy chronology:

- historical future prediction bị disable;
- S2/P3 status = `blocked_by_chronology`;
- không đổi tên thành future prediction;
- có thể giữ exploratory player profile analysis nhưng phải tách khỏi historical claim.

---

# 17. RQ2 Player Profile

## 17.1. Minimum games threshold

Chưa chốt trước data.

Candidate diagnostics:
- 5;
- 10;
- 20;
- 50.

Chọn dựa trên:
- players retained;
- profile stability;
- feature reliability;
- compute feasibility.

Không chọn threshold dựa trên:
- cluster survival;
- cluster placement;
- test performance.

## 17.2. Main Design 3 — Selected Behavioral Profile

### Combat Level
- `avg_kills`;
- `avg_damage`;
- `std_kills`;
- `std_damage`.

### Movement Style
- `avg_walk`;
- `avg_ride`;
- `avg_walk_ratio`.

### Support Style
- `avg_assists`;
- `avg_dbno`;
- `avg_assist_ratio`.

### Combat Timing
- `avg_early_kill_ratio`;
- `avg_mid_kill_ratio`;
- `avg_late_kill_ratio`;
- `early_combat_match_ratio`.

Candidate:
- `kill_active_match_ratio`.

### Meta
- `games_played` dùng để filter reliability;
- mặc định không clustering input;
- C3 sensitivity: with/without `games_played`.

## 17.3. Conditional averages

Nếu match-level ratio structural missing:
- `avg_early_kill_ratio` phải ghi rõ là average **trên kill-active matches** nếu NaN bị bỏ khi aggregate.
- lưu denominator:
  - `kill_active_matches`;
  - `support_active_matches` nếu cần.

Không để `mean(skipna=True)` tạo semantics ngầm.

## 17.4. Outcomes — tuyệt đối không dùng làm clustering input

- `avg_survival`;
- `avg_normalized_placement`.

Chỉ dùng sau clustering.

---

# 18. RQ2 Mode Confounding Rule

Sau Game Mode EDA:

### Nếu mode differences nhỏ/chấp nhận được
Có thể dùng overall player profile.

### Nếu mode differences rõ
Main clustering:
- per-mode player profiles;
- hoặc `(player_name, team_size_mode)` profile.

Không đưa `team_size_mode` dạng one-hot vào clustering chỉ để “sửa” confounding nếu điều đó khiến cluster chủ yếu phản ánh mode.

Decision phải:
- ghi trong config;
- ghi lý do;
- được khóa trước outcome interpretation.

---

# 19. Clustering Methods

## 19.1. Main
K-Means.

Nếu full profile data quá lớn:
- được phép dùng MiniBatchKMeans như scalable implementation;
- phải log algorithm change;
- không gọi MiniBatchKMeans là exact K-Means;
- cùng feature space/scaling.

## 19.2. Supporting
Hierarchical Clustering.

Nếu full data không khả thi:
- reproducible subset;
- hoặc cluster centroids;
- chỉ dùng supporting validation.

## 19.3. Optional
DBSCAN chỉ khi EDA cho thấy density/outlier structure có lý do rõ.

## 19.4. Scaling
Fit scaler trên clustering training/development profiles.

Default implementation hỗ trợ:
- StandardScaler;
- RobustScaler sensitivity.

Log transform:
- code có khả năng;
- mặc định off/TBD;
- chỉ bật sau skew/outlier EDA.

## 19.5. K selection

Dùng:
- Elbow;
- Silhouette;
- Davies-Bouldin;
- stability;
- interpretability.

Không dùng survival/placement để chọn K.

Silhouette full data quá đắt:
- diagnostic sample được phép;
- seed cố định;
- ghi n/sample rule.

## 19.6. Cluster naming

Chỉ đặt tên sau:
- centers/profiles;
- standardized means;
- feature distributions.

Không đặt tên trước rồi ép cluster theo kỳ vọng.

---

# 20. RQ3 Experiment Matrix

## 20.1. Survival

### S1 — Current-match safe
Current-match feature không chứa survival trong formula.

Đây là:
**retrospective current-match modeling**, không phải pre-match prediction.

### S2 — Historical
Previous-match behavior → current `player_survive_time`.

Chỉ chạy nếu chronology Grade A/B.

## 20.2. Placement

### P1 — Current Full Behavior
Combat + Movement + Support + Combat Timing + `player_survive_time`
→ `normalized_placement`.

### P2 — Current Behavior Without Survival
Giống P1 nhưng bỏ `player_survive_time`.

P1 vs P2 là comparison chính.

### P3 — Historical
Historical features → current normalized placement.

Chỉ Grade A/B.

## 20.3. Combat Timing Contribution

### T0
Combat + Movement + Support.

### T1
Combat + Movement + Support + Combat Timing.

Compare:
- ΔMAE;
- ΔRMSE;
- ΔR².

Comparison phải:
- same cohort;
- same split;
- same model;
- same preprocessing;
- same rows.

## 20.4. Group Ablation

- ABL-FULL;
- ABL-C remove Combat;
- ABL-M remove Movement;
- ABL-S remove Support;
- ABL-T remove Combat Timing.

Khi remove group:
- remove raw;
- remove derived descendants.

Ví dụ bỏ Movement mà còn `total_distance` là sai.

---

# 21. Leakage Rules

## 21.1. Survival target — forbidden current features

- `player_survive_time`;
- `kills_per_minute`;
- `damage_per_minute`;
- `walking_velocity`;
- `riding_velocity`;
- `death_time`;
- bất kỳ feature nào chứa current survival target.

## 21.2. Placement target — forbidden current features

- `team_placement`;
- `normalized_placement`;
- feature trực tiếp/gián tiếp tạo từ placement.

Historical previous placement được phép.

## 21.3. RQ1 target-derived association rule

Nếu feature chứa target trong formula:
- không dùng làm primary evidence về relationship với chính target đó.

## 21.4. Fit leakage

Mọi learned preprocessing:
- imputer;
- scaler;
- feature selector;
- model;
- clustering scaler;

phải fit trên training/development appropriate partition, không toàn dataset nếu artifact được đánh giá trên heldout.

## 21.5. Match grouping

Mọi row cùng `match_id` phải thuộc cùng split.

Không split player rows của cùng match qua train/test.

## 21.6. Historical leakage

Current match tuyệt đối không được vào:
- history count;
- historical mean;
- rolling window;
- historical rank;
- historical Combat Timing.

---

# 22. Split Strategy

## 22.1. Main — chronology reliable

Nếu Grade A/B:

- Past → Train;
- Later → Validation;
- Latest → Test.

Mỗi `match_id` chỉ ở một split.

Exact proportions:
- TBD sau inventory/time coverage;
- không chốt trước data.

Test:
- locked;
- không dùng để chọn threshold, K, feature, model, hyperparameter.

## 22.2. Fallback — chronology Grade C

Nếu no reliable chronology:
- group split by `match_id`;
- không gọi là future prediction;
- gọi là heldout retrospective generalization.

Historical S2/P3 không chạy chính thức.

## 22.3. Optional secondary split

Group by `player_name`:
- test unseen-player generalization.

Không thay main split.

---

# 23. Models

## 23.1. Constant Baselines

Cần cả:
- train mean;
- train median.

Lý do:
- mean hữu ích cho squared-error comparison;
- median là constant baseline tự nhiên cho MAE.

## 23.2. Linear
- Linear Regression;
- scalable SGDRegressor optional/core fallback nếu full data cần streaming.

## 23.3. Nonlinear candidates
- Random Forest Regressor;
- Gradient Boosting / HistGradientBoosting nếu phù hợp;
- XGBoost nếu environment/resource cho phép.

Không cần chạy tất cả Cartesian product.

## 23.4. Full-data rule

Official full-data model:
- phải fit toàn training cohort hợp lệ của experiment đó.

Nếu model không khả thi:
- status `resource_limited`;
- không thay bằng sample và gọi cùng tên kết quả.

---

# 24. Feature Selection

Task-specific feature sets:

- `feature_set_rq1`;
- `feature_set_rq2`;
- `feature_set_rq3_survival`;
- `feature_set_rq3_placement`.

Pipeline:

```text
RuleBasedFiltering
→ Variance/SparsityCheck
→ CorrelationAnalysis
→ VIF/RedundancyAnalysis
→ InterpretabilityReview
→ ModelBasedImportance
→ GroupAblation
→ Final Task-Specific Feature Set
```

## 24.1. Correlation
Use:
- Pearson;
- Spearman.

Không dùng p-value nhỏ vì N lớn làm bằng chứng “mạnh”.
Tập trung:
- effect size;
- direction;
- consistency;
- mode differences.

## 24.2. VIF
Diagnostic only.

Không mechanical delete theo threshold duy nhất.

Chỉ dùng trên:
- numeric suitable subset;
- sau missing handling;
- tránh đưa deterministic descendants cùng lúc.

## 24.3. Importance
RQ3:
- model importance;
- permutation importance.

Interpret correlated features cẩn thận.

## 24.4. Ablation
Feature-group ablation là evidence chính về group contribution.

---

# 25. EDA Plan — 8 Phases

## Phase 1 — Structural EDA
- matches;
- players;
- teams;
- files/shards;
- game size;
- team_size_mode;
- perspective mode nếu có;
- games_per_player;
- N_teams;
- date/time coverage.

## Phase 2 — Data Quality EDA
- missing;
- duplicates;
- invalid ranges;
- outliers;
- match consistency;
- join quality;
- identity coverage.

## Phase 3 — Raw Feature EDA
- mean;
- median;
- std;
- skewness;
- zero rate;
- histograms;
- boxplots.

## Phase 4 — Derived Feature Validation
- ranges;
- NaN;
- Inf;
- denominator counts;
- structural missing rates.

## Phase 5 — Game Mode EDA
Overall vs Solo/Duo/Squad.

Quyết định:
- joint;
- stratified;
- player-mode profile.

## Phase 6 — Relationship EDA for RQ1
Combat/Movement/Support vs:
- survival;
- placement.

Pearson + Spearman khi phù hợp.

Target-derived features không được dùng sai.

## Phase 7 — Combat Timing EDA
- phase counts;
- ratios;
- first kill;
- survival/placement associations;
- mode differences.

## Phase 8 — Historical Feasibility EDA
- chronology grade;
- games history distribution;
- history depth;
- same-day collisions;
- stability.

Chỉ sau Phase 1–8 mới chốt data-dependent parameters.

---

# 26. Chart Catalog

## A. Dataset Overview
- A01 Games per Player Distribution
- A02 Players Remaining by Threshold
- A03 Team Size Mode Distribution
- A04 Game Size Distribution
- A05 Teams per Match Distribution
- A06 Match Date Coverage

## B. Raw Features
- B01 kills histogram + box
- B02 damage histogram + box
- B03 assists
- B04 DBNO
- B05 walk
- B06 ride
- B07 total distance
- B08 survival
- B09 team placement
- B10 normalized placement

## C. Derived Validation
- C01 kills/minute
- C02 damage/minute
- C03 damage/kill
- C04 walk ratio
- C05 assist ratio
- C06 structural missing rates

## D. Mode Comparison
- D01 kills by mode
- D02 damage
- D03 assists
- D04 DBNO
- D05 walk
- D06 ride
- D07 survival
- D08 placement

## E. Correlation
- E01 Pearson heatmap
- E02 Spearman heatmap

## F. Behavior vs Survival
Selected F01–F07 based on valid non-target-derived features.

## G. Behavior vs Placement
G01–G06.

## H. Combat Timing
- H01 Kill Phase Distribution
- H02 Kill Phase Ratio
- H03 First Kill Time Distribution
- H04 First Kill Time vs Survival
- H05 First Kill Time vs Placement
- H06 Combat Phase by Placement Group — high priority
- H07 Combat Timing by Mode

## I. Historical
- I01 Historical Games Available
- I02 Historical Feature Stability
- I03 Same-Day Chronology Collision Rate

---

# 27. Visualization Rule

Full-data statistic ≠ vẽ mọi điểm.

Được phép:
- hexbin;
- binning;
- density;
- aggregated mean;
- fixed-seed visualization sample.

Nếu sample chỉ để plot:
ghi rõ:
`visualization sample only — statistics computed on full valid data`.

---

# 28. Data Quality Report

Bắt buộc có:

## Dataset Summary
- rows;
- columns;
- unique matches;
- unique players;
- unique teams;
- date range;
- shards;
- dtypes.

## Missing
- per column;
- structural vs error.

## Duplicate
- exact row;
- duplicate `(match_id, player_name)` agg;
- event duplicates theo validated event key.

## Range
- kills/damage/assists/dbno >=0;
- walk/ride/survival >=0;
- placement valid;
- ratios [0,1].

## Match Consistency
- team placement;
- team count;
- survive vs duration proxy;
- event time.

## Join Quality
- matched killer;
- unmatched killer;
- matched victim;
- unmatched victim;
- unmatched match;
- join success rate;
- discrepancy.

---

# 29. Player Identity Audit

`player_name` không được mặc định là immutable account ID.

Audit:
- missing player_name;
- duplicates same player name within match;
- games_per_player;
- suspicious identifiers;
- join case/whitespace;
- encoding.

Rows missing `player_name`:
- có thể giữ cho RQ1 nếu các field khác hợp lệ;
- không được đưa vào player-profile/history như một fake `"UNKNOWN"` player chung.

---

# 30. RQ1 Output

RQ1 phải tạo:

`reports/tables/rq1_relationship_summary.csv`

Columns gợi ý:
- feature;
- feature_group;
- outcome;
- mode;
- n;
- Pearson;
- Spearman;
- valid_for_primary_interpretation;
- target_derived_flag;
- notes.

RQ1 kết luận:
- group-level;
- feature-level;
- mode-aware;
- Combat Timing riêng.

---

# 31. RQ2 Experiments

- C1 Main K-Means
- C2 Hierarchical Validation
- C3 games_played Sensitivity
- C4 Minimum Games Threshold Sensitivity
- C5 Outcome Comparison

Optional:
- C6 mode-specific clustering sensitivity nếu mode strategy cần.

Output:
- cluster assignments;
- cluster centers;
- standardized profiles;
- cluster sizes;
- silhouette/DB;
- outcome comparison;
- robustness summary.

---

# 32. RQ3 Evaluation Metrics

Main:
- MAE;
- RMSE;
- R².

Placement MAE dễ diễn giải trên [0,1].

Không gọi R² là accuracy.

## Error aggregation

Report:
- micro by player-match;
- match-aware summary;
- nếu phù hợp team-aware summary cho placement.

---

# 33. Uncertainty / Confidence Interval

Main comparisons nên hỗ trợ paired bootstrap by match.

Process:
1. aggregate per-match error contribution;
2. sample matches with replacement;
3. same resampled matches for candidate/reference;
4. compute delta;
5. 95% percentile CI.

Priorities:
- P1 vs P2;
- T0 vs T1;
- strongest nonlinear model vs baseline;
- ABL group effects.

Không bắt buộc chạy CI cho mọi exploratory chart.

---

# 34. Error Analysis

Required:

## By mode
Solo/Duo/Squad.

## By historical depth
Candidate bins:
- 5–10;
- 11–20;
- 21–50;
- 50+.

Actual bins có thể điều chỉnh theo EDA trước final test.

## By placement region
- top;
- middle;
- bottom.

## By survival region
- short;
- medium;
- long.

Boundary phải dựa trên train/validation distribution, không test cherry-pick.

---

# 35. Experiment Registry

Metadata:

- `experiment_id`;
- `research_question`;
- `task`;
- `dataset`;
- `target`;
- `feature_set`;
- `model`;
- `split`;
- `metrics`;
- `status`;
- `result_path`;
- `model_path`;
- `figure_path`;
- `run_id`;
- `dataset_version`;
- `feature_version`;
- `pipeline_version`;
- `config_hash`;
- `random_state`;
- `n_train`;
- `n_val`;
- `n_test`;
- `chronology_grade`.

Statuses:
- planned;
- running;
- completed;
- failed;
- resource_limited;
- blocked;
- stale.

Không gán score giả cho failed.

---

# 36. Experiment Execution Order

```text
Data validation
→ RQ1 analysis
→ RQ2 clustering
→ RQ3 baselines
→ RQ3 stronger models
→ Combat Timing comparison
→ Feature group ablation
→ Error analysis
→ Uncertainty
→ Finalization
```

---

# 37. Cloud-First Execution

Môi trường ưu tiên:
Google Colab.

Không khóa project cứng vào Colab.

Core code phải chạy Python chuẩn nếu đường dẫn/config hợp lệ.

## CPU-first
Preprocessing/EDA:
- CPU;
- RAM;
- disk throughput.

GPU:
- optional;
- chỉ model hỗ trợ và có lợi;
- không phải dependency.

---

# 38. Storage Model

## Raw
Immutable.

## Interim
Rebuildable checkpoint.

## Processed
Core processed datasets.

## Artifacts
Models, metrics, figures, registries, manifests.

Structure:

```text
storage/
├── raw/
├── interim/
├── processed/
└── artifacts/
```

---

# 39. Ephemeral vs Persistent

## Ephemeral
Runtime local disk:
- temp chunk;
- temporary sort;
- visualization cache;
- extracted files.

## Persistent
Cần giữ qua session reset:
- processed Parquet;
- expensive interim;
- metrics;
- model;
- figures;
- registry;
- manifests;
- logs.

Persistent backend configurable:
- mounted Drive;
- another mounted cloud path;
- manually exported checkpoint/release.

Raw public download không bắt buộc mount Drive.

Nếu persistent backend không được cấu hình:
- README phải cảnh báo;
- user phải export checkpoint trước khi runtime bị reset.

---

# 40. Large Data Strategy

## 40.1. Full-data engine

Recommended default:
- DuckDB/PyArrow/Parquet cho scan/join/group;
- pandas cho bảng vừa/summary/model matrices khi phù hợp.

Không yêu cầu pandas giữ toàn raw dataset trong RAM.

Backend phải abstract đủ để không phụ thuộc notebook.

## 40.2. Two-pass match processing

Pass 1:
build match metadata.

Pass 2:
player-level feature build.

## 40.3. Combat Timing
Aggregate event data sớm trước merge.

## 40.4. Historical
Không build trực tiếp từ raw chunk.

Flow:

```text
player_match_features
→ chronology validation
→ partition/sort
→ historical features
```

## 40.5. Player hash partition

Nếu cần:

\[
bucket = stable\_hash(player\_name) \bmod B
\]

Không dùng Python built-in `hash()` nếu hash seed làm kết quả thay đổi giữa process.

Dùng stable hash:
- SHA;
- xxhash với seed cố định;
- deterministic library hash.

---

# 41. Parquet Strategy

Processed datasets dùng partitioned Parquet.

Không partition mỗi player/match vì tạo quá nhiều small files.

Options:
- numbered parts;
- stable hash buckets;
- mode partitions nếu hợp lý.

Output metadata phải ghi:
- rows;
- columns;
- schema;
- parts;
- bytes;
- source version.

---

# 42. Checkpoint and Versioning

Mỗi checkpoint quan trọng có `_metadata.json`.

Version types:
- `schema_version`;
- `feature_version`;
- `pipeline_version`;
- `config_hash`.

Không chỉ:
`if file exists → load`.

Phải check metadata compatibility.

---

# 43. Dependency Invalidation

Ví dụ sửa Combat Timing:

```text
combat_timing
→ player_match_features
→ player_profile_features
→ historical_player_match_features
→ dependent RQ runs
```

Downstream artifact phải `stale`.

---

# 44. Checkpoint Manifest

`artifacts/checkpoints/checkpoint_manifest.json`

Fields:
- stage;
- status;
- version;
- config hash;
- output;
- dependencies;
- created;
- validated;
- row count.

Statuses:
- planned;
- running;
- completed;
- failed;
- stale.

---

# 45. Resume

Stage dài:
- partial checkpoints;
- deterministic chunk ID;
- progress state.

Combat Timing example:
- partial chunk state;
- progress manifest;
- final reduce.

Resume không:
- double count;
- skip chunk;
- append duplicate.

---

# 46. Cache Safety

Cache invalid nếu:
- schema changes;
- feature formula changes;
- relevant config changes;
- source checksum changes;
- upstream dependency changes.

Không dùng cache cũ chỉ vì filename giống nhau.

---

# 47. Development vs Full Mode

`mode: development`
- smoke test;
- limited rows/matches;
- code validation;
- no official result.

`mode: full`
- all valid data;
- final statistics;
- official experiments.

Cùng code path.

Không viết separate “mini pipeline” cho development.

---

# 48. Runtime Diagnostics

`00_setup.ipynb` kiểm tra:

- Python version;
- package versions;
- CPU count;
- RAM;
- disk;
- GPU;
- storage backend;
- write permission;
- checkpoint status;
- config validity.

Chunk size:
- config default;
- có thể adaptive theo RAM;
- actual value log.

---

# 49. Logging

Structured logging:

Levels:
- INFO;
- WARNING;
- ERROR.

Log:
- stage;
- start/end;
- input;
- output;
- rows in/out;
- rows removed;
- warnings;
- checkpoint;
- version;
- config hash;
- memory/disk nếu đo được.

---

# 50. Config Management

Files:

```text
configs/
├── data.yaml
├── schema.yaml
├── paths.yaml
├── preprocessing.yaml
├── features.yaml
├── eda.yaml
├── rq2.yaml
├── rq3.yaml
├── models.yaml
└── runtime.yaml
```

No research-important hard-coded parameter in notebook.

---

# 51. TBD / NULL Rule

Data-dependent values ban đầu để:

`null` / `TBD`

Examples:
- minimum_games_threshold;
- minimum_history_threshold;
- n_clusters;
- final split ratio/cutoffs;
- log transforms;
- outlier removal thresholds nếu chưa có evidence;
- final model hyperparameters.

Nếu notebook cần value chưa chốt:
- fail gracefully;
- print instruction;
- không tự đoán.

---

# 52. Random Seed

Global:
`random_state: 42` (default recommendation)

Dùng nhất quán cho:
- K-Means;
- model;
- visualization sampling;
- diagnostic sampling;
- randomized search.

Seed không thay thế versioning.

---

# 53. Reproducibility Metadata

Mỗi run lưu:

`run_metadata.json`

Bao gồm:
- run_id;
- experiment;
- dataset version;
- feature version;
- pipeline version;
- config hash;
- random seed;
- train/val/test rows;
- split definition;
- package versions;
- model params;
- chronology grade;
- hardware summary.

---

# 54. Environment Files

Initial:
`requirements.txt`

Sau khi first successful Colab setup:
- generate environment snapshot;
- optional `requirements-lock.txt`.

Không dùng unbounded “latest” cho final reproduction.

---

# 55. Final Results Manifest

`final_results_manifest.json`

Khóa:
- RQ1 official tables;
- RQ2 official run;
- S1/S2;
- P1/P2/P3;
- T0/T1;
- ablation;
- error analysis;
- figure versions.

Report/summary không dùng “whatever latest”.

---

# 56. Figure Manifest

Fields:
- figure_id;
- source_experiment;
- research_question;
- source_table;
- purpose;
- caption;
- report_ready;
- version.

---

# 57. Report Tables

`reports/tables/`

Examples:
- `data_quality_summary.csv`;
- `rq1_relationship_summary.csv`;
- `cluster_profile.csv`;
- `rq3_model_comparison.csv`;
- `combat_timing_comparison.csv`;
- `ablation_results.csv`;
- `error_analysis.csv`.

---

# 58. Notebook Architecture

Final proposed order:

```text
00_setup.ipynb
01_download_validate.ipynb
02_data_quality_and_structure.ipynb
03_build_player_match.ipynb
04_combat_timing.ipynb
05_eda.ipynb
06_rq1_analysis.ipynb
07_rq2_clustering.ipynb
08_build_historical.ipynb
09_rq3_prediction.ipynb
10_ablation_error_analysis.ipynb
11_finalize_results.ipynb
12_final_results_summary.ipynb
```

---

# 59. Notebook Responsibility

## 00_setup
- environment;
- configs;
- storage;
- runtime;
- checkpoint status.

## 01_download_validate
- public download;
- source inventory;
- checksum;
- schema report.

## 02_data_quality_and_structure
- structural EDA;
- DQ;
- chronology preliminary inspection;
- mode inspection.

## 03_build_player_match
- cleaning;
- metadata;
- behavior features;
- normalized placement;
- base player-match dataset.

## 04_combat_timing
- event aggregation;
- join audit;
- final player_match_features.

## 05_eda
- full EDA phases;
- threshold diagnostics;
- transform diagnostics.

## 06_rq1_analysis
- relationships;
- correlation;
- timing analysis;
- RQ1 table/figures.

## 07_rq2_clustering
- profile creation;
- threshold application;
- scaling;
- K diagnostics;
- clustering;
- robustness.

## 08_build_historical
- chronology grade;
- historical construction;
- history depth diagnostics.

## 09_rq3_prediction
- S1/S2;
- P1/P2/P3;
- baselines;
- model comparison;
- T0/T1.

## 10_ablation_error_analysis
- group ablation;
- error slices;
- CI/bootstrap;
- importance.

## 11_finalize_results
- validate official runs;
- lock final manifest;
- create report tables;
- figure manifest;
- consistency checks.

## 12_final_results_summary
Read-only summary:
- no preprocessing;
- no training;
- no silent run creation.

---

# 60. Notebook Precondition Checks

Mỗi notebook kiểm tra:
- config valid;
- dependencies completed;
- checkpoint compatible;
- required parameter not null;
- schema expected;
- previous stage validation passed.

Nếu fail:
- stop early;
- actionable message;
- không chạy nửa pipeline rồi fail.

---

# 61. Core Project Structure

```text
pubg_data_mining_project/
├── PUBG_RESEARCH_SPEC.md
├── README.md
├── requirements.txt
├── configs/
├── notebooks/
├── src/
│   ├── data/
│   ├── features/
│   ├── analysis/
│   ├── models/
│   ├── evaluation/
│   └── utils/
├── tests/
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
├── artifacts/
│   ├── checkpoints/
│   ├── experiments/
│   ├── manifests/
│   ├── models/
│   ├── metrics/
│   └── logs/
├── figures/
└── reports/
    ├── tables/
    └── appendix/
```

Notebook không chứa core business logic dài.

---

# 62. Recommended `src/` Modules

## `src/data/`
- `download_data.py`
- `inventory.py`
- `schema.py`
- `cleaning.py`
- `match_metadata.py`
- `io.py`
- `checkpoints.py`

## `src/features/`
- `combat.py`
- `movement.py`
- `support.py`
- `placement.py`
- `combat_timing.py`
- `historical.py`
- `profiles.py`
- `registry.py`

## `src/analysis/`
- `eda.py`
- `correlation.py`
- `mode_analysis.py`
- `rq1.py`
- `clustering.py`

## `src/models/`
- `baselines.py`
- `linear.py`
- `tree_models.py`
- `xgboost_model.py`
- `training.py`

## `src/evaluation/`
- `metrics.py`
- `bootstrap.py`
- `error_analysis.py`
- `importance.py`
- `ablation.py`

## `src/utils/`
- `config.py`
- `logging.py`
- `runtime.py`
- `hashing.py`
- `validation.py`

---

# 63. README.md Requirements

README là hướng dẫn sử dụng project.

Phải gồm:

1. Project Overview.
2. Research Questions.
3. Folder structure.
4. Cách mở/chạy trên Google Colab.
5. Thứ tự notebook.
6. Cách cấu hình data public URL.
7. Cách cấu hình persistent storage.
8. Development vs full mode.
9. Cách thay parameter.
10. Parameter nào được thay sau EDA.
11. Research rule nào không được tự thay.
12. Leakage rules không được phá.
13. Checkpoint/resume.
14. Status `stale`.
15. Dependency invalidation.
16. Cách chạy lại khi đổi Combat Timing.
17. Cách chạy lại khi đổi threshold RQ2.
18. Cách chạy lại khi đổi model config.
19. Troubleshooting:
    - RAM;
    - disk;
    - reset;
    - download fail;
    - stale checkpoint;
    - null config;
    - schema mismatch;
    - chronology fail;
    - join quality fail.
20. Cách mở `12_final_results_summary.ipynb`.

README phải có bảng:

| Muốn thay | File config | Key | Notebook cần chạy lại |
|---|---|---|---|

---

# 64. Unit Tests

Bắt buộc:

## Placement
- winner = 1;
- last = 0;
- bounds;
- N_teams invalid.

## Ratios
- bounds;
- denominator zero;
- structural missing.

## Combat Timing
- phase boundaries;
- partial aggregation;
- average via sum/count;
- first kill min;
- no-kill semantics.

## Historical
- current match excluded;
- expanding shift;
- same-day exclusion Grade B;
- stable sort;
- no future rows.

## Split
- same match same split;
- deterministic.

## Cache
- config hash invalidates;
- source hash invalidates.

---

# 65. Smoke Tests

Dùng:
- synthetic fixtures;
- small development sample.

Smoke output không phải research result.

Smoke test:
- raw parse;
- schema;
- join;
- feature formulas;
- checkpoint resume;
- historical leakage;
- model train/predict;
- artifact writing.

---

# 66. Execution Workflow — Code First, Execute Later

## Stage A — Build entire codebase
Trước full data execution:
- src;
- configs;
- notebooks;
- tests;
- checkpoint logic;
- README;
- spec.

## Stage B — Code review
Check:
- no hard-coded research threshold;
- no leakage;
- notebook thin;
- tests;
- null/TBD;
- dependency graph;
- paths.

## Stage C — Colab execution
Sau khi code hoàn chỉnh:
- open notebook in order;
- mostly Run All;
- inspect outputs;
- update only configs where data-dependent.

## Stage D — Finalize
- lock runs;
- summary notebook;
- user writes final report manually.

---

# 67. Data-Dependent Decisions — Chưa Chốt

Các giá trị sau **không được coding agent tự chốt trước khi có evidence**:

- RQ2 `minimum_games_threshold`;
- RQ3 `minimum_history_threshold`;
- K;
- median additions;
- log transform;
- actual outlier exclusions;
- overall vs mode-specific clustering;
- chronology grade;
- final feature sets;
- final model;
- hyperparameters;
- exact train/val/test boundaries;
- adaptive chunk size;
- hierarchical sample size;
- DBSCAN use;
- same-mode historical extension.

---

# 68. Decision Rules for TBD Parameters

## Minimum games
Choose from retention + stability, not outcome.

## Minimum history
Choose from history coverage/stability, not test MAE.

## K
Choose from unsupervised metrics + stability + interpretability, no outcome.

## Log transform
Use skewness/outlier diagnosis + validation impact, fit/decision on development only.

## Outlier removal
Only when evidence suggests invalid/error or clearly predeclared rule.

## Mode split
Use Phase 5 EDA before RQ2/RQ3 final strategy.

---

# 69. Outlier Policy

Default:
**do not auto-delete.**

Outlier categories:
- valid extreme;
- data error;
- impossible value;
- uncertain.

Only remove:
- invalid/impossible;
- source error with evidence;
- predeclared justified rule.

Winsorization/clipping:
- not default;
- any learned threshold fit on training only;
- log.

---

# 70. Model Selection Rule

Không chỉ chọn lowest metric.

Final model assessment:

**Performance + Generalization + Interpretability + Stability + Compute Feasibility**

Có thể báo:
- best-performing model;
- interpretable baseline.

Không cần tạo một “overall winner” nếu mục tiêu nghiên cứu khác nhau.

---

# 71. Report Architecture

Người dùng tự viết report sau.

Khung đề xuất:

1. Introduction
2. Related Work
3. Dataset
4. Preprocessing
5. EDA
6. RQ1
7. RQ2
8. RQ3
9. Combat Timing Contribution
10. Feature Importance + Ablation
11. Error Analysis
12. Discussion
13. Limitations
14. Conclusion
15. Appendix

---

# 72. Final Summary Notebook

`12_final_results_summary.ipynb`

Sections:

1. Dataset Summary
2. Data Quality Summary
3. RQ1 Results
4. RQ2 Results
5. RQ3 Survival
6. RQ3 Placement
7. Combat Timing T0/T1
8. Ablation
9. Error Analysis
10. Uncertainty
11. Key Findings
12. Limitations / Notes

Notebook này là nguồn chính để người dùng tự tổng hợp báo cáo.

---

# 73. Report Figure Policy

Main report:
- Report Charts.

Notebook/appendix:
- Diagnostic Charts.

Figure chỉ `report_ready=true` mới xuất trong summary official.

---

# 74. Scientific Interpretation Rules

Không viết:
- “walking causes survival”;
- “early kills make players win”;
- “cluster X is objectively the best playstyle”.

Viết:
- “walk distance is positively associated…”;
- “players in cluster X show higher observed…”;
- “Combat Timing provides incremental predictive information…” nếu T1 comparison hỗ trợ.

---

# 75. Limitations to Report

At least:

- post-match/retrospective features;
- observational data;
- survival-derived feature coupling;
- match-duration proxy;
- player_name identity limitation;
- event join mismatch;
- chronology granularity;
- same-day order if Grade B;
- repeated team outcome across player rows;
- clustering representation dependence;
- K sensitivity;
- Colab resource constraints;
- source dataset age/version;
- lack of unobserved gameplay variables.

---

# 76. Literature Use

Three core papers:

1. Dehpanah et al. — behavioral signals / historical behavior.
2. Lee & Lee — factors influencing rank, mode analysis, VIF/importance.
3. Ghazali et al. — placement prediction, feature selection/model comparison.

Use literature to:
- motivate;
- compare method;
- discuss result.

Do not copy metric directly across different dataset/split/target as if comparable.

---

# 77. Scope Exclusions

Unless later explicitly added:

- no Association Rule Mining core deliverable;
- no full spatial hotspot research;
- no Elo/Glicko/TrueSkill core baseline;
- no NDCG core metric;
- no deep neural network requirement;
- no survival-analysis censoring model;
- no causal claim;
- no classification requirement.

---

# 78. Security / Privacy / Data Handling

- không commit token/cookie;
- public URLs trong config có thể commit nếu thực sự public;
- secrets dùng environment variable;
- không đưa danh sách player names vào public report nếu không cần;
- raw data không bắt buộc commit Git;
- large artifact không commit Git.

---

# 79. Code Quality Requirements

- type hints cho core function khi hợp lý;
- docstring;
- deterministic paths;
- no duplicated formulas giữa notebook/src;
- one canonical implementation per feature;
- explicit exceptions;
- no silent fallback làm đổi research meaning;
- clear logs;
- tests cho leakage-critical logic.

---

# 80. Definition of Done — Research Design

Design complete khi:
- RQ rõ;
- target rõ;
- unit rõ;
- feature rules rõ;
- leakage rules rõ;
- experiment matrix rõ;
- EDA rõ;
- cloud architecture rõ;
- checkpoint/reproducibility rõ;
- data-dependent TBD được đánh dấu.

**Trạng thái hiện tại: đạt.**

---

# 81. Definition of Done — Implementation

Implementation complete trước full execution khi:

- tất cả module tồn tại;
- notebook tồn tại;
- config tồn tại;
- README tồn tại;
- tests pass trên synthetic/development fixture;
- precondition checks hoạt động;
- no hard-coded TBD;
- checkpoint metadata hoạt động;
- full mode path tồn tại;
- final summary notebook không train.

---

# 82. Definition of Done — Full Run

Full run complete khi:

- mọi raw shard đã inventory;
- processed full valid data;
- DQ report hoàn thành;
- RQ1 complete;
- RQ2 complete hoặc limitation rõ;
- RQ3 complete theo chronology grade;
- official experiment rows locked;
- error analysis;
- final manifests;
- summary notebook render được;
- không có official metric từ development sample.

---

# 83. Exit Criteria per Notebook

## 00
Environment/config/storage healthy.

## 01
All sources verified + schema contract result.

## 02
DQ + structural EDA complete, no unresolved critical schema error.

## 03
Base player-match dataset validated.

## 04
Combat Timing built, join audit complete.

## 05
EDA complete; data-dependent decisions required for RQ2/RQ3 ready.

## 06
RQ1 tables/figures generated.

## 07
RQ2 cluster run + robustness + outcome profiling generated.

## 08
Chronology grade assigned; historical dataset built or blocked.

## 09
RQ3 official candidate runs completed.

## 10
Ablation/error/importance/CI complete for selected runs.

## 11
Final runs locked; tables/figures manifest created.

## 12
Summary notebook loads only official artifacts successfully.

---

# 84. Audit Checks Before Running on Colab

Coding agent/reviewer must answer YES:

- Does every feature formula exist once?
- Does survival feature registry block rate features?
- Does RQ1 block target-derived association?
- Does historical Grade B exclude same-day matches?
- Are all match rows grouped in same split?
- Does clustering exclude outcome?
- Is K chosen without outcome?
- Are threshold choices independent of final test?
- Does Combat Timing aggregate correctly across chunks?
- Can cache become stale when formula changes?
- Can failed experiment remain failed without fake metric?
- Does full mode use all eligible data?
- Can Colab resume after reset?
- Does README tell user exactly what to change?
- Does final summary avoid retraining?

Nếu một câu trả lời là NO → implementation chưa sẵn sàng.

---

# 85. Suggested Config Skeletons

## `configs/data.yaml`

```yaml
source:
  dataset_name: "PUBG Match Deaths and Statistics"
  dataset_slug: "skihikingkevin/pubg-match-deaths"
  archive_url: null
  agg_urls: []
  kill_urls: []
  expected_checksums: {}

discovery:
  agg_patterns:
    - "agg_match_stats*.csv"
  kill_patterns:
    - "kill_match_stats*.csv"
```

## `configs/runtime.yaml`

```yaml
mode: development
random_state: 42
chunk_size: null
storage_backend: local
resume: true
```

## `configs/rq2.yaml`

```yaml
minimum_games_threshold: null
profile_level: auto
n_clusters: null
algorithm: kmeans
scaler: standard
hierarchical_validation: true
include_games_played_in_main: false
```

## `configs/rq3.yaml`

```yaml
minimum_history_threshold: null
chronology_required_for_historical: true
split:
  strategy: auto
  train_ratio: null
  validation_ratio: null
  test_ratio: null
```

## `configs/features.yaml`

```yaml
combat_timing:
  enabled: true
  early_cutoff: 0.3333333333
  mid_cutoff: 0.6666666667

transforms:
  log_transform_features: []

feature_versions:
  schema_version: 1
  feature_version: 1
  pipeline_version: 1
```

---

# 86. Coding-Agent Instructions

Coding agent MUST:

1. đọc toàn bộ file này;
2. không tự thay RQ;
3. không tự thêm extension vào core;
4. không hard-code TBD;
5. tạo plan trước implementation nếu được yêu cầu;
6. giữ core logic trong `src/`;
7. notebook chỉ gọi function + visualize;
8. viết tests trước/đồng thời cho leakage-critical code;
9. đảm bảo `development` và `full` cùng code path;
10. làm fail-fast thay vì silent correction;
11. sinh README usage guide;
12. không chạy full data nếu user chỉ yêu cầu code;
13. không gọi result thật nếu chưa chạy;
14. không điền metric giả;
15. không sửa raw;
16. log mọi removal/invalid/stale;
17. preserve full-data policy;
18. preserve chronology rule;
19. preserve current-vs-historical distinction;
20. tạo finalization + summary notebooks.

---

# 87. Final Canonical Workflow

```text
RESEARCH SPEC
      ↓
FULL CODEBASE IMPLEMENTATION
      ↓
STATIC REVIEW + UNIT/SMOKE TESTS
      ↓
GOOGLE COLAB
      ↓
00 Setup
      ↓
01 Download + Validate
      ↓
02 Data Quality + Structural EDA
      ↓
03 Build Player-Match Base
      ↓
04 Combat Timing + Final Player-Match
      ↓
05 Full EDA
      ↓
06 RQ1
      ↓
07 RQ2
      ↓
08 Historical Build
      ↓
09 RQ3
      ↓
10 Ablation + Error + Uncertainty
      ↓
11 Finalize Official Results
      ↓
12 Final Results Summary
      ↓
USER WRITES REPORT
```

---

# 88. Final Status

## Đã chốt
- problem;
- 3 RQ;
- full-data policy;
- Combat Timing;
- player profile design;
- historical architecture;
- leakage rules;
- EDA;
- visualization;
- clustering;
- RQ3 experiment matrix;
- feature selection;
- evaluation;
- error analysis;
- cloud-first;
- checkpoint;
- versioning;
- logging;
- reproducibility;
- notebook architecture;
- final summary workflow;
- README requirements;
- code-first execution.

## Chờ data
- source public URL;
- exact schema;
- chronology grade;
- mode strategy;
- RQ2 threshold;
- RQ3 history threshold;
- K;
- transforms;
- outlier decisions;
- final features;
- final models;
- hyperparameters;
- exact split cutoffs;
- final report findings.

---

# 89. Kết luận của bản audit

Thiết kế hiện tại đủ trưởng thành để chuyển sang implementation.

Rủi ro lớn nhất không còn là “thiếu mô hình”, mà là:
1. chronology không đủ tốt;
2. target-derived feature bị diễn giải sai;
3. mode confounding trong RQ2;
4. event join mismatch;
5. full-data resource limits;
6. cache/stale artifact;
7. accidental reuse of old plan;
8. final test bị dùng để ra quyết định;
9. summary/report lấy nhầm run.

Các quy tắc trong version 3.0 đã bổ sung guardrail cho chín rủi ro này.

**Bước tiếp theo:** dùng tài liệu này làm input chính thức để Codex/Claude triển khai toàn bộ project theo workflow `code-first, execute-later`.
