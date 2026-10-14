# Dự án nghiên cứu hành vi người chơi PUBG

Hướng dẫn dành cho thành viên nhóm: chuẩn bị môi trường, chạy notebook nối tiếp, đọc kết quả, lưu trên Drive và bàn giao cho người tiếp theo.

Cập nhật: 14/10/2026. README mô tả cấu trúc và cấu hình hiện có; không chứng nhận toàn bộ dự án đã chạy thành công trên dữ liệu thật. Trạng thái thực phải đọc từ checkpoint, manifest và output của đúng lần chạy.

## I. Thành viên mới bắt đầu từ đâu?

1. Đọc mục II để hiểu bài toán, phạm vi và giới hạn nghiên cứu.
2. Thiết lập đúng Drive chung theo mục V. Không tạo bản sao riêng nếu muốn chạy nối tiếp.
3. Xem mục VII và VIII: notebook cần CPU/GPU, đầu vào và điều kiện bàn giao.
4. Xác nhận người trước đã commit stage và artifact hợp lệ, không chỉ tạo file.
5. Chạy cấu hình, bootstrap, khởi tạo và các cell nghiệp vụ theo thứ tự.
6. Nếu lỗi hoặc bị chặn nghiên cứu, xem mục XIV; không bỏ cell đỏ để chạy cell cuối.
7. Hoàn tất thì kiểm đầu ra, lưu notebook có output và bàn giao theo mục X.

Trong mọi notebook Colab của nhóm, giữ:

~~~python
PUBG_STORAGE_MODE = "drive"
PUBG_DRIVE_PROJECT_ROOT = "/content/drive/MyDrive/PUBG_Project/Project_PUBG"
PUBG_REQUIRE_EXISTING_PROJECT = True
PUBG_BATCH_ROWS = 50000
~~~

Không chạy notebook All-in-One. Dự án chạy riêng từng notebook 00-12, không cần khôi phục hoặc tạo notebook tổng hợp.

Tra nhanh: [Drive](#v-chuẩn-bị-drive-chung-và-bản-triển-khai-gọn), [CPU/GPU](#vii-cpu-và-gpu), [thứ tự notebook](#viii-thứ-tự-và-điều-kiện-hoàn-thành), [vị trí kết quả](#ix-kết-quả-lưu-ở-đâu), [bàn giao](#x-phân-công-và-bàn-giao), [xử lý lỗi](#xiv-xử-lý-lỗi-thường-gặp), [kiểm thử local](#xviii-kiểm-thử-local).

Tài liệu đọc sâu hơn:

- [PUBG_RESEARCH_SPEC.md](PUBG_RESEARCH_SPEC.md): đặc tả nghiên cứu, công thức và giới hạn.
- [PUBG_IMPLEMENTATION_PLAN.md](PUBG_IMPLEMENTATION_PLAN.md): kế hoạch hiện hành và bằng chứng nghiệm thu.
- [TEAM_DRIVE.md](TEAM_DRIVE.md): thư mục chung, shortcut và bàn giao.
- [NOTEBOOK_CELL_GUIDE.md](NOTEBOOK_CELL_GUIDE.md): bản đồ cell, tiêu đề và cách đọc.
- [GPU_PER_MODE_GUIDE.md](GPU_PER_MODE_GUIDE.md): backend, GPU và giới hạn.
- [AGENTS.md](AGENTS.md): quy tắc sửa dự án.
- [Literature mapping](reports/appendix/literature_mapping.md): truy vết tài liệu học thuật.

README không thay thế đặc tả. Nếu tài liệu cũ và cấu hình hiện tại khác nhau, đối chiếu quyết định có bằng chứng và checkpoint, không chọn cách dễ chạy tiếp nhất. Theo yêu cầu hiện tại, đợt viết README không khôi phục hoặc ghi thêm nhật ký lịch sử đã xóa.

Các từ thường gặp:

| Từ | Hiểu ngắn gọn |
| --- | --- |
| Bootstrap | Cell chuẩn bị import, môi trường, đường dẫn và gắn Drive; NB12 có bootstrap chỉ đọc riêng |
| Artifact | File đầu ra: dataset, model, bảng, hình hoặc metadata |
| Manifest | File ghi danh sách, đường dẫn, phiên bản và trạng thái artifact |
| Commit stage | Ghi nhận hoàn tất sau khi kiểm tra đầu ra; khác việc vừa tạo tên file |
| Cohort | Tập quan sát đủ điều kiện cho một phân tích/thí nghiệm |
| Scope | Phạm vi kết quả: fixture, development, dữ liệu thật, mode hoặc split cụ thể |
| Fixture | Dữ liệu nhỏ tạo để kiểm thử, không phải kết quả nghiên cứu PUBG |
| Receipt | Bản ghi quyết định/kiểm chứng, giúp truy vết lý do và tính tương thích |
| Checksum/hash | Dấu vết nội dung file dùng đối soát; không thay kiểm tra dữ liệu giải nén đọc được |

## II. Mục tiêu nghiên cứu

Dữ liệu gồm thống kê sau trận và sự kiện hạ gục/bị hạ trong PUBG. Dự án phân tích liên hệ giữa hành vi, thời gian sống sót và thứ hạng; phân nhóm người chơi; xây dựng mô hình có kiểm soát rò rỉ dữ liệu.

| Câu hỏi | Đơn vị phân tích | Nội dung | Notebook |
| --- | --- | --- | --- |
| RQ1 | Người chơi trong một trận, hay player-match | Hành vi nào liên hệ với survival/placement? | 05, 06 |
| RQ2 | Hồ sơ người chơi trong từng mode | Có những nhóm hành vi nào và outcome quan sát của chúng khác nhau thế nào? | 07 |
| RQ3 | Player-match hoặc lịch sử trước trận | Dự đoán survival và placement bằng hành vi hiện tại hoặc quá khứ | 08, 09, 10 |

Combat Timing là phần mở rộng chính: dùng event time để tạo thời điểm kill đầu tiên, trung bình và counts/ratios theo pha.

Cần phân biệt:

- Hồi cứu: dùng thống kê của chính trận đã xảy ra để mô hình hóa outcome trận đó; không gọi là dự đoán trước trận.
- Dự đoán lịch sử: chỉ dùng thông tin sẵn sàng trước trận hiện tại; phải có chronology và availability hợp lệ.

Dữ liệu quan sát không chứng minh nhân quả. Viết "liên hệ với" hoặc "cung cấp thông tin dự đoán", không viết "hành vi này gây ra chiến thắng".

Không tự mở rộng core sang deep learning, classification Top-N, ranking, association rules, spatial mining hoặc causal inference.

## III. Dataset và cấu trúc thư mục

Dataset cấu hình: PUBG Match Deaths and Statistics, slug `skihikingkevin/pubg-match-deaths`, phiên bản 3. Nguồn/license/checksum nằm trong `configs/data.yaml`.

Hai nhóm:

- `agg_match_stats*.csv`: thống kê player-match, gồm kills, damage, movement, assists, survival, team và placement.
- `kill_match_stats*.csv`: event-level, gồm match, time, killer, victim và các trường nguồn khác.

Hai nhóm không có nghĩa hai file. NB01 phải kiểm kê và xử lý đủ mọi shard (phân đoạn dữ liệu).

~~~text
Project_PUBG/
  README.md
  PUBG_RESEARCH_SPEC.md
  PUBG_IMPLEMENTATION_PLAN.md
  requirements.txt
  configs/
  notebooks/
  src/
    data/
    features/
    analysis/
    models/
    evaluation/
    utils/
  scripts/
  tests/
  data/
    raw/
    interim/
    processed/
  artifacts/
    checkpoints/
    experiments/
    manifests/
    models/
    metrics/
    logs/
  figures/
  reports/
    tables/
    appendix/
~~~

| Thành phần | Vai trò | Lưu ý |
| --- | --- | --- |
| `configs/` | Cấu hình và quyết định | Không tự thay ngưỡng/params đã duyệt |
| `notebooks/` | Điều phối, bảng/hình, hướng dẫn đọc | Chạy đúng thứ tự, lưu output |
| `src/` | Logic chuẩn | Notebook mới vẫn có thể import source cũ trên Drive |
| `scripts/` | Công cụ kiểm tra/vận hành | Không chạy mọi script chỉ vì tồn tại |
| `tests/` | Kiểm công thức, leakage, checkpoint trên dữ liệu nhỏ | Test không phải kết quả nghiên cứu |
| `data/raw/` | Nguồn khi sử dụng đường dẫn này | Không sửa/xóa raw để xử lý lỗi |
| `data/interim/` | Staging và dữ liệu trung gian | Có thể cần cho người chạy sau |
| `data/processed/` | Dataset phân tích/mô hình | Không thay bằng fixture local |
| `artifacts/` | Checkpoint, manifest, model, metrics, logs | Không phải toàn bộ đều là file tạm |
| `reports/tables/` | CSV/Parquet kết quả và kiểm toán | Nguồn đối chiếu số liệu báo cáo |
| `reports/appendix/` | Bằng chứng/quyết định/output nghiệm thu | Có thể chứa fixture, phải phân biệt |
| `figures/` | Biểu đồ | Giữ catalog và bảng nguồn đi kèm |

`raw_root` local có thể là `../Data_PUBG`; không cần sao chép CSV thêm vào `data/raw/`. Đường dẫn đã resolve trong `paths` và bảng đầu vào notebook là căn cứ vận hành.

### Scripts và tests có cần giữ?

Giữ cả hai trên máy/GitHub. Công cụ tiêu biểu:

- `scripts/run_phase15_tests.py`: runner local, loại hai bài thực thi All-in-One.
- `scripts/verify_notebooks_00_06.py`: kiểm cấu trúc/cú pháp 00-06, không kiểm dữ liệu thật.
- `scripts/smoke_test_00_06.py`: kiểm luồng nhỏ; đọc phạm vi trước khi chạy.
- `scripts/smoke_test_07_real.py`: có thể đọc dữ liệu thật, không là kiểm thử nhẹ mặc định.
- `scripts/repair_nb04_drive_source.py`: phục hồi theo một phiên bản/hash cụ thể; không chạy mù quáng trên source/config mới.
- `tests/test_*.py`: kiểm thử công thức, tình huống lỗi, leakage, publication và resume.

Bản Drive chạy thông thường có thể không cần công cụ local/output fixture. Giữ `tests/` nếu chạy kiểm thử GPU/logic trên Colab. Không lấy "untracked" làm tiêu chí file rác.

## IV. Cấu hình hiện hành

Bảng này là cấu hình trên máy tại ngày cập nhật; không chứng minh Drive đã đồng bộ hoặc production run đã hoàn tất.

| Nội dung | Giá trị/điều kiện hiện tại | Nguồn |
| --- | --- | --- |
| Storage nhóm | Drive, require-existing, batch 50.000 | Cell cấu hình |
| Runtime mode | `full` | `runtime.yaml` |
| DuckDB | 2 threads, giới hạn2 GB | `runtime.yaml` |
| Seed | 42 trong các cấu hình liên quan | Runtime/RQ2/RQ3 |
| RQ2 | `per_mode`, `device: cuda` | `rq2.yaml` |
| RQ3 | `device: cuda` | `rq3.yaml` |
| Split | Train0,70; validation0,15; test0,15 | `rq3.yaml` |
| Timing | Status/evidence cập nhật theo quyết định A ngày 08/10 | `features.yaml` |
| Min-games và K mỗi mode | Còn null; cần diagnostics | `rq2.yaml` |
| History threshold/protocol/availability | Còn pending/null | `rq3.yaml` |

Split ratios là tỷ lệ mục tiêu. Counts thực có thể không chính xác 70/15/15 vì phân chia theo match/time. Không tách lại player-row để ép tỷ lệ.

`mode: full` không tự mở gate, bảo đảm RAM hoặc biến fixture thành dữ liệu thật. Trong Drive mode, root/session storage được thiết lập bởi bootstrap. Không đọc riêng `storage_backend: local` trong YAML rồi kết luận Colab đang lưu local; kiểm `paths` thực được in ra.

## V. Chuẩn bị Drive chung và bản triển khai gọn

### 1. Thư mục nhóm

Khuyên dùng một chủ thư mục và shortcut cho các thành viên, không nhiều bản sao cùng tên.

~~~text
MyDrive/
  PUBG_Project/
    Project_PUBG/
      src/
      configs/
      notebooks/
      requirements.txt
      README.md
      data/
      artifacts/
      reports/
      figures/
    Data_PUBG.zip       # Chỉ khi chọn lưu ZIP ở Drive
~~~

Không bắt buộc upload cả ZIP và CSV giải nén. NB01 có thể đọc CSV trong ZIP theo batch; cấu hình nguồn nằm trong `data.yaml`.

| Nên có trong bản Drive | Không cần upload chỉ để chạy |
| --- | --- |
| Source/config/notebook đồng bộ | `.git/`, `.venv/`, cache |
| requirements và hướng dẫn nhóm | Output synthetic của nhiều lần kiểm thử |
| Dữ liệu/checkpoint/kết quả thật cần tiếp tục | Gói cập nhật mã nguồn cũ |
| Tests nếu kiểm GPU/logic trên Colab | Tài liệu môn học/dự án khác |
| Nguồn theo phương án download được cấu hình | Bản CSV giải nén thứ hai chỉ để khớp cây thư mục |

Không ghi đè các thư mục kết quả thật bằng folder local trống hoặc fixture.

### 2. Chia sẻ và shortcut

1. Chủ thư mục chia sẻ `PUBG_Project` cho từng thành viên quyền Editor.
2. Người nhận thêm shortcut của thư mục chung vào My Drive. Giữ tên `PUBG_Project` nếu phù hợp đường dẫn; nếu trùng tên thì xác định lại target.
3. Shortcut không tự cấp quyền vào nguồn: chủ thư mục phải cấp quyền cần thiết. Xem [hướng dẫn Drive](https://support.google.com/drive/answer/9700156?hl=en).
4. Thành viên mở Colab bằng tài khoản của mình, chạy cấu hình/bootstrap và kiểm root.
5. Kiểm file nhận diện chung; thử một file nhỏ để chủ thư mục xác nhận quyền đọc/ghi thực.

Tên đường dẫn giống nhau chưa chứng minh cùng folder Drive. `PUBG_REQUIRE_EXISTING_PROJECT=True` kiểm các file nhận diện như `configs/data.yaml` và `src/utils/config.py`, không xác minh Drive folder ID hay source đầy đủ. Một project vẫn có thể thiếu `combat_timing.py`.

## VI. Cách chạy một notebook

1. Mở file đúng phiên bản từ `notebooks/` bằng Colab.
2. Chọn runtime phù hợp trước khi xử lý dữ liệu.
3. Chạy cell storage với bốn giá trị đã chốt.
4. Chạy bootstrap: mount Drive, import/dependencies, resolve paths.
5. Chạy khởi tạo nghiệp vụ: config, input và dependency checkpoint.
6. Đọc Markdown trước mỗi khối; chạy code và đọc bảng/hình/thông báo.
7. Dừng tại lỗi hoặc pending; chỉ tiếp tục khi điều kiện thiếu được giải quyết.

Cell ID trong file, ví dụ `cell-009`, khác số đếm của giao diện. Phiên bản mới có thể đổi số cell; ưu tiên tiêu đề và traceback.

Run All không có nghĩa hoàn tất: NB07/NB08/NB09 có điểm đọc diagnostics/chốt quyết định/duyệt gate. Không bỏ cell lỗi.

### PUBG_WRITER_ID

Định danh phiên ghi, giúp tránh hai runtime cùng công bố một stage.

- Có thể để trống để hệ thống tạo runtime/process ID.
- Nếu đặt, dùng nhãn khác nhau từng phiên, ví dụ `thanhvien_b_nb04_phien_02`; không dùng chung cho hai runtime.
- Không là quyền Drive hay cơ chế lưu dữ liệu.
- Không sao ID người trước để vượt khóa.

### PUBG_FORCE_STAGE_TAKEOVER

Mặc định False. Chỉ bật sau khi xác nhận runtime cũ dừng và không ai còn ghi stage.

Cờ chỉ tiếp quản khóa writer; không sửa dependency chưa completed hoặc làm file dở hợp lệ. Sau khi bật có chủ đích, chạy cấu hình rồi khởi tạo; notebook có cơ chế reset sẽ trả về False. Không dùng takeover vượt integrity/research gate.

## VII. CPU và GPU

| Phần việc | Runtime phù hợp | Giới hạn |
| --- | --- | --- |
| 00-06 | CPU | DuckDB/Parquet/thống kê/I/O |
| 07 KMeans/diagnostics/C1/C3/C4 | GPU khi CUDA/cuML hoạt động | C2 Ward vẫn CPU supporting |
| 08 | CPU | History/chronology/leakage |
| 09 exact linear/OLS hỗ trợ | GPU khi cấu hình CUDA | Mean/median baselines CPU |
| 09 RF/HGB/SGD | Backend CPU ứng viên tương ứng | CUDA không hỗ trợ bị chặn, không fallback |
| 10 | CPU | Saved predictions/metrics/bootstrap/importance, không fit lại |
| 11-12 | CPU | Finalize/read-only report |

T4 không khiến mọi thư viện dùng GPU. VRAM là bộ nhớ thiết bị, khác host RAM; OOM DuckDB không được giải quyết chỉ bằng chọn T4.

Colab không bảo đảm GPU/tài nguyên cố định. Chọn GPU không chứng minh code dùng GPU: đọc backend/device/version thực. Xem [FAQ Colab](https://research.google.com/colaboratory/faq.html).

Kiểm GPU/backend trước bước đắt của 07/09. Không tự đổi device, OLS sang SGD hay KMeans sang MiniBatch trong cùng run; estimator/backend khác cần recipe và kiểm chứng riêng.

## VIII. Thứ tự và điều kiện hoàn thành

| File | Công việc | Kết quả chính/điều kiện bàn giao |
| --- | --- | --- |
| [00_setup.ipynb](notebooks/00_setup.ipynb) | Root/config/packages/storage/hardware/checkpoint | Môi trường đúng; không chứng nhận toàn bộ full run |
| [01_download_validate.ipynb](notebooks/01_download_validate.ipynb) | Đủ shards/hash/schema/parse | Staging và manifest hoàn tất, không chỉ ZIP tải xong |
| [02_data_quality_and_structure.ipynb](notebooks/02_data_quality_and_structure.ipynb) | Cleaning/roster/chronology/mode/split | Cleaned aggregate, metadata, split và audits hợp lệ |
| [03_build_player_match.ipynb](notebooks/03_build_player_match.ipynb) | Base features/target/dictionary | Base/parts/validation đọc được, invariant và final commit đạt |
| [04_combat_timing.ipynb](notebooks/04_combat_timing.ipynb) | Event aggregate/audit/safe merge | Timing/features/coverage, decision hợp lệ và final checkpoint completed |
| [05_eda.ipynb](notebooks/05_eda.ipynb) | EDA/catalog/mode/diagnostics | Bảng/hình có scope/source; quyết định không dùng final test |
| [06_rq1_analysis.ipynb](notebooks/06_rq1_analysis.ipynb) | Quan hệ hành vi/outcome | Coefficients/N/mode và cảnh báo target-derived |
| [07_rq2_clustering.ipynb](notebooks/07_rq2_clustering.ipynb) | Per-mode profiles/retention/K/C1-C5 | Assignments/centers/fitted artifacts/receipts, status từng mode/experiment |
| [08_build_historical.ipynb](notebooks/08_build_historical.ipynb) | Chronology/availability/depth/strict-past | Feasibility/status/dataset khi đủ điều kiện; Grade C blocked hợp lệ |
| [09_rq3_prediction.ipynb](notebooks/09_rq3_prediction.ipynb) | Models/validation/G4/final evaluation | Models/predictions/metrics, test chỉ sau gate đúng |
| [10_ablation_error_analysis.ipynb](notebooks/10_ablation_error_analysis.ipynb) | Saved prediction comparisons | T0/T1/ablation/errors/importance/CI trên cohort/recipe khớp |
| [11_finalize_results.ipynb](notebooks/11_finalize_results.ipynb) | Kiểm run/compatibility và khóa | Release/manifest cuối hợp lệ, không chọn file còn sót |
| [12_final_results_summary.ipynb](notebooks/12_final_results_summary.ipynb) | Đọc release cụ thể | 12 phần có nguồn/status/limitations, không tạo kết quả mới |

Luồng chính: nguồn/cleaning, base, timing/features, EDA/RQ1/RQ2/history, models, comparisons, release, summary. Dependency không luôn là duy nhất notebook liền trước; đọc kiểm tra khởi tạo.

Checkbox code/fixture không là nghiệm thu production. Synthetic, GPU mock hoặc mount mock không chứng minh full-data/GPU/Drive thật.

## IX. Kết quả lưu ở đâu?

Các đường dẫn dưới đây tính từ root Drive:

~~~text
/content/drive/MyDrive/PUBG_Project/Project_PUBG/
~~~

| Đường dẫn | Nội dung |
| --- | --- |
| `data/interim/staging_shards/` | Shard Parquet NB01 |
| `data/interim/cleaned_aggregate.parquet` | Aggregate sau cleaning |
| `data/interim/match_metadata.parquet` | Một dòng/trận, duration proxy và flags |
| `data/interim/split_assignments.parquet` | Split theo match |
| `data/interim/player_match_base.parquet` | Base NB03, chưa là timing/features cuối |
| `data/interim/combat_timing.parquet` | Timing NB04 theo match/killer |
| `data/processed/player_match_features.parquet` | Dataset sau merge NB04 |
| `data/processed/player_profile_features*.parquet` | Profiles RQ2, phân biệt development/full |
| `artifacts/checkpoints/checkpoint_manifest.json` | Stage/status/owner/dependencies/signatures/artifacts |
| `artifacts/manifests/source_inventory.json` | Nguồn/shard/schema/provenance |
| `artifacts/manifests/chronology_report.json` | Chronology report cho consumer |
| `artifacts/manifests/split_manifest.json` | Định nghĩa/phạm vi split |
| `artifacts/manifests/historical_status.json` | Historical built/pending/blocked |
| `artifacts/experiments/` | Runs, metadata và các artifact theo run |
| `artifacts/models/`, `artifacts/metrics/` | Models/metrics khi run sử dụng đường dẫn này |
| `reports/tables/` | Bảng DQ/EDA/RQ1/RQ2/RQ3/audits/comparisons |
| `reports/tables/rq2/<mode>/` | Output per-mode ở nhánh dùng cấu trúc này |
| `figures/` | Biểu đồ có nguồn/catalog/manifest |
| `artifacts/manifests/releases/<release_id>/` | Snapshot bất biến NB11 |

Đường dẫn in trong manifest/bảng bàn giao là căn cứ chính xác; không suy từ tên ví dụ. Predictions/models có thể nằm trong namespace experiment.

Bảng thường đọc trong `reports/tables/`:

- `feature_dictionary.csv`: công thức, nhóm, unit/missing semantics.
- `event_join_audit.csv`: event/joins/eligibility/research status.
- `event_validation_ledger.parquet`: từng event; không collect toàn bộ bằng pandas khi RAM thấp.
- `combat_duration_review_summary.csv` và `combat_duration_review_cases.parquet`: review duration, không tự động loại trận.
- `kill_discrepancy.csv`: đầy đủ player-match, sai lệch aggregate/event.
- `event_timing_coverage.csv`: coverage theo player-match.
- `rq1_relationship_summary.csv`: RQ1.
- `eda_figure_catalog.csv`, `eda_catalog_status.csv`, `rq2_figure_catalog.csv`: source/scope/sample/caption/status.

`/content/temp` chỉ thuộc runtime và có thể mất khi VM bị thu hồi. Không là dữ liệu đã bàn giao.

Notebook chứa code/ghi chú/output hiển thị, không thay Parquet/model/checkpoint. Tải .ipynb không có nghĩa tải đủ kết quả để chạy offline.

## X. Phân công và bàn giao

Ví dụ A chạy 00-02, B chạy 03-04, C chạy 05-07, thành viên khác chạy 08-12. Đây không là cho phép hai writer chạy song song trên dữ liệu chung.

Trước nhận việc:

- Kiểm đúng root/source/config phiên bản nhóm.
- Kiểm upstream completed và artifact còn hợp lệ.
- Xác nhận người trước không còn ghi stage/file mình dùng.
- Chọn runtime; biến Python/RAM không chuyển giữa notebook hoặc tài khoản.

Trước bàn giao:

- Cell kiểm tra/commit cuối chạy xong không lỗi.
- Status đúng notebook/stage, không chỉ diagnostics completed.
- File đọc được và người nhận thấy trên Drive, không chỉ tồn tại tên.
- Giữ hình cùng catalog/bảng nguồn.
- Lưu output; tải notebook đã chạy thành công về và cập nhật đúng bản `notebooks/` local/Drive.
- Không thay bản tốt bằng notebook lỗi hoặc template vừa regenerate chưa giữ output.
- Kết thúc phiên ghi trước khi người tiếp theo tiếp quản.

Mẫu tin nhắn nhóm, không yêu cầu tạo nhật ký lịch sử mới trong repository:

~~~text
Người chạy:
Notebook, phiên bản source/config:
Thời điểm hoàn tất:
Drive folder/link:
Stage/status trong checkpoint:
Cell cuối đã thành công:
Artifacts và đường dẫn:
Scope: fixture / development / dữ liệu thật của experiment
Runtime/backend/device:
Pending/blocked và lý do:
Người nhận, notebook tiếp theo:
~~~

## XI. Checkpoint và resume

Checkpoint không lưu toàn bộ RAM. Nó kiểm soát stage/status, signatures (dấu vết input/code/config), dependencies và artifact/checksum.

| Status | Ý nghĩa | Hành động |
| --- | --- | --- |
| planned/pending | Chưa làm hoặc thiếu quyết định | Đọc reason/diagnostics |
| running | Có owner, có thể còn chạy hoặc bị ngắt | Kiểm runtime trước takeover |
| completed | Đã commit | Vẫn kiểm compatibility/integrity trước reuse |
| failed | Xử lý lỗi hoặc bị ngắt có ghi nhận | Sửa nguyên nhân, init lại |
| resource_limited | Thiếu tài nguyên | Dừng, không ngầm giảm cohort |
| blocked | Dependency/decision chưa đạt | Giải quyết điều kiện, không ép status |
| stale | Cache không còn tương thích | Xác định producer/downstream cần tái tạo |

Thay source checksum/formula/config/split/allowlist/backend/dependency có thể làm cache stale. Một số signatures bao gồm nhiều file source/config nên phạm vi ảnh hưởng rộng hơn một file trực tiếp.

Không chỉnh manifest completed thủ công, xóa dependency, giả writer hoặc đổi tên để bypass.

Khi runtime ngắt:

1. Giữ dữ liệu/manifest đã commit; ghi cell/lỗi trong bàn giao.
2. Runtime hợp lệ mới chạy cấu hình/bootstrap/init.
3. Kiểm status/integrity để xác định reuse.
4. Shard/mode/experiment completed compatible có thể dùng lại theo cơ chế riêng; fit dở/file chưa commit phải làm lại phần tương ứng.
5. Không bảo đảm resume từng cell/batch/bước fit ở mọi notebook.

NB01 checkpoint theo shard, không theo mỗi50.000 dòng. Receipt/local copy có thể hỗ trợ retry cùng runtime; VM bị thu hồi có thể làm mất phần chưa publish.

Nếu NB04 báo NB03 chưa completed dù có base, kiểm `notebook/03_build_player_match.ipynb` trong manifest và output cell cuối. Xử lý dữ liệu xong chưa đủ, cần commit bàn giao. Không mặc định chạy lại toàn bộ NB03.

## XII. Combat Timing và quyết định A

Đọc [quyết định A ngày 08/10](reports/appendix/nb04_completion_review_2026-10-08/decision_A.md) cùng evidence trong `features.yaml`:

- Giữ credited-killer: killer có tên, không self-kill, match/time hợp lệ theo quy tắc hiện tại.
- Same-team/unknown-team vẫn có thể nằm trong counts; không gọi là confirmed enemy-only kills.
- 60 giây là quy ước đã khai báo, không là ngưỡng tối ưu duy nhất được chứng minh.
- Diễn giải giây dựa trên consistency audit, không phải tài liệu nguồn độc lập xác minh mọi case.
- Giữ/audit abnormal source values; không tự đổi đơn vị, thay max bằng median hoặc xóa 5 trận duration cực lớn.

Tên legacy `enemy_kill_eligibility_status` không cho phép diễn giải mọi event là kill đối phương. Đọc evidence, không chỉ `verified`.

Duration proxy là max survival trong match, không là thời lượng chính thức đo độc lập. Event vượt duration có thể giữ absolute timing nhưng không vào phase. Thiếu event không đồng nghĩa không kill; không tự fill first-kill-time bằng0.

Biên bản 08/10 xác nhận diagnostics tiếp tục, nhưng chưa xác nhận merge/final commit. Kiểm checkpoint thật trên Drive; README không suy NB04 completed từ biên bản.

Nếu RUN-04 còn xuất hiện, kiểm config/evidence đã được Drive đồng bộ và runtime đã nạp bản mới chưa. Không sao status từ fixture hoặc bỏ raise.

## XIII. Cách đọc kết quả

Trước trích số liệu, kiểm:

1. RQ/grain: event, player-match, match, team hay profile?
2. Scope: fixture, development, cohort thật hay final test?
3. N là số gì; n có phải sample; mẫu số tỷ lệ là gì?
4. Unit verified/accepted/candidate/pending?
5. Missing theo định nghĩa hay thiếu/lỗi nguồn; valid N?
6. Mode/split/seed/version và source khớp?
7. Status/reason/limitation có cho phép dùng làm kết quả chính?

Event join rate khác player-match coverage về mẫu số, không so như cùng đơn vị.

| Kết quả | Cách hiểu |
| --- | --- |
| Pearson/Spearman | Hướng/mức liên hệ, đọc N/mode/target-derived flag; không nhân quả |
| Cluster center | Raw behavior khác standardized center |
| Cluster ID | Chỉ trong run/mode; cluster0Solo không bằng cluster0Squad |
| MAE | Sai số tuyệt đối trung bình; nhỏ hơn tốt hơn, đọc unit |
| RMSE | Nhạy lỗi lớn; nhỏ hơn tốt hơn, cùng unit target |
| R² | Có thể âm/undefined, không là accuracy |
| Delta | candidate-reference: MAE/RMSE âm tốt hơn, R² dương tốt hơn |
| CI | Bất định comparison theo bootstrap; không chứng minh nhân quả |

Placement chuẩn hóa, với số team/placement hợp lệ:

\[
normalized\_placement = 1 - \frac{team\_placement - 1}{N_{teams} - 1}.
\]

25 team và placement5 cho \(1-4/24\approx0{,}8333\). Một team hoặc placement lỗi cần flag/quy tắc riêng.

Thống kê toàn dữ liệu không cần vẽ mọi điểm. Sample/hexbin/binning dùng trực quan phải công bố n/seed/rule; không thay full-data statistics/model.

## XIV. Xử lý lỗi thường gặp

| Dấu hiệu | Kiểm tra/làm gì | Không làm |
| --- | --- | --- |
| ModuleNotFoundError của module src | .py đúng tên/vị trí, root/import path/source/runtime cache | Không pip install module nội bộ hoặc chỉ upload notebook |
| Chạy thành công cell trước | Sửa init/cell lỗi, chạy lại đúng thứ tự | Không sửa progress để bypass |
| NB03 chưa completed | Manifest/root/owner/cell commit | Không xóa checkpoint hoặc chạy lại mọi bước ngay |
| Writer khác running | Xác nhận runtime cũ dừng trước takeover | Không giả ID |
| RUN-04_BLOCKED | Bảng gate, evidence/decision, Drive/runtime sync | Không tự verified/bỏ raise |
| DuckDB OOM | RAM/memory_limit/threads/temp disk/source bản sửa | Không nghĩ T4 làm SQL dùng VRAM, không sample cohort |
| CUDA/cuML lỗi | GPU thực/backend/version/estimator hỗ trợ | Không silent CPU/model fallback |
| Parquet/ZSTD decode | Producer/storage/integrity/read-back, file hỏng cụ thể | Không chỉ kiểm footer hoặc commit file không đọc được |
| Drive I/O/quota/disk | Drive storage khác VM disk; giữ committed state | Không xóa raw/checkpoint chưa xác định |
| Download HTML/403/hash | URL/quyền/nguồn/checksum | Không tắt hash hoặc nhận HTML làm ZIP |
| Null/pending | Diagnostics và decision đúng stage | Không sao ngưỡng/K từ test |
| Schema/alias/parse | Header/mapping/report/shard cụ thể | Không ép kiểu/bỏ dòng che lỗi |
| History Grade C/availability pending | Historical blocked/pending theo hợp đồng | Không tạo chronology từ file order |
| Join/kill discrepancy | Ledger/unmatched/team/cause/row counts | Không ép kills bằng nhau hoặc unknown=0 |
| Summary thiếu release | Explicit manifest/path/checksum/source | Không train lại trong NB12 |

Báo lỗi kèm notebook, cell/tiêu đề, traceback đầy đủ, root, stage/status và file vừa đồng bộ. Không gửi secrets/token/cookie.

Hết tài nguyên: dừng, giữ committed checkpoint. Cộng tác qua cùng thư mục là hợp lệ, nhưng không dùng nhiều tài khoản để vượt giới hạn truy cập/tài nguyên Colab; xem [FAQ Colab](https://research.google.com/colaboratory/faq.html).

Có thể chờ tài nguyên hoặc dùng môi trường/gói tính toán được cho phép. Chuyển môi trường cần kiểm storage/mount/compatibility; đổi tài khoản không bảo đảm giải quyết OOM/quota.

## XV. Sửa và đồng bộ source

1. Đối chiếu đặc tả/kế hoạch/config trước sửa.
2. Sửa implementation chuẩn trong `src/`, cập nhật generator nếu caller/Markdown đổi.
3. Kiểm thử nhỏ và notebook caller.
4. Nếu sửa src/generator, regenerate notebook bị ảnh hưởng; bundle chung có thể cần cập nhật nhiều notebook.
5. Giữ output cần thiết trước regenerate; không sinh All-in-One.
6. Đồng bộ source/config được duyệt/notebook vào đúng Drive project.
7. Cập nhật đúng file/version; tránh (1)/(2)/.py.txt. Không upload fixture thay kết quả thật.
8. Restart runtime, chạy bootstrap/init và kiểm signature/dependency.

Bootstrap không tự cập nhật source/config hiện hữu. Python cũng giữ module đã import trong RAM. Khi thay nhiều .py/config, restart rõ ràng hơn reload một module trong khi dependency vẫn cũ.

Không xóa toàn bộ src/configs/data/artifacts để upload lại. Xác định đúng file và giữ quyết định nghiên cứu của nhóm.

## XVI. Đổi tham số, chạy lại phần nào?

Đây là phạm vi nghiệp vụ dự kiến; signatures thực quyết định reuse và có thể invalidate rộng hơn.

| Muốn thay | Config/source | Key/nội dung | Notebook cần rà soát/chạy lại |
| --- | --- | --- | --- |
| Nguồn/schema | data.yaml/schema.yaml | Source/discovery/aliases/contract | 01 và consumer02-12, kiểm raw riêng |
| Root/storage | Cell/paths.yaml | Root/environment | Bootstrap/setup và verify artifact transfer |
| RAM/batch/temp | Cell/runtime.yaml | Batch/threads/memory/temp | Stage liên quan, giữ đủ rows/phép tính |
| Mode mapping | preprocessing.yaml/rq2.yaml | Mapping/strategy | 02 và consumer |
| Chronology/split | preprocessing.yaml/rq3.yaml | Grade/strategy/ratios | 02 và analyses/models phụ thuộc |
| Base formula | `src/features/`, `configs/features.yaml` | Formula/allowlist/version | 03,04 và consumer stale |
| Combat Timing | `src/features/combat_timing.py`, `configs/features.yaml` | Eligibility/cutoff/duration/evidence | 04,05-12 theo dependency |
| RQ2 min-games/K | rq2.yaml | Threshold/K per mode/reasons | Diagnostics/final07,11-12 và consumer assignments |
| RQ2 scaler/log/device | rq2.yaml | Policy/backend | 07 và consumer |
| History | rq3.yaml | Depth/protocol/availability | 08,09 và consumer lịch sử |
| Feature/model/device | `configs/features.yaml`, `configs/models.yaml`, `configs/rq3.yaml` | Task/params/recipe | 09 selection/G4 rồi 10-12 |
| CI/error bins | rq3.yaml/G4receipt | Bootstrap/bins | Duyệt trước test; G4/10 rồi11-12 |
| Caption/style | eda.yaml/generator/helpers | Plot/catalog | Hình/manifest/consumer, không tự refit |

K/min-games/min-history/outlier/chronology/availability/final features/models/params/bins cần evidence đúng stage, không dùng final test để chọn. Drive/root/batch/per_mode đã chốt không đưa về null tùy ý.

## XVII. Quy tắc chống leakage

Leakage (rò rỉ dữ liệu) là sử dụng thông tin không được phép biết trong huấn luyện/lựa chọn, khiến đánh giá tốt giả tạo.

- Cùng match luôn cùng split.
- Imputer/scaler/selection học train; validation lựa chọn, final test không điều chỉnh.
- S1 cấm survival và descendants theo allowlist, gồm rates/velocity/phase-duration coupling.
- RQ1 không dùng feature chứa target làm primary evidence với chính target đó.
- RQ2 không dùng outcome làm input/chọn K/min-games; C5 sau khóa assignment.
- P1/P2 cùng cohort/split/model, chỉ khác survival trực tiếp; P2 vẫn có duration coupling.
- History loại current/future. Grade A xử lý ties/availability, Grade B chỉ ngày trước, Grade C không official S2/P3 future prediction.
- T0/T1/ablation cùng row IDs/target/split/recipe; không âm thầm lấy tập giao nhỏ hơn.
- Bỏ feature group phải bỏ descendants/indicators.
- Không gắn sample training là full-data; full nghĩa mọi train-row hợp lệ trong cohort khai báo.
- Failed/resource_limited/blocked không có metric hợp lệ thì không điền0 hoặc prediction giả.

Chronology A/B chưa đủ nếu không biết thống kê quá khứ đã sẵn sàng trước dự đoán. Availability là điều kiện riêng.

## XVIII. Kiểm thử local

Trong `Project_PUBG`, tạo môi trường riêng:

~~~bash
python -m venv .venv
~~~

PowerShell:

~~~powershell
.\.venv\Scripts\Activate.ps1
~~~

Linux/macOS:

~~~bash
source .venv/bin/activate
~~~

Sau đó:

~~~bash
python -m pip install -r requirements.txt
python -B scripts/run_phase15_tests.py
~~~

Một số tests trình bày cần package thêm như matplotlib/nbformat/nbconvert; đọc dependency/môi trường của bài test. Requirements core không là lock toàn bộ môi trường tái lập. Không cài cuML/CUDA vào Windows CPU chỉ để test CPU.

Kiểm NB04 tập trung:

~~~bash
python -B -m unittest discover -s tests -p test_w05_combat_timing.py -v
python -B -m unittest discover -s tests -p test_nb04_bounded_combat.py -v
~~~

Regenerate notebook sau thay source/caller:

~~~bash
python -B src/utils/generate_notebooks.py --only 04_combat_timing.ipynb
~~~

Không chạy generator không --only hoặc discovery chưa lọc có thể thực thi All-in-One. Syntax/import pass không là nghiệm thu khoa học. Local fixture không chứng minh dữ liệu thật/GPU/Drive.

GPU smoke cần thiết bị/dependencies phù hợp theo [GPU guide](GPU_PER_MODE_GUIDE.md); skipped không là GPU passed.

Đợt viết README chỉ kiểm tài liệu/liên kết/cấu hình, chưa chạy lại các lệnh kiểm thử, package installation hoặc GPU smoke trên môi trường nhóm. Nếu chạy test, đọc cả failed/skipped và dependency thiếu; không coi việc có hướng dẫn là test đã đạt.

## XIX. Khóa kết quả và summary12

NB11 chọn run từ registry/manifest, kiểm status/scope/compatibility/checksum/required matrix rồi khóa snapshot. Release version là chủ đích, không là file trùng ngẫu nhiên.

NB12 chọn manifest cụ thể, không tìm latest hoặc dùng current checkpoint thay snapshot.

~~~python
PUBG_SUMMARY_MANIFEST = (
    "artifacts/manifests/releases/<release_id>/final_results_manifest.json"
)
PUBG_SUMMARY_ALLOW_FIXTURE = False
~~~

Thay <release_id> bằng release thật bàn giao từ 11. Chuẩn bị source/dependencies trước: bootstrap12 không install/unpack/train/build/checkpoint. Thiếu release phải sửa producer/finalization, không tạo kết quả trong 12.

12 phần: dataset, DQ, RQ1, RQ2, survival, placement, T0/T1, ablation, error analysis, uncertainty, findings và limitations. Chỉ hình official report-ready/nguồn khớp; fixture release không là nghiên cứu PUBG.

## XX. Dung lượng và an toàn

Drive quota khác VM disk/RAM. ZIP/staging/cleaned/features/models/spill cần chỗ; không cam kết pipeline dưới10 GB.

Chỉ dọn cache/transfer lỗi thời/output thử đã xác minh không cần. Không xóa .partial/receipt trước khi kiểm phục hồi hoặc fixture còn dẫn làm evidence.

Không upload .git/.venv/credentials/token/cookie hay player identifiers không cần lên public. Không commit raw/model/artifact lớn chỉ để sync Drive.

Luôn tránh tạo project riêng mỗi người, chỉ upload notebook, ép manifest/progress, đổi cohort/model/split/ngưỡng để che lỗi, hoặc gọi diagnostics/fixture là full research result.

## XXI. Tiêu chí hoàn tất

Phải có nguồn hợp lệ, DQ/cohort/split/decisions, RQ1/RQ2/RQ3 với nhánh điều kiện có status/reason, comparisons/errors/CI, release hợp lệ và summary đọc được.

| Gate | Ý nghĩa |
| --- | --- |
| G0 | Code/config/notebook/tests/hướng dẫn sẵn sàng, không là full run |
| G1 | Nguồn/shards/contract được kiểm chứng |
| G2 | Cohort/target/chronology/split sẵn sàng |
| G3 | Quyết định nghiên cứu có evidence/receipt |
| G4 | Recipe/comparisons/model khóa trước final test |
| G5 | Kết quả hợp lệ, release cuối được khóa |

Kế hoạch, output và manifests phải khớp. Không suy gates đạt từ13 file notebook hoặc số tests passed; thiếu gì thì công bố đúng giới hạn.
