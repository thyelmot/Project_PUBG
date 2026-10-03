"""Phase12: real NB09/NB10 cells, saved predictions only, isolated small CPU fixtures."""
import base64
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import nbformat
import numpy as np
import pandas as pd
import test_phase_d_prediction as core_tests
import test_phase11_completion as selection_tests
import test_history_workflow as history_tests
from src.data.io import atomic_write_json, read_json
from src.data.checkpoints import CheckpointManager
from src.evaluation.bootstrap import pair_predictions, run_paired_match_bootstrap
from src.evaluation.comparisons import comparison_context, run_locked_comparisons
from src.evaluation.error_analysis import analyze_prediction_errors, bin_labels
from src.evaluation.metrics import compute_regression_metrics
from src.evaluation.importance import extract_feature_importance
from src.utils.hashing import hash_file


class TestPhase12Comparisons(unittest.TestCase):
    def predictions(self):
        return pd.DataFrame({"row_id":["a0","b0","b1","b2","c0","c1"],"match_id":["a","b","b","b","c","c"],
            "split":"test","team_id":["a0","b0","b1","b2","c0","c1"],"target_actual":[1.,2.,2.,2.,3.,3.],
            "target_predicted":[0.,2.5,3.,4.,2.,2.],"target":"player_survive_time"})

    def test_bootstrap_multiplicity_matches_independent_reference(self):
        reference=self.predictions()
        candidate=reference.copy()
        candidate.target_predicted=candidate.target_actual+.25
        measured=run_paired_match_bootstrap(candidate,reference,70,17)
        rng=np.random.RandomState(17)
        expected={key:[] for key in ["mae","rmse","r2"]}
        groups=list(reference.groupby("match_id",sort=True))
        for _ in range(70):
            ids=rng.choice(3,3,replace=True)
            # Independent tiny reference deliberately concatenates whole matches with duplicates.
            frame=pd.concat([groups[index][1] for index in ids])
            a=compute_regression_metrics(frame.target_actual.to_numpy(),frame.target_actual.to_numpy()+.25)
            b=compute_regression_metrics(frame.target_actual.to_numpy(),frame.target_predicted.to_numpy())
            for key in expected:
                if np.isfinite(a[key]) and np.isfinite(b[key]):
                    expected[key].append(a[key]-b[key])
        for key,values in expected.items():
            actual=measured["delta_"+key]
            self.assertAlmostEqual(actual["mean"],np.mean(values),places=12)
            np.testing.assert_allclose([actual["ci_lower"],actual["ci_upper"]],np.percentile(values,[2.5,97.5]),atol=1e-12)
            self.assertEqual(actual["valid_replicates"],len(values))
        shuffled=run_paired_match_bootstrap(candidate.sample(frac=1,random_state=2),reference.sample(frac=1,random_state=3),70,17)
        for key in expected:
            self.assertEqual(measured["delta_"+key],shuffled["delta_"+key])
        with patch("src.evaluation.bootstrap.pd.concat",side_effect=AssertionError("no full row concat per replicate")):
            same=run_paired_match_bootstrap(reference,reference,7,2)
        self.assertEqual(same["delta_mae"]["ci_lower"],0.)
        self.assertEqual(same["delta_rmse"]["ci_upper"],0.)
        self.assertEqual(same["delta_r2"]["mean"],0.)

    def test_pairing_guards_and_resource_undefined(self):
        reference=self.predictions()
        bads=[reference.iloc[:-1],pd.concat([reference,reference.iloc[:1]])]
        for column in ["target_actual","match_id","team_id","split","target"]:
            bad=reference.copy()
            bad.loc[0,column]=4. if column=="target_actual" else "changed"
            bads.append(bad)
        bad=reference.copy()
        bad.loc[0,"target_predicted"]=np.inf
        bads.append(bad)
        for bad in bads:
            with self.assertRaises(ValueError):
                pair_predictions(bad,reference)
        constant=reference.copy()
        constant.target_actual=1.
        result=run_paired_match_bootstrap(constant,constant,8)
        self.assertEqual(result["delta_r2"]["valid_replicates"],0)
        self.assertEqual(result["delta_r2"]["reason"],"undefined_global_r2")
        limited=run_paired_match_bootstrap(reference,reference,8,max_memory_gb=1e-12)
        self.assertEqual(limited["status"],"resource_limited")
        self.assertTrue(np.isnan(limited["delta_mae"]["ci_lower"]))
        with self.assertRaises(ValueError):
            run_paired_match_bootstrap(reference,reference,0)

    def test_error_bins_metadata_history_and_coverage(self):
        frame=self.predictions()
        frame.target_actual=[0.,.25,.5,.75,1.,.3]
        frame.target_predicted=.4
        frame["team_size_mode"]="canonical_special_mode"
        frame["hist_games_played"]=[0.,1.,2.,5.,100.,np.nan]
        bins={"placement":[0,.25,.5,.75,1],"survival":[0,.5,1],"history_depth":[0,2,5,100]}
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/"errors.csv"
            result=analyze_prediction_errors(frame,output,error_bins=bins)
            self.assertIn("survival_region",set(result.slice_category))  # survival target values inside [0,1] are NOT placement.
            self.assertNotIn("placement_region",set(result.slice_category))
            self.assertIn("canonical_special_mode",result.slice_value.tolist())
            for _,group in result.groupby("slice_category"):
                self.assertEqual(group.n_observations.sum(),6)
                self.assertAlmostEqual(group.coverage.sum(),1.)
            self.assertIn("insufficient",result.status.tolist())
            self.assertIn("unstable_small_slice",result.status.tolist())
            missing=frame.drop(columns="target")
            with self.assertRaisesRegex(ValueError,"metadata"):
                analyze_prediction_errors(missing,output,error_bins=bins)
            with self.assertRaisesRegex(ValueError,"locked"):
                analyze_prediction_errors(frame,output)
        labels,_=bin_labels(pd.Series([0.,.25,.5,.75,1.]),bins["placement"])
        self.assertEqual(labels.tolist(),["[0, 0.25)","[0.25, 0.5)","[0.5, 0.75)","[0.75, 1]","[0.75, 1]"])
        with self.assertRaises(ValueError):
            bin_labels(pd.Series([1.]),[0,2,1])

    def test_importance_labels_uncertainty_and_failure_status(self):
        from src.models.linear import LinearModelWrapper
        from src.models.tree_models import RandomForestWrapper
        x=np.arange(12.).reshape(-1,1)
        y=x[:,0]*2
        model=LinearModelWrapper(standardize=False).fit(x,y)
        frame=extract_feature_importance(model,["x"],x,y,n_repeats=3,random_state=7)
        self.assertIn("unstandardized_coefficient",frame.importance_type.tolist())
        self.assertTrue(frame.loc[frame.importance_type=="permutation_mae_increase","std"].notna().all())
        tree=RandomForestWrapper(n_estimators=2).fit(x,y)
        self.assertEqual(extract_feature_importance(tree,["x"]).importance_type.tolist(),["regression_impurity_decrease"])
        with patch("src.evaluation.importance.permutation_importance",side_effect=RuntimeError("synthetic failure")):
            failed=extract_feature_importance(model,["x"],x,y)
        self.assertIn("failed",failed.status.tolist())
        limited=extract_feature_importance(model,["x"],x,y,max_memory_gb=1e-12)
        self.assertIn("resource_limited",limited.status.tolist())
        with self.assertRaisesRegex(ValueError,"pre-registered"):
            extract_feature_importance(model,["x"],x,y,scope="test")

    def execute_notebook(self,fixture,cfg,name,approve=False):
        project=Path(__file__).resolve().parents[1]
        notebook=nbformat.read(project/"notebooks"/name,as_version=4)
        nbformat.validate(notebook)
        scope={"paths":fixture.paths,"PROJECT_ROOT":project}
        scope.update(getattr(fixture, 'notebook_options', {}))
        captured=[]
        def capture(value):
            if isinstance(value,pd.DataFrame):
                captured.append(nbformat.v4.new_output("display_data",data={"text/html":value.to_html(index=False),"text/plain":value.to_string(index=False)}))
            elif value.__class__.__name__=="Image":
                captured.append(nbformat.v4.new_output("display_data",data={"image/png":base64.b64encode(value.data).decode()}))
            elif value.__class__.__name__=="Markdown":
                captured.append(nbformat.v4.new_output("display_data",data={"text/markdown":value.data}))
        with patch("src.utils.config.load_config",return_value=cfg),patch("src.utils.config.resolve_paths",return_value=fixture.paths),patch("IPython.display.display",side_effect=capture):
            for cell in notebook.cells:
                if cell.cell_type!="code" or cell.metadata.get("tags"):
                    continue
                if approve and "selection_lock = lock_rq3_selection" in cell.source:
                    selection_tests.TestPhase11Completion.write_decision(fixture.paths, cfg)
                captured=[]
                stream=io.StringIO()
                with redirect_stdout(stream):
                    exec(compile(cell.source,name,"exec"),scope)
                cell.outputs=[nbformat.v4.new_output("stream",name="stdout",text=stream.getvalue())]+captured
                cell.execution_count=1
        return notebook,scope

    def evidence(self,fixture,notebook,branch):
        directory=os.environ.get("PUBG_PHASE12_EVIDENCE_DIR")
        if not directory:
            return
        destination=Path(directory)/branch
        destination.mkdir(parents=True,exist_ok=True)
        nbformat.write(notebook,destination/"10_fixture.ipynb")
        from nbconvert import HTMLExporter
        html,_=HTMLExporter().from_notebook_node(notebook)
        (destination/"10_fixture.html").write_text(html,encoding="utf-8")
        for key in ["tables","figures","manifests","checkpoints","experiments","models"]:
            shutil.copytree(fixture.paths[key],destination/key,dirs_exist_ok=True)

    def test_real_notebook_core_resume_no_fit_corruption_and_resource(self):
        fixture=core_tests.TestPhaseDPrediction()
        fixture.setUp()
        try:
            cfg=fixture.development_config()
            cfg["rq3"]["evaluation"]["bootstrap"]["replicates"]=40
            cfg["models"]["linear"]["sgd_regressor"]["enabled"]=False
            cfg["models"]["nonlinear_candidates"]["hist_gradient_boosting"]["enabled"]=False
            cfg["features"]["transforms"]["log_transform_features"]=["player_dmg","player_dist_walk"]
            cfg["features"]["transforms"]["add_indicator"]=True
            fixture.paths["interim"]=fixture.root/"interim"
            fixture.paths["interim"].mkdir()
            fixture.df.drop(columns="split").to_parquet(fixture.paths["processed"]/"player_match_features.parquet",index=False)
            fixture.df[["match_id","split"]].drop_duplicates().to_parquet(fixture.paths["interim"]/"split_assignments.parquet",index=False)
            with patch("src.evaluation.comparisons.pd.read_parquet",side_effect=AssertionError("G4 closed")):
                with self.assertRaisesRegex(ValueError,"G4"):
                    comparison_context(fixture.paths,cfg)
            self.execute_notebook(fixture,cfg,"09_rq3_prediction.ipynb",approve=True)
            # Registration completeness fails before any additional final-test evaluation.
            from src.models.rq3_selection import lock_rq3_selection
            decision_file=fixture.paths["manifests"]/"rq3_selection_decision.json"
            decision=read_json(decision_file)
            atomic_write_json(decision_file,{**decision,"comparisons":decision["comparisons"][:2]})
            with self.assertRaisesRegex(ValueError,"comparisons before test"):
                lock_rq3_selection(fixture.paths,cfg)
            atomic_write_json(decision_file,decision)
            with patch("src.models.training.train_and_predict_experiment",side_effect=AssertionError("NB10 must not fit")),patch("src.models.linear.LinearModelWrapper.fit",side_effect=AssertionError("NB10 must not refit")):
                notebook,scope=self.execute_notebook(fixture,cfg,"10_ablation_error_analysis.ipynb")
            result=scope["evaluation"]
            self.assertFalse(result["reused"])
            table=pd.read_csv(result["artifacts"]["comparisons"])
            self.assertEqual(len(table),102)  # 12 pairs, two survival pairs have no team metrics.
            self.assertTrue((table.n_rows==20).all())
            # Independently recompute each observed hierarchical delta from the saved files.
            from src.evaluation.metrics import compute_hierarchical_metrics
            recipe=scope["context"]["recipe"]
            for pair in recipe["decision"]["comparisons"]:
                c=pd.read_parquet(scope["context"]["files"][pair["candidate"]])
                r=pd.read_parquet(scope["context"]["files"][pair["reference"]])
                task=recipe["models"][pair["candidate"]]["task"]
                cm,rm=compute_hierarchical_metrics(c,task),compute_hierarchical_metrics(r,task)
                measured=table.loc[(table.candidate==pair["candidate"])&(table.reference==pair["reference"])]
                for _,row in measured.iterrows():
                    expected=cm[row.aggregation][row.metric]-rm[row.aggregation][row.metric]
                    np.testing.assert_allclose(row.delta,expected,atol=1e-12,equal_nan=True)
            timing=table.loc[(table.candidate=="t1_timing_ols")&(table.metric=="mae")&(table.aggregation=="micro")]
            self.assertEqual(len(timing),1)
            errors=pd.read_csv(result["artifacts"]["errors"])
            for _,group in errors.groupby(["experiment_id","slice_category"]):
                self.assertEqual(group.n_observations.sum(),20)
                self.assertAlmostEqual(group.coverage.sum(),1.)
            residual=pd.read_csv(result["artifacts"]["residuals"])
            self.assertTrue((residual.groupby("experiment_id").n.sum()==20).all())
            catalog=read_json(result["artifacts"]["figure_catalog"])
            self.assertEqual(set(catalog),{"comparisons","ablation","forest","error","coverage","residual","importance"})
            for item in catalog.values():
                self.assertEqual(item["source_sha256"],hash_file(item["source"]))
                self.assertEqual(item["figure_sha256"],hash_file(item["path"]))
                self.assertFalse(item["report_ready"])
            permutation=pd.read_csv(result["artifacts"]["validation_importance"])
            self.assertTrue(permutation.configured_memory_bytes.notna().all())
            self.assertEqual(sum("image/png" in output.get("data",{}) for cell in notebook.cells if cell.cell_type=="code" for output in cell.outputs),7)
            self.evidence(fixture,notebook,"core")
            with patch("src.evaluation.comparisons.load_prediction",side_effect=AssertionError("completed must resume")):
                resumed=run_locked_comparisons(fixture.paths,cfg)
            self.assertTrue(resumed["reused"])
            manager=CheckpointManager(fixture.paths["checkpoints"]/"checkpoint_manifest.json")
            # Corrupt one pair artifact: rerun that pair only, canonical names stay unchanged.
            result["artifacts"]["comparison_000"].write_bytes(b"synthetic corruption")
            from src.evaluation.comparisons import run_paired_match_bootstrap as bootstrap
            with patch("src.evaluation.comparisons.run_paired_match_bootstrap",wraps=bootstrap) as recalculated:
                run_locked_comparisons(fixture.paths,cfg)
            self.assertEqual(recalculated.call_count,1)
            self.assertFalse(any(file.stem.endswith("(1)") for file in fixture.paths["tables"].glob("*.csv")))
            # Failed rerun must not retain completed stage, but preserves good published predictions.
            good=hash_file(scope["context"]["files"]["p2_ols_no_direct_survival"])
            result["artifacts"]["comparison_000"].write_bytes(b"synthetic corruption")
            with patch("src.evaluation.comparisons.load_prediction",side_effect=MemoryError("fixture collect budget")):
                with self.assertRaises(MemoryError):
                    run_locked_comparisons(fixture.paths,cfg)
            self.assertEqual(manager.load_manifest()["stages"]["ablation_error"]["status"],"resource_limited")
            self.assertEqual(good,hash_file(scope["context"]["files"]["p2_ols_no_direct_survival"]))
            run_locked_comparisons(fixture.paths,cfg)
            # Changed saved file invalidates upstream before reading any prediction.
            scope["context"]["files"]["p2_ols_no_direct_survival"].write_bytes(b"bad parquet")
            with patch("src.evaluation.comparisons.pd.read_parquet",side_effect=AssertionError("no stale read")):
                with self.assertRaisesRegex(ValueError,"checkpoint"):
                    comparison_context(fixture.paths,cfg)
        finally:
            fixture.tearDown()

    def test_real_notebook_verified_history_depth_and_constant_r2(self):
        fixture=history_tests.TestHistoryWorkflow()
        fixture.setUp()
        try:
            frame=fixture.frame
            frame["damage_per_kill"]=frame.player_dmg/frame.player_kills
            frame["total_distance"]=frame.player_dist_walk+frame.player_dist_ride
            frame["walk_ratio"]=frame.player_dist_walk/frame.total_distance
            frame["assist_ratio"]=frame.player_assists/(frame.player_assists+frame.player_kills)
            frame["has_kill"]=1
            for name in ["first_kill_time","avg_kill_time"]:
                frame[name]=100.
            for name in ["early_kills","mid_kills","late_kills","early_kill_ratio","mid_kill_ratio","late_kill_ratio"]:
                frame[name]=0.
            frame.to_parquet(fixture.source,index=False)
            for key in ["models","experiments"]:
                fixture.paths[key]=fixture.root/key
                fixture.paths[key].mkdir()
            fixture.cfg["rq3"]["device"]="cpu"
            fixture.cfg["rq3"]["evaluation"]["bootstrap"]["replicates"]=20
            fixture.cfg["models"]["linear"]["sgd_regressor"]["enabled"]=False
            fixture.cfg["models"]["nonlinear_candidates"]["hist_gradient_boosting"]["enabled"]=False
            fixture.complete()
            self.execute_notebook(fixture,fixture.cfg,"09_rq3_prediction.ipynb",approve=True)
            with patch("src.models.training.train_and_predict_experiment",side_effect=AssertionError("no refit")):
                notebook,scope=self.execute_notebook(fixture,fixture.cfg,"10_ablation_error_analysis.ipynb")
            table=pd.read_csv(scope["evaluation_artifacts"]["comparisons"])
            historical=table.loc[table.candidate.isin(["s2_historical_survival","p3_historical_placement"])]
            self.assertEqual(set(historical.n_rows),{4})
            self.assertTrue(historical.loc[historical.metric=="r2","delta"].isna().all())
            import json
            for key,file in scope["evaluation_artifacts"].items():
                if key.startswith("bootstrap_"):
                    # Standard JSON consumers must not see non-standard NaN/Infinity tokens.
                    receipt=json.loads(file.read_text(encoding="utf-8"),parse_constant=lambda token:(_ for _ in ()).throw(AssertionError(token)))
                    self.assertIsNone(receipt["delta_r2"]["ci_lower"])
            errors=pd.read_csv(scope["evaluation_artifacts"]["errors"])
            depth=errors.loc[(errors.experiment_id=="p3_historical_placement")&(errors.slice_category=="history_depth")]
            self.assertEqual(depth.n_observations.sum(),4)
            self.evidence(fixture,notebook,"history")
        finally:
            fixture.tearDown()
