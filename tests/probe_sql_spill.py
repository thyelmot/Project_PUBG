"""Subprocess probe: a native DuckDB failure must not kill the test runner."""
import argparse
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from src.io import Context,quote
from test_data_features import fixture


def probe(shared=False):
    root=Path(tempfile.mkdtemp(prefix="pubg-d5-spill-probe-"));fixture(root)
    ctx=Context(root,"development");ctx.cfg["runtime"]["duckdb_memory"]="64MiB"
    print("ROOT",root,"SHARED_RECONSTRUCTION",shared,flush=True)
    with ctx.disk_db() as parent:
        if shared:parent.execute("SET temp_directory="+quote(ctx.temp))
        print("PARENT_TEMP",parent.execute("SELECT current_setting('temp_directory')").fetchone()[0],flush=True)
        reader=parent.execute("SELECT i,sha256(CAST(i AS VARCHAR)) k FROM range(1000000) t(i) ORDER BY k").fetch_record_batch(50000)
        seen=np.zeros(1000000,dtype=bool);count=0;total=0
        def accept(batch):
            nonlocal count,total
            ids=batch.column(0).to_numpy()
            if seen[ids].any() or len(np.unique(ids))!=len(ids):raise AssertionError("Duplicate spilled row IDs")
            seen[ids]=True;count+=len(ids);total+=int(ids.sum())
        try:
            accept(next(reader))
            with ctx.disk_db() as child:
                if shared:child.execute("SET temp_directory="+quote(ctx.temp))
                print("CHILD_TEMP",child.execute("SELECT current_setting('temp_directory')").fetchone()[0],flush=True)
                child.execute("CREATE TABLE other AS SELECT i,sha256(CAST(i+1 AS VARCHAR)) k FROM range(1000000) t(i) ORDER BY k")
                assert child.execute("SELECT count(*) FROM other").fetchone()[0]==1000000
            print("CHILD_CLOSED_RESUME_PARENT",flush=True)
            for batch in reader:accept(batch)
            assert count==1000000 and total==499999500000 and seen.all()
        finally:reader.close()
    assert not list(ctx.temp.glob("pubg-sql-*"))
    print("PASSED",count,total,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--shared",action="store_true");args=parser.parse_args()
    probe(args.shared)
