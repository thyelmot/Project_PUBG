import copy
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nbformat
import numpy as np
import pandas as pd
from nbclient import NotebookClient

from src.analysis import choose_clusters
from src.io import Context, digest, read_json, stage_options, time_unit_info
from src.kaggle_runtime import preflight
from src.modeling import validate_automatic_selection
from src.preprocessing import automatic_chronology, ingest
from src.reporting import load_release
from test_data_features import ROOT, fixture, write_config

if os.name=="nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class Automatic(unittest.TestCase):
    def test_chronology_requires_semantics_and_whole_blocks(self):
        meta=pd.DataFrame({"match_time":pd.to_datetime(["2026-01-01","2026-01-02","2026-01-03"]),
                           "dates":1,"bad_dates":0})
        self.assertEqual(automatic_chronology(meta,None)[0],"C")
        self.assertEqual(automatic_chronology(meta,"synthetic dates are match dates")[0],"B")
        meta["match_time"]+=pd.Timedelta(hours=1)
        self.assertEqual(automatic_chronology(meta,"synthetic timestamps")[0],"A")
        meta.loc[0,"bad_dates"]=1
        self.assertEqual(automatic_chronology(meta,"synthetic timestamps")[0],"C")
        meta["bad_dates"]=0;meta["match_time"]=pd.Timestamp("2026-01-01")
        self.assertEqual(automatic_chronology(meta,"synthetic timestamp ties")[0],"C")

    def test_k_selection_ties_overrides_and_invalid_diagnostics(self):
        table=pd.DataFrame({"mode":["Solo"]*3+["Duo"]*2,"k":[4,2,3,2,3],
                            "silhouette":[.4,.4,np.nan,.2,.5],"seed_ari":[1,0,1,1,1]})
        self.assertEqual(choose_clusters(table,{}),{"Duo":3,"Solo":2})
        self.assertEqual(choose_clusters(table,{"Solo":4})["Solo"],4)
        self.assertEqual(choose_clusters(table.sample(frac=1,random_state=7),{}),choose_clusters(table,{}))
        with self.assertRaises(ValueError):choose_clusters(table,{"Solo":5})
        table.loc[table["mode"].eq("Solo"),"silhouette"]=np.nan
        with self.assertRaises(ValueError):choose_clusters(table,{})

    def test_cell_options_are_validated_and_do_not_invalidate_s01(self):
        with tempfile.TemporaryDirectory(prefix="pubg-auto-options-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            ctx.run("S01",ingest)
            signature=ctx.manifest()["S01"]["signature"]
            stage_options(ctx,"S07",{"decision_mode":"auto","minimum_games":10,"clusters":{"Solo":3}})
            self.assertEqual(ctx.cfg["rq2"]["clusters"],{"Solo":3,"Duo":None,"Squad":None})
            self.assertEqual(ctx.require("S01")["signature"],signature)
            good=digest(root/"configs/project.yaml")
            with self.assertRaises(ValueError):stage_options(ctx,"S07",{"device":"invalid"})
            with self.assertRaises(ValueError):stage_options(ctx,"S07",{"clusters":{"Typo":4}})
            self.assertEqual(digest(root/"configs/project.yaml"),good)

    def test_source_facts_are_required_before_unattended_ingest(self):
        with tempfile.TemporaryDirectory(prefix="pubg-auto-preflight-") as folder:
            root=Path(folder);cfg=fixture(root)
            cfg["preprocessing"].update(decision_mode="auto",mode_evidence=None)
            write_config(root,cfg);ctx=Context(root,"development")
            with self.assertRaisesRegex(ValueError,"SOURCE_MODE_EVIDENCE"):preflight(ctx,"S01","S10")
            cfg["preprocessing"]["mode_evidence"]="synthetic fixture only"
            cfg["timing"]["unit_status"]="pending"
            write_config(root,cfg);ctx=Context(root,"development")
            with self.assertRaisesRegex(ValueError,"SOURCE_TIME_UNIT"):preflight(ctx,"S01","S10")
            self.assertFalse((ctx.data/"aggregate.parquet").exists())

    def test_automatic_g4_checks_registered_validation_not_score_threshold(self):
        names={"s1_mean","s1_median","s1_linear","p2_mean","p2_median","p2_linear","t0_linear"}
        records=[{"experiment":name,"split":"validation","aggregation":"micro","n":10,
                  "mae":100,"rmse":200,"r2":-100,"r2_reason":"",
                  "target":"player_survive_time" if name.startswith("s1") else "normalized_placement"} for name in sorted(names)]
        validate_automatic_selection(records,dict.fromkeys(names))
        undefined=copy.deepcopy(records);undefined[0].update(r2=np.nan,r2_reason="constant target")
        validate_automatic_selection(undefined,dict.fromkeys(names))
        for key,value in (("split","test"),("mae",np.nan),("target","wrong"),("r2",np.inf)):
            bad=copy.deepcopy(records);bad[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_automatic_selection(bad,dict.fromkeys(names))
        with self.assertRaises(ValueError):validate_automatic_selection(records[:-1],dict.fromkeys(names))

    def test_actual_auto_runall_reuse_and_report_only(self):
        review=Path(tempfile.mkdtemp(prefix="pubg-auto-review-"))
        with tempfile.TemporaryDirectory(prefix="pubg-auto-notebook-") as folder:
            root=Path(folder);cfg=fixture(root)
            for section in ("preprocessing","features","rq2","rq3"):
                cfg[section]["decision_mode"]="auto"
            cfg["preprocessing"].update(chronology_grade=None,chronology_reason=None,chronology_evidence=None)
            cfg["features"]["transform_reason"]=None
            cfg["rq2"]["minimum_games"]=None
            # Synthetic data exercises the approved status, not real-source evidence.
            cfg["source"]["version"]=3
            cfg["timing"].update(unit_status="assumed_seconds",unit_assumption_approved=True,
                unit_assumption_scope="skihikingkevin/pubg-match-deaths/versions/3",
                unit_evidence="Synthetic fixture: declared seconds to exercise approval/labels; not source evidence")
            write_config(root,cfg)
            template=nbformat.read(ROOT/"notebooks/PUBG_COURSEWORK.ipynb",as_version=4)
            def execute(mode="development",manifest=""):
                nb=copy.deepcopy(template)
                params=next(c for c in nb.cells if c.id=="parameters")
                params.source+=(f"\nALLOW_DATA_PROCESSING=True\nPUBG_PROJECT_ROOT={str(root)!r}\nEXECUTION_MODE={mode!r}\n"
                                f"START_STAGE='S01'\nEND_STAGE='S10'\nRELEASE_MANIFEST={manifest!r}\n"
                                "CODE_INPUT=''\nRESUME_INPUT=''\nRESUME_VERSION=''\nALLOW_CPU_GPU_RESUME=False\nSOURCE_DIRECTORY=''\nSOURCE_LICENSE=''\nRUN_GPU_SMOKE=False\n")
                NotebookClient(nb,timeout=180,kernel_name="python3",resources={"metadata":{"path":str(root.parent)}}).execute()
                nbformat.write(nb,review/(mode+".ipynb"))
                return nb
            execute()
            ctx=Context(root,"development")
            self.assertTrue(all(ctx.manifest()[f"S{i:02d}"]["status"]=="completed" for i in range(1,11)))
            self.assertEqual(read_json(ctx.path("manifests/split.json"))["grade"],"C")
            selected=read_json(ctx.path("manifests/cluster_selection.json"))
            self.assertEqual(selected["minimum_games"],10)
            diagnostic=pd.read_csv(ctx.path("tables/k_diagnostics.csv"))
            self.assertEqual(selected["clusters"],choose_clusters(diagnostic,{}))
            self.assertFalse(selected["outcomes_used"])
            approval=read_json(ctx.path("manifests/selection.json"))
            self.assertTrue(approval["approved"])
            self.assertFalse(approval["test_accessed_at_approval"])
            self.assertEqual(approval["time_unit"]["status"],"assumed_seconds")
            self.assertFalse(approval["time_unit"]["verified"])
            metric_table=pd.read_csv(ctx.path("tables/model_metrics.csv"))
            self.assertTrue(metric_table.time_unit_status.eq("assumed_seconds").all())
            self.assertTrue(metric_table.loc[metric_table.target.eq("player_survive_time"),"target_unit"].str.contains("giả định").all())
            for name in ("eda_statistics","mode_statistics","rq1_relationships","cluster_outcomes","coefficients","error_analysis"):
                table=pd.read_csv(ctx.path("tables/"+name+".csv"))
                self.assertTrue(table.time_unit_status.eq("assumed_seconds").all(),name)
            self.assertTrue((root/"handoff_development.json").is_file())
            hashes={p.name:digest(p) for p in ctx.path("models").glob("*.joblib")}
            execute()
            self.assertEqual(hashes,{p.name:digest(p) for p in ctx.path("models").glob("*.joblib")})
            pointer=read_json(ctx.path("manifests/final_results.json"))
            release=read_json(root/pointer["manifest"])
            self.assertFalse(release["time_unit"]["verified"])
            self.assertTrue(release["time_unit"]["limitation"])
            before={str(p.relative_to(root)):digest(p) for p in root.rglob("*") if p.is_file()}
            execute("report_only",str(root/pointer["manifest"]))
            self.assertEqual(before,{str(p.relative_to(root)):digest(p) for p in root.rglob("*") if p.is_file()})
            # A top-level manifest cannot silently promote the archived assumption.
            import json
            release["time_unit"]["verified"]=True
            (root/pointer["manifest"]).write_text(json.dumps(release),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"time-unit metadata"):
                load_release(root/pointer["manifest"])
        print("AUTO_REVIEW_ROOT="+str(review))

    def test_declared_units_require_approval_evidence_and_exact_source(self):
        with tempfile.TemporaryDirectory(prefix="pubg-declared-unit-") as folder:
            root=Path(folder);cfg=fixture(root)
            cfg["source"]["version"]=3
            cfg["timing"].update(unit_status="assumed_seconds",unit_assumption_approved=True,
                unit_assumption_scope="skihikingkevin/pubg-match-deaths/versions/3",unit_evidence="Synthetic declared seconds")
            unit=time_unit_info(cfg)
            self.assertTrue(unit["accepted"]);self.assertFalse(unit["verified"])
            self.assertIn("giả định",unit["label"])
            write_config(root,cfg);preflight(Context(root,"development"),"S01","S10")
            for section,key,value in (("timing","unit_status","pending"),("timing","unit_assumption_approved",False),
                                      ("timing","unit_evidence","  "),("source","version",4),
                                      ("source","dataset","different/source")):
                broken=copy.deepcopy(cfg);broken[section][key]=value
                self.assertFalse(time_unit_info(broken)["accepted"])
                write_config(root,broken)
                with self.subTest(key=key),self.assertRaisesRegex(ValueError,"SOURCE_TIME_UNIT"):
                    preflight(Context(root,"development"),"S01","S10")

    def test_declared_unit_does_not_rescale_or_drop_player_rows(self):
        from test_data_features import run_features
        from src.features import feature_dictionary
        with tempfile.TemporaryDirectory(prefix="pubg-no-rescale-") as folder:
            root=Path(folder);cfg=fixture(root);cfg["source"]["version"]=3;write_config(root,cfg)
            ctx=run_features(root)
            before={name:pd.read_parquet(ctx.data/(name+".parquet")).sort_values("row_id").reset_index(drop=True)
                    for name in ("base","player_match")}
            raw={p.name:digest(p) for p in (root/"raw_fixture").glob("*.csv")}
            cfg["timing"].update(unit_status="assumed_seconds",unit_assumption_approved=True,
                unit_assumption_scope="skihikingkevin/pubg-match-deaths/versions/3",unit_evidence="Synthetic declared seconds")
            write_config(root,cfg);ctx=run_features(root)
            for name,frame in before.items():
                after=pd.read_parquet(ctx.data/(name+".parquet")).sort_values("row_id").reset_index(drop=True)
                pd.testing.assert_frame_equal(frame,after)
            self.assertEqual(raw,{p.name:digest(p) for p in (root/"raw_fixture").glob("*.csv")})
            audit=pd.read_csv(ctx.path("tables/timing_audit.csv")).iloc[0]
            self.assertFalse(audit.time_unit_verified)
            dictionary=feature_dictionary(time_unit_info(cfg)).set_index("feature")
            self.assertIn("giả định",dictionary.loc["player_survive_time","unit"])
            self.assertEqual(dictionary.loc["player_kills","time_unit_status"],"not_applicable")


if __name__=="__main__":unittest.main()
