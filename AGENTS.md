# Quy tắc bản triển khai mới

Đọc PUBG_RESEARCH_SPEC.md và PUBG_IMPLEMENTATION_PLAN.md trước sửa. Chỉ một notebooks/PUBG_COURSEWORK.ipynb; src là code mới, không nhập manager/generator/bundle cũ. Giữ RQ, full eligible data, group match split 70/15/15, per_mode và chống leakage. Quyết định null phải có diagnostics và evidence, không default ngầm hoặc fake metric/checkpoint.

Notebook từng section theo Phương án 2, tiếng Việt có dấu, bảng/hình thật có nguồn/N/unit/scope/caption/cách đọc. Kiểm actual cells/fixtures riêng; mock/CPU không chứng minh Drive/GPU/full-data. report_only không write/build/train/download. Ghi thay đổi nối tiếp CHANGELOG_FIXES.md; không commit/push khi chưa được yêu cầu.

Không xóa ngoài bản triển khai này hoặc dữ liệu trên Drive bằng suy đoán. Dự án cũ Project_PUBG chưa được xóa do lệnh bị policy chặn; không đổi cách xóa để vượt cơ chế đó.

Ngoại lệ được người dùng yêu cầu ngày20/10/2026: thêm notebooks/PUBG_COURSEWORK_COLAB.ipynb cho Colab Pro, dữ liệu Kaggle pin Version3. Notebook Kaggle vẫn là bản canonical của các section khoa học; tools/build_colab_notebook.py tái dùng các section đó và đóng kèm code5.11, không fork công thức/estimator. Không tạo notebook demo khác. Colab dùng GPU0 tường minh và project Drive riêng, SQL/cache ở runtime; không ép reuse checkpoint Kaggle hoặc gọi mounted-file read-back là xác nhận cloud save.
