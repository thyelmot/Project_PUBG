"""Independent fits on isolated GPUs; the parent alone publishes stage artifacts."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def device_tokens(ids, count):
    if (not isinstance(ids,list) or len(ids) not in (1,2)
            or any(type(i) is not int or i<0 or i>=count for i in ids) or len(set(ids))!=len(ids)):
        raise ValueError("gpu_ids cần một hoặc hai GPU khác nhau đang hiển thị; không fallback")
    mask=os.environ.get("CUDA_VISIBLE_DEVICES")
    visible=mask.split(",") if mask is not None else [str(i) for i in range(count)]
    if len(visible)<count or any(not x.strip() for x in visible):
        raise ValueError("CUDA_VISIBLE_DEVICES không khớp GPU inventory")
    return {i:visible[i].strip() for i in ids}


def run_jobs(ctx, section, jobs):
    """Yield private result paths in input order, at most one process per GPU."""
    import joblib
    from .io import compute_metadata, require_memory
    inventory=compute_metadata("cuda")
    ids=ctx.cfg[section].get("gpu_ids",[0])
    tokens=device_tokens(ids,inventory["gpu_count"])
    root=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="gpu-jobs-",dir=ctx.temp) as folder:
        folder=Path(folder)
        for offset in range(0,len(jobs),len(ids)):
            batch=jobs[offset:offset+len(ids)]
            devices=[job.get("gpu_id",ids[(offset+i)%len(ids)]) for i,job in enumerate(batch)]
            if len(set(devices))!=len(devices) or any(i not in tokens for i in devices):
                raise ValueError("Batch có GPU trùng hoặc ngoài gpu_ids")
            required=sum(job.get("host_bytes",job["matrix_bytes"]*8) for job in batch)
            require_memory(ctx.cfg,required,"Concurrent GPU workers")
            running=[]
            try:
                for i,(job,gpu_id) in enumerate(zip(batch,devices)):
                    request=folder/f"{offset+i}.joblib";output=folder/f"{offset+i}.result"
                    payload={**job["payload"],"device":"cuda"}
                    joblib.dump({"kind":job["kind"],"payload":payload,"output":str(output)},request)
                    env=dict(os.environ,CUDA_VISIBLE_DEVICES=tokens[gpu_id],PYTHONDONTWRITEBYTECODE="1",
                             OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1")
                    env["PYTHONPATH"]=str(root)+os.pathsep+env.get("PYTHONPATH","")
                    log=folder/f"{offset+i}.log"
                    with log.open("wb") as stream:
                        process=subprocess.Popen([sys.executable,"-B","-m","src.gpu",str(request)],
                                                 cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT)
                    running.append((process,job,gpu_id,output,log))
                    ctx.progress("GPU worker started",job=job["key"],gpu_id=gpu_id,pid=process.pid)
                heartbeat=time.monotonic()
                while any(p.poll() is None for p,*_ in running):
                    if any(p.poll() not in (None,0) for p,*_ in running):break
                    if time.monotonic()-heartbeat>=15:
                        ctx.progress("GPU workers running",jobs=[j["key"] for p,j,*_ in running if p.poll() is None])
                        heartbeat=time.monotonic()
                    time.sleep(.1)
                for process,job,gpu_id,output,log in running:
                    if process.poll() not in (None,0):
                        detail=log.read_text(encoding="utf-8",errors="replace")[-4000:]
                        if "MemoryError" in detail or "out of memory" in detail.lower() or "OutOfMemory" in detail:
                            raise MemoryError(f"GPU {gpu_id}/{job['key']}: {detail}")
                        raise RuntimeError(f"GPU {gpu_id}/{job['key']} failed; không fallback: {detail}")
                for process,job,gpu_id,output,log in running:
                    process.wait()
                    if process.returncode or not output.is_file():
                        raise RuntimeError("GPU worker thiếu kết quả hợp lệ: "+job["key"])
                    result=joblib.load(output)
                    execution=result.get("gpu_execution",{})
                    if (execution.get("visible_device")!=tokens[gpu_id] or execution.get("pid")!=process.pid
                            or execution.get("gpu_count")!=1):
                        raise ValueError("GPU worker identity mismatch")
                    result["gpu_execution"]["gpu_id"]=gpu_id
                    joblib.dump(result,output)
                    del result
                    ctx.progress("GPU worker completed",job=job["key"],gpu_id=gpu_id,pid=process.pid)
                    yield job,output
            finally:
                for process,*_ in running:
                    if process.poll() is None:process.terminate()
                for process,*_ in running:
                    try:process.wait(timeout=10)
                    except subprocess.TimeoutExpired:process.kill();process.wait()


def worker(request):
    # CUDA visibility is fixed by Popen before importing any CUDA library.
    import joblib
    from .io import compute_metadata
    data=joblib.load(request)
    compute=compute_metadata("cuda")
    visible=os.environ.get("CUDA_VISIBLE_DEVICES","")
    if compute["gpu_count"]!=1 or not visible or "," in visible:
        raise RuntimeError("Worker phải chỉ nhìn thấy đúng một GPU")
    kind=data["kind"];payload=data["payload"]
    if payload.get("device")!="cuda":raise ValueError("GPU worker không nhận CPU fallback")
    started=time.time()
    if kind=="k_diagnostic":
        from .analysis import diagnostic_fit
        result=diagnostic_fit(payload)
    elif kind=="k_full":
        from .analysis import cluster_fit
        result=cluster_fit(payload)
    elif kind=="regression_fit":
        from .modeling import fit_candidate
        result=fit_candidate(payload)
    elif kind=="regression_predict":
        from .modeling import predict_candidate
        result=predict_candidate(payload)
    elif kind=="smoke":
        from .kaggle_runtime import gpu_smoke
        result=gpu_smoke()
    else:raise ValueError("Unknown GPU job")
    result["gpu_execution"]={"visible_device":visible,"pid":os.getpid(),"gpu_count":compute["gpu_count"],
                             "started":started,"finished":time.time(),"compute":compute}
    joblib.dump(result,data["output"])


if __name__=="__main__":
    worker(Path(sys.argv[1]))
