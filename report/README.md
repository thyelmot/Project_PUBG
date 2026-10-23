# Báo cáo môn Khai phá dữ liệu

Biên dịch bằng XeLaTeX, chạy hai lần trong thư mục này:

```
xelatex -interaction=nonstopmode -halt-on-error main.tex
xelatex -interaction=nonstopmode -halt-on-error main.tex
```

Font: Times New Roman. Nếu Overleaf không có font này, thay dòng setmainfont bằng `\setmainfont{TeX Gyre Termes}`. Chọn compiler XeLaTeX.

Mẫu bìa, thành viên và email lấy từ BaoCaoBTL_ML.pdf. Giảng viên hướng dẫn: ThS. Phạm Kim Thành, theo xác nhận của người dùng.

Phiên bản hoàn thiện ngày23/10 dùng CSV đầy đủ từ results/PUBG_Coursework_v511_S09_S10. Công cụ build_full_results.py kiểm SHA256 của81CSV với handoff, tạo bảng báo cáo và hai hình bổ sung. Các CSV nguồn được chọn nằm tại evidence/full_results, kèm verification.json và manifest phục vụ diễn giải. SOURCE_MAP.md truy vết bảng mới; evidence/index.json giữ ánh xạ hình và bảng xem trước lịch sử.

Phần survival có bất thường lớn; báo cáo giữ kết quả và trình bày giới hạn. Chưa có CI bootstrap. Gói results đã được kiểm466entry handoff khi nhập; đợt hoàn thiện báo cáo đọc lại81CSV và metadata có liên quan, không huấn luyện lại hoặc nạp joblib.

Để tái tạo bảng/hình của bản hoàn thiện, chạy `python -B build_full_results.py` khi có snapshot đầy đủ ở ../results, rồi biên dịch XeLaTeX hai lần. Khi chỉ biên dịch gói ZIP đã bàn giao thì không cần snapshot hoặc chạy Python. extract_evidence.py và build_assets.py là công cụ của bản báo cáo dựa trên notebook trước đó; không dùng chúng để ghi đè bảng đã hoàn thiện từ CSV.
