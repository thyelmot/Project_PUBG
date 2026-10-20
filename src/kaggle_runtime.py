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
    from .modeling import fit_memory_bytes, prediction_memory_bytes
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
                    estimate=fit_memory_bytes(n,len(columns)) if split=="train" else prediction_memory_bytes(n,chars[split])
                    checks.append({"step":f"S08 {task}/{split}","rows":n,"estimated_bytes":estimate})
                rows=counts.get("train",0)+counts.get("validation",0)
                host_bytes=fit_memory_bytes(counts.get("train",0),len(columns))+prediction_memory_bytes(counts.get("validation",0),chars.get("validation",0))
                jobs.append({"step":f"S08 {task} worker","rows":rows,"estimated_bytes":host_bytes})
                if gpu_inventory:
                    required=counts.get("train",0)*2*len(columns)*8*4
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
    from .modeling import estimator
    compute=compute_metadata("cuda")
    x=np.random.default_rng(42).normal(size=(48,3));y=x@np.array([2.,-1.,.5])+3
    with tempfile.TemporaryDirectory(prefix="pubg-gpu-smoke-") as folder:
        for name,model in (("kmeans",kmeans("cuda",2,42).fit(x)),("ols",estimator("cuda").fit(x,y))):
            path=Path(folder)/(name+".joblib");joblib.dump(model,path)
            a=np.asarray(model.predict(x));b=np.asarray(joblib.load(path).predict(x))
            if not np.allclose(a,b,rtol=1e-6,atol=1e-6):raise ValueError("GPU smoke reload mismatch")
            if name=="ols" and np.max(np.abs(a.reshape(-1)-y))>1e-4:raise ValueError("GPU OLS smoke formula mismatch")
    return {"scope":"synthetic 48 rows, not PUBG results","status":"passed",**compute}


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


def restore_handoff(input_root,target,scope,source_directory,version_reference):
    source,target=Path(input_root).resolve(),Path(target).resolve()
    manifest,evidence=verify_handoff(source,scope,version_reference)
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
