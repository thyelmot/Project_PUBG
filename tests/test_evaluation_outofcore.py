import tempfile
import unittest
import os
import subprocess
import sys
from decimal import Decimal,localcontext
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from src import evaluation,modeling
from src.io import Context,digest,validate_parquet
from test_data_features import fixture,ROOT
import reference_modeling_v58 as reference


# Declared before comparison, not widened after observing a difference.
RTOL,ATOL=1e-9,1e-10


def prediction_fixture(n=100007):
    i=np.arange(n)
    frame=pd.DataFrame({"row_id":[f"r{k:09}" for k in i],"match_id":["trận"+str(k//9) for k in i],
        "team_id":["đội"+str((k%9)//3) for k in i],"team_size_mode":np.take(["Solo","Duo","Squad"],i%3),
        "split":"test","target":"normalized_placement","actual":((i%9)//3).astype(float)/2,
        "predicted":((i%9)//3)/2+np.cos(i)*.2,"experiment":"p2_linear","run_id":"synthetic"})
    frame=frame.loc[i%11!=0].sample(frac=1,random_state=17).reset_index(drop=True)
    frame["residual"]=frame.actual-frame.predicted
    return frame


def synthetic_prediction_files(ctx,rows=1200000):
    with ctx.disk_db() as con:
        for name,offset in (("left",.125),("right",.0625)):
            ctx.parquet(con,f"""SELECT 'r'||CAST(i AS VARCHAR) AS row_id,'m'||CAST(i//8 AS VARCHAR) AS match_id,
                't'||CAST(i%4 AS VARCHAR) AS team_id,'Squad' AS team_size_mode,'test' AS split,
                'normalized_placement' AS target,(i%4)::DOUBLE/3 AS actual,(i%4)::DOUBLE/3+{offset} AS predicted,
                -{offset}::DOUBLE AS residual FROM range({rows}) t(i)""",name)
    return [ctx.data/(name+".parquet") for name in ("left","right")]


def decimal_metrics(y,pred,weights=None):
    with localcontext() as context:
        context.prec=60
        y=list(map(Decimal.from_float,map(float,y)));p=list(map(Decimal.from_float,map(float,pred)))
        w=[Decimal(1)]*len(y) if weights is None else list(map(Decimal.from_float,map(float,weights)))
        total=sum(w);mean=sum(a*b for a,b in zip(w,y))/total
        sse=sum(a*(b-c)**2 for a,b,c in zip(w,y,p));sst=sum(a*(b-mean)**2 for a,b in zip(w,y))
        return [float(sum(a*abs(b-c) for a,b,c in zip(w,y,p))/total),float((sse/total).sqrt()),float(1-sse/sst) if sst else np.nan]


class EvaluationOutOfCore(unittest.TestCase):
    def test_two_disk_databases_keep_spill_files_isolated(self):
        env={**os.environ,"PYTHONUTF8":"1","OMP_NUM_THREADS":"1","OPENBLAS_NUM_THREADS":"1","MKL_NUM_THREADS":"1"}
        result=subprocess.run([sys.executable,"-B","-u",str(ROOT/"tests/probe_sql_spill.py")],
                              cwd=ROOT,env=env,capture_output=True,text=True,encoding="utf-8",timeout=120)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn("PASSED 1000000 499999500000",result.stdout)

    def test_parquet_reader_closes_when_decoding_fails(self):
        with tempfile.TemporaryDirectory(prefix="pubg-d5-reader-close-") as folder:
            path=Path(folder)/"pred.parquet";prediction_fixture(20).to_parquet(path,index=False)
            file=pq.ParquetFile(path)
            with patch("src.io.pq.ParquetFile",return_value=file),patch.object(file,"iter_batches",side_effect=OSError("synthetic decode error")):
                with self.assertRaisesRegex(OSError,"decode error"):validate_parquet(path)
            self.assertTrue(file.closed)

    def test_global_hierarchical_metrics_match_reference_and_reject_bad_rows(self):
        with tempfile.TemporaryDirectory(prefix="pubg-d5-metrics-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            frame=prediction_fixture();path=root/"pred.parquet";frame.to_parquet(path,index=False,row_group_size=4096)
            expected=reference.hierarchical(frame,"normalized_placement")
            with patch("pandas.read_parquet",side_effect=AssertionError("No full prediction collection")):
                actual=evaluation.prediction_metrics(ctx,path,"normalized_placement")
            pd.testing.assert_frame_equal(pd.DataFrame(actual),pd.DataFrame(expected),rtol=RTOL,atol=ATOL)
            for mutation in ("duplicate","null_key","nan","inf","empty","team_null","team_conflict"):
                bad=frame.iloc[:20].copy()
                if mutation=="duplicate":bad.loc[1,"row_id"]=bad.loc[0,"row_id"]
                elif mutation=="null_key":bad.loc[0,"match_id"]=None
                elif mutation=="nan":bad.loc[0,"actual"]=np.nan
                elif mutation=="inf":bad.loc[0,"predicted"]=np.inf
                elif mutation=="empty":bad=bad.iloc[:0]
                elif mutation=="team_null":bad.loc[0,"team_id"]=None
                else:
                    bad.loc[1,["match_id","team_id"]]=bad.loc[0,["match_id","team_id"]].values
                    bad.loc[1,"actual"]=bad.loc[0,"actual"]+.1
                bad.to_parquet(path,index=False)
                with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                    evaluation.prediction_metrics(ctx,path,"normalized_placement")
            self.assertFalse(list(ctx.temp.glob("pubg-sql-*")))

    def test_centered_metrics_large_offset_and_constant_match_decimal(self):
        with tempfile.TemporaryDirectory(prefix="pubg-d5-numeric-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            frame=prediction_fixture(40)
            frame["actual"]=1e12+np.arange(len(frame))*.125
            frame["predicted"]=frame.actual+np.take([-.25,.125,.5],np.arange(len(frame))%3)
            path=root/"pred.parquet";frame.to_parquet(path,index=False)
            actual=evaluation.prediction_metrics(ctx,path,"player_survive_time")
            for row,weights in zip(actual,(None,1/frame.groupby("match_id").actual.transform("size"))):
                np.testing.assert_allclose([row[c] for c in ("mae","rmse","r2")],decimal_metrics(frame.actual,frame.predicted,weights),rtol=RTOL,atol=ATOL)
            frame["actual"]=.1;frame.to_parquet(path,index=False)
            for row in evaluation.prediction_metrics(ctx,path,"player_survive_time"):
                self.assertTrue(np.isnan(row["r2"]));self.assertTrue(row["r2_reason"])

    def test_full_pairing_and_bootstrap_match_rng_and_multiplicity(self):
        with tempfile.TemporaryDirectory(prefix="pubg-d5-paired-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            a=prediction_fixture(507);b=a.copy();b["predicted"]+=.07*np.sin(np.arange(len(b)))
            paths=[root/"a.parquet",root/"b.parquet"]
            a.to_parquet(paths[0],index=False);b.iloc[::-1].to_parquet(paths[1],index=False)
            expected=pd.DataFrame(reference.paired_bootstrap(a,b,40,73))
            with ctx.disk_db() as con:
                evaluation.paired_view(con,*paths)
                actual=pd.DataFrame(evaluation.bootstrap_sql(ctx,con,40,73))
            pd.testing.assert_frame_equal(actual,expected,rtol=RTOL,atol=ATOL)
            for mutation in ("missing","duplicate","extra_key","match_id","team_id","split","target","actual"):
                bad=b.copy()
                if mutation=="missing":bad=bad.iloc[1:]
                elif mutation=="duplicate":bad.loc[1,"row_id"]=bad.loc[0,"row_id"]
                elif mutation=="extra_key":bad.loc[0,"row_id"]="not-in-reference"
                elif mutation=="actual":bad.loc[0,"actual"]+=.1
                else:bad.loc[0,mutation]="different"
                bad.to_parquet(paths[1],index=False)
                with self.subTest(mutation=mutation),ctx.disk_db() as con,self.assertRaises(ValueError):
                    evaluation.paired_view(con,*paths)
            for frame in (a,b):frame["actual"]=.1
            a.to_parquet(paths[0],index=False);b.to_parquet(paths[1],index=False)
            with ctx.disk_db() as con:
                evaluation.paired_view(con,*paths)
                r2=next(r for r in evaluation.bootstrap_sql(ctx,con,40,73) if r["metric"]=="r2")
            self.assertEqual(r2["valid_replicates"],0);self.assertTrue(np.isnan(r2["lower"]))

    def test_error_bins_histogram_and_exact_plot_sample_preserve_reference(self):
        with tempfile.TemporaryDirectory(prefix="pubg-d5-plot-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            for n in (1,1501,100007):
                frame=prediction_fixture(n+1)
                if frame.empty:frame=prediction_fixture(3)
                frame.loc[frame.index[::17],"team_size_mode"]=None
                path=root/"pred.parquet";frame.to_parquet(path,index=False,row_group_size=4096)
                expected=frame.sample(min(1500,len(frame)),random_state=42)[["actual","predicted","residual"]].reset_index(drop=True)
                with patch("pandas.read_parquet",side_effect=AssertionError("No full prediction collection")):
                    sample=evaluation.plot_sample(ctx,path,len(frame),42)
                pd.testing.assert_frame_equal(sample,expected,check_exact=True)
                edges=[0.,.3333333333333333,.5,1.]
                expected_slices=[]
                for mode,g in frame.groupby("team_size_mode"):
                    expected_slices.append({"slice":"mode","group":mode,"matches":g.match_id.nunique(),**reference.metrics(g.actual,g.predicted)})
                bins=np.unique([-np.inf]+edges[1:-1]+[np.inf])
                for region,g in frame.groupby(pd.cut(frame.actual,bins,include_lowest=True),observed=True):
                    expected_slices.append({"slice":"train_target_region","group":str(region),"matches":g.match_id.nunique(),**reference.metrics(g.actual,g.predicted)})
                with ctx.disk_db() as con:
                    evaluation.prediction_view(con,"p",path)
                    actual=pd.DataFrame(evaluation.error_slices(con,"p",edges))
                    histogram=evaluation.residual_histogram(con,"p")
                pd.testing.assert_frame_equal(actual,pd.DataFrame(expected_slices),rtol=RTOL,atol=ATOL)
                counts=pd.cut(frame.residual,20).value_counts(sort=False)
                pd.testing.assert_frame_equal(histogram,pd.DataFrame({"bin":counts.index.astype(str),"n":counts.values}),check_exact=True)

    def test_sampling_and_bootstrap_have_explicit_ram_guards(self):
        with tempfile.TemporaryDirectory(prefix="pubg-d5-guards-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            frame=prediction_fixture(50);path=root/"pred.parquet";frame.to_parquet(path,index=False)
            ctx.cfg["runtime"]["max_matrix_gb"]=1e-12
            with self.assertRaisesRegex(MemoryError,"plot sampling"):
                evaluation.plot_sample(ctx,path,len(frame),42)
            with ctx.disk_db() as con:
                evaluation.paired_view(con,path,path)
                with self.assertRaisesRegex(MemoryError,"bootstrap states"):
                    evaluation.bootstrap_sql(ctx,con,40,42)

    def test_1200000_rows_global_metrics_and_pairs_at_128mib(self):
        with tempfile.TemporaryDirectory(prefix="pubg-d5-128mib-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            ctx.cfg["runtime"]["duckdb_memory"]="128MiB"
            paths=synthetic_prediction_files(ctx)
            with patch("pandas.read_parquet",side_effect=AssertionError("No full prediction frame")):
                rows=evaluation.prediction_metrics(ctx,paths[0],"normalized_placement")
                with ctx.disk_db() as con:
                    evaluation.paired_view(con,*paths)
                    ci=evaluation.bootstrap_sql(ctx,con,20,42)
            self.assertEqual([r["n"] for r in rows],[1200000,1200000,600000])
            for row in rows:
                np.testing.assert_allclose([row[c] for c in ("mae","rmse","r2")],[.125,.125,.8875],rtol=RTOL,atol=ATOL)
            for row in ci:
                expected=.084375 if row["metric"]=="r2" else -.0625
                np.testing.assert_allclose([row["lower"],row["upper"]],[expected,expected],rtol=RTOL,atol=ATOL)
            self.assertFalse(list(ctx.temp.glob("pubg-sql-*")))


if __name__=="__main__":unittest.main()
