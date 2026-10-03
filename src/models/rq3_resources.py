"""Measured resource gate for development fits; never choose another estimator."""
from datetime import datetime, timezone
import numbers


def resource_snapshot(frame, features, device, limit_gb):
    from src.utils.runtime import collect_runtime_info
    runtime = collect_runtime_info()
    footprint = int(frame.memory_usage(index=True, deep=True).sum())
    matrix = len(frame) * len(features) * 8
    # ponytail: conservative working-copy estimate, not a measured peak or a RAM guarantee.
    estimated = footprint + matrix * 6 + len(frame) * 8 * 8
    free = runtime.get("available_ram_gb")
    available = float(free) * 1024**3 if isinstance(free, numbers.Real) else None
    result = {"measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_device": device, "dataframe_bytes": footprint,
        "estimated_working_bytes": estimated, "ram_available_bytes": available,
        "configured_memory_bytes": float(limit_gb) * 1024**3,
        "vram_free_bytes": None, "vram_total_bytes": None,
        "status": "ready", "reason_code": None}
    if float(limit_gb) <= 0:
        raise ValueError("max_memory_gb must be positive")
    if available is None:
        result.update(status="blocked", reason_code="ram_measurement_unavailable")
    elif estimated > min(available, result["configured_memory_bytes"]):
        result.update(status="resource_limited", reason_code="estimated_host_memory_exceeds_budget")
    if device == "cuda" and features:
        try:
            from src.models.compute import compute_info
            compute_info(device)
            import cupy
            free, total = cupy.cuda.runtime.memGetInfo()
            result.update(vram_free_bytes=int(free), vram_total_bytes=int(total))
            if matrix * 4 > free:
                result.update(status="resource_limited", reason_code="estimated_gpu_memory_exceeds_budget")
        except (ImportError, RuntimeError) as error:
            result.update(status="blocked", reason_code="gpu_unavailable", error=str(error))
    return result
