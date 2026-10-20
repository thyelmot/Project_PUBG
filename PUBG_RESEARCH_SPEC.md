# Đặc tả bài cuối kỳ khai phá dữ liệu PUBG

Phiên bản thiết kế: 5.11-normalized-storage. Cập nhật: 20/10/2026.
Trạng thái 16/10/2026: có evidence pipeline synthetic CUDA và saved-output read-back Version 3 do người dùng cung cấp; chưa có kết quả PUBG chính thức. Người dùng đã cho phép chuyển sang dữ liệu lớn, gắn Dataset thật và gửi kiểm header đầu mỗi nhóm (5 aggregate/5 deaths, tổng khoảng18.89GiB; working trống19.5GiB). Đây không phải inventory/hash/schema toàn nguồn hoặc xác nhận đủ tài nguyên. Đã sửa vận hành S01 giảm bản sao Parquet:31/31tests CPU local và đối chiếu90bảng/dataset/predictions trước/sau đạt; chưa chạy nguồn lớn trong lượt sửa. Version Input thực, đơn vị/chronology và quyết định nghiên cứu thật vẫn cần xác minh. Cấu hình/quyết định fixture không áp dụng cho nghiên cứu thật. Dọn cây cũ vẫn bị chặn.
Cập nhật 17/10/2026: người dùng cung cấp ảnh S01 full completed, 67.369.231 dòng aggregate và 65.370.475 dòng event trên 10 shard. Đây là bằng chứng ingest, chưa phải kết quả RQ1/RQ2/RQ3. Bản lưu official Version1 không có file hiển thị và kiểm working sau đó cho False; không có bản sao theo phản hồi người dùng. Chưa xác định được nguyên nhân lỗi lưu, không gọi đã có output bền vững. Code auto 5.2 đạt37/37tests CPU local trong165.956giây, không chứng minh GPU/full-data trên Kaggle.

Kế hoạch thực hiện duy nhất: [PUBG_IMPLEMENTATION_PLAN.md](PUBG_IMPLEMENTATION_PLAN.md).

## I. Mục tiêu và ranh giới

Đề tài: Phân tích hành vi người chơi PUBG, phân nhóm hành vi và hồi quy thời gian sống sót/thứ hạng từ dữ liệu sau trận.

Mục tiêu là bài cuối kỳ có câu hỏi rõ, xử lý dữ liệu đúng, phương pháp bám môn học, kết quả truy vết được và nhóm giải thích được khi bảo vệ. Mục tiêu 10 điểm là định hướng chất lượng, không phải điểm được bảo đảm. Chưa có rubric (bảng tiêu chí chấm) của giảng viên; không tự tạo trọng số rồi gọi đó là thang điểm chính thức.

Phiên bản này thực hiện yêu cầu xây mới bài cuối kỳ sau khi đối chiếu bảy slide C1-C7, xóa sản phẩm dự án cũ theo phạm vi đã kiểm kê và chỉ kế thừa phương pháp/hướng nghiên cứu. Notebook duy nhất là notebooks/PUBG_COURSEWORK.ipynb. Giữ ba RQ, hai target, Combat Timing và tính trung thực khoa học. Giảm số nhánh thí nghiệm bắt buộc, không giảm yêu cầu kiểm tra dữ liệu, chống rò rỉ hoặc khả năng đọc notebook.

Thay đổi phạm vi so với v3.0:

| Nội dung | Phạm vi mới |
| --- | --- |
| RQ1, tiền xử lý, EDA, Combat Timing | Bắt buộc |
| RQ2 KMeans per_mode, chọn K, độ ổn định qua seed, mô tả cụm và outcome sau khóa | Bắt buộc |
| C2 phân cấp, C3 thêm games_played, C4 chạy phân cụm lại nhiều ngưỡng, DBSCAN | Mở rộng, không điều kiện qua bài chính |
| RQ3 S1, P2, hai baseline hằng số, Linear Regression | Bắt buộc |
| T0/T1 cho placement, cùng cohort/model/split | Bắt buộc, điểm nhấn thực nghiệm |
| P1 và so P1/P2, lịch sử S2/P3, ablation mọi nhóm, nhiều mô hình boosting | Mở rộng |
| Random Forest hồi quy | Mở rộng ưu tiên nếu đủ tài nguyên và thời gian |
| Sai số theo mode/miền target, hệ số tuyến tính, tái lập và báo cáo | Bắt buộc |
| Khoảng tin cậy bootstrap | Ưu tiên T0/T1; được ghi giới hạn thiếu CI, không tuyên bố ý nghĩa thống kê khi chưa tính |
| Toàn bộ dữ liệu hợp lệ | Giữ nguyên. Chưa phê duyệt lấy mẫu nghiên cứu chính |

Người dùng đã yêu cầu xóa và làm mới code/config/notebook/tài liệu cùng dữ liệu/kết quả cũ thuộc dự án. Chỉ kế thừa phương pháp, không giữ implementation/checkpoint/manifest/models/predictions hoặc số liệu audit cũ như kết quả mới. Giai đoạn 0 phải kiểm kê exact paths trong Project_PUBG, không xóa workspace cha, tài liệu môn học, .git hoặc theo link sang thư mục ngoài. Drive và raw/ZIP ngoài root phải được xác định target thực riêng. Phần code đã triển khai, nhưng chưa thực hiện xóa. Thí nghiệm mở rộng chưa chạy không được đánh completed.

## II. Liên hệ nội dung môn học

Các slide nằm ở thư mục cha repository. C1-C7 dưới đây là CHƯƠNG học, khác với mã thí nghiệm phân cụm C1-C5.

| Chương và file | Áp dụng | Đầu ra chứng minh |
| --- | --- | --- |
| C1: C1_GioiThieu.pdf, 44 trang | Quy trình KDD: hiểu bài toán, chọn dữ liệu, tiền xử lý, khai phá, đánh giá, trình bày | Luồng nghiên cứu và câu hỏi RQ trong báo cáo |
| C2: C2_ThongKevaTienXuly.pdf, 49 trang | Chất lượng dữ liệu, thống kê, missing, ngoại lệ, chuẩn hóa | S01-S06: bảng đối soát, phân bố, tương quan, giải thích xử lý |
| C3: C3_LuatKetHop.pdf, 33 trang | Chưa thuộc bài chính; Apriori/FP-Growth chỉ khi có câu hỏi giao dịch riêng | Nếu mở: định nghĩa giao dịch, support/confidence, diễn giải và giới hạn |
| C4: C4_classification_sample_ensemble.pdf, 88 trang | Phân chia/đánh giá dữ liệu; Random Forest hồi quy là mở rộng ưu tiên | So với Linear Regression trên cùng thiết kế |
| C5: C5_Bayesian Decision Theory and Classification.pdf, 26 trang | Không ép Naive Bayes vào target liên tục | Nếu mở phân loại phải định nghĩa target/phép đánh giá riêng |
| C6: C6_Regression.pdf, 65 trang | Hồi quy tuyến tính, residual, đa cộng tuyến và đánh giá | S1/P2, baseline, MAE/RMSE/R², hệ số và sai số |
| C7: C7_Clustering.pdf, 78 trang | KMeans, chuẩn hóa, chọn K, diễn giải cụm; phân cấp tùy chọn | K diagnostics, centers, sizes, stability theo mode |

Không cần áp dụng tất cả chương nếu không phù hợp câu hỏi. Logistic Regression là phân loại, không thay Linear Regression cho hai target hiện tại. Không chép metric hoặc ngưỡng từ slide/paper làm mức kết quả bắt buộc.

## III. Câu hỏi, đơn vị và target

| Câu hỏi | Đơn vị | Phương pháp chính | Ranh giới diễn giải |
| --- | --- | --- | --- |
| RQ1: Hành vi nào liên hệ với sống sót/thứ hạng? | Player-match | Pearson, Spearman, so sánh theo mode | Quan hệ quan sát, không nhân quả |
| RQ2: Có các nhóm hành vi nào? | Player-mode profile | KMeans riêng Solo/Duo/Squad | Tên cụm dựa hành vi; outcome chỉ giải thích sau khóa |
| RQ3: Hành vi sau trận cung cấp thông tin hồi quy survival/placement thế nào? | Player-match | Baseline và Linear Regression; T0/T1 | Hồi cứu, không phải dự báo trước trận |

Nguồn: PUBG Match Deaths and Statistics, Kaggle slug `skihikingkevin/pubg-match-deaths`. Hai nhóm aggregate và death/event có nhiều shard; phải inventory toàn bộ nguồn thật, không hard-code số shard. Lưu URL/version/license/đơn vị khi xác minh được; unknown khi chưa biết, không dùng mtime giả ngày tải.

Target survival: `player_survive_time`, hữu hạn, không âm, đơn vị công bố theo evidence. Không gọi đây là mô hình survival analysis có censoring.

Target placement: quan sát kết quả đội trên dòng người chơi. Với roster hợp lệ:

\[
y_{placement}=1-\frac{team\_placement-1}{N_{teams}-1}.
\]

`N_teams` là số team ID đã kiểm chứng trong match trước lọc cohort theo target. Yêu cầu `N_teams>1`, rank thuộc miền hợp lệ và cùng đội không mâu thuẫn. Không clip rank hoặc sửa mẫu số để che roster thiếu. Một target lỗi chỉ loại khỏi task cần target đó.

Team-size mode theo mapping khai báo 1/Solo, 2/Duo, 4/Squad, được kiểm tính phù hợp trên mẫu ZIP (mục XIII), không gọi là đã xác minh toàn nguồn; giá trị khác giữ Custom/Other hoặc unknown theo contract, không tự gộp mọi giá trị >=3 thành Squad. Perspective TPP/FPP là biến khác. RQ2 giữ `per_mode`.

Tên người chơi không phải bằng chứng account ID bất biến. Không ghép tên thiếu thành một player UNKNOWN; lưu lineage cho các dòng còn đủ điều kiện ở RQ khác.

## IV. Dữ liệu, làm sạch và phạm vi

- Raw bất biến; inventory hash/schema/rows từng shard, alias có kiểm soát, đếm record bằng parser.
- Tách missing gốc, parse error, structural missing (thiếu đúng theo định nghĩa), identity conflict và nguồn không sẵn có.
- Deduplicate xuyên shard bằng khóa/nguồn đã xác minh; không dùng thứ tự file chọn đại row mâu thuẫn.
- Event khác victim nhưng cùng killer/time không tự là duplicate.
- Flags có thể chồng lặp; removal ledger tuần tự phải đối soát rows_before = rows_removed + rows_after. Không cộng flags thành tổng số loại.
- Metadata roster, số đội, mode và duration proxy tính trước task-specific exclusions.
- Join phải kiểm khóa, many-to-one và bảo toàn số dòng. Parquet phải giải mã/đọc lại được, không chỉ footer/checksum.
- Ngoại lệ chưa giải thích giữ flag và công bố; không xóa/cắt ngọn chỉ để biểu đồ hoặc metric đẹp.
- Mỗi cohort ghi rule, exclusions, rows/matches/teams/players, mode/split và hash.

Phân biệt ba phạm vi: fixture kiểm logic; development train/validation để chọn thiết kế; full eligible data là toàn dữ liệu hợp lệ trong cohort đã khai báo. Vẽ mẫu không biến mô hình thành mô hình mẫu.

Chưa cho phép lấy mẫu làm kết quả chính. Nếu tài nguyên không đủ, trình phương án lấy mẫu theo match, giữ roster và event tương ứng, nguồn, seed, phạm vi suy rộng và tác động đến profile/history; chỉ triển khai sau yêu cầu riêng của người dùng. Không tự đặt số mẫu hoặc đổi nhãn thành full-data.

## V. Đặc trưng và Combat Timing

Registry lưu tên, nguồn, công thức, đơn vị, mẫu số, missing, dependencies, quyền sử dụng theo target/RQ, trạng thái và phiên bản. Một công thức có một nguồn thực thi canonical trong src.

| Nhóm | Thành phần | Quy tắc |
| --- | --- | --- |
| Combat | kills, damage, damage_per_kill | kills=0 thì ratio missing, không epsilon |
| Movement | walk, ride, total_distance, walk_ratio | tổng distance=0 thì ratio missing; tránh cặp ratio bù nhau |
| Support | assists, DBNO, assist_ratio | kills+assists=0 thì ratio missing |
| Timing tuyệt đối | event count, has_kill, first/avg kill time | Tách không kill và thiếu event; lineage không phụ thuộc target để dùng S1 |
| Timing pha | early/mid/late counts và ratios | Phụ thuộc duration proxy hậu trận; không dùng S1 hoặc RQ1-survival primary |
| Target-derived diagnostic | kills/minute, damage/minute, velocities | Không dùng dự đoán survival hoặc làm bằng chứng chính tương quan với survival |

`estimated_match_duration = max(player_survive_time)` trong match là proxy, không phải duration chính thức. Relative event time là event time / proxy; Early [0,1/3), Mid [1/3,2/3), Late [2/3,1]. Không clip event vượt proxy; timing tuyệt đối hợp lệ không tự bị loại chỉ vì phase không hợp lệ.

Kế thừa quy ước phương pháp đã lựa chọn cho timing, ghi đủ tại đây để dự án mới không phụ thuộc reports/decision files cũ:
- Event ghi nhận cho killer có tên, không self, match/time hợp lệ; có thể chứa same-team/unknown-team. Không gọi enemy-only.
- Giữ ngưỡng duration 60 giây như quy ước công bố, không gọi tối ưu.
- Giây là đơn vị dự kiến từ thiết kế trước; dữ liệu mới phải kiểm nguồn/consistency trước khi verified. Không bê trạng thái verified hoặc số audit cũ sang manifest mới.
- Giữ các giá trị bất thường nguồn và giới hạn chưa giải thích.
- Các quy ước này không chứng minh ingest/merge/features mới đã chạy. Stage S04 phải tạo evidence/checkpoint mới.

Qua batch phải cộng sum/count rồi chia, min toàn cục; không trung bình các chunk means. Phase ratios dùng đúng phase-valid denominator. Aggregate kills và event count không bắt buộc bằng nhau; xuất coverage/discrepancy và phân biệt:
- Xác nhận không kill: count 0, first/avg/phase ratios missing.
- Có aggregate kills nhưng thiếu event: missing do coverage, không coi là no-kill.
- Có event nhưng phase không hợp lệ: absolute/phase có trạng thái riêng.

RQ2 dùng thiết kế phương pháp Design 3: mean/std kills và damage; mean walk/ride/walk_ratio; mean assists/DBNO/assist_ratio; mean early/mid/late ratios và early_combat_match_ratio. Lưu valid counts; std singleton chưa xác định, không gán 0. Mean phase ratio là trung bình trên các trận kill-active có timing hợp lệ, không tự đổi thành ratio pooled kills. `games_played` để lọc độ tin cậy, không input chính. Outcomes tách khỏi input.

## VI. Split, chống rò rỉ và RQ1/RQ2

Giữ tỷ lệ train/validation/test 0.70/0.15/0.15 đã chốt; mọi dòng cùng match ở cùng split. Với chronology đáng tin ưu tiên thời gian; Grade B giữ nguyên block ngày, Grade A không bịa thứ tự tie. Grade C dùng group split theo match và không gọi future prediction. Tỷ lệ đạt được có thể lệch do nguyên block; phải báo actual counts.

Khóa split trước EDA quan hệ phục vụ lựa chọn mô hình. DQ toàn nguồn được phép theo quy tắc chất lượng đã định; không dùng test để chọn K, ngưỡng, feature hoặc model. Nếu test từng được xem, công bố giới hạn; không resplit chỉ để xóa việc đã xem.

RQ1:
- Pearson và Spearman với N hợp lệ từng cặp và từng mode; constant/thiếu dữ liệu là NA có lý do.
- Spearman cần ranks/ties toàn scope; không lấy trung bình correlation theo batch.
- Báo dấu, độ lớn và tính nhất quán theo mode; p nhỏ không đồng nghĩa quan hệ mạnh.
- Timing pha với survival là diagnostic có coupling. Người sống lâu có thêm cơ hội tích lũy hành vi.
- Phân tích lựa chọn dùng development. Full-descriptive chỉ sau khóa thiết kế, không quay lại tune.

RQ2:
- Auto 5.2 dùng mặc định 10 trận theo quy ước được người dùng duyệt ngày 17/10/2026, cho ghi đè trước chạy; vẫn xuất retention/valid counts. Không gọi ngưỡng này là tối ưu. Manual giữ quy trình chốt từ diagnostics.
- Imputation/StandardScaler trên development phù hợp; lưu feature order và fitted objects.
- Auto 5.2 chọn K trong 2-8 có silhouette development hữu hạn cao nhất, hòa chính xác chọn K nhỏ hơn; ghi đè từng mode được ưu tiên và phải thuộc diagnostics. Elbow, kích thước cụm, ARI qua seed và Davies-Bouldin vẫn báo để diễn giải, không thêm ngưỡng lọc ngầm. Manual giữ lựa chọn có reason/hash.
- Silhouette/plot diagnostic được lấy mẫu có n/seed/rule, không thay fit toàn eligible profiles.
- Cluster ID chỉ trong mode. Đổi outcome không được làm thay lựa chọn K/assignment khi hành vi cố định.
- Full descriptive fit sau khóa có nhãn mô tả, không gọi heldout generalization.
- Nếu timing proxy chi phối, công bố coupling và giới hạn; kiểm tra bỏ timing là mở rộng có lý do, không tối ưu theo outcome.

## VII. Ma trận thí nghiệm bài chính

Tên dưới đây là nhãn nghiên cứu cho project mới. Dùng experiment metadata tối thiểu cho models/predictions/comparisons; không sao hệ thống registry cũ hoặc hard-code run ID.

| Thành phần | Bắt buộc | Target/đầu vào |
| --- | --- | --- |
| RQ1 | Có | Quan hệ hợp lệ theo target/mode |
| C1 main + C5 post-hoc | Có | KMeans per_mode + outcome mô tả sau khóa |
| S1 mean, median, linear | Có | Survival; behavior an toàn, timing tuyệt đối chỉ khi lineage hợp lệ |
| P2 mean, median, linear | Có | Placement; behavior + timing, không cột survival trực tiếp |
| T0 linear | Có | Placement; bỏ toàn timing và descendants/indicators tương ứng |
| T1 linear | Có | Dùng lại P2 linear khi đúng cùng cohort/recipe/signature |
| Sai số, hệ số tuyến tính, bảng T0/T1 | Có | Saved predictions và fitted model đã chọn |
| CI T0/T1 | Ưu tiên có điều kiện | Paired bootstrap theo match; thiếu thì khai báo |
| P1, S2/P3, C2-C4, full group ablation, nonlinear | Không, trừ khi đăng ký mở rộng | Có scope/status/reason riêng |

Tối thiểu có bảy fit logic: ba S1, ba P2 và một T0; không huấn luyện lại T1 chỉ để đổi tên. Hai baseline dùng thống kê train, không test. Linear Regression là mô hình chính bám C6; không âm thầm thay OLS bằng SGD.

T0/T1 cùng row IDs, target, split, estimator, seed và chính sách preprocessing; mỗi nhánh fit transformer trên train và đúng cột của nhánh. Khóa common cohort trước fit, không intersect predictions để che dòng mất. Survival trực tiếp không được thêm vào chỉ một nhánh. P2 vẫn có coupling gián tiếp từ timing proxy, không được gọi loại hết thông tin survival.

Random Forest hồi quy là mở rộng ưu tiên bám C4. Nếu quá nặng có thể đề xuất cây hồi quy giới hạn độ sâu, nhưng phải có recipe/tên riêng; không coi đó là cùng thuật toán. HGB/XGBoost/SGD không thuộc core config mới; chỉ thêm nếu mở rộng có lý do.

Giữ yêu cầu dùng GPU cho KMeans/Linear Regression khi backend hỗ trợ và đã xác minh. Constants, SQL/EDA/metrics là CPU. RF/HGB/SGD theo backend thực hỗ trợ; không ép CUDA hoặc fallback ngầm. Mọi đổi thiết bị/estimator chính phải khai báo và kiểm tương thích trước chạy.

## VIII. Đánh giá và diễn giải

\[
MAE=\frac{1}{n}\sum_i|y_i-\hat y_i|,\qquad
RMSE=\sqrt{\frac{1}{n}\sum_i(y_i-\hat y_i)^2},\qquad
R^2=1-\frac{\sum_i(y_i-\hat y_i)^2}{\sum_i(y_i-\bar y)^2}.
\]

Báo MAE/RMSE theo đơn vị target, R² không phải accuracy và có thể âm. Target hằng số hoặc n<2: R² undefined có reason. Không clip predictions ngầm.

Primary metric là micro player-match; bổ sung match-aware và team-aware cho placement để tránh diễn giải các đồng đội như quan sát độc lập. Không lấy trung bình RMSE/R² từng batch thành metric toàn bộ. Team target phải nhất quán trước aggregate.

Chọn feature/params trên train/validation; main recipe fit train-only, test predict-only sau G4. Không tự refit train+validation. Đăng ký error bins theo development, báo N/coverage/NA cho slice nhỏ. Giải thích hệ số tuyến tính kèm scale/đa cộng tuyến; không gọi hệ số là tác động nhân quả.

Delta = candidate - reference: MAE/RMSE âm là tốt hơn; R² dương tốt hơn. CI nếu làm: resample cùng match IDs có hoàn lại và multiplicity, dùng cùng resample cho hai nhánh; seed/replicates đăng ký trước. CI chứa 0 không phải bằng chứng không có hiệu ứng; thiếu CI không vẽ khoảng hoặc khẳng định chắc chắn. Không bắt CI cho mọi bảng/hình.

## IX. Mở rộng có điều kiện

Chỉ mở khi bài chính đủ và có yêu cầu, không biến extension thành việc bắt buộc ngầm.

- P1/P2: chỉ khác survival trực tiếp, cùng cohort hợp lệ, công bố descendants còn lại.
- S2/P3 trong phần con history tùy chọn của notebook duy nhất: kiểm timestamp/availability, Grade A strictly earlier whole block, Grade B chỉ ngày trước, Grade C blocked. Depth dựa quá khứ, không dùng số trận tương lai; current/future outcome không đổi current history. Không lấy full RQ2 profiles làm history. Protocol/history threshold cần evidence riêng.
- C2 phân cấp: sample hoặc centers nếu cần, công bố supporting scope. C3/C4 so đúng scaler/common profile keys.
- Ablation nhóm: xóa toàn dependency descendants và indicators, giữ recipe/cohort.
- Luật kết hợp, phân loại, DBSCAN: phải có câu hỏi, biểu diễn, metric, ngân sách và giới hạn riêng; không thêm chỉ để đủ bảy chương.

History không phải prerequisite của core current-match. Dự án mới không tạo NB08 hoặc các dependencies notebook cũ. Nếu mở history, thực hiện trong phần con cùng notebook, đăng ký scope/decision/evidence riêng.

## X. Kiến trúc mới, lưu trữ và notebook duy nhất

Vận hành chính là Kaggle Notebook, raw gắn bằng Add Input từ nguồn/version đã pin; Input chỉ đọc. Code mới từ Input/repository được chuẩn bị vào working có marker, không copy raw hoặc project cũ.

Cập nhật vận hành18/10/2026 theo yêu cầu sửa file upload chính thức: cell parameters gán trực tiếp full/ALLOW_DATA_PROCESSING=True/ALLOW_FULL_DATA=True, S01-S10, CODE_INPUT và raw mount đã được người dùng chọn, SOURCE_VERSION=3 cùng assumed_seconds theo mụcXIII. Không dùng globals để kế thừa False/pending cũ. Đây là cấu hình phiên được phê duyệt cho nguồn cụ thể, không cấp quyền chung cho nguồn khác, không thay nghiên cứu hoặc bỏ guard. Khối development/False dưới là mặc định an toàn của bản nền trước khi được cho phép chạy thật, không còn là nội dung cell parameters của bản upload này.

```python
PUBG_STORAGE_MODE = "local"
PUBG_PROJECT_ROOT = "/kaggle/working/PUBG_Coursework"
PUBG_REQUIRE_EXISTING_PROJECT = True
PUBG_BATCH_ROWS = 50000
EXECUTION_MODE = "development"
ALLOW_DATA_PROCESSING = False
ALLOW_FULL_DATA = False
```

Bật ALLOW_DATA_PROCESSING chỉ khi đã xác nhận nguồn được phép; development không tự giới hạn số dòng của nguồn. Full-data cần ALLOW_FULL_DATA và yêu cầu riêng của người dùng. SOURCE_DIRECTORY là path thật, SOURCE_VERSION là số version đã pin; license/mode/chronology/timing vẫn cần evidence. Không gọi dataset latest ngầm hoặc tự tạo token/upload.

DuckDB/Parquet/PyArrow dùng scan/join/group theo batch, pandas cho bảng vừa RAM. GPU không tăng host RAM. DuckDB spill/shard ingest tạm ở runtime ngoài working; riêng staging xuất Parquet ở cùng filesystem với đích để publish bằng rename, giữ checksum/read-back và bảo vệ bản cũ. Shard tạm chỉ giữ tới khi aggregate.parquet/event.parquet gộp đã kiểm số dòng và publish thành công, không lưu thêm typed trùng dữ liệu trong gói bàn giao; không bỏ raw columns hoặc lineage. source raw không đổi; data/<scope>/ và outputs/<scope>/ chứa kết quả mới, ngân sách output khai báo rõ là ngân sách nhóm chứ không quota dịch vụ đã đo. Sửa vận hành này không bảo đảm toàn quy trình vừa19.5GiB; thiếu tài nguyên phải dừng đúng trạng thái.

Một người ghi một stage, takeover có chủ đích. Publish/read-back/checksum tại working tạo checkpoint runtime; chỉ reuse compatible theo nội dung nguồn/version/code/config/split/cohort/backend/package/Python, không theo mount path tuyệt đối hoặc tên file. File artifact dùng relative paths. Memo checksum chỉ trong một lượt xác minh, không che sửa file ở lượt sau.

Kaggle working không tự là lưu bền vững. prepare_handoff xuất inventory đủ code/config/data/outputs cho resume, saved_version_verified=False. Save Version phải kèm output; gắn lại output/version cụ thể và verify_handoff đọc/giải mã/checksum trước bàn giao. Version reference do người dùng chọn, không được gọi xác minh API/quyền tài khoản. Local read-back chỉ chứng minh đọc file local.

restore_handoff chỉ vào working mới/trống, không ghi đè kết quả hiện có; kiểm software/source/stage signatures và mọi prerequisite, không sửa completed bằng tay hoặc mang writer lock sang. Native output folder là luồng chính; không giải nén archive không tin cậy. Gói code ZIP được tạo từ allowlist, không raw/results/secrets.

Tên canonical ghi đè an toàn, không (1)/(2); Kaggle Versions và release snapshots mới có chủ đích tái lập. Dừng khi quota/RAM/disk/GPU/budget thiếu, giữ checkpoint tốt trước đó, không silent sample hoặc đổi estimator. Không hứa resume giữa estimator fit dở, auto-save Drive hoặc chuyển tài khoản vượt quota. Drive chỉ optional export nếu có yêu cầu riêng.

Chỉ tạo notebooks/PUBG_COURSEWORK.ipynb, gồm S00-S12 theo kế hoạch. Xóa 13 notebook và bản tổng hợp cũ khi thực thi dọn dự án; không ghép nguyên cells hoặc khôi phục generator/bundle cũ. Yêu cầu một notebook mới thay quy tắc cũ cấm notebook tổng hợp. Hàm dùng lại nằm trong một số module src nhỏ, cấu hình ở configs/project.yaml; không tạo notebook phụ cho demo/test/summary.

Mỗi section trong notebook duy nhất theo Phương án 2: bối cảnh/câu hỏi, input và provenance, phương pháp/công thức, thực thi từng bước, kiểm chất lượng, bảng/hình thật, cách đọc, diễn giải, giới hạn, artifact/bàn giao. Tiếng Việt có dấu UTF-8; số cell không thay độ chi tiết. Biểu đồ cần đơn vị/N/scope/mode/split/nguồn/caption; mẫu trực quan có n/seed/rule. Thiếu dữ liệu không dựng hình hoặc metric giả.

Cấu trúc mới chi tiết nằm tại kế hoạch III. Một README mới gom hướng dẫn nhóm/Kaggle/Input/working/Versions/GPU/sections/troubleshooting; các guide cũ được loại bỏ khi dọn. Không mang code/config/tests cũ vào cây mới. .git được giữ để không mất thông tin repository; đây không phải yêu cầu xóa Git history hoặc remote.

S00 khai báo execution mode development/full/report_only và START_STAGE/END_STAGE. Trong full/development, stage có completed signature/artifacts hợp lệ được load lại; stage mới chạy theo dependency. Runtime mới vẫn phải bootstrap/init và đọc state từ đĩa; không chỉ mở cell giữa dựa biến RAM. Auto dùng quy tắc 5.2 đã duyệt, không chờ người chốt K/ngưỡng/G4 giữa luồng; manual vẫn dừng khi thiếu quyết định. report_only đọc snapshot không cần raw/current model training state. Mỗi section commit output riêng để nhiều thành viên thay nhau chạy cùng một notebook.

## XI. Hoàn thành và bàn giao

G0: code/fixture bài chính phù hợp thiết kế mới. G1: nguồn thật hợp lệ. G2: cohort/split hợp lệ. G3: quyết định có bằng chứng. G4: khóa lựa chọn trước final test. G5: khóa release đủ thành phần bắt buộc. Các cổng không được coi đạt chỉ vì viết xong tài liệu.

Section S10 kiểm required matrix core, signatures/schema/checksum, run IDs và figure sources rồi khóa release mới. Optional chưa chạy ghi not_requested với reason/null metrics. Lifecycle/stage schema mới được thiết kế tối thiểu, không giữ enum/format/compatibility của manager cũ chỉ để reuse kết quả.

Execution mode report_only chạy S00 kiểm đọc tối thiểu và S11/S12 trong cùng notebook, chỉ đọc release manifest cụ thể; S01-S10 tính toán phải được bỏ qua bằng nhánh control flow đã test, không train/build/download/write. Báo cáo gồm bài toán/KDD, dữ liệu/chất lượng, EDA/RQ1, RQ2, hồi quy hai target, T0/T1, sai số, giới hạn và khả năng tái lập. Mỗi nhận định truy được bảng/hình/run.

Chuẩn chất lượng hướng tới điểm cao: phương pháp đúng môn học, so sánh công bằng, lời giải thích dễ hiểu, số liệu thật, biểu đồ đọc được, nhận biết giới hạn và các thành viên bảo vệ được lựa chọn. Bảng tiêu chí giảng viên khi có sẽ được đối chiếu vào kế hoạch hiện hành, không tạo kế hoạch ghi đè.


## XII. Protocol tự động 5.2 được duyệt ngày 17/10/2026

Người dùng đã đồng ý đề xuất tự động hoàn toàn và chỉnh tại từng mục. Đây là thay đổi protocol lựa chọn, không phải tối ưu I/O thuần túy. Giữ ba RQ, hai target, toàn eligible data, per_mode, split 70/15/15, leakage allowlists, bảy fit OLS/baseline, GPU theo backend đã chọn và mọi metric. Không bê quyết định fixture sang nghiên cứu thật.

- preprocessing/features/rq2/rq3.decision_mode mặc định auto; manual vẫn giữ cổng chờ. OPTIONS ở mỗi cell thực thi ghi đè các trường đã khai báo; None kế thừa giá trị config hiện tại, không xóa quyết định đã lưu. Các sửa đổi được publish config và đưa vào stage signature; stage sau phải dùng đúng upstream, không đổi split sau khi xem test để che exposure.
- Chronology auto không coi parse timestamp là bằng chứng semantics. Chỉ chọn A/B khi có chronology_evidence, mọi match nhất quán và có ít nhất ba block; toàn ngày chọn B, có thời gian trong ngày chọn A. Nếu chưa đủ thì C, seeded match-group, công bố không phải future prediction. Ghi đè A/B/C cần reason và vẫn kiểm consistency. mode_evidence phải do nguồn/người vận hành xác nhận.
- Features auto giữ nguyên/no-log/no-outlier-removal khi chưa có lựa chọn khác. Nếu người dùng bật log, phải cung cấp transform_reason và qua allowlist. Không chọn biến đổi theo test.
- RQ2 mặc định minimum_games=10 nếu null. Không giảm ngưỡng để cứu mode thiếu profile. Chọn K bằng silhouette development theo quy tắc trên; invalid/undefined diagnostics phải lỗi rõ, không chọn tùy ý. cluster_selection.json khóa hash, ngưỡng, K, reason trước fit full descriptive/outcomes; config không bị tự sửa giữa stage làm stale signature.
- Auto G4 duyệt tất cả bảy fit đã đăng ký sau kiểm cohort/train-only/model reload/predictions và validation. Kiểm đủ bảy micro experiments, đúng target, n dương, MAE/RMSE hữu hạn không âm; R2 undefined có lý do được giữ, infinity không được nhận. Không đặt ngưỡng điểm tùy tiện, không chọn winner bằng test, không refit train+validation. selection.json lưu validation hash/approval/reason/test_accessed_at_approval=False trước đọc tập test của S08; prior_test_exposure vẫn unknown nếu chưa có bằng chứng.
- Nguồn/đơn vị là sự kiện phải xác minh, không phải tham số tự chọn. Preflight của lượt đi tới S02/S04 chặn sớm nếu thiếu mode_evidence hoặc thiếu trạng thái đơn vị được chấp nhận/evidence, trước khi tốn giờ S01. Từ 5.3, assumed_seconds được chấp nhận theo phê duyệt có phạm vi ở mục XIII, không nâng thành verified. Các trường SOURCE_MODE_EVIDENCE/SOURCE_TIME_UNIT_STATUS/SOURCE_TIME_UNIT_EVIDENCE tại S00 là đầu vào một lần; không gán verified từ histogram hoặc từ dataset slug. Metadata công khai Kaggle kiểm ngày 17/10 xác nhận license CC0/version3 nhưng API trả cột rỗng, chưa xác minh được đơn vị hoặc mode từ metadata đó.
- Checkpoint runtime vẫn sau từng stage. Mặc định chỉ prepare_handoff ở END_STAGE, không quét/giải mã lại toàn output sau mỗi cell. HANDOFF_EVERY_STAGE=True là lựa chọn cần thời gian I/O; không bỏ artifact/source hash và kiểm dependency, không memo checksum qua lượt xác minh. Không gọi đây là auto-save Kaggle: lưu Version kèm output/read-back vẫn là thao tác riêng.
- Giới hạn RAM/VRAM/đĩa vẫn dừng trung thực. max_matrix_gb=2 chưa thay đổi; full-data S07/S08 có thể vượt. Tự động hóa không đổi batch thành thuật toán streaming OLS/KMeans hoặc chứng minh đủ tài nguyên. Lỗi platform JSON/HTML không được sửa bằng thay protocol nghiên cứu.


## XIII. Giả định giây có công bố, người dùng duyệt ngày 18/10/2026

Đây là thay đổi protocol diễn giải đơn vị theo yêu cầu rõ của người dùng. Không biến giả định thành sự kiện đã được tác giả nguồn xác nhận. time_unit_info là nơi duy nhất xác định trạng thái/nhãn/điều kiện chấp nhận cho preflight, S03/S04, EDA, mô hình và báo cáo.

- pending: chưa chấp nhận để chạy timing; verified: cần evidence xác minh thật; assumed_seconds: cần unit_evidence có nội dung, unit_assumption_approved=True và unit_assumption_scope khớp chính xác source.dataset/versions/source.version. Phê duyệt hiện tại chỉ cho skihikingkevin/pubg-match-deaths/versions/3. Đổi nguồn/version làm giả định không được chấp nhận; không mặc định đưa sự chấp thuận sang nguồn khác.
- Cấu hình production ghi assumed_seconds cùng bằng chứng và ngày phê duyệt. source.version/path/license vẫn phải nhập đúng nguồn gắn; không suy ra nguồn thật từ tên ZIP local. Người dùng có thể đặt pending để chặn hoặc verified chỉ khi bổ sung evidence xác minh thật. Không tự đổi bất kỳ pending thành verified.
- Bằng chứng local: Data_PUBG.zip 4.399.919.847bytes, 12members (5aggregate CSV,5deaths CSV,2maps), tổng20.284.734.459bytes sau giải nén, không có README/từ điển/comment. Đọc đầu2000record của từng CSV, tổng20000record, là prefix diagnostic không phải random sample và không đại diện toàn nguồn. Không giải nén toàn bộ hoặc huấn luyện dữ liệu lớn.
- Trên10000aggregate prefix: party_size1/2/4 lần lượt2040/2276/5684rows. Bỏ nhóm trận đầu/cuối từng prefix CHỈ khi kiểm đội đủ nội bộ mẫu (không loại dữ liệu nghiên cứu):1848team của mode1 đều1người;1081team mode2 có45team1người/1036team2người;1551team mode4 có73/63/567/848team tương ứng1/2/3/4người. Mẫu phù hợp mapping đăng ký, không thay tài liệu gốc hoặc xác minh mọi đội toàn nguồn; match_mode trong prefix chỉ tpp, không suy toàn nguồn chỉ tpp.
- Đối chiếu10000event prefix với aggregate theo(match_id,victim_name), chỉ dùng identity có một giá trị survival duy nhất trong mẫu, được8096cặp:8038cặp chênh<=1đơn vị nguồn (99.2836%), median abs difference0.296;58cặp lệch>1, max1787.814. Supports common scale, does not prove absolute seconds. Giây là giả định vận hành được người dùng duyệt để tiếp tục, không phải suy luận đã được xác minh từ histogram hoặc 99.28%. Không có full-source consistency proof.
- Không nhân/chia60 hoặc1000, không đổi minimum_duration60, không thay phase thirds, không clip hoặc xóa58cặp lệch vì kiểm tra này. Không thêm bộ lọc từ audit mẫu vào cohort nghiên cứu. RQ/targets/features/split/leakage/per_mode/OLS/KMeans/GPU/metrics và full eligible data giữ nguyên. MAE/RMSE survival và hệ số có đơn vị giây GIẢ ĐỊNH; nếu thang đo sai, diễn giải giá trị tuyệt đối và ngưỡng60 phải xem lại. R2/tương quan không được gọi là bằng chứng đơn vị.
- S03 dictionary/figures ghi trạng thái theo config; S03 signature phụ thuộc timing để không reuse nhãn cũ khi đơn vị đổi. S04 tạo manifests/time_unit.json và timing_audit với verified=False khi assumed. Preflight/S00, bảng metrics/coefficients/errors, model metadata, figure metadata/footer, release và report_only hiển thị đúng giả định/giới hạn. Không thay số liệu fit/predictions chỉ để gắn nhãn.
- Release5.3 phải có metadata đơn vị. Loader so metadata với config và time_unit.json trong snapshot đã kiểm checksum; metadata đầu manifest không được tự nâng giả định thành verified. report_ready nói đủ gói báo cáo, không đồng nghĩa unit verified. Release cũ thiếu trạng thái riêng phải báo thiếu thông tin, không tự nâng độ tin cậy.
- Src/config/signatures thay đổi; không hứa dùng lại checkpoint bản cũ với code mới. Không sửa code nóng/manifest/checksum để ép reuse. Bộ kiểm local/fixture không chứng minh toàn dữ liệu hoặc GPU/Kaggle đủ tài nguyên; giới hạn2GiB matrix và18GiB output vẫn giữ.

## XIV. Hai GPU độc lập theo yêu cầu ngày 18/10/2026

- rq2.gpu_ids và rq3.gpu_ids mặc định [0,1], device=cuda. S00 kiểm đủ GPU đã chọn trước S01, không fallback CPU hoặc một GPU nếu thiếu; cấu hình [0] chỉ là lựa chọn tường minh khác của người vận hành. CPU fixture vẫn phải chọn device=cpu, không nhận là chứng minh CUDA.
- S07 phân lịch các cặp mode/K độc lập cho tối đa hai tiến trình, mỗi GPU một job; mỗi job vẫn fit toàn eligible development profiles của mode đó cho từng seed, cùng n_init10/seed và diagnostic sample đã đăng ký. Sau khóa K, fit full descriptive riêng từng mode song song. Không shard một bài KMeans hoặc đổi thuật toán/diagnostics/tiêu chí chọn K.
- S08 các baseline hằng số vẫn CPU; S1/P2/T0 linear fit độc lập có thể chạy đồng thời trên hai GPU. OLS cuML algorithm=svd, feature order/log/imputer/scaler/train-only/common cohort/split không đổi. G4 phải kiểm đủ bảy validation fits trước tạo dữ liệu job test; test predict-only từ model đã lưu, không refit. T1 vẫn alias P2.
- CUDA_VISIBLE_DEVICES được đặt riêng trước khi Python worker import CUDA/cuML; tránh đổi device toàn cục trong luồng hoặc fork context CUDA đang sống. Theo [cuML device selection](https://docs.nvidia.com/cuml/26.08/advanced/#selecting-the-cuda-device), không dựa cupy.cuda.Device để chọn GPU cho fit cuML; API đó chỉ được dùng truy vấn metadata từng thiết bị. Serialization yêu cầu cùng phiên bản cuML theo [tài liệu persistence](https://docs.nvidia.com/cuml/latest/pickling_cuml_models/); guard phần mềm hiện có được giữ.
- Tiến trình cha là bên duy nhất publish/record/checkpoint. Worker chỉ ghi file tạm trong thư mục riêng thuộc runtime spill, kiểm reload trước trả labels/predictions/coefficients/compute. Model CUDA không được unpickle trong notebook cha để tránh nạp model GPU1 lên GPU0. Metadata ghi GPU index theo visibility của cha, token visibility của worker, PID, start/finish, compute và dấu mốc test sau G4. Smoke48dòng/GPU kiểm KMeans/OLS/reload; không đọc raw.
- Scheduler giới hạn một worker/GPU, kiểm tổng ước lượng matrix hai worker theo budget2GiB và host available; mỗi fit vẫn kiểm VRAM riêng. Hai GPU không cộng VRAM, không giải quyết một fit quá lớn, không tăng budget hoặc đổi cohort. Lỗi worker/OOM hoặc hủy phải dừng worker còn lại, không commit completed hoặc chạy lùi âm thầm. Temp ngoài working vẫn cần đủ đĩa; không bỏ prerequisites/output để cứu quota.
- Đây là thay đổi vận hành song song được user yêu cầu, không đổi RQ/target/estimator/metric/leakage hoặc phạm vi full. Khác phần cứng/thứ tự CUDA có thể gây sai số số thực nhỏ, không hứa bitwise hay tăng tốc2lần. Src/config đổi làm checkpoint5.3 stale; không migration/checksum giả. Local test dùng CPU/fake CUDA ghi rõ simulated, actual Kaggle T4x2/full-data vẫn phải kiểm thật.

## XV. Kiểm tài nguyên và đồng bộ5.5, ngày18/10/2026

Người dùng yêu cầu thực hiện hướng2 sau audit Run All. Đây là sửa vận hành, không chấp thuận đổi estimator hoặc lấy mẫu. Thay trần matrix2GiB cố định bằng memory_policy=auto, memory_fraction=.60 của RAM đang available; fixed/max_matrix_gb vẫn có thể chọn tường minh. Không dùng tổngRAM thay available, không gộpVRAM, không fallback mộtGPU. S00 kiểm phiên bản code/config, cache src và requirements trước import pipeline. Working v55 mới giữ nguyên dữ liệu phiên cũ; source/code/checkpoint khác nhau vẫn bị chặn.

Sau S04, trước S05 tốn thời gian, đếm cohort/profile, ước lượng host của từng tập và tổngworker, VRAM riêng từngOLS. Chỉ đọc counts/độ dài khóa, không dùng test-target giá trị/metrics/fit để quyết định nghiên cứu. Không gọi ước lượng này là measured peak hoặc bảo đảm full-data; S07/S08 vẫn kiểm lại tại thời điểm collect/worker. S10 kiểm byte bản sao release cộng dự phòng metadata1MiB và dung lượng trống trước ghi, giữ budget18GiB.

Hash bảng theo batch giữ chính serialization/digest cũ; reload predictions theo batch giữ tolerance; T0/P2 kiểm row IDs không cần tải cả feature matrix lần nữa; dev/full profile không đồng thời sống trongRAM. Giữ tất cả row/float64/features/models/metrics và bảy fit. Không sửa protocol để phù hợp máy: nếu một fit vẫn vượtRAM/VRAM phải dùng môi trường đủ tài nguyên hoặc xin quyết định nghiên cứu riêng, không đánh completed giả.

## XVI. Triển khai D0-D1, S02 ngoài RAM, ngày 19/10/2026

Theo kế hoạch OOC mụcXII, đợt5.6 chỉ triển khai D0-D1 để giải quyết OOM metadata S02. Chưa triển khai D2-D6 hoặc đổi huấn luyện S07/S08.

- S02 dùng cơ sở dữ liệu tạm trên đĩa trong thư mục runtime riêng; đóng kết nối trước dọn file thuộc lượt chạy, kể cả lỗi. Không đưa database/spill vào output hoặc handoff. DuckDB memory_limit2GB và threads2 giữ nguyên; không dùng thêm bộ nhớ bằng cách mở giới hạn.
- Metadata tính bảngteam theo(match_id,team_id) rồi tổng hợp sốđội/độimâu thuẫn; roster, ngày khácnhau, party_size khácnhau tính riêng; LEFT JOIN các bảng nhỏ về tập trận. NULL không bị đếm như giátrị distinct; nhóm không cóteam/date/party hợp lệ nhậncount0 như trước. Không lọc target trước roster/durationproxy.
- Dedup/conflict/filter/lineage và côngthức row_id giữ nguyên. Drop exact/conflicts sau khi không cònconsumer; assigned làview thay vì bảncopy rộng. Toàn cleaned/metadata/split vẫn được xuất/kiểm theo canonical contract; provenance s02_execution.json ghi layout và actual SQL limit/threads.
- Giữ chữký băm mọi src/runtime, kiểmstale và bảo vệ working. Chưa có migration từ5.5; không sửa checksum/status để ép reuse. Working5.6 riêng, codeZIP và notebook cùng sourcechecksum. Reuse S01 chỉ được kiểm trong cùngbản; chưa hứa bảo toàn signature xuyênversion dù ingest không đổi.
- Requirements thêm nbconvert7 tươngthích nbclient mới do lỗi môi trường người dùng cungcấp. Không tự chỉnh pandas/requests/jupyter-server để chạy theo yêu cầu google-colab ngoàipipeline.
- Các kiểm local/null/conflict/split/parity và synthetic lowmemory được ghi vào hai CHANGELOG. Test truyvấn metadata1.2triệudòng không chứngminh toànS02/fullsource hoặc peakRAM thực; actualKaggle/full-data và tiếtkiệm tài nguyên toànpipeline còn mở.

## XVII. Triển khai D2, S03-S04 trên đĩa, ngày 19/10/2026

Đợt5.7 thực hiện OOC-03/OOC-04 sau D0-D1. Đây là thay đổi tổ chức thực thi, không đổi protocol nghiên cứu trong IV-VIII; D3-D6 vẫn mở.

- S03 dùng database tạm trên đĩa, metadata projection hẹp. Kiểm unique match_id và match thiếu metadata trước publish; đối soát số dòng sau JOIN. Tất cả feature/target/flags/lineage/kiểu dữ liệu/missing rule giữ nguyên; một lượt aggregate lấy mọi cột validation thay nhiều lượt quét.
- S04 chia events/metadata/base bằng cùng quy tắc first16hex(SHA256(coalesce(match_id,''))) dưới dạng uint64 moduloP, mặc địnhP=16. Hash chỉ chọn phần; mọi dedup/JOIN dùng khóa gốc đầy đủ, không coi hash collision là cùng thực thể. Giữ canonical event fields và toàn bộ raw_ fields trong dedup, nên sự kiện khácvictim/raw không bị gộp dù cùngkiller/time; replay xuyênshard cùng nội dung chỉ tính mộtlần. EventNULL/orphan vẫn góp audit theo quy tắc cũ, không bị vứt sớm để dễ chia.
- Mỗi nguồn ghi các phần bằng một COPY PARTITION_BY, giới hạn16file mở và rowgroup8192 cho writer phân vùng. Mọi dòng cùng trận luôn ở cùng phần, gồm metadata durationproxy từ roster trước task exclusions. Tính exact count/min/sum/phase theo match/killer trên database đĩa, JOIN base cùng phần, validateParquet/rows trước-sau, rồi ghép các phần thành canonical player_match.parquet sau khi toàn bộ phần đạt. Không fit estimator riêng từng phần.
- Giữ absolute eligibility khi event vượtproxy hoặc duration<60; giữ biênpha, mẫu sốphasevalid, confirmed_no_kill/event_missing/absolute_only, has_kill theo aggregate và structuralmissing. Auditglobal cộng các count phân vùng rời nhau, không lấy mean-of-means hoặc trungbình ratio. Công thức feature/target/split/per_mode/KMeans/OLS/G4/metrics/haiGPU không đổi.
- timing_partition_audit.csv ghi events/unique/eligible và bảo toànrows từngphần; s04_execution.json ghi quy tắc/layout/bytes trước dọn. Bytes này không phải peaktemp/RSS, không gồm mọi spill/databasefile. File tạm của lượt chạy được đóng/dọn kể cả lỗi; không xóa raw/canonical tốt hoặc file không thuộc lượt chạy.
- Đánh đổi: thêm lượt ghi/đọc và bản sao tạm trên runtime disk, không hứa tăngtốc. Chưa tự tách phần lệch hoặc checkpoint từngphần; một phần/trận quálớn vẫn có thểOOM, hủy giữa phần phải chạy lạiS04. Giữ giới hạnSQL2GB/threads2 và outputbudget18GiB, chưa chứngminh đủ đĩa/Kaggle/fullsource.
- Chữký conservative vẫn băm toànsrc/runtime và toàntiming trongS03/S04. Đổi partitions làm staleS03, phải chạy lại producer; không giảsignature/status để ép reuse. Chưa có migrationS01 từ5.6; rootv57 mới, notebook/ZIPsourcehash phảikhớp và không cập nhật nóng phiên đang giữ output chưa bảo vệ.
- Tests có oracle5.6 đóngbăng chỉ trong thưmục kiểmthử, không là nguồn côngthức production hoặc thànhphần ZIP. Kiểm exactschema/rowIDs/NULL/flags/counts và double tolerance cốđịnh rtol=atol=1e-12 trên fixture adversarial, partition1/2/7/16, emptyinput/emptybase, metadata sai, failure/retry và SQL128MiB. Đây không là nghiệmthu CUDA hoặc sốliệu nghiêncứu PUBG.
- Kiểm mở rộng downstream còn sai khác Davies-Bouldin Solo/K3 khoảng2.35e-9 vượt ngưỡng rtol1e-9/atol1e-10 đã đặt;10bảng phân tích còn lại,14predictions, labels/centers và K từ silhouette đạt trên fixture. Giữ kết quả kiểm không đạt của chỉ số đó, chưa đóng toàn OOC-Q3, không nới ngưỡng hoặc làm tròn để gọi tương đương. Sai khác profile nhỏ do thứ tự/số học là giả thuyết cần kiểm tiếp ở D4; không dùng59tests unit/integration đạt làm chứng minh mọi chỉ số downstream giống nhau hoặc mọi nguồn thật sẽ chạy.

## XVIII. Triển khai D3, thống kê toàn cục trên đĩa, ngày 19/10/2026

Bản5.8 thực hiện OOC-05/OOC-06, chỉ đổi tổ chức tính toán S05-S06. Không đổi cohort, feature, target, split, leakage, protocol lựa chọn hoặc estimator. D4-D6 và kiểm số học Davies-Bouldin ở mụcXVII vẫn mở.

- S05 dùng database tạm trên đĩa. Count/mean/std/min/max/skew/zero của 21 cột lấy trong một lượt aggregate có trạng thái nhỏ; vẫn dùng kernel DuckDB cũ, sample std và predicate valid_survival riêng cho thống kê target survival. Không thêm lọc finite/target/missing khác hoặc lấy mẫu để giảm bộ nhớ. Placement và các cột khác giữ predicate cũ.
- Median/q25/q75 vẫn exact Type-7 trên toàn cột non-NULL thuộc đúng scope. Với phân vị $p$, vị trí tính từ0 là $h=(n-1)p$; dùng row_number sau global sort để xác định hai đầu mút. Kernel quantile_cont gốc nhận tối đa hai giá trị và phần nội suy tương ứng, nên không giữ vector quantile toàn cột trong aggregate; không dùng trung vị từng batch, sketch hoặc phép tính xấp xỉ. Bảng ordinal/value đặt trên đĩa và dọn sau cột cuối cùng dùng nó. Histogram dùng lại min/max exact đã tính, giữ 30bin, mẫu số và units.
- S06 materialize riêng các cặp x/y hữu hạn theo từng feature-target-mode và target-validity ở train+validation. Global value counts rồi cumulative sum tạo average rank cho ties: $r(v)=N_{<v}+\frac{N_v+1}{2}$. Mọi tie trên đúng cặp được xét chung, không rank theo partition hoặc tái dùng rank y trên cohort khác. Giữ corr(x,y) cho Pearson và corr(rank_x,rank_y) cho Spearman, không trung bình hệ số lô. JOIN hạng x rồi y thành hai bước riêng, đối soát N sau mỗi JOIN, dọn trung gian hết consumer. Empty/constant giữ undefined/NA, không thay0 hoặc clip hệ số.
- Main tables và plot sources giữ schema/names/scope/units/primary flags. s05_execution.json/s06_execution.json và progress từng cột/cặp chỉ thêm provenance vận hành, không là checkpoint bền vững hoặc measured peak. Giữ report_only chỉ đọc và raw bất biến.
- Cấu hình SQL2GB/threads2, matrix policy, outputbudget18GiB, haiGPU S07/S08, KMeans per_mode và OLS SVD không đổi. Temporary database/sort spill ngoài working nhưng vẫn cần RAM/đĩa; tăng I/O có thể chậm hơn. Chưa resume riêng cột/cặp, chưa chứng minh đủ ngân sách toàn nguồn. Source/config đổi làm checkpoint trước5.8 stale theo guard cũ; rootv58 riêng, không migration/checksum/status giả.
- Kiểm tham chiếu5.7 đóng băng chỉ ở tests, không xuất trong gói production. Quantiles so exact; scalar moments/correlations double với rtol1e-10/atol1e-12 đặt trước trên fixtures, counts/schema/NULL/flags theo contract. Có SciPy Spearman độc lập, null/ties/constant/empty/singleton/integer/extreme/nonfinite, test-only mode/outcome, all-missing, failure/retry và stress SQL64MiB. Đây không là kết quả nghiên cứu PUBG hay actualCUDA; kết quả kiểm/benchmark cụ thể ở kế hoạch mụcXII.13 và nhật ký.

## XIX. Triển khai D4, luồng dữ liệu mô hình, ngày 19/10/2026

Bản5.9 thực hiện phần giảm bản sao trong OOC-07/OOC-08. Không đổi công thức profile, cohort, feature, target, split, G4, lựa chọn K, estimator hoặc solver. Không lấy mẫu để fit. D5-D6, CUDA thật và toàn nguồn vẫn cần kiểm riêng.

- S07 tổng hợp profile trên database tạm trên đĩa, giữ đầy đủ player-mode trước fit; collect toàn profile vẫn có cổng RAM, không gọi là hoàn toàn ngoài RAM. Không giữ các nhãn đầy đủ của mọi seed khi ARI chỉ cần mẫu diagnostic đã đăng ký; seed đầu vẫn giữ nhãn toàn bộ cho DB/kích thước cụm. Các lần fit, seeds/n_init và silhouette không đổi. Dữ liệu kết quả từng mode lưu Parquet tạm, đọc một mode khi xuất; reload model dự đoán theo lô50000.
- Đính chính số học Davies-Bouldin ởXVII: khoảng cách theo norm/dot có cancellation (mất chữ số khi trừ các số gần nhau) tại điểm gần tâm cụm. Tính trực tiếp hiệu tọa độ, chuẩn Euclid và trung bình khoảng cách trên toàn profile, float64 theo lô; giữ nguyên định nghĩa chỉ số và quy tắc suy biến. Có oracle Decimal60chữ số, không làm tròn/nới tolerance để giống số cũ sai số học. DB chỉ dùng báo cáo; K vẫn chọn theo silhouette. Vì đây là sửa độ ổn định phép tính, số DB có thể khác bản5.8, không khẳng định bitwise parity của chỉ số cũ.
- S08 tạo một bộ float64 X/y trên đĩa dạng memory map (ánh xạ file để đọc phần cần thiết) cho mỗi task/split. Khóa chuỗi tách sang Parquet, không gửi DataFrame có tên người chơi tới worker; chỉ gửi đường dẫn nhỏ. SQL ghi theo lô50000 với row_id tăng/unique/nonnull, đủ số dòng, target hữu hạn; cohort hash giữ cách tuần tự hóa cũ. T0/P2 kiểm cùng rows/hash trước fit. Quantile error bins vẫn exact trên toàn target train.
- Vẫn một Pipeline.fit đầy đủ cho mỗi bảy thí nghiệm: log, mean imputer/missing indicators/keep_empty, StandardScaler train-only và baseline mean/median hoặc OLS hiện hành. Không đổi float32, partial_fit, SGD, solver hoặc distributed fit. Memory map không ngăn estimator copy toàn ma trận; dự toán host/VRAM và cổng từng fit vẫn giữ. Hai GPU chỉ thực thi các fit độc lập.
- Validation/test transform/predict/reload theo lô, ghi Parquet tạm; worker trả đường dẫn, không trả DataFrame dự đoán toàn tập. Kiểm schema/dtype/shape, checksum metadata, row IDs/target/cohort và reload trước publish. Không mở test trước G4; validation cache vẫn kiểm chữ ký/checksum và không refit khi chỉ duyệt G4. TemporaryDirectory đóng/dọn file sở hữu sau thành công/lỗi; raw/output tốt không bị xóa để giải phóng RAM.
- Metrics micro/match/team còn đọc một prediction frame đầy đủ và được tính vào dự toán RAM; S09 vẫn cần D5, không nhận đã streaming metrics. S07 còn collect profile, một fit có thể vẫn quá RAM/VRAM. Không thay protocol nếu cổng tài nguyên chặn; cần quyết định riêng cho solver/estimator khác.
- Source/config mới vẫn làm checkpoint cũ stale; rootv59 riêng, notebook/code ZIP cùng hash. Không có migrationS01 từ5.8, không sửa manifest/checksum để reuse. Kết quả local/parity/failure/đóng gói ghi nối tại kế hoạchXII.14 và hai CHANGELOG, không là chứng minh Run All nguồn thật.

## XX. Triển khai D5, đánh giá trên đĩa và snapshot, ngày 19/10/2026

Bản5.10 thực hiện OOC-09..11. Giữ toàn bộ cohort, công thức MAE/RMSE/R2, trọng số theo trận, target đội, bảyfit/T1alias/G4/seed/estimators và quy tắc không clip dự đoán. Đây là thay đổi vận hành và ổn định số học, không đổi câu hỏi nghiên cứu hoặc lấy mẫu kết quả chính.

- S08 đọc prediction Parquet qua database tạm trên đĩa để tính metrics; không collect toàn prediction frame. Micro tính trên tất cả dòng. Match-aware lập count trên đúng cohort rồi dùng trọng số nghịch số dòng trận; team-aware kiểm target nhất quán và team ID không thiếu trước lấy trung bình dự đoán theo đội. Không lấy trung bình RMSE/R2 từng lô, không đổi mẫu số. Kiểm input hữu hạn, row IDs unique/nonnull và match IDs hợp lệ; dữ liệu hỏng bị lỗi, không drop ngầm.
- Phép tính dùng tổng có bù sai số và hai lượt toàn cục, trừ anchor trước tính variance để tránh mất chữ số ở target có offset lớn. R2 target hằng hoặc n<2 vẫn NA có lý do; min/max cũng kiểm hằng thật thay vì nhận variance giả do rounding. Có đối chiếu Decimal60digits cho số lớn/hằng. Có thể khác vài chữ số cuối so phép cộng cũ; không làm tròn hoặc nới tolerance sau khi thấy số.
- S09 dùng database đĩa để kiểm unique row IDs từng nhánh, đủ toàn bộ IDs, identity/target/split khớp chính xác trước JOIN/metrics. Không intersect để che dòng mất. SQL JOIN có thể spill theo backend, không tuyên bố tự viết sort-merge. So sánh T0/T1 vẫn candidate-reference trên cùng cohort. Error slices giữ mode và các biên target từ train, histogram giữ biên/nhãn pandas.cut, không cắt cực trị.
- Bootstrap nếu bật giữ default_rng/seed, cùng resample IDs trận có hoàn lại và multiplicity hai nhánh. Chỉ đưa vectors trạng thái numeric từng trận vào RAM có guard, không full prediction rows. Variance tính within/between quanh anchor để tránh cancellation; constant replicate có R2NA, valid_replicates thật. Type-7 nanquantile và mức2.5/97.5% không đổi; thiếu CI không tuyên bố significance. Không thêm bootstrap mặc định khi chưa được chọn.
- Plot sample vẫn tối đa1500 dòng, cùng RandomState/seed/quy tắc uniform without replacement và thứ tự file vật lý như pandas.sample bản cũ. Đọc Parquet projected ba cột theo lô50000; giữ workspace chỉ số O(N) có guard để không âm thầm đổi sample. Đây chỉ là mẫu vẽ, không mẫu fit/metrics; không gọi toàn bộ S09 có bộ nhớ hằng. S00 resource_plan chỉ đọc counts/khóa, không đọc giá trị test target, và dự toán cả workspace plot/bootstrap khi đi tớiS09.
- S10 inventory đầy đủ bytes/hash, tính cả JSON manifest/pointer và dự phòng1MiB trước tạo snapshot. Copy vào thư mục staging sở hữu cùng filesystem, kiểm checksum/giải mã Parquet/load_release rồi rename snapshot UUID mới; publish final_results pointer cuối. Lỗi copy/readback dọn staging, giữ release/pointer cũ. Nếu lỗi pointer sau rename, snapshot đầy đủ nhưng chưa được trỏ tới có thể còn; không là completed hay tự được xóa. Không ghi đè/xóa release cũ hoặc raw/canonical để cứu budget.
- Loader giữ format1, kiểm checksum/bytes/duplicate/unsafe paths, đọc giải mã Parquet theo lô và đối chiếu đơn vị. Coverage metricsCSV đọc chunks50000 chỉ ba cột; display preview dùng nrows25, không fullCSV.head. report_only không raw/fit/build/download/write; local snapshot readback không chứng minh Kaggle đã lưu Version.
- Mỗi database đĩa có thư mục spill riêng bên trong thư mục tạm sở hữu, không dùng chung tên file spill giữa hai instance DuckDB. Kiểm bổ sung sau lượt87tests phát hiện native crash khi reader ngoài vẫn cần spill còn kết nối trong ghi/đóng cùng file tạm. Đã tách scope mỗi connection, không tăng memory_limit hoặc đổi query/công thức; có subprocess probe tái hiện và đọc đủ IDs sau khi kết nối trong đóng. Folderdatabase/spill cùng được dọn sau đóng connection, không xóa raw/canonical.
- Cấu hình khoa học/nguồnVersion3/assumed_seconds/haiGPU/SQL2GB/threads2/output18GiB giữ nguyên ngoài version/rootv510. Chữ ký mọi src/runtime vẫn conservative, chưa migrationS01 từ5.9. Một fullprofile/fullKMeans/OLS vẫn có thể không vừa RAM/VRAM. D6/actualCUDA/Kaggle/fullsource còn mở; nghiệmthu và hash gói ghi nối tại kế hoạchXII.15/haiCHANGELOG.

## XXI. D6: ranh giới nghiệm thu, ngày19/10/2026

D6 kiểm xuyên suốt và đóng gói, không thay protocol hoặc code production5.10. Bộ kiểm mới dùng ba mode/Unicode/replay/conflict/target lỗi, toàn chuỗi S01-S10, restore/reuse/report_only và ngắt thật tiến trình giữa partition. Tham chiếu ghép các helper đóng băng5.6-5.9; ingest/S02 vẫn có phần dùng chung nên không gọi đây là oracle độc lập cho mọi phép tính. Davies-Bouldin kiểm Decimal60 riêng, không nhận số cũ có cancellation làm tiêu chuẩn tuyệt đối. Exact keys/cohort/schema/NULL/flags và tolerance số thực được đăng ký trước, không nới sau kết quả.

Giữ một notebook48cells/16code và sourcechecksum5.10. Tests/tài liệu không nằm trong signature mã nguồn stage, không đổi version/root hoặc cố ý làm S01 stale chỉ để ghi tên D6; vẫn không có migration qua các bản src khác. Ngắt tiến trình có thể để running/lock/scratch dở, không completed hay tự reuse phần chưa commit. Takeover chỉ sau xác nhận tiến trình trước đã dừng; S04 chạy lại toàn stage, không nhận có partition checkpoint hoặc tự dọn an toàn mọi scratch cũ.

Q6/actualT4x2/nguồn PUBG tăng quy mô và toàn nguồn phải có evidence thực riêng. Mốc small/medium chỉ kiểm vận hành trên trọn trận/roster/events, scope rõ và không thay main full cohort. Không chọn/lọc/tune theo test outcomes để đạt tài nguyên. Local CPU/mock/RTX3050 đơn lẻ, số tests hoặc GPU smoke48dòng không đóng được các cổng nguồn thật. Trạng thái/kết quả/log và cổng còn mở ghi tại kế hoạchXII.16/haiCHANGELOG; không gọi D6 hoặc nghiên cứu chính hoàn tất khi thiếu nghiệm thu nguồn thật.

## XXII. Layout chuẩn hóa5.11, người dùng chọn hướng1 ngày20/10/2026

Ảnh thực tế S02 cho project18.018GiB/budget18/free1.484, cleaned10.681GiB bên cạnh S01aggregate3.173/event4.163. Đây là lỗi lưu trữ ở guard sau publish cleaned, không phải chứng minh hết RAM hoặc tăngGPU giải quyết được. S01completed, S02resource_limited; không nhận cleaned dở là stagecompleted.

Chỉ thay layout/producer compatibility, không RQ/cohort/rowIDs/flags/rawcolumns/lineage/feature/target/split/leakage/OLS/KMeans/G4/metrics/seeds/float64. S01 giữ đầy đủ typed/raw. S02 lưu các source_file/source_row được chọn theo exact-dedup/identity/filter cũ; JOIN tái dựng schema sạch cũ, split/mode/row_id giữ công thức và mapping đã khóa. Base là recipe công thức canonical, player_match ghép base với timing states theo match/killer; discrepancy là projection logic. Descriptor chỉ cho các recipe cố định, không thi hành SQL tùy ý. Mọi physical input/descriptor vẫn phải thuộc artifact/dependency được checksum; huấn luyện cache băm toàn cây đầu vào, không chỉ metadata descriptor.

Prediction pool có thứ tự position tường minh, lưu row_id/match/team/mode/split/actual một lần mỗi cohort; mỗi experiment lưu position/predictedfloat64 và nhãn hằng ở metadata. Trước publish kiểm exact identities/actual/constants theo lô; khi đọc kiểm checksum pool/count/schema/vị trí liên tục/finite. Không ghép bằng giao IDs, không đổi mẫu vẽ/RNG hoặc giảm precision. Release snapshot copy cả pool/values bất biến, không hardlink canonical vào release; report_only chỉ đọc, không cần raw hoặc ghi lại frame rộng.

Import S01 là thao tác tường minh chỉ từ producer5.10/sourceSHA71de81ca811d4d66ebb1c432c56a370c12fb48e41411adee5996eb436af23690. Kiểm codeproducer, ASTingest/constants/writer, requirements/software/source/version/license, signature/checksum/giải mãParquet; chỉ sau đó tạo S01signature hiện hành với producer_import giữ dấu vết cũ và recomputedFalse. Dùng hardlink cùngfilesystem, không largecopyfallback. Không import S02failed hoặc tự xem dữ liệu cũ tương thích chỉ vì filename trùng. Rootv511 riêng; source/schema/parser có thay đổi ngoài proof phải từ chối, không sửa checksums để ép reuse.

CLEANUP_IMPORTED_510=False mặc định. Chỉ sau importS01đạt và operator chủ động xác nhận mới bỏ exact file cleaned của S02failed và tên hardlink aggregate/event cũ nếu vẫn cùnginode với S01 giữ tại rootmới; không writerlock/downstreamcompleted/symlink hoặc filefailed được completedcheckpoint sở hữu. Không xóa raw Input hay recursive root; rawS01 bytes giữ ở rootmới, rootcũ nghỉ dùng. Cleaned dở chỉ dựng lại được từS01, hardlink không là backup độc lập. Không sửa nóng project hoặc xóa dữ liệu Kaggle thật trong lượt triển khai local.

Giữ budget18GiB, SQL2GB/threads2 và haiGPU. Chuẩn hóa giảm bản sao nhưng thêm JOIN/đọc lại và không bảo đảm đủ dung lượng/host/VRAM cho nguồn thật. Phải kiểm parity/lowmemory/failure/import/restore/read-only/package và đo dung lượng riêng; không suy từ fixture hoặc helperbenchmark thành full-data/CUDA acceptance. Kế hoạchXII.17/haiCHANGELOG ghi evidence và giới hạn.

## XXIII. Biến thể Colab Pro được yêu cầu ngày20/10/2026

Yêu cầu mới cho phép thêm notebooks/PUBG_COURSEWORK_COLAB.ipynb bên cạnh notebook Kaggle canonical, thay giới hạn một file chỉ cho trường hợp Colab này. Không thêm thí nghiệm hoặc bộ công thức khác. tools/build_colab_notebook.py lấy các section khoa học S01-S10 của canonical, đóng kèm 12module src5.11/config/requirements/đặc tả (15file), không cần Dataset code hoặc token chứa trong notebook. Không chứa raw/model/output cũ. SourceSHA4e3f9a19 giữ nguyên; chỉ adapter môi trường/nền tảng ở tools và notebook mới.

Colab dùng GPU0 tường minh với cùng cuML KMeans/OLS và bảyfit; không đòi haiT4 hoặc fallback CPU. Đổi số GPU là thực thi tuần tự các fit độc lập, không đổi estimator/solver/cohort/split/seed/feature/target/metric/G4/precision. Môi trường CUDA/driver/cuML/Python phải qua kiểm và smoke; việc notebook tạo được hoặc CPU fixture đạt không chứng minh actualColab GPU/full-data. Cài dependencies trước raw, khi đổi thư viện phải restart session, không xóa VM. Cố định cuML/cuDF26.2.* và CuPy13.6 đến trước14 cho đúng cu12/cu13; metadata PyPI26.10 yêu cầu pandas3 nên không tương thích core pandas<3. Metadata26.2 yêu cầu pandas2.0 đến trước2.4, giao với core>=2.2/<3; không sửa core requirements để đuổi phiên bảnGPU. Record software của core vẫn chặn reuse không tương thích; chưa chứng minh Linuxpipresolver thực đã chạy.

Nguồn Kaggle chỉ skihikingkevin/pubg-match-deaths/versions/3 đã được cho phép, tải bằng kagglehub.dataset_download với handle có version, cache/runtime riêng. Không gọi latest hoặc dataset_load để nạp CSV toàn bộ vào RAM. License/mapping/assumed_seconds giữ evidence và giới hạn cũ, không nâng thành verified. Public dataset thử không đăng nhập; khi cần chỉ dùng Secrets/login của Kagglehub, không ghi/in token trong notebook/config/Drive.

Mặc định project mới /content/drive/MyDrive/PUBG_Coursework_Colab_v511 lưu trực tiếp canonical Parquet/checkpoint/model/release; raw/cache/SQL/spill/matrices ở runtime. Không sao toàn project sau mỗi stage; Drive đọc nhiều JOIN có thể chậm, không hứa nhanh hơn Kaggle. USE_GOOGLE_DRIVE=False chỉ lưu runtime và cảnh báo mất khi VM bị thu hồi. Giữ output18GiB/SQL2GB/threads2/batch50000; dự phòng55GiB ổ runtime trước tải và hướng dẫn người dùng tự kiểm quota Drive khoảng25GiB, không gọi đó là quota dịch vụ đã xác minh hoặc Colab Pro cấp sẵn.

Resume dùng đúng root Drive, rawVersion3 và software/source/config/signature/checksum tương thích. Kiểm completed bằng candidateconfig trước ghi thay thế config, không ép checksum/completed hoặc tự takeover lock. Stage dở vẫn phải chạy lại; hard reset/phiên mới có thể cần cài/tải lại raw, không có resume giữa fit. HandoffColab ghi platform rõ và kiểm file qua mount, không tạo Kaggle Version reference giả. Mounted-file checksum/read-back không xác nhận đồng bộ máy chủ Google hoặc backup độc lập; một writer/root. report_only không giải nén/cài/downloadraw/prepare/copy/train/ghi project, chỉ dùng code/môi trường đã chuẩn bị và release cụ thể, mount Drive để đọc nếu cần.

Các thay đổi này không di chuyển/xóa dữ liệu Kaggle/Drive thật. Trạng thái kiểm/notebook/hash/giới hạn ghi ở PLANXII.18 và hai CHANGELOG. Colab Pro không bảo đảm GPU/RAM/runtime cụ thể; fullfit có thể vẫn thiếu tài nguyên, không lấy mẫu hoặc đổi thuật toán để gọi là full.

