"""Build the explicitly requested Colab variant from the canonical scientific sections."""
from pathlib import Path
import base64
import copy
import hashlib
import io
import zipfile

import nbformat

ROOT = Path(__file__).resolve().parents[1]

PARAMETERS = '''#@title 1. Cấu hình Colab Pro
EXECUTION_MODE = "full"  # full, development hoặc report_only; development KHÔNG tự lấy mẫu.
ALLOW_DATA_PROCESSING = True
ALLOW_FULL_DATA = True
USE_GOOGLE_DRIVE = True
PUBG_PROJECT_ROOT = "/content/drive/MyDrive/PUBG_Coursework_Colab_v511" if USE_GOOGLE_DRIVE else "/content/PUBG_Coursework_Colab_v511"
CODE_ROOT = "/content/pubg-code-511-4e3f9a19"
KAGGLE_CACHE_ROOT = "/content/pubg-kaggle-cache"
SOURCE_DATASET = "skihikingkevin/pubg-match-deaths"
SOURCE_VERSION = 3
GPU_IDS = [0]  # Một GPU Colab; không yêu cầu hai T4, không fallback CPU.
CUDA_FAMILY = "cu12"  # Phải khớp nvcc; nếu toolkit CUDA13 thì sửa thành cu13.
INSTALL_COLAB_DEPENDENCIES = True
KAGGLE_LOGIN = False  # Chỉ True nếu Kaggle yêu cầu đăng nhập/đồng ý điều khoản.
MIN_LOCAL_FREE_GIB = 55  # Dự phòng raw/cache/giải nén/SQL, không phải quota Colab đã đo.
START_STAGE = "S01"
END_STAGE = "S10"
RUN_GPU_SMOKE = True
PUBG_WRITER_ID = ""
PUBG_FORCE_STAGE_TAKEOVER = False  # Chỉ bật khi chắc phiên cũ đã dừng.
RELEASE_MANIFEST = ""  # report_only: đường dẫn release.json cụ thể trên Drive.
VERIFY_HANDOFF = True  # Cuối lượt đọc lại checksum/Parquet qua mount; có thể mất thời gian.
'''

INTRO = '''# PUBG: Khai phá hành vi người chơi trên Colab Pro

Notebook Colab riêng được yêu cầu ngày20/10/2026. Giữ ba RQ, toàn bộ dữ liệu hợp lệ, match split70/15/15, KMeans per_mode, OLS/baselines và Combat Timing của bản5.11. Không chứa kết quả PUBG hoặc checkpoint cũ. Code src/config/requirements được đóng kèm ngay trong notebook, không cần tải Dataset code riêng.

I. Bắt đầu

1. Chọn Runtime > Change runtime type > GPU, bật High RAM nếu tài khoản có lựa chọn này. Notebook dùng GPU0 được cấp thực tế; Pro không bảo đảm loại GPU, số GPU, RAM hoặc thời gian vô hạn.
2. Chạy cell1 cấu hình và cell2 cài môi trường. Nếu cell2 báo đã cài: chọn Runtime > Restart session, rồi Runtime > Run all. Không chọn Disconnect and delete runtime. Khi đủ phiên bản, cell2 tự bỏ qua cài lại.
3. Cho phép kết nối Drive khi được hỏi. Cell3 tải đúng Dataset Version3 từ Kaggle vào ổ runtime, không nạp tất cả CSV vào pandas. Public dataset thường không cần token; khi cần, thêm KAGGLE_API_TOKEN vào Colab Secrets và cấp quyền notebook, hoặc đặt KAGGLE_LOGIN=True. Không dán token vào code/output hay gửi cho người khác.

II. Lưu trữ

- Mặc định project/checkpoint/Parquet/model/release nằm trong thư mục Drive riêng PUBG_Coursework_Colab_v511. Raw/cache, SQL/spill và ma trận tạm nằm ở runtime. Không sao cả project sau mỗi stage. Drive có thể chậm khi đọc JOIN nhiều lượt; không hứa tăng tốc.
- Cần tự kiểm tra Drive còn tối thiểu khoảng25GiB; Colab Pro không phải gói tăng dung lượng Drive. Ngân sách project vẫn18GiB, không phải quota thực. Runtime còn ít nhất55GiB trước tải là dự phòng, không bảo đảm toàn pipeline vừa tài nguyên.
- Khi mất phiên: mở lại đúng notebook/root, cài lại môi trường nếu cần, tải raw đúngVersion3 rồi Run all. Chỉ reuse stage completed có code/config/software/source/checksum khớp; phiên bản phần mềm đổi sẽ bị chặn, không ép manifest/checksum. Stage đang chạy dở phải chạy lại, takeover chỉ sau khi xác nhận writer cũ đã dừng. Không chạy đồng thời hai phiên ghi cùng root.
- Nếu USE_GOOGLE_DRIVE=False thì toàn project chỉ ở ổ tạm và có thể mất khi VM bị thu hồi. Lưu file notebook KHÔNG đồng nghĩa lưu dữ liệu hoặc model.

III. Giới hạn

S01-S06/SQL và phần lớn I/O là CPU; S07/S08 mới dùng cuML GPU. GPU không cộng VRAM vào RAM. Full KMeans/OLS vẫn có thể vượt tài nguyên; không tự lấy mẫu hoặc đổi thuật toán. Giây vẫn là giả định được duyệt cho nguồnVersion3, không phải tác giả xác minh. Checksum đọc qua Drive mount không chứng minh đã đồng bộ lên máy chủ Google.

Nguồn vận hành: [Colab FAQ](https://research.google.com/colaboratory/faq.html), [Kagglehub](https://github.com/Kaggle/kagglehub), [RAPIDS installation](https://docs.nvidia.com/datascience/install/).
'''

BOOTSTRAP = '''import runpy
sys.dont_write_bytecode = True
if EXECUTION_MODE not in {"full", "development", "report_only"}:
    raise ValueError("execution mode phải full/development/report_only")
if START_STAGE not in [f"S{i:02d}" for i in range(1,11)] or END_STAGE not in [f"S{i:02d}" for i in range(1,11)] or START_STAGE > END_STAGE:
    raise ValueError("Stage range phải S01..S10 và START<=END")
project_root = Path(PUBG_PROJECT_ROOT).resolve()
import_root = project_root if EXECUTION_MODE == "report_only" else Path(CODE_ROOT).resolve()
bundle = runpy.run_path(str(import_root/"src/bootstrap.py"))["check_bundle"](import_root, "5.11-normalized-storage", "__SOURCE_HASH__")
print(bundle)
sys.path.insert(0, str(import_root))
__IMPORTS__
if EXECUTION_MODE != "report_only":
    project_root = configure_project(import_root, project_root, SOURCE_DIRECTORY, GPU_IDS, EXECUTION_MODE)
    progress_view = display(pd.DataFrame([{"step":"Sẵn sàng; chưa scan nguồn"}]), display_id=True)
    def show_progress(event):
        progress_view.update(pd.DataFrame([event]))
    ctx = Context(project_root, EXECUTION_MODE, PUBG_WRITER_ID, PUBG_FORCE_STAGE_TAKEOVER, progress=show_progress)
    display(ctx.environment())
    display(pd.DataFrame([preflight(ctx, START_STAGE, END_STAGE, kaggle=True)]))
    display(pd.DataFrame([time_unit_info(ctx.cfg)]))
    print("Project:", ctx.root, "; SQL/scratch runtime:", ctx.temp)
    print("Drive quota phải tự kiểm tra; disk runtime không phải quota Drive.")
    if RUN_GPU_SMOKE:
        display(pd.DataFrame([gpu_smoke(ctx)]))
else:
    load_config(project_root)
    if not RELEASE_MANIFEST:
        raise ValueError("report_only cần RELEASE_MANIFEST cụ thể, không lấy latest")
    print("Chỉ đọc release; không tải raw/cài đặt/build/train/ghi project.")
'''

DATA = '''#@title 3. Kết nối Drive và tải dữ liệu Kaggle đã pin
if EXECUTION_MODE not in {"full", "development", "report_only"}:
    raise ValueError("execution mode không hợp lệ")
project = Path(PUBG_PROJECT_ROOT).resolve()
if USE_GOOGLE_DRIVE:
    from google.colab import drive
    drive.mount("/content/drive")
    project = Path(PUBG_PROJECT_ROOT).resolve()
    drive_root = Path("/content/drive/MyDrive").resolve()
    if not project.is_relative_to(drive_root) or project == drive_root:
        raise ValueError("Chọn thư mục project riêng bên trong MyDrive, không dùng MyDrive làm project")
elif project in {Path("/"), Path("/content"), Path("/content/drive")}:
    raise ValueError("Không dùng root runtime hoặc mount làm project")
if EXECUTION_MODE != "report_only":
    if not ALLOW_DATA_PROCESSING or (EXECUTION_MODE == "full" and not ALLOW_FULL_DATA):
        raise ValueError("Chưa cho phép xử lý/full-data cho nguồn này")
    for location in (Path(CODE_ROOT).resolve(), Path(KAGGLE_CACHE_ROOT).resolve()):
        if project.is_relative_to(location) or location.is_relative_to(project):
            raise ValueError("Project phải tách khỏi code/cache raw")
    # Check actual CUDA imports/count in a fresh child before downloading ~19GiB.
    subprocess.check_call([sys.executable, "-c", "import cupy,cuml; assert cupy.cuda.runtime.getDeviceCount() >= 1; print('cuML',cuml.__version__,'GPU count',cupy.cuda.runtime.getDeviceCount())"])
    SOURCE_DIRECTORY = download_source(SOURCE_DATASET, SOURCE_VERSION, KAGGLE_CACHE_ROOT, MIN_LOCAL_FREE_GIB, KAGGLE_LOGIN)
else:
    print("report_only: bỏ qua GPU/raw download; chỉ mount để đọc release.")
'''


def build(root=ROOT):
    root = Path(root)
    original = nbformat.read(root / "notebooks/PUBG_COURSEWORK.ipynb", as_version=4)
    notebook = copy.deepcopy(original)
    cells = {c.id: c for c in notebook.cells}
    source_hash = hashlib.sha256()
    files = sorted((root / "src").glob("*.py"))
    for path in files:
        source_hash.update(path.name.encode())
        source_hash.update(path.read_bytes())
    source_hash = source_hash.hexdigest()
    if source_hash != "4e3f9a191e589c963727c12bbf00ec656ee6bf17de0621ca6a6f520b3641dd3c":
        raise RuntimeError("Re-audit source compatibility before building a new Colab runtime")
    files += [root / "configs/project.yaml", root / "requirements.txt", root / "PUBG_RESEARCH_SPEC.md"]
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(root).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    data = stream.getvalue()
    payload, bundle_hash = base64.b64encode(data).decode("ascii"), hashlib.sha256(data).hexdigest()
    support = (root / "tools/colab_runtime.py").read_text(encoding="utf-8")
    imports = cells["bootstrap"].source.split("from IPython.display", 1)[1].split('if EXECUTION_MODE != "report_only":', 1)[0]
    imports = "from IPython.display" + imports
    cells["introduction"].source = INTRO
    cells["s00-method"].source = '<a id="S00"></a>\n## S00. Colab: môi trường, Kaggle Version3 và nơi lưu\n\nChạy cell1 cấu hình, cell2 môi trường; restart session một lần nếu được yêu cầu, rồi Run all. Cell3 kết nối Drive/tải raw, cell4 khởi tạo kiểm nguồn/đơn vị/GPU. Không mang checkpoint Kaggle sang Colab để ép reuse; đây là root mới với một GPU và software signature riêng.'
    cells["parameters"].source = PARAMETERS
    cells["bootstrap"].source = BOOTSTRAP.replace("__SOURCE_HASH__", source_hash).replace("__IMPORTS__", imports.rstrip())
    cells["s00-reading"].source = "Cách đọc: version tải cố định3, unit assumed_seconds không phải verified. GPU smoke48dòng chỉ kiểm backend/reload. Các guard RAM/VRAM/đĩa/output và G4 vẫn giữ. Checkpoint ghi ngay trong project Drive; không cần Save Version Kaggle. Drive mount không bảo đảm quota hoặc đồng bộ máy chủ. Không xóa/ép lock nếu writer cũ còn chạy."
    runner = cells["section-runner"].source
    runner = runner.replace('kaggle=Path("/kaggle/input").exists()', "kaggle=True")
    runner = runner[:runner.index("        if HANDOFF_EVERY_STAGE")]
    runner += '''        if stage == END_STAGE:
            try:
                print("Manifest Colab:", colab_handoff(ctx))
            except (RuntimeError, ValueError, MemoryError, OSError) as error:
                print("Chưa tạo được handoff; checkpoint stage vẫn cần kiểm:", str(error))
        else:
            print("Checkpoint đã ghi ở", ctx.manifest_path, "; chưa chứng minh đồng bộ Drive máy chủ.")
'''
    cells["section-runner"].source = runner
    for name in ("s07-execute", "s08-execute"):
        cells[name].source = cells[name].source.replace("Kế thừa [0, 1]", "Kế thừa [0] trên Colab")
    cells["s11-method"].source = '<a id="S11"></a>\n## S11. Đọc kết quả đã khóa\n\nreport_only bỏ qua cài môi trường, tải raw, prepare/copy project và S01-S10. Điền RELEASE_MANIFEST là release.json cụ thể trên Drive; môi trường/code phải chuẩn bị từ trước. Bảng/hình đọc từ snapshot đã kiểm, không lấy current outputs hay số fixture cũ làm kết quả PUBG. Notebook phát hành không nhúng output thực thi.'
    cells["s12-handover"].source = '''if EXECUTION_MODE != "report_only":
    display(pd.DataFrame([{"stage":s,"status":r.get("status"),"reason":r.get("reason","")} for s,r in ctx.manifest().items()]))
    print("Project:", ctx.root)
    print("Checkpoint:", ctx.manifest_path)
    print("Giữ cả src/config/data/outputs và notebook Colab; không chỉ tải một file prediction.")
    if not USE_GOOGLE_DRIVE:
        print("CẢNH BÁO: project chỉ ở runtime, có thể mất khi VM bị thu hồi.")
else:
    print("Chỉ đọc release:", RELEASE_MANIFEST)
'''
    cells["saved-output-method"].source = "### Kiểm đọc lại project Colab\n\nCell sau kiểm checksum/giải mã Parquet của handoff qua filesystem đang mount, có thể đọc nhiều GiB. Không gọi đây là đã lưu Kaggle Version hoặc xác nhận đồng bộ máy chủ Google. Project Drive là nơi ghi trực tiếp, không phải bản backup độc lập. Stage bị ngắt giữa fit không có checkpoint giữa fit; giữ writer lock và chỉ takeover khi chắc phiên cũ đã dừng. report_only không tạo handoff hoặc ghi lại project."
    cells["verify-saved-output"].source = '''if VERIFY_HANDOFF and EXECUTION_MODE != "report_only":
    display(pd.DataFrame([verify_colab_handoff(project_root, EXECUTION_MODE)]))
else:
    print("Không chạy kiểm handoff trong lượt này; không xác nhận cloud/Kaggle save.")
'''
    setup = '#@title 2. Cài môi trường và mở gói code đi kèm\n' + support
    setup += f'\nBUNDLED_CODE = {payload!r}\nBUNDLED_CODE_SHA256 = {bundle_hash!r}\n'
    setup += '''if EXECUTION_MODE not in {"full", "development", "report_only"}:
    raise ValueError("execution mode không hợp lệ")
if EXECUTION_MODE != "report_only":
    if not ALLOW_DATA_PROCESSING or (EXECUTION_MODE == "full" and not ALLOW_FULL_DATA):
        raise ValueError("Chưa cho phép xử lý/full-data")
    unpack_code(BUNDLED_CODE, BUNDLED_CODE_SHA256, CODE_ROOT)
    setup_environment(CODE_ROOT, CUDA_FAMILY, INSTALL_COLAB_DEPENDENCIES)
else:
    print("report_only: không giải nén/cài đặt; dùng code đã có trong project.")
'''
    notebook.cells[3:3] = [nbformat.v4.new_code_cell(setup, id="colab-environment"),
                           nbformat.v4.new_code_cell(DATA, id="colab-data")]
    notebook.metadata.pop("kaggle", None)
    notebook.metadata["accelerator"] = "GPU"
    notebook.metadata["colab"] = {"name": "PUBG_COURSEWORK_COLAB.ipynb", "provenance": []}
    notebook.metadata["pubg_colab"] = {"source_sha256": source_hash, "bundle_sha256": bundle_hash,
                                       "embedded_files": len(files), "support_sha256": hashlib.sha256(support.encode()).hexdigest()}
    for cell in notebook.cells:
        cell.metadata["id"] = cell.id
        if cell.cell_type == "code":
            cell.outputs, cell.execution_count = [], None
    next(c for c in notebook.cells if c.id == "colab-environment").metadata["cellView"] = "form"
    nbformat.validate(notebook)
    path = root / "notebooks/PUBG_COURSEWORK_COLAB.ipynb"
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        nbformat.write(notebook, stream)
    return path


if __name__ == "__main__":
    print(build())
