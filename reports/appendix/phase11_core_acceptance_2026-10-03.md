# Giai đoạn 11: nghiệm thu đợt đầu S1/P1/P2

Ngày: 03/10/2026. Phạm vi: code và fixture CPU cô lập, không full-data, Colab, GPU, Drive hoặc All-in-One. Đối chiếu toàn bộ `PUBG_RESEARCH_SPEC.md` v3.0 và kế hoạch hiện hành, đặc biệt D01/D02, G4 và NB09-01..34. Không thay đặc tả hoặc chốt tham số YAML đang null.

## I. Công việc được nghiệm thu

NB09-01: mỗi task S1/P1/P2 thực thi train-mean, train-median và OLS thật. Không dùng target cộng hằng số làm dự đoán. Có 9 model, 9 prediction parquet, 9 metadata JSON, compute metadata và bảng validation. Baseline không có predictor, fit target train; OLS fit imputer/scaler/regressor trên train, thứ tự feature đúng cấu hình. P1/P2 dùng cùng cohort valid placement và valid survival trước fit.

- Implementation: `src/models/training.py::run_rq3_prediction_suite`, `load_rq3_development_data`, `train_and_predict_experiment`; tái sử dụng `TrainMeanRegressor`, `TrainMedianRegressor`, `LinearModelWrapper` và verified publication hiện có.
- Caller thật: `notebooks/09_rq3_prediction.ipynb`, cell-006 cấu hình/backend, cell-008 SQL join development, cell-010 allowlists, cell-012 fit/cohort, cell-014 trạng thái, cell-016 metric, cell-018 hình, cell-021 bàn giao.
- Fixture: 30 trận x 4 người = 120 dòng; 80 train/20 validation/20 test. Target placement nhất quán trong từng team. SQL chỉ collect 100 development rows; final-test behavior/targets không vào dataframe notebook.
- Kiểm chứng: `test_run_rq3_prediction_suite_full_workflow` xác nhận 9 ứng viên, constants bằng mean/median train, fitted imputer/scaler bằng thống kê train và predictions model reload khớp đến atol 1e-10. Mọi prediction chỉ chứa train/validation; metadata test_samples=0. Registry có split_scope development_train_validation.
- Mutation: thay target và player_kills test bằng infinity không đổi toàn bộ bảng validation hoặc predictions development. Thiếu feature, thiếu split hoặc cùng match ở nhiều split bị từ chối. Hai dòng target không hợp lệ cho P1/P2 cùng còn 98 development rows, không thay raw.
- Flags/backend: tắt P1/median thực sự không fit; tắt cả core tasks vẫn chạy notebook và hiển thị lý do không có hình P2, không dựng prediction giả. Giả lập GPU không sẵn sàng phải lỗi, không fallback CPU.

Lệnh kiểm thử:

```powershell
$env:MPLBACKEND='Agg'
$env:PUBG_PREDICTION_EVIDENCE_DIR='reports/appendix/phase11_nb09_fixture_2026-10-03'
python -m unittest discover -s tests -p test_phase_d_prediction.py -v
```

Kết quả lượt fixture cuối: 11/11 đạt; log `phase11_nb09_tests_2026-10-03.log`. Đây không phải bằng chứng hoàn tất 34 công việc của giai đoạn 11.

## II. Output và khả năng đọc

`phase11_nb09_fixture_2026-10-03/09_fixture.ipynb` và `.html` có output các cell thực, cấu trúc khoa học 10 phần (0..9), Bảng 09-A..E, hai hình inline. Namespace fixture lưu riêng, không ghi output synthetic vào notebook nghiên cứu gốc.

Đã mở PNG và đối chiếu bảng `tables/rq3_development_validation.csv`:

- Hình 09-01 `figures/rq3_development_mae.png`: 3 panel S1/P1/P2, N validation=20, matches=5, 3 ứng viên mỗi task. Đơn vị survival giữ pending; placement score [0,1]. S1 OLS MAE 21.9482; P1 OLS 0.133140; P2 OLS 0.134072. Đây là số fixture, không kết quả PUBG.
- Hình 09-02 `figures/rq3_development_p2_diagnostics.png`: toàn bộ P2 validation N=20, observed/predicted density và residual actual-predicted; không lấy mẫu hoặc clip prediction. Caption/cách đọc/giới hạn và nguồn có ngay trước hình trong notebook. Colorbar số dòng không giả định mật độ xác suất.
- Bảng status giữ lịch sử blocked với reason, T0/T1 planned và nonlinear blocked/pending_resource_gate. Model completed chỉ có scope development, không là kết quả cuối.
- Checkpoint `rq3_development` completed chứa artifacts kiểm checksum; `rq3_prediction` và `notebook/09_rq3_prediction.ipynb` blocked/pending_G4. Bàn giao canonical có status blocked và next_step là tiếp tục NB09, không NB10. Fixture gọi begin_notebook NB10 và xác nhận bị chặn.

Các đường dẫn trong output trỏ tới namespace tạm lúc test. Bản sao evidence không dùng làm checkpoint nghiên cứu trên Drive. Muốn tái lập, chạy lệnh fixture trên phiên bản code/config tương ứng.

## III. Phần chưa nghiệm thu và điểm tiếp tục

- NB09-02: Grade C có blocked/reason/null metrics và registry; nhánh A/B đủ điều kiện chưa tích hợp training trên require_historical_dataset/receipt NB08. Không tích toàn task chỉ vì nhánh blocked đã có.
- NB09-03..10: T0/T1, nonlinear/resource status, mọi model parameter, lựa chọn validation và G4 lock đầy đủ còn mở. G4 hiện fail-closed, không auto-lock hay final-test prediction/metric. Prior exposure ghi unknown và cảnh báo code cũ từng predict test trước auto-lock; chưa audit lịch sử thực tế.
- NB09-11..34: đã có một phần allowlist/closure, common cohort, batch prediction, train-only objects, model reload, metric units và visuals. Chưa tích các dòng này: feature selection, indicators, RAM/VRAM/resource gates, streaming SGD riêng, compatible resume, run IDs, mode/resource plots, history integration và recipe final test chưa đủ.
- OLS hiện chỉ hỗ trợ fit_intercept=True; cấu hình False được ghi blocked, không im lặng bỏ qua. Không chốt estimator thay thế. Baseline CPU/GPU routing còn phải nghiệm thu production thật.
- Metrics dùng helper hiện có. Kiểm tra team-target conflict, weighted global R2, coverage/undefined reason và paired uncertainty còn phải hoàn thiện theo NB09/NB10; không tuyên bố tất cả contract metric đã đạt.
- Đợt tiếp theo tiếp tục NB09-02 với historical cohort xác minh từ NB08, rồi recipe T0/T1, resource/config/selection gates. Không chuyển giai đoạn 12 và không mở final test.

## IV. Phiên bản và kiểm tra hồi quy

SHA256 tại nghiệm thu:

| File | SHA256 |
| --- | --- |
| src/models/training.py | 069a3426aa379261f3dc05160ed2c747e2899886ba1a093c6fbef96e853c0272 |
| src/utils/generate_notebooks.py | ac50f349f308bdd870b9a676926f6b4ed024fb51dc72ec2eec3e2959b29f6b61 |
| notebooks/09_rq3_prediction.ipynb | 2cc7efa27753b7e5d3ce56fad980521268f6cea5c0241879cc88e19446a0edf6 |
| configs/models.yaml | d273cec1184771d4b85baa164c98fe6e2c9100be17416dd0146d353113fcdbf8 |
| configs/rq3.yaml | de891a0bcec85b0bd615fe4f87a153cc14325d73a98cf4b110d1e013a4bfaab4 |
| configs/features.yaml | 9eb0ffa15f19a2154ce1425fee52ff0c2b61fccf9ca96e195daea06cde718618 |

Lượt hồi quy đầu: 203 tests, 1 failure và 1 error, 2 skips. Failure bắt đúng thiếu artifact/handover sau thay đổi semantics notebook; đã khôi phục bàn giao blocked thật, không xóa assertion. Error historical stale xảy ra khi sửa generator trong lúc test đang chạy; giữ guard hash và chạy lại với code cố định. Log ban đầu giữ tại `phase11_regression_initial_2026-10-03.log`, không gọi lượt này là pass.

Lượt hồi quy sau sửa lưu tại `phase11_regression_2026-10-03.log`: 204 tests trong 150.408s, OK, skipped=2, 0 failures/errors. Loại rõ hai method có đường thực thi All-in-One: `test_all_cells_on_synthetic_data_in_fresh_workspace` và `test_notebooks_block_out_of_order_cells_and_invalidate_success_on_rerun_failure`; không gọi chúng là passed. `git diff --check` các file code/notebook/test của đợt đạt. Fixture NB09 sau cùng đã chỉnh placement nhất quán trong team và chạy lại riêng 11/11; code/config/notebook hash không đổi so với lượt hồi quy.
