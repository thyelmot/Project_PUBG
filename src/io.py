"""Config, stage checkpoints và publication có read-back."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import copy
import errno
import csv
import json
import os
import platform
import importlib.metadata
import shutil
import tempfile
import time
import uuid
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import yaml
import psutil


class PendingDecision(RuntimeError):
    """Diagnostics đã lưu nhưng quyết định nghiên cứu chưa được chốt."""


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def frame_fingerprint(frame, batch_rows=50000):
    """Same JSON-list digest without materializing millions of dicts at once."""
    return frame_batches_fingerprint(frame.iloc[start:start+batch_rows] for start in range(0,len(frame),batch_rows))


def frame_batches_fingerprint(frames):
    """Identical record serialization for streamed, ordered DataFrame batches."""
    h=hashlib.sha256();h.update(b"[");first=True
    for frame in frames:
        records=frame.to_dict("records")
        encoded=json.dumps(records,sort_keys=True,default=str)[1:-1].encode()
        if encoded:
            if not first:h.update(b", ")
            h.update(encoded);first=False
    h.update(b"]")
    return h.hexdigest()


def matrix_budget(cfg):
    """Reserve host memory for the notebook, SQL and concurrent allocations."""
    available=psutil.virtual_memory().available
    runtime=cfg["runtime"]
    if runtime.get("memory_policy","fixed")=="auto":
        return int(available*runtime.get("memory_fraction",.6))
    return min(int(runtime["max_matrix_gb"]*2**30),available)


def require_memory(cfg,required,label):
    budget=matrix_budget(cfg)
    if required>budget:
        raise MemoryError(f"{label}: estimate {required/2**30:.2f} GiB > available budget {budget/2**30:.2f} GiB. "
                          "Need more host RAM; no sampling or estimator fallback.")
    return budget


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def publish(temp, target, *, consume=False):
    """Giữ bản tốt qua read-back; consume chỉ dành cho file tạm do caller sở hữu."""
    temp, target = Path(temp), Path(target)
    if consume and temp.resolve() == target.resolve():
        raise ValueError("Không consume chính file đích")
    expected = digest(temp)
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_name(target.name + "." + uuid.uuid4().hex + ".partial")
    previous = None
    try:
        if consume:
            try:
                os.replace(temp, staged)
            except OSError as error:
                if error.errno != errno.EXDEV:
                    raise
                shutil.copyfile(temp, staged)
        else:
            shutil.copyfile(temp, staged)
        if digest(staged) != expected:
            raise IOError("Publication staging checksum mismatch")
        if target.exists():
            previous = staged.with_suffix(".previous")
            shutil.copyfile(target, previous)
        os.replace(staged, target)
        if digest(target) != expected:
            raise IOError("Publication read-back mismatch")
        if consume:
            temp.unlink(missing_ok=True)
    except Exception:
        if previous and previous.exists():
            os.replace(previous, target)
        raise
    finally:
        staged.unlink(missing_ok=True)
        if previous:
            previous.unlink(missing_ok=True)
    return target


def write_json(value, target):
    with tempfile.TemporaryDirectory(prefix="pubg-json-") as folder:
        temp = Path(folder) / "value.json"
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return publish(temp, target)


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def ident(value):
    return '"' + str(value).replace('"', '""') + '"'


def validate_parquet(path):
    with pq.ParquetFile(path) as file:
        count = sum(batch.num_rows for batch in file.iter_batches(batch_size=50000))
        if count != file.metadata.num_rows:
            raise IOError(f"Parquet row count mismatch: {path}")
    return count


def artifact_info(root,path):
    value={"path":path.relative_to(root).as_posix(),"sha256":digest(path),"bytes":path.stat().st_size}
    if path.suffix==".parquet":
        file=pq.ParquetFile(path)
        value.update(rows=file.metadata.num_rows,schema=str(file.schema_arrow))
    elif path.suffix==".csv":
        with path.open(encoding="utf-8",newline="") as stream:
            reader=csv.reader(stream);columns=next(reader)
            value.update(rows=sum(1 for _ in reader),columns=columns)
    return value


STAGE_CONFIG = {
    "S01": ["source", "schema"], "S02": ["preprocessing", "split"],
    "S03": ["timing"], "S04": ["timing"], "S05": ["features"], "S06": [],
    "S07": ["rq2"], "S08": ["rq3", "models", "features"],
    "S09": ["report"], "S10": [],
}
DEPENDENCIES = {
    "S01": [], "S02": ["S01"], "S03": ["S02"], "S04": ["S03", "S01"],
    "S05": ["S04"], "S06": ["S05"], "S07": ["S05", "S06"],
    "S08": ["S04", "S05", "S07"], "S09": ["S08"],
    "S10": ["S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09"],
}


def load_config(root):
    cfg = yaml.safe_load((Path(root) / "configs/project.yaml").read_text(encoding="utf-8"))
    if cfg.get("project_id") != "pubg-coursework-2026-v5":
        raise ValueError("Sai project marker; không dùng project/config cũ")
    ratios = cfg["split"]["ratios"]
    if len(ratios) != 3 or any(not isinstance(x, (int, float)) or x <= 0 for x in ratios) or not np.isclose(sum(ratios), 1):
        raise ValueError("Split ratios phải dương và có tổng 1")
    if cfg["runtime"]["batch_rows"] != 50000:
        raise ValueError("PUBG_BATCH_ROWS đã chốt là 50000")
    for key in ("rq2", "rq3"):
        if cfg[key]["device"] not in {"cpu", "cuda"}:
            raise ValueError(f"Device không hợp lệ: {key}")
        ids=cfg[key].get("gpu_ids",[0])
        if (not isinstance(ids,list) or len(ids) not in (1,2)
                or any(type(i) is not int or i<0 for i in ids) or len(set(ids))!=len(ids)):
            raise ValueError(f"gpu_ids không hợp lệ: {key}")
    if cfg["rq2"]["mode_strategy"] != "per_mode":
        raise ValueError("RQ2 phải per_mode")
    if not cfg["models"].get("linear"):
        raise ValueError("Linear Regression là core bắt buộc")
    if cfg["runtime"]["max_matrix_gb"]<=0 or cfg["runtime"]["threads"]<1:
        raise ValueError("Resource budget/threads phải dương")
    if cfg["runtime"].get("memory_policy","fixed") not in {"fixed","auto"} or not 0<cfg["runtime"].get("memory_fraction",.6)<=.75:
        raise ValueError("memory_policy fixed/auto; memory_fraction must be in (0, .75]")
    if cfg["models"].get("random_forest"):
        raise ValueError("RF chưa thuộc implementation core; không bật placeholder")
    if cfg["storage"].get("output_budget_gb",18.0)<=0:
        raise ValueError("Output budget phải dương")
    if cfg["storage"].get("layout","materialized") not in {"materialized","normalized_v1"}:
        raise ValueError("Unknown storage layout")
    for section in ("preprocessing", "features", "rq2", "rq3"):
        if cfg[section].get("decision_mode", "manual") not in {"auto", "manual"}:
            raise ValueError(f"decision_mode phải auto/manual: {section}")
    if cfg["timing"].get("unit_status") not in {"pending","verified","assumed_seconds"}:
        raise ValueError("timing.unit_status phải pending/verified/assumed_seconds")
    if not isinstance(cfg["timing"].get("unit_assumption_approved",False),bool):
        raise ValueError("unit_assumption_approved phải boolean")
    parts=cfg["timing"].get("partitions",16)
    if type(parts) is not int or not 1<=parts<=256:
        raise ValueError("timing.partitions must be an integer in [1,256]")
    return cfg


def time_unit_info(cfg):
    """A source-bound, approved assumption is accepted but never called verified."""
    timing=cfg["timing"]
    status=timing.get("unit_status","pending")
    evidence=timing.get("unit_evidence")
    evidence=evidence.strip() if isinstance(evidence,str) else ""
    source=cfg["source"]
    reference=f"{source.get('dataset')}/versions/{source.get('version')}"
    assumed=status=="assumed_seconds"
    approved=timing.get("unit_assumption_approved") is True
    bound=timing.get("unit_assumption_scope")==reference and source.get("version") is not None
    accepted=bool(evidence) and (status=="verified" or assumed and approved and bound)
    label="Giây (giả định, chưa xác minh)" if assumed else ("Giây" if status=="verified" else "Đơn vị thời gian nguồn chưa xác định")
    limitation=("Đơn vị giây là giả định được duyệt, chưa được tác giả nguồn xác nhận. "
                "Đối chiếu mẫu hỗ trợ cùng thang đo, không xác minh đơn vị tuyệt đối; không tự đổi thang hoặc bỏ dòng lệch."
                if assumed else ("" if status=="verified" else "Chưa xác định đơn vị thời gian nguồn."))
    return {"status":status,"accepted":accepted,"verified":status=="verified" and accepted,
            "unit":"seconds" if status in {"verified","assumed_seconds"} else "unknown",
            "label":label,"evidence":evidence,"source_reference":reference,
            "assumption_approved":assumed and approved,"assumption_scope":timing.get("unit_assumption_scope") if assumed else None,
            "limitation":limitation}


def stage_options(ctx, stage, options):
    """Persist explicit cell overrides; None inherits the project configuration."""
    section = {"S01":"source", "S02":"preprocessing", "S04":"timing", "S05":"features",
               "S07":"rq2", "S08":"rq3", "S09":"report"}.get(stage)
    if not options:
        return
    if section is None:
        raise ValueError(f"{stage} không có tùy chọn nghiên cứu riêng")
    cfg = copy.deepcopy(ctx.cfg)
    for key, value in options.items():
        if key not in cfg[section]:
            raise ValueError(f"Tùy chọn không hợp lệ: {stage}/{key}")
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(cfg[section][key], dict):
            if set(value)-set(cfg[section][key]):
                raise ValueError(f"Khóa không hợp lệ: {stage}/{key}")
            cfg[section][key].update(value)
        else:
            cfg[section][key] = value
    if cfg != ctx.cfg:
        # Validate before publishing; a typo must not replace a good config.
        with tempfile.TemporaryDirectory(prefix="pubg-config-") as folder:
            check = Path(folder)
            (check/"configs").mkdir()
            (check/"configs/project.yaml").write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding="utf-8")
            load_config(check)
            publish(check/"configs/project.yaml", ctx.root/"configs/project.yaml")
        ctx.cfg = cfg


def software_versions():
    versions={"python":platform.python_version()}
    for name in ("numpy","pandas","duckdb","pyarrow","scikit-learn","scipy","matplotlib","PyYAML","joblib",
                 "cuml","cuml-cu12","cuml-cu13","cupy","cupy-cuda12x","cupy-cuda13x"):
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:pass
    return versions


def check_output_budget(root,budget_gb):
    size=sum(p.stat().st_size for p in Path(root).rglob("*") if p.is_file())
    if size>budget_gb*2**30:
        raise MemoryError("Working project vượt output budget; dừng, không bỏ cohort/artifact cần resume")
    return size


class Context:
    def __init__(self, root, scope="full", writer="", force_takeover=False, progress=None):
        self.root = Path(root).resolve()
        self.cfg = load_config(self.root)
        if scope not in {"development", "full"}:
            raise ValueError("Scope phải development/full")
        self.scope = scope
        self.out = self.root / "outputs" / scope
        self.data = self.root / "data" / scope
        self.writer = writer or f"{platform.node()}-{uuid.uuid4().hex[:8]}"
        self.force = force_takeover
        self.manifest_path = self.out / "checkpoints/stages.json"
        self.created = []
        self.software=software_versions()
        self.progress_callback=progress
        self.events=[]
        self.active_stage=""
        temp_cfg = self.cfg["runtime"].get("temp_directory")
        self.temp = Path(temp_cfg) if temp_cfg else Path(tempfile.gettempdir()) / f"pubg-spill-{uuid.uuid4().hex}"
        self.temp.mkdir(parents=True, exist_ok=True)

    def db(self):
        con = duckdb.connect()
        try:
            return self._configure_db(con)
        except Exception:
            con.close()
            raise

    def _configure_db(self, con, temp_directory=None):
        con.execute(f"SET memory_limit={quote(self.cfg['runtime']['duckdb_memory'])}")
        con.execute(f"SET threads={int(self.cfg['runtime']['threads'])}")
        con.execute(f"SET temp_directory={quote(temp_directory or self.temp)}")
        con.execute("SET preserve_insertion_order=false")
        return con

    @contextmanager
    def disk_db(self):
        """Owned scratch database; close before removing its files, including on failure."""
        with tempfile.TemporaryDirectory(prefix="pubg-sql-", dir=self.temp) as folder:
            con=duckdb.connect(str(Path(folder)/"stage.duckdb"))
            try:
                # Separate database instances must not overwrite each other's spill files.
                self._configure_db(con,Path(folder)/"spill")
                yield con
            finally:
                con.close()

    def path(self, name):
        return self.out / name

    def manifest(self):
        return read_json(self.manifest_path) if self.manifest_path.exists() else {}

    def record(self, path):
        path = Path(path)
        if path not in self.created:
            self.created.append(path)
        check_output_budget(self.root,self.cfg["storage"].get("output_budget_gb",18.0))
        return path

    def progress(self,step,**counts):
        event={"stage":self.active_stage,"step":step,"scope":self.scope,
               "elapsed_seconds":round(time.monotonic()-getattr(self,"stage_started",time.monotonic()),2),**counts}
        self.events.append(event)
        self.events=self.events[-200:]  # Chỉ lưu 200 sự kiện gần nhất; không phải ledger toàn dữ liệu.
        if self.progress_callback:self.progress_callback(event)
        else:print(json.dumps(event,ensure_ascii=True),flush=True)

    def table(self, name, frame):
        target = self.path("tables/" + name + ".csv")
        with tempfile.TemporaryDirectory(prefix="pubg-table-") as folder:
            temp = Path(folder) / "table.csv"
            frame.to_csv(temp, index=False)
            publish(temp, target)
        return self.record(target)

    def json(self, name, value):
        return self.record(write_json(value, self.path("manifests/" + name + ".json")))

    def parquet(self, con, query, name):
        target = self.data / (name + ".parquet")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Cùng filesystem để publish bằng rename, không nhân đôi Parquet lớn.
        with tempfile.TemporaryDirectory(prefix=".pubg-parquet-", dir=target.parent) as folder:
            temp = Path(folder) / "data.parquet"
            con.execute(f"COPY ({query}) TO {quote(temp)} (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 50000)")
            validate_parquet(temp)
            publish(temp, target, consume=True)
        return self.record(target)

    def view(self, con, name, dataset):
        from .storage import dataset_sql
        con.execute(f"CREATE OR REPLACE VIEW {ident(name)} AS "+dataset_sql(self,dataset))

    def signature(self, stage, _validated=None, _hashes=None):
        validated=set() if _validated is None else _validated
        hashes={} if _hashes is None else _hashes
        def sha(path):
            if path not in hashes:hashes[path]=digest(path)
            return hashes[path]
        records = self.manifest()
        deps = {}
        for dependency in DEPENDENCIES[stage]:
            self.require(dependency,validated,hashes)
            deps[dependency] = records[dependency]["signature"]
        source_files = []
        if stage == "S01":
            source = self.cfg["source"].get("directory")
            if not source:
                raise PendingDecision("source.directory còn null; nhập thư mục chứa CSV mới")
            for group in ("aggregate_patterns", "event_patterns"):
                for pattern in self.cfg["source"][group]:
                    for p in sorted(Path(source).glob(pattern)):
                        if p.is_file():
                            if not p.resolve().is_relative_to(Path(source).resolve()):raise ValueError("Source link ngoài Input root")
                            source_files.append((p.relative_to(source).as_posix(),sha(p)))
        config={k:dict(self.cfg[k]) for k in STAGE_CONFIG[stage]}
        if stage!="S01":config["storage_layout"]=self.cfg["storage"].get("layout","materialized")
        if "source" in config:config["source"].pop("directory",None)
        runtime={k:v for k,v in self.cfg["runtime"].items() if k!="temp_directory"}
        return fingerprint({"project": self.cfg["project_id"], "scope": self.scope, "stage": stage,
                            "config":config,"runtime":runtime,"dependencies":deps,"software":self.software,
                            "code": {p.name:sha(p) for p in sorted((self.root / "src").glob("*.py"))},
                            "source": sorted(set(source_files))})

    def require(self, stage, _validated=None, _hashes=None):
        validated=set() if _validated is None else _validated
        hashes={} if _hashes is None else _hashes
        record = self.manifest().get(stage, {})
        if stage in validated:return record
        if record.get("status") != "completed" or not record.get("artifacts"):
            raise RuntimeError(f"{stage} chưa completed; xem {self.manifest_path}")
        for artifact in record["artifacts"]:
            path = (self.root / artifact["path"]).resolve()
            if not path.is_relative_to(self.root):raise ValueError("Artifact ngoài project root")
            if path.is_file() and path not in hashes:hashes[path]=digest(path)
            if not path.is_file() or hashes[path] != artifact["sha256"]:
                raise RuntimeError(f"{stage} artifact thiếu/hỏng/stale: {path}")
        # Check dependency/config changes even when a later stage is entered directly.
        if record["signature"] != self.signature(stage,validated,hashes):
            raise RuntimeError(f"{stage} signature stale; chạy lại producer với config hiện hành")
        validated.add(stage)
        return record

    def run(self, stage, function):
        self.active_stage=stage
        self.stage_started=time.monotonic()
        self.events=[]
        self.progress("checking prerequisites")
        signature = self.signature(stage)
        records = self.manifest()
        old = records.get(stage, {})
        if old.get("status") == "completed" and old.get("signature") == signature:
            check_output_budget(self.root,self.cfg["storage"].get("output_budget_gb",18.0))
            self.require(stage)
            self.progress("reuse verified completed",recomputed=False)
            print(f"{stage}: reuse completed compatible")
            return
        lock = self.out / "checkpoints" / (stage + ".lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock.mkdir()
        except FileExistsError:
            owner_file = lock / "owner.json"
            owner = read_json(owner_file) if owner_file.exists() else {}
            if not self.force:
                raise RuntimeError(f"{stage} đang khóa bởi {owner}; chỉ takeover khi chắc phiên cũ đã dừng")
            shutil.rmtree(lock)
            lock.mkdir()
        write_json({"writer": self.writer, "started": time.time()}, lock / "owner.json")
        self.force = False
        self.created = []
        record = {"status": "running", "signature": signature, "writer": self.writer,
                  "scope": self.scope, "started": time.time(), "artifacts": []}
        records[stage] = record
        write_json(records, self.manifest_path)
        try:
            self.progress("running")
            function(self)
            if not self.created:
                raise ValueError(f"{stage} không có artifact; không commit rỗng")
            self.progress("completed runtime; Kaggle Version chưa được xác minh")
            self.table("progress_"+stage,pd.DataFrame(self.events))
            record["artifacts"] = [artifact_info(self.root,p) for p in self.created]
            record["status"] = "completed"
        except Exception as error:
            record["status"] = "pending" if isinstance(error, PendingDecision) else (
                "resource_limited" if isinstance(error, MemoryError) or "out of memory" in str(error).lower()
                or isinstance(error,OSError) and error.errno in {errno.ENOSPC,errno.EDQUOT} else "failed")
            record["reason"] = str(error)
            raise
        finally:
            record["finished"] = time.time()
            current = self.manifest()
            if read_json(lock / "owner.json")["writer"] != self.writer:
                raise RuntimeError("Writer ownership changed; không ghi đè manifest")
            current[stage] = record
            write_json(current, self.manifest_path)
            shutil.rmtree(lock)

    def environment(self):
        return pd.DataFrame([{"project_id": self.cfg["project_id"], "scope": self.scope,
                              "root": str(self.root), "writer": self.writer,
                              "python": platform.python_version(), "duckdb": duckdb.__version__,
                              "free_runtime_disk_GiB": shutil.disk_usage(self.temp).free / 2**30,
                              "available_host_RAM_GiB":psutil.virtual_memory().available/2**30,
                              "software":json.dumps(self.software),
                              "note": "Disk runtime không phải giới hạn saved output/quota GPU; CPU local không chứng minh Kaggle/GPU"}])


def compute_metadata(device,matrix_bytes=0):
    value={"device":device,"python":platform.python_version(),"host_available_bytes":psutil.virtual_memory().available,
           "packages":{name:importlib.metadata.version(name) for name in ("numpy","pandas","duckdb","pyarrow","scikit-learn","scipy","matplotlib","PyYAML","joblib","psutil")}}
    if matrix_bytes*4 > value["host_available_bytes"]:
        raise MemoryError("Matrix estimate vượt host available RAM")
    if device=="cuda":
        try:
            import cupy
            import cuml
            gpu_count=cupy.cuda.runtime.getDeviceCount()
            gpus=[]
            for index in range(gpu_count):
                with cupy.cuda.Device(index):
                    free,total=cupy.cuda.runtime.memGetInfo()
                    props=cupy.cuda.runtime.getDeviceProperties(index)
                    gpus.append({"gpu_id":index,"name":str(props.get("name")),"free_bytes":free,"total_bytes":total})
            if not gpus:raise RuntimeError("Không có CUDA GPU")
            current=cupy.cuda.runtime.getDevice()
            free,total=gpus[current]["free_bytes"],gpus[current]["total_bytes"]
            props=cupy.cuda.runtime.getDeviceProperties(current)
            value.update(gpu_name=str(props.get("name")),gpu_free_bytes=free,gpu_total_bytes=total,
                         cuml_version=cuml.__version__,cupy_version=cupy.__version__,gpu_count=gpu_count,gpus=gpus)
            if matrix_bytes*4>free:
                raise MemoryError("Matrix estimate vượt GPU free VRAM")
        except MemoryError:
            raise
        except Exception as error:
            raise RuntimeError("GPU metadata không xác minh được; không fallback CPU") from error
    return value
