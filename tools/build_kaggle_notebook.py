"""Refresh the canonical notebook binding and the audited Version-6 S08 TSQR profile."""
from pathlib import Path
import hashlib
import re

import nbformat

ROOT = Path(__file__).resolve().parents[1]

PARAMETERS = '''# Khôi phục nguyên S01-S07 từ Version6; chỉ tính S08 bằng OLS chia khối.
PUBG_STORAGE_MODE = "local"
PUBG_PROJECT_ROOT = "/kaggle/working/PUBG_Coursework_v511_S08_matrixdisk"
PUBG_REQUIRE_EXISTING_PROJECT = True
PUBG_BATCH_ROWS = 50000
EXECUTION_MODE = "full"
CODE_INPUT = "/kaggle/input/datasets/quangthinng/pubg-coursework-code"
SOURCE_DIRECTORY = "/kaggle/input/datasets/skihikingkevin/pubg-match-deaths"
SOURCE_VERSION = 3
SOURCE_LICENSE = "CC0: Public Domain"
ALLOW_DATA_PROCESSING = True
ALLOW_FULL_DATA = True
START_STAGE = "S08"
END_STAGE = "S08"
RESUME_INPUT = "/kaggle/input/notebooks/quangthinng/pubg-v3/PUBG_Coursework_v511_S07_profiles"
RESUME_VERSION = "quangthinng/pubg-v3/versions/6"
ALLOW_CPU_GPU_RESUME = False
ALLOW_S07_TSQR_RESUME = True  # Chỉ nhập S01-S07 đã kiểm; không huấn luyện lại KMeans.
S01_IMPORT_ROOT = ""
CLEANUP_IMPORTED_510 = False
RELEASE_MANIFEST = ""
SAVED_OUTPUT_ROOT = ""
SAVED_VERSION = ""
RUN_GPU_SMOKE = True  # Kiểm cuML và QR trên 48 dòng tổng hợp/GPU, không tính lại S01-S07.
INSTALL_DEPENDENCIES = False  # Không dùng nhánh cài rồi yêu cầu restart của S00.
INSTALL_RESUME_ENVIRONMENT = True  # Chỉ khớp DuckDB bản lưu và bốn yêu cầu runtime trước import src.
PUBG_WRITER_ID = ""
PUBG_FORCE_STAGE_TAKEOVER = False
HANDOFF_EVERY_STAGE = False
SOURCE_MODE_EVIDENCE = ""  # Kế thừa evidence từ config bản lưu.
SOURCE_TIME_UNIT_STATUS = "assumed_seconds"
SOURCE_TIME_UNIT_EVIDENCE = ""
SOURCE_TIME_UNIT_ASSUMPTION_APPROVED = True
SOURCE_TIME_UNIT_ASSUMPTION_SCOPE = "skihikingkevin/pubg-match-deaths/versions/3"
'''


ENVIRONMENT_SETUP = '''# BEGIN RESUME ENVIRONMENT: install before importing computational modules.
if INSTALL_RESUME_ENVIRONMENT and RESUME_INPUT and EXECUTION_MODE != "report_only":
    import json, platform, importlib
    from importlib.metadata import version, PackageNotFoundError
    from packaging.requirements import Requirement
    from packaging.version import Version
    producer_software = json.loads((Path(RESUME_INPUT)/("handoff_"+EXECUTION_MODE+".json")).read_text(encoding="utf-8"))["software"]
    if producer_software["python"] != platform.python_version():
        raise RuntimeError("Python khác bản lưu; chọn môi trường tương thích, không ép checkpoint")
    duckdb_version = str(Version(producer_software["duckdb"]))
    required = ["duckdb=="+duckdb_version, "nbclient>=0.10,<1", "nbconvert>=7.16.6,<8", "psutil>=6,<8"]
    to_install = []
    for text in required:
        requirement = Requirement(text)
        try:
            if version(requirement.name) not in requirement.specifier:to_install.append(text)
        except PackageNotFoundError:to_install.append(text)
    if to_install:
        if "duckdb" in sys.modules and sys.modules["duckdb"].__version__ != duckdb_version:
            raise RuntimeError("DuckDB cũ còn trong RAM; restart kernel rồi chạy lại S00")
        print("Chuẩn bị thư viện khôi phục:", to_install)
        subprocess.check_call([sys.executable,"-m","pip","install",*to_install])
        importlib.invalidate_caches()
    else:
        print("Thư viện khôi phục đã phù hợp; không cài lại.")
# END RESUME ENVIRONMENT
'''


def build(root=ROOT):
    root = Path(root)
    path = root / "notebooks/PUBG_COURSEWORK.ipynb"
    nb = nbformat.read(path, as_version=4)
    cells = {cell.id:cell for cell in nb.cells}
    cells["parameters"].source = PARAMETERS.rstrip()
    notices={
        "introduction":"Cấu hình tiếp tục hiện tại: nhập S01-S07 từ Version6 đã lưu, chỉ tính S08 tại root mới v511_S08_matrixdisk. Bản22/10 giữ sửa CuPy và tách JOIN khỏi thống kê/sắp xếp ma trận qua Parquet tạm, một SQL thread mỗi pha, không tăng giới hạn2GB. Giữ GPU smoke bắt buộc. Không sửa Output Input hoặc huấn luyện lại KMeans. Cần cập nhật cả Dataset code và notebook, pin OutputVersion6/rawVersion3. Các mô tả bản cũ bên dưới là lịch sử; S08 mới dùng OLS QR chia khối được người dùng duyệt, không lấy mẫu. Chưa nghiệm thu S08 toàn nguồn trên CUDA.",
        "s08-intro":"Đường S08 được duyệt 21/10/2026: rq3.solver=tsqr sau nhập Version6 có kiểm. Log/imputer/missing indicators/StandardScaler học trên toàn train; QR GPU tối đa50000dòng mỗi khối, gộp R và giải SVD nhỏ với rank cutoff theo n_train gốc. Không normal equations/SGD/mean-of-chunk-models, không đổi dữ liệu hoặc G4. Baseline mean/median toàn train, bins Type7 sort đĩa. Đây là thay solver số học, không hứa hệ số bit-identical cuML; smoke và resource guard vẫn bắt buộc. Nhánh dense cũ chỉ dùng khi không chọn tsqr. Mô tả5.9 dưới đây là lịch sử, không mô tả nhánh tsqr hiện tại."}
    for cell_id,notice in notices.items():
        text=re.sub(r"\n\n<!-- S08 TSQR NOTICE -->.*?<!-- END S08 TSQR NOTICE -->", "", cells[cell_id].source, flags=re.S)
        cells[cell_id].source=text+"\n\n<!-- S08 TSQR NOTICE -->\n"+notice+"\n<!-- END S08 TSQR NOTICE -->"
    bootstrap = cells["bootstrap"].source
    bootstrap = re.sub(r"# BEGIN RESUME ENVIRONMENT:.*?# END RESUME ENVIRONMENT\n", "", bootstrap, flags=re.S)
    bootstrap = bootstrap.replace("import runpy\n", ENVIRONMENT_SETUP+"import runpy\n", 1)
    bootstrap = bootstrap.replace("RESUME_INPUT or CODE_INPUT", "CODE_INPUT or RESUME_INPUT")
    old = "restore_handoff(RESUME_INPUT,project_root,EXECUTION_MODE,SOURCE_DIRECTORY,RESUME_VERSION)"
    new = "restore_handoff(RESUME_INPUT,project_root,EXECUTION_MODE,SOURCE_DIRECTORY,RESUME_VERSION,code_input=CODE_INPUT or None,allow_cpu_gpu=ALLOW_CPU_GPU_RESUME,allow_s07_tsqr=ALLOW_S07_TSQR_RESUME)"
    bootstrap = bootstrap.replace(old, new)
    bootstrap = bootstrap.replace("allow_cpu_gpu=ALLOW_CPU_GPU_RESUME)",
                                  "allow_cpu_gpu=ALLOW_CPU_GPU_RESUME,allow_s07_tsqr=ALLOW_S07_TSQR_RESUME)")
    h = hashlib.sha256()
    for source in sorted((root / "src").glob("*.py")):
        h.update(source.name.encode()); h.update(source.read_bytes())
    bootstrap, count = re.subn(r"('5\.11-normalized-storage', ')[0-9a-f]{64}(')",
                               lambda m:m[1]+h.hexdigest()+m[2], bootstrap)
    if count != 1:raise ValueError("Expected one canonical source binding")
    cells["bootstrap"].source = bootstrap
    runner = cells["section-runner"].source
    runner = runner.replace("if stage == 'S05' and END_STAGE >= 'S07':",
                            "if (stage == 'S05' and END_STAGE >= 'S07') or stage in {'S07', 'S08'}:")
    cells["section-runner"].source = runner
    for cell in nb.cells:
        if cell.cell_type == "code":cell.outputs, cell.execution_count = [], None
    nbformat.validate(nb)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        nbformat.write(nb, stream)
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8")
    marker = "### Khối S00 đầy đủ cho nguồn PUBG Version 3 đã chọn"
    start = text.index("```python\n", text.index(marker)) + len("```python\n")
    end = text.index("```", start)
    text = text[:start]+PARAMETERS+text[end:]
    with readme.open("w", encoding="utf-8", newline="\n") as stream:stream.write(text)
    return h.hexdigest()


if __name__ == "__main__":print(build())
