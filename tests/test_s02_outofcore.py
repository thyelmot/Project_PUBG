"""Exact parity against the previous metadata query, not a full-data benchmark."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.io import Context, digest
from src.preprocessing import build_match_metadata, clean_split, ingest
from test_data_features import fixture, write_config


def reference_metadata(con):
    con.execute("CREATE TABLE team_check AS SELECT match_id,team_id,count(distinct team_placement) ranks FROM clean WHERE team_id IS NOT NULL GROUP BY ALL")
    con.execute("""CREATE TABLE metadata AS SELECT c.match_id,
        count(distinct c.team_id) n_teams,count(*) roster_rows,
        count(*) FILTER(WHERE c.team_id IS NULL) missing_team_rows,
        max(c.team_placement) max_placement,
        max(c.player_survive_time) FILTER(WHERE c.player_survive_time>=0 AND isfinite(c.player_survive_time)) duration_proxy,
        min(try_cast(c.date AS TIMESTAMP)) match_time,
        count(distinct c.date) dates,count(distinct c.party_size) party_values,
        count(*) FILTER(WHERE c.date IS NULL OR try_cast(c.date AS TIMESTAMP) IS NULL) bad_dates,
        count(distinct c.team_id) FILTER(WHERE t.ranks>1) conflicting_teams
        FROM clean c LEFT JOIN team_check t USING(match_id,team_id) GROUP BY c.match_id""")


class S02OutOfCore(unittest.TestCase):
    def test_synthetic_metadata_1200000_rows_at_64mib(self):
        with tempfile.TemporaryDirectory(prefix="pubg-s02-64mib-") as folder:
            root=Path(folder);cfg=fixture(root)
            cfg["runtime"]["duckdb_memory"]="64MiB";write_config(root,cfg)
            ctx=Context(root,"development")
            with ctx.disk_db() as con:
                con.execute("""CREATE TABLE clean AS SELECT 'm'||CAST(i//10 AS VARCHAR) match_id,
                    't'||CAST(i%100000 AS VARCHAR) team_id,CAST(i%10+1 AS DOUBLE) team_placement,
                    CAST(300+i%1500 AS DOUBLE) player_survive_time,
                    CASE WHEN i%3=0 THEN '2026-01-01' ELSE '2026-01-02' END date,
                    CAST(CASE WHEN i%2=0 THEN 1 ELSE 2 END AS DOUBLE) party_size
                    FROM range(1200000) t(i)""")
                build_match_metadata(con)
                row=con.execute("SELECT count(*),sum(roster_rows),sum(n_teams),sum(conflicting_teams),min(dates),min(party_values) FROM metadata").fetchone()
                self.assertEqual(row,(120000,1200000,1200000,0,2,2))
            self.assertFalse(list(ctx.temp.glob("pubg-sql-*")))

    def test_metadata_exact_null_conflict_date_and_nonfinite_parity(self):
        frame=pd.DataFrame({
            "match_id":["a"]*5+["b"]*2+["c"]*2,
            "team_id":["t","t","u",None,None,None,None,"z","z"],
            "team_placement":[1.,2.,np.nan,4.,np.nan,np.nan,np.nan,1.,1.],
            "player_survive_time":[10.,20.,np.inf,-1.,np.nan,-2.,np.nan,30.,40.],
            "date":["2026-01-01","2026-01-01","bad",None,"2026-01-02",None,None,"2026-01-03","2026-01-03"],
            "party_size":[1.,2.,np.nan,1.,np.nan,np.nan,np.nan,4.,4.]})
        with tempfile.TemporaryDirectory(prefix="pubg-s02-null-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            outputs=[]
            for build in (reference_metadata,build_match_metadata):
                with ctx.disk_db() as con:
                    con.register("source",frame)
                    con.execute("CREATE TABLE clean AS SELECT * FROM source")
                    build(con)
                    outputs.append(con.execute("SELECT * FROM metadata ORDER BY match_id").df())
            pd.testing.assert_frame_equal(*outputs)
            b=outputs[1].set_index("match_id").loc["b"]
            self.assertEqual((b.n_teams,b.dates,b.party_values,b.conflicting_teams),(0,0,0,0))
            self.assertFalse(list(ctx.temp.glob("pubg-sql-*")))

    def test_clean_split_outputs_match_reference_and_preserve_s01(self):
        with tempfile.TemporaryDirectory(prefix="pubg-s02-parity-") as folder:
            roots=[Path(folder)/name for name in ("old","new")]
            for root in roots:
                cfg=fixture(root);cfg["runtime"]["duckdb_memory"]="128MiB";write_config(root,cfg)
                # Adversarial changes span source shards; neither implementation may keep-first.
                for path in (root/"raw_fixture").glob("agg_match_stats*.csv"):
                    frame=pd.read_csv(path)
                    frame.loc[frame.match_id.eq("match0"),"team_id"]=None
                    frame.loc[frame.match_id.eq("match1"),"date"]=None
                    extra=frame.iloc[:1].copy();extra["player_dmg"]+=1
                    pd.concat([frame,extra],ignore_index=True).to_csv(path,index=False)
                cfg["preprocessing"].update(chronology_grade="C",chronology_reason="synthetic parity")
                write_config(root,cfg)
                ctx=Context(root,"development");ctx.run("S01",ingest)
                source_hashes={p.name:digest(p) for p in ctx.data.glob("*.parquet")}
                with patch("src.preprocessing.build_match_metadata",side_effect=reference_metadata) if root==roots[0] else patch("src.preprocessing.build_match_metadata",wraps=build_match_metadata):
                    ctx.run("S02",clean_split)
                self.assertEqual(source_hashes,{p.name:digest(p) for p in ctx.data.glob("*.parquet") if p.name in source_hashes})
                ctx.require("S01")
                manifest_hash=digest(ctx.manifest_path)
                ctx.cfg["runtime"]["duckdb_memory"]="256MiB"
                with self.assertRaisesRegex(RuntimeError,"stale"):ctx.require("S01")
                self.assertEqual(digest(ctx.manifest_path),manifest_hash)
                self.assertFalse(list(ctx.temp.glob("pubg-sql-*")))
            for name,key in (("cleaned","row_id"),("match_metadata","match_id"),("split","match_id")):
                frames=[pd.read_parquet(r/f"data/development/{name}.parquet").sort_values(key).reset_index(drop=True) for r in roots]
                pd.testing.assert_frame_equal(*frames)
            for name in ("removal_ledger","quality_flags","identity_conflicts","split_summary"):
                frames=[pd.read_csv(r/f"outputs/development/tables/{name}.csv") for r in roots]
                pd.testing.assert_frame_equal(*frames)

    def test_disk_database_closes_and_cleans_only_owned_files_on_error(self):
        with tempfile.TemporaryDirectory(prefix="pubg-s02-cleanup-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            unrelated=ctx.temp/"keep.txt";unrelated.write_text("keep",encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError,"injected"):
                with ctx.disk_db() as con:
                    con.execute("CREATE TABLE a AS SELECT 1 x")
                    path=Path(con.execute("SELECT path FROM duckdb_databases() WHERE database_name='stage'").fetchone()[0])
                    self.assertTrue(path.is_file())
                    raise RuntimeError("injected")
            self.assertEqual(list(ctx.temp.iterdir()),[unrelated])
