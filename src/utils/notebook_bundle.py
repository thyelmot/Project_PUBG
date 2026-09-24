"""Build self-contained Colab notebooks from the project's existing source files."""

import base64
import io
from pathlib import Path
import zipfile


STORAGE_OPTIONS_CELL = '''# @title Chọn nơi lưu dữ liệu { display-mode: "form" }
# @markdown `runtime`: không cần Drive, phù hợp notebook All-in-One.
# @markdown `drive`: lưu nối tiếp 13 notebook trong cùng thư mục Google Drive.
PUBG_STORAGE_MODE = "runtime"  # @param ["runtime", "drive"]
PUBG_DRIVE_PROJECT_ROOT = "/content/drive/MyDrive/PUBG_Project/Project_PUBG"  # @param {type:"string"}
'''


def bootstrap_source(project_root: Path) -> str:
    """Embed only code/config/docs; no raw data, credentials or research outputs."""
    files = [project_root / "requirements.txt", project_root / "README.md"]
    for directory, pattern in [("src", "*.py"), ("configs", "*.yaml"), ("tests", "test_*.py")]:
        files.extend(sorted((project_root / directory).rglob(pattern)))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(project_root).as_posix())
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    payload = base64.b64encode(stream.getvalue()).decode("ascii")
    return '''# Bootstrap: runtime mode needs no Drive; drive mode persists stage outputs.
import base64
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import zipfile

IN_COLAB = "google.colab" in sys.modules or bool(os.environ.get("COLAB_RELEASE_TAG"))
PUBG_STORAGE_MODE = globals().get("PUBG_STORAGE_MODE", "runtime").strip().lower()
if PUBG_STORAGE_MODE not in {"runtime", "drive"}:
    raise ValueError("PUBG_STORAGE_MODE must be 'runtime' or 'drive'")

if PUBG_STORAGE_MODE == "drive":
    if not IN_COLAB:
        raise RuntimeError("Drive mode is available only on Google Colab")
    from google.colab import drive
    drive.mount("/content/drive")
    PROJECT_ROOT = Path(globals().get(
        "PUBG_DRIVE_PROJECT_ROOT", "/content/drive/MyDrive/PUBG_Project/Project_PUBG"
    )).expanduser().resolve()
else:
    _candidates = ([Path("/content/Project_PUBG")] if IN_COLAB else
                   [Path.cwd(), *Path.cwd().parents])
    _candidates += [p / "Project_PUBG" for p in list(_candidates)]
    PROJECT_ROOT = next((p.resolve() for p in _candidates
                         if (p / "configs/data.yaml").is_file() and (p / "src/utils/config.py").is_file()), None)
if PROJECT_ROOT is None:
    PROJECT_ROOT = (Path("/content") if IN_COLAB else Path.cwd()) / "Project_PUBG"

if not (PROJECT_ROOT / "configs/data.yaml").is_file() or not (PROJECT_ROOT / "src/utils/config.py").is_file():
    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)
    _bundle = zipfile.ZipFile(io.BytesIO(base64.b64decode(BUNDLE_PAYLOAD)))
    for _entry in _bundle.infolist():
        _target = (PROJECT_ROOT / _entry.filename).resolve()
        if not _target.is_relative_to(PROJECT_ROOT.resolve()):
            raise ValueError("Invalid bundled path")
        if not _target.exists():
            _target.parent.mkdir(parents=True, exist_ok=True)
            _target.write_bytes(_bundle.read(_entry))
    _bundle.close()

os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if globals().get("PUBG_INSTALL_DEPENDENCIES", IN_COLAB) and not globals().get("_PUBG_PACKAGES_READY", False):
    _requirements = {
        "numpy": "numpy>=1.24.0", "pandas": "pandas>=2.0.0",
        "pyarrow": "pyarrow>=12.0.0", "duckdb": "duckdb>=0.9.0",
        "scipy": "scipy>=1.10.0", "sklearn": "scikit-learn>=1.3.0",
        "yaml": "pyyaml>=6.0",
    }
    _missing = [spec for module, spec in _requirements.items() if importlib.util.find_spec(module) is None]
    if _missing:
        print("Installing missing packages:", ", ".join(_missing))
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--prefer-binary", *_missing])
    _PUBG_PACKAGES_READY = True

if PUBG_STORAGE_MODE == "drive":
    os.environ["PUBG_SESSION_DRIVE_ROOT"] = str(PROJECT_ROOT)
    os.environ["PUBG_SESSION_TEMP_DIR"] = str(globals().get("PUBG_RUNTIME_TEMP_DIR", "/content/temp"))
else:
    os.environ.pop("PUBG_SESSION_DRIVE_ROOT", None)
    os.environ.pop("PUBG_SESSION_TEMP_DIR", None)
from src.utils.config import load_config, resolve_paths
cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
for _path in paths.values():
    _path.mkdir(parents=True, exist_ok=True)
print("Project:", PROJECT_ROOT)
print("Storage:", paths["data_root"], "| Results:", paths["reports_root"])
if PUBG_STORAGE_MODE == "drive":
    print("Storage mode: Google Drive. Stage outputs persist for the next notebook.")
else:
    print("Storage mode: runtime. No Drive authorization required; export before reset.")
'''.replace("BUNDLE_PAYLOAD", repr(payload))


EXPORT_CELL = '''# Export results to your computer; no Drive authorization.
# Set True only when you also want the potentially large processed/interim data.
INCLUDE_DATA_CHECKPOINTS = False
import zipfile
from pathlib import Path

export_path = PROJECT_ROOT / "PUBG_results.zip"
roots = {"reports": paths["reports_root"], "figures": paths["figures"],
         "configs": PROJECT_ROOT / "configs", "artifacts": paths["artifacts_root"]}
if INCLUDE_DATA_CHECKPOINTS:
    roots.update({"data/interim": paths["interim"], "data/processed": paths["processed"]})
with zipfile.ZipFile(export_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
    for prefix, root in roots.items():
        for file in sorted(root.rglob("*")):
            relative = file.relative_to(root)
            if file.is_file() and not any(p in {"temp", "duckdb_temp", "__pycache__"} for p in relative.parts):
                archive.write(file, str(Path(prefix) / relative))
print("Export:", export_path, "bytes:", export_path.stat().st_size)
if IN_COLAB:
    from google.colab import files
    files.download(str(export_path))
else:
    from IPython.display import FileLink, display
    display(FileLink(str(export_path.relative_to(PROJECT_ROOT))))
'''
