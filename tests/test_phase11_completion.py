"""Phase 11 real NB08 handoff and resource/resume invariants, isolated CPU fixtures."""
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import json
from pathlib import Path
import test_history_workflow as history_tests
import test_phase_d_prediction as core_tests
from src.models.training import run_rq3_prediction_suite


class TestPhase11Completion(unittest.TestCase):
    @staticmethod
    def write_decision(paths, cfg):
        from src.utils.hashing import hash_file, hash_dict
        from src.data.io import read_json, atomic_write_json
        registry=read_json(paths["manifests"]/"rq3_development_registry.json")["experiments"]
        selected=[key for key,record in registry.items() if record["status"]=="completed"]
        decision={"approved":True,"approved_by":"synthetic fixture reviewer; NOT production approval",
            "data_scope":"Synthetic fixture CPU, không phải kết quả PUBG",
            "descriptive_design":{"rq1":"full_descriptive_locked","no_reselection":True,
                "rq2_config_hash":hash_dict(cfg['rq2'])},
            "fit_protocol":"fit_train_only","selected_experiments":selected,
            "features_by_experiment":{key:read_json(paths["models"]/f"meta_{key}.json")["features"] for key in selected},
            "registry_hash":hash_file(paths["manifests"]/"rq3_development_registry.json"),
            "validation_hash":hash_file(paths["tables"]/"rq3_development_validation.csv"),
            "diagnostics_hash":read_json(paths["manifests"]/"rq3_feature_diagnostics_receipt.json")["diagnostics_hash"],
            "error_bins":{"survival":[0,100,1000,10000],"placement":[0,.25,.5,.75,1],"history_depth":[0,2,5,100]},
            "comparisons":[{"reference":"p1_ols_direct_survival","candidate":"p2_ols_no_direct_survival"},
                           {"reference":"t0_timing_ols","candidate":"t1_timing_ols"}],
            "selection_reasons":{key:"Fixture verifies receipt structure only; no real scientific selection." for key in ["performance","generalization","interpretability","stability","compute"]},
            "prior_test_exposure":"synthetic test only; real prior exposure unknown"}
        main={"s1":"s1_retrospective_survival","p1":"p1_ols_direct_survival","p2":"p2_ols_no_direct_survival","s2":"s2_historical_survival","p3":"p3_historical_placement"}
        for task,model in main.items():
            if model in selected:
                decision["comparisons"].extend({"reference":f"{task}_baseline_{kind}","candidate":model} for kind in ["mean","median"])
        decision["comparisons"].extend({"reference":"p2_ols_no_direct_survival","candidate":key} for key in selected if "_validation_ablation_" in key)
        atomic_write_json(paths["manifests"]/"rq3_selection_decision.json",decision)
        return decision

    def test_explicit_g4_real_notebook_and_stale_guard(self):
        import nbformat, io, os, base64, shutil
        from contextlib import redirect_stdout
        from src.models.rq3_selection import lock_rq3_selection, evaluate_locked_test
        from src.data.io import atomic_write_json
        fixture=core_tests.TestPhaseDPrediction()
        fixture.setUp()
        try:
            cfg=fixture.development_config()
            cfg["models"]["linear"]["sgd_regressor"]["max_iter"]=15
            cfg["models"]["nonlinear_candidates"]["hist_gradient_boosting"]["max_iter"]=3
            fixture.paths["interim"]=fixture.root/"data/interim"
            fixture.paths["interim"].mkdir(parents=True)
            fixture.df.drop(columns="split").to_parquet(fixture.paths["processed"]/"player_match_features.parquet",index=False)
            fixture.df[["match_id","split"]].drop_duplicates().to_parquet(fixture.paths["interim"]/"split_assignments.parquet",index=False)
            self.assertIsNone(lock_rq3_selection(fixture.paths,cfg))
            with self.assertRaisesRegex(ValueError,"closed"):
                evaluate_locked_test(fixture.paths,cfg,None)
            project=Path(__file__).resolve().parents[1]
            notebook=nbformat.read(project/"notebooks/09_rq3_prediction.ipynb",as_version=4)
            scope={"paths":fixture.paths,"PROJECT_ROOT":project}
            outputs=[]
            def capture(value):
                if isinstance(value,pd.DataFrame):
                    outputs.append(nbformat.v4.new_output("display_data",data={"text/html":value.to_html(index=False),"text/plain":value.to_string(index=False)}))
                elif value.__class__.__name__=="Image":
                    outputs.append(nbformat.v4.new_output("display_data",data={"image/png":base64.b64encode(value.data).decode()}))
                elif value.__class__.__name__=="Markdown":
                    outputs.append(nbformat.v4.new_output("display_data",data={"text/markdown":value.data}))
            with patch("src.utils.config.load_config",return_value=cfg),patch("src.utils.config.resolve_paths",return_value=fixture.paths),patch("IPython.display.display",side_effect=capture):
                for cell in notebook.cells:
                    if cell.cell_type!="code" or cell.metadata.get("tags"):
                        continue
                    outputs=[]
                    if "selection_lock = lock_rq3_selection" in cell.source:
                        self.write_decision(fixture.paths, cfg)
                    stream=io.StringIO()
                    with redirect_stdout(stream):
                        exec(compile(cell.source,"NB09-approved-fixture","exec"),scope)
                    cell.outputs=[nbformat.v4.new_output("stream",name="stdout",text=stream.getvalue())]+outputs
                    cell.execution_count=1
            self.assertEqual(scope["res"]["status"],"completed")
            for task in ["p1","p2"]:
                pred=pd.read_parquet(fixture.paths["experiments"]/f"predictions_{task}_linear.parquet")
                self.assertEqual(set(pred.split),{"test"})
                self.assertEqual(len(pred),20)
                self.assertTrue(pred.recipe_hash.notna().all())
            recipe=scope["selection_lock"]
            with patch("src.models.rq3_selection.get_duckdb_connection",side_effect=AssertionError("must not open test")):
                with self.assertRaisesRegex(ValueError,"Corrupt"):
                    evaluate_locked_test(fixture.paths,cfg,{**recipe,"recipe_hash":"bad"})
            with patch("src.models.training.train_and_predict_experiment",side_effect=AssertionError("must not fit")):
                table,_=evaluate_locked_test(fixture.paths,cfg,recipe,batch_size=3)
            self.assertTrue((table.n==20).all())
            source=fixture.paths["processed"]/"player_match_features.parquet"
            changed=pd.read_parquet(source)
            changed.loc[0,"player_kills"]+=1
            changed.to_parquet(source,index=False)
            with patch("src.models.rq3_selection.get_duckdb_connection",side_effect=AssertionError("must not open test")):
                with self.assertRaisesRegex(ValueError,"dataset/split changed"):
                    evaluate_locked_test(fixture.paths,cfg,recipe)
            with self.assertRaisesRegex(ValueError,"changed after fitting"):
                lock_rq3_selection(fixture.paths,cfg)
            evidence=os.environ.get("PUBG_PHASE11_EVIDENCE_DIR")
            if evidence:
                destination=Path(evidence)/"approved_g4"
                destination.mkdir(parents=True,exist_ok=True)
                nbformat.write(notebook,destination/"09_fixture.ipynb")
                from nbconvert import HTMLExporter
                html,_=HTMLExporter().from_notebook_node(notebook)
                (destination/"09_fixture.html").write_text(html,encoding="utf-8")
                for key in ["figures","tables","manifests","checkpoints"]:
                    shutil.copytree(fixture.paths[key],destination/key,dirs_exist_ok=True)
        finally:
            fixture.tearDown()

    def test_streaming_statistics_all_rows_and_reproducibility(self):
        from src.models.streaming import StreamingSGDWrapper
        frame=pd.DataFrame({"x":[1.,np.nan,3.,4.,100.],"all_missing":[np.nan]*5,"y":[1.,2.,3.,4.,5.]})
        validation=pd.DataFrame({"x":[2.,3.],"all_missing":[np.nan]*2,"y":[2.,3.]})
        params={"batch_size":2,"max_iter":8,"random_state":19,"add_indicator":True}
        a=StreamingSGDWrapper(**params).fit_frame(frame,validation,["x","all_missing"],"y")
        b=StreamingSGDWrapper(**params).fit_frame(frame,validation,["x","all_missing"],"y")
        np.testing.assert_allclose(a.means_,[27.,0.])
        np.testing.assert_allclose(a.predict(validation[["x","all_missing"]]),b.predict(validation[["x","all_missing"]]))
        self.assertTrue(all(row["train_rows_seen"]==5 for row in a.epoch_history_))
        self.assertEqual(len(a.coefficient_names()),4)
        self.assertEqual(a.scaler_.n_samples_seen_,5)

    def test_metrics_and_mean_indicator_pipeline(self):
        from src.evaluation.metrics import compute_regression_metrics, compute_hierarchical_metrics
        from src.models.linear import LinearModelWrapper
        x=np.array([[1.,np.nan],[np.nan,np.nan],[3.,np.nan]])
        model=LinearModelWrapper(add_indicator=True).fit(x,np.array([1.,2.,3.]))
        np.testing.assert_allclose(model.pipeline.named_steps["imputer"].statistics_,[2.,0.])
        self.assertEqual(len(model.coefficients),4)
        constant=compute_regression_metrics(np.array([1.,1.]),np.array([0.,0.]))
        self.assertTrue(np.isnan(constant["r2"]))
        self.assertEqual(constant["r2_reason"],"zero_target_variance")
        self.assertEqual(compute_regression_metrics(np.array([1.,1.+1e-7]),np.array([1.,1.+1e-7]))["r2"],1.)
        with self.assertRaisesRegex(ValueError,"Non-finite"):
            compute_regression_metrics(np.array([1.]),np.array([np.inf]))
        pred=pd.DataFrame({"match_id":["a","a","b"],"team_id":["x","x","y"],"actual":[0.,0.,1.],"predicted":[.2,.4,.8]})
        measured=compute_hierarchical_metrics(pred,task="p2")
        self.assertAlmostEqual(measured["match_aware"]["r2"],1-(.5*(.04+.16)+.04)/.5)
        pred.loc[1,"actual"]=.5
        with self.assertRaisesRegex(ValueError,"Conflicting"):
            compute_hierarchical_metrics(pred,task="p2")

    def test_verified_history_candidates_and_stale_block(self):
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
            for key in ["experiments","models"]:
                fixture.paths[key]=fixture.root/key
                fixture.paths[key].mkdir()
            fixture.cfg["rq3"]["device"]="cpu"
            fixture.cfg["models"]["nonlinear_candidates"]["hist_gradient_boosting"]["enabled"]=False
            fixture.complete()
            from src.models.training import load_rq3_development_data
            current=load_rq3_development_data(fixture.paths)
            result=run_rq3_prediction_suite(current,fixture.paths,config=fixture.cfg,device="cpu",chronology_grade="Grade B")
            for task in ["s2","p3"]:
                for kind in ["baseline_mean","baseline_median","historical_survival" if task=="s2" else "historical_placement"]:
                    exp_id=f"{task}_{kind}"
                    pred=pd.read_parquet(result["predictions"][exp_id])
                    self.assertEqual(set(pred.split),{"train","validation"})
                    self.assertTrue((pred.hist_games_played >= 2).all())
                    self.assertTrue(pred.run_id.notna().all())
                    self.assertEqual(result["experiment_status_table"].set_index("experiment_id").loc[exp_id,"status"],"completed")
            # Execute the actual consumer notebook against the verified producer, not only its module.
            import nbformat, io, os, base64, shutil
            from contextlib import redirect_stdout
            project=Path(__file__).resolve().parents[1]
            notebook=nbformat.read(project/"notebooks/09_rq3_prediction.ipynb",as_version=4)
            scope={"paths":fixture.paths,"PROJECT_ROOT":project}
            outputs=[]
            def capture(value):
                if isinstance(value,pd.DataFrame):
                    outputs.append(nbformat.v4.new_output("display_data",data={"text/html":value.to_html(index=False),"text/plain":value.to_string(index=False)}))
                elif value.__class__.__name__=="Image":
                    outputs.append(nbformat.v4.new_output("display_data",data={"image/png":base64.b64encode(value.data).decode()}))
                elif value.__class__.__name__=="Markdown":
                    outputs.append(nbformat.v4.new_output("display_data",data={"text/markdown":value.data}))
            with patch("src.utils.config.load_config",return_value=fixture.cfg),patch("src.utils.config.resolve_paths",return_value=fixture.paths),patch("IPython.display.display",side_effect=capture):
                for cell in notebook.cells:
                    if cell.cell_type!="code" or cell.metadata.get("tags"):
                        continue
                    outputs=[]
                    stream=io.StringIO()
                    with redirect_stdout(stream):
                        exec(compile(cell.source,"NB09-history-fixture","exec"),scope)
                    cell.outputs=[nbformat.v4.new_output("stream",name="stdout",text=stream.getvalue())]+outputs
                    cell.execution_count=1
            self.assertEqual(scope["res"]["status"],"pending_selection")
            self.assertIn("p3_historical_placement",scope["res"]["models"])
            evidence=os.environ.get("PUBG_PHASE11_EVIDENCE_DIR")
            if evidence:
                destination=Path(evidence)/"history"
                destination.mkdir(parents=True,exist_ok=True)
                nbformat.write(notebook,destination/"09_fixture.ipynb")
                from nbconvert import HTMLExporter
                html,_=HTMLExporter().from_notebook_node(notebook)
                (destination/"09_fixture.html").write_text(html,encoding="utf-8")
                for key in ["figures","tables","manifests","checkpoints"]:
                    shutil.copytree(fixture.paths[key],destination/key,dirs_exist_ok=True)
            fixture.cfg["rq3"]["minimum_history_threshold"]=3
            stale=run_rq3_prediction_suite(current,fixture.paths,config=fixture.cfg,device="cpu",chronology_grade="Grade B")
            matrix=stale["experiment_status_table"]
            blocked=matrix[matrix.task.isin(["s2","p3"])]
            self.assertTrue((blocked.status=="blocked").all())
            self.assertTrue(blocked.reason_code.notna().all())
        finally:
            fixture.tearDown()

    def test_timing_pair_config_and_resume_resource_limit(self):
        fixture=core_tests.TestPhaseDPrediction()
        fixture.setUp()
        try:
            cfg=fixture.development_config()
            cfg["models"]["linear"]["exact_linear"]["fit_intercept"]=False
            cfg["features"]["transforms"]["standardize"]=False
            cfg["models"]["nonlinear_candidates"]["hist_gradient_boosting"].update(max_iter=3,random_state=19)
            result=run_rq3_prediction_suite(fixture.df,fixture.paths,config=cfg,device="cpu",batch_size=7)
            self.assertFalse(result["models"]["p2_ols_no_direct_survival"].fit_intercept)
            self.assertEqual(result["models"]["p2_ols_no_direct_survival"].pipeline.named_steps["scaler"],"passthrough")
            self.assertEqual(result["models"]["p2_hgb_nonlinear_candidate"].model.max_iter,3)
            self.assertEqual(result["models"]["p2_hgb_nonlinear_candidate"].model.random_state,19)
            pd.testing.assert_frame_equal(pd.read_parquet(result["predictions"]["t0_timing_ols"])[["row_id","split","actual"]],
                                          pd.read_parquet(result["predictions"]["t1_timing_ols"])[["row_id","split","actual"]])
            with patch("src.models.training.train_and_predict_experiment",side_effect=AssertionError("must resume")):
                reused=run_rq3_prediction_suite(fixture.df,fixture.paths,config=cfg,device="cpu",batch_size=7)
            self.assertTrue((reused["resource_table"].execution=="compatible_resume").all())
            from src.utils.hashing import hash_file
            from src.models.training import train_and_predict_experiment
            model_file=fixture.paths["models"]/"p2_ols_no_direct_survival.joblib"
            model_file.write_bytes(b"synthetic corruption")
            with patch("src.models.training.train_and_predict_experiment",wraps=train_and_predict_experiment) as fitted:
                run_rq3_prediction_suite(fixture.df,fixture.paths,config=cfg,device="cpu",batch_size=7)
            self.assertEqual(fitted.call_count,1)
            self.assertEqual(fitted.call_args.args[4],"p2_ols_no_direct_survival")
            before=hash_file(model_file)
            cfg["models"]["linear"]["exact_linear"]["fit_intercept"]=True
            with patch("src.models.training.train_and_predict_experiment",side_effect=MemoryError("synthetic fit OOM")):
                oom=run_rq3_prediction_suite(fixture.df,fixture.paths,config=cfg,device="cpu",batch_size=7)
            self.assertEqual(hash_file(model_file),before)
            self.assertEqual(len(oom["models"]),0)
            self.assertTrue((oom["resource_table"].status=="resource_limited").all())
            cfg["models"]["resource_limits"]["max_memory_gb"]=1e-12
            limited=run_rq3_prediction_suite(fixture.df,fixture.paths,config=cfg,device="cpu")
            self.assertEqual(len(limited["models"]),0)
            statuses=limited["experiment_status_table"]
            self.assertTrue((statuses[statuses.task.isin(["s1","p1","p2"]) & statuses.experiment_id.isin(result["models"])].status=="resource_limited").all())
            self.assertFalse(any("test" in str(row) for row in limited["val_metrics"].values()))
        finally:
            fixture.tearDown()


if __name__=="__main__":
    unittest.main()
