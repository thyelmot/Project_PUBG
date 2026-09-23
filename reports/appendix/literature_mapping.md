# Phụ lục: Ánh xạ và Kế thừa Tài liệu Nghiên cứu (Literature Mapping)

**Ngày lập:** 24/09/2026  
**Căn cứ:** [PUBG_RESEARCH_SPEC.md](../../../PUBG_RESEARCH_SPEC.md), Phiên bản 3.0; [PUBG_IMPLEMENTATION_PLAN.md](../../../PUBG_IMPLEMENTATION_PLAN.md) §3.  

Tài liệu này xác định ranh giới kế thừa từ ba bài báo khoa học nền tảng (**L1, L2, L3**), đảm bảo việc sử dụng các khái niệm và phương pháp học thuật có kiểm soát, tránh sao chép sai lệch hoặc suy diễn vượt quá phạm vi dữ liệu thực tế.

---

## 1. Bảng đối chiếu kế thừa

| Bài báo & Vị trí | Điểm kế thừa vào dự án | Điểm KHÔNG sao chép sang dự án |
|---|---|---|
| **L1 — Dehpanah et al. (2021)**<br>*Player Modeling using Behavioral Signals in Competitive Online Games*<br>arXiv:2112.04379v1, §III–IV, tr. 2–4 | • Ý tưởng biểu diễn hành vi người chơi đa chiều (Combat, Movement, Support).<br>• Tích lũy lịch sử thi đấu trước trận đấu.<br>• Tách biệt giữa kinh nghiệm tích lũy và hiệu suất tức thời. | • Paper tập trung vào chế độ Solo, xếp hạng và đánh giá bằng NDCG so với hệ thống Rating (TrueSkill, Glicko).<br>• Dự án mở rộng sang Duo/Squad, mô hình hồi quy (Regression), phân cụm (Clustering) và thời điểm giao tranh (Combat Timing).<br>• Không so sánh metric trực tiếp với hệ thống xếp hạng của paper. |
| **L2 — Lee & Lee (2025)**<br>*A Study on the Factors Influencing Rank Prediction in PlayerUnknown’s Battlegrounds*<br>Electronics 14(3), 626, §3–4, tr. 4–14 | • Phân tích tương quan và tầm quan trọng theo từng chế độ chơi (Solo, Duo, Squad).<br>• Chẩn đoán đa cộng tuyến / trùng lặp (Redundancy / VIF).<br>• Quy trình so sánh mô hình cơ bản và nâng cao. | • Dataset của L2 có 29 cột, có các biến ingame như `boosts`, `heals`, `weaponsAcquired` mà dataset của dự án (15/12 cột) không có.<br>• Không tạo giả các biến còn thiếu.<br>• Không tự ý sao chép ngưỡng lọc outlier, siêu tham số hay % hiệu năng từ paper sang dự án. |
| **L3 — Ghazali, Sanat & As’ari (2021)**<br>*Esports Analytics on PlayerUnknown’s Battlegrounds Player Placement Prediction using Machine Learning Approach*<br>IJHaTI 5(1), 17–28, §III–IV, tr. 20–26 | • Khung so sánh mô hình học máy trên dữ liệu PUBG.<br>• Cân bằng giữa sai số dự báo và chi phí tính toán (thời gian huấn luyện). | • Paper sử dụng 5 tập mẫu con nhỏ (mỗi tập 6.000 dòng) và chia holdout 25%.<br>• Dự án không sử dụng thiết kế lấy mẫu cục bộ này làm kết quả chính thức; dự án cam kết xử lý toàn bộ dữ liệu hợp lệ (Full-data policy). |

---

## 2. Các nguyên tắc và phân biệt cốt lõi

1. **Khái niệm Walking Ratio:**  
   Trong L1, "Walking ratio" là khoảng cách đi bộ tích lũy chia cho số trận đã chơi. Trong đặc tả của dự án, `walk_ratio = player_dist_walk / (player_dist_walk + player_dist_ride)`. Hai biến này có tên tương tự nhưng bản chất toán học và ý nghĩa phân tích hoàn toàn khác nhau.
2. **Khái niệm Firing Accuracy:**  
   L1 gọi tỷ lệ `kills / damage` là "firing accuracy". Dữ liệu của dự án không có số lượng phát đạn bắn ra và số phát trúng đích. Do đó, dự án dùng `damage_per_kill = player_dmg / player_kills` và tuyệt đối không gọi đây là "độ chính xác bắn súng thực đo".
3. **Normalized Placement vs winPlacePerc:**  
   Dự án sử dụng `normalized_placement = 1.0 - (team_placement - 1.0) / (N_teams - 1.0)` với $N_{\text{teams}}$ được kiểm chứng trên roster thực tế của từng trận. Không đồng nhất công thức này với `winPlacePerc` ở các cuộc thi Kaggle khác nếu chưa kiểm tra định nghĩa mẫu số.
4. **Hàm tính R² và tương quan:**  
   Không suy ra $R^2$ của hồi quy đơn biến từ bình phương hệ số Pearson ($r^2$). Mọi metric Pearson, Spearman và Out-of-sample $R^2$ được tính bằng các hàm độc lập.
5. **Tiêu chí đánh giá khách quan:**  
   Không sử dụng các chỉ số phần trăm từ các bài báo trước làm mục tiêu áp đặt. Mọi so sánh định tính chỉ có ý nghĩa sau khi giải trình đầy đủ sự khác biệt về tập dữ liệu, kích thước mẫu, cách chia split và định nghĩa target.
6. **Đóng góp riêng của dự án:**  
   Thiết kế phân cụm hành vi (RQ2) kết hợp với đặc trưng thời điểm giao tranh (Combat Timing - RQ1, RQ3) là đóng góp nghiên cứu thực nghiệm độc lập của dự án; không trích dẫn như một kết quả đã được cả ba bài báo trên chứng minh trước đó.
