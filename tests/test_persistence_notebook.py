import ast
import asyncio
import copy
import errno
import os
import re
import shutil
import tempfile
import unittest
import unicodedata
from pathlib import Path
from unittest.mock import patch

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

from src.io import Context, digest, publish, read_json
from test_data_features import ROOT, fixture, write_config

if os.name=="nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class PersistenceNotebook(unittest.TestCase):
    def test_publication_preserves_old_file_on_failure(self):
        with tempfile.TemporaryDirectory(prefix="pubg-publish-") as folder:
            source=Path(folder)/"new";target=Path(folder)/"old"
            source.write_text("new",encoding="utf-8");target.write_text("good",encoding="utf-8")
            with patch("src.io.os.replace",side_effect=OSError("simulated disk failure")):
                with self.assertRaises(OSError):publish(source,target)
            self.assertEqual(target.read_text(),"good")
            publish(source,target);self.assertEqual(target.read_text(),"new")

    def test_consumed_publication_renames_and_handles_cross_filesystem(self):
        with tempfile.TemporaryDirectory(prefix="pubg-consume-") as folder:
            source=Path(folder)/"staged";target=Path(folder)/"published"
            source.write_text("new",encoding="utf-8")
            with patch("src.io.shutil.copyfile",side_effect=AssertionError("No copy for same-filesystem publish")):
                publish(source,target,consume=True)
            self.assertEqual(target.read_text(),"new")
            self.assertFalse(source.exists())
            source.write_text("cross filesystem",encoding="utf-8")
            replace=os.replace
            def cross_device(a,b):
                if Path(a)==source:raise OSError(errno.EXDEV,"simulated different filesystem")
                return replace(a,b)
            with patch("src.io.os.replace",side_effect=cross_device):publish(source,target,consume=True)
            self.assertEqual(target.read_text(),"cross filesystem")
            self.assertFalse(source.exists())
            self.assertEqual(list(Path(folder).iterdir()),[target])

    def test_consumed_publication_failure_keeps_previous_output(self):
        with tempfile.TemporaryDirectory(prefix="pubg-consume-fail-") as folder:
            source=Path(folder)/"staged";target=Path(folder)/"published"
            source.write_text("new",encoding="utf-8");target.write_text("good",encoding="utf-8")
            replace=os.replace
            def failed_commit(a,b):
                if Path(b)==target and Path(a).suffix==".partial":
                    raise OSError(errno.ENOSPC,"simulated full disk")
                return replace(a,b)
            with patch("src.io.os.replace",side_effect=failed_commit):
                with self.assertRaises(OSError):publish(source,target,consume=True)
            self.assertEqual(target.read_text(),"good")
            self.assertFalse(list(Path(folder).glob("*.partial")))
            self.assertFalse(list(Path(folder).glob("*.previous")))
            source.write_text("new",encoding="utf-8")
            def corrupt_readback(path):
                return "wrong checksum" if Path(path)==target else digest(path)
            with patch("src.io.digest",side_effect=corrupt_readback):
                with self.assertRaisesRegex(IOError,"read-back"):publish(source,target,consume=True)
            self.assertEqual(target.read_text(),"good")
            with self.assertRaisesRegex(ValueError,"file đích"):publish(target,target,consume=True)
            self.assertEqual(target.read_text(),"good")

    def test_notebook_schema_and_scientific_sections(self):
        paths={p.name for p in (ROOT/"notebooks").glob("*.ipynb")}
        self.assertEqual(paths,{"PUBG_COURSEWORK.ipynb","PUBG_COURSEWORK_COLAB.ipynb"})
        nb=nbformat.read(ROOT/"notebooks/PUBG_COURSEWORK.ipynb",as_version=4);nbformat.validate(nb)
        self.assertEqual(len(nb.cells),48)
        self.assertEqual(len({cell.id for cell in nb.cells}),48)
        self.assertEqual(sum(cell.cell_type=="code" for cell in nb.cells),16)
        text="\n".join(c.source for c in nb.cells if c.cell_type=="markdown")
        for i in range(13):self.assertIn(f'id="S{i:02d}"',text)
        for cell in nb.cells:
            self.assertTrue(cell.source.strip())
            if cell.cell_type=="code":
                ast.parse(cell.source)
                self.assertFalse(any(output.output_type=="error" for output in cell.outputs))
        self.assertIn("report_only",text)

    def test_notebook_markdown_math_and_vietnamese(self):
        nb=nbformat.read(ROOT/"notebooks/PUBG_COURSEWORK.ipynb",as_version=4)
        formulas={cell.id for cell in nb.cells if cell.cell_type=="markdown" and cell.id.endswith("-formulas")}
        self.assertEqual(formulas,{"s03-formulas","s04-formulas","s06-formulas",
                                   "s07-formulas","s08-formulas","s09-formulas"})
        for cell in nb.cells:
            with self.subTest(cell=cell.id):
                self.assertEqual(cell.source,unicodedata.normalize("NFC",cell.source))
                self.assertNotIn("\ufffd",cell.source)
                if cell.cell_type!="markdown":continue
                for delimiter in (r"\[",r"\]",r"\(",r"\)"):
                    self.assertNotIn(delimiter,cell.source)
                self.assertEqual(cell.source.count("$$")%2,0)
                inline=re.sub(r"\$\$.*?\$\$","",cell.source,flags=re.S)
                self.assertEqual(inline.count("$")%2,0)
                if cell.id in formulas:
                    self.assertIn("\n\n$$\n",cell.source)
                    for block in re.findall(r"\$\$(.*?)\$\$",cell.source,flags=re.S):
                        self.assertTrue(block.strip())
                        self.assertEqual(block.count("{"),block.count("}"))

    def test_stale_code_and_missing_artifact_are_rejected(self):
        from src.preprocessing import ingest
        with tempfile.TemporaryDirectory(prefix="pubg-stale-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            ctx.run("S01",ingest)
            (root/"src/io.py").write_text("# different code",encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError,"stale"):ctx.require("S01")
            ctx.path("tables/source_inventory.csv").write_text("corrupt",encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError,"artifact"):ctx.require("S01")

    def test_writer_lock_and_empty_commit(self):
        from src.preprocessing import ingest
        from src.io import write_json
        with tempfile.TemporaryDirectory(prefix="pubg-writer-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development",writer="ownerB")
            lock=ctx.path("checkpoints/S01.lock");lock.mkdir(parents=True)
            write_json({"writer":"ownerA"},lock/"owner.json")
            with self.assertRaisesRegex(RuntimeError,"khóa"):ctx.run("S01",ingest)
            ctx=Context(root,"development",writer="ownerB",force_takeover=True)
            with self.assertRaisesRegex(ValueError,"artifact"):ctx.run("S01",lambda c:None)
            self.assertEqual(ctx.manifest()["S01"]["status"],"failed")
            self.assertFalse(lock.exists())

    def test_resource_failure_is_not_completed(self):
        with tempfile.TemporaryDirectory(prefix="pubg-resource-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            def exhausted(c):raise MemoryError("fixture simulated RAM exhaustion")
            with self.assertRaises(MemoryError):ctx.run("S01",exhausted)
            self.assertEqual(ctx.manifest()["S01"]["status"],"resource_limited")
            self.assertFalse(ctx.manifest()["S01"]["artifacts"])

    def test_actual_notebook_sections_and_report_only(self):
        review=Path(tempfile.mkdtemp(prefix="pubg-notebook-review-"))
        with tempfile.TemporaryDirectory(prefix="pubg-nb-") as folder:
            root=Path(folder);cfg=fixture(root)
            template=nbformat.read(ROOT/"notebooks/PUBG_COURSEWORK.ipynb",as_version=4)
            def execute(start,end,mode="development",manifest="",extra=""):
                nb=copy.deepcopy(template)
                prefix=(f"ALLOW_DATA_PROCESSING=True\nPUBG_STORAGE_MODE='local'\nPUBG_PROJECT_ROOT={str(root)!r}\nEXECUTION_MODE={mode!r}\n"
                        f"START_STAGE={start!r}\nEND_STAGE={end!r}\nRELEASE_MANIFEST={manifest!r}\n")
                params=next(c for c in nb.cells if c.id=="parameters")
                params.source+=("\nCODE_INPUT=''\nSOURCE_DIRECTORY=''\nSOURCE_VERSION=None\nSOURCE_LICENSE=''\n"
                                "SOURCE_TIME_UNIT_STATUS=''\nSOURCE_TIME_UNIT_ASSUMPTION_APPROVED=None\n"
                                "SOURCE_TIME_UNIT_ASSUMPTION_SCOPE=''\nRUN_GPU_SMOKE=False\n"+prefix+extra)
                client=NotebookClient(nb,timeout=120,kernel_name="python3",resources={"metadata":{"path":str(root.parent)}})
                try:client.execute()
                finally:
                    nbformat.write(nb,review/f"{start}_{end}_{mode}.ipynb")
                return nb
            with self.assertRaises(CellExecutionError):execute("S01","S07")
            ctx=Context(root,"development")
            receipt=read_json(ctx.path("manifests/k_diagnostic_receipt.json"))
            cfg["rq2"].update(diagnostic_hash=receipt["diagnostic_hash"],decision_reason="fixture notebook routing only",clusters={"Solo":2,"Duo":2,"Squad":None})
            write_config(root,cfg)
            execute("S07","S07")
            with self.assertRaises(CellExecutionError):execute("S08","S08")
            self.assertFalse(list(ctx.path("predictions").glob("test_*.parquet")))
            receipt=read_json(ctx.path("manifests/validation_receipt.json"))
            cfg["rq3"].update(selection_approved=True,selection_reason="fixture only; not production approval",validation_hash=receipt["validation_hash"])
            write_config(root,cfg)
            executed=execute("S08","S10")
            complete=execute("S01","S10")
            nbformat.write(complete,review/"complete_fixture.ipynb")
            pointer=read_json(ctx.path("manifests/final_results.json"));manifest=root/pointer["manifest"]
            before={str(p.relative_to(root)):digest(p) for p in root.rglob("*") if p.is_file()}
            execute("S01","S10",mode="report_only",manifest=str(manifest))
            after={str(p.relative_to(root)):digest(p) for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before,after,"report_only wrote files")
            for stage in (f"S{i:02d}" for i in range(1,11)):
                self.assertEqual(ctx.manifest()[stage]["status"],"completed")
            shutil.copytree(ctx.path("figures"),review/"figures")
            shutil.copytree(ctx.path("tables"),review/"tables")
            html_count=sum(1 for cell in executed.cells for output in cell.get("outputs",[]) if "text/html" in output.get("data",{}))
            self.assertGreater(html_count,10)
            from src.kaggle_runtime import prepare_handoff
            ctx=Context(root,"development")
            handoff=prepare_handoff(ctx)
            saved=Path(folder)/"input/saved-version";saved.mkdir(parents=True)
            record=read_json(handoff)
            for entry in record["entries"]:
                dest=saved/entry["path"];dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(root/entry["path"],dest)
            shutil.copyfile(handoff,saved/handoff.name)
            raw_mount=Path(folder)/"input/raw-remount";shutil.copytree(root/"raw_fixture",raw_mount)
            root=Path(folder)/"restored-project"
            extra=f"RESUME_INPUT={str(saved)!r}\nRESUME_VERSION='team/notebook/versions/2'\nSOURCE_DIRECTORY={str(raw_mount)!r}\n"
            resumed=execute("S07","S10",extra=extra)
            nbformat.write(resumed,review/"restored_S07_S10.ipynb")
            self.assertTrue((root/"handoff_readback_development.json").exists())
            root=saved
            before={str(p.relative_to(root)):digest(p) for p in root.rglob("*") if p.is_file()}
            execute("S01","S10",mode="report_only",manifest=str(saved/pointer["manifest"]))
            self.assertEqual(before,{str(p.relative_to(root)):digest(p) for p in root.rglob("*") if p.is_file()})
            print("REVIEW_ROOT="+str(review))


if __name__=="__main__":unittest.main()
