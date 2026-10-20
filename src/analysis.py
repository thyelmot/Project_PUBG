"""EDA SQL, exact pairwise Spearman và KMeans per_mode."""
import tempfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

from .features import ABSOLUTE, BASE, PHASE
from .io import PendingDecision, digest, fingerprint, ident, publish, quote, compute_metadata, time_unit_info, frame_fingerprint, require_memory
from .reporting import figure
from .gpu import run_jobs

PROFILE_RAW={"avg_kills":"player_kills","avg_damage":"player_dmg","avg_walk":"player_dist_walk",
             "avg_ride":"player_dist_ride","avg_walk_ratio":"walk_ratio","avg_assists":"player_assists",
             "avg_dbno":"player_dbno","avg_assist_ratio":"assist_ratio"}
PROFILE_FEATURES=list(PROFILE_RAW)+["std_kills","std_damage","avg_early_kill_ratio","avg_mid_kill_ratio","avg_late_kill_ratio","early_combat_match_ratio"]


def column_quantiles(con, column, n):
    """Exact Type-7 quantiles: sort one column on disk, interpolate <=2 endpoints."""
    if not n:
        return con.execute("SELECT NULL::DOUBLE median,NULL::DOUBLE q25,NULL::DOUBLE q75").df()
    where=" AND valid_survival" if column=="player_survive_time" else ""
    try:
        con.execute(f"""CREATE TABLE eda_ordered AS SELECT x,row_number() OVER(ORDER BY x) ordinal
            FROM (SELECT {ident(column)} x FROM dev WHERE {ident(column)} IS NOT NULL{where})""")
        if con.execute("SELECT count(*) FROM eda_ordered").fetchone()[0]!=n:
            raise ValueError("EDA non-null count changed before quantile selection")
        expressions=[];endpoints=set()
        for name,numerator in (("median",2),("q25",1),("q75",3)):
            low,remainder=divmod((int(n)-1)*numerator,4)
            lo,hi=low+1,low+1+bool(remainder)
            endpoints.update((lo,hi))
            expressions.append(f"quantile_cont(x,{remainder/4}) FILTER(WHERE ordinal IN ({lo},{hi})) AS {name}")
        # Reuse DuckDB's interpolation kernel; never average batch quantiles.
        return con.execute("SELECT "+",".join(expressions)+" FROM eda_ordered WHERE ordinal IN ("+
                           ",".join(str(i) for i in sorted(endpoints))+")").df()
    finally:
        con.execute("DROP TABLE IF EXISTS eda_ordered")


def eda_statistics(con, unit_info, progress):
    columns=BASE+ABSOLUTE+PHASE+["player_survive_time","normalized_placement"]
    expressions=["count(*) n","count(*) FILTER(WHERE valid_survival) survival_n"]
    names=["valid","mean","std","min","max","skew","zero"]
    for i,column in enumerate(columns):
        c=ident(column)
        condition="valid_survival" if column=="player_survive_time" else "TRUE"
        aggregates=[f"count({c})",f"avg({c})",f"stddev_samp({c})",f"min({c})",f"max({c})",f"skewness({c})"]
        expressions.extend(f"{aggregate} FILTER(WHERE {condition}) c{i}_{name}" for name,aggregate in zip(names,aggregates))
        expressions.append(f"count(*) FILTER(WHERE {condition} AND {c}=0) c{i}_zero")
    scalar=con.execute("SELECT "+",".join(expressions)+" FROM dev").df()
    rows=[]
    for i,column in enumerate(columns):
        row=scalar[["survival_n" if column=="player_survive_time" else "n"]+[f"c{i}_{name}" for name in names]].copy()
        row.columns=["n"]+names
        progress("exact EDA quantiles",feature=column,column_index=i+1,columns=len(columns),valid=int(row["valid"].iloc[0]))
        quantiles=column_quantiles(con,column,int(row["valid"].iloc[0]))
        for name in ("median","q25","q75"):row[name]=quantiles[name]
        row=row[["n","valid","mean","median","std","min","max","q25","q75","skew","zero"]]
        row["feature"]=column
        row["missing"]=row["n"]-row["valid"]
        row["time_unit_status"]=unit_info["status"]
        row["unit"]=unit_info["label"] if column in {"player_survive_time","first_kill_time","avg_kill_time"} else "Xem feature_dictionary"
        rows.append(row)
    return pd.concat(rows,ignore_index=True)


def eda(ctx):
    unit_info=time_unit_info(ctx.cfg)
    with ctx.disk_db() as con:
        ctx.view(con,"p","player_match")
        con.execute("CREATE VIEW dev AS SELECT * FROM p WHERE split IN ('train','validation')")
        ctx.progress("EDA scalar statistics and exact global quantiles")
        stats=eda_statistics(con,unit_info,ctx.progress)
        ctx.table("eda_statistics",stats)
        modes=con.execute("SELECT team_size_mode,count(*) n,avg(player_kills) kills,avg(player_dmg) damage,avg(player_dist_walk) walk,avg(player_survive_time) FILTER(WHERE valid_survival) survival,avg(normalized_placement) placement FROM dev GROUP BY ALL").df()
        modes["time_unit_status"]=unit_info["status"];modes["survival_unit"]=unit_info["label"]
        ctx.table("mode_statistics",modes)
        for c in ("player_kills","player_dmg","player_survive_time","normalized_placement","first_kill_time"):
            valid_filter="AND valid_survival" if c=="player_survive_time" else ""
            stat=stats.loc[stats.feature.eq(c)].iloc[0]
            lo,hi=(float(stat["min"]),float(stat["max"])) if stat["valid"] else (None,None)
            width=(hi-lo)/30 if lo is not None and hi>lo else 1
            hist=con.execute(f"SELECT least(29,floor(({ident(c)}-?)/?)) bin,count(*) n FROM dev WHERE {ident(c)} IS NOT NULL {valid_filter} GROUP BY bin ORDER BY bin",[lo or 0,width]).df()
            hist=hist.set_index("bin").reindex(range(30),fill_value=0).rename_axis("bin").reset_index()
            hist["left_edge"]=(lo or 0)+hist.bin*width;hist["right_edge"]=hist.left_edge+width
            hist["source_unit"]=time_unit_info(ctx.cfg)["label"] if c in {"first_kill_time","player_survive_time"} else ("placement [0,1]" if c=="normalized_placement" else "đơn vị giá trị nguồn")
            figure(ctx,"hist_"+c,hist,"left_edge",["n"],"Phân bố "+c,
                   "30 khoảng min-max train+validation, kể cả khoảng0; trụcX=biên trái, right_edge/source_unit ở bảng.",
                   unit="Số player-match",analysis_scope="train+validation",population_n=int(hist.n.sum()))
        figure(ctx,"eda_missing",stats,"feature",["missing","zero"],"Giá trị thiếu và bằng 0","Missing khác zero; N/valid/missing trong bảng nguồn.",unit="Số player-match")
        figure(ctx,"mode_kills",modes,"team_size_mode",["kills"],"Số hạ gục trung bình theo mode","Khác biệt mô tả, không dùng outcome để chọn representation.",unit="kills/player-match")
        feature_cfg=ctx.cfg["features"]
        reason=feature_cfg.get("transform_reason")
        if reason is None and feature_cfg.get("decision_mode","manual")=="auto" and not feature_cfg["log_columns"]:
            reason="Auto policy approved 2026-10-17: unchanged features, no log and no outlier removal; no outcome-driven transformation selection"
        ctx.json("eda_scope",{"scope":"train+validation","test_used":False,"outlier_removal":"none","transform_reason":reason,
                             "log_columns":feature_cfg["log_columns"],"decision_mode":feature_cfg.get("decision_mode","manual")})
        ctx.json("s05_execution",{"storage":"temporary_disk_database","scalar_scans":1,
            "quantiles":"exact global row_number sort per column; Type-7 interpolation on endpoints only",
            "histogram_range":"reuse exact scalar min/max","duckdb_memory":ctx.cfg["runtime"]["duckdb_memory"],
            "threads":ctx.cfg["runtime"]["threads"],"sampling":False,"scope":"train+validation"})
        if reason is None:
            raise PendingDecision("S05: đọc eda_statistics, ghi features.transform_reason (kể cả giữ nguyên, không log)")


def pair_correlations(con, query):
    """Pair-specific global ties; no rank or correlation computed per partition."""
    try:
        con.execute("CREATE TABLE rq_pairs AS "+query)
        row=con.execute("SELECT count(*) n,corr(x,y) pearson FROM rq_pairs").df().iloc[0].to_dict()
        for column in ("x","y"):
            con.execute(f"CREATE TABLE value_counts AS SELECT {column} AS tie_value,count(*) n FROM rq_pairs GROUP BY {column}")
            con.execute(f"""CREATE TABLE {column}_ranks AS SELECT tie_value,
                coalesce(sum(n) OVER(ORDER BY tie_value ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),0)
                +(n+1)/2.0 rank_value FROM value_counts""")
            con.execute("DROP TABLE value_counts")
        con.execute("""CREATE TABLE ranked_x AS SELECT p.y,xr.rank_value rx
            FROM rq_pairs p JOIN x_ranks xr ON p.x=xr.tie_value""")
        if con.execute("SELECT count(*) FROM ranked_x").fetchone()[0]!=row["n"]:
            raise ValueError("RQ1 x rank join changed pair count")
        con.execute("DROP TABLE rq_pairs")
        con.execute("DROP TABLE x_ranks")
        ranked=con.execute("""SELECT count(*) n,corr(p.rx,yr.rank_value) spearman
            FROM ranked_x p JOIN y_ranks yr ON p.y=yr.tie_value""").df().iloc[0]
        if ranked["n"]!=row["n"]:raise ValueError("RQ1 global rank join changed pair count")
        row["spearman"]=ranked["spearman"]
        return row
    finally:
        for name in ("value_counts","x_ranks","y_ranks","rq_pairs","ranked_x"):
            con.execute(f"DROP TABLE IF EXISTS {name}")


def relationship(ctx):
    unit_info=time_unit_info(ctx.cfg)
    with ctx.disk_db() as con:
        ctx.view(con,"p","player_match")
        records=[]
        modes=["Overall"]+[r[0] for r in con.execute("SELECT DISTINCT team_size_mode FROM p ORDER BY 1").fetchall()]
        for mode in modes:
            where="split IN ('train','validation')"+("" if mode=="Overall" else f" AND team_size_mode={quote(mode)}")
            for target in ("player_survive_time","normalized_placement"):
                for feature in BASE+ABSOLUTE+PHASE:
                    validity="valid_survival" if target=="player_survive_time" else "valid_placement"
                    ctx.progress("global relationship pair",mode=mode,target=target,feature=feature)
                    query=f"""SELECT {ident(feature)} x,{ident(target)} y FROM p WHERE {where}
                        AND {validity} AND isfinite({ident(feature)}) AND isfinite({ident(target)})"""
                    row=pair_correlations(con,query)
                    row.update({"mode":mode,"target":target,"feature":feature,"analysis_scope":"train+validation",
                                "primary":not(target=="player_survive_time" and feature in PHASE),
                                "status":"ok" if row["n"]>=3 and np.isfinite(row["spearman"]) else "undefined",
                                "time_unit_status":unit_info["status"],"coefficient_unit":"dimensionless"})
                    records.append(row)
        result=pd.DataFrame(records)
        ctx.table("rq1_relationships",result)
        ctx.json("s06_execution",{"storage":"temporary_disk_database","pairs":len(records),
            "ranks":"global value counts and cumulative average ranks within each finite pair cohort",
            "pearson":"corr(x,y) on all finite pairs","spearman":"corr(global average rank x,global average rank y)",
            "duckdb_memory":ctx.cfg["runtime"]["duckdb_memory"],"threads":ctx.cfg["runtime"]["threads"],
            "sampling":False,"scope":"train+validation"})
        for target in ("player_survive_time","normalized_placement"):
            panel=result[result["target"].eq(target)&result["mode"].eq("Overall")]
            figure(ctx,"rq1_"+target,panel,"feature",["pearson","spearman"],"Quan hệ với "+target,
                   "Hệ số giữ dấu; N từng cặp và primary flag trong bảng; không suy nhân quả.",unit="Hệ số [-1,1]",analysis_scope="train+validation")


def profiles(con,ctx,development=True):
    ctx.view(con,"p","player_match")
    filt="AND split IN ('train','validation')" if development else ""
    means=",".join(f"avg({ident(source)}) {name},count({ident(source)}) {name}_n" for name,source in PROFILE_RAW.items())
    phase=",".join(f"avg({p}_kill_ratio) FILTER(WHERE player_kills>0 AND timing_status='phase_observed') avg_{p}_kill_ratio,count({p}_kill_ratio) FILTER(WHERE player_kills>0 AND timing_status='phase_observed') avg_{p}_kill_ratio_n" for p in ("early","mid","late"))
    return con.execute(f"""SELECT player_name,team_size_mode,count(*) games_played,{means},{phase},
        stddev_samp(player_kills) std_kills,count(player_kills) std_kills_n,
        stddev_samp(player_dmg) std_damage,count(player_dmg) std_damage_n,
        count(*) FILTER(WHERE player_kills>0) kill_active_matches,
        count(*) FILTER(WHERE player_kills+player_assists>0) support_active_matches,
        avg(CASE WHEN timing_status='confirmed_no_kill' THEN 0 WHEN timing_status='phase_observed' THEN CAST(early_kills>0 AS INTEGER) END) early_combat_match_ratio,
        count(*) FILTER(WHERE timing_status IN ('confirmed_no_kill','phase_observed')) early_combat_match_ratio_n,
        avg(player_survive_time) FILTER(WHERE valid_survival AND split IN ('train','validation')) avg_survival,
        count(player_survive_time) FILTER(WHERE valid_survival AND split IN ('train','validation')) survival_n,
        avg(normalized_placement) FILTER(WHERE split IN ('train','validation')) avg_placement,
        count(normalized_placement) FILTER(WHERE split IN ('train','validation')) placement_n
        FROM p WHERE player_name IS NOT NULL AND team_size_mode IN ('Solo','Duo','Squad') {filt} GROUP BY ALL""").df()


def bounded_profiles(con,ctx,development):
    ctx.view(con,"p","player_match")
    where="AND split IN ('train','validation')" if development else ""
    n=con.execute(f"SELECT count(*) FROM (SELECT player_name,team_size_mode FROM p WHERE player_name IS NOT NULL {where} GROUP BY ALL)").fetchone()[0]
    require_memory(ctx.cfg,n*len(PROFILE_FEATURES)*8*10,"RQ2 profiles/matrices")
    return profiles(con,ctx,development)


def kmeans(device,k,seed):
    if device=="cpu":
        return KMeans(n_clusters=k,n_init=10,random_state=seed)
    try:
        from cuml.cluster import KMeans as GPUKMeans
        import cupy
        if cupy.cuda.runtime.getDeviceCount()<1:
            raise RuntimeError("Không có CUDA device")
        return GPUKMeans(n_clusters=k,n_init=10,random_state=seed,output_type="numpy")
    except Exception as error:
        raise RuntimeError("GPU KMeans không sẵn sàng; không fallback CPU. Kiểm cuML/CUDA runtime") from error


def choose_clusters(diagnostic, overrides):
    """Only development behavior diagnostics; exact ties favor the smaller K."""
    chosen={}
    for mode, group in diagnostic.groupby("mode",sort=True):
        override=overrides.get(mode)
        if override is not None:
            if isinstance(override,bool) or not isinstance(override,int) or override not in group.k.tolist():
                raise ValueError(f"K ghi đè không có trong diagnostics: {mode}/{override}")
            chosen[mode]=override
            continue
        eligible=group[np.isfinite(group.silhouette)]
        if eligible.empty:
            raise ValueError(f"{mode}: không có silhouette hợp lệ; không tự chọn K tùy ý")
        chosen[mode]=int(eligible.sort_values(["silhouette","k"],ascending=[False,True]).iloc[0].k)
    return chosen


def stable_davies_bouldin(X, labels, batch_rows=50000):
    """Same DB formula, direct coordinate differences avoid norm/dot cancellation."""
    if isinstance(batch_rows,bool) or not isinstance(batch_rows,int) or batch_rows<1:
        raise ValueError("Davies-Bouldin batch_rows must be a positive integer")
    classes,inverse=np.unique(labels,return_inverse=True)
    if X.ndim!=2 or np.asarray(labels).ndim!=1 or len(X)!=len(inverse) or not 1<len(classes)<len(X):
        raise ValueError("Davies-Bouldin requires 2..n-1 nonempty clusters")
    counts=np.bincount(inverse,minlength=len(classes))
    sums=np.zeros((len(classes),X.shape[1]),dtype=np.float64)
    for start in range(0,len(X),batch_rows):
        batch=np.asarray(X[start:start+batch_rows],dtype=np.float64)
        if not np.isfinite(batch).all():raise ValueError("Nonfinite Davies-Bouldin input")
        np.add.at(sums,inverse[start:start+len(batch)],batch)
    centers=sums/counts[:,None]
    scatter=np.zeros(len(classes),dtype=np.float64)
    for start in range(0,len(X),batch_rows):
        group=inverse[start:start+batch_rows]
        distances=np.linalg.norm(X[start:start+batch_rows]-centers[group],axis=1)
        scatter+=np.bincount(group,weights=distances,minlength=len(classes))
    scatter/=counts
    distances=np.linalg.norm(centers[:,None,:]-centers[None,:,:],axis=2)
    if np.allclose(scatter,0) or np.allclose(distances,0):return 0.0
    distances[distances==0]=np.inf
    return float(np.max((scatter[:,None]+scatter[None,:])/distances,axis=1).mean())


def diagnostic_fit(payload):
    X=np.load(payload["matrix"],mmap_mode="r")
    k=payload["k"];seeds=payload["seeds"];seed=payload["seed"]
    compute=compute_metadata(payload["device"],X.nbytes)
    n_sample=min(len(X),payload["diagnostic_sample"])
    selected=np.sort(np.random.default_rng(seed).choice(len(X),n_sample,replace=False))
    first=None;aris=[]
    for s in seeds:
        labels=np.asarray(kmeans(payload["device"],k,s).fit(X).labels_)
        if first is None:first=labels
        else:aris.append(adjusted_rand_score(first[selected],labels[selected]))
        del labels
    fit=kmeans(payload["device"],k,seed).fit(X)
    unique=len(np.unique(first[selected]))
    row={"mode":payload["mode"],"k":k,"profiles":len(X),"inertia":float(fit.inertia_),
         "silhouette":silhouette_score(X[selected],first[selected]) if 1<unique<len(selected) else np.nan,
         "davies_bouldin":stable_davies_bouldin(X,first) if 1<len(np.unique(first))<len(X) else np.nan,
         "seed_ari":float(np.mean(aris)),
         "min_cluster_share":float(np.bincount(first).min()/len(X)),"diagnostic_n":n_sample,"seed":seed}
    return {"diagnostic":row,"compute":compute}


def cluster_fit(payload):
    frame=pd.read_parquet(payload["frame"])
    imputer=SimpleImputer(strategy="mean",add_indicator=True,keep_empty_features=True)
    scaler=StandardScaler()
    X=scaler.fit_transform(imputer.fit_transform(frame[PROFILE_FEATURES]))
    compute=compute_metadata(payload["device"],X.nbytes)
    fit=kmeans(payload["device"],payload["k"],payload["seed"]).fit(X)
    labels=np.asarray(fit.labels_)
    joblib.dump({"imputer":imputer,"scaler":scaler,"model":fit,"features":PROFILE_FEATURES},payload["model_path"])
    loaded=joblib.load(payload["model_path"])
    for start in range(0,len(frame),50000):
        batch=frame.iloc[start:start+50000][PROFILE_FEATURES]
        reloaded=np.asarray(loaded["model"].predict(loaded["scaler"].transform(loaded["imputer"].transform(batch))))
        if not np.array_equal(reloaded,labels[start:start+len(batch)]):raise ValueError("Clustering reload labels mismatch")
    return {"labels":labels,"compute":compute}


def clustering(ctx):
    with tempfile.TemporaryDirectory(prefix="pubg-clusters-",dir=ctx.temp) as folder:
        _clustering(ctx,Path(folder))


def _clustering(ctx,work):
    cfg=ctx.cfg["rq2"]
    unit_info=time_unit_info(ctx.cfg)
    automatic=cfg.get("decision_mode","manual")=="auto"
    with ctx.disk_db() as con:
        dev=bounded_profiles(con,ctx,True).sort_values(["team_size_mode","player_name"]).reset_index(drop=True)
    if dev.empty:
        raise ValueError("Không có development profiles")
    thresholds=[]
    for mode,g in dev.groupby("team_size_mode"):
        for threshold in cfg["threshold_candidates"]:
            kept=g[g.games_played>=threshold]
            thresholds.append({"mode":mode,"minimum_games":threshold,"total_profiles":len(g),"retained":len(kept),
                               "coverage":len(kept)/len(g),"median_games":kept.games_played.median(),
                               "mean_valid_phase_matches":kept.avg_early_kill_ratio_n.mean()})
    retention=pd.DataFrame(thresholds)
    ctx.table("profile_retention",retention)
    ctx.table("profile_coverage",dev.drop(columns=["player_name","avg_survival","avg_placement","survival_n","placement_n"]).describe().reset_index())
    figure(ctx,"profile_retention",retention.assign(group=retention["mode"]+"/"+retention["minimum_games"].astype(str)),"group",["retained"],"Giữ profile theo ngưỡng","Chọn từ coverage/reliability, không dùng survival/placement.",unit="Player-mode profiles")
    minimum=cfg["minimum_games"]
    if minimum is None and automatic:
        minimum=10
    if minimum is None or isinstance(minimum,bool) or not isinstance(minimum,int) or minimum<1:
        raise PendingDecision("S07: đọc profile_retention; chốt rq2.minimum_games trước K diagnostics")
    if set(dev.team_size_mode)-set(dev.loc[dev.games_played.ge(minimum),"team_size_mode"]):
        raise ValueError("Ngưỡng số trận loại hết một mode; chỉnh minimum_games rõ ràng, không tự bỏ mode")
    diagnostics=[]
    prepared=[]
    diagnostic_jobs=[]
    parallel=cfg["device"]=="cuda"
    for mode,g in dev[dev.games_played>=minimum].groupby("team_size_mode"):
        ctx.progress("K diagnostics",mode=mode,profiles=len(g))
        g=g.sort_values("player_name").reset_index(drop=True)
        if len(g)<3:
            raise ValueError(f"Mode {mode} cần >=3 eligible profiles, không tự bỏ mode")
        imputer=SimpleImputer(strategy="mean",add_indicator=True,keep_empty_features=True)
        scaler=StandardScaler()
        X=scaler.fit_transform(imputer.fit_transform(g[PROFILE_FEATURES]))
        matrix=work/(mode+".npy");np.save(matrix,X)
        prepared.append(mode)
        for k in cfg["candidate_k"]:
            ctx.progress("candidate K",mode=mode,k=k)
            if k>=len(X):
                continue
            payload={"mode":mode,"matrix":str(matrix),"k":k,"device":cfg["device"],
                     "seeds":cfg["stability_seeds"],"seed":ctx.cfg["runtime"]["seed"],"diagnostic_sample":cfg["diagnostic_sample"]}
            if parallel:
                diagnostic_jobs.append({"kind":"k_diagnostic","key":mode+"/K="+str(k),"matrix_bytes":X.nbytes,"payload":payload})
            else:
                result=diagnostic_fit(payload);diagnostics.append(result["diagnostic"])
                ctx.json("compute_rq2_"+mode,result["compute"])
        del X,g,imputer,scaler
    if parallel:
        executions=[]
        for job,path in run_jobs(ctx,"rq2",diagnostic_jobs):
            result=joblib.load(path);diagnostics.append(result["diagnostic"])
            executions.append({"job":job["key"],**result["gpu_execution"]})
        ctx.json("gpu_rq2_diagnostics",{"executions":executions,"gpu_ids":cfg["gpu_ids"]})
    diagnostic=pd.DataFrame(diagnostics)
    if diagnostic.empty:
        raise ValueError("Candidate K không phù hợp profile count")
    diag_path=ctx.table("k_diagnostics",diagnostic)
    receipt=fingerprint({"table":digest(diag_path),"profiles":frame_fingerprint(dev[PROFILE_FEATURES+["player_name","team_size_mode","games_played"]]),
                         "minimum":minimum,"device":cfg["device"],"gpu_ids":cfg.get("gpu_ids",[0]),"seeds":cfg["stability_seeds"]})
    ctx.json("k_diagnostic_receipt",{"diagnostic_hash":receipt,"outcomes_used":False,"population":"development profiles","sample_rule":"uniform without replacement, fixed seed; full fit"})
    figure(ctx,"k_diagnostics",diagnostic.assign(group=diagnostic["mode"]+"/K="+diagnostic.k.astype(str)),"group",["silhouette","seed_ari"],"Chất lượng và ổn định cụm","K chọn bằng hành vi và diagnostics; outcome không tham gia.",unit="Score")
    if automatic:
        selected_clusters=choose_clusters(diagnostic,cfg["clusters"])
        decision_reason="Auto policy approved 2026-10-17: maximum finite development silhouette; exact ties smaller K; explicit per-mode overrides take precedence. Stability/cluster sizes reported, not optimized using outcomes."
    elif cfg.get("diagnostic_hash")!=receipt or not cfg.get("decision_reason"):
        raise PendingDecision("S07: đọc K diagnostics, chốt clusters/decision_reason và diagnostic_hash từ k_diagnostic_receipt.json")
    else:
        selected_clusters=cfg["clusters"]
        decision_reason=cfg["decision_reason"]
    # Lock selection before the full descriptive fit or outcome interpretation.
    ctx.json("cluster_selection",{"diagnostic_hash":receipt,"minimum_games":minimum,"clusters":selected_clusters,
                                 "reason":decision_reason,"decision_mode":cfg.get("decision_mode","manual"),"outcomes_used":False})
    ctx.progress("RQ2 selection locked before outcome interpretation",minimum_games=minimum,clusters=selected_clusters)
    del dev
    with ctx.disk_db() as con:
        full=bounded_profiles(con,ctx,False)
    centers,sizes,outcomes,assignments=[],[],[],[]
    full_jobs=[];full_frames={}
    for mode in prepared:
        ctx.progress("full descriptive fit",mode=mode)
        k=selected_clusters.get(mode)
        if k not in diagnostic.loc[diagnostic["mode"].eq(mode),"k"].tolist():
            raise PendingDecision(f"Chốt K hợp lệ cho {mode}")
        g=full[full.team_size_mode.eq(mode)&full.games_played.ge(minimum)].sort_values("player_name").copy()
        frame=work/(mode+".parquet");g[PROFILE_FEATURES].to_parquet(frame,index=False)
        payload={"frame":str(frame),"model_path":str(work/(mode+".joblib")),"device":cfg["device"],
                 "k":int(k),"seed":ctx.cfg["runtime"]["seed"]}
        full_jobs.append({"kind":"k_full","key":mode,"matrix_bytes":len(g)*len(PROFILE_FEATURES)*16,"payload":payload})
        metadata=work/(mode+".full.parquet");g.to_parquet(metadata,index=False)
        full_frames[mode]=metadata
        del g
    del full
    def full_results():
        if parallel:
            for job,path in run_jobs(ctx,"rq2",full_jobs):yield job,joblib.load(path)
        else:
            for job in full_jobs:yield job,cluster_fit(job["payload"])
    executions=[]
    for job,result in full_results():
        mode=job["key"];g=pd.read_parquet(full_frames.pop(mode))
        g["cluster"]=result["labels"]
        target=ctx.path("models/kmeans_"+mode+".joblib")
        publish(Path(job["payload"]["model_path"]),target);ctx.record(target)
        ctx.json("compute_rq2_"+mode,result["compute"])
        if parallel:executions.append({"mode":mode,**result["gpu_execution"]})
        for c,h in g.groupby("cluster"):
            center={"mode":mode,"cluster":c,**h[PROFILE_FEATURES].mean().to_dict()}
            centers.append(center)
            sizes.append({"mode":mode,"cluster":c,"profiles":len(h),"share":len(h)/len(g)})
            outcomes.append({"mode":mode,"cluster":c,"avg_survival":h.avg_survival.mean(),"avg_placement":h.avg_placement.mean(),
                             "time_unit_status":unit_info["status"],"survival_unit":unit_info["label"],
                             "valid_survival_profiles":h.avg_survival.count(),"valid_placement_profiles":h.avg_placement.count(),
                             "scope":"locked full descriptive labels; outcomes train+validation only, final-test not exposed"})
        assignments.append(g[["player_name","team_size_mode","cluster"]])
        mean=g[PROFILE_FEATURES].mean();std=g[PROFILE_FEATURES].std(ddof=0).replace(0,np.nan)
        profile=g.groupby("cluster")[PROFILE_FEATURES].mean().sub(mean).div(std).reset_index()
        figure(ctx,"centers_"+mode,profile,"cluster",PROFILE_FEATURES,"Hành vi chuẩn hóa - "+mode,
               "Màu thể hiện lệch so với profile mean, không xếp hạng tốt/xấu; cluster ID chỉ trong mode. Ô trắng là variance0/undefined.",kind="heatmap",unit="Độ lệch chuẩn",analysis_scope="full descriptive",population_n=len(g))
    ctx.table("cluster_centers",pd.DataFrame(centers));ctx.table("cluster_sizes",pd.DataFrame(sizes))
    ctx.table("cluster_outcomes",pd.DataFrame(outcomes));ctx.table("cluster_assignments",pd.concat(assignments,ignore_index=True))
    size_frame=pd.DataFrame(sizes).assign(group=lambda f:f["mode"]+"/"+f.cluster.astype(str))
    figure(ctx,"cluster_sizes",size_frame,"group",["profiles"],"Quy mô cụm từng mode","Mẫu số và share riêng từng mode.",unit="Player-mode profiles")
    outcome_frame=pd.DataFrame(outcomes).assign(group=lambda f:f["mode"]+"/"+f.cluster.astype(str))
    figure(ctx,"cluster_outcomes",outcome_frame,"group",["avg_placement"],"Outcome sau khóa phân cụm","Outcome chỉ train+validation để không mở test trước G4; không dùng chọn K.",unit="Placement [0,1]",analysis_scope="development outcomes, locked full labels")
    ctx.json("clustering",{"modes":list(prepared),"device":cfg["device"],"gpu_ids":cfg.get("gpu_ids",[0]),
                           "gpu_executions":executions,"features":PROFILE_FEATURES,
                           "diagnostic_hash":receipt,"minimum_games":minimum,"clusters":selected_clusters,
                           "decision_reason":decision_reason,"outcome_used_for_selection":False,"scope":"full descriptive","time_unit":unit_info})
    ctx.json("s07_execution",{"profile_sql":"temporary_disk_database; full profile collection still RAM-guarded",
        "diagnostic_labels":"first seed full; other seeds compared on registered diagnostic sample",
        "davies_bouldin":"all rows, direct coordinate distances, float64, bounded batches",
        "full_mode_metadata":"temporary Parquet, one result mode loaded at a time",
        "fit":"unchanged full KMeans per mode; not partial_fit or partition fits","sampling_fit":False})
