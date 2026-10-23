"""Lossless normalized intermediates; all scientific columns remain logical views."""
from pathlib import Path
import json
import re
import tempfile

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .io import digest, fingerprint, ident, publish, quote, read_json, validate_parquet, write_json


def normalized(ctx):
    return ctx.cfg["storage"].get("layout", "materialized") == "normalized_v1"


def dataset_path(ctx, name):
    if not re.fullmatch("[A-Za-z_][A-Za-z0-9_]*",name):raise ValueError("Unsafe dataset name")
    physical = ctx.data / (name + ".parquet")
    descriptor = ctx.data / (name + ".dataset.json")
    if physical.exists() and descriptor.exists():
        raise ValueError("Ambiguous physical/logical dataset: " + name)
    if physical.is_file():
        return physical
    if descriptor.is_file():
        return descriptor
    raise FileNotFoundError("Missing dataset: " + name)


def dataset_sql(ctx, name):
    path = dataset_path(ctx, name)
    if path.suffix == ".parquet":
        return "SELECT * FROM read_parquet(" + quote(path) + ")"
    record = read_json(path)
    if record.get("format") != 1 or record.get("recipe") != name:
        raise ValueError("Invalid dataset descriptor: " + name)
    def source(key):
        return "(" + dataset_sql(ctx, key) + ")"
    if name == "cleaned":
        modes = record["mode_mapping"]
        if not isinstance(modes, dict) or any(not str(k).isdigit() or not isinstance(v, str) for k, v in modes.items()):
            raise ValueError("Invalid stored mode mapping")
        mapping = " ".join(f"WHEN party_size={int(k)} THEN {quote(v)}" for k, v in modes.items())
        columns=record["source_columns"]
        if not isinstance(columns,list) or any(not isinstance(c,str) for c in columns):
            raise ValueError("Invalid cleaned source columns")
        selected=",".join("a."+ident(c) for c in columns)
        return f"""SELECT {selected},s.split,CASE {mapping} ELSE 'Other' END team_size_mode,
            sha256(to_json(struct_pack(m:=match_id,p:=player_name,
            f:=CASE WHEN player_name IS NULL THEN source_file END,
            r:=CASE WHEN player_name IS NULL THEN source_row END))) row_id
            FROM {source('aggregate')} a JOIN {source('cleaned_rows')} k USING(source_file,source_row)
            JOIN {source('split')} s USING(match_id)"""
    if name == "base":
        from .features import base_query
        return base_query().replace("FROM c JOIN m USING(match_id)",
            f"FROM {source('cleaned')} c JOIN {source('match_metadata')} m USING(match_id)")
    if name == "player_match":
        from .features import timing_query
        return timing_query().replace("FROM b LEFT JOIN timing t", f"FROM {source('base')} b LEFT JOIN {source('timing')} t")
    if name == "kill_discrepancy":
        return ("SELECT row_id,match_id,player_kills,event_kill_count,"
                "player_kills-event_kill_count discrepancy,timing_status FROM " + source("player_match"))
    raise ValueError("Unknown dataset recipe: " + name)


def dataset_fingerprint(ctx, name):
    path=dataset_path(ctx,name)
    if path.suffix==".parquet":return digest(path)
    dependencies={"cleaned":["aggregate","cleaned_rows","split"],"base":["cleaned","match_metadata"],
                  "player_match":["base","timing"],"kill_discrepancy":["player_match"]}
    hashes={}
    def visit(key):
        if key in hashes:return
        file=dataset_path(ctx,key);hashes[key]=digest(file)
        if file.suffix==".json":
            for child in dependencies[key]:visit(child)
    visit(name)
    return fingerprint(hashes)


def describe_dataset(ctx, con, name, query, **parameters):
    if name not in {"cleaned", "base", "player_match", "kill_discrepancy"}:
        raise ValueError("Unsupported normalized dataset")
    record = {"format": 1, "recipe": name, **parameters,
              "rows": con.execute("SELECT count(*) FROM (" + query + ")").fetchone()[0],
              "schema": con.execute("DESCRIBE (" + query + ")").fetchall()}
    target = ctx.data / (name + ".dataset.json")
    if (ctx.data / (name + ".parquet")).exists():
        raise ValueError("Use a fresh normalized project; never overwrite a wide dataset")
    write_json(record, target)
    return ctx.record(target)


PREDICTION_KEY = b"pubg_normalized_prediction_v1"
IDENTITY = ["row_id", "match_id", "team_id", "team_size_mode", "split", "actual"]


def prediction_metadata(path):
    with pq.ParquetFile(path) as file:
        encoded = (file.schema_arrow.metadata or {}).get(PREDICTION_KEY)
    if encoded is None:
        return None
    record = json.loads(encoded)
    if (record.get("format") != 1 or not re.fullmatch("[0-9a-f]{64}", record.get("cohort", ""))
            or type(record.get("rows")) is not int or record["rows"] <= 0
            or any(not isinstance(record.get(k), str) for k in ("experiment", "run_id", "target", "cohort_sha256"))):
        raise ValueError("Invalid compact prediction metadata")
    pool = Path(path).parent / "cohorts" / (record["cohort"] + ".parquet")
    if not pool.resolve().is_relative_to(Path(path).parent.resolve()) or not pool.is_file() or digest(pool) != record["cohort_sha256"]:
        raise ValueError("Missing/corrupt prediction cohort")
    return record, pool


def validate_prediction(path):
    metadata = prediction_metadata(path)
    if metadata is None:
        return validate_parquet(path)
    record, pool = metadata
    count = 0
    with pq.ParquetFile(path) as values, pq.ParquetFile(pool) as keys:
        if values.metadata.num_rows != record["rows"] or keys.metadata.num_rows != record["rows"]:
            raise ValueError("Compact prediction/cohort row count mismatch")
        if values.schema_arrow.names != ["position", "predicted"] or keys.schema_arrow.names != ["position"] + IDENTITY:
            raise ValueError("Compact prediction/cohort schema mismatch")
        for a, b in zip(values.iter_batches(batch_size=50000), keys.iter_batches(batch_size=50000)):
            x, y = a.to_pandas(), b.to_pandas()
            position = np.arange(count, count + len(x), dtype=np.int64)
            if (len(x) != len(y) or not np.array_equal(x.position, position) or not np.array_equal(y.position, position)
                    or not np.isfinite(x.predicted).all() or not np.isfinite(y.actual).all()
                    or y.row_id.isna().any() or y.match_id.isna().any()):
                raise ValueError("Compact prediction position/identity/target mismatch")
            count += len(x)
    if count != record["rows"]:
        raise ValueError("Truncated compact prediction")
    return count


def prediction_sql(path):
    metadata = prediction_metadata(path)
    if metadata is None:
        return "SELECT * FROM read_parquet(" + quote(path) + ")"
    record, pool = metadata
    validate_prediction(path)
    return f"""SELECT c.row_id,c.match_id,c.team_id,c.team_size_mode,c.split,c.actual,v.predicted,
        c.actual-v.predicted residual,{quote(record['experiment'])} AS experiment,
        {quote(record['run_id'])} AS run_id,{quote(record['target'])} AS "target"
        FROM read_parquet({quote(pool)}) c JOIN read_parquet({quote(path)}) v USING(position)"""


def prediction_batches(path, columns):
    metadata = prediction_metadata(path)
    if metadata is None:
        with pq.ParquetFile(path) as file:
            yield from file.iter_batches(batch_size=50000, columns=columns)
        return
    record, pool = metadata
    validate_prediction(path)
    with pq.ParquetFile(path) as values, pq.ParquetFile(pool) as keys:
        for a, b in zip(values.iter_batches(batch_size=50000), keys.iter_batches(batch_size=50000)):
            frame = b.to_pandas().drop(columns="position")
            frame["predicted"] = a.column("predicted").to_numpy()
            frame["residual"] = frame.actual - frame.predicted
            for key in ("experiment", "run_id", "target"):
                frame[key] = record[key]
            yield pa.RecordBatch.from_pandas(frame[columns], preserve_index=False)


def publish_prediction(ctx, source, target, bundle):
    if not normalized(ctx):
        publish(Path(source), target)
        return ctx.record(target)
    pool_id = fingerprint({"cohort": bundle["cohort"]["cohort_hash"],
                           "split": bundle["cohort"]["split"], "target": bundle["target"]})
    pool = target.parent / "cohorts" / (pool_id + ".parquet")
    with tempfile.TemporaryDirectory(prefix="pubg-prediction-", dir=ctx.temp) as folder:
        candidate = Path(folder) / "cohort.parquet"
        with pq.ParquetFile(bundle["metadata"]) as metadata:
            schema = pa.schema([pa.field("position", pa.int64())] + [
                pa.field("actual" if c == bundle["target"] else c, metadata.schema_arrow.field(c).type)
                for c in metadata.schema_arrow.names])
            with pq.ParquetWriter(candidate, schema, compression="zstd") as writer:
                offset = 0
                for batch in metadata.iter_batches(batch_size=50000):
                    frame = batch.to_pandas().rename(columns={bundle["target"]: "actual"})
                    frame.insert(0, "position", np.arange(offset, offset + len(frame), dtype=np.int64))
                    writer.write_table(pa.Table.from_pandas(frame, schema=schema, preserve_index=False))
                    offset += len(frame)
        if offset != bundle["rows"]:
            raise ValueError("Prediction cohort size changed")
        expected = digest(candidate)
        if pool.exists():
            if digest(pool) != expected:
                raise ValueError("Prediction shared cohort content mismatch")
        else:
            publish(candidate, pool)
        ctx.record(pool)
        with pq.ParquetFile(source) as source_file, pq.ParquetFile(pool) as pool_file:
            facts = next(source_file.iter_batches(batch_size=1, columns=["experiment", "run_id", "target"])).to_pandas().iloc[0]
            record = {"format": 1, "cohort": pool_id, "cohort_sha256": expected, "rows": offset,
                      **{key: str(facts[key]) for key in ("experiment", "run_id", "target")}}
            schema = pa.schema([pa.field("position", pa.int64()), pa.field("predicted", pa.float64())],
                               metadata={PREDICTION_KEY: json.dumps(record, sort_keys=True).encode()})
            packed = Path(folder) / "values.parquet"
            count = 0
            with pq.ParquetWriter(packed, schema, compression="zstd") as writer:
                for a, b in zip(source_file.iter_batches(batch_size=50000), pool_file.iter_batches(batch_size=50000)):
                    values, keys = a.to_pandas(), b.to_pandas()
                    if len(values) != len(keys) or not values[IDENTITY].equals(keys[IDENTITY]):
                        raise ValueError("Prediction shared cohort identity mismatch")
                    if any(not values[k].eq(record[k]).all() for k in ("experiment", "run_id", "target")):
                        raise ValueError("Prediction constants changed")
                    frame = pd.DataFrame({"position": keys.position, "predicted": values.predicted})
                    if not np.isfinite(frame.predicted).all():
                        raise ValueError("Nonfinite compact prediction")
                    writer.write_table(pa.Table.from_pandas(frame, schema=schema, preserve_index=False))
                    count += len(frame)
            if count != offset or source_file.metadata.num_rows != offset:
                raise ValueError("Prediction size mismatch")
        validate_parquet(packed)
        publish(packed, target)
    validate_prediction(target)
    return ctx.record(target)
