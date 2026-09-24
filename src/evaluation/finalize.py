from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from src.data.io import atomic_write_json, read_json
from src.utils.hashing import hash_file
from src.utils.logging import get_logger

logger = get_logger("pubg_finalize")


def build_final_results_manifest(
    artifacts_root: Path,
    reports_root: Path,
    official_run_ids: Dict[str, str],
    output_manifest_path: Path,
) -> Dict[str, Any]:
    """Lock all official experiment artifacts, tables, and figures with cryptographic checksums."""
    output_manifest_path.parent.mkdir(parents=True, exist_ok=True)

    manifest: Dict[str, Any] = {
        "format_version": "3.0",
        "finalized_at": datetime.now(timezone.utc).isoformat(),
        "official_run_ids": official_run_ids,
        "tables": {},
        "figures": {},
        "models": {},
        "predictions": {},
    }

    # Verify tables
    tables_dir = reports_root / "tables"
    if tables_dir.is_dir():
        for csv_file in tables_dir.glob("*.csv"):
            manifest["tables"][csv_file.name] = {
                "path": Path(os.path.relpath(csv_file.resolve(), output_manifest_path.parent.resolve())).as_posix(),
                "sha256": hash_file(csv_file),
                "byte_size": csv_file.stat().st_size,
            }

    # Verify models
    models_dir = artifacts_root / "models"
    if models_dir.is_dir():
        for mod_file in models_dir.glob("*.*"):
            if not mod_file.is_file() or ".uploading_" in mod_file.name or ".tmp_" in mod_file.name:
                continue
            manifest["models"][mod_file.name] = {
                "path": Path(os.path.relpath(mod_file.resolve(), output_manifest_path.parent.resolve())).as_posix(),
                "sha256": hash_file(mod_file),
                "byte_size": mod_file.stat().st_size,
            }

    for run_id in official_run_ids.values():
        prediction = artifacts_root / "experiments" / f"predictions_{run_id}.parquet"
        if prediction.is_file():
            manifest["predictions"][prediction.name] = {
                "path": Path(os.path.relpath(prediction.resolve(), output_manifest_path.parent.resolve())).as_posix(),
                "sha256": hash_file(prediction), "byte_size": prediction.stat().st_size,
            }
    atomic_write_json(output_manifest_path, manifest)
    logger.info(f"Final results manifest locked: {len(manifest['tables'])} tables -> {output_manifest_path.name}")
    return manifest


def verify_final_manifest_integrity(manifest_path: Path) -> Tuple[bool, List[str]]:
    """Verify that all files in final_results_manifest exist and match their locked sha256 checksums."""
    manifest = read_json(manifest_path)
    all_valid = True
    mismatches = []

    for category in ["tables", "figures", "models", "predictions"]:
        items = manifest.get(category, {})
        for name, item_meta in items.items():
            f_path = Path(item_meta["path"])
            if not f_path.is_absolute():
                f_path = manifest_path.parent / f_path
            if not f_path.is_file():
                all_valid = False
                mismatches.append(f"Missing file: {f_path}")
                continue
            actual_hash = hash_file(f_path)
            if actual_hash != item_meta["sha256"]:
                all_valid = False
                mismatches.append(f"Checksum mismatch for {name}: expected {item_meta['sha256']}, got {actual_hash}")

    return all_valid, mismatches
