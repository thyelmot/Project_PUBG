# Kiểm tra notebook và hướng dẫn chạy lại

## Lỗi đã sửa

- Bootstrap trước đây đặt cấu hình Drive chỉ trong biến `cfg`. Cell tiếp theo nạp YAML lại khiến output quay về `/content/data`. Đây là lỗi code có thể gây mất dữ liệu giữa các tab dù người dùng đã chọn Drive. `load_config()` nay giữ lựa chọn của phiên ở mọi stage, chỉ áp dụng cho đúng project.
- Chế độ runtime trên Colab nay chọn `/content/Project_PUBG`, tránh dùng nhầm thư mục Drive từ cwd của phiên trước.
- Đường dẫn Drive mặc định trong toàn bộ notebook: `/content/drive/MyDrive/PUBG_Project/Project_PUBG`.
- Chẩn đoán K không gọi silhouette/Davies–Bouldin khi mẫu đánh giá có một cụm cho mỗi điểm; trường hợp này trả NaN vì chỉ số không xác định.

## Phạm vi kiểm thử

- Kiểm tra cấu trúc và biên dịch mọi code cell của 14 notebook.
- Chạy toàn bộ All-in-One trong workspace trống với dữ liệu giả, không mount Drive.
- Chạy cả 13 notebook lần lượt bằng 13 tiến trình Python riêng với Drive mô phỏng. Không chia sẻ biến Python giữa notebook; chỉ dùng tệp trong project chung. Sau từng cell, kiểm tra raw/interim/processed/tables/manifests/experiments vẫn nằm trong project Drive, kể cả sau khi nạp lại config.
- Chạy toàn bộ All-in-One với Drive mô phỏng và kiểm tra final manifest.
- Chạy notebook 00–06 trên 10.000 dòng aggregate và 10.000 dòng deaths lấy từ các CSV thật hiện có. Đây chỉ là kiểm thử thực thi, không dùng kết quả mẫu này làm kết luận nghiên cứu.
- Bộ unittest: **26/26 đạt**, gồm các kiểm tra dữ liệu, feature, mô hình, download, checkpoint, checksum và hồi quy notebook.
- Bản batch: kiểm tra đọc ZIP không tạo CSV trên đĩa, nhiều batch trong một shard, tên file trùng ở hai thư mục, alias cột, ID có số 0 đầu và tên `NA`, dòng CSV có xuống dòng trong dấu nháy, lỗi giữa chừng, resume, output hỏng và manifest chưa hoàn tất.
- Chuyển đổi 120.000 dòng aggregate và 120.000 dòng deaths từ ZIP thật, mỗi batch 10.000 dòng. Kết quả tương đương cách chuyển đổi cũ sau khi chuẩn hóa cột ngày sang UTC để so sánh (bản mới giữ nguyên chuỗi ngày nguồn; cách cũ tự suy luận timestamp rồi đổi theo múi giờ máy).

Chưa kiểm thử OAuth/Google Drive thật, cài thư viện qua mạng trong một runtime Colab mới hoặc toàn bộ dataset nhiều GB. Các bước pandas vẫn cần RAM đủ cho toàn bảng; kiểm thử dữ liệu nhỏ không chứng minh khả năng chạy full dataset trên Colab RAM thấp.

Hướng dẫn batch và các giới hạn dung lượng: [BATCH_COLAB.md](BATCH_COLAB.md).

## Cập nhật trên Drive trước khi chạy lại

1. Lấy phiên bản mới của `src/`, `notebooks/`, `requirements.txt` và tài liệu. Giữ các cấu hình riêng của nhóm nếu có.
2. Ghi đè đúng các tệp mã nguồn trên Drive. Chỉ tải notebook mới sẽ không cập nhật `src/` cũ vì Bootstrap tái sử dụng project đã tồn tại.
3. Khởi động lại runtime để Python không dùng module cũ đã import.
4. Trong từng notebook riêng, chọn `PUBG_STORAGE_MODE = "drive"` và `PUBG_DRIVE_PROJECT_ROOT = "/content/drive/MyDrive/PUBG_Project/Project_PUBG"`.
5. Chạy 00 rồi 01 đến 12, từ trên xuống từng notebook. Notebook 01 phải hoàn thành cell chuyển Parquet trước notebook 02.
6. Kiểm tra `Storage:` trỏ vào `.../PUBG_Project/Project_PUBG/data`. Stage 02 phải in số aggregate shards lớn hơn 0 ở đúng thư mục Drive đó.

`Data_PUBG.zip` có thể giữ ở `/content/drive/MyDrive/PUBG_Project/Data_PUBG.zip`; downloader đã tìm ZIP ở thư mục cha của project. Không cần thay URL tải công khai bằng link thư mục Drive.

Với All-in-One không dùng Drive, giữ `PUBG_STORAGE_MODE = "runtime"`, chạy từ đầu và tải ZIP kết quả ở cell cuối.
