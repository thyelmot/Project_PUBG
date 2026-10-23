import copy
import errno
import hashlib
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import nbformat
import pandas as pd
import yaml
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

from src.io import Context, digest, read_json, write_json
from src.preprocessing import ingest
from src.kaggle_runtime import (code_archive, prepare_project, preflight, prepare_handoff,
                                restore_handoff, verify_handoff, gpu_smoke)
from test_data_features import ROOT, fixture, write_config
from build_kaggle_fixture import build_fixture


class KaggleRuntime(unittest.TestCase):
    def test_official_parameters_replace_stale_session_values(self):
        nb=nbformat.read(ROOT/"notebooks/PUBG_COURSEWORK.ipynb",as_version=4)
        source=next(c.source for c in nb.cells if c.id=="parameters")
        expected={"EXECUTION_MODE":"full","ALLOW_DATA_PROCESSING":True,"ALLOW_FULL_DATA":True,
                  "START_STAGE":"S08","END_STAGE":"S08","SOURCE_VERSION":3,
                  "CODE_INPUT":"/kaggle/input/datasets/quangthinng/pubg-coursework-code",
                  "SOURCE_DIRECTORY":"/kaggle/input/datasets/skihikingkevin/pubg-match-deaths",
                  "SOURCE_TIME_UNIT_STATUS":"assumed_seconds","SOURCE_TIME_UNIT_ASSUMPTION_APPROVED":True,
                  "SOURCE_TIME_UNIT_ASSUMPTION_SCOPE":"skihikingkevin/pubg-match-deaths/versions/3","RUN_GPU_SMOKE":True,
                  "ALLOW_CPU_GPU_RESUME":False,"ALLOW_S07_TSQR_RESUME":True,"INSTALL_RESUME_ENVIRONMENT":True,"RESUME_VERSION":"quangthinng/pubg-v3/versions/6",
                  "RESUME_INPUT":"/kaggle/input/notebooks/quangthinng/pubg-v3/PUBG_Coursework_v511_S07_profiles",
                  "PUBG_PROJECT_ROOT":"/kaggle/working/PUBG_Coursework_v511_S08_matrixdisk"}
        for ns in ({},{"EXECUTION_MODE":"development","ALLOW_DATA_PROCESSING":False,
                         "ALLOW_FULL_DATA":False,"SOURCE_TIME_UNIT_STATUS":"pending","END_STAGE":"S01"}):
            exec(compile(source,"parameters","exec"),ns)
            for key,value in expected.items():self.assertEqual(ns[key],value,key)
            self.assertFalse(ns["PUBG_FORCE_STAGE_TAKEOVER"])
            self.assertFalse(ns["INSTALL_DEPENDENCIES"])
        readme=(ROOT/"README.md").read_text(encoding="utf-8")
        block=readme.split("### Khối S00 đầy đủ cho nguồn PUBG Version 3 đã chọn",1)[1].split("```python\n",1)[1].split("```",1)[0]
        self.assertEqual(source.strip(),block.strip())

    def test_exported_fixture_setup_and_feature_stages(self):
        from src.preprocessing import clean_split
        from src.features import base_features, combat_timing
        original=digest(ROOT/"configs/project.yaml")
        with tempfile.TemporaryDirectory(prefix="pubg-exported-fixture-") as folder:
            base=Path(folder);source=base/"input";source.mkdir()
            archive=build_fixture(base/"fixture.zip")
            with zipfile.ZipFile(archive) as z:
                self.assertEqual(len(z.namelist()),7)
                self.assertIsNone(z.testzip())
                manifest=json.loads(z.read("fixture_manifest.json"))
                for entry in manifest["entries"]:
                    data=z.read(entry["path"])
                    self.assertEqual(hashlib.sha256(data).hexdigest(),entry["sha256"])
                    self.assertEqual(len(data),entry["bytes"])
                # Our own generated archive; do not use this as an untrusted ZIP extractor.
                for name in z.namelist():
                    self.assertEqual(Path(name).name,name)
                    (source/name).write_bytes(z.read(name))
            cfg=yaml.safe_load((source/"fixture_config.yaml").read_text(encoding="utf-8"))
            self.assertEqual(cfg["rq2"]["device"],"cuda")
            self.assertEqual(cfg["rq3"]["device"],"cuda")
            self.assertIsNone(cfg["rq2"]["clusters"]["Solo"])
            self.assertFalse(cfg["rq3"]["selection_approved"])
            raw_hashes={p.name:digest(p) for p in source.glob("*.csv")}
            ns={"CODE_INPUT":str(ROOT),"FIXTURE_INPUT":str(source),
                "PUBG_PROJECT_ROOT":str(base/"working"),"EXECUTION_MODE":"development",
                "ALLOW_FULL_DATA":False,"SOURCE_VERSION":1}
            setup=(source/"setup_fixture.py").read_text(encoding="utf-8")
            forbidden={**ns,"ALLOW_FULL_DATA":True}
            with self.assertRaisesRegex(ValueError,"full-data"):exec(compile(setup,"setup_fixture.py","exec"),forbidden)
            self.assertFalse((base/"working").exists())
            exec(compile(setup,"setup_fixture.py","exec"),ns)
            self.assertTrue(ns["ALLOW_DATA_PROCESSING"])
            self.assertEqual(ns["SOURCE_DIRECTORY"],str(source.resolve()))
            ctx=Context(base/"working","development")
            preflight(ctx,"S01","S04",kaggle=True)
            for stage,fn in (("S01",ingest),("S02",clean_split),("S03",base_features),("S04",combat_timing)):
                ctx.run(stage,fn)
            data=pd.read_parquet(ctx.data/"player_match.parquet")
            self.assertEqual(len(data),240)
            self.assertEqual(data.match_id.nunique(),30)
            self.assertEqual(raw_hashes,{p.name:digest(p) for p in source.glob("*.csv")})
            ns["CODE_INPUT"]=str(ROOT)
            with self.assertRaisesRegex(ValueError,"trống"):exec(compile(setup,"setup_fixture.py","exec"),ns)
            bad={**ns,"PUBG_PROJECT_ROOT":str(base/"bad-working")}
            (source/"agg_match_stats_0.csv").write_text("corrupt",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"checksum"):exec(compile(setup,"setup_fixture.py","exec"),bad)
            self.assertFalse((base/"bad-working").exists())
        self.assertEqual(original,digest(ROOT/"configs/project.yaml"))

    def test_light_code_input_and_archive(self):
        with tempfile.TemporaryDirectory(prefix="pubg-kaggle-code-") as folder:
            base=Path(folder);source=base/"input";fixture(source)
            archive=code_archive(source,base/"code.zip")
            with zipfile.ZipFile(archive) as z:
                self.assertIn("src/kaggle_runtime.py",z.namelist())
                self.assertFalse(any(n.startswith(("data/","outputs/","raw_fixture/")) for n in z.namelist()))
            hashes={p:digest(p) for p in source.rglob("*") if p.is_file()}
            prepared=prepare_project(source,base/"working")
            self.assertTrue((prepared/"src/io.py").is_file())
            self.assertFalse((prepared/"raw_fixture").exists())
            self.assertEqual(hashes,{p:digest(p) for p in source.rglob("*") if p.is_file()})
            with self.assertRaisesRegex(ValueError,"Input"):prepare_project(source,source/"child")
            (prepared/"src/io.py").write_text("changed",encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError,"code khác"):prepare_project(source,prepared)

    def test_resume_new_root_mount_and_corruption(self):
        with tempfile.TemporaryDirectory(prefix="pubg-kaggle-resume-") as folder:
            base=Path(folder);root=base/"first";root.mkdir();fixture(root)
            ctx=Context(root,"development");ctx.run("S01",ingest)
            handoff=prepare_handoff(ctx)
            self.assertFalse(read_json(handoff)["saved_version_verified"])
            mount=base/"input/raw-v1";shutil.copytree(root/"raw_fixture",mount)
            snapshot=base/"input/output-v3";snapshot.mkdir(parents=True)
            record=read_json(handoff)
            for entry in record["entries"]:
                dest=snapshot/entry["path"];dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(root/entry["path"],dest)
            shutil.copyfile(handoff,snapshot/handoff.name)
            before={p:digest(p) for p in snapshot.rglob("*") if p.is_file()}
            _,evidence=verify_handoff(snapshot,"development","team/notebook/versions/3")
            self.assertIn("local file",evidence["environment"])
            restored=restore_handoff(snapshot,base/"second", "development",mount,"team/notebook/versions/3")
            new=Context(restored,"development")
            self.assertEqual(ctx.require("S01")["signature"],new.require("S01")["signature"])
            new.run("S01",lambda _:self.fail("same source rebuilt"))
            self.assertEqual(before,{p:digest(p) for p in snapshot.rglob("*") if p.is_file()})
            self.assertFalse(list(restored.rglob("*.lock")))
            with self.assertRaisesRegex(ValueError,"ghi đè"):restore_handoff(snapshot,restored,"development",mount,"team/notebook/versions/3")
            cfg=copy.deepcopy(new.cfg);cfg["source"]["version"]=2;write_config(restored,cfg)
            with self.assertRaisesRegex(RuntimeError,"stale"):Context(restored,"development").require("S01")
            bad=snapshot/record["entries"][-1]["path"];bad.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError,"checksum"):verify_handoff(snapshot,"development","team/notebook/versions/3")

    def test_unsafe_incomplete_and_fake_latest(self):
        with tempfile.TemporaryDirectory(prefix="pubg-kaggle-unsafe-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development");ctx.run("S01",ingest)
            path=prepare_handoff(ctx);record=read_json(path)
            with self.assertRaises(ValueError):verify_handoff(root,"development","latest")
            record["entries"].append({"path":"../secret","bytes":0,"sha256":"x"});write_json(record,path)
            with self.assertRaisesRegex(ValueError,"Unsafe"):verify_handoff(root,"development","team/notebook/versions/1")
            record["entries"]=[];write_json(record,path)
            with self.assertRaisesRegex(ValueError,"Incomplete"):verify_handoff(root,"development","team/notebook/versions/1")

    def test_preflight_budget_software_and_gpu_no_fallback(self):
        with tempfile.TemporaryDirectory(prefix="pubg-kaggle-preflight-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            with self.assertRaisesRegex(ValueError,"Pin"):preflight(ctx,"S01","S06",kaggle=True)
            ctx.cfg["source"]["version"]=1
            result=preflight(ctx,"S01","S06",kaggle=True)
            self.assertFalse(result["saved_version_verified"])
            ctx.run("S01",ingest)
            ctx.software["numpy"]="changed"
            with self.assertRaisesRegex(RuntimeError,"stale"):ctx.require("S01")
            cfg=copy.deepcopy(ctx.cfg);cfg["storage"]["output_budget_gb"]=1e-12;write_config(root,cfg)
            limited=Context(root,"development")
            with self.assertRaises(MemoryError):limited.run("S01",lambda _:self.fail("cached stage fit"))
            self.assertEqual(limited.manifest()["S01"]["status"],"completed","Guard must not erase the prior valid checkpoint")
            with self.assertRaises(MemoryError):limited.run("S02",lambda c:c.table("x",__import__("pandas").DataFrame([{"x":1}])))
            self.assertEqual(limited.manifest()["S02"]["status"],"resource_limited")
            cfg["storage"]["output_budget_gb"]=18.;write_config(root,cfg)
            disk=Context(root,"development")
            def full_disk(_):raise OSError(errno.ENOSPC,"disk full fixture")
            with self.assertRaises(OSError):disk.run("S02",full_disk)
            self.assertEqual(disk.manifest()["S02"]["status"],"resource_limited")
            with patch("src.kaggle_runtime.compute_metadata",side_effect=RuntimeError("No GPU")):
                with self.assertRaisesRegex(RuntimeError,"No GPU"):gpu_smoke()

    def test_actual_bootstrap_copy_and_processing_guard(self):
        with tempfile.TemporaryDirectory(prefix="pubg-kaggle-notebook-") as folder:
            base=Path(folder);source=base/"input/code";source.mkdir(parents=True);fixture(source)
            template=nbformat.read(ROOT/"notebooks/PUBG_COURSEWORK.ipynb",as_version=4)
            def run(allowed,target):
                nb=copy.deepcopy(template)
                nb.cells=[c for c in nb.cells if c.id in {"parameters","bootstrap","section-runner","s01-execute"}]
                cell=next(c for c in nb.cells if c.id=="parameters")
                cell.source+=(f'\nCODE_INPUT={str(source)!r}\nPUBG_PROJECT_ROOT={str(target)!r}\nALLOW_DATA_PROCESSING={allowed!r}\nSTART_STAGE="S01"\nEND_STAGE="S01"\nRESUME_INPUT=""\nRESUME_VERSION=""\nALLOW_CPU_GPU_RESUME=False\n'
                              'EXECUTION_MODE="development"\nALLOW_FULL_DATA=False\nSOURCE_DIRECTORY=""\nSOURCE_VERSION=None\nSOURCE_LICENSE=""\n'
                              'SOURCE_TIME_UNIT_STATUS=""\nSOURCE_TIME_UNIT_ASSUMPTION_APPROVED=None\nSOURCE_TIME_UNIT_ASSUMPTION_SCOPE=""\nRUN_GPU_SMOKE=False\n')
                return NotebookClient(nb,timeout=120,kernel_name="python3",resources={"metadata":{"path":str(base)}}).execute()
            with self.assertRaises(CellExecutionError):run(False,base/"blocked")
            self.assertFalse((base/"blocked").exists())
            executed=run(True,base/"working")
            self.assertTrue((base/"working/handoff_development.json").exists())
            outputs=[o for c in executed.cells for o in c.get("outputs",[])]
            self.assertTrue(any("Kaggle Version" in str(o) for o in outputs))
            self.assertEqual(Context(base/"working","development").manifest()["S01"]["status"],"completed")
            nb=copy.deepcopy(template);nb.cells=[c for c in nb.cells if c.id in {"parameters","bootstrap"}]
            c=nb.cells[0];c.source+=f'\nPUBG_PROJECT_ROOT={str(source)!r}\nALLOW_DATA_PROCESSING=True\nEXECUTION_MODE="full"\nALLOW_FULL_DATA=False\n'
            before={p:digest(p) for p in source.rglob("*") if p.is_file()}
            with self.assertRaises(CellExecutionError):NotebookClient(nb,timeout=120,kernel_name="python3",resources={"metadata":{"path":str(base)}}).execute()
            self.assertEqual(before,{p:digest(p) for p in source.rglob("*") if p.is_file()})


if __name__=="__main__":unittest.main()
