# Giai đoạn 15: tích hợp 00-12 và rà soát nghiệm thu

Ngày 03/10/2026. Nguồn: AGENTS.md, PUBG_RESEARCH_SPEC.md v3.0, PUBG_IMPLEMENTATION_PLAN.md, CHANGELOG_FIXES.md. Codex tự thực hiện, dùng Ponytail để tái sử dụng code/tests và không thêm dependency. Không chạy Colab, dữ liệu lớn, GPU/Drive thật hoặc All-in-One. Không commit/push.

## I. Trạng thái và phạm vi

G0 chưa được chứng nhận. Thành công của 13 notebook fixture hoặc bộ hồi quy không thay việc kiểm từng bảng/hình, 10 khối khoa học và tất cả dấu tích lịch sử. Báo cáo này là điểm tiếp tục, không phải tuyên bố hoàn tất mọi QA.

Fixture chung: 120 player-match rows, 30 trận, 4 player giả lập, 2 đội mỗi trận, mode Duo, 3 ngày có timestamp ties, no-kill và phase boundaries, 2 aggregate CSV và 2 event CSV xen kẽ rows xuyên shard. Config chỉ thay trong TemporaryDirectory: CPU, development, K=2/min_games=1, split=.6/.2/.2 và bootstrap20. Chronology chủ động downgrade Grade C qua config để kiểm caller và ngoại lệ S2/P3. Không thay production per_mode/cuda, Drive/root/require-existing/batch50000 hoặc pending decisions.

Mỗi notebook chạy trong process mới, thực thi cả storage/bootstrap và mọi code cell; mock duy nhất dịch vụ Colab mount/download cùng bộ thu output IPython. G4/selection approval chỉ có nhãn fixture explicit, không phải quyết định của nhóm. Raw fixture được so SHA trước/sau; outputs tách namespace. History A/B và các trường hợp lỗi được kiểm riêng bởi test_history_workflow/test_phase11_completion, không giả vờ chuỗi Grade C đã train S2/P3.

## II. Lệnh và các lỗi đã tìm thấy

```text
python -m unittest discover -s tests -p test_phase15_integration.py -v
python -m unittest discover -s tests -p test_w04_base_features.py -v
python -m unittest discover -s tests -p test_phase_b_rq2.py -v
python scripts/run_phase15_tests.py
python src/utils/generate_notebooks.py --only <tên notebook>
```

| Lượt | Log trong reports/appendix | Kết quả và nguyên nhân |
| --- | --- | --- |
| 1 | phase15_targeted_2026-10-03.log | 2 tests, 1 failure: validate_config từ chối development |
| 2 | phase15_targeted_second_2026-10-03.log | 2 tests, 1 failure: YAML mapping khóa số qua JSON thành chuỗi làm NB11 từ chối cấu hình tương đương |
| 3 | phase15_targeted_third_2026-10-03.log | 2 tests, 1 failure: helper display AST bỏ guard bảng rỗng của NB06 single-mode |
| 4 | phase15_targeted_fourth_2026-10-03.log | 2 tests, 1 failure: NB02 không truyền grade_assignment; NB08 availability blocked không hợp lệ để dùng ngoại lệ chronology tại NB11 |
| 5 | phase15_targeted_fifth_2026-10-03.log | 2/2 đạt, 97.813s, chuỗi thực 00-12 có locked fixture và summary12parts |
| Base adapter | phase15_formula_targeted_2026-10-03.log | 8/8 đạt, 4.301s, có actual NB03 |
| C3 scaler | phase15_scaler_targeted_2026-10-03.log | 7/7 đạt, 3.097s; spy native RobustScaler trên core+games matrix |
| Placement adapter | phase15_placement_targeted_2026-10-03.log | 8/8 đạt, 4.217s; zero/invalid/roster/no clipping và actual NB03 |
| Hồi quy trước adapter cuối | phase15_regression_2026-10-03.log | 224 tests, 396.694s, OK, 2 skipped; không dùng chứng nhận source sau thay đổi |
| Hồi quy phiên bản cuối | phase15_regression_verified_2026-10-03.log | 224 tests, 398.850s, OK, 2 skipped, 222 passed, exit0, không failures/errors |

Runner loại chính xác hai method thực thi All-in-One: test_all_cells_on_synthetic_data_in_fresh_workspace và test_notebooks_block_out_of_order_cells_and_invalidate_success_on_rerun_failure. Chúng không được gọi passed/skipped bởi suite đã chọn. Hai skip có điều kiện là CUDA/cuML thật chưa có và chmod/non-writable trên Windows; không gọi GPU passed.

Sửa tại canonical: config mode, NB02 config_grade caller, NB03 scope/G3 claim, inline_saved_outputs giữ IfExp và display đúng PNG/bảng, RQ2 config hash canonical, base/placement adapters dùng chính SQL expressions và C3 assertion kiểm thực dùng. NB07 sửa source catalog/N/units/scope. Không nới required-matrix guard, đổi estimator, fake prediction, chốt null hoặc gọi fixture là full research.

## III. Consumer và bằng chứng QA-01..08

| ID | Logic/caller/cell | Tích hợp và output | Expected/actual, giới hạn |
| --- | --- | --- | --- |
| QA-01 | NB04 final features -> NB05/06 scope -> NB07 load_profiles/final_clustering -> NB08 diagnostics/publish -> NB09 run_rq3_prediction_suite/G4 -> NB10 saved comparisons -> NB11 inspect/publish -> NB12 locked loader | tests/test_phase15_integration.py worker chạy từng notebook riêng; NB07 cells005/007/009/011/013/015, NB08 cells005/009/011/013/015, NB09 cells006..026, NB10 cells006..020, NB11 cells007/009/013/015/020, NB12 cells005..031 | Không cần biến RAM producer; chỉ source/config và artifacts chia sẻ trong root fixture. Grade C đi tới summary với S2/P3 blocked/null, không biến mất |
| QA-02 | src/utils/generate_notebooks.py; NB02 cell012 config_grade, NB03 cell020 scope/handover, NB00-07 tables/Image insertion, NB07 cell013 N/units/catalog | Tất cả canonical regular notebooks đã sinh bằng --only; actual rendered fixture kiểm downstream NB11/12 | NB03 không tự G3; conditional empty table không KeyError; config downgrade tới Grade C; CSV source 07-02 đúng k_diagnostics.csv. Không chứng nhận mọi caption đã review |
| QA-03 | Bootstrap bundle chứa source/config nên source changes ảnh hưởng 13 regular files | Trước regenerate 13 canonical notebooks đều không output; outputs mới chỉ ở appendix/fixture, backup cũ giữ nguyên | Không mất output nghiên cứu, không viết All-in-One, không thay file người dùng ngoài phạm vi. Notebook canonical không nhúng kết quả giả lập |
| QA-04 | test_notebook_schema_ast_and_accented_headings, nbformat.validate và ast.parse mọi code cell | 13 notebooks schema hợp lệ, không cell rỗng; headings có dấu | Cell count chỉ inventory, không chứng nhận khoa học. Accent heuristic chưa thay manual QA-24 |
| QA-05 | NB03 gọi build_player_match_base/FeatureRegistry; NB04 canonical combat_timing; NB07 clustering workflow; NB08 history_workflow; NB09 training; NB10 comparisons; NB11/12 finalize/summary | Base/placement dataframe adapters dùng SQL canonical, actual NB03 và cả chuỗi kiểm NaN/index/row conservation | Plot/hand-calculation minh họa không thành feature implementation. Toàn repo formula audit vẫn phải khép QA-13/16 trước G0 |
| QA-06 | scripts/run_phase15_tests.py flatten/filter suite | Ma trận được kiểm bởi test_w02_ingest_schema, test_batch_ingest, test_w03_cleaning_roster_split, test_w04_base_features, test_w05_combat_timing, test_phase_b_rq2, test_history_workflow, test_phase11_completion, test_phase12_comparisons, test_phase13_finalization, test_phase14_summary và phase15 actual chain | Schema fail/aliases, xuyên shard/resume, roster/ratio/boundary/reduce/lineage, history/ties/mutation, train-only/pairing/bootstrap, stale/no fallback/required files/read-only đều có assert riêng. Lỗi mới được giữ log, không xóa test |
| QA-07 | worker từng notebook trong subprocess timeout240; bootstrap thật, service mock | Snapshot .ipynb có outputs, HTML và process .log từng 00-12 trong phase15_fixture_acceptance_2026-10-03/notebooks khi lượt cuối đạt | assert all notebook HTML; NB01-07 PNG; NB00-11 checkpoint completed; NB12 summary_views12; raw fixture hashes không đổi; release fixture=True. Không có full/GPU/Drive claim |
| QA-08 | CheckpointManager signatures/read-back/single-writer, canonical publishers; tests/test_phase1_infrastructure_contract.py, test_rq2_workflow.py, test_batch_ingest.py, test_phase13_finalization.py, test_phase14_summary.py | Compatible resume không rebuild profile, completed shard reuse; failed publication giữ bytes tốt; second release không phá snapshot, portable release đọc không raw/config/checkpoint/RAM phiên cũ | Không tạo filename hậu tố để bypass; root stale/takeover có gate. Đây là fixture/filesystem, file ID/quyền/quota Drive thật giữ RUN-01/12/13/14 |

## IV. Inventory bảng/hình của chuỗi thực

Đếm từ notebook outputs của lượt hồi quy đầu, không phải số file path tồn tại. Lượt cuối cập nhật ở cùng namespace acceptance. HTML được xuất bằng nbconvert; PNG là byte của file canonical, không hình giả. Mỗi bản .ipynb/.html/.log có tên tương ứng trong thư mục notebooks.

| NB | Cells | Bảng HTML | PNG inline | Cell đọc chính và giới hạn |
| --- | --- | --- | --- | --- |
| 00 | 17 | 11 | 0 | 006..016: config/resources/checkpoint; không ép biểu đồ setup |
| 01 | 15 | 9 | 2 | 008/010/012/014: inventory/schema/missing/parse/G1 fixture |
| 02 | 19 | 13 | 4 | 008..018: ledger/roster/chronology/split/G2 fixture |
| 03 | 21 | 14 | 3 | 008..020: dictionary/base/schema/formula/task/mode/handover |
| 04 | 16 | 14 | 3 | 005..015: events/timing/coverage/safe join; timing evidence chỉ fixture |
| 05 | 26 | 11 | 14 | 005..025: EDA catalog/tables/plots; development96rows, không dùng24testrows |
| 06 | 20 | 5 | 3 | 005..019: coefficient/N/interpretations, một Duo mode; empty mode-comparison hợp lệ |
| 07 | 16 | 16 | 6 | 005..015: Design3/retention/K/C1-C5/centers/C5/catalog; 4 profiles, K2 fixture |
| 08 | 16 | 12 | 1 | 005..015: chronology/feasibility/blocked; không fake depth/stability/model PNG Grade C |
| 09 | 27 | 15 | 6 | 006..026: real fit train72/validation24/test24; G4 approval fixture explicit |
| 10 | 21 | 15 | 7 | 006..020: saved comparison/pairing/delta/CI/errors/importance; không train |
| 11 | 21 | 10 | 1 | 007..020: selection/matrix/snapshot/catalog/handover; fixture_locked/report_ready=False |
| 12 | 32 | 58 | 1 | 005..031: 12 views, findings/exclusions/relative paths; read-only release cụ thể |

Các số đếm trên chỉ chứng minh render/tích hợp, không tự nghiệm thu QA-19/20/21/25/26. Phải đối chiếu deliverable cụ thể và 10 khối, không dùng một hàng đếm để tích cả notebook.

## V. Review trực quan đã thực hiện và phần còn mở

Đã mở PNG từ phase15_fixture_final_2026-10-03/figures và đối chiếu nguồn:

- nb01_missing_vs_parse.png: 300 records (120 aggregate +180 events), 4 shard; missing/parse đều0 hợp lệ, chart zero không lỗi hoặc bằng chứng dữ liệu thật sạch.
- nb02_split_distribution.png: 30matches, train18/validation6/test6, player rows72/24/24; khớp split ledger và config fixture, không resplit sau test.
- nb04_player_match_coverage.png: exact-event90 +confirmed-no-kill30 =120 player-match; khớp coverage source, không gọi missing events=no-kill.
- rq2/Duo/cluster_centers_heatmap.png: 14 core columns, N4profiles, 2clusters, z-score; không outcome predictor, cluster tên từ behavior.
- rq2/Duo/outcome_distributions.png: N4 và validN4 cho từng outcome; placement[0,1], survival unit chưa xác minh; hậu nghiệm, không dùng chọn K hoặc tên cụm.
- rq1_scatter_density.png: development N96, reservoir seed42, placement[0,1], count trên colorbar; không dùng sample để thay coefficient/N thống kê đầy đủ scope.
- history_collisions.png: 120rows cùng timestamp/cùng ngày, hai count có thể chồng; khớp history_chronology_collisions.csv và không cộng thành240 lỗi riêng.
- rq3_evaluation_forest.png: locked fixture test N24/6matches, delta MAE candidate-reference và95% match-bootstrap CI; CSV có baseline mean/median riêng, placement unit score[0,1], survival unit pending. Chỉ micro CI hữu hạn được vẽ, không suy causal hoặc model thắng từ fixture.
- eda_group_g_behavior_vs_outcome.png: đã mở, trục placement[0,1] và raw behavior. PNG riêng chưa thể hiện N/scope/seed/rule hoặc colorbar; catalog hiện có sample_n96/seed42/rule nhưng cần review liên kết caption/manifest cho deliverable này. Chưa công nhận đạt chuẩn biểu đồ tách riêng.

Chưa mở và đối chiếu đầy đủ mọi PNG/deliverable ở bảng/hình kế hoạch. 51 PNG trong namespace figures có cả export full-descriptive đã khóa fixture và outputs development, không phải tất cả là official. Không được tích QA-09/19/26 hoặc gọi kiểm đếm=visual pass.

Điểm tiếp tục theo thứ tự: QA-09, kiểm toàn danh mục deliverable và bảng nguồn; sau đó QA-10..27 gồm README20mục, audit15câu §84, mọi dấu tích lịch sử, ngôn ngữ/caption, ma trận10khối00-12 và chart sample disclosures/manifest. Việc này chưa có đủ bằng chứng cuối trong đợt hiện tại, nên G0 vẫn mở. Không tự tích GPU/Drive thật; không xóa history. Xem phase16_preflight_2026-10-03.md để chuẩn bị mà chưa thực thi.

Kết quả cuối: QA-01..08 được nghiệm thu riêng theo mục III sau hồi quy exit0; QA-09..27 vẫn mở. Không được chuyển trạng thái G0/G5production hoặc tích RUN từ222passed. Trước khi đóng QA-09 cần review toàn bộ PNG/CSV/caption, sau đó tiếp tục đúng thứ tự. Việc chuẩn bị giai đoạn16 là tài liệu preflight theo yêu cầu người dùng, không phải chạy giai đoạn16 vượt gate.

## VI. Phiên bản môi trường và source

Windows11/Python3.13.5; numpy2.2.6, pandas2.3.0, duckdb1.5.5, pyarrow23.0.1, scikit-learn1.7.0, nbformat5.11.0, nbconvert7.17.1, matplotlib3.10.3, PyYAML6.0.3. Không suy các phiên bản này là Colab package lock.

| File | SHA256 phiên bản kiểm cuối |
| --- | --- |
| src/features/base.py | 8555280859e1d9a7433e787794edb0fa9305d8bf13d92d275fce3725405535d9 |
| src/features/placement.py | a804bb50f73c4660a59f1ea11f4d76b2e20bac68c232cbe4a762d6333c05b285 |
| src/utils/generate_notebooks.py | ddbb6d11aa0291dd621f29c12f4a6face2d5aa51c3a9329382286158d5b22697 |
| src/evaluation/finalize.py | 96a2fc41d9e68f10602bcadec51fdc8836437729023149ab47bd368c15a9c15d |
| src/utils/config.py | dcf54f91e79599cc08e5a4bc5ae4a7b9161e57508806e4ef05c3333dddfd4355 |
| tests/test_phase15_integration.py | 2387dff5fe694cdbbe188d662c1d710bb142a3ce3ae29517cdc27498d054f1d7 |

Source/config changes invalidates current G4/signatures theo hợp đồng; locked release đọc độc lập current workspace. Không sửa hash cũ để ép resume. Fixture evidence không thay canonical notebooks hoặc checkpoint production.

Read-back cuối: snapshot fixture20261003T103657876636Z_7af4922a tải được bằng load_locked_release(allow_fixture=True), report_ready=False; năm source canonical trong reproduction khớp bytes hiện hành. Inventory output lượt cuối khớp mục IV. Kế hoạch đúng8QAđã tích/19QA mở,18RUN mở; checkpoint production01 vẫn running/artifacts rỗng, không bị sửa. Bundle00 có67source/config files khớp bytes và không raw/artifacts. Các file code/docs đã kiểm diff whitespace đạt; không gọi đó là bằng chứng đầy đủ khoa học.
