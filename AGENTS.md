# Quy tắc bắt buộc trong dự án PUBG

## I. Nguồn quyết định và phạm vi

1. Trước khi sửa bất kỳ file nào, đọc toàn bộ `PUBG_RESEARCH_SPEC.md`, `PUBG_IMPLEMENTATION_PLAN.md` và phần mới nhất của `CHANGELOG_FIXES.md`.
2. `PUBG_RESEARCH_SPEC.md` là nguồn quyết định nghiên cứu. `PUBG_IMPLEMENTATION_PLAN.md` là danh sách công việc hiện hành duy nhất. Không dùng kế hoạch lưu trữ, changelog hoặc kết quả test cũ thay cho trạng thái hiện tại.
3. Làm từ trên xuống, bắt đầu tại mục chưa nghiệm thu đầu tiên. Sau khi đặt lại checklist phải bắt đầu từ `INV-01`. Không bỏ qua mục mở để làm hoặc tích mục phía sau.
4. Chỉ sửa vận hành mà không làm lệch RQ, cohort, feature, target, split, leakage rule, estimator, metric, checkpoint hoặc khả năng tái lập. Nếu cần đổi protocol nghiên cứu, dừng và xin người dùng quyết định.
5. Không chạy notebook All-in-One. Không sửa hoặc xóa raw data. Không lấy mẫu, bỏ dòng, đổi thuật toán hay giảm phạm vi rồi gọi kết quả là full-data.

Các giá trị người dùng đã chốt, không hỏi lại và không tự đổi:

```python
PUBG_STORAGE_MODE = "drive"
PUBG_DRIVE_PROJECT_ROOT = "/content/drive/MyDrive/PUBG_Project/Project_PUBG"
PUBG_REQUIRE_EXISTING_PROJECT = True
PUBG_BATCH_ROWS = 50000
```

RQ2 dùng `per_mode`. Các notebook huấn luyện mô hình dùng GPU khi estimator/backend hỗ trợ; phải ghi backend, device và version. CPU local hoặc mock routing không phải bằng chứng GPU thật.

## II. Cách thực hiện kế hoạch

1. Xử lý đúng thứ tự giai đoạn 0 đến 15 để đạt G0; chỉ sau đó mới thực hiện giai đoạn 16 trên Colab/Drive.
2. Trong mỗi giai đoạn, xử lý từng task ID theo thứ tự. Hoàn tất và ghi bằng chứng riêng cho task hiện tại trước khi sang task tiếp theo.
3. Mỗi lượt làm việc chỉ xử lý một giai đoạn. Kết thúc giai đoạn phải cập nhật kế hoạch, nối nhật ký, báo cáo bàn giao rồi dừng; không sang giai đoạn kế tiếp khi người dùng chưa cho phép.
4. Với mỗi task:
   - Đọc yêu cầu, dependency, consumer và tiêu chí nghiệm thu.
   - Tìm code đã có trước khi viết mới. Code đúng thì giữ nguyên nhưng vẫn phải kiểm chứng.
   - Truy vết từ notebook đến config, `src/`, generator, test và artifact liên quan.
   - Sửa nguyên nhân gốc tại nơi dùng chung; không vá riêng một notebook nếu các caller khác cùng chịu lỗi.
   - Sinh lại đúng notebook bị ảnh hưởng nếu sửa `src/` hoặc generator.
   - Chạy kiểm thử nhỏ nhất chứng minh lỗi cũ thất bại và bản sửa thành công.
   - Chạy chính notebook bằng fixture cô lập qua cùng code path với full run; không chỉ gọi trực tiếp hàm trong `src/`.
   - Mở hoặc render output notebook để kiểm tra bảng, hình, caption, hướng dẫn đọc và lỗi ẩn.
   - Chỉ sau khi đủ bằng chứng mới đổi đúng một checkbox `[ ]` thành `[x]`.
5. Không thay hàng loạt checkbox. Không tích cả giai đoạn, cả notebook hoặc QA chỉ vì generator chạy, import thành công, syntax đúng, số artifact đủ hay unit test tổng quát pass.
6. Nếu task bị chặn, giữ `[ ]`, ghi `blocked`, nguyên nhân, dependency và điều kiện tiếp tục. `skipped`, `pending`, synthetic, CPU mock hoặc fixture không được ghi là `passed` cho full-data/GPU/Drive thật.
7. Chỉ dùng gate G0-G5 theo kế hoạch. Không tạo hoặc sử dụng Gate G7.

## III. Ba mặt nghiệm thu bắt buộc

Một task chỉ được tích khi đủ các mặt mà task yêu cầu:

1. Logic: công thức, invariant, leakage rule, split, full-data policy và trạng thái lỗi đúng.
2. Tích hợp: notebook truyền đúng config, gọi đúng code path, lưu và đọc lại artifact/checkpoint hợp lệ; không chỉ test hàm độc lập.
3. Khả năng đọc: notebook thực sự hiển thị bảng/hình, tiêu đề, đơn vị, scope, mode, N, missing semantics, nguồn dữ liệu, caption và 1-3 câu hướng dẫn đọc.

Bằng chứng cho mỗi task phải ghi rõ task ID, file/hàm, cell ID hoặc tiêu đề cell, lệnh thực chạy, fixture/scope, điều kiện kiểm tra, expected/actual, đường dẫn output/report và giới hạn. Câu `test PASS`, số test, số cell hoặc số artifact không đủ để nghiệm thu.

## IV. Chuẩn bắt buộc cho notebook 07-12

Không được coi 07-12 là hoàn thiện nếu chỉ có markdown mô tả, lệnh `print`, dictionary path hoặc lời hứa về output.

- Notebook 07: phải có Design 3, missing và mẫu số, retention theo mode, chẩn đoán K, cluster sizes, centers/heatmap, stability, C1, C2-C4, C5, artifact và bàn giao. Cluster ID chỉ có ý nghĩa trong từng mode.
- Notebook 08: phải thể hiện chronology/availability, chẩn đoán và quyết định threshold, ví dụ strict-past, coverage, leakage audit, nhánh blocked hợp lệ và bàn giao. Notebook phải truyền `minimum_history_threshold` từ config; không âm thầm dùng default khi config là null.
- Notebook 09: phải huấn luyện và đánh giá mô hình thật theo ma trận task/target/features/cohort/split, allowlist, preprocessing train-only, baseline, model, G4, metric và hình. Cấm mock prediction, placeholder metric và mọi công thức dùng `actual`, target hoặc test label để tạo prediction.
- Notebook 10: phải có kiểm tra common cohort/recipe, T0/T1, ablation feature-removal closure, paired bootstrap theo match, CI, error analysis, importance và bàn giao.
- Notebook 11: phải chọn run từ registry/manifest, kiểm tra required/actual/status/reason/run/scope/artifact/checksum, compatibility, figure manifest và khóa immutable release tại G5. Cấm hard-code official run ID.
- Notebook 12: chỉ đọc locked release, không download/build/train/tạo run mới; đủ 12 phần trong kế hoạch. Mỗi phần có câu hỏi, bảng/hình thực, cách đọc, kết luận truy nguồn và limitation/status nếu thiếu. Cấm gom phần 2-12 thành một cell sơ sài hoặc bịa số liệu.

Các lỗi phải tìm và chặn rõ ràng:

- `prediction = actual + constant` hoặc biến thể dùng target để giả kết quả.
- Commit checkpoint với `{}` khi stage bắt buộc phải có artifact.
- Hard-code `official_runs` hoặc chọn mọi file còn sót thay vì registry/manifest tương thích.
- Default ngầm thay cho config null cần quyết định.
- Test module pass nhưng notebook caller truyền sai hoặc không truyền tham số.
- Markdown kết luận trước khi có bảng/hình thực sinh.

## V. Lưu trữ, checkpoint và môi trường thật

1. Artifact canonical phải ghi đè an toàn hoặc commit nguyên tử vào đúng đường dẫn; chạy lại không tạo file trùng thêm số thứ tự. Không xóa bản hợp lệ trước khi bản mới được xác minh.
2. Mỗi checkpoint phải có scope, config/code/data signature, status và danh sách artifact. Chỉ reuse stage `completed` và tương thích; stale hoặc incomplete phải bị chặn.
3. Fixture/test dùng namespace riêng, không ghi đè output nghiên cứu.
4. Khi hết RAM, disk, GPU hoặc quota Colab: dừng an toàn, giữ checkpoint đã commit, ghi `resource_limited` hoặc `failed`, báo stage/cell/path/lỗi và cách tiếp tục. Không silent sample hoặc silent CPU fallback.
5. Xác minh GPU thật, Drive thật và full-data chỉ tại RUN tương ứng. Không suy ra từ máy local.

## VI. Cập nhật kế hoạch và nhật ký

1. Không xóa hoặc viết lại lịch sử trong `CHANGELOG_FIXES.md`; chỉ nối thêm mục mới.
2. Mỗi đợt sửa phải ghi ngày, yêu cầu, tài liệu đã đối chiếu, file thay đổi, nội dung sửa, ảnh hưởng nghiên cứu, kiểm thử và giới hạn còn lại.
3. Khi cập nhật checkbox trong kế hoạch, đặt bằng chứng ngay dưới task tương ứng. Không dùng một câu bằng chứng chung cho nhiều task.
4. Sau mỗi notebook, báo riêng: task đã nghiệm thu, file sửa, test đã chạy, notebook output đã xem, artifact tạo ra, mục còn mở và lý do. Chỉ sau báo cáo này mới chuyển notebook kế tiếp.
5. Không commit hoặc push nếu người dùng chưa yêu cầu. Không reset, ghi đè hoặc xóa thay đổi không thuộc nhiệm vụ hiện tại.

## VII. Điều kiện dừng bắt buộc

Dừng và báo người dùng khi gặp một trong các trường hợp sau:

- Cần thay đổi protocol nghiên cứu hoặc quyết định còn null mà dữ liệu thật chưa đủ để chốt.
- Có nguy cơ mất raw data, checkpoint hợp lệ hoặc kết quả của thành viên khác.
- Kết quả notebook mâu thuẫn với artifact, manifest, plan hoặc đặc tả.
- Không thể tạo bằng chứng cho đủ logic, tích hợp và khả năng đọc.
- Colab hết tài nguyên hoặc quyền Drive/shortcut không cho đọc ghi đúng project root.

Không được che blocker bằng cách tích task, giảm phạm vi, tạo dữ liệu giả hoặc viết mô tả như thể công việc đã hoàn thành.
