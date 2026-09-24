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
    """Validate config integrity and fail-fast if critical preconditions or schema are violated."""
    for required_section in ["data", "schema", "paths", "preprocessing", "features", "runtime"]:
        if required_section not in cfg:
            raise ValueError(f"Missing required configuration section: '{required_section}'")

    # Validate specific execution stage gates
    if stage == "rq2_clustering_final":
        k = cfg.get("rq2", {}).get("n_clusters")
        if k is None:
            raise ValueError(
                "Gate G3 Violated: 'n_clusters' in configs/rq2.yaml is null. "
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
