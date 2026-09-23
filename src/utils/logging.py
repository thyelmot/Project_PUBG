import logging
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


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
