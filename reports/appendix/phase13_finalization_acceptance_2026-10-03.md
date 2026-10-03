# Nghiệm thu giai đoạn 13: Notebook 11 và khóa phiên bản kết quả

## I. Phạm vi và tài liệu đối chiếu

Ngày 2026-10-03. Đối chiếu AGENTS.md, PUBG_RESEARCH_SPEC.md v3.0, PUBG_IMPLEMENTATION_PLAN.md và CHANGELOG_FIXES.md. Chỉ nghiệm thu code và fixture (dữ liệu giả lập nhỏ, cô lập). Không chạy Colab, full-data, GPU, Drive thật hoặc All-in-One. Không thực hiện giai đoạn 14, không commit/push.

Giữ RQ, feature, target, split, cohort, estimator, metric và protocol. Không chốt quyết định production còn null. Storage Drive/root/require-existing/batch50000 và per_mode không đổi. Ponytail giúp dùng lại checkpoint, IO, registry, DuckDB và thư viện có sẵn, không thêm dependency.

G5 production chưa được chứng nhận. Receipt do test tạo chỉ có hiệu lực trong thư mục tạm, không phải approval của nhóm. Thay đổi source làm các G4/checkpoint cũ stale đúng hợp đồng; phải đồng bộ phiên bản và duyệt lại từ bằng chứng development, không sửa hash để ép resume.

## II. Lệnh và bằng chứng kiểm thử

Lệnh hồi quy dùng unittest discovery, chọn tất cả test trừ đúng hai method thực thi All-in-One: `test_all_cells_on_synthetic_data_in_fresh_workspace` và `test_notebooks_block_out_of_order_cells_and_invalidate_success_on_rerun_failure`. Đặt `MPLBACKEND=Agg`, `PUBG_PHASE13_EVIDENCE_DIR=reports/appendix/phase13_fixture_acceptance_2026-10-03`.

Log cuối: [phase13_regression_verified_2026-10-03.log](phase13_regression_verified_2026-10-03.log). Process đã kết thúc exit 0: 217 tests trong 248.572s, OK, 2 skipped có điều kiện, 215 passed, 0 failures/errors. Hai bài All-in-One bị loại khỏi lượt chạy và không được gọi là passed.

Hai skip là kiểm thử GPU thật không có thiết bị/môi trường cần thiết và kiểm thử chmod không thể làm thư mục không ghi được trên Windows. QA cuối: NB11 nbformat schema/AST đạt, kế hoạch có đúng 21 NB11 checked và 21 dòng bằng chứng riêng; source hash không đổi sau regression, snapshot verify vẫn `(True, [])`. git diff --check các file thuộc đợt đạt; cảnh báo LF/CRLF không phải lỗi. Whitespace lịch sử CHANGELOG trước đợt không được viết lại.

Hai test chuyên biệt ở `tests/test_phase13_finalization.py`:

- `test_actual_notebook_release_guards_resume_immutability_and_portability`: chạy chính business cells NB09/NB10/NB11, không thay bằng mock prediction. Kiểm pending approval, scope, stale signature, missing prediction, missing figure metadata, synthetic report_ready, leakage provenance, required schema, stray files, compatible resume, canonical corruption, publication failure, hai release và chuyển release sang thư mục khác.
- `test_empty_invalid_and_legacy_manifests_are_not_complete`: manifest thiếu, rỗng, format không hỗ trợ không được xác minh như release hoàn chỉnh.

Hồi quy đầu có 1 failure và 2 errors, giữ log `phase13_regression_2026-10-03.log`. Hai fixture G4 cũ thiếu descriptive design, sửa factory nhận đúng cfg trước test; không nới production guard. Corruption nay báo cả checksum và schema, sửa assertion kiểm phát hiện đúng artifact thay vì ép chỉ có một thông báo. Các log targeted thất bại/đạt trước đó được giữ nguyên.

## III. Output đã thực thi và đối chiếu

Evidence: [11_fixture.ipynb](phase13_fixture_acceptance_2026-10-03/11_fixture.ipynb), [11_fixture.html](phase13_fixture_acceptance_2026-10-03/11_fixture.html), [manifest snapshot](phase13_fixture_acceptance_2026-10-03/release/final_results_manifest.json).

Fixture CPU có 120 dòng/30 trận, 80 train/20 validation/20 test; final-test 20 dòng/5 trận. RQ2 Duo có 4 profile. RQ1 full-descriptive fixture có 64 dòng thống kê, 14 cột; chữ full ở đây chỉ toàn bộ fixture, không phải dữ liệu PUBG thật.

NB11 có 21 cell, 7 business cells ở index 7/9/11/13/15/17/20, 10 phần khoa học 0-9. Output thực có 10 bảng HTML và 1 PNG. Kiểm stream không in G5 production đạt; in rõ `Chỉ khóa fixture kiểm thử; G5 production chưa được chứng nhận.`

Snapshot `20261003T084643509049Z_550bf1c1` có 37 dòng required/status matrix, 58 bảng, 1 hình, 16 model, 15 prediction và 155 metadata (gồm code/config/spec để tái lập). Đây là tập selected, không phải đếm mọi file trong thư mục. S2/P3 có Grade C, blocked_by_chronology và không có metric giả. RQ2 ID gắn thời điểm execution đã commit; RQ1 có execution UUID; RQ3 dùng run ID của registry.

Đã gọi verifier trên snapshot evidence: `(True, [])`. Đã kiểm SHA source finalize trong reproduction trùng source hiện hành. Đã mở PNG forest và đối chiếu bảng comparisons: N=20, 5 trận; hai panel tách placement score [0,1] và time unit chưa xác minh. Synthetic label rõ, CI chứa 0 không được diễn giải là cải thiện chắc chắn; nhãn model dài nhưng đọc được. Đã kiểm các bảng render và ghi chú source/scope/N/checksum, bảng figure có caption và sampling. HTML được xuất và kiểm nội dung, không tuyên bố đã kiểm browser trên Colab.

## IV. Bằng chứng riêng cho từng task

Các cell index dưới đây tính từ 0. Tất cả dòng chỉ nghiệm thu code/fixture. Test chính là method integration ở mục II; các trường hợp production-specific được kiểm đường gọi/guard, chưa chạy nguồn thật. Không diễn giải một test integration là 21 test độc lập.

| ID | Logic và producer/consumer | Tích hợp và expected/actual | Output và khả năng đọc | Giới hạn |
| --- | --- | --- | --- | --- |
| NB11-01 | inspect_finalization chọn stage/run từ receipt và registry completed | Cell 9/11 chọn đúng G4 executions; không hard-code run | Bảng task và actual run IDs | Approval thật pending |
| NB11-02 | Matrix RQ1, C1-C5/mode, core baselines/S/P/timing/ablation và tables error/importance/CI | Cell 9 tạo 37 dòng; thiếu final prediction bị chặn | Required/status/reason hiện riêng từng dòng | Full coverage thật chưa kiểm |
| NB11-03 | Grade C phải đúng chronology và blocked_by_chronology/null metrics; resource_limited cần evidence | Fixture dùng Grade C thật trong registry test; S2/P3 conditional blocked, không biến lỗi missing file thành exception | Bảng B hiện Grade C và reason; log publication failure có resource_limited | Quota/VRAM thật chưa kiểm; production chronology gọi verify_chronology |
| NB11-04 | G4/current config/code/source/split và selected provenance; production inventory/env guards | Cell 9 chặn development hoặc thiếu leakage provenance | Bảng C/D hiện scope và nguồn metadata | Source shards/units/environment thật chưa nghiệm thu |
| NB11-05 | _committed/checkpoint signatures/checksums, comparison_context/G4 | Đổi rq1 signature thành stale bị chặn; corrupt canonical bị chặn | Bảng C có upstream signature/SHA | Không chấp nhận receipt cũ chỉ vì file tồn tại |
| NB11-06 | Explicit artifact allowlist, không quét CSV/model để tuyển official | Thêm stale_unselected.csv/joblib không lọt release | Bảng C/F đếm selected, không toàn folder | Code/config reproduction scan không phải selection kết quả |
| NB11-07 | Development/failed không thành metric official, optional reason/null | Development receipt bị chặn; incomplete entries giữ status riêng | Bảng B có conditional/optional blocked và reason | Không tự loại required task để ép pass |
| NB11-08 | RQ1 UUID, RQ2 execution timestamp, RQ3 registry run_id/G4 match | Cell 11 hiện run IDs thật của fixture; resume giữ cùng release/execution | Bảng actual run IDs, không rq1_v1 tượng trưng | Producer cũ cần chạy lại phiên bản tương thích |
| NB11-09 | Selected figures bắt buộc và figure catalog đồng bộ | Cell 15 preview forest từ snapshot; thiếu catalog bị chặn | 1 PNG thực, source table selected | Không tuyên bố khóa mọi PNG có trên đĩa |
| NB11-10 | Caption/RQ/source/purpose/scope/sampling/report_ready/version/source SHA | Synthetic report_ready=True bị chặn; version/source hash được gắn lúc publish | Bảng E và caption N=20/5 trận | Chưa có hình official production |
| NB11-11 | Selected fitted model/metadata/features/predictions và provenance bắt buộc | 16 model, 15 prediction, snapshots code/config/env/registry trong release | Bảng C/D/G có paths và hashes | Pickle cần package/backend tương thích |
| NB11-12 | G4 đăng ký descriptive_design trước test; export_locked_rq1 cố định/resume; full RQ1 execution phải gắn current G4 | NB11 opt-in exporter, scope toàn fixture; gọi lại không recompute | Cell 7 bảng artifact mô tả; ghi chú không tune/reselect | Không approve design thật; NB11 không fit RQ2 |
| NB11-13 | Snapshot releases/id; canonical rebased vào snapshot bất biến | Corrupt canonical RQ1 không phá release cũ; tạo release thứ hai vẫn đọc cả hai | Cell 13/20 hiển thị release ID/path | Version ID có chủ đích, không hậu tố file trùng |
| NB11-14 | schema/hash/count/completeness trước publication và read-back trước commit | Required columns sai hoặc file corrupt bị chặn; verifier snapshot True | Bảng C và trạng thái đọc lại cell 13 | Hash không chứng minh kết luận khoa học đúng |
| NB11-15 | Required task chưa giải quyết chặn G5; fixture không report_ready | Missing prediction làm actual NB11 blocked; valid fixture không in production pass | Stream và bảng gate/scope | G5 production pending |
| NB11-16 | Format4/categories/run coverage/content hash, rỗng/legacy bị từ chối | Test invalid/empty/missing manifest trả False | Cell 13 nói rõ integrity khác completeness | Legacy3.1 chỉ integrity_inventory_only |
| NB11-17 | Relative paths + selected snapshots/reproduction/source/config lineage | Copy sang temp root mới verify True, corrupt PNG verify False | Bảng G path/version/SHA, ghi chú tái lập | Đọc portable không đồng nghĩa retrain không cần raw |
| NB11-18 | Gate inspected matrix/artifact_rows trước publish | Cell 9 trước cell 13; missing-case hiện bảng blocked rồi raise | Bảng B/C required/status/reason/run/scope/hash | Validator dừng ở lỗi đầu, không liệt kê hết mọi lỗi cùng lúc |
| NB11-19 | Immutable/canonical distinction, read-back, handover | Cell 13/20 lưu release/final/figure manifests và handover | Bảng release ID/path và G consumer12 | NB12 chưa được nghiệm thu giai đoạn14 |
| NB11-20 | Actual NB11 success/missing + helper stale/corrupt/publish/resume/portable | No-fit guard trong NB11; old/new release đều verify đúng, old canonical giữ khi copy lỗi | Notebook fixture và log có completed/blocked/resource_limited | Không chạy Colab hoặc full-data |
| NB11-21 | Generator 10 phần 0-9, tiêu chí G5/scope/provenance/exception/limitations | 7 business cells thực thi, 10 bảng và PNG inline, không fit/tune | Đọc ghi chú có dấu/caption/cách đọc/giới hạn | Preview fixture không dùng làm kết quả nghiên cứu |

## V. Đường dẫn sử dụng và giới hạn còn lại

Production khi đủ điều kiện: `paths['manifests']/finalization_selection.json` do nhóm duyệt; snapshot ở `paths['manifests']/releases/<release_id>/`; canonical ở `paths['manifests']/final_results_manifest.json`. Không tự chuyển evidence test sang Drive như checkpoint production.

Đồng bộ src/config/notebook cùng phiên bản. Người tiếp nhận chọn đúng manifest rồi verify; không dùng biến RAM của phiên trước. Một người ghi một stage. Không xóa raw/backup/release cũ; partial release chưa commit không phải kết quả chính thức.

Kiểm dung lượng volume không chứng minh Drive quota còn đủ. Remote publication/shortcut permission/Colab RAM/GPU/peak memory, full source coverage, units, chronology, threshold/K và approval thật thuộc RUN. Chưa mở rộng sang summary NB12; giai đoạn 14 là bước tiếp theo sau bàn giao này.

## VI. SHA-256 source/notebook nghiệm thu

| File | SHA-256 |
| --- | --- |
| src/evaluation/finalize.py | 734bd70aa4a7f5d9d3e40a62ce72a2627a82dec432612d51235a78c627c77acb |
| src/models/rq3_selection.py | 6cd16a9c0e19a92cd048ce190a52e914ffc21688985087d8dcf4717ef39bab62 |
| src/analysis/rq2_workflow.py | 094add57b9ddc9081251bcbaa9f22487ae8b7f621d396b117f199bcbfe1eb6ea |
| src/utils/generate_notebooks.py | 2313f361aac8c61960ad01e69318512bb1bb02116f2a0b6f1e5600fd4154e73e |
| notebooks/06_rq1_analysis.ipynb | fd0a8930cd256219b18bb9b475e22f8b7c68275d5de1eed8263a15d4a7fdcc17 |
| notebooks/07_rq2_clustering.ipynb | 0cdd6d5ac87162a052e3fcf66d6a8dabc7687733c17d612c1b064648d21c8435 |
| notebooks/09_rq3_prediction.ipynb | 5413160789c0eb579735112543b966040bc0186f1302b04b5439bcf461b39145 |
| notebooks/11_finalize_results.ipynb | e75ccd52bf99281e714957ef92b61c9bfc9f7b741a68609622b0e9eb7a2363da |
| tests/test_phase13_finalization.py | 2989091398a388cb084728e429abb0ad42c0f89e4c45be9e416ce0c1cf65be2f |
