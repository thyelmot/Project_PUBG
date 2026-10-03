# Giai đoạn 12: Notebook 10, comparisons và uncertainty

## I. Phạm vi và quyết định được giữ nguyên

Yêu cầu: tiếp tục toàn bộ giai đoạn12 bằng kiểm thử logic nhỏ và hoàn thiện notebook theo NCKH. Đối chiếu PUBG_RESEARCH_SPEC.md v3.0, toàn bộ PUBG_IMPLEMENTATION_PLAN.md, AGENTS.md và nhật ký gần nhất. Ponytail full: dùng lại checkpoint/verified IO/registry/metrics/sklearn, không thêm dependency hoặc framework.

Không đổi RQ, targets, common cohorts, split, main OLS, D01/D02, per_mode, lịch sử hay cấu hình Drive/batch50000. Không Colab, full-data, GPU thật, Drive thật, All-in-One hoặc commit/push. Bins/approval/log transforms/indicator trong fixture chỉ mô phỏng protocol đã được duyệt, không chọn cho dữ liệu thật. Các quyết định null production giữ nguyên.

Sửa producer G4 là cần thiết: nhánh ablation, so sánh baseline và history-depth bins phải được duyệt trước test; không được bổ sung ở NB10 sau khi đọc test. NB09 vẫn là nguồn train-only duy nhất. Legacy helper ablation nay từ chối dataframe có test và chỉ báo validation, tránh đường vòng huấn luyện lại hậu nghiệm. Không tự duyệt G4 thật.

## II. Bằng chứng chung và cách tái lập

- Nguồn logic: src/evaluation/comparisons.py, bootstrap.py, error_analysis.py, importance.py; metrics.py được tái sử dụng; producer src/models/rq3_selection.py, rq3_diagnostics.py, training.py.
- Notebook: 10_ablation_error_analysis.ipynb có21cells,7codecells nghiệp vụ và10mục khoa học0-9. Generator là nguồn canonical, chỉ sinh lại09/10; không sinh hoặc chạy All-in-One.
- T = tests/test_phase12_comparisons.py::TestPhase12Comparisons. B = test_bootstrap_multiplicity_matches_independent_reference; P = test_pairing_guards_and_resource_undefined; E = test_error_bins_metadata_history_and_coverage; I = test_importance_labels_uncertainty_and_failure_status; N = test_real_notebook_core_resume_no_fit_corruption_and_resource; H = test_real_notebook_verified_history_depth_and_constant_r2.
- B so với reference độc lập concat toàn trận trên fixture6rows/3trận không đều,70replicates/seed17; kiểm mean/CI/valid replicate tới1e-12. Implementation thật aggregate contributions một lần, không concat full rows mỗi replicate. Shuffle và identical predictions delta0; constant target không CI R² giả.
- N chạy actual NB09 approved giả lập rồi NB10: train80/validation20/test20rows/5trận;12cặp,102metric records (2cặp survival không team),40bootstrap replicates. Fixture bật log1p hai cột và missing indicators để kiểm cùng policy với positional indices khác nhau sau ablation. Recompute từng observed hierarchical delta từ saved predictions; kiểm source/figure hashes, N/counts/coverage và7hình inline.
- H có verified history producer, train/validation/history depth riêng; test4rows/2trận.16cặp gồm S2/P3 vs mean/median; historical depth bins từ fixture decision. Constant target R²/delta/CI undefined được giữ với lý do; không diễn giải số missing là0.
- N chặn gọi fit/refit, compatible resume không đọc lại prediction, corrupt một comparison chỉ bootstrap lại1cặp, resource failure lưu resource_limited và giữ predictions tốt; retry canonical không hậu tố. Corrupt prediction upstream bị chặn trước read_parquet. Pending G4, recipe registration thiếu, duplicate/missing/extra/identity/target/split mismatch, nonfinite đều bị chặn.
- E kiểm metadata survival có actual trong[0,1] vẫn survival; mode canonical không hard-code1/2/4; bins [left,right), final endpoint included, history missing/outside riêng. Mỗi chiều slice sumN/coverage riêng, không cộng chồng giữa các chiều.
- I kiểm unstandardized/native regression impurity đúng nhãn, std/repeats/seed/N, failure/resource status và cấm permutation test chưa đăng ký. Producer permutation validation còn lưu configured/available RAM, estimated working bytes, VRAM và measured_at; thất bại/resource_limited chặn G4.

Lệnh targeted: `python -m unittest discover -s tests -p test_phase12_comparisons.py -v`, MPLBACKEND=Agg. Để lưu evidence, đặt PUBG_PHASE12_EVIDENCE_DIR=reports/appendix/phase12_fixture_2026-10-03.

Bộ hồi quy discover lọc đúng hai method thực thi All-in-One: test_all_cells_on_synthetic_data_in_fresh_workspace và test_notebooks_block_out_of_order_cells_and_invalidate_success_on_rerun_failure. Không gọi chúng passed; không chạy lệnh Run All hoặc dữ liệu thật.

Evidence: reports/appendix/phase12_fixture_2026-10-03/{core,history}/10_fixture.ipynb và10_fixture.html; tables/figures/manifests/checkpoints/experiments/models. Source path trong receipt là workspace tạm lúc test, copy chỉ để audit, không làm Drive resume checkpoint. Tái tạo bằng tests, không sửa checkpoint copy để dùng như nghiên cứu.

## III. Nghiệm thu riêng từng mã: logic, notebook và khả năng đọc

| Task | Logic và kiểm thử | Tích hợp notebook và output đọc được | Giới hạn |
| --- | --- | --- | --- |
| NB10-01 | NB09 timing recipe; comparisons context xác minh T1=P2/policy/cohort; N/H | cell007/010/012, bảng B/C/E và timing delta trong plots | Timing placement theo config hiện hành; S1 vẫn D01, không tự mở survival timing sensitivity |
| NB10-02 | remove absolute+phase và descendants; context recheck; N có indicators/log1p | bảng C/F giữ/bỏ features, ablation plot | Không causal |
| NB10-03 | registry dependency closure cả3nhóm; N actual fitted branches | bảng C/F, coefficients transformed ở I | Không lựa chọn lại feature |
| NB10-04 | same_preprocessing_policy so actual params/log feature policy; saved train-only pipelines; N | C train/validation/testN/model/cohort/run hash | GPU chưa thử |
| NB10-05 | NB09 model/meta/pred/checkpoint, NB10 percomparison CSV/JSON/checkpoint; N/H | C/L, receipt/canonical paths | Copy fixture không checkpoint Drive |
| NB10-06 | pair_predictions exact row sets/target trước metric; P/N | E pairing/coverage=1,N/trận | Không intersect |
| NB10-07 | compute_hierarchical_metrics và observed candidate-reference; N recompute | D/E cảMAE/RMSE/R²/aggregation/count/unit | Team survival không áp dụng |
| NB10-08 | G4+prediction checksum+signature; compatible reuse, corrupt/stale; N | A/C/L signature và compatible_resume | Chưa Drive thật |
| NB10-09 | row_id unique, sorted exact join, match/player/team/split/target/recipe/mode/history; P/B | E, phần2 giải thích pairing | Không ghép positional |
| NB10-10 | missing/extra/duplicate/target exact fail; P/N | cell007/010 guards, phần7 | Lỗi chặn, không tự sửa identity |
| NB10-11 | float64 per-match count/sums và sample indices với multiplicity; B | F bootstrap level/N/budget/seed | Match chưa giải quyết repeat player giữa trận |
| NB10-12 | cùng indices candidate/reference; globalMAE/RMSE/SST; B independent reference | E/F, phần3 công thức | Không average chunk RMSE/R² |
| NB10-13 | G4 mandatory P1/P2,T0/T1,core baselines,ablation pairs; N/H | E/F, forest cho CI thực | Không thêm cặp hậu nghiệm |
| NB10-14 | configured reps/seed/estimate/free RAM/valid replicate; P/N | F receipts, forest conditional | Estimate không peak proof; CI micro hiện hành |
| NB10-15 | paired evaluation rejects nonfinite, coverage explicit; P/N | D/E/G coverage/N/reasons | Không drop khác nhau giữa nhánh |
| NB10-16 | actual placement conflict guard trong shared metrics; hồi quy Phase11 | D team rows; phần3 | Survival not_applicable |
| NB10-17 | equal-match weighted global R² trong metrics; N recompute, Phase11 hand expectation | D/E match-aware | Không average per-match R² |
| NB10-18 | canonical team_size_mode, unknown/unavailable explicit; E/N/H | G vàmode heatmap | Không tạo mapping mới |
| NB10-19 | target_name/target metadata explicit; E survival values[0,1] | G đơn vị/task; phần5 | Không infer range |
| NB10-20 | mode,target region,history depth; E/N/H | G/H/error/coverage/residual | History chỉ với verified NB08/G4 |
| NB10-21 | G4 bins trước test; strictly ascending, left closed/final endpoint; E/N/H | B/G vàphần5 cách đọc | Bins production chưa duyệt |
| NB10-22 | rows/matches/coverage/insufficient/unstable_small_slice; E/H | G,error/coverage | 2trận chỉ min toán học, không scientific guarantee |
| NB10-23 | native fitted coefficients/tree importance và validation receipt reused; I/N | I/J/K, importance plot | HGB native unavailable có reason |
| NB10-24 | test permutation không requested, API rejects unregistered test; I | phần6 vàreceipt final_test_permutation | Không dùng test chọn feature; protocol mới cần duyệt trước test |
| NB10-25 | actual standardize flag/transformed names, regression_impurity_decrease; I/N | I, phần6 | Log coefficient không hệ số trên raw scale |
| NB10-26 | validation mean/std/repeats/seed/N/sample/budget; failed/resource status; I/N | J, bars std không CI; G4 guard | GPU/peak chưa thử |
| NB10-27 | group ablation primary, correlation diagnostic và causal caveat | C/F/K, ablation/importance captions | Correlated features giới hạn diễn giải |
| NB10-28 | float64/globalSST/constant/n<2; B/P/H vàPhase11 metrics | D/E/F reason/count; phần3 | Không clip hoặc row-independent uncertainty |
| NB10-29 | context closure/policy/commoncohort plus exported feature recipes; N/H | C/E/F vàcomparison/ablation plots | Không chọn sau test |
| NB10-30 | chỉ finite CI, observed delta và0line; B/P/H | forest inlinecell012, phần3/4 | CI chứa0không hỗ trợ chiều chắc chắn |
| NB10-31 | exact errors/counts/histogram/validation importance; E/I/N/H | G/H/I/J/K và4plots cell014/016 | Empty không tô MAE=0; smallslice caveat |
| NB10-32 | actual NB09/NB10, fit patched forbidden, shuffle/identical/mismatch/recompute/sourcehash; B/P/N/H | notebook fixture+HTML+7inline PNG, L/handover | Synthetic không full-data |
| NB10-33 | generator đủ0-9, LaTeX/tiếngViệt/delta/N/unit/source/scope/limits | 12nhóm bảng A-L,7PNG mở trực quan và đối chiếu nguồn | Không G5/report-ready thật |

## IV. Output và review trực quan

Đã mở comparison, ablation, forest, error, coverage, residual vàimportance PNG; nguồn CSV vàpredictions fixture được lưu cạnh evidence. Các thang survival/placement tách panels, counts không dùng đơn vị score, residual đúng actual-predicted; forest không vẽ CI undefined. Nhãn N được sửa khỏi biểu diễn np.int64 để thành số dễ đọc. Figure có nhãn synthetic fixture, source/figure/counts hashes, scope/recipe/report_ready=false.

Metric theo nguồn: core mỗimodel20rows/5trận; residual histogram counts sum20; history4rows/2trận; coverage mỗichiều sum1. Các giá trị thực tế và hash/version cuối được ghi dưới đây sau QA, không đặt trước kết luận nghiên cứu.

## V. Hạn chế và điểm bàn giao

G4 production, history threshold/availability/protocol, chronology evidence, full-data/GPU/T4/cuML/Drive/Colab/quota/peakRAM vẫn chưa được chứng nhận. Không tính final-test permutation vì chưa requested ở recipe; validation evidence có đủ status và uncertainty. RAM path dừng resource_limited, không sample/CPU/SGD substitute. CI micro là recipe hiện tại, match/team metric vẫn báo riêng với CI not_requested.

Giai đoạn13/Notebook11 chưa thực hiện trong đợt này: required matrix, G5 và immutable release còn mở. Chưa thay notebook nghiên cứu bằng output synthetic, chưa đồng bộ lên Drive hoặc GitHub. Cần đồng bộ source/config/notebook cùng phiên bản trước RUN, không chỉ upload NB10.

## VI. QA cuối và version nghiệm thu

- Targeted đạt 6/6; lượt full cuối 215 tests trong 217.599s, OK với 2 skip có điều kiện, tương đương 213 passed. Hai method thực thi All-in-One được loại khỏi discovery selection, không tính là passed hoặc skip. Log cuối: phase12_regression_verified_2026-10-03.log; log đầu đạt 215/218.628s cũng được giữ.
- Kiểm nbformat/schema/AST đạt: NB10 có 21 cells và 7 business code cells, không cell rỗng vô nghĩa. Không chạy storage/bootstrap thật trong fixture; config/path/display được patch vào workspace tạm, logic SQL/model/prediction/checkpoint/publication/chart không mock.
- git diff --check trên source/notebook/test/plan/guide liên quan đạt. Lịch sử CHANGELOG cũ còn whitespace được bảo toàn, không gọi toàn dirty worktree là sạch. Cập nhật từng NB10 checkbox bằng 33 patch riêng sau đối chiếu per-ID; kiểm 33 checked/0 open và report chứa đủ33IDs.
- Đã mở lại forest/coverage core và forest/error historical ở version cuối, có nhãn synthetic, N/trận đọc được, unit riêng và MAE không có thang âm. Constant-placement panel toàn0 đúng nguồn; không dựng CI R². Strict JSON receipt giữ null/valid_replicates=0/reason=undefined_global_r2.
- Đối chiếu CSV core: P1 có20features, P2/T1 có19, T0/ABL-T có10; Combat/Movement/Support có15/15/16. Tất cả15models đã chọn có20testrows/5trận. T1-T0 delta MAE=0.005894876873127064, CI95%=[-0.0006706838401594837,0.00950913812855578] từ40replicates: chỉ số fixture, CI chứa0, không kết luận timing cải thiện trên PUBG.
- Bootstrap fixture không clip dự đoán, không trộn đơn vị, không average chunk/per-match R²; exact paired identities/targets verified trước delta. Hist fixture mỗi selected model có4testrows/2trận, bins/depth/status được hiển thị; đây không phải chứng nhận chronology/history trên dữ liệu thật.

| File | SHA-256 cuối |
| --- | --- |
| src/evaluation/comparisons.py | 5660e65d53afd131a99816fbd1a8476d09376fb3e06f88852c6459285336a8aa |
| src/evaluation/bootstrap.py | a75b01de69fc3a199f898256bbfad6211e6a21abc23553cc4ddfd383f755fae0 |
| src/evaluation/error_analysis.py | 5f9467730b1781ad6f42235d106c35aec3dce05620d6e19c17d155486caf2717 |
| src/evaluation/importance.py | aa95bb248e51857fd4aa23386bea350c04dda4aaec0efdee83afbbdeb73d0539 |
| src/models/rq3_selection.py | 7271551d09c1b2769e9b61d63db4750c63b76ad76f2d760593d82012de1350cb |
| src/models/rq3_diagnostics.py | 5e8e82ffa6ab7519f8bdad8255344c3a0a3aa7e1ac7a2415e25c63ca53f55938 |
| src/models/training.py | a996b28bdf6b44903b271f5862dbeba37bf201a79ed21c4755334402cba90bbf |
| src/utils/generate_notebooks.py | 51c2ac1b520d31b52fbdabe215dc6e78bb2e6a62f3d30f1a2c066c085d362f30 |
| notebooks/09_rq3_prediction.ipynb | abbf23eb68109ed5e9601b3756b5fd7159e37d0691a2ac1505b688951f4840ba |
| notebooks/10_ablation_error_analysis.ipynb | 8ab39d92d0b96ae6053c1fbcae4b42581e6355dcf78bb83e61721edafc43912b |

Những hash này xác minh version đã kiểm thử, không thay integrity/completeness/approval của release dữ liệu thật. Các report lịch sử Phase11 được giữ nguyên; thay source làm lock cũ stale đúng hợp đồng, cần đồng bộ/rerun development để duyệt G4 phiên bản mới, không sửa hash receipt cũ để ép resume.
