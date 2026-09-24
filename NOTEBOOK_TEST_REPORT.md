# Kiểm tra notebook và hướng dẫn chạy lại

## Lỗi đã sửa

- Đợt rà soát ngày 24/09/2026: các bước SQL tạo dữ liệu sạch, match metadata, combat timing và historical features ghi Parquet vào đĩa tạm trước, đóng file rồi chép và kiểm tra SHA256 trước khi thay output trên Drive. Kiểm tra số dòng sau join cũng thực hiện trước khi thay output hợp lệ cũ. Ảnh lỗi chỉ chứng minh không mở được file tạm; chưa đủ kết luận nguyên nhân là Drive mất kết nối.
- Resume notebook 01 giữ các checkpoint chưa duyệt lại khi phiên bị ngắt trong lúc kiểm tra checksum, thay vì xóa danh sách shard đã hoàn tất.
- Notebook 05/06 xử lý được nhóm có giá trị hằng, thiếu quan sát và bảng kết quả rỗng. Notebook 07 xử lý giá trị thiếu, dùng cùng ma trận feature cho chẩn đoán K và phân cụm; ghép outcome theo khóa thay vì vị trí dòng. Nếu không đủ profile khác nhau cho K đã chọn, ghi trạng thái bỏ qua và bảng rỗng có cột, không tự đổi K.
- Historical features loại các trận cùng thời điểm khỏi lịch sử và chuẩn hóa múi giờ. Placement vượt số đội quan sát được trả thiếu thay vì sinh giá trị ngoài miền. Sửa đếm duplicate thiếu cột, chuẩn hóa match ID khi ghép deaths, kiểm tra split thiếu/sai và xử lý metrics rỗng.
- Notebook 02 kiểm tra cột ngày trên toàn bộ dữ liệu sạch, thay vì chỉ 50.000 dòng đầu. Mô tả notebook 05/09/10 được sửa đúng với phân tích/mô hình thực sự đang chạy.
- Bootstrap trước đây đặt cấu hình Drive chỉ trong biến `cfg`. Cell tiếp theo nạp YAML lại khiến output quay về `/content/data`. Đây là lỗi code có thể gây mất dữ liệu giữa các tab dù người dùng đã chọn Drive. `load_config()` nay giữ lựa chọn của phiên ở mọi stage, chỉ áp dụng cho đúng project.
- Chế độ runtime trên Colab nay chọn `/content/Project_PUBG`, tránh dùng nhầm thư mục Drive từ cwd của phiên trước.
- Đường dẫn Drive mặc định trong toàn bộ notebook: `/content/drive/MyDrive/PUBG_Project/Project_PUBG`.
- Chẩn đoán K không gọi silhouette/Davies–Bouldin khi mẫu đánh giá có một cụm cho mỗi điểm; trường hợp này trả NaN vì chỉ số không xác định.

## Phạm vi kiểm thử

- Kiểm tra cấu trúc và biên dịch mọi code cell của 14 notebook.
- Chạy toàn bộ All-in-One trong workspace trống với dữ liệu giả, không mount Drive.
- Chạy cả 13 notebook lần lượt bằng 13 tiến trình Python riêng với Drive mô phỏng. Không chia sẻ biến Python giữa notebook; chỉ dùng tệp trong project chung. Sau từng cell, kiểm tra raw/interim/processed/tables/manifests/experiments vẫn nằm trong project Drive, kể cả sau khi nạp lại config.
- Chạy toàn bộ All-in-One với Drive mô phỏng và kiểm tra final manifest.
- Lần kiểm tra trước đã chạy notebook 00–06 trên 10.000 dòng aggregate và 10.000 dòng deaths lấy từ các CSV thật hiện có. Chưa chạy lại mẫu thật này trong đợt sửa hiện tại; không dùng kết quả mẫu làm kết luận nghiên cứu.
- Đợt hiện tại: `python -m unittest discover -s tests -v` — **32/32 đạt** (38,347 giây), gồm thực thi notebook với dữ liệu giả, dữ liệu/feature/mô hình, download, checkpoint/checksum và 5 kiểm tra hồi quy mới trong `tests/test_notebook_edge_cases.py`.
- Kiểm tra hồi quy Drive shortcut xác nhận `ParquetWriter` chỉ ghi vào thư mục runtime cục bộ; file đã đóng được chép, kiểm tra rồi mới công bố vào thư mục Drive.
- Bản batch: kiểm tra đọc ZIP không tạo CSV trên đĩa, nhiều batch trong một shard, tên file trùng ở hai thư mục, alias cột, ID có số 0 đầu và tên `NA`, dòng CSV có xuống dòng trong dấu nháy, lỗi giữa chừng, resume, output hỏng và manifest chưa hoàn tất.
- Lần kiểm tra trước đã chuyển đổi 120.000 dòng aggregate và 120.000 dòng deaths từ ZIP thật, mỗi batch 10.000 dòng. Kết quả tương đương cách chuyển đổi cũ sau khi chuẩn hóa cột ngày sang UTC để so sánh (bản mới giữ nguyên chuỗi ngày nguồn; cách cũ tự suy luận timestamp rồi đổi theo múi giờ máy).

Chưa kiểm thử OAuth/Google Drive thật, cài thư viện qua mạng trong một runtime Colab mới hoặc toàn bộ dataset nhiều GB. Các bước pandas vẫn cần RAM đủ cho toàn bảng; kiểm thử dữ liệu nhỏ không chứng minh khả năng chạy full dataset trên Colab RAM thấp.

Hướng dẫn batch và các giới hạn dung lượng: [BATCH_COLAB.md](BATCH_COLAB.md).

## Cập nhật trên Drive trước khi chạy lại

1. Lấy phiên bản mới của `src/`, `notebooks/`, `requirements.txt` và tài liệu. Giữ các cấu hình riêng của nhóm nếu có.
2. Ghi đè đúng các tệp mã nguồn trên Drive. Chỉ tải notebook mới sẽ không cập nhật `src/` cũ vì Bootstrap tái sử dụng project đã tồn tại.
3. Khởi động lại runtime để Python không dùng module cũ đã import.
4. Trong từng notebook riêng, chọn `PUBG_STORAGE_MODE = "drive"` và `PUBG_DRIVE_PROJECT_ROOT = "/content/drive/MyDrive/PUBG_Project/Project_PUBG"`.
5. Chạy 00 rồi 01 đến 12, từ trên xuống từng notebook. Notebook 01 phải hoàn thành cell chuyển Parquet trước notebook 02.
6. Kiểm tra `Storage:` trỏ vào `.../PUBG_Project/Project_PUBG/data`. Stage 02 phải in số aggregate shards lớn hơn 0 ở đúng thư mục Drive đó.

Giữ raw ZIP và staging hiện có: notebook 01 kiểm tra và dùng lại shard hoàn tất. Chạy lại notebook 02–12 để kết quả downstream phản ánh các sửa đổi về placement, lịch sử và phân cụm. Không cần xóa toàn bộ dữ liệu hoặc tải ZIP lại.

Bản `00_setup.ipynb` chứa output/cấu hình người dùng trước khi tạo lại notebook đã được giữ riêng ở thư mục cạnh project: `../PUBG_notebook_backups/00_setup.user-run.20260924-233016.ipynb`. Các notebook mới được tạo sạch output; cần chọn lại chế độ Drive trong cell cấu hình.

`Data_PUBG.zip` có thể giữ ở `/content/drive/MyDrive/PUBG_Project/Data_PUBG.zip`; downloader đã tìm ZIP ở thư mục cha của project. Không cần thay URL tải công khai bằng link thư mục Drive.

Với All-in-One không dùng Drive, giữ `PUBG_STORAGE_MODE = "runtime"`, chạy từ đầu và tải ZIP kết quả ở cell cuối.
