import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional
import yaml


CONFIG_FILES = [
    "data.yaml",
    "schema.yaml",
    "paths.yaml",
    "preprocessing.yaml",
    "features.yaml",
    "eda.yaml",
    "rq2.yaml",
    "rq3.yaml",
    "models.yaml",
    "runtime.yaml",
]


def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Safely load a single YAML file."""
    if not file_path.is_file():
        raise FileNotFoundError(f"Config file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        content = yaml.safe_load(f)
    return content or {}


def load_config(config_dir: str = "configs", base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Load all 10 core YAML configuration files into a unified dictionary."""
    base = Path(base_dir) if base_dir else Path.cwd()
    cfg_dir = (base / config_dir) if not Path(config_dir).is_absolute() else Path(config_dir)

    if not cfg_dir.is_dir():
        # Fallback to check relative to Project_PUBG
        fallback = base / "Project_PUBG" / config_dir
        if fallback.is_dir():
            cfg_dir = fallback
        else:
            raise FileNotFoundError(f"Config directory does not exist: {cfg_dir}")

    config: Dict[str, Any] = {}
    for filename in CONFIG_FILES:
        key = filename.replace(".yaml", "")
        file_path = cfg_dir / filename
        config[key] = load_yaml(file_path)

    # Attach base directory
    config["_project_root"] = str(cfg_dir.parent.resolve())
    # Preserve the notebook's storage selection across every stage config reload.
    session_root = os.environ.get("PUBG_SESSION_DRIVE_ROOT")
    if session_root and Path(session_root).resolve() == cfg_dir.parent.resolve():
        config["paths"]["environments"]["drive"] = {
            "raw_root": "./data/raw", "data_root": "./data",
            "artifacts_root": "./artifacts", "reports_root": "./reports",
            "figures_root": "./figures",
            "temp_dir": os.environ.get("PUBG_SESSION_TEMP_DIR", "/content/temp"),
        }
        config["paths"]["active_environment"] = "drive"
    return config


def resolve_paths(cfg: Dict[str, Any]) -> Dict[str, Path]:
    """Resolve logical paths according to active environment (local / colab)."""
    paths_cfg = cfg.get("paths", {})
    env_name = paths_cfg.get("active_environment", "auto")
    if env_name == "auto":
        env_name = "colab" if "google.colab" in sys.modules or os.environ.get("COLAB_RELEASE_TAG") else "local"
    if env_name not in paths_cfg.get("environments", {}):
        raise ValueError(f"Unknown paths environment: {env_name}")
    env_paths = paths_cfg.get("environments", {}).get(env_name, {})

    project_root = Path(cfg.get("_project_root", ".")).resolve()

    resolved = {}
    for key, path_str in env_paths.items():
        p = Path(path_str)
        if not p.is_absolute():
            resolved[key] = (project_root / p).resolve()
        else:
            resolved[key] = p.resolve()

    # Subpaths
    subpaths = paths_cfg.get("subpaths", {})
    data_root = resolved.get("data_root", project_root / "data")
    artifacts_root = resolved.get("artifacts_root", project_root / "artifacts")
    reports_root = resolved.get("reports_root", project_root / "reports")

    resolved["raw"] = resolved.get("raw_root", (data_root / "raw").resolve())
    resolved["raw_root"] = resolved["raw"]
    resolved["reports"] = reports_root
    resolved["interim"] = (data_root / "interim").resolve()
    resolved["processed"] = (data_root / "processed").resolve()
    resolved["checkpoints"] = (artifacts_root / "checkpoints").resolve()
    resolved["experiments"] = (artifacts_root / "experiments").resolve()
    resolved["manifests"] = (artifacts_root / "manifests").resolve()
    resolved["models"] = (artifacts_root / "models").resolve()
    resolved["metrics"] = (artifacts_root / "metrics").resolve()
    resolved["logs"] = (artifacts_root / "logs").resolve()
    resolved["tables"] = (reports_root / "tables").resolve()
    resolved["figures"] = resolved.get("figures_root", (reports_root / "figures").resolve())
    resolved["appendix"] = (reports_root / "appendix").resolve()

    return resolved


def validate_config(cfg: Dict[str, Any], stage: Optional[str] = None) -> None:
    """Validate config integrity and fail-fast if critical preconditions or schema are violated.

    Also validates field types and values for required fields, and distinguishes
    required fields (must be set) from pending fields (allowed to be null/blocked
    until evidence is available, e.g. K for RQ2 before diagnostics run).
    """
    for required_section in ["data", "schema", "paths", "preprocessing", "features", "runtime"]:
        if required_section not in cfg:
            raise ValueError(f"Missing required configuration section: '{required_section}'")

    # --- Required field type/value checks ---
    runtime = cfg.get("runtime", {})
    random_state = runtime.get("random_state")
    if not isinstance(random_state, int):
        raise ValueError(
            f"runtime.random_state must be an integer (got {type(random_state).__name__}={random_state!r}). "
            "Fix in configs/runtime.yaml: set random_state to 42 or another integer."
        )
    mode = runtime.get("mode")
    if mode not in ("full", "development", "sample"):
        raise ValueError(
            f"runtime.mode must be 'full' or 'development' (got {mode!r}). "
            "The legacy 'sample' alias is supported for nonofficial smoke tests only. "
            "Mode does not automatically sample data; isolate fixture inputs and outputs."
        )
    chunk_size = runtime.get("chunk_size")
    if not isinstance(chunk_size, int) or chunk_size < 1:
        raise ValueError(
            f"runtime.chunk_size must be a positive integer (got {chunk_size!r}). "
            "Set in configs/runtime.yaml; default is 50000."
        )
    duckdb_cfg = runtime.get("duckdb", {})
    if not isinstance(duckdb_cfg.get("threads"), int) or duckdb_cfg.get("threads", 0) < 1:
        raise ValueError(
            "runtime.duckdb.threads must be a positive integer. Fix in configs/runtime.yaml."
        )
    if not isinstance(duckdb_cfg.get("memory_limit"), str):
        raise ValueError(
            "runtime.duckdb.memory_limit must be a string (e.g. '2GB'). Fix in configs/runtime.yaml."
        )
    if not isinstance(runtime.get("resume"), bool):
        raise ValueError("runtime.resume must be true or false. Fix in configs/runtime.yaml.")
    if runtime.get("storage_backend") not in ("local", "colab"):
        raise ValueError(
            "runtime.storage_backend must be 'local' or 'colab'. Fix in configs/runtime.yaml."
        )

    paths_cfg = cfg.get("paths", {})
    environments = paths_cfg.get("environments")
    if not isinstance(environments, dict) or not environments:
        raise ValueError("paths.environments must be a non-empty mapping in configs/paths.yaml.")
    active_environment = paths_cfg.get("active_environment")
    if active_environment != "auto" and active_environment not in environments:
        raise ValueError(
            f"paths.active_environment={active_environment!r} has no matching paths.environments entry."
        )
    required_path_keys = {"raw_root", "data_root", "artifacts_root", "reports_root", "figures_root", "temp_dir"}
    for environment_name, environment_paths in environments.items():
        if not isinstance(environment_paths, dict):
            raise ValueError(f"paths.environments.{environment_name} must be a mapping.")
        missing_path_keys = sorted(required_path_keys - set(environment_paths))
        if missing_path_keys:
            raise ValueError(
                f"paths.environments.{environment_name} is missing: {', '.join(missing_path_keys)}."
            )

    # --- RQ2 required fields ---
    rq2 = cfg.get("rq2", {})
    mode_strategy = rq2.get("mode_strategy")
    if mode_strategy not in ("overall", "player_mode", "per_mode"):
        raise ValueError(
            f"rq2.mode_strategy must be one of 'overall', 'player_mode', 'per_mode' (got {mode_strategy!r}). "
            "Project has locked per_mode. Fix in configs/rq2.yaml."
        )
    for section in ("rq2", "rq3"):
        device = cfg.get(section, {}).get("device")
        if device not in ("cuda", "cpu"):
            raise ValueError(
                f"{section}.device must be 'cuda' or 'cpu' (got {device!r}). Fix in configs/{section}.yaml."
            )
    mode_decision_reason = rq2.get("mode_decision_reason", "")
    if not mode_decision_reason or not isinstance(mode_decision_reason, str):
        raise ValueError(
            "rq2.mode_decision_reason must be a non-empty string explaining why mode_strategy was chosen. "
            "Fix in configs/rq2.yaml."
        )

    # Validate specific execution stage gates
    if stage == "rq2_clustering_final":
        rq2 = cfg.get('rq2', {})
        k = rq2.get('n_clusters_by_mode') if rq2.get('mode_strategy') == 'per_mode' else rq2.get('n_clusters')
        values = list(k.values()) if isinstance(k, dict) else [k]
        if not values or any(type(value) is not int or value < 2 for value in values):
            raise ValueError(
                "Gate G3 Violated: set n_clusters_by_mode for per_mode, or n_clusters otherwise. "
                "You must inspect clustering diagnostics in Notebook 07 and select K before running final fit."
            )
        min_games = cfg.get("rq2", {}).get("minimum_games_threshold")
        if min_games is None:
            raise ValueError(
                "Gate G3 Violated: 'minimum_games_threshold' in configs/rq2.yaml is null. "
                "Must set retention-backed threshold (e.g. 5, 10, 20) before final clustering fit."
            )

    if stage == "rq3_modeling_test":
        split_cfg = cfg.get("rq3", {}).get("split", {})
        if split_cfg.get("train_ratio") is None:
            raise ValueError("Gate G4 Violated: Train split ratio is null before test evaluation.")


def describe_config_status(cfg: Dict[str, Any]) -> list:
    """Return a list of dicts describing each key config field with type, value, and status.

    Status is one of:
      'required' — must be set to a non-null value before any notebook runs.
      'pending'  — allowed to be null/blocked until evidence from a specific notebook is available.
      'ok'       — set and validated.

    Callers (notebook 00) print or display this as a table.
    """
    runtime = cfg.get("runtime", {})
    rq2 = cfg.get("rq2", {})
    rq3 = cfg.get("rq3", {})
    split_cfg = rq3.get("split", {})

    def _row(field: str, value: Any, status: str, note: str = "") -> Dict[str, Any]:
        return {"field": field, "value": str(value) if value is not None else "null",
                "type": type(value).__name__, "status": status, "note": note}

    def _req(field: str, value: Any, note: str = "") -> Dict[str, Any]:
        s = "ok" if value is not None else "required"
        return _row(field, value, s, note)

    def _pend(field: str, value: Any, gate: str) -> Dict[str, Any]:
        s = "ok" if value is not None else "pending"
        return _row(field, value, s, f"Set after {gate}")

    rows = [
        _req("runtime.mode", runtime.get("mode"), "full=full-input path, not G5; development/sample=nonofficial tests, no automatic sampling"),
        _req("runtime.random_state", runtime.get("random_state"), "Seed for all stochastic steps"),
        _req("runtime.chunk_size", runtime.get("chunk_size"), "Batch rows for CSV ingest"),
        _req("runtime.duckdb.threads", runtime.get("duckdb", {}).get("threads"), ""),
        _req("runtime.duckdb.memory_limit", runtime.get("duckdb", {}).get("memory_limit"), ""),
        _req("rq2.mode_strategy", rq2.get("mode_strategy"), "Locked to per_mode"),
        _req("rq2.mode_decision_reason", rq2.get("mode_decision_reason"), ""),
        _req("rq2.device", rq2.get("device"), "cuda=GPU required; cpu=local"),
        _req("rq3.device", rq3.get("device"), "cuda=GPU required; cpu=local"),
        _pend("rq2.minimum_games_threshold", rq2.get("minimum_games_threshold"), "notebook 05 EDA"),
        _pend("rq2.n_clusters_by_mode (Solo)", (rq2.get("n_clusters_by_mode") or {}).get("Solo"),
              "notebook 07 diagnostics (Gate G3)"),
        _pend("rq2.n_clusters_by_mode (Duo)", (rq2.get("n_clusters_by_mode") or {}).get("Duo"),
              "notebook 07 diagnostics (Gate G3)"),
        _pend("rq2.n_clusters_by_mode (Squad)", (rq2.get("n_clusters_by_mode") or {}).get("Squad"),
              "notebook 07 diagnostics (Gate G3)"),
        _pend("rq3.split.train_ratio", split_cfg.get("train_ratio"), "notebook 02 split (Gate G4)"),
        _pend("rq3.split.validation_ratio", split_cfg.get("validation_ratio"), "notebook 02 split (Gate G4)"),
    ]
    return rows

