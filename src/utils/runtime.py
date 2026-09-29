import json
import os
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def collect_runtime_info() -> Dict[str, Any]:
    """Collect comprehensive hardware, OS, and package runtime information."""
    info: Dict[str, Any] = {
        "os_name": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
    }

    # Memory info
    try:
        import psutil  # type: ignore
        vm = psutil.virtual_memory()
        info["total_ram_gb"] = round(vm.total / (1024 ** 3), 2)
        info["available_ram_gb"] = round(vm.available / (1024 ** 3), 2)
        info["cpu_count_logical"] = psutil.cpu_count(logical=True)
        info["cpu_count_physical"] = psutil.cpu_count(logical=False)
    except ImportError:
        info["total_ram_gb"] = "unavailable"
        try:
            mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
            for field, key in (("MemTotal", "total_ram_gb"), ("MemAvailable", "available_ram_gb")):
                info[key] = round(int(mem[field].split()[0]) / (1024 ** 2), 2)
        except (OSError, KeyError, ValueError):
            pass
        info["cpu_count_logical"] = os.cpu_count()

    # Core data science package versions
    # Note: sklearn module name maps to scikit-learn package; yaml maps to pyyaml.
    packages = ["numpy", "pandas", "pyarrow", "duckdb", "scipy", "sklearn", "yaml", "matplotlib", "seaborn"]
    pkg_versions = {}
    for pkg in packages:
        try:
            mod = __import__(pkg)
            pkg_versions[pkg] = getattr(mod, "__version__", "installed")
        except ImportError:
            pkg_versions[pkg] = "not_installed"
    info["packages"] = pkg_versions

    # GPU check via cuML or torch (cuML is the project GPU backend)
    info["cuda_available"] = False
    try:
        import cuml  # type: ignore
        info["cuda_available"] = True
        info["cuml_version"] = cuml.__version__
    except ImportError:
        pass
    if not info["cuda_available"]:
        try:
            import torch  # type: ignore
            info["cuda_available"] = torch.cuda.is_available()
            if torch.cuda.is_available():
                info["cuda_device_name"] = torch.cuda.get_device_name(0)
        except ImportError:
            pass

    return info


def check_environment(
    target_dir: Optional[str] = ".",
    min_disk_gb: float = 5.0,
    raise_on_critical: bool = False,
) -> Dict[str, Any]:
    """Verify environment health: write permissions, disk space, and core dependencies.

    Args:
        target_dir: Directory to check for write permission and disk space.
        min_disk_gb: Minimum acceptable free disk in GB.
        raise_on_critical: If True, raise RuntimeError when status is 'critical'
            with a specific remediation message. Default False preserves the
            existing behaviour of returning the report without raising.
    """
    target_path = Path(target_dir).resolve()
    target_path.mkdir(parents=True, exist_ok=True)

    # Check write permission
    test_file = target_path / ".write_test.tmp"
    can_write = False
    try:
        with open(test_file, "w") as f:
            f.write("test")
        test_file.unlink()
        can_write = True
    except Exception:
        can_write = False

    # Check disk space
    disk = shutil.disk_usage(target_path)
    free_gb = round(disk.free / (1024 ** 3), 2)
    total_gb = round(disk.total / (1024 ** 3), 2)

    runtime_info = collect_runtime_info()

    status = "healthy"
    warnings = []
    remediation: List[str] = []
    if not can_write:
        status = "critical"
        warnings.append(f"Directory {target_path} is not writable.")
        remediation.append(
            f"Write permission denied on {target_path}. "
            "In Colab Drive mode: verify the shared folder has Editor access and re-mount. "
            "In runtime mode: the Colab VM may have a full /content; restart the runtime. "
            "Locally: check OS permissions with `ls -la` and grant write access."
        )
    if free_gb < min_disk_gb:
        new_status = "warning" if status == "healthy" else "critical"
        status = new_status
        warnings.append(f"Low free disk space: {free_gb} GB < {min_disk_gb} GB required.")
        remediation.append(
            f"Only {free_gb} GB free on the volume holding {target_path}. "
            "This is the runtime/VM disk, not Google Drive quota. "
            "Delete temp files in artifacts/logs/temp or reduce DuckDB spill usage. "
            "For Colab, a factory reset gives ~78 GB ephemeral disk."
        )

    result = {
        "status": status,
        "can_write": can_write,
        "free_disk_gb": free_gb,
        "total_disk_gb": total_gb,
        "warnings": warnings,
        "remediation": remediation,
        "runtime": runtime_info,
    }

    if raise_on_critical and status == "critical":
        msg = " | ".join(remediation) if remediation else " | ".join(warnings)
        raise RuntimeError(f"Environment check CRITICAL — cannot proceed. {msg}")

    return result


def estimate_disk_budget(raw_dir: Path) -> Dict[str, float]:
    """Estimate disk needs (GB) for the pipeline from observed raw data size.

    Returns a dict with keys: raw_gb, interim_gb, processed_gb,
    spill_gb, staging_gb, total_estimated_gb, note.
    All values are estimates, not guarantees.
    """
    raw_gb = 0.0
    if raw_dir.exists():
        for f in raw_dir.rglob("*"):
            if f.is_file():
                raw_gb += f.stat().st_size
        raw_gb = round(raw_gb / (1024 ** 3), 3)

    # Conservative expansion ratios based on observed PUBG pipeline:
    # CSV → Parquet ZSTD ~0.4x; interim keeps both staging + cleaned; processed ~0.7x raw.
    staging_gb = round(raw_gb * 0.5, 3)   # batch staging shards (Parquet ZSTD)
    interim_gb = round(raw_gb * 0.9, 3)   # cleaned aggregate + metadata + split parquets
    processed_gb = round(raw_gb * 0.7, 3) # player_match + features parquets
    # ponytail: spill ratio assumes DuckDB 2 GB memory_limit; raise if memory_limit increased.
    spill_gb = round(raw_gb * 0.3, 3)     # DuckDB temp spill at 2 GB memory_limit
    total_estimated_gb = round(staging_gb + interim_gb + processed_gb + spill_gb, 3)

    return {
        "raw_gb": raw_gb,
        "staging_gb": staging_gb,
        "interim_gb": interim_gb,
        "processed_gb": processed_gb,
        "spill_gb": spill_gb,
        "total_estimated_gb": total_estimated_gb,
        "note": (
            "Estimates from raw data size. Ratios: staging=0.5x, interim=0.9x, "
            "processed=0.7x, spill=0.3x raw. This is runtime/VM disk, not Drive quota."
        ),
    }


def save_runtime_snapshot(
    output_path: Path,
    project_root: Path,
    cfg: Dict[str, Any],
    doc_hashes: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Save a complete runtime snapshot JSON for audit and reproducibility.

    Captures: timestamp, runtime info, config summary, source hash, doc hashes.
    Always writes atomically (temp file then rename).

    Args:
        output_path: Destination JSON file path.
        project_root: Project root directory.
        cfg: Loaded config dict.
        doc_hashes: Optional mapping of doc name → sha256 hex string.
    """
    from src.utils.hashing import hash_file  # local import to avoid circular dependency

    generator_path = project_root / "src" / "utils" / "generate_notebooks.py"
    snapshot: Dict[str, Any] = {
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "runtime": collect_runtime_info(),
        "config_summary": {
            "runtime_mode": cfg.get("runtime", {}).get("mode"),
            "random_state": cfg.get("runtime", {}).get("random_state"),
            "duckdb_threads": cfg.get("runtime", {}).get("duckdb", {}).get("threads"),
            "duckdb_memory_limit": cfg.get("runtime", {}).get("duckdb", {}).get("memory_limit"),
            "chunk_size": cfg.get("runtime", {}).get("chunk_size"),
            "storage_backend": cfg.get("runtime", {}).get("storage_backend"),
            "active_environment": cfg.get("paths", {}).get("active_environment"),
            "mode_strategy": cfg.get("rq2", {}).get("mode_strategy"),
            "rq2_device": cfg.get("rq2", {}).get("device"),
            "rq3_device": cfg.get("rq3", {}).get("device"),
        },
        "source_hashes": {
            "generate_notebooks.py": hash_file(generator_path) if generator_path.is_file() else "missing",
        },
        "doc_hashes": doc_hashes or {},
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(output_path)
    return snapshot
