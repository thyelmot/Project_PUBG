# Khai phá hành vi người chơi PUBG

Bài tập lớn kết thúc học phần **Khai phá Dữ liệu** của **Nhóm 3**, Trường Công nghệ Thông tin Phenikaa, Đại học Phenikaa.

Đề tài sử dụng dữ liệu trận đấu PUBG để tìm hiểu mối liên hệ giữa hành vi và kết quả, phân nhóm người chơi theo chế độ chơi, đồng thời xây dựng mô hình hồi quy thời gian sống sót và thứ hạng. Dự án kết hợp thống kê, tiền xử lý, phân cụm và hồi quy trong một quy trình có lưu kết quả và truy vết nguồn.

## Giảng viên hướng dẫn và thành viên

**Giảng viên hướng dẫn:** ThS. Phạm Kim Thành

| Thành viên | Mã sinh viên | Email |
| --- | --- | --- |
| Kiều Thị Thu Trang | 24100093 | 24100093@st.phenikaa-uni.edu.vn |
| Trần Minh Sang | 24100012 | 24100012@st.phenikaa-uni.edu.vn |
| Ngô Quang Thiện | 24102651 | 24102651@st.phenikaa-uni.edu.vn |

## Giới thiệu đề tài

Trong PUBG, số lần hạ gục chưa phản ánh toàn bộ cách chơi. Di chuyển, hỗ trợ đồng đội và thời điểm giao tranh cũng có thể liên hệ với khả năng sống sót và thứ hạng. Nhóm khai thác cả bảng thống kê tổng hợp và bảng sự kiện để xem xét những khía cạnh này.

Đề tài tập trung vào ba câu hỏi:

| Câu hỏi nghiên cứu | Nội dung | Phương pháp |
| --- | --- | --- |
| RQ1 | Hành vi nào liên hệ với thời gian sống sót và thứ hạng? | Thống kê mô tả, tương quan Pearson và Spearman |
| RQ2 | Có thể nhận diện những nhóm hành vi nào trong Solo, Duo và Squad? | Hồ sơ người chơi theo chế độ, chuẩn hóa và KMeans |
| RQ3 | Các biến hành vi giải thích kết quả sau trận đến mức nào? Timing đóng góp thêm bao nhiêu? | Baseline trung bình/trung vị, hồi quy tuyến tính và so sánh T0/T1 |

Phạm vi của mô hình là phân tích hồi cứu bằng thông tin sau trận. Các kết quả thể hiện quan hệ quan sát, chưa chứng minh tác động nhân quả hoặc khả năng dự báo trước khi trận đấu diễn ra.

## Dữ liệu sử dụng

Nguồn: [PUBG Match Deaths and Statistics trên Kaggle](https://www.kaggle.com/datasets/skihikingkevin/pubg-match-deaths), phiên bản 3.

| Nhóm dữ liệu | Nội dung | Quy mô đầu vào đã kiểm kê |
| --- | --- | --- |
| Aggregate | Thống kê từng người chơi trong từng trận | 67.369.231 dòng, 5 tệp |
| Deaths/Event | Sự kiện hạ gục trong trận | 65.370.475 dòng, 5 tệp |

Quy mô trên lấy từ bảng kiểm kê trong notebook đã chạy. Số dòng không phải số người chơi duy nhất. Cấu hình nguồn ghi giấy phép CC0: Public Domain.

Nhóm sử dụng toàn bộ dữ liệu hợp lệ theo từng bài toán. Một số biểu đồ và phép chẩn đoán dùng mẫu có ghi phạm vi và seed; việc đó không thay thế tập dữ liệu dùng để huấn luyện và tính chỉ số chính.

Hai biến mục tiêu:

- **Thời gian sống sót:** biến `player_survive_time`.
- **Thứ hạng chuẩn hóa:** chuyển thứ hạng đội về khoảng từ 0 đến 1, trong đó giá trị lớn hơn biểu thị kết quả tốt hơn.

Đơn vị thời gian được công bố theo trạng thái `assumed_seconds`: giả định giây đã được chấp thuận trong thiết kế, chưa được tác giả nguồn xác minh độc lập.

## Phương pháp thực hiện

1. **Kiểm tra và tiền xử lý:** kiểm kê tệp, kiểm schema, trùng lặp, định danh, giá trị thiếu và điều kiện hợp lệ của từng mục tiêu.
2. **Chia tập dữ liệu:** giữ tất cả người chơi của cùng một trận trong cùng một tập, với tỷ lệ train/validation/test xấp xỉ 70/15/15.
3. **Tạo đặc trưng:** tổng hợp giao tranh, di chuyển, hỗ trợ và Combat Timing (thông tin thời điểm giao tranh).
4. **Khám phá quan hệ:** tính thống kê và tương quan trên phạm vi dữ liệu được khai báo.
5. **Phân cụm:** tạo hồ sơ người chơi, lọc theo số trận tối thiểu và chạy KMeans riêng cho Solo, Duo, Squad.
6. **Hồi quy và đánh giá:** so sánh mô hình cơ sở với hồi quy tuyến tính, đánh giá bằng MAE, RMSE và hệ số xác định R².
7. **Tổng hợp báo cáo:** phân tích sai số, lưu bảng/hình, khóa kết quả và biên soạn báo cáo LaTeX.

Trong phép so sánh timing, **T0** sử dụng nhóm đặc trưng không có timing; **T1** dùng lại mô hình placement P2 có timing. Hai nhánh được đánh giá trên cùng tập dòng và cùng biến mục tiêu.

## Kết quả chính

Bốn notebook kết quả đã ghi nhận hoàn thành các bước S01-S10, kèm phần đọc báo cáo và bàn giao S11-S12.

### Hồi quy thứ hạng và đóng góp của timing

Kết quả test theo từng dòng người chơi (micro), trên **10.085.842 quan sát**:

| Chỉ số | T0: không có timing | T1: có timing |
| --- | ---: | ---: |
| MAE | 0,186802 | 0,173516 |
| RMSE | 0,231220 | 0,217318 |
| R² | 0,413202 | 0,481642 |

Trong thí nghiệm này, timing giúp giảm MAE khoảng **7,11%** và tăng R² khoảng **0,06844 điểm**. Nguồn số liệu: bảng `timing_comparison` trong [notebook S09-S12](output/pubg_S09_S10_S11_S12.ipynb).

Chưa thực hiện bootstrap để ước lượng khoảng tin cậy, nên chưa kết luận chênh lệch có ý nghĩa thống kê. Timing theo pha còn phụ thuộc vào thời lượng trận xấp xỉ từ dữ liệu hậu trận.

### Phân cụm hành vi

Kết quả mô tả có **2 cụm Solo, 4 cụm Duo và 3 cụm Squad**. Hai cụm Solo khác nhau về mức độ giao tranh. Duo và Squad có phân bố cụm rất lệch, xuất hiện những cụm chỉ gồm một số ít hồ sơ; cần đọc thêm kích thước cụm, tâm cụm và độ ổn định trước khi gắn tên phong cách chơi.

Nguồn: [notebook S07](output/pubg_S07.ipynb), các bảng `cluster_sizes`, `cluster_centers` và `k_diagnostics`.

### Giới hạn của mô hình thời gian sống

Mô hình hồi quy thời gian sống có sai số rất lớn và R² âm mạnh. Bảng EDA cũng ghi nhận các giá trị thời gian sống cực đoan. Kết quả hiện tại cần tiếp tục đối soát dữ liệu và chuỗi xử lý; nhóm chưa kết luận nguyên nhân và chưa đề xuất sử dụng mô hình này để dự đoán thực tế.

Các phân tích chi tiết được trình bày trong [báo cáo PDF](report/BaoCao_KhaiPhaDuLieu_PUBG.pdf).

## Sản phẩm của nhóm

| Sản phẩm | Tệp |
| --- | --- |
| Báo cáo môn Khai phá Dữ liệu | [Báo cáo PDF](report/BaoCao_KhaiPhaDuLieu_PUBG.pdf) |
| Bộ mã nguồn báo cáo và hình/bảng | [Gói LaTeX](report/BaoCao_KhaiPhaDuLieu_PUBG_LaTeX.zip) |
| Mã LaTeX chính | [main.tex](report/main.tex) |
| Kết quả chuẩn bị dữ liệu, EDA và quan hệ | [S00-S06](output/pubg_S00_S06.ipynb) |
| Kết quả phân cụm | [S07](output/pubg_S07.ipynb) |
| Kết quả hồi quy | [S08](output/pubg_S08.ipynb) |
| So sánh, sai số và báo cáo tổng hợp | [S09-S12](output/pubg_S09_S10_S11_S12.ipynb) |
| Notebook thực thi trên Kaggle | [PUBG_COURSEWORK.ipynb](notebooks/PUBG_COURSEWORK.ipynb) |
| Notebook dành cho Colab | [PUBG_COURSEWORK_COLAB.ipynb](notebooks/PUBG_COURSEWORK_COLAB.ipynb) |

Các notebook trong `output/` chứa kết quả đã chạy, phục vụ đọc và đối chiếu. Notebook trong `notebooks/` là mã thực thi; cấu hình lưu sẵn có thể dành cho một giai đoạn tiếp tục cụ thể, cần kiểm tra S00 trước khi chạy.

## Cấu trúc dự án

```text
PUBG_Coursework/
  configs/                       Cấu hình nguồn, xử lý và mô hình
  src/                           Mã nguồn các bước phân tích
  notebooks/                     Notebook thực thi Kaggle và Colab
  output/                        Bốn notebook chứa kết quả đã chạy
  report/
    main.tex                     Nội dung báo cáo LaTeX
    figures/                     Hình sử dụng và bằng chứng trích
    tables/                      Bảng định dạng cho báo cáo
    evidence/                    Bảng xem trước và chỉ mục nguồn
    SOURCE_MAP.md                Ánh xạ bảng/hình về notebook nguồn
  tests/                         Kiểm thử và dữ liệu fixture
  tools/                         Công cụ tạo notebook
  requirements.txt               Phụ thuộc phần mềm
  PUBG_RESEARCH_SPEC.md          Đặc tả nghiên cứu
  PUBG_IMPLEMENTATION_PLAN.md    Kế hoạch triển khai
  CHANGELOG_FIXES.md             Lịch sử thay đổi
```

`output/` là nơi lưu notebook kết quả của nhóm. Khi thực thi trên Kaggle, thư mục `outputs/<scope>/` do pipeline tạo chứa bảng, hình, mô hình, dự đoán và checkpoint; hai thư mục có vai trò khác nhau. Một số bảng hiển thị trong notebook được giới hạn số dòng xem trước.

## Xem báo cáo và tái lập

Để tìm hiểu kết quả, đọc báo cáo PDF trước, sau đó đối chiếu notebook theo thứ tự S00-S06, S07, S08, S09-S12. [SOURCE_MAP.md](report/SOURCE_MAP.md) hỗ trợ truy vết các bảng và hình trong báo cáo.

Để biên dịch LaTeX, giải nén gói báo cáo, chọn XeLaTeX và chạy `main.tex` hai lần. Hướng dẫn font và cấu trúc bộ báo cáo nằm trong [report/README.md](report/README.md).

Để thực thi pipeline, sử dụng notebook Kaggle hoặc Colab tương ứng, kiểm tra đường dẫn dữ liệu, phiên bản nguồn, phạm vi stage và môi trường trong S00. Các bước đã lưu chỉ được dùng lại khi vượt qua kiểm tra tương thích và checksum. Bốn notebook kết quả hiện có không thay thế toàn bộ dữ liệu trung gian, mô hình và checkpoint cần để tiếp tục tính toán.

Tài liệu kỹ thuật:

- [Đặc tả nghiên cứu](PUBG_RESEARCH_SPEC.md): câu hỏi, đặc trưng, mục tiêu, chia tập và nguyên tắc đánh giá.
- [Kế hoạch triển khai](PUBG_IMPLEMENTATION_PLAN.md): quy trình và kiểm thử các bước.
- [Nhật ký thay đổi](CHANGELOG_FIXES.md): các đợt sửa lỗi và bằng chứng kiểm tra.

<details>
<summary>Phụ lục: cấu hình kỹ thuật đã dùng cho lượt tiếp tục S08</summary>

Phần này được công cụ tạo notebook đồng bộ để đối chiếu cấu hình. Đây là cấu hình tiếp tục S08 từ bản lưu S07, không phải lệnh chạy lại toàn bộ kết quả trong README. Khi tiếp tục từ bản S08 đã hoàn thành, phải chọn đúng Input/version và phạm vi stage tiếp theo.

### Khối S00 đầy đủ cho nguồn PUBG Version 3 đã chọn

```python
# Khôi phục nguyên S01-S07 từ Version6; chỉ tính S08 bằng OLS chia khối.
PUBG_STORAGE_MODE = "local"
PUBG_PROJECT_ROOT = "/kaggle/working/PUBG_Coursework_v511_S08_matrixdisk"
PUBG_REQUIRE_EXISTING_PROJECT = True
PUBG_BATCH_ROWS = 50000
EXECUTION_MODE = "full"
CODE_INPUT = "/kaggle/input/datasets/quangthinng/pubg-coursework-code"
SOURCE_DIRECTORY = "/kaggle/input/datasets/skihikingkevin/pubg-match-deaths"
SOURCE_VERSION = 3
SOURCE_LICENSE = "CC0: Public Domain"
ALLOW_DATA_PROCESSING = True
ALLOW_FULL_DATA = True
START_STAGE = "S08"
END_STAGE = "S08"
RESUME_INPUT = "/kaggle/input/notebooks/quangthinng/pubg-v3/PUBG_Coursework_v511_S07_profiles"
RESUME_VERSION = "quangthinng/pubg-v3/versions/6"
ALLOW_CPU_GPU_RESUME = False
ALLOW_S07_TSQR_RESUME = True  # Chỉ nhập S01-S07 đã kiểm; không huấn luyện lại KMeans.
S01_IMPORT_ROOT = ""
CLEANUP_IMPORTED_510 = False
RELEASE_MANIFEST = ""
SAVED_OUTPUT_ROOT = ""
SAVED_VERSION = ""
RUN_GPU_SMOKE = True  # Kiểm cuML và QR trên 48 dòng tổng hợp/GPU, không tính lại S01-S07.
INSTALL_DEPENDENCIES = False  # Không dùng nhánh cài rồi yêu cầu restart của S00.
INSTALL_RESUME_ENVIRONMENT = True  # Chỉ khớp DuckDB bản lưu và bốn yêu cầu runtime trước import src.
PUBG_WRITER_ID = ""
PUBG_FORCE_STAGE_TAKEOVER = False
HANDOFF_EVERY_STAGE = False
SOURCE_MODE_EVIDENCE = ""  # Kế thừa evidence từ config bản lưu.
SOURCE_TIME_UNIT_STATUS = "assumed_seconds"
SOURCE_TIME_UNIT_EVIDENCE = ""
SOURCE_TIME_UNIT_ASSUMPTION_APPROVED = True
SOURCE_TIME_UNIT_ASSUMPTION_SCOPE = "skihikingkevin/pubg-match-deaths/versions/3"
```

</details>
