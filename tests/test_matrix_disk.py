"""SQL JOIN/sort separation, low-memory full cohorts and owned-scratch cleanup; CPU only."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import duckdb

from src import modeling
from src.features import FEATURES,TARGETS
from src.io import Context,digest,ident,quote
from test_data_features import fixture,write_config
from test_model_dataflow import matrix_fixture


class MatrixDisk(unittest.TestCase):
    def test_joined_1200000_rows_at_128mib_preserve_every_matrix_row(self):
        with tempfile.TemporaryDirectory(prefix='pubg-matrix-lowmem-') as folder:
            root=Path(folder);cfg=fixture(root);cfg['runtime']['duckdb_memory']='128MiB'
            write_config(root,cfg);ctx=Context(root,'development',progress=lambda _:None);n=1200000
            left=root/'numeric.parquet';right=root/'identity.parquet'
            expressions=','.join(f'CAST((i*{j+1})%29 AS DOUBLE)/7 AS {ident(c)}' for j,c in enumerate(FEATURES['s1']))
            with ctx.disk_db() as con:
                con.execute(f'COPY (SELECT i k,{expressions} FROM range({n}) t(i)) TO {quote(left)} (FORMAT PARQUET)')
                con.execute(f"COPY (SELECT i k,sha256(CAST(i AS VARCHAR)) row_id,"
                    "'m:'||CAST(i AS VARCHAR)||':'||repeat('trận',12) match_id,"
                    "'player'||CAST(i%23 AS VARCHAR) player_name,"
                    "CASE WHEN i%13=0 THEN NULL ELSE 'đội'||CAST(i%7 AS VARCHAR) END team_id,"
                    "'Duo' team_size_mode,'train' split,true valid_survival,"
                    f"CAST(10+i%17 AS DOUBLE) player_survive_time FROM range({n}) t(i)) TO {quote(right)} (FORMAT PARQUET)")
                con.execute(f'CREATE VIEW p AS SELECT l.* EXCLUDE(k),r.* EXCLUDE(k) '
                            f'FROM read_parquet({quote(left)}) l JOIN read_parquet({quote(right)}) r USING(k)')
                before={p.name:digest(p) for p in (left,right)}
                # Same data/budget: the original combined JOIN+sort must reproduce the failure.
                fields=['row_id','match_id','team_id','team_size_mode','split',TARGETS['s1'],*FEATURES['s1']]
                reader=None
                # Arrow can surface a deferred DuckDB OOM as OSError while consuming the reader.
                with self.assertRaisesRegex((duckdb.OutOfMemoryException,OSError),'[Oo]ut of [Mm]emory'):
                    try:
                        reader=con.execute(f"SELECT {','.join(ident(c) for c in fields)} FROM p "
                            "WHERE split='train' AND valid_survival ORDER BY row_id").fetch_record_batch(50000)
                        for batch in reader:pass
                    finally:
                        if reader is not None:reader.close()
                bundle=modeling.matrix_data(ctx,con,'s1','train',root)
                self.assertEqual(con.execute("SELECT current_setting('threads')").fetchone()[0],2)
                self.assertEqual(con.execute("SELECT current_setting('memory_limit')").fetchone()[0],'128.0 MiB')
            X=np.load(bundle['X'],mmap_mode='r');y=np.load(bundle['y'],mmap_mode='r');offset=0;last=None
            try:
                for batch in pq.ParquetFile(bundle['metadata']).iter_batches(batch_size=50000):
                    frame=batch.to_pandas();ids=frame.row_id
                    self.assertTrue(ids.is_unique and ids.is_monotonic_increasing)
                    if last is not None:self.assertLess(last,ids.iloc[0])
                    last=ids.iloc[-1];i=frame.match_id.str.split(':').str[1].to_numpy(dtype=np.int64)
                    expected=np.column_stack([((i*(j+1))%29)/7 for j in range(len(FEATURES['s1']))])
                    end=offset+len(frame)
                    np.testing.assert_array_equal(X[offset:end],expected)
                    np.testing.assert_array_equal(y[offset:end],10+i%17)
                    np.testing.assert_array_equal(frame[TARGETS['s1']],y[offset:end]);offset=end
                self.assertEqual(offset,n);self.assertEqual(bundle['cohort']['rows'],n)
                self.assertEqual(bundle['cohort']['matches'],n);self.assertEqual(bundle['cohort']['players'],23)
            finally:modeling.close_mmaps(X,y)
            self.assertEqual(before,{p.name:digest(p) for p in (left,right)})
            self.assertFalse(list(root.glob('pubg-matrix-source-*')))
            self.assertFalse(list(ctx.temp.glob('pubg-sql-*')))

    def test_projection_has_no_sort_and_sort_connection_has_no_join(self):
        with tempfile.TemporaryDirectory(prefix='pubg-matrix-plan-') as folder:
            root=Path(folder);fixture(root);ctx=Context(root,'development');frame=matrix_fixture(ctx,100007)
            frame['row_id']=['é/β_'+str(i) if i%2 else 'a_'+str(i) for i in range(len(frame))]
            frame.loc[0,TARGETS['s1']]=-0.0
            frame.iloc[::-1].to_parquet(ctx.data/'player_match.parquet',index=False)
            observed={};real=modeling._matrix_data
            def inspect(ctx,scan,task,split,work):
                observed['threads']=scan.execute("SELECT current_setting('threads')").fetchone()[0]
                observed['sql']=scan.execute("SELECT sql FROM duckdb_views() WHERE view_name='p'").fetchone()[0]
                return real(ctx,scan,task,split,work)
            with ctx.disk_db() as con:
                ctx.view(con,'p','player_match')
                queries=[]
                class Logged:
                    def execute(self,sql,*args):
                        queries.append(sql);return con.execute(sql,*args)
                with patch('src.modeling._matrix_data',side_effect=inspect):bundle=modeling.matrix_data(ctx,Logged(),'s1','train',root)
                copies=[sql for sql in queries if sql.startswith('COPY ')]
                self.assertEqual(len(copies),1);self.assertNotIn('ORDER BY',copies[0].upper())
            self.assertEqual(observed['threads'],1)
            self.assertIn('read_parquet',observed['sql']);self.assertNotIn('JOIN',observed['sql'].upper())
            expected=frame.sort_values('row_id').reset_index(drop=True)
            pd.testing.assert_series_equal(pd.read_parquet(bundle['metadata']).row_id,expected.row_id)
            y=np.load(bundle['y'],mmap_mode='r')
            try:
                np.testing.assert_array_equal(y,expected[TARGETS['s1']])
                np.testing.assert_array_equal(np.signbit(y),np.signbit(expected[TARGETS['s1']]))
            finally:modeling.close_mmaps(y)

    def test_failure_restores_parent_settings_and_removes_only_owned_projection(self):
        with tempfile.TemporaryDirectory(prefix='pubg-matrix-fail-') as folder:
            root=Path(folder);fixture(root);ctx=Context(root,'development');matrix_fixture(ctx,20)
            unrelated=root/'keep.parquet';unrelated.write_bytes(b'unrelated user file')
            before=digest(ctx.data/'player_match.parquet')
            with ctx.disk_db() as con:
                ctx.view(con,'p','player_match')
                with patch('src.modeling._matrix_data',side_effect=OSError('simulated disk/sort failure')):
                    with self.assertRaisesRegex(OSError,'simulated'):modeling.matrix_data(ctx,con,'s1','train',root)
                self.assertEqual(con.execute("SELECT current_setting('threads')").fetchone()[0],2)
                con.execute('DROP VIEW p')
                with self.assertRaises(duckdb.CatalogException):modeling.matrix_data(ctx,con,'s1','train',root)
                self.assertEqual(con.execute("SELECT current_setting('threads')").fetchone()[0],2)
            self.assertEqual(unrelated.read_bytes(),b'unrelated user file')
            self.assertEqual(before,digest(ctx.data/'player_match.parquet'))
            self.assertFalse(list(root.glob('pubg-matrix-source-*')))
            self.assertFalse(list(ctx.temp.glob('pubg-sql-*')))


if __name__=='__main__':unittest.main()
