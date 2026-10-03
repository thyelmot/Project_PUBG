from datetime import datetime, timezone
import csv
import os
from pathlib import Path
import socket
from typing import Any, Dict, List, Optional, Set, Union
import pyarrow.parquet as pq
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
    "rq2_diagnostics": ["rq2_profiles"],
    "rq2_clustering": ["rq2_profiles", "rq2_diagnostics"],
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
            for snapshot_path in [self.manifest_path.with_suffix(".recovery.json"), *self._snapshot_paths()]:
                try:
                    manifest = read_json(snapshot_path)
                    atomic_write_json(self.manifest_path, manifest)
                    return
                except (OSError, ValueError):
                    continue
            initial_data = {
                "format_version": "1.0",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "stages": {},
            }
            self.save_manifest(initial_data)

    def _snapshot_paths(self) -> List[Path]:
        pattern = f"{self.manifest_path.stem}.snapshot_*.json"
        return sorted(self.manifest_path.parent.glob(pattern), reverse=True)

    def load_manifest(self) -> Dict[str, Any]:
        try:
            return read_json(self.manifest_path)
        except (OSError, ValueError):
            for snapshot_path in [self.manifest_path.with_suffix(".recovery.json"), *self._snapshot_paths()]:
                try:
                    manifest = read_json(snapshot_path)
                    atomic_write_json(self.manifest_path, manifest)
                    return manifest
                except (OSError, ValueError):
                    continue
            raise

    def save_manifest(self, manifest: Dict[str, Any]) -> None:
        """Snapshot the last readable manifest before replacing the canonical copy."""
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        if self.manifest_path.is_file():
            try:
                previous = read_json(self.manifest_path)
                snapshot_name = (
                    f"{self.manifest_path.stem}.snapshot_"
                    f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"
                )
                atomic_write_json(self.manifest_path.with_name(snapshot_name), previous)
            except (OSError, ValueError):
                pass
        atomic_write_json(self.manifest_path, manifest)
        atomic_write_json(self.manifest_path.with_suffix(".recovery.json"), manifest)

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
        if not artifacts:
            return False
        for art_name, art_path in artifacts.items():
            path = Path(art_path)
            if not path.is_absolute():
                path = self.manifest_path.parent / path
            if not path.is_file():
                return False
            if path.stat().st_size == 0:
                return False
            checksum = stage_record.get("checksums", {}).get(art_name)
            if checksum and hash_file(path) != checksum:
                return False
            details = stage_record.get("artifact_metadata", {}).get(art_name, {})
            if details.get("byte_size") is not None and path.stat().st_size != details["byte_size"]:
                return False
            if path.suffix.lower() == ".parquet" and details.get("row_count") is not None:
                try:
                    if pq.ParquetFile(path).metadata.num_rows != details["row_count"]:
                        return False
                except (OSError, ValueError):
                    return False

        return True

    def mark_running(self, stage: str, signature: str, writer_id: Optional[str] = None) -> None:
        """Record stage execution start."""
        manifest = self.load_manifest()
        manifest["stages"][stage] = {
            "status": "running",
            "signature": signature,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "artifacts": {},
            "writer_id": writer_id,
        }
        self.save_manifest(manifest)
        log_stage(stage, "started", signature=signature)

    def begin_notebook(
        self,
        name: str,
        dependencies: List[str],
        signature: str = "notebook_v1",
        writer_id: Optional[str] = None,
        force_takeover: bool = False,
    ) -> None:
        """Block cross-runtime use of outputs from a notebook interrupted mid-run."""
        manifest = self.load_manifest()
        stages = manifest.setdefault("stages", {})
        writer_id = writer_id or os.environ.get("PUBG_WRITER_ID") or f"{socket.gethostname()}:{os.getpid()}"
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
        current = stages.get(stage, {})
        if (current.get("status") == "running"
                and current.get("writer_id") not in (None, writer_id)
                and not force_takeover):
            raise RuntimeError(
                f"{name} is already running under writer {current.get('writer_id')}. Confirm the old runtime stopped before takeover."
            )
        if (current.get("status") == "running"
                and current.get("dependencies") == ["notebook/" + d for d in dependencies]
                and current.get("signature") == signature
                and current.get("writer_id") == writer_id
                and all(stages[key].get("status") == "stale" for key in invalidated - {stage})):
            return  # Already invalidated; preserve the original start time and avoid a Drive write.
        for key in invalidated - {stage}:
            stages[key]["status"] = "stale"
        stages[stage] = {"status": "running", "signature": signature,
                         "dependencies": ["notebook/" + d for d in dependencies], "artifacts": {},
                         "writer_id": writer_id,
                         "started_at": datetime.now(timezone.utc).isoformat()}
        self.save_manifest(manifest)

    @staticmethod
    def _artifact_details(path: Path) -> Dict[str, Any]:
        """Return format-aware integrity metadata without loading complete tables."""
        details: Dict[str, Any] = {
            "byte_size": path.stat().st_size,
            "sha256": hash_file(path),
            "row_count": None,
            "schema": None,
        }
        suffix = path.suffix.lower()
        if suffix == ".parquet":
            parquet = pq.ParquetFile(path)
            details["row_count"] = parquet.metadata.num_rows
            details["schema"] = [
                {"name": field.name, "type": str(field.type)} for field in parquet.schema_arrow
            ]
        elif suffix == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                rows = csv.reader(stream)
                details["schema"] = next(rows, [])
                details["row_count"] = sum(1 for _ in rows)
        elif suffix == ".json":
            payload = read_json(path)
            details["schema"] = sorted(payload) if isinstance(payload, dict) else None
            details["row_count"] = len(payload) if isinstance(payload, list) else 1
        return details

    def commit(
        self,
        stage: str,
        signature: str,
        artifacts: Dict[str, Union[str, Path]],
        metadata: Optional[Dict[str, Any]] = None,
        writer_id: Optional[str] = None,
    ) -> None:
        """Publish completed checkpoint with verified artifacts."""
        if not artifacts:
            raise ValueError(f"Cannot complete stage '{stage}' without at least one artifact")
        # Check files exist
        verified_artifacts = {}
        checksums = {}
        artifact_metadata = {}
        for name, path_val in artifacts.items():
            path = Path(path_val).resolve()
            if not path.is_file():
                raise FileNotFoundError(f"Cannot commit missing artifact for stage '{stage}': {path}")
            if path.stat().st_size == 0:
                raise ValueError(f"Cannot commit empty (0 bytes) artifact for stage '{stage}': {path}")
            verified_artifacts[name] = Path(os.path.relpath(path, self.manifest_path.parent.resolve())).as_posix()
            artifact_metadata[name] = self._artifact_details(path)
            checksums[name] = artifact_metadata[name]["sha256"]

        manifest = self.load_manifest()
        current = manifest.get("stages", {}).get(stage, {})
        if writer_id and current.get("writer_id") and current["writer_id"] != writer_id:
            raise RuntimeError(f"Stage '{stage}' is owned by writer {current['writer_id']}")
        dependencies = current.get("dependencies", [])
        manifest["stages"][stage] = {
            "status": "completed",
            "signature": signature,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": verified_artifacts,
            "checksums": checksums,
            "dependencies": dependencies,
            "artifact_metadata": artifact_metadata,
            "metadata": metadata or {},
            "writer_id": writer_id or current.get("writer_id"),
        }
        self.save_manifest(manifest)
        log_stage(stage, "completed", signature=signature, artifacts_count=len(verified_artifacts))

    def record_failure(
        self,
        stage: str,
        signature: str,
        error: str,
        *,
        resource_limited: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist failure without inventing metrics or promoting partial artifacts."""
        manifest = self.load_manifest()
        status = "resource_limited" if resource_limited else "failed"
        manifest["stages"][stage] = {
            "status": status,
            "signature": signature,
            "error": str(error),
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": {},
            "metadata": metadata or {},
        }
        self.save_manifest(manifest)
        log_stage(stage, status, signature=signature, error=str(error))


    def record_blocked(
        self,
        stage: str,
        signature: str,
        reason_code: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record stage execution as blocked (e.g. Chronology Grade C blocks S2/P3)."""
        manifest = self.load_manifest()
        manifest["stages"][stage] = {
            "status": "blocked",
            "signature": signature,
            "reason_code": reason_code,
            "blocked_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": {},
            "metadata": metadata or {},
        }
        self.save_manifest(manifest)
        log_stage(stage, "blocked", signature=signature, reason_code=reason_code)

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
        if stage in {"rq2_profiles", "rq2_diagnostics"}:
            invalidated.update(
                key for key in manifest.get("stages", {}) if key.startswith("rq2_clustering/")
            )

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
