"""Kaggle Input/working và bàn giao file; không đăng nhập/upload tự động."""
from pathlib import Path, PurePosixPath
import json
import shutil
import tempfile
import zipfile
import re
import ast
import os
import subprocess
import sys
import hashlib

import numpy as np
import yaml

from .io import (Context, artifact_info, check_output_budget, compute_metadata, digest,
                 load_config, publish, read_json, software_versions, validate_parquet, write_json, time_unit_info, matrix_budget)

CODE_FILES=["configs/project.yaml","requirements.txt","PUBG_RESEARCH_SPEC.md","README.md",
            "PUBG_IMPLEMENTATION_PLAN.md","AGENTS.md","notebooks/PUBG_COURSEWORK.ipynb"]


def safe_file(root,name):
    """Untrusted manifest paths cannot escape the selected Input root."""
    relative=PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
        raise ValueError("Unsafe handoff path")
    path=(Path(root)/name).resolve()
    if not path.is_relative_to(Path(root).resolve()) or not path.is_file():
        raise ValueError("Missing/unsafe handoff file: "+name)
    return path


def code_files(root):
    root=Path(root)
    load_config(root)
    files=[safe_file(root,name) for name in CODE_FILES if (root/name).is_file()]
    if not (root/"src/io.py").is_file():raise FileNotFoundError("Thiếu src/io.py")
    files += [safe_file(root,p.relative_to(root).as_posix()) for p in sorted((root/"src").glob("*.py"))]
    return files


def prepare_project(code_input,target):
    source,target=Path(code_input).resolve(),Path(target).resolve()
    if target.is_relative_to(source):raise ValueError("Working không được nằm trong code Input")
    files=code_files(source)
    if target.exists() and any(target.iterdir()):
        load_config(target)
        for path in files:
            if path.parent==source/"src" and digest(path)!=digest(safe_file(target,path.relative_to(source).as_posix())):
                raise RuntimeError("Working chứa code khác Input; không ghi đè project đang chạy")
        return target
    target.mkdir(parents=True,exist_ok=True)
    for path in files:publish(path,target/path.relative_to(source))
    load_config(target)
    return target


def code_archive(root,target):
    """Build a light upload artifact; excludes data, outputs, tokens and old project."""
    root,target=Path(root).resolve(),Path(target).resolve()
    with tempfile.TemporaryDirectory(prefix="pubg-code-") as folder:
        archive=Path(folder)/"code.zip"
        with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as z:
            for path in code_files(root):z.write(path,path.relative_to(root).as_posix())
        publish(archive,target)
    return target


LEGACY_S01_CODE="71de81ca811d4d66ebb1c432c56a370c12fb48e41411adee5996eb436af23690"


def import_s01_510(source_root,code_input,target,scope,source_directory,source_version=None,source_license=""):
    """Explicit verified import; never edit a live old project or infer completion."""
    source_root,code_input,target=map(lambda p:Path(p).resolve(),(source_root,code_input,target))
    if scope not in {"development","full"} or target==source_root or target.is_relative_to(source_root):
        raise ValueError("S01 import requires a separate new working root and valid scope")
    if list((source_root/"outputs"/scope/"checkpoints").glob("*.lock")):
        raise RuntimeError("Old project has a writer lock; stop it before importing")
    import hashlib
    h=hashlib.sha256()
    for p in sorted((source_root/"src").glob("*.py")):h.update(p.name.encode());h.update(p.read_bytes())
    if h.hexdigest()!=LEGACY_S01_CODE:raise ValueError("Only the audited 5.10 S01 producer can be imported")
    old_cfg=load_config(source_root);new_cfg=load_config(code_input)
    for key,value in (("version",source_version),("license",source_license)):
        if value not in (None,"") and old_cfg["source"].get(key)!=value:
            raise ValueError("S01 import source fact mismatch: "+key)
    if old_cfg["spec_version"]!="5.10-evaluation-out-of-core" or new_cfg["spec_version"]!="5.11-normalized-storage":
        raise ValueError("Unsupported S01 import versions")
    if (source_root/"requirements.txt").read_bytes()!=(code_input/"requirements.txt").read_bytes():
        raise ValueError("S01 import requirements changed")
    # The parser, serialization and publication must be unchanged, not merely the version label.
    def definitions(root,file):
        tree=ast.parse((root/"src"/file).read_text(encoding="utf-8"))
        result={}
        for node in tree.body:
            if isinstance(node,(ast.FunctionDef,ast.ClassDef)):
                result[node.name]=ast.dump(node,include_attributes=False)
                if isinstance(node,ast.ClassDef):
                    for child in node.body:
                        if isinstance(child,ast.FunctionDef):result[node.name+"."+child.name]=ast.dump(child,include_attributes=False)
            elif isinstance(node,ast.Assign):
                for name in node.targets:
                    if isinstance(name,ast.Name):result[name.id]=ast.dump(node.value,include_attributes=False)
        return result
    for file,names in (("preprocessing.py",["ingest","NUMERIC","COUNTS","AGG_REQUIRED","EVENT_REQUIRED"]),
                       ("io.py",["digest","publish","quote","ident","validate_parquet","Context.parquet","Context.db","Context._configure_db"])):
        old,new=definitions(source_root,file),definitions(code_input,file)
        if any(old[name]!=new[name] for name in names):raise ValueError("S01 parser/writer proof changed: "+file)
    if target.exists() and any(target.iterdir()):
        receipt=target/"s01_import_510.json"
        if not receipt.is_file() or read_json(receipt).get("producer_root")!=str(source_root):
            raise ValueError("Import target is not empty or not owned by this migration")
        ctx=Context(target,scope,progress=lambda _:None);ctx.require("S01")
        return target
    script="""import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from src.io import Context
ctx=Context(Path(sys.argv[1]),sys.argv[2],progress=lambda _:None)
ctx.cfg['source']['directory']=sys.argv[3]
record=ctx.require('S01')
print(json.dumps({'record':record,'config':ctx.cfg,'software':ctx.software}))
"""
    print("S01 import: checking the original producer, every source/artifact checksum and software; not rerunning ingest",flush=True)
    checked=subprocess.run([sys.executable,"-B","-c",script,str(source_root),scope,str(Path(source_directory).resolve())],
        cwd=source_root,env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1","PYTHONUTF8":"1","PYTHONIOENCODING":"utf-8"},
        capture_output=True,text=True,encoding="utf-8",timeout=1800)
    if checked.returncode:raise RuntimeError("Original S01 verification failed: "+checked.stderr[-4000:])
    evidence=json.loads(checked.stdout.strip().splitlines()[-1])
    if evidence["software"]!=software_versions():raise ValueError("S01 import software mismatch")
    record=evidence["record"]
    expected={f"data/{scope}/aggregate.parquet",f"data/{scope}/event.parquet"}
    if not expected.issubset({a["path"] for a in record["artifacts"]}):raise ValueError("Incomplete original S01")
    print("S01 import: producer verified; validating Parquet and linking into the new project",flush=True)
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pubg-s01-import-",dir=target.parent) as folder:
        staged=Path(folder)/"project";prepare_project(code_input,staged)
        cfg=evidence["config"]
        cfg["spec_version"]=new_cfg["spec_version"]
        cfg["storage"].update(layout="normalized_v1",project_root=str(target))
        cfg["runtime"]["temp_directory"]=None
        write_json_path=staged/"configs/project.yaml"
        write_json_path.write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding="utf-8")
        for artifact in record["artifacts"]:
            source=safe_file(source_root,artifact["path"]);dest=staged/artifact["path"]
            if artifact["path"] in expected:
                validate_parquet(source)
                dest.parent.mkdir(parents=True,exist_ok=True)
                try:os.link(source,dest)
                except OSError as error:raise RuntimeError("S01 hardlink unavailable; no unsafe large-copy fallback") from error
            else:publish(source,dest)
            if digest(dest)!=artifact["sha256"]:raise ValueError("Imported S01 checksum mismatch")
        ctx=Context(staged,scope,progress=lambda _:None)
        producer={"code_sha256":LEGACY_S01_CODE,"signature":record["signature"],"scope":scope}
        record={**record,"signature":ctx.signature("S01"),"producer_import":producer}
        write_json({"S01":record},ctx.manifest_path)
        write_json({"producer_root":str(source_root),"producer":producer,"method":"verified same-filesystem hardlinks",
                    "recomputed":False,"old_project_modified":False},staged/"s01_import_510.json")
        ctx.require("S01");check_output_budget(staged,cfg["storage"]["output_budget_gb"])
        if target.exists():
            if any(target.iterdir()):raise ValueError("Import destination changed")
            target.rmdir()
        staged.rename(target)
    return target


def cleanup_imported_510(source_root,imported_root,scope,confirm=False):
    """Opt-in discard of failed S02 and old hardlink names; retained imported S01 is verified first."""
    if confirm is not True:raise ValueError("Explicit confirm=True is required to discard failed S02 and retire old S01 hardlink names")
    source_root,imported_root=Path(source_root).resolve(),Path(imported_root).resolve()
    ctx=Context(imported_root,scope,progress=lambda _:None);ctx.require("S01")
    receipt=read_json(imported_root/"s01_import_510.json")
    if receipt.get("producer_root")!=str(source_root) or receipt["producer"]["code_sha256"]!=LEGACY_S01_CODE:
        raise ValueError("S01 migration receipt mismatch")
    checkpoints=source_root/"outputs"/scope/"checkpoints"
    if list(checkpoints.glob("*.lock")):raise RuntimeError("Old writer still locked")
    if list(ctx.out.glob("checkpoints/*.lock")):raise RuntimeError("New writer still locked")
    stages=read_json(checkpoints/"stages.json")
    if stages.get("S02",{}).get("status") not in {"failed","resource_limited"} or any(
        r.get("status")=="completed" for s,r in stages.items() if s not in {"S01","S02"}):
        raise ValueError("Only a failed S02 without completed downstream stages can be discarded")
    path=source_root/"data"/scope/"cleaned.parquet"
    if path.is_symlink() or path.resolve()!=path or not path.is_relative_to(source_root/"data"/scope):
        raise ValueError("Unsafe failed-cleaned path")
    if any(a["path"]==path.relative_to(source_root).as_posix() for r in stages.values() if r.get("status")=="completed" for a in r.get("artifacts",[])):
        raise ValueError("File is owned by a completed checkpoint")
    aliases=[]
    for name in ("aggregate.parquet","event.parquet"):
        old=source_root/"data"/scope/name;new=ctx.data/name
        if old.exists():
            if old.is_symlink() or old.resolve()!=old or not os.path.samefile(old,new):
                raise ValueError("Old S01 path is not the verified shared inode")
            aliases.append(old)
    removed=[];size=0
    if path.exists():size=path.stat().st_size;path.unlink();removed.append(str(path))
    for old in aliases:old.unlink();removed.append(str(old))
    return {"removed":removed,"failed_cleaned_bytes":size,"S01_retained_at":str(ctx.data),
            "recovery":"Failed S02 must be rebuilt; S01 bytes remain at imported root. Old root is retired, not resumable."}


def preflight(ctx,start,end,kaggle=False):
    source=ctx.cfg["source"]
    if not source.get("directory") or not Path(source["directory"]).is_dir():
        raise ValueError("Điền source.directory hoặc SOURCE_DIRECTORY từ Input; chưa đọc dữ liệu")
    if kaggle and (not isinstance(source.get("version"),int) or source["version"]<1):
        raise ValueError("Pin Input version và nhập SOURCE_VERSION dương; không lấy latest")
    if ctx.scope=="full" and not source.get("license"):
        raise ValueError("Full-data cần source license/quyền sử dụng đã xác minh")
    # Fail before an expensive S01, not midway through an unattended run.
    if start<="S02"<=end and ctx.cfg["preprocessing"].get("decision_mode")=="auto" and not ctx.cfg["preprocessing"].get("mode_evidence"):
        raise ValueError("Auto S02 cần SOURCE_MODE_EVIDENCE tại S00 trước Run All; không suy ý nghĩa party_size từ dữ liệu")
    unit_info=time_unit_info(ctx.cfg)
    if start<="S04"<=end and not unit_info["accepted"]:
        raise ValueError("S04 cần SOURCE_TIME_UNIT_STATUS verified kèm evidence, hoặc assumed_seconds có evidence/approval/scope đúng nguồn; không tự xác minh đơn vị")
    check_output_budget(ctx.root,ctx.cfg["storage"]["output_budget_gb"])
    devices={"cpu"}
    for stage,key in (("S07","rq2"),("S08","rq3")):
        if start<=stage<=end:devices.add(ctx.cfg[key]["device"])
    compute=[compute_metadata(device) for device in sorted(devices)]
    gpu_selection={}
    if "cuda" in devices:
        from .gpu import device_tokens
        inventory=next(c for c in compute if c["device"]=="cuda")
        for stage,key in (("S07","rq2"),("S08","rq3")):
            if start<=stage<=end and ctx.cfg[key]["device"]=="cuda":
                gpu_selection[stage]=device_tokens(ctx.cfg[key].get("gpu_ids",[0]),inventory["gpu_count"])
    return {"source":source,"working_root":str(ctx.root),"saved_version_verified":False,"time_unit":unit_info,
            "compute":compute,"gpu_selection":gpu_selection,
            "output_budget_gb":ctx.cfg["storage"]["output_budget_gb"],
            "note":"Budget nhóm, không phải quota service đã xác minh"}


def resource_plan(ctx,start="S07",end="S10"):
    """Counts and allocation estimates only; never selects using test outcomes."""
    from .features import FEATURES
    from .analysis import PROFILE_FEATURES
    from .modeling import fit_memory_bytes, prediction_memory_bytes, regression_solver, regression_vram_bytes
    from .evaluation import bootstrap_memory_bytes, plot_memory_bytes
    budget=matrix_budget(ctx.cfg)
    report={"host_budget_GiB":budget/2**30,"memory_policy":ctx.cfg["runtime"].get("memory_policy","fixed"),
            "status":"deferred_until_S04","checks":[],"feasible":None,
            "limitation":"Estimates, not a measured peak or a guarantee of CUDA/full-data completion"}
    from .storage import dataset_path
    try:dataset_path(ctx,"player_match")
    except FileNotFoundError:return report
    checks=report["checks"]
    gpu_inventory=compute_metadata("cuda") if start<="S08"<=end and ctx.cfg["rq3"]["device"]=="cuda" else None
    jobs=[]
    solver=regression_solver(ctx.cfg["rq3"].get("solver","dense"))
    report["regression_solver"]=solver
    with ctx.disk_db() as con:
        ctx.view(con,"p","player_match")
        if start<="S07"<=end:
            n=con.execute("SELECT count(*) FROM (SELECT player_name,team_size_mode FROM p WHERE player_name IS NOT NULL AND team_size_mode IN ('Solo','Duo','Squad') GROUP BY ALL)").fetchone()[0]
            checks.append({"step":"S07 profiles","rows":n,"estimated_bytes":n*len(PROFILE_FEATURES)*8*10})
        if start<="S08"<=end:
            for task,columns in FEATURES.items():
                validity="valid_survival" if task=="s1" else "valid_placement"
                # Exact counts, but no test targets/predictions/metrics are read here.
                counts=dict(con.execute(f"SELECT split,count(*) FROM p WHERE {validity} GROUP BY split").fetchall())
                # Prediction batches use the maximum key length; metrics stay on disk.
                strings=" + ".join(f"coalesce(length(CAST({name} AS VARCHAR)),0)" for name in
                                     ("row_id","match_id","team_id","team_size_mode","split"))
                chars=dict(con.execute(f"SELECT split,coalesce(max({strings}),0) FROM p WHERE {validity} GROUP BY split").fetchall())
                for split,n in counts.items():
                    estimate=fit_memory_bytes(n,len(columns),solver) if split=="train" else prediction_memory_bytes(n,chars[split])
                    checks.append({"step":f"S08 {task}/{split}","rows":n,"estimated_bytes":estimate})
                rows=counts.get("train",0)+counts.get("validation",0)
                host_bytes=fit_memory_bytes(counts.get("train",0),len(columns),solver)+prediction_memory_bytes(counts.get("validation",0),chars.get("validation",0))
                jobs.append({"step":f"S08 {task} worker","rows":rows,"estimated_bytes":host_bytes})
                if gpu_inventory:
                    required=regression_vram_bytes(counts.get("train",0),len(columns),solver)
                    ids=ctx.cfg["rq3"].get("gpu_ids",[0])
                    gpu_id=ids[(len(jobs)-1)%len(ids)]
                    free=gpu_inventory["gpus"][gpu_id]["free_bytes"]
                    checks.append({"step":f"S08 {task} GPU {gpu_id}","rows":counts.get("train",0),
                                   "estimated_bytes":required,"capacity_bytes":free,"resource":"VRAM"})
        if start<="S09"<=end:
            for task,validity in (("s1","valid_survival"),("p2","valid_placement")):
                n=con.execute(f"SELECT count(*) FROM p WHERE split='test' AND {validity}").fetchone()[0]
                checks.append({"step":f"S09 {task} exact plot sampling indices","rows":n,"estimated_bytes":plot_memory_bytes(n)})
            replicates=ctx.cfg["report"]["bootstrap_replicates"]
            if replicates:
                n=con.execute("SELECT count(*) FROM (SELECT match_id FROM p WHERE split='test' AND valid_placement GROUP BY match_id)").fetchone()[0]
                checks.append({"step":"S09 paired match bootstrap states","rows":n,"estimated_bytes":bootstrap_memory_bytes(n,replicates)})
    if jobs:
        width=len(ctx.cfg["rq3"].get("gpu_ids",[0])) if gpu_inventory else 1
        for i in range(0,len(jobs),width):
            batch=jobs[i:i+width]
            checks.append({"step":" + ".join(j["step"] for j in batch),"rows":sum(j["rows"] for j in batch),
                           "estimated_bytes":sum(j["estimated_bytes"] for j in batch)})
    for check in checks:
        check["estimated_GiB"]=check["estimated_bytes"]/2**30
        check["capacity_GiB"]=check.get("capacity_bytes",budget)/2**30
        check["within_budget"]=check["estimated_bytes"]<=check.get("capacity_bytes",budget)
    report.update(status="estimated_from_actual_cohort",feasible=all(c["within_budget"] for c in checks))
    return report


def gpu_smoke(ctx=None):
    """Tiny synthetic fit/reload on real CUDA; never reads the PUBG dataset."""
    import joblib
    if ctx is not None:
        from .gpu import run_jobs
        results=[];checked=set()
        for section in ("rq2","rq3"):
            if ctx.cfg[section]["device"]!="cuda":continue
            ids=[i for i in ctx.cfg[section].get("gpu_ids",[0]) if i not in checked]
            jobs=[{"kind":"smoke","key":"smoke/GPU="+str(i),"gpu_id":i,"matrix_bytes":48*3*8,"payload":{}} for i in ids]
            if not jobs:continue
            for job,path in run_jobs(ctx,section,jobs):results.append(joblib.load(path))
            checked.update(ids)
        if not results:raise ValueError("GPU smoke cần cấu hình CUDA tường minh")
        return {"scope":"synthetic 48 rows per GPU, not PUBG results","status":"passed",
                "gpu_ids":sorted(checked),"workers":results}
    from .analysis import kmeans
    from .modeling import estimator,TSQROLS
    compute=compute_metadata("cuda")
    x=np.random.default_rng(42).normal(size=(48,3));y=x@np.array([2.,-1.,.5])+3
    with tempfile.TemporaryDirectory(prefix="pubg-gpu-smoke-") as folder:
        for name,model in (("kmeans",kmeans("cuda",2,42).fit(x)),("ols",estimator("cuda").fit(x,y))):
            path=Path(folder)/(name+".joblib");joblib.dump(model,path)
            a=np.asarray(model.predict(x));b=np.asarray(joblib.load(path).predict(x))
            if not np.allclose(a,b,rtol=1e-6,atol=1e-6):raise ValueError("GPU smoke reload mismatch")
            if name=="ols" and np.max(np.abs(a.reshape(-1)-y))>1e-4:raise ValueError("GPU OLS smoke formula mismatch")
        offset=x.mean(axis=0);y_offset=float(y.mean())
        qr=TSQROLS("cuda").fit_batches([(x[:23],y[:23]),(x[23:],y[23:])],offset,y_offset,len(x))
        path=Path(folder)/"tsqr.joblib";joblib.dump(qr,path)
        if not np.allclose(qr.predict(x),y,rtol=1e-8,atol=1e-8) or not np.array_equal(qr.predict(x),joblib.load(path).predict(x)):
            raise ValueError("GPU TSQR smoke formula/reload mismatch")
    return {"scope":"synthetic 48 rows, not PUBG results","status":"passed","tsqr":"passed",**compute}


def prepare_handoff(ctx):
    """Inventory working files only. This does not claim a Kaggle Version was saved."""
    records=ctx.manifest()
    if any(v.get("status")=="running" for v in records.values()) or list(ctx.out.glob("checkpoints/*.lock")):
        raise RuntimeError("Stage đang chạy/khóa; chưa được bàn giao")
    validated,hashes=set(),{}
    for stage,record in records.items():
        if record.get("status")=="completed":ctx.require(stage,validated,hashes)
    selected=set(code_files(ctx.root))
    for folder in (ctx.data,ctx.out):
        selected.update(p for p in folder.rglob("*") if p.is_file())
    for path in selected:
        safe_file(ctx.root,path.relative_to(ctx.root).as_posix())
        if path.suffix==".parquet":
            from .storage import validate_prediction
            validate_prediction(path)
    entries=[artifact_info(ctx.root,p) for p in sorted(selected)]
    if not (ctx.manifest_path in selected):raise ValueError("Chưa có stage manifest để bàn giao")
    check_output_budget(ctx.root,ctx.cfg["storage"]["output_budget_gb"])
    manifest={"format":1,"project_id":ctx.cfg["project_id"],"scope":ctx.scope,
              "software":ctx.software,"source":ctx.cfg["source"],"stages":records,"entries":entries,
              "saved_version_verified":False,"instructions":"Save Version với output; gắn lại Version cụ thể rồi verify_handoff"}
    return write_json(manifest,ctx.root/("handoff_"+ctx.scope+".json"))


def verify_handoff(root,scope,version_reference):
    """Read back explicitly mounted output; reference is supplied by the operator, not queried."""
    if scope not in {"development","full"} or not re.fullmatch(r"[^/\s]+/[^/\s]+/versions/[1-9]\d*",version_reference):
        raise ValueError("Cần scope và notebook slug/version cụ thể, không latest")
    root=Path(root).resolve()
    on_kaggle=Path("/kaggle/input").is_dir()
    if on_kaggle and not root.is_relative_to(Path("/kaggle/input").resolve()):
        raise ValueError("Read-back trên Kaggle phải chọn Output đã gắn như Input, không working runtime")
    manifest=read_json(safe_file(root,"handoff_"+scope+".json"))
    if manifest.get("format")!=1 or manifest.get("project_id")!="pubg-coursework-2026-v5" or manifest.get("scope")!=scope:
        raise ValueError("Sai handoff marker/scope")
    entries=manifest.get("entries",[])
    names=[a["path"] for a in entries]
    required={"configs/project.yaml","src/io.py","outputs/"+scope+"/checkpoints/stages.json"}
    if len(names)!=len(set(names)) or not required.issubset(names):raise ValueError("Incomplete/duplicate handoff")
    for entry in entries:
        path=safe_file(root,entry["path"])
        if path.stat().st_size!=entry["bytes"] or digest(path)!=entry["sha256"]:
            raise ValueError("Handoff checksum mismatch: "+entry["path"])
        if path.suffix==".parquet":
            from .storage import validate_prediction
            validate_prediction(path)
    records=read_json(root/("outputs/"+scope+"/checkpoints/stages.json"))
    if records!=manifest["stages"] or any(v.get("status")=="running" for v in records.values()):
        raise ValueError("Handoff stage records mismatch/running")
    for record in records.values():
        for artifact in record.get("artifacts",[]):
            if artifact["path"] not in names or next(a for a in entries if a["path"]==artifact["path"])["sha256"]!=artifact["sha256"]:
                raise ValueError("Stage artifact missing/mismatched in handoff")
    return manifest,{"version_reference":version_reference,"readback_verified":True,
                     "environment":"Kaggle Input" if on_kaggle else "local file read-back, not Kaggle save proof",
                     "reference_source":"operator supplied; API identity not independently verified",
                     "entries":len(entries),"scope":scope}


CPU_PRODUCER_511 = "4e3f9a191e589c963727c12bbf00ec656ee6bf17de0621ca6a6f520b3641dd3c"
GPU_PACKAGES = frozenset(("cuml", "cuml-cu12", "cuml-cu13", "cupy", "cupy-cuda12x", "cupy-cuda13x"))
CPU_STAGES = tuple(f"S{i:02d}" for i in range(1, 7))
# S07-only profile execution patch, audited separately; S01-S06 definitions stay unchanged.
CPU_RESUME_PROFILE_SHA256 = "1378b2ff27abe1438fe32185de073adc027377e1ca529a2dbd9a4d2862b3c6b1"
S07_PRODUCER_511 = "b663bd7528cd4bd0be7a64bb03f88e07f5c97418b340ba09626853691af602a0"
# Filled from the audited S08 module when the implementation is frozen.
TSQR_MODELING_SHA256 = "84dbb3e2ff7a2afc2e5062c7710618068a37ac767e1a664e497b3e369f62ce47"


def source_fingerprint(root):
    h = hashlib.sha256()
    for path in sorted((Path(root) / "src").glob("*.py")):
        h.update(path.name.encode()); h.update(path.read_bytes())
    return h.hexdigest()


def cpu_resume_policy(source, code_input, manifest, current):
    """An explicit import of the audited CPU-only prefix, never a generic mismatch waiver."""
    if source_fingerprint(source) != CPU_PRODUCER_511:
        raise ValueError("CPU resume requires the audited 5.11 producer; arbitrary code is not compatible")
    records = manifest["stages"]
    if set(records) != set(CPU_STAGES) or any(records[s].get("status") != "completed" for s in CPU_STAGES):
        raise ValueError("CPU resume requires completed S01-S06 only; no S07-S10 or partial stages")
    if any(record.get("producer_import") for record in records.values()):
        raise ValueError("CPU resume does not accept a previously migrated producer")
    if any(e["path"].startswith((f"outputs/{manifest['scope']}/models/", f"outputs/{manifest['scope']}/predictions/"))
           for e in manifest["entries"]):
        raise ValueError("CPU prefix must not contain trained models or predictions")
    saved = manifest["software"]
    if GPU_PACKAGES.intersection(saved) or {k:v for k,v in current.items() if k not in GPU_PACKAGES} != saved:
        raise RuntimeError("CPU resume requires identical Python and all CPU packages; only GPU additions are allowed")
    if (Path(source) / "requirements.txt").read_bytes() != (Path(code_input) / "requirements.txt").read_bytes():
        raise ValueError("CPU resume requirements changed")
    # Preserve the entire producer prefix. Only the pinned S07 profile implementation may differ.
    old_files = {p.name:p for p in (Path(source) / "src").glob("*.py")}
    new_files = {p.name:p for p in (Path(code_input) / "src").glob("*.py")}
    if old_files.keys() != new_files.keys():
        raise ValueError("CPU resume computational source set changed")
    for name, path in old_files.items():
        if name=="modeling.py" and digest(new_files[name])==TSQR_MODELING_SHA256:
            continue  # S08-only code; original S01-S06 signatures are still independently verified.
        if name == "analysis.py" and digest(new_files[name]) == CPU_RESUME_PROFILE_SHA256:
            def prefix_tree(file):
                tree=ast.parse(file.read_text(encoding="utf-8"))
                tree.body=[node for node in tree.body if not (isinstance(node,ast.FunctionDef)
                    and node.name in {"profiles","bounded_profiles","profile_query"})]
                return ast.dump(tree,include_attributes=False)
            if prefix_tree(path) != prefix_tree(new_files[name]):
                raise ValueError("CPU resume changed a producer analysis operation")
            continue
        if name != "kaggle_runtime.py" and path.read_bytes() != new_files[name].read_bytes():
            raise ValueError("CPU resume computational code changed: " + name)
    def definitions(path):
        return {n.name:ast.dump(n, include_attributes=False) for n in ast.parse(path.read_text(encoding="utf-8")).body
                if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    old, new = definitions(old_files["kaggle_runtime.py"]), definitions(new_files["kaggle_runtime.py"])
    if any(new.get(name) != value for name,value in old.items() if name not in {"restore_handoff","resource_plan","gpu_smoke"}):
        raise ValueError("CPU resume changed a producer runtime operation")
    if load_config(source)["spec_version"] != "5.11-normalized-storage":
        raise ValueError("CPU resume producer version changed")
    return {k:current[k] for k in sorted(GPU_PACKAGES.intersection(current))}


def restore_cpu_handoff(source, target, scope, source_directory, version_reference, code_input, manifest, evidence):
    """Validate original CPU signatures, then import unchanged artifacts with explicit provenance."""
    source, target, code_input = map(lambda p:Path(p).resolve(), (source, target, code_input))
    if source_fingerprint(code_input) != source_fingerprint(Path(__file__).resolve().parents[1]):
        raise ValueError("CODE_INPUT must match the running updated resume code")
    current = software_versions()
    added = cpu_resume_policy(source, code_input, manifest, current)
    cfg = load_config(source)
    if not Path(source_directory).is_dir():
        raise ValueError("Cần mount nguồn hiện tại khi resume")
    if target.is_relative_to(source) or (target.exists() and any(target.iterdir())):
        raise ValueError("Restore chỉ vào working project trống/mới; không ghi đè kết quả hiện có")
    if list((source / "outputs" / scope / "checkpoints").glob("*.lock")):
        raise RuntimeError("CPU producer has a writer lock")
    if any(".lock" in e["path"] for e in manifest["entries"]):
        raise ValueError("Không restore writer lock")
    total = sum(e["bytes"] for e in manifest["entries"]) + 4 * 2**20
    target.parent.mkdir(parents=True, exist_ok=True)
    if total > cfg["storage"]["output_budget_gb"] * 2**30 or total > shutil.disk_usage(target.parent).free:
        raise MemoryError("Not enough output budget/disk for CPU resume and its provenance")
    # Read-only verifier uses the frozen producer itself. Its effective CPU environment is
    # calculated from actual installed packages, not copied from the saved manifest.
    script = '''import json,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,sys.argv[1])
from src.io import Context,software_versions,read_json
root=Path(sys.argv[1]);scope=sys.argv[2]
saved=read_json(root/('handoff_'+scope+'.json'))
gpu={'cuml','cuml-cu12','cuml-cu13','cupy','cupy-cuda12x','cupy-cuda13x'}
actual=software_versions()
cpu={k:v for k,v in actual.items() if k not in gpu}
if gpu.intersection(saved['software']) or cpu!=saved['software']:
    raise RuntimeError('Producer Python/CPU packages differ')
ctx=Context(root,scope,progress=lambda _:None)
ctx.cfg['source']['directory']=str(Path(sys.argv[3]).resolve())
ctx.software=cpu
validated=set();hashes={}
for stage in ('S01','S02','S03','S04','S05','S06'):
    ctx.require(stage,validated,hashes)
raw=Path(sys.argv[3]).resolve()
source_files={p.relative_to(raw).as_posix():v for p,v in hashes.items() if p.is_relative_to(raw)}
print(json.dumps({'verified_stages':sorted(validated),'producer_cpu_software':cpu,'current_software':actual,'source_files':source_files}))
'''
    print("CPU resume: verifying original S01-S06 signatures and raw hashes; no producer is rerun", flush=True)
    checked = subprocess.run([sys.executable, "-B", "-c", script, str(source), scope, str(source_directory)],
        cwd=source, env={**os.environ, "PYTHONDONTWRITEBYTECODE":"1", "PYTHONUTF8":"1", "PYTHONIOENCODING":"utf-8"},
        capture_output=True, text=True, encoding="utf-8", timeout=1800)
    if checked.returncode:
        raise RuntimeError("Original CPU checkpoint verification failed: " + checked.stderr[-4000:])
    proof = json.loads(checked.stdout.strip().splitlines()[-1])
    if proof["verified_stages"] != list(CPU_STAGES):
        raise RuntimeError("Incomplete producer signature verification")
    print("CPU resume: verified; copying unchanged artifacts into a new working project", flush=True)
    with tempfile.TemporaryDirectory(prefix="pubg-cpu-resume-", dir=target.parent) as folder:
        staged = Path(folder) / "project"; staged.mkdir()
        for entry in manifest["entries"]:
            if entry["bytes"] > 256 * 2**20:
                print("CPU resume: copying", entry["path"], f"({entry['bytes']/2**30:.2f} GiB)", flush=True)
            publish(safe_file(source, entry["path"]), staged / entry["path"])
        # Replace code/docs only in our staging folder, never in the saved Input.
        for path in code_files(code_input):
            if path.relative_to(code_input).as_posix() != "configs/project.yaml":
                publish(path, staged / path.relative_to(code_input))
        cfg["source"]["directory"] = str(Path(source_directory).resolve())
        cfg["storage"]["project_root"] = str(target)
        (staged / "configs/project.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        provenance = staged / "outputs" / scope / "provenance"
        provenance.mkdir(parents=True, exist_ok=True)
        archive = code_archive(source, provenance / "cpu_producer_511.zip")
        receipt = provenance / "cpu_gpu_resume.json"
        write_json({"policy":"audited_511_cpu_prefix_to_gpu_v1", "source_code_sha256":CPU_PRODUCER_511,
            "target_code_sha256":source_fingerprint(code_input), "version_reference":version_reference,
            "reference_source":evidence["reference_source"], "producer_software":manifest["software"],
            "current_software":current, "added_gpu_packages":added, "producer_stages":manifest["stages"],
            "producer_handoff":manifest, "verification":proof, "recomputed_stages":[],
            "producer_archive_sha256":digest(archive)}, receipt)
        ctx = Context(staged, scope, progress=lambda _:None)
        if ctx.software != current:
            raise RuntimeError("Software changed during CPU import")
        # New compatibility signatures attest a verified import, not execution on the new backend.
        write_json({}, ctx.manifest_path)
        validated, hashes = set(), {}
        provenance_artifacts = [artifact_info(staged, p) for p in (archive, receipt)]
        for stage in CPU_STAGES:
            original = manifest["stages"][stage]
            record = {**original, "artifacts":[*original["artifacts"], *provenance_artifacts],
                "producer_import":{"policy":"audited_511_cpu_prefix_to_gpu_v1",
                    "source_code_sha256":CPU_PRODUCER_511, "signature":original["signature"],
                    "software":manifest["software"], "version_reference":version_reference, "recomputed":False}}
            record["signature"] = ctx.signature(stage, validated, hashes)
            records = ctx.manifest(); records[stage] = record
            write_json(records, ctx.manifest_path)
            ctx.require(stage, validated, hashes)
        raw = Path(source_directory).resolve()
        source_files = {p.relative_to(raw).as_posix():v for p,v in hashes.items() if p.is_relative_to(raw)}
        if not source_files or source_files != proof["source_files"]:
            raise RuntimeError("Raw source changed during CPU import; no checkpoint is published")
        write_json({**evidence, "compatibility_import":"audited_511_cpu_prefix_to_gpu_v1",
                    "recomputed_stages":[]}, staged / ("handoff_readback_" + scope + ".json"))
        check_output_budget(staged, cfg["storage"]["output_budget_gb"])
        if target.exists():
            if any(target.iterdir()):raise ValueError("Restore destination changed")
            target.rmdir()
        staged.rename(target)
    return target


def restore_s07_tsqr_handoff(source,target,scope,source_directory,version_reference,code_input,manifest,evidence):
    """Import the immutable audited S01-S07 prefix; no model/data is refit or overwritten."""
    source,target,code_input=map(lambda p:Path(p).resolve(),(source,target,code_input))
    if source_fingerprint(source)!=S07_PRODUCER_511:
        raise ValueError("S08 TSQR import requires audited Version-6 source b663bd75")
    if source_fingerprint(code_input)!=source_fingerprint(Path(__file__).resolve().parents[1]):
        raise ValueError("CODE_INPUT must match the running TSQR code")
    stages=tuple(f"S{i:02d}" for i in range(1,8))
    if set(manifest["stages"])!=set(stages) or any(manifest["stages"][s].get("status")!="completed" for s in stages):
        raise ValueError("TSQR import requires completed S01-S07 only; no partial or downstream stages")
    if manifest["software"]!=software_versions():raise RuntimeError("TSQR import needs identical Python/CPU/GPU packages")
    if (source/"requirements.txt").read_bytes()!=(code_input/"requirements.txt").read_bytes():
        raise ValueError("TSQR import requirements changed")
    old_files={p.name:p for p in (source/"src").glob("*.py")}
    new_files={p.name:p for p in (code_input/"src").glob("*.py")}
    if old_files.keys()!=new_files.keys():raise ValueError("TSQR import source set changed")
    for name,path in old_files.items():
        if name=="modeling.py":
            if digest(new_files[name])!=TSQR_MODELING_SHA256:raise ValueError("Unaudited TSQR modeling module")
        elif name!="kaggle_runtime.py" and path.read_bytes()!=new_files[name].read_bytes():
            raise ValueError("TSQR import changed an upstream module: "+name)
    def definitions(path):
        return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text(encoding="utf-8")).body
                if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    old,new=definitions(old_files["kaggle_runtime.py"]),definitions(new_files["kaggle_runtime.py"])
    if any(new.get(name)!=value for name,value in old.items()
           if name not in {"cpu_resume_policy","restore_handoff","resource_plan","gpu_smoke"}):
        raise ValueError("TSQR import changed an upstream runtime operation")
    cfg=load_config(source)
    if cfg["rq3"].get("solver","dense")!="dense":raise ValueError("Producer solver is not the audited dense version")
    for entry in manifest["entries"]:
        name=entry["path"]
        if ".lock" in name or name.startswith(f"outputs/{scope}/predictions/"):
            raise ValueError("No writer locks or S08 predictions allowed in S07 prefix")
        if name.startswith(f"outputs/{scope}/models/") and not re.fullmatch(
                f"outputs/{scope}/models/kmeans_(Solo|Duo|Squad)\\.joblib",name):
            raise ValueError("Unexpected trained model in S07 prefix")
    if not Path(source_directory).is_dir():raise ValueError("Mount the original raw source for verified resume")
    if target.is_relative_to(source) or target.exists() and any(target.iterdir()):
        raise ValueError("Restore requires a new/empty working project; never overwrite old results")
    if list((source/f"outputs/{scope}/checkpoints").glob("*.lock")):raise RuntimeError("Producer has a writer lock")
    target.parent.mkdir(parents=True,exist_ok=True)
    total=sum(e["bytes"] for e in manifest["entries"])+4*2**20
    if total>cfg["storage"]["output_budget_gb"]*2**30 or total>shutil.disk_usage(target.parent).free:
        raise MemoryError("Not enough disk/output budget for unchanged S01-S07 and provenance")
    script='''import json,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,sys.argv[1])
from src.io import Context
root=Path(sys.argv[1]);raw=Path(sys.argv[3]).resolve()
ctx=Context(root,sys.argv[2],progress=lambda _:None)
ctx.cfg['source']['directory']=str(raw)
validated=set();hashes={}
for stage in ('S01','S02','S03','S04','S05','S06','S07'):ctx.require(stage,validated,hashes)
print(json.dumps({'verified_stages':sorted(validated),'software':ctx.software,
 'source_files':{p.relative_to(raw).as_posix():v for p,v in hashes.items() if p.is_relative_to(raw)}}))
'''
    print("S08 import: checking original S01-S07 signatures, raw and KMeans hashes; no recomputation",flush=True)
    checked=subprocess.run([sys.executable,"-B","-c",script,str(source),scope,str(source_directory)],cwd=source,
        env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1","PYTHONUTF8":"1","PYTHONIOENCODING":"utf-8"},
        capture_output=True,text=True,encoding="utf-8",timeout=1800)
    if checked.returncode:raise RuntimeError("Original S01-S07 verification failed: "+checked.stderr[-4000:])
    proof=json.loads(checked.stdout.strip().splitlines()[-1])
    if proof["verified_stages"]!=list(stages) or proof["software"]!=manifest["software"]:
        raise RuntimeError("Incomplete S01-S07 producer verification")
    with tempfile.TemporaryDirectory(prefix="pubg-s07-tsqr-resume-",dir=target.parent) as folder:
        staged=Path(folder)/"project";staged.mkdir()
        for entry in manifest["entries"]:
            if entry["bytes"]>256*2**20:print("S08 import: copying unchanged",entry["path"],flush=True)
            publish(safe_file(source,entry["path"]),staged/entry["path"])
        for path in code_files(code_input):
            if path.relative_to(code_input).as_posix()!="configs/project.yaml":publish(path,staged/path.relative_to(code_input))
        cfg["source"]["directory"]=str(Path(source_directory).resolve())
        cfg["storage"]["project_root"]=str(target)
        cfg["rq3"]["solver"]="tsqr"
        (staged/"configs/project.yaml").write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding="utf-8")
        provenance=staged/f"outputs/{scope}/provenance";provenance.mkdir(parents=True,exist_ok=True)
        archive=code_archive(source,provenance/"s07_producer_511.zip")
        receipt=provenance/"s07_tsqr_resume.json"
        write_json({"policy":"audited_511_s07_to_tsqr_v1","producer_handoff":manifest,"verification":proof,
            "source_code_sha256":S07_PRODUCER_511,"target_code_sha256":source_fingerprint(code_input),
            "version_reference":version_reference,"reference_source":evidence["reference_source"],
            "config_changes":{"rq3.solver":["dense","tsqr"]},"recomputed_stages":[],
            "producer_archive_sha256":digest(archive)},receipt)
        ctx=Context(staged,scope,progress=lambda _:None)
        if ctx.software!=manifest["software"]:raise RuntimeError("Software changed during S07 import")
        extra=[artifact_info(staged,p) for p in (archive,receipt)]
        write_json({},ctx.manifest_path);validated=set();hashes={}
        for stage in stages:
            original=manifest["stages"][stage]
            record={**original,"artifacts":[*original["artifacts"],*extra],
                "execution_import":{"policy":"audited_511_s07_to_tsqr_v1","signature":original["signature"],
                    "source_code_sha256":S07_PRODUCER_511,"software":manifest["software"],
                    "version_reference":version_reference,"recomputed":False}}
            record["signature"]=ctx.signature(stage,validated,hashes)
            records=ctx.manifest();records[stage]=record;write_json(records,ctx.manifest_path)
            ctx.require(stage,validated,hashes)
        raw=Path(source_directory).resolve()
        current_raw={p.relative_to(raw).as_posix():v for p,v in hashes.items() if p.is_relative_to(raw)}
        if not current_raw or current_raw!=proof["source_files"]:raise RuntimeError("Raw source changed during S07 import")
        write_json({**evidence,"compatibility_import":"audited_511_s07_to_tsqr_v1","recomputed_stages":[]},staged/("handoff_readback_"+scope+".json"))
        check_output_budget(staged,cfg["storage"]["output_budget_gb"])
        if target.exists():
            if any(target.iterdir()):raise ValueError("Restore destination changed")
            target.rmdir()
        staged.rename(target)
    return target


def restore_handoff(input_root,target,scope,source_directory,version_reference,*,code_input=None,allow_cpu_gpu=False,allow_s07_tsqr=False):
    source,target=Path(input_root).resolve(),Path(target).resolve()
    print("Resume: verifying saved files, checksums and Parquet; not recomputing stages", flush=True)
    manifest,evidence=verify_handoff(source,scope,version_reference)
    if allow_s07_tsqr:
        if allow_cpu_gpu or not code_input:raise ValueError("S07 TSQR import needs CODE_INPUT and CPU import disabled")
        return restore_s07_tsqr_handoff(source,target,scope,source_directory,version_reference,code_input,manifest,evidence)
    if allow_cpu_gpu:
        if not code_input:raise ValueError("CPU resume requires the matching updated CODE_INPUT")
        return restore_cpu_handoff(source,target,scope,source_directory,version_reference,code_input,manifest,evidence)
    if manifest["software"]!=software_versions():raise RuntimeError("Package/Python version mismatch; không reload model ngầm")
    if not Path(source_directory).is_dir():raise ValueError("Cần mount nguồn hiện tại khi resume")
    if target.is_relative_to(source) or (target.exists() and any(target.iterdir())):
        raise ValueError("Restore chỉ vào working project trống/mới; không ghi đè kết quả hiện có")
    total=sum(a["bytes"] for a in manifest["entries"])
    cfg=yaml.safe_load(safe_file(source,"configs/project.yaml").read_text(encoding="utf-8"))
    if total>cfg["storage"]["output_budget_gb"]*2**30:raise MemoryError("Gói resume vượt output budget")
    target.parent.mkdir(parents=True,exist_ok=True)
    if total>shutil.disk_usage(target.parent).free:raise MemoryError("Không đủ disk để restore")
    # Staging is our own temporary directory; failures never replace the destination project.
    with tempfile.TemporaryDirectory(prefix="pubg-restore-",dir=target.parent) as folder:
        staged=Path(folder)/"project";staged.mkdir()
        for entry in manifest["entries"]:
            if ".lock" in entry["path"]:raise ValueError("Không restore writer lock")
            publish(safe_file(source,entry["path"]),staged/entry["path"])
        cfg["source"]["directory"]=str(Path(source_directory).resolve())
        config=staged/"configs/project.yaml"
        config.write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding="utf-8")
        ctx=Context(staged,scope)
        validated,hashes=set(),{}
        for stage,record in ctx.manifest().items():
            if record.get("status")=="completed":ctx.require(stage,validated,hashes)
        write_json(evidence,staged/("handoff_readback_"+scope+".json"))
        # No file overwrite: the earlier empty-target check prevents replacing user results.
        if target.exists():
            if any(target.iterdir()):raise ValueError("Restore destination changed")
            target.rmdir()
        staged.rename(target)
    return target
