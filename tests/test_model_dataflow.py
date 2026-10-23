import copy
import tempfile
import unittest
from decimal import Decimal, localcontext
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.metrics import davies_bouldin_score

from src import analysis, modeling
from src.features import FEATURES, TARGETS
from src.io import Context, digest, frame_fingerprint, read_json
from test_data_features import fixture, run_features, write_config
import reference_clustering_v58 as old_clustering
import reference_modeling_v58 as old_modeling


# Frozen before D4 comparisons; DB has a separate independent high-precision oracle.
RTOL, ATOL = 1e-9, 1e-10


def decimal_db(X, labels):
    with localcontext() as context:
        context.prec=60
        groups=[[list(map(Decimal.from_float,map(float,row))) for row in X[np.asarray(labels)==c]]
                for c in np.unique(labels)]
        centers=[[sum(row[j] for row in g)/len(g) for j in range(X.shape[1])] for g in groups]
        def distance(a,b):return sum((x-y)**2 for x,y in zip(a,b)).sqrt()
        scatter=[sum(distance(row,c) for row in g)/len(g) for g,c in zip(groups,centers)]
        return float(sum(max((scatter[i]+scatter[j])/distance(centers[i],centers[j])
                             for j in range(len(groups)) if j!=i) for i in range(len(groups)))/len(groups))


def matrix_fixture(ctx, n=100007):
    i=np.arange(n)
    frame=pd.DataFrame({c:((i*(j+1))%29).astype(float)/7 for j,c in enumerate(FEATURES["s1"])})
    frame[FEATURES["s1"][0]]=np.nan
    frame.loc[i%13==0,FEATURES["s1"][-1]]=np.nan
    frame["row_id"]=[f"r{k:08d}" for k in i]
    frame["match_id"]=["Trận_"+str(k//5) for k in i]
    frame["player_name"]=["Người_"+str(k%23) for k in i]
    frame["team_id"]=np.where(i<50000,None,"đội_2")
    frame["team_size_mode"]="Duo";frame["split"]="train"
    frame["valid_survival"]=True;frame["valid_placement"]=False
    frame[TARGETS["s1"]]=10+(i%17).astype(float)
    ctx.data.mkdir(parents=True,exist_ok=True)
    table=pa.Table.from_pandas(frame,preserve_index=False)
    # Canonical keys are VARCHAR even when an entire cohort is missing team IDs.
    schema=table.schema.set(table.schema.get_field_index("team_id"),pa.field("team_id",pa.string()))
    pq.write_table(table.cast(schema),ctx.data/"player_match.parquet")
    return frame


class ModelDataflow(unittest.TestCase):
    def assert_frame(self,a,b):
        self.assertEqual(list(a),list(b))
        pd.testing.assert_frame_equal(a.isna(),b.isna(),check_exact=True)
        pd.testing.assert_frame_equal(a,b,rtol=RTOL,atol=ATOL)

    def test_db_direct_distances_match_decimal_without_relaxing_tolerance(self):
        rng=np.random.default_rng(42)
        # Singleton/near-center distances amplify cancellation in norm/dot distances.
        X=np.vstack([rng.normal(size=(5,4)),rng.normal(size=(4,4))+4,rng.normal(size=(1,4))-3])
        labels=np.repeat([0,1,2],[5,4,1])
        expected=decimal_db(X,labels)
        for size in (1,3,50000):
            self.assertAlmostEqual(analysis.stable_davies_bouldin(X,labels,size),expected,places=14)
        ordinary=rng.normal(size=(30,4));groups=np.arange(30)%3
        np.testing.assert_allclose(analysis.stable_davies_bouldin(ordinary,groups),davies_bouldin_score(ordinary,groups),rtol=RTOL,atol=ATOL)
        for size in (0,-1,True):
            with self.assertRaises(ValueError):analysis.stable_davies_bouldin(X,labels,size)
        with self.assertRaises(ValueError):analysis.stable_davies_bouldin(X,np.zeros(len(X)))
        with self.assertRaises(ValueError):analysis.stable_davies_bouldin(X,np.arange(len(X)))
        bad=X.copy();bad[0,0]=np.nan
        with self.assertRaises(ValueError):analysis.stable_davies_bouldin(bad,labels)
        self.assertEqual(analysis.stable_davies_bouldin(np.zeros((4,2)),[0,0,1,1]),0)

    def test_db_regression_case_and_diagnostic_policy_match_v58(self):
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
        with tempfile.TemporaryDirectory(prefix="pubg-d4-diagnostic-") as folder:
            root=Path(folder);fixture(root);ctx=run_features(root)
            with ctx.disk_db() as con:frame=analysis.profiles(con,ctx,True)
            for mode,g in frame.groupby("team_size_mode"):
                g=g.sort_values("player_name")
                X=StandardScaler().fit_transform(SimpleImputer(strategy="mean",add_indicator=True,keep_empty_features=True).fit_transform(g[analysis.PROFILE_FEATURES]))
                matrix=root/(mode+".npy");np.save(matrix,X)
                for k in (2,3):
                    payload={"matrix":str(matrix),"mode":mode,"device":"cpu","k":k,"seed":42,
                             "seeds":[42,43,44],"diagnostic_sample":5}
                    expected=old_clustering.diagnostic_fit(payload)["diagnostic"]
                    calls=[]
                    real=analysis.kmeans
                    def tracked(device,k,seed):
                        calls.append((device,k,seed));return real(device,k,seed)
                    with patch("src.analysis.kmeans",side_effect=tracked):actual=analysis.diagnostic_fit(payload)["diagnostic"]
                    self.assertEqual(calls,[("cpu",k,s) for s in (42,43,44,42)])
                    labels=real("cpu",k,42).fit(X).labels_
                    np.testing.assert_allclose(actual.pop("davies_bouldin"),decimal_db(X,labels),rtol=RTOL,atol=ATOL)
                    expected.pop("davies_bouldin")
                    self.assertEqual(actual,expected)

    def test_matrix_mmap_identity_schema_and_batch_prediction_match_reference(self):
        with tempfile.TemporaryDirectory(prefix="pubg-d4-matrix-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            frame=matrix_fixture(ctx)
            with ctx.disk_db() as con:
                ctx.view(con,"p","player_match")
                bundle=modeling.matrix_data(ctx,con,"s1","train",root)
            X=np.load(bundle["X"],mmap_mode="r");y=np.load(bundle["y"],mmap_mode="r")
            self.assertIsInstance(X,np.memmap)
            np.testing.assert_array_equal(X,frame[FEATURES["s1"]].to_numpy(float))
            np.testing.assert_array_equal(y,frame[TARGETS["s1"]])
            del X,y
            self.assertEqual(bundle["cohort"]["cohort_hash"],frame_fingerprint(frame[["row_id",TARGETS["s1"]]]))
            self.assertEqual(bundle["cohort"]["players"],23)
            metadata=pd.read_parquet(bundle["metadata"])
            self.assertNotIn("player_name",metadata)
            self.assertEqual(metadata.team_id.isna().sum(),50000)
            sizes=[]
            class BatchedModel:
                def predict(self,part):
                    sizes.append(len(part));return np.nan_to_num(part.iloc[:,-1].to_numpy())+2
            target=root/"predicted.parquet"
            modeling.stream_predictions(bundle,"s1",BatchedModel(),"s1_linear","fixed",target)
            self.assertEqual(sizes,[50000,50000,7])
            actual=pd.read_parquet(target)
            expected=old_modeling.prediction_frame(frame,"s1",BatchedModel(),"s1_linear","fixed")
            self.assert_frame(actual,expected)
            schema=pq.ParquetFile(target).schema_arrow
            self.assertEqual(str(schema.field("team_id").type),"string")

    def test_bundle_rejects_duplicates_and_prediction_detects_corruption(self):
        with tempfile.TemporaryDirectory(prefix="pubg-d4-corrupt-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            frame=matrix_fixture(ctx,20)
            with ctx.disk_db() as con:
                ctx.view(con,"p","player_match");bundle=modeling.matrix_data(ctx,con,"s1","train",root)
            class Constant:
                def predict(self,frame):return np.zeros(len(frame))
            destination=root/"good.parquet"
            modeling.stream_predictions(bundle,"s1",Constant(),"s1_mean","fixed",destination)
            before=digest(destination)
            metadata=pd.read_parquet(bundle["metadata"])
            metadata.loc[0,TARGETS["s1"]]+=1
            metadata.to_parquet(bundle["metadata"],index=False)
            with self.assertRaisesRegex(ValueError,"metadata checksum"):
                modeling.stream_predictions(bundle,"s1",Constant(),"s1_mean","fixed",root/"private.parquet")
            bundle["metadata_sha256"]=digest(Path(bundle["metadata"]))
            with self.assertRaisesRegex(ValueError,"target mismatch"):
                modeling.stream_predictions(bundle,"s1",Constant(),"s1_mean","fixed",root/"private.parquet")
            self.assertEqual(digest(destination),before)
            metadata[TARGETS["s1"]]=frame[TARGETS["s1"]]
            metadata.loc[0,"match_id"]="corrupted"
            metadata.loc[0,"row_id"]="q000"
            metadata.to_parquet(bundle["metadata"],index=False)
            bundle["metadata_sha256"]=digest(Path(bundle["metadata"]))
            with self.assertRaisesRegex(ValueError,"cohort identity"):
                modeling.stream_predictions(bundle,"s1",Constant(),"s1_mean","fixed",root/"private.parquet")
            frame.loc[1,"row_id"]=frame.loc[0,"row_id"]
            frame.to_parquet(ctx.data/"player_match.parquet",index=False)
            with ctx.disk_db() as con:
                ctx.view(con,"p","player_match")
                with self.assertRaisesRegex(ValueError,"unique"):
                    modeling.matrix_data(ctx,con,"s1","train",root)
            frame.loc[0,TARGETS["s1"]]=np.nan;frame.loc[1,"row_id"]="unique"
            frame.to_parquet(ctx.data/"player_match.parquet",index=False)
            with ctx.disk_db() as con:
                ctx.view(con,"p","player_match")
                with self.assertRaisesRegex(ValueError,"Nonfinite matrix target"):
                    modeling.matrix_data(ctx,con,"s1","train",root)
                with self.assertRaisesRegex(ValueError,"Empty eligible"):
                    modeling.matrix_data(ctx,con,"s1","validation",root)

    def test_full_stage_scientific_outputs_match_v58(self):
        with tempfile.TemporaryDirectory(prefix="pubg-d4-parity-") as folder:
            root=Path(folder);contexts=[]
            for version in ("old","new"):
                project=root/version;project.mkdir();cfg=fixture(project)
                cfg["rq2"]["decision_mode"]="auto";cfg["rq3"]["decision_mode"]="auto"
                write_config(project,cfg);ctx=run_features(project)
                ctx.run("S05",analysis.eda);ctx.run("S06",analysis.relationship)
                source=digest(ctx.data/"player_match.parquet")
                ctx.run("S07",old_clustering.clustering if version=="old" else analysis.clustering)
                ctx.run("S08",old_modeling.prediction if version=="old" else modeling.prediction)
                self.assertEqual(digest(ctx.data/"player_match.parquet"),source)
                self.assertFalse(list(ctx.temp.glob("pubg-regression-*")))
                self.assertFalse(list(ctx.temp.glob("pubg-clusters-*")))
                self.assertFalse(list(ctx.temp.glob("pubg-sql-*")))
                contexts.append(ctx)
            old,new=contexts
            for name in ("cluster_centers","cluster_sizes","cluster_outcomes","cluster_assignments",
                         "profile_retention","profile_coverage","coefficients","model_cohorts","model_metrics","validation_metrics"):
                a=pd.read_csv(old.path("tables/"+name+".csv"));b=pd.read_csv(new.path("tables/"+name+".csv"))
                self.assert_frame(a,b)
            for split in ("validation","test"):
                for experiment in ("s1_mean","s1_median","s1_linear","p2_mean","p2_median","p2_linear","t0_linear"):
                    name=f"predictions/{split}_{experiment}.parquet"
                    self.assert_frame(pd.read_parquet(old.path(name)).drop(columns="run_id"),pd.read_parquet(new.path(name)).drop(columns="run_id"))
            for task in ("s1","p2","t0"):
                self.assertEqual(read_json(old.path("manifests/bins_"+task+".json")),read_json(new.path("manifests/bins_"+task+".json")))
            self.assertFalse(read_json(new.path("manifests/selection.json"))["test_accessed_at_approval"])
            self.assertFalse(read_json(new.path("manifests/s08_execution.json"))["sampling_fit"])
            good=new.path("predictions/validation_s1_mean.parquet");before=digest(good)
            # A fresh signature, not a bypass of the verified validation cache.
            new.cfg["runtime"]["seed"]+=1
            with patch("src.modeling.stream_predictions",side_effect=OSError("synthetic disk full")):
                with self.assertRaises(OSError):modeling.prediction(new)
            self.assertEqual(digest(good),before)
            self.assertFalse(list(new.temp.glob("pubg-regression-*")))

    def test_single_full_fit_guard_still_blocks_before_estimator(self):
        with tempfile.TemporaryDirectory(prefix="pubg-d4-fit-budget-") as folder:
            root=Path(folder);cfg=fixture(root);ctx=Context(root,"development")
            matrix_fixture(ctx,20)
            with ctx.disk_db() as con:
                ctx.view(con,"p","player_match");bundle=modeling.matrix_data(ctx,con,"s1","train",root)
            data=root/"bundle.joblib";joblib.dump({"train":bundle,"validation":bundle},data)
            runtime=copy.deepcopy(cfg["runtime"]);runtime["max_matrix_gb"]=1e-12
            payload={"data":str(data),"runtime":runtime,"task":"s1","kind":"linear","device":"cpu"}
            with patch("src.modeling.estimator") as estimator:
                with self.assertRaisesRegex(MemoryError,"full fit"):modeling.fit_candidate(payload)
                estimator.assert_not_called()

    def test_all_missing_indicators_float64_and_reload_match_v58(self):
        with tempfile.TemporaryDirectory(prefix="pubg-d4-missing-") as folder:
            root=Path(folder);cfg=fixture(root);ctx=Context(root,"development")
            frame=matrix_fixture(ctx,57)
            with ctx.disk_db() as con:
                ctx.view(con,"p","player_match")
                frame=old_modeling.matrix_data(ctx,con,"s1","train")
                bundle=modeling.matrix_data(ctx,con,"s1","train",root)
            data=root/"new.joblib";joblib.dump({"train":bundle,"validation":bundle},data)
            original=root/"old.joblib";joblib.dump({"train":frame,"validation":frame},original)
            for kind in ("mean","median","linear"):
                payload={"data":str(data),"runtime":cfg["runtime"],"task":"s1","kind":kind,"device":"cpu",
                    "model_path":str(root/(kind+".new.joblib")),"prediction_path":str(root/(kind+".parquet")),
                    "logs":[FEATURES["s1"][1]],"experiment":"s1_"+kind,"run_id":"fixed"}
                new=modeling.fit_candidate(payload)
                old=old_modeling.fit_candidate({**payload,"data":str(original),"model_path":str(root/(kind+".old.joblib"))})
                expected_path=root/(kind+".expected.parquet")
                pq.write_table(pa.Table.from_pandas(old["predicted"],preserve_index=False),expected_path)
                self.assert_frame(pd.read_parquet(new["prediction_path"]),pd.read_parquet(expected_path))
                self.assertEqual(new["names"],old["names"])
                np.testing.assert_allclose(new["coefficients"],old["coefficients"],rtol=RTOL,atol=ATOL)
                a=joblib.load(payload["model_path"])
                b=joblib.load(root/(kind+".old.joblib"))
                for name,attributes in (("imputer",("statistics_",)),("scaler",("mean_","var_","scale_"))):
                    for attr in attributes:np.testing.assert_allclose(getattr(a.named_steps[name],attr),getattr(b.named_steps[name],attr),rtol=RTOL,atol=ATOL)
                self.assertEqual(a.named_steps["scaler"].mean_.dtype,np.float64)

    def test_owned_mmap_files_close_on_allocation_fit_and_predict_errors(self):
        with tempfile.TemporaryDirectory(prefix="pubg-d4-map-close-") as folder:
            root=Path(folder);cfg=fixture(root);ctx=Context(root,"development")
            matrix_fixture(ctx,20)
            real=np.lib.format.open_memmap;calls=[]
            def fail_second(*args,**kwargs):
                calls.append(1)
                if len(calls)==2:raise OSError("synthetic map allocation failure")
                return real(*args,**kwargs)
            with self.assertRaisesRegex(OSError,"synthetic map allocation failure"):
                with tempfile.TemporaryDirectory(prefix="owned-",dir=ctx.temp) as owned:
                    with ctx.disk_db() as con:
                        ctx.view(con,"p","player_match")
                        with patch("src.modeling.np.lib.format.open_memmap",side_effect=fail_second):
                            modeling.matrix_data(ctx,con,"s1","train",Path(owned))
            for phase in ("fit","predict"):
                with self.subTest(phase=phase),self.assertRaisesRegex(RuntimeError,"synthetic "+phase):
                    with tempfile.TemporaryDirectory(prefix="owned-",dir=ctx.temp) as owned:
                        work=Path(owned)
                        with ctx.disk_db() as con:
                            ctx.view(con,"p","player_match");bundle=modeling.matrix_data(ctx,con,"s1","train",work)
                        if phase=="fit":
                            path=work/"data.joblib";joblib.dump({"train":bundle,"validation":bundle},path)
                            payload={"data":str(path),"task":"s1","kind":"mean","device":"cpu","runtime":cfg["runtime"],"logs":[]}
                            with patch("sklearn.pipeline.Pipeline.fit",side_effect=RuntimeError("synthetic fit")):
                                modeling.fit_candidate(payload)
                        else:
                            class FailedModel:
                                def predict(self,frame):raise RuntimeError("synthetic predict")
                            modeling.stream_predictions(bundle,"s1",FailedModel(),"s1_mean","fixed",work/"partial.parquet")
            self.assertFalse(list(ctx.temp.glob("owned-*")))


if __name__=="__main__":unittest.main()
