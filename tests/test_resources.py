import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.io import frame_fingerprint, fingerprint, matrix_budget, require_memory, Context, check_output_budget, write_json
from src.kaggle_runtime import resource_plan
from src.reporting import finalize
from test_data_features import ROOT, fixture, write_config


class Resources(unittest.TestCase):
    def test_batched_hash_matches_original_including_empty_and_missing(self):
        frame=pd.DataFrame({"x":[1.,np.nan,3.],"name":["Tiếng Việt",None,"quoted\"text"]})
        for f in (frame,frame.iloc[:0]):
            for size in (1,2,50000):
                self.assertEqual(frame_fingerprint(f,size),fingerprint(f.to_dict("records")))

    def test_auto_budget_tracks_available_ram_and_fixed_remains_supported(self):
        cfg={"runtime":{"max_matrix_gb":2,"memory_policy":"auto","memory_fraction":.6}}
        with patch("src.io.psutil.virtual_memory",return_value=SimpleNamespace(available=10*2**30)):
            self.assertEqual(matrix_budget(cfg),6*2**30)
            require_memory(cfg,5*2**30,"fit")
            with self.assertRaisesRegex(MemoryError,"Need more host RAM"):require_memory(cfg,7*2**30,"fit")
            cfg["runtime"]["memory_policy"]="fixed"
            self.assertEqual(matrix_budget(cfg),2*2**30)

    def test_bundle_fresh_cached_and_old_code(self):
        with tempfile.TemporaryDirectory(prefix="pubg-bootstrap-") as folder:
            root=Path(folder);cfg=fixture(root)
            script=("import runpy,sys; from pathlib import Path; "
                    f"root=Path({str(root)!r}); "
                    "check=runpy.run_path(str(root/'src/bootstrap.py'))['check_bundle']; "
                    "check(root,'5.11-normalized-storage'); "
                    "sys.path.insert(0,str(root)); import src.io; "
                    "check(root,'5.11-normalized-storage'); "
                    "sys._pubg_bundle_identity=None; "
                    "check(root,'5.11-normalized-storage')")
            result=subprocess.run([sys.executable,"-B","-c",script],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn("Cached src differs",result.stderr)
            prefix=script.split("check(root,'5.11-normalized-storage');",1)[0]
            result=subprocess.run([sys.executable,"-B","-c",prefix+"check(root,'5.11-normalized-storage','wrong')"],capture_output=True,text=True)
            self.assertIn("source checksum mismatch",result.stderr)
            result=subprocess.run([sys.executable,"-B","-c",prefix+"import importlib.metadata; importlib.metadata.version=lambda name:'0.0'; check(root,'5.11-normalized-storage')"],capture_output=True,text=True)
            self.assertIn("Dependency mismatch",result.stderr)
            cfg["spec_version"]="5.4-kaggle-dual-gpu";write_config(root,cfg)
            result=subprocess.run([sys.executable,"-B","-c",script],capture_output=True,text=True)
            self.assertIn("Update the code Dataset",result.stderr)

    def test_resource_plan_counts_without_loading_targets_and_blocks_small_budget(self):
        with tempfile.TemporaryDirectory(prefix="pubg-resource-plan-") as folder:
            root=Path(folder);cfg=fixture(root);ctx=Context(root,"development")
            self.assertEqual(resource_plan(ctx)["status"],"deferred_until_S04")
            ctx.data.mkdir(parents=True)
            frame=pd.DataFrame({"player_name":["a","b","a"],"team_size_mode":["Solo"]*3,
                                "row_id":["1","2","3"],"match_id":["m1","m2","m3"],"team_id":["t1"]*3,
                                "split":["train","validation","test"],"valid_survival":[True]*3,
                                "valid_placement":[True,True,False]})
            frame.to_parquet(ctx.data/"player_match.parquet",index=False)
            plan=resource_plan(ctx)
            self.assertTrue(plan["feasible"])
            self.assertEqual(plan["checks"][0]["rows"],2)
            # No actual target columns exist: the planner must not inspect them.
            ctx.cfg["runtime"]["max_matrix_gb"]=1e-12
            self.assertFalse(resource_plan(ctx)["feasible"])

    def test_release_budget_checks_extra_copy_before_creating_snapshot(self):
        with tempfile.TemporaryDirectory(prefix="pubg-release-budget-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            tables=ctx.path("tables");tables.mkdir(parents=True)
            names=["source_inventory","removal_ledger","split_summary","feature_dictionary",
                   "timing_audit","timing_coverage","eda_statistics","rq1_relationships",
                   "cluster_centers","cluster_sizes","cluster_outcomes","timing_comparison","error_analysis","coefficients"]
            for name in names:pd.DataFrame({"value":[1]}).to_csv(tables/(name+".csv"),index=False)
            pd.DataFrame({"experiment":["s1_mean","s1_median","s1_linear","p2_mean","p2_median","p2_linear","t0_linear"],
                          "split":"test","aggregation":"micro"}).to_csv(tables/"model_metrics.csv",index=False)
            write_json({"modes":["Solo"]},ctx.path("manifests/clustering.json"))
            size=check_output_budget(root,18)
            ctx.cfg["storage"]["output_budget_gb"]=(size+1024)/2**30
            # Scientific prerequisites are stubbed only to isolate the disk guard.
            with patch.object(ctx,"require",return_value={"artifacts":[]}):
                with self.assertRaisesRegex(MemoryError,"S10 release needs"):finalize(ctx)
            self.assertFalse(ctx.path("manifests/releases").exists())
