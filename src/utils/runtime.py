import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional


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
        info["total_ram_gb"] = "psutil_not_installed"
        info["cpu_count_logical"] = os.cpu_count()

    # Core data science package versions
    packages = ["numpy", "pandas", "pyarrow", "duckdb", "scipy", "sklearn", "yaml", "matplotlib", "seaborn"]
    pkg_versions = {}
    for pkg in packages:
        try:
            mod = __import__(pkg)
            pkg_versions[pkg] = getattr(mod, "__version__", "installed")
        except ImportError:
            pkg_versions[pkg] = "not_installed"
    info["packages"] = pkg_versions

    # GPU check if torch or tensorflow exists
    try:
        import torch  # type: ignore
        info["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            info["cuda_device_name"] = torch.cuda.get_device_name(0)
    except ImportError:
        info["cuda_available"] = False

    return info


def check_environment(
    target_dir: Optional[str] = ".",
    min_disk_gb: float = 5.0,
) -> Dict[str, Any]:
    """Verify environment health: write permissions, disk space, and core dependencies."""
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
    if not can_write:
        status = "critical"
        warnings.append(f"Directory {target_path} is not writable.")
    if free_gb < min_disk_gb:
        status = "warning" if status != "critical" else "critical"
        warnings.append(f"Low free disk space: {free_gb} GB < {min_disk_gb} GB required.")

    return {
        "status": status,
        "can_write": can_write,
        "free_disk_gb": free_gb,
        "total_disk_gb": total_gb,
        "warnings": warnings,
        "runtime": runtime_info,
    }
