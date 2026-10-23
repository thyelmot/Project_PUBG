# Frozen 5.8 reference for parity tests only; excluded from production ZIP.
"""Baseline/OLS thật, train-only preprocessing, G4 và paired comparisons."""
import platform
import tempfile
import uuid
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.dummy import DummyRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.preprocessing import FunctionTransformer

from src.features import FEATURES, TARGETS, allowlist
from src.io import PendingDecision, digest, fingerprint, ident, publish, quote, compute_metadata, read_json, artifact_info, time_unit_info, frame_fingerprint, require_memory
from src.reporting import figure
from src.gpu import run_jobs


def metrics(y,pred,weights=None):
    y,pred=np.asarray(y,float),np.asarray(pred,float)
    if y.shape!=pred.shape or not len(y) or not np.isfinite(y).all() or not np.isfinite(pred).all():
        raise ValueError("Metrics require equal, finite, nonempty arrays")
    w=np.ones(len(y)) if weights is None else np.asarray(weights,float)
    if w.shape!=y.shape or not np.isfinite(w).all() or (w<=0).any():
        raise ValueError("Invalid weights")
    mean=np.average(y,weights=w)
    error=y-pred
    sse=float(np.sum(w*error**2));sst=float(np.sum(w*(y-mean)**2))
    return {"n":len(y),"mae":float(np.average(abs(error),weights=w)),
            "rmse":float(np.sqrt(np.average(error**2,weights=w))),
            "r2":float(1-sse/sst) if len(y)>1 and sst>0 else np.nan,
            "r2_reason":"" if len(y)>1 and sst>0 else "constant target or insufficient n"}


def hierarchical(frame,target):
    rows=[]
    rows.append({"aggregation":"micro",**metrics(frame.actual,frame.predicted)})
    weights=1/frame.groupby("match_id").actual.transform("size")
    rows.append({"aggregation":"match_aware",**metrics(frame.actual,frame.predicted,weights)})
    if target=="normalized_placement":
        if frame.team_id.isna().any() or frame.groupby(["match_id","team_id"]).actual.nunique().gt(1).any():
            raise ValueError("Team placement target conflict")
        teams=frame.groupby(["match_id","team_id"],as_index=False).agg(actual=("actual","first"),predicted=("predicted","mean"))
        rows.append({"aggregation":"team_aware",**metrics(teams.actual,teams.predicted)})
    return rows


def estimator(device):
    if device=="cpu":
        return LinearRegression()
    try:
        from cuml.linear_model import LinearRegression as GPULinear
        import cupy
        if cupy.cuda.runtime.getDeviceCount()<1:
            raise RuntimeError("No CUDA device")
        return GPULinear(fit_intercept=True,algorithm="svd",output_type="numpy")
    except Exception as error:
        raise RuntimeError("GPU Linear Regression không sẵn sàng; không fallback CPU") from error


def log_features(frame, columns):
    result=frame.copy()
    for c in columns:
        if result[c].dropna().lt(0).any():
            raise ValueError(f"log1p không hợp lệ với giá trị âm: {c}")
        result[c]=np.log1p(result[c])
    return result


def matrix_data(ctx,con,task,split):
    columns=FEATURES[task]
    allowlist(task,columns)
    condition="valid_survival" if task=="s1" else "valid_placement"
    where=f"split={quote(split)} AND {condition}"
    n=con.execute(f"SELECT count(*) FROM p WHERE {where}").fetchone()[0]
    if not n:
        raise ValueError(f"Empty eligible cohort: {task}/{split}")
    require_memory(ctx.cfg,n*(len(columns)+8)*8*5,f"{task}/{split}")
    fields=["row_id","match_id","player_name","team_id","team_size_mode","split",TARGETS[task]]+columns
    return con.execute(f"SELECT {','.join(ident(c) for c in fields)} FROM p WHERE {where} ORDER BY row_id").df()


def save_predictions(ctx,name,frame):
    target=ctx.path("predictions/"+name+".parquet")
    with tempfile.TemporaryDirectory(prefix="pubg-pred-") as folder:
        temp=Path(folder)/"pred.parquet"
        pq.write_table(pa.Table.from_pandas(frame,preserve_index=False),temp,compression="zstd")
        publish(temp,target)
    return ctx.record(target)


def prediction_frame(frame,task,model,experiment,run_id):
    result=frame[["row_id","match_id","team_id","team_size_mode","split"]].copy()
    result["actual"]=frame[TARGETS[task]].to_numpy()
    batches=[]
    for start in range(0,len(frame),50000):
        batches.append(np.asarray(model.predict(frame[FEATURES[task]].iloc[start:start+50000])).reshape(-1))
    result["predicted"]=np.concatenate(batches)
    result["residual"]=result.actual-result.predicted
    result["experiment"]=experiment;result["run_id"]=run_id;result["target"]=TARGETS[task]
    if not np.isfinite(result[["actual","predicted"]].to_numpy()).all():
        raise ValueError("Nonfinite prediction/target")
    return result


def validate_automatic_selection(records, models):
    """Approve the registered seven fits, never choose a winner using test labels."""
    expected={"s1_mean","s1_median","s1_linear","p2_mean","p2_median","p2_linear","t0_linear"}
    table=pd.DataFrame(records)
    if set(models)!=expected or table.empty or not table.split.eq("validation").all():
        raise ValueError("Auto G4: thiếu model hoặc có dữ liệu ngoài validation")
    primary=table[table.aggregation.eq("micro")]
    if set(primary.experiment)!=expected or primary.experiment.duplicated().any():
        raise ValueError("Auto G4: validation không đủ bảy thí nghiệm duy nhất")
    if not np.isfinite(table[["n","mae","rmse"]].to_numpy(float)).all() or table.n.le(0).any() or table[["mae","rmse"]].lt(0).any().any():
        raise ValueError("Auto G4: validation metric không hợp lệ")
    undefined=~np.isfinite(table.r2.to_numpy(float))
    if np.isinf(table.r2.to_numpy(float)).any() or table.loc[undefined,"r2_reason"].fillna("").str.strip().eq("").any():
        raise ValueError("Auto G4: R2 không xác định cần lý do, không nhận infinity")
    for row in primary.itertuples():
        if row.target!=TARGETS[row.experiment.split("_")[0]]:
            raise ValueError("Auto G4: target không khớp thí nghiệm")
    return "Auto policy approved 2026-10-17: all seven pre-registered train-only fits passed reload/finite-prediction, cohort and validation checks; no metric cutoff or test-driven model selection; no train+validation refit"


def fit_candidate(payload):
    data=joblib.load(payload["data"])
    train,validation=data["train"],data["validation"]
    task,kind=payload["task"],payload["kind"]
    compute=compute_metadata(payload["device"] if kind=="linear" else "cpu",len(train)*len(FEATURES[task])*16)
    final_estimator=estimator(payload["device"]) if kind=="linear" else DummyRegressor(strategy=kind)
    model=Pipeline([("log",FunctionTransformer(log_features,kw_args={"columns":payload["logs"]})),
                    ("imputer",SimpleImputer(strategy="mean",add_indicator=True,keep_empty_features=True)),
                    ("scaler",StandardScaler()),("model",final_estimator)])
    model.fit(train[FEATURES[task]],train[TARGETS[task]])
    joblib.dump(model,payload["model_path"])
    loaded=joblib.load(payload["model_path"])
    predicted=prediction_frame(validation,task,loaded,payload["experiment"],payload["run_id"])
    for start in range(0,len(validation),50000):
        reference=np.asarray(model.predict(validation[FEATURES[task]].iloc[start:start+50000])).reshape(-1)
        if not np.allclose(predicted.predicted.iloc[start:start+50000],reference,rtol=1e-7,atol=1e-7):
            raise ValueError("Model reload predictions mismatch")
    names=loaded.named_steps["imputer"].get_feature_names_out(FEATURES[task]) if kind=="linear" else []
    coef=np.asarray(loaded.named_steps["model"].coef_).reshape(-1) if kind=="linear" else []
    return {"predicted":predicted,"names":list(names),"coefficients":coef,
            "compute":compute,"backend":type(final_estimator).__module__}


def predict_candidate(payload):
    frame=joblib.load(payload["data"])
    compute_metadata(payload["device"],len(frame)*len(FEATURES[payload["task"]])*8)
    model=joblib.load(payload["model_path"])
    return {"predicted":prediction_frame(frame,payload["task"],model,payload["experiment"],payload["run_id"])}


def prediction(ctx):
    with tempfile.TemporaryDirectory(prefix="pubg-regression-",dir=ctx.temp) as folder:
        _prediction(ctx,Path(folder))


def _prediction(ctx,work):
    cfg=ctx.cfg["rq3"]
    parallel=cfg["device"]=="cuda"
    unit_info=time_unit_info(ctx.cfg)
    records,cohorts,models,model_meta,coefficients=[],[],{},[],[]
    with ctx.db() as con:
        ctx.view(con,"p","player_match")
        training_signature=fingerprint({"input":digest(ctx.data/"player_match.parquet"),
            "features":ctx.cfg["features"],"device":cfg["device"],"gpu_ids":cfg.get("gpu_ids",[0]),"bins":cfg["error_quantiles"],"time_unit":unit_info,
            "scope":ctx.scope,"seed":ctx.cfg["runtime"]["seed"],
            "software":ctx.software,
            "code":{p.name:digest(p) for p in sorted((ctx.root/"src").glob("*.py"))}})
        receipt_path=ctx.path("manifests/validation_receipt.json")
        cached=read_json(receipt_path) if receipt_path.exists() else {}
        reuse=(cached.get("training_signature")==training_signature
               and cached.get("training_artifacts")
               and all((ctx.root/a["path"]).is_file() and digest(ctx.root/a["path"])==a["sha256"]
                       for a in cached["training_artifacts"]))
        if reuse:
            for artifact in cached["training_artifacts"]:
                ctx.record(ctx.root/artifact["path"])
            ctx.record(receipt_path)
            model_meta=cached["models"]
            for item in model_meta:
                experiment=item["experiment"]
                task=experiment.split("_")[0]
                model=None if parallel and experiment.endswith("linear") else joblib.load(ctx.path("models/"+experiment+".joblib"))
                models[experiment]=(task,model,item["run_id"])
            records=pd.read_csv(ctx.path("tables/validation_metrics.csv")).to_dict("records")
            validation_hash=cached["validation_hash"]
            print("S08: reuse verified train/validation models (no refit)")
        else:
            jobs=[]
            if not set(ctx.cfg["features"]["log_columns"]).issubset(set(FEATURES["p2"])):
                raise ValueError("Log column ngoài predictor allowlist")
            def accept_fit(job,result):
                payload=job["payload"];task=payload["task"];kind=payload["kind"]
                experiment=payload["experiment"];run_id=payload["run_id"]
                target=ctx.path("models/"+experiment+".joblib")
                publish(Path(payload["model_path"]),target);ctx.record(target)
                predicted=result["predicted"]
                save_predictions(ctx,"validation_"+experiment,predicted)
                for row in hierarchical(predicted,TARGETS[task]):
                    records.append({"experiment":experiment,"target":TARGETS[task],"split":"validation","device":cfg["device"] if kind=="linear" else "cpu",
                                    "time_unit_status":unit_info["status"],"target_unit":unit_info["label"] if task=="s1" else "Placement [0,1]",**row})
                model=None if parallel and kind=="linear" else joblib.load(target)
                models[experiment]=(task,model,run_id)
                model_meta.append({"experiment":experiment,"run_id":run_id,"target":TARGETS[task],"features":FEATURES[task],
                                   "backend":result["backend"],"device":cfg["device"] if kind=="linear" else "cpu",
                                   "gpu_execution":result.get("gpu_execution"),
                                   "model_sha256":digest(target),"fit_scope":"train_only","status":"completed","compute":result["compute"],"time_unit":unit_info})
                coefficients.extend({"experiment":experiment,"feature":str(c),"coefficient":float(v),"scale":"StandardScaler train-only",
                                     "time_unit_status":unit_info["status"],
                                     "coefficient_unit":unit_info["label"]+"/độ lệch chuẩn" if task=="s1" else "Placement/độ lệch chuẩn"}
                                    for c,v in zip(result["names"],result["coefficients"]))
                ctx.json("bins_"+task,{"edges":payload["bins"],"source":"train_target_quantiles"})
            for task in ("s1","p2","t0"):
                train=matrix_data(ctx,con,task,"train")
                validation=matrix_data(ctx,con,task,"validation")
                for split,data in (("train",train),("validation",validation)):
                    cohorts.append({"task":task,"split":split,"rows":len(data),"matches":data.match_id.nunique(),"players":data.player_name.nunique(),
                                    "cohort_hash":frame_fingerprint(data[["row_id",TARGETS[task]]])})
                del data
                if task=="t0":
                    for split,frame in (("train",train),("validation",validation)):
                        reference=con.execute(f"SELECT row_id FROM p WHERE split={quote(split)} AND valid_placement ORDER BY row_id").df()
                        if not frame.row_id.equals(reference.row_id):raise ValueError("T0/T1 cohort mismatch before fit")
                        del reference
                    del frame
                for kind in (("mean","median","linear") if task!="t0" else ("linear",)):
                    experiment=f"{task}_{kind}"
                    ctx.progress("train/validation fit",experiment=experiment,train_rows=len(train),validation_rows=len(validation),test_accessed=False)
                    run_id=uuid.uuid4().hex
                    data=work/(task+".data.joblib")
                    if not data.exists():joblib.dump({"train":train,"validation":validation},data)
                    payload={"data":str(data),"model_path":str(work/(experiment+".joblib")),
                             "task":task,"kind":kind,"device":cfg["device"],"experiment":experiment,"run_id":run_id,
                             "logs":[c for c in ctx.cfg["features"]["log_columns"] if c in FEATURES[task]],
                             "bins":np.unique(np.quantile(train[TARGETS[task]],cfg["error_quantiles"])).tolist()}
                    job={"kind":"regression_fit","key":experiment,"payload":payload,
                         "matrix_bytes":int(train.memory_usage(deep=True).sum()+validation.memory_usage(deep=True).sum()),
                         "host_bytes":int(2*(train.memory_usage(deep=True).sum()+validation.memory_usage(deep=True).sum())
                                          +len(train)*(2*len(FEATURES[task])+1)*8*5)}
                    if parallel and kind=="linear":jobs.append(job)
                    else:accept_fit(job,fit_candidate(payload))
                del train,validation
            if parallel:
                for job,path in run_jobs(ctx,"rq3",jobs):accept_fit(job,joblib.load(path))
            validation_table=pd.DataFrame(records)
            val_path=ctx.table("validation_metrics",validation_table)
            cohort_path=ctx.table("model_cohorts",pd.DataFrame(cohorts))
            validation_hash=fingerprint({"metrics":digest(val_path),"cohorts":digest(cohort_path),
                "input":digest(ctx.data/"player_match.parquet"),"features":FEATURES,
                "model_hashes":{r["experiment"]:r["model_sha256"] for r in model_meta}})
            coefficient_table=pd.DataFrame(coefficients)
            ctx.table("coefficients",coefficient_table)
            for experiment in coefficient_table.experiment.unique():
                part=coefficient_table[coefficient_table.experiment.eq(experiment)]
                figure(ctx,"coefficients_"+experiment,part,"feature",["coefficient"],
                       "Hệ số hồi quy có dấu - "+experiment,
                       "Train-only StandardScaler: hệ số ứng với tăng một độ lệch chuẩn đầu vào đã xử lý; "
                       "dấu không chứng minh nhân quả, tương quan giữa predictors có thể làm hệ số kém ổn định. "
                       "Missing-indicator và log feature giữ tên trong bảng nguồn; không so độ lớn giữa hai target.",
                       unit=unit_info["label"]+"/độ lệch chuẩn" if experiment.startswith("s1") else "Placement/độ lệch chuẩn",
                       analysis_scope="train-only")
            for target_name in validation_table.target.unique():
                figure(ctx,"validation_mae_"+target_name,validation_table[validation_table.aggregation.eq("micro") & validation_table.target.eq(target_name)],"experiment",["mae"],
                       "Sai số validation - "+target_name,"Chỉ so cùng target/cohort; không trộn đơn vị survival/placement.",
                       unit=unit_info["label"] if target_name=="player_survive_time" else "Placement [0,1]",analysis_scope="validation")
            ctx.json("validation_receipt",{"validation_hash":validation_hash,"training_signature":training_signature,
                "training_artifacts":[artifact_info(ctx.root,p) for p in ctx.created],
                "models":model_meta,"test_accessed":False,"prior_test_exposure":cfg["prior_test_exposure"],
                "instructions":"Approve pinned models/cohorts from validation before test"})
        automatic=cfg.get("decision_mode","manual")=="auto"
        if automatic:
            selection_reason=validate_automatic_selection(records,models)
        elif not cfg["selection_approved"] or not cfg.get("selection_reason") or cfg.get("validation_hash")!=validation_hash:
            raise PendingDecision("S08: xem validation_metrics và validation_receipt; G4 cần approval/reason/hash trước test")
        else:
            selection_reason=cfg["selection_reason"]
        ctx.json("selection",{"validation_hash":validation_hash,"reason":selection_reason,"fit_scope":"train_only",
                              "decision_mode":cfg.get("decision_mode","manual"),"test_accessed_at_approval":False,"time_unit":unit_info,
                              "prior_test_exposure":cfg["prior_test_exposure"],"approved":True})
        test_jobs=[]
        execution_by_model={m["experiment"]:m.get("gpu_execution") for m in model_meta}
        def accept_test(experiment,task,predicted):
            save_predictions(ctx,"test_"+experiment,predicted)
            for row in hierarchical(predicted,TARGETS[task]):
                records.append({"experiment":experiment,"target":TARGETS[task],"split":"test","device":cfg["device"] if experiment.endswith("linear") else "cpu",
                                "time_unit_status":unit_info["status"],"target_unit":unit_info["label"] if task=="s1" else "Placement [0,1]",**row})
        for experiment,(task,model,run_id) in models.items():
            test=matrix_data(ctx,con,task,"test")
            if parallel and experiment.endswith("linear"):
                data=work/(experiment+".test.joblib");joblib.dump(test,data)
                execution=execution_by_model[experiment]
                if not execution:raise ValueError("Dual-GPU cached model thiếu GPU identity; không đoán thiết bị")
                test_jobs.append({"kind":"regression_predict","key":experiment,"gpu_id":execution["gpu_id"],
                                  "matrix_bytes":int(test.memory_usage(deep=True).sum()),
                                  "payload":{"data":str(data),"model_path":str(ctx.path("models/"+experiment+".joblib")),
                                             "task":task,"experiment":experiment,"run_id":run_id,"device":"cuda"}})
            else:accept_test(experiment,task,prediction_frame(test,task,model,experiment,run_id))
            del test
        test_executions=[]
        if parallel:
            for job,path in run_jobs(ctx,"rq3",test_jobs):
                result=joblib.load(path);experiment=job["key"]
                accept_test(experiment,job["payload"]["task"],result["predicted"])
                test_executions.append({"experiment":experiment,**result["gpu_execution"]})
            ctx.json("gpu_rq3_test",{"executions":test_executions,"after_selection_approval":True})
        ctx.table("model_metrics",pd.DataFrame(records))
        ctx.json("models",{"core":model_meta,"gpu_ids":cfg.get("gpu_ids",[0]),"T1_alias":"p2_linear","scope":ctx.scope,"optional_RF":"not_requested"})


def pair_predictions(a,b):
    if len(a)!=len(b) or a.row_id.duplicated().any() or b.row_id.duplicated().any():
        raise ValueError("Missing/extra/duplicate row IDs in paired comparison")
    left=a.sort_values("row_id").reset_index(drop=True)
    right=b.sort_values("row_id").reset_index(drop=True)
    if not left.row_id.equals(right.row_id):
        raise ValueError("Missing/extra/duplicate row IDs in paired comparison")
    for c in ("match_id","team_id","split","target","actual"):
        if not left[c].equals(right[c]):
            raise ValueError(f"Paired identity/target mismatch: {c}")
    return left,right


def paired_bootstrap(a,b,replicates,seed):
    a,b=pair_predictions(a,b)
    match=a.match_id.to_numpy()
    ids,codes=np.unique(match,return_inverse=True)
    centered=a.actual.to_numpy(float)-a.actual.mean()
    n=np.bincount(codes);ya=np.bincount(codes,weights=centered);y2=np.bincount(codes,weights=centered**2)
    abs_a=np.bincount(codes,weights=abs(a.actual-a.predicted));abs_b=np.bincount(codes,weights=abs(b.actual-b.predicted))
    sq_a=np.bincount(codes,weights=(a.actual-a.predicted)**2);sq_b=np.bincount(codes,weights=(b.actual-b.predicted)**2)
    rng=np.random.default_rng(seed);deltas=[]
    for _ in range(replicates):
        counts=np.bincount(rng.integers(0,len(ids),len(ids)),minlength=len(ids))
        N=np.dot(counts,n);sst=np.dot(counts,y2)-np.dot(counts,ya)**2/N
        sa=np.dot(counts,sq_a);sb=np.dot(counts,sq_b)
        deltas.append([np.dot(counts,abs_b-abs_a)/N,np.sqrt(sb/N)-np.sqrt(sa/N),
                       (sa-sb)/sst if sst>0 else np.nan])
    array=np.asarray(deltas)
    return [{"metric":name,"lower":float(np.nanquantile(array[:,i],.025)),"upper":float(np.nanquantile(array[:,i],.975)),
             "valid_replicates":int(np.isfinite(array[:,i]).sum()),"replicates":replicates,"seed":seed,"level":"match"}
            for i,name in enumerate(("mae","rmse","r2"))]


def comparisons(ctx):
    unit_info=time_unit_info(ctx.cfg)
    a=pd.read_parquet(ctx.path("predictions/test_t0_linear.parquet"))
    b=pd.read_parquet(ctx.path("predictions/test_p2_linear.parquet"))
    a,b=pair_predictions(a,b)
    comparison=[]
    for left,right in zip(hierarchical(a,"normalized_placement"),hierarchical(b,"normalized_placement")):
        for name in ("mae","rmse","r2"):
            comparison.append({"metric":name,"aggregation":left["aggregation"],"reference":"T0","candidate":"T1=P2",
                               "T0":left[name],"T1":right[name],"delta":right[name]-left[name],"n":left["n"],"time_unit_status":unit_info["status"]})
    ctx.table("timing_comparison",pd.DataFrame(comparison))
    if not ctx.cfg["report"]["bootstrap_replicates"]:del a,b
    errors=[];plot_sample=[]
    for experiment in ("s1_linear","p2_linear"):
        frame=pd.read_parquet(ctx.path("predictions/test_"+experiment+".parquet"))
        for mode,g in frame.groupby("team_size_mode"):
            errors.append({"experiment":experiment,"slice":"mode","group":mode,"matches":g.match_id.nunique(),**metrics(g.actual,g.predicted)})
        from src.io import read_json
        task=experiment.split("_")[0];edges=read_json(ctx.path("manifests/bins_"+task+".json"))["edges"]
        # Outside training range remains visible, no clipping of extreme errors.
        bins=np.unique([-np.inf]+edges[1:-1]+[np.inf])
        for region,g in frame.groupby(pd.cut(frame.actual,bins,include_lowest=True),observed=True):
            errors.append({"experiment":experiment,"slice":"train_target_region","group":str(region),"matches":g.match_id.nunique(),**metrics(g.actual,g.predicted)})
        sample=frame.sample(min(1500,len(frame)),random_state=ctx.cfg["runtime"]["seed"])
        sample=sample[["actual","predicted","residual"]]
        ctx.table("prediction_plot_"+task,sample)
        figure(ctx,"predicted_observed_"+task,sample,"actual",["predicted"],"Dự đoán và thực tế - "+task,
               "Đường nét đứt là predicted=actual; sample chỉ vẽ, metrics trên toàn test cohort.",kind="scatter",unit=unit_info["label"] if task=="s1" else "Placement [0,1]",
               sample={"n":len(sample),"population":len(frame),"seed":ctx.cfg["runtime"]["seed"],"rule":"uniform without replacement"},analysis_scope="test",population_n=len(frame))
        figure(ctx,"residual_"+task,pd.DataFrame({"bin":pd.cut(frame.residual,20).value_counts(sort=False).index.astype(str),"n":pd.cut(frame.residual,20).value_counts(sort=False).values}),
               "bin",["n"],"Phân bố residual - "+task,"Residual=actual-predicted; đọc cả N và khoảng, không diễn giải nhân quả.",unit="Player-match")
    error_frame=pd.DataFrame(errors)
    error_frame["time_unit_status"]=unit_info["status"]
    error_frame["target_unit"]=np.where(error_frame.experiment.str.startswith("s1"),unit_info["label"],"Placement [0,1]")
    ctx.table("error_analysis",error_frame)
    for experiment in error_frame.experiment.unique():
        figure(ctx,"mode_error_"+experiment,error_frame[error_frame.slice.eq("mode") & error_frame.experiment.eq(experiment)].assign(group=lambda f:f["group"]),"group",["mae"],
               "Sai số theo mode - "+experiment,"Nhóm ít N/match kém ổn định; đọc cả coverage.",
               unit=unit_info["label"] if experiment.startswith("s1") else "Placement [0,1]",analysis_scope="test")
    comparison_frame=pd.DataFrame(comparison)
    figure(ctx,"timing_delta",comparison_frame[comparison_frame.aggregation.eq("micro")],"metric",["delta"],"Chênh lệch T1 so với T0",
           "MAE/RMSE âm và R² dương là tốt hơn; không significance nếu CI chưa tính.",unit="Delta theo metric",analysis_scope="test")
    replicates=ctx.cfg["report"]["bootstrap_replicates"]
    if replicates:
        if replicates<20:
            raise ValueError("CI requires >=20 declared replicates")
        ctx.table("timing_ci",pd.DataFrame(paired_bootstrap(a,b,replicates,ctx.cfg["report"]["bootstrap_seed"])))
    ctx.json("uncertainty",{"status":"completed" if replicates else "not_requested","replicates":replicates,
        "reason":"Không tuyên bố significance nếu chưa tính CI","delta":"candidate-reference","level":"match"})
