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
from sklearn.base import BaseEstimator, RegressorMixin, TransformerMixin
from sklearn.dummy import DummyRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.preprocessing import FunctionTransformer

from .features import FEATURES, TARGETS, allowlist
from .io import PendingDecision, digest, fingerprint, ident, publish, quote, compute_metadata, read_json, artifact_info, time_unit_info, frame_batches_fingerprint, require_memory
from .reporting import figure
from .gpu import run_jobs
from .evaluation import prediction_metrics, prediction_view, hierarchical_sql, paired_view, bootstrap_sql, error_slices, residual_histogram, plot_sample
from .storage import dataset_fingerprint, publish_prediction


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


def regression_solver(value):
    if value not in {"dense","tsqr"}:raise ValueError("Unknown regression solver; choose dense or tsqr explicitly")
    return value


def fit_memory_bytes(rows,columns,solver="dense"):
    if regression_solver(solver)=="tsqr":
        return 512*2**20+min(rows,50000)*(2*columns+2)*8*16
    # Full imputation/scaling/OLS still allocate; mmap is not an incremental fit.
    return rows*(2*columns+1)*8*5+min(rows,50000)*(2*columns+1)*8*5


def regression_matrix_bytes(rows,columns,solver="dense"):
    return min(rows,50000)*(2*columns+2)*8 if regression_solver(solver)=="tsqr" else rows*columns*16


def regression_vram_bytes(rows,columns,solver="dense"):
    return (2**30+regression_matrix_bytes(rows,columns,solver)*16
            if regression_solver(solver)=="tsqr" else rows*2*columns*8*4)


class BlockMeanImputer(TransformerMixin,BaseEstimator):
    """Global train means/counts and train-only missing indicators, never batch means at predict time."""
    def fit(self,x,y=None):
        columns=list(x.columns) if isinstance(x,pd.DataFrame) else [f"x{i}" for i in range(np.shape(x)[1])]
        return self.fit_batches((x[start:start+50000] for start in range(0,len(x),50000)),columns)

    def fit_batches(self,batches,columns):
        self.feature_names_in_=np.asarray(columns,dtype=object)
        self.n_features_in_=len(columns)
        self.statistics_=np.zeros(len(columns),dtype=np.float64)
        self.valid_counts_=np.zeros(len(columns),dtype=np.int64)
        self.missing_features_=np.zeros(len(columns),dtype=bool)
        self.rows_=0
        for frame in batches:
            x=self._array(frame);missing=np.isnan(x);counts=(~missing).sum(axis=0)
            means=np.divide(np.where(missing,0,x).sum(axis=0),counts,
                            out=np.zeros(len(columns)),where=counts>0)
            total=self.valid_counts_+counts
            self.statistics_+=(means-self.statistics_)*np.divide(counts,total,out=np.zeros(len(columns)),where=total>0)
            self.valid_counts_=total;self.missing_features_|=missing.any(axis=0);self.rows_+=len(x)
        if not self.rows_ or not np.isfinite(self.statistics_).all():raise ValueError("Invalid/empty imputation training data")
        self.indicator_features_=np.flatnonzero(self.missing_features_)
        return self

    def _array(self,frame):
        if isinstance(frame,pd.DataFrame) and list(frame.columns)!=list(self.feature_names_in_):
            raise ValueError("Imputer feature order changed")
        x=np.asarray(frame,dtype=np.float64)
        if x.ndim!=2 or x.shape[1]!=self.n_features_in_ or np.isinf(x).any():
            raise ValueError("Invalid imputer shape or infinite input")
        return x

    def transform(self,frame):
        x=self._array(frame);missing=np.isnan(x)
        filled=np.where(missing,self.statistics_,x)
        return np.concatenate((filled,missing[:,self.indicator_features_].astype(np.float64)),axis=1)

    def get_feature_names_out(self,input_features=None):
        if input_features is not None and list(input_features)!=list(self.feature_names_in_):
            raise ValueError("Imputer feature names changed")
        names=list(self.feature_names_in_)
        return np.asarray(names+["missingindicator_"+str(names[i]) for i in self.indicator_features_],dtype=object)


def qr_backend(device):
    if device=="cpu":return np
    if device!="cuda":raise ValueError("Unknown TSQR device")
    try:
        import cupy
        if cupy.cuda.runtime.getDeviceCount()<1:raise RuntimeError("No CUDA device")
        return cupy
    except Exception as error:
        raise RuntimeError("CUDA TSQR unavailable; no CPU fallback") from error


def checked_factor(xp,operation,array,**options):
    if xp is np:return getattr(xp.linalg,operation)(array,**options)
    import cupyx
    with cupyx.errstate(linalg="raise"):
        return getattr(xp.linalg,operation)(array,**options)


class TSQROLS(RegressorMixin,BaseEstimator):
    def __init__(self,device="cpu"):
        self.device=device

    def fit(self,x,y):
        x=np.asarray(x,dtype=np.float64);y=np.asarray(y,dtype=np.float64)
        if x.ndim!=2 or not len(x) or y.shape!=(len(x),):raise ValueError("Invalid OLS training shape")
        return self.fit_batches(((x[s:s+50000],y[s:s+50000]) for s in range(0,len(x),50000)),
                                x.mean(axis=0),float(y.mean()),len(x))

    def fit_batches(self,batches,offset,y_offset,rows):
        xp=qr_backend(self.device);R=None;seen=0
        self.n_features_in_=len(offset)
        if rows<1 or not self.n_features_in_:raise ValueError("Empty TSQR design")
        for x,y in batches:
            if np.shape(x)!=(len(x),self.n_features_in_) or np.shape(y)!=(len(x),):
                raise ValueError("Invalid TSQR block shape")
            a=np.column_stack((x-offset,np.asarray(y,dtype=np.float64)-y_offset))
            if not np.isfinite(a).all():raise ValueError("Nonfinite TSQR training block")
            block=xp.asarray(a,dtype=xp.float64)
            local=checked_factor(xp,"qr",block,mode="r")
            R=local if R is None else checked_factor(xp,"qr",xp.concatenate((R,local),axis=0),mode="r")
            seen+=len(x)
            del block,local,a
        if R is None or seen!=rows:raise ValueError("TSQR training row count changed")
        design,rhs=R[:,:self.n_features_in_],R[:,-1]
        u,s,vh=checked_factor(xp,"svd",design,full_matrices=False)
        # Rank cutoff uses the ORIGINAL design dimensions, not the reduced R dimensions.
        self.rcond_=max(rows,self.n_features_in_)*np.finfo(np.float64).eps
        keep=s>self.rcond_*s[0]
        weights=xp.zeros_like(s)
        weights[keep]=(u.T@rhs)[keep]/s[keep]
        coef=vh.T@weights
        to_host=np.asarray if xp is np else xp.asnumpy
        self.coef_=to_host(coef);self.singular_=to_host(s)
        self.rank_=int(to_host(keep).sum());self.training_rows_=seen
        self.intercept_=float(y_offset-np.dot(offset,self.coef_))
        if not np.isfinite(self.coef_).all() or not np.isfinite(self.intercept_):raise ValueError("Nonfinite TSQR solution")
        return self

    def predict(self,x):
        xp=qr_backend(self.device)
        result=xp.asarray(x,dtype=xp.float64)@xp.asarray(self.coef_)+self.intercept_
        return np.asarray(result) if xp is np else xp.asnumpy(result)


def exact_target_quantiles(con,bundle,probabilities):
    """External global Type-7 sort; no full target copy or chunk medians."""
    n=bundle["rows"];target=ident(bundle["target"])
    try:
        con.execute(f"CREATE TABLE regression_target_ordered AS SELECT {target} x,"
                    f"row_number() OVER(ORDER BY {target}) ordinal FROM read_parquet({quote(bundle['metadata'])})")
        if con.execute("SELECT count(*) FROM regression_target_ordered").fetchone()[0]!=n:raise ValueError("Target quantile count mismatch")
        values=[]
        for p in probabilities:
            if not 0<=p<=1:raise ValueError("Invalid target quantile")
            h=(n-1)*p;low=int(np.floor(h));fraction=h-low
            values.append(con.execute("SELECT quantile_cont(x,?) FROM regression_target_ordered WHERE ordinal IN (?,?)",
                                      [fraction,low+1,low+1+bool(fraction)]).fetchone()[0])
        return values
    finally:con.execute("DROP TABLE IF EXISTS regression_target_ordered")


def block_pipeline(train,logs,device,kind,median=None):
    X=y=None
    try:
        X=np.load(train["X"],mmap_mode="r");y=np.load(train["y"],mmap_mode="r")
        n=train["rows"];columns=train["columns"]
        if X.shape!=(n,len(columns)) or y.shape!=(n,) or X.dtype!=np.float64 or y.dtype!=np.float64:
            raise ValueError("TSQR matrix shape/dtype mismatch")
        log=FunctionTransformer(log_features,kw_args={"columns":logs})
        def inputs():
            for start in range(0,n,50000):
                yield log.transform(pd.DataFrame(X[start:start+50000],columns=columns,copy=False))
        imputer=BlockMeanImputer().fit_batches(inputs(),columns)
        scaler=StandardScaler()
        for frame in inputs():scaler.partial_fit(imputer.transform(frame))
        offset=np.zeros(len(imputer.get_feature_names_out()));seen=0
        anchor=float(y[0]);total=0.;compensation=0.
        for start,frame in zip(range(0,n,50000),inputs()):
            z=scaler.transform(imputer.transform(frame));size=len(z)
            offset+=(z.mean(axis=0)-offset)*size/(seen+size);seen+=size
            target=np.asarray(y[start:start+size])
            if not np.isfinite(target).all():raise ValueError("Nonfinite training target")
            value=float(np.sum(target-anchor))-compensation
            updated=total+value;compensation=(updated-total)-value;total=updated
        y_mean=anchor+total/n
        if kind=="linear":
            def batches():
                for start,frame in zip(range(0,n,50000),inputs()):
                    yield scaler.transform(imputer.transform(frame)),y[start:start+len(frame)]
            model=TSQROLS(device).fit_batches(batches(),offset,y_mean,n)
        else:
            if kind not in {"mean","median"} or kind=="median" and (median is None or not np.isfinite(median)):
                raise ValueError("Exact train median required for the median baseline")
            model=DummyRegressor(strategy=kind)
            # These are the global train statistics, not a fit on fabricated/sample rows.
            model.constant_=np.array([[y_mean if kind=="mean" else median]],dtype=np.float64)
            model.n_outputs_=1
        return Pipeline([("log",log),("imputer",imputer),("scaler",scaler),("model",model)])
    finally:close_mmaps(X,y)


def prediction_memory_bytes(rows,characters):
    # Maximum key length, not a full-frame allocation; SQL metrics use disk tables.
    return min(rows,50000)*((2*max(map(len,FEATURES.values()))+1)*8*5+8*64+int(characters)*4)


def close_mmaps(*arrays):
    # Tracebacks can retain views; GC alone keeps files locked on Windows failures.
    for array in arrays:
        if array is not None:array._mmap.close()


def matrix_data(ctx,con,task,split,work):
    """Separate normalized JOINs from blocking statistics/sort; retain exact global row order."""
    columns=FEATURES[task]
    allowlist(task,columns)
    condition="valid_survival" if task=="s1" else "valid_placement"
    fields=["row_id","match_id","team_id","team_size_mode","split",TARGETS[task],
            *columns,"player_name",condition]
    threads=con.execute("SELECT current_setting('threads')").fetchone()[0]
    with tempfile.TemporaryDirectory(prefix="pubg-matrix-source-",dir=work) as folder:
        source=Path(folder)/"projection.parquet"
        try:
            con.execute("SET threads=1")
            ctx.progress("matrix projection to disk; no global sort",task=task,split=split)
            con.execute(f"COPY (SELECT {','.join(ident(c) for c in fields)} FROM p "
                        f"WHERE split={quote(split)} AND {condition}) TO {quote(source)} "
                        "(FORMAT PARQUET,COMPRESSION ZSTD,ROW_GROUP_SIZE 8192)")
        finally:con.execute(f"SET threads={int(threads)}")
        with ctx.disk_db() as scan:
            scan.execute("SET threads=1")
            scan.execute(f"CREATE VIEW p AS SELECT * FROM read_parquet({quote(source)})")
            ctx.progress("matrix statistics and external sort from projection",task=task,split=split)
            return _matrix_data(ctx,scan,task,split,work)


def _matrix_data(ctx,con,task,split,work):
    columns=FEATURES[task]
    allowlist(task,columns)
    condition="valid_survival" if task=="s1" else "valid_placement"
    where=f"split={quote(split)} AND {condition}"
    strings=" + ".join(f"coalesce(length(CAST({ident(c)} AS VARCHAR)),0)" for c in
                       ("row_id","match_id","team_id","team_size_mode","split"))
    n,chars=con.execute(f"SELECT count(*),coalesce(max({strings}),0) FROM p WHERE {where}").fetchone()
    if not n:
        raise ValueError(f"Empty eligible cohort: {task}/{split}")
    # Separate spillable key grouping instead of two growing DISTINCT aggregates.
    matches,players=[con.execute(f"SELECT count(*) FROM (SELECT {ident(c)} FROM p WHERE {where} AND {ident(c)} IS NOT NULL GROUP BY {ident(c)})").fetchone()[0]
                     for c in ("match_id","player_name")]
    require_memory(ctx.cfg,min(n,50000)*(len(columns)+8)*8*5,f"{task}/{split} matrix batch")
    target=TARGETS[task]
    metadata=["row_id","match_id","team_id","team_size_mode","split",target]
    fields=metadata+columns
    prefix=Path(work)/(task+"."+split)
    x_path=Path(str(prefix)+".X.npy");y_path=Path(str(prefix)+".y.npy");meta_path=Path(str(prefix)+".meta.parquet")
    X=y=reader=None;offset=0;last=None
    try:
        X=np.lib.format.open_memmap(x_path,mode="w+",dtype=np.float64,shape=(n,len(columns)))
        y=np.lib.format.open_memmap(y_path,mode="w+",dtype=np.float64,shape=(n,))
        reader=con.execute(f"SELECT {','.join(ident(c) for c in fields)} FROM p WHERE {where} ORDER BY row_id").fetch_record_batch(50000)
        with pq.ParquetWriter(meta_path,pa.schema([reader.schema.field(c) for c in metadata]),compression="zstd") as writer:
            def batches():
                nonlocal offset,last
                for batch in reader:
                    frame=batch.to_pandas();ids=frame.row_id
                    if ids.isna().any() or ids.duplicated().any() or not ids.is_monotonic_increasing or (last is not None and ids.iloc[0]<=last):
                        raise ValueError("Matrix row IDs must be unique, nonnull and sorted")
                    last=ids.iloc[-1];stop=offset+len(frame)
                    X[offset:stop]=frame[columns].to_numpy(dtype=np.float64,na_value=np.nan)
                    values=frame[target].to_numpy(dtype=np.float64,na_value=np.nan)
                    if not np.isfinite(values).all():raise ValueError("Nonfinite matrix target")
                    y[offset:stop]=values
                    writer.write_batch(batch.select(metadata))
                    offset=stop
                    yield frame[["row_id",target]]
            cohort_hash=frame_batches_fingerprint(batches())
        if offset!=n:raise ValueError("Matrix row count changed")
        X.flush();y.flush()
    finally:
        try:
            if reader is not None:reader.close()
        finally:close_mmaps(X,y)
    return {"layout":"numeric_memmap_v1","X":str(x_path),"y":str(y_path),"metadata":str(meta_path),
            "metadata_sha256":digest(meta_path),
            "rows":n,"columns":columns,"target":target,"prediction_host_bytes":prediction_memory_bytes(n,chars),
            "cohort":{"task":task,"split":split,"rows":n,"matches":matches,"players":players,"cohort_hash":cohort_hash}}


def stream_predictions(bundle,task,model,experiment,run_id,path,reference=None):
    """Bounded prediction only; fitting and downstream metrics are not out-of-core."""
    if bundle["layout"]!="numeric_memmap_v1" or bundle["columns"]!=FEATURES[task] or bundle["target"]!=TARGETS[task]:
        raise ValueError("Matrix bundle schema mismatch")
    if digest(Path(bundle["metadata"]))!=bundle["metadata_sha256"]:raise ValueError("Prediction metadata checksum mismatch")
    n=bundle["rows"];target=TARGETS[task]
    X=y=None;offset=0;last=None;writer=None
    try:
        X=np.load(bundle["X"],mmap_mode="r");y=np.load(bundle["y"],mmap_mode="r")
        if X.shape!=(n,len(FEATURES[task])) or y.shape!=(n,) or X.dtype!=np.float64 or y.dtype!=np.float64:
            raise ValueError("Matrix bundle shape/dtype mismatch")
        def batches():
            nonlocal offset,last,writer
            for batch in pq.ParquetFile(bundle["metadata"]).iter_batches(batch_size=50000):
                frame=batch.to_pandas();stop=offset+len(frame);ids=frame.row_id
                if ids.isna().any() or ids.duplicated().any() or not ids.is_monotonic_increasing or (last is not None and ids.iloc[0]<=last):
                    raise ValueError("Prediction metadata row identity mismatch")
                last=ids.iloc[-1]
                if stop>n or not np.array_equal(frame[target].to_numpy(float),y[offset:stop]):
                    raise ValueError("Prediction metadata target mismatch")
                inputs=pd.DataFrame(X[offset:stop],columns=FEATURES[task],copy=False)
                predicted=np.asarray(model.predict(inputs)).reshape(-1)
                if len(predicted)!=len(frame) or not np.isfinite(predicted).all():raise ValueError("Nonfinite/invalid prediction")
                if reference is not None and not np.allclose(predicted,np.asarray(reference.predict(inputs)).reshape(-1),rtol=1e-7,atol=1e-7):
                    raise ValueError("Model reload predictions mismatch")
                result=frame[["row_id","match_id","team_id","team_size_mode","split"]].copy()
                result["actual"]=y[offset:stop];result["predicted"]=predicted;result["residual"]=result.actual-result.predicted
                result["experiment"]=experiment;result["run_id"]=run_id;result["target"]=target
                schema=pa.schema([batch.schema.field(c) for c in ("row_id","match_id","team_id","team_size_mode","split")]
                    +[pa.field(c,pa.float64()) for c in ("actual","predicted","residual")]
                    +[pa.field(c,pa.string()) for c in ("experiment","run_id","target")])
                table=pa.Table.from_pandas(result,schema=schema,preserve_index=False)
                if writer is None:writer=pq.ParquetWriter(path,table.schema,compression="zstd")
                writer.write_table(table);offset=stop
                yield frame[["row_id",target]]
        cohort_hash=frame_batches_fingerprint(batches())
        if offset!=n or cohort_hash!=bundle["cohort"]["cohort_hash"]:raise ValueError("Prediction cohort identity mismatch")
    finally:
        try:
            if writer is not None:writer.close()
        finally:close_mmaps(X,y)
    return str(path)


def prediction_frame(frame,task,model,experiment,run_id):
    result=frame[["row_id","match_id","team_id","team_size_mode","split"]].copy()
    result["actual"]=frame[TARGETS[task]].to_numpy()
    predicted=np.empty(len(frame),dtype=np.float64)
    for start in range(0,len(frame),50000):
        predicted[start:start+50000]=np.asarray(model.predict(frame.iloc[start:start+50000][FEATURES[task]])).reshape(-1)
    result["predicted"]=predicted
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
    solver=regression_solver(payload.get("solver","dense"))
    require_memory({"runtime":payload["runtime"]},fit_memory_bytes(train["rows"],len(FEATURES[task]),solver)+validation["prediction_host_bytes"],"S08 full fit and validation")
    compute=compute_metadata(payload["device"] if kind=="linear" else "cpu",regression_matrix_bytes(train["rows"],len(FEATURES[task]),solver))
    if solver=="tsqr":
        model=block_pipeline(train,payload["logs"],payload["device"],kind,payload.get("train_median"))
        final_estimator=model.named_steps["model"]
        compute.update(solver="tsqr_global_centered_qr_svd_float64",training_rows=train["rows"],batch_rows=50000,
                       preprocessing="global train means/missing indicators; StandardScaler.partial_fit on every train block",
                       rank_rcond=getattr(final_estimator,"rcond_",None),normal_equations=False)
        joblib.dump(model,payload["model_path"])
        loaded=joblib.load(payload["model_path"])
        path=stream_predictions(validation,task,loaded,payload["experiment"],payload["run_id"],payload["prediction_path"],reference=model)
        return {"prediction_path":path,"names":list(loaded.named_steps["imputer"].get_feature_names_out(FEATURES[task])) if kind=="linear" else [],
                "coefficients":np.asarray(final_estimator.coef_) if kind=="linear" else [],
                "compute":compute,"backend":type(final_estimator).__module__}
    final_estimator=estimator(payload["device"]) if kind=="linear" else DummyRegressor(strategy=kind)
    model=Pipeline([("log",FunctionTransformer(log_features,kw_args={"columns":payload["logs"]})),
                    ("imputer",SimpleImputer(strategy="mean",add_indicator=True,keep_empty_features=True)),
                    ("scaler",StandardScaler()),("model",final_estimator)])
    X=y=None
    try:
        X=np.load(train["X"],mmap_mode="r");y=np.load(train["y"],mmap_mode="r")
        model.fit(pd.DataFrame(X,columns=FEATURES[task],copy=False),y)
    finally:
        close_mmaps(X,y)
    joblib.dump(model,payload["model_path"])
    loaded=joblib.load(payload["model_path"])
    path=stream_predictions(validation,task,loaded,payload["experiment"],payload["run_id"],payload["prediction_path"],reference=model)
    names=loaded.named_steps["imputer"].get_feature_names_out(FEATURES[task]) if kind=="linear" else []
    coef=np.asarray(loaded.named_steps["model"].coef_).reshape(-1) if kind=="linear" else []
    return {"prediction_path":path,"names":list(names),"coefficients":coef,
            "compute":compute,"backend":type(final_estimator).__module__}


def predict_candidate(payload):
    bundle=joblib.load(payload["data"])
    require_memory({"runtime":payload["runtime"]},bundle["prediction_host_bytes"],"S08 prediction and metrics")
    compute_metadata(payload["device"],min(bundle["rows"],50000)*len(FEATURES[payload["task"]])*8)
    model=joblib.load(payload["model_path"])
    return {"prediction_path":stream_predictions(bundle,payload["task"],model,payload["experiment"],payload["run_id"],payload["prediction_path"])}


def prediction(ctx):
    with tempfile.TemporaryDirectory(prefix="pubg-regression-",dir=ctx.temp) as folder:
        _prediction(ctx,Path(folder))


def _prediction(ctx,work):
    cfg=ctx.cfg["rq3"]
    solver=regression_solver(cfg.get("solver","dense"))
    parallel=cfg["device"]=="cuda"
    unit_info=time_unit_info(ctx.cfg)
    records,cohorts,models,model_meta,coefficients=[],[],{},[],[]
    with ctx.disk_db() as con:
        ctx.view(con,"p","player_match")
        input_identity=dataset_fingerprint(ctx,"player_match")
        training_signature=fingerprint({"input":input_identity,
            "features":ctx.cfg["features"],"device":cfg["device"],"gpu_ids":cfg.get("gpu_ids",[0]),"bins":cfg["error_quantiles"],"time_unit":unit_info,
            "solver":solver,
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
                prediction_path=ctx.path("predictions/validation_"+experiment+".parquet")
                publish_prediction(ctx,Path(result["prediction_path"]),prediction_path,joblib.load(payload["data"])["validation"])
                for row in prediction_metrics(ctx,prediction_path,TARGETS[task]):
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
                train=matrix_data(ctx,con,task,"train",work)
                validation=matrix_data(ctx,con,task,"validation",work)
                for split,data in (("train",train),("validation",validation)):
                    cohorts.append(data["cohort"])
                del data
                if task=="t0":
                    for split,bundle in (("train",train),("validation",validation)):
                        reference=next(c for c in cohorts if c["task"]=="p2" and c["split"]==split)
                        if any(bundle["cohort"][c]!=reference[c] for c in ("rows","cohort_hash")):
                            raise ValueError("T0/T1 cohort mismatch before fit")
                data=work/(task+".data.joblib");joblib.dump({"train":train,"validation":validation},data)
                require_memory(ctx.cfg,fit_memory_bytes(train["rows"],len(FEATURES[task]),solver)+validation["prediction_host_bytes"],"S08 full fit and validation")
                median=None
                if solver=="tsqr":
                    quantiles=exact_target_quantiles(con,train,[*cfg["error_quantiles"],.5])
                    bins=np.unique(quantiles[:-1]).tolist();median=quantiles[-1]
                else:
                    train_y=np.load(train["y"],mmap_mode="r")
                    try:bins=np.unique(np.quantile(train_y,cfg["error_quantiles"])).tolist()
                    finally:close_mmaps(train_y)
                for kind in (("mean","median","linear") if task!="t0" else ("linear",)):
                    experiment=f"{task}_{kind}"
                    ctx.progress("train/validation fit",experiment=experiment,train_rows=train["rows"],validation_rows=validation["rows"],test_accessed=False)
                    run_id=uuid.uuid4().hex
                    payload={"data":str(data),"model_path":str(work/(experiment+".joblib")),
                             "prediction_path":str(work/(experiment+".validation.parquet")),"runtime":ctx.cfg["runtime"],
                             "task":task,"kind":kind,"device":cfg["device"],"experiment":experiment,"run_id":run_id,
                             "logs":[c for c in ctx.cfg["features"]["log_columns"] if c in FEATURES[task]],
                             "bins":bins,"solver":solver,"train_median":median}
                    job={"kind":"regression_fit","key":experiment,"payload":payload,
                         "matrix_bytes":regression_matrix_bytes(train["rows"],len(FEATURES[task]),solver),
                         "host_bytes":fit_memory_bytes(train["rows"],len(FEATURES[task]),solver)+validation["prediction_host_bytes"]}
                    if parallel and kind=="linear":jobs.append(job)
                    else:accept_fit(job,fit_candidate(payload))
                del train,validation
            if parallel:
                for job,path in run_jobs(ctx,"rq3",jobs):accept_fit(job,joblib.load(path))
            # All consumers finished and canonical models/predictions passed publication.
            for task in ("s1","p2","t0"):
                data_path=work/(task+".data.joblib")
                for bundle in joblib.load(data_path).values():
                    for key in ("X","y","metadata"):
                        path=Path(bundle[key])
                        if path.parent!=work:raise ValueError("Matrix scratch escaped owned work directory")
                        path.unlink()
                data_path.unlink()
            validation_table=pd.DataFrame(records)
            val_path=ctx.table("validation_metrics",validation_table)
            cohort_path=ctx.table("model_cohorts",pd.DataFrame(cohorts))
            validation_hash=fingerprint({"metrics":digest(val_path),"cohorts":digest(cohort_path),
                "input":input_identity,"features":FEATURES,
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
        test_jobs=[];test_bundles={}
        execution_by_model={m["experiment"]:m.get("gpu_execution") for m in model_meta}
        def accept_test(experiment,task,result):
            path=ctx.path("predictions/test_"+experiment+".parquet")
            publish_prediction(ctx,Path(result["prediction_path"]),path,test_bundles[task])
            for row in prediction_metrics(ctx,path,TARGETS[task]):
                records.append({"experiment":experiment,"target":TARGETS[task],"split":"test","device":cfg["device"] if experiment.endswith("linear") else "cpu",
                                "time_unit_status":unit_info["status"],"target_unit":unit_info["label"] if task=="s1" else "Placement [0,1]",**row})
        for experiment,(task,model,run_id) in models.items():
            if task not in test_bundles:
                test_bundles[task]=matrix_data(ctx,con,task,"test",work)
                joblib.dump(test_bundles[task],work/(task+".test.joblib"))
            test=test_bundles[task]
            data=work/(task+".test.joblib")
            payload={"data":str(data),"model_path":str(ctx.path("models/"+experiment+".joblib")),
                     "prediction_path":str(work/(experiment+".test.parquet")),"runtime":ctx.cfg["runtime"],
                     "task":task,"experiment":experiment,"run_id":run_id,"device":"cuda" if parallel and experiment.endswith("linear") else "cpu"}
            if parallel and experiment.endswith("linear"):
                execution=execution_by_model[experiment]
                if not execution:raise ValueError("Dual-GPU cached model thiếu GPU identity; không đoán thiết bị")
                test_jobs.append({"kind":"regression_predict","key":experiment,"gpu_id":execution["gpu_id"],
                                  "matrix_bytes":min(test["rows"],50000)*len(FEATURES[task])*8,
                                  "host_bytes":test["prediction_host_bytes"],"payload":payload})
            else:accept_test(experiment,task,predict_candidate(payload))
            del test
        test_executions=[]
        if parallel:
            for job,path in run_jobs(ctx,"rq3",test_jobs):
                result=joblib.load(path);experiment=job["key"]
                accept_test(experiment,job["payload"]["task"],result)
                test_executions.append({"experiment":experiment,**result["gpu_execution"]})
            ctx.json("gpu_rq3_test",{"executions":test_executions,"after_selection_approval":True})
        ctx.table("model_metrics",pd.DataFrame(records))
        ctx.json("models",{"core":model_meta,"gpu_ids":cfg.get("gpu_ids",[0]),"T1_alias":"p2_linear","scope":ctx.scope,"optional_RF":"not_requested"})
        ctx.json("s08_execution",{"matrix_layout":"float64 numeric mmap plus separate metadata Parquet; shared per task/split",
            "persistent_prediction_layout":ctx.cfg["storage"].get("layout","materialized"),
            "prediction":"bounded 50000-row batches and temporary Parquet; no full prediction frame returned by worker",
            "fit":"global train-only blocked mean/scaling and centered TSQR/SVD; original-dimension rank cutoff, no normal equations" if solver=="tsqr" else "one unchanged full Pipeline.fit per registered experiment, not incremental; guarded host/VRAM",
            "solver":solver,
            "metrics":"global two-pass metrics, match/team aggregation on owned disk database; no full prediction frame",
            "cohort":"sorted unique row IDs and exact target/hash checked before publication","sampling_fit":False})


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
    replicates=ctx.cfg["report"]["bootstrap_replicates"]
    if replicates and replicates<20:raise ValueError("CI requires >=20 declared replicates")
    with ctx.disk_db() as con:
        paired_view(con,ctx.path("predictions/test_t0_linear.parquet"),ctx.path("predictions/test_p2_linear.parquet"))
        comparison=[]
        for left,right in zip(hierarchical_sql(con,"pair_left","normalized_placement"),hierarchical_sql(con,"pair_right","normalized_placement")):
            for name in ("mae","rmse","r2"):
                comparison.append({"metric":name,"aggregation":left["aggregation"],"reference":"T0","candidate":"T1=P2",
                                   "T0":left[name],"T1":right[name],"delta":right[name]-left[name],"n":left["n"],"time_unit_status":unit_info["status"]})
        ci=bootstrap_sql(ctx,con,replicates,ctx.cfg["report"]["bootstrap_seed"]) if replicates else None
    ctx.table("timing_comparison",pd.DataFrame(comparison))
    errors=[]
    for experiment in ("s1_linear","p2_linear"):
        path=ctx.path("predictions/test_"+experiment+".parquet")
        task=experiment.split("_")[0];edges=read_json(ctx.path("manifests/bins_"+task+".json"))["edges"]
        with ctx.disk_db() as con:
            n=prediction_view(con,"error_input",path)
            errors.extend({"experiment":experiment,**r} for r in error_slices(con,"error_input",edges))
            histogram=residual_histogram(con,"error_input")
        sample=plot_sample(ctx,path,n,ctx.cfg["runtime"]["seed"])
        ctx.table("prediction_plot_"+task,sample)
        figure(ctx,"predicted_observed_"+task,sample,"actual",["predicted"],"Dự đoán và thực tế - "+task,
               "Đường nét đứt là predicted=actual; sample chỉ vẽ, metrics trên toàn test cohort.",kind="scatter",unit=unit_info["label"] if task=="s1" else "Placement [0,1]",
               sample={"n":len(sample),"population":n,"seed":ctx.cfg["runtime"]["seed"],"rule":"uniform without replacement"},analysis_scope="test",population_n=n)
        figure(ctx,"residual_"+task,histogram,
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
    if replicates:ctx.table("timing_ci",pd.DataFrame(ci))
    ctx.json("uncertainty",{"status":"completed" if replicates else "not_requested","replicates":replicates,
        "reason":"Không tuyên bố significance nếu chưa tính CI","delta":"candidate-reference","level":"match"})
    ctx.json("s09_execution",{"metrics":"global centered two-pass sums; no mean of batch metrics",
        "pairing":"full unique row IDs and null-safe identity/target checks before metrics; disk-backed SQL join",
        "bootstrap":"one numeric state per match, unchanged RNG/multiplicity; guarded in-memory state vectors",
        "plots":"same RandomState sample and pandas bin boundaries; projected Parquet batches, guarded O(N) index workspace",
        "full_prediction_frames_collected":False,"sampling_fit":False})
