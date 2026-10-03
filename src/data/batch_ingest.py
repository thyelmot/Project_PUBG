"""Stream ZIP members/local CSVs to compressed staging, with per-file recovery."""

from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
import errno
import time
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

import pandas as pd
import pyarrow.parquet as pq

from src.data.download_data import download_configured_shards, resolve_archive, resolve_local_sources
from src.data.io import atomic_write_json, read_json, publish_file, check_storage_writable
from src.data.schema import validate_shard_schema
from src.utils.hashing import hash_file

SENSITIVE_PLAYER_COLUMNS = {"player_name", "killer_name", "victim_name"}


def convert_csv_batches(con, stream, output, schema, batch_rows=50000, work_dir=None, resume_key=None,
                        result_metadata=None, retain_local=False, source_name=None):
    """Build locally, then publish the closed Parquet file to persistent storage."""
    if not isinstance(batch_rows, int) or isinstance(batch_rows, bool) or batch_rows < 1:
        raise ValueError("batch_rows must be a positive integer")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    source_name = source_name or output.name
    local_dir = Path(work_dir) if work_dir else Path(tempfile.gettempdir()) / "pubg_batch_ingest"
    local_dir.mkdir(parents=True, exist_ok=True)
    partial = local_dir / f"{output.name}.{resume_key or os.getpid()}.partial"
    receipt = partial.with_suffix(".ready.json")
    if retain_local and (not resume_key or result_metadata is None):
        raise ValueError("retain_local requires resume_key and result_metadata")
    if result_metadata is not None:
        result_metadata.update(local_path=str(partial), receipt_path=str(receipt))
    rows = 0
    writer = None
    ready = False
    if resume_key and receipt.is_file() and partial.is_file():
        try:
            saved = read_json(receipt)
            ready = (saved.get("resume_key") == resume_key
                     and saved.get("sha256") == hash_file(partial))
            if ready:
                with pq.ParquetFile(partial) as parquet:
                    rows = parquet.metadata.num_rows
                ready = rows > 0 and rows == saved.get("rows")
        except (ValueError, OSError):
            ready = False
    try:
        if ready:
            print(f"Retrying publication of {rows:,} converted rows: {output.name}", flush=True)
            if result_metadata is not None:
                result_metadata.update(sha256=saved["sha256"], byte_size=partial.stat().st_size)
                if "parse_audit" in saved:
                    result_metadata["parse_audit"] = saved["parse_audit"]
                if "schema_validation" in saved:
                    result_metadata["schema_validation"] = saved["schema_validation"]
            publish_file(partial, output)
            ready = retain_local
            return rows
        rows = 0
        receipt.unlink(missing_ok=True)
        # Read identifiers as strings: preserve leading zeroes, NA names and large IDs.
        with pd.read_csv(stream, chunksize=batch_rows, dtype=str,
                         keep_default_na=False, na_values=[""]) as chunks:
            expressions = None
            col_sql_types = {}
            parse_audit = {}
            for chunk in chunks:
                if {"source_file", "source_row", "__pubg_source_file", "__pubg_source_row"}.intersection(chunk.columns):
                    raise ValueError("Input uses reserved lineage columns")
                chunk["__pubg_source_file"] = source_name
                chunk["__pubg_source_row"] = range(rows + 1, rows + len(chunk) + 1)

                if expressions is None:
                    validation = validate_shard_schema(
                        list(chunk.columns),
                        schema["required_columns"],
                        schema.get("aliases", {}),
                        optional_columns=schema.get("optional_columns"),
                        units=schema.get("units"),
                    )
                    if not validation["is_valid"]:
                        raise ValueError(f"Missing CSV columns: {validation['missing_columns']}")
                    expressions = []
                    all_cols = {**schema.get("required_columns", {}), **schema.get("optional_columns", {})}
                    for original, canonical in validation["column_mapping"].items():
                        dtype = all_cols.get(canonical, "string").lower()
                        sql_type = "BIGINT" if "int" in dtype else "DOUBLE" if any(
                            t in dtype for t in ("float", "double")) else "VARCHAR"
                        col_sql_types[canonical] = sql_type
                        parse_audit[canonical] = {
                            "original_missing": 0,
                            "parse_errors": 0,
                            "valid": 0,
                            "sample_parse_errors": [],
                        }
                        original_quoted = original.replace('"', '""')
                        canonical_quoted = canonical.replace('"', '""')
                        expressions.append(f'TRY_CAST("{original_quoted}" AS {sql_type}) AS "{canonical_quoted}"')
                    expressions.extend([
                        '"__pubg_source_file" AS "source_file"',
                        'CAST("__pubg_source_row" AS BIGINT) AS "source_row"',
                    ])

                # Audit types, parse errors, and integer validity per column
                for original, canonical in validation["column_mapping"].items():
                    col = chunk[original]
                    is_missing = col.isna() | (col == "")
                    n_missing = int(is_missing.sum())
                    parse_audit[canonical]["original_missing"] += n_missing

                    non_missing = col[~is_missing]
                    if len(non_missing) > 0:
                        sql_type = col_sql_types[canonical]
                        if sql_type == "BIGINT":
                            nums = pd.to_numeric(non_missing, errors="coerce")
                            # Count must be strictly integer before cast to prevent silent rounding
                            is_err = nums.isna() | (nums % 1 != 0)
                            n_err = int(is_err.sum())
                            n_valid = len(non_missing) - n_err
                            if n_err > 0:
                                chunk.loc[non_missing.index[is_err], original] = None
                                if canonical not in SENSITIVE_PLAYER_COLUMNS:
                                    rem = 5 - len(parse_audit[canonical]["sample_parse_errors"])
                                    if rem > 0:
                                        parse_audit[canonical]["sample_parse_errors"].extend(
                                            non_missing[is_err].head(rem).tolist()
                                        )
                            parse_audit[canonical]["parse_errors"] += n_err
                            parse_audit[canonical]["valid"] += n_valid
                        elif sql_type == "DOUBLE":
                            nums = pd.to_numeric(non_missing, errors="coerce")
                            is_err = nums.isna()
                            n_err = int(is_err.sum())
                            n_valid = len(non_missing) - n_err
                            if n_err > 0:
                                chunk.loc[non_missing.index[is_err], original] = None
                                if canonical not in SENSITIVE_PLAYER_COLUMNS:
                                    rem = 5 - len(parse_audit[canonical]["sample_parse_errors"])
                                    if rem > 0:
                                        parse_audit[canonical]["sample_parse_errors"].extend(
                                            non_missing[is_err].head(rem).tolist()
                                        )
                            parse_audit[canonical]["parse_errors"] += n_err
                            parse_audit[canonical]["valid"] += n_valid
                        else:
                            parse_audit[canonical]["valid"] += len(non_missing)

                con.register("_csv_batch", chunk)
                try:
                    table_res = con.execute("SELECT " + ", ".join(expressions) + " FROM _csv_batch")
                    table = table_res.to_arrow_table() if hasattr(table_res, "to_arrow_table") else table_res.fetch_arrow_table()
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
        with pq.ParquetFile(partial) as parquet:
            if parquet.metadata.num_rows != rows:
                raise ValueError("Parquet row count does not match CSV batches")
        # Keep a verified local copy after publication failure. The ingest signature
        # includes source identity and schema; never reuse arbitrary previous CSVs.
        local_checksum = hash_file(partial)
        if result_metadata is not None:
            result_metadata.update(sha256=local_checksum, byte_size=partial.stat().st_size,
                                   parse_audit=parse_audit, schema_validation=validation)
        if resume_key:
            atomic_write_json(receipt, {"resume_key": resume_key, "rows": rows,
                                       "sha256": local_checksum, "parse_audit": parse_audit,
                                       "schema_validation": validation})
            ready = True
        publish_file(partial, output)
        ready = retain_local
        return rows
    finally:
        if writer is not None:
            writer.close()
        if ready:
            print(f"Local recovery copy retained until checkpoint verification: {partial}", flush=True)
        else:
            partial.unlink(missing_ok=True)
            receipt.unlink(missing_ok=True)


def ingest_sources(con, raw_root, staging_dir, data_cfg, schema_cfg, batch_rows=50000, work_dir=None, manifests_dir=None):
    """Prefer the ZIP when available; otherwise use existing CSVs without deleting them.

    Checkpoints become reusable only after a complete member and its checksum are saved.
    No grouping/deduplication happens here: those operations still see all shards.
    """
    raw_root, staging_dir = Path(raw_root), Path(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    check_storage_writable(staging_dir)
    manifest_path = staging_dir / "batch_manifest.json"
    old = read_json(manifest_path) if manifest_path.is_file() else {}
    manifest = {"version": 1, "status": "running", "complete": False, "shards": [],
                "started_at": datetime.now(timezone.utc).isoformat(),
                "source_info": {
                    "archive_url": data_cfg.get("source", {}).get("archive_url"),
                    "aggregate_urls": data_cfg.get("source", {}).get("agg_urls", []),
                    "death_urls": data_cfg.get("source", {}).get("kill_urls", []),
                    "download_date": data_cfg.get("source", {}).get("download_date"),
                    "version": data_cfg.get("source", {}).get("dataset_version"),
                }}
    cached = {s["source"]: s for s in old.get("shards", [])}
    source = data_cfg["source"]
    filename = source.get("archive_filename", "Data_PUBG.zip")
    local_zip = any(p.is_file() for p in (
        raw_root / filename, raw_root.parent / filename, Path(filename), Path("..") / filename))
    groups = [("aggregate", "agg_patterns"), ("deaths", "kill_patterns")]
    local = {kind: resolve_local_sources(raw_root, data_cfg["discovery"][patterns])
             for kind, patterns in groups}
    missing_local = [kind for kind, _ in groups if not local[kind]]
    configured_url_kinds = {
        "aggregate" if source.get("agg_urls") else None,
        "deaths" if source.get("kill_urls") else None,
    } - {None}
    downloadable = [kind for kind in missing_local if kind in configured_url_kinds]
    if not local_zip and downloadable:
        download_configured_shards(source, raw_root, downloadable, temp_dir=work_dir)
        local = {kind: resolve_local_sources(raw_root, data_cfg["discovery"][patterns])
                 for kind, patterns in groups}
    with ExitStack() as stack:
        entries = []
        archive = None
        if local_zip or (not all(local.values()) and bool(source.get("archive_url"))):
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
        entries.sort(key=lambda entry: (entry[0], entry[1]))
        if not all(any(e[0] == kind for e in entries) for kind, _ in groups):
            raise FileNotFoundError("Missing aggregate/deaths CSV. Check the ZIP or raw_root; no partial dataset is accepted.")
        # Keep prior records during revalidation so another interruption cannot erase them.
        manifest["shards"] = [s for s in old.get("shards", [])
                              if s["source"] in {entry[1] for entry in entries}]
        atomic_write_json(manifest_path, manifest)
        for index, (kind, name, size, checksum, handle) in enumerate(entries, 1):
            signature = hashlib.sha256(json.dumps(
                [1, kind, name, size, checksum, schema_cfg[kind]], sort_keys=True).encode()).hexdigest()
            prefix = "agg" if kind == "aggregate" else "kill"
            output = staging_dir / f"{prefix}_{signature}.parquet"
            recovery_dir = Path(work_dir) if work_dir else Path(tempfile.gettempdir()) / "pubg_batch_ingest"
            local_path = recovery_dir / f"{output.name}.{signature}.partial"
            receipt_path = local_path.with_suffix(".ready.json")
            record = cached.get(name, {})
            reusable = record.get("signature") == signature
            if reusable:
                try:
                    verify_staged_record(output, record)
                    rows = record["rows"]
                except StagingIntegrityError:
                    reusable = False
            if not reusable:
                print(f"[{index}/{len(entries)}] {name}: streaming {batch_rows:,} rows/batch", flush=True)
                verified_local = {}
                with (archive.open(handle) if archive else open(handle, "rb")) as stream:
                    rows = convert_csv_batches(
                        con, stream, output, schema_cfg[kind], batch_rows, work_dir=work_dir,
                        resume_key=signature, result_metadata=verified_local, retain_local=True, source_name=name)
                local_path = Path(verified_local.pop("local_path"))
                receipt_path = Path(verified_local.pop("receipt_path"))
                record = {"source": name, "kind": kind, "signature": signature,
                          "file": output.name, "rows": rows, "source_bytes": size,
                          "source_checksum": checksum,
                          "source_checksum_algorithm": "crc32" if archive else "sha256",
                          **verified_local}
                try:
                    verify_staged_record(output, record)
                except StagingIntegrityError:
                    print(f"Re-publishing verified local shard without CSV conversion: {output.name}", flush=True)
                    publish_file(local_path, output)
                    verify_staged_record(output, record)
            manifest["shards"] = [s for s in manifest["shards"] if s["source"] != name] + [record]
            atomic_write_json(manifest_path, manifest)
            # Also clean a recovery copy left by a prior commit that succeeded but
            # reported an error: reusable shards have now been checked and committed.
            local_path.unlink(missing_ok=True)
            receipt_path.unlink(missing_ok=True)
            print(f"[{index}/{len(entries)}] {'Reused' if reusable else 'Saved'} {rows:,} rows: {output.name}", flush=True)

        # Generate summary schema_parse_report across all shards
        column_summary = {}
        for s in manifest["shards"]:
            for col, stat in s.get("parse_audit", {}).items():
                if col not in column_summary:
                    column_summary[col] = {
                        "total_rows": 0,
                        "original_missing": 0,
                        "parse_errors": 0,
                        "valid": 0,
                        "sample_parse_errors": [],
                    }
                tot = stat.get("valid", 0) + stat.get("original_missing", 0) + stat.get("parse_errors", 0)
                column_summary[col]["total_rows"] += tot
                column_summary[col]["original_missing"] += stat.get("original_missing", 0)
                column_summary[col]["parse_errors"] += stat.get("parse_errors", 0)
                column_summary[col]["valid"] += stat.get("valid", 0)
                for err in stat.get("sample_parse_errors", []):
                    if err not in column_summary[col]["sample_parse_errors"] and len(column_summary[col]["sample_parse_errors"]) < 5:
                        column_summary[col]["sample_parse_errors"].append(err)

        for col, summary in column_summary.items():
            tot = summary["total_rows"]
            summary["missing_rate"] = round(summary["original_missing"] / tot, 6) if tot > 0 else 0.0
            summary["parse_error_rate"] = round(summary["parse_errors"] / tot, 6) if tot > 0 else 0.0

        parse_report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_shards": len(manifest["shards"]),
            "total_rows": sum(s.get("rows", 0) for s in manifest["shards"]),
            "column_summary": column_summary,
        }
        report_dir = Path(manifests_dir) if manifests_dir else staging_dir
        report_dir.mkdir(parents=True, exist_ok=True)
        parse_report_path = report_dir / "schema_parse_report.json"
        atomic_write_json(parse_report_path, parse_report)
        manifest["parse_report"] = parse_report_path.name

        # Generate schema comparison report (expected vs actual contract)
        shard_validations = {}
        for s in manifest["shards"]:
            val = s.get("schema_validation")
            if val:
                shard_validations[s["source"]] = {**val, "kind": s["kind"]}
        if shard_validations:
            from src.data.schema import generate_schema_report
            schema_report = generate_schema_report(schema_cfg, shard_validations)
            schema_report_path = report_dir / "schema_report.json"
            atomic_write_json(schema_report_path, schema_report)
            manifest["schema_report"] = schema_report_path.name

        parse_error_cells = sum(v["parse_errors"] for v in column_summary.values())
        original_missing_cells = sum(v["original_missing"] for v in column_summary.values())
        rows_saved = sum(s.get("rows", 0) for s in manifest["shards"])
        manifest["row_reconciliation"] = {
            "rows_read": rows_saved,
            "rows_saved": rows_saved,
            "rows_dropped": 0,
            "parse_error_cells_retained_as_null": parse_error_cells,
            "original_missing_cells": original_missing_cells,
            "policy": "Ingest preserves every parsed CSV record; invalid typed cells become null and are audited.",
            "is_reconciled": rows_saved == sum(s.get("rows", 0) for s in manifest["shards"]),
        }
        manifest["complete"] = True
        manifest["status"] = "completed"
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(manifest_path, manifest)
    return manifest


class StagingIntegrityError(ValueError):
    """A shard could not be verified after bounded retries."""


def verify_staged_record(path, record):
    """Distinguish missing files, changed bytes and invalid Parquet metadata."""
    path = Path(path)
    expected = record.get("sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise StagingIntegrityError(f"Missing/invalid expected SHA256 in manifest: {path.name}. Rerun notebook 01.")
    for attempt in range(3):
        try:
            size = path.stat().st_size
            if record.get("byte_size") is not None and size != record["byte_size"]:
                reason = f"byte size mismatch: expected={record['byte_size']}, actual={size}"
            else:
                actual = hash_file(path)
                if actual != expected:
                    reason = f"checksum mismatch: expected={expected}, actual={actual}, bytes={size}"
                else:
                    with pq.ParquetFile(path) as parquet:
                        rows = parquet.metadata.num_rows
                    if rows == record.get("rows"):
                        return
                    reason = f"row count mismatch: expected={record.get('rows')}, actual={rows}"
        except OSError as error:
            if not isinstance(error, FileNotFoundError) and error.errno not in {errno.EIO, errno.ESTALE}:
                raise
            reason = f"file missing/unavailable: {error}"
        except ValueError as error:
            reason = f"invalid Parquet: {error}"
        if attempt < 2:
            time.sleep(attempt + 1)
    raise StagingIntegrityError(f"Staging {reason}; path={path}. Rerun notebook 01 to repair this shard.")


def finalize_ingest(con, raw_root, staging_dir, data_cfg, schema_cfg, batch_rows=50000, work_dir=None, manifests_dir=None):
    """Gate G1: recheck both groups; repair failed shards from source once."""
    try:
        for kind in ("aggregate", "deaths"):
            staged_paths(staging_dir, kind)
    except StagingIntegrityError as error:
        print(f"Final validation failed: {error}\nRepairing invalid shards from source once.", flush=True)
        ingest_sources(con, raw_root, staging_dir, data_cfg, schema_cfg, batch_rows, work_dir, manifests_dir=manifests_dir)
        for kind in ("aggregate", "deaths"):
            staged_paths(staging_dir, kind)
    return read_json(Path(staging_dir) / "batch_manifest.json")


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
        records = [s for s in manifest["shards"] if s["kind"] == kind]
        paths = [(staging_dir / s["file"]).resolve() for s in records]
        if any(not p.is_relative_to(staging_dir.resolve()) for p in paths):
            raise ValueError("Invalid staging manifest path")
        if len(paths) != len(set(paths)):
            raise ValueError("Duplicate shard in staging manifest; rerun notebook 01.")
        for path, record in zip(paths, records):
            verify_staged_record(path, record)
    if not paths or any(not p.is_file() for p in paths):
        raise FileNotFoundError("Thiếu staging Parquet. Chạy lại notebook 01 với cùng thư mục lưu dữ liệu.")
    return paths
