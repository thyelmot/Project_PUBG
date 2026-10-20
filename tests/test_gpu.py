"""CPU simulations validate isolation/control flow, never actual CUDA performance."""
import copy
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd

from src.gpu import device_tokens, run_jobs
from src.io import Context, PendingDecision, digest, load_config, read_json
from src.analysis import clustering, diagnostic_fit, cluster_fit, eda, relationship
from src.modeling import prediction, fit_candidate, predict_candidate
from src.kaggle_runtime import preflight
from test_data_features import fixture, run_features, write_config


FAKE_CUPY='''__version__="CPU-TEST-NOT-CUDA"
class Runtime:
    def getDeviceCount(self):return 1
    def getDevice(self):return 0
    def memGetInfo(self):return (16*2**30,16*2**30)
    def getDeviceProperties(self,index):return {"name":"CPU-TEST-NOT-CUDA"}
class Device:
    def __init__(self,index):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass
class CUDA:
    runtime=Runtime()
    Device=Device
cuda=CUDA()
'''
FAKE_CLUSTER='''import os,time
from pathlib import Path
from sklearn.cluster import KMeans as CPUKMeans
class KMeans(CPUKMeans):
    def __init__(self,n_clusters,n_init,random_state,output_type=None):
        self.output_type=output_type
        super().__init__(n_clusters=n_clusters,n_init=n_init,random_state=random_state)
    def fit(self,X,y=None):
        token=os.environ["CUDA_VISIBLE_DEVICES"]
        if os.environ.get("PUBG_TEST_FAIL_GPU")==token:raise MemoryError("CPU-simulated worker out of memory")
        barrier=os.environ.get("PUBG_TEST_BARRIER")
        if barrier:
            root=Path(barrier);(root/(token+".ready")).touch()
            deadline=time.monotonic()+15
            while len(list(root.glob("*.ready")))<2:
                if time.monotonic()>deadline:raise RuntimeError("CPU test workers did not overlap")
                time.sleep(.02)
        return super().fit(X,y)
'''
FAKE_LINEAR='''from sklearn.linear_model import LinearRegression as CPUOLS
class LinearRegression(CPUOLS):
    def __init__(self,fit_intercept=True,algorithm="svd",output_type=None):
        self.algorithm=algorithm;self.output_type=output_type
        super().__init__(fit_intercept=fit_intercept)
'''


def fake_packages(root):
    (root/"cupy").mkdir();(root/"cuml").mkdir()
    for name,source in {"cupy/__init__.py":FAKE_CUPY,"cuml/__init__.py":'__version__="CPU-TEST-NOT-CUDA"',
                        "cuml/cluster.py":FAKE_CLUSTER,"cuml/linear_model.py":FAKE_LINEAR}.items():
        (root/name).write_text(source,encoding="utf-8")


class DualGPU(unittest.TestCase):
    def test_visibility_mapping_and_invalid_config(self):
        with patch.dict(os.environ,{"CUDA_VISIBLE_DEVICES":"GPU-A,GPU-B"}):
            self.assertEqual(device_tokens([0,1],2),{0:"GPU-A",1:"GPU-B"})
            self.assertEqual(device_tokens([1],2),{1:"GPU-B"})
            for ids in ([0,0],[True,1],[0,2],[],[0,1,2]):
                with self.assertRaises(ValueError):device_tokens(ids,2)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cfg=fixture(root)
            for ids in ([0,0],[True,1],[[0],1],[]):
                cfg["rq2"]["gpu_ids"]=ids;write_config(root,cfg)
                with self.assertRaises(ValueError):load_config(root)

    def test_preflight_rejects_missing_second_gpu(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            ctx.cfg["rq2"].update(device="cuda",gpu_ids=[0,1])
            with patch("src.kaggle_runtime.compute_metadata",side_effect=lambda device:{"device":device,"gpu_count":1}):
                with self.assertRaises(ValueError):preflight(ctx,"S07","S07")

    def test_real_process_isolation_overlap_and_resource_failure_simulated_on_cpu(self):
        with tempfile.TemporaryDirectory(prefix="pubg-dual-process-test-") as folder:
            root=Path(folder);fake=root/"fake";fake.mkdir();fake_packages(fake)
            barrier=root/"barrier";barrier.mkdir()
            events=[]
            ctx=SimpleNamespace(temp=root,cfg={"rq2":{"gpu_ids":[0,1]},"runtime":{"max_matrix_gb":2}},
                                progress=lambda step,**kw:events.append((step,kw)))
            jobs=[{"key":"smoke"+str(i),"kind":"smoke","matrix_bytes":48*3*8,"payload":{}} for i in range(2)]
            env={"PYTHONPATH":str(fake),"CUDA_VISIBLE_DEVICES":"0,1","PUBG_TEST_BARRIER":str(barrier)}
            inventory={"gpu_count":2,"host_available_bytes":32*2**30}
            with patch.dict(os.environ,env),patch("src.io.compute_metadata",return_value=inventory):
                results=[joblib.load(path) for _,path in run_jobs(ctx,"rq2",jobs)]
            a,b=[r["gpu_execution"] for r in results]
            self.assertEqual({a["gpu_id"],b["gpu_id"]},{0,1})
            self.assertNotEqual(a["pid"],b["pid"])
            self.assertLess(max(a["started"],b["started"]),min(a["finished"],b["finished"]))
            self.assertTrue(all(r["status"]=="passed" for r in results))
            self.assertTrue(all(r["gpu_execution"]["compute"]["cuml_version"]=="CPU-TEST-NOT-CUDA" for r in results))
            self.assertEqual(len([e for e in events if e[0]=="GPU worker completed"]),2)
            self.assertFalse(list(root.glob("gpu-jobs-*")))
            oversized=copy.deepcopy(jobs);oversized[0]["matrix_bytes"]=2**30
            with patch.dict(os.environ,env),patch("src.io.compute_metadata",return_value=inventory),patch("src.gpu.subprocess.Popen") as spawn:
                with self.assertRaises(MemoryError):list(run_jobs(ctx,"rq2",oversized))
                spawn.assert_not_called()
            env["PUBG_TEST_FAIL_GPU"]="0";env["PUBG_TEST_BARRIER"]=""
            with patch.dict(os.environ,env),patch("src.io.compute_metadata",return_value=inventory):
                with self.assertRaises(MemoryError):list(run_jobs(ctx,"rq2",jobs))
            self.assertFalse(list(root.glob("gpu-jobs-*")))

    def test_dual_stage_routing_g4_cache_and_predictions_simulated_on_cpu(self):
        with tempfile.TemporaryDirectory(prefix="pubg-dual-stage-test-") as folder:
            root=Path(folder);cfg=fixture(root);ctx=run_features(root)
            ctx.run("S05",eda);ctx.run("S06",relationship)
            cfg["rq2"].update(device="cuda",gpu_ids=[0,1],decision_mode="auto")
            cfg["rq3"].update(device="cuda",gpu_ids=[0,1])
            write_config(root,cfg);ctx=Context(root,"development")
            calls=[]
            def simulated(ctx,section,jobs):
                for i,job in enumerate(jobs):
                    calls.append(job["kind"])
                    payload={**job["payload"],"device":"cpu"}
                    function={"k_diagnostic":diagnostic_fit,"k_full":cluster_fit,
                              "regression_fit":fit_candidate,"regression_predict":predict_candidate}[job["kind"]]
                    result=function(payload)
                    result["gpu_execution"]={"gpu_id":job.get("gpu_id",i%2),"simulation":"CPU, not CUDA"}
                    path=root/("result"+str(len(calls))+".joblib");joblib.dump(result,path)
                    yield job,path
            with patch("src.analysis.run_jobs",side_effect=simulated),patch("src.modeling.run_jobs",side_effect=simulated):
                ctx.run("S07",clustering)
                clustered=read_json(ctx.path("manifests/clustering.json"))
                self.assertEqual({e["gpu_id"] for e in clustered["gpu_executions"]},{0,1})
                with self.assertRaises(PendingDecision):ctx.run("S08",prediction)
                self.assertNotIn("regression_predict",calls)
                self.assertFalse(list(ctx.path("predictions").glob("test_*.parquet")))
                receipt=read_json(ctx.path("manifests/validation_receipt.json"))
                linear=[r for r in receipt["models"] if r["experiment"].endswith("linear")]
                self.assertEqual({r["gpu_execution"]["gpu_id"] for r in linear},{0,1})
                hashes={p.name:digest(p) for p in ctx.path("models").glob("*.joblib")}
                fit_count=calls.count("regression_fit")
                cfg["rq3"].update(selection_approved=True,selection_reason="CPU simulation only",validation_hash=receipt["validation_hash"])
                write_config(root,cfg);ctx=Context(root,"development")
                ctx.run("S08",prediction)
                self.assertEqual(fit_count,calls.count("regression_fit"))
                self.assertEqual(calls.count("regression_predict"),3)
                self.assertEqual(hashes,{p.name:digest(p) for p in ctx.path("models").glob("*.joblib")})
                a=pd.read_parquet(ctx.path("predictions/test_p2_linear.parquet"))
                b=pd.read_parquet(ctx.path("predictions/test_t0_linear.parquet"))
                self.assertTrue(a.row_id.equals(b.row_id))
                self.assertTrue(np.isfinite(a.predicted).all())
                self.assertTrue(read_json(ctx.path("manifests/gpu_rq3_test.json"))["after_selection_approval"])
                paired={p.name:pd.read_parquet(p) for p in ctx.path("predictions").glob("test_*.parquet")}
                cfg["rq3"].update(device="cpu",decision_mode="auto")
                write_config(root,cfg);ctx=Context(root,"development");ctx.run("S08",prediction)
                self.assertEqual(len(paired),7)
                for name,previous in paired.items():
                    current=pd.read_parquet(ctx.path("predictions/"+name))
                    pd.testing.assert_frame_equal(previous.drop(columns="run_id"),current.drop(columns="run_id"))


if __name__=="__main__":unittest.main()
