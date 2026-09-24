# Kiểm tra notebook và hướng dẫn chạy lại

## Rà soát mở rộng ngày 25/09/2026

Đã đọc lại mã cell của 13 notebook riêng, notebook tổng hợp và các hàm được gọi. Các notebook được tạo từ `src/utils/generate_notebooks.py`; bản phát hành đã được tạo lại từ nguồn này.

Kết quả cuối đợt mở rộng: **49/49 kiểm thử đạt trong 46,011 giây**, lệnh `python -m unittest discover -s tests -v`. Log cục bộ: `../pubg_full_logic_audit_20260925.log`. Các ca mới nằm trong `tests/test_notebook_logic_audit.py`; bài thực thi notebook trong `tests/test_no_drive_notebooks.py` đã được mở rộng để kiểm tra chạy lại cell và bàn giao thư mục.

| Notebook | Nội dung kiểm tra và sửa trong đợt mở rộng |
|---|---|
| 00 | Bootstrap, cấu hình runtime/Drive; checkpoint dùng đường dẫn tương đối cho lần ghi mới để có thể đổi thư mục gốc. |
| 01 | Download ghi cục bộ, phát hiện thiếu byte; retry công bố, checksum, giữ shard hoàn tất cục bộ, kiểm tra manifest trước Gate G1. |
| 02 | Kiểm tra checksum/số dòng shard đầu vào; đường dẫn có dấu nháy, split sai cấu hình hoặc trùng match ID bị từ chối trước khi ghi; split theo thời gian chuẩn hóa UTC. |
| 03 | Xác nhận đây là notebook khởi tạo/thông báo, phần tạo features thực tế nằm ở 04. Không coi 03 là một bước xử lý dữ liệu độc lập. |
| 04 | Kiểm tra shard deaths; bảo toàn số dòng join; audit CSV ghi qua file cục bộ. |
| 05 | CSV ghi có kiểm chứng; bảng phân bố rỗng vẫn có schema để cell hiển thị không lỗi. |
| 06–07 | CSV phân tích/phân cụm ghi có kiểm chứng; kiểm tra lại trường hợp thiếu dữ liệu, profile không đủ, alignment outcome và chạy lại cell. |
| 08 | Không mặc định cho phép lịch sử khi thiếu grade; từ chối grade không hợp lệ; lưu `historical_status.json` cả khi bị chặn. |
| 09 | Linear giữ cột toàn thiếu trong tập Train để pipeline không còn 0 feature; dự đoán được khóa trong manifest cuối. |
| 10 | Khi không có Test, ghi bảng lỗi rỗng có header, không để lại bảng cũ từ lần chạy trước; CSV dùng hàm ghi chung. |
| 11–12 | Khóa/kiểm tra checksum predictions ngoài tables/models; bỏ file model tạm; chặn kết quả có notebook chưa hoàn tất hoặc đã stale. |
| All-in-One | Kiểm tra trình tự cell và chạy lại, chuyển stage, cả runtime lẫn Drive mô phỏng. |

### Quy tắc chạy lại và bàn giao

- Mỗi cell chỉ được chạy sau khi cell trước của notebook đã thành công. Khi chạy lại một cell mà lỗi, các cell sau không được dùng biến cũ để bỏ qua lỗi.
- Notebook 01–11 ghi trạng thái đang chạy/hoàn tất vào checkpoint. Notebook phụ thuộc sẽ dừng nếu bước trước bị ngắt. Chạy lại upstream đánh dấu các notebook downstream đã ghi nhận quan hệ phụ thuộc là `stale`; cần chạy lại chúng theo thứ tự. Notebook 12 chỉ đọc và kiểm tra trạng thái/checksum.
- Checkpoint mới ghi đường dẫn tương đối và checksum artifact; không chỉ kiểm tra file có tồn tại. Checkpoint cũ dùng đường dẫn tuyệt đối không được tự suy đoán/chuyển sang đường dẫn mới. Hãy chạy lại notebook tương ứng để tạo checkpoint mới khi đổi vị trí dự án.
- Kiểm thử bàn giao dùng 13 tiến trình riêng, chạy mỗi code cell nghiệp vụ hai lần và đổi thư mục dự án sau notebook 04. Kiểm thử phát hiện lỗi gồm mất file upload, rename lỗi, upload hỏng, download thiếu byte, lỗi ghi CSV, checkpoint/shard thay nội dung, out-of-order cell, upstream bị ngắt và downstream stale.
- Với dữ liệu từ phiên bản cũ chưa có trạng thái notebook, các kiểm tra file vẫn áp dụng; không thể suy ra lịch sử thất bại của những lần chạy cũ. Để thiết lập đủ trạng thái và kết quả nhất quán, cập nhật source/notebooks rồi chạy 00 → 12 một lượt. Các shard ingest đúng checksum vẫn được dùng lại.

### Giới hạn của kết luận

Không thể chứng minh “không còn mọi lỗi” bằng kiểm thử hữu hạn. Các thử nghiệm hiện chạy cục bộ với dữ liệu giả và lỗi I/O được mô phỏng, chưa chạy full dataset trên Drive/Colab thật. Một cell có thể phải dừng có chủ đích khi input hỏng, thiếu quyền ghi hoặc tài nguyên không đủ; không bỏ qua lỗi để tuyên bố hoàn tất. Bản sửa không biến các bước pandas thành streaming và không triển khai thêm các thí nghiệm nghiên cứu còn thiếu. Ghi từng file có kiểm chứng cũng không phải giao dịch nguyên tử cho toàn bộ project: vẫn chỉ một người được ghi tại một thời điểm.

## Lỗi đã sửa

- Đợt bổ sung 25/09/2026: ảnh lỗi mới chỉ rõ `Path.replace()` thất bại khi đổi `.uploading` sang Parquet. Sửa hàm công bố dùng chung: retry có giới hạn, kiểm tra đích nếu rename báo lỗi muộn, fallback chép có kiểm chứng chỉ khi có thể tạo độc quyền file đích mới. Không cắt ngắn/ghi đè checkpoint cũ để né lỗi rename. JSON checkpoint dùng cùng cơ chế; ingest thử quyền tạo/thay thế file trước khi chuyển đổi dài.
- Shard ingest đã chuyển đổi xong được giữ cục bộ cùng receipt khi công bố thất bại; chạy lại cùng runtime kiểm tra chữ ký và checksum rồi thử lưu, không phải chuyển CSV lại. Cell Gate G1 kiểm tra manifest và cả aggregate/deaths trước khi commit; chạy cell này sau lỗi ingest không còn ghi nhận hoàn tất sai.
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
- Đợt bổ sung 25/09/2026: `python -m unittest discover -s tests -v` — **40/40 đạt**, gồm thực thi notebook với dữ liệu giả và 8 kiểm tra trong `tests/test_storage_publication.py`: rename ENOENT, rename thành công nhưng báo lỗi, giữ checkpoint cũ, retry JSON, preflight thất bại, hỏng checksum, chép trực tiếp bị ngắt, giữ/tái sử dụng shard cục bộ, và chặn Gate G1 khi manifest chưa hoàn tất. Các tình huống Drive được mô phỏng bằng fault injection; chưa xác thực trên mount Drive thật của người dùng.
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

Đợt 25/09 đã giữ thêm bản mới nhất ở `../PUBG_notebook_backups/00_setup.user-run.20260925-000053.ipynb`. Với lỗi rename ở notebook 01, sau khi cập nhật code chỉ cần chạy lại các cell từ đầu notebook 01 bằng cùng cấu hình Drive; shard có checkpoint hợp lệ được giữ. Không chạy cell Gate G1 riêng để bỏ qua lỗi. Bản sửa này không khôi phục file cục bộ mà phiên bản cũ đã xóa khi gặp lỗi.

`Data_PUBG.zip` có thể giữ ở `/content/drive/MyDrive/PUBG_Project/Data_PUBG.zip`; downloader đã tìm ZIP ở thư mục cha của project. Không cần thay URL tải công khai bằng link thư mục Drive.

Với All-in-One không dùng Drive, giữ `PUBG_STORAGE_MODE = "runtime"`, chạy từ đầu và tải ZIP kết quả ở cell cuối.
