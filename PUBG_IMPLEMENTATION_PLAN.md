# Kế hoạch duy nhất — PUBG: dự đoán thứ hạng đội còn sống tại mốc t

Phiên bản nghiên cứu: **3.3**. Hợp nhất tài liệu: **21/10/2026**.

Đây là nguồn quyết định duy nhất cho đặc tả, quy trình, checklist, vận hành và nhật ký của dự án. Đọc file này trước khi sửa code. Các kế hoạch hồi cứu, ma trận S/P và các dấu tích nghiệm thu cũ không áp dụng cho pipeline mới. Source còn lại phải được đối chiếu trước khi tái sử dụng. Người dùng đang chủ động xóa cấu trúc cũ; configs/notebooks/tests/scripts hiện không còn trong workspace. INV-01 phải kiểm kê phần còn lại và phần cần dựng lại, không giả định các thư mục đã tồn tại. Tài liệu không chứng nhận pipeline đã triển khai.

> Câu hỏi: **Biết diễn biến đến phút t, đội còn sống sẽ về hạng mấy?**

Một dòng là `(match_id, team_id, t_seconds)`, chỉ gồm đội còn sống sau các sự kiện đến t. Hồi quy `normalized_placement` trong nhóm còn sống; so thêm phương pháp ranking. Mốc5/10/15/20 phút là đề xuất, chờ audit dữ liệu. Không dùng tổng thống kê cuối trận làm input.

Nguồn dự kiến: Kaggle PUBG Match Deaths and Statistics, `skihikingkevin/pubg-match-deaths`, hai nhóm shard `agg_match_stats*.csv` và `kill_match_stats*.csv`. Số player-match thật và độ đầy đủ events chưa được xác minh trong đợt thiết kế. Các mốc count cũ không thay COUNT/source audit mới.

Điều hướng: [Hợp đồng nghiên cứu](#research-contract), [Quy tắc làm việc](#working-rules), [Checklist triển khai](#implementation), [Drive và bàn giao](#operations), [Nhật ký](#journal).

<a id="research-contract"></a>
<a id="snapshot-prediction-contract"></a>
<a id="placement-duckdb-contract"></a>

# 1. Hợp đồng nghiên cứu hiện hành

## A. Đơn vị, target và thời điểm dự đoán

- Khóa duy nhất `(match_id, team_id, t_seconds)`. Đơn vị huấn luyện/đánh giá là đội tại mốc t, không nhân bản target theo player. Mốc đề xuất [5,10,15,20] phút, **chưa chốt** trước audit duration/coverage; xác minh event time và đổi phút sang giây đúng một lần.
- Snapshot là trạng thái **sau tất cả sự kiện time <= t**. Người chơi chết đúng t không còn sống; đội chỉ còn sống nếu còn ít nhất một thành viên sống. Gom xử lý các sự kiện cùng timestamp; không xếp thứ tự tùy file để suy ai còn sống.
- Chỉ tạo supervised snapshot khi trận còn diễn ra, roster/event coverage đủ và `N_alive_teams(t)>1`. Trận đã kết thúc hoặc chỉ còn một đội: lưu lý do/count ở bảng riêng, không chia cho 0, không thêm mẫu dễ đoán vào metric chính. Đội đã bị loại trước/đúng t không thuộc prediction cohort.
- Với thứ hạng cuối r của đội còn sống và N=N_alive_teams(t), target `normalized_placement = 1-(r-1)/(N-1)`. Target version phải đổi, không reuse target cùng tên v3.2. Chỉ hợp lệ nếu các đội sống chiếm đúng các hạng 1..N theo luật/rank dữ liệu đã xác minh; không renumber nhãn, clip hoặc đổi mẫu số để che thiếu roster/death.
- Winner=1, đội xếp cuối trong nhóm còn sống=0. Target chỉ join sau khi dựng X; rank cuối và mọi descendant chỉ trong label/audit sidecar. `N_alive_teams` phải tính từ roster + death events đến t, không từ placement hoặc survival tổng trận.
- Query dùng full-match outcome để audit tính hợp lệ không biến outcome thành feature: lưu receipt ở audit riêng. Report nêu rõ kết quả có điều kiện trên cohort event-complete được kiểm hồi cứu; suy luận thực tế cần feed đầy đủ, thiếu feed phải báo unavailable.

## B. Nguồn và tiền xử lý Parquet + DuckDB

- Chạy COUNT thật player-match staging, roster hợp lệ, events, match/team và snapshots theo t/mode; không gọi 65 triệu events là player-match. `DESCRIBE` schema thật và kiểm units/aliases trước xây SQL. Schema config chỉ là khai báo, không là bằng chứng raw có đủ cột.
- CSV → typed/projected Parquet nén theo source/schema/projection signature, audit parse/duplicates trước projection, raw bất biến. **Giữ date** raw và parsed timestamp/day/chronology grade. Roster giữ match/player/team, party_size/game_size/mode và metadata được xác minh biết trước/tại t. Placement và thống kê cuối trận lưu riêng cho label/QA/history của các trận trước, không vào current X.
- Event staging giữ event identity/lineage, match, time, killer/victim, cause, map và tọa độ nếu thật có. `killer_placement`, `victim_placement` hoặc alias outcome chỉ được giữ ở audit riêng, không đưa vào feature projection. ID là string; kiểm blank/parse/finite/range, không bỏ lỗi parser ngầm.
- Death ledger phục vụ trạng thái sống phải gồm **mọi nguyên nhân chết hợp lệ**, kể cả môi trường, suicide, killer thiếu, team kill. Không dùng eligibility credited-killer non-self của kill feature để lọc death ledger. Roster join riêng cho killer và victim; kiểm unmatched/ambiguous, duplicate/replay, nhiều death/player, respawn/revive semantics. Nếu không xác minh được phiên bản game không respawn hoặc death thực sự là elimination thì chặn reconstruction; DBNO không phải death.
- Đội bị loại tại max death_time của toàn bộ thành viên khi tất cả đã chết hợp lệ; thành viên không có death event chỉ được xem còn sống khi event-completeness gate đã đạt. Không lấy max các death quan sát của một roster thiếu làm thời điểm loại đội. Winner có thể không có death của người sống cuối; không ép mọi người phải chết.
- Audit coverage theo match/mode/shard: roster resolution, victim uniqueness, tổng death phù hợp số người sống cuối nếu có nguồn kiểm độc lập, kill-counter consistency chỉ dùng QA, elimination-order vs final rank, nhóm cùng timestamp/tied placement, duration evidence. Thời điểm loại sớm hơn phải ứng với hạng kém hơn trong các cặp không tie. Kiểm hạng 1..N tại từng t; đối chiếu thứ tự chỉ là điều kiện cần, không chứng minh ledger đầy đủ.
- Loại **toàn trận** thiếu roster/target sai hoặc không thể xác minh trạng thái sống đáng tin; giữ reason/retention. “Lệch nhiều” cần ngưỡng/tie-policy có bằng chứng và quyết định trước model selection; chưa có ngưỡng thì pending, không tự đặt phần trăm. Rule áp đồng nhất train/test và báo selection bias của cohort lọc theo audit outcome.
- Dựng snapshots bằng SQL trên event `time<=t`, aggregate theo đội rồi lọc alive; đội sống không có event vẫn giữ bằng LEFT JOIN roster. Sau đó relative windows chỉ trong `(match_id,t)` trên đội sống; cuối cùng join labels. Cache theo grid/coverage/feature/source version; aggregate toàn trận v3.2 không đủ để tạo snapshots.
- Dữ liệu có thể lớn theo số mốc nhưng không đúng bằng roster nhân T do đội bị loại. Scan/spill DuckDB, chỉ pandas trên mẫu đủ RAM. Budget khởi điểm10GB trên máy16GB, local scratch, benchmark cả disk/RAM/VRAM; không bảo đảm vừa RAM. Drive/root/require-existing/batch50000 giữ nguyên. Hết tài nguyên giữ checkpoint, `resource_limited`, không silent sample/CPU fallback.

## C. Feature allowlist và Combat Timing mới

| Nhóm | Input tại t | Quy tắc |
|---|---|---|
| S: sống sót/context | n_alive_members, deaths_to_t, N_alive_teams, party_size, game_size, map, t | Roster/metadata đã biết và death ledger prefix; game_size semantics phải kiểm, không tự gọi số đội |
| C: giao tranh | kills_to_t, first_kill_time_to_t, avg_kill_time_to_t, has_kill_to_t | SUM/COUNT/MIN prefix, credited-killer non-self đã chốt; không tự gọi enemy-only |
| P: vị trí | tọa độ sự kiện gần nhất có vai trò killer/victim của đội, tuổi của quan sát, khoảng cách tâm bản đồ | Chỉ event<=t; chọn role đúng, tie cùng timestamp bằng rule xác định; không đại diện vị trí liên tục hoặc tâm vòng bo |
| R: tương đối | rank/z-score của S/C/P hợp lệ giữa các đội sống | Window(match,t), non-NULL, rank ties nhất quán; std=0/valid N<2 → NULL |
| H: kỹ năng trước trận (optional) | số trận trước, kill/rank trung bình trước đó, coverage/history depth | Chỉ trận đã có outcome trước trận hiện tại; Grade B dùng date < ngày hiện tại |

- Cấm current-match full totals damage/distance/survival/kills, final placement, estimated final duration, ratios/phase dựa trên thời lượng cuối và mọi descendant; kể cả “chỉ diagnostic D” cũng không thuộc ma trận dự đoán mới. Metadata sau trận chỉ dùng nếu semantics chứng minh chính là thông tin sẵn có trước/tại t.
- No-event với feed đã xác minh đủ: count=0, first/mean time=NULL; feed thiếu/unknown: không tự fill0 hoặc suy sống. `has_kill_to_t` từ prefix kill count, không từ aggregate player_kills. Tọa độ NULL vẫn giữ cohort, impute train-only và báo coverage/map; tâm/units/map extents chưa xác minh thì distance feature blocked, không hard-code midpoint.
- Prefix invariance: thêm/sửa/xóa event sau t không đổi X/cohort sống tính từ prefix trên một roster/coverage eligibility đã khóa. Mutation placement/survival/full totals không đổi X; audit có thể đổi trạng thái eligible nhưng không điền giá trị feature từ outcome. Inference API không nhận final labels hoặc future events.
- H trước hết đếm repeated players, phân phối số trận/người và strict-past coverage theo mode/ngày; tên không phải định danh tài khoản chắc chắn. Thiếu history vẫn giữ đội bằng missing/coverage indicators; ngưỡng nếu cần phải quyết định từ evidence, không ngầm dùng default. Optional H không chặn core S/C/P/R.
- Với random-group CV, H được dựng **fold-local** từ lịch sử có outcome của training matches sớm hơn; không lấy outcome validation/test để dựng training hoặc validation features. Frozen-history policy ở holdout; không update bằng test labels. Temporal protocol cũng chỉ dùng history train đã sẵn sàng. Nếu sau này dùng online update phải là protocol riêng được chốt.
- RQ mới: **Tại cùng t và cùng đội còn sống, nhóm feature giao tranh bổ sung bao nhiêu giá trị dự đoán ngoài sống sót/context?** T0=S; T1=S+C. Ablation S/C/P/R/H và dependency closure; bỏ C phải bỏ cả relative C, không để descendant sót lại. So cùng snapshot IDs/folds, không bỏ đội thiếu P/H làm cohort co khác nhau.

## D. Split, sampling và chronology

- Mọi snapshot của cùng match, ở mọi t, nằm chung split/fold; query ranking là (match,t) nhưng **CV group vẫn match_id**. Hash chính giữ train80/test20: md5_number_lower('split:v1:42:'||match_id)%100 <80 là train; lưu assignments/checksum. Null IDs bị chặn; test sealed, không sample test.
- Bắt đầu 5–10% số trận **chỉ trong train**, phân tầng match_mode; khởi điểm kế hoạch5%, khóa actual fraction/budget trước run, mở rộng theo learning curve. Order độc lập md5_number_lower('sample:v1:42:'||match_id), tie match_id; ceil(p*N_mode). Giữ tất cả snapshot hợp lệ của trận được chọn. Nested5/10/20/40% train là diagnostics; cùng validation panel khi tăng training size, không đưa holdout fold vào train.
- Broad shared5 StratifiedGroupKFold strata match_mode trên match manifest; tune GroupKFold3, groups match_id; OOF/meta/early-stop cũng nhóm match. Nếu mode/t thiếu support, báo blocked comparison thay vì đổi seed/số fold âm thầm. Transform/imputer/scaler/encoding fit từng fold; Ridge log1p chỉ feature không âm đã đăng ký.
- Thêm **temporal sensitivity trong train pool** để không mở test chính lần hai: development trận sớm train, trận muộn validation; boundary ngày/timestamp và khoảng gap/availability chốt từ chronology audit trước xem score. Không tách cùng match hoặc cùng ngày khi chỉ có date. Cùng bản ghi split/scope riêng; không gọi temporal development validation là final future test.
- Nếu muốn temporal test chính thức thay hash test hoặc holdout tương lai thứ hai, cần chốt protocol/cutoff riêng trước G4; không lấy điểm hash-test để quyết định đổi. Date không đáng tin → temporal/H blocked có lý do, vẫn báo hạn chế của random-group generalization. Ngày là metadata grouping/history, không tự đưa làm predictor.

## E. Baseline, metric và cách tổng hợp

- Baseline bắt buộc: xếp đội trong (match,t) theo n_alive_members giảm dần, rồi kills_to_t giảm dần. Ties dùng average rank cho output liên tục `1-(pred_rank-1)/(N-1)`; chọn top-k cần tie-break hash team ID/salt cố định độc lập labels. Giữ mean/median học fold-train tại từng t làm baseline phụ. Không dùng final rank để phá ties.
- MAE chính, RMSE/R² phụ **trên team snapshots riêng từng t**; mỗi đội một trọng số trong t, R² undefined nếu n<2/SST=0. Báo fold mean/std ddof1 và pooled OOF riêng. Scalar selection khai báo là mean_t(MAE_t), equal weight trên grid đã khóa, rồi mean giữa folds; không pooled row MAE khiến t sớm đông đội lấn át t muộn. Thiếu một t đã đăng ký phải báo, không tự bỏ t để cải thiện scalar.
- Đồ thị chính MAE(t) của model và baseline kèm CI, số matches/teams, N_alive distribution và coverage. MAE giảm theo t là **giả thuyết**, không ép đường cong đơn điệu: cohort sống và thang chuẩn hóa thay đổi. Báo thêm common-match sensitivity (các trận có đủ mốc) với survivor bias; không suy “đoán được từ phút X” chỉ từ độ dốc nếu chưa định nghĩa ngưỡng chất lượng.
- Spearman từng (match,t) giữa prediction lớn=tốt và y lớn=tốt, average ranks cho ties; macro-average qua match trong từng t, constant predictions/labels hoặc thiếu mẫu → undefined kèm count, không fill0. N rất nhỏ cần báo riêng.
- Winner accuracy: top1 prediction có final rank1 hay không, random kỳ vọng 1/N. Winner-in-top3: winner có trong k=min(3,N) dự đoán hay không, random k/N. Top3 overlap: |predicted_top_k ∩ actual_top_k|/k, random k/N; báo rõ định nghĩa. Với N<=3 hai metric top3 bão hòa1, tách N>3; không gán mức random1/N cho mọi top3 metric. Random tham chiếu aggregate mean(1/N) hoặc mean(k/N) theo đúng nhóm, không 1/mean(N).
- Bootstrap95% lấy mẫu match có hoàn lại, giữ toàn bộ teams/t của match và multiplicity, cùng draws cho model-baseline và đường cong; khởi điểm500 draws seed42. CI theo t là pointwise trừ khi đăng ký simultaneous band. Slices mode, timing/position/history coverage và residual bins theo y/t đã khóa từ train.
- Chỉ tuyên bố model có giá trị thêm khi vượt baseline sống+kills trên metric đã đăng ký; báo paired delta/CI. Nếu không vượt, giữ baseline làm kết quả hợp lệ, không chọn bằng test lại.

## F. Mô hình, thí nghiệm, tune và ensemble

- Broad defaults: Ridge, ExtraTrees hoặc RandomForest (train submatches nếu budget đã khai báo, cùng validation), LightGBM, XGBoost, CatBoost và baselines. Chỉ seed/device/threads/input handling ngoại lệ defaults; log actual versions/params/GPU support. Dependencies thiếu là blocked, không tự cài.
- Thử sớm LambdaRank với query=(match,t), rows contiguous trong query, `group` là kích thước query sau mỗi fold slicing; không truyền match_id vào API group-size. Nhãn relevance nguyên N-r với label_gain tuyến tính bao phủ miền đã xác minh; không dùng y float trực tiếp. Ranker score không phải y: chuyển rank prediction trong query thành [0,1] bằng cùng rule baseline để chấm MAE. Đây là transformation bắt buộc của ranker, không dùng true rank. Objective ranking khác regression; vẫn chọn bằng MAE đã đăng ký, metric ranking hỗ trợ diễn giải.
- So mô hình chung có t feature với một model/mốc, cùng t/teams/folds và ngân sách ghi rõ tổng/per-t. Với model riêng, recipe family và tổng score các t chọn trong CV; không cherry-pick từng t bằng test. Grain hiện hành chỉ team-snapshot; bỏ thí nghiệm player-vs-team cũ.
- Broad recipe S+C+P+R với P chỉ cột/schema đã kiểm, hoặc recipe khả thi được khóa trước so sánh nếu P blocked. Leader ablate theo nhóm và T0/T1 cùng cohort, tùy chọn H khi gate đạt. L2/L1/Huber chỉ backend hỗ trợ; pseudo-Huber tên riêng, LambdaRank không gắn loss hồi quy.
- Giữ top2–3; regressors tune RandomizedSearchCV mặc định40 trials trong30–50, GroupKFold3, custom negative mean_t MAE, refit=False; Optuna chỉ khi được duyệt. Param family đúng backend: learning_rate, leaves/depth, child controls, subsample/colsample, regularization; Ridge alpha. Với ranker, fold loop tái tạo contiguous query/groups và chấm normalized predictions, không dùng generic SearchCV với group-size mảng nguyên gốc. Cùng trial budget/folds/scorer.
- Rescore tuned singles shared5fold; OOF key(match,team,t). Ensemble weighted mean/Ridge meta học inner grouped OOF trong outer-train, đánh giá outer-holdout; không fit/chấm meta cùng OOF. Dùng outputs cùng thang y, ranker đã transform. Giữ ensemble khi mean paired improvement > std fold primary score best single(ddof1), không gọi ngưỡng này là significance test.
- Rank postprocess cho regressors là optional chọn trong CV theo query (match,t), ties average; không gom mọi t cùng match. Tất cả choices CV có selection optimism, không gọi nested tuning unbiased. Mô hình cuối có thể là baseline nếu learners không cải thiện.

## G. Refit, đánh giá một lần, giải thích và đóng gói

- G4 khóa grid, eligibility, feature/history/tie rules, shared/per-t strategy, winner, preprocessing, objective/ensemble/postprocess, sample/folds, refit budget, score/slices, temporal scope và test-access receipt. Refit lớn hơn trong train nếu máy cho phép, exact fraction/N được báo, không gọi sampled fit full-data.
- Một final evaluation episode trên toàn eligible heldout20% matches ở các mốc đã khóa; final predictor/collection theo t + baselines đăng ký trước. Inference batch giữ đủ query để rank, ghi predictions; bootstrap/slices đọc lại saved predictions, không retrain/chọn model qua test. Test exposure/resume phải có receipt; không giấu lần đọc lỗi.
- Permutation importance trên development với cùng scorer và đơn vị nhóm phù hợp; nếu hoán vị source feature phải xử lý relative descendants nhất quán hoặc ghi rõ chỉ là column diagnostic. SHAP background train, explain development có budget; nói rõ ranker raw score khác y/rank transform. Không dùng test để chọn feature hoặc suy nhân quả.
- Joblib pipeline/model hoặc collection theo t + native state cần thiết, khóa version và feature/query/time schema, event-to-snapshot contract, baseline/tie/rank transforms; inference smoke chỉ roster + event prefix + history được phép, không cần final outcomes. Datasheet actual counts/coverage/retention/split, model card per-t metrics, nhật ký thí nghiệm và manifest.
- Limitations: snapshot cũ/game drift, death-feed thiếu, tọa độ chỉ tại event, không có telemetry damage/movement prefix, tên player không chắc identity, survivor/cohort selection, chronology và phụ thuộc outcomes giữa t. In-match forecasting trên snapshot lịch sử chưa là bằng chứng triển khai realtime.

## H. Quyết định còn chờ dữ liệu và nghiệm thu

Chưa chốt: grid t chính thức; duration/end-of-match semantics; khả năng xác minh event completeness; tie/discordance exclusion threshold; map geometry; chronology cutoff/gap; optional history coverage/threshold. Giá trị chưa có bằng chứng giữ null/pending và chặn consumer tương ứng; không tự biến [5,10,15,20] thành grid chính thức. Không thể kết luận feasibility từ schema config hoặc test giả.

Tài liệu kỹ thuật để triển khai: [LightGBM ranking groups](https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMRanker.html), [integer relevance và label_gain](https://lightgbm.readthedocs.io/en/stable/Parameters.html#label_gain), [Spearman undefined/constant input](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html). Cần kiểm API/version thực tế; chưa có bằng chứng runtime.

<a id="working-rules"></a>

# 2. Quy tắc thực hiện và nghiệm thu

- Chỉ duy trì file Markdown này; bổ sung quy tắc, quyết định, evidence và nhật ký tại đây. Báo cáo máy sinh dùng artifact JSON/CSV/Parquet/HTML/PNG phù hợp; không tạo kế hoạch hoặc hướng dẫn Markdown song song.
- Giải thích bằng tiếng Việt, thay đổi nhỏ, kiểm code/caller/config trước sửa. Không tự thêm dependency: đọc requirements hiện có, xin quyết định khi cần thêm. Không commit/push, reset hoặc sửa/xóa raw, checkpoint hợp lệ ngoài yêu cầu được giao.
- Làm giai đoạn0→15 để đạt G0, rồi giai đoạn16 chạy thật. Bắt đầu tại INV-01, làm task mở theo thứ tự. Mỗi lượt triển khai một giai đoạn; báo bàn giao rồi dừng. Đợt hợp nhất tài liệu không nghiệm thu triển khai hoặc reset trạng thái của kết quả nghiên cứu trên đĩa.
- Checklist dưới đây là checklist chuyển đổi v3.3, thay checklist nhiều protocol cũ. Mọi task chưa có bằng chứng v3.3 giữ `[ ]`; không suy code cần viết lại chỉ vì chưa nghiệm thu. Tái sử dụng code đúng và kiểm chứng, không bê dấu tích cũ sang.
- Mỗi task phải kiểm logic, tích hợp notebook cùng code path và khả năng đọc output. Khi sửa src/generator, sinh lại đúng notebook bị ảnh hưởng; bảo toàn outputs hợp lệ. Không chạy hoặc sinh lại All-in-One.
- Chỉ tích từng task sau khi đủ evidence: file/hàm, cell ID/tiêu đề, lệnh thực chạy, scope/fixture, expected/actual, output/report path và giới hạn. Bảng/hình cần title, đơn vị, mode/t/N, missing semantics, nguồn, caption và hướng dẫn đọc.
- Không tạo predictions từ target, placeholder metrics, completed checkpoint rỗng, hard-code official run IDs, default ngầm cho quyết định null. `blocked`, `resource_limited`, `failed`, `stale` có reason; skipped/CPU mock/fixture không là full-data/GPU/Drive evidence.
- Artifact publish an toàn và read-back trước commit; chỉ reuse completed tương thích code/config/data/schema/recipe. Fixture namespace riêng. Không xóa bản tốt trước khi bản mới xác minh; một writer/stage, release đã khóa bất biến.
- Dừng đúng consumer nếu thiếu quyết định nghiên cứu, coverage/chronology không đủ, kết quả mâu thuẫn manifest/plan, không đủ evidence hoặc hết tài nguyên/quyền. Làm phần độc lập được phép, không tự giảm phạm vi hay đổi estimator/device để che blocker.
- Sau mỗi đợt: nối nhật ký trong mục5; báo task nghiệm thu, file sửa, tests, notebook output đã xem, artifacts, mục còn mở và lý do. Handoff tới giai đoạn tiếp cần quyền theo quy tắc trên.

| Gate | Điều kiện |
|---|---|
| G0 | Code/config/notebooks/tests cho recipe hiện hành sẵn sàng qua fixture; chưa chứng nhận dữ liệu thật |
| G1 | Source/schema/units/checksum đầy đủ, lỗi critical được xử lý |
| G2 | Roster/death coverage/cohort/target/split và grid quyết định hợp lệ, manifests khóa |
| G3 | Feature/history/chronology decisions đủ evidence, các nhánh pending có trạng thái đúng |
| G4 | Chọn bằng development CV, khóa winner/grid/recipe/refit/scorer/slices/test access trước mở test |
| G5 | Required artifacts/actual runs compatible, metrics truy nguồn, immutable release và summary hợp lệ |

Chỉ dùng G0–G5. Optional H có thể blocked trong khi core event-only tiếp tục. RQ2 per_mode là nhánh cũ ngoài core forecasting: giữ source/artifact, không tự chạy/xóa hoặc tuyên bố hoàn thành; nếu đưa vào release phải chốt scope và tiêu chí riêng trước consumer.

<a id="implementation"></a>

# 3. Checklist chuyển đổi v3.3

Trạng thái: chưa nghiệm thu snapshot pipeline. Các mã chuyển đổi được giữ để truy vết; không mang checklist của bài hồi cứu vào file này. Giai đoạn03 chuẩn bị roster/labels,04 mới finalize snapshots, tránh dependency cycle.

## Giai đoạn 0. Kiểm kê và chốt phạm vi

- [ ] INV-01: Tái kiểm kê v3.3 team-snapshot forecasting: đọc đặc tả/kế hoạch/nhật ký, baseline và consumer map grain/target/date/prefix/death coverage/scorer/ranking/history; ghi quyết định còn pending grid/duration/ties/coverage/temporal scope, giữ nhánh cũ/provenance. Chỉ nghiệm thu khi scope và dependency rõ, không tự chốt ngưỡng thiếu data.

## Giai đoạn 1. Hạ tầng, registry và checkpoint

- [ ] INF-30: Nối v3.3 vào registry/config/signatures: key(match,team,t), target version, prefix/coverage/grid/date/history rules, query/fold/sample/temporal/test receipts. Chặn reuse artifact hồi cứu v3.2 và dependency cycles03/04; crash/resume/stale tests, không thêm dependency chưa duyệt.

## Giai đoạn 2. Notebook00 — Môi trường

- [ ] ENV-SNAPSHOT: Kiểm storage/root/require-existing/batch50000, package/version/device và budget RAM/disk/VRAM/local scratch; băm file kế hoạch duy nhất, source/config/generator; notebook fixture render environment/checkpoint/blocked decisions. Không cài package chưa được duyệt hoặc coi GPU routing là GPU thật.

## Giai đoạn 3. Notebook01 — Ingest và schema

- [ ] NB01-15: DuckDB CSV→typed/projected Parquet ZSTD theo source/schema signature; giữ date raw/parsed, audit cột event placement và loại khỏi feature view. DESCRIBE/schema/count/units/coordinate metadata và parser ledger; fixture quoted newline/leading-zero IDs/row khác date/replay/resume, notebook output thật từ fixture, không suy schema thực từ config.

## Giai đoạn 4. Notebook02 — Roster, coverage, split

- [ ] NB02-23: Roster/DQ whole-match exclusions rồi hash train80/test20 manifest; mọi t cùng match cùng split. Sample5–10% chỉ train, kế hoạch5%, stratified match_mode digest order; nested5/10/20/40% train, test không sample. Fixture null/shuffle/isolation/nesting; render counts/scopes và không đổi budget sau OOM.
- [ ] NB02-24: Handoff COUNT thật player-match/events/roster riêng; coverage/duration/chronology và retained matches/teams theo t/mode. Duration proxy không tự coi end time. Fixture count/retention tables, raw counts tại RUN; không đặt grid hoặc event completeness từ dữ liệu giả.
- [ ] NB02-25: Audit feasibility snapshot trên dữ liệu thật tại RUN và cơ chế trên fixture tại02: roster completeness, all-cause death identity/coverage, elimination-order/ties vs labels, duration/grid retention, map geometry và chronology. Lưu pending decisions không default; temporal boundary trong train pool, optional H coverage gate. Output notebook phân biệt evidence đủ/chưa đủ, không tự nhận event-complete từ rank consistency.

## Giai đoạn 5. Notebook03 — Roster/labels và target contract

- [ ] NB03-16: Chuẩn bị roster/static metadata và label/audit sidecars cho04, target formula snapshot1-(r-1)/(N_alive-1) chỉ N_alive>1/range hợp lệ. Cấm full totals/outcome descendants trong X; finalize sau prefix ledger04, không tạo dependency cycle. Fixture oracle winner/last/singleton/rank conflict và label mutation isolation, output notebook rõ availability.

## Giai đoạn 6. Notebook04 — Death ledger và snapshots

- [ ] NB04-19: Dựng all-cause death ledger, kill credited-nonself và position actor ledger riêng; xác minh coverage/roster trước suy alive. Aggregate time<=t cho team, window relative(match,t), LEFT JOIN giữ no-event teams; labels join cuối. Test death đúng t/ties/missing-victim/environment/replay/last-member/future mutation/N<=1/unknown feed; notebook hiển thị snapshot/eligibility/retention và prefix receipts.

## Giai đoạn 7. Notebook05 — EDA theo mốc t

- [ ] EDA-SNAPSHOT: Development EDA distributions/counts/coverage theo t/mode/N_alive, missing timing/position/history, target/cohort changes và duration diagnostics. Quyết định grid/threshold chỉ từ evidence theo protocol; test không mở cho lựa chọn. Notebook có source tables/figures/retention và hạn chế survivor bias.

## Giai đoạn 8. Notebook06 — Combat Timing RQ

- [ ] RQ-COMBAT: Câu hỏi S so S+C tại cùng t, cùng snapshot cohort/folds, metric team/t và paired match uncertainty. Mô tả prefix timing/missing/relative closure, không suy nhân quả hoặc dùng kết luận giả; notebook dẫn tới comparisons đã đăng ký ở09/10.

## Giai đoạn 9. Notebook07 — Cách ly nhánh clustering cũ

- [ ] SCOPE-RQ2: Kiểm dependency graph forecast không phụ thuộc clustering07; giữ source/artifact per_mode cũ, trạng thái outside_core với lý do. Không tạo completed rỗng. Nếu yêu cầu release RQ2 thì chốt scope/tiêu chí riêng trước chạy; forecast không nghiệm thu RQ2.

## Giai đoạn 10. Notebook08 — Optional history

- [ ] NB08-31: Audit repeat-player/history depth/chronology trước optional H; Grade B strict earlier-day, fold-local training-source history và frozen holdout history. Thiếu evidence ghi H blocked không chặn core S/C/P/R; fixture heldout-label mutation/same-day exclusion/no-history giữ cohort, notebook coverage/decision, không default thay null hoặc checkpoint rỗng.

## Giai đoạn 11. Notebook09 — Model selection và final test

- [ ] NB09-35: Export v3.3 team-snapshot sample/train/test, keys(match,team,t)/mode sidecar, numeric features FLOAT32/target DOUBLE, memory gate/Pipeline fold-local. Fulltest inference batch sauG4 giữ đủ query cho rank; fixture dtypes/prefix-only inputs/alignment/test-read guards.
- [ ] NB09-36: Tích hợp baseline alive-members rồi kills_to_t, mean/median phụ theo t, Ridge/ExtraTrees hoặc RF/LightGBM/XGBoost/CatBoost sau quyền dependency. Thử LambdaRank sớm, query(match,t), contiguous group sizes rebuild từng fold/integer relevance/label_gain/score-to-rank. Log defaults/version/device/support/budget; fixture predictions/reload/baseline ties, GPU thật tại RUN.
- [ ] NB09-37: Shared5 SGKF trên match manifest strata mode/groups match, mọi t cùng fold. Scorer âm mean_t MAE_t, mean/std folds, per-t MAE/RMSE/R² và ranking support; so pooled model với collection per-t cùng panels/budget. Fixture pooled-row vs equal-t weighting, t missing blocked, query-group slicing; shortlist2–3 không dùng test.
- [ ] NB09-38: Leader ablate S/C/P/R/optional H và dependency closure, T0=S/T1=S+C cùng snapshots/t/folds; bỏ A–D/player-vs-team cũ. So losses native hỗ trợ, LambdaRank riêng; learningcurve5/10/20/40% train fixed validation. Fixture missing P/H giữ cohort/availability/descendants, notebook comparisons và temporal development sensitivity theo boundary đã chốt, không test-driven cutoff.
- [ ] NB09-39: Tune2–3 với40 trials (30–50),3groupfold match, custom negative mean_t MAE/refit=False; family params đúng backend. Ranker fold loop rebuild query groups, không truyền static group-size vào generic search; earlystop chỉ fold-train, Optuna khi duyệt. Kiểm groups/scorer/budget/status, rescore shared5fold.
- [ ] NB09-40: OOF key(match,team,t), ranker output chuyển cùng thang y; weighted mean/Ridge meta học inner groupOOF outer-train, đánh outer holdout. Không fit/chấm meta cùng OOF; gate mean delta>std fold primary bestsingle. Optional regression rank trong(match,t), fixture chống trộn t/leakage và render fold deltas/weights.
- [ ] NB09-41: Chọn CV primary tốt nhất, tie đơn giản/nhanh; baseline thắng là kết quả hợp lệ. G4 khóa grid/coverage/features/shared-per-t/history/rank/scorer/temporal scope/refitbudget. Refit larger train có receipt, một final episode+baselines trên full eligible20%test ở mọi t; batch inference/testaccess/resume fixture không cho chọn lại bằng test.

## Giai đoạn 12. Notebook10 — Metrics, uncertainty, explanations

- [ ] NB10-34: Saved team-snapshot test predictions: MAE(t)/RMSE/R²/pointwiseCI95%, paired matchbootstrap giữ all t/multiplicity. Spearman/match,t, winner1/N, winner-in-top3 và top3overlap k/N, N<=3 tách riêng. Render N/coverage/mode/missing/residuals/common-match sensitivity; không ép curve giảm hoặc suy đoán-được từ slope, không test leaderboard.
- [ ] NB10-35: Permutation/SHAP development fold-train background, scope/t/mode/N/budget rõ; permutation closure hoặc column-diagnostic label, ranker SHAP rawscore khác normalized-rank output. Không test featureselection, dependencies thiếu blocked; mở notebook tables/figures và bàn giao limitations.

## Giai đoạn 13. Notebook11 — Release và đóng gói

- [ ] NB11-22: G5 khóa v3.3 snapshot eligibility/grid/prefix/chronology/sample/query/folds/history/CV/OOF/G4/refit và một test receipt, actual run IDs. Reject hồi cứu/sai target version/thiếu t, giữ immutable release; fixture stale/invalid/missing/duplicate exposure, không bắt candidates có test metrics.
- [ ] NB11-23: Joblib Pipeline/model hoặc per-t collection/ensemble + native state, environment lock, event-prefix/roster/query/time/history/tie/rank contract và no-label/no-future inference smoke. Datasheet/model card/experiment log chứa coverage/retention/per-t metrics và drift/survivor limits; fixture reload khớp predictions, không thêm dependency chưa duyệt.

## Giai đoạn 14. Notebook12 — Tổng hợp chỉ đọc

- [ ] NB12-15: Locked read-only summary12 phần theo migration v3.3: source,coverage,target,split/chronology,baselineCV,eventablation,shared-per-t/ranker,tuneensemble,finalMAEcurve,ranking/slices/explain,package,limits. Phân biệt train sample/refit/fulltest/temporal development; fixture không build/train/run và bảng/hình truy nguồn.

## Giai đoạn 15. QA và G0

- [ ] QA-28: Tái nghiệm thu v3.3 end-to-end notebook/caller/config/generator/bundle/README: date/roster/deathcoverage/prefix/snapshot/target/query/group/scorer/history/CV/tune/OOF/G4/testonce/package/summary. Không lấy G0 cũ, All-in-One hoặc fixture làm bằng chứng full-data.
- [ ] QA-29: Fixture đủ prefix mutation/label isolation, death đúng t/environment/replay/missing/respawn, singleton/rank conflict, no-kill NULL, mọi t chung matchfold, query slicing, foldlocalhistory, equal-t scorer/ranking chance/bootstrap multiplicity, OOFmeta và testaccess. Oracle độc lập; chạy notebook cùng path và xem output; fail/resource giữ checkpoint.

## Giai đoạn 16. Chạy thật Colab/Drive và bàn giao

- [ ] RUN-19: Sau G0 v3.3 và quyền chạy thật: DESCRIBE/COUNT/coverage/roster/elimination/duration/date/repeat-player evidence; chốt grid/ties/thresholds/chronology scope trước consumers. Benchmark DuckDB10GB/local scratch/máy16GB/snapshot counts/5–10% train; realDrive/GPU, không coi raw absent/synthetic là evidence.
- [ ] RUN-20: Real shared5/3fold baselines/eventablation/shared-per-t/ranker/tune/OOF/temporal development evidence trướcG4; refit locked budget và một final eligible test episode. MAE(t)/ranking/chance/CI/slices từ saved predictions, explanationsdev/model/cards/lock; exposure/resource lỗi có receipts, không rerun test chọn lại.

### Các ca kiểm thử bắt buộc khi triển khai

- Future-event mutation không đổi prefix X/alive trên eligibility cố định; đổi labels/full totals không đổi X. Audit eligibility và label table tách khỏi feature builder.
- Death đúng t, mọi event cùng timestamp, last-member death, environment/suicide/no killer, missing victim/roster, replay, multi-death/respawn; thiếu feed phải blocked, không alive-by-default.
- N_alive=1/0 không tạo training label; hạng không đúng1..N bị từ chối, không clip/renumber. Đội sống không kill vẫn có row và count0 khi coverage đủ; timing/location thiếu vẫn NULL.
- Snapshot key unique, tất cả t cùng match cùng split/fold, query group sizes đúng sau slice/reorder, không rank chung nhiều t; sample không chứa test.
- Fold-local transforms/history, same-day exclusion, heldout outcome mutation không đổi training X; history thiếu không co cohort.
- Baseline ties/oracle, mean_t MAE khác pooled row MAE, Spearman undefined và random top3 k/N; match-bootstrap multiplicity giữ mọi t.
- OOF/meta leakage guards, default-vs-tuned receipts, early-stop fold-train only; G4/read-test-once, package inference no future/no labels, stale signatures và resource failure bảo toàn checkpoint.

<a id="operations"></a>

# 4. Vận hành, artifact và bàn giao

```python
PUBG_STORAGE_MODE = "drive"
PUBG_DRIVE_PROJECT_ROOT = "/content/drive/MyDrive/PUBG_Project/Project_PUBG"
PUBG_REQUIRE_EXISTING_PROJECT = True
PUBG_BATCH_ROWS = 50000
```

Chủ project chia sẻ thư mục PUBG_Project cho thành viên với quyền chỉnh sửa; thành viên thêm shortcut vào My Drive để dùng cùng root. Kiểm thực tế cùng một file nhận diện và quyền đọc/ghi; thư mục trùng tên không chứng minh cùng project. Không tạo bản sao dữ liệu riêng hoặc mở hai writer cùng stage.

Mỗi notebook khởi tạo config/bootstrap/import riêng; RAM không truyền giữa notebooks. Cập nhật source/config/notebook đúng phiên bản rồi restart runtime. Đường dẫn output dựa trên config/manifest đã resolve, không suy từ tên file còn sót. Upload thay đúng file ID/version, không bản hậu tố số.

| Nơi lưu | Vai trò |
|---|---|
| data/raw | Raw bất biến |
| data/interim | Typed Parquet, roster/label/ledger, audits và snapshot staging |
| data/processed | Snapshot features/splits export đã xác minh |
| artifacts/manifests | Source/schema/cohort/grid/split/sample/fold/history/test-access và release receipts |
| artifacts/checkpoints | Trạng thái stage và signatures/artifact checksums |
| artifacts/models, artifacts/experiments | Pipeline/model/OOF/predictions/params/resources, exact path theo registry |
| reports/tables, figures | Bảng nguồn, metric/CI/curves và figure manifests |
| Local scratch | DuckDB spill và staging tạm; không dùng làm checkpoint bền vững |

GPU dùng khi estimator/backend hỗ trợ, lưu actual device/version/name; CPU-only estimator ghi rõ. GPU không tăng host RAM. Không đổi backend/estimator hoặc hạ mẫu ngầm khi OOM. Pipeline mới chưa có benchmark16GB hoặc xác minh Drive/GPU thật.

Khi ngắt phiên: chỉ reuse completed compatible với checksum/schema/count; fit dở phải chạy lại, local scratch có thể mất. Người nhận kiểm read-back file trên Drive, stage/cell/run/status và committed artifacts trước tiếp tục. Giữ đủ source tables/catalog cho hình, không đưa fixture vào official results. Hết tài nguyên/quyền thì ghi resource_limited/failed và bàn giao, không vượt quota.

Notebook12 chỉ đọc release được chọn rõ ràng, đủ12 phần: source/count; coverage/retention; target/availability; split/sample/chronology; baseline/CV; event ablation; shared/per-t/ranker; tune/ensemble; final MAE(t)/CI; ranking/slices/explain; package/cards; limitations. Mỗi phần có câu hỏi, bảng/hình thực, cách đọc và kết luận truy nguồn hoặc trạng thái thiếu. Không train/download/build/run mới.

Tài liệu tham khảo học thuật dùng để đặt vấn đề, không sao scores/cutoffs: Dehpanah et al.(2021) về behavioral/history modeling; Lee & Lee(2025) về placement features; Ghazali et al.(2021) về ML placement. Đối chiếu PDF trong Paper/ khi trích dẫn; dataset/grain/target/split khác nhau nên không so phần trăm trực tiếp. Không nhận feature không có trong schema hoặc gọi damage/kill là firing accuracy thực đo.

<a id="journal"></a>

# 5. Nhật ký và trạng thái hiện tại

- 21/10/2026: Chuyển nghiên cứu từ placement hồi cứu sang forecasting team-snapshot v3.3; giữ DuckDB/Parquet, giữ date, event-prefix features, baseline sống+kills, groupedCV/ranking/per-t evaluation. Chưa có dữ liệu thật để chốt grid/coverage; chưa triển khai mô hình mới.
- 21/10/2026: Theo yêu cầu người dùng, hợp nhất38 Markdown thành file này. Thay checklist nhiều protocol bằng checklist chuyển đổi v3.3, giữ các task chuyển đổi đang mở; không chuyển dấu tích lịch sử thành bằng chứng mới. Lệnh dọn tài liệu chỉ xóa37 file Markdown đã kiểm kê; file ngoài Markdown không thuộc danh sách xóa của đợt này. Các nguồn trước hợp nhất được sao lưu ZIP ngoài project, gồm cả thay đổi chưa commit.
- Việc cập nhật consumer tài liệu chưa hoàn tất: trong lúc hợp nhất, phát hiện configs/notebooks/tests/scripts và một số artifact bị xóa từ ngoài lệnh xóa Markdown của đợt này. Người dùng xác nhận chủ động xóa và yêu cầu giữ nguyên. Đã hoàn tác đúng hai thay đổi tham chiếu vừa thực hiện, không khôi phục các file người dùng xóa. Source còn tham chiếu tài liệu cũ cần sửa ở INV-01 trước chạy; không chạy/regenerate notebook hoặc All-in-One.
- Giới hạn: tài liệu và references không phải bằng chứng G0/full-data/Drive/GPU. INV-01 là việc đầu tiên còn mở. Không cài dependency, commit hoặc push.

- Kiểm tra hợp nhất: còn đúng một file `.md` trong cây project; UTF-8/fences/local anchors/checklist và `git diff --check` được kiểm. Backup ZIP ngoài project: `C:/Users/PC/AppData/Local/Temp/pubg_markdown_backup_p7b1dprt/markdown_before_unification.zip`. Không có kiểm chứng notebook/model trong đợt này.

- Người dùng xác nhận giữ việc xóa configs/notebooks/tests/scripts ngoài chat. Checklist là kế hoạch đích; INV-01 kiểm kê lại workspace và xác định phần cần tái sử dụng/dựng mới. Không khôi phục thư mục hoặc cập nhật code nghiệp vụ trong đợt hợp nhất này.
