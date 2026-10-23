"""Only the frozen, audited 5.10 parser may supply S01 to normalized storage."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from src.io import Context,digest,read_json
from src.kaggle_runtime import import_s01_510,cleanup_imported_510
from test_data_features import ROOT,fixture,write_config


class S01Import(unittest.TestCase):
    def old_project(self,root):
        cfg=fixture(root);cfg["spec_version"]="5.10-evaluation-out-of-core";write_config(root,cfg)
        # This file belongs to the just-created test fixture, not the user's project.
        (root/"src/storage.py").unlink()
        archive=ROOT/"tests/fixtures/audited_s01_producer_510.zip"
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if name.startswith("src/"):(root/name).write_bytes(z.read(name))
        script="""import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from src.io import Context
from src.preprocessing import ingest,clean_split
ctx=Context(Path(sys.argv[1]),'development',progress=lambda _:None)
ctx.run('S01',ingest)
record=ctx.record
def fail(path):
    if Path(path).name=='cleaned.parquet':raise MemoryError('Working project exceeds output budget')
    return record(path)
ctx.record=fail
try:ctx.run('S02',clean_split)
except MemoryError:pass
"""
        result=subprocess.run([sys.executable,"-B","-c",script,str(root)],cwd=root,
            env={**os.environ,"PYTHONUTF8":"1","PYTHONDONTWRITEBYTECODE":"1","OMP_NUM_THREADS":"1","OPENBLAS_NUM_THREADS":"1","MKL_NUM_THREADS":"1"},
            capture_output=True,text=True,encoding="utf-8",timeout=120)
        self.assertEqual(result.returncode,0,result.stderr)
        return cfg

    def test_import_and_explicit_cleanup_preserve_s01_without_copying_it(self):
        with tempfile.TemporaryDirectory(prefix="pubg-s01-import-test-") as folder:
            old=Path(folder)/"old";new=Path(folder)/"new";cfg=self.old_project(old)
            with self.assertRaisesRegex(ValueError,"source fact"):
                import_s01_510(old,ROOT,Path(folder)/"bad-version","development",cfg["source"]["directory"],source_version=99)
            hashes={name:digest(old/f"data/development/{name}.parquet") for name in ("aggregate","event")}
            with patch("src.kaggle_runtime.shutil.copyfile",wraps=__import__('shutil').copyfile) as copied:
                import_s01_510(old,ROOT,new,"development",cfg["source"]["directory"])
            self.assertFalse(any(Path(call.args[0]).name in {"aggregate.parquet","event.parquet"} for call in copied.call_args_list))
            for name in hashes:self.assertTrue(os.path.samefile(old/f"data/development/{name}.parquet",new/f"data/development/{name}.parquet"))
            ctx=Context(new,"development",progress=lambda _:None);ctx.require("S01")
            self.assertIn("producer_import",ctx.manifest()["S01"])
            self.assertEqual(ctx.cfg["storage"]["layout"],"normalized_v1")
            with self.assertRaises(ValueError):cleanup_imported_510(old,new,"development")
            self.assertTrue((old/"data/development/cleaned.parquet").exists())
            result=cleanup_imported_510(old,new,"development",confirm=True)
            self.assertEqual(len(result["removed"]),3)
            self.assertGreater(result["failed_cleaned_bytes"],0)
            for name in hashes:self.assertEqual(digest(new/f"data/development/{name}.parquet"),hashes[name])
            ctx.require("S01")
            self.assertEqual(import_s01_510(old,ROOT,new,"development",cfg["source"]["directory"]),new)
            self.assertFalse(cleanup_imported_510(old,new,"development",confirm=True)["removed"])

    def test_bad_producer_source_and_nonempty_target_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="pubg-s01-import-guard-") as folder:
            old=Path(folder)/"old";new=Path(folder)/"new";cfg=self.old_project(old)
            new.mkdir();(new/"keep.txt").write_text("User result",encoding="utf-8")
            with self.assertRaises(ValueError):import_s01_510(old,ROOT,new,"development",cfg["source"]["directory"])
            self.assertEqual((new/"keep.txt").read_text(),"User result")
            raw=next((old/"raw_fixture").glob("agg*.csv"));original=raw.read_bytes();raw.write_bytes(original+b"\n")
            with self.assertRaises(RuntimeError):import_s01_510(old,ROOT,Path(folder)/"changed-source","development",cfg["source"]["directory"])
            raw.write_bytes(original)
            with patch("src.kaggle_runtime.os.link",side_effect=OSError("different filesystem")):
                with self.assertRaisesRegex(RuntimeError,"hardlink"):import_s01_510(old,ROOT,Path(folder)/"no-link","development",cfg["source"]["directory"])
            self.assertFalse((Path(folder)/"no-link").exists())
            code=old/"src/io.py";code.write_bytes(code.read_bytes()+b"\n# changed producer\n")
            with self.assertRaises(ValueError):import_s01_510(old,ROOT,Path(folder)/"bad-code","development",cfg["source"]["directory"])

    def test_cleanup_refuses_active_writer_downstream_and_unshared_alias(self):
        with tempfile.TemporaryDirectory(prefix="pubg-s01-clean-guard-") as folder:
            old=Path(folder)/"old";new=Path(folder)/"new";cfg=self.old_project(old)
            import_s01_510(old,ROOT,new,"development",cfg["source"]["directory"])
            lock=old/"outputs/development/checkpoints/S02.lock";lock.mkdir()
            with self.assertRaises(RuntimeError):cleanup_imported_510(old,new,"development",confirm=True)
            lock.rmdir()
            path=old/"outputs/development/checkpoints/stages.json";original=path.read_bytes()
            records=json.loads(original);records["S03"]={"status":"completed"}
            path.write_text(json.dumps(records),encoding="utf-8")
            with self.assertRaises(ValueError):cleanup_imported_510(old,new,"development",confirm=True)
            path.write_bytes(original)
            alias=old/"data/development/aggregate.parquet";data=alias.read_bytes();alias.unlink();alias.write_bytes(data)
            with self.assertRaises(ValueError):cleanup_imported_510(old,new,"development",confirm=True)
            self.assertTrue((old/"data/development/cleaned.parquet").exists())


if __name__=="__main__":unittest.main()
