# Nghiệm thu giai đoạn 14: Notebook 12 tổng hợp chỉ đọc

## I. Phạm vi và nguồn quyết định

Ngày 2026-10-03. Đối chiếu AGENTS.md, PUBG_RESEARCH_SPEC.md v3.0, PUBG_IMPLEMENTATION_PLAN.md và nhật ký giai đoạn13. Giữ RQ/features/targets/cohort/split/leakage/estimator/metric/per_mode/storageDrive/root/require-existing/batch50000. Không chốt tham số production null, không thay protocol.

Chỉ nghiệm thu code/fixture. Không Colab/full-data/GPU/Drive thật, không All-in-One, không commit/push. Dừng sau14; giai đoạn15/G0 và16/RUN chưa thực hiện. Ponytail dùng lại locked verifier/artifacts/IO/pandas/IPython/unittest và fixture NB09/10/11, không thêm dependency/framework.

Files: src/evaluation/finalize.py (load_locked_release và bỏ logger không dùng gây ghi lúc import), summary.py mới; src/utils/notebook_bundle.py (SUMMARY_BOOTSTRAP), generate_notebooks.py; tái tạo riêng NB11/12. Tests test_phase14_summary.py mới, README.md, NOTEBOOK_CELL_GUIDE.md, kế hoạch và nhật ký cùng đợt. Giữ dirty changes cũ và snapshot evidence trước.

## II. Lệnh và kiểm thử

Targeted: `python -m unittest discover -s tests -p test_phase14_summary.py -v`, `MPLBACKEND=Agg`. Lượt đầu4tests/61.180s có1failure freshprocess vì logger import tạo artifacts/logs; log phase14_targeted_2026-10-03.log giữ nguyên. Bỏ logger finalize không dùng, sửa test instrumentation tránh import download logger; không nới invariant. Lượt tiếp4/4 đạt55.506s ở phase14_targeted_verified_2026-10-03.log. Review thêm frozen G4/model/C1-C5 coverage, units/source captions và counts unknown trước hồi quy cuối.

Hồi quy: unittest discovery chọn mọi method trừ đúng hai test thực thi All-in-One `test_all_cells_on_synthetic_data_in_fresh_workspace` và `test_notebooks_block_out_of_order_cells_and_invalidate_success_on_rerun_failure`. Evidence env `PUBG_PHASE14_EVIDENCE_DIR=reports/appendix/phase14_fixture_acceptance_2026-10-03`. [Log cuối](phase14_regression_2026-10-03.log): process exit0,221tests/299.441s,OK,2skipped có điều kiện,219passed,0failures/errors. Hai skip là GPU thật chưa có môi trường và chmod/non-writable không áp dụng trên Windows; không coi skip hoặc hai method All-in-One bị loại là passed.

Các test riêng:

- `test_actual_12_sections_read_only_and_independent_workspace`: chạy bootstrap và mọi business cell NB12 trên copied snapshot, không raw; unrelated current checkpoint running không chặn. Guards cấm config hiện hành, CheckpointManager, fit, pickle, urllib download, mkdir và install; file tree hashes trước/sau không đổi, đủ views và actual output.
- `test_missing_corrupt_legacy_completeness_and_fixture_guards`: fixture không opt-in bị chặn; corrupt/missing/legacy bị chặn; manifest content hash đúng nhưng mất RQ1 hoặc selected model matrix vẫn bị chặn vì completeness. Không sửa file để ép pass.
- `test_findings_values_privacy_and_non_report_ready_figure`: đối chiếu first coefficient/N với CSV, 52 findings đúng source; private sentinel bị loại khỏi frame/metadata; display policy không preview figure report_ready=false như official. Fault injection trong RAM kiểm blocked/resource_limited/failed reasons, không phải publication/approval production.
- `test_fresh_process_without_raw_config_or_checkpoint`: process Python mới, cwd chỉ có portable release; chạy đủ12phần, không raw/config/current checkpoint và workspace file hashes giữ nguyên. Dependencies/source hiện hành được cung cấp qua sys.path, không giả vờ notebook tự chứa mọi package.

## III. Output đã xem và cách đọc

Evidence: [Notebook đã thực thi](phase14_fixture_acceptance_2026-10-03/12_fixture.ipynb), [HTML render](phase14_fixture_acceptance_2026-10-03/12_fixture.html), [manifest](phase14_fixture_acceptance_2026-10-03/release/final_results_manifest.json).

Snapshot fixture `20261003T093206827772Z_2ff07c88`, synthetic_fixture/fixture_locked/report_ready=false. NB12 có32cells/14business, đủ12views,58HTMLtables và1PNG preview đã khóa, không sinh hình mới. Đây không phải số mẫu nghiên cứu; counts nguồn riêng120dòng/30trận, train80/validation20/test20, finaltest20dòng/5trận, RQ2Duo4profile. RQ1 toàn fixture có64association rows;52findings gồm40RQ1 valid primary và12micro-MAE paired comparisons. Không gọi full fixture là full PUBG.

Đã đọc output/captions/source refs của12phần, render HTML và mở PNG forest. Bảng nguồn comparisons có N20/5trận; hình tách placement[0,1] và time unit pending, nhãn synthetic rõ. MAE/RMSE units lấy từ saved mode metrics, R2 không đơn vị/không accuracy. CI chứa0 không đủ chứng minh chiều cải thiện; no CI association được nói rõ. Các bảng feature/cohort/experiment giữ run/SHA/scope. Preview100dòng được công bố; artifact không bị cắt và findings đọc toàn summary chunks, không chọn từ preview.

DQ fixture chưa có raw missing/removal/join/roster audits selected: từng nhóm hiện not_in_release, không tự coi DQ hoàn tất hoặc tải raw để lấp. Counts players/mode/date_range thiếu ở cohort receipt hiện unknown, cohort ledger theo task vẫn được đọc. Header scope chung là phạm vi release; fit_scope/scope của bảng producer phải đọc riêng, không gộp diagnostics development thành final metric. S2/P3 GradeC hiện conditional blocked và reason; metric thiếu không trở thành0.

## IV. Bằng chứng từng task

Cell IDs từ canonical generator. Lệnh/test/scope chung ở mụcII; từng task dưới có logic, notebook caller, output/expected-actual và giới hạn riêng. Không coi14task là14unit test độc lập.

| ID | Logic và file/hàm | Cell và phép kiểm tra thực | Output/cách đọc | Giới hạn |
| --- | --- | --- | --- | --- |
| NB12-01 | load_locked_release nhận path rõ, không directory latest scan; bootstrap không raw | 003/005 actual trên copied manifest; no network/fit/config guards | Audit file/path/run/scope hiện trong bảng | Source/dependencies cần có trước |
| NB12-02 | Format4/hash/schema/count khác matrix/G4/models/C1-C5 coverage | 005; corrupt file và missing matrix dù resealed hash đều fail | Bảng integrity và required states riêng, thông báo đúng lỗi/file/model | Không chứng minh scientific validity hoặc source thật |
| NB12-03 | Chỉ frozen snapshot/selection, không current checkpoint | 005 với unrelated stage03 running vẫn đọc đủ12views | Actual run IDs là locked executions, không latest | Rerun pipeline có thể stale, snapshot vẫn đọc theo provenance cũ |
| NB12-04 | SUMMARY_BOOTSTRAP không mkdir/extract/install/output/checkpoint/env config mutation | 003 và mọi cells với write/manager/install guards; fingerprints bất biến | Stream chỉ đọc manifest, bàn giao không ghi run | Colab mount chưa test thật |
| NB12-05 | render figures chỉ selected source/table và report_ready official; fixture opt-in riêng | 025 preview locked PNG; unit display policy suppress false official figure | Caption/SHA/scope/sample/version và synthetic warning | Chưa có hình official production |
| NB12-06 | Required matrix locked giữ mọi exclusions/reasons; không fake metrics | 015/017/029 GradeC và fault injection3statuses trong RAM | Bảng blocked/resource_limited/failed/reason, không giấu historical | Injection không chứng nhận quota/OOM thật |
| NB12-07 | Findings chép saved numbers; grouping mode/cohort/units/CI, không causal/winner | 011/013/015/017/019/027; first finding khớp CSV/N | Cluster ID cục bộ, MAE/R2/D02 giải thích riêng | Không kết luận PUBG từ synthetic |
| NB12-08 | Selected source_inventory/cohort/ledger/DQ/chronology/leakage, unknown/not_in_release rõ | 007/009 actual120rows/30matches, ledger và GradeC metadata | Missing/removal/join/roster thiếu evidence hiện status; không suy số người | Cơ chế đọc/gate đã kiểm; DQ/source coverage thật còn RUN |
| NB12-09 | public_frame bỏ player/row IDs; metadata_frame không dump record lists/secrets | Mọi display gọi sanitizer; helper sentinel không xuất | Aggregate/profile centers thay assignment names | Không phải cơ chế anonymize arbitrary free text hoặc toàn raw |
| NB12-10 | Bootstrap/imports không yêu cầu raw/config/current workspace stage | Fresh subprocess cwd portable release, SECTION_COUNT12 và không tạo data/config | Một manifest/version để thành viên mới mở, không biến RAM cũ | Dependencies/current source cần đồng bộ, không tự cài |
| NB12-11 | key_findings source table/SHA/run/N/CI/limits; no recompute metrics | 027:52findings/first Spearman và N khớp saved CSV | Phát biểu trung tính có nguồn, uncertainty hoặc cảnh báo thiếu | Không chọn overall winner hoặc p-value causal |
| NB12-12 | Generator12sections mỗi phần question/input/method/reading/limit/status | 007..029 step2; summary_views đúng1..12, mỗi view có bảng | 58HTMLtables/1PNG và missing states, không khối2-12 gộp | Không tự dựng hình nếu không selected |
| NB12-13 | Actual bootstrap/business no raw/newrun/fit/pickle/config/write | main và freshprocess tests, full-tree checks,32cells schema/AST | ipynb/HTML/render và handover031 relative/persistent/SHA/version | Test publication upstream tạo fixture, summary bản thân chỉ đọc |
| NB12-14 | 10khối Phươngán2 liên kết vào0/input/QC/12parts/limitations/handover | Đọc Markdown có dấu, chạy toàn bộ cells, mở PNG và đối chiếu CSV | RQ-phươngpháp-kếtquả-giớihạn, captions/report_ready/blocked/null thật | Không chứng nhận G0/G5production/full-data/Drive/GPU |

## V. Mở báo cáo và bàn giao

Trên Colab giữ storageDrive/root/require-existing/batch50000. Điền `PUBG_SUMMARY_MANIFEST` bằng `artifacts/manifests/releases/<release_id>/final_results_manifest.json` hoặc canonical cụ thể. Canonical có thể đổi sang release khác ở lần mở sau, snapshot ổn định; luôn ghi ID trong bảng. Local chọn runtime, manifest absolute hoặc relative source root; optional `PUBG_SUMMARY_CODE_ROOT`.

Bootstrap chỉ chuẩn bị imports trong RAM và mount nếu cần; không cài requirements hoặc giải nén bundle. Đồng bộ source hiện hành trước, restart kernel khi đổi source; thiếu import/path thì dừng với hướng dẫn, không tạo project mới. Bật allow_fixture chỉ kiểm thử, không dùng approval/score/hình fixture cho báo cáo PUBG.

Summary không ghi handover/checkpoint mới. Việc lưu notebook có output là thao tác bàn giao riêng. Snapshot là tập artifact phục vụ đọc; retrain cần raw/processed và environment/model-pickle compatibility/approval riêng. Full-data, quota, GPU/T4, Drive shortcut/remote publication, chronology/unit/threshold/K/source coverage thật giữ pending ởRUN. DQ thiếu trong snapshot phải bổ sung ở producer/selection rồi khóa phiên bản mới, không chỉnh release cũ từ summary.

## VI. SHA-256 cuối của source/notebook

| File | SHA-256 |
| --- | --- |
| src/evaluation/finalize.py | eceba8fe7124a4303866b2ffe95991a2a19950a57bc22f9589d4181c24a08a96 |
| src/evaluation/summary.py | eccaa31c9b76eb20a7bd56150cc1ae90542df787f430d0a776e00cd194f47a19 |
| src/utils/notebook_bundle.py | 98ea3bc5d394dd655cea029d7c4cf48cfa402b4e3673d1c54391ffca3e1128ee |
| src/utils/generate_notebooks.py | 7afc523abed5a09530ff5109834855cc1e03bdddfff70e088a1f2c9f319e33fc |
| notebooks/11_finalize_results.ipynb | 4726e318cdfb0662d43a74174cd6f85dbe7abd96a6b7b5d7a019f773b9b7c5a4 |
| notebooks/12_final_results_summary.ipynb | 7160d0d27c3783fd15509fdc777385286ce4d48c9ec53ed34c6edf3ffd31860b |
| tests/test_phase14_summary.py | 242ae3f75d5d19f73a0b478b5b363bbab9d4f1f26aea560bdea5c095ca9adde8 |

QA bàn giao: nbformat/schema/AST NB12 đạt; đúng14checkbox và14dòng bằng chứng riêng, không tích QA/RUN thay. Source summary snapshot trùng source hiện hành và notebook hash không đổi sau regression. Loader đọc lại evidence vẫn fixture_locked. git diff --check file thuộc đợt đạt; cảnh báo LF/CRLF không là failure, whitespace lịch sử CHANGELOG được giữ. Dừng sau giai đoạn14.
