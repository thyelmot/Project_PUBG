# Báo cáo môn Khai phá dữ liệu

Biên dịch bằng XeLaTeX, chạy hai lần trong thư mục này:

```
xelatex -interaction=nonstopmode -halt-on-error main.tex
xelatex -interaction=nonstopmode -halt-on-error main.tex
```

Font: Times New Roman. Nếu Overleaf không có font này, thay dòng setmainfont bằng `\setmainfont{TeX Gyre Termes}`. Chọn compiler XeLaTeX.

Mẫu bìa, thành viên và email lấy từ BaoCaoBTL_ML.pdf. Giảng viên hướng dẫn: ThS. Phạm Kim Thành, theo xác nhận của người dùng.

Số liệu lấy từ output nhúng trong bốn notebook của người dùng. CSV trong evidence là bảng xem trước được trích, không phải toàn bộ CSV gốc. Không chạy lại notebook hoặc thay đổi kết quả. SOURCE_MAP.md truy vết bảng/hình theo chỉ số cell/output bắt đầu từ 0.

Phần survival có bất thường lớn; báo cáo giữ kết quả và trình bày giới hạn. Chưa có CI bootstrap, chưa kiểm độc lập checksum toàn bộ release vì chưa được cung cấp thư mục artifact đầy đủ.

extract_evidence.py và build_assets.py chỉ phục vụ tái tạo bảng/hình từ notebook gốc ở thư mục ../output; không cần chạy để biên dịch LaTeX đã đóng gói.
