# Kết quả chạy đầy đủ

Gói `results.zip` được nhập tại `results/`, giữ nguyên snapshot và đường dẫn tương đối để bảo toàn manifest, cấu hình và checkpoint.

```text
results/
  PUBG_Coursework_v511_S09_S10/
    configs/                       Cấu hình của lần chạy đã lưu
    data/full/                     Dữ liệu xử lý và mô tả dataset
    outputs/full/
      tables/                      CSV đầy đủ
      figures/                     Biểu đồ
      models/                      Mô hình và bộ tiền xử lý
      predictions/                 Kết quả dự đoán
      checkpoints/                 Trạng thái S01-S10
      manifests/                   Metadata, cấu hình và release đã khóa
    src/                           Mã nguồn đi kèm kết quả
    notebooks/                     Notebook đi kèm lần chạy
    handoff_full.json              Inventory bàn giao gốc
  IMPORT_VERIFICATION.json         Biên nhận kiểm tra sau nhập
```

`output/` ở gốc dự án vẫn chứa bốn notebook có output hiển thị. `report/` là bộ báo cáo LaTeX/PDF của nhóm. `results/` chứa file thực sinh ra khi chạy, không thay thế các thư mục đó.

Sau khi nhập, 42 ảnh trong `__results___files/` được xác nhận trùng SHA256 với ảnh ở `outputs/full/figures/` và chuyển sang thư mục khôi phục ngoài dự án. Thư mục xuất ảnh hiện rỗng. Biên nhận nhập vẫn ghi 510 file của gói ZIP gốc; snapshot khoa học và 466 entry trong handoff được giữ nguyên.

Đọc bảng đầy đủ tại `results/PUBG_Coursework_v511_S09_S10/outputs/full/tables/`. Release được chỉ định bởi `outputs/full/manifests/final_results.json` bên trong snapshot.

Không sửa cấu hình, mã nguồn hoặc manifest trong snapshot để đổi đường dẫn. Đường dẫn Kaggle được giữ làm thông tin nguồn; việc tiếp tục chạy cần môi trường, dữ liệu nguồn và bước khôi phục tương thích. Import chỉ kiểm file, không chạy lại notebook hay nạp mô hình joblib.

Toàn bộ `results/` được loại khỏi Git vì dung lượng lớn. Bản ZIP gốc vẫn giữ ở nơi người dùng tải về; clone repository từ GitHub không tự tải các file này.

Lệnh nhập vào một thư mục mới:

```powershell
python -B tools/import_results.py "duong_dan/results.zip" "results"
```

Công cụ kiểm CRC ZIP, SHA256 của các entry trong handoff, đối chiếu checkpoint/release inventory và đọc header Parquet. Không coi các kiểm tra này là xác minh lại dữ liệu raw hoặc nghiệm thu số học của mô hình.
