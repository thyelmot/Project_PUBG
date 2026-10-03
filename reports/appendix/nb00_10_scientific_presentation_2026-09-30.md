# Nghiệm thu NB00-10: ghi chú khoa học và trực quan Notebook 00

## I. Phạm vi

- Chỉ hoàn thiện `00_setup.ipynb` theo Chuẩn Phương án 2.
- Đối chiếu `PUBG_RESEARCH_SPEC.md` v3.0 và `PUBG_IMPLEMENTATION_PLAN.md`, task NB00-10.
- Không sửa protocol nghiên cứu, không chạy Notebook 01-12 và không chạy All-in-One.

## II. Nội dung hoàn thiện

- Viết lại nguồn canonical trong `src/utils/generate_notebooks.py`; Notebook 00 không bị sửa tay rồi mất ở lần regenerate sau.
- Toàn bộ title, Markdown, nhãn bảng, cảnh báo và bàn giao của Notebook 00 dùng tiếng Việt có dấu, UTF-8.
- Bổ sung bối cảnh khoa học, câu hỏi kiểm tra, input/output, provenance, phương pháp, invariant, expected/actual, cách đọc, giới hạn và điều kiện chuyển bước.
- Bổ sung công thức dự trù đĩa và phân biệt rõ runtime disk với Google Drive quota.
- Giữ Notebook 00 là stage vận hành: không tạo cohort, split, model, metric hoặc kết luận RQ.

## III. Các bảng được render

| ID | Nội dung |
| --- | --- |
| 00-A | Project root và provenance phiên chạy |
| 00-B | Trạng thái cấu hình nghiên cứu |
| 00-C | Đường dẫn canonical và quyền ghi |
| 00-D | Sự hiện diện của raw input |
| 00-E | Tài nguyên phần cứng quan sát được |
| 00-F | Phiên bản thư viện |
| 00-G | Dự trù dung lượng |
| 00-H | Checkpoint DAG hiện tại |
| 00-I | Trạng thái 13 notebook |
| 00-J | Expected/actual và điều kiện chuyển bước |
| 00-K | Bàn giao Notebook 00 |

Không tạo biểu đồ vì dữ liệu của Notebook 00 là trạng thái, đường dẫn và giá trị kiểm toán rời rạc. Bảng truyền đạt chính xác hơn; biểu đồ tài nguyên chỉ có ý nghĩa khi có chuỗi đo hoặc nhiều runtime để so sánh.

## IV. Bằng chứng kiểm thử

- Chính `00_setup.ipynb` đã chạy hết cell trong workspace runtime tạm.
- Cả 11 bảng 00-A đến 00-K xuất hiện trong output thực thi.
- `runtime_snapshot.json` được tạo và checkpoint `notebook/00_setup.ipynb` kết thúc ở trạng thái `completed`.
- `test_w00_env.py`: 34 test, 33 đạt và 1 skip có điều kiện do chmod trên Windows.
- `test_no_drive_notebooks.py`: 8 đạt, 1 skip All-in-One theo chủ đích.
- `test_notebook_logic_audit.py`: 9/9 đạt.
- Toàn bộ suite: 170 test đạt, 3 skip có điều kiện, 0 lỗi.
- Kiểm tra tĩnh 14 notebook: cú pháp Python hợp lệ, output rỗng và execution count null.

## V. Giới hạn và điểm dừng

- Fixture local không chứng minh Google Drive shortcut/quota, Colab, T4, CUDA/cuML hoặc full-data resource budget.
- Không có raw trong fixture là hợp lệ ở Notebook 00; Gate G1 vẫn thuộc Notebook 01.
- Các giá trị `pending` chưa được tự điền; chúng phải được giải quyết tại gate có dữ liệu tương ứng.
- NB00-10 hoàn tất. Điểm tiếp theo là NB01-14; chưa bắt đầu trong đợt này.