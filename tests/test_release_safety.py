import copy
import errno
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src import reporting,modeling
from src.io import Context,digest,read_json,write_json
from test_analysis_models import finish_fixture
import reference_modeling_v58 as reference
import reference_reporting_v59 as old_reporting


RTOL,ATOL=1e-9,1e-10


class ReleaseSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(prefix="pubg-d5-release-base-")
        cls.base=Path(cls.folder.name)/"project";cls.base.mkdir()
        cls.context,_=finish_fixture(cls.base)

    @classmethod
    def tearDownClass(cls):cls.folder.cleanup()

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(prefix="pubg-d5-release-case-")
        self.root=Path(self.folder.name)/"project";shutil.copytree(self.base,self.root)
        self.ctx=Context(self.root,"development",progress=lambda _:None)

    def tearDown(self):self.folder.cleanup()

    def test_all_s09_tables_and_samples_match_reference_with_bootstrap(self):
        ctx=self.ctx;ctx.cfg["report"]["bootstrap_replicates"]=40
        reference.comparisons(ctx)
        expected={p.name:pd.read_csv(p) for p in ctx.path("tables").glob("*.csv") if p.name in
            {"timing_comparison.csv","error_analysis.csv","timing_ci.csv","prediction_plot_s1.csv","prediction_plot_p2.csv"}
            or p.name.endswith("_source.csv")}
        with patch("pandas.read_parquet",side_effect=AssertionError("S09 must not collect predictions")):
            modeling.comparisons(ctx)
        for name,frame in expected.items():
            with self.subTest(table=name):
                pd.testing.assert_frame_equal(pd.read_csv(ctx.path("tables/"+name)),frame,rtol=RTOL,atol=ATOL)
        self.assertFalse(list(ctx.temp.glob("pubg-sql-*")))

    def test_copy_failure_cleans_staging_and_preserves_old_pointer(self):
        ctx=self.ctx;pointer=ctx.path("manifests/final_results.json");old=digest(pointer)
        releases=ctx.path("manifests/releases");before={p.name for p in releases.iterdir()}
        copyfile=shutil.copyfile;calls=[]
        def fail(source,target,*args,**kwargs):
            calls.append(1)
            if len(calls)==2:raise OSError(errno.ENOSPC,"synthetic release disk full")
            return copyfile(source,target,*args,**kwargs)
        with patch("src.reporting.shutil.copyfile",side_effect=fail):
            with self.assertRaises(OSError):reporting.finalize(ctx)
        self.assertEqual(digest(pointer),old)
        self.assertEqual({p.name for p in releases.iterdir()},before)
        reporting.load_release(self.root/read_json(pointer)["manifest"])

    def test_readback_failure_preserves_old_release_and_success_is_immutable(self):
        ctx=self.ctx;pointer=ctx.path("manifests/final_results.json");before=digest(pointer)
        releases=ctx.path("manifests/releases");names={p.name for p in releases.iterdir()}
        old_manifest=self.root/read_json(pointer)["manifest"];old=digest(old_manifest)
        with patch("src.reporting.load_release",side_effect=ValueError("synthetic validation failure")):
            with self.assertRaisesRegex(ValueError,"validation"):reporting.finalize(ctx)
        self.assertEqual(digest(pointer),before);self.assertEqual({p.name for p in releases.iterdir()},names)
        reporting.finalize(ctx)
        new_manifest=self.root/read_json(pointer)["manifest"]
        self.assertNotEqual(new_manifest,old_manifest);self.assertEqual(digest(old_manifest),old)
        reporting.load_release(new_manifest);reporting.load_release(old_manifest)
        self.assertEqual(reporting.load_release(new_manifest),old_reporting.load_release(new_manifest))

    def test_pointer_failure_leaves_only_a_complete_unreferenced_snapshot(self):
        ctx=self.ctx;pointer=ctx.path("manifests/final_results.json");before=digest(pointer)
        releases=ctx.path("manifests/releases");names={p.name for p in releases.iterdir()}
        with patch.object(ctx,"json",side_effect=OSError("synthetic pointer failure")):
            with self.assertRaisesRegex(OSError,"pointer"):reporting.finalize(ctx)
        self.assertEqual(digest(pointer),before)
        added=[p for p in releases.iterdir() if p.name not in names]
        self.assertEqual(len(added),1);self.assertFalse(added[0].name.startswith(".pubg-release-"))
        reporting.load_release(added[0]/"manifest.json")

    def test_loader_rejects_duplicate_size_and_forged_corrupt_parquet(self):
        pointer=read_json(self.ctx.path("manifests/final_results.json"));path=self.root/pointer["manifest"]
        original=read_json(path)
        for kind in ("duplicate","size","parquet"):
            manifest=copy.deepcopy(original)
            if kind=="duplicate":manifest["entries"].append(manifest["entries"][0])
            elif kind=="size":manifest["entries"][0]["bytes"]+=1
            else:
                entry=next(e for e in manifest["entries"] if e["path"].endswith(".parquet"))
                corrupt=path.parent/entry["path"];corrupt.write_bytes(b"not a parquet file")
                entry.update(sha256=digest(corrupt),bytes=corrupt.stat().st_size)
            write_json(manifest,path)
            if kind=="parquet":old_reporting.load_release(path)
            with self.subTest(kind=kind),self.assertRaises(Exception):reporting.load_release(path)

    def test_report_only_uses_bounded_csv_reads_and_does_not_write(self):
        pointer=read_json(self.ctx.path("manifests/final_results.json"));path=self.root/pointer["manifest"]
        before={p.relative_to(self.root).as_posix():digest(p) for p in self.root.rglob("*") if p.is_file()}
        read=pd.read_csv;calls=[]
        def bounded(*args,**kwargs):
            calls.append(kwargs)
            if kwargs.get("nrows")!=25 and kwargs.get("chunksize")!=50000:
                raise AssertionError("Unbounded CSV read in report_only")
            return read(*args,**kwargs)
        with patch("pandas.read_csv",side_effect=bounded),patch("IPython.display.display"),patch("IPython.display.Image"),patch("pandas.read_parquet",side_effect=AssertionError("No full Parquet frame")):
            reporting.display_release(path)
        self.assertTrue(any(c.get("nrows")==25 for c in calls))
        self.assertEqual(before,{p.relative_to(self.root).as_posix():digest(p) for p in self.root.rglob("*") if p.is_file()})


if __name__=="__main__":unittest.main()
