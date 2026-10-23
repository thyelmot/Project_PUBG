# Nâng cấp lịch sử nhân quả theo plan.md

Ngày 22/10/2026. Trạng thái: đã triển khai và kiểm chứng trên Kaggle; pilot version 1 COMPLETE, readiness passed. Holdout thật chưa được chấm.

## Thay đổi

- Ngưỡng lớp hiếm 1%, tính trên toàn bộ train sau cleaning, trước giảm mẫu. Lịch sử dùng nhãn đã gộp.
- Sáu đặc trưng lịch sử chỉ dùng sự kiện có timestamp nhỏ hơn nghiêm ngặt trong cùng `(match_id, killer_name)`. Cùng giây không thấy nhau; mode hòa lấy thứ tự chữ cái; khoảng cách gần nhất là trung bình ở giây trước.
- Tính đặc trưng trên toàn bộ chuỗi trước khi cap train. Main D có 17 đặc trưng; X không chứa định danh, nhãn hiện tại hoặc placement.
- Chín biến thể chính trên D; ablation A/B/C/D cố định họ, tham số và cân bằng của mô hình tốt nhất trên validation. Full grid có 16 trials, 12 pipeline.
- Top-2, tactical role (quy chiếu nhãn dự đoán) và bảng hai nhóm has_prior_kill. Chỉ số của nhóm rỗng để trống.
- Diagnostics xuất CI Macro-F1, so sánh cặp và C→D bằng paired cluster bootstrap 1.000 lần theo match_id, seed 42. Đánh giá cuối cũng xuất đủ các chỉ số mới.
- Training từ chối processed cũ thiếu lịch sử. Không sửa split/registry hoặc artifact đã khóa trước đây.

## Kiểm tra local

64/64 test pass, không skip; JUnit: `local-history-upgrade-tests-20261022.xml`. Có một cảnh báo joblib về nhận diện CPU trong sandbox macOS. Kiểm tra riêng lịch sử cùng timestamp, không nối qua trận/người chơi, độc lập thứ tự dòng, đối chiếu với tính trực tiếp tập t'<t, ánh xạ nhãn hiếm, tính trước cap và category chưa thấy.

## Pilot Kaggle

Kernel: https://www.kaggle.com/code/sangtranminh211/pubg-loadout-history-pilot-20261022

Version 1; bundle `artifacts/kaggle-history-pilot-20261022`; private CPU, Internet tắt, dataset Kaggle gắn trực tiếp. Mode pilot: 3.000 trận, tối đa 100.000 train, grid đầy đủ, evaluate=False. Chạy lại pytest trước EDA/preprocessing/training/diagnostics. Provenance và source hash tại `history-pilot-submission-20261022.json`.

Giữ kín holdout thật; không chạy full 1 triệu dòng hoặc đánh giá test cuối trong pilot. Kết quả cũ 7 lớp/C không dùng để kết luận mức tăng của D/6 lớp.

## Kết quả đã kiểm chứng trên Kaggle version 1

- 64/64 test pass, không failure/error/skip. 33 source hash khớp bundle và source local.
- Đủ 6 họ, 16 trials, 12 pipeline; main D/17 đặc trưng, không quick hoặc placement. Không cảnh báo hội tụ/tính toán số hay thư viện. Pipeline nạp lại tái lập điểm; xác suất hữu hạn và tổng bằng 1.
- Source split SHA-256 giữ nguyên `3cd3e1a76c8679b510ee791bbd280a3684a51ffc03676c39ffbcc7466296c8ce`.
- Train đầy đủ trước cap: 136.351 dòng; train thực tế: 100.000 dòng / 2.095 trận; validation: 28.165 dòng / 434 trận. Ngưỡng 1% gộp LMG vào Other, còn 6 lớp. Bổ sung cleaning placeholder `#unknown`, nên không so trực tiếp số dòng/điểm với các lượt cũ.
- Mô hình chọn bằng Macro-F1 validation: **Random Forest balanced**, 300 cây, depth 18, min leaf 5, max_samples 0.15.

| Ablation | Macro-F1 | CI 95% | Accuracy | Top-2 |
|---|---:|---:|---:|---:|
| A: khoảng cách | 0,3039 | [0,2976; 0,3101] | 36,96% | 58,07% |
| B: + thời gian | 0,3416 | [0,3348; 0,3478] | 43,77% | 64,72% |
| C: + vị trí/bản đồ | 0,3524 | [0,3454; 0,3589] | 46,00% | 66,47% |
| D: + lịch sử nhân quả | **0,4306** | **[0,4232; 0,4377]** | **51,13%** | **70,53%** |

Cả bốn bậc dùng cùng cấu hình RF được chọn trên D. C→D tăng **+0,078246 Macro-F1**, paired cluster bootstrap 1.000 lần theo 434 trận, CI 95% **[+0,071723; +0,085446]**. Mức tăng trên validation có CI không chứa 0. A→B tăng +0,037726; B→C tăng +0,010770; CI đều dương. Đây là bằng chứng trên validation đã dùng phát triển/chọn mô hình, chưa phải kết luận test cuối.

| Nhóm validation | Số dòng | C Macro-F1 | D Macro-F1 | C Accuracy | D Accuracy | D Top-2 |
|---|---:|---:|---:|---:|---:|---:|
| Mạng đầu tiên, has_prior_kill=0 | 15.393 | 0,3362 | 0,3384 | 42,71% | 40,19% | 62,02% |
| Có mạng trước đó, has_prior_kill=1 | 12.772 | 0,3408 | **0,5197** | 49,95% | **64,32%** | **80,79%** |

Nhóm có lịch sử chiếm 45,35% validation. Lợi ích tập trung ở nhóm này; trên mạng đầu tiên, Macro-F1 tăng rất ít và Accuracy giảm. Tổng thể D đạt Weighted-F1 0,5260, tactical role Macro-F1 0,6225 và tactical role Accuracy 64,85%.

Accuracy D toàn validation **51,13% thấp hơn majority 52,24%** (majority Macro-F1 chỉ 0,1144). RF plain D và HGB plain D đạt Accuracy lần lượt 59,51% và 59,59%, nhưng Macro-F1 thấp hơn (0,3927 và 0,4062), nên không được chọn theo tiêu chí chính. Không kết luận mô hình chọn thắng majority ở mọi chỉ số.

F1 từng lớp của RF balanced D: AR 0,6507; DMR 0,3668; Other 0,4094; SMG 0,3386; SR 0,3696; Shotgun 0,4486. Không còn lớp hoạt động có F1=0. Permutation importance validation xếp last_weapon_group cao nhất; các cột lịch sử dominant_prior_weapon và last_kill_distance_m cũng đóng góp.

Macro-F1 trên mẫu train stratified 20.000 dòng: 0,4950; validation 0,4306; gap **0,0644**. C dùng cùng cấu hình có gap 0,1110; không retune C vì phải cố định tham số trong ablation. Không coi gap trên mẫu train là điểm toàn train.

Runner mất **540,63 giây (~9,01 phút)**, gồm test/EDA/preprocessing/train/diagnostics; không gồm chờ cấp máy. RSS đỉnh tiến trình cha **965,24 MiB (~0,94 GiB)**, tích lũy qua các bước; không phải RAM riêng mô hình hay peak toàn máy. Lượt fit/predict của RF chọn mất 17,93 giây. Môi trường Kaggle: sklearn 1.6.1, pandas 2.3.3, numpy 2.1.3.

Bằng chứng lưu tại:

- [Readiness Kaggle](kaggle-history-pilot-20261022.json), [JUnit Kaggle](kaggle-history-pilot-tests-20261022.xml).
- [Ablation](history-pilot-ablation-20261022.csv), [CI mức tăng](history-pilot-ablation-gains-20261022.csv), [hai nhóm lịch sử](history-pilot-subsets-20261022.csv).
- [Tất cả mô hình](history-pilot-validation-20261022.csv), [từng lớp](history-pilot-per-class-20261022.csv), [importance](history-pilot-importance-20261022.csv).
- [Provenance và hash output](history-pilot-verification-20261022.json).

Chưa chạy lại train dài 50.000 trận/1 triệu dòng theo D; chưa mở/chấm holdout thật. Kết quả pilot đủ cơ sở kỹ thuật để chạy bước train dài tiếp theo bằng bundle mới, vẫn giữ evaluate=False.

## Đã có kết quả cuối sau pilot

Lượt full D và đánh giá holdout version 1 đã hoàn tất: [báo cáo cuối](HISTORY_FULL_FINAL_RESULTS.md), [ZIP bảng/hình](pubg-final-results-20261022.zip). Số liệu test cuối dùng báo cáo này; các bảng ở trên là pilot validation.
