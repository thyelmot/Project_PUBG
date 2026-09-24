"""Stream ZIP members/local CSVs to compressed staging, with per-file recovery."""

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

import pandas as pd
import pyarrow.parquet as pq

from src.data.download_data import resolve_archive, resolve_local_sources
from src.data.io import atomic_write_json, read_json
from src.data.schema import validate_shard_schema
from src.utils.hashing import hash_file


def convert_csv_batches(con, stream, output, schema, batch_rows=50000):
    """Keep at most one CSV chunk and its typed Arrow result in memory."""
    if not isinstance(batch_rows, int) or isinstance(batch_rows, bool) or batch_rows < 1:
        raise ValueError("batch_rows must be a positive integer")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix(".parquet.partial")
    rows = 0
    writer = None
    try:
        # Read identifiers as strings: preserve leading zeroes, NA names and large IDs.
        with pd.read_csv(stream, chunksize=batch_rows, dtype=str,
                         keep_default_na=False, na_values=[""]) as chunks:
            expressions = None
            for chunk in chunks:
                if expressions is None:
                    validation = validate_shard_schema(
                        list(chunk.columns), schema["required_columns"], schema.get("aliases", {}))
                    if not validation["is_valid"]:
                        raise ValueError(f"Missing CSV columns: {validation['missing_columns']}")
                    expressions = []
                    for original, canonical in validation["column_mapping"].items():
                        dtype = schema["required_columns"][canonical].lower()
                        sql_type = "BIGINT" if "int" in dtype else "DOUBLE" if any(
                            t in dtype for t in ("float", "double")) else "VARCHAR"
                        original = original.replace('"', '""')
                        canonical = canonical.replace('"', '""')
                        expressions.append(f'TRY_CAST("{original}" AS {sql_type}) AS "{canonical}"')
                con.register("_csv_batch", chunk)
                try:
                    table = con.execute("SELECT " + ", ".join(expressions) + " FROM _csv_batch").fetch_arrow_table()
                finally:
                    con.unregister("_csv_batch")
                if writer is None:
                    writer = pq.ParquetWriter(partial, table.schema, compression="zstd")
                writer.write_table(table, row_group_size=batch_rows)
                rows += table.num_rows
                del table, chunk
                if rows % (batch_rows * 20) == 0:
                    print(f"  Converted {rows:,} rows", flush=True)
        if rows == 0:
            raise ValueError("CSV contains no data rows")
        writer.close()
        writer = None
        if pq.ParquetFile(partial).metadata.num_rows != rows:
            raise ValueError("Parquet row count does not match CSV batches")
        partial.replace(output)
        return rows
    finally:
        if writer is not None:
            writer.close()
        partial.unlink(missing_ok=True)


def ingest_sources(con, raw_root, staging_dir, data_cfg, schema_cfg, batch_rows=50000):
    """Prefer the ZIP when available; otherwise use existing CSVs without deleting them.

    Checkpoints become reusable only after a complete member and its checksum are saved.
    No grouping/deduplication happens here: those operations still see all shards.
    """
    raw_root, staging_dir = Path(raw_root), Path(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = staging_dir / "batch_manifest.json"
    old = read_json(manifest_path) if manifest_path.is_file() else {}
    manifest = {"version": 1, "complete": False, "shards": []}
    cached = {s["source"]: s for s in old.get("shards", [])}
    source = data_cfg["source"]
    filename = source.get("archive_filename", "Data_PUBG.zip")
    local_zip = any(p.is_file() for p in (
        raw_root / filename, raw_root.parent / filename, Path(filename), Path("..") / filename))
    groups = [("aggregate", "agg_patterns"), ("deaths", "kill_patterns")]
    local = {kind: resolve_local_sources(raw_root, data_cfg["discovery"][patterns])
             for kind, patterns in groups}
    with ExitStack() as stack:
        entries = []
        archive = None
        if local_zip or not any(local.values()):
            archive_path = resolve_archive(source.get("archive_url", ""), raw_root,
                                           source.get("archive_sha256"), filename)
            archive = stack.enter_context(zipfile.ZipFile(archive_path))
            seen = set()
            for member in archive.infolist():
                name = member.filename.replace("\\", "/")
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError(f"Unsafe ZIP entry: {name}")
                if member.is_dir():
                    continue
                for kind, patterns in groups:
                    if any(path.match(p) or (p.startswith("**/") and path.match(p[3:]))
                           for p in data_cfg["discovery"][patterns]):
                        if name in seen:
                            raise ValueError(f"Duplicate/ambiguous ZIP entry: {name}")
                        seen.add(name)
                        entries.append((kind, name, member.file_size, str(member.CRC), member))
        else:
            for kind, _ in groups:
                for path in local[kind]:
                    entries.append((kind, path.relative_to(raw_root).as_posix(),
                                    path.stat().st_size, hash_file(path), path))
        if not all(any(e[0] == kind for e in entries) for kind, _ in groups):
            raise FileNotFoundError("Missing aggregate/deaths CSV. Check the ZIP or raw_root; no partial dataset is accepted.")
        atomic_write_json(manifest_path, manifest)
        for index, (kind, name, size, checksum, handle) in enumerate(entries, 1):
            signature = hashlib.sha256(json.dumps(
                [1, kind, name, size, checksum, schema_cfg[kind]], sort_keys=True).encode()).hexdigest()
            prefix = "agg" if kind == "aggregate" else "kill"
            output = staging_dir / f"{prefix}_{signature}.parquet"
            record = cached.get(name, {})
            reusable = (record.get("signature") == signature and output.is_file()
                        and record.get("sha256") == hash_file(output))
            if reusable:
                rows = pq.ParquetFile(output).metadata.num_rows
                reusable = rows == record.get("rows")
            if not reusable:
                print(f"[{index}/{len(entries)}] {name}: streaming {batch_rows:,} rows/batch", flush=True)
                with (archive.open(handle) if archive else open(handle, "rb")) as stream:
                    rows = convert_csv_batches(con, stream, output, schema_cfg[kind], batch_rows)
                record = {"source": name, "kind": kind, "signature": signature,
                          "file": output.name, "rows": rows, "source_bytes": size,
                          "sha256": hash_file(output)}
            manifest["shards"].append(record)
            atomic_write_json(manifest_path, manifest)
            print(f"[{index}/{len(entries)}] {'Reused' if reusable else 'Saved'} {rows:,} rows: {output.name}", flush=True)
        manifest["complete"] = True
        atomic_write_json(manifest_path, manifest)
    return manifest


def staged_paths(staging_dir, kind):
    """Use only the completed manifest, never mix old and current staging files."""
    staging_dir = Path(staging_dir)
    manifest_path = staging_dir / "batch_manifest.json"
    if not manifest_path.is_file():
        # Compatibility with already completed pre-batch notebook 01 runs.
        paths = sorted(staging_dir.rglob("agg_*.parquet" if kind == "aggregate" else "kill_*.parquet"))
    else:
        manifest = read_json(manifest_path)
        if not manifest.get("complete"):
            raise RuntimeError("Notebook 01 chưa hoàn tất. Chạy lại 01 để tiếp tục các shard còn thiếu.")
        paths = [(staging_dir / s["file"]).resolve() for s in manifest["shards"] if s["kind"] == kind]
        if any(not p.is_relative_to(staging_dir.resolve()) for p in paths):
            raise ValueError("Invalid staging manifest path")
    if not paths or any(not p.is_file() for p in paths):
        raise FileNotFoundError("Thiếu staging Parquet. Chạy lại notebook 01 với cùng thư mục lưu dữ liệu.")
    return paths
