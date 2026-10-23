# Khai phá hành vi người chơi PUBG

Bài tập lớn kết thúc học phần Khai phá Dữ liệu của Nhóm 3, Trường Công nghệ Thông tin Phenikaa, Đại học Phenikaa.

Dự án phân tích dữ liệu PUBG sau trận để khám phá mối liên hệ giữa hành vi và kết quả thi đấu, phân nhóm hành vi theo chế độ chơi, đồng thời đánh giá hồi quy thời gian sống sót và thứ hạng. Đây là dự án khai phá dữ liệu sử dụng học máy truyền thống (Machine Learning), không sử dụng mạng học sâu (Deep Learning).

Bản báo cáo hiện hành có 34 trang. Các số liệu dưới đây được đối chiếu với bảng kết quả đầy đủ đi kèm báo cáo; không phải kết quả kiểm thử trên dữ liệu giả lập.

## I. Giảng viên hướng dẫn và thành viên

Giảng viên hướng dẫn: ThS. Phạm Kim Thành.

| Thành viên | Mã sinh viên | Email |
| --- | --- | --- |
| Kiều Thị Thu Trang | 24100093 | 24100093@st.phenikaa-uni.edu.vn |
| Trần Minh Sang | 24100012 | 24100012@st.phenikaa-uni.edu.vn |
| Ngô Quang Thiện | 24102651 | 24102651@st.phenikaa-uni.edu.vn |

## II. Mục tiêu và phạm vi nghiên cứu

Trong PUBG, số lần hạ gục không thể hiện toàn bộ cách chơi. Di chuyển, hỗ trợ đồng đội và thời điểm giao tranh cũng có thể liên hệ với thời gian sống sót hoặc thứ hạng. Nhóm kết hợp thống kê tổng hợp và sự kiện hạ gục để trả lời ba câu hỏi:

| Câu hỏi | Nội dung | Phương pháp chính |
| --- | --- | --- |
| RQ1 | Hành vi nào liên hệ với thời gian sống sót và thứ hạng? | Thống kê mô tả, tương quan Pearson và Spearman |
| RQ2 | Những nhóm hành vi nào xuất hiện trong Solo, Duo và Squad? | Hồ sơ người chơi theo chế độ, chuẩn hóa, KMeans riêng từng chế độ |
| RQ3 | Hành vi sau trận giải thích kết quả đến mức nào? Thời điểm giao tranh bổ sung bao nhiêu thông tin? | Mô hình cơ sở trung bình/trung vị, hồi quy tuyến tính, so sánh T0/T1 |

Ranh giới diễn giải:

- Mô hình dùng thông tin sau trận để phân tích hồi cứu, không phải dự báo trước trận hoặc dự báo theo thời gian thực.
- Tương quan và hệ số hồi quy không chứng minh quan hệ nhân quả.
- Các nhóm phân cụm là mô tả hành vi trong dữ liệu; không tự gắn nhãn người chơi giỏi, kém hoặc gian lận.
- Phạm vi chính giữ toàn bộ dữ liệu hợp lệ của từng bài toán. Mẫu dùng cho biểu đồ và chẩn đoán được ghi riêng, không thay thế dữ liệu huấn luyện hay đánh giá chính.

## III. Dữ liệu và thiết kế thực nghiệm

### 1. Nguồn dữ liệu

Nguồn sử dụng: [PUBG Match Deaths and Statistics](https://www.kaggle.com/datasets/skihikingkevin/pubg-match-deaths), Dataset Version 3, slug `skihikingkevin/pubg-match-deaths`.

| Nhóm dữ liệu | Đơn vị bản ghi | Số tệp | Số dòng đầu vào |
| --- | --- | ---: | ---: |
| Aggregate | Một người chơi trong một trận | 5 | 67.369.231 |
| Deaths/Event | Một sự kiện hạ gục được ghi nhận | 5 | 65.370.475 |

Nguồn đối chiếu: [source_inventory.csv](report/evidence/full_results/source_inventory.csv). Số dòng trên là quy mô đầu vào, không phải số người chơi duy nhất hoặc số dòng hợp lệ của mọi mô hình. Giấy phép được cấu hình trong lần chạy là `CC0: Public Domain`; README không thay thế điều khoản của nguồn dữ liệu.

Dữ liệu CSV thô không được đóng kèm repository. Các trường định danh được dùng để ghép, chia tập và truy vết, không mặc định đưa vào mô hình.

### 2. Biến mục tiêu

- S1: thời gian sống sót `player_survive_time`, hữu hạn và không âm; đây là hồi quy thông thường, không phải mô hình phân tích sống sót có kiểm duyệt.
- P2 và T0: thứ hạng đội được chuẩn hóa trên dòng người chơi:

$$
y_{\mathrm{placement}} = 1 - \frac{\mathrm{team\_placement}-1}{N_{\mathrm{teams}}-1}.
$$

Chỉ tính thứ hạng chuẩn hóa khi roster và thứ hạng hợp lệ, với $N_{\mathrm{teams}}>1$. Giá trị 1 biểu thị hạng nhất, 0 biểu thị hạng cuối theo roster hợp lệ. Không cắt ngọn giá trị sai để che lỗi dữ liệu.

Đơn vị thời gian có trạng thái `assumed_seconds`: giả định giây đã được chấp thuận cho nguồn Version 3, chưa được tác giả nguồn xác minh độc lập. Điều này ảnh hưởng đến diễn giải MAE/RMSE thời gian sống và các ngưỡng thời gian.

### 3. Chia tập và chống rò rỉ

- Tỷ lệ thiết kế train/validation/test là 70/15/15, chia theo nhóm trận: toàn bộ người chơi trong một trận thuộc cùng một tập.
- Lần chạy đã lưu có chronology Grade C: ý nghĩa và tính nhất quán của thời gian chưa đủ để khẳng định chia theo thứ tự thời gian. Phương án thực tế là chia nhóm trận với seed cố định, không gọi là đánh giá dự báo tương lai.
- [split.json](report/evidence/full_results/split.json) ghi số trận giao nhau giữa các tập bằng 0.
- Bộ điền giá trị thiếu, phép biến đổi và chuẩn hóa của hồi quy được học trên train; không dùng test để khớp các bước này.
- T0 và P2 dùng cùng tập dòng, mục tiêu và split; T1 là mô hình P2 có timing được dùng lại, không phải một lần huấn luyện độc lập thứ tám.
- Thông tin lịch sử truy cập test vẫn được ghi `prior_test_exposure=unknown`; không khẳng định toàn bộ lịch sử test chưa từng được xem.

Các tập huấn luyện đã lưu có 47.158.595 dòng cho S1 và 47.068.529 dòng cho P2/T0. Sự khác biệt đến từ điều kiện hợp lệ của từng mục tiêu. Xem [model_cohorts.csv](report/evidence/full_results/model_cohorts.csv) và [selection.json](report/evidence/full_results/selection.json).

### 4. Combat Timing và phương pháp mô hình

Combat Timing là nhóm đặc trưng về thời điểm giao tranh, gồm thời điểm hạ gục đầu tiên, thời điểm trung bình và phân bố theo pha đầu/giữa/cuối trận. Thời lượng trận được xấp xỉ từ thời gian sống lớn nhất trong trận, không phải thời lượng chính thức. Vì vậy timing theo pha có liên hệ cấu trúc với survival và cần công bố giới hạn này.

Các phương pháp chính:

- RQ1: Pearson, Spearman, kèm số quan sát hợp lệ cho từng cặp biến và chế độ.
- RQ2: tạo hồ sơ người chơi theo chế độ; quy ước tối thiểu 10 trận, thử K từ 2 đến 8, chọn theo silhouette trên development; báo thêm kích thước cụm và độ ổn định qua seed. Chẩn đoán silhouette dùng mẫu có khai báo, không đồng nghĩa chỉ khớp mô hình trên mẫu đó.
- RQ3: bảy mô hình logic gồm S1 mean/median/linear, P2 mean/median/linear và T0 linear. Mean/median chỉ dùng thống kê train. Mô hình chính là hồi quy tuyến tính bình phương tối thiểu (OLS).
- S08 đã chạy sử dụng solver TSQR: QR chia khối, gộp kết quả và giải bài toán nhỏ bằng SVD, giữ toàn bộ dòng train hợp lệ. Đây không phải SGD, lấy trung bình mô hình theo từng khối hoặc lấy mẫu để giảm dữ liệu.
- Đánh giá bằng MAE, RMSE và $R^2$, trong đó MAE/RMSE nhỏ hơn tốt hơn; $R^2$ không phải độ chính xác phân loại và có thể âm. Chỉ số chính theo dòng người chơi-trận, bổ sung cách tổng hợp theo trận và đội.

## IV. Quy trình notebook S00-S12

| Bước | Nội dung | Vai trò đầu ra |
| --- | --- | --- |
| S00 | Cấu hình, kiểm môi trường, nguồn, tài nguyên và khôi phục | Xác nhận điều kiện trước tính toán |
| S01 | Kiểm kê, schema, đọc và đối soát nguồn | Aggregate/event và bằng chứng nguồn |
| S02 | Kiểm chất lượng, roster, chế độ và chia tập | Dữ liệu sạch, metadata trận, split |
| S03 | Đặc trưng cơ sở và biến mục tiêu | Dữ liệu đặc trưng và điều kiện hợp lệ |
| S04 | Combat Timing và hợp nhất | Timing, độ bao phủ và dữ liệu cho phân tích |
| S05 | Phân tích khám phá dữ liệu (EDA) | Thống kê, phân bố, quyết định biến đổi |
| S06 | RQ1: quan hệ hành vi và kết quả | Tương quan theo mục tiêu/chế độ |
| S07 | RQ2: phân cụm | Chọn K, mô hình, tâm và kích thước cụm |
| S08 | RQ3: hồi quy | Mô hình cơ sở, OLS và dự đoán đã lưu |
| S09 | So sánh timing và phân tích sai số | T0/T1, sai số theo nhóm, hệ số, giới hạn |
| S10 | Kiểm tra và khóa kết quả | Release và inventory để truy vết |
| S11 | Đọc kết quả | Trình bày release đã chọn |
| S12 | Bàn giao | Thông tin kiểm tra và sử dụng kết quả |

S01-S10 là các stage tính toán có checkpoint; S11-S12 là phần đọc kết quả và bàn giao, không phải hai lần huấn luyện bổ sung. Tham số `START_STAGE/END_STAGE` nhận S01 đến S10, với `START_STAGE <= END_STAGE`.

## V. Kết quả chính và giới hạn

### 1. Hồi quy thứ hạng

Kết quả test theo từng dòng người chơi-trận, trên cùng 10.085.842 quan sát:

| Mô hình | MAE | RMSE | R² |
| --- | ---: | ---: | ---: |
| P2: dự đoán bằng trung bình train | 0,262813 | 0,301843 | xấp xỉ 0 |
| P2: dự đoán bằng trung vị train | 0,262774 | 0,301908 | -0,000430 |
| T0: OLS không có timing | 0,186802 | 0,231220 | 0,413202 |
| T1 = P2: OLS có timing | 0,173516 | 0,217318 | 0,481642 |

So với T0, T1 giảm MAE khoảng 7,11%, giảm RMSE khoảng 6,01% và tăng R² khoảng 0,06844. Đây là chênh lệch quan sát trong thí nghiệm đã lưu, chưa phải kết luận về ý nghĩa thống kê.

Nguồn đầy đủ: [model_metrics.csv](report/evidence/full_results/model_metrics.csv), [timing_comparison.csv](report/evidence/full_results/timing_comparison.csv). Các bảng này gồm cả validation/test và nhiều cách tổng hợp; cần chọn đúng `split` và `aggregation` trước khi so sánh.

### 2. Phân cụm theo chế độ

| Chế độ | K đã chọn | Số hồ sơ ở bản mô tả full | ARI qua seed trên development |
| --- | ---: | ---: | ---: |
| Solo | 2 | 327.422 | 0,599239 |
| Duo | 4 | 540.292 | 0,027045 |
| Squad | 3 | 800.422 | 0,697830 |

ARI là chỉ số so sánh độ nhất quán của phân cụm qua seed, không phải độ chính xác dự đoán. Số hồ sơ full và ARI development thuộc hai phạm vi khác nhau, không được coi là cùng một phép đánh giá.

Tổng cộng có 1.668.136 hồ sơ người chơi-chế độ, không phải số người duy nhất. Duo có một cụm chiếm khoảng 99,27%, Squad có một cụm chiếm khoảng 99,17%; một số cụm chỉ có vài hồ sơ. Đặc biệt, ARI thấp ở Duo cho thấy cần thận trọng khi diễn giải độ ổn định.

Nguồn: [cluster_selection.json](report/evidence/full_results/cluster_selection.json), [cluster_sizes.csv](report/evidence/full_results/cluster_sizes.csv), [k_diagnostics.csv](report/evidence/full_results/k_diagnostics.csv). Bản phân cụm full có mục đích mô tả, không phải chứng minh khả năng tổng quát trên dữ liệu chưa thấy.

### 3. Thời gian sống và những điều chưa thể kết luận

- Hồi quy thời gian sống có sai số rất lớn và R² âm mạnh. Trên test, OLS có MAE khoảng 186.899,05 và RMSE khoảng 356.911,71 theo đơn vị giây giả định.
- Dữ liệu EDA ghi nhận giá trị survival cực đoan. Chưa đủ bằng chứng kết luận nguyên nhân do nguồn, đơn vị hoặc chuỗi xử lý; không tự loại các dòng này sau khi xem hiệu năng.
- Chưa thực hiện bootstrap để ước lượng khoảng tin cậy; [uncertainty.json](report/evidence/full_results/uncertainty.json) ghi `not_requested`, số lần lặp bằng 0.
- Các hệ số hồi quy cần đọc cùng thang đo và đa cộng tuyến, không xem là mức ảnh hưởng nhân quả.
- Kết quả hiện tại không phải hệ thống đã được triển khai để tư vấn hoặc dự đoán thi đấu thực tế.

## VI. Sản phẩm và cách đọc kết quả

| Sản phẩm | Đường dẫn | Mục đích |
| --- | --- | --- |
| Báo cáo hoàn thiện, 34 trang | [Báo cáo PDF](report/BaoCao_KhaiPhaDuLieu_PUBG.pdf) | Đọc bài toán, phương pháp, thực nghiệm và giới hạn |
| Bộ LaTeX kèm bảng/hình | [Gói báo cáo](report/BaoCao_KhaiPhaDuLieu_PUBG_LaTeX.zip) | Biên dịch báo cáo mà không cần chạy mô hình |
| Mã LaTeX chính | [main.tex](report/main.tex) | Chỉnh nội dung báo cáo |
| Kết quả S00-S06 | [Notebook chuẩn bị dữ liệu và RQ1](output/pubg_S00_S06.ipynb) | Đối chiếu xử lý dữ liệu, EDA và tương quan |
| Kết quả S07 | [Notebook phân cụm](output/pubg_S07.ipynb) | Đọc chẩn đoán K và kết quả cụm |
| Kết quả S08 | [Notebook hồi quy](output/pubg_S08.ipynb) | Đọc mô hình, chỉ số và dự đoán |
| Kết quả S09-S12 | [Notebook tổng hợp](output/pubg_S09_S10_S11_S12.ipynb) | Đọc so sánh, khóa và bàn giao kết quả |
| Notebook thực thi Kaggle | [PUBG_COURSEWORK.ipynb](notebooks/PUBG_COURSEWORK.ipynb) | Thực thi pipeline có kiểm tra |
| Biến thể Colab đã đóng gói | [PUBG_COURSEWORK_COLAB.ipynb](notebooks/PUBG_COURSEWORK_COLAB.ipynb) | Tham khảo luồng Colab, lưu ý phiên bản ở mục IX |

Nếu chỉ muốn xem kết quả, đọc PDF trước, sau đó đối chiếu bốn notebook trong `output/`. Không cần cài CUDA, tải raw hoặc chạy lại notebook.

Để kiểm chứng số liệu trong báo cáo, đọc [CSV và metadata đính kèm](report/evidence/full_results/) cùng [SOURCE_MAP.md](report/SOURCE_MAP.md). Đây là các bảng được chọn phục vụ báo cáo, không phải toàn bộ artifact của mọi stage. Hình và bảng xem trước lịch sử còn được ánh xạ trong [evidence/index.json](report/evidence/index.json).

## VII. Cấu trúc và nơi lưu dữ liệu

Thư mục làm việc chính trên máy là `PUBG_Coursework/`; đó cũng là thư mục gốc của kho Git hiện hành.

```text
PUBG_Coursework/
  README.md
  requirements.txt
  configs/project.yaml
  src/                            Mã nguồn pipeline
  notebooks/                      Notebook Kaggle và biến thể Colab
  output/                         Bốn notebook đã có kết quả hiển thị
  docs/                           Đặc tả, kế hoạch, quy tắc và lịch sử
  report/
    main.tex
    BaoCao_KhaiPhaDuLieu_PUBG.pdf
    BaoCao_KhaiPhaDuLieu_PUBG_LaTeX.zip
    figures/                      Hình dùng trong báo cáo
    tables/                       Bảng LaTeX
    evidence/full_results/        CSV/metadata được chọn và biên nhận kiểm
    SOURCE_MAP.md
  tests/                          Kiểm thử bằng dữ liệu nhỏ có kiểm soát
  tools/                          Công cụ tạo notebook, fixture và nhập kết quả
  kaggle_code.zip                 Gói mã upload đã lưu, không phải kết quả
  kaggle_fixture.zip              Dữ liệu nhỏ dùng kiểm thử, không phải PUBG thật
  results/                        Chỉ có ở máy đã nhập gói Output; Git bỏ qua
    IMPORT_VERIFICATION.json
    PUBG_Coursework_v511_S09_S10/
      configs/
      src/
      notebooks/
      data/full/
      outputs/full/
        tables/
        figures/
        models/
        predictions/
        checkpoints/
        manifests/
      handoff_full.json
```

Cần phân biệt ba vị trí:

- `output/`: notebook đã chạy và có bảng/hình hiển thị, được đưa lên GitHub.
- `outputs/<scope>/`: artifact do pipeline sinh trong một project thực thi, gồm bảng, hình, mô hình, dự đoán, checkpoint và manifest.
- `results/`: bản nhập nguyên cấu trúc Output đã tải về; snapshot nằm trong `results/PUBG_Coursework_v511_S09_S10/`. Đây là nơi chứa file thực của lần chạy, không chỉ phần hiển thị trong notebook.

Snapshot local có dung lượng khoảng 16,67 GiB. Lần kiểm tra sau hợp nhất đã đối chiếu SHA256 của 466 entry trong handoff và checkpoint S01-S10. Release được lưu có ID `ff9f409dc0bc4720904d58545d25d1b4`. Việc kiểm file không thay thế xác minh raw, kiểm lại số học mô hình hoặc nghiệm thu khả năng chạy trên máy khác.

Raw, `results/`, các thư mục runtime `data/`, `outputs/`, file mô hình và thông tin bí mật không thuộc bộ file Git đang quản lý theo quy tắc ignore hiện hành. Clone GitHub không tự tải raw hoặc snapshot đầy đủ.

## VIII. Cài đặt và sử dụng trên Kaggle

### 1. Lấy mã và cài thư viện cơ bản

Nếu chưa có dự án:

```powershell
git clone https://github.com/thyelmot/Project_PUBG.git PUBG_Coursework
cd PUBG_Coursework
```

Nếu đã có thư mục dự án thì dùng bản đang làm việc, không clone đè. Để tạo môi trường Python riêng trên Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` mô tả khoảng phiên bản cho mã Python cơ bản, không phải bản khóa chính xác môi trường đã chạy và không cài đầy đủ GPU. Không cài cuML/CUDA vào môi trường Windows CPU chỉ để đọc báo cáo hoặc chạy kiểm thử CPU.

### 2. Chuẩn bị một lần chạy Kaggle

1. Mở notebook Kaggle trong `notebooks/`; gắn raw đúng Dataset Version 3 và gói code có phiên bản phù hợp. Không dùng fixture làm nguồn nghiên cứu thật.
2. Kiểm tra đường dẫn Input thực tế. Các đường dẫn tài khoản trong phụ lục là đường dẫn của lần chạy cũ, không bảo đảm giống tài khoản khác.
3. Cài thư viện trước khi import pipeline. Nếu dùng gói code theo đường dẫn đã lưu, cell cài cơ bản là:

```python
%pip install -r /kaggle/input/datasets/quangthinng/pubg-coursework-code/requirements.txt
```

4. Sau thay đổi thư viện, khởi động lại kernel khi được yêu cầu. Với resume, phải khớp phiên bản trong handoff; chỉ cài theo khoảng của requirements chưa đủ để bảo đảm tương thích.
5. Kiểm tra toàn bộ tham số S00: nguồn, code, working root, phạm vi stage, chế độ chạy, GPU và checkpoint cần nhập.
6. Chạy cell tham số, bootstrap/khởi tạo và cell định nghĩa hàm chạy stage trước khi chạy phần giữa notebook. Không dựa vào biến RAM của phiên trước.

S01-S06 và phần lớn đọc/ghép dữ liệu, thống kê, đánh giá sử dụng CPU. S07/S08 có các nhánh GPU theo cấu hình; cấu hình gốc khai báo hai GPU. GPU không thay thế RAM và không tự làm mọi phép xử lý nhanh hơn. Kiểm tài nguyên và GPU smoke phải đạt trước khi chạy phần yêu cầu GPU; không bỏ guard để ép chạy.

### 3. Chạy mới, tiếp tục và chỉ đọc

| Nhu cầu | Cấu hình/nguyên tắc |
| --- | --- |
| Chạy mới | Working root mới, không nhập checkpoint cũ; chọn nguồn và khoảng S01-S10 phù hợp |
| Tiếp tục stage sau | Gắn Output của phiên bản cụ thể có handoff; khai báo `RESUME_INPUT`, `RESUME_VERSION` và working root riêng; khôi phục có kiểm |
| Chỉ đọc release | `EXECUTION_MODE="report_only"`, chọn release cụ thể theo cell S00; không tải raw, huấn luyện hoặc tạo stage mới |

Lưu ý quan trọng:

- Notebook Kaggle hiện lưu cấu hình của lượt tiếp tục S08 từ S07, không phải cấu hình chạy S01-S10 từ đầu. Phụ lục cuối README giữ nguyên khối này để đối chiếu với generator và kiểm thử.
- `development` không có nghĩa mã tự lấy mẫu hay tự giảm số dòng. Fixture phải được chọn và tách rõ khỏi full-data.
- Chỉ tái sử dụng stage đã completed khi nguồn, code, config, phần mềm và checksum phù hợp. Không sửa manifest để ép tương thích, không lấy Output khác phiên bản nhưng cùng tên thư mục làm checkpoint.
- Khác RAM/GPU hoặc giới hạn đĩa có thể khiến chương trình dừng. TSQR chỉ giảm áp lực bộ nhớ ở phần hồi quy phù hợp, không bảo đảm toàn bộ pipeline vừa mọi máy.
- Không có cơ chế mặc định tiếp tục một phép fit đang dở. Không cho hai phiên cùng ghi một project hoặc ép takeover khi phiên cũ vẫn chạy.

### 4. Lưu kết quả và khôi phục

Checkpoint và `handoff_full.json` trong working là bằng chứng runtime, chưa tự chứng minh Output đã được Kaggle lưu bền vững. Sau khi chạy, cần lưu một Kaggle Version có Output, kiểm trạng thái hoàn thành và xác nhận file thực có trong Output.

Khi tiếp tục ở phiên khác, gắn đúng Output/version đã lưu và để bước restore kiểm inventory/checksum. Bốn notebook trong `output/` không thay thế data/model/prediction/checkpoint cần cho resume.

Để nhập gói `results.zip` đã tải vào máy mới, chạy từ gốc dự án:

```powershell
python -B tools/import_results.py "D:\Downloads\results.zip" "results"
```

Đích `results` phải chưa tồn tại. Công cụ kiểm đường dẫn ZIP, CRC, SHA256 trong handoff, checkpoint và inventory release; không ghi đè snapshot sẵn có. Snapshot là bằng chứng bất biến: không sửa src/config/manifest bên trong để đổi đường dẫn hoặc giả trạng thái completed.

## IX. Môi trường và biến thể Colab

Môi trường của snapshot S09-S10 được ghi trong handoff, gồm Python 3.13.15, NumPy 2.1.3, pandas 2.3.3, DuckDB 1.5.6, PyArrow 23.0.1, scikit-learn 1.6.1, cuML-cu12 26.2.0 và CuPy CUDA12 14.0.1. Đây là thông tin lịch sử của lần chạy, không phải lệnh cài đặt dùng chung cho mọi nền tảng.

Notebook Colab có mã nguồn đóng kèm và thư mục Drive riêng. Nó không tự nạp phiên bản `src/` hiện tại từ repository. Trong mã hiện tại, generator Colab còn khóa vào một source hash cũ và kiểm tương thích trước khi sinh lại; không mặc định coi biến thể này đã nhận bản sửa TSQR/CuPy của S08.

Vì vậy:

- Ưu tiên notebook Kaggle và các Output đã lưu khi đối chiếu kết quả chính thức hiện tại.
- Nếu dùng Colab, đọc cell cấu hình và môi trường ngay trong notebook đó; kiểm GPU/CUDA, dung lượng, phạm vi stage và source hash trước khi tính toán.
- Không ép checkpoint Kaggle vào Colab hoặc coi gói thư viện của Colab là bản khóa môi trường snapshot S09-S10.
- Việc đồng bộ và nghiệm thu lại Colab là công việc riêng; README này không xác nhận đã chạy full-data thành công trên Colab.

## X. Biên dịch và cập nhật báo cáo

Để chỉ biên dịch báo cáo, không cần raw, GPU hoặc snapshot lớn. Giải nén gói LaTeX hoặc mở thư mục `report/`, chọn XeLaTeX và chạy hai lần:

```powershell
cd report
xelatex -interaction=nonstopmode -halt-on-error main.tex
xelatex -interaction=nonstopmode -halt-on-error main.tex
```

Font đang dùng là Times New Roman. Nếu môi trường không có font này, xem [hướng dẫn báo cáo](report/README.md) để thay bằng font tương thích; thay font có thể làm thay đổi phân trang.

Lệnh trên sinh `main.pdf`. File báo cáo mang tên chính thức trong repository không tự cập nhật chỉ vì `main.pdf` được tạo lại. `package_report.py` có thể cập nhật bản PDF đặt tên và gói ZIP sau khi đã biên dịch, nhưng cần thêm PyMuPDF và Pillow; kiểm trực quan trước khi bàn giao.

Nếu cần tạo lại bảng/hình từ CSV đầy đủ, phải có snapshot local đúng cấu trúc và chạy `python -B build_full_results.py` bên trong `report/` trước khi biên dịch. Công cụ này đọc và kiểm CSV đã lưu, không chạy lại mô hình. Không dùng `build_assets.py` của bản preview cũ để ghi đè bảng mới.

## XI. Kiểm thử và lưu ý bảo trì

Kiểm thử nhỏ của công cụ nhập kết quả có thể chạy từ gốc dự án:

```powershell
python -B -m unittest discover -s tests -p test_import_results.py -v
```

Kiểm đồng bộ khối S00 giữa README và notebook:

```powershell
python -B -m unittest discover -s tests -p test_kaggle_runtime.py -k official_parameters -v
```

Các kiểm thử này không chứng minh CUDA hoạt động hoặc toàn dữ liệu chạy được trên một cấu hình cụ thể. Kiểm thử bằng fixture cũng không phải kết quả nghiên cứu PUBG.

Một số công cụ và helper kiểm thử còn tham chiếu tài liệu ở gốc dự án, trong khi tài liệu hiện đã chuyển vào `docs/`; generator Colab còn có cổng source hash cũ. Đây là các điểm tương thích cần xử lý riêng trước khi tái sinh gói hoặc chạy toàn bộ bộ kiểm thử. Không tự dời tài liệu ngược lại, sửa hash hoặc ghi đè notebook kết quả để bỏ qua lỗi. Lượt chỉnh README không sửa các thành phần này và không tuyên bố toàn bộ test suite đã đạt.

## XII. Tài liệu và truy vết

- [Đặc tả nghiên cứu](docs/PUBG_RESEARCH_SPEC.md): phạm vi RQ, cohort, feature, target, split, chống rò rỉ, phương pháp và đánh giá.
- [Kế hoạch triển khai](docs/PUBG_IMPLEMENTATION_PLAN.md): thiết kế và lịch sử thực hiện.
- [Quy tắc dự án](docs/AGENTS.md): nguyên tắc làm việc và thay đổi.
- [Nhật ký thay đổi](docs/CHANGELOG_FIXES.md): lịch sử các đợt sửa và bằng chứng kiểm tra.
- [Nguồn bảng/hình báo cáo](report/SOURCE_MAP.md): ánh xạ về CSV và metadata.
- [Biên nhận nguồn báo cáo](report/evidence/full_results/verification.json): hash và phạm vi các bảng đã kiểm.

Đặc tả và kế hoạch giữ các ghi chú theo từng thời điểm phát triển; những dòng lịch sử như "chưa chạy nguồn thật" không thay thế trạng thái của snapshot đã hoàn thành sau đó. Để biết kết quả thực nghiệm hiện có, đối chiếu release, bảng nguồn, notebook đã chạy và báo cáo thay vì chỉ đọc một ghi chú tiến độ cũ.

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
