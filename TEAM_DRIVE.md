# Nhóm chạy lần lượt 13 notebook trên cùng thư mục Drive

## Thiết lập một lần

Tài khoản A giữ thư mục gốc:

```text
MyDrive/PUBG_Project/
├── Data_PUBG.zip
└── Project_PUBG/
    ├── src/
    ├── configs/
    ├── notebooks/
    ├── data/
    ├── artifacts/
    └── reports/
```

1. A chia sẻ **cả thư mục `PUBG_Project`** cho email từng thành viên, quyền **Editor / Người chỉnh sửa**. Nhờ vậy nhóm truy cập được cả ZIP và project. Không cần chia sẻ mật khẩu hoặc mở quyền chỉnh sửa công khai.
2. B, C… mở thư mục được chia sẻ trong Drive, chọn **Organize / Sắp xếp → Add shortcut / Thêm lối tắt**, đặt trong **My Drive / Drive của tôi**, tên `PUBG_Project`. Dùng shortcut đến thư mục A sở hữu, không sao chép dữ liệu thành các project riêng. Nếu đã có thư mục cá nhân trùng tên, đổi tên shortcut và sửa đường dẫn cấu hình tương ứng.
3. Mỗi thành viên mở Colab bằng tài khoản của mình, mount Drive của chính mình và dùng cấu hình sau. Tài khoản A dùng cùng cấu hình vì đã có thư mục gốc.

```python
PUBG_STORAGE_MODE = "drive"
PUBG_DRIVE_PROJECT_ROOT = "/content/drive/MyDrive/PUBG_Project/Project_PUBG"
PUBG_REQUIRE_EXISTING_PROJECT = True
PUBG_BATCH_ROWS = 50000
```

Tùy chọn `PUBG_REQUIRE_EXISTING_PROJECT` yêu cầu có sẵn `configs/data.yaml` và `src/utils/config.py` trước khi Bootstrap ghi file. Nếu thiếu quyền/shortcut hoặc đường dẫn sai, Bootstrap dừng với hướng dẫn thay vì tạo project mới tại đó. Nó không xác minh được ID Drive của thư mục: nhóm vẫn phải xác nhận đang mở cùng thư mục gốc, đặc biệt khi có bản sao trùng tên.

Chủ thư mục tạo một file văn bản có tên riêng của nhóm trong `PUBG_Project`. Các thành viên kiểm tra thấy đúng file đó qua đường dẫn đã mount; thử tạo một file nhỏ và xác nhận tài khoản A nhìn thấy trong thư mục gốc. Đây là bước xác nhận thực tế quyền đọc/ghi và shortcut. Chưa kiểm thử mount Google Drive thật trong môi trường phát triển này.

## Chạy và bàn giao

- Một người chạy 00 rồi 01 đến khi toàn bộ shard hoàn tất; người sau không cần tải/giải nén lại dataset.
- Ví dụ A chạy 00–02; B chạy 03–04; C chạy 05–07; A hoặc thành viên khác chạy 08–12. Đây là chia công việc cho các thành viên, không chạy song song các notebook ghi chung dữ liệu.
- Trong mỗi notebook mới, luôn chạy cell lựa chọn, Bootstrap, cell khởi tạo rồi các cell nghiệp vụ. Không có biến Python nào tự chuyển từ notebook trước sang notebook sau.
- Trước bàn giao, chờ cell ghi kết quả kết thúc, kiểm tra file xuất hiện trên giao diện Drive của người nhận, ghi lại tên notebook/cell đã hoàn thành, sau đó kết thúc phiên đang ghi. Không bàn giao chỉ dựa vào việc file đã có tên: file có thể vẫn đang ghi.
- Người nhận đọc các file đã lưu trong `data/`, `artifacts/`, `reports/` của cùng project. Các file tạm DuckDB trong `/content/temp` chỉ thuộc phiên hiện tại và không cần chuyển.

| Hoàn tất notebook | Đầu ra chính dùng tiếp |
|---|---|
| 01 | `data/interim/staging_shards/` và `batch_manifest.json` có `complete: true` |
| 02 | `cleaned_aggregate.parquet`, `match_metadata.parquet`, `split_assignments.parquet` trong `data/interim/`; chronology/split manifest trong `artifacts/manifests/` |
| 03 | Bước thông báo; phần tạo features thực hiện ở 04 |
| 04 | `data/processed/player_match_features.parquet` |
| 05–07 | Bảng EDA, RQ1 và phân cụm trong `reports/tables/` |
| 08 | Historical features nếu chronology cho phép; có thể bị bỏ qua khi Grade C |
| 09 | `artifacts/experiments/predictions_p1_linear.parquet` và `predictions_p2_linear.parquet` |
| 10 | Bảng ablation và phân tích sai số trong `reports/tables/` |
| 11 | `artifacts/manifests/final_results_manifest.json` |
| 12 | Đọc và trình bày kết quả đã khóa |

## Nếu phiên bị ngắt

File được ghi xong vẫn ở Drive. Các biến RAM, mô hình chưa ghi ra file và tiến trình đang chạy không được tự lưu toàn bộ.

- **Notebook 01:** khởi tạo lại và chạy cell batch. Kiểm tra checksum rồi dùng lại shard đã hoàn tất; shard dở phải đọc lại.
- **Notebook 02:** nếu cleaning đã hoàn tất và file Parquet đọc được, có thể khởi tạo lại rồi tiếp tục cell metadata. Nếu không chắc file ghi xong, chạy lại cell tạo file đó.
- **Các notebook còn lại:** cách đơn giản là khởi tạo lại và chạy lại notebook đang dở từ đầu; không cần chạy lại các notebook trước đã hoàn tất. Không coi sự tồn tại của file là bằng chứng checkpoint hợp lệ.

Chạy riêng notebook giúp giải phóng RAM giữa các bước, nhưng không giảm nhu cầu RAM tối đa của một cell. Notebook 05–07, 09–10 hiện vẫn có bước pandas đọc toàn bảng. Nếu một cell hết RAM, đổi thành viên có cùng cấu hình RAM không giải quyết được nguyên nhân đó.

## Phạm vi lưu trữ và giới hạn dịch vụ

Kết quả nằm trong **một thư mục chung thuộc Drive của A** và được nhóm truy cập qua shortcut. Điều này không đồng nghĩa mọi file mới đều có A là chủ sở hữu hoặc mọi byte đều tính vào quota của A; quyền sở hữu file và dung lượng tài khoản cần được kiểm tra riêng. Không chuyển quyền sở hữu tự động trong notebook.

Colab không cho phép dùng nhiều tài khoản để vượt giới hạn truy cập/tài nguyên. Khi tài khoản hết quota, chờ tài nguyên được cấp lại hoặc dùng phương án tính toán được dịch vụ cho phép; hướng dẫn này phục vụ cộng tác nhóm và tiếp tục từ file đã lưu.

Tài liệu chính thức: [chia sẻ thư mục](https://support.google.com/drive/answer/7166529?hl=en), [shortcut Drive](https://support.google.com/drive/answer/9700156?hl=en), [FAQ Colab](https://research.google.com/colaboratory/faq.html).

## Cập nhật bản sửa

Cập nhật `src/`, `notebooks/` và tài liệu này vào project chung, giữ nguyên dữ liệu đã lưu. Khởi động lại runtime để không dùng module cũ. Cấu hình trên dùng cho mỗi notebook riêng; chế độ `runtime` cũ vẫn tồn tại nhưng không phù hợp việc bàn giao qua Drive.
