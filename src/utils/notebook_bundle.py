"""Build self-contained Colab notebooks from the project's existing source files."""

import base64
import io
from pathlib import Path
import zipfile


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
    return '''# Bootstrap: bundled project code, no Google Drive authorization.
import base64
import io
import os
from pathlib import Path
import subprocess
import sys
import zipfile

IN_COLAB = "google.colab" in sys.modules or bool(os.environ.get("COLAB_RELEASE_TAG"))
_candidates = [Path.cwd(), *Path.cwd().parents, Path("/content/Project_PUBG")]
_candidates += [p / "Project_PUBG" for p in list(_candidates)]
PROJECT_ROOT = next((p.resolve() for p in _candidates
                     if (p / "configs/data.yaml").is_file() and (p / "src/utils/config.py").is_file()), None)
if PROJECT_ROOT is None:
    PROJECT_ROOT = (Path("/content") if IN_COLAB else Path.cwd()) / "Project_PUBG"
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
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "-r", str(PROJECT_ROOT / "requirements.txt")])
    _PUBG_PACKAGES_READY = True

from src.utils.config import load_config, resolve_paths
cfg = load_config(str(PROJECT_ROOT / "configs"))
paths = resolve_paths(cfg)
for _path in paths.values():
    _path.mkdir(parents=True, exist_ok=True)
print("Project:", PROJECT_ROOT)
print("Storage:", paths["data_root"], "| Results:", paths["reports_root"])
print("No Drive mount or account token required. Export results before resetting the runtime.")
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
