# Tiếp tục sau khi Colab mất runtime

`ModuleNotFoundError: src` và `NameError: paths` sau khi ngắt phiên cho biết môi trường chưa được khởi tạo lại. Chúng không xác định nguyên nhân Colab bị ngắt. Để xác nhận hết RAM cần xem thông báo hoặc nhật ký runtime của Colab.

## Cập nhật bản sửa

Cập nhật `src/`, `notebooks/` và `configs/runtime.yaml` trên Drive. Cấu hình mới dùng DuckDB 2 thread, giới hạn 2GB; mã mới xử lý metadata theo từng nhóm match, ghi output tạm rồi mới thay file chính thức. Việc chia nhóm cần đọc lại dữ liệu nhiều lần nên có thể chậm hơn, nhất là khi đọc trực tiếp từ Drive. Đây không phải bảo đảm toàn bộ pipeline vừa RAM Colab: các bước pandas sau đó vẫn đọc toàn bảng.

## Khôi phục ngay tại bước metadata

Trong All-in-One mới:

1. Chạy cell **Chọn nơi lưu dữ liệu** với `PUBG_STORAGE_MODE = "drive"` và `PUBG_DRIVE_PROJECT_ROOT = "/content/drive/MyDrive/PUBG_Project/Project_PUBG"`.
2. Chạy cell **Bootstrap**, cấp quyền mount Drive nếu được hỏi.
3. Chạy cell khởi tạo của phần **02 — Chất lượng dữ liệu…** (cell import các hàm cleaning, metadata, split và tạo kết nối DuckDB).
4. Nếu `data/interim/cleaned_aggregate.parquet` đã được cell làm sạch ghi thành công trước khi ngắt, bỏ qua cell làm sạch và chạy thẳng **Xây dựng Match Metadata**. Cell metadata tự khai báo lại đường dẫn dữ liệu sạch.
5. Chạy tiếp chronology, split và các phần sau. Nếu dữ liệu sạch thiếu hoặc không đọc được, phải chạy lại cell làm sạch trước.

Không dùng Run all nếu mục đích là tiếp tục từ metadata: Run all sẽ thực thi lại các bước trước. Không chạy các cell còn lại sau khi Bootstrap hoặc cell khởi tạo stage đã báo lỗi.

Nếu trước đó dùng `runtime` và máy ảo bị xóa, dữ liệu `/content` có thể đã mất; cần chạy lại từ đầu hoặc phục hồi bản sao. Lưu notebook không lưu các biến Python hoặc ổ đĩa của máy ảo.
