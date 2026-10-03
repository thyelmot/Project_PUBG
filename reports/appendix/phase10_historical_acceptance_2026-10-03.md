# Nghiệm thu giai đoạn 10: Notebook 08

Ngày: 03/10/2026. Phạm vi: code và fixture cô lập, không phải nghiên cứu chạy toàn dữ liệu.
Đối chiếu: `PUBG_RESEARCH_SPEC.md` v3.0, `PUBG_IMPLEMENTATION_PLAN.md` giai đoạn 10, `AGENTS.md`.
Không chạy Colab, Drive, GPU, All-in-One hoặc dữ liệu thật. Không đổi RQ, split, estimator hay metric.

## I. Phiên bản, lệnh và dữ liệu kiểm thử

Code hash của workflow: `08d4eb52207c3b6f9fb50da8b0d7e548f2cee25938224af1e8794ea95f2698e9`.
Hash khóa workflow, historical, registry, IO, checkpoint, hashing và generator; receipt/status lưu riêng hash input/config.
Ngưỡng fixture là 2, ứng viên 1/2/3/50; không ghi các giá trị này vào config nghiên cứu.

Fixture: 24 player-match, 12 trận, hai người, Solo/Duo, sáu ngày UTC; hai trận/ngày.
Train ba ngày đầu, validation hai ngày tiếp, test ngày cuối; diagnostics có 20 dòng, không dùng bốn dòng test.
Timestamp fixture là match start, statistics available một giờ sau. Đây không phải evidence của dữ liệu PUBG.

Lệnh chuyên biệt thực chạy:

```powershell
$env:MPLBACKEND='Agg'
$env:PUBG_HISTORY_EVIDENCE_DIR='reports/appendix/phase10_fixture_2026-10-03'
python -m unittest discover -s tests -p test_history_workflow.py -v
```

Kết quả: 9 test đạt, gồm thực thi sáu cell nghiệp vụ của notebook sinh thật trên bốn nhánh.
Storage/config fixture thay bằng namespace tạm; không chạy bootstrap, mount, network hoặc export Colab.
Bảng HTML, hình PNG và caption Markdown đều được bắt từ `display` thật và render bằng nbconvert.
Không mock SQL, lịch sử, checksum, leakage audit, chart hoặc dự đoán trong lượt này.

Kiểm thử hồi quy dùng `unittest.defaultTestLoader.discover('tests')`, lọc chính xác hai method:
`test_all_cells_on_synthetic_data_in_fresh_workspace` và
`test_notebooks_block_out_of_order_cells_and_invalidate_success_on_rerun_failure`.
Hai method có đường thực thi All-in-One nên bị loại, không được tính là pass.
Lệnh chạy bộ suite đã lọc và log nằm ở [phase10_regression_2026-10-03.log](phase10_regression_2026-10-03.log).
Lượt cuối: 199 test, kết quả OK, 2 skip có điều kiện, 0 failure/error (164.354 giây).
Log chuyên biệt: [phase10_history_tests_2026-10-03.log](phase10_history_tests_2026-10-03.log).
`git diff --check` trên các file sửa trong đợt đạt; không sửa khoảng trắng trong lịch sử nhật ký cũ.

## II. Output đã render và đã xem

| Nhánh | Expected và actual status | Dataset hiện hành | Hình inline |
| --- | --- | --- | --- |
| null | pending/minimum_history_threshold_pending | Không tạo mới | 4 |
| selected, Grade B | completed, 20/24 eligible | Dataset strict previous days | 5 |
| selected_a, Grade A | completed, 20/24 eligible | Dataset strict availability timestamp | 5 |
| grade_c | blocked/blocked_by_chronology | File cũ có thể còn nhưng stale, không bàn giao | 1 feasibility |

Bản render: [null](phase10_fixture_2026-10-03/null/08_fixture.html),
[Grade B](phase10_fixture_2026-10-03/selected/08_fixture.html),
[Grade A](phase10_fixture_2026-10-03/selected_a/08_fixture.html),
[Grade C](phase10_fixture_2026-10-03/grade_c/08_fixture.html).
Mỗi thư mục giữ bản `.ipynb` có output và bản sao tables/figures/manifests/checkpoints/processed/interim nhỏ.
Paths tuyệt đối trong output và manifest là namespace tạm tại thời điểm thực thi; bản lưu chỉ để xem bằng chứng,
không phải checkpoint nghiên cứu có thể dùng thẳng trên Drive. Tái lập bằng lệnh test trên.
File cũ có thể còn trong thư mục nhánh blocked; chỉ artifacts của manifest hiện hành được chấp nhận.

Cell sinh thật: `cell-005` cấu hình/grade/report, `cell-007` ví dụ/dictionary,
`cell-009` diagnostics, `cell-011` quyết định/build/status, `cell-013` audit/coverage/hình,
`cell-015` bàn giao/checksum. Các nhánh đều hiển thị ít nhất 10 bảng DataFrame.
Notebook feasibility checkpoint completed không được đọc thành completed model training.

Đã mở năm PNG của Grade B, đối chiếu các bảng CSV và xem lại hai hình sau chỉnh trình bày:

- 08-01: development N=20, depth 0/2/4/6/8 có bốn dòng mỗi mức; trục số đếm nguyên.
- 08-02: retention ngưỡng 1/2/3/50 tương ứng 16/16/12/0 trên mẫu số 20.
- 08-03: sáu behavior features có đơn vị nguồn, valid transition; ngưỡng 50 thiếu transition được ghi rõ, không fill-zero.
- 08-04: timestamp collision ảnh hưởng 0 dòng, same-day ảnh hưởng 24; hai loại không cộng thành tổng dòng lỗi.
- 08-05: cold start=4, eligible=20 ở threshold 2; train/validation/test và Solo/Duo/ngày đối soát tổng N=24.

Chú giải coverage đã chuyển sang tiếng Việt và không che cột; tên nhóm/split, trục, N đọc được.
Caption, cách đọc, giới hạn, scope, version và bảng nguồn lưu ở `history_figure_catalog.csv`.
Các hình là SQL summary đúng scope, không lấy mẫu raw point và không được coi là metric mô hình.

## III. Bằng chứng riêng từng công việc

Các test dưới đây thuộc `tests/test_history_workflow.py`, trừ khi ghi khác.
Mỗi dòng dùng cùng lệnh mục I, expected đối chiếu actual bằng assertion và output mục II.

| Task | File/hàm, cell | Điều kiểm tra và kết quả | Output hoặc giới hạn |
| --- | --- | --- | --- |
| NB08-01 | historical.threshold_value, workflow.publish; cell-005/011 | null giữ pending, không dùng 5; threshold 2 truyền từ config; bool/nonpositive bị từ chối | null/selected status; feasibility vẫn completed |
| NB08-02 | workflow.diagnostics/publish; cell-009/011 | 20 development rows; retention 16/16/12/0; thiếu lý do/receipt và receipt stale bị chặn | history_coverage/stability và diagnostics receipt; ngưỡng thật pending |
| NB08-03 | verify_chronology; cell-005/009 | Report hash sai, match/date mismatch, Grade A thiếu evidence đều bị từ chối | test_input_chronology_and_consumer_integrity; report gắn metadata_checksum từ NB02 |
| NB08-04 | history_query; cell-007 | Ví dụ A counts 0/0/2/3; B 0/0/0/3; mean 3 và 14/3 đúng tay | Bảng 08-D; tie không phá bằng ID |
| NB08-05 | history_query; cell-005/009 | Unverified availability blocked; trận còn chạy không vào history; duration survival bị từ chối | test_start_duration_policy_and_corrupted_audit; chỉ evidence synthetic, dữ liệu thật pending RUN-07 |
| NB08-06 | publish; cell-011 | C ghi blocked S2/P3 và checksum input/code/config; không tạo fake dataset | grade_c status/checkpoint; absence của historical_features trong artifact list |
| NB08-07 | publish/require_historical_dataset; cell-011/015 | B chuyển C giữ nguyên hash bytes cũ nhưng rq3 checkpoint stale và consumer bị chặn | test_grade_c_and_unverified_availability_never_make_fake_dataset |
| NB08-08 | publish; cell-011/015 | Feasibility completed trong nhánh pending/C; historical không completed; notebook chỉ commit đúng artifacts của nhánh | bốn checkpoint_manifest.json |
| NB08-09 | history_query/FEATURES; cell-007 | Có tám valid counts; thiếu một kills cho games=2, kills_count=1, damage_count=2, mean kills=4 | test_counts_missing_identity_no_eligible_and_registry |
| NB08-10 | history_query; cell-007/013 | Cold start games=0, toàn bộ tám mean missing, không biến thành 0 | bốn leakage checks đều observed=0 trên 24 dòng |
| NB08-11 | FeatureRegistry; cell-007 | hist_kd candidate, không nằm trong S2 allowlist | D06 chưa có death denominator; không tạo hist_kd giả |
| NB08-12 | history_query/leakage_audit; cell-013 | Per-row cutoff/max_available/grade/policy; sửa max_available bằng cutoff làm audit fail | historical parquet; strict_past_availability expected 0 |
| NB08-13 | diagnostics/history_query; cell-009 | Thêm một blank player thì identity exclusions=1; không tạo UNKNOWN profile | history_identity_exclusions.csv; player_name không phải ID bất biến |
| NB08-14 | history_query; cell-007 | Expanding block sums/counts, ngày cuối dùng cả 10 trận cũ; không rolling/same-mode mặc định | test mutation; optional extensions không bật |
| NB08-15 | publish; cell-011 | Null evaluation_protocol chặn build; chỉ core walk_forward_fixed_model được hỗ trợ; nhóm chưa chốt production | blocked quyết định thật, giữ checklist mở; dependency RUN-07 trước G4 |
| NB08-16 | diagnostics/publish; cell-009/011 | DuckDB 256MB, 1 thread; spill planning/recheck; MemoryError giữ bytes và resource_limited | test_reuse_and_failure_preserve_verified_bytes; không chứng nhận peak/quota/full-data |
| NB08-17 | publish/require_historical_dataset; cell-011/015 | Hash nguồn/metadata/split/report/code/config; bảng diagnostics đổi bị chặn; scope khác bị chặn; artifact checkpoint checksum | status/receipt/checkpoint; không reuse chỉ vì exists |
| NB08-18 | history_query; cell-007/013 | Đổi outcome ngày hiện tại và tương lai không đổi toàn hist_* của ngày hiện tại Grade B | test_strict_availability_overlap_ties_timezone_and_mutation |
| NB08-19 | history_query/illustrative_history; cell-007 | Shuffle processed rows và row groups giữ kết quả; timezone +07 tie đúng UTC; expected means/counts tính tay | Bảng 08-D và mutation fixture; không thay full dataset bằng sample |
| NB08-20 | publish; cell-011 | Threshold 50 tạo zero eligible, blocked/no_eligible_history, consumer bị chặn | valid descriptive dataset không phải đủ train |
| NB08-21 | publish; cell-011 | C chỉ block S2/P3; S1/P1/P2 trong registry vẫn planned theo điều kiện riêng | Bảng 08-I; không chứng nhận các task hiện tại đã chạy |
| NB08-22 | history_query/FeatureRegistry; cell-007 | Source player_match raw features, không đọc profiles RQ2; tám mean/count và games | dictionary historical; hist_kd không input |
| NB08-23 | history_query; cell-007 | Cumulative sums/counts theo player availability-day; các trận cùng ngày có chung past; A strict ASOF whole block | counts tay A/B; không dùng partial mean average hoặc row order |
| NB08-24 | history_query + training.train_and_predict_experiment | Đổi validation outcome làm later-test hist mean tăng đúng 1; S2/P3 baseline fit đúng một lần trên train, test-label đổi không đổi prediction | test_historical_handoff_fits_once_on_train_not_test; chỉ helper CPU fixture, NB09 toàn workflow và GPU chưa nghiệm thu; frozen sensitivity không bật |
| NB08-25 | generator NB08; cell-005 tới 015 | Có cấu hình/chronology/availability, diagnostic/decision, strict-past/audit/coverage/bàn giao, bảng A/B/C | bốn notebook render; chỉ gate G3 |
| NB08-26 | illustrative_history; cell-007 | Current time/cutoff/max available/count/mean hiển thị; expected A/B tay; cold start diễn giải riêng | Bảng 08-D synthetic duration 0 độc lập input |
| NB08-27 | diagnostics/create_figures; cell-009/013 | Null vẫn có depth/retention/stability và development coverage; selected có split/mode/date coverage; null không tự chốt | 08-01/02/03/05, bảng nguồn và catalog |
| NB08-28 | leakage_audit; cell-013 | Expected/observed/violations/status hiển thị; bốn checks 0/0; corrupt audit fail; mutation test ngoài report phân biệt rõ | selected audit + grade_c chỉ feasibility image |
| NB08-29 | test_real_notebook_cells_null_selected_and_grade_c; cell-005 tới 015 | Thực thi sáu cell thật qua bốn nhánh; config null/2; reload require guard; artifact list theo nhánh; reuse không rebuild; rerun một canonical name | .ipynb/.html và checkpoint bốn nhánh; không mount Drive |
| NB08-30 | generator + create_figures; toàn notebook | Ghi chú/công thức LaTeX/tiếng Việt có dấu; bảng inline, năm PNG đã mở; nguồn/N/scope/units/caption và limitations khớp | mục II, source CSV; không gọi synthetic là kết quả PUBG |

## IV. Điểm bàn giao và giới hạn

NB08-15 chưa được chốt cho nghiên cứu thật. `minimum_history_threshold`, lý do/receipt quyết định,
availability evidence và `evaluation_protocol` vẫn null/pending trong `configs/rq3.yaml`.
Cơ chế chặn đã kiểm thử; chỉ nhóm quyết định tại RUN-07 sau khi có evidence/diagnostics thật.
Không bật sensitivity frozen-history hay optional history để né quyết định.
Không thay đổi protocol bằng giá trị fixture. `hist_kd` tiếp tục candidate theo D06.

Đã sinh lại riêng NB02 (checksum chronology), NB03 (dictionary mở rộng, gate chỉ kiểm 26 features cơ sở)
và NB08 (caller/trình bày). Không sinh hoặc thực thi All-in-One.
Notebook gốc không gắn output synthetic thành output nghiên cứu thật; evidence được lưu riêng.
Chưa sửa hoặc chạy quy trình huấn luyện toàn NB09, chưa sang giai đoạn 11.
Không chứng nhận GPU, Drive replacement/version hay full-data; các mục RUN vẫn mở.
