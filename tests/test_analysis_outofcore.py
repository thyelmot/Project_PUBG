import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src import analysis
from src.features import BASE, ABSOLUTE, PHASE
from src.io import Context, digest
from test_data_features import fixture, write_config, run_features
import reference_analysis_v57 as reference


# Fixed before comparison; no approximate statistics or tolerance widening.
RTOL, ATOL = 1e-10, 1e-12


def synthetic_analysis(ctx, n=180):
    i=np.arange(n)
    frame=pd.DataFrame({c:((i*(k+1))%37).astype(float)/3
                        for k,c in enumerate(BASE+ABSOLUTE+PHASE+["player_survive_time","normalized_placement"])})
    for k,c in enumerate(frame):frame.loc[i%(k+3)==0,c]=np.nan
    frame["split"]=np.take(["train","validation","test"],i%3)
    frame["team_size_mode"]=np.take(["Solo","Duo","Squad","Other"],i%4)
    frame["valid_survival"]=i%7!=0
    frame["valid_placement"]=i%11!=0
    # A test-only mode and extreme test outcomes must not enter development statistics.
    frame.loc[frame.split.eq("test"),"team_size_mode"]="TestOnly"
    frame.loc[frame.split.eq("test"),"player_survive_time"]=1e12
    ctx.data.mkdir(parents=True,exist_ok=True)
    frame.to_parquet(ctx.data/"player_match.parquet",index=False)
    return frame


class AnalysisOutOfCore(unittest.TestCase):
    def assert_table(self,actual,expected):
        self.assertEqual(list(actual.columns),list(expected.columns))
        keys=[c for c in ("mode","target","feature","team_size_mode","bin") if c in actual]
        if keys:
            actual=actual.sort_values(keys,na_position="first").reset_index(drop=True)
            expected=expected.sort_values(keys,na_position="first").reset_index(drop=True)
        pd.testing.assert_frame_equal(actual.isna(),expected.isna(),check_exact=True)
        exact=[c for c in actual if not pd.api.types.is_float_dtype(actual[c])]
        pd.testing.assert_frame_equal(actual[exact],expected[exact],check_exact=True)
        pd.testing.assert_frame_equal(actual,expected,rtol=RTOL,atol=ATOL)

    def test_all_scientific_tables_and_plot_sources_match_v57(self):
        with tempfile.TemporaryDirectory(prefix="pubg-analysis-parity-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development",progress=lambda _:None)
            synthetic_analysis(ctx)
            source=digest(ctx.data/"player_match.parquet")
            reference.eda(ctx);reference.relationship(ctx)
            expected={p.name:pd.read_csv(p) for p in ctx.path("tables").glob("*.csv")}
            analysis.eda(ctx);analysis.relationship(ctx)
            for name,table in expected.items():
                with self.subTest(table=name):self.assert_table(pd.read_csv(ctx.path("tables/"+name)),table)
            self.assertEqual(source,digest(ctx.data/"player_match.parquet"))
            self.assertFalse(list(ctx.temp.glob("pubg-sql-*")))
            stats=pd.read_csv(ctx.path("tables/eda_statistics.csv")).set_index("feature")
            self.assertLess(stats.loc["player_survive_time","n"],120)
            self.assertLess(stats.loc["player_survive_time","max"],1e12)
            relations=pd.read_csv(ctx.path("tables/rq1_relationships.csv"))
            self.assertTrue(relations.loc[relations["mode"].eq("TestOnly"),"n"].eq(0).all())

    def test_exact_quantiles_empty_singleton_ties_integer_and_nonfinite(self):
        with tempfile.TemporaryDirectory(prefix="pubg-quantile-parity-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development",progress=lambda _:None)
            samples=[[],[4.],[1.,9.],[0.,1.,2.],[0.,0.,1.,1.,8.],
                     [None,-np.inf,-3.,1.,np.inf],[1e100,1e101,1e102,1e103]]
            samples += [list(np.random.default_rng(42).normal(size=n)) for n in (7,16,101,5001)]
            with ctx.disk_db() as con:
                for values in samples:
                    frame=pd.DataFrame({"value":pd.Series(values,dtype="float64")})
                    con.register("input_frame",frame)
                    con.execute("CREATE OR REPLACE VIEW dev AS SELECT * FROM input_frame")
                    expected=con.execute("SELECT median(value) median,quantile_cont(value,.25) q25,quantile_cont(value,.75) q75 FROM dev").df()
                    actual=analysis.column_quantiles(con,"value",int(frame.value.notna().sum()))
                    pd.testing.assert_frame_equal(actual,expected,check_exact=True)
                con.execute('CREATE OR REPLACE VIEW dev AS SELECT i::BIGINT AS "value" FROM range(10) t(i)')
                expected=con.execute("SELECT median(value) median,quantile_cont(value,.25) q25,quantile_cont(value,.75) q75 FROM dev").df()
                pd.testing.assert_frame_equal(analysis.column_quantiles(con,"value",10),expected,check_exact=True)
                self.assertFalse(con.execute("SELECT table_name FROM information_schema.tables WHERE table_name='eda_ordered'").fetchall())

    def test_global_pair_ranks_match_original_windows_and_scipy(self):
        with tempfile.TemporaryDirectory(prefix="pubg-rank-parity-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development",progress=lambda _:None)
            rng=np.random.default_rng(42)
            frames=[pd.DataFrame({"x":rng.integers(0,7,10001).astype(float),"y":rng.integers(0,13,10001).astype(float)}),
                    pd.DataFrame({"x":[1.,1.,1.,np.inf,np.nan],"y":[3.,2.,1.,0.,0.]}),
                    pd.DataFrame({"x":[],"y":[]}),pd.DataFrame({"x":[2.],"y":[4.]})]
            with ctx.disk_db() as con:
                for frame in frames:
                    con.register("input_frame",frame)
                    query="SELECT x,y FROM input_frame WHERE isfinite(x) AND isfinite(y)"
                    expected=con.execute("""WITH pairs AS ("""+query+"""),ranks AS (
                        SELECT x,y,rank() OVER(ORDER BY x)+(count(*) OVER(PARTITION BY x)-1)/2.0 rx,
                        rank() OVER(ORDER BY y)+(count(*) OVER(PARTITION BY y)-1)/2.0 ry FROM pairs)
                        SELECT count(*) n,corr(x,y) pearson,corr(rx,ry) spearman FROM ranks""").df()
                    actual=pd.DataFrame([analysis.pair_correlations(con,query)])
                    self.assertEqual(actual.n.iloc[0],expected.n.iloc[0])
                    np.testing.assert_allclose(actual[["pearson","spearman"]],expected[["pearson","spearman"]],rtol=RTOL,atol=ATOL,equal_nan=True)
                    finite=frame[np.isfinite(frame.x)&np.isfinite(frame.y)]
                    if len(finite)>1 and finite.x.nunique()>1 and finite.y.nunique()>1:
                        self.assertAlmostEqual(actual.spearman.iloc[0],spearmanr(finite.x,finite.y).statistic,places=12)
                    self.assertFalse(con.execute("SELECT table_name FROM information_schema.tables WHERE table_name IN ('rq_pairs','x_ranks','y_ranks','ranked_x','value_counts')").fetchall())

    def test_empty_all_missing_and_singleton_eda_match_reference(self):
        with tempfile.TemporaryDirectory(prefix="pubg-empty-eda-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development",progress=lambda _:None)
            for n in (0,1,8):
                frame=synthetic_analysis(ctx,n)
                columns=BASE+ABSOLUTE+PHASE+["player_survive_time","normalized_placement"]
                frame[columns]=np.nan
                frame["split"]="train";frame["valid_survival"]=True
                if n==1:frame["player_kills"]=0.
                frame.to_parquet(ctx.data/"player_match.parquet",index=False)
                with patch.object(reference,"figure"),patch("src.analysis.figure"):
                    reference.eda(ctx)
                    expected=pd.read_csv(ctx.path("tables/eda_statistics.csv"))
                    analysis.eda(ctx)
                self.assert_table(pd.read_csv(ctx.path("tables/eda_statistics.csv")),expected)

    def test_external_quantiles_1200000_values_and_ranks_600000_pairs_at_64mib(self):
        with tempfile.TemporaryDirectory(prefix="pubg-analysis-64mib-") as folder:
            root=Path(folder);cfg=fixture(root);cfg["runtime"]["duckdb_memory"]="64MiB";write_config(root,cfg)
            ctx=Context(root,"development",progress=lambda _:None)
            with ctx.disk_db() as con:
                con.execute('CREATE TABLE dev AS SELECT ((i*104729)%1200000)::DOUBLE AS "value" FROM range(1200000) t(i)')
                result=analysis.column_quantiles(con,"value",1200000).iloc[0]
                self.assertEqual(tuple(result),(599999.5,299999.75,899999.25))
                con.execute("DROP TABLE dev")
                result=analysis.pair_correlations(con,"SELECT i::DOUBLE x,(600000-i)::DOUBLE y FROM range(600000) t(i)")
                self.assertEqual(result["n"],600000)
                self.assertAlmostEqual(result["pearson"],-1.,places=12)
                self.assertAlmostEqual(result["spearman"],-1.,places=12)
            self.assertFalse(list(ctx.temp.glob("pubg-sql-*")))

    def test_s05_failure_preserves_previous_statistics_and_retries(self):
        with tempfile.TemporaryDirectory(prefix="pubg-eda-failure-") as folder:
            root=Path(folder);cfg=fixture(root);ctx=run_features(root);ctx.progress_callback=lambda _:None
            ctx.run("S05",analysis.eda)
            target=ctx.path("tables/eda_statistics.csv");old=digest(target)
            unrelated=ctx.temp/"keep.txt";unrelated.write_text("not owned by EDA")
            cfg["features"]["transform_reason"]="synthetic retry only";write_config(root,cfg);ctx.cfg=cfg
            build=analysis.column_quantiles;calls=[]
            def fail_second(con,column,n):
                calls.append(column)
                if len(calls)==2:raise MemoryError("injected EDA allocation failure")
                return build(con,column,n)
            with patch("src.analysis.column_quantiles",side_effect=fail_second):
                with self.assertRaises(MemoryError):ctx.run("S05",analysis.eda)
            self.assertEqual(ctx.manifest()["S05"]["status"],"resource_limited")
            self.assertEqual(digest(target),old)
            self.assertEqual(list(ctx.temp.iterdir()),[unrelated])
            ctx.run("S05",analysis.eda);ctx.require("S05")

    def test_s06_failure_preserves_previous_relationships_and_retries(self):
        with tempfile.TemporaryDirectory(prefix="pubg-rq1-failure-") as folder:
            root=Path(folder);fixture(root);ctx=run_features(root);ctx.progress_callback=lambda _:None
            ctx.run("S05",analysis.eda)
            reference.relationship(ctx)
            target=ctx.path("tables/rq1_relationships.csv");old=digest(target)
            unrelated=ctx.temp/"keep.txt";unrelated.write_text("not owned by RQ1")
            build=analysis.pair_correlations;calls=[]
            def fail_second(con,query):
                calls.append(query)
                if len(calls)==2:raise MemoryError("injected global rank allocation failure")
                return build(con,query)
            with patch("src.analysis.pair_correlations",side_effect=fail_second):
                with self.assertRaises(MemoryError):ctx.run("S06",analysis.relationship)
            self.assertEqual(ctx.manifest()["S06"]["status"],"resource_limited")
            self.assertEqual(digest(target),old)
            self.assertEqual(list(ctx.temp.iterdir()),[unrelated])
            ctx.run("S06",analysis.relationship);ctx.require("S06")


if __name__=="__main__":unittest.main()
