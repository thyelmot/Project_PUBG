from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
from src.data.io import atomic_write_json, read_json
from src.utils.hashing import hash_file
from src.utils.logging import log_stage


# Directed acyclic graph of research pipeline stages
STAGE_DEPENDENCIES: Dict[str, List[str]] = {
    "inventory": [],
    "schema": ["inventory"],
    "cleaning_metadata": ["schema"],
    "player_match_base": ["cleaning_metadata"],
    "combat_timing": ["player_match_base"],
    "player_match_features": ["combat_timing"],
    "split_manifest": ["cleaning_metadata"],
    "eda": ["player_match_features", "split_manifest"],
    "rq1": ["player_match_features", "split_manifest"],
    "rq2_profiles": ["player_match_features"],
    "rq2_clustering": ["rq2_profiles"],
    "historical": ["player_match_features", "split_manifest"],
    "rq3_prediction": ["player_match_features", "historical", "split_manifest"],
    "ablation_error": ["rq3_prediction"],
    "finalization": ["rq1", "rq2_clustering", "rq3_prediction", "ablation_error"],
}


class CheckpointManager:
    """Manages idempotent pipeline execution, checkpoint commit, and dependency invalidation."""

    def __init__(self, manifest_path: Union[str, Path] = "./artifacts/checkpoints/checkpoint_manifest.json") -> None:
        self.manifest_path = Path(manifest_path)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_manifest_exists()

    def _ensure_manifest_exists(self) -> None:
        if not self.manifest_path.is_file():
            initial_data = {
                "format_version": "1.0",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "stages": {},
            }
            atomic_write_json(self.manifest_path, initial_data)

    def load_manifest(self) -> Dict[str, Any]:
        return read_json(self.manifest_path)

    def save_manifest(self, manifest: Dict[str, Any]) -> None:
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(self.manifest_path, manifest)

    def is_compatible(self, stage: str, signature: str) -> bool:
        """Check if stage checkpoint exists, is marked completed, and matches current signature."""
        manifest = self.load_manifest()
        stage_record = manifest.get("stages", {}).get(stage)
        if not stage_record:
            return False

        if stage_record.get("status") != "completed":
            return False

        if stage_record.get("signature") != signature:
            return False

        # Verify all committed artifacts exist on disk
        artifacts = stage_record.get("artifacts", {})
        for art_name, art_path in artifacts.items():
            path = Path(art_path)
            if not path.is_absolute():
                path = self.manifest_path.parent / path
            if not path.is_file():
                return False
            checksum = stage_record.get("checksums", {}).get(art_name)
            if checksum and hash_file(path) != checksum:
                return False

        return True

    def mark_running(self, stage: str, signature: str) -> None:
        """Record stage execution start."""
        manifest = self.load_manifest()
        manifest["stages"][stage] = {
            "status": "running",
            "signature": signature,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "artifacts": {},
        }
        self.save_manifest(manifest)
        log_stage(stage, "started", signature=signature)

    def begin_notebook(self, name: str, dependencies: List[str]) -> None:
        """Block cross-runtime use of outputs from a notebook interrupted mid-run."""
        manifest = self.load_manifest()
        stages = manifest.setdefault("stages", {})
        for dependency in dependencies:
            record = stages.get("notebook/" + dependency)
            # Legacy outputs have no notebook-level record; their file checks still apply.
            if record and record.get("status") != "completed":
                raise RuntimeError(f"{dependency} chưa hoàn tất. Chạy lại notebook đó trước {name}.")
        stage = "notebook/" + name
        invalidated = {stage}
        while True:
            added = {key for key, record in stages.items()
                     if key not in invalidated and invalidated.intersection(record.get("dependencies", []))}
            if not added:
                break
            invalidated.update(added)
        for key in invalidated - {stage}:
            stages[key]["status"] = "stale"
        stages[stage] = {"status": "running", "signature": "notebook_v1",
                         "dependencies": ["notebook/" + d for d in dependencies], "artifacts": {},
                         "started_at": datetime.now(timezone.utc).isoformat()}
        self.save_manifest(manifest)

    def commit(
        self,
        stage: str,
        signature: str,
        artifacts: Dict[str, Union[str, Path]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Publish completed checkpoint with verified artifacts."""
        # Check files exist
        verified_artifacts = {}
        checksums = {}
        for name, path_val in artifacts.items():
            path = Path(path_val).resolve()
            if not path.is_file():
                raise FileNotFoundError(f"Cannot commit missing artifact for stage '{stage}': {path}")
            verified_artifacts[name] = Path(os.path.relpath(path, self.manifest_path.parent.resolve())).as_posix()
            checksums[name] = hash_file(path)

        manifest = self.load_manifest()
        dependencies = manifest.get("stages", {}).get(stage, {}).get("dependencies", [])
        manifest["stages"][stage] = {
            "status": "completed",
            "signature": signature,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": verified_artifacts,
            "checksums": checksums,
            "dependencies": dependencies,
            "metadata": metadata or {},
        }
        self.save_manifest(manifest)
        log_stage(stage, "completed", signature=signature, artifacts_count=len(verified_artifacts))

    def invalidate_descendants(self, stage: str) -> List[str]:
        """Invalidate all downstream dependent stages when an upstream checkpoint is stale."""
        manifest = self.load_manifest()
        invalidated: Set[str] = set()
        queue = [stage]

        # Find all stages that depend directly or indirectly on queue
        while queue:
            current = queue.pop(0)
            for stg, deps in STAGE_DEPENDENCIES.items():
                if current in deps and stg not in invalidated:
                    invalidated.add(stg)
                    queue.append(stg)

        # Mark invalidated stages in manifest
        for stg in invalidated:
            if stg in manifest.get("stages", {}):
                manifest["stages"][stg]["status"] = "stale"
                log_stage(stg, "invalidated_stale", cause=stage)

        self.save_manifest(manifest)
        return list(invalidated)

    def restore(self, stage: str) -> Optional[Dict[str, Any]]:
        """Retrieve completed checkpoint record if valid."""
        manifest = self.load_manifest()
        record = manifest.get("stages", {}).get(stage)
        if record and self.is_compatible(stage, record.get("signature")):
            record["artifacts"] = {
                name: str((self.manifest_path.parent / path).resolve())
                for name, path in record.get("artifacts", {}).items()
            }
            return record
        return None
