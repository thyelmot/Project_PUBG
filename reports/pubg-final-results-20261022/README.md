# PUBG — bộ kết quả holdout cuối

Đọc REPORT.md để xem kết quả và giới hạn. `test/` chứa bảng/hình gốc của lần đánh giá holdout; `validation/` chứa chẩn đoán validation; `models/` chứa manifest lựa chọn và trials; `processed/` chứa audit/manifest dữ liệu; `provenance/` chứa checksum, readiness và test; `figures/` chứa hình dựng lại từ CSV cho báo cáo.

Train 50.000 trận / 1.000.000 dòng, Kaggle version 1. Holdout đã đánh giá một lần sau lựa chọn bằng validation. Bộ này không chứa model joblib hoặc parquet lớn; chúng ở output Kaggle version 1. Có 15 CSV và 2 PNG gốc trong test/. Hình bổ sung không chạy lại mô hình.

Kiểm tra file bằng MANIFEST_SHA256.json. Số liệu test trên sáu lớp hiệu lực; không trộn với kết quả 7 lớp ở các run cũ.
