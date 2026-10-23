"""Full-key profile aggregation parity and bounded-SQL regression, synthetic CPU only."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb
import numpy as np
import pandas as pd

from src import analysis
from src.io import Context, digest, quote
from test_data_features import fixture, run_features
import reference_clustering_v58 as reference


class ProfilePartitions(unittest.TestCase):
    def compare(self, actual, expected):
        keys=["team_size_mode","player_name"]
        actual=actual.sort_values(keys).reset_index(drop=True)
        expected=expected.sort_values(keys).reset_index(drop=True)
        self.assertEqual(list(actual),list(expected))
        pd.testing.assert_frame_equal(actual.isna(),expected.isna(),check_exact=True)
        pd.testing.assert_frame_equal(actual,expected,rtol=1e-9,atol=1e-10)

    def test_unicode_null_singletons_scope_and_conditional_denominators(self):
        with tempfile.TemporaryDirectory(prefix="pubg-profile-parity-") as folder:
            root=Path(folder);fixture(root);ctx=run_features(root)
            frame=pd.read_parquet(ctx.data/"player_match.parquet")
            frame["player_name"]=["Người|'_"+str(i%13) if i%17 else None for i in range(len(frame))]
            frame["team_size_mode"]=np.resize(["Solo","Duo","Squad","Other",None],len(frame))
            frame.loc[frame.index%7==0,"player_dmg"]=np.nan
            frame.loc[frame.index%11==0,"walk_ratio"]=np.nan
            frame.loc[frame.index%9==0,"early_kill_ratio"]=np.nan
            frame.to_parquet(ctx.data/"player_match.parquet",index=False)
            original=digest(ctx.data/"player_match.parquet")
            with ctx.disk_db() as con:
                settings=con.execute("SELECT current_setting('threads'),current_setting('partitioned_write_max_open_files')").fetchone()
                for development in (True,False):
                    self.compare(analysis.bounded_profiles(con,ctx,development),reference.profiles(con,ctx,development))
                    self.assertEqual(con.execute("SELECT current_setting('threads'),current_setting('partitioned_write_max_open_files')").fetchone(),settings)
                frame["split"]="test";frame.to_parquet(ctx.data/"player_match.parquet",index=False)
                self.compare(analysis.profiles(con,ctx,True),reference.profiles(con,ctx,True))
                frame["player_name"]=None;frame.to_parquet(ctx.data/"player_match.parquet",index=False)
                self.compare(analysis.profiles(con,ctx,False),reference.profiles(con,ctx,False))
            self.assertFalse(list(ctx.temp.glob("pubg-profiles-*")))
            self.assertNotEqual(digest(ctx.data/"player_match.parquet"),original)  # Only our fixture mutation.

    def test_normalized_joins_match_materialized_reference(self):
        from test_data_features import write_config
        with tempfile.TemporaryDirectory(prefix="pubg-profile-normalized-") as folder:
            root=Path(folder);cfg=fixture(root);cfg["storage"]["layout"]="normalized_v1"
            write_config(root,cfg);ctx=run_features(root)
            with ctx.disk_db() as con:
                for development in (True,False):
                    self.compare(analysis.profiles(con,ctx,development),reference.profiles(con,ctx,development))

    def test_low_sql_memory_where_monolithic_aggregation_fails(self):
        with tempfile.TemporaryDirectory(prefix="pubg-profile-stress-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            ctx.data.mkdir(parents=True,exist_ok=True)
            target=ctx.data/"player_match.parquet"
            with ctx.db() as con:
                # 180k complete groups, each split across three source rows/row groups.
                query="""SELECT 'Người_'||repeat('x',48)||CAST(i%180000 AS VARCHAR) player_name,
                    CASE WHEN i%3=0 THEN 'Solo' WHEN i%3=1 THEN 'Duo' ELSE 'Squad' END team_size_mode,
                    CASE WHEN i>=360000 THEN 'test' ELSE 'train' END split,
                    CAST(i%5 AS DOUBLE) player_kills,CAST(i%7 AS DOUBLE) player_dmg,
                    1.0 player_dist_walk,2.0 player_dist_ride,1.0/3 walk_ratio,
                    1.0 player_assists,1.0 player_dbno,0.25 assist_ratio,
                    0.5 early_kill_ratio,0.25 mid_kill_ratio,0.25 late_kill_ratio,
                    'phase_observed' timing_status,1 early_kills,100.0 player_survive_time,
                    true valid_survival,0.5 normalized_placement FROM range(540000) t(i)"""
                con.execute(f"COPY ({query}) TO {quote(target)} (FORMAT PARQUET,ROW_GROUP_SIZE 8192)")
                expected=reference.profiles(con,ctx,False)
            original=digest(target)
            ctx.cfg["runtime"]["duckdb_memory"]="64MiB"
            with ctx.disk_db() as con:
                with self.assertRaises(duckdb.OutOfMemoryException):reference.profiles(con,ctx,False)
            with ctx.disk_db() as con:
                actual=analysis.profiles(con,ctx,False)
            self.compare(actual,expected)
            self.assertEqual(len(actual),180000)
            self.assertTrue(actual.games_played.eq(3).all())
            self.assertTrue(actual.survival_n.eq(2).all())
            self.assertEqual(digest(target),original)
            self.assertFalse(list(ctx.temp.glob("pubg-profiles-*")))

    def test_memory_guard_and_failure_cleanup_restore_connection_settings(self):
        with tempfile.TemporaryDirectory(prefix="pubg-profile-failure-") as folder:
            root=Path(folder);fixture(root);ctx=run_features(root)
            original=digest(ctx.data/"player_match.parquet")
            with ctx.disk_db() as con:
                settings=con.execute("SELECT current_setting('threads'),current_setting('partitioned_write_max_open_files')").fetchone()
                with patch("src.analysis.require_memory",side_effect=MemoryError("guard")):
                    with self.assertRaisesRegex(MemoryError,"guard"):analysis.profiles(con,ctx)
                self.assertEqual(con.execute("SELECT current_setting('threads'),current_setting('partitioned_write_max_open_files')").fetchone(),settings)
                self.assertFalse(con.execute("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'rq2_profile_%'").fetchall())
                with patch.object(ctx,"progress",side_effect=OSError("simulated disk failure")):
                    with self.assertRaisesRegex(OSError,"disk failure"):analysis.profiles(con,ctx)
                self.compare(analysis.profiles(con,ctx),reference.profiles(con,ctx))
            self.assertEqual(digest(ctx.data/"player_match.parquet"),original)
            self.assertFalse(list(ctx.temp.glob("pubg-profiles-*")))


if __name__ == "__main__":unittest.main()
