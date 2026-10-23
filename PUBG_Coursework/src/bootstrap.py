"""Executed by path before importing src, so stale packages cannot hide the guard."""
import hashlib
import importlib.metadata
import sys
from pathlib import Path


def check_bundle(root,expected,expected_hash=None):
    import yaml
    from packaging.requirements import Requirement
    root=Path(root).resolve()
    cfg=yaml.safe_load((root/"configs/project.yaml").read_text(encoding="utf-8"))
    if cfg.get("spec_version")!=expected:
        raise RuntimeError(f"Notebook requires code {expected}, found {cfg.get('spec_version')}. Update the code Dataset and restart kernel.")
    h=hashlib.sha256()
    for path in sorted((root/"src").glob("*.py")):
        h.update(path.name.encode());h.update(path.read_bytes())
    identity=(str(root),h.hexdigest())
    if expected_hash is not None and identity[1]!=expected_hash:
        raise RuntimeError("Notebook/code source checksum mismatch. Upload the matching code ZIP and notebook, then restart kernel.")
    loaded=[name for name in sys.modules if name=="src" or name.startswith("src.")]
    if loaded and getattr(sys,"_pubg_bundle_identity",None)!=identity:
        raise RuntimeError("Cached src differs or was imported before bootstrap. Restart kernel, then Run All.")
    problems=[]
    for line in (root/"requirements.txt").read_text(encoding="utf-8").splitlines():
        line=line.strip()
        if not line or line.startswith("#"):continue
        requirement=Requirement(line)
        try:
            version=importlib.metadata.version(requirement.name)
            if version not in requirement.specifier:problems.append(f"{requirement.name} {version}, requires {requirement.specifier}")
        except importlib.metadata.PackageNotFoundError:problems.append(requirement.name+" missing")
    if problems:
        raise RuntimeError("Dependency mismatch: "+"; ".join(problems)+". Install requirements, restart kernel, then Run All.")
    sys._pubg_bundle_identity=identity
    return {"code_version":expected,"source_sha256":identity[1],"import_root":str(root)}
