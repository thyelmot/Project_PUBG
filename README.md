# PUBG Coursework: một notebook, ba câu hỏi nghiên cứu

Đây là bản xây mới độc lập tại PUBG_Coursework. Notebook chính: [PUBG_COURSEWORK.ipynb](notebooks/PUBG_COURSEWORK.ipynb). Các module src, config và tests đều được viết mới; không dùng lại code hoặc checkpoint của Project_PUBG cũ.

Dự án trả lời RQ1 (quan hệ hành vi), RQ2 (phân nhóm hành vi per_mode), RQ3 (hồi quy hậu trận survival/placement và đóng góp timing). Nội dung bám C1/C2/C6/C7 và nguyên tắc đánh giá C4. C3/C5 cùng RF/history/DBSCAN là mở rộng, chưa triển khai; không cần ép mọi chương vào bài cuối kỳ. Thiết kế khoa học tại [đặc tả](PUBG_RESEARCH_SPEC.md), tiến độ tại [kế hoạch](PUBG_IMPLEMENTATION_PLAN.md).

## Chạy trên Colab Pro, notebook riêng

Mở [PUBG_COURSEWORK_COLAB.ipynb](notebooks/PUBG_COURSEWORK_COLAB.ipynb) bằng Colab > File > Upload notebook. Không cần upload kaggle_code.zip hoặc Dataset code: 15file code/config/requirements/đặc tả được đóng kèm. Notebook Kaggle cũ không đổi; biến thể Colab được người dùng yêu cầu riêng, dùng cùng section/phương pháp nghiên cứu.

1. Chọn Runtime > Change runtime type > GPU; chọn High RAM nếu có. Mặc định dùng GPU0, không cần haiT4. Chạy cell1 cấu hình và cell2 cài môi trường; nếu cell2 yêu cầu, chọn Runtime > Restart session rồi Run all lại. Không Disconnect and delete runtime. Nếu CUDA_FAMILY không khớp nvcc, đặt cu12/cu13 đúng thông báo; không tự fallback CPU.
2. Cho phép mount Drive. Raw tải bằng Kagglehub đúng skihikingkevin/pubg-match-deaths/versions/3 về runtime. Public dataset không cần token trừ khi nguồn yêu cầu auth/đồng ý điều khoản; khi cần, dùng Colab Secrets KAGGLE_API_TOKEN hoặc KAGGLE_LOGIN=True, không dán token vào cell/output. Không cần chép bộ CSV18.9GiB lên Drive trước.
3. Mặc định chạy full S01-S10 tự động, vẫn chỉnh OPTIONS ở từng section được. Project/checkpoint nằm trong Drive/PUBG_Coursework_Colab_v511; raw/cache/SQL/spill/ma trận tạm ở runtime. Drive có thể chậm hơn ổ tạm, nhất là JOIN đọc lại. Cần tự kiểm Drive còn khoảng25GiB; Colab Pro không xác nhận quota Drive. Guard project18GiB và reserve55GiB local không bảo đảm đủ toàn pipeline.
4. Phiên sau mở lại đúng notebook/root, giữ phần mềm tương thích, cài lại nếu cần rồi Run all. Completed chỉ reuse sau kiểm code/config/software/source/checksum; phần mềm khác bị chặn trước thay config, không ép trạng thái. Nếu stage dở có lock, chỉ takeover khi chắc phiên cũ đã dừng. Không chạy hai writer cùng root. USE_GOOGLE_DRIVE=False lưu runtime và có thể mất khi VM bị thu hồi; lưu notebook không lưu model/data.
5. report_only: chuẩn bị môi trường trước, đặt EXECUTION_MODE="report_only" và RELEASE_MANIFEST là release.json cụ thể; không cài/giải nén/download raw/copy/build/train/ghi project trong lượt đọc. Handoff cuối kiểm file qua mount, không xác nhận remote cloud sync hoặc Kaggle Version.

Tái tạo notebook Colab: python -B tools/build_colab_notebook.py. Chỉ thay adapter ở tools, không sửa src hoặc phương pháp để hợp phần cứng. Bộ cuối106/106tests local đạt, gồm6tests Colab với externalGPU/pip/Kaggle/Drive giả lậpCPU và actualcells đủ10stage/reuse/report_only. Cố định cuML/cuDF26.2.* và CuPy>=13.6/<14, không chọn26.10 vì yêu cầu pandas3 xung đột core<3; Kagglehub1.0.2. Nguồn hướng dẫn chính thức: [Colab FAQ](https://research.google.com/colaboratory/faq.html), [Kagglehub](https://github.com/Kaggle/kagglehub), [RAPIDS](https://docs.nvidia.com/datascience/install/). Chưa nghiệm thu GPU/Drive/runtime Colab thật, resolverLinux thực hoặc toàn nguồn PUBG; localtests/metadata không thay thế kiểm thực đó.

## Bản5.11: giảm bản sao dữ liệu và chuyển S01 có kiểm

Bản5.11-normalized-storage xử lý lỗi thực tế ngày20/10: project18.018GiB/budget18GiB, còn1.484GiB; cleaned10.681GiB ngoài aggregate3.173GiB/event4.163GiB. Không tăng budget18GiB, không đổi cohort/feature/target/split/OLS/KMeans/G4/float64 hoặc haiGPU. Không thêm thư viện.

- S02 lưu chỉ mục source_file/source_row của các dòng được giữ; dữ liệu typed/raw/lineage vẫn ở S01. Khi đọc, JOIN tái dựng cleaned đầy đủ, cùng row_id/mode/split.
- S03 base là công thức đọc lại từ cleaned/metadata; S04 chỉ lưu timing states và ghép khi đọc. cleaned/base/player_match/kill_discrepancy có descriptor .dataset.json, không tạo lại các bản Parquet rộng trùng nhau. Dùng ctx.view để đọc bảng logic, không pd.read_parquet vào descriptor.
- S08 dùng một pool khóa/actual cho mỗi cohort/split/target và chỉ lưu position/predicted cho mỗi thí nghiệm. T0/P2 dùng chung pool khi cohort khớp chính xác. Residual và các nhãn hằng tái dựng không mất độ chính xác; S09/release/handoff kiểm đủ dependency. Cần mang cả thư mục cohorts khi bàn giao, không chỉ một file prediction.
- Đổi layout/code làm checkpoint cũ không tự tương thích. Chỉ có import S01 riêng từ đúng producer5.10/source71de đã audit, không sửa manifest hoặc nhận nhầm S02 là completed. S02-S10 phải chạy lại theo layout mới; S01 chỉ reuse sau kiểm nguồn/phần mềm/ASTparser-writer/checksum/giải mã Parquet và ghi producer_import minh bạch.

### Giữ S01 hiện tại và dọn bản S02 dở trên Kaggle

Không tắt toàn bộ session đang giữ working5.10. Cập nhật CẢ Dataset code và notebook5.11; nếu src cũ còn trong RAM cần restart kernel Python, không thao tác xóa/reset working. Gắn đúng nguồnVersion3 và giữ các phiên bản thư viện đã tạo S01. Import sẽ quét checksum/Parquet, có thể mất thời gian nhưng không ingest CSV lại.

1. Trong cell parameters mới, giữ rootv511 và đặt:

```python
S01_IMPORT_ROOT = "/kaggle/working/PUBG_Coursework_v510"
CLEANUP_IMPORTED_510 = False
```

2. Chạy cell parameters và bootstrap S00, đợi import/preflight đạt. Chỉ hỗ trợ working cùng filesystem có hardlink; không tự copy7GiB nếu hardlink thất bại. S01 cũ phải completed, đúng source/version/license/software, không writer lock; targetv511 phải mới/trống hoặc là lần import tương thích của chính producer này. S01 ở rootv511 được kiểm thật rồi mới có checkpoint imported, không đánh completed bằng tay.
3. Khi đã kiểm import đạt, nếu đồng ý dọn bản cleaned S02 chưa commit và bỏ các tên hardlink S01 tại rootcũ, đặt CLEANUP_IMPORTED_510=True rồi chạy lại parameters/bootstrap. Hàm chỉ xóa đúng data/full/cleaned.parquet của S02failed/resource_limited và hai tên aggregate/event cũ sau kiểm chúng cùng inode với bản giữ ở rootv511; chặn khi có lock/downstreamcompleted hoặc đường dẫn không an toàn. Không xóa raw Input. S01 vẫn nguyên bytes ở rootv511; rootcũ được nghỉ dùng, không resume ở đó nữa. Cleaned dở không có bản trash, chỉ có thể tính lại S02 từ S01 đã giữ.
4. Đặt lại S01_IMPORT_ROOT="" và CLEANUP_IMPORTED_510=False, giữ rootv511 rồi chạy S00/Run All. S01 được kiểm và reuse, S02 trở đi tính theo layout mới. Nếu đã mất working/S01, không có cách khôi phục từ các ảnh; dùng cấu hình mặc định mới để ingest lại sau khi đã bảo đảm dung lượng.

Không chỉ tăng18lên19GiB hoặc xóa file lớn tùy ý. Hardlink là hai tên của cùng dữ liệu, không phải bản backup độc lập; không sửa file Parquet in-place. Giữ guard RAM/VRAM/đĩa/output: layout mới chưa bảo đảm toàn nguồn PUBG hoặc một fullfit sẽ vừa tài nguyên. Kết quả kiểm/đo và giới hạn tại kế hoạchXII.17/haiCHANGELOG.

Kiểm cuối5.11: 100/100 tests đạt, chia bốn tiến trình độc lập (30/20/21/29), gồm notebook tự động/thủ công, restore/report_only, đối chiếu layout và import S01. Benchmark cùng nguồn giả lập120000dòng giảm tổng project từ99406055 xuống25616163bytes (khoảng74.2%); chỉ ETL S01-S04 và đóng gói dự đoán hằng, không fit mô hình hay chạy toàn PUBG. Không suy tỷ lệ này thành bảo đảm cho nguồn thật. Evidence bền: artifacts/pubg_storage_acceptance_20261020.json ở workspace, không đưa tests/artifacts vào gói upload.

## Lịch sử5.10: chạy tự động trên hai GPU

Bản5.10 triển khai D5: metrics S08/S09 và so sánh T0/T1 xử lý trên database đĩa, không tải toàn prediction frame. Giữ công thức/trọng số toàn tập, kiểm đủ khóa trước ghép, cùng seed/multiplicity bootstrap và đúng mẫu vẽ cũ. S10 copy vào staging, đọc lại đạt mới công bố snapshot/pointer; report_only chỉ đọc bảng preview có giới hạn. Không thêm dependency/framework hoặc đổi KMeans/OLS/cohort theo skill Ponytail.

Mỗi database đĩa có thư mục spill riêng. Probe bổ sung phát hiện cách dùng chung temp_directory giữa hai kết nối có thể làm lỗi native khi xử lý lớn dù fixture nhỏ đạt; bản5.10 đã tách và có kiểm đọc đủIDs sau khi kết nối lồng đóng. Không tăng RAM/SQLlimit hoặc đổi dữ liệu để xử lý lỗi này.

Cập nhật đồng thời Dataset code và notebook5.10, dùng root mới /kaggle/working/PUBG_Coursework_v510. Không xóa kết quả cũ/hotpatch/sửa checksum để reuseS01 xuyênbản; chưa có migration5.9. Giữ SourceVersion3, assumed_seconds, SQL2GB/threads2, output18GiB và haiGPU độc lập. D6/actualCUDA/fullsource chưa nghiệmthu, không bảo đảm mộtRunAll đã chắcchắn hoànthành.

Giới hạn còn lại: fullprofile/fullfit S07/S08 vẫn cần RAM/VRAM; SQL cần đĩa spill. Bootstrap giữ vectors numeric theo match và mẫu vẽ giữ workspace chỉ số O(N), cả hai có guard, không âm thầm đổi RNG/sample. Lỗi pointer sau rename có thể để một snapshot đầy đủ chưa được trỏ tới, không completed hoặc tự bị xóa. Kết quả tests/benchmark/hash cuối ghi tại kế hoạchXII.15 và haiCHANGELOG.

Kiểm cuối5.10: 88/88 tests đạt trong757.911giây, exit0, trên source sau sửa spill. Bao gồm notebook auto/manual/reuse/restore/report_only, đối chiếu kết quả, lỗi copy/readback/pointer và probe hai database cùng spill. Có log ZMQError:not a socket từ Jupyter local nhưng assertions và suite vẫn đạt; chưa sửa hoặc xác định nguyên nhân môi trường. Benchmark helper1.2triệu dòng giả lập quan sát RSS giảm khoảng62%, đổi lại thêm đĩa/I/O; không đại diện toàn S09, toàn PUBG hoặc CUDA. HaiGPU vẫn mới kiểm bằng mô phỏng CPU.

### D6: nghiệm thu local và bước chạy thật

D6 bổ sung kiểm thử xuyên suốt, không sửa src/config/cell code. Giữ bản5.10 và rootv510; không bắt chạy lại S01 chỉ vì bổ sung tests/tài liệu. Gói ZIP chỉ cập nhật tài liệu; notebook và sourcechecksum không đổi. Nếu đã có đúng bản5.10 thì không cần thay code nóng trong phiên đang chạy.

Kiểm riêng D6 dùng nguồn giả lập, đủ Solo/Duo/Squad, tên Unicode, duplicate/conflict xuyên shard, target lỗi và SQL128MiB. Chuỗi S01-S10 được đối chiếu với các helper tham chiếu đóng băng qua các bản5.6-5.9, không gọi là baseline5.5 nguyên gói. Đối chiếu dữ liệu/bảng/dự đoán bỏ riêng run_id và thứ tự file vật lý, giữ khóa/cohort/NULL/số dòng; số thực dùng rtol1e-9/atol1e-10 đặt trước. Davies-Bouldin kiểm oracle Decimal60 vì bản cũ có cancellation. Có thử os._exit giữa hai partition S04, chặn bàn giao/retry khi còn khóa, rồi takeover sau khi tiến trình sở hữu đã thoát; phải chạy lại cả S04, chưa resume từng partition hoặc tự dọn scratch của tiến trình chết.

Phần chưa nghiệm thu là haiT4/CUDA thật, nguồn PUBG thật tăng quy mô và Run All toàn nguồn. Máy local chỉ có một RTX3050 Laptop4GiB, không thể thay bằng chứng này cho haiT4. Kiểm thử nguồn nhỏ/vừa sau này phải chọn trọn trận cùng roster/events, ghi scope kiểm vận hành riêng; không dùng làm kết quả nghiên cứu full hoặc tune theo test outcomes.

Các bước trên Kaggle cho nguồn thật đã chọn:

1. Nếu dùng bản trước5.10, bảo vệ output trước khi cập nhật đồng thời Dataset code và notebook5.10. Không xóa kết quả cũ hoặc sửa manifest để reuse khác phiên bản. Nếu đã đúng5.10, giữ nguyên sourcechecksum và working tương thích.
2. Chọn T4 x2, gắn đúng Dataset code và nguồn Version3; chạy S00. Giữ RUN_GPU_SMOKE=True, rq2/rq3 device=cuda và gpu_ids=[0,1]. Chỉ tiếp tục khi dependency/source/unit/preflight và smoke thực đều đạt; không tắt guard để vượt lỗi. Smoke48dòng/GPU chỉ kiểm backend/fit/reload, không chứng minh dữ liệu lớn vừa bộ nhớ.
3. Giữ EXECUTION_MODE=full, ALLOW_DATA_PROCESSING=True, ALLOW_FULL_DATA=True, START_STAGE=S01 và END_STAGE=S10 như cell parameters; Run All trên cùng notebook. Không sửa config/cell code giữa lúc đang chạy. Checkpoint completed tương thích tự được kiểm và reuse; không cần Save Version giữa các stage để chuyển bước.
4. Nếu bị cổng RAM/VRAM/disk chặn, giữ nguyên lỗi và checkpoint tốt. Gửi tên stage, bảng resource_plan, progress và traceback; không đổi solver, giảm dòng hoặc gán completed. Nếu tiến trình đã chết còn khóa, chỉ takeover sau khi xác nhận nó thực sự đã dừng; S04 vẫn chạy lại toàn bước. Không bật takeover mặc định.
5. Sau S10 đạt, lưu Version kèm output. Gắn lại đúng output/version rồi kiểm handoff/checksum/read-back và mở report_only từ manifest cụ thể theo mục bàn giao bên dưới. Runtime checkpoint hoặc local read-back không phải bằng chứng Kaggle đã lưu. Giữ log/metadata GPU, nguồn, cohort và artifact để nghiệm thu Q6; không gửi token hoặc credentials.

Chi tiết kết quả D6 và phần còn mở ghi tại kế hoạchXII.16 và hai CHANGELOG. Không hứa mọi full KMeans/OLS vừa RAM/VRAM hoặc Run All nguồn thật chắc chắn hoàn thành.

Kết quả cuối D6 local ngày19/10:92/92 tests đạt865.757giây, exit0; riêng4tests D6 đạt118.326giây ở lượt tập trung. Có log ZMQError:not a socket từ Jupyter local nhưng assertions và suite đạt, chưa chẩn đoán nguyên nhân môi trường. Log tổng tại artifacts/pubg_d6_regression_final_20261019.log ở workspace cha. Không sửa src/config/cell code hoặc thêm thư viện; phần GPU thật/Q6 chưa được đóng bằng kết quả này.

### Lịch sử tối ưu bản5.9

Bản5.9 tiếp tục D4: S07 giảm giữ nhãn/ma trận phụ, reload theo lô và đọc metadata từng mode từ đĩa; S08 tách ma trận số float64 dạng memorymap khỏi khóa chuỗi, tái dùng theo task/split và ghi dự đoán từng lô50000. Worker chỉ nhận/trả đường dẫn, không truyền DataFrame đầy đủ. Giữ bảyfit, KMeans/OLS SVD, G4 trước test, train-only preprocessing và toàn dữ liệu hợp lệ. Không thêm dependency/framework theo skill Ponytail.

Davies-Bouldin được sửa độ ổn định số học bằng khoảng cách trực tiếp hiệu tọa độ, có kiểm Decimal60chữ số; không đổi định nghĩa hoặc nới tolerance. Silhouette vẫn quyết định K. Giá trị DB báo cáo có thể khác kernel cũ bị cancellation, không gọi đây là thay thuật toán phân cụm.

Cập nhật CẢ notebook và Dataset code5.9; working mới /kaggle/working/PUBG_Coursework_v59. Không hotpatch/xóa kết quả phiên cũ hoặc sửa manifest để reuseS01 xuyênbản. Cổng RAM/VRAM vẫn có thể chặn: memorymap không làm một fit thành ngoài RAM; collect profile S07 và metrics S08/S09 vẫn cần tài nguyên, D5-D6 chưa hoàn tất. Chưa kiểm Run All nguồn thật/haiT4; không thể bảo đảm chỉ upload là hết OOM. Kết quả kiểm và giới hạn tại kế hoạchXII.14/haiCHANGELOG.

Kiểm cuối5.9:74/74tests đạt620.339giây, exit0; támtests D4 mới, actual notebook auto/manual/reuse/restore/report_only và GPU CPU-simulation. Đối chiếu bảng kết quả,14predictionframes và missing-indicator/scaler đạt ngưỡng đặt trước. Benchmark riêng600000dòng giả lập/tên dài/một meanbaseline ở SQL512MiB: observedRSS giảm khoảng70%, dự đoán/metrics exact; không đại diện OLS/fullsource hoặc haiGPU thật. Notebook48cells/16code/0outputs, codeZIP cùng sourcehash. D5 metrics ngoàiRAM và D6 nghiệmthu nguồnthật còn mở.

### Lịch sử tối ưu bản5.8

Bản5.8 bổ sung D3/OOC-05/OOC-06. S05 gom count/mean/std/min/max/skew/zero vào một lượt quét; trung vị và q25/q75 dùng sắp xếp toàn cột trên database đĩa rồi nội suy Type-7 đúng các đầu mút, không xấp xỉ hoặc lấy trung bình theo lô. Histogram dùng lại min/max. S06 lưu cặp hữu hạn riêng cho mỗi feature-target-mode, đếm ties và cộng dồn toàn cục để lấy average ranks; JOIN từng hạng riêng rồi tính Pearson/Spearman với kiểm bảo toàn N. Không chia Spearman theo partition hoặc dùng rank trên cohort khác. Có tiến độ từng cột/cặp và s05_execution.json/s06_execution.json.

Chỉ đổi tổ chức thực thi, không thêm framework, lấy mẫu, lọc dòng mới hoặc đổi feature/target/split/estimator. Giữ nguồn Version3, assumed_seconds, DuckDB2GB/threads2, outputbudget18GiB và haiGPU độc lập S07/S08. Database đĩa vẫn cần RAM/đĩa tạm; có thể tăng I/O, không hứa nhanh hơn hoặc hoàn thành nguồn thật. Sai khác Davies-Bouldin đã ghi ở5.7 vẫn mở choD4, không nới tolerance để gọi đã đạt.

Cập nhật đồng thời notebook và Dataset code5.8, dùng working /kaggle/working/PUBG_Coursework_v58. Bảo vệ output phiên cũ trước khi chuyển; không hotpatch hoặc sửa manifest/checksum. Chữ ký vẫn băm mọi src/runtime, chưa có migration5.7/S01 nên không hứa dùng lại checkpoint qua bản. Kết quả kiểm D3 và giới hạn ghi tại mục13 của kế hoạch và hai CHANGELOG; chưa phải bảo đảm Run All toàn nguồn/GPU thật.

Kiểm cuối5.8:66/66 tests đạt555.515giây, gồm7tests D3 mới, actual notebook auto/manual/reuse/restore/report_only, resource/failure/sourcebinding và GPU mô phỏng CPU. Có log ZMQError: not a socket từ Jupyter local ở các kiểm thử notebook, các assertions vẫn đạt và suite exit0; chưa chẩn đoán nguyên nhân môi trường, không thay dependencies để che log. Stress helpers1.2triệu dòng ởSQL64MiB cũng đạt cả bản cũ/mới, không là chứng minh nguồn PUBG hoặc tăng tốc: bản mới chậm hơn trong phép đo và có thể dùng thêm đĩa tạm.

### Lịch sử tối ưu bản5.7

Bản5.7 bổ sung D2: S03 JOIN metadata hẹp, kiểm khóa/số dòng và tổng hợp validation trong một lượt scan trên database đĩa. S04 phân vùng events/metadata/base một lượt theo SHA256(match_id), tính timing và JOIN từng phần trên đĩa, kiểm đầy đủ rồi ghép canonical player_match.parquet. Mặc định16phần, giới hạn16file writer mở, row group phân vùng8192; không chia một trận sang nhiều phần. Dedup dùng toàn khóa/raw, không dùng hash thay identity. Giữ SQL2GB/threads2, toàn dữ liệu, công thức/missing/split/cohort/estimators và haiGPU S07/S08. S02 giữ tối ưu5.6. Chưa triển khai D3-D6.

S04 có timing_partition_audit.csv (events/unique/eligible/rows trước-sau từng phần) và s04_execution.json (layout/bytes trước dọn). Bytes không phải peak đĩa/RSS. Thư mục tạm thuộc lượt chạy nằm ngoài working và được dọn khi thành công/lỗi; chưa có checkpoint từng phần hoặc tự tách phần lệch, một phần/trận quá lớn vẫn có thể OOM. TăngI/O và dùng thêm đĩa là đánh đổi, không hứa nhanh hơn. Nếu đổi S04_OPTIONS.partitions sau S03, chữ ký hiện tại làm S03 stale: chạy lại S03 rồi S04, không sửa manifest để ép reuse.

Kiểm bản5.7:59/59 tests đạt450.453giây, gồm chạy notebook auto/manual/reuse/restore/report-only và6tests D2 mới. S04 synthetic600000events đạtSQL128MiB. Đối chiếu mở rộng hai nhánh oracle5.6/mới: giá trị player_match exact,10bảng phân tích và14bảng dự đoán đạt ngưỡng đặt trước; labels cụm và K chọn từ silhouette giống nhau trên fixture. Riêng Davies-Bouldin ở Solo/K3 lệch2.347921745915471e-9, vượt rtol1e-9/atol1e-10 đã đặt. Không nới ngưỡng để cho qua: OOC-Q3 phần số học downstream còn mở cho D4. Đây không phải nghiệm thu toàn nguồn hoặc CUDA thật. Notebook vẫn48cell/16code/0outputs.

Lịch sử5.6:53/53tests CPU/simulation đạt201.885giây, gồm4tests S02 mới, actual notebook auto/manual/reuse/restore/report-only. Benchmark riêng metadata synthetic1.2triệudòng/120000trận: querycũOOM ở64 và128MiB, querymới đạt cảhai mức. Không gọi memory_limit là peakRSS, không dùng querythấtbại để tínhspeedup và chưa kiểm nguồnPUBG/fullS02 thật.

Lịch sử chuyển bản5.7 dùng working /kaggle/working/PUBG_Coursework_v57, không hotpatch phiên đang giữ S01 chưa bảo vệ. Quy tắc bảo toàn file/manifest và chỉ reuse checkpoint tương thích vẫn áp dụng ở5.8. Nếu chưa có output đã lưu và đọc lại, cần coi S01 hiện tại chỉ là bản runtime.

Requirements giữ nbconvert>=7.16.6,<8 để tránh xung đột nbclient/nbconvert cũ đã thấy trên Kaggle. Cài trong phiên cần chạy, xác nhận phiên bản thực rồi chạy S00; thao tác tạo lại toàn session có thể trả về môi trường gốc. Không nâng/downgrade các package khác để xử lý cảnh báo google-colab không thuộc pipeline. Các mục5.9/5.8/5.7/5.5/5.4 giữ lịch sử; bản upload hiện hành và khối tham số bên dưới là5.10.

Lịch sử kiểm bản5.5 ngày19/10/2026:49/49tests đạt395.243giây, gồm actual notebook auto S01-S10/reuse/restore/report_only, kiểm checksum/dependencies/cache và tài nguyên, GPU subprocess mô phỏng trênCPU. Đây không phải kết quả kiểm5.8 hoặc CUDA đôi/Kaggle. Quy tắc notebook và codeZIP cùng phiên bản/checksum vẫn áp dụng cho bản hiện hành.

Bản5.5 đồng bộ notebook/code trước import: sai phiên bản, module cũ trong kernel hoặc dependencies ngoài requirements sẽ chặn ở S00 với hướng dẫn. Cần cập nhật cả Dataset code và notebook, restart kernel rồi Run All. Working mới mặc định `/kaggle/working/PUBG_Coursework_v55`; không xóa hoặc ghi đè kết quả phiên cũ. Nếu thư mục này đã có code khác thì vẫn chặn, không tạo root mới vô hạn.

Ngân sách ma trận hiện dùng `runtime.memory_policy: auto`, tối đa60% RAM đang còn trống, tính lại trước collect và mỗi lượt worker; không tự tăng tổng RAM máy hoặc gộp VRAM. `max_matrix_gb: 2` chỉ áp dụng khi chọn `memory_policy: fixed`. Sau S04, trước S05, notebook dự toán số dòng/hồ sơ S07/S08 và dừng sớm nếu vượt ngân sách. Dự toán là điều kiện cần, không đủ: chưa mô phỏng đỉnh RAM/VRAM thật, thời hạn phiên hoặc dung lượng toàn output. S10 kiểm dung lượng bản sao release trước ghi. Giữ18GiB output budget, không xóa artifact, không sample/đổi thuật toán hoặc tự giảm số GPU.

Giảm RAM bằng hash bảng theo batch giữ nguyên digest, kiểm reload dự đoán theo batch, đối soát T0/P2 chỉ đọc row IDs, không giữ đồng thời bảng profile development/full. Đây là tối ưu vận hành; một OLS/KMeans vẫn phải vừa một GPU. Nếu full eligible data không vừa máy, cần môi trường nhiều RAM/VRAM hơn hoặc quyết định nghiên cứu riêng; bản này không hứa hoàn tất toàn nguồn Kaggle chỉ từ fixture.

Bản5.4 được yêu cầu ngày18/10: rq2.gpu_ids và rq3.gpu_ids=[0,1], chọn accelerator T4 x2. S07 chạy các K ứng viên song song, sau khóa K mới fit đầy đủ từng mode; S08 chạy ba hồi quy S1/P2/T0 độc lập trên hai GPU. Một fit vẫn dùng một GPU, giữ OLS SVD/KMeans/n_init10/seed/cohort và full eligible data, không cộng VRAM hoặc đổi sang Dask/SGD/MiniBatch. Các baseline/SQL/EDA/metrics vẫn CPU. Một batch có tối đa hai worker, mỗi GPU một worker, tiến trình chính là bên duy nhất publish artifact/checkpoint. S00 kiểm đủ hai GPU; RUN_GPU_SMOKE=True kiểm48dòng synthetic/GPU với KMeans/OLS/reload trước ingest. Thiếu GPU, worker lỗi hoặc tổng RAM budget không đủ thì dừng, không lùi ngầm một GPU/CPU. Chưa kiểm CUDA đôi/Kaggle/dữ liệu lớn trong môi trường local.

GPU được cô lập bằng CUDA_VISIBLE_DEVICES trước khởi tạo CUDA, kể cả khi notebook đã import cuML. Cách chọn thiết bị này theo [tài liệu cuML](https://docs.nvidia.com/cuml/26.08/advanced/#selecting-the-cuda-device). Metadata lưu gpu_id theo inventory của tiến trình cha, token visibility, PID/start/finish/compute của worker; không gọi mock hoặc sốGPU nhìn thấy là bằng chứng đã fit trên cả hai. Worker ghi tạm ngoài working; model/predictions chỉ publish sau kiểm reload/finite/cohort, test chỉ sau G4. Không hứa tăng tốc gấp đôi; CPU/I/O và giới hạn một fit vẫn có thể là nút thắt. Src/config5.4 làm checkpoint5.3 stale; không sửa chữ ký hoặc ghi đè nóng phiên cũ.

Lịch sử kiểm local5.4:44/44tests đạt339.789giây, gồm subprocess visibility/PID/overlap bằng CUDA giả trên CPU, haiGPU routing/G4/cache, đối chiếu7predictionframes với serialCPU, actual notebook auto/manual/restore/report_only. Máy local chỉ có một RTX3050 và chưa có CuPy/cuML; đây không là nghiệm thu CUDA hoặc T4x2. Nhật ký ghi cả log ZMQ từ môi trường notebook local; không thay dependencies để che log. Khi chuyển sang bản hiện hành5.10, cập nhật CẢ Dataset code và notebook5.10, chọn T4x2 rồi kiểm S00 smoke status=passed với gpu_ids=[0,1].

Bản hiện tại có đúng một notebook 48 cell, 16 cell code. Auto là mặc định trong config; không còn yêu cầu dừng để chọn ngưỡng/K/G4 nếu đã cung cấp facts nguồn và đủ tài nguyên. Không cần Save Version sau mỗi cell. Hướng dẫn 5.1 và số liệu kiểm thử phía dưới là lịch sử, không phải kết quả auto mới.

1. Cập nhật Dataset code từ kaggle_code.zip mới và import notebooks/PUBG_COURSEWORK.ipynb. Import notebook riêng không cập nhật src. Không thay code trong working đang có kết quả chưa lưu; bản mới sẽ chặn khác code thay vì ghi đè.
2. Notebook upload ngày18/10 đã điền S00 cho hai Input đã chọn: EXECUTION_MODE='full', ALLOW_DATA_PROCESSING=True, ALLOW_FULL_DATA=True, START_STAGE='S01', END_STAGE='S10', nguồn PUBG Version3. Không cần dán lại cấu hình. Kiểm CODE_INPUT/SOURCE_DIRECTORY đúng mount thực và pin Version3; PUBG_PROJECT_ROOT phải là working root đúng marker, không dùng output fixture. Cell gán trực tiếp nên chạy lại sẽ dùng đúng giá trị hiển thị, không giữ False/pending cũ trong RAM.
3. Config5.3 đã ghi mapping mode có đối chiếu mẫu và assumed_seconds do người dùng duyệt ngày18/10/2026, chỉ cho nguồn PUBG Version3. Không phải đơn vị đã verified. Giữ các SOURCE_* evidence trống để kế thừa config mới; nếu còn SOURCE_TIME_UNIT_STATUS="pending" từ khối cũ thì sửa rõ thành "assumed_seconds" và chạy lại cell parameters. Thiếu evidence/approval hoặc source/version khác scope thì preflight vẫn chặn. SOURCE_LICENSE được hỗ trợ chính thức, không sửa bootstrap để vượt kiểm tra.
4. Mỗi cell S01-S10 có Sxx_OPTIONS. None là kế thừa cấu hình hiện tại, không tự đặt null. S02/S05/S07/S08 hỗ trợ decision_mode='auto' hoặc 'manual'. Muốn đổi thông số thì sửa trước lúc chạy mục đó; Run All lần đầu đọc lựa chọn khi đi tới cell. Không sửa trong lúc cell đang chạy.
5. Bấm Run All để chạy tương tác, hoặc Save & Run All để chạy một lượt độc lập rồi lưu; chỉ chọn một, tránh xử lý hai lần. Chạy tương tác xong cần Quick Save kèm output hoặc bản sao riêng nếu muốn dùng lại sau khi phiên kết thúc. Mọi lưu dịch vụ đều phải kiểm Output/read-back; lỗi HTML/JSON của Kaggle không phải lỗi mô hình.

Ví dụ thay cell S07 (không thêm cell mới):

```python
S07_OPTIONS = {
    "minimum_games": 10,
    "candidate_k": [2, 3, 4, 5, 6, 7, 8],
    "clusters": {"Solo": None, "Duo": None, "Squad": None},
}
run_section("S07", S07_OPTIONS)
```

None trong clusters là tự chọn khi decision_mode auto; số nguyên là ghi đè cho mode đó, phải có trong diagnostics. Auto chọn silhouette development cao nhất, hòa chọn K nhỏ hơn; vẫn hiển thị ARI và kích thước cụm để nhận diện kết quả yếu. Ngưỡng10 là quy ước đã duyệt, không phải tối ưu. Chọn ngưỡng loại hết một mode hoặc không có silhouette hợp lệ phải lỗi, không tự cứu bằng bỏ mode/lấy mẫu.

S02: không có evidence chronology đáng tin sẽ dùng Grade C chia ngẫu nhiên theo trận, không tuyên bố dự báo tương lai. Nếu có chronology_evidence và dữ liệu nhất quán, tự chọn A/B và giữ nguyên block thời gian/ngày. S05: no-log mặc định; muốn log thì thêm log_columns và transform_reason. S08: tự duyệt bảy fit đã đăng ký sau validation, không cần chọn winner hoặc đặt approval/hash bằng tay trong auto; test không dùng chọn tham số.

HANDOFF_EVERY_STAGE=False mặc định: checkpoint runtime vẫn sau mỗi stage, handoff đầy đủ chỉ cuối END_STAGE. Muốn bàn giao giữa chừng, khi không có cell chạy gọi prepare_handoff(ctx) ở cell bàn giao sẵn có; không đổi status bằng tay. Đây không phải tự lưu output trên Kaggle.

Giới hạn: ngân sách RAM tự tính từ phần còn trống theo5.5; output_budget18GiB là ngân sách nhóm. Đủ S01 không chứng minh S07/S08 đủ RAM/VRAM/đĩa. Không lấy mẫu, đổi OLS/KMeans hoặc xóa prerequisites để ép hoàn thành. Khi cấu hình upstream đổi, downstream stale sẽ bị chặn; không resplit để che test đã xem. Các số kiểm5.4 dưới/trên là lịch sử, không phải nghiệm thu5.5.

Kiểm thử bản auto5.2:37/37tests CPU local đạt165.956giây, gồm actual Run All S01-S10, reuse, report_only không ghi, manual gates và restore. Notebook mới sạch output cũ, không nhúng số liệu synthetic để giả kết quả mới. Chưa kiểm GPU/Kaggle/full-data5.2; không bảo đảm vượt được giới hạn RAM2GiB hiện tại.

### Đơn vị giây là giả định, không phải xác minh tác giả nguồn

Bản5.3 được người dùng duyệt ngày18/10/2026. Audit trực tiếp Data_PUBG.zip:2000record đầu mỗi10CSV,20000record tổng;8096cặp victim-survival ghép được,8038chênh<=1đơn vị, median0.296,58lệch lớn. Kiểm này hỗ trợ cùng thang đo nhưng KHÔNG chứng minh tuyệt đối giây. Không có README/dictionary trong ZIP, không được gọi đây là audit toàn nguồn.

Trạng thái mới: timing.unit_status=assumed_seconds, unit_assumption_approved=True, scope skihikingkevin/pubg-match-deaths/versions/3, evidence và giới hạn lưu trong config. verified=False được đưa vào metadata, S00/S04, hình/bảng/mô hình/release và báo cáo chỉ đọc. Không đổi raw/time/target, không loại58cặp lệch, không tự nhân/chia60/1000. Nếu giả định đơn vị sai, cách diễn giải MAE/RMSE tuyệt đối và ngưỡng60 phải được xem lại.

Sau cập nhật Dataset code và notebook mới, các dòng S00 cần rõ ràng (không chỉ sửa default của globals().get vì có thể giữ pending cũ):

```python
SOURCE_VERSION = 3
SOURCE_MODE_EVIDENCE = ""  # Kế thừa bằng chứng mẫu trong config5.3 mới.
SOURCE_TIME_UNIT_STATUS = "assumed_seconds"
SOURCE_TIME_UNIT_EVIDENCE = ""  # Kế thừa lý do/giới hạn đã ghi, không bịa evidence.
SOURCE_TIME_UNIT_ASSUMPTION_APPROVED = True
SOURCE_TIME_UNIT_ASSUMPTION_SCOPE = "skihikingkevin/pubg-match-deaths/versions/3"
```

Chạy lại cell parameters rồi bootstrap. Chỉ sửa các dòng này trên Dataset code cũ5.2 vẫn chưa đủ vì code cũ chưa biết assumed_seconds. Phải cập nhật cả kaggle_code.zip và notebook. Không xóa root/kết quả đang sống hoặc sửa manifest để ép tương thích; prepare_project chặn code khác là có chủ đích. Giữ Source Input Version3, không dùng latest.

### Khối S00 đầy đủ cho nguồn PUBG Version 3 đã chọn

Dùng sau khi cập nhật CẢ Dataset code và notebook5.11. Bản upload đã có sẵn chính khối này ở cell parameters đầu S00; hai trường import/cleanup tắt mặc định. Đây là nguồn và quyền chạy full người dùng đã chọn, không áp dụng ngầm cho nguồn khác. S00 đối chiếu thư viện với requirements; nếu thiếu cần cài và xác nhận phiên bản thực trong phiên sẽ chạy. Không dùng thao tác tạo lại toàn session như cách giữ packages vừa cài hoặc giữ S01.

```python
PUBG_STORAGE_MODE = "local"
PUBG_PROJECT_ROOT = "/kaggle/working/PUBG_Coursework_v511"
PUBG_REQUIRE_EXISTING_PROJECT = True
PUBG_BATCH_ROWS = 50000
EXECUTION_MODE = "full"
CODE_INPUT = "/kaggle/input/datasets/quangthinng/pubg-coursework-code"
SOURCE_DIRECTORY = "/kaggle/input/datasets/skihikingkevin/pubg-match-deaths"
SOURCE_VERSION = 3
SOURCE_LICENSE = "CC0: Public Domain"
ALLOW_DATA_PROCESSING = True
ALLOW_FULL_DATA = True
START_STAGE = "S01"
END_STAGE = "S10"
RESUME_INPUT = ""
RESUME_VERSION = ""
S01_IMPORT_ROOT = ""  # Chỉ nhập S01 đã kiểm từ working5.10, không phải RESUME_INPUT.
CLEANUP_IMPORTED_510 = False  # Chỉ True khi đồng ý bỏ cleaned S02 dở và các tên liên kết S01 cũ.
RELEASE_MANIFEST = ""
SAVED_OUTPUT_ROOT = ""
SAVED_VERSION = ""
RUN_GPU_SMOKE = True
INSTALL_DEPENDENCIES = False
PUBG_WRITER_ID = ""
PUBG_FORCE_STAGE_TAKEOVER = False
HANDOFF_EVERY_STAGE = False
SOURCE_MODE_EVIDENCE = ""  # Kế thừa audit mẫu trong config5.3.
SOURCE_TIME_UNIT_STATUS = "assumed_seconds"
SOURCE_TIME_UNIT_EVIDENCE = ""  # Kế thừa evidence/giới hạn trong config5.3.
SOURCE_TIME_UNIT_ASSUMPTION_APPROVED = True
SOURCE_TIME_UNIT_ASSUMPTION_SCOPE = "skihikingkevin/pubg-match-deaths/versions/3"
```

S00 hiện status=assumed_seconds, accepted=True, verified=False là đúng, không phải lỗi. Nếu prepare_project báo working có code khác Input: đừng xóa dữ liệu hoặc sửa khóa/manifest; bảo vệ output phiên cũ trước khi chuyển sang working mới. Bản này không tự migrate checkpoint cũ và chưa chứng minh đủ bộ nhớ toàn nguồn.

## I. Trạng thái và phạm vi

Bản code có S01-S10/report_only và vận hành Kaggle trong cùng notebook 48 cells/S00-S12. Người dùng đã gửi GPU smoke, kết quả pipeline synthetic trên Kaggle và kiểm đọc lại output Version 3: 408 mục, S01-S10 completed. Bản notebook tải về được dọn và giữ báo cáo S11 cùng kết quả đọc lại; đây là bằng chứng do người dùng cung cấp, không xác minh API/quyền nhóm hoặc chạy dữ liệu thật. Config 5.2 dùng quy tắc auto được duyệt cho các lựa chọn nghiên cứu; facts nguồn vẫn phải có evidence, model device mặc định cuda theo lựa chọn nhóm.

Core đã kiểm thử bằng 240 player-match/30 matches/2 modes/4 CSV shards; bản trước có 46 cells/13 sections. Bộ kiểm thử trước chuyển Kaggle chạy 20 ca, gồm kernel mới, stage giữa, G4 và report_only. Đã rà 34 hình có bảng nguồn và từ điển 26 feature/target với công thức/đơn vị/missing/vai trò S1/P2/T0. Không dùng các con số kiểm thử này thay kết quả nghiên cứu.

Sau sửa I/O S01 ngày 16/10/2026: 31/31 tests local đạt trong 280.573 giây; notebook có 48 cells/16 code cells, kiểm actual kernel từ đầu, restore sang working/source mount mới rồi S07-S10, report_only từ saved snapshot không raw/no-write. Đối chiếu 90 bảng/dataset/predictions giữa code trước/sau đạt cùng schema/rows/values trong tolerance1e-10, không tính run_id mới. 69 output báo cáo Kaggle lịch sử giữ nguyên; evidence ghi trong CHANGELOG_FIXES.md và kế hoạch. Bộ test này là CPU local, tách biệt bằng chứng Kaggle do người dùng cung cấp và không chứng nhận dữ liệu thật/quota dịch vụ.

Việc xóa Project_PUBG cũ bị cơ chế công cụ chặn. Bản cũ còn nguyên, không nhập vào bản này. Local folder mới không tự xóa hoặc thay đổi Drive, Git remote hoặc dataset ngoài folder. Không chạy hai bản chung một root/checkpoint.

## II. Cây file và vai trò

```text
configs/project.yaml                  Cấu hình duy nhất
notebooks/PUBG_COURSEWORK.ipynb        S00-S12: toàn quy trình và đọc kết quả
src/io.py                             Stage signatures, writer, publish/read-back
src/preprocessing.py                  CSV streaming, schema, cleaning/roster/split
src/features.py                       Formulas, target validity và Combat Timing
src/analysis.py                       EDA, Pearson/Spearman, KMeans per_mode
src/modeling.py                       Baseline/OLS/G4/predictions/errors/CI
src/reporting.py                      Source plots, locked release, read-only loader
src/kaggle_runtime.py                 Code Input/preflight/smoke/handoff/restore
tests/                                Dữ liệu nhỏ, kiểm logic/tích hợp/notebook
data/<scope>/                         typed/interim/processed Parquet mới
outputs/<scope>/                      tables/figures/models/predictions/manifests/checkpoints
```

`scope` là development hoặc full. Dữ liệu/generated outputs bị Git ignore. Stage IDs là phần notebook, không tên 13 file cũ. Models và predictions lưu riêng để người sau không cần RAM phiên trước.

## III. Chuẩn bị local và nguồn dữ liệu

Python 3.11 trở lên. Kiểm thử đã chạy trên Python 3.13; không suy mọi phiên bản/cuML đều tương thích từ đây. Môi trường tái lập cuối cần snapshot versions sau setup thành công.

```powershell
cd "E:\NAM_BA\KY_1_NAM_BA\KHAI PHÁ DỮ LIỆU\PUBG_Coursework"
python -m pip install -r requirements.txt
```

Mở notebook qua Jupyter hoặc VS Code. S00 chọn local và điền PUBG_PROJECT_ROOT tới folder này. Device CPU phải được chọn rõ trong project.yaml nếu thử logic local; không gọi đó là GPU verification.

Nguồn thực: PUBG Match Deaths and Statistics, Kaggle slug `skihikingkevin/pubg-match-deaths`. Bản mới đọc CSV gắn trực tiếp từ Kaggle Input hoặc nguồn nhỏ local được phép. Không có script tự đăng nhập/tải ZIP hoặc dùng token. Đặt mount folder thật trong source.directory/SOURCE_DIRECTORY, ghi version/license; discovery các patterns aggregate/event. Null source dừng ngay.

```yaml
source:
  directory: /kaggle/input/<mount-folder-thuc>
  aggregate_patterns: ["**/agg_match_stats*.csv"]
  event_patterns: ["**/kill_match_stats*.csv"]
```

Không trỏ vào processed/model/checkpoint cũ. Nếu nhóm chọn tải lại hoặc giữ một nguồn raw ngoài folder cần khai báo rõ nguồn/version/checksum, không giả rằng folder mới đã có dữ liệu. Bản kiểm thử tự tạo raw tổng hợp trong Temp, không dùng dataset thật ngoài dự án.

Aggregate required: match_id/player_name/team_id/date, party_size/game_size, kills/damage/assists/DBNO/walk/ride/survival/placement theo tên schema trong src/preprocessing.py. Event required: match_id/killer_name/victim_name/event_time; alias time -> event_time mặc định. Thiếu required hoặc alias collision dừng, không tự đoán cột.

## IV. Chuẩn bị Kaggle, chưa chạy dữ liệu lớn

Người dùng đã tạo notebook Kaggle, kiểm GPU nhỏ và cung cấp output đọc lại Version 3 thành công; các bước dưới đây hướng dẫn nhóm tự thao tác. Agent chưa upload/đổi tài khoản hoặc xác minh API/quyền cộng tác. Người dùng đã cho phép dữ liệu lớn; không đồng nghĩa mọi stage đã chạy xong hoặc đủ tài nguyên.

### Bản notebook đã dọn sau kiểm Kaggle (lịch sử 5.1)

Bản tải project-pubg-abc.ipynb đã được hợp nhất vào notebooks/PUBG_COURSEWORK.ipynb: bỏ 11 cell hỗ trợ tạm, giữ 48 cell chính, 69 output gồm 34 hình. Các bảng/hình hiện lưu ở S11 là synthetic/development của quangthinng/project-pubg-abc/versions/3, không dùng viết kết quả PUBG thật. S01-S10 trong bản tải cuối không có output riêng; không cần chạy lại chỉ để xem báo cáo đã nhúng.

Lịch sử dọn notebook giữ16cell code và cấu hình nghiên cứu lúc đó. Cập nhật18/10: cell parameters hiện đã gán trực tiếp cấu hình full được người dùng duyệt, ALLOW_DATA_PROCESSING và ALLOW_FULL_DATA=True cho nguồn PUBG Version3, không còn mặc định False. Muốn report_only/fixture hoặc đổi nguồn phải sửa ngay cell này theo đúng mục hướng dẫn, không dựa globals hoặc RAM cũ; restart kernel trước chuyển fixture sang dữ liệu thật.

Để đọc lại đúng báo cáo fixture trong phiên mới, gắn code và output Version 3 làm Input, chuẩn bị sẵn dependencies rồi đặt các biến sau ngay trong cell parameters hiện có. Nếu mount path đổi, dùng đường dẫn thực từ Input; không đoán từ slug:

```python
PUBG_PROJECT_ROOT = "/kaggle/input/notebooks/quangthinng/project-pubg-abc/PUBG_Fixture"
EXECUTION_MODE = "report_only"
CODE_INPUT = ""
RESUME_INPUT = ""
RUN_GPU_SMOKE = False
INSTALL_DEPENDENCIES = False
RELEASE_MANIFEST = PUBG_PROJECT_ROOT + "/outputs/development/manifests/releases/23e06692771840c68def99924dc6dd29/manifest.json"
SAVED_OUTPUT_ROOT = PUBG_PROJECT_ROOT
SAVED_VERSION = "quangthinng/project-pubg-abc/versions/3"
```

Chạy S00 parameters/bootstrap/section-runner, rồi S11/S12 và cell kiểm gói đã lưu; report_only không train hoặc ghi Input. Các giá trị trên chỉ dành cho báo cáo fixture. Khi chạy nguồn thật, khai báo lại root working/nguồn/version và đọc preflight, không dùng release hoặc K/G4 của fixture. Import bản sạch vào cùng notebook Kaggle để thay nội dung; không tạo notebook identity mới.

1. Import notebooks/PUBG_COURSEWORK.ipynb vào một Kaggle Notebook riêng của nhóm; giữ cùng identity, không tạo một notebook cho mỗi stage.
2. Add Input gắn nguồn skihikingkevin/pubg-match-deaths. Chọn/pin version, ghi số version/license; kiểm có cả aggregate và event. Không đoán mount folder từ slug.
3. Đưa gói code nhẹ của bản mới lên một Dataset riêng tư có quyền nhóm rồi Add Input; không đưa thư mục raw/results/secrets/project cũ vào gói. Notebook hiện có báo cáo synthetic nhúng để xem; ZIP giữ nguyên các output này, không phải archive dữ liệu hoặc checkpoint để resume. Có thể tạo ZIP từ local:

   ```powershell
   python -B -c "from src.kaggle_runtime import code_archive; code_archive('.', 'kaggle_code.zip')"
   ```

   Nếu upload ZIP được nền tảng giải nén thành folder, CODE_INPUT trỏ folder có src/ và configs/, không trỏ file ZIP. Helper không tự extract ZIP hoặc tự upload. Gói phải được tạo lại sau sửa code/config/notebook.
4. Trong S00 điền CODE_INPUT, SOURCE_DIRECTORY và SOURCE_VERSION theo Input thực. Marker phải pubg-coursework-2026-v5. Working root mặc định /kaggle/working/PUBG_Coursework; prepare_project chỉ copy code/config, không copy raw. Có kết quả hiện tại thì không tự ghi đè code khác phiên bản.
5. Chuẩn bị accelerator/thư viện khi được phép kiểm Kaggle. Preflight kiểm thiết bị cần cho range đã chọn, package versions/RAM/disk và output budget. RUN_GPU_SMOKE dùng synthetic 48 rows để fit/reload KMeans và OLS thực, không đọc dataset.
6. Chưa bật ALLOW_DATA_PROCESSING hoặc ALLOW_FULL_DATA cho nguồn lớn. development là nhãn output, không phải cơ chế lấy mẫu. Chỉ bật xử lý khi nguồn nhỏ đã được phép; full-data cần quyền riêng, source version/license và quyết định nghiên cứu hợp lệ.

```python
PUBG_STORAGE_MODE = "local"
PUBG_PROJECT_ROOT = "/kaggle/working/PUBG_Coursework"
PUBG_REQUIRE_EXISTING_PROJECT = True
PUBG_BATCH_ROWS = 50000
EXECUTION_MODE = "development"
ALLOW_DATA_PROCESSING = False
ALLOW_FULL_DATA = False
```

Input chỉ đọc; working là vùng ghi trong phiên. Code không mount Drive, đăng nhập/upload/tạo token hoặc tự nhận đã Save Version. INSTALL_DEPENDENCIES mặc định False: kiểm môi trường trước cài, không nâng toàn bộ packages mù vì có thể làm cuML mất tương thích. report_only tuyệt đối không install. Tham khảo [RAPIDS trên Kaggle](https://docs.nvidia.com/datascience/deployment/nightly/platforms/kaggle/).

Nếu bật INSTALL_DEPENDENCIES, cell dừng sau pip để yêu cầu restart kernel; đặt lại False rồi chạy S00. Không tiếp tục với thư viện cũ còn trong RAM nhưng metadata của phiên bản mới.

| Phần | Thiết bị |
| --- | --- |
| S01-S06 | CPU/RAM/disk |
| S07 KMeans | GPU cuML theo rq2.device; CPU chỉ khi chọn rõ cho kiểm local |
| S08 baselines | CPU |
| S08 OLS | GPU cuML theo rq3.device |
| S09-S12 | CPU/đọc artifact |

Bật GPU không tự khiến mọi Python chạy GPU và không tự cộng VRAM nhiều GPU. Thiếu/incompatible GPU dừng trước xử lý dài, không fallback. Ngân sách output mặc định 18 GiB là ngưỡng nhóm tự đặt, không phải quota Kaggle được bảo đảm; cần đối chiếu giới hạn tài khoản thực khi chạy.

### Kiểm Kaggle bằng nguồn tổng hợp nhỏ trước dữ liệu thật

Sau khi GPU smoke đạt và DuckDB/psutil đã đúng requirements, dùng gói kaggle_fixture.zip, không gắn nguồn PUBG thật cho bước này. Gói được tạo từ fixture local đã kiểm: 4 CSV, fixture_config.yaml, fixture_manifest.json và setup_fixture.py. Có 241 dòng aggregate gồm một dòng trùng, 240 player-match sau cleaning, 360 event và 30 match; chỉ hai mode Solo/Duo. Đây là dữ liệu kiểm logic, không mô phỏng hoàn chỉnh luật trận PUBG hoặc bằng chứng nghiên cứu.

Tạo lại gói trên máy khi cần:

```powershell
python -B tests/build_kaggle_fixture.py
```

Upload ZIP thành Dataset riêng tư rồi Add Input trong cùng notebook. Input cần hiện 7 file đã giải nén; nếu chỉ còn ZIP, giải nén trên máy rồi upload các file. Chỉ chạy setup_fixture.py do chính nhóm tạo, không chạy script từ Dataset lạ. Không upload các tests hoặc thay config dữ liệu thật bằng config fixture.

Chỉ khi chủ động kiểm fixture: chạy cell parameters trước, rồi thêm cell chuẩn bị tạm NGAY SAU parameters và TRƯỚC bootstrap, để ghi đè cấu hình production bằng fixture. Không chạy lại parameters production sau setup. Điền số version Dataset fixture thực đã gắn; số1 dưới chỉ đúng với version đầu tiên:

```python
from pathlib import Path

CODE_INPUT = "/kaggle/input/datasets/quangthinng/pubg-coursework-code"
sources = [p.parent for p in Path("/kaggle/input").rglob("fixture_manifest.json")]
assert len(sources) == 1, "Cần đúng một Dataset fixture đã giải nén"
FIXTURE_INPUT = str(sources[0])
SOURCE_VERSION = 1  # Đổi theo version Dataset fixture thực đã gắn.
PUBG_PROJECT_ROOT = "/kaggle/working/PUBG_Fixture"
EXECUTION_MODE = "development"
ALLOW_DATA_PROCESSING = False
ALLOW_FULL_DATA = False
START_STAGE = "S01"
END_STAGE = "S04"
RUN_GPU_SMOKE = False
INSTALL_DEPENDENCIES = False
SOURCE_LICENSE = ""
SOURCE_TIME_UNIT_STATUS = ""
SOURCE_TIME_UNIT_ASSUMPTION_APPROVED = None
SOURCE_TIME_UNIT_ASSUMPTION_SCOPE = ""
exec((Path(FIXTURE_INPUT) / "setup_fixture.py").read_text(encoding="utf-8"))
```

Cell chuẩn bị kiểm manifest/checksum, chỉ copy code và ghi config fixture vào working root mới/trống, không copy raw hoặc tính stage. Chỉ sau xác minh nguồn nhỏ nó mới đặt SOURCE_DIRECTORY và ALLOW_DATA_PROCESSING=True, giữ ALLOW_FULL_DATA=False; CODE_INPUT/RESUME_INPUT được đặt trống để S00 dùng project đã chuẩn bị. Không chạy lại cell này khi working root đã có kết quả; khi kiểm lại S00 thì giữ biến và root hiện có, không ghi đè config/checkpoint. Đây là cell hỗ trợ tạm riêng cho setup fixture; sau kiểm và bàn giao thì bỏ, không đưa vào notebook nghiên cứu. Những lần đổi range chỉ sửa START_STAGE/END_STAGE trong cell parameters có sẵn, không thêm cell mới.

Sau parameters và setup tạm, chạy bootstrap và section-runner ở S00, sau đó cell thực thi S01, S02, S03, S04. Nếu muốn chạy lại S00 trong phiên fixture, phải sửa cell parameters theo đúng cấu hình fixture trước, không để bản full ghi đè setup. Không Run All hoặc chạy S05-S12 trong lượt đầu. Expected: aggregate 241/event 360, loại đúng1dòng trùng, giữ240player-match/30match; split21train/5validation/4testmatch, S04 không tăng số dòng sau join. Bảng/biểu đồ và handoff runtime xuất ở PUBG_Fixture/data/development và outputs/development. Gói vẫn giữ K/receipts/G4 pending; kiểm S07/S08 và saved Version là bước riêng, không tự mở test hoặc dùng quyết định fixture cho nghiên cứu thật.

## V. Thứ tự chạy và chốt quyết định

1. S00: project/source/config/scope/device/path/resource. Runtime mới luôn chạy S00.
2. S01/S02: source/schema/parse, cleaning/roster/chronology/split.
3. S03/S04: target/features/timing, unit evidence, merge và coverage.
4. S05/S06: development EDA/RQ1, transforms không dùng final test.
5. S07: diagnostics minimum-games/K; cập nhật config sau đọc evidence, rồi chạy lại S00/S07.
6. S08: train/validation; cập nhật G4 approval/reason/hash sau kiểm, rồi S00/S08 để predict final test.
7. S09/S10: pairing/comparisons/errors/CI nếu có, khóa release.
8. S11/S12: đọc kết quả/bàn giao/báo cáo.

Không chọn K hoặc approval từ fixture cho full-data. Config nghiên cứu không nằm trong notebook cells rải rác; sửa project.yaml rồi reload S00.

Sửa src hoặc package phải restart kernel trước chạy lại, không chỉ chạy lại lệnh import vì Python có thể giữ module cũ trong RAM. Không sửa code/config khi stage đang có writer hoạt động.

| Cần chốt | Config | Evidence |
| --- | --- | --- |
| Nguồn | source.directory/source metadata | Shards mới và nguồn được phép |
| Mode mapping | preprocessing.mode_evidence | Field/labels nguồn; không >=3 tự thành Squad |
| Chronology | chronology_grade/reason | Semantics/ties/granularity, không từ format timestamp |
| Timing units | timing.unit_status/unit_evidence | Nguồn và event_unit_diagnostics mới |
| Log hoặc giữ nguyên | features.log_columns/transform_reason | EDA train/validation; không xóa cực trị cho metric đẹp |
| Minimum games | rq2.minimum_games | profile_retention.csv và reliability |
| K theo mode | rq2.clusters/decision_reason/diagnostic_hash | k_diagnostics.csv, k_diagnostic_receipt.json; không outcomes |
| G4 | rq3.selection_approved/selection_reason/validation_hash | validation_metrics.csv + validation_receipt.json trước test |
| CI | report.bootstrap_replicates/seed | Đăng ký trước chạy; 0 là not_requested |

Các file evidence ở outputs/<scope>/tables và manifests. Nếu nhận pending, diagnostics đã lưu để đọc nhưng stage chưa completed, consumer phải dừng. Không ép status hoặc biến tiến độ để bỏ lỗi. Khi G4 được chốt, train/validation cache được xác minh bằng source/code/config/cohort/model hash và tái sử dụng, không fit lại chỉ để predict test.

## VI. Lưu và chạy tiếp trong một notebook

### S01 tiết kiệm dung lượng, bản sửa 16/10/2026

S01 giữ đúng aggregate.parquet và event.parquet cho các bước sau. Parquet từng shard chỉ nằm trong thư mục tạm riêng; sau khi bản gộp được giải mã, đối chiếu số dòng và publish/read-back thành công, các shard tạm được dọn. Không còn tạo data/<scope>/typed chứa bản sao đã có trong hai file gộp. Giữ toàn bộ raw columns, source_file/source_row và mọi quy tắc parse/cleaning; không lấy mẫu hoặc bỏ dữ liệu để tiết kiệm đĩa.

Khi xuất Parquet, file staging nằm cùng filesystem với đích để rename thay vì copy thêm một file lớn; checksum/read-back và bản tốt trước đó vẫn được bảo vệ. Các thao tác copy code/Input vẫn không consume nguồn. DuckDB spill và shard ingest tạm ở runtime, không đưa vào bàn giao; chỉ dọn thư mục tạm do chính lượt chạy tạo, không quét/xóa các thư mục cũ không rõ chủ sở hữu.

Bảng outputs/<scope>/tables/ingest_storage.csv có một dòng mỗi nhóm: rows/shards, temporary_bytes_removed, canonical_bytes và temporary_files_remaining. Giá trị cuối phải bằng 0 sau thành công; byte đã dọn không phải số đo đỉnh đĩa, và tỷ lệ tiết kiệm fixture không suy thành toàn bộ dữ liệu thật. Vẫn có thể thiếu RAM/đĩa/output budget ở S01 hoặc các bước sau; dừng khi thiếu tài nguyên, không đổi cohort/estimator.

Sau sửa src, tạo/cập nhật Dataset code bằng kaggle_code.zip mới, chọn version code mới trong Input và restart kernel trước chạy S00. Chỉ import lại notebook không cập nhật src trong Dataset. Notebook vẫn 48 cell; báo cáo synthetic nhúng từ Version 3 là bằng chứng lịch sử, không được coi là output của bản src mới. Không ép reuse checkpoint chữ ký code cũ; không xóa fixture/version kiểm thử trên Kaggle. Người dùng đã cho phép tách một notebook chính thức mới khỏi notebook fixture; giữ notebook chính thức đó xuyên suốt các stage tiếp theo.

Ví dụ người A chạy S01-S04, người B chạy S05-S07, người C chạy S08-S10. Người nhận vẫn chạy S00/bootstrap/init rồi chọn START_STAGE/END_STAGE. Dependency completed compatible mới được chấp nhận; không chỉ có tên Parquet.

Sửa K chỉ stale S07 và consumers. Sửa timing stale S04 trở đi. Sửa source/schema stale toàn nguồn và downstream; code module đổi làm signature stale để tránh reuse phép tính cũ. Thay decision config vẫn cần receipt/checksum đúng.

Đã completed compatible thì load lại, không fit/tính lại. Stage pending có thể chạy lại để đọc diagnostics. Fit model dở không được giả resume chính giữa estimator. Canonical paths ghi đúng tên và publish/read-back; snapshot release có ID là chủ đích tái lập.

PUBG_WRITER_ID có thể tên thành viên, mặc định ID phiên. Khi writer stage còn lock phải kiểm phiên trước đã dừng; chỉ khi chắc chắn mới bật takeover một lần. Không chạy đồng thời hai người vào cùng outputs.

Hết quota/RAM/VRAM/disk: dừng, đọc stage/reason/path; completed checkpoints còn dùng được. Tăng runtime/query-budget trong phạm vi đã chốt hoặc trình phương án khác; không tự đổi estimator/sample. Không dùng việc đổi thành viên/tài khoản để vượt giới hạn dịch vụ.



Sau mỗi stage, notebook hiển thị bảng/hình và tiến độ gần nhất. Mặc định chỉ chuẩn bị handoff_<scope>.json tại END_STAGE; HANDOFF_EVERY_STAGE=True mới quét bàn giao mỗi bước và có thể tốn nhiều I/O. Event progress gần nhất được lưu trong progress_<stage>.csv (tối đa 200), không thay removal ledger/source inventory đầy đủ. Biểu đồ chính xuất sau khi hoàn thành bước; không có fake loss/epoch cho OLS/KMeans.

Lưu bền vững:

1. Kiểm stage status, artifacts và handoff manifest. working hiện tại chưa chứng minh output được lưu.
2. Save Version với tùy chọn lưu file Output. Save & Run All tạo phiên sạch riêng, cần đủ Input/config/decisions; Quick Save phải kiểm rõ output có được giữ, không chỉ notebook text.
3. Add Input gắn output của đúng Version. Điền SAVED_OUTPUT_ROOT và SAVED_VERSION dạng owner/notebook/versions/NUMBER; chạy cell verify-saved-output. Kiểm checksum/Parquet không xác minh độc lập identity API hoặc quyền tài khoản.
4. Khi tiếp tục: dùng working project mới/trống, điền RESUME_INPUT, RESUME_VERSION và SOURCE_DIRECTORY mount hiện tại. S00 restore có kiểm, không overwrite project đã có kết quả; same content/version chỉ đổi mount/root vẫn reuse. Đổi content/version/code/config/feature/split/backend/package bị stale.
5. Người nhận có đúng quyền trên nguồn/code/output, giữ cùng notebook identity. Tải notebook có output về local bằng cùng tên; không dùng gói pickle/code lạ ngoài nhóm.

Handoff giữ đủ processed/intermediate/decisions/models/predictions/manifests/code/config; không chỉ ảnh. Gói report_only có thể chỉ giữ release và code/dependencies cần đọc. Budget tính cả canonical/release/temp copy; tránh copy raw vào working, dừng khi quá budget. Nếu code chỉ báo prepare_handoff thành công, đó là chuẩn bị inventory, chưa tự Save Version. Local read-back không chứng minh Kaggle persistence. [Tài liệu Kaggle Notebook](https://www.kaggle.com/docs/notebooks).

## VII. Đọc kết quả, không chạy dữ liệu lại

Sau S10, outputs/<scope>/manifests/final_results.json chỉ tới release cụ thể. Trong S00:

```python
EXECUTION_MODE = "report_only"
PUBG_PROJECT_ROOT = "/kaggle/input/<output-version-thuc>/PUBG_Coursework"
RELEASE_MANIFEST = PUBG_PROJECT_ROOT + "/outputs/full/manifests/releases/<id>/manifest.json"
CODE_INPUT = RESUME_INPUT = ""
INSTALL_DEPENDENCIES = False
```

S00 trỏ project code đã gắn sẵn, giữ CODE_INPUT/RESUME_INPUT trống và RUN_GPU_SMOKE=False. Run All cùng notebook chỉ bootstrap đọc tối thiểu và S11/S12. Không build/download/train/write/new run; không cần raw/current checkpoint. Package và src phải được chuẩn bị sẵn. Loader xác minh artifact checksums và đủ core model/predictions/tables; missing/corrupt dừng.

| Kết quả | Cách đọc |
| --- | --- |
| rq1_relationships.csv | target/feature/mode/n, Pearson/Spearman, primary; phase-survival chỉ diagnostic |
| cluster_centers/sizes/outcomes.csv | Cluster trong từng mode, behavioral centers, valid N, outcomes sau khóa |
| validation_metrics.csv | Dùng để xem lựa chọn, khác final test |
| model_metrics.csv | experiment/split/aggregation/target/N/MAE/RMSE/R²; R² không accuracy |
| timing_comparison.csv | Same cohort/recipe; delta candidate-reference, MAE/RMSE âm tốt hơn |
| error_analysis.csv | Mode/miền target có N/matches, không tối ưu lại test bins |
| coefficients.csv | Feature order/scale đúng, đa cộng tuyến ảnh hưởng diễn giải |
| uncertainty.json/timing_ci.csv | CI nếu thực tính; không CI thì không claim significance |

Survival và placement khác đơn vị, đồ thị metrics tách target. Charts lưu PNG cùng *_source.csv và figure metadata có scope/source/caption/sample n/seed/rule. White heatmap cell có thể variance0/undefined, không phải kiểu hành vi trung bình0.

Development release report_ready=false, không dùng làm kết quả khoa học chính thức. Notebook đã chạy với fixture có thể chứng minh logic, không chứng minh dữ liệu thật/GPU/Kaggle save. C5 dùng outcome train+validation sau khóa full descriptive labels; không dùng test outcome trước G4. Environment snapshot lưu package versions thực cùng Python/hardware/config, GPU versions thêm tại fit tương ứng.

## VIII. Kiểm thử và giới hạn

```powershell
$env:OMP_NUM_THREADS="1"
$env:OPENBLAS_NUM_THREADS="1"
$env:MKL_NUM_THREADS="1"
python -B -m unittest discover -s tests -v
```

Tests tự tạo complete synthetic matches xuyên shard, expected formulas/metrics/split/missing, G4 pending/approved fixture, exact pairing/bootstrap, release corrupt/snapshot, publication failure và actual notebook/report_only. Notebook execution outputs tạm ngoài repository; không tạo notebook thứ hai trong notebooks/.

Giới hạn implementation công bố:
- Đọc Input CSV hoặc local nhỏ; không downloader/login/upload tự động, không giải nén archive không tin cậy.
- SQL/batch cho preprocessing/EDA/timing, nhưng exact OLS và per-mode KMeans collect ma trận qua RAM gate. Chưa có disk-streaming OLS; quá budget dừng resource_limited, không giảm cohort.
- CUDA backend chưa thử trên thiết bị thật trong lượt triển khai local. Đã có GPU smoke callable; chưa chạy trên CUDA/Kaggle thật.
- Requirements là khoảng phiên bản tương thích, không phải lockfile môi trường. Khi bàn giao, đối chiếu phiên bản Python/thư viện trong environment/model metadata, signature/restore chặn khác phiên bản Python/package; chưa kiểm cuML thật.
- History, RF, C2-C4, group ablation không thuộc core mới và chưa triển khai.
- Chưa có dữ liệu thật, quyết định min-games/K/G4 hoặc report chính thức; không cam kết điểm 10 từ test pass.

## IX. Báo cáo và bảo vệ

Viết từ release: vấn đề/RQ/KDD, dataset/source/cohort, cleaning/target, EDA/RQ1, clustering per_mode, baseline/OLS hai target, T0/T1, errors, limitations và tái lập. Slides chọn charts có nguồn/N/đơn vị; không train raw lớn trong buổi bảo vệ. Demo report_only và chuẩn bị bản HTML/PDF nếu cần.

Nhóm phải giải thích vì sao group match, vì sao không dùng survival descendants, vì sao per_mode/scaling/K, baseline và metrics khác nhau, timing duration proxy có coupling, hồi cứu không phải pre-match. Kết quả timing không cải thiện vẫn có giá trị nếu thí nghiệm đúng; không viết trước model thắng.
