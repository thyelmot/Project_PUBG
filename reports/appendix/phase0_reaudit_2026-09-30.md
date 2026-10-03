# Giai đoạn 0 - Tái kiểm kê ngày 30/09/2026

## I. Phạm vi và kết luận

Đợt này đặt lại toàn bộ 181 dấu hoàn thành cũ; kế hoạch có 349 task checklist. Một checkbox nằm trong code block minh họa đã được đổi thành nhãn `TASK` để không bị nhận nhầm là công việc thật. Giai đoạn 0 chỉ kiểm kê local, đối chiếu lịch sử và khóa baseline. Không chứng nhận notebook, full-data, Drive thật hoặc GPU thật.

Google Drive không được mount trong phiên local này nên chưa kiểm kê được file ID/version trên Drive. Việc đó giữ cho RUN-01, RUN-12, RUN-13 và RUN-17.

## II. Inventory local

| Nhóm | Số file | Ghi chú |
| --- | ---: | --- |
| configs | 10 | Đủ 10 file YAML trong hợp đồng hiện tại |
| notebooks | 14 | 13 notebook 00-12 và một All-in-One bị cấm chạy |
| src | 100 | Bao gồm module Python và cache hiện có |
| tests | 46 | Có 23 module `test*.py`; không đồng nhất số file với số test case |
| artifacts | 35 | Phần lớn là snapshot, backup và artifact fixture/local |
| reports | 3 trước đợt này | Không tính báo cáo tái kiểm kê mới |

Raw local tại `../Data_PUBG` có 10 CSV, tổng 20.281.921.579 byte:

- 5 shard `agg_match_stats*.csv`.
- 5 shard `kill_match_stats*.csv`.
- Không có `source_inventory.json` hiện hành để chứng nhận row count, checksum từng shard hoặc ngày tải.
- Số shard quan sát là inventory hiện tại, không được hard-code thành hợp đồng cố định.

## III. Notebook, backup và checkpoint

- Cả 13 notebook 00-12 hiện có `outputs=0` và `executed=0`.
- All-in-One cũng không có output và không được chạy.
- Năm backup 07/09/10/11/12 trong `artifacts/backups/per_mode_gpu_20260928_202356` không có output.
- Backup `rq2_before_fix_20260928_152015/07_rq2_clustering.ipynb` chỉ có một output và hai code cell có execution count; không phải bản hoàn thành.
- `checkpoint_manifest.json` chỉ có `notebook/01_download_validate.ipynb` ở trạng thái `running`, signature `notebook_v1`, artifact rỗng.
- `runtime_snapshot.json` là snapshot Windows local, `storage_backend=local`, `cuda_available=false`; không phải bằng chứng Colab, Drive hoặc GPU.

Do đó các phát biểu cũ như “notebook chạy toàn vẹn”, “output đã xem” hoặc “artifact chính thức đã tạo” đều bị rút nghiệm thu cho tới khi tái kiểm tra đúng ba mặt.

## IV. Baseline trước sửa logic tiếp theo

| Thành phần | SHA-256 |
| --- | --- |
| AGENTS.md | `fd450ca5c5e87b850ed208ab046c0ec42cf698cc38bc64688c42f13e6a3f9923` |
| PUBG_RESEARCH_SPEC.md | `64305bd7d924eecf55a7f83279b59d7f85eccaa997691093ef41a119c2dfa3fc` |
| PUBG_IMPLEMENTATION_PLAN.md sau reset | `5622421f208c942abcb0cbd6ef730556f58c8f8aa3140a54217c5b789e189e8a` |
| src tree | `257f0ca09368dd0bd92ca980073f0d3873fa4c07593fb9d774d25f92cae432c2` |
| configs tree trước sửa provenance | `ad6a39f83e86947f0e99f36e1938be271614e21637d85bd91eb4f5c6ecc1cfb5` |
| notebooks tree | `e07bbcfa3ae68c49b4468e70426d516238514b08b7075e4516169f5524955da7` |
| tests tree | `b794f3544c33b53f915baeb7cb3880af2602c68c7b1f721cb5f74d04f2996fff` |

Các hash là baseline local, không phải version khóa của kết quả nghiên cứu.

## V. Đối chiếu dấu tích lịch sử

`legacy_checklist_reaudit_2026-09-30.csv` liệt kê đủ 106 dấu tích trong bản lưu:

- 7 mục kiểm kê cũ được tái kiểm tra trong Giai đoạn 0.
- 99 mục còn lại có trạng thái `unverified_after_reset`.
- Không dùng 153/156 test lịch sử, số artifact hoặc việc sinh notebook làm bằng chứng nghiệm thu hiện tại.

## VI. Quyết định và khoảng trống đang mở

| Nhóm | Trạng thái hiện tại | Xử lý bắt buộc sau Giai đoạn 0 |
| --- | --- | --- |
| Storage | Cell notebook mặc định Drive nhưng runtime snapshot/config metadata còn local | Giai đoạn 1-2 phải thống nhất metadata và đường dẫn, kiểm thử Drive thật ở RUN |
| RQ2 mode | `per_mode` đã được người dùng chốt | Vẫn phải xác minh mapping; `party_size_mapping=null` |
| RQ2 threshold/K | `minimum_games_threshold=null`, `selection_reason=null`; K per-mode đang có số nhưng chưa có receipt hợp lệ | Coi K là pending, không final fit trước diagnostics G3 |
| Historical | `minimum_history_threshold=null`, chronology grade null | Không dùng default 5; 08 phải diagnostics hoặc blocked đúng |
| Split | Tỷ lệ đang có số nhưng chưa có chronology/data receipt | Không coi là final cutoff; kiểm tra lại ở 02/G2 |
| Transform/outlier | Log-transform rỗng, không có decision receipt | Giữ pending; không tự xóa outlier |
| Estimator fallback | `fallback_to_sgd_on_oom=true` có nguy cơ đổi estimator im lặng | Giai đoạn 1/11 phải chặn silent fallback hoặc đăng ký recipe riêng |
| Unit provenance | Trang nguồn chưa chứng minh rõ đơn vị | Chuyển các đơn vị sang candidate, status pending; notebook 01 phải xác minh |
| Source provenance | Kaggle xác nhận Version 3 và CC0; ngày tải local chưa biết | Ghi version/license; giữ `download_date=null`, không dùng mtime |

Các lỗi code đã tìm thấy nhưng chưa sửa ngoài phạm vi Giai đoạn 0:

- Generator còn wrapper commit `{}` cho notebook khác 07 tại `src/utils/generate_notebooks.py:106`.
- Generator notebook 09 còn chú thích và logic prediction giả tại khoảng dòng 2300.
- Dependency notebook và checkpoint chưa đồng nhất hoàn toàn cho historical/RQ3.
- Kế hoạch/changelog từng đánh dấu notebook 07 hoàn thành dù chính nhật ký ghi notebook thật thất bại do CUDA.
- README còn hướng dẫn runtime ở một vị trí, trái cấu hình Drive đã chốt.

## VII. Nguồn và literature

- `literature_mapping.md` phân biệt đúng walking ratio với `walk_ratio`, firing accuracy với damage-per-kill, normalized placement với `winPlacePerc`, Pearson với heldout R-squared và không sao metric/sample từ paper.
- Trang nguồn Kaggle được đối chiếu ngày 30/09/2026: dataset Version 3, license CC0, 5 aggregate chunks và 5 death chunks quan sát local. Metadata nguồn: <https://www.kaggle.com/datasets/skihikingkevin/pubg-match-deaths>.
- Không suy ngày tải từ mtime.

## VIII. Kiểm thử

Lệnh import module trực tiếp ban đầu thất bại vì `tests` không phải package; đây là lỗi cách gọi test, không phải lỗi implementation.

Các lệnh discovery đúng đã chạy, không thực thi All-in-One:

- `python -m unittest discover -s tests -p test_w00_env.py -v`: 29 test, 28 pass, 1 skipped do chmod Windows.
- `python -m unittest discover -s tests -p test_w02_ingest_schema.py -v`: 10 pass.
- `python -m unittest discover -s tests -p test_phase_a_infrastructure.py -v`: 8 pass.

Tổng: 47 test, 46 pass, 1 skipped. Kết quả này chỉ hỗ trợ kiểm kê/config/infrastructure; không nghiệm thu notebook 00-12.

## IX. Điểm tiếp tục

Giai đoạn tiếp theo là Giai đoạn 1, bắt đầu từ INF-01. Chỉ tiếp tục khi người dùng duyệt báo cáo Giai đoạn 0.
