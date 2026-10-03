# Hướng dẫn cell notebook 00-12

Cập nhật giai đoạn15 ngày03/10/2026. Bảng cell được đối chiếu canonical generator/notebook, không dùng số cell làm chứng nhận NCKH. Cell ID bắt đầu từ000; ID ổn định trong phiên bản đang đọc, khác số vị trí giao diện Colab. Đặc tả/kế hoạch ưu tiên nếu tài liệu mâu thuẫn.

## I. Cách chạy chung

Giữ Drive/root/require-existing/batch50000 theo README; một người ghi stage. Chạy cell-002 storage, cell-003 bootstrap, rồi nghiệp vụ từ trên xuống. Null/blocked/resource_limited phải đọc reason/action; không bỏ cell lỗi. Runtime mới phải bootstrap/init, không nhận biến RAM cũ. Checkpoint compatible mới reuse.

Bootstrap00-11 chuẩn bị source/config/dependencies/paths; source/config dự án hiện hữu phải đồng bộ trước. Bootstrap12 chỉ đọc, cần source/dependencies và explicit manifest, không tự cài/extract/write. Không chạy hoặc regenerate All-in-One; file đó chỉ là lịch sử, bảng55cell cũ không áp dụng.

Mỗi khối khoa học có câu hỏi/input/phươngpháp/output/cáchđọc/giới hạn. Trước code đọc Markdown; sau code đọc actual tables/PNG inline và source artifact. Scope/N/missing/unit/version quyết định diễn giải, không suy từ tên file. Synthetic/fixture không phải full-data.

## II. Bản đồ cell và cách đọc

### 00_setup.ipynb

Config required/pending, paths, package/hardware/resource và checkpoint. Chỉ môi trường sẵn sàng ingest; disk không là Drive quota, không chứng nhận G0 hay full-run.

| Markdown/cell ID | Code tiếp theo | Nội dung và output cần đọc |
| --- | --- | --- |
| cell-004 | cell-006 | 0. Bối cảnh khoa học, phạm vi và tiêu chí thành công |
| cell-005 | cell-006 | 1. Xác minh project root và provenance đầu vào |
| cell-007 | cell-008 | 2. Nạp và kiểm tra cấu hình nghiên cứu |
| cell-009 | cell-010 | 3. Phân giải đường dẫn và kiểm tra nơi lưu trữ |
| cell-011 | cell-012 | 4. Tài nguyên, phiên bản và snapshot tái lập |
| cell-013 | cell-014 | 5. Trạng thái checkpoint và quan hệ phụ thuộc |
| cell-015 | cell-016 | 6. Kết luận vận hành, giới hạn và bàn giao |

### 01_download_validate.ipynb

Inventory mọi shard/hash/schema/units; parse-error khác missing gốc. Đối soát rows đọc/lưu, batch50000, raw bất biến; completed shard verified mới reuse.

| Markdown/cell ID | Code tiếp theo | Nội dung và output cần đọc |
| --- | --- | --- |
| cell-004 | cell-006 | 0. Bối cảnh khoa học, phạm vi và tiêu chí thành công |
| cell-005 | cell-006 | 1. Phương pháp ingest, bảo toàn raw và resume |
| cell-007 | cell-008 | 2. Provenance, inventory và đối soát dòng |
| cell-009 | cell-010 | 3. Schema, alias, missing/parse và bằng chứng đơn vị |
| cell-011 | cell-012 | 4. Trực quan kiểm toán nguồn và lỗi chuyển kiểu |
| cell-013 | cell-014 | 5. Gate G1, diễn giải khoa học, giới hạn và bàn giao |

### 02_data_quality_and_structure.ipynb

Removal cascade không cộng flags chồng lặp, roster trước task filter. Chronology evidence/availability và match split trước EDA; ratios null phải dừng, không70/15/15 ngầm.

| Markdown/cell ID | Code tiếp theo | Nội dung và output cần đọc |
| --- | --- | --- |
| cell-004 | cell-006 | 0. Bối cảnh khoa học, phạm vi và tiêu chí thành công |
| cell-005 | cell-006 | 1. Tiền điều kiện, provenance và trạng thái quyết định split |
| cell-007 | cell-008 | 2. Identity, duplicate/conflict và removal cascade |
| cell-009 | cell-010 | 3. Roster, metadata conflict và tính nhất quán placement trong đội |
| cell-011 | cell-012 | 4. Chronology audit và bằng chứng Grade A/B/C |
| cell-013 | cell-014 | 5. Khóa split theo config và chronology |
| cell-015 | cell-016 | 6. Trực quan kiểm toán G2 |
| cell-017 | cell-018 | 7. Gate G2, giới hạn và bàn giao |

### 03_build_player_match.ipynb

Base formulas/registry/target; zero denominator là NaN, invalid placement không clip. Row-ID/grain/schema/numberedparts và ví dụ tính tay; hoàn tất03 không phải G3.

| Markdown/cell ID | Code tiếp theo | Nội dung và output cần đọc |
| --- | --- | --- |
| cell-004 | cell-006 | 0. Bối cảnh khoa học, phạm vi và tiêu chí thành công |
| cell-005 | cell-006 | 1. Tiền điều kiện, provenance và phạm vi dữ liệu |
| cell-007 | cell-008 | 2. Feature Registry và hợp đồng chống leakage |
| cell-009 | cell-010 | 3. Tạo player_match_base và báo cáo validation |
| cell-011 | cell-012 | 4. Grain, schema và numbered parts |
| cell-013 | cell-014 | 5. Ví dụ tính tay và kiểm tra target validity |
| cell-015 | cell-016 | 6. Mode audit và giới hạn diễn giải |
| cell-017 | cell-018 | 7. Trực quan kiểm toán |
| cell-019 | cell-020 | 8. Gate G3, giới hạn và bàn giao |

### 04_combat_timing.ipynb

Global count/sum/min, event identity không dedup bằng match/killer/time, absolute/phase riêng. Units/enemy eligibility/duration threshold pending: lưu diagnostics rồi RUN-04 dừng, không fake completed.

| Markdown/cell ID | Code tiếp theo | Nội dung và output cần đọc |
| --- | --- | --- |
| cell-004 | cell-005 | I. Giới thiệu và Khung Lý thuyết về Thời điểm Giao tranh (Combat Timing Theory) |
| cell-006 | cell-007 | II. Trích xuất và Tổng hợp Thời điểm Giao tranh (Combat Timing Aggregation & Audit) |
| cell-008 | cell-009 | III. Event ledger, phase boundary và trực quan timing |
| cell-010 | cell-011 | IV. Ghép nối Bảo toàn Số dòng và Ngữ nghĩa Không có Kill (Safe Left Join) |
| cell-012 | cell-013 | V. Kiểm toán Sai lệch Số mạng Hạ gục và Độ phủ Dữ liệu (Discrepancy & Coverage Audit) |
| cell-014 | cell-015 | VI. Kiểm tra hoàn tất stage NB04 và bàn giao |

### 05_eda.ipynb

Development train+validation loại finaltest. Támnhóm/catalog A01-I03 có source/status hoặc chuyển đúng producer; exact SQL moments/global ranks, sample chỉvisual n/seed/rule. I02 history thuộc08.

| Markdown/cell ID | Code tiếp theo | Nội dung và output cần đọc |
| --- | --- | --- |
| cell-004 | cell-005 | I. Giới thiệu và Khung Phương pháp luận Khám phá Dữ liệu Toàn diện (Full EDA Catalog A01–I03) |
| cell-006 | cell-007 | II. Khám phá Cấu trúc Tổng thể và Phân bố Chế độ Chơi (Group A: Structural Overview A01–A06) |
| cell-008 | cell-009 | III. Kiểm toán Chất lượng Dữ liệu và Khuyết thiếu có Cấu trúc (Group B: Data Quality & Structural Missing) |
| cell-010 | cell-011 | IV. Phân tích Phân bố Đặc trưng Hành vi Thô (Group C: Raw Distributions B01–B10) |
| cell-012 | cell-013 | V. Phân tích Đặc trưng Dẫn xuất và Tốc độ (Group D: Derived Distributions C01–C05) |
| cell-014 | cell-015 | VI. So sánh Hành vi giữa các Chế độ Chơi và Kiểm định Thống kê (Group E: Mode Comparison D01–D08) |
| cell-016 | cell-017 | VII. Phân tích Ma trận Tương quan và Đa cộng tuyến (Group F: Correlation Matrix E01–E02) |
| cell-018 | cell-019 | VIII. Động học Giao tranh theo Phân khúc Thứ hạng (Group G: Combat Timing Dynamics H01–H07 & H06) |
| cell-020 | cell-021 | IX. Đánh giá Khả thi Lịch sử và Đường cong Giữ chân Người chơi (Group H: Historical Feasibility & Retention I01–I03) |
| cell-022 | cell-023 | IX-A. Bổ sung catalog A01-I03 và biên nhận quyết định |
| cell-024 | cell-025 | X. Tổng kết Khám phá Dữ liệu, Khóa Checkpoint và Bàn giao sang Notebook 06 |

### 06_rq1_analysis.ipynb

Primary allowlist từngtarget, Pearson/Spearman/N/status/mode; duration-phase survival chỉdiagnostic. Density sample ghi n/seed/rule, không CI giả, không kết luận nhân quả.

| Markdown/cell ID | Code tiếp theo | Nội dung và output cần đọc |
| --- | --- | --- |
| cell-004 | cell-005 | I. Giới thiệu Câu hỏi Nghiên cứu RQ1 và Khung Phương pháp luận (RQ1 Bivariate Methodology) |
| cell-006 | cell-007 | II. Thực thi Phân tích Quan hệ Hai biến Bắt buộc (Execution of RQ1 Association Pipeline) |
| cell-008 | cell-009 | III. Phân tích Tương quan với Thời gian Sinh tồn (Survival Target S1) |
| cell-010 | cell-011 | IV. Phân tích Tương quan với Thứ hạng Chuẩn hóa Đội (Normalized Placement P1) |
| cell-012 | cell-013 | V. So sánh Hệ số Tương quan giữa các Chế độ Chơi (Solo vs Duo vs Squad) |
| cell-014 | cell-015 | VI. Trực quan hóa Mối quan hệ Hai biến (RQ1 Visualizations) |
| cell-016 | cell-017 | VII. Diễn giải Khoa học, Khuyến nghị và Giới hạn Phương pháp (Interpretations & Limitations) |
| cell-018 | cell-019 | VIII. Nghiệm thu Stage NB06 và Bàn giao sang Notebook 07 (RQ2 Clustering) |

### 07_rq2_clustering.ipynb

Design3 đúng14features, counts/structural missing/ddof1, outcomes riêng. Retention/stability và K không outcome; null dừng. Main per_mode StandardScaler, C2 supporting,C3/C4 common-key/C5 post-hoc; fitted model reload/receipt.

| Markdown/cell ID | Code tiếp theo | Nội dung và output cần đọc |
| --- | --- | --- |
| cell-004 | cell-005 | I. Bối cảnh khoa học, câu hỏi và phạm vi |
| cell-006 | cell-007 | II. Design 3, missing semantics, coverage và retention |
| cell-008 | cell-009 | III. Chẩn đoán K và decision receipt |
| cell-010 | cell-011 | IV. C1-C5, tài nguyên và khả năng tái lập |
| cell-012 | cell-013 | V. Kết quả từng mode, centers, sensitivity và C5 |
| cell-014 | cell-015 | VI. Diễn giải, giới hạn và bàn giao |

### 08_build_historical.ipynb

Authority chronology/report checksum, availability, strict-past count/mean và valid counts riêng. GradeB trướcngày, GradeA trướcavailability/tieblock; C chỉblocked S2/P3. Threshold/protocol null khôngdefault5; diagnostics khác build.

| Markdown/cell ID | Code tiếp theo | Nội dung và output cần đọc |
| --- | --- | --- |
| cell-004 | cell-005 | 0. Câu hỏi khoa học, phạm vi và tiêu chí |
| cell-006 | cell-007 | 2. Công thức và ví dụ tính tay, tách khỏi dữ liệu nghiên cứu |
| cell-008 | cell-009 | 3. Chẩn đoán trước quyết định: coverage, stability và tài nguyên |
| cell-010 | cell-011 | 4. G3: khóa quyết định và protocol; 5. Build strict-past |
| cell-012 | cell-013 | 6. Leakage audit; 7. Coverage và trực quan |
| cell-014 | cell-015 | 8. Diễn giải, giới hạn và 9. Bàn giao |

### 09_rq3_prediction.ipynb

Train/validation only, baseline/S/P/candidates/paired validation, actualdevice/params/resource/reload. G4 explicitselection/bins/comparisons trước test; khôngauto lowestMAE, không refit test. SGD dataframe khôngraw-out-of-core.

| Markdown/cell ID | Code tiếp theo | Nội dung và output cần đọc |
| --- | --- | --- |
| cell-004 | cell-006 | 0. Bối cảnh và câu hỏi khoa học |
| cell-005 | cell-006 | 1. Đầu vào, provenance và đơn vị phân tích |
| cell-007 | cell-008 | 2. Nạp dữ liệu development, không mở final test |
| cell-009 | cell-010 | 3. Cohort, target và leakage |
| cell-011 | cell-012 | 4. Phương pháp, baseline và train-only preprocessing |
| cell-013 | cell-014 | 5. Kiểm tra trạng thái và điều kiện S2/P3 |
| cell-015 | cell-016 | 6. Đọc kết quả validation |
| cell-017 | cell-018 | 7. Trực quan kết quả và cách đọc |
| cell-019 | cell-020 | 7.1. Cặp timing, contribution và mode |
| cell-021 | cell-022 | 7.2. Tài nguyên và bằng chứng chọn feature |
| cell-023 | cell-024 | 8. G4, prior exposure và giới hạn hiện tại |
| cell-025 | cell-026 | 9. Lưu trữ, bàn giao và điều kiện chạy tiếp |

### 10_ablation_error_analysis.ipynb

Saved predictions exactrow-ID sets/target/split/identity, ablation dependencyclosure. Delta=candidate-reference; bootstrapmatch multiplicity, CI95%, errorbins trướctest, importancevalidation uncertainty. Khôngfit/refit.

| Markdown/cell ID | Code tiếp theo | Nội dung và output cần đọc |
| --- | --- | --- |
| cell-004 | cell-006 | 0. Câu hỏi nghiên cứu và phạm vi |
| cell-005 | cell-006 | 1. Đầu vào, provenance và điều kiện G4 |
| cell-008 | cell-010 | 2. Phương pháp so sánh công bằng và ablation closure |
| cell-009 | cell-010 | 3. Hợp đồng metric và bất định |
| cell-011 | cell-012 | 4. T0/T1, P1/P2, baselines và ablation |
| cell-013 | cell-014 | 5. Sai số theo lát cắt và coverage |
| cell-015 | cell-016 | 6. Importance và giới hạn diễn giải |
| cell-017 | cell-020 | 7. Kết quả kỳ vọng, quan sát và kiểm chứng |
| cell-018 | cell-020 | 8. Hạn chế và những gì chưa chứng nhận |
| cell-019 | cell-020 | 9. Lưu canonical, resume và bàn giao Notebook 11 |

### 11_finalize_results.ipynb

Explicitselection với requiredmatrix/cohort/source/config/code/actualruns. Stale/development/incomplete chặn; GradeCexceptions córeason/null. Publication immutable snapshot/read-back; canonicaloverwrite không phá release cũ. Hash integrity khác G5.

| Markdown/cell ID | Code tiếp theo | Nội dung và output cần đọc |
| --- | --- | --- |
| cell-004 | cell-007 | 0. Bối cảnh khoa học và giới hạn phạm vi |
| cell-005 | cell-007 | 1. Mục tiêu và các câu hỏi kiểm tra |
| cell-006 | cell-007 | 2. Đầu vào và bằng chứng lựa chọn |
| cell-008 | cell-009 | 3. Phương pháp kiểm định trước khóa |
| cell-010 | cell-011 | 4. Đối soát và cách đọc kết quả |
| cell-012 | cell-013 | 5. Công bố phiên bản bất biến |
| cell-014 | cell-015 | 6. Hình đã khóa và bảng nguồn |
| cell-016 | cell-017 | 7. Diễn giải khoa học trong đúng phạm vi |
| cell-018 | cell-020 | 8. Hạn chế và quyết định còn mở |
| cell-019 | cell-020 | 9. Artifact và bàn giao sang Notebook 12 |

### 12_final_results_summary.ipynb

Manifest cụ thể, format4/integrity/completeness/selection/scope;12parts từlockedartifacts. No raw/currentcfg/checkpoint/newrun/pickle/fit/download/install/mkdir. DQthiếu=not_in_release, counts thiếu=unknown; figuresofficial report_ready, fixtureoptin.

| Markdown/cell ID | Code tiếp theo | Nội dung và output cần đọc |
| --- | --- | --- |
| cell-004 | cell-005 | 0. Bối cảnh, mục tiêu và kiểm soát chỉ đọc |
| cell-006 | cell-007 | 1. Tóm tắt dữ liệu |
| cell-008 | cell-009 | 2. Chất lượng dữ liệu |
| cell-010 | cell-011 | 3. Kết quả RQ1 |
| cell-012 | cell-013 | 4. Kết quả RQ2 |
| cell-014 | cell-015 | 5. RQ3: thời gian sống sót |
| cell-016 | cell-017 | 6. RQ3: thứ hạng chuẩn hóa |
| cell-018 | cell-019 | 7. Đóng góp Combat Timing T0/T1 |
| cell-020 | cell-021 | 8. Loại nhóm đặc trưng và importance |
| cell-022 | cell-023 | 9. Phân tích sai số |
| cell-024 | cell-025 | 10. Độ bất định |
| cell-026 | cell-027 | 11. Phát hiện chính có truy nguồn |
| cell-028 | cell-029 | 12. Hạn chế và ghi chú bàn giao |
| cell-030 | cell-031 | Bàn giao phiên bản đã đọc |

## III. Đường dẫn, giới hạn và bàn giao

- 01 typed shard/batch_manifest/source_inventory/schema/parse; 02 cleaned_aggregate/match_metadata/split và chronology_report; 03 player_match_base; 04 player_match_features. Đọc resolved paths và handover, không đoán absolute path từ tên.
- 05 EDA/correlation/catalog/decision evidence; 06 rq1_relationship_summary.csv/interpretations/3PNG. Chỉtrain/validation phục vụ lựa chọn trước khóa.
- NB05 cell023 hiển thị catalog hình, bảng nguồn và mẫu trực quan đã lưu; đối chiếu `eda_figure_catalog.csv`, `eda_visualization_sample.csv`, `eda_matches_per_player_distribution.csv`, `eda_teams_per_match_distribution.csv`. N từng cặp hợp lệ có thể nhỏ hơn N scope; sample không thay full-scope statistics.
- NB07 cell013/015 hiển thị figure catalog; `sampling_details` giữ N/population/seed/rule thực theo từng K hoặc nhánh robustness, không dùng một N chung để che mẫu C2 nhỏ hơn.
- 07 profiles development/full-descriptive, tables/rq2/<mode> và fitted objects; 08 historical_status/diagnostics/coverage/leakage và dataset khi eligible.
- 09 models/meta/predictions_<experiment>, development validation/diagnostics, selectionlock; predictions_final_<experiment> chỉ sau G4. 10 comparisons/ablation/errors/importance/CI và sourcecatalog từsaved predictions.
- 11 artifacts/manifests/releases/<release_id>/ có final/figure/selection/reproduction snapshot; canonicalmanifest trỏrelease. 12PUBG_SUMMARY_MANIFEST chọnpath cụ thể, PUBG_SUMMARY_CODE_ROOT khi cần, fixture phảioptin PUBG_SUMMARY_ALLOW_FIXTURE=True.
- Hình03/04/EDA/RQ1/RQ2/history theo paths["figures"]; RQ3 helper có reports/figures qua paths resolver. Output actualhandover/catalog là nguồnpath, không tự ghép reports/figures trái cfg.
- G0 code-ready, G1 source, G2 cohort/split, G3 decisions, G4 testaccess, G5 results. Hoàn tất một stage không tự đạtgate nghiên cứu. Không cóG7 hiện hành.
- ThiếuCUDA không CPUfallback; NB10-12 khôngtrain nên khôngcầnT4. OOM/quota dừnggiữ committed state. Fixture Windows chưa chứng minhDrive/quota/GPU/full-data/peakRAM.
- Sau thành công verify artifact/checkpoint rồisave notebook cóoutput, thayđúngfile Drive/local vớiID/version, không(1)/(2). Báo stage/cell/signature/status/paths/nextconditions cho người nhận; raw/lockedsnapshot giữ nguyên.

Bằng chứng nghiệm thu: báo cáo từnggiaiđoạn và phase15 ở reports/appendix. Các đườngdẫn fixture tạm trong output chỉ để kiểmchứng, không copy receipt/approval lênDrive làm quyết định nghiên cứu.
