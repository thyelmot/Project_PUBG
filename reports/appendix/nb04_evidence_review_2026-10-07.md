# NB04: kiểm toán nguồn và sửa thiếu evidence, 2026-10-07

## I. Phạm vi và kết luận

Đối chiếu đặc tả mục15.2-15.3 và plan NB04-08/14/16. Quét chỉ đọc CSV nguồn cục bộ, không chạy pipeline, không huấn luyện, không sửa source data/metadata/config/checkpoint. RUN-04 chưa được mở.

Metadata thực có729969trận, không trùng key. Hai duration dưới60 là1,219 và1,417; năm giá trị rất lớn là63646420000 đến63648215000. Các729962trận còn lại từ194,877 đến2373,716. 3600 chỉ là bin rà soát, không phải ngưỡng nghiên cứu hoặc lý do loại trận.

Năm giá trị rất lớn xuất hiện nguyên dạng trong CSV aggregate. Max survival nguồn khớp metadata của cả5match, trong khi median survival từ346,7375 đến928,729. Đây là giá trị nguồn cực lớn, không phải bằng chứng parser làm sai; chưa xác định được nguyên nhân upstream và đơn vị của các case.

## II. Truy nguyên raw có giới hạn

Nguồn: ../Data_PUBG/aggregate/agg_match_stats_0.csv đến4.csv và ../Data_PUBG/deaths/kill_match_stats_final_0.csv đến4.csv. Chỉ giữ dòng thuộc5match lớn nhất trong metadata, DuckDB512MB/1thread, đọc all_varchar để bảo toàn raw_survive; try_cast dùng cho đối chiếu số, không ghi đè chuỗi nguồn.

Năm match có lần lượt90/82/97/99/94player records theo duration sắp giảm dần. Bốn match có death records:79/96/98/91events, time min/max lần lượt98/1871,74/1866,96/1768,101/1860. Match còn lại không có death record. Roster key không có nhiều team trong subset.

Trong364events:5non-self cùng team,328khác team,29unknown team. Không thể coi tất cả non-self là enemy kill. Số liệu chỉ áp dụng subset5match, không dùng để xác nhận toàn bộ dataset, đơn vị thời gian hoặc căn cứ60giây.

## III. Thay đổi tối thiểu

- Thêm helper audit_match_duration xuất summary CSV nhỏ và case Parquet streaming. Dữ liệu nguồn và công thức max proxy không thay đổi.
- NB04 thêm bảng04-N; summary/cases được đăng ký artifacts diagnostics/final. Có7cases trên metadata thực đã tải. File tại reports/tables/combat_duration_review_summary.csv và combat_duration_review_cases.parquet.
- Roster giờ đối chiếu team theo match/player, không chỉ membership. Nhiều team, NULL hoặc blank giữ unknown; không chọn tùy ý và không nhân dòng. Ledger/event audit thêm cờ/count same-team nonself/different-team/unknown-team. Các cờ không lọc event hoặc đổi timing count.
- Thông báo RUN-04 ghi rõ parameter còn pending và file evidence cần xem. Không chỉ yêu cầu đổi status=verified. Skill Ponytail giúp tái sử dụng nhóm hash/publisher hiện có, không thêm thư viện hay framework.

## IV. Kiểm thử và bàn giao

5tests bounded/audit/recovery đạt2,514s;16tests NB04 đạt14,729s gồm notebook execution cả production expected-blocked và verified fixture. 13regular nbformat/AST hợp lệ; git diff --check đạt; All-in-One hash giữ nguyên khi sinh riêng13regular. Case review bảo toàn byte metadata; team audit giữ đủ6fixture events dù roster conflict/missing và chỉ quy tắc self-kill cũ ảnh hưởng eligible count.

Backup notebook có output thật trước sinh: nb04_evidence_review_2026-10-07/04_before_evidence_review.ipynb. Không coi test fixture hoặc quét5match là full-data acceptance.

## V. Điều kiện còn lại trước mở RUN-04

1. Xác minh đơn vị event time/survival và giải thích các survival nguồn cực lớn; không tự chia tỷ lệ, thay max bằng median hoặc loại trận.
2. Phê duyệt semantics timing: giữ credited-killer như hiện tại hay enemy-only có xử lý same-team/unknown/cause rõ ràng. Thay bộ lọc cần duyệt nghiên cứu và tái tạo timing, không chỉ chỉnh status.
3. Căn cứ ngưỡng duration60giây và sensitivity; hai trận ngắn và các case cực lớn chưa tự chứng minh ngưỡng này đúng.

Không yêu cầu chạy lại NB03 trong đợt kiểm toán này. Chưa deploy Drive; source mới cần cập nhật cùng notebook và kiểm tra signatures. Chưa có resume diagnostics qua source/config thay đổi; không hứa chạy cell merge sẽ sử dụng an toàn cache cũ. Team audit toàn dataset trên Drive chưa chạy, resource và evidence vẫn cần kiểm tra.
