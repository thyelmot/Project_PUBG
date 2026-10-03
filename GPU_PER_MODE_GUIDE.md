# GPU, per_mode và đồng bộ phiên bản
Cập nhật 03/10/2026. Đây là hướng dẫn theo code hiện tại, không bằng chứng T4/Colab/cuML/Drive thật.

## I. Bước nào dùng GPU?
| Phần | Backend và giới hạn |
| --- | --- |
| 00-06,08 | CPU/DuckDB/I/O, không cần GPU |
| 07 KMeans/C1/diagnostics/C3/C4 | cuML khi device=cuda; C2 Ward CPU supporting |
| 09 exact OLS hỗ trợ | cuML khi device=cuda; baselines constants CPU |
| 09 RF/HGB/SGD | CPU candidates riêng khi explicitly allowed; yêu cầu CUDA unsupported ghi blocked, không fallback |
| 10 | Saved predictions/metrics/bootstrap/importance; không fit, không cần T4 |
| 11-12 | Finalize/read-only report, không train, không cần T4 |

T4 không tăng host RAM, không chắc mọi bước nhanh hơn. CUDA thiếu/incompatible hoặc OOM dừng với reason/resource_limited và null metric. Chuyển backend là quyết định explicit/signature mới, có thể đổi labels/coefficients; kiểm tolerance/reload, không hứa bitwise parity. Không đổi OLS sang SGD/KMeans sang MiniBatch trong cùng run.

## II. Đồng bộ trước Colab
Cập nhật tất cả source/config liên quan cùng13notebooks đã regenerate bằng đúng file ID/version, không bản (1)/(2), giữ documented research decisions. Không chỉ upload notebook: bootstrap không overwrite source/config hiện hữu. Restart runtime sau cập nhật.
Giữ drive, /content/drive/MyDrive/PUBG_Project/Project_PUBG, require-existing=True, batch50000, per_mode. Kiểm shortcut/read-write cùng root và single writer.
07 và09 metadata yêu cầu T4 nhưng không cấp GPU; chọn runtime hỗ trợ. Setup chỉ cài thư viện GPU khi NVIDIA/environment phù hợp và được cho phép, không cài cuML vào Windows CPU local. Package/backend/version/GPU name phải lưu thực, pin snapshot Colab sau setup thành công, không tự gọi latest là tái lập.

## III. Smoke GPU thật, chỉ khi có thiết bị
Sau bootstrap Colab có dependencies và trước full-data, chạy bài GPU riêng:
```python
import os, subprocess, sys
os.environ["PUBG_TEST_GPU"] = "1"
subprocess.run([sys.executable, "-m", "unittest", "discover",
                "-s", "tests", "-p", "test_gpu_compute.py", "-v"], check=True)
```
Đọc test output/device/backend/package/tolerance. Skipped không phải passed; mock constructor/CPU routing chỉ chứng minh điều phối. RUN-06/RUN-08 giữ xác minh GPU thật. Kiểm module source hiện tại để biết pin/API dùng, không sao số phiên bản cũ từ tài liệu.

## IV. Bàn giao và tài nguyên
Per-mode outputs reports/tables/rq2/<mode>, fitted objects/receipts/checkpoint actual paths; labels chỉ trong từngmode. NB09 meta/compute/predictions theo experiment/run, final predictions chỉ sau G4; NB10 không tạo fit mới.
Khi quota/RAM/VRAM/disk hết: dừng, giữ completed checkpoints, báo notebook/cell/path/reason. Fit dở phải khởi động lại, stage completed compatible reuse. Thành viên tiếp chỉ chạy trên runtime hợp lệ cùng shared shortcut/root, không dùng tài khoản khác vượt giới hạn dịch vụ. Resource estimate không phải peak/quota proof.
NB11 selected artifacts/immutable snapshot, NB12 explicit manifest read-only không raw/config/checkpoint hiện hành hoặc model pickle. CPU fixture hiện có không đủ gọi GPU/full-data/report-ready production.
