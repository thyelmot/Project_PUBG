import os
from pathlib import Path
from typing import Any, Dict, List, Optional
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
) -> Dict[str, Any]:
    """Inventory all raw shard files, sizes, checksums, and accurate row counts."""
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

    inventory: Dict[str, Any] = {
        "raw_root": str(raw_dir),
        "aggregate_shards": [],
        "death_shards": [],
        "total_files": len(agg_files) + len(kill_files),
        "total_bytes": 0,
        "total_aggregate_rows": 0,
        "total_death_rows": 0,
    }

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

    return inventory
