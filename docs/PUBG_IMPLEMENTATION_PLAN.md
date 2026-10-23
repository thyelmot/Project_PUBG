# Kế hoạch xây mới bài cuối kỳ PUBG với một notebook

Phiên bản kế hoạch: 5.11, chuẩn hóa lưu trữ sau lỗi dung lượng S02 thực tế; D6/actualCUDA/nguồn thật còn mở. Cập nhật: 20/10/2026. Kế hoạch gốc: 14/10/2026.
Đặc tả: [PUBG_RESEARCH_SPEC.md](PUBG_RESEARCH_SPEC.md).
Kế hoạch công việc và tiến độ duy nhất của dự án mới.

## I. Quyết định người dùng và trạng thái

Người dùng đã chọn:

- Dự án mới hoàn toàn: làm mới code, cấu hình, notebook và tài liệu.
- Xóa thành phần dự án cũ, kể cả dữ liệu/kết quả cũ nằm trong phạm vi được xác định; không kế thừa checkpoint hoặc kết quả đã chạy.
- Chỉ kế thừa phương pháp và hướng nghiên cứu trong kế hoạch bài cuối kỳ, không sao chép nguyên implementation cũ.
- Duy nhất một notebook: notebooks/PUBG_COURSEWORK.ipynb.
- Giữ mục tiêu bài cuối kỳ chất lượng cao bám C1-C7, ba RQ và Combat Timing.
- Phương án 1: gắn dữ liệu Kaggle trực tiếp và thực thi ngay trong Kaggle Notebook; không bắt buộc tải raw về máy hoặc đưa raw lên Drive.
- Chạy từng cell/section, có bảng và biểu đồ ngay tại bước tương ứng; vẫn một notebook, không chuyển thành script chạy kín rồi chỉ xuất kết quả cuối.
- Ngày16/10/2026 người dùng đã cho phép chạy dữ liệu lớn, tạo notebook chính thức và gắn Dataset code/nguồn thật. Chưa chạy full pipeline: đang kiểm điều kiện nguồn và sửa I/O S01 để giảm bản sao, không lấy fixture làm quyết định nghiên cứu thật. Sau lần tách khỏi fixture này, giữ một notebook identity chính thức xuyên suốt các stage.

Bản core mới đã xây độc lập tại E:/NAM_BA/KY_1_NAM_BA/KHAI PHÁ DỮ LIỆU/PUBG_Coursework: một notebook hiện có 48 cells/S00-S12, một YAML, 9 file src và 6 nhóm tests (bản5.4). Lệnh xóa cây cũ Project_PUBG bị công cụ từ chối blocked by policy, chưa xóa file nào. Phương án thay thế này giữ đúng quyền xây mới và tránh kẹt phần code; không vượt chặn bằng công cụ khác. Xóa cũ và chạy thật vẫn mở, không gọi toàn dự án completed.

Lựa chọn Kaggle thay phương án vận hành Colab/Drive trong kế hoạch này. Không đổi RQ, target, cohort, full-data policy, split 70/15/15, per_mode, estimator, metric hoặc leakage rules. Có thay đổi bootstrap, đường dẫn, nơi lưu output, chữ ký checkpoint và cách bàn giao giữa phiên, vì vậy phải kiểm lại các phần đó. Spec mục X, README, YAML và notebook đã được đồng bộ Kaggle trong đợt triển khai local này. Kiểm service/GPU/save/restore thật vẫn là task chưa nghiệm thu; không suy từ fixture là đã triển khai tài khoản.

Các dấu tích còn giữ chỉ chứng minh code/CPU fixture theo evidence từng task, không chứng minh full-data. Mục có yêu cầu mới về Kaggle giữ evidence cũ để truy vết. Người dùng đã cho phép chạy dữ liệu lớn ngày16/10/2026 nhưng RUN-01 đến RUN-12 chưa nghiệm thu; không nhầm quyền chạy với chạy thành công.

Đây là kế hoạch xây mới, thay toàn bộ kế hoạch vá nối 13 notebook. Các mã NB00-12, CP00-CP15, registry/manifest/generator cũ không phải dependency hoặc tiêu chí tiến độ của dự án mới.

Mục tiêu 10 điểm được cụ thể hóa bằng phương pháp đúng, thực nghiệm trung thực, bảng/hình dễ đọc, tái lập được và nhóm bảo vệ được. Chưa có rubric giảng viên, không cam kết điểm hoặc bịa trọng số chấm.

<a id="tracking-rules"></a>

## II. Cách thực hiện

1. Đọc đặc tả và kế hoạch hiện hành. Đợt xây core đã làm nhiều task; điểm tiếp tục hiện tại là NEW01-01/NEW01-03 và các task Kaggle mở theo thứ tự, không làm lại mọi công thức đã kiểm. NEW00-04/06 dọn cũ vẫn mở riêng, không lấy cây cũ làm dependency của bản mới.
2. Mỗi lượt một giai đoạn trừ khi người dùng giao nhiều hơn; xong cập nhật evidence/điểm tiếp tục, bàn giao để kiểm tra.
3. Giai đoạn dọn cũ phải kiểm kê và xác định absolute paths trước xóa. Không cần hỏi lại lựa chọn xây mới/xóa thành phần đã xác định trong project; ngoài phạm vi chưa rõ thì không tự suy rộng.
4. Xây code mới dựa công thức/contract/method, không chép cây src/configs/tests cũ hoặc hệ thống registry phức tạp.
5. Notebook là nơi nhóm mở, chạy và đọc toàn quy trình; hàm dùng lại ở một số module Python nhỏ. Một notebook không có nghĩa giữ toàn bộ dữ liệu trong RAM hoặc một cell khổng lồ.
6. Chỉ tích từng task khi logic, tích hợp và trình bày phù hợp đều có evidence. Placeholder, file tồn tại, import/AST pass, số test hoặc số cell không thay kiểm chứng.
7. Fixture (dữ liệu nhỏ kiểm thử) cùng code path, output namespace riêng. Không gọi fixture là kết quả nghiên cứu.
8. Lựa chọn K/min-games/feature/transform cần evidence thật; null phải chặn đúng phần với hướng dẫn, không default ẩn.
9. Chưa chạy dữ liệu lớn, tải raw, tạo/upload Kaggle Dataset hoặc thay đổi tài khoản khi chỉ được giao viết kế hoạch/code. Kaggle là nền tảng đã chọn, không phải sự cho phép chạy full-data. Dọn Drive cũ là việc riêng, không là prerequisite của Kaggle.
10. Không tự commit/push. Ghi nhận thay đổi theo AGENTS; trạng thái task ngay kế hoạch, không tạo kế hoạch phụ ghi đè.

Mẫu evidence:

```text
Task / trạng thái:
File/hàm; section/cell ID:
Yêu cầu và thay đổi:
Lệnh đã chạy; fixture/scope:
Expected / actual:
Bảng nguồn / output / hình đã mở:
Giới hạn / blocker / điểm tiếp tục:
Ngày; code/config/input version:
```

Không tái sử dụng dấu tích cũ, output cũ hoặc báo cáo phase cũ làm bằng chứng cho code mới. Kế thừa phương pháp không chứng minh đơn vị/schema/data mới đã được xác minh.

<a id="architecture"></a>

## III. Cấu trúc tối thiểu của dự án mới

Bản local hiện hành là PUBG_Coursework. Trên Kaggle, code và nơi ghi mới nằm tại /kaggle/working/PUBG_Coursework; nguồn dataset gắn ở Input riêng. Dùng project_id và manifest mới, không nhận dạng theo tên thư mục đơn thuần.

```text
PUBG_Coursework/
  AGENTS.md
  README.md
  PUBG_RESEARCH_SPEC.md
  PUBG_IMPLEMENTATION_PLAN.md
  CHANGELOG_FIXES.md
  requirements.txt
  .gitignore
  configs/
    project.yaml
  notebooks/
    PUBG_COURSEWORK.ipynb
  src/
    __init__.py
    io.py
    preprocessing.py
    features.py
    analysis.py
    modeling.py
    reporting.py
    kaggle_runtime.py
    gpu.py
  tests/
    test_data_features.py
    test_analysis_models.py
    test_persistence_notebook.py
    test_kaggle_runtime.py
  data/<scope>/                    Parquet typed/intermediate/processed cần cho resume
  outputs/<scope>/
    tables/
    figures/
    models/
    predictions/
    manifests/
    checkpoints/
```

Đây là cấu trúc phương pháp. Bản triển khai hiện nằm ở PUBG_Coursework vì xóa Project_PUBG bị policy chặn; module/data staging names cụ thể xem README. Chỉ thêm file/module khi có trách nhiệm thực; không scaffold hàng chục file trống, không giữ scripts/generator/test notebook tổng hợp cũ.

- Một YAML chính với các nhóm source/paths/runtime/preprocessing/features/rq2/rq3/models/report.
- README gom hướng dẫn nhóm, Kaggle Input/Output, GPU/CPU, section/cell, lưu phiên bản, resume, đọc kết quả và sửa config; không tạo nhiều guide song song.
- outputs giữ kết quả mới; fixture đặt trong thư mục tạm hoặc namespace riêng và không tham gia final results.
- Không có notebook thứ hai để test/demo/summary; execution fixture dùng bản tạm ngoài cây dự án và dọn sau test.
- Không mang raw, model, checkpoint, release hoặc lịch sử kiểm thử cũ sang outputs mới.

Vai trò thư mục trên Kaggle:

| Vị trí | Vai trò | Quy tắc |
| --- | --- | --- |
| Input dataset gắn, dưới /kaggle/input/ | CSV aggregate/event nguồn | Chỉ đọc; lấy mount path thật từ Input, ghi slug/version/relative file paths/hash, không đoán folder name |
| Input code riêng hoặc repository phiên bản cố định | src/config/docs tối thiểu | Không upload cả workspace, raw hoặc kết quả dự án cũ; ghi code version/hash |
| /kaggle/working/PUBG_Coursework | Code làm việc và data/outputs mới | Ghi file canonical; dữ liệu ở đây mới thuộc phiên runtime, chưa chứng minh đã lưu vào một Kaggle Version |
| Thư mục tạm runtime ngoài working | DuckDB spill/staging tạm | Không đưa vào gói output; kiểm dung lượng và không coi đây là lưu bền vững |
| Output của Kaggle Version cụ thể, có thể gắn lại như Input | Gói bàn giao đã lưu | Xác minh version ID, artifact inventory/checksum; restore có kiểm vào working khi tiếp tục tính toán |

Input là vùng chỉ đọc; working dùng để ghi output. [Giải thích của nhân viên Kaggle](https://www.kaggle.com/discussions/general/223073). Gắn dataset trực tiếp là luồng chính; kagglehub là lựa chọn truy cập resource cùng nền tảng, không bắt buộc viết một downloader ZIP mới. [Tài liệu kagglehub](https://github.com/Kaggle/kagglehub).

<a id="scientific-notebook-standard"></a>

## IV. Thiết kế notebook duy nhất

notebooks/PUBG_COURSEWORK.ipynb có mục lục, tiêu đề tiếng Việt có dấu, stable cell IDs và các section sau. Thứ tự section không có nghĩa mọi section phải tính lại trong mọi phiên.

| Section | Nội dung | Đầu ra và trực quan |
| --- | --- | --- |
| S00 | Bài toán, cấu hình, môi trường, nguồn và phạm vi | RQ/core-optional, paths, config required/pending, RAM/disk/GPU, trạng thái stage |
| S01 | Nguồn và schema | Inventory mọi shard, hash/rows/schema/unit evidence; quy mô shard và parse/missing |
| S02 | Cleaning, roster, chronology, split | Removal ledger/flags, roster conflicts, mode/date coverage; biểu đồ giữ-loại và bảng split |
| S03 | Feature cơ sở và target | Dictionary/công thức/validity, ví dụ tính tay, phân bố target/ratios |
| S04 | Combat Timing và merge | Identity/phase/coverage/discrepancy, timing plots, no-kill-vs-missing, bảo toàn rows |
| S05 | EDA bám C2 | N/mean/median/std/skew/quantiles/missing/zero, mode panels, retention/redundancy |
| S06 | RQ1 | Pearson/Spearman/N, primary/diagnostic, heatmap, signed coefficients và mode comparisons |
| S07 | RQ2 bám C7 | Profiles/denominators/min-games, K diagnostics/stability, centers heatmap/sizes; C5 sau khóa |
| S08 | RQ3 bám C6 | S1/P2 baseline/linear/T0, validation, G4, final-test, model/backend/metric tables, predicted-observed/residual |
| S09 | T0/T1, sai số và giải thích | Exact pairing/delta/error slices/N/coefficients; CI khi có |
| S10 | Kiểm kết quả và khóa release | Required matrix, status/reason/source/split/config/code/checksum/run IDs, release manifest |
| S11 | Đọc lại kết quả | Cùng notebook mở ở report_only: tables/figures từ manifest cụ thể, không build/train |
| S12 | Kết luận, giới hạn và bàn giao | Phát biểu truy nguồn, liên hệ C1-C7, bộ nộp, điểm tiếp tục, đóng góp nhóm |

S00 thêm bảng Input/source version/code version, working root, CPU/GPU/backend/package versions, RAM/disk và trạng thái đã lưu phiên bản. S11 đọc đúng output/version được bàn giao, không tự chọn latest. S12 hướng dẫn lưu Version, kiểm output, gắn lại và tiếp tục trên cùng notebook.

Nhánh mở rộng nếu được yêu cầu là các phần con trong chính notebook này, không thêm file notebook.

Cấu trúc Phương án 2 áp dụng trong mỗi section: câu hỏi/bối cảnh, input/provenance/scope, phương pháp/công thức/missing/leakage, thực thi từng bước, expected/actual, bảng/hình inline, cách đọc, diễn giải, giới hạn, artifact/điểm tiếp tục. Không dồn một section thành cell gọi pipeline dài rồi print paths.

Mỗi hình có ID/title/trục/đơn vị/N/scope/mode/split/source/filter/caption và 1-3 câu hướng dẫn đọc/giới hạn. Bảng lưu đầy đủ, notebook có thể preview có nhãn. Plot sample ghi n/seed/rule; thống kê chính tính đúng full eligible scope khi được gọi full. Không ép chart trang trí cho setup/finalization.

Trực quan đến đâu hiểu đến đó:

- Chia section thành cell theo bước phương pháp/QC/kết quả khi có ích; không buộc chờ S10 mới xem bảng/hình S01-S09.
- Trong bước dài, hiển thị tiến độ theo shard/batch: nguồn đang xử lý, rows đã đọc, thời gian, cảnh báo và bước hiện tại. Phân biệt số đã xử lý với tổng dữ liệu và số eligible cuối; chưa xong không công bố thống kê tạm là kết quả toàn bộ.
- Sau bước hoàn thành, hiển thị ngay bảng QC và biểu đồ từ dữ liệu thực đã commit, có cách đọc. Không vẽ lại biểu đồ toàn dữ liệu ở mỗi batch hoặc thu nhỏ cohort để giao diện nhanh.
- Trong huấn luyện, hiển thị trạng thái theo mode/thí nghiệm và chất lượng sau fit. KMeans/OLS hiện không có lịch sử epoch như mạng nơ-ron; không dựng loss curve hoặc accuracy giả.

## V. Chạy, tiếp tục và báo cáo trong một file

Ba chế độ đặt tại S00:

- development: fixture hoặc dữ liệu kiểm thử nhỏ, tách output, cùng hàm thực thi.
- full: toàn eligible data của experiment, không silent sample.
- report_only: đọc một release manifest cụ thể và hiển thị S11/S12; không download/clean/build/train/tạo run.

Cần phân biệt research scope development/full với execution mode report_only khi thiết kế config; report_only không được ghi đè scope của release.

- START_STAGE/END_STAGE đã có ở bản core local; phải kiểm lại bootstrap/range/reuse sau chuyển Kaggle, không gọi bản hiện tại đã chạy được trên Kaggle.
- Runtime mới phải chạy S00/bootstrap/init để nạp config và state từ đĩa. Không tin biến RAM phiên trước.
- Stage trước đã completed, signature/required artifacts/schema/hash hợp lệ mới reuse. Chọn bắt đầu từ S07 nhưng thiếu processed/split/decision phải báo đúng file/stage.
- Auto 5.2: stage tương thích được load; quyết định transforms/min-games/K/G4 theo protocol đã duyệt 17/10/2026 và OPTIONS từng mục. Manual vẫn dừng với diagnostics; thiếu dữ kiện nguồn hoặc tài nguyên vẫn chặn, không giả chạy xong.
- report_only đi qua S00 kiểm read-only tối thiểu, bỏ toàn stage tính toán S01-S10, chỉ load đúng release; không skip checks cần cho đọc release.
- Một người ghi một stage; takeover có chủ đích. Save model/preprocessing/ordered features/predictions ở đĩa để người khác tiếp tục.
- CPU cho I/O/SQL/EDA/metrics; KMeans và Linear Regression dùng GPU backend hỗ trợ theo cấu hình đã chọn. Không ép GPU vào toàn notebook hoặc silent CPU fallback.
- Output canonical ghi đè sau staging/validate/read-back, không (1)/(2); snapshot release mới để tái lập, không trộn với bản kết quả cũ đã bỏ.
- Dùng cùng một Kaggle notebook identity và file local PUBG_COURSEWORK.ipynb, không tạo file notebook (1)/(2) hoặc notebook riêng cho từng thành viên. Kaggle Versions là snapshot hợp lệ để bàn giao/tái lập, không phải tên file trùng cần loại bỏ. Output và checkpoint lưu riêng; notebook có output chưa chứng minh stage completed hoặc output đã lưu bền vững.

Cấu hình vận hành nền đã triển khai ở NEW01 trước khi được cho phép xử lý nguồn/full-data (lịch sử; bản upload chính thức18/10 dùng cấu hình được duyệt bên dưới):

```python
PUBG_STORAGE_MODE = "local"  # Trên Kaggle: ghi vào working, không mount Google Drive.
PUBG_PROJECT_ROOT = "/kaggle/working/PUBG_Coursework"
PUBG_REQUIRE_EXISTING_PROJECT = True
PUBG_BATCH_ROWS = 50000
EXECUTION_MODE = "development"  # Không tự giới hạn số dòng nguồn.
ALLOW_DATA_PROCESSING = False
ALLOW_FULL_DATA = False
```

Cập nhật18/10/2026: theo yêu cầu sửa trực tiếp file upload, cell parameters hiện gán full, hai cờ cho phép=True, S01-S10, mount nguồn PUBG Version3 và giả định giây được duyệt. Gán trực tiếp thay globals().get để không giữ False/pending cũ; bootstrap/guard/backend/budget không đổi. Kiểm hồi quy phải đặt cấu hình fixture/report_only sau tham số production trong bản notebook tạm; không thực thi raw lớn ở local.

Tận dụng mode local hiện có; không thêm manager/storage framework mới nếu không cần. Chuẩn bị code/config vào working rồi mới validate require-existing; không tự tạo project trống để vượt marker. source.directory trỏ mount path thật của phiên bản dataset gắn. S07/S08 chọn cuda cho KMeans/OLS khi GPU và cuML thực đã được kiểm; I/O/SQL/EDA/baselines/metrics vẫn CPU. Bật accelerator không tự biến sklearn CPU thành GPU và không tự cộng VRAM nhiều GPU.

Lưu và tiếp tục phải phân biệt hai việc:

1. Sau stage, publish/read-back/checksum ở working để có checkpoint runtime hợp lệ.
2. Lưu phiên bản Kaggle kèm các file output cần thiết, xác minh chúng xuất hiện trong Output và mở lại được từ phiên sạch; chỉ lúc đó mới ghi bằng chứng bàn giao bền vững. Không hứa auto-save Drive hoặc auto-save mọi file trong phiên.

Save & Run All chạy một phiên sạch riêng; cần cấu hình/nguồn/quyết định/restore rõ, không lấy biến RAM phiên tương tác. Nếu dùng Quick Save, phải kiểm tùy chọn lưu file output và kiểm read-back, không suy từ việc đã lưu notebook text. Output của phiên bản đã lưu có thể gắn lại làm Input. [Tài liệu Kaggle Notebook](https://www.kaggle.com/docs/notebooks).

Gói resume phải đủ processed data/split/cohort/decisions/models/preprocessors/predictions/stage manifests cho đoạn tiếp theo, cùng config/code/source version. Không chỉ lưu notebook hoặc vài ảnh. Gói report_only nhẹ hơn, đọc release đã khóa và bảng/hình/model evidence cần thiết, không bắt raw/intermediate thừa. Chọn snapshot cụ thể, không lấy latest giữa lúc nhóm đang cập nhật.

Đo riêng disk runtime, quota GPU và giới hạn output có thể lưu của tài khoản/dịch vụ tại thời điểm chạy. Tránh copy raw nguồn vào working, loại spill/temp khỏi gói, kiểm tổng Parquet/predictions/models/canonical/release có thể nhân đôi dung lượng. Nếu gói resume vượt giới hạn lưu, dừng và trình phương án lưu thêm hoặc chia công việc không đổi cohort; không âm thầm bỏ input cần resume, lấy mẫu hoặc giảm bài nghiên cứu.

Drive chỉ là nơi xuất bản sao kết quả nếu sau này được yêu cầu, không là nguồn dữ liệu hay dependency trong phương án 1. Không mount Drive, tạo token, upload dataset, đổi quyền chia sẻ hoặc dọn Drive trong lượt chỉ sửa kế hoạch. Quyền cộng tác/quota của Kaggle phải được xác minh; không hứa đổi tài khoản để vượt quota.

<a id="phase-0"></a>

## Giai đoạn 0. Chuẩn bị xóa cũ và khởi tạo dự án mới

Việc dọn cũ vẫn độc lập với môi trường Kaggle mới. Quyền xóa đã được người dùng chốt, nhưng phải giải quyết exact targets trước thực hiện và không vượt tool policy. Không đòi dọn Drive cũ trước khi kiểm code Kaggle bằng dữ liệu nhỏ.

- [x] NEW00-01: Kiểm kê toàn Project_PUBG, git diff, file ẩn, junction/symlink và thư mục dữ liệu trỏ ngoài; xác định absolute paths, số file/kích thước và trách nhiệm. Không theo liên kết để xóa ngoài root.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Kiểm kê 10 target dirs trong Project_PUBG: 6.953 file, khoảng586 MiB, 0 reparse points; .git và slide/dataset ngoài root không tác động. Read-only inventory/git diff đã xem. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW00-02: Hoàn thiện bảng xóa/viết lại/giữ kỹ thuật bên dưới bằng đường dẫn thực. Không lấy glob/root chung làm lệnh recursive delete; không xóa workspace cha.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Resolve-Path xác nhận mọi target con thuộc exact Project_PUBG; danh sách 10 dirs và3 guides được kiểm trước lệnh xóa. Lệnh bị policy reject, không giả thành công. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW00-03: Ghi đủ công thức, thiếu/zero, target, leakage, split, per_mode và timing convention vào spec mới để không phụ thuộc file decision/evidence cũ bị xóa.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Spec V/VI/VII giữ formulas/target validity/timing convention/leakage/split/profile semantics độc lập evidence cũ; bản mới không import decision reports. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [ ] NEW00-04: Xóa code/config/tests/scripts/notebooks/report/fixture/checkpoint/model/data cũ trong danh sách đã xác định; không chuyển chúng sang archive hoặc backup mới. Cập nhật trạng thái sau xóa thực, nêu rõ file nào chỉ có thể phục hồi từ nguồn/Git.
  - Trạng thái 14/10/2026: blocked: PowerShell recursive deletion exact validatedpaths bị automatictoolpolicy reject; khôngxóafile, khôngbypass bằngcôngcụkhác.
- [x] NEW00-05: Viết mới root docs, requirements/.gitignore, project config và khung src/tests cần thiết; notebook mới duy nhất không được đánh hoàn thiện từ skeleton. Giữ spec/plan mới và mục ghi nhận đợt hiện tại.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Bản độc lập PUBG_Coursework có root docs/config/requirements/.gitignore/src/tests/notebook thực, không clone implementation cũ; việc xóa cây cũ không được tính vào task này. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [ ] NEW00-06: Quét cây mới: không còn 00-12.ipynb, generator/bundle/registry/guide cũ, output/checkpoint/release cũ, source imports cũ hoặc secrets. git diff chỉ thay phạm vi đã giao, không tự commit/push.
  - Trạng thái 14/10/2026: blocked cho câycũ Project_PUBG; cây mới PUBG_Coursework sạch dependency cũ và1notebook, nhưng không giả xóa13notebookoldđãxong.
- [ ] NEW00-07: Xác minh dataset Kaggle skihikingkevin/pubg-match-deaths, version/license/schema/quyền truy cập/mount path thật; khóa phiên bản Input trước chạy. Không thay bằng dataset chỉ có aggregate vì bài chính cần event timing. Không tải hoặc scan dữ liệu lớn trong lượt chưa được phép.
  - Trạng thái 14/10/2026: đã chọn nền tảng Kaggle và nguồn theo spec; version/license/Input inventory thật chưa xác minh, source.directory hiện vẫn null. Không dùng cache/kết quả cũ làm nguồn mới.

Bảng phạm vi mục tiêu:

| Thành phần cũ trong Project_PUBG | Hành động khi thực thi NEW00 | Giới hạn |
| --- | --- | --- |
| src/, configs/, notebooks/, tests/, scripts/ | Xóa nội dung cũ; tạo mới tối thiểu | Không bê nguyên code hoặc ghép 13 notebook |
| data/, artifacts/, figures/, reports/, .tmp/ | Xóa dữ liệu/kết quả/cache/evidence cũ | Giải quyết links/exact paths trước; không theo link ra ngoài root |
| README, requirements, .gitignore, AGENTS | Viết mới theo dự án mới | Root AGENTS của workspace cha không bị xóa |
| TEAM_DRIVE, GPU_PER_MODE_GUIDE, NOTEBOOK_CELL_GUIDE | Xóa sau khi nội dung cần thiết được viết mới vào README | Không giữ guide luồng cũ song song |
| PUBG_RESEARCH_SPEC, PUBG_IMPLEMENTATION_PLAN | Giữ bản thiết kế mới và cập nhật hiện hành | Không xóa phương pháp đang lập cho dự án mới |
| CHANGELOG_FIXES | Ghi đợt hiện tại theo AGENTS | Không dựng lại lịch sử đã xóa |
| .git/ | Giữ metadata repository | Xóa sản phẩm cũ không đồng nghĩa xóa Git history hoặc remote |
| Slide C1-C7, Paper/, file bài học ngoài Project_PUBG | Ngoài phạm vi dọn | Không coi tài liệu môn học là file rác dự án |
| Data_PUBG/ZIP/recovery ngoài root | Kiểm kê riêng nếu thuộc dữ liệu dự án | Chưa tự xóa workspace cha; xác định target/nguồn trước |
| Drive project cũ | Việc dọn riêng khi có exact folder/file ID và access | Không là dependency của phương án Kaggle; không xóa trong lượt sửa kế hoạch |

Nghiệm thu: tree và project identity mới, nguồn/phương pháp không phụ thuộc reports cũ; không còn kết quả giả kế thừa. Bàn giao NEW01-01, không tự chạy raw lớn.

<a id="phase-1"></a>

## Giai đoạn 1. Chuyển cấu hình và notebook nền sang Kaggle

- [x] NEW01-01: Cập nhật một configs/project.yaml và S00 cho Kaggle: local working root, Input source/version, output/resume reference, budget và development mặc định khi chưa chạy thật. Giữ project marker/batch50000/per_mode/required-pending; không chốt K/min-games hoặc G4 từ fixture.
  - Evidence triển khai 14/10/2026 (CPU local/fixture, không actual Kaggle/GPU/full-data): project.yaml 5.1/local/working/budget; S00 development mặc định, ALLOW_DATA_PROCESSING và ALLOW_FULL_DATA=False. Tests chặn nguồn/full chưa cho phép trước tạo working; K/min-games/G4 production vẫn null/pending.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): configs/project.yaml + io.load_config: marker mới, ratios sum1, batch50000, per_mode/device/resource validation; invalid ratios/alias tests đạt, production decisions còn pending. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW01-02: Viết storage/resume nhỏ: manifest mới theo stage, input/code/config/split/cohort signatures, required outputs, checksum/schema/rows. Không clone manager/registry cũ.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): io.Context.run/require/artifact_info: status/signature/hash/bytes/CSV rows/Parquet schema; tests stale/corrupt/reuse/empty commit/resource failure đạt. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW01-03: S00 không mặc định google.colab/Drive khi chạy Kaggle; dùng PUBG_STORAGE_MODE=local, PUBG_PROJECT_ROOT=/kaggle/working/PUBG_Coursework, require-existing=True và batch50000. Marker kiểm sau chuẩn bị code; Input raw bất biến, spill ngoài working. Phân biệt working runtime với Output của Version đã lưu.
  - Evidence triển khai 14/10/2026 (CPU local/fixture, không actual Kaggle/GPU/full-data): S00 bỏ mount google.colab, dùng local root/batch50000/require-existing; prepare_project copy code có marker, không raw. Tests kernel mới/code Input không đổi SHA, target nằm trong Input bị chặn.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): S00 parameters/bootstrap và project.yaml giữ4PUBG settings/require-existing/marker; actual notebook fixture chạy local. Chỉ nghiệm thu code routing, chưa Drive. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW01-04: Tạo đúng notebooks/PUBG_COURSEWORK.ipynb với mục lục/S00-S12 và stable cell IDs. Chỉ notebook này là source trình bày; không cần generator hoặc bundle nhúng toàn dự án nếu không có nhu cầu thật.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): notebooks/PUBG_COURSEWORK.ipynb duy nhất trong bản mới, 46cells/13sections/15code cells; test nbformat/AST/headings và actual execution đạt. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW01-05: Kiểm execution modes/stage range/reuse với Kaggle; S00 báo thiếu Input/code/dependency/GPU và quyết định cần ở bước tương ứng trước công việc dài. report_only không copy code, restore, install/extract/build/write hoặc tạo run.
  - Evidence triển khai 14/10/2026 (CPU local/fixture, không actual Kaggle/GPU/full-data): Notebook actual kernel kiểm stage ranges/processing guard, preflight và report_only; report_only đọc saved snapshot không restore/copy/install/write, tree SHA bất biến. Installer yêu cầu restart để không trộn phiên bản trong RAM.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): S00 START/END exact whitelist và full/development/report_only; actual notebook stage-range/complete/reuse/report-only fresh kernels. report_only toàn tree SHA bất biến. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW01-06: Fixture kiểm root/paths/schema/config/type/bad device/writer/stale/publish thất bại; hình/bảng S00 có actual environment, không gọi disk runtime là Drive quota.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Persistence tests: ownerA lock chặn ownerB, takeover fixture/empty commit failed, publication failure giữgood, MemoryError resource_limited; schema/config unit tests và environment tables actual. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.

- [x] NEW01-07: Chuẩn bị luồng Add Input cho raw và gói code nhẹ có phiên bản; lấy path thật, kiểm marker/allowlist rồi copy code/config cần ghi vào working. Không ghi vào Input, không copy raw toàn bộ hoặc mang secrets/checkpoint cũ. Nếu dùng kagglehub, lưu resource version và đường dẫn trả về, không lấy latest ngầm.
  - Evidence triển khai 14/10/2026 (CPU local/fixture, không actual Kaggle/GPU/full-data): kaggle_runtime.prepare_project/code_archive từ allowlist, ZIP chỉ code/config/docs/notebook; không raw/outputs/secrets files. Không downloader/kagglehub tự gọi latest; Kaggle attachment/upload chưa thực hiện.
- [ ] NEW01-08: Preflight và GPU smoke bằng fixture nhỏ: Python/packages/CUDA/cuML/GPU thực, RAM/VRAM/disk, fit/reload KMeans per_mode và OLS. Lưu phiên bản tái lập, kiểm đúng backend; unavailable/OOM thì dừng với reason, không silent CPU fallback hoặc đổi estimator. Chưa chạy full-data.
  - Cập nhật 14/10/2026: người dùng gửi gpu_smoke 48 dòng synthetic status=passed/device=cuda trên Tesla T4 (Python3.13.15/cuML26.02/CuPy14.0.1) tại notebook quangthinng/project-pubg-abc, và báo hoàn thành cập nhật DuckDB/psutil; chưa có snapshot phiên bản sau cài. Đây là evidence GPU nhỏ do người dùng cung cấp, không chứng minh pipeline per_mode/Version save. Đã bổ sung gói fixture tách biệt và hướng dẫn S01-S04 trong README; kết quả local/giới hạn ghi CHANGELOG_FIXES.md, giữ task mở.
  - Trạng thái triển khai 14/10/2026: Code preflight/GPU smoke synthetic48 và no-fallback guard đã kiểm local. Không có CUDA/Kaggle runtime được cấp; người dùng chọn chỉ local nên actual GPU fit/reload chưa làm, không tích.
- [x] NEW01-09: Thiết kế gói output/save có inventory/checksum/relative paths/source+code+config version và budget; tách checkpoint runtime với bằng chứng Kaggle Version đã lưu/read-back. Canonical tên file cố định, giữ snapshot release mới cần tái lập, không coi notebook autosave là file persistence. Hướng dẫn thao tác save rõ, không tự tạo API token/upload/chia sẻ.
  - Evidence triển khai 14/10/2026 (CPU local/fixture, không actual Kaggle/GPU/full-data): prepare_handoff inventory/checksum/Parquet toàn cột/budget, không nhận saved_version_verified=True. verify_handoff bắt version reference cụ thể, chặn incomplete/duplicate/path escape/corrupt; local read-back ghi rõ không là Kaggle save proof.
- [x] NEW01-10: Restore từ Output của một Version cụ thể vào working: validate toàn artifact và đủ prerequisites, kiểm đường dẫn archive nếu có, không sửa manifest thành completed. Relative artifact paths dùng lại khi đổi root; source identity dựa resource version và file content, không chỉ tên mount. Khác data/code/config/split/cohort/backend/package version phải chặn hoặc báo cần kiểm lại; same source chỉ đổi root không được rebuild ngầm. Không copy khóa writer cũ sang như khóa hoạt động; takeover chỉ khi biết phiên trước đã dừng.
  - Evidence triển khai 14/10/2026 (CPU local/fixture, không actual Kaggle/GPU/full-data): restore_handoff staging vào target mới/trống; tests đổi working/source mount vẫn require/reuse S01, source version hoặc software đổi bị stale. Snapshot SHA không đổi, nonempty target bị chặn, không copy lock hoặc sửa completed. Actual notebook restored S07-S10 thành công.
- [x] NEW01-11: Bổ sung hiển thị tiến độ theo shard/batch/mode/thí nghiệm và kết quả ngay từng bước; số tạm có scope rõ, bảng/biểu đồ hoàn thành có nguồn/N/unit/QC/cách đọc. Không chart mỗi batch toàn dữ liệu, không fake loss/accuracy, không tự sample fit.
  - Evidence triển khai 14/10/2026 (CPU local/fixture, không actual Kaggle/GPU/full-data): Context.progress/live DataFrame update, CSV tối đa200 events/stage; ingest shard/batch, K diagnostics/mode và train/validation experiment. Actual output đối chiếu rows_read/shard/mode/scope, bảng/hình hiện tại bước xong; không fake epoch/loss.
- [x] NEW01-12: Đồng bộ mục vận hành X của spec cùng config/S00/README theo phương án Kaggle khi được giao triển khai; giữ phần nghiên cứu còn lại. report_only đọc release gắn như Input trong cùng notebook, không tạo folder/restore/write; đóng băng environment và kiểm trình bày sau kernel reset. Không đánh các task này xong chỉ vì kế hoạch đã đổi.
  - Evidence triển khai 14/10/2026 (CPU local/fixture, không actual Kaggle/GPU/full-data): Spec X/README/config/S00 đồng bộ Kaggle 5.1; same notebook 48 cells/S00-S12. Actual report_only từ snapshot không raw không đổi SHA; signature gắn Python/package và relative paths. Còn GPU/service read-back thật chưa kiểm.

Nghiệm thu: cấu hình/paths/phiên bản/hiển thị/resume mới có fixture evidence; kiểm Kaggle CPU/GPU nhỏ là chứng nhận riêng, không phải full-data. Chưa chạy dữ liệu lớn theo yêu cầu hiện tại.

<a id="phase-2"></a>

## Giai đoạn 2. S01/S02: nguồn, cleaning, roster, split

- [x] NEW02-01: Viết và kiểm discovery/inventory mọi shard từ Kaggle Input version cố định; CSV parser rows/hash/schema/alias, relative source paths và thiếu aggregate/event báo rõ. Không tải ZIP qua mạng khi dataset đã gắn; nếu nguồn cần giải nén, kiểm member paths/budget trước extract ngoài Input. Metadata/units chưa biết giữ pending.
  - Evidence triển khai 14/10/2026 (CPU local/fixture, không actual Kaggle/GPU/full-data): CSV discovery/lineage/inventory relative POSIX, không viết raw; fixture4shards xuyên aggregate/event và Input-like mount mới, raw SHA bất biến, header/alias/parse/budget guards. Code đã kiểm local, source version/license/schema toàn dataset thật vẫn chờ NEW00-07/RUN-03. Không nhận extract ZIP không tin cậy.
- [x] NEW02-02: Ingest batch50000 vào typed Parquet, parse error/missing/count không nguyên tách riêng; raw mới không sửa tại chỗ.
  - Bổ sung vận hành16/10/2026: typed shard chỉ là file tạm riêng theo nhóm, không còn artifact data/<scope>/typed trùng bản gộp. Sau giải mã/kiểm row count/publish read-back aggregate.parquet hoặc event.parquet mới dọn shard tạm; không đổi parsing/raw columns/lineage hoặc canonical paths dùng S02/S04. Context.parquet staging cùng filesystem, consume file tạm bằng rename, giữ checksum/rollback và copy fallback khi khác filesystem. Có ingest_storage.csv (rows/shards/byte tạm đã dọn/byte canonical/số file tạm còn lại), không gọi đây là peak disk hoặc bằng chứng đủ đĩa full-data. Kết quả đối chiếu bản cũ/bản mới, test lỗi và notebook ghi trong CHANGELOG_FIXES.md.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): preprocessing.ingest đọc Arrow CSV/string canonical/parse stats, batch<=50000, full projected typed Parquet readback; fixture4CSVshards/source SHA bất biến, không mất record. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW02-03: Deduplicate xuyên shard, conflict identity, missing keys/invalid domain và removal ledger tuần tự; không keep-first file order hoặc cộng flags chồng lặp.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): clean_split exact/raw group/conflict anti-join/flags vs sequential ledger; 241aggregate input ->240valid sau1duplicate xuyên shard, before=removed+after. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW02-04: Roster/observed teams/date/mode/conflicts trước task-specific filter; mode mapping có evidence, Custom/Other riêng, không gộp mọi >=3 thành Squad.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): match_metadata trước target cohort, distinctteam/missing/conflicting/date/party audit; targetinvalid test vẫn240rows và N_teams không lọc theo model. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW02-05: Chronology A/B/C có semantics/ties/day; split70/15/15 group match, chronology khi đáng tin, Grade B giữ nguyên ngày; actual counts và intersections lưu.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): split_matches GradeB giữwhole-day, GradeA timestampblock, GradeC deterministic match shuffle; test same-day/split3partitions/isolation và actual split summary. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW02-06: Khóa split trước EDA lựa chọn, báo test exposure nếu có; dự án mới không được lấy test đã biết làm untouched test bằng lời tuyên bố.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): S02 khóa split trước S05/06; S08 G4 giữtest đóng và prior exposure unknown được lưu, không gọi untouched test thật. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW02-07: Notebook render inventory/parse/removal/flags/roster/time/split tables và charts; fixture xuyên shard/ngày/team/duplicates xác minh expected rows và split giao0.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Actual S01/S02 cells render inventory/parse/removal/roster/time/split; source_rows/source_parse/removal/date PNG cùng source CSV, fixture30matches. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.

Đầu ra mới: source/schema/parse/removal/roster/chronology/split manifests và interim Parquet. Không reuse dữ liệu stage cũ.

<a id="phase-3"></a>

## Giai đoạn 3. S03/S04: features, targets, Combat Timing

- [x] NEW03-01: Viết dictionary/formula/units/missing/task allowlists và dependency metadata vừa đủ; không lấy mọi numeric column làm model inputs.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): features BASE/ABSOLUTE/PHASE/allowlist và dictionary; S03 formulas LaTeX/missing, forbidden target-derived unit test đạt. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW03-02: Target placement theo roster hợp lệ, N_teams>1/rank domain/team consistency; giữ raw target/flags, survival task còn được dùng khi placement lỗi.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): base_features valid_survival/valid_placement riêng, normalizedplacement khôngclip; invalid-target test survivalbad cònP2valid, placementbad cònS1valid. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW03-03: Ratios damage/kill, walk/total, assists/(kills+assists) không epsilon; denominator0 missing. S1 cấm survival và descendants.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): SQL CASE mẫu số>0, zero=>NULL; zero-kill damage/kill test, S1 feature allowlist cấm survival/phase/rates/teamplacement. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW03-04: Timing theo credited-killer non-self, không enemy-only; duration=max survival là proxy; min60 giây là quy ước, phase1/3 và2/3, out-of-range không clip.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): combat_timing giữ credited-killer non-self, proxymax/min60/thirds; unit gate pending tạodiagnostic chứkhông verified từold. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW03-05: Chunk-safe global sum/count/min; event identity qua nguồn, giữ different victims cùng giây; absolute/phase eligibility tách riêng.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Global min/sum/count và raweventdedup; same-second differentvictims +times0/100/100/200/300/999 ->6absolute/5phase, first0/avg1699÷6. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW03-06: Left merge many-to-one bảo toàn rows, no-kill khác missing-event, discrepancy/coverage đầy đủ SQL/batch; không coi units dữ liệu mới đã verified từ số audit cũ.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): LEFTtimingjoin240->240; no-kill counts0/ratiosNaN khácpositivekills/noevent; fullkill_discrepancy Parquet, audit/coverage/source charts actual. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW03-07: Kiểm Parquet giải mã toàn cột, row IDs/row counts/checksum/publish/read-back rồi commit; lỗi giữ state failed/resource_limited, không giả completed.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): io.validate_parquet iterbatchfullcolumns + publishreadback; stagechecksum/schema/rows/identity vàfailed/resource state tests, khôngcommitartifactrỗng. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW03-08: Chạy section notebook fixture phase boundaries/batch/source replay/target invalid/zero missing, mở dictionary/coverage/discrepancy/phân bố/timing charts và đối chiếu actual data.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): DataFeatures7tests + actualS03/S04 notebook: boundaries/zero/out-of-range/same-second/missing/targetinvalid; tables/PNGđãxem, scopefixture. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.

Nghiệm thu: processed dataset mới và công thức đúng; không có liên kết bắt buộc đến decision_A.md hoặc file evidence cũ sau dọn.

<a id="phase-4"></a>

## Giai đoạn 4. S05/S06: EDA và RQ1

- [x] NEW04-01: Thống kê N/mean/median/std/skew/quantiles/zero/missing bằng SQL/batch trên scope hợp lệ; plot sample không thay statistics.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): EDA SQL avg/median/std/quantiles/skew/zero/missing trên development, targetvalid filter; histogram30bins minmax gồm0bins, sourceleft/right/unit/totalN. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW04-02: EDA cấu trúc/chất lượng/raw/derived/mode/timing/retention/redundancy; development train/validation cho lựa chọn, không test-target tuning.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): eda/relationship WHEREtrain+validation; actualfixture giữ208development/32testrows, không dùngtesttargetchọnfeatures. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW04-03: Log hoặc giữ nguyên/outlier policy có lý do và evidence; không tự chọn từ fixture hoặc xóa cực trị vì boxplot.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): features.transform_reason null expected Pending; log_columns allowlist + FunctionTransformer train-only, outlier_removal none. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW04-04: Pearson/Spearman exact trên valid pairs và global ties theo scope/mode; pair-N/constant/insufficient status, không average batch correlations.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): relationship SQL validpairs/averageglobalrankties corr; canonicalN/primary/status/mode; renderedRQ1tables/charts actual. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW04-05: Registry rule cho primary-vs-diagnostic: phase-survival có coupling, rates theo target không primary; p nhỏ không đồng nghĩa mạnh, không suy nhân quả.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Survivalphaseprimary=False, targetvalidity filters, narrative association≠causal và p≠strength; allowlist tests/tracedcallers. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW04-06: S05/S06 bảng đầy đủ và distribution/mode/heatmap/signed coefficients/quan hệ minh họa, mỗi hình source/caption/cách đọc; fixture đối chiếu tham chiếu độc lập.
  - Evidence 14/10/2026, chỉ CPU fixture: đã mở hình phân phối, missing, mode, hai hình RQ1 và ba hình hệ số hồi quy có dấu, đối chiếu bảng nguồn/N/đơn vị/phạm vi. Metrics và missing semantics có kiểm tra độc lập. Xem nhật ký cho lần chạy notebook thực; không chứng nhận kết quả dữ liệu thật.

Nghiệm thu: trả lời RQ1 đúng scope/N/độ lớn; dữ liệu thật mới quyết định tham số nghiên cứu.

<a id="phase-5"></a>

## Giai đoạn 5. S07: RQ2 KMeans per_mode

- [x] NEW05-01: Viết profile Design3, player-mode keys và valid counts; phase ratio conditional mean, early active denominator, std singleton NA; outcomes riêng.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): profiles SQL14Design3features/validcounts/stdsample/conditionalmeans; test 1/1+0/3 mean0.5, singletonstdNA; outcomes không trong PROFILE_FEATURES. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW05-02: Retention/reliability chốt min-games; candidate K metrics/inertia/silhouette/sizes/seed stability development không outcomes. Null tạo diagnostics rồi hướng dẫn chốt.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Retentions vàKdiagnostics receipt độc lập outcomes, minnull/receipt null dừng; CPU fixture chọnK2córeason/hash riêng, khôngchốtproduction. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW05-03: Imputation/StandardScaler/feature order/fitted KMeans lưu và reload; GPU backend hỗ trợ theo explicit config, không fallback CPU hoặc MiniBatch ngầm.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): SimpleImputer/StandardScaler/features/KMeans dump-load/predict exact labels; GPUabsence test fail khôngfallback, compute metadata/RAMVRAM code. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW05-04: Fit full eligible profiles từng mode sau khóa; ghi descriptive scope, không heldout generalization; diagnostic sample có n/seed/rule.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Full eligible profiles per_mode fit after receipt, diagnostic uniforms n/seed/rule; fixture2mode8profiles/mode, declared full descriptive khôngheldout. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW05-05: Centers raw/standardized heatmap/sizes/naming hành vi; C5 chỉ sau khóa assignments, valid N và timing-proxy limitations rõ.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): cluster_centers/sizes/outcomes validdenominators; centeredheatmap/size/outcomes PNG nguồn actual, labels chỉtrongmode/namingghi chútheo centers. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW05-06: Fixture outcomes mutation/shuffle/missing/singleton/mode stale/reload/stability; chạy section S07 thật và mở output, không chỉ test helper.
  - Evidence 14/10/2026, chỉ CPU fixture: thay outcome không đổi feature/labels; thay final-test outcome không đổi bảng C5 train+validation. Model Solo hỏng bị chặn, checksum model Duo không đổi; không coi đây là selective per-mode refit cache. Missing, singleton, reload và seed diagnostics được kiểm; S07 chạy trong kernel mới, đã mở centers/sizes/retention/K/C5 và bảng nguồn.

Nghiệm thu: người mới hiểu KMeans, scaling, K và cụm trong từng mode. C2-C4/hierarchical/DBSCAN không thuộc core.

<a id="phase-6"></a>

## Giai đoạn 6. S08: RQ3 baseline và Linear Regression

- [x] NEW06-01: Matrix core S1/P2 mean/median/linear và T0 linear; T1=P2 reuse đúng signature/recipe/cohort. Bảy fit logic, không thêm Cartesian product.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): prediction core7fits s1/p2mean/median/linear+t0linear, T1aliasp2; actualmetrics test7experiments, registrycũ khôngimport. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW06-02: Train-only imputation/scaling/allowlists và variance/redundancy; S1 cấm survival descendants, P2 chỉ bỏ survival trực tiếp và công bố coupling gián tiếp.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Pipeline log/imputer/scaler/train-only allowlist; S1cấmdescendants/P2coupling narrative; frozen preprocessing/forbiddenfeatures tests đạt. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW06-03: Common cohort T0/T1 khóa trước fit, row IDs/target/split chính xác; event coverage/exclusions rõ, không dùng giao nhỏ của predictions.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Pre-fit T0/P2 same row-ID train/validation checks, pair_predictions exactidentity/split/target; missing/extra/duplicate/mutatedtarget tests fail đúng. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW06-04: Baselines dùng train mean/median; OLS thực fit train, validation chọn params/features, G4 khóa recipe/cohort/split/backend/seed/error bins trước test.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): G4 approval/reason/hash checks sau validation và trước matrix_data test; test assert no test predictions while Pending. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW06-05: Model/preprocessing reload, feature order/predictions/actual/residual/run metadata và batch prediction; test-label mutation không đổi fitted train pipeline/predictions.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): joblib reload1e-7, features/backend/runmeta/predictions persisted; secondG4run Pipeline.fit patched forbidden và cache reuse verified vẫn thành công. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW06-06: RAM/VRAM footprint trước collect/fit; OOM đúng status/null metric, không đổi OLS sang SGD hoặc full sang sample. RF extension chỉ nếu được đăng ký và feasible.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): matrix/profilebudget + actualavailablehost/GPUinfo và noCPUfallback; MemoryErrorstage resource_limited/null/noartifactcomplete, CPUfixture khôngGPUproof. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW06-07: Micro/match-aware và team-aware placement MAE/RMSE/R² với units/counts/undefined reason; không clip predictions hoặc average chunk RMSE/R².
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): metrics MAE1/RMSEsqrt(5/3)/R2-1.5 oracle, constantNA; weightedmatch/teamconflict logic, không clip; model table aggregation actual. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW06-08: Notebook render matrix/cohort/backend/validation/final metric tables, observed-predicted và residual plots; fixture G4 pending/approved/stale/flags/low resources.
  - Evidence 14/10/2026, chỉ CPU fixture: notebook hiển thị bảy thí nghiệm, validation/test metrics, observed-predicted/residual và errors. G4 pending không tạo test predictions; approve dùng lại fit đã khóa, Pipeline.fit bị patch cấm vẫn chạy; stale/corruption/flags/resource_limited kiểm riêng. GPU và thiếu tài nguyên thật chưa kiểm, không suy từ lỗi mô phỏng.

Nghiệm thu: kết quả thực và fair comparison, không gọi mô hình hậu trận là dự báo trước trận.

<a id="phase-7"></a>

## Giai đoạn 7. S09: timing contribution, sai số và giải thích

- [x] NEW07-01: Exact unique row-ID pairing/split/target trước delta từ saved predictions; shuffle bất biến, missing/extra/duplicate phải chặn.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): pair_predictions sort/exact unique sets vàmatch/team/split/actual/target equal; shuffleholds/mismatchraises unit tests. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW07-02: Bảng T0/T1 metrics/delta candidate-reference, N/scope/cohort/model/features/coverage; MAE/RMSE âm tốt hơn, R² dương tốt hơn.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): timing_comparison micro/match/team delta candidate-reference actualsavedtestpredictions; fixture32rows16teams, no cohortintersection. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW07-03: Error slices theo mode/vùng target từ development bins, N/matches/coverage/low-N rõ; không chọn bins vì test cho kết quả đẹp.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Train-targetquantile bins saved before G4/test; error_analysis mode/region/n/matches; source PNGper-target khôngmixedunit. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW07-04: Hệ số tuyến tính theo fitted scale/feature order, giải thích đa cộng tuyến/không nhân quả. Không bắt full ablation/permutation core.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Coefficients lấyactual imputer feature_names/model.coef/StandardScaler; correlation/coupling/causal limitations trongS08/S09. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW07-05: CI T0/T1 nếu đăng ký: paired match bootstrap giữ multiplicity, recompute metrics, seed/replicates/budget. Không CI thì reason và không claim statistical significance.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): paired_bootstrap matchcontributions/resample multiplicity/centeredSST, identicaldelta0 test40replicates; productionrep0=not_requested khôngCIgiả. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW07-06: Fixture identical predictions delta0, reference metrics/bootstrap và mismatch; notebook table/delta/error/coefficients/CI charts đối chiếu nguồn, không train lại.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): ActualS09fromsavedpredictions/no-fit, pairing/metrics/bins/figures+source tables; identical bootstrap vàmutatedactual tests đạt. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.

Nghiệm thu: giải thích được đóng góp timing và giới hạn, kết quả không cải thiện vẫn có giá trị học thuật nếu kiểm đúng.

<a id="phase-8"></a>

## Giai đoạn 8. S10/S11/S12: khóa, đọc lại và tổng hợp

- [x] NEW08-01: Required matrix chỉ core, optional reason; missing/stale/corrupt core chặn khóa, không metric giả/model rỗng hoặc chọn tất cả CSV còn trên đĩa.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): finalize require core stages/7testexperiments/tables/models; load_release format/completeness/hash guards; corruptsnapshot testraises. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW08-02: Manifest mới lưu project_id/spec/source/split/cohort/features/config/code/backend/run/checksums và figure source/caption/report_ready; fixture không official.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Releaseincludesstage source/split/config/code/backend/runmetadata and figurecsv/hash/captions; fixture scope development/report_readyfalse. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW08-03: Khóa release snapshot mới đọc được sau canonical overwrite; verify content/read-back và chọn manifest cụ thể, không lấy latest.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Copyimmutable releases/UUID/readback; mutatecanonicalRQ1 khôngđổirelease, corruptreleaseCSVverifyfailed test. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW08-04: Implement report_only trong cùng notebook: S00 minimal read-only và S11/S12; guards không build/train/download/write/fit, không cần raw/current checkpoint.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Notebookreport_onlysame46cells bỏS01-S10, S00 khôngContext/install; freshkernelbefore/aftertreeSHAequal, no newrun. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW08-05: Summary riêng từng RQ/target/T0-T1/errors/uncertainty/limitations, bảng/hình thật, cách đọc và phát biểu source/N/scope; không dùng player names thừa.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): S11coretables/PNGreload+scopewarning, S12claim/limitations/source; no assignment/playernames display; actualoutputsHTMLtables/PNG. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW08-06: Fixture valid/missing/corrupt/stale/core-optional và fresh process; mở output/report visuals, hash release trước/sau giữ nguyên.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Notebookmultiplefreshkernels fullfixture/partialPending/approved/cache/readonly; releasevalid/corrupt/canonicalmutated assertions đạt. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [ ] NEW08-07: Bàn giao cùng một notebook identity/local file và Kaggle Version cụ thể: output đã lưu/read-back, config/models/predictions/manifests cùng processed prerequisites cho stage sau. Người khác gắn lại output/version có quyền, restore có kiểm hoặc đọc report_only; optional chưa làm không completed. Không yêu cầu shortcut Drive trong luồng chính.
  - Trạng thái hiện tại 14/10/2026: người dùng cung cấp pipeline synthetic CUDA và output đọc lại Input quangthinng/project-pubg-abc/versions/3: readback_verified=True, 408 entries, S01-S10 completed. Bản tải local giữ báo cáo và verifier; không xác minh API identity/quyền nhóm. Restore để người khác tiếp tục tính toán trên Kaggle chưa kiểm; task bàn giao tổng thể vẫn mở.
  - Trạng thái 14/10/2026: mở lại bàn giao theo Version/Input/working; evidence local cũ không chứng minh file đã lưu bền vững hoặc người khác đã resume trên Kaggle.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): READMEV-VII/IX hướng dẫn config/one-notebook/paths/checksum/stage writer/snapshot/optionalnot_requested; bàn giaofixture chưaDrive. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.

Nghiệm thu: người khác xem toàn bài trong một file và mở report_only từ phiên sạch.

<a id="phase-9"></a>

## Giai đoạn 9. Kiểm thử tích hợp và README mới

- [x] NEW09-01: Chạy các section chính S00-S12 với fixture từ raw nhỏ đến locked results/report_only trong process sạch; cùng code path/full, raw bất biến, fixture namespace riêng.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Actualnotebook từ4rawshards->240playerrows/30matches->EDA/RQ2/7models/release/report_only qua codepaths, fullcompletefreshreuse kernel; rawSHAunchanged. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW09-02: Test dùng expected values tính tay/reference độc lập cho formulas/roster/split/leakage/profile/pairing/metrics/resume/publish; không sao implementation làm oracle.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): 3testgroups: hand metric/phase/split/conditionalmean/pairedreference/targetinvalid/publish/checkpoint/G4; finaltests hiện tại đạt. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW09-03: Kiểm đúng một .ipynb trong repository, schema/AST/UTF-8/cell IDs/no empty/error; tests không để notebook fixture/demo cạnh notebook chính.
  - Dọn bản tải Kaggle 14/10/2026: project-pubg-abc.ipynb có 59 cell, 48 cell chính khớp nguồn canonical và 11 cell hỗ trợ tạm. Hợp nhất về PUBG_COURSEWORK.ipynb, khôi phục stable IDs, giữ nguyên 16 cell code và 69 output gồm 34 hình ở báo cáo S11/kiểm bàn giao. Ghi rõ scope synthetic/development/Version 3; không giả output S01-S10 hoặc đưa K/G4 fixture sang config production. Kiểm schema/AST/ID/output checksum và notebook kernel local ghi ở CHANGELOG_FIXES.md.
  - Sửa trình bày 14/10/2026 theo ảnh Kaggle: công thức S03 hiện mã LaTeX thô, không phải mất dấu tiếng Việt. Đổi delimiter Markdown của sáu cell công thức sang $...$ và $$...$$, tách biểu thức dài, giữ 48 cell và nguyên 16 cell code/src/config. Bổ sung regression test cho UTF-8/NFC, delimiter, ngoặc và công thức không rỗng; evidence kiểm thử và gói ZIP cập nhật ở CHANGELOG_FIXES.md. Chưa nghiệm thu hiển thị bản sửa trên Kaggle hoặc tích thêm task GPU/save/full-data.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): nbformatschema/AST/UTF8/id/headings tests; đúng1ipynb canonical, executedfixture copies nằmTemp ngoàirepo. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW09-04: Mở từng bảng/hình/section đối chiếu N/unit/scope/labels/source/caption/cách đọc; độ chi tiết khoa học không giảm khi gộp file.
  - Evidence 14/10/2026, chỉ CPU fixture: đã mở đủ 34 PNG và kiểm bảng nguồn, từ điển 26 feature/target, output notebook, split/count/coverage/metrics/C5. Sửa footer, tách target khác đơn vị, histogram zero bins và nhãn heatmap. Notebook 46 cells, 13 sections có mục tiêu/phương pháp/QC/cách đọc/giới hạn/bàn giao; chưa xác nhận hình trên dữ liệu thật.
- [x] NEW09-05: Kiểm run-range/resume/report_only sau phiên sạch với Input nguồn và output/version gắn lại; cần đủ prerequisites, không RAM cũ. Thay source version/content/config/code/split/backend/package làm stale đúng; đổi working root đơn thuần phải giữ tính tương thích khi identity/content không đổi.
  - Evidence triển khai 14/10/2026 (CPU local/fixture, không actual Kaggle/GPU/full-data): Actual notebook S01-S10/partial/S07/S08/report_only qua kernel sạch; restore snapshot đủ prerequisites sang root mới rồi S07-S10 reuse. Corrupt/content/version/code/software guards; same mount-content không rebuild. Mô phỏng Input local, không actual Kaggle service.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): START/END routing/freshkernel/cache/gates; stale code/artifact checks; report_onlykhông cầnraw/currentcheckpoint, SHAunchanged. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [x] NEW09-06: Cập nhật README đầy đủ theo Kaggle: Add Input/pin version/gói code nhẹ, config/root/CPU-GPU/Internet-dependencies, chạy từng cell/section, progress và cách đọc, Save Version kèm output/read-back, restart/restore/report_only, quota/budget/errors, quyền nhóm và bộ nộp. Drive chỉ export optional, không tiếp tục hướng dẫn mount mặc định.
  - Evidence triển khai 14/10/2026 (CPU local/fixture, không actual Kaggle/GPU/full-data): README mới hướng dẫn Add Input/pin/code ZIP, fields/guards/dev-full/CPU-GPU, progress, stage decisions, save/read-back/restore/report_only và budget; không mount Drive mặc định hoặc chia sẻ token. Spec operational cùng version.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): README mới9mục vớisource/localCSV/Drive/CPU-GPU/sections/null/decision/resume/output/readonly/errors/team/report; khôngguidecũimports. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.
- [ ] NEW09-07: Cập nhật G0 sau chuyển Kaggle: evidence mới cho bootstrap/source/save/restore/progress/report_only, phân biệt mô phỏng local, actual Kaggle CPU/GPU nhỏ và full-data. Chỉ đóng sau task liên quan đạt; không dùng 20 tests cũ thay kiểm tương thích mới.
  - Trạng thái triển khai 16/10/2026: sau sửa I/O S01, 31/31 tests CPU local đạt trong280.573giây, gồm kernel mới/full-chain/restore/report_only và publication rollback/temp ownership; đối chiếu90bảng/dataset/predictions trước/sau đạt. 48cell/16code và69output Kaggle lịch sử bảo toàn. G0 tổng thể chưa đóng vì source/cleanup/environment/service requirements còn mở; không dùng local pass chứng minh GPU/quota/full-data. Evidence Kaggle synthetic/read-back của người dùng ghi riêng tại NEW08-07 và nhật ký.
  - Trạng thái 14/10/2026: mở lại G0 môi trường mới; core CPU 20 tests/34 hình là bằng chứng lịch sử của implementation hiện có, không chứng nhận Kaggle.
  - Evidence 14/10/2026: nhật ký ghi lệnh/kết quả kiểm thử mới, nơi lưu notebook/hình/bảng fixture và giới hạn thực. Core CPU logic đã kiểm; G0 toàn kế hoạch vẫn chưa đóng vì NEW00 cleanup và NEW02-01 downloader còn mở. Không chứng nhận G1-G5 production, GPU hoặc Drive.
- [x] NEW09-08: Kiểm chỉ còn file có vai trò mới; không metadata/rerun instructions cũ. Gói upload chỉ code/config/notebook/docs/dependencies cần; raw/results không vào Git.
  - Evidence 14/10/2026 (code/CPU fixture, không full-data/GPU/Drive): Fresh tree .gitignore bỏdata/outputs/pycache/secrets, oneconfig/onenotebook/7modules/3testfiles; READMEgóiuploadnhẹ, câycũchưađượcxóa khôngtínhpass. Lệnh: `python -B -m unittest discover -s tests -v`; xem nhật ký và Temp review outputs.

- [x] NEW09-09: Kiểm fixture Kaggle-layout ở local: Input chỉ đọc/working ghi được, mount path khác nhưng cùng content, thiếu/corrupt/version mismatch/giải nén không an toàn, save giả không có read-back và output budget. Chạy actual notebook từ đầu, resume stage giữa và report_only no-write trong kernel mới, mở tables/plots/progress; mock filesystem không chứng minh save/quota/GPU thật. Khi thực hiện kiểm môi trường Kaggle nhỏ, ghi bằng chứng riêng; chưa chạy dữ liệu lớn.
  - Evidence triển khai 14/10/2026 (CPU local/fixture, không actual Kaggle/GPU/full-data): test_kaggle_runtime gồm5 tests mới và notebook integration đã mở rộng: code copy/archive/guards, version/package/corruption/path escape/nonempty target/budget/ENOSPC/no-fallback, kernel copy+full guard, full chain+restore/report_only. Không extract archive nên path traversal bị từ chối, không cần mạng/raw lớn.

Nghiệm thu: G0 chuyển nền tảng mới đạt trước run thật; kiểm local mô phỏng không đóng task actual Kaggle, không tự chạy dữ liệu lớn.

<a id="phase-10"></a>

## Giai đoạn 10. Kaggle, chạy dữ liệu thật và bài nộp

Dữ liệu thật chỉ được chạy khi người dùng cho phép sau G0 chuyển nền tảng và preflight. RUN-01 đến RUN-12 chưa nghiệm thu toàn bộ; người dùng đã cung cấp bằng chứng S01 full completed, chưa có kết quả đầy đủ S02-S10 hoặc gói lưu official xác minh được. Dataset/Input trực tiếp trên Kaggle là luồng chính, không bắt buộc Drive. Dọn dự án/Drive cũ giữ ở phạm vi NEW00 riêng, không được suy từ lựa chọn Kaggle thành quyền thay đổi tài khoản/dataset hoặc xóa dữ liệu ngoài scope.

- [ ] RUN-01: Kiểm Kaggle account/notebook identity, quyền dataset/cộng tác và accelerator/Internet/dependencies cần thiết. Gắn nguồn version cố định, kiểm giới hạn RAM/disk/GPU/output thực và fit/reload fixture nhỏ trước full-data; không sửa license, bật public hoặc tạo token ngầm. GPU nhỏ là bước kiểm môi trường, không kết quả nghiên cứu.
- [ ] RUN-02: Đưa gói code mới tối thiểu theo version/hash vào Kaggle, chuẩn bị working project, marker/config và một notebook identity. Kiểm Input chỉ đọc, working publish/read-back, package versions và output budget; single writer. Không upload toàn workspace hoặc raw đã có trên Kaggle.
- [ ] RUN-03: Khi được phép chạy lớn, đọc mọi shard nguồn đã pin từ Input và chạy S01-S04; xác minh G1/G2 bằng inventory/quality/roster/split/timing mới. Kiểm schema/units/chronology thực, raw hash bất biến và bảng/biểu đồ từng bước; không đọc checkpoint/input cache cũ hoặc dùng dataset aggregate-only thay event source.
  - Chuẩn bị16/10/2026: người dùng đã cho phép, gửi mount /kaggle/input/datasets/skihikingkevin/pubg-match-deaths, có5aggregate/5event, CSV9.81+9.08GiB, working trống19.5GiB. Headers đầu mỗi nhóm khớp required với alias time->event_time; chưa kiểm header mọi shard/hash/rows hoặc source version đang gắn. Trước S01 phải cập nhật Dataset code bằng gói sửa I/O, restart và điền source/version/license đúng; giữ các gate mode/chronology/timing/K/G4, không ép completed.
- [ ] RUN-04: S05-S07 diagnostics, chốt transforms/min-games/K có evidence, fit clustering per_mode và lưu G3; không dùng outcome/test chọn K.
- [ ] RUN-05: S08 train/validation bằng backend thực đã kiểm, G4 trước test; S09 comparisons/errors/CI theo đăng ký. Lưu model/scaler/feature order/predictions và metadata CUDA/cuML; tiến độ theo thí nghiệm, biểu đồ có actual values; không refit ngầm khi duyệt G4.
- [ ] RUN-06: S10 khóa G5 core, kiểm release đủ bảng/hình/models/predictions/source/config/code/environment và checksum. S11/S12 đọc release/version cụ thể gắn như Input, thử report_only phiên sạch không raw/build/train/restore/write; không lấy latest hoặc công bố fixture là official.
- [ ] RUN-07: Sau stage kiểm artifact/checksum/schema/counts tại working; không bắt lưu Version sau mỗi stage. Cuối lượt hoặc tại mốc cần bảo vệ, lưu Kaggle Version kèm gói output đủ resume; xác minh output đã lưu bằng phiên sạch, ghi version ID/checkpoint cuối/tác giả/bước kế tiếp. Cùng notebook identity và tên file local, không (1)/(2). Hết quota/RAM/disk thì dừng; chỉ nói resume từ checkpoint đã có output bền vững. Quyền thành viên và quota phải phù hợp dịch vụ, không hứa shortcut Drive hoặc đổi tài khoản vượt giới hạn.
- [ ] RUN-08: Viết báo cáo từ số liệu release: bài toán/KDD, dataset/cohort, preprocessing, RQ1/RQ2/RQ3, timing, errors, limitations/reproduction; không sao metric paper làm chỉ tiêu.
- [ ] RUN-09: Slides chọn hình từ release/version đã khóa, demo cùng notebook report_only có output; tải notebook/bảng/hình/models cần thiết về local để dự phòng HTML/PDF khi cần. Không train raw lớn trong giờ bảo vệ, không phụ thuộc phiên GPU đang sống.
- [ ] RUN-10: Nhóm luyện giải thích scaling/K/per_mode, match split, target leakage/hồi cứu, baseline/metrics, timing proxy/T0-T1 và giới hạn; phân công/đóng góp thực.
- [ ] RUN-11: Đối chiếu rubric/hạn nộp/thời lượng khi có; số liệu báo cáo/slides/notebook cùng release/version; kiểm quyền chia sẻ phù hợp và không secrets/raw player identifiers thừa. Không bật public dataset/code chỉ để tiện bàn giao nếu chưa được yêu cầu và license chưa rõ.
- [ ] RUN-12: Xác minh final tree chỉ một notebook, code/docs không phụ thuộc project cũ/Drive, kiểm tải bản notebook có output về đúng tên local và restore/read-only từ version đã chọn. Ghi task chưa làm, optional reasons, cleanup blocker và điểm tiếp tục; còn blocker không gọi toàn kế hoạch completed.

<a id="completion"></a>

## VI. Tiêu chí nghiệm thu

G0 code/fixture mới; G1 nguồn; G2 cohort/split; G3 decisions; G4 selection trước test; G5 locked official results. Một file notebook không tự làm các gate đạt.

| Kiểm tra | Expected |
| --- | --- |
| Cây dự án | Một PUBG_COURSEWORK.ipynb, không import/cấu hình/checkpoint cũ |
| Source/roster/split | Đủ shard, ledger đối soát, N_teams trước task filter, match intersections0 |
| Chunk timing | t=10 và t=20/30/40 cho mean25/min10; phase boundaries đúng |
| Profile semantics | Mean ratios 1/1 và0/3 là0.5, singleton std NA, valid denominators rõ |
| Leakage | Train-only preprocessing, S1 chặn descendants, outcome không chọn clusters |
| T0/T1 | Same row IDs/target/split/recipe, mismatch phải lỗi, identical delta0 |
| Metrics | Reference MAE/RMSE/R² khớp; degenerate R² NA, không fake score |
| Stage resume | Gói Output/version đủ prerequisites; compatible reuse sau restore, stale/corrupt chặn, không RAM cũ hoặc sửa manifest bằng tay |
| Input/working | Source pin version/read-only; working ghi được, code marker đúng, không copy raw lớn vào output |
| Save/bàn giao | Checkpoint runtime tách persisted version; saved output read-back ở phiên sạch và budget phù hợp |
| report_only | Cùng notebook, release/version cụ thể gắn như Input, no raw/train/new run/restore/write |
| Hình/bảng | Inline, source/N/unit/scope/caption/cách đọc khớp actual outputs |
| Dọn cũ | Chỉ exact approved targets, không workspace/slide/.git hoặc liên kết ngoài |
| Chạy thật | Kaggle CPU/GPU/save/restore/full-data bằng actual evidence; local/mock/skipped không pass thật |

<a id="traceability"></a>

## VII. Liên hệ môn học và điểm tiếp tục

| Nội dung | Section/task |
| --- | --- |
| C1 KDD/câu chuyện nghiên cứu | S00/S12, NEW08, RUN-08/09 |
| C2 preprocessing/statistics | S01-S06, NEW02-NEW04 |
| C3 luật kết hợp/C5 Bayesian | Extension chỉ khi có câu hỏi riêng, không bắt core |
| C4 đánh giá/ensemble | S02/S08/S09; RF optional |
| C6 regression | S08/S09, NEW06/NEW07 |
| C7 clustering | S07, NEW05 |
| Một notebook duy nhất | NEW01-04, NEW09-03, RUN-12 |
| Làm mới/xóa cũ | NEW00; dọn Drive cũ là việc riêng, không dependency Kaggle |
| Kaggle/nhóm bàn giao | NEW01-07 đến NEW01-12, NEW08-07, NEW09-05/06/09, RUN-01/02/07 |
| Chi tiết khoa học/trực quan | IV và task render ở từng giai đoạn |

Điểm tiếp tục19/10/2026: bản5.8 triển khai D3 S05/S06 trên đĩa, scalar statistics một lượt quét, Type-7 quantile exact và Spearman global ties theo đúng finite pair cohort. Full regression66/66 đạt555.515giây; kiểm tập trung7/7 và stress quantiles/ranks64MiB tại mục13. D0-D2 có evidence lịch sử5.6/5.7, không là nghiệm thu nguồn thật. Davies-Bouldin5.7 vẫn mở choD4/OOC-Q3, không nới tolerance. Chưa migration5.7/S01, rootv58 riêng; bước tiếp D4, sau đó D5-D6 và actualGPU/full-data. Không đổi estimator/cohort để né thiếu tài nguyên.

Sau mỗi lượt cập nhật đúng dòng này và evidence task; không tạo thêm phần kế hoạch ghi đè.


## VIII. Cập nhật thực thi tự động 5.2, ngày 17/10/2026

Người dùng duyệt protocol tự động, có OPTIONS tại từng cell. Mục này thay các hướng dẫn hiện hành đòi chốt thủ công trong auto; evidence/task lịch sử 5.1 giữ nguyên, không xóa hoặc biến thành evidence 5.2.

- [x] AUTO-01: Cấu hình auto/manual theo section; ghi đè từng cell, None kế thừa; validate trước publish, stage signatures theo phạm vi. Đối chiếu mục XII đặc tả.
- [x] AUTO-02: Chronology có evidence/consistency/block hoặc fallback C công bố giới hạn; features no-log mặc định; min-games10; K max finite development silhouette/tie smaller K và override có kiểm.
- [x] AUTO-03: Auto G4 đúng bảy fits, validation checks/reason/hash trước final test; giữ nhánh manual và cache train-only, không metric cutoff hoặc refit ngầm.
- [x] AUTO-04: S00 nhận license và facts nguồn một lần, preflight chặn sớm facts thiếu; bỏ prepare_handoff lặp từng section mặc định, checkpoint runtime vẫn từng stage. Không gọi đây là lưu Kaggle tự động.
- [x] AUTO-05: Kiểm toàn suite, actual notebook auto fresh kernel/reuse/report_only no-write, nhánh manual, unit guards/override/corrupt/resource; đóng khi có kết quả thực.
- [x] AUTO-06: Tái tạo một notebook, đồng bộ README/ZIP và kiểm allowlist/read-back/UTF-8; ghi kết quả vào hai CHANGELOG.
- [ ] AUTO-07: Xác minh nguồn thực mode/đơn vị/chronology và ngân sách S07/S08 trên Kaggle trước công bố full-data hoàn thành. License/version metadata công khai đã kiểm; không có đơn vị/column evidence trong API trả về.

Không sửa source/raw/Kaggle account hoặc code phiên đang chạy trong lượt local. Src đổi làm checkpoint 5.1 stale theo thiết kế; không ép chữ ký cũ hoặc ghi completed bằng tay. Giữ code/output phiên cũ để bảo vệ trước khi chuyển môi trường mới; không hứa tái sử dụng S01 cũ với src mới nếu chưa có kiểm tương thích.

Kiểm đóng local AUTO-05/06 ngày17/10:37/37tests exit0 trong165.956giây. Auto review C:/Users/TT/AppData/Local/Temp/pubg-auto-review-bunnon6b; manual/restore/report_only review C:/Users/TT/AppData/Local/Temp/pubg-notebook-review-ywdyge4o. Actual notebook auto có9thông báo checkpoint và1handoff cuối, không errorcell, model hashes giữ nguyên khi reuse, report_only SHA toàn cây không đổi. Hình S07 đã mở kiểm chữ tiếng Việt/nhãn/N/scope; config/AST/schema/UTF-8/NFC và một notebook đạt. ZIP được tạo từ allowlist và kiểm CRC/nội dung từng file trước bàn giao; chi tiết kích thước cuối ghi nhật ký. Chỉ nghiệm thu implementation/local, không dịch vụ Kaggle hoặc nguồn lớn.


## IX. Protocol đơn vị khai báo 5.3, ngày 18/10/2026

Đặc tả mục XIII là quyết định hiện hành, thay điều kiện verified-only của bản5.2 theo đúng yêu cầu người dùng; bằng chứng/task lịch sử giữ nguyên.

- [x] UNIT-01: Bổ sung assumed_seconds riêng verified/pending, yêu cầu evidence/approval/đúng dataset-version; kiểm một helper dùng chung, không tạo framework mới.
- [x] UNIT-02: Production config ghi chấp thuận cho PUBG Version3 và audit prefix; notebook S00/S04 nhận override, cảnh báo rõ; không đổi dữ liệu/thang đo/cohort/estimator.
- [x] UNIT-03: Nhãn dictionary/EDA/metrics/coefficients/errors/figures/models/release/report_only phải phản ánh giả định; S03 signature gồm timing, load_release đối chiếu archived metadata/config, không promotion giả định thành verified.
- [x] UNIT-04: Test nguồn/version sai, chưa duyệt/evidence trống/pending bị chặn; so base/player_match trước-sau không rescale/drop; actual auto notebook/reuse/report_only/tampered release và full regressions. Ngày18/10:39/39tests CPU local đạt trong164.952giây; không là kiểm GPU/nguồn lớn.
- [x] UNIT-05: Tái tạo một notebook, cập nhật README/ZIP, CRC/allowlist/content, nhật ký hai cây và hướng dẫn S00 không bị giá trị pending cũ trong RAM. Kết quả đóng gói cuối ghi nối tiếp CHANGELOG.

Giới hạn: kiểm prefix20k không thay kiểm nguồn toàn bộ; 58/8096cặp lệch>1 còn chưa giải thích, không xóa khỏi nghiên cứu. Chấp thuận giả định không là xác minh tác giả nguồn hoặc hoàn tất RUN/full-data.

Kiểm local5.3: python -B -m unittest discover -s tests -v -b, threads OMP/OPENBLAS/MKL=1, exit0. Evidence auto C:/Users/TT/AppData/Local/Temp/pubg-auto-review-8_440ujl; manual/restore/report_only C:/Users/TT/AppData/Local/Temp/pubg-notebook-review-k35mqbw9. Auto chạy S01-S10 trong kernel mới, reuse model, đọc lại không ghi và từ chối metadata nâng giả định thành verified. Notebook canonical48cell/16code/0output; README có khối S00 full nguồnVersion3 để thay cell tham số đầu, không thay bootstrap.

## X. Hai GPU theo yêu cầu ngày 18/10/2026

Đối chiếu đặc tả XIV. Giữ KMeans per_mode và OLS SVD, không chuyển sang estimator phân tán, không gộp VRAM hoặc lấy mẫu. Bản5.4 mặc định gpu_ids=[0,1] cho S07/S08, cell S00 vẫn full/True/S01-S10 và bật smoke48dòng/GPU trước ingest. Có thể chỉnh gpu_ids ngay S07/S08_OPTIONS trước khi chạy, không đổi nóng.

- [x] GPU-01: Kiểm visibility hai GPU ở preflight, ánh xạ CUDA_VISIBLE_DEVICES theo mask cha; subprocess sạch mỗi GPU một worker, không fork CUDA hoặc đổi context toàn cục để fit.
- [x] GPU-02: K diagnostics song song, khóa K rồi full per_mode; ba OLS song song, G4 trước test, worker predict từ model đã reload đúng GPU. Tiến trình cha publish artifact và single-writer checkpoint.
- [x] GPU-03: Tổng matrix/host RAM và VRAM riêng, fail-fast/terminate worker, no fallback; model metadata/PID/GPU/start/finish và nhận diện cached models. Thêm kiểm thử CPU simulation, không nhận là actual CUDA.
- [x] GPU-04: Kiểm helper/parity/routing/cache/G4, actual isolated processes với thư viện CUDA giả trên CPU, failures/cleanup/resource/visibility; toàn regression + notebook fresh/restore/report_only. Ghi evidence thực sau kiểm.
- [x] GPU-05: Tái tạo notebook48cell/16code, đồng bộ README/spec/ZIP, kiểm allowlist/content/CRC, ghi hai CHANGELOG và bàn giao user chọn T4x2.
- [ ] GPU-06: Actual Kaggle T4x2 smoke/fit/reload và ngân sách full-data/source thực; không đóng từ local mock/CPU hoặc sốGPU hiển thị.

Điểm tiếp tục: local44/44tests đạt339.789giây, exit0; GPU-04/05 nghiệm thu code/local và đóng gói, không actual CUDA. GPU-06/AUTO-07/RUN giữ mở. Người dùng cập nhật cả code và notebook5.4, chọn T4x2, kiểm smoke48dòng/GPU tại S00; không suy từ CPU simulation thành fit2GPU đã xác minh. Không sửa tài khoản/dữ liệu/phiên Kaggle đang sống hoặc ép reuse checkpoint khác src.

## XI. Run All5.5: đồng bộ và tài nguyên

Theo yêu cầu hướng2 ngày18/10, đối chiếu đặc tảXV. Đã triển khai check_bundle trước import, dependency/cache/source version, rootv55 mới, auto60% availableRAM, dự toán counts/host/VRAM trướcS05 và dung lượngrelease trướcS10. Giảm copies/hashes/reload/row-ID comparisons, giữ nguyên thuật toán và toàneligibledata. Không coi source cụ thể đã vừaRAM/VRAM/đĩa.

- Kiểm đóng local ngày19/10/2026:49/49tests đạt395.243giây, exit0; actual notebook auto/reuse/restore/report_only và5tests tài nguyên mới đạt. Bản notebook48cell/16code/0output có checksum nguồn. GóiZIP17file được kiểm allowlist/CRC/byte-equality; SHA cuối ghi CHANGELOG_FIXES.md. Chỉ nghiệm thu code/local, không actualCUDA/full-data.
- GPU-06/AUTO-07/RUN vẫn mở đến khi có evidence actualKaggle/full-data. Src/config5.5 không ép reuse5.4. Không xóa/upload/commit/push hoặc tự sửa phiên Kaggle.

## XII. Kế hoạch xử lý toàn dự án với bộ nhớ giới hạn, ngày 19/10/2026

Trạng thái cập nhật19/10: bản5.9/D4 đã kiểm local, bản5.10/D5 triển khai ở mục15; D6/actualCUDA/fullsource còn mở. OOC-02 nhánhA có53tests local5.6 và benchmarkmetadata; nhánh hashpartition S02 chưatriểnkhai. OOC-03/OOC-04 có S03/S04 databaseđĩa/matchpartition5.7; OOC-05/OOC-06 có thống kê/global ranks trên đĩa5.8; S07/S08 giảm bản sao ở5.9 và số học DB có oracle độc lập. OOC-00/OOC-12 mới phần audit/guard/môi trường/cleanup cần cho các đợt đã chạy, chưa schema chữký theo producer, migration, tựtách skew hoặc partitioncheckpoint. Không hiểu các mục lộ trình bên dưới là tất cả đã hoàn thành, không dùng evidence local làm nghiệm thu full-data.

### 1. Mục tiêu, phạm vi và lựa chọn

Mục tiêu: giảm bộ nhớ đỉnh bằng tổ chức phép tính, dữ liệu trung gian và thứ tự thực thi, thay vì mặc định tăng RAM/đổi GPU. Áp dụng nguyên tắc cho S00-S12, nhưng phải phân biệt xử lý dữ liệu và huấn luyện estimator. Out-of-core là xử lý dữ liệu lớn hơnRAM bằng đọc/ghi từng phần và lưu trạng thái ngoài RAM; không có nghĩa không cầnRAM hoặc không cầnđĩa.

Đối chiếu đặc tả IV-VIII, X-XV. Giữ RQ1/RQ2/RQ3; toàn eligible cohort; nguồn Version3 và assumed_seconds; thứ tự dedup/conflict/filter; lineage; roster trước task filter; split theo trận70/15/15; feature allowlists; train-only preprocessing; per_mode; KMeans/n_init10/seeds; OLS cuML SVD; bảy fit; G4 trước test; metrics và snapshot/read-back. Không thay bằng lấy mẫu, float32, sketch/xấp xỉ, SGD/MiniBatch hoặc fit từng partition rồi ghép mô hình.

| Phương án | Nội dung | Ưu điểm | Đánh đổi | Quyết định đề xuất |
| --- | --- | --- | --- | --- |
| A | Tách truy vấn, tổng hợp trước JOIN, chiếu cột cần dùng, giải phóng bảng sau lần dùng cuối | Ít thay đổi, dễ giải thích, tận dụng code hiện có | Một số GROUP BY/global sort vẫn lớn | Bắt đầu tại S02, phù hợp người mới |
| B | Bổ sung phân vùng theo khóa, database/file tạm trên đĩa, tổng hợp nhiều lượt | Kiểm soát dữ liệu đang sống, xử lý đầy đủ nguồn | TăngI/O và độ phức tạp checkpoint/kiểm tương đương | Kết hợpA cho S02/S04 và các bước còn nghẽn |
| C | Nghiên cứu thuật toán huấn luyện ngoài RAM hoặc phân tán | Có thể giải quyết một fit không vừa bộ nhớ thiết bị | Đổi solver/backend/estimator hoặc công thức cập nhật; cần protocol và kiểm riêng | Chỉ khảo sát, chưa cho phép triển khai vào bài chính |

Kế hoạch triển khai chính là A kết hợp B theo bằng chứng đo. Không thêm Spark/Dask hoặc framework quản lý mới khi DuckDB/PyArrow/Parquet hiện có đáp ứng được. Mục tiêu đầu tiên là sửa S02, không viết lại toàn dự án một lượt.

### 2. Chẩn đoán hiện tại và quy tắc thiết kế

- S02 dùng duckdb.connect() trongRAM; nhiều bảng exact/conflicts/clean/team_check cùng tồn tại. Truy vấn metadata ghép bảng đội về dòng người chơi rồi tính nhiều COUNT(DISTINCT). OOM người dùng cung cấp xuất hiện ở metadata với khoảng1.8GiB/1.8GiB. Đây là bằng chứng lỗi một lượt thật, chưa là đo peak của toàn pipeline.
- memory_policy=auto của5.5 áp dụng budget ma trận, không thay duckdb_memory=2GB. Kế hoạch mới phải làm rõ hai budget riêng và đo SQL, không coi mở guard là tối ưu thuật toán.
- Mỗi phép tính khai báo khóa nhóm, cột cần đọc, phạm vi train/validation/test, trạng thái có thể cộng gộp, trạng thái cần distinct/sort toàn cục, đầu ra và consumer cuối cùng.
- Chỉ giữ bảng/cột đang cần; dữ liệu nguồn và lineage vẫn lưu theo contract. Giảm cột trung gian không đồng nghĩa bỏ cột nguồn khỏi artifact nghiên cứu.
- Chia lô đọc không tự giới hạn bộ nhớ GROUP BY/JOIN/ORDER BY. Dùng EXPLAIN xác định toán tử nặng; EXPLAIN ANALYZE chỉ trên dữ liệu kiểm thử có kiểm soát trước, vì nó thực sự chạy truy vấn.
- Tổng/count/min/max có thể ghép trạng thái; mean phải từ tổng/count; std ghép count/mean/M2 với cùng ddof và missing rule. Không cộng distinct-count hoặc trung bình median/quantile/correlation giữa các lô.
- SQL NULL, NaN, infinity, kiểu dữ liệu, dấu bằng ở biên pha, exact duplicates và thứ tự chọn lineage phải giống bản tham chiếu. Biến đổi làm thay đổi thời điểm lọc hoặc điều kiện dedup không được nhận là tối ưu thuần vận hành.

### 3. Thiết kế phân vùng và vòng đời dữ liệu

Khóa mặc định cho làm sạch/roster/timing là match_id. Ví dụ thiết kế:

\[
p(m)=\operatorname{stable\_hash}(m)\bmod P.
\]

- Dùng hash ổn định có phiên bản; không dùng Python hash() mặc định để lưu phân vùng giữa phiên. Hash chỉ chọn nơi lưu, mọi so sánh/dedup/join vẫn dùng khóa gốc đầy đủ để không coi va chạm hash là cùng thực thể.
- Mọi dòng của cùng trận trong mọi shard phải tới cùng phân vùng; bảng aggregate/event/metadata dùng cùng mapping khi JOIN theo trận. Trận thiếu ID giữ đúng thứ tự kiểm/ledger hiện hành, không vứt sớm để tiện phân vùng.
- P=32 chỉ là ứng viên kiểm thử, không chốt cho nguồn thật. Đo rows/bytes/cardinality từng phần; phần lệch lớn phải tách tiếp theo hash của match_id nếu còn nhiều trận. Không cắt một trận ra nhiều phần rồi tổng hợp thiếu; một trận đơn lẻ quá lớn phải báo giới hạn.
- Ghi phân vùng một lượt bằng writer có giới hạn file mở; tránh quét toàn nguồnP lần cho từng WHERE partition_id. Chọn layout vừa sốfile, không tạo file cực nhỏ cho từng trận.
- S07 phải đổi khóa tập hợp sang (player_name, team_size_mode), vì cùng người xuất hiện ở nhiều trận/phân vùng. Cộng states hoặc repartition theo khóa mới trước tạo profile; không fit trên những mảnh profile riêng.
- Thứ tự phân vùng không được thay thứ tự match dùng RNG/split. Sau gom metadata phải áp dụng global ordering/tie rules và logic chia hiện hành.
- File tạm SQL/partition thuộc runtime riêng, ngoài gói bàn giao. Artifact canonical vẫn ở data/<scope>/ và outputs/<scope>/ như contract. Database tạm hỗ trợ xử lý trên đĩa không tự trở thành checkpoint bềnvững.
- Mỗi trung gian có producer, consumer cuối, kích thước và trạng thái validated. Chỉ dọn file tạm của lượt chạy sau publish/read-back/checksum; giữ raw, canonical đã tốt và prerequisites để resume. Không dọn mọi file dựa tênglob hoặc giải phóng đĩa bằng bỏ dữ liệu cần thiết.

### 4. Kế hoạch chi tiết theo section

| Mã | Bước/file chính | Kỹ thuật và công việc | Điều kiện nghiệm thu |
| --- | --- | --- | --- |
| OOC-00 | S00; bootstrap.py, io.py, kaggle_runtime.py, requirements | Tách dependency chạyKaggle với công cụ test/export nếu phù hợp; giải quyết nbclient/nbconvert theo môi trường đã thấy, không tự downgrade cả môi trường. Ghi phiên bản thực, SQL budget, matrix budget, đường dẫn spill, nguồn và codehash | Phiên sạch phát hiện mismatch trước ingest; không vòng lặp cài/restart; report_only không cài hoặc ghi |
| OOC-01 | S01; preprocessing.ingest | Giữ ArrowCSV50k/parser/schema/raw columns; ghi Parquet theo luồng; kiểm xem tái dùng layout partition ở bước sau có tiết kiệm hơn repartition không | Mọi shard/row/parse flags/lineage/sourcehash khớp tham chiếu; không thay ingest chỉ để tối ưuS02 nếu không cần |
| OOC-02 | S02; preprocessing.clean_split | Tách distinct và metadata; tổng hợp bảng đội trước JOIN; database tạm trên đĩa; dọn intermediate sau consumer cuối; nếu vẫnOOM thì match partition | cleaned, metadata, split và removal ledger tương đương; hoàn thành test cưỡng bức memory thấp |
| OOC-03 | S03; features.base_features | Tính biểu thức trên scan từng phần; chỉ mang cột cần vào JOIN; streaming writer cho base; flags/targets tính từ metadata trận đã hoàn tất | n_teams/target/cohort/formulas/NULL và row IDs không đổi; schema/dictionary đầy đủ |
| OOC-04 | S04; features.combat_timing | Match partition cho events vàmetadata; dedup exact toàn khóa nguồn; aggregate theo match/killer; JOIN phần tương ứng và xuất theo luồng | Không nhân dòng; eventcount/sum/min/pha/coverage/discrepancy khớp; không-kill khác thiếuevent |
| OOC-05 | S05; analysis.eda | Thống kê nhiều cột trong ít lượt scan; bộ đếm/sum/trạng thái moment; median/quantile exact qua external sort/selection khiSQL hiện tại cònOOM | N/missing/zero/quantiles/skew/mode statistics khớp; không thay bằng xấp xỉ hoặc mean-of-means |
| OOC-06 | S06; analysis.relationship | Mỗi feature-target-mode chỉ đọc cột cần; lọc validpair trước rank; materialize cặp/rank trên đĩa khi cần; giữ global ties | Pearson/Spearman/N/sign/primaryflag khớp; không lấy trung bình correlation/rank từng partition |
| OOC-07 | S07; analysis.clustering/profiles | Ghép states profile theo player-mode; giữ mẫu số/mean-of-match-ratios; một tập cột numeric gọn cho mỗi mode; tái dùng dữ liệu diagnostic giữaK, hạn chế duplicate | Full profiles/features/min-games/K/seeds/diagnostics/outcomes sau khóa đúng; không gọi fit theo phần là fullKMeans |
| OOC-08 | S08; modeling.prediction | Tách khóa chuỗi khỏi numericmatrix khi không phục vụ fit; row-ID mapping trên đĩa; batch transform/predict/output; baseline trainmean/exactmedian; fit giữ backend hiện hành | Đủ7fit và T1alias; train-only transformers; T0/P2 exactpairing; reload predictions đúng; G4 trước test |
| OOC-09 | S09; modeling.comparisons | External merge theo row_id, phát hiện duplicate/missing trướcmetric; tổng hợp micro/match/team bằngstates; đọc projection thay wholepredictionframes | Metrics/deltas/errorbins đúng toàn scope; bootstrap nếu bật giữ multiplicity cấp trận |
| OOC-10 | S10; reporting.finalize | Lập dependency và byteinventory trước snapshot; kiểm dung lượng bản copy/metadata; không gom temp vào release; publish manifest cuối | Thiếu đĩa không phá release cũ; đủ bảng/hình/model/predictions theocontract, artifactchecksum/readback đạt |
| OOC-11 | S11-S12; reporting/display/notebook | Chỉ đọc manifest cụ thể; CSVpreview giới hạnrows, figure từ bảng nhỏ; mô tả scope/units thật | report_only giữ nguyên toàntree, không raw/fit/build; một notebook, bảng/hình/claims truy được nguồn |
| OOC-12 | Xuyên suốt; Context/checkpoint/tests | ĐoRSS cha/worker, SQL/spill/temp/working, thời gian và tiếnđộpartition; quy tắc commit/resume tương thích; test failure và package đồng bộ | Gián đoạn không falsecompleted, không reuse sai nguồn/code/config; có báo cáo trước/sau |

### 5. Đợt ưu tiên S02: thiết kế cụ thể

1. Giữ nguyên S01 và bản5.5 làm baseline trên dữ liệu kiểm thử; xác nhận artifactS01 hiện có bằng trạng thái/checksum, không sửa kernel đang giữ kết quả thật.
2. Tách metadata hiện tại thành các phép tổng hợp nhỏ:
   - Roster theo match: countrows/missingteam/maxplacement/durationproxy/matchtime/baddates.
   - Team theo (match_id,team_id): distinctplacement chính xác, loạiNULL khỏi phép đếm giốngSQL cũ; teamNULL vẫn góp đúng roster/missingcount.
   - Tổng hợp bảngteam theo match: n_teams là số dòngteam đã phân biệt, conflicting_teams là sốteam có ranks>1. Không JOINteam trở lại hàng chục triệu dòng chỉ để distinct lần nữa.
   - Ngày khácnhau và party_size khácnhau theo match: tính trên quan hệ key/value riêng đã distinct, giữ countdistinct bỏNULL nhưSQL cũ.
   - LEFT JOIN các kết quả về tập match chuẩn; đội/ngày/party toànNULL phải ra0 ởcount phù hợp, không làm mất trận hoặc đổi0 thànhNULL.
3. Dùng database tạm trên đĩa và ghi intermediate hẹp. Lập lần dùng cuối trước DROP exact/conflicts/teamtables; không DROP bảng còn là nguồn cho kiểm đối soát.
4. Kiểm bảnA trên tập nhiều identity ở memory_limit thấp. Nếu vẫnOOM, partition từ trước dedup/conflict để giảm cả trạng thái của các bước đầu, không chỉ partition truy vấn metadata cuối.
5. Ghép metadata toàn cục, áp dụng chronology/split trên cùng thứ tự match/tie/seed. Không chia70/15/15 độc lập mỗi phần; xác nhận không có match xuất hiện ở hai split.
6. Xuất lại cleaned/match_metadata/split theo canonical schema; ledger cộng theo các bước loại tuần tự, không cộng các flags chồnglặp.
7. Sau parity đúng mới đo nguồn thực. Lỗi mới phải giữ status và artifact đã tốt, không thay tỷlệsplit/lọc thêm dòng để hoàn thành.

### 6. Những phép tính phải giữ tính toàn cục

- Dedup và identity conflicts: mọi bản ghi của cùng khóa phải được xét chung, kể cả xuyênfile/batch. Nullidentity dùng đúng lineage hiện hành; không gộp tên thiếu thành một người.
- Median/quantile: không ghép trung vị từng batch; dùng toàn bộ thứhạng hoặc lựa chọn exact. Các giá trị biên errorbins vẫn từtrain.
- Pearson: ghép sufficientstates (trạng thái đủ để tính lại thống kê) với thuật toán ổn định số; không trungbình correlation từng batch. Kiểm targetconstant và N nhỏ như cũ.
- Spearman: rank trên đúng các cặp hữu hạn của từng feature/target/mode, average-rank cho ties toàn scope; không tái dùng rank của cohort khác hoặc tính rank từng phần rồi cộng.
- Timing: durationproxy từ roster đúngscope trước task exclusions; count/min/sum theo match/killer; meanratio của profile vẫn là mean các trận hợp lệ, không đổi thành ratio của tổngkill.
- StandardScaler/imputer: train-only với đúng missing indicators, variance convention, featureorder và object được save. Nếu thay cáchfit transformer bằng cập nhật từng batch phải kiểm attributes/predictions và compatibility riêng trước dùng.
- Match-aware metrics: mỗi dòng có trọngsố nghịch số dòng của match trong đúngcohort. Team-aware: tổng hợp dựđoán theo team sau kiểm targetnhấtquán, không trungbình metric của cácbatch.

### 7. Ranh giới S07/S08: không hứa toàn bộ estimator trở thành streaming

Out-of-core ETL/metrics không chứng minh KMeans/OLS hiện tại fit được ngoài RAM/VRAM. Memorymap chỉ giúp lưu numericmatrix trên đĩa phía CPU; estimator có thể vẫn copy toàn matrix sangRAM/GPU.

- Pha chính giữ nguyên estimator5.5; giảm keys/copies/transfer và predict theo batch. HaiGPU vẫn chạy những fit độc lập; không tự chuyển mộtfit thành distributed.
- Không huấn luyện KMeans trên từng partition rồi ghép centers; không trungbình coefficients của OLS cácpartition. Cả hai làm thay recipe hoặc lời giải.
- Nếu mộtfit vẫn không vừa, lập báo cáo cổng quyết định: rows/features/matrix bytes/đỉnhRAM/VRAM quan sát, phần nào đã tối ưu, lựa chọn và ảnh hưởng khoa học. Không đổi thuật toán tự động.
- Hướng khảo sát riêng khi người dùng yêu cầu tiếp: OLS giải theo khối bằng QR/TSQR rồi SVD khối nhỏ có thể giữ mục tiêu least-squares về toán học, nhưng thay solver/backend/persistence và phải kiểm rankdeficiency/tolerance; không dùng normal-equations đơn giản vì bình phương condition number. Full-batch Lloyd nhiều lượt quađĩa cần cùngcentroids toàn cục và đúng initialization/n_init/stopping, không tự gọi tương đương cuML hiện hành. MiniBatchKMeans/SGD là thayestimator, không thuộc pha chính.
- Không triển khai các hướng khảo sát chỉ vì người dùng yêu cầu lập kế hoạch này. Phải cập nhật đặc tả/quyếtđịnh nghiên cứu riêng nếu được yêu cầu chọn.

### 8. Checkpoint, tương thích và bảo vệ S01

Hiện signature băm tấtcảsrc và runtimeconfig; sửaS02/io hoặc đổiduckdb_memory có thể làmS01 stale. Đây là điểm cần xửlý cóthiết kế, không né bằng sửa manifest.

- OOC-12 trước patchchính: lập sơđồ code/config nào ảnhhưởng stage nào; tách định danh khoa học, thực thi và layout, ghi actualresource settings vào provenance. Loại trường khỏi signature chỉ khi chứng minh không đổi nghĩa và có test invalidation.
- Mặc định checkpoint5.5 giữ nguyên, không sửa checksum/version/status hoặc copy code nóng. Chuyển phiên mới sau bảo vệ output nếu có thể; các file hiện tại không được coi đãsave trênKaggle chỉ vì runtime cómanifest.
- ReuseS01 qua phiênbản mới chỉ được làm khi có đườngimport/migration tường minh, kiểm nguồn/parser/schema/rowcount/giải mã/checksum và ghi producer cũ. Nếu chưa có cơ chế đã kiểm thì chấp nhận chạy lạiS01, không hứa tránhđược.
- Checkpoint phần chỉ thêm ở bước thật sự dài và đãpartition: receipt có source/config/code/schema/partitionmap/rowcount/hash. File.part dở không reuse; publish phần sau kiểm, commitstage chỉ sau đủmọi phần/ledger/dependencies. Không xây manager mới cho mọi vònglặp nhỏ.
- Chuẩn hóa thứ tự nếu cần seed/hash reproducibility; thaythứ tự Parquet/filecompression có thể đổi byte hash dù cùngbảng. Nội dung đãsắp theo khóa là phép đối chiếu nghiên cứu; checksumfile vẫn kiểm toànvẹn và không thay bằng contentparity giả.

### 9. Kế hoạch kiểm thử và đo hiệu quả

OOC-Q1: Đối chiếu bản thamchiếu5.5 trên cùng fixture, cùngconfig/seed/software và bản mới. Tạo case đặc thù: duplicate/conflict xuyênshard/partition; NULL/NaN; teamplacementmâu thuẫn; ngàybịlệch; đội thiếuID; một trận lớn; partition rỗng/lệch; events khácvictim cùngtime; boundaries pha; targetconstant/rank deficient; tênUnicode.

OOC-Q2: Kiểm nguyên hàng/khóa/flags/split/cohort/target cho các đại lượng rời rạc; số thực so theo tolerance được định trước dựa precision/điều kiện số và côngthức thamchiếu. Không nới tolerance sau khi thấy kết quả để cho pass. Schema, nullcounts, setrowIDs phải exact; không chỉ so count/hash tổng hoặc in10dòng.

OOC-Q3: Đối chiếu tấtcả outputs chính: removalledger; metadata/split; base/player_match; profile counts/features; Kdiagnostics/selection/labels sau ánhxạcluster khi cần; coefficients/predictions/metrics/T0-T1; release/reportonly. Chỉ đổi tên cluster không đủ chứng minh môhình tương đương: còn phải kiểm centers/inertia/assignments/recipe.

OOC-Q4: Đo tại budgetSQL cốđịnh thấp (vídụ512MiB/1GiB/2GB để khảo sát), đủdữ liệu kiểm thử gây nhiềuunique keys. Có synthetic tăngquy mô để tái lậpOOM; ghi là synthetic, không gọi nghiên cứufull. Đo RSS bao gồm childworkers, thời gian, peaktemp/working và spill khi đo được; nếu chỉ lấy mẫutheo chu kỳ thì ghi là observed peak/lowerbound, không phải maximumchính xác. Không đặt lời hứa giảmRAM/tăngtốc trước benchmark.

OOC-Q5: Hủy giữa partition, mô phỏng diskfull/writefail/corrupt/checksum/staleconfig/sourcechanged; artifacttốt trước đó giữ nguyên, chỉ phần đãcommit tương thích được reuse. Test restart/restore/reportonly bằng kernelmới; no-write khi đọc; smokeCUDA thật ghi riêng CPU/mock.

OOC-Q6: Kiểm quy mô thật tăngdần trên tập kiểm chọn trọn trận để bảo toàn roster/event, gắn scope riêng và không dùng test outcomes tune. Mốcsmall/medium là kiểm vận hành, không thay nghiên cứufull. Sau parity và low memory đạt mới chạy đủ nguồn, ghi đúng stage nào đãcompleted.

### 10. Thứ tự triển khai và điểm dừng

| Đợt | Phạm vi | Sản phẩm và cổng hoàn thành |
| --- | --- | --- |
| D0 | OOC-00/OOC-12, baseline và an toànS01 | Báo cáo bottleneck/dependency/signature, kế hoạch chuyển phiên; chưa sửa scientificrecipe |
| D1 | OOC-02, A trước B | S02 metadata/ledger/split parity, testSQL thấpRAM và failure; nếu chưaqua không lan sang stagekhác |
| D2 | OOC-03/OOC-04, S01 chỉ nếu cần | S03/S04 stream/partition đúngkhóa, timing và row conservation đạt |
| D3 | OOC-05/OOC-06 | Thống kê exact/Spearman global, đo external-sort/spill và tránh scanthừa |
| D4 | OOC-07/OOC-08 | Profiles/numericmatrix gọn, batchpredict, cổng khảthi từngfit; dừng xin quyếtđịnh nếu buộc đổi solver/estimator |
| D5 | OOC-09/OOC-10/OOC-11 | Metrics/pairedcomparison ngoài RAM, release/readback/reportonly và ngân sáchsnapshot đạt |
| D6 | OOC-Q1..Q6, đóng gói | Một notebook tái tạo, sourcechecksum/ZIP khớp, full regression và actual CUDA/full-data táchevidence; nhật ký đầy đủ |

Độ dài công việc đánh giá theo cổng kiểm thử, không cam kết số giờ chạy thật khi chưa profile. Thứtự code ưu tiên S02, S04, S06, S08, S09; thay đổi kiến trúc dùng chung từ D0 chỉ làm mức tối thiểu cần cho các đợt đó.

Mẫu báo cáo mỗi đợt: mãtask; commit/codehash nếu có; inputversion/scope/rows; cấu hình/budget; elapsed; RSS cha/con; spill/temp/working; outputs đãso; exact/tolerance; kết quả expected/actual; failure/reuse; giới hạn; bước tiếp. Chỉ tích nhiệm vụ khi có bằng chứng, không dùng tài liệu này làm dấuđãtriển khai.

### 11. Tài liệu kỹ thuật đối chiếu

- [DuckDB tuning workloads](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads): các toán tử chặn, spill, giới hạn truy vấn nhiều toán tử, EXPLAIN và bảng trên đĩa.
- [DuckDB external aggregation](https://duckdb.org/2024/03/29/external-aggregation): tổ chức aggregation có phân vùng và trạng thái ngoài RAM.
- [scikit-learn scaling strategies](https://scikit-learn.org/stable/computing/scaling_strategies.html): streaming chỉ phù hợp estimator có cách cập nhật tương ứng; không coi mọi fit có thể chuyển thành partial_fit.

Các tài liệu hỗ trợ nguyên lý; benchmark D1 chỉ ở metadata synthetic, không chứng minh toàn nguồn hoặc estimator ngoài RAM. Evidence lịch sử local5.6:53/53tests, auto C:/Users/TT/AppData/Local/Temp/pubg-auto-review-q3vwzdwf, manual/restore/report-only C:/Users/TT/AppData/Local/Temp/pubg-notebook-review-o8gyyuuh. Evidence5.7 tại mục12 và5.8 tại mục13; điểm tiếp tụcD4, chưa có migrationS01 qua bản5.8.

### 12. Triển khai D2 và kết quả kiểm bản5.7

- Phạm vi thực hiện: OOC-03/OOC-04. S03 JOIN hẹp/validate khóa/số dòng và một lượt aggregatevalidation; S04 ghi partition theoSHA256(match_id) mộtlượt choevents/metadata/base, exactdedup/aggregation/JOIN từngphần trênđĩa rồi publishcanonical sauvalidate. Không sửaS01 hoặc thuậttoán huấnluyện.
- Mặcđịnh16phần, writer mở tốiđa16file/rowgroup8192; config timing.partitions cókiểm1..256 integer. Không gọi16 là tốiưu nguồnthật. S04_OPTIONS cho chỉnh, nhưng giữ signatureconservative nên đổi sauS03 cần chạy lạiS03. Có auditrows/countstừngphần và executionprovenance. Chưa có tựtách phầnlệch hoặc commit/resume từngphần; đó vẫn là giới hạn OOC-12, không đánhđãxong.
- Kiểm tập trung6/6 đạt39.853giây trước lần regressioncuối: frozen5.6 oracle; schema/rowIDs/nulls/counts/flags exact, doubles rtol=atol=1e-12 chốttrướckhi so; partition1/2/7/16, cross-shardreplay/khácraw, cùngtimekhácvictim, self/missingkiller, orphan/NULLmatch, boundaryphase/nonfinite/shortduration/missingproxy, emptyinput/base, duplicate metadata và lỗiENOSPC ởphần2. Canonicalcũ giữ bytehash, chỉtempsởhữu bịdọn, retrycompleted.
- Stress synthetic S04:600000events/200000base/100000matches, SQL128MiB/threads2/P16, khônglấymẫu. Bảncũ vàmới đềuđạt; thời gian lầnđo độc lập2.932s/9.346s, observedpeakRSS100ms310099968/299667456bytes; scratch77758464/48056789bytes; working24661480/25082684bytes. Bảnmới chậmhơn trong phépđo này, không suy tốcđộnguồnthật. RSS/scratch/working là observed lowerbound do lấymẫu100ms, khôngmaximumchínhxác hoặc memory_limit. Scratch đo ởfolderruntime, khôngphải quota savedoutput.
- Evidence benchmark: C:/Users/TT/AppData/Local/Temp/pubg-d2-benchmark-vby5xf5r/benchmark.json và pubg-d2-benchmark-flhz8y7w/benchmark.json. Datasetđược sinh bởi tests/test_features_outofcore.synthetic_timing; không phải nghiêncứuPUBG/fullpipeline hoặc actualCUDA.
- Giới hạn: có bảnsaophânvùng/tạm nên tăngI/O và cầnđĩa; phần/trận quáto vẫnOOM; S05/S06globalranks, S07/S08mộtfit và S09/S10 vẫn cầnD3-D6. Không chuyểnhotcode vào phiênKaggle, không sửa/xóa data/manifest cũ, không hứa reuseS01 hoặc mộtlần RunAll nguồnthật hoànthành.

- Full regression cuối: python -B -m unittest discover -s tests -v -b với OMP/OPENBLAS/MKL threads1,59/59 đạt450.453giây, exit0. Bao gồm actual notebook auto/manual/reuse/restore/report-only, dependency/source binding, mô phỏng GPU trên CPU và6tests D2. Evidence auto C:/Users/TT/AppData/Local/Temp/pubg-auto-review-kte9urui; manual/restore/report-only pubg-notebook-review-79oyg9xb. Không là actual CUDA.
- Đối chiếu mở rộng hai pipeline synthetic CPU tới S10: player_match sau sắp row_id có giá trị exact;10bảng phân tích và14bảng prediction đạt rtol1e-9/atol1e-10 đặt trước. Cluster labels exact, centers đạt ngưỡng, K từ silhouette của cả hai là Duo3/Solo2. Bỏ riêng run_id khỏi so giá trị vì nó bám hash file vật lý/thứ tự, không bỏ rowIDs/cohort/targets. Evidence C:/Users/TT/AppData/Local/Temp/pubg-d2-downstream-parity-wj56msy4/parity.json.
- OOC-Q3 chưa đóng toàn bộ: k_diagnostics Davies-Bouldin Solo/K3 là0.8471702362236838/0.8471702338757621, lệch2.347921745915471e-9, vượt ngưỡng đã đặt. Không nới tolerance sau khi thấy số. Profiles cùng dữ liệu khác thứ tự vật lý có khác biệt tối đa2.842170943040401e-14 ở std_damage; giả thuyết là sai số tích lũy số thực theo thứ tự/luồng, phù hợp [DuckDB floating-point aggregates](https://duckdb.org/docs/current/operations_manual/non-deterministic_behavior.html#floating-point-aggregate-operations-with-multi-threading), chưa xác nhận toàn chuỗi khuếch đại. D4 phải kiểm tính ổn định profile/DB và quyết định cách thực thi có bằng chứng; không đổi estimator/làm tròn số để che sai khác. Phép so ban đầu sắp theo cả cột số gây lệch căn hàng, đã sửa dùng unique non-floating keys và so khóa/NULL exact, không sửa dữ liệu hoặc ngưỡng.
- Môi trường local: Python3.13.5, DuckDB1.5.5, PyArrow23.0.1, pandas2.3.0, numpy2.2.6, scikit-learn1.7.0, scipy1.16.0; SQLthreads2, không CUDA. Đóng gói5.7 không đồng nghĩa toàn cổngQ3/Q6 hoặc toàn kế hoạch đã qua.

### 13. Triển khai D3 và kết quả kiểm bản5.8

- OOC-05: S05 dùng một aggregate scan cho scalar moments/counts của21cột; global sort/row_number từng cột trên database đĩa để lấy đầu mút Type-7 exact, kernel quantile_cont chỉ giữ tối đa2giá trị/phân vị. Giữ median/q25/q75, predicate survival và NULL theo5.7. Histogram dùng lại min/max, progress và s05_execution.json. Không pandas collect nguồn, không sketch hoặc median lô.
- OOC-06: mỗi finite feature-target-mode cohort được materialize riêng, counts và cumulative global average ranks cho ties. JOIN x/y từng bước, đối soát N và dọn bảng khi không còn consumer. Corr toàn cặp giữ dấu/NA/primary và không dùng test outcomes; ranks không tái dùng giữa cohort. Progress và s06_execution.json; tables/schema/plot sources cũ giữ nguyên.
- Phạm vi chỉ vận hành: không sửa profiles/KMeans/OLS hoặc scientific recipe, không đổi SQL2GB/threads2/matrix budget/output18GiB. Guard source hash/cached imports/report_only được giữ; rootv58 riêng, chưa migration5.7/S01. Không sửa phiênKaggle hoặc raw/output của người dùng. Giữ sai khác DB5.7/OOC-Q3 mở choD4.
- Kiểm tập trung7/7 đạt62.129giây: toàn CSV thống kê/RQ1/plot sources so frozen5.7, rtol1e-10/atol1e-12 đặt trước; quantiles exact trên empty/singleton/ties/BIGINT/extreme/nonfinite; all-missing/invalid target predicates/test-only mode và outcome cực trị không vào development; global Spearman so SciPy/cửa sổ cũ; failure S05/S06 trước publish giữ CSV tốt và chỉ dọn temp sở hữu, retry thành công. Stress sort1.2triệu/ranks600000 ởSQL64MiB/threads2 đạt. Không dùng số tests thay nghiệm thu nguồn thật.

| Helper benchmark synthetic | Limit/rows | Cũ/mới elapsed(s) | Cũ/mới observed RSS(bytes) | Cũ/mới observed scratch(bytes) | Kết quả |
| --- | --- | --- | --- | --- | --- |
| Median/q25/q75 | 64MiB/1.2triệu | 0.141/0.218 | 248668160/230100992 | 0/12769 | Cả hai đạt, giá trị exact |
| Pearson/Spearman global | 64MiB/1.2triệu | 1.078/2.486 | 304594944/296878080 | 41713664/49545657 | Cả hai đạt, sai khác cỡ1e-16 |

Các case chạy tiến trình riêng, Python3.13.5/DuckDB1.5.5/threads2; source là giá trị số giả lập, không phải PUBG. Có regression khác chạy đồng thời, elapsed không là benchmark máy cô lập. RSS gồm tiến trình con nếu có, sampled100ms là lowerbound, không maximum; scratch0 không chứng minh không spill, SQL memory_limit không là totalRSS. Working4211717bytes. Không hứa tăngtốc: mới chậm hơn và correlations dùng thêm scratch trong lần đo. Dữ liệu1.2triệu chưa chứng minh hành vi toàn nguồn67triệu hoặc các kernel/thiết bị khác.

- Evidence JSON: C:/Users/TT/AppData/Local/Temp/pubg-d3-benchmark-yyq7tjc7/benchmark.json (cũ quantile), pubg-d3-benchmark-akk_wqdc/benchmark.json (mới quantile), pubg-d3-benchmark-j5i02d25/benchmark.json (cũ corr), pubg-d3-benchmark-3p3pnolo/benchmark.json (mới corr). Có software và observed sizes. Khối dữ liệu stress trong tests/test_analysis_outofcore.py tái tạo được, không đưa vào ZIP.
- Giới hạn/điểm tiếp: chưa resume từng cột/cặp, một global sort/count/JOIN vẫn cần đĩa và RAM. D4 tối ưu profiles/matrix/predict và kiểm ổn định số học Davies-Bouldin, không đổi solver/estimator nếu chưa có quyết định riêng; D5-D6/actualT4x2/fullsource tiếp tục mở. Package5.8 đối soát notebook/source/ZIP theo nhật ký cuối.
- Nguồn kỹ thuật: [DuckDB aggregates/Type-7](https://duckdb.org/docs/current/sql/functions/aggregates.html), [window functions](https://duckdb.org/docs/lts/sql/functions/window_functions.html), [tuning blocking operators](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads.html). Chỉ dùng giải thích nguyên lý; không dùng tài liệu làm bằng chứng đã chạy nguồn thật.

- Full regression5.8: python -B -m unittest discover -s tests -v -b, OMP/OPENBLAS/MKL threads1,66/66 đạt555.515giây, exit0. Actual notebook auto/manual/reuse/restore/report_only đạt, mã GPU chỉ CPU simulation. Có log ZMQError: not a socket từ Jupyter/IPykernel local trong hai nhóm notebook, assertions vẫn qua; giữ log/ghi giới hạn, chưa xác định nguyên nhân hoặc sửa môi trường ngoàiD3. Evidence auto C:/Users/TT/AppData/Local/Temp/pubg-auto-review-6rum_vi9; manual/restore/report_only pubg-notebook-review-6q94ep0m. Không dùng đây làm chứng minh Kaggle/CUDA/full source.
- Kiểm phạm vi bằng AST với gói5.7 trước khi thay: profiles/bounded_profiles/kmeans/choose_clusters/diagnostic_fit/cluster_fit/clustering/_clustering không đổi nội dung; research config giống hệt ngoài spec_version và workingroot. Chỉ một notebook48cells/16code, sourcechecksum ràng buộc5.8; không generator/notebook phụ. Các cổng nghiên cứu và OOC-Q3 chưa được đóng bằng số lượng tests.

### 14. Triển khai D4 và kiểm bản5.9

- Phạm vi: giảm bản sao S07/S08, giữ KMeans per_mode/n_init10/seeds, OLS SVD, train-only transformer, bảyfit/T1alias, G4 trước test và toàn cohort. Không thêm dependency/framework hoặc đổi solver. Đây là tối ưu vận hành OOC-07/OOC-08, không tuyên bố mọi fit đã ngoàiRAM.
- S07 chuyển SQL profile sang database tạm trên đĩa, bỏ giữ nhiều labels đầy đủ và transformer development không dùng, lưu metadata từngmode trên Parquet tạm thay giữ mọi nhóm trong RAM; reload theo lô50000. Full profile collect và fit vẫn có cổng RAM. Chưa phân vùng player-mode/states toànS07 hoặc streaming các bảng assignments/summaries.
- S08 ghi numeric X/y float64 qua Arrow50000 thành NPY memorymap, khóa chuỗi sang Parquet riêng. Một bundle cho mỗi task/split được các thí nghiệm tái dùng, worker nhận descriptor/path nhỏ; không gửi toàn DataFrame hoặc trả fullprediction về cha. Dự đoán/reload/output theo lô, kiểm hash metadata/schema/row identity/target/cohort trước publish. Cha vẫn đọc một prediction frame cho hierarchical metrics, dự toán tính phần này; D5 phải giải quyết tiếp.
- Cổng tài nguyên đồng bộ với layout mới: full imputer/scaler/OLS allocations vẫn dự toán, cộng validation/test metrics và tổng worker khi chạyhaiGPU. Không cộng VRAM haiGPU. Error bins vẫn exact quantile toàn target train; không giảm precision hoặc lấy mẫu. Một fit không vừa thì dừng yêu cầu quyết định riêng.
- DB5.7 được xác định do phép khoảng cách norm/dot cancellation. Evidence ban đầu trên hai nhánh D2 cho directDB0.8471702282073776 và0.847170228207378, trong khi kernel cũ chênh2.347921745915471e-9. Sửa bằng Euclid hiệu tọa độ trên toàn dữ liệu, không đổi định nghĩa hoặc lựa chọnK, có oracle Decimal60digits. Không nới rtol1e-9/atol1e-10; các giá trị DB cũ không coi là oracle tuyệt đối, lưu lịch sử sai khác nguyên trạng. Kiểm cổng khoa học còn cần actualCUDA/fullsource.
- Test tham chiếu5.8 đóng băng chỉ ở tests; đối chiếu fullstage bảng profile/cụm/cohort/hệ số/metrics và14predictionframes, train statistics/missing indicators, batch boundaries/NULLschema/Unicode, dữ liệu hỏng, cổngfit/failurecleanup/G4cache. Kết quả kiểm cuối và ZIP sẽ ghi nối sau chạy đủ.
- Giới hạn: memorymap giảm bản sao chứ không biến estimator thành incremental; SQL/profile collection/metrics vẫn cần tài nguyên. Chưa nghiệmthu T4x2/67triệu dòng, chưa migrationS01 xuyênbản hoặc checkpoint từngphần. D5 (metrics/pairedcomparison/release/read-only) là bước tiếp; D6/full-data acceptance vẫn mở.
- Tài liệu gốc: [NumPy memorymap I/O](https://numpy.org/doc/stable/user/how-to-io.html), [np.load mmap_mode](https://numpy.org/doc/stable/reference/generated/numpy.load.html), [định nghĩa Davies-Bouldin](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.davies_bouldin_score.html), [cảnh báo cancellation của Euclidean norm/dot](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.pairwise.euclidean_distances.html). Tài liệu giải thích kỹ thuật, không là bằng chứng đã chạy nguồn thật.

Audit bổ sung: thống kê cohort dùng GROUP BY từng khóa riêng để tránh nhiều DISTINCT tăng bộ nhớ cùng lúc. File mapping được đóng tường minh ở lỗi cấp phát/fit/predict, kể cả traceback giữ views trên Windows; training input dọn sau consumer cuối và publish/readback canonical, trước tạo test input. Không dựa GC để dọn file đang mở. Có test chủ động gây lỗi; hai lượt regression nháp chủ động dừng để bổ sung trước freeze, không gọi đã đạt.

Đọc lại đúng evidence D2 với Decimal60digits: DB hai nhánh0.8471702282073776/0.847170228207378, oracle cùng0.8471702282073779, labels exact. Đạt ngưỡng cũ rtol1e-9/atol1e-10. JSON C:/Users/TT/AppData/Local/Temp/pubg-d4-db-readback-xylc5exp/evidence.json.

Benchmark local cuối bằng artifacts/pubg_d4_benchmark.py:600000dòng giả lập/13featuresS1, tênUnicode dài,480000train/120000validation, một meanbaseline. Không đại diện toànS08/OLS/fullsource hoặc CUDA. Từng case là tiến trình riêng nhưng có regression khác chia CPU/disk; RSS/scratch/working sampled100ms là lowerbound, không maximum hoặc SQLmemory_limit.

| SQL limit/threads2 | Cũ/mới | Elapsed(s) | Observed RSS(bytes) | Observed scratch(bytes) | Kết quả |
| --- | --- | --- | --- | --- | --- |
| 512MiB | Cũ | 10.315 | 1728294912 | 270929278 | Completed |
| 512MiB | Mới | 5.655 | 518885376 | 69829435 | Completed, predictions/metrics exact so cũ |
| 128MiB | Cũ | Không so tốc độ | 395177984 | 13137 | OOM khi collect/sort, chưa có predictions |
| 128MiB | Mới | 8.141 | 453488640 | 78851414 | Completed, predictions/metrics exact so case512MiB |

Ở512MiB inputserialized giảm270926357 còn69267996bytes, observedRSS giảm khoảng70% trong case này; không suy ra tỷ lệ hoặc tốc độ cho nguồnPUBG/tênngắn/fullKMeans-OLS. Working1871452bytes. Predictionhash cả ba casecompleted bf06316290199a0351d3dd997f82bbe1ef95400cebb64ee17ed88d821635fa5f. Evidence C:/Users/TT/AppData/Local/Temp/pubg-d4-benchmark-43iznhnl (old512), eamd6tn2 (new512), 0yuc53_d (old128), axdwxe3u (new128), mỗi folder có benchmark.json. Local Python3.13.5/DuckDB1.5.5/PyArrow23.0.1/pandas2.3.0/numpy2.2.6/sklearn1.7.0, không CUDA. Kết quả regression/đóng gói cuối ghi nối sau khi chạy đủ.

- Kiểm regression cuối5.9:74/74tests đạt620.339giây, exit0; lệnh python -B -m unittest discover -s tests -v -b, UTF8 và OMP/OPENBLAS/MKL threads1. Gồm támtests D4, actual notebook auto/manual/reuse/restore/report_only, nguồn/checkpoint/publication/resource và GPU CPU-simulation. Log artifacts/pubg_d4_regression_verified_20261019.log; các lượt nháp dừng/sửa không dùng làm kết quả này.
- Evidence notebook auto C:/Users/TT/AppData/Local/Temp/pubg-auto-review-zv3q60tc; manual/restore/report_only pubg-notebook-review-epq2d8fr. Sourcehash7795405eda850bd326226c305f2dbbd4ccf95fe03a1c4faa2a217d210e5e810d, một notebook48cells/16code/0outputs và stableIDs. Research config chỉ đổi spec_version/rootv59; formulas/estimators/metrics/G4 đã kiểm AST không đổi. DB sửa số học theo oracle độc lập như mô tả, không ép bằng chỉ số cũ có cancellation.
- Điểm tiếp tục: D5/OOC-09..11, metrics/pairedcomparison ngoàiRAM và bảo vệ release/read-only; giữ giới hạn fullprofile/fullfit, actualCUDA/fullsource/migrationS01/chốtD6 còn mở. Bản5.8 trước thay được giữ ở PUBG_notebook_backups/kaggle_code_5.8_before_d4_20261019.zip, không phải checkpoint hoặc migrationS01.

### 15. Triển khai D5, bản5.10

Kết quả cuối sau sửa spill: 88/88 tests đạt757.911giây, exit0; python -B -m unittest discover -s tests -v -b, UTF8, OMP/OPENBLAS/MKL threads1. Log artifacts/pubg_d5_regression_final_20261019.log. Có8tests evaluation và6tests release mới, actual notebook auto/manual/reuse/restore/report_only, kiểm source/resource/checkpoint và GPU mô phỏng CPU. Có ZMQError:not a socket từ Jupyter local ở ca notebook, assertions vẫn đạt; giữ log và giới hạn môi trường, chưa chẩn đoán nguyên nhân hoặc thay dependencies để che lỗi. Evidence auto C:/Users/TT/AppData/Local/Temp/pubg-auto-review-438u4x7c; manual/restore/report_only pubg-notebook-review-0a7k1ooh. Source cuối71de81ca811d4d66ebb1c432c56a370c12fb48e41411adee5996eb436af23690, notebook48cells/16code/0outputs/stableIDs. Đối chiếu YAML chỉ thay version/root; code fit/G4 không đổi AST, requirements và upstream analysis/features/preprocessing/gpu/bootstrap giữ byte. Chỉ nghiệm thu local D5, không đóng D6/CUDA/fullsource hoặc hứa mọi fullfit vừa RAM.

- OOC-09: evaluation.py tính metrics hai lượt toàn scope bằng centered/compensated sums; match counts, weighted rows và team aggregates là bảng hẹp trên database đĩa. S08 gọi cùng hàm khi nhận kết quả validation/test, không pd.read_parquet toàn prediction. S09 kiểm duplicate/missing IDs và null-safe identity/target/split trước JOIN và metrics, không giao cohort để bỏ dòng lỗi.
- S09 error bins dùng đúng train edges, mode/match counts và công thức toàn tập; residual histogram giữ pandas.cut biên/nhãn/20bins. Plot sample giữ đúng legacy RandomState, seed, physical row order và tối đa1500, đọc ba cột qua Arrow50000. Workspace chỉ số O(N) vẫn ở RAM có guard, không đổi sample để cứu tài nguyên.
- Bootstrap khi chọn giữ RNG/default_rng/seed và multiplicity theo match. Match states/within-between variance giảm cancellation, vectors numeric từng match có guard24*8bytes/match cộng kết quả, không collect full rows. Target hằng thật phải R2NA, không nhận variance giả từ rounding. Decimal60digits kiểm riêng số lớn; thường dùng rtol1e-9/atol1e-10 đặt trước, không nới sau so sánh. Không bật CI hoặc thay estimator mới.
- S00/S08 dự toán lại theo buffer predict50000 và maxlength khóa, không fullprediction metadata; thêm cổng S09 index/bootstates chỉ từ counts/keys không test-target values. Full imputer/scaler/KMeans/OLS allocations vẫn kiểm, không gộpVRAM hoặc tự fallback. SQL2GB/threads2/output18GiB không đổi.
- OOC-10: byte/hash inventory trước ghi gồm cả JSON/dựphòng1MiB; staged snapshot cùngfilesystem, validate/load trước rename, pointer cuối. Copy/validation failure giữ pointer/release cũ và dọn staging; lỗi pointer sau rename có thể để một snapshot đầy đủ chưa được trỏ tới, không đánh completed. Chưa có GC tự xóa release cũ hoặc snapshot UUID không trỏ tới.
- OOC-11: loader kiểm duplicate/bytes/checksum/path/giải mãParquet/đơn vị; coverage CSV chunks50000 và preview nrows25. Report_only không raw/training/ghi lại hoặc fullprediction collection. Readbacklocal không là savedVersionKaggle.
- Kiểm tập trung trước freeze:6/6evaluation đạt18.588giây, gồm stress1.2triệudòng/SQL128MiB/threads2 với global metrics/pair/bootstrap20replicates, không fullframe.6/6release đạt89.241giây, gồm S09CSV/plot/CI parity với công thức5.9 (frozen5.8), diskfull/copy/readback/pointer failure, duplicate/bytes/forgedcorruptParquet và bounded no-write report. Bản nháp đầu có biến plot_sample cũ che hàm mới và alias SQL fixture thiếu AS, đã sửa; không dùng lượt lỗi làm pass. Các bổ sung sau lần tập trung này cần fullregression cuối, ghi nối sau chạy thực.
- Chưa nghiệmthu CUDA/fullsource/migrationS01 hoặc mọi quota/đỉnhRAM. Vectors theo match và index RNG còn dùng RAM; SQL/spill cần đĩa; fullfit có thể vẫn bị chặn. D6 và cổng nghiên cứu thật giữ mở. Một notebookcanonical, version/rootv510/sourcehash đồng bộ và codeZIP allowlist sẽ kiểm cuối; không generator hoặc notebook sản phẩm phụ.
- Tài liệu đối chiếu: [DuckDB aggregate/compensated fsum](https://duckdb.org/docs/current/sql/functions/aggregates.html), [pandas.cut](https://pandas.pydata.org/docs/reference/api/pandas.cut.html), [DataFrame.sample](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.sample.html). API tham khảo không là evidence đã chạy; requirements vẫn pandas<3 và kiểm trên phiên bản local thực, không tự nâng theo docs mới.

Benchmark helper sau freeze5.10, artifacts/pubg_d5_benchmark.py: hai Parquetgiốngbyte ởcảhai case,1200000rows/150000matches/600000teams, bootstrap20/seed42 và sample1500 đúnglegacy. Chỉ pairedmetrics/bootstrap/plot, không toànS09/PUBG/CUDA hoặc fit estimator. Case mới SQL128MiB/threads2; case cũ pandas/NumPy, không coi SQLlimit là tổngRAM. Case subprocessriêng nhưng có regression khác chạy đồngthời, không suy speedup/tỷlệ RAM sang nguồnthật.

| Case | Elapsed(s) | Observed RSS(bytes) | Observed scratch(bytes) | Kết quả |
| --- | --- | --- | --- | --- |
| Cũ | 13.988 | 933756928 | 0 | Completed |
| Mới | 9.129 | 363671552 | 195507340 | Completed, metric/CI đạt ngưỡng, sample exact |

RSS quan sát giảm khoảng61% trong case này, không cộng với tỷlệD4 hoặc gọi totalpipeline reduction. Sampling100ms là lowerbound, không maximum; scratch0 không chứng minh không dùng memory khác. Working2559261bytes, sampling_errors0. MAE/RMSE/CI vàsamplehash exact trongcase; R2micro/match/team lệch~2.2e-16, vẫn dùng rtol1e-9/atol1e-10 đã chốt. Thêm đĩa/I/O là đánhđổi rõ. Plothash f9964c967e13eefa225909d70856f94d96de0b66a5c0a3071a20615905930a1b. Evidence C:/Users/TT/AppData/Local/Temp/pubg-d5-benchmark-lry2jpg4/benchmark.json và pubg-d5-benchmark-o4anrvpx/benchmark.json, có Python3.13.5/DuckDB1.5.5/PyArrow23.0.1/pandas2.3.0/numpy2.2.6/sklearn1.7.0 vàinputhashes.

Bổ sung resource-lifetime: validate_parquet/plotreader đóng kể cả decode lỗi, test close1/1đạt0.032s. Sourcefreeze11dc14dca46ffbbb576c494c279a12d479d2aef4529e81508d84bc7c3b7986ed; notebook48/16/0 và sourcebinding đúng. Full regression và ZIP cuối sẽ ghi nối, chưa dùng số tập trung làm nghiệmthu toànnguồn.

Phát hiện bổ sung trước đóng gói: lượt87/87tests đạt751.362s trên freeze11dc, nhưng probe hai database đồng thời có spill bắt được lỗi ngoài coverage cũ. Tái dựng cách dùng chung temp_directory trước sửa: hai sort1triệudòng/64MiB, reader ngoài dừng ở batchđầu; kết nối trong ghi/đóng cùng tên spill rồi reader ngoài tiếp tục làm subprocess kết thúc3221225477 (native access violation trênWindows), không phải Python exception có thể retry an toàn.

Sửa tại Context.disk_db: mỗi database được đặt temp_directory ở childfolder/spill của TemporaryDirectory riêng, vẫn cùng parent runtime/temp budget/SQLlimit/threads và cùng query. Không hotpatch kết nối đang sống; chỉ bản code mới tạo connection mới. Probe bản sửa đọc đủ1000000unique IDs, sum499999500000 sau khi child đóng, exit0; phiên tái dựng dùng chung vẫn lỗi như cũ. Evidence C:/Users/TT/AppData/Local/Temp/pubg-d5-spill-evidence-n6speoln/evidence.json, runner artifacts/pubg_d5_spill_audit.py và tests/probe_sql_spill.py. Probe là synthetic, không nguồnPUBG/CUDA. Test riêng subprocess được thêm vào regression để nativecrash không giết test runner; lần87tests trước đó không đủ chứng minh đã an toàn spill. Full regression sau sửa/sourcehash/ZIP cuối sẽ ghi nối.

Đo lại helpers trên code sau táchspill, source71de81ca811d4d66ebb1c432c56a370c12fb48e41411adee5996eb436af23690: cùng1.2triệudòng/150000matches/600000teams, sourcehash2Parquet vàsamplehash giữ nguyên như lầntrước. Cũ/mới completed17.910s/9.594s; observedRSS961830912/364875776bytes (giảm khoảng62% trongcase), observed scratch0/188560524bytes, working2559991bytes/sampling_errors0. Evidence C:/Users/TT/AppData/Local/Temp/pubg-d5-benchmark-8ksbazmy/benchmark.json và pubg-d5-benchmark-n7cn1ixs/benchmark.json. Đây là lần đo saufix, không thay/xóa bằngchứng lần11dc. Vẫn là observed lowerbound100ms tronglúc regression khác chạy, không camkết62% hoặc tăngtốc cho toànpipeline/nguồnthật; đánhđổi thêmđĩa/I/O. Metrics/CI đạt tolerance đặttrước vàsampleexact như cũ. Fullregression saufix ở artifacts/pubg_d5_regression_final_20261019.log.

### 16. D6: nghiệm thu xuyên suốt và giới hạn còn mở

Kết quả cuối D6 local:92/92 tests đạt865.757giây, exit0, python -B -m unittest discover -s tests -v -b, UTF8 và OMP/OPENBLAS/MKL threads1. Log artifacts/pubg_d6_regression_final_20261019.log;4tests D6 mới đạt trong cả lượt này và lượt tập trung118.326giây. Có log ZMQError:not a socket từ Jupyter local, assertions/suite vẫn đạt, không thay dependency để che log hoặc gọi đã sửa nguyên nhân. Evidence cuối C:/Users/TT/AppData/Local/Temp/pubg-d6-evidence-lmcz4xw8 (environment/parity/restore/interruption JSON); actual notebook auto pubg-auto-review-jievd9ta, manual/restore/report_only pubg-notebook-review-r868how_. Nguồn/thuật toán/config/48cells notebook giữ nguyên bytes như góiD5, nên không cần tái tạo notebook hoặc đổi version/signature. ZIP chỉ thay ba tài liệu README/spec/plan, kiểm CRC/byte-equality/sourcebinding riêng sau cập nhật số liệu này. Báo cáo nghiệm thu tóm tắt artifacts/pubg_d6_acceptance_20261019.json và checksum cuối ghi ở hai CHANGELOG. Không gọi92tests là chứng minh actualT4x2/fullsource/Q6 hoặc mọi fit vừaRAM.

D6 giữ bản5.10-evaluation-out-of-core/source71de81ca811d4d66ebb1c432c56a370c12fb48e41411adee5996eb436af23690, rootv510, toàn bộ src/config/cell code không đổi. Chỉ bổ sung tests và tài liệu/đóng gói, không bắt S01 stale vô cớ hoặc giả migration qua source khác. Notebookcanonical vẫn48cells/16code, cùng stableIDs, sourcebinding và thiết lập haiGPU độc lập.

- tests/test_pipeline_acceptance.py chạy chuỗi hai nhánh S01-S10 ở SQL128MiB/threads2, ba mode Solo/Duo/Squad, Unicode, duplicate/conflict xuyênshard, missing team/name, invalid survival và nonfinite feature. Nguồn là fixture giả lập có nhãn, không PUBG hoặc Q6 nguồn thật. Tham chiếu ghép helpers features5.6/analysis5.7/clustering-modeling5.8/reporting5.9; ingest và phần S02 dùng chung với metadata query cũ, không gọi độc lập hoàn toàn hoặc baseline5.5 nguyên gói.
- Kiểm8canonical datasets,26bảng chính,14predictionframes; exact khóa/NULL/schema/đại lượng rời rạc, float rtol1e-9/atol1e-10 đặt trước. Chỉ bỏ run_id và thứ tự vật lý khi căn hàng; không bỏ cohort/target/keys. K/labels/centers/recipe vẫn so; Davies-Bouldin kiểm riêng Decimal60 trên toàn profile diagnostic, không nới ngưỡng để bằng số cũ có cancellation.
- Restore sang root mới kiểm checksum/source/software/prerequisites, yêu cầu cả10stage reuse không gọi lại function. Report_only so SHA toàn cây trước/sau và cấm fit. Readback local ghi rõ không phải Kaggle save proof.
- Ngắt thật bằng os._exit(73) tại đầu partition2S04 sau phần1 đã ghi. Kiểm running/lock và không có canonical dở được completed; handoff/retry thường phải bị chặn. Chỉ sau child đã exit mới explicit takeover và chạy lại toànS04, giữ upstream good bytehash/rowIDs. Không nhận đã có partitioncheckpoint hoặc tựdọn scratch của process chết; test chỉ dùng thư mục sở hữu fixture.

Cổng D6 không được đóng bằng số tests:

| Cổng | Phần local đang nghiệm thu | Phần còn mở |
| --- | --- | --- |
| Q1/Q2 | Adversarial fixtures và exact/tolerance qua các nhóm D1-D6 | Không thay source inventory thật |
| Q3 | Chuỗi bảng/dữ liệu/cụm/dự đoán/metrics/release đối chiếu; DB oracle riêng | ActualCUDA có thể có sai số backend cần kiểm riêng |
| Q4 | Stresshelpers1.2triệu dòng/SQL64-128MiB và benchmark D1-D5 đã ghi | Không là measured peak toàn pipeline hoặc toàn PUBG |
| Q5 | Diskfull/corrupt/stale, ngắt process, khóa/takeover, restore/no-write | Chưa resume giữa partition/fit, chưa actualKaggle Versions |
| Q6 | Chưa chạy nguồn PUBG tăng quy mô trong lượt D6 | Whole-match small/medium operational, haiT4, nguồn đầy đủ và saved-output read-back thật |

Máy local kiểm nvidia-smi ngày19/10: một RTX3050 Laptop4096MiB, driver610.62, không haiT4. Không tự đổi productiondevice hoặc dùng CPU/mock thay actualCUDA. README mụcD6 hướng dẫn cổng S00/RunAll/lỗi/checkpoint/lưuVersion/read-back; giữ quyền full cho nguồnVersion3 đã duyệt, không mở rộng sang nguồn khác. Kết quả test/thời gian/log/evidence/ZIP cuối sẽ ghi nối sau chạy thực. Lỗi tham số Context.force ở bài test nháp đã sửa force_takeover; không sửa API production để qua kiểm và không tính lượt nháp là pass.

### 17. Lưu trữ chuẩn hóa5.11 sau lỗi S02 trên dữ liệu thật, ngày20/10

- Evidence người dùng: /kaggle/working/PUBG_Coursework_v510 chiếm18.018GiB, budget18GiB, free1.484GiB; cleaned10.681GiB/aggregate3.173GiB/event4.163GiB; S01completed/S02resource_limited. Đây không phải lỗi hếtRAM. Chỉ nâng18lên19 không đủ cho các bản widebase/player/prediction/release sau đó.
- Phạm vi vận hành được người dùng chọn hướng1: storage.layout=normalized_v1, rootv511 riêng. S01 giữ typed/raw; cleaned_rows là selector source_file/source_row; cleaned/base/player_match/kill_discrepancy là recipe cố định tái dựng fullschema qua ctx.view. Rawcolumns/lineage/rowIDs/mode/split/flags/validtarget/timing/formulas không đổi. S04 partitionbase hẹp và lưu timingstates, không sao cảbase rộng. Descriptor input trees được băm để không reuse sai trainingcache.
- S08 giữ bảyfit/T1alias/G4 như cũ, private worker outputs vẫn kiểm/reload theo50k. Parent lưu poolidentity/actual dùng chung theo exactcohort và position/predictedfloat64 từng experiment. Metadata hằng/residual tái dựng khi đọc, checksum/count/schema/ordinal/finite/identity kiểm trước publish và đọc lại; S09 sample/RNG/hist/paired metrics giữ semantics. Releasecopy chứa đủ pool/values, không hardlink canonical vào snapshot; handoff/restore/report_only kiểm dependency và no-write.
- ImportS01 là đườngcompatibility tường minh, không whitelist toàncheckpoint. Chỉ producer5.10/source71de, ASTparser/constants/writer không đổi, requirements/software/source/version/license/records/hash/Parquetđạt mới tạo S01signature hiện hành với producer_import. Hardlink cùngfilesystem tránh cần thêm7GiB; khôngfallbackcopy. Target mới/trống hoặc importidempotent tương thích, không writerlock. Chưa kiểm trên filesystemKaggle thật nên nếuhardlinkkhônghỗtrợ phải dừng.
- CLEANUP_IMPORTED_510=False. Chỉ confirm sau importđạt mới bỏ đúng cleanedS02dở và các tên hardlinkS01cũ cùnginode; retainedS01 ởrootmới phải requiređạt, chặn old/newwriterlock/completeddownstream/symlink/khôngcùnginode/filecompletedowned. Không recursive delete/rawInput. Rootcũ nghỉdùng, cleaned chỉ có thể tính lạiS02. Không gọi hardlink là backup độc lập hoặc tự xóa dữ liệuKaggle trong lượtlocal.
- Kiểm tập trung normalized5/5 đạt113.191s (lượt trước4/4 đạt51.326s trước thêmcase100007rows); import/cleanup3/3 đạt16.593s trước vài bổ sung thông báo/guard sourcefacts. So fullchainwide/normalized3modes,17bảngchính/14predictionframes, logicalETL/fullrawschema, missingpool/corruptposition/cacheinput, report_only/treeSHA, restore10stage reuse, sampleexact và float64 qua50000/100000 biên. Importtests dùng code5.10 đóng băng tạo S01 thật và S02 fail tại recordcleaned, kiểm không copy haiParquet lớn và retainedS01 hash nguyên sau cleanup. Fullregression sẽ ghi nối trên freeze cuối.
- Mã nguồn freeze5.11:4e3f9a191e589c963727c12bbf00ec656ee6bf17de0621ca6a6f520b3641dd3c. Notebook tái tạo cùng48cells/16code/0outputs/stableIDs, thêm hai tham số import/cleanup trong cellparameters hiện có, không notebook/cell bổ sung. Sourceversion3/assumed_seconds/SQL2GB/threads2/budget18GiB/haiGPU giữ nguyên; chỉ nghiên cứu/producer/layout fields thay theo đặc tảXXII.
- Kiểm cuối trên source freeze: 100/100 đạt trong bốn tiến trình unittest độc lập, không phải một lượt serial100tests. Các nhóm a/b/c/d:30tests150.940s,20tests210.109s,21tests199.929s,29tests273.976s; log artifacts/pubg_511_regression_{a,b,c,d}_20261020.log. Bao gồm đủ100test được discover, không trùng/thiếu; normalized5tests/import3tests đều đạt trong nhómd. Không cộng thời gian tiến trình thành thời gian tường hoặc gọi mô phỏng CPU là actualCUDA.
- Đo lại source freeze: materialized/normalized cùngCSVbytes, completed34.015s/31.888s, finalproject99406055/25616163bytes (giảm khoảng74.2%), data77121107/19909668, predictions21580188/5004656. ObservedRSS610897920/505466880, scratch61220686/33493964, working96323171/25616163bytes; sampling100ms/sampling_errors0, không phải peak chính xác. SQL256MiB/threads2,120000aggregate/20000events; ETLS01-S04 và đónggói7constantpredictionhelpers, zero estimatorfits, không phải fullS08/S10/PUBG/CUDA. JSON tại pubg-normalized-benchmark-v1vs9kd9 và pubg-normalized-benchmark-o07absc3 trong Temp; kết quả và hash được ghi bền trong artifacts/pubg_storage_acceptance_20261020.json.
- Đo helper120000rows: cùngCSVbytes, ETLS01-S04 và đónggói7constantpredictionhelpers, không fitmodel/toànS08/S10/PUBG/CUDA. Lần đầu materialized/normalized completed30.909s/19.087s, finalproject99371515/25598865bytes, data77091005/19896826, predictions21580188/5004656. ObservedRSS609509376/481726464, scratch66677393/33493915bytes, sampled100ms lowerbound/sampling_errors0. JSON C:/Users/TT/AppData/Local/Temp/pubg-normalized-benchmark-j9ouoibv/benchmark.json và pubg-normalized-benchmark-9e__5m_m/benchmark.json. Có tiến trình tests chiaCPU/disk; không suy tốcđộ/tỷlệra67triệu hoặc peak chính xác. Script artifacts/pubg_normalized_benchmark.py, parseralias time nháp đã sửa ASquoted, không dùng lượt lỗi làm pass; đo lại freeze cuối sẽ ghi riêng.
- Giới hạn: JOIN lại có thể tăngCPU/I/O; physical Parquet không còn là fulllogicaltable, phải giữ recipe/inputs hoặc pool khi handoff. FullKMeans/OLS vẫn cần host/VRAM; không sample/SGD/Minibatch/distributedsolver hoặc tăngbudget để gọifull. ActualKaggleT4x2/fullsource/19.5GiB/savedVersion chưa nghiệmthu. Đường reuseS01 không áp dụng code khác/source hoặc software khác; không thaychecksum/status bằngtay. BackupCOPYgói5.10 trướcđổi tại PUBG_notebook_backups/kaggle_code_5.10_before_normalized_20261020.zip, SHA6c997ad501ff4b7816d9c613baae2996d8d175dcc8cf5645a8d0346442764d66.

### 18. Notebook Colab Pro riêng, người dùng yêu cầu ngày20/10

- Phạm vi: thêm notebooks/PUBG_COURSEWORK_COLAB.ipynb, ngoại lệ một notebook được yêu cầu rõ; canonical Kaggle và toàn src/config/requirements giữ nguyên bytes. tools/build_colab_notebook.py tái dùng S01-S10/formulas/OPTIONS canonical, tools/colab_runtime.py chỉ adapter setup/download/Drive/config/read-back, không đổi RQ/cohort/feature/target/matchsplit/leakage/KMeans/OLS/metrics/G4/float64. MộtGPU0 chạy các fit độc lập tuần tự; không fallback CPU hoặc yêu cầu haiT4.
- Đóng kèm 15file (12src/config/requirements/SPEC), ZIP/base64 có hash/allowlist/checkpath/không ghi đè code khác, không raw/outputs/secrets. Kagglehub1.0.2 tải handle versions/3, cache local, không dataset_load/latest; auth chỉ khi cần qua Secrets/login, không in token. Installer kiểm Linux/nvidia-smi/toolkitfamily; cố định cuML/cuDF26.2.* và CuPy>=13.6/<14 đúngcu12/cu13, cùngtransaction yêu cầu CPU/GPU; đổi thư viện dừng yêu cầu restart session, không kill/delete VM. Đối chiếu metadata PyPI phát hiện26.10 yêu cầu pandas3 xung đột core<3, đã bỏ fallback đó trước bàn giao;26.2 yêu cầu pandas>=2/<2.4 giao core>=2.2/<3, không đổi requirementscore. Đây là kiểm metadata, chưa cài resolverLinux thật.
- Project/checkpoint mặc định trực tiếp Drive namespaceColab riêng; raw/cache/SQL/spill/matrices ở runtime, không copy project mỗi stage. Dự phòng55GiB local trước tải, yêu cầu tự kiểm quotaDrive khoảng25GiB; vẫn guardoutput18GiB/SQL2GB/threads2/batch50000, không bảo đảm toànnguồn vừa. Drive có thể chậm hoặc bịquota/I/O. Không dùng Colab Pro như bằng chứng đủ GPU/RAM/Drive/runtime vô hạn.
- Resume kiểm completed với candidateconfig/source/software trước thay config, không ép trạng thái; lock/takeover và stage dở như core. HandoffColab dùng platform riêng, không giả owner/notebook/versionKaggle; đọc mountedfile không xác nhận remotecloudsync. report_only bỏ cài/giải nén/raw/download/copy/build/train/ghi project; chỉ mount cần thiết để đọc release/code/môi trường đã chuẩn bị.
- Kiểm tập trung6/6 đạt74.479s trước pinKagglehub1.0.2 và chuyển vị trí mụcSPEC. Actualcells S01-S10/10completed, chạy lại modelhash không đổi, report_only treehash không ghi; externalpip/GPU/download/Drive được giả lậpCPU và nguồn nhỏ3modes, không là actualColab/CUDA/fullPUBG. Lượt nháp đầu phát hiện thiếu SPEC trong gói nhúng tại S10: đã bổ sung file phụ thuộc thật, không bỏ kiểm finalization; không tính lượt lỗi là pass. Fullregression cuối và hash sẽ ghi nối.
- Kiểm bản cuối106/106 đạt trên bốn tiến trình unittest độc lập, không phải một lượt serial106tests: a30tests78.990s, b26tests171.651s, c21tests103.362s, d29tests171.208s, exit0/cả bốnOK. Log artifacts/pubg_colab_regression_final_{a,b,c,d}_20261020.log. Bộ trước pinGPU26.2 cũng106/106, nhưng không dùng lượt đó thay kiểm cuối. Nhóm b gồm6testColab, toàn10stage/chạy lại modelhash/report_onlytreehash, package15file/canonical AST/config/sourcepreservation và install/version/pin/cache/quota/authguards. Tất cả106IDdiscover được đối chiếu không trùng/thiếu khi chốt; actualColab/GPU/Drive chưa được chứng minh.
- Metadata chính thức PyPI ghi tại artifacts/pubg_colab_dependency_metadata_20261020.json cho cuML/cuDF26.2.0 haifamily, CuPy13.6.0 và cuDF26.10.0 bị từ chối. Có giao constraints pandas2.2-2.3/NumPy2/PyArrow18-23/sklearn>=1.5; chưa phải chạy pipresolverLinux hoặc CUDAimport thật. Không thay core requirements để né xung đột.
- Điểm tiếp tục: bàn giao notebook tự chứa và chạy S00 trênColab thật, kiểm GPU/môi trường/Drivequota/auth trước tải nguồn; actualColabGPU/Drive/quota/pipresolver/rawdownload/fullsource vẫn cần evidence riêng. Chỉ chốt triển khai và localacceptance, không gọi nghiên cứu/actualcloud hoàn thành. Không tự đăng nhập/tải18.9GiB/mountDrive/upload hoặc xóa dữ liệu tài khoản trong lượt local. Hash/packageQA/evidence được ghi nối haiCHANGELOG và artifacts/pubg_colab_acceptance_20261020.json.

### 19. Tiếp tục Version4 CPU bằng GPU, ngày21/10/2026

Ghi chú đính chính nối tiếp ngày21/10: xem mục20 sau lỗi S07 thực. Quy tắc11module byte-identical bên dưới mô tả buildbe2284cd trước đó; build mới chỉ thêm ngoại lệ analysis.py được pinSHA và kiểm AST cho các hàm profile S07, không thay S01-S06.

- Yêu cầu: sửa lỗi strict software khi chỉ bổ sung cuML/CuPy, giữ nguyên S01-S06 đã lưu và không tính lại. Đối chiếu SPECX/XXII/XXIV và kế hoạch import/restore/D6. Chỉ đổi cơ chế compatibility/checkpoint/bootstrap và tài liệu, không mục tiêu nghiên cứu hoặc solver/cohort/split/metrics.
- src/kaggle_runtime.py thêm allowlist/policy producerCPU5.11 đóng băng4e3f9a19 và import tường minh: require gốc trong subprocess với CPU packages thực, full handoff/raw/code/config/signatures xác minh, staging/copy read-back, provenanceZIP/receipt và rebind sáu signature dưới current code/software. Bản gốc Input không ghi; working target mới/trống, writerlock/model/prediction/downstream/CPU/Python khác bị từ chối. restore_handoff không opt-in giữ kiểm strict cũ.
- tools/build_kaggle_notebook.py tái sinh cùng48cells/16code, mặc định resume Version4/S07-S07; bootstrap ưu tiên code cập nhật và truyền opt-in, runner kiểm RAM tại S07/S08. tools/build_colab_notebook.py cùng bundle nhúng/metadata tái sinh theo source cập nhật, không thêm migration Colab. requirements và các module tính toán không đổi. tests fixtures freeze code5.11 trước sửa; producer5.10 cũ giữ nguyên.
- tests/test_cpu_gpu_resume.py tạo S01-S06 thật bằng code5.11 đóng băng trên CSV synthetic, GPU chỉ metadata giả lập. Kiểm cả sáu stage reuse với callback cấm recompute, artifact bytehash, provenance, handoff/strict restore lần sau, base/Python/code/raw/model/partial/downstream/nonempty/diskfailure và source input không ghi. Lượt nháp5tests có4pass/1error vì test dùng trường run_id không có trong manifest; sửa oracle kiểm mọi trường gốc trừ signature/artifacts thay vì thêm trường giả vào production. Không tính lượt nháp là nghiệm thu.
- Nghiệm thu cuối/sourcehash/package/log và điểm tiếp tục sẽ được ghi nối sau kiểm. Chưa chạy CUDA/nhập Version4 thật/tài khoản/upload GitHub hoặc Kaggle; không tuyên bố hết vấn đề RAM/VRAM S07/S08 hoặc full-data hoàn tất. Sau local checks, người dùng cập nhật code Dataset và notebook, restart kernel để bỏ module cũ, giữ InputVersion4/rawVersion3 rồi chạy S00 để kiểm thực.
- Kết quả source freeze cuối be2284cda4030beafb99a8b63cca80e15b9de146ecb6a134911b3804471c1a6a:113/113 tests báo unittest OK trong bốn tiến trình độc lập a19/81.172s, b29/405.903s, c34/201.419s, d31/331.345s; không cộng thời gian thành thời gian tường hoặc gọi một lượt serial. Log artifacts/pubg_cpu_gpu_regression_final_{a,b,c,d}_20261021.log. Launcher PowerShell ghi stderr thành ErrorRecord và tool báo exit1 dù summary unittest OK; không dùng exitstatus đó để giả exit0. Lượt trước có lỗi ZIP chưa đồng bộ SPEC, đã tái đóng gói rồi kiểm lại đạt; không bỏ test hoặc tính lượt lỗi là pass.
- Hậu kiểm11/11 trong125.951s, artifacts/pubg_cpu_gpu_postchecks_20261021.log: bảy test nhậpCPU gồm thực thi S00/installer có kiểm/phòng raw đổi giữa copy/cấm recompute/provenance/strict resave và bốn kiểm gói/notebook. Bổ sung kiểm normalized player_match đủ240 unique rowIDs, profile S07 từ bản nhập bằng bản gốc theo tolerance1e-9/1e-10, không gọi lại producer. Local Windows/Python3.13.5/DuckDB1.5.5/PyArrow23.0.1; cuML26.2/CuPy14.0.1 chỉ metadata giả lập. Actual userVersion4/GPU/raw full chưa chạy.
- Thêm INSTALL_RESUME_ENVIRONMENT mặc định True chỉ chuẩn bị DuckDB đúng producer + nbclient/nbconvert/psutil trước import src; unit test kiểm không nâng CPU stack/GPU, bỏ qua khi phù hợp/report_only và chặn Python/DuckDB cached không tương thích. Mọi module src ngoài kaggle_runtime.py (11file) byte-identical producer4e3f9a19. Hai generator tái sinh trên bản copy đạt byte-deterministic; Kaggle48cells/16code, Colab50/18, không output, stableIDs. Code ZIP19file chỉ code/config/docs/notebook, không raw/data/outputs/secrets; CRC/member binding kiểm lại sau ghi kết quả nghiệm thu. Điểm tiếp tục: cập nhật riêng Dataset code và nội dung notebook, giữ Output Input Version4; S00 verify/copy có thể lâu do hash/decode nhiều GiB nhưng không compute S01-S06.

### 20. S07 profile theo khóa đầy đủ, sau lỗi thực ngày21/10/2026

- Yêu cầu sửa log S07 OOM tại analysis.profiles, không tính lại S01-S06. Đối chiếu SPEC V/VI/X/XIX/XXII/XXIV/XXV và PLAN NEW05/OOC07/12.3/12.6/12.8. RQ/cohort/features/targets/matchsplit/leakage/minimumgames/K/seeds/estimators/metrics/precision/full-data giữ nguyên; thay thực thi SQL và compatibility đích có provenance.
- src/analysis.py tách profile_query giữ công thức cũ; profiles COPY projection một lượt sang32bucket SHA256player-mode, GROUP BY từngbucket với1SQLthread/8openfiles, restore connectionsettings/cleanup; bounded_profiles bỏ lượt fullGROUPBYđếm lặp, guard tổngprofile trước collect từngphần. Không fitpartition/meanofmeans hoặc lấy mẫu. Disk join/spill/finalprofile/fullfit vẫn có giới hạn; không tăngSQL2GB/budget18GiB hoặc giả dự toán17GiB là cấp phátSQL.
- src/kaggle_runtime.py chấp nhận đúng analysis.pySHA1378b2ff27abe1438fe32185de073adc027377e1ca529a2dbd9a4d2862b3c6b1, AST ngoài3hàmprofiles/bounded_profiles/profile_query phải giống frozenproducer4e3f9a19. Các module khác ngoài runtime vẫnbyte-identical. Verifier gốc/CPUsoftware/rawhash/provenance/importguard giữ nguyên. Không nhận tùyý sửaanalysis hoặc reuseS07cũ.
- tools/build_kaggle_notebook.py mặc định rootmới v511_S07_profiles, vẫnVersion4/S07-S07/autoenv/GPU; Colabgenerator cùnggói nhúng tái sinh theo sourceb663bd7528cd4bd0be7a64bb03f88e07f5c97418b340ba09626853691af602a0, không sửa adapter hoặc thêm migrator. README và cảhaiCHANGELOG cập nhật; oldZIP được copy vào PUBG_notebook_backups/kaggle_code_5.11_before_s07_profiles_20261021.zip, SHA88901ef9dea92121cb076fd2e49e8b94e0126d2123e836d284faf345a8d42149.
- tests/test_profile_partitions.py4/4 đạt42.208s: synthetic540000rows/180000profile, SQL64MiB, oldGROUPBYOOM/newpass đầyđủ180000keys/counts/null/schema/floatparity1e-9/1e-10; Unicode, empty, null, full/development/test-only/outcome scope, normalizedviews, cleanup/failure/connectionsettings. tests/test_analysis_models.py7/7 đạt66.932s gồm fullchain/reload/leakage/conditionalmeans. Không tính đây là actualGPU/PUBG, không có sửa fileInput/cấp quyềntài khoản hoặc Gitpush. Hồi quy đầyđủ/package/sourcefreeze sẽ ghi nối khi kếtthúc.
- Nghiệm thu sourcefreeze b663bd75:117/117tests đạt trong bốn tiến trình độc lập exit0 (nhóm0:32/245.675s,1:30/199.766s,2:32/193.208s,3:23/251.511s), artifacts/pubg_s07_profiles_regression_{0,1,2,3}_20261021.log. Đây không phải một lượt serial hoặc thời gian tổng cộng. Mọi test có sẵn113 và4profiletests mới đều đã chạy trên source cuối; không cộng các lượt kiểm banđầu thành testsunique.
- Sau discover hồi quy, thêm đúng một test actualnotebook S07-only mới:1/1 đạt37.908s, artifacts/pubg_s07_resume_notebook_20261021.log. Notebook canonical chạy toàn bộ cells trong kernel mới trên frozenCPUfixture; callback chặn mọi stage ngoàiS07, đủS01-S07completed, upstreamproducer_import signatures và nguồnInputtreehash nguyên, S08-S10 không gọi. Tổng118testunique được phủ bởi117suite và1testbổsung; không gọi là một lần fullsuite118. CPUfixture không actualCUDA.
- Đónggói kiểm19ZIPmembers/CRC/allbytes; config/requirements cùng10module khácanalysis/runtime byte-identical frozenCPUproducer; hai notebook schema/nooutputs/sourcebinding và generators được kiểm riêng sau cập nhật tài liệu nghiệm thu. Chỉ6entry trong codeZIP thay so vớibe2284cd:analysis/runtime/notebook/README/SPEC/PLAN. Người dùng cập nhật cảcodeDatasetvànotebook, giữ OutputInputVersion4/rawVersion3 và chọnT4x2. Save&RunAll khởi tạo/khôi phục lại trong phiên sạch nhưng chỉ computeS07; không xóaworkingcũ hoặc nângmemory để né lỗi. ActualKaggle/PUBG/VRAM/scratchquota vẫn mở.

### 21. S08 TSQR toàn train và giữ Version6, ngày21/10/2026

- Yêu cầu mới cho phép solver chia khối, không chạy lại S01-S07/không thay kết quả cũ. Đối chiếu SPEC VII/X/XIV/XVIII/XXII/XXIV/XXV và bổ sung XXVI; đây là quyết định solver/preprocessing implementation được người dùng duyệt, không coi là I/O thuần túy. RQ/cohort/features/targets/split/leakage/estimators mục tiêu/bảy fit/G4/metrics/KMeans/float64 giữ nguyên. Version6 Successful/S01-S07completed/full đã đọc UI; source b663bd75 được đóng băng tại tests/fixtures/audited_s07_producer_511.zip trước sửa.
- src/modeling.py thêm global-train imputer/scaler, TSQR augmented float64 trên tối đa50000dòng, SVD nhỏ/rank cutoff theo số hàng gốc, baseline statistics/globalexternalquantiles. Giữ nhánh dense, chọn tsqr tường minh cho project mới nhập. Resource guard/cache/model metadata có solver; dự toán bounded thay full-matrix vì thực thi đã đổi, không bỏ guard. GPUworker/testpredict/publish/metrics/G4 giữ cùng luồng, S00 kiểm TSQR thật trên48dòng mỗi GPU.
- src/kaggle_runtime.py thêm đường nhập S07 có kiểm producer source/requirements/software/exactprefix/artifacts/raw/KMeans/AST và staging atomic, lưu archive+receipt/chữ ký gốc/recomputedFalse, không giả chữ ký producer. Giữ CPU-import cũ qua pin modeling mới S08-only, không ảnh hưởng S01-S06 hoặc nhập S07 tùy ý. Root S08 mới, InputVersion6 bất biến, mọi src ngoài hai module trên không đổi byte so b663bd75.
- Generator Kaggle mặc định S08-S08/Version6/ALLOW_S07_TSQR_RESUME=True/CPUimportFalse; cần Dataset code mới cùng notebook. Colab tái sinh bundle source đồng bộ, không bật TSQR cho checkpoint Colab hoặc tự migrate môi trường. README cập nhật đầy đủ quy trình an toàn; nhật ký cảhai project nối tiếp. Backupgói cũ PUBG_notebook_backups/kaggle_code_5.11_before_s08_tsqr_20261021.zip/SHA78a7cd9f76a2a71fec3234673504addbd197abfdb6a42555b89ae53f60d34f1e.
- Kiểm ban đầu test_tsqr5/5 đạt17.837s, test_s07_tsqr_resume4/4 đạt43.336s: denseparity>100000dòng/globalmean/median/indicator/scaler/rank/reload/sevenfits/G4, frozenproducerb663S01-S07thật trênfixture, actualnotebookS08-only với callbackcấmupstream, giữ mọi artifact/model/hash/history/sourceInputtree, strictresave/restore và failurecases. Lượt đầu3errors do estimator thiếu API fit, đã sửa đúng giao diện và kiểm lại; không tính lượt lỗi là pass. Đây là CPUfixture Windows, không actualCUDA/fullPUBG. Hồi quy/đónggói cuối sẽ ghi nối sau kiểm.
- Nghiệm thu sourcefreeze652e4f8903cfcf296c3496835185bcf23d54ef1d8af428bf2ebbb209b5f4bf71:128/128testunique đã được phủ, đối chiếu IDdiscover không trùng/thiếu. Bốn tiến trình độc lập exit0: nhóm0_final39tests204.525s, nhóm1:30/130.512s, nhóm2:32/123.194s, nhóm3:27/221.732s; logs artifacts/pubg_tsqr_regression_{0_final,1,2,3}_20261021.log. Không cộng thời gian thành thời gian tường hoặc gọi một lượt serial128. Nhóm0 ban đầu có2errors: fakeCuPy cũ thiếu API QR và testgenericresume chưa tắt opt-inmới. Bổ sung numpy-backedmock được ghi CPU-TEST-NOT-CUDA, override profile riêng trong test; không bỏ GPU smoke/guard production. Chạy lại cả nhóm39 đạt, không tính lượt lỗi là đạt.
- test_tsqr hiện6tests gồm manualG4 pending chưa có testpredictions, sau duyệt reuse đủmodelhash và callbackcấmrefit; actualQRshapes không vượt50000dòng và SVD nhỏ, originaldimensionscutoff. test_s07_tsqr_resume4tests gồm raw đổi giữa copy bị chặn/no-target, originalsource/model/artifacthash giữnguyên. Hậu kiểm artifacts/pubg_tsqr_acceptance_20261021.py xác minh10module src khácmodeling/runtime cùng config/requirements byte-identical b663;15hàm modeling cũ ngoài fitguard/fitcandidate/_prediction cùngAST. Notebook48/16 và Colab50/18, stableIDs/nooutputs/compile/schema, sourcepin/paramsS08/Version6, generators byte-deterministic, ZIP19CRC/allmemberbytes và gói Colab15file binding khớp.
- Dự toán chỉ phầnfitTSQR ở47158595dòng: S1host0.667/VRAM1.167GiB, P2host0.738/VRAM1.238, T0host0.631/VRAM1.131; chưa tính chung mọi consumer như một đo peak, dự toán validation và tổngworker vẫn kiểm riêng. Không suy đủ CUDA/time/scratchquota/fullPUBG từ những số này. Bàn giao local; cần cập nhật cả codeDataset/notebook, OutputInputVersion6/rawVersion3, T4x2 và S00QRsmoke thật. Không upload/push/đụng Version6; kết quả researchS08/S09/S10 thực còn mở.

### 22. Sửa GPU smoke CuPy where, ngày22/10/2026

- Yêu cầu tiếp nối log S00 GPU0 TypeError Wrong arguments {'where': ...}. Đối chiếu SPEC VII/X/XXVI và PLAN XII.21, ghi thêm SPECXXVII. Đây là sửa API vận hành, không đổi mục tiêu/cohort/features/target/split/leakage/OLS/rankcutoff/metrics/G4/checkpointproducer. Không nâng/hạ CuPy, bỏ guard hoặc chạy lại S01-S07.
- modeling.py đổi đúng phép masked divide sang boolean indexing, không chia singular values bị loại. kaggle_runtime.py chỉ cập nhật pin module đã kiểm. Generator/notebook Kaggle dùng root cupyfix mới để tránh root cũ có sourcehash khác; giữ Version6/S08-only. Colab sync bundle/pin, không migrate checkpoint cũ. README và hai journal nối tiếp, không sửa lịch sử. BackupZIPtrướcđổi tại PUBG_notebook_backups/kaggle_code_5.11_before_cupy_where_20261022.zip/SHA142c27d3de50cbe4f743e3cf2213ecf0c2cfa159f808ea8e34c9357166ce9c97.
- Test mới test_tsqr.test_cuda_backend_without_divide_where_handles_full_and_zero_rank tái hiện đúng TypeError trên code cũ ở3case, không tính lượt lỗi là pass. Sau sửa kiểm cùngngưỡng/sốthực/full/zero/deficient-rank, test_gpu fakeCuPy không còn mượn divide cho phép where từ NumPy. Kiểm hồi quy, packaging và actualnotebook/no-upstream-recompute sẽ ghi nối. Không đụng Input/Kaggle thật; actualGPU smoke sau sửa vẫn mở.
- Nghiệm thu sourcea73054d6:129/129testunique đạt, bốn tiến trình độc lập exit0:40tests354.650s,30/248.895s,32/246.877s,27/371.127s. Logs artifacts/pubg_cupy_where_regression_{0,1,2,3}_20261022.log; không cộngthờigian hay tests lặp. Có actualnotebookS08-only/callbackcấmupstream/frozenproducer/raw/mọiartifact và model/Inputtreehashgiữnguyên, manualG4/reload/singular/full/zero-rank/workerisolation/noCPUfallback. Testmớifailtrướcsửa3subcase, passsaụsửa0.070s; đây là CPU/API simulation, khôngactualCUDA. artifacts/pubg_cupy_where_acceptance_20261022.py/.json kiểm scope2dòng+pin so backup,10module/config/requirementsbyte-identical,129IDcoverage, notebooks/sourcepin/root/Version6/nooutputs/compile, generatorbyte-determinism, ZIP19/Colab15CRC/memberbytes. Bàn giao rootcupyfix riêng trong phiên sạch, vẫnS08only/Version6; khôngupdatecloud hoặc xóa working cũ. ActualT4/fullsource/time/scratch còn mở.

### 23. S08 matrix projection + external sort riêng, ngày22/10/2026

- Yêu cầu: người dùng cho phép sửa theo cách hợp lý sau log S08 DuckDBOOM tại matrix_data train JOIN+ORDER BY. Đối chiếu SPEC VII/X/XVIII/XXII/XXVI/XXVII, thêmXXVIII và PLAN OOC08/XII.21-22. Không đổi protocol/estimator/cohort/features/target/split/leakage/globalorder/float64/rank/G4/metrics hoặc tính lại S01-S07.
- src/modeling.py thêm wrapper COPY projection khôngsort một luồng, rowgroup8192, restorethreads; disk_db mới một luồng chỉ đọc projection rồi dùng nguyên thân matrix builder cũ đổi tên _matrix_data. Không increase SQL2GB/budget18GiB hoặc đọc hết dataframe. Projection tạm thuộc thư mục riêng trong runtimework, đóngscan/reader/mmap rồi dọn; chỉ thêm một file projection mỗi matrix, không checkpoint/outputcũ. Cần thêm scratchdisk/I/O, nativeerror vẫn dừng nếu không đủ; không chắc chắn whole-source.
- kaggle_runtime.py chỉ pinmodeling84dbb3e2ff7a2afc2e5062c7710618068a37ac767e1a664e497b3e369f62ce47, sourcea2f7ecff1a39245dc2313993d2b4dc05e5c45efc72a3ec6f5b9ffb252a486d71. GeneratorKaggle rootmới PUBG_Coursework_v511_S08_matrixdisk, vẫnVersion6/S08-only/smoke; Colab sync sourcebundle, không migrate. README/SPEC/journals nối tiếp. BackupZIP8f379d87cf45e9761695afa31ef05bbdc77b2da95538d818ab27d4474c5cfb56 giữ tại PUBG_notebook_backups/kaggle_code_5.11_before_matrix_disk_20261022.zip.
- tests/test_matrix_disk.py3tests: kiểm1.2triệu hàng/128MiBSQL/querycũJOIN+sortOOM/cáchmớipass/toànX/y/key/target/counts, Unicode/negativezero/Arrow-schema/order/copy-no-sort/freshscan-no-JOIN/threadscope, failurecleanup/sourcehash/unrelatedfile. Focused3/3 đạt26.567s trước bổ sung assertionghiCOPY; sẽ kiểm lại bản cuối trong suite. Lượt64MiB COPYfail cảrowgroup50000/8192, không nhận64MiB làpass; control banđầu gọi cảhàm cũ thấtbạitừstatsquery, đã sửa testoracle gọi đúngSELECT+ORDERBY như log, không nới độ chính xác hay đổi code để che lỗi. Fullregression/no-upstream-recompute/package cuối sẽ ghi nối. ActualGPU/PUBG/time/scratch/savedS08 còn mở.
- Nghiệm thu sourcefreeze a2f7ecff1a39245dc2313993d2b4dc05e5c45efc72a3ec6f5b9ffb252a486d71:132/132testunique đủIDdiscover, bốn tiến trình exit0: nhóm0 34/292.867s, nhóm1 44/223.284s, nhóm2_final26/195.404s, nhóm3 28/159.712s; log artifacts/pubg_matrix_disk_regression_{0,1,2_final,3}_20261022.log. Không cộng thời gian hoặc lượt nháp. Nhóm2 đầu26 có1error ở cađốichứng cũ: OOM từArrowreader được bọcOSError thay vìduckdb.OutOfMemoryException; sửa oracle nhận đúng hai kiểu với messageOutOfMemory, không bỏ lỗi/newpath/tolerance. Chạy lại cả26 đạt. Fullparity/actualnotebook S08only/no-upstreamcompute/mọioldInput/model/artifactbytehash/normalizedlayouts/G4/TSQR/CuPycompat/release-readonly đều đạt trênCPUfixture, khôngactualT4.
- QA artifacts/pubg_matrix_disk_acceptance_20261022.py/.json đối chiếu backup8f379d87: nguyên thân builder cũ chỉ đổi tên _matrix_data, mọi modeling definition khác cùngAST; runtime chỉ pin đổi,10module/config/requirements byte-identical. Kiểmnewsourcepin/rootVersion6/S08scope/nooutputs/stableIDs/compile/schema, CRC vàeverymember19ZIP/15Colab, generators byte-deterministic vàcoverage132. Cần nghiệm thu S08fullPUBG/SQL2GB/T4x2/scratch/time/savedVersion riêng, không suy từfixture128MiB. Gói mới và notebook phảiupdatecùngnhau, rootmatrixdisk mới/phiênsạch, giữ InputVersion6/rawVersion3, khôngxóa/ghiđèworkingfailed hoặccomputeS01-S07.



