# Giai đoạn 11: nghiệm thu Notebook 09 đến hết phạm vi code và fixture

Ngày: 03/10/2026. Đối chiếu PUBG_RESEARCH_SPEC.md v3.0, PUBG_IMPLEMENTATION_PLAN.md, AGENTS.md; áp dụng Ponytail để tái sử dụng registry/checkpoint/verified IO/sklearn, không thêm dependency hoặc framework. Báo cáo đợt đầu được giữ nguyên như lịch sử, không dùng các hạn chế của bản cũ làm trạng thái hiện hành.

## I. Phạm vi và cách tái lập

Không chạy Colab, GPU, Drive, dữ liệu PUBG lớn hoặc All-in-One. Không thay raw, split, RQ, D01/D02, estimator chính hay cấu hình storage/per_mode; không lấy mẫu rồi gọi full-data. Các quyết định production null vẫn null. G4 phê duyệt chỉ trong thư mục tạm của fixture, không phải phê duyệt nghiên cứu thật.

Nguồn thực thi: training.py, linear.py, streaming.py, tree_models.py, compute.py; rq3_resources.py, rq3_diagnostics.py, rq3_selection.py; evaluation/metrics.py; generator và Notebook 09. Notebook được sinh riêng bằng:

```powershell
python src/utils/generate_notebooks.py --only 09_rq3_prediction.ipynb
$env:MPLBACKEND='Agg'
$env:PUBG_PHASE11_EVIDENCE_DIR='reports/appendix/phase11_completion_fixture_2026-10-03'
$env:PUBG_PREDICTION_EVIDENCE_DIR='reports/appendix/phase11_completion_fixture_2026-10-03/core'
python -m unittest discover -s tests -p test_phase11_completion.py -v
python -m unittest discover -s tests -p test_phase_d_prediction.py -v
```

Bộ hồi quy: unittest discovery, loại chính xác hai method `test_all_cells_on_synthetic_data_in_fresh_workspace` và `test_notebooks_block_out_of_order_cells_and_invalidate_success_on_rerun_failure` thực thi All-in-One. Không gọi hai method bị loại là passed. Xem lệnh và kết quả trong log `phase11_completion_regression_verified_2026-10-03.log`.

Fixture core: 30 trận, 120 player rows; train80, validation20, test20; placement nhất quán trong team. SQL chỉ collect100 development rows. Fixture history: NB08 producer thật, Grade B, availability minh họa, threshold2, walk_forward_fixed_model chỉ được chọn trong fixture; 12 trận/24 rows, S2/P3 đủ lịch sử có train8/validation8. Sửa threshold mà không xây lại NB08 phải blocked. Fixture G4 phê duyệt giữa hai cell development và selection; final test chỉ predict từ model đã lưu, không fit lại.

Các tên kiểm thử bên dưới là method trong `tests/test_phase11_completion.py` hoặc `tests/test_phase_d_prediction.py`:

- H: `test_verified_history_candidates_and_stale_block`, gồm thực thi NB09 với receipt NB08 thật.
- C: `test_timing_pair_config_and_resume_resource_limit`, gồm tham số thực, paired rows, compatible resume, corrupt-one refit-one, OOM và pre-fit resource gate.
- G: `test_explicit_g4_real_notebook_and_stale_guard`, thực thi NB09 qua nhánh G4 approved giả lập; không có decision/corrupt lock/data stale không mở test.
- S: `test_streaming_statistics_all_rows_and_reproducibility`, thống kê train, frozen scaler, đủ rows mỗi epoch, external validation, seed tái lập.
- M: `test_metrics_and_mean_indicator_pipeline`, mean/indicator/all-missing, weighted global R2, degenerate R2, nonfinite prediction và team conflict.
- D: `test_run_rq3_prediction_suite_full_workflow`, `test_final_test_mutation_does_not_change_development`, `test_common_cohort_and_fail_closed_features_split`, `test_config_disabled_task_and_backend_error_no_fallback`.
- N: `test_real_notebook_cells_development_handoff`, `test_real_notebook_all_core_tasks_disabled`: trực tiếp cell nghiệp vụ, bảng/hình/checkpoint/handover/NB10 blocked.

## II. Bằng chứng theo từng task

Mỗi dòng là nghiệm thu code/fixture, không phải RUN-08. Cell ID của notebook hiện tại: 006 cấu hình; 008 SQL collect; 010 allowlists; 012 fitting; 014 status; 016 tables/diagnostics; 018 MAE/density/residual; 020 ablation/timing/mode; 022 resources/correlation; 024 figure catalog/G4; 026 checkpoint/handover.

| Task | File/hàm và cell | Điều kiện kiểm tra, expected và actual | Bằng chứng |
| --- | --- | --- | --- |
| NB09-01 | run_rq3_prediction_suite, 012 | 3 core tasks có mean/median/OLS thật, thống kê fit train, không target-derived prediction giả; đạt lại. | D, N; core/models và tables |
| NB09-02 | require_historical_dataset/load_rq3_development_data, 012/014 | S2/P3 chỉ train history verified đủ ngưỡng; 3 model mỗi task có depth>=2; receipt stale/Grade C blocked với reason và metric null. | H, D; history/tables |
| NB09-03 | suite timing recipes, 012/020 | T0 subset T1=P2, cùng row IDs/target/split/OLS; NB09 là producer development, không có producer T0/T1 thứ hai trong NB10 hiện tại. | C; timing parquet, ablation_timing PNG |
| NB09-04 | HGB/RF factories/resource_snapshot, 012/014 | P2 HGB chạy đúng config CPU; RF đọc flag/params; GPU không hỗ trợ bị chặn rõ, không sample/substitute. XGBoost optional ghi backend chưa triển khai, không giả chạy. | C, G, N; status/resources/meta |
| NB09-05 | resource_snapshot/record_failure, 012/014 | Budget quá nhỏ hoặc fit OOM: resource_limited, metric null, old good model hash không đổi. | C; checkpoint/state/resource rows |
| NB09-06 | factories/model.get_params, 012/016 | fit_intercept=False, standardize=False, HGB max_iter3/seed19 thực sự tới estimator; SGD enabled được đăng ký riêng, không chỉ import. | C, G, S; model/meta/status |
| NB09-07 | lock_rq3_selection/evaluate_locked_test, 024 | Development chỉ train/validation; explicit review chọn fitted candidates/features/params; trước lock không test prediction/metric. Nhánh approved giả lập mới đọc test. | G, D, N; G4 recipe/final table |
| NB09-08 | SQL loader/suite/final evaluator, 008/024 | Không còn notebook đọc test trước G4; None/corrupt/stale lock bị từ chối trước mở DuckDB test. Legacy lock helper không được notebook dùng để tự duyệt. | G, N; test mutation và gate |
| NB09-09 | selection receipt, 024 | Recipe chứa ordered features, model params/backend/seed, fitted-object hashes, development cohort, input/split/code/config hashes, bins/comparisons. | G; approved_g4/manifests |
| NB09-10 | development_gate/recipe, 023/024 | Không tuyên bố test cũ untouched; ghi unknown và cảnh báo prior code exposure; fixture ghi đúng synthetic scope. | D, G, N; gate JSON/render |
| NB09-11 | registry closure/task lists, 010/012 | D01 không survival descendants; P1/P2 chỉ khác direct survival; phase coupling được giải thích không phải causal. | D, N; allowlists/render |
| NB09-12 | common valid-survival/placement cohort, 012 | Hai invalid targets cho P1/P2 cùng98 development rows, không trùng row tình cờ hoặc loại chỉ một task. | D; prediction row keys |
| NB09-13 | timing/group closure, 012/020 | Mỗi paired branch cùng development keys/target/split; group removal có descendants; cohort table ghi kill-event rows (core validation16/20). | C, N; cohort CSV/ablation delta |
| NB09-14 | shared validators/SQL split/metrics, 008/012/024 | Finite/range targets, unique match assignment, match isolation; invalid split/missing feature fail-closed; final eligible test20 mỗi selected model. | D, G, M; actual output |
| NB09-15 | LinearModelWrapper/StreamingSGDWrapper, 012/016 | Imputer/scaler chỉ train, fitted objects và feature order được serialize; validation dùng đánh giá/selection, không fit transforms. | D, S, M, G; joblib/meta/coefs |
| NB09-16 | atomic model/prediction publication, 012/026 | Reload model predictions khớp atol1e-10; canonical filenames, compute/run/meta, validation và final comparison tách biệt. | D, G, N; artifacts |
| NB09-17 | canonical pred schema, 012/024 | Có row/match/player/team/mode/task/target/split/actual/pred/residual/experiment/run ID; history có depth; final có recipe_hash. | H, D, G; Parquet |
| NB09-18 | batch predict/canonical paths, 012/024 | Không X_all; ma trận predict theo batch7/3; suite trả paths thay nhiều full prediction frames còn sống. | D, G; reload/parquet consistency |
| NB09-19 | precollect budget/resource_snapshot, 008/012/022 | RAM thực và DF footprint đo trước fit; actual string length trong collect estimate; CUDA có VRAM khi backend sẵn sàng, không ghi CPU=0 GPU. Estimate không là peak guarantee. | C, N; resource CSV/PNG |
| NB09-20 | StreamingSGDWrapper.fit_frame, 012/023 | Mean pass train, scaler partial_fit pass train rồi frozen; bounded batch matrices; mỗi epoch đủ mọi train row, external validation. Không OLS OOM fallback. | S, C, N; SGD metadata |
| NB09-21 | backend/OOM guards, 012/014 | Không tự đổi OLS CUDA sang CPU/SGD; fallback flag True bị từ chối; OOM có evidence, không bịa metric. | C, D; statuses |
| NB09-22 | compute routing/model type guard, 012/014 | Constants CPU; OLS có explicit sklearn/cuML; HGB/RF/SGD không có GPU bị blocked khi requested CUDA. CPU fixture không chứng minh T4 chạy. | D, C, N; actual device/meta |
| NB09-23 | manager.is_compatible, 012 | Rerun tương thích zero fits; corrupt một model chỉ fit đúng model đó. Signature gồm actual device và batch size, không reuse recipe khác. | C; compatible_resume rows |
| NB09-24 | hierarchical metrics, 016/024 | Micro, equal-match weighted metrics/global R2; team placement target phải nhất quán; survival team metrics not applicable. Undefined R2 không thay zero. | M, D, G; tables |
| NB09-25 | feature_diagnostics/ablations/G4, 016/020/024 | Train variance/sparsity/correlation/raw-subset VIF, fitted coefs và validation permutation/ablation hiện ra; final features phải khớp fitted candidate được review, không auto-drop VIF. | N, G, H; diagnostics CSV/receipt |
| NB09-26 | mean imputer/add_indicator, 012/023 | Mean/all-missing/indicator giữ schema và train statistics; hiện không chọn median/RobustScaler, không gọi chúng incremental. Nếu chọn các phương án đó phải có exact train quantiles disk-backed trước khi triển khai. | M, S; notebook limitation |
| NB09-27 | separate SGD recipe, 012/023 | Seeded batch order, đủ5 train rows mỗi epoch fixture batch2, scaler n_samples5 không cập nhật lại trong epochs, validation ngoài early stopping/best epoch. | S, C; SGD epoch metadata |
| NB09-28 | fit protocol guard, 024 | Main models fit train, final path predict only; train+validation refit bị từ chối nếu không protocol riêng, không âm thầm refit baseline/paired branches. | G, D; fitted artifacts/guard |
| NB09-29 | approval reasons/bins/comparisons, 024 | G4 yêu cầu 5 nhóm lý do, valid ordered bins và explicit selected comparisons cùng cohort/target; không tự duyệt theo thấp nhất MAE. | G; decision/lock JSON |
| NB09-30 | scientific blocks/matrix, 004..016 | Task/target/features/cohort/split, D01/D02/coupling, baseline/train-only/validation/G4 được trình bày với bảng thực. | N, H, G; ipynb/HTML |
| NB09-31 | resources/status/event logs, 012/014/016/022 | Requested/actual backend và status/fit/resume/reason hiện rõ; RAM/VRAM missing semantics và T4 không tăng host RAM. | C, N; CSV/PNG/log |
| NB09-32 | metric/visuals, 016..022 | Validation N20/5 trận, units/time pending, negative/undefined R2 được giải thích; density/residual không clip/sampling, mode không trộn units. Historical rows/MAE panel khi hợp lệ. | M, N, H; 6 PNG/CSV/render |
| NB09-33 | generated notebook execution, 006..026 | Chạy actual cells ở pending, all-core-disabled, verified history và approved G4; model reload/schema/checkpoints/handover kiểm bằng assertion; NB10 blocked khi pending. | N, H, G; fixtures |
| NB09-34 | generator/scientific presentation/catalog, 004..026 | 27 cells, 11 business code cells, 10 phần 0..9 và 7.1/7.2; bảng/hình inline có nguồn/caption/units/N/scope/cách đọc/giới hạn; catalog checksum và nguồn. Đã mở PNG và đối chiếu CSV. | N, H, G; HTML/6 PNG/catalog |

## III. Output và giới hạn

Namespace evidence: `phase11_completion_fixture_2026-10-03/core`, `history`, `approved_g4`; mỗi nhánh có `09_fixture.ipynb`, HTML và bản sao tables/figures/manifests/checkpoints; core có model/prediction copies để reload. Path trong receipt/render là namespace tạm lúc test, không dùng bản sao làm checkpoint Drive. Notebook nghiên cứu gốc không được gắn output synthetic.

Đã mở lại 6 PNG core: MAE tasks, observed/predicted + residual P2, group ablation + timing, mode MAE, resource estimate/RAM, train Pearson. Undefined/constant cells màu xám, không zero; đã sửa đường chéo constant dù floating variance gần zero. Nhánh history có thêm S2/P3 trong MAE figure, target variance hằng có R2 null/reason; không coi đây là kết quả PUBG.

Số minh họa core validation N20: P1 OLS MAE0.1331402563, P2 OLS0.1340721239, T0 OLS0.1344448857, T1 OLS0.1340721239. Không so trực tiếp survival time với placement score; đơn vị thời gian nguồn vẫn pending xác minh production.

G4 thiếu quyết định thật thì notebook09 và handover blocked; chỉ rq3_development completed. G4 fixture approved có final n20 mỗi selected experiment, test aliases cho P1/P2, notebook/handover completed; checkpoint development không chứa final-test artifacts. Đây chỉ là kiểm tra nhánh code, không mở quyền chạy thật. RUN-07/RUN-08 và NB08-15 vẫn chờ quyết định nhóm.

SGD stream ma trận trên dataframe đã qua RAM gate, chưa là raw ingestion/out-of-core disk training. Nếu dataframe không vừa budget, dừng resource_limited, không sample. Không triển khai median/RobustScaler streaming vì config hiện dùng mean/StandardScaler; cần exact disk-backed quantiles nếu sau này được chốt. XGBoost chưa có backend triển khai và được blocked rõ nếu bật, không gọi là completed; RF/HGB/SGD CPU không thay yêu cầu GPU. CPU tests không xác minh VRAM/cuML/Colab quota/quyền shortcut/Drive canonical overwrite thật. Bản source/bootstrap phải đồng bộ cùng notebook khi chuyển máy/tài khoản.

Giai đoạn 12 chưa thực hiện: CI/bootstrap theo match, final ablation/error bins application/error analysis/importance reporting và hoàn thiện NB10. Không dùng mẫu hay đưa thêm thuật toán nghiên cứu khác để giảm phạm vi. Không commit/push.

## IV. Phiên bản và kết quả kiểm thử

SHA256 của bản được nghiệm thu:

| File | SHA256 |
| --- | --- |
| src/models/training.py | 408DCAF604313C315F8339765A55EC46B94E928B54DB8CDA5E0B5BF2CA57EB72 |
| src/models/streaming.py | B023B3237F0D6F646B6B1EA9C3FA957F0D1AA75C8CCED3A16750C2CA37BC76D5 |
| src/models/rq3_selection.py | F55A14869D80821BB9BBEFD88E3D8E9352A49C63FCDA83AE02C154C0962AEDC2 |
| src/models/rq3_resources.py | 768829AB6E355AA46FBE9E1607BE1442703E41B676ECB6917C15B1839CE609DE |
| src/models/rq3_diagnostics.py | EFA7C9C1B3D429B282653C7E2AEC52C901ED952869C111DBDB7D55CEBA05501F |
| src/utils/generate_notebooks.py | B4090E2657471F3F297A58D377CAE1D2FCED939CEFD1E8C76AFE144630EC026F |
| notebooks/09_rq3_prediction.ipynb | 6E6C0361B72D9CE8A99F45578F4EAB41C04E57630BC227658F80FDA7C785C7F1 |

Lượt targeted đạt16 tests trong83.374s. Lượt hồi quy đầu209 tests có1 failure/1 error do hai fixture cũ vi phạm miền placement và placement đồng đội; giữ guard, sửa fixture và giữ log lỗi `phase11_completion_regression_2026-10-03.log`. Lượt sau209 tests đạt, skipped2,177.760s. Sau review bổ sung actual device/batch_size vào signature, dời invalidation trước validation/collect lịch sử và nhận dạng GPU OOM, chạy lại cùng bộ209 tests trên bản hash ở trên: 209 tests trong179.937s, OK (skipped=2), 0 failure/error, log `phase11_completion_regression_verified_2026-10-03.log`. Hai bài All-in-One không được chạy. `git diff --check` cho code/notebook/test/plan/guide đạt; warning chuyển LF/CRLF không là lỗi whitespace. Khi thêm CHANGELOG_FIXES.md vào phép kiểm, Git báo trailing whitespace trong các mục lịch sử cũ (dòng504..788); không viết lại lịch sử để làm sạch. Mục nối thêm của đợt này không có trailing whitespace.
