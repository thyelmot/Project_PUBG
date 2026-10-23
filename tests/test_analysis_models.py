import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.analysis import eda, relationship, clustering, profiles
from src.io import Context, PendingDecision, read_json, digest
from src.modeling import metrics, hierarchical, pair_predictions, paired_bootstrap, prediction, comparisons
from src.reporting import finalize, load_release
from test_data_features import fixture, write_config, run_features


def finish_fixture(root):
    cfg=fixture(root);ctx=run_features(root)
    ctx.run("S05",eda);ctx.run("S06",relationship)
    try:ctx.run("S07",clustering)
    except PendingDecision:pass
    receipt=read_json(ctx.path("manifests/k_diagnostic_receipt.json"))
    cfg["rq2"].update(diagnostic_hash=receipt["diagnostic_hash"],decision_reason="synthetic fixture only",clusters={"Solo":2,"Duo":2,"Squad":None})
    write_config(root,cfg);ctx=Context(root,"development");ctx.run("S07",clustering)
    try:ctx.run("S08",prediction)
    except PendingDecision:pass
    if list(ctx.path("predictions").glob("test_*.parquet")):
        raise AssertionError("G4 accessed final test while pending")
    approval=read_json(ctx.path("manifests/validation_receipt.json"))
    cfg["rq3"].update(selection_approved=True,selection_reason="synthetic fixture gate test, NOT production approval",validation_hash=approval["validation_hash"])
    write_config(root,cfg);ctx=Context(root,"development")
    from unittest.mock import patch
    with patch("sklearn.pipeline.Pipeline.fit",side_effect=AssertionError("G4 approval must reuse verified validation fit")):
        ctx.run("S08",prediction)
    ctx.run("S09",comparisons);ctx.run("S10",finalize)
    return ctx,cfg


class AnalysisModels(unittest.TestCase):
    def test_metrics_and_weighted_contract(self):
        m=metrics([1,2,3],[1,1,1])
        self.assertAlmostEqual(m["mae"],1)
        self.assertAlmostEqual(m["rmse"],np.sqrt(5/3))
        self.assertAlmostEqual(m["r2"],-1.5)
        self.assertTrue(np.isnan(metrics([2,2],[1,2])["r2"]))
        with self.assertRaises(ValueError):metrics([1],[np.nan])

    def test_pairing_bootstrap_identity(self):
        frame=pd.DataFrame({"row_id":["a","b","c"],"match_id":["x","x","y"],"team_id":["1","2","1"],
            "split":"test","target":"normalized_placement","actual":[0,.5,1],"predicted":[.2,.4,.8]})
        a,b=pair_predictions(frame,frame.iloc[::-1])
        self.assertTrue(a.row_id.equals(b.row_id))
        for row in paired_bootstrap(frame,frame,40,42):
            self.assertAlmostEqual(row["lower"],0);self.assertAlmostEqual(row["upper"],0)
        with self.assertRaises(ValueError):pair_predictions(frame,frame.iloc[:2])
        corrupted=frame.copy();corrupted.loc[0,"actual"]=1
        with self.assertRaises(ValueError):pair_predictions(frame,corrupted)

    def test_profile_conditional_mean_and_singleton(self):
        with tempfile.TemporaryDirectory(prefix="pubg-profile-") as folder:
            root=Path(folder);fixture(root);ctx=run_features(root)
            data=pd.read_parquet(ctx.data/"player_match.parquet").iloc[:3].copy()
            data["player_name"]=["paired","paired","singleton"]
            data["team_size_mode"]="Solo";data["split"]="train"
            data["player_kills"]=[1,3,1];data["early_kill_ratio"]=[1,0,0]
            data["timing_status"]="phase_observed";data["early_kills"]=[1,0,0]
            data.to_parquet(ctx.data/"player_match.parquet",index=False)
            with ctx.db() as con:out=profiles(con,ctx).set_index("player_name")
            self.assertAlmostEqual(out.loc["paired","avg_early_kill_ratio"],.5)
            self.assertEqual(out.loc["paired","avg_early_kill_ratio_n"],2)
            self.assertTrue(np.isnan(out.loc["singleton","std_kills"]))

    def test_train_imputation_and_ols_do_not_use_test(self):
        from sklearn.pipeline import Pipeline
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
        from sklearn.linear_model import LinearRegression
        train=pd.DataFrame({"x":[1.,2.,np.nan,4.]});y=np.array([2.,4.,4.,8.])
        model=Pipeline([("imputer",SimpleImputer()),("scaler",StandardScaler()),("model",LinearRegression())]).fit(train,y)
        imputation=model.named_steps["imputer"].statistics_.copy()
        before=model.predict(pd.DataFrame({"x":[3.]}))
        model.predict(pd.DataFrame({"x":[1e9]}))
        np.testing.assert_array_equal(model.named_steps["imputer"].statistics_,imputation)
        np.testing.assert_array_equal(before,model.predict(pd.DataFrame({"x":[3.]})))

    def test_gpu_absence_does_not_fallback(self):
        import sys
        from unittest.mock import patch
        from src.analysis import kmeans
        from src.modeling import estimator
        with patch.dict(sys.modules,{"cuml.cluster":None,"cuml.linear_model":None}):
            with self.assertRaisesRegex(RuntimeError,"không fallback"):kmeans("cuda",2,42)
            with self.assertRaisesRegex(RuntimeError,"không fallback"):estimator("cuda")

    def test_outcome_mutation_keeps_behavior_profiles(self):
        from src.analysis import PROFILE_FEATURES,kmeans
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
        with tempfile.TemporaryDirectory(prefix="pubg-outcome-") as folder:
            root=Path(folder);fixture(root);ctx=run_features(root)
            with ctx.db() as con:before=profiles(con,ctx).sort_values(["team_size_mode","player_name"]).reset_index(drop=True)
            data=pd.read_parquet(ctx.data/"player_match.parquet")
            data["player_survive_time"]+=10000;data["normalized_placement"]=1-data["normalized_placement"]
            data.to_parquet(ctx.data/"player_match.parquet",index=False)
            with ctx.db() as con:after=profiles(con,ctx).sort_values(["team_size_mode","player_name"]).reset_index(drop=True)
            pd.testing.assert_frame_equal(before[PROFILE_FEATURES],after[PROFILE_FEATURES])
            transform=Pipeline([("imputer",SimpleImputer(keep_empty_features=True)),("scaler",StandardScaler())])
            X=transform.fit_transform(before[PROFILE_FEATURES])
            model=kmeans("cpu",2,42).fit(X)
            np.testing.assert_array_equal(model.labels_,model.predict(transform.transform(after[PROFILE_FEATURES])))
            data.loc[data.split.eq("test"),"normalized_placement"]=12345
            data.loc[data.split.eq("test"),"player_survive_time"]=12345
            data.to_parquet(ctx.data/"player_match.parquet",index=False)
            with ctx.db() as con:heldout=profiles(con,ctx,development=False).sort_values(["team_size_mode","player_name"]).reset_index(drop=True)
            pd.testing.assert_frame_equal(after[["avg_survival","avg_placement"]],heldout[["avg_survival","avg_placement"]])

    def test_notebook_core_helpers_full_chain(self):
        with tempfile.TemporaryDirectory(prefix="pubg-integration-") as folder:
            root=Path(folder);ctx,cfg=finish_fixture(root)
            metrics_table=pd.read_csv(ctx.path("tables/model_metrics.csv"))
            self.assertEqual(metrics_table[metrics_table.split.eq("test")].experiment.nunique(),7)
            pointer=read_json(ctx.path("manifests/final_results.json"))
            manifest=root/pointer["manifest"]
            release,files=load_release(manifest)
            self.assertFalse(release["report_ready"])
            self.assertEqual(release["scope"],"development")
            source=next(p for k,p in files.items() if k.endswith("rq1_relationships.csv"))
            before=digest(source)
            duo=digest(ctx.path("models/kmeans_Duo.joblib"))
            ctx.path("models/kmeans_Solo.joblib").write_bytes(b"corrupt mode artifact")
            with self.assertRaisesRegex(RuntimeError,"artifact"):ctx.require("S07")
            self.assertEqual(digest(ctx.path("models/kmeans_Duo.joblib")),duo)
            load_release(manifest)
            ctx.path("tables/rq1_relationships.csv").write_text("canonical changed",encoding="utf-8")
            self.assertEqual(digest(source),before)
            load_release(manifest)
            source.write_text("corrupt",encoding="utf-8")
            with self.assertRaises(ValueError):load_release(manifest)


if __name__=="__main__":unittest.main()
