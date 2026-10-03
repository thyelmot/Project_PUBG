import logging
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
import pandas as pd

from src.data.io import atomic_write_csv


_LOGGERS: Dict[str, logging.Logger] = {}


def setup_logger(
    name: str = "pubg_research",
    log_dir: Optional[str] = "./artifacts/logs",
    level: str = "INFO",
    log_to_file: bool = True,
    log_to_console: bool = True,
) -> logging.Logger:
    """Setup and cache a structured logger."""
    if name in _LOGGERS:
        return _LOGGERS[name]

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if log_to_console and not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
            except Exception:
                pass
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if log_to_file and log_dir:
        os.makedirs(log_dir, exist_ok=True)
        log_file = Path(log_dir) / f"{name}.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _LOGGERS[name] = logger
    return logger


def get_logger(name: str = "pubg_research") -> logging.Logger:
    """Retrieve logger or initialize default."""
    if name not in _LOGGERS:
        return setup_logger(name)
    return _LOGGERS[name]


def log_stage(
    stage: str,
    status: str,
    logger: Optional[logging.Logger] = None,
    **kwargs: Any,
) -> None:
    """Log a structured pipeline stage transition."""
    log = logger or get_logger()
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "status": status,
        "inputs": kwargs.pop("inputs", None),
        "outputs": kwargs.pop("outputs", None),
        "counts": kwargs.pop("counts", None),
        "warnings": kwargs.pop("warnings", None),
        "config_hash": kwargs.pop("config_hash", None),
        "version": kwargs.pop("version", None),
        "memory_gb": kwargs.pop("memory_gb", None),
        "disk_gb": kwargs.pop("disk_gb", None),
        **kwargs,
    }
    log.info(f"STAGE_EVENT: {json.dumps(entry, default=str)}")


def log_metrics(
    experiment_id: str,
    metrics: Dict[str, Any],
    stage: str = "evaluation",
    logger: Optional[logging.Logger] = None,
) -> None:
    """Log experiment metrics in machine-readable structured format."""
    log = logger or get_logger()
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment_id": experiment_id,
        "stage": stage,
        "metrics": metrics,
    }
    log.info(f"METRIC_EVENT: {json.dumps(entry, default=str)}")


def _replace_stage_rows(path: Path, stage: str, rows: pd.DataFrame) -> None:
    """Replace one stage's rows in a canonical CSV without numbered copies."""
    path = Path(path)
    previous = pd.read_csv(path) if path.is_file() else pd.DataFrame(columns=rows.columns)
    if "stage" in previous:
        previous = previous[previous["stage"] != stage]
    atomic_write_csv(path, pd.concat([previous, rows], ignore_index=True))


def write_handover(
    path: Path,
    *,
    stage: str,
    artifacts: Mapping[str, Any],
    status: str,
    writer_id: str,
    version: str,
    error: Optional[str] = None,
    next_step: str = "",
) -> None:
    """Persist the one-row team handover contract for a notebook stage."""
    row = pd.DataFrame([{
        "stage": stage,
        "status": status,
        "writer_id": writer_id,
        "version": version,
        "artifact_paths": "; ".join(f"{k}={v}" for k, v in sorted(artifacts.items())),
        "error": error,
        "next_step": next_step,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }])
    _replace_stage_rows(path, stage, row)


def write_figure_metadata(path: Path, *, stage: str, artifacts: Mapping[str, Any], details=None) -> None:
    """Record a minimal catalog row for each generated figure."""
    figures = [Path(value) for value in artifacts.values()
               if Path(value).suffix.lower() in {".png", ".jpg", ".jpeg", ".svg", ".pdf"}]
    rows = pd.DataFrame([{
        "stage": stage, "path": str(figure), "title": figure.stem.replace("_", " "),
        "caption": "Diagnostic: đọc caption và phạm vi trong notebook; chưa phải hình báo cáo chính thức.",
        "report_ready": False, "created_at": datetime.now(timezone.utc).isoformat(),
        **(details or {}).get(figure.name, {}),
    } for figure in figures])
    if rows.empty:
        rows = pd.DataFrame(columns=["stage", "path", "title", "caption", "report_ready", "created_at"])
    _replace_stage_rows(path, stage, rows)
