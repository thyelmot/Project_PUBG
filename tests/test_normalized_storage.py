"""Normalized layout is compared by logical tables, never by pretending index files are wide data."""
import copy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.io import Context,digest,read_json,write_json
from src import analysis,features,modeling,reporting
from src.storage import dataset_sql,dataset_fingerprint,prediction_sql,validate_prediction,prediction_batches
from src.evaluation import plot_sample
from src.kaggle_runtime import prepare_handoff,restore_handoff
from test_pipeline_acceptance import acceptance_fixture,STAGES,tree_hashes
import test_pipeline_acceptance as acceptance
from test_data_features import write_config
from test_data_features import fixture
from test_model_dataflow import matrix_fixture
from src.storage import publish_prediction


def logical(ctx,name):
    with ctx.disk_db() as con:return con.execute(dataset_sql(ctx,name)).df()


class NormalizedStorage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(prefix="pubg-normalized-")
        cls.contexts=[]
        for layout in ("materialized","normalized_v1"):
            root=Path(cls.folder.name)/layout;cfg=acceptance_fixture(root)
            cfg["storage"]["layout"]=layout;write_config(root,cfg)
            ctx=Context(root,"development",progress=lambda _:None)
            for number,function in enumerate(STAGES,1):ctx.run(f"S{number:02d}",function)
            cls.contexts.append(ctx)

    @classmethod
    def tearDownClass(cls):cls.folder.cleanup()

    def test_etl_and_all_downstream_values_match_wide_layout(self):
        a,b=self.contexts
        compare=acceptance.PipelineAcceptance.compare
        for name,key in (("cleaned","row_id"),("base","row_id"),("player_match","row_id"),("kill_discrepancy","row_id")):
            compare(self,logical(a,name),logical(b,name),[key])
            self.assertFalse((b.data/(name+".parquet")).exists())
        for name in ("removal_ledger","split_summary","feature_dictionary","timing_audit","eda_statistics","rq1_relationships",
                     "cluster_centers","cluster_assignments","cluster_sizes","cluster_outcomes","coefficients","model_metrics",
                     "model_cohorts","validation_metrics","timing_comparison","timing_ci","error_analysis"):
            compare(self,pd.read_csv(a.path("tables/"+name+".csv")),pd.read_csv(b.path("tables/"+name+".csv")))
        for split in ("validation","test"):
            for experiment in ("s1_mean","s1_median","s1_linear","p2_mean","p2_median","p2_linear","t0_linear"):
                paths=[c.path(f"predictions/{split}_{experiment}.parquet") for c in (a,b)]
                expected=pd.read_parquet(paths[0])
                with b.disk_db() as con:actual=con.execute(prediction_sql(paths[1])).df()
                compare(self,expected,actual,["row_id"])
                self.assertEqual(pq.read_schema(paths[1]).names,["position","predicted"])
                self.assertEqual(validate_prediction(paths[1]),len(expected))
        self.assertEqual(len(list(b.path("predictions/cohorts").glob("*.parquet"))),4)
        self.assertEqual(read_json(a.path("manifests/cluster_selection.json"))["clusters"],read_json(b.path("manifests/cluster_selection.json"))["clusters"])

    def test_restore_report_only_and_missing_compact_dependency(self):
        ctx=self.contexts[1];prepare_handoff(ctx)
        target=Path(self.folder.name)/"restore"
        restore_handoff(ctx.root,target,"development",ctx.cfg["source"]["directory"],"synthetic/normalized/versions/1")
        restored=Context(target,"development",progress=lambda _:None)
        for number in range(1,11):restored.run(f"S{number:02d}",lambda _:self.fail("Unexpected recomputation"))
        pointer=read_json(restored.path("manifests/final_results.json"));before=tree_hashes(target)
        with patch("IPython.display.display"),patch("IPython.display.Image"):
            reporting.display_release(target/pointer["manifest"])
        self.assertEqual(before,tree_hashes(target))
        manifest=target/pointer["manifest"];record=read_json(manifest)
        entry=next(e for e in record["entries"] if "/cohorts/" in e["path"])
        (manifest.parent/entry["path"]).unlink()
        with self.assertRaises(ValueError):reporting.load_release(manifest)

    def test_plot_sample_keeps_physical_order_and_compact_position_validation(self):
        a,b=self.contexts
        for experiment in ("s1_mean","p2_linear"):
            paths=[c.path(f"predictions/test_{experiment}.parquet") for c in (a,b)]
            n=pq.ParquetFile(paths[0]).metadata.num_rows
            pd.testing.assert_frame_equal(plot_sample(a,paths[0],n,42),plot_sample(b,paths[1],n,42),rtol=1e-9,atol=1e-10)
        source=b.path("predictions/test_p2_linear.parquet")
        with tempfile.TemporaryDirectory(prefix="pubg-bad-compact-") as folder:
            root=Path(folder);shutil.copytree(source.parent,root/"predictions")
            path=root/"predictions"/source.name;table=pq.read_table(path)
            position=table.column("position").to_pylist();position[0]=position[-1]
            table=table.set_column(0,"position",pa.array(position,type=pa.int64()))
            pq.write_table(table,path)
            with self.assertRaises(ValueError):validate_prediction(path)

    def test_underlying_data_changes_identity_and_descriptor_is_not_arbitrary_sql(self):
        ctx=self.contexts[1]
        with tempfile.TemporaryDirectory(prefix="pubg-normalized-identity-") as folder:
            root=Path(folder)/"project";shutil.copytree(ctx.root,root)
            copy_ctx=Context(root,"development",progress=lambda _:None)
            before=dataset_fingerprint(copy_ctx,"player_match")
            path=copy_ctx.data/"timing.parquet";table=pd.read_parquet(path)
            table.loc[0,"avg_kill_time"]+=1;table.to_parquet(path,index=False)
            self.assertNotEqual(dataset_fingerprint(copy_ctx,"player_match"),before)
            descriptor=copy_ctx.data/"base.dataset.json";record=read_json(descriptor);record["recipe"]="arbitrary_sql"
            write_json(record,descriptor)
            with self.assertRaises(ValueError):dataset_sql(copy_ctx,"base")

    def test_compact_predictions_cross_50000_row_boundaries_without_precision_loss(self):
        with tempfile.TemporaryDirectory(prefix="pubg-compact-batches-") as folder:
            root=Path(folder);cfg=fixture(root);cfg["storage"]["layout"]="normalized_v1";write_config(root,cfg)
            ctx=Context(root,"development",progress=lambda _:None);matrix_fixture(ctx,100007)
            with ctx.disk_db() as con:
                ctx.view(con,"p","player_match");bundle=modeling.matrix_data(ctx,con,"s1","train",root)
            class Constant:
                def predict(self,frame):return np.full(len(frame),12.125,dtype=np.float64)
            for index in range(2):
                path=root/("private"+str(index)+".parquet")
                modeling.stream_predictions(bundle,"s1",Constant(),"s1_"+str(index),"fixed",path)
                target=ctx.path("predictions/s1_"+str(index)+".parquet")
                publish_prediction(ctx,path,target,bundle)
                self.assertEqual(validate_prediction(target),100007)
                actual=pd.concat([b.to_pandas() for b in prediction_batches(target,pq.read_schema(path).names)],ignore_index=True)
                pd.testing.assert_frame_equal(actual,pd.read_parquet(path),check_exact=True)
                pd.testing.assert_frame_equal(plot_sample(ctx,target,100007,42),plot_sample(ctx,path,100007,42),check_exact=True)
            self.assertEqual(len(list(ctx.path("predictions/cohorts").glob("*.parquet"))),1)


if __name__=="__main__":unittest.main()
