from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from src.data.io import atomic_write_json, read_json
from src.utils.hashing import hash_file
from src.utils.logging import get_logger
from src.data.checkpoints import CheckpointManager

logger = get_logger("pubg_finalize")

RQ2_RESULT_TABLES = {'cluster_profile.csv', 'cluster_centers_standardized.csv',
                     'cluster_assignments.csv', 'clustering_robustness.csv',
                     'c4_min_games_sensitivity.csv', 'c5_outcome_comparison.csv'}


def select_rq2_results(paths, cfg):
    """Only completed, compatible RQ2 artifacts can enter the final report."""
    manager = CheckpointManager(paths['checkpoints'] / 'checkpoint_manifest.json')
    record = manager.load_manifest()['stages'].get('rq2_clustering', {})
    if not manager.is_compatible('rq2_clustering', record.get('signature')):
        raise ValueError('RQ2 is incomplete/stale or its artifacts changed. Complete notebook 07 first.')
    decisions = read_json(paths['manifests'] / 'rq2_decisions.json')
    if decisions['config'] != cfg['rq2']:
        raise ValueError('RQ2 config differs from the completed run. Rerun notebook 07 with the selected settings.')
    runs = decisions.get('run_ids')
    if not runs:
        raise ValueError('RQ2 run IDs missing. Complete the updated notebook 07 first.')
    artifacts = {name: (manager.manifest_path.parent / path).resolve()
                 for name, path in record['artifacts'].items()}
    if cfg['rq2']['mode_strategy'] == 'per_mode':
        for mode in runs:
            if mode not in ('Solo', 'Duo', 'Squad'):
                raise ValueError(f'Invalid RQ2 mode: {mode}')
            for filename in RQ2_RESULT_TABLES:
                if artifacts.get(f'{mode}/{filename}') != (paths['tables'] / 'rq2' / mode / filename).resolve():
                    raise ValueError(f'Missing official per-mode output: {mode}/{filename}')
    return {f'rq2/{mode}': run for mode, run in runs.items()}, artifacts


def build_final_results_manifest(
    artifacts_root: Path,
    reports_root: Path,
    official_run_ids: Dict[str, str],
    output_manifest_path: Path,
    rq2_artifacts: Optional[Dict[str, Path]] = None,
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
        "metadata": {},
    }

    # Verify tables
    tables_dir = reports_root / "tables"
    if tables_dir.is_dir():
        selected = {p.resolve() for p in (rq2_artifacts or {}).values()}
        for csv_file in tables_dir.rglob("*.csv"):
            if rq2_artifacts is not None and (csv_file.name in RQ2_RESULT_TABLES or 'rq2' in csv_file.relative_to(tables_dir).parts):
                if csv_file.resolve() not in selected:
                    continue
            manifest["tables"][csv_file.relative_to(tables_dir).as_posix()] = {
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
    metadata_files = [p for p in (rq2_artifacts or {}).values() if p.suffix == '.json']
    metadata_files += [artifacts_root / 'experiments' / f'compute_{run}.json'
                       for run in official_run_ids.values() if '/' not in run]
    for path in metadata_files:
        if path.is_file():
            key = Path(os.path.relpath(path, artifacts_root)).as_posix()
            manifest['metadata'][key] = {'path': Path(os.path.relpath(path, output_manifest_path.parent)).as_posix(),
                                         'sha256': hash_file(path), 'byte_size': path.stat().st_size}
    atomic_write_json(output_manifest_path, manifest)
    logger.info(f"Final results manifest locked: {len(manifest['tables'])} tables -> {output_manifest_path.name}")
    return manifest


def verify_final_manifest_integrity(manifest_path: Path) -> Tuple[bool, List[str]]:
    """Verify that all files in final_results_manifest exist and match their locked sha256 checksums."""
    manifest = read_json(manifest_path)
    all_valid = True
    mismatches = []

    for category in ["tables", "figures", "models", "predictions", "metadata"]:
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
