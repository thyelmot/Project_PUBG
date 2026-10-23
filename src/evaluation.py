"""Global prediction metrics and paired checks on an owned disk database."""
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .io import ident, quote, require_memory
from .storage import prediction_sql, prediction_batches


def bootstrap_memory_bytes(matches,replicates):
    return matches*8*24+replicates*3*8


def plot_memory_bytes(rows):
    return rows*8+50000*3*8*4


def prediction_view(con,name,path):
    con.execute(f"CREATE OR REPLACE VIEW {ident(name)} AS "+prediction_sql(path))
    n,bad=con.execute(f"""SELECT count(*),count(*) FILTER(WHERE row_id IS NULL OR match_id IS NULL
        OR actual IS NULL OR predicted IS NULL OR NOT isfinite(actual) OR NOT isfinite(predicted)) FROM {ident(name)}""").fetchone()
    if not n or bad:raise ValueError("Prediction metrics require nonempty finite rows and nonnull identities")
    if con.execute(f"SELECT count(*) FROM (SELECT row_id FROM {ident(name)} GROUP BY row_id HAVING count(*)>1)").fetchone()[0]:
        raise ValueError("Duplicate row IDs in predictions")
    return n


def metric_sql(con,name,weight="1.0"):
    """Two global passes; center before summation, never average batch RMSE/R2."""
    table=ident(name)
    n,anchor,low,high=con.execute(f"SELECT count(*),min(actual),min(actual),max(actual) FROM {table}").fetchone()
    if not n:raise ValueError("Metrics require nonempty input")
    total,center=con.execute(f"SELECT fsum({weight}),fsum(({weight})*(actual-?))/fsum({weight}) FROM {table}",[anchor]).fetchone()
    absolute,sse,sst=con.execute(f"""SELECT fsum(({weight})*abs(actual-predicted)),
        fsum(({weight})*pow(actual-predicted,2)),fsum(({weight})*pow((actual-?)-?,2)) FROM {table}""",[anchor,center]).fetchone()
    if not np.isfinite([total,center,absolute,sse,sst]).all() or total<=0 or min(sse,sst)<0:
        raise ValueError("Nonfinite/invalid metric accumulation")
    defined=n>1 and low!=high and sst>0
    return {"n":n,"mae":float(absolute/total),"rmse":float(np.sqrt(sse/total)),
            "r2":float(1-sse/sst) if defined else np.nan,
            "r2_reason":"" if defined else "constant target or insufficient n"}


def hierarchical_sql(con,name,target):
    table=ident(name)
    rows=[{"aggregation":"micro",**metric_sql(con,name)}]
    con.execute(f"CREATE OR REPLACE TABLE metric_matches AS SELECT match_id,count(*) n FROM {table} GROUP BY match_id")
    con.execute(f"CREATE OR REPLACE TABLE metric_weighted AS SELECT p.actual,p.predicted,1.0/m.n w FROM {table} p JOIN metric_matches m USING(match_id)")
    rows.append({"aggregation":"match_aware",**metric_sql(con,"metric_weighted","w")})
    con.execute("DROP TABLE metric_weighted");con.execute("DROP TABLE metric_matches")
    if target=="normalized_placement":
        if con.execute(f"SELECT count(*) FROM {table} WHERE team_id IS NULL").fetchone()[0]:
            raise ValueError("Team placement target conflict")
        con.execute(f"""CREATE OR REPLACE TABLE metric_teams AS SELECT match_id,team_id,min(actual) actual,
            max(actual) maximum,avg(predicted) predicted FROM {table} GROUP BY match_id,team_id""")
        if con.execute("SELECT count(*) FROM metric_teams WHERE actual!=maximum").fetchone()[0]:
            raise ValueError("Team placement target conflict")
        rows.append({"aggregation":"team_aware",**metric_sql(con,"metric_teams")})
        con.execute("DROP TABLE metric_teams")
    return rows


def prediction_metrics(ctx,path,target):
    with ctx.disk_db() as con:
        prediction_view(con,"metric_input",path)
        return hierarchical_sql(con,"metric_input",target)


def paired_view(con,left,right):
    a=prediction_view(con,"pair_a",left);b=prediction_view(con,"pair_b",right)
    if a!=b:raise ValueError("Missing/extra row IDs in paired comparison")
    con.execute("""CREATE TABLE paired AS SELECT a.row_id,a.match_id,a.team_id,a.split,a.target,a.actual,
        a.predicted reference,b.predicted candidate,
        b.match_id b_match,b.team_id b_team,b.split b_split,b.target b_target,b.actual b_actual
        FROM pair_a a JOIN pair_b b USING(row_id)""")
    if con.execute("SELECT count(*) FROM paired").fetchone()[0]!=a:
        raise ValueError("Missing/extra row IDs in paired comparison")
    for a,b in (("match_id","b_match"),("team_id","b_team"),("split","b_split"),("target","b_target"),("actual","b_actual")):
        if con.execute(f"SELECT count(*) FROM paired WHERE {ident(a)} IS DISTINCT FROM {ident(b)}").fetchone()[0]:
            raise ValueError("Paired identity/target mismatch: "+a)
    for name,column in (("pair_left","reference"),("pair_right","candidate")):
        con.execute(f"CREATE VIEW {name} AS SELECT row_id,match_id,team_id,split,target,actual,{column} predicted FROM paired")


def bootstrap_sql(ctx,con,replicates,seed):
    """One numeric state per match; the registered RNG/multiplicity is unchanged."""
    anchor=con.execute("SELECT min(actual) FROM paired").fetchone()[0]
    con.execute("""CREATE TABLE boot_means AS SELECT match_id,count(*) n,avg(actual-?) mean_delta
        FROM paired GROUP BY match_id""",[anchor])
    con.execute("""CREATE TABLE boot_state AS SELECT p.match_id,m.n,m.mean_delta,
        fsum(pow((p.actual-?)-m.mean_delta,2)) within_sst,
        fsum(abs(p.actual-p.reference)) abs_a,fsum(abs(p.actual-p.candidate)) abs_b,
        fsum(pow(p.actual-p.reference,2)) sq_a,fsum(pow(p.actual-p.candidate,2)) sq_b
        FROM paired p JOIN boot_means m USING(match_id) GROUP BY p.match_id,m.n,m.mean_delta""",[anchor])
    count=con.execute("SELECT count(*) FROM boot_state").fetchone()[0]
    require_memory(ctx.cfg,bootstrap_memory_bytes(count,replicates),"S09 match bootstrap states and RNG workspace")
    states=con.execute("SELECT n,mean_delta,within_sst,abs_a,abs_b,sq_a,sq_b FROM boot_state ORDER BY match_id").fetchnumpy()
    n,mean,within,abs_a,abs_b,sq_a,sq_b=[states[c] for c in ("n","mean_delta","within_sst","abs_a","abs_b","sq_a","sq_b")]
    rng=np.random.default_rng(seed);deltas=[]
    for _ in range(replicates):
        counts=np.bincount(rng.integers(0,count,count),minlength=count)
        N=np.dot(counts,n);average=np.dot(counts,n*mean)/N
        sst=np.dot(counts,within+n*(mean-average)**2)
        chosen=counts>0
        defined=np.any(within[chosen]>0) or np.min(mean[chosen])!=np.max(mean[chosen])
        sa=np.dot(counts,sq_a);sb=np.dot(counts,sq_b)
        deltas.append([np.dot(counts,abs_b-abs_a)/N,np.sqrt(sb/N)-np.sqrt(sa/N),
                       (sa-sb)/sst if defined and sst>0 else np.nan])
    con.execute("DROP TABLE boot_state");con.execute("DROP TABLE boot_means")
    array=np.asarray(deltas)
    return [{"metric":name,"lower":float(np.nanquantile(array[:,i],.025)) if np.isfinite(array[:,i]).any() else np.nan,
             "upper":float(np.nanquantile(array[:,i],.975)) if np.isfinite(array[:,i]).any() else np.nan,
             "valid_replicates":int(np.isfinite(array[:,i]).sum()),"replicates":replicates,"seed":seed,"level":"match"}
            for i,name in enumerate(("mae","rmse","r2"))]


def distinct_matches(con,name):
    return con.execute(f"SELECT count(*) FROM (SELECT match_id FROM {ident(name)} WHERE match_id IS NOT NULL GROUP BY match_id)").fetchone()[0]


def error_slices(con,name,edges):
    result=[]
    modes=con.execute(f"SELECT team_size_mode FROM {ident(name)} WHERE team_size_mode IS NOT NULL GROUP BY team_size_mode ORDER BY team_size_mode").fetchall()
    for mode, in modes:
        con.execute(f"CREATE OR REPLACE VIEW error_slice AS SELECT * FROM {ident(name)} WHERE team_size_mode={quote(mode)}")
        result.append({"slice":"mode","group":mode,"matches":distinct_matches(con,"error_slice"),**metric_sql(con,"error_slice")})
    bins=np.unique([-np.inf]+edges[1:-1]+[np.inf])
    categories=pd.cut(np.array([0.]),bins,include_lowest=True).categories
    for lower,upper,region in zip(bins[:-1],bins[1:],categories):
        condition=f"actual>{quote(float(lower))}::DOUBLE AND actual<={quote(float(upper))}::DOUBLE"
        con.execute(f"CREATE OR REPLACE VIEW error_slice AS SELECT * FROM {ident(name)} WHERE {condition}")
        if con.execute("SELECT count(*) FROM error_slice").fetchone()[0]:
            result.append({"slice":"train_target_region","group":str(region),"matches":distinct_matches(con,"error_slice"),**metric_sql(con,"error_slice")})
    return result


def residual_histogram(con,name):
    lo,hi=con.execute(f"SELECT min(residual),max(residual) FROM {ident(name)}").fetchone()
    labels,bins=pd.cut(np.array([lo,hi]),20,retbins=True)
    counts=con.execute("SELECT "+",".join(f"count(*) FILTER(WHERE residual>{quote(float(a))}::DOUBLE AND residual<={quote(float(b))}::DOUBLE)" for a,b in zip(bins[:-1],bins[1:]))+f" FROM {ident(name)}").fetchone()
    return pd.DataFrame({"bin":labels.categories.astype(str),"n":counts})


def plot_sample(ctx,path,n,seed):
    # Preserve pandas/RandomState sampling exactly; only this index workspace is O(N).
    require_memory(ctx.cfg,plot_memory_bytes(n),"S09 exact plot sampling indices and batch")
    selected=np.random.RandomState(seed).choice(n,size=min(1500,n),replace=False)
    order=np.argsort(selected);indices=selected[order]
    values=np.empty((len(selected),3));offset=0
    from contextlib import closing
    with closing(prediction_batches(path,["actual","predicted","residual"])) as batches:
        for batch in batches:
            stop=offset+batch.num_rows
            lo,hi=np.searchsorted(indices,[offset,stop])
            if hi>lo:values[order[lo:hi]]=batch.to_pandas().to_numpy()[indices[lo:hi]-offset]
            offset=stop
    if offset!=n:raise ValueError("Prediction rows changed during plot sampling")
    return pd.DataFrame(values,columns=["actual","predicted","residual"])
