"""Colab transport/setup only; scientific code remains the frozen src bundle."""
import base64
import copy
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile


def unpack_code(payload, expected_hash, target):
    data = base64.b64decode(payload, validate=True)
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError("Embedded code checksum mismatch; use the original notebook")
    target = Path(target).resolve()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        expected = {"configs/project.yaml", "requirements.txt", "PUBG_RESEARCH_SPEC.md"}
        expected.update(n for n in names if re.fullmatch(r"src/[a-z_]+\.py", n))
        if len(names) != len(set(names)) or set(names) != expected or "src/io.py" not in names:
            raise ValueError("Unexpected embedded code paths")
        if sum(i.file_size for i in archive.infolist()) > 4 * 1024**2:
            raise ValueError("Embedded code is too large")
        for name in names:
            path = target.joinpath(*PurePosixPath(name).parts)
            if not path.resolve().is_relative_to(target):
                raise ValueError("Code path escapes target")
            if path.exists() and (not path.is_file() or path.read_bytes() != archive.read(name)):
                raise RuntimeError("Code folder contains different files; choose a new CODE_ROOT")
        # Validate every existing destination before writing anything.
        for name in names:
            path = target / name
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(name))
    return target


def environment_requirements(code_root, cuda_family):
    from packaging.requirements import Requirement
    if cuda_family not in {"cu12", "cu13"}:
        raise ValueError("CUDA_FAMILY must be cu12 or cu13, matching the installed CUDA toolkit")
    opposite = "cu13" if cuda_family == "cu12" else "cu12"
    for package in (f"cudf-{opposite}", f"cuml-{opposite}", f"cupy-cuda{opposite[2:]}x"):
        try:
            importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            continue
        raise RuntimeError("Conflicting CUDA family installed: " + package)
    requirements = [s.strip() for s in (Path(code_root) / "requirements.txt").read_text(encoding="utf-8").splitlines()
                    if s.strip() and not s.lstrip().startswith("#")]
    # 26.10 requires pandas3, outside the frozen core's pandas<3 contract.
    requirements += ["kagglehub==1.0.2", f"cuml-{cuda_family}==26.2.*", f"cudf-{cuda_family}==26.2.*",
                     f"cupy-cuda{cuda_family[2:]}x>=13.6,<14"]
    missing = []
    for line in requirements:
        requirement = Requirement(line)
        try:
            if importlib.metadata.version(requirement.name) not in requirement.specifier:
                missing.append(line)
        except importlib.metadata.PackageNotFoundError:
            missing.append(line)
    return requirements, missing


def setup_environment(code_root, cuda_family, install=True):
    if sys.platform != "linux":
        raise RuntimeError("This setup cell requires a Linux Colab GPU runtime")
    subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], check=True)
    nvcc = shutil.which("nvcc")
    if nvcc:
        toolkit = subprocess.check_output([nvcc, "--version"], text=True)
        match = re.search(r"release (\d+)\.", toolkit)
        if match and "cu" + match[1] != cuda_family:
            raise RuntimeError("CUDA_FAMILY does not match nvcc; set it to cu" + match[1])
    requirements, missing = environment_requirements(code_root, cuda_family)
    if missing:
        if not install:
            raise RuntimeError("Enable INSTALL_COLAB_DEPENDENCIES; missing: " + ", ".join(missing))
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *requirements])
        raise RuntimeError("Đã cài môi trường. Chọn Runtime > Restart session, rồi Run all lại. Không Disconnect and delete runtime. Không tiếp tục S01 trong kernel cũ.")
    print("Môi trường đã có các phiên bản yêu cầu; không cài lại.")


def download_source(dataset, version, cache_root, minimum_free_gib=55, login=False):
    # Source-bound time-unit approval must not silently transfer to another dataset/version.
    if dataset != "skihikingkevin/pubg-match-deaths" or type(version) is not int or version != 3:
        raise ValueError("This notebook is approved for skihikingkevin/pubg-match-deaths/versions/3 only")
    cache_root = Path(cache_root).resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(cache_root).free / 2**30
    if free < minimum_free_gib:
        raise MemoryError(f"Local disk free {free:.1f} GiB < reserve {minimum_free_gib}; raw download, extraction and SQL need local disk")
    if "kagglehub" in sys.modules and os.environ.get("KAGGLEHUB_CACHE") != str(cache_root):
        raise RuntimeError("kagglehub was loaded with another cache; restart session")
    os.environ["KAGGLEHUB_CACHE"] = str(cache_root)
    import kagglehub
    if login:
        kagglehub.login()  # Interactive/secret authentication; never print or save tokens in this notebook.
    handle = f"{dataset}/versions/{version}"
    root = Path(kagglehub.dataset_download(handle)).resolve()
    groups = {"aggregate": sorted(root.rglob("agg_match_stats*.csv")),
              "event": sorted(root.rglob("kill_match_stats*.csv"))}
    if any(not paths for paths in groups.values()):
        raise FileNotFoundError("Pinned Kaggle download lacks aggregate or death CSVs")
    if any(not p.resolve().is_relative_to(root) for paths in groups.values() for p in paths):
        raise ValueError("Source link escapes download root")
    print("Kaggle handle:", handle, "; không dùng latest")
    print("Raw cache:", root)
    for name, paths in groups.items():
        print(name, ":", len(paths), "files;", round(sum(p.stat().st_size for p in paths) / 2**30, 3), "GiB")
    print("Chỉ kiểm tên/dung lượng; S01 mới kiểm đầy đủ hash/schema/rows.")
    return str(root)


def configure_project(code_root, target, source_directory, gpu_ids, scope):
    from src.io import Context, load_config, publish
    from src.kaggle_runtime import prepare_project
    import yaml
    if gpu_ids != [0] or any(type(i) is not int for i in gpu_ids):
        raise ValueError("Colab variant explicitly uses GPU_IDS=[0]; no silent CPU/second-GPU fallback")
    target = prepare_project(code_root, target)
    original = load_config(target)
    cfg = copy.deepcopy(original)
    cfg["source"].update(directory=source_directory, version=3, license="CC0: Public Domain")
    cfg["storage"]["project_root"] = str(target)
    cfg["runtime"]["temp_directory"] = None  # /tmp runtime, not the mounted Drive project.
    for section in ("rq2", "rq3"):
        cfg[section].update(device="cuda", gpu_ids=gpu_ids)
    # Check completed checkpoints against the candidate configuration before replacing a good config.
    check = Context(target, scope)
    check.cfg = cfg
    validated, hashes = set(), {}
    for stage, record in check.manifest().items():
        if record.get("status") == "completed":
            check.require(stage, validated, hashes)
    if cfg != original:
        with tempfile.TemporaryDirectory(prefix="pubg-colab-config-") as folder:
            path = Path(folder) / "project.yaml"
            path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
            publish(path, target / "configs/project.yaml")
    return target


def colab_handoff(ctx):
    from src.io import read_json, write_json
    from src.kaggle_runtime import prepare_handoff
    path = prepare_handoff(ctx)
    value = read_json(path)
    value.update(platform="Colab", saved_version_verified=False,
                 instructions="Keep this complete project on Drive, including src/config/data/outputs. Mounted-file read-back is not remote-cloud or Kaggle Version confirmation.")
    return write_json(value, path)


def verify_colab_handoff(root, scope):
    from src.io import digest, read_json
    from src.kaggle_runtime import safe_file
    from src.storage import validate_prediction
    if scope not in {"full", "development"}:
        raise ValueError("Invalid scope")
    root = Path(root).resolve()
    value = read_json(safe_file(root, f"handoff_{scope}.json"))
    if (value.get("format") != 1 or value.get("platform") != "Colab"
            or value.get("project_id") != "pubg-coursework-2026-v5" or value.get("scope") != scope):
        raise ValueError("Invalid Colab handoff marker")
    entries = value.get("entries", [])
    names = [entry["path"] for entry in entries]
    required = {"configs/project.yaml", "src/io.py", f"outputs/{scope}/checkpoints/stages.json"}
    if len(names) != len(set(names)) or not required.issubset(names) or list(root.glob(f"outputs/{scope}/checkpoints/*.lock")):
        raise ValueError("Incomplete/duplicate/locked Colab handoff")
    by_name = {entry["path"]: entry for entry in entries}
    for entry in entries:
        path = safe_file(root, entry["path"])
        if path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise ValueError("Colab handoff checksum mismatch: " + entry["path"])
        if path.suffix == ".parquet":
            validate_prediction(path)
    records = read_json(safe_file(root, f"outputs/{scope}/checkpoints/stages.json"))
    if records != value["stages"] or any(r.get("status") == "running" for r in records.values()):
        raise ValueError("Handoff stage records mismatch/running")
    for record in records.values():
        for entry in record.get("artifacts", []):
            if entry["path"] not in by_name or by_name[entry["path"]]["sha256"] != entry["sha256"]:
                raise ValueError("Missing/mismatched stage artifact")
    return {"readback_verified": True, "entries": len(entries), "scope": scope,
            "environment": "mounted filesystem read-back; not remote-cloud confirmation",
            "kaggle_version_verified": False}
