# Chạy ZIP theo batch trên Colab

## Thay đổi

ZIP hiện có trong workspace gồm 10 CSV, tổng dung lượng giải nén 20.281.921.579 byte (~18,89 GiB); ZIP là 4.399.919.847 byte (~4,10 GiB).
Notebook 01 mới không tạo thêm bản CSV giải nén này. Nó đọc lần lượt từng CSV trong ZIP, mỗi lần 50.000 dòng, ép kiểu theo schema rồi ghi ngay vào Parquet nén ZSTD. Toàn bộ dòng được đọc; không lấy mẫu. CSV có sẵn vẫn được hỗ trợ và không bị xóa.

Mỗi Parquet của một shard được tạo và đóng hoàn chỉnh trong `/content/temp/batch_ingest`, sau đó mới chép sang Drive dưới tên `.uploading`, kiểm tra kích thước và SHA256 rồi đổi sang tên chính thức. Cách này tránh giữ file `.partial` mở nhiều giờ qua Google Drive shortcut. File tạm cục bộ được xóa sau khi công bố hoặc khi cell lỗi.

Shard hoàn tất mới được công bố và ghi checksum vào `data/interim/staging_shards/batch_manifest.json`. Khi chạy lại, shard đúng checksum được dùng lại; shard bị ngắt hoặc hỏng được chuyển đổi lại từ đầu. File `.partial` không được notebook 02/04 đọc. Không mở hai phiên cùng ghi vào một thư mục staging.

Các bước SQL tạo dữ liệu sạch, metadata, combat timing và historical features cũng tạo Parquet cục bộ rồi mới chép/kiểm tra trên Drive. Vì vậy đĩa runtime phải đủ cho file kết quả của bước đó và file tạm DuckDB, không chỉ một shard đầu vào. Nếu chép thất bại, output cũ được giữ nhưng bước đang chạy cần chạy lại; đây không phải resume giữa chừng một câu SQL. Manifest ingest giữ các checkpoint shard đã có kể cả khi bị ngắt trong lúc kiểm tra lại.

Notebook 02/04 dùng danh sách shard trong manifest, tránh đọc lặp các Parquet cũ còn trong thư mục. Làm sạch, loại trùng và tổng hợp theo trận vẫn xét tất cả shard; không tính riêng từng batch rồi ghép các thống kê sai. All-in-One giải phóng DataFrame của stage trước khi khởi tạo stage tiếp theo.

## Cập nhật và chạy

1. Cập nhật **cả `src/` và `notebooks/`** trên Drive từ bản sửa này. Bootstrap không ghi đè mã nguồn của project đã có; chỉ tải notebook mới là chưa đủ.
2. Giữ ZIP tại `/content/drive/MyDrive/PUBG_Project/Data_PUBG.zip` và project tại `/content/drive/MyDrive/PUBG_Project/Project_PUBG`.
3. Khởi động lại runtime để bỏ các module cũ đã import.
4. Chạy cell lựa chọn, Bootstrap, rồi các cell từ đầu. Cấu hình lưu bền vững:

```python
PUBG_STORAGE_MODE = "drive"
PUBG_DRIVE_PROJECT_ROOT = "/content/drive/MyDrive/PUBG_Project/Project_PUBG"
PUBG_BATCH_ROWS = 50000
```

Nếu RAM ít, giảm `PUBG_BATCH_ROWS` xuống `10000`. Tham số này chỉ kiểm soát bước đọc CSV → Parquet, không giảm số dòng trong nghiên cứu. Với 13 notebook riêng, chạy 00 → 12 và dùng cùng thư mục Drive. Nếu bị ngắt ở notebook 01, chạy lại các cell khởi tạo rồi cell batch; các shard hoàn tất được dùng lại.

Chế độ không dùng Drive vẫn giữ nguyên:

```python
PUBG_STORAGE_MODE = "runtime"
PUBG_BATCH_ROWS = 50000
```

Dữ liệu trong runtime không bền vững khi máy ảo bị xóa. Dùng `drive` nếu cần tiếp tục qua các phiên khác nhau.

## Giới hạn cần hiểu đúng

- Batch tránh lưu thêm toàn bộ CSV giải nén; ZIP, Parquet staging, dữ liệu sạch, features và file tạm DuckDB vẫn cần chỗ lưu. Không thể hứa tổng dung lượng dưới 10 GB.
- RAM và dung lượng đĩa/Drive là hai tài nguyên khác nhau. Con số 10 GB chưa đủ xác định vì sao phiên bị ngắt. Kiểm tra riêng RAM và disk trong báo cáo notebook 00.
- Các notebook 05–07 và 09–10 vẫn có phép đọc toàn bảng bằng pandas và mô hình cần dữ liệu trong RAM. Thay đổi này chưa biến toàn bộ phân tích/huấn luyện thành thuật toán streaming; giảm batch không khắc phục thiếu RAM ở những bước đó.
- Dữ liệu raw và staging từ lần chạy cũ không bị tự động xóa. Vì vậy cập nhật code không tự thu hồi dung lượng đã dùng trước đó. Chỉ dọn bản CSV giải nén cũ sau khi xác minh ZIP gốc còn nguyên và notebook 01 mới hoàn tất; giữ các output cần dùng tiếp.
- Checkpoint hiện tại theo **shard**, không theo từng batch 50.000 dòng. Nếu một shard đang chạy bị ngắt, chỉ shard đó phải đọc lại (các shard hoàn tất được kiểm tra và dùng lại).
- Ổ đĩa runtime phải còn đủ chỗ cho một Parquet shard nén và Drive phải còn đủ chỗ cho file đích. Dòng `Converted ...` chỉ báo tiến độ trong shard; checkpoint chỉ được ghi sau khi file đã chép và kiểm tra xong.

Không tự thay mô hình hoặc lấy mẫu để che giới hạn tài nguyên, vì điều đó làm thay đổi thí nghiệm nghiên cứu.
