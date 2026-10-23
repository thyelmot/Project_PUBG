# Mapping nhãn

`label_mapping.json` ánh xạ tên `killed_by` sang AR, DMR, SR, LMG, SMG, Shotgun, Other; `null` nghĩa là loại.

Đã đối chiếu toàn bộ 57 nguyên nhân của chunk 0 trong `reports/tables/source_weapon_counts_chunk0.csv`; mẫu audit prefix local trước đó chỉ có 56 tên. Các alias trong plan (`Mini14`) và vũ khí có thể xuất hiện ở chunk khác (`SLR`) được khai báo tường minh. Mỗi sample mới vẫn phải qua kiểm tra nhãn chưa biết; không âm thầm gộp giá trị lạ thành Other.

- Nguyên nhân môi trường: Bluezone, Falling, Drown, RedZone và death.RedZoneBomb_C → null.
- death.PlayerMale_A_C → null vì tên đối tượng nhân vật không xác định họ vũ khí; phát hiện trong pilot lấy ngẫu nhiên trên toàn chunk 0.
- Down and Out → null vì không quan sát được họ vũ khí gây knock ban đầu; đây là nhãn chưa xác định, khác nguyên nhân môi trường.
- Sawed-off (`death.WeapSawnoff_C`) → Shotgun.
- Punch, melee, pistol, crossbow, grenade/Molotov và xe → Other.

Không dùng tỷ lệ lớp trên test để sửa mapping. Bước preprocessing xác định nhóm dưới 0.5% từ train, lưu cả mapping ban đầu và `effective_label_mapping.json` sau gộp, rồi áp dụng cùng mapping lên mọi split.

# Registry development

`development_matches.csv` chứa 2.294 match_id duy nhất đã được sử dụng trong pilot trước khi cố định holdout: hợp của 2.000 trận Kaggle và 300 trận local (6 trận trùng). Không chứa tên người chơi. Khi tạo `source_match_splits.csv` trên toàn nguồn, các trận này chỉ được gán train hoặc validation, không được gán test cuối.

Registry là bằng chứng lịch sử; không sửa/xóa để thay điểm test. Những pilot mới dùng cùng phân hoạch nguồn cố định, nên không cần thêm trận train/validation mới vào registry khi nguồn và seed chia giữ nguyên. Thay đổi nguồn dữ liệu hoặc seed chia cần xem là một thiết kế đánh giá mới, không so sánh trực tiếp với holdout đã giữ trước đó.
