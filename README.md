# PUBG — Weapon Type Prediction

Pipeline phân loại nhóm vũ khí từ ngữ cảnh pha hạ gục và lịch sử nhân quả trong trận theo [plan.md](plan.md). Mỗi mẫu là một sự kiện; chia train/validation/test theo trận, chọn mô hình bằng **macro-F1 trên validation**. [Báo cáo nâng cấp lịch sử nhân quả](reports/HISTORY_UPGRADE.md) ghi kết quả local/Kaggle và bundle train dài đã chuẩn bị.

Kết quả cuối đã có: [báo cáo train dài và holdout](reports/HISTORY_FULL_FINAL_RESULTS.md), [bộ bảng/hình ZIP](reports/pubg-final-results-20261022.zip). Kaggle version 1 đã chấm holdout một lần trên 484.074 sự kiện: Macro-F1 0,4219 (CI 95% [0,4201; 0,4236]). Xem báo cáo để biết Accuracy/baseline, ablation và giới hạn; không chạy lại evaluation của run đã khóa.

## Cài đặt và kiểm tra

Python >=3.11, khuyến nghị 3.11/3.12 để tương đồng môi trường Kaggle. Đã có test cho cleaning, mapping, đặc trưng, lấy mẫu theo trận, chia tập, giới hạn train, cả sáu họ mô hình, tuning đầy đủ trên dữ liệu tổng hợp và toàn bộ luồng đánh giá.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

Các dependency có giới hạn phiên bản; metadata mỗi run lưu phiên bản thực tế. Kết quả test local mới nhất ở `reports/local-plan-update-tests-20261021.xml`; kết quả chạy Kaggle nằm trong output kernel và bản tải về ở `artifacts/`.

## Cấu trúc

```text
configs/label_mapping.json       Mapping tên vũ khí thật → nhóm; null = loại
scripts/01_eda.py                Đọc chunk, lấy mẫu theo trận, audit và EDA
scripts/02_preprocess.py         Làm sạch, chia tập, gộp lớp hiếm, tạo đặc trưng
scripts/03_models.py             Fit, tuning, ablation, chọn bằng validation
scripts/04_evaluation.py         Đánh giá test cuối, xuất bảng và hình
scripts/05_diagnostics.py        Phân tích validation, train gap và kiểm tra xáo nhãn
scripts/06_rf_regularization.py  Đối chiếu 8 cấu hình chống overfitting cho RF trên validation
scripts/build_kaggle.py          Đóng gói source + test thành private CPU kernel
src/pubg_weapon/
  config.py                     Đường dẫn, mặc định, cột dữ liệu và nhóm đặc trưng
  io.py                         Chunked CSV, parquet, checksum, manifest
  eda.py                        Audit dữ liệu; EDA theo nhãn chỉ trên train
  preprocessing.py              Mapping nhãn, cleaning, đặc trưng và điều phối bước 02
  splits.py                     GroupShuffleSplit; giảm mẫu train theo lớp
  models.py                     Estimator, trọng số lớp làm dịu và sklearn Pipeline
  training.py                   Tuning và khóa danh sách thí nghiệm
  evaluation.py                 Test một lần, CI, bảng/hình và importance
  bootstrap.py                  Bootstrap theo trận, so sánh cặp dùng chung mẫu
  error_analysis.py             Trung vị khoảng cách, macro-F1 theo tầm, lớp Other
  diagnostics.py                Phân tích validation, train gap và kiểm tra xáo nhãn
  rf_experiment.py              Thực nghiệm sub-bootstrapping, tempered weights và OOB cho RF
kaggle/runner.py                Chạy test và pipeline trong Kaggle
tests/                          Unit test và kiểm tra đầu cuối
```

CSV nguồn ở `data/raw/`; dữ liệu trung gian ở `data/interim/`; các tập train/validation/test ở `data/processed/`; pipeline và manifest huấn luyện ở `artifacts/`. Các file dữ liệu và model lớn được gitignore. `reports/` giữ tài liệu và bằng chứng kiểm tra nhỏ. Source cũ đã xóa không được khôi phục.

Các script `build_kaggle.py` và `build_appendix_kaggle.py` là mã nguồn đóng gói; chỉ đầu ra trong `artifacts/` được bỏ qua. Theo cấu hình Git hiện tại, `kaggle/` và `tests/` là thư mục cục bộ: cần cung cấp chúng riêng nếu tạo bundle từ một bản clone mới.

## Chạy bốn bước

Mỗi `--output` phải là **thư mục mới** để tránh ghi đè. Các script chạy được từ checkout mà không cần cài package editable; các dependency vẫn phải được cài.

```bash
python scripts/01_eda.py \
  --source data/raw/kill_match_stats_final_0.csv \
  --output data/interim/run01 --matches 50000

python scripts/02_preprocess.py \
  --eda data/interim/run01 --output data/processed/run01 \
  --max-train-rows 1000000

python scripts/03_models.py \
  --processed data/processed/run01 --output artifacts/run01 --jobs 2
```

Bước 01 đọc toàn bộ danh sách match_id, chọn ngẫu nhiên với seed mặc định 42 rồi đọc lại CSV để giữ **toàn bộ sự kiện** thuộc các trận đã chọn. Lượt đọc đầu đồng thời kiểm kê toàn bộ tên killed_by của chunk, lưu `source_weapon_counts.csv`; preprocessing kiểm tra mapping với toàn bộ danh mục này trước khi train. Chỉ dùng 12 cột trong deaths, không cần aggregate. Không tải dữ liệu tự động khi import hoặc chạy test.

Bước 02 loại killer thiếu/placeholder, tự hạ gục, vị trí (0,0), tọa độ/thời gian không hợp lệ, bản ghi trùng và identity/map không hợp lệ; sau đó loại nhãn null. Mỗi bước có số lượng/tỷ lệ dòng bị loại, và breakdown nguyên nhân gốc. Nhãn bị loại còn có bảng `excluded_label_counts.csv` riêng với mẫu số nguồn/sample tường minh. Loại trùng trên toàn tập lấy mẫu nên bắt được trùng giữa các chunk. Gộp lớp dưới 1,0% dựa **chỉ trên train**, rồi áp dụng nguyên quy tắc sang validation/test. Nhãn không có trong mapping sẽ báo lỗi.

Chia 70/15/15 theo match_id bằng hai GroupShuffleSplit trên **toàn bộ danh sách trận của nguồn**, trước khi lấy cohort; lưu `source_match_splits.csv`. Mọi cohort nhỏ/lớn từ cùng nguồn dùng lại cách chia này, nên một trận không chuyển từ train/validation sang test khi tăng số mẫu. `configs/development_matches.csv` giữ 2.294 trận đã dùng trong pilot cũ, bao gồm local và Kaggle; chúng bị loại khỏi danh sách ứng viên test cuối. Không đổi registry/seed chia sau khi bắt đầu thí nghiệm. Mỗi cohort lưu thêm `split_manifest.csv`; tỷ lệ trận trong cohort xấp xỉ 70/15/15. Dữ liệu theo cách chia cũ bị từ chối khi huấn luyện/đánh giá test.

Tạo sáu đặc trưng lịch sử trên toàn bộ sự kiện hợp lệ của từng trận, sau khi áp dụng nhãn hiệu lực. Chỉ dùng sự kiện có `time` nhỏ hơn nghiêm ngặt; các mạng cùng giây không thấy nhau. Vũ khí gần nhất dùng mode, khoảng cách gần nhất dùng trung bình của giây trước đó; hòa mode lấy tên nhóm theo thứ tự chữ cái. Lịch sử không nối qua trận hoặc người chơi. Manifest ghi `history_policy`; dữ liệu processed cũ phải được tạo lại.

Sau đó chỉ giảm số dòng train theo tỷ lệ lớp, vẫn giữ ít nhất một dòng mỗi lớp. Validation/test giữ phân phối tự nhiên. Sai lệch phân phối giữa các split được báo trong `split_class_distribution.csv` và manifest. Mọi bước lấy mẫu/chia tập dùng seed 42. Pilot mặc định 3.000 trận; cohort 2.000 trận cũ với seed 42 chỉ chứa các trận development nên không phù hợp để dựng đủ ba tập. Nếu cohort không có đủ split, tăng số trận thay vì đổi seed.

Bước 03 dùng sklearn Pipeline để fit imputer/scaler/encoder chỉ trên train. Tên người chơi, killed_by, target và match_id không vào X. One-hot xử lý category chưa thấy; output dense dùng được với GaussianNB và HistGradientBoosting.

Mọi lượt fit, kể cả cấu hình không được chọn, được lưu trong `trials.json`. Readiness kiểm tra cảnh báo hội tụ/tính toán số trên toàn bộ các lượt này. Mỗi lượt ghi thời gian và RSS cao nhất của tiến trình; RSS là mức đỉnh tích lũy, không phải RAM riêng của từng mô hình. Bước huấn luyện cũng kiểm tra lại giao nhau giữa match_id của train/validation.

| Họ mô hình | Cân bằng lớp | Cấu hình đầy đủ |
|---|---|---|
| Majority | Không | Most frequent |
| Logistic Regression | Có | StandardScaler + balanced, tối đa 1500 vòng |
| Gaussian Naive Bayes | Không | Mốc xác suất |
| Decision Tree | Có/không | Depth 12, min leaf 5 |
| Random Forest | Có/không | Tuning hai cấu hình sub-bootstrapping 200/300 cây, depth 18, min leaf 5, max_samples 0.20/0.15 |
| HistGradientBoosting | Có/không | Tuning hai cấu hình 150/250 vòng, learning rate .1/.05, leaf nodes 31/15 |

HGB cân bằng bằng sample_weight tính từ train; Random Forest dùng balanced_subsample. Mỗi họ/biến thể giữ cấu hình macro-F1 validation tốt nhất. Cấu hình `--quick` chỉ còn RF 20 cây và HGB 30 vòng; dùng cho kiểm tra luồng, không dùng làm kết quả cuối.

Mặc định chín biến thể chính dùng `loadout_history` (D: 17 đặc trưng). Ablation giữ cố định họ mô hình tốt nhất trên validation, cùng tham số và cân bằng lớp, chạy A = khoảng cách, B = khoảng cách + time, C = ngữ cảnh đầy đủ (11 đặc trưng), D = C + sáu đặc trưng lịch sử. Có 12 pipeline lưu cuối, 16 lượt fit/tuning trong bản đầy đủ và 12 trong bản quick. `--main-feature-set full` dùng C làm cấu hình chính để so sánh với thí nghiệm cũ; vẫn tạo đủ A–D và yêu cầu processed có lịch sử.

Sau khi đã chốt lựa chọn trên validation, chạy bước cuối một lần:

```bash
python scripts/04_evaluation.py \
  --processed data/processed/run01 --run artifacts/run01 \
  --output reports/run01 --jobs 2
```

Bước 04 kiểm tra checksum dataset và artifact, tạo khóa độc quyền trong run rồi đánh giá test. Chạy lại cùng run sẽ bị từ chối. Nếu bước này lỗi sau khi khóa đã tạo, giữ nguyên bằng chứng và điều tra nguyên nhân; không xóa khóa để thử chọn lại mô hình theo test.

Đầu ra gồm macro-F1 kèm CI 95%, accuracy/weighted-F1, Top-2 Accuracy, Tactical Role Accuracy/Macro-F1, precision/recall/F1 từng lớp, ablation, confusion matrix CSV/PNG, cặp nhãn nhầm kèm khoảng cách trung vị và accuracy/macro-F1 theo bốn khoảng cách. Bootstrap lấy lại toàn bộ trận 1.000 lần, seed 42, dùng chung mẫu cho mọi pipeline. `paired_model_differences.csv` ghi CI của từng hiệu số; `ablation_gains.csv` ghi mức tăng A→B, B→C, C→D. Chỉ kết luận cao hơn khi CI hiệu số không chứa 0. `bootstrap_macro_f1.csv` lưu các lần lặp để kiểm chứng. `history_subset_metrics.csv` tách hai nhóm `has_prior_kill=0/1` cho mọi pipeline, có số dòng, Macro-F1, Accuracy và Top-2. Nhóm rỗng có 0 dòng và để trống chỉ số. Quy chiếu tactical role áp dụng lên nhãn dự đoán: Other/SMG/Shotgun → Close_Range, AR/LMG → Mid_Range, DMR/SR → Long_Range. Các bảng `other_*` phân tích khoảng cách từng nguyên nhân/thành phần và đích nhầm của Other; `cause_for_audit` chỉ là metadata, bị cấm vào X. Dữ liệu processed cũ thiếu cột này phải chạy lại preprocessing trước khi train/đánh giá. Permutation importance của mô hình cây tốt nhất chọn trên validation dùng tối đa 2.000 dòng test, 3 lần lặp; số dòng/phương pháp được lưu trong summary. Không đổi lựa chọn mô hình theo test.

## Chạy thử và chuẩn bị train dài trên Kaggle

Pilot lịch sử theo plan mới (3.000 trận, tối đa 100.000 dòng train, grid đầy đủ, chỉ validation):

```bash
python scripts/build_kaggle.py --owner YOUR_USERNAME \
  --slug pubg-loadout-history-pilot --output artifacts/kaggle-history-pilot --mode pilot
kaggle kernels push -p artifacts/kaggle-history-pilot
```

Chế độ `pilot` chạy một mốc dữ liệu, đủ sáu họ, ablation bốn bậc và diagnostics; không mở test thật. Các kết quả cũ trong `reports/` thuộc cấu hình C/7 lớp, không phải bằng chứng cho D/6 lớp. Không dùng lại bundle cũ cho kế hoạch nâng cấp.


Trước khi đánh giá test cuối, có thể phân tích validation mà không mở test:

```bash
python scripts/05_diagnostics.py \
  --processed data/processed/run01 --run artifacts/run01 \
  --output reports/run01-validation
```

Đầu ra có thêm ablation A–D, CI và hiệu số bằng paired cluster bootstrap 1.000 lần theo trận, Top-2, tactical role và bảng tách theo lịch sử. Đầu ra gồm điểm validation và điểm train trên tối đa 20.000 dòng có giữ tỷ lệ lớp, chênh lệch macro-F1, F1/recall từng lớp, số lần dự đoán từng lớp, confusion matrix cho mọi pipeline, lỗi theo khoảng cách và permutation importance. Pipeline được nạp lại phải tái lập đúng điểm validation; xác suất dự đoán phải hữu hạn và tổng bằng 1. Phép kiểm tra tín hiệu fit cùng cấu hình HGB nhỏ trên cùng dữ liệu với nhãn thật và nhãn xáo trộn; đây là bằng chứng chẩn đoán, không phải điểm test cuối.

Có thể thử riêng hai cấu hình RF đơn giản hơn trên đúng dữ liệu/pipeline pilot đã lưu:

```bash
python scripts/06_rf_regularization.py \
  --processed data/processed/run01 --baseline-run artifacts/run01 \
  --output reports/run01-rf-comparison
```

[Kết quả xử lý overfitting RF trên pilot](reports/RF_REGULARIZATION.md) ghi điểm và đánh giá 8 cấu hình (gồm sub-bootstrapping `max_samples`, làm dịu trọng số lớp `tempered_class_weights` và tập đặc trưng `no_position`). Xuất điểm train/validation, OOB macro-F1, F1 từng lớp và CI hiệu số bằng bootstrap chung theo trận trên validation; không đọc test. Cấu hình sub-bootstrapping tốt nhất (`max_depth=18, min_samples_leaf=5, max_samples=0.15/0.20`) đã được đưa vào grid huấn luyện chính.

Cần Kaggle CLI đã đăng nhập trên máy gửi. Không đóng gói credential. Bundle chỉ chứa package, script, test, mapping và manifest source; không gửi dữ liệu local hoặc `.git`. Dataset Kaggle được gắn trực tiếp, kernel private, CPU, không bật Internet.

```bash
python scripts/build_kaggle.py --owner YOUR_USERNAME \
  --slug pubg-weapon-pilot --output artifacts/kaggle-pilot --mode smoke
kaggle kernels push -p artifacts/kaggle-pilot -t 1800
kaggle kernels status YOUR_USERNAME/pubg-weapon-pilot
kaggle kernels output YOUR_USERNAME/pubg-weapon-pilot -p artifacts/kaggle-pilot-output
```

Pilot chạy toàn bộ test trước, sau đó lấy ngẫu nhiên 3.000 trận từ **toàn bộ chunk 0** và giới hạn 30.000 sự kiện train. Các mô hình được chấm trên validation. Pilot mặc định **không đánh giá test thật**. Test luồng đánh giá cuối dùng dữ liệu tổng hợp riêng. File `smoke/readiness.json` chỉ xuất hiện sau khi tất cả bước thành công, không có cảnh báo hội tụ/tính toán số; cảnh báo thư viện được lưu riêng; nó ghi kết quả, môi trường và hash source.

Để kiểm tra cấu hình đầy đủ ở quy mô vừa trước train dài:

```bash
python scripts/build_kaggle.py --owner YOUR_USERNAME \
  --slug pubg-weapon-diagnostic --output artifacts/kaggle-diagnostic --mode diagnostic
kaggle kernels push -p artifacts/kaggle-diagnostic -t 1800
```

Chế độ `diagnostic` giữ cùng cohort 3.000 trận và cùng validation, chạy grid đầy đủ ở train tối đa 30.000 dòng rồi tối đa 100.000 dòng (nếu cohort ít hơn thì dùng toàn bộ train). Có 32 lượt fit/tuning chính, 24 pipeline lưu cuối và 4 lượt kiểm tra nhãn thật/xáo nhãn; xuất `learning_curve.csv`, phân tích từng lớp, thông tin RAM và `diagnostic/readiness.json`. Không chấm test thật. Bản `full` cũng xuất chẩn đoán validation sau khi train nhưng không chạy lại mốc 30.000 dòng.

Chuẩn bị bản train dài (lệnh build chỉ tạo bundle, chưa chạy trên Kaggle):

```bash
python scripts/build_kaggle.py --owner YOUR_USERNAME \
  --slug pubg-weapon-full --output artifacts/kaggle-full --mode full
# Khi sẵn sàng train:
kaggle kernels push -p artifacts/kaggle-full
```

Full mặc định 50.000 trận, tối đa 1 triệu dòng train và grid đầy đủ. Mặc định vẫn để dành test. Sau khi chốt validation, có thể tải artifact về chạy bước 04 trong đúng môi trường ghi ở metadata. `--evaluate` khi build chỉ dùng nếu muốn khóa toàn bộ lựa chọn trước và thực hiện luôn đánh giá cuối trong cùng kernel. Không chạy full chỉ để kiểm tra cài đặt.

## Phạm vi và cách diễn giải

Mục tiêu là đo thông tin về nhóm vũ khí trong ngữ cảnh sự kiện, không phải xây dựng sản phẩm dự đoán. Điểm yếu vẫn là kết quả nghiên cứu hợp lệ. Kết quả cuối lấy từ test sau khi chốt toàn bộ lựa chọn trên validation.

- Mapping đối chiếu toàn bộ 57 nguyên nhân của chunk 0; nhãn lạ dừng pipeline. `excluded_label_counts.csv` ghi riêng số lượng/tỷ lệ nhãn bị loại trên nguồn và sample, phân biệt số bị loại ở bước nhãn với các bước trước. `cleaning_counts.csv` còn ghi nguyên nhân của từng dòng bị loại theo bước.
- EDA xuất `quality_audit.csv` với số lượng/tỷ lệ map lạ/rỗng và các lỗi khác; `down_and_out_by_map.csv`, `down_and_out_by_phase.csv`, `down_and_out_by_map_phase.csv` mô tả phần Down and Out trước làm sạch.
- Mặc định không dùng thứ hạng cuối trận. Thí nghiệm tùy chọn `03_models.py --with-placement` thêm **cả ba** placement vào B, C và D. Dùng thư mục run/output riêng; bảng metrics và metadata ghi **retrospective**, không dùng kết quả này trả lời các câu hỏi chính.
- Ngoài phạm vi theo plan: k-NN, ROC/AUC, XGBoost/LightGBM, chunk 1–4 và bảng agg. Biến thể tách Melee là tùy chọn, chưa chạy.
- Hạn chế cần giữ khi viết báo cáo: dữ liệu 2017–2018 và cách thu thập thiên về người chơi hạng thấp/trung bình; loại Down and Out tạo thiên lệch về pha chết ngay; bản ghi có thể phản ánh người kết liễu; không nhận diện được đồng đội; Other không đồng nhất; chỉ dùng chunk 0.

Giới hạn hiện tại: input được đọc theo chunk, nhưng cleaning và feature engineering giữ tập trận đã lấy mẫu trong RAM. Với 50.000 trận, cần theo dõi bộ nhớ Kaggle; nếu sample vượt RAM thì giảm `--matches` hoặc triển khai xử lý parquet theo batch trước khi tăng quy mô. Pipeline không có checkpoint/resume giữa các lượt fit; nếu kernel bị dừng, cần chạy lại bước huấn luyện.

## Phụ lục C — chỉ Cross-Validation/Validation

`07_appendix.py` dùng nguyên train/validation và metadata/pipeline đóng băng của lượt full D. Không mở test và không cập nhật lựa chọn bài chính.

- `rf_grid`: GridSearchCV với GroupKFold 3 theo match_id, đủ 12 tổ hợp RF trong plan; 300 cây cố định.
- `hgb_grid`: đủ 12 tổ hợp HGB trong plan; 150 vòng cố định.
- `alpha_placement`: 6 mức alpha trên cả RF/HGB với cùng tham số của biến thể balanced D gốc, so sánh D/D+placement và C→D/D→D+placement trên validation.

Trọng số là `(N/(K*N_c))**alpha`, học trong mỗi lần fit (kể cả từng fold), không normalize/clip. RF alpha=1 dùng trọng số cố định theo lớp của fold, khác balanced_subsample của baseline chính. Các mốc điểm/Pareto trong plan là giả thuyết để đối chiếu, không phải kết quả bắt buộc.

```bash
python scripts/07_appendix.py --processed PATH_TO_FROZEN_PROCESSED \
  --baseline-run PATH_TO_FROZEN_MODELS --section rf_grid --output reports/appendix-rf
```

`build_appendix_kaggle.py` đóng gói một section với kernel_source là full-final version 1; private CPU, Internet tắt. Ba section có thể chạy trong các kernel độc lập. Guard runtime chỉ cho đọc đúng train/validation parquet; checksum pin source version/dataset và phiên bản thư viện. Thí nghiệm retrospective không được dùng làm mô hình tiền nghiệm cuối cùng.
