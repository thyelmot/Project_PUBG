"""Phase 10 synthetic acceptance, executing the real generated NB08 cells."""
import base64
from contextlib import redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import nbformat
import numpy as np
import pandas as pd
from matplotlib import image as mpimg

from src.data.checkpoints import CheckpointManager
from src.data.io import atomic_write_json, get_duckdb_connection, read_json
from src.features.history_workflow import (FEATURES, diagnostics, publish, history_query,
    require_historical_dataset, literal, illustrative_history, leakage_audit)
from src.features.registry import FeatureRegistry
from src.models.registry import create_canonical_experiment_matrix
from src.models.training import train_and_predict_experiment
from src.models.baselines import TrainMeanRegressor
from src.utils.config import load_config
from src.utils.hashing import hash_file


class TestHistoryWorkflow(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.root=Path(self.directory.name)
        self.project=Path(__file__).resolve().parents[1]
        self.paths={key:self.root/key for key in
            ("processed","interim","tables","figures","manifests","checkpoints","temp_dir")}
        for path in self.paths.values():
            path.mkdir()
        self.cfg=load_config(str(self.project/"configs"))
        self.cfg["runtime"].update(mode="development",duckdb={"threads":1,"memory_limit":"256MB"})
        self.cfg["rq3"]["historical"]["threshold_candidates"]=[1,2,3,50]
        self.availability={"status":"verified","evidence":"Synthetic fixture: match starts and statistics published one hour later",
            "policy":"explicit_columns","timestamp_semantics":"prediction_and_statistic_availability",
            "prediction_column":"prediction_time","available_column":"available_time"}
        self.cfg["rq3"]["historical"]["availability"]=self.availability
        records=[]
        for day in range(6):
            for hour in [10,13]:
                time=pd.Timestamp("2020-01-01",tz="UTC")+pd.Timedelta(days=day,hours=hour)
                for player,mode in [("p1","Solo"),("p2","Duo")]:
                    records.append({"match_id":f"m{day}_{hour}","player_name":player,"team_id":player,
                        "date":time.isoformat(),"prediction_time":time.isoformat(),
                        "available_time":(time+pd.Timedelta(hours=1)).isoformat(),
                        "team_size_mode":mode,"player_kills":2.+day*4+(2 if hour==13 else 0),
                        "player_dmg":100.+day*10,"player_dist_walk":100.+day,
                        "player_dist_ride":0.,"player_assists":1.,"player_dbno":1.,
                        "player_survive_time":300.+day,"normalized_placement":.5})
        self.frame=pd.DataFrame(records)
        self.source=self.paths["processed"]/"player_match_features.parquet"
        self.frame.to_parquet(self.source,index=False,row_group_size=3)
        self.con=get_duckdb_connection(self.paths["temp_dir"],memory_limit="256MB",threads=1)
        self.checkpoint=CheckpointManager(self.paths["checkpoints"]/"checkpoint_manifest.json")
        metadata=self.frame[["match_id","date"]].drop_duplicates().rename(columns={"date":"match_date"})
        self.metadata=self.paths["interim"]/"match_metadata.parquet"
        metadata.to_parquet(self.metadata,index=False)
        self.split=metadata[["match_id"]].assign(split=lambda x:x.match_id.map(
            lambda m:"test" if m.startswith("m5_") else "validation" if m.startswith(("m3_","m4_")) else "train"))
        self.split.to_parquet(self.paths["interim"]/"split_assignments.parquet",index=False)
        self.report={"grade":"Grade B","evidence_grade":"Grade B","null_date_count":0,
            "timezone_normalized":"UTC","has_exact_order_evidence":False,
            "metadata_checksum":hash_file(self.metadata),"source_timestamp_semantics":"synthetic fixture"}
        self.write_report()

    def tearDown(self):
        self.con.close()
        self.directory.cleanup()

    def write_report(self):
        atomic_write_json(self.paths["manifests"]/"chronology_report.json",self.report)

    def receipt(self):
        return diagnostics(self.con,self.cfg,self.paths)[0]

    def choose(self,receipt,threshold=2):
        self.cfg["rq3"]["minimum_history_threshold"]=threshold
        self.cfg["rq3"]["historical"].update(threshold_decision_reason="Synthetic acceptance only; retention/stability reviewed",
            threshold_diagnostics_hash=receipt["diagnostics_hash"],evaluation_protocol="walk_forward_fixed_model")

    def complete(self):
        receipt=self.receipt()
        self.choose(receipt)
        status,artifacts=publish(self.con,self.cfg,self.paths,receipt,self.checkpoint)
        self.assertEqual(status["status"],"completed")
        return status,artifacts

    def test_decision_gate_diagnostics_and_stale_receipts(self):
        receipt=self.receipt()
        retention=pd.read_csv(self.paths["tables"]/"history_coverage.csv")
        self.assertEqual(retention.total_rows.unique().tolist(),[20])  # 4 final-test rows excluded.
        stability=pd.read_csv(self.paths["tables"]/"history_stability.csv")
        self.assertEqual(set(stability.feature),{v[1] for k,v in FEATURES.items() if k not in {"survival","placement"}})
        self.assertGreater(stability.valid_transitions.max(),0)
        status,artifacts=publish(self.con,self.cfg,self.paths,receipt,self.checkpoint)
        self.assertEqual(status["reason_code"],"minimum_history_threshold_pending")
        self.assertNotIn("historical_features",artifacts)
        self.assertEqual(self.checkpoint.load_manifest()["stages"]["historical_feasibility"]["status"],"completed")
        self.choose(receipt)
        self.cfg["rq3"]["historical"]["evaluation_protocol"]=None
        status,_=publish(self.con,self.cfg,self.paths,receipt,self.checkpoint)
        self.assertEqual(status["reason_code"],"historical_evaluation_protocol_pending")
        self.cfg["rq3"]["historical"]["evaluation_protocol"]="walk_forward_fixed_model"
        # Test outcome/behavior changes do not affect diagnostic numbers.
        before=retention.copy()
        changed=self.frame.copy()
        changed.loc[changed.match_id.str.startswith("m5_"),["player_kills","player_dmg","player_survive_time"]]=999.
        changed.to_parquet(self.source,index=False)
        receipt2=self.receipt()
        pd.testing.assert_frame_equal(before,pd.read_csv(self.paths["tables"]/"history_coverage.csv"))
        status,_=publish(self.con,self.cfg,self.paths,receipt2,self.checkpoint)
        self.assertEqual(status["reason_code"],"threshold_decision_receipt_pending_or_stale")
        self.choose(receipt2)
        path=self.paths["tables"]/"history_stability.csv"
        path.write_bytes(path.read_bytes()+b"\n")
        with self.assertRaisesRegex(ValueError,"Stale diagnostic table"):
            publish(self.con,self.cfg,self.paths,receipt2,self.checkpoint)

    def test_grade_c_and_unverified_availability_never_make_fake_dataset(self):
        status,artifacts=self.complete()
        output=self.paths["processed"]/"historical_player_match_features.parquet"
        old=hash_file(output)
        self.checkpoint.commit("rq3_prediction","fixture",{"old_history":output})
        self.report.update(grade="Grade C",evidence_grade="Grade C")
        self.write_report()
        registry=create_canonical_experiment_matrix()
        receipt=self.receipt()
        blocked,artifacts=publish(self.con,self.cfg,self.paths,receipt,self.checkpoint,registry)
        self.assertEqual(blocked["reason_code"],"blocked_by_chronology")
        self.assertNotIn("historical_features",artifacts)
        self.assertEqual(hash_file(output),old)  # Preserve old bytes; status prevents use.
        for task in ["s2_historical_survival","p3_historical_placement"]:
            self.assertEqual(registry.get(task).status,"blocked")
        self.assertTrue(all(e.status=="planned" for e in registry.list_all() if e.task in {"s1","p1","p2"}))
        self.assertEqual(self.checkpoint.load_manifest()["stages"]["rq3_prediction"]["status"],"stale")
        with self.assertRaisesRegex(ValueError,"blocked_by_chronology"):
            require_historical_dataset(self.paths,self.cfg)
        self.report.update(grade="Grade B",evidence_grade="Grade B")
        self.write_report()
        self.cfg["rq3"]["historical"]["availability"]["status"]="pending"
        receipt=self.receipt()
        status,_=publish(self.con,self.cfg,self.paths,receipt,self.checkpoint)
        self.assertEqual(status["reason_code"],"blocked_by_availability")

    def test_input_chronology_and_consumer_integrity(self):
        self.complete()
        require_historical_dataset(self.paths,self.cfg)
        changed_scope=copy.deepcopy(self.cfg)
        changed_scope["runtime"]["mode"]="full"
        with self.assertRaisesRegex(ValueError,"scope mismatch"):
            require_historical_dataset(self.paths,changed_scope)
        changed_cfg=copy.deepcopy(self.cfg)
        changed_cfg["rq3"]["minimum_history_threshold"]=3
        with self.assertRaisesRegex(ValueError,"code/config"):
            require_historical_dataset(self.paths,changed_cfg)
        self.report["grade"]="Grade A"
        self.write_report()
        with self.assertRaisesRegex(ValueError,"exact-order evidence"):
            self.receipt()
        with self.assertRaisesRegex(ValueError,"chronology_checksum"):
            require_historical_dataset(self.paths,self.cfg)
        self.report["grade"]="Grade B"
        self.report["metadata_checksum"]="wrong"
        self.write_report()
        with self.assertRaisesRegex(ValueError,"Stale chronology"):
            self.receipt()
        self.report["metadata_checksum"]=hash_file(self.metadata)
        self.write_report()
        changed=self.frame.copy()
        changed.loc[0,"date"]="2019-01-01T00:00:00Z"
        changed.to_parquet(self.source,index=False)
        with self.assertRaisesRegex(ValueError,"mismatch"):
            self.receipt()

    def test_strict_availability_overlap_ties_timezone_and_mutation(self):
        demo=illustrative_history(self.con,self.paths["temp_dir"])
        for grade,expected_counts,expected_mean in [
            ("Grade A",[0,0,2,3],[np.nan,np.nan,3.,14/3]),
            ("Grade B",[0,0,0,3],[np.nan,np.nan,np.nan,14/3])]:
            actual=demo[demo.chronology_grade==grade]
            self.assertEqual(actual.hist_games_played.tolist(),expected_counts)
            np.testing.assert_allclose(actual.hist_kills_mean,expected_mean,equal_nan=True)
        def evaluate(frame,grade="Grade B"):
            frame.to_parquet(self.source,index=False,row_group_size=2)
            query=history_query(self.con,self.source,grade,1,self.availability)
            return self.con.execute(f"SELECT * FROM ({query})").df().sort_values(["match_id","player_name"]).reset_index(drop=True)
        original=evaluate(self.frame)
        # Shuffle simulates processed rows merged from shuffled source shards.
        shuffled=evaluate(self.frame.sample(frac=1,random_state=13))
        pd.testing.assert_frame_equal(original,shuffled)
        changed=self.frame.copy()
        mask=changed.match_id.str.startswith(("m3_","m4_","m5_"))
        changed.loc[mask,["player_kills","player_survive_time","normalized_placement"]]=0.
        mutated=evaluate(changed)
        cols=[c for c in original if c.startswith("hist_")]
        pd.testing.assert_frame_equal(original.loc[original.match_id.str.startswith("m3_"),cols],
                                     mutated.loc[mutated.match_id.str.startswith("m3_"),cols])
        # A: previous match still running at next prediction; do not include its outcome.
        overlap=self.frame.copy()
        overlap.loc[overlap.match_id=="m0_10","available_time"]="2020-01-01T14:00:00Z"
        a=evaluate(overlap,"Grade A")
        self.assertEqual(a.loc[a.match_id=="m0_13","hist_games_played"].tolist(),[0,0])
        # Same instant in a different timezone must be an excluded tie block.
        tie=self.frame.copy()
        tie.loc[tie.match_id=="m0_13",["date","prediction_time"]]="2020-01-01T17:00:00+07:00"
        tie.loc[tie.match_id=="m0_13","available_time"]="2020-01-01T18:00:00+07:00"
        a=evaluate(tie,"Grade A")
        self.assertTrue((a[a.match_id.str.startswith("m0_")].hist_games_played==0).all())
        # Updating validation history changes later test history without fitting a model.
        latest=original.loc[original.match_id=="m5_10","hist_kills_mean"].to_numpy()
        modified=self.frame.copy()
        modified.loc[modified.match_id=="m4_13","player_kills"]+=10
        next_history=evaluate(modified)
        np.testing.assert_allclose(next_history.loc[next_history.match_id=="m5_10","hist_kills_mean"],latest+1.)

    def test_counts_missing_identity_no_eligible_and_registry(self):
        data=self.frame.copy()
        data.loc[0,"player_kills"]=np.nan
        extra=data.iloc[[1]].assign(player_name=" ",team_id="unnamed")
        data=pd.concat([data,extra],ignore_index=True)
        data.to_parquet(self.source,index=False)
        receipt=self.receipt()
        identity=pd.read_csv(self.paths["tables"]/"history_identity_exclusions.csv").iloc[0]
        self.assertEqual(identity.excluded_identity_rows,1)
        self.choose(receipt)
        status,_=publish(self.con,self.cfg,self.paths,receipt,self.checkpoint)
        history=pd.read_parquet(self.paths["processed"]/"historical_player_match_features.parquet")
        row=history[(history.match_id=="m1_10") & (history.player_name=="p1")].iloc[0]
        self.assertEqual((row.hist_games_played,row.hist_kills_count,row.hist_damage_count),(2,1,2))
        self.assertEqual(row.hist_kills_mean,4.)
        cold=history[history.hist_games_played==0]
        self.assertTrue(cold[[v[1] for v in FEATURES.values()]].isna().all().all())
        registry=FeatureRegistry()
        self.assertEqual(registry.get("hist_kd").status,"candidate")
        self.assertNotIn("hist_kd",registry.get_allowed_features("s2"))
        self.choose(receipt,50)
        status,_=publish(self.con,self.cfg,self.paths,receipt,self.checkpoint)
        self.assertEqual(status["reason_code"],"no_eligible_history")
        with self.assertRaisesRegex(ValueError,"no_eligible_history"):
            require_historical_dataset(self.paths,self.cfg)
        with self.assertRaisesRegex(ValueError,"verified NB08"):
            train_and_predict_experiment(pd.DataFrame(),["hist_kills_mean"],"current_survive_time",TrainMeanRegressor(),"fixture",task="s2")

    def test_start_duration_policy_and_corrupted_audit(self):
        data=self.frame.copy()
        data["verified_match_duration"]=3600.
        data.to_parquet(self.source,index=False)
        policy={"status":"verified","evidence":"Synthetic match duration exactly one hour",
            "policy":"start_plus_verified_duration","timestamp_semantics":"match_start",
            "duration_column":"verified_match_duration","duration_unit":"seconds"}
        query=history_query(self.con,self.source,"Grade A",1,policy)
        history=self.con.execute(query).df()
        self.assertEqual(history.loc[history.match_id=="m0_13","hist_games_played"].tolist(),[1,1])
        policy["duration_column"]="player_survive_time"
        with self.assertRaisesRegex(ValueError,"not match completion"):
            history_query(self.con,self.source,"Grade A",1,policy)
        history.loc[history.hist_games_played>0,"max_history_available_at"]=history.loc[history.hist_games_played>0,"history_cutoff"]
        out=self.root/"corrupt.parquet"
        history.to_parquet(out,index=False)
        self.assertGreater(leakage_audit(self.con,out).observed_violations.sum(),0)

    def test_reuse_and_failure_preserve_verified_bytes(self):
        status,artifacts=self.complete()
        output=artifacts["historical_features"]
        old=hash_file(output)
        with patch("src.features.history_workflow.history_query",side_effect=AssertionError("must reuse")):
            receipt=self.receipt()
            reused,_=publish(self.con,self.cfg,self.paths,receipt,self.checkpoint)
            self.assertEqual(reused["signature"],status["signature"])
        self.choose(receipt,3)
        with patch("src.features.history_workflow.copy_query_to_parquet",side_effect=MemoryError("synthetic spill exhaustion")):
            with self.assertRaisesRegex(MemoryError,"spill exhaustion"):
                publish(self.con,self.cfg,self.paths,receipt,self.checkpoint)
        failed=read_json(self.paths["manifests"]/"historical_status.json")
        self.assertEqual(failed["status"],"resource_limited")
        self.assertEqual(hash_file(output),old)
        with self.assertRaisesRegex(ValueError,"historical_build_failed"):
            require_historical_dataset(self.paths,self.cfg)
        # Retry uses the same canonical name and recovers from blocked task records.
        recovered,_=publish(self.con,self.cfg,self.paths,receipt,self.checkpoint)
        self.assertEqual(recovered["status"],"completed")
        require_historical_dataset(self.paths,self.cfg)
        self.assertEqual(len(list(output.parent.glob("historical_player_match_features*"))),1)
        stages=self.checkpoint.load_manifest()["stages"]
        for task in ["s2_historical_survival","p3_historical_placement"]:
            self.assertEqual(stages[task]["status"],"planned")

    def test_real_notebook_cells_null_selected_and_grade_c(self):
        notebook=nbformat.read(self.project/"notebooks/08_build_historical.ipynb",as_version=4)
        for branch in ["null","selected","selected_a","grade_c"]:
            with self.subTest(branch=branch):
                self.cfg["rq3"]["minimum_history_threshold"]=None
                if branch=="selected_a":
                    self.report.update(grade="Grade A",has_exact_order_evidence=True)
                    self.write_report()
                if branch.startswith("selected"):
                    self.choose(self.receipt())
                elif branch=="grade_c":
                    self.report.update(grade="Grade C",evidence_grade="Grade C")
                    self.write_report()
                scope={"paths":self.paths,"PROJECT_ROOT":self.project}
                executed=copy.deepcopy(notebook)
                displayed=[]
                current_outputs=[]
                def capture(value):
                    displayed.append(value)
                    if isinstance(value,pd.DataFrame):
                        current_outputs.append(nbformat.v4.new_output("display_data",data={"text/html":value.to_html(index=False),"text/plain":value.to_string(index=False)}))
                    elif value.__class__.__name__=="Image":
                        current_outputs.append(nbformat.v4.new_output("display_data",data={"image/png":base64.b64encode(value.data).decode()}))
                    elif value.__class__.__name__=="Markdown":
                        current_outputs.append(nbformat.v4.new_output("display_data",data={"text/markdown":value.data}))
                with patch("src.utils.config.load_config",return_value=self.cfg),patch("src.utils.config.resolve_paths",return_value=self.paths), \
                     patch("IPython.display.display",side_effect=capture):
                    for cell in executed.cells:
                        if cell.cell_type!="code" or cell.metadata.get("tags"):
                            continue  # No Colab/network/bootstrap/All-in-One; isolated pre-established storage.
                        current_outputs=[]
                        stream=io.StringIO()
                        with redirect_stdout(stream):
                            exec(compile(cell.source,"NB08-synthetic", "exec"),scope)
                        cell.outputs=[nbformat.v4.new_output("stream",name="stdout",text=stream.getvalue())]+current_outputs
                        cell.execution_count=1
                status=read_json(self.paths["manifests"]/"historical_status.json")
                self.assertEqual(status["status"],{"null":"pending","selected":"completed","selected_a":"completed","grade_c":"blocked"}[branch])
                record=self.checkpoint.load_manifest()["stages"]["notebook/08_build_historical.ipynb"]
                self.assertEqual(record["status"],"completed")  # Notebook feasibility, not model training.
                self.assertEqual("historical_features" in record["artifacts"],branch.startswith("selected"))
                catalog=pd.read_csv(self.paths["tables"]/"history_figure_catalog.csv")
                self.assertEqual(set(catalog.figure_id),{"08-01","08-02","08-03","08-04","08-05"} if branch.startswith("selected") else {"08-04"} if branch=="grade_c" else {"08-01","08-02","08-03","08-04"})
                self.assertTrue(catalog[["caption","how_to_read","limitation","source_table"]].notna().all().all())
                for _,row in catalog.iterrows():
                    self.assertTrue(Path(row.source_table).exists())
                    image=mpimg.imread(row.path)
                    self.assertGreater(min(image.shape[:2]),400)
                    self.assertTrue(np.isfinite(image).all())
                self.assertGreaterEqual(sum(isinstance(v,pd.DataFrame) for v in displayed),10)
                self.assertEqual(sum(v.__class__.__name__=="Image" for v in displayed),len(catalog))
                evidence=os.environ.get("PUBG_HISTORY_EVIDENCE_DIR")
                if evidence:
                    dest=Path(evidence)/branch
                    dest.mkdir(parents=True,exist_ok=True)
                    nbformat.write(executed,dest/"08_fixture.ipynb")
                    from nbconvert import HTMLExporter
                    html,_=HTMLExporter().from_notebook_node(executed)
                    (dest/"08_fixture.html").write_text(html,encoding="utf-8")
                    for name in ["tables","figures","manifests","checkpoints","processed","interim"]:
                        shutil.copytree(self.paths[name],dest/name,dirs_exist_ok=True)
                # Clean runtime objects; notebook closed its own connection, not setUp's.
                self.assertIn("BẢNG 08-K", "\n".join(c.source for c in executed.cells))

    def test_historical_handoff_fits_once_on_train_not_test(self):
        self.complete()
        frame=pd.read_parquet(require_historical_dataset(self.paths,self.cfg)).merge(self.split,on="match_id",validate="many_to_one")
        frame=frame[frame.has_sufficient_history].copy()
        for task,target in [("s2","current_survive_time"),("p3","current_normalized_placement")]:
            model=TrainMeanRegressor()
            with patch.object(model,"fit",wraps=model.fit) as fit:
                _,predictions=train_and_predict_experiment(frame,["hist_kills_mean"],target,model,
                    "synthetic_fixed_model",task=task,historical_paths=self.paths,historical_config=self.cfg,batch_size=3)
                self.assertEqual(fit.call_count,1)
                np.testing.assert_array_equal(fit.call_args.args[1],frame.loc[frame.split=="train",target])
                self.assertEqual(len(predictions),len(frame))
                self.assertTrue((predictions.predicted==frame.loc[frame.split=="train",target].mean()).all())
            changed=frame.copy()
            # Mutate within each target's valid domain; out-of-range placement is excluded by contract.
            changed.loc[changed.split=="test",target]=10000. if task=="s2" else .75
            _,other=train_and_predict_experiment(changed,["hist_kills_mean"],target,TrainMeanRegressor(),
                "synthetic_changed_test_labels",task=task,historical_paths=self.paths,historical_config=self.cfg)
            np.testing.assert_array_equal(predictions.predicted,other.predicted)


if __name__=="__main__":
    unittest.main()
