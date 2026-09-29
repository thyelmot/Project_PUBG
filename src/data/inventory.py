import os
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional
import zipfile
import duckdb
from src.data.io import atomic_write_json, get_duckdb_connection
from src.utils.hashing import hash_file
from src.utils.logging import get_logger

logger = get_logger("pubg_inventory")


def count_csv_rows_duckdb(con: duckdb.DuckDBPyConnection, csv_path: Path) -> int:
    """Accurately count rows in a CSV file using DuckDB's robust CSV parser."""
    safe_path = str(csv_path.resolve()).replace("\\", "/")
    query = f"SELECT count(*) FROM read_csv_auto('{safe_path}', header=True, all_varchar=True);"
    result = con.execute(query).fetchone()
    return int(result[0]) if result else 0


def inventory_sources(
    raw_root: Path,
    agg_patterns: List[str],
    kill_patterns: List[str],
    con: Optional[duckdb.DuckDBPyConnection] = None,
    compute_hash: bool = True,
    data_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Inventory all raw shard files, sizes, checksums, and accurate row counts.

    Supports both directory-based CSV files and streaming ZIP archives.
    Preserves exact provenance without speculating version or download dates.
    """
    db_con = con or get_duckdb_connection()
    raw_dir = Path(raw_root).resolve()

    agg_files = []
    for pat in agg_patterns:
        agg_files.extend(list(raw_dir.glob(pat)))
    agg_files = sorted(list(set(agg_files)))

    kill_files = []
    for pat in kill_patterns:
        kill_files.extend(list(raw_dir.glob(pat)))
    kill_files = sorted(list(set(kill_files)))

    # Check for archive if no direct CSVs found
    source_cfg = data_cfg.get("source", {}) if data_cfg else {}
    archive_name = source_cfg.get("archive_filename", "Data_PUBG.zip")
    candidate_archives = [
        raw_dir / archive_name,
        raw_dir.parent / archive_name,
        Path(archive_name),
        Path("..") / archive_name,
    ]
    detected_archive = None
    for cand in candidate_archives:
        if cand.is_file():
            detected_archive = cand.resolve()
            break

    storage_format = "local_csv"
    archive_shards = {"aggregate": [], "deaths": []}

    if not agg_files and not kill_files and detected_archive:
        storage_format = "zip_streaming"
        logger.info(f"Inventorying shards inside ZIP archive: {detected_archive.name}")
        with zipfile.ZipFile(detected_archive, "r") as zf:
            for member in zf.infolist():
                name = member.filename.replace("\\", "/")
                p = PurePosixPath(name)
                if member.is_dir() or ".." in p.parts or p.is_absolute():
                    continue
                # Match aggregate
                is_agg = any(p.match(pat) or (pat.startswith("**/") and p.match(pat[3:])) for pat in agg_patterns)
                if is_agg:
                    archive_shards["aggregate"].append({
                        "filename": member.filename,
                        "relative_path": name,
                        "byte_size": member.file_size,
                        "compressed_size": member.compress_size,
                        "crc32": str(member.CRC),
                        "row_count": -1,  # Ingest will count rows via streaming
                        "status": "valid",
                    })
                # Match deaths
                is_kill = any(p.match(pat) or (pat.startswith("**/") and p.match(pat[3:])) for pat in kill_patterns)
                if is_kill:
                    archive_shards["deaths"].append({
                        "filename": member.filename,
                        "relative_path": name,
                        "byte_size": member.file_size,
                        "compressed_size": member.compress_size,
                        "crc32": str(member.CRC),
                        "row_count": -1,
                        "status": "valid",
                    })

    source_info = {
        "dataset_name": source_cfg.get("dataset_name", "PUBG Match Deaths and Statistics"),
        "dataset_slug": source_cfg.get("dataset_slug", "skihikingkevin/pubg-match-deaths"),
        "archive_filename": detected_archive.name if detected_archive else archive_name,
        "archive_path": str(detected_archive) if detected_archive else None,
        "archive_sha256": source_cfg.get("archive_sha256"),
        "archive_size_bytes": detected_archive.stat().st_size if detected_archive else source_cfg.get("archive_size_bytes"),
        "download_date": None,  # Strictly recorded only when verified; never speculated
        "version": None,        # Version is null when unversioned/unverified
        "storage_format": storage_format,
    }

    inventory: Dict[str, Any] = {
        "raw_root": str(raw_dir),
        "source_info": source_info,
        "aggregate_shards": [],
        "death_shards": [],
        "total_files": 0,
        "total_bytes": 0,
        "total_aggregate_rows": 0,
        "total_death_rows": 0,
    }

    if storage_format == "zip_streaming":
        inventory["aggregate_shards"] = archive_shards["aggregate"]
        inventory["death_shards"] = archive_shards["deaths"]
        inventory["total_files"] = len(archive_shards["aggregate"]) + len(archive_shards["deaths"])
        inventory["total_bytes"] = sum(s["byte_size"] for s in archive_shards["aggregate"] + archive_shards["deaths"])
    else:
        logger.info(f"Inventorying {len(agg_files)} aggregate shards and {len(kill_files)} death shards in {raw_dir}")
        for file_path in agg_files:
            size = file_path.stat().st_size
            checksum = hash_file(file_path) if compute_hash else None
            try:
                row_count = count_csv_rows_duckdb(db_con, file_path)
            except Exception as e:
                logger.warning(f"Could not count rows in {file_path.name}: {e}")
                row_count = -1

            inventory["aggregate_shards"].append({
                "filename": file_path.name,
                "relative_path": str(file_path.relative_to(raw_dir)),
                "byte_size": size,
                "sha256": checksum,
                "row_count": row_count,
                "status": "valid" if row_count > 0 else "error",
            })
            inventory["total_bytes"] += size
            if row_count > 0:
                inventory["total_aggregate_rows"] += row_count

        for file_path in kill_files:
            size = file_path.stat().st_size
            checksum = hash_file(file_path) if compute_hash else None
            try:
                row_count = count_csv_rows_duckdb(db_con, file_path)
            except Exception as e:
                logger.warning(f"Could not count rows in {file_path.name}: {e}")
                row_count = -1

            inventory["death_shards"].append({
                "filename": file_path.name,
                "relative_path": str(file_path.relative_to(raw_dir)),
                "byte_size": size,
                "sha256": checksum,
                "row_count": row_count,
                "status": "valid" if row_count > 0 else "error",
            })
            inventory["total_bytes"] += size
            if row_count > 0:
                inventory["total_death_rows"] += row_count

        inventory["total_files"] = len(agg_files) + len(kill_files)

    return inventory


def update_inventory_with_staged_counts(
    inventory: Dict[str, Any],
    manifest: Dict[str, Any],
) -> Dict[str, Any]:
    """Synchronize actual row counts from staged batch manifest into source inventory."""
    shard_rows = {}
    for s in manifest.get("shards", []):
        src = s.get("source", "")
        rows = s.get("rows", 0)
        shard_rows[src] = rows
        shard_rows[Path(src).name] = rows

    total_agg = 0
    for s in inventory.get("aggregate_shards", []):
        name = s.get("filename")
        rel = s.get("relative_path")
        if rel in shard_rows:
            s["row_count"] = shard_rows[rel]
        elif name in shard_rows:
            s["row_count"] = shard_rows[name]
        if s.get("row_count", -1) > 0:
            s["status"] = "valid"
            total_agg += s["row_count"]

    total_kill = 0
    for s in inventory.get("death_shards", []):
        name = s.get("filename")
        rel = s.get("relative_path")
        if rel in shard_rows:
            s["row_count"] = shard_rows[rel]
        elif name in shard_rows:
            s["row_count"] = shard_rows[name]
        if s.get("row_count", -1) > 0:
            s["status"] = "valid"
            total_kill += s["row_count"]

    inventory["total_aggregate_rows"] = total_agg
    inventory["total_death_rows"] = total_kill
    return inventory

