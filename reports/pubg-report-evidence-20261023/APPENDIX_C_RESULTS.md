# Phụ lục C — GridSearchCV, alpha tradeoff và placement

Cập nhật lúc 09:54 ngày 23/10/2026 (giờ Việt Nam): **Phụ lục C đã hoàn tất và xác minh**, gồm RF/HGB GridSearchCV, 12 điểm α có Minority Recall và C2 placement. Không chấm lại holdout hoặc đổi main model.

## Phạm vi đóng băng

Dùng đúng 1.000.000 dòng train / 34.614 trận và 480.891 dòng validation / 7.373 trận của full-final version 1. Không đọc holdout thật, không thay model/selection/kết quả chính đã khóa.

- RF: 12 tổ hợp trong plan × 3 GroupKFold theo match_id, alpha=1; 300 cây cố định.
- HGB: 12 tổ hợp × 3 GroupKFold, alpha=1; 150 vòng cố định.
- Alpha: 0/.35/.50/.65/.80/1 trên cả RF/HGB, dùng tham số của biến thể balanced D trong main run, chỉ thay trọng số. Công thức chính xác `(N/(K*N_c))**alpha`, học trong từng lần fit; không normalize/clip. RF alpha=1 dùng trọng số lớp cố định trên train của fold, khác balanced_subsample ở main run.
- C2: nạp lại C/D đã khóa, kiểm tra tái lập validation; fit riêng D+placement với cùng RF/params/balancing; bootstrap validation 1.000 lần để so sánh C→D và D→D+placement.

## Lần gửi

- https://www.kaggle.com/code/sangtranminh211/pubg-appendix-rf-cv-20261022
- https://www.kaggle.com/code/sangtranminh211/pubg-appendix-hgb-cv-20261022
- https://www.kaggle.com/code/sangtranminh211/pubg-appendix-alpha-placement-20261022

Đã hoàn tất thiết kế 87 fits (không tính phiên thử lỗi). Bản gửi đầu local 73/73 test pass / bundle 38 file; HGB retry v3 local và Kaggle 76/76 pass / bundle 39 file. Các 34 file runtime chính giữ nguyên hash. Provenance: `appendix-c-submission-20261022.json`. Mỗi kernel chạy lại toàn bộ test trước, pin hash dataset/metadata và phiên bản thư viện, rồi chặn parquet ngoài train/validation.

Các mốc Accuracy/Macro-F1 trong plan là kỳ vọng; chỉ kết luận từ output. Thí nghiệm thêm placement là retrospective và chỉ đo nguồn thông tin hậu nghiệm này, không tự chứng minh rằng mọi dạng rò rỉ khác đều đã bị loại bỏ. Toàn bộ phần này là phân tích bổ sung sau khi bài chính đã khóa, không phải kết quả test cuối mới.

## HGB CV v3 — COMPLETE, đã xác minh

Kiểm tra lúc 08:50 ngày 23/10/2026 (giờ Việt Nam). Readiness passed; 76/76 test Kaggle pass; 39 source hash và input/metadata/library versions khớp. Đủ 12 tổ hợp × 3 GroupKFold + 1 refit. Fold audit giống hệt RF cả SHA-256 (34.614 trận / 1 triệu dòng). Guard chỉ đọc train/validation, giữ nguyên selection chính.

- Best: **learning_rate=0.10, max_leaf_nodes=63, min_samples_leaf=50**, max_iter=150, α=1 học trong fold.
- Macro-F1 CV **0,408334 ± 0,001025 SD**; Accuracy CV **45,85%**. SD giữa fold không phải CI 95%.
- Validation sau refit: Macro-F1 **0,407183**, Accuracy **45,78%**, Weighted-F1 **0,479228**, Top-2 **66,75%**, Tactical Role Macro-F1 **0,585816**, Tactical Role Accuracy **60,61%**.
- Runtime 77.08 phút; RSS đỉnh tiến trình cha 1735.21 MiB.
- [CSV 12 tổ hợp](appendix-c/appendix_hgb_gridsearch_cv.csv), [validation refit](appendix-c/appendix_hgb_cv_best_validation.csv), [fold audit](appendix-c/appendix_hgb_cv_match_folds.csv), [kiểm chứng](provenance/appendix-c-hgb_grid-v3-verification-20261023.json), [provenance](provenance/appendix-c-hgb-retry-v3-submission-20261023.json).

V1 lỗi không có traceback, nguyên nhân gốc chưa rõ; v2 thiếu builder trong bundle, fail test trước dữ liệu thật. V3 đã bổ sung builder, ghim image main, giới hạn luồng trước import, lưu progress/traceback; archive thực tế đã qua 76 test trước push. [Bằng chứng v1](provenance/linked/reports/appendix-c-hgb_grid-error-20261023.json), [bằng chứng v2](provenance/linked/reports/appendix-c-hgb_grid-v2-error-20261023.json). Lịch theo dõi đã xóa sau khi tải/xác minh thành công; không chạy lại hoặc chấm lại holdout.

## Kết quả đã xác minh

- RF CV: 12 tổ hợp × 3 GroupKFold + 1 refit, 73/73 test Kaggle pass. Best: 300 cây / depth 22 / leaf 5 / max_samples 0.15, α=1 trọng số cố định trong fold. Macro-F1 CV 0,432913 ± 0,000628 SD; validation sau refit 0,431908, Accuracy 51,20%, Top-2 70,67%. CSV: `appendix-c-20261022/appendix_rf_gridsearch_cv.csv`.
- RF α=0,65 đạt Macro-F1 validation 0,440113, Accuracy 55,71%; HGB α=0,50 đạt 0,441691, Accuracy 56,42%. α=1 không tối ưu Macro-F1 trong 6 mức thử. Đủ 12 điểm và Pareto tại `appendix-c-20261022/appendix_alpha_tradeoff.csv` / `.png`; Minority Recall đã bổ sung và kiểm chứng trên 12 điểm.
- D→D+placement: +0,001339 Macro-F1, CI [0,000610; 0,002051]; Accuracy +0,3541 điểm phần trăm. C→D: +0,070987, CI [0,069443; 0,072463]. Chênh lệch giữa hai mức tăng +0,069648, CI [0,067729; 0,071428]. Baseline D được nạp lại và tái lập validation; C2 không dùng model RF depth=22 của CV.
- RF và α/placement đã đối chiếu 38 source hash, input hash, 73/73 test; HGB v3 đã đối chiếu 39 source hash, input hash, 76/76 test. Cả ba section chỉ đọc train/validation và không đổi selection chính. C1.1 đủ hai bảng; C1.2 đã đủ Minority Recall sau replay riêng 12 fits được xác minh bên dưới.

Bảng số liệu chi tiết, diễn giải và các phần còn thiếu đã cập nhật trực tiếp trong [plan.md](plan.md). Không mở/chấm lại holdout và không dùng những model phụ lục để thay kết quả chính đã khóa.

## Minority Recall — COMPLETE, kiểm chứng passed

Kernel `sangtranminh211/pubg-appendix-alpha-recall-20261023` v1 COMPLETE; 80/80 test Kaggle pass, 40 source hashes khớp, frozen train/validation và versions khớp, không đọc holdout. Replay 12 fits theo params/weights ban đầu, không chạy lại CV/C2. Max delta của 7 chỉ số cũ trên 12 điểm là **0**; params, weights và Pareto giống bảng gốc. Runtime 40.18 phút, RSS cha đỉnh 2671.14 MiB.

Minority = train_fraction <1/K (K6): DMR/Other/SMG/SR/Shotgun; Minority Recall là macro mean 5 class recalls trên validation, không weighted/pooled và không chọn nhóm từ validation. Quy ước recall=0 nếu support=0.

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

Trong 6 mức thử, Minority Recall cao nhất ở α=1: RF 0,477945, HGB 0,502308. α tăng đánh đổi recall nhóm minority với Accuracy; không đồng nghĩa Macro-F1 cũng tăng. RF α=.65 và HGB α=.50 tối ưu Macro-F1 trong họ nhưng có Minority Recall lần lượt 0,412053 và 0,407648. Đây là kết quả validation bổ sung, không dùng đổi mô hình/test chính.

Đã tính lại 72 class recalls/432 confusion cells, Macro/Weighted-F1/Accuracy độc lập và xem đồ thị. [Bảng α đủ chỉ số](appendix-c/appendix_alpha_tradeoff.csv), [recall từng lớp](appendix-c/appendix_alpha_class_recall.csv), [confusion cells](appendix-c/appendix_alpha_confusion.csv), [đồ thị](appendix-c/appendix_alpha_minority_recall.png), [reference check](appendix-c/alpha_recall_reference_check.json), [kiểm chứng](provenance/appendix-c-alpha_recall-verification-20261023.json), [provenance](provenance/appendix-c-alpha-recall-submission-20261023.json).

Tổng thiết kế 87 fits ban đầu +12 replay α bổ sung recall, không tính phiên lỗi/test fixture. Bước 5 đã hoàn tất; Bước 6 viết báo cáo còn lại. Main results/test giữ nguyên.

## Bộ số liệu để viết báo cáo

Đã hoàn tất các thí nghiệm và kiểm chứng. [README và bộ minh chứng](README.md), [mục lục bộ minh chứng](README.md), [manifest tệp trong gói](MANIFEST_SHA256.json). Gói gồm main test đã khóa, bảng/hình phụ lục đầy đủ, provenance và snapshot kế hoạch; các liên kết trong bản sao tài liệu đã chỉnh để dùng trong gói. Không chứa joblib/parquet lớn. Bước tiếp theo là viết Báo cáo tổng kết; không cần train hoặc chấm lại holdout. Lịch theo dõi đã xóa.
