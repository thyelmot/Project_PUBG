import errno
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pyarrow.parquet as pq

from src import features
from src.io import Context, digest
from src.preprocessing import ingest, clean_split
from test_data_features import fixture, write_config
import reference_features_v56 as reference


# Fixed before comparison: SQL double sums may differ by summation order only.
RTOL, ATOL = 1e-12, 1e-12


def sorted_frame(frame, keys):
    return frame.sort_values(keys, na_position="first").reset_index(drop=True)


def synthetic_timing(ctx, rows=600000):
    """Deterministic stress input, not source evidence or a research cohort."""
    with ctx.disk_db() as con:
        ctx.parquet(con,f"""SELECT 'm'||CAST(i//6 AS VARCHAR) match_id,
            'p'||CAST((i%6)//3 AS VARCHAR) killer_name,'v'||CAST(i AS VARCHAR) victim_name,
            CAST((i%3)*100 AS DOUBLE) event_time,CAST(i AS VARCHAR) raw_event_id,
            sha256(CAST(i AS VARCHAR)) raw_detail FROM range({rows}) t(i)""","event")
        ctx.parquet(con,f"SELECT 'm'||CAST(i AS VARCHAR) match_id,300.0::DOUBLE duration_proxy FROM range({rows//6}) t(i)","match_metadata")
        ctx.parquet(con,f"""SELECT 'r'||CAST(i AS VARCHAR) row_id,'m'||CAST(i//2 AS VARCHAR) match_id,
            'p'||CAST(i%2 AS VARCHAR) player_name,3.0::DOUBLE player_kills,'Duo' team_size_mode
            FROM range({rows//3}) t(i)""","base")


class FeaturesOutOfCore(unittest.TestCase):
    def assert_frame(self, actual, expected, keys):
        actual, expected = sorted_frame(actual, keys), sorted_frame(expected, keys)
        self.assertEqual(list(actual.columns), list(expected.columns))
        pd.testing.assert_frame_equal(actual.isna(), expected.isna(), check_exact=True)
        exact = [c for c in actual if not pd.api.types.is_float_dtype(actual[c])]
        pd.testing.assert_frame_equal(actual[exact], expected[exact], check_exact=True)
        pd.testing.assert_frame_equal(actual, expected, rtol=RTOL, atol=ATOL)

    def test_s03_s04_match_frozen_v56_across_partitions_and_shards(self):
        with tempfile.TemporaryDirectory(prefix="pubg-feature-parity-") as folder:
            root = Path(folder); fixture(root); raw = root / "raw_fixture"
            for path in raw.glob("agg*.csv"):
                frame = pd.read_csv(path)
                frame.loc[frame.match_id.eq("match0"), "player_survive_time"] = 300
                frame.loc[frame.match_id.eq("match1"), "player_survive_time"] = 59
                frame.loc[frame.match_id.eq("match2"), "player_survive_time"] = float("nan")
                frame.to_csv(path, index=False)
            events = [{"match_id":"match0", "killer_name":"player1", "victim_name":f"v{i}",
                       "time":t, "killed_by":"rifle"}
                      for i,t in enumerate([0, 100, 100, 200, 300, 999, -1, float("inf"), None])]
            events += [dict(events[0]), dict(events[0], killed_by="different raw content"),
                       dict(events[0], killer_name="player0", victim_name="player0"),
                       dict(events[0], killer_name=None), dict(events[0], victim_name=None),
                       dict(events[0], match_id="match1"), dict(events[0], match_id="match2"),
                       dict(events[0], match_id=None), dict(events[0], match_id="orphan"),
                       dict(events[0], killer_name="Tên Unicode", match_id="trận Unicode")]
            pd.DataFrame(events[::2]).to_csv(raw/"kill_match_stats_0.csv", index=False)
            pd.DataFrame(events[1::2]+[events[0]]).to_csv(raw/"kill_match_stats_1.csv", index=False)
            ctx = Context(root, "development", progress=lambda _:None)
            ctx.run("S01", ingest); ctx.run("S02", clean_split)
            source_hashes = {p.name:digest(p) for p in ctx.data.glob("*.parquet")}
            reference.base_features(ctx)
            expected_base = pd.read_parquet(ctx.data/"base.parquet")
            base_schema = pq.read_schema(ctx.data/"base.parquet")
            expected_tables = {name:pd.read_csv(ctx.path("tables/"+name+".csv"))
                               for name in ("feature_validation", "feature_dictionary", "feature_example")}
            features.base_features(ctx)
            self.assertEqual(pq.read_schema(ctx.data/"base.parquet"), base_schema)
            self.assert_frame(pd.read_parquet(ctx.data/"base.parquet"), expected_base, ["row_id"])
            for name, expected in expected_tables.items():
                self.assert_frame(pd.read_csv(ctx.path("tables/"+name+".csv")), expected, [expected.columns[0]])
            reference.combat_timing(ctx)
            expected = pd.read_parquet(ctx.data/"player_match.parquet")
            expected_schema = pq.read_schema(ctx.data/"player_match.parquet")
            discrepancy = pd.read_parquet(ctx.data/"kill_discrepancy.parquet")
            tables = {name:pd.read_csv(ctx.path("tables/"+name+".csv")) for name in (
                "event_unit_diagnostics", "timing_coverage", "timing_discrepancy_summary",
                "timing_phase_summary", "timing_audit")}
            for parts in (1, 2, 7, 16):
                with self.subTest(partitions=parts):
                    ctx.cfg["timing"]["partitions"] = parts
                    features.combat_timing(ctx)
                    self.assertEqual(pq.read_schema(ctx.data/"player_match.parquet"), expected_schema)
                    self.assert_frame(pd.read_parquet(ctx.data/"player_match.parquet"), expected, ["row_id"])
                    self.assert_frame(pd.read_parquet(ctx.data/"kill_discrepancy.parquet"), discrepancy, ["row_id"])
                    for name, table in tables.items():
                        keys = ["team_size_mode", "timing_status"] if name=="timing_coverage" else [table.columns[0]]
                        self.assert_frame(pd.read_csv(ctx.path("tables/"+name+".csv")), table, keys)
                    audit = pd.read_csv(ctx.path("tables/timing_partition_audit.csv"))
                    self.assertEqual(audit.input_events.sum(), len(events)+1)
                    self.assertEqual(audit.player_rows_after.sum(), len(expected))
                    self.assertTrue(audit.player_rows_before.eq(audit.player_rows_after).all())
                    self.assertEqual(audit.unique_events.sum(), tables["timing_audit"].unique_events.iloc[0])
                    self.assertFalse(list(ctx.temp.glob("pubg-timing-*")))
                    self.assertFalse(list(ctx.temp.glob("pubg-sql-*")))
            self.assertEqual(source_hashes, {name:digest(ctx.data/name) for name in source_hashes})

    def test_empty_events_and_empty_base_preserve_schema_and_missing_rules(self):
        with tempfile.TemporaryDirectory(prefix="pubg-empty-timing-") as folder:
            root = Path(folder); fixture(root); ctx = Context(root, "development", progress=lambda _:None)
            ctx.run("S01", ingest); ctx.run("S02", clean_split); ctx.run("S03", features.base_features)
            frame = pd.read_parquet(ctx.data/"event.parquet")
            frame.iloc[:0].to_parquet(ctx.data/"event.parquet", index=False)
            for empty_base in (False, True):
                if empty_base:
                    base = pd.read_parquet(ctx.data/"base.parquet")
                    base.iloc[:0].to_parquet(ctx.data/"base.parquet", index=False)
                reference.combat_timing(ctx)
                expected = pd.read_parquet(ctx.data/"player_match.parquet")
                expected_schema = pq.read_schema(ctx.data/"player_match.parquet")
                features.combat_timing(ctx)
                self.assertEqual(pq.read_schema(ctx.data/"player_match.parquet"), expected_schema)
                self.assert_frame(pd.read_parquet(ctx.data/"player_match.parquet"), expected, ["row_id"])

    def test_partition_failure_preserves_good_output_and_cleans_only_owned_scratch(self):
        with tempfile.TemporaryDirectory(prefix="pubg-timing-failure-") as folder:
            root = Path(folder); cfg = fixture(root); ctx = Context(root,"development",progress=lambda _:None)
            for stage,fn in (("S01",ingest),("S02",clean_split),("S03",features.base_features),("S04",features.combat_timing)):
                ctx.run(stage,fn)
            target = ctx.data/"player_match.parquet"; old = digest(target)
            unrelated = ctx.temp/"keep.txt"; unrelated.write_text("not owned by S04")
            cfg["timing"]["partitions"] = 3; write_config(root,cfg)
            ctx = Context(root,"development",progress=lambda _:None)
            # Reuse the same runtime scratch to check ownership, not a separate empty folder.
            ctx.temp = unrelated.parent
            # The existing conservative signature includes timing in S03 as well.
            ctx.run("S03",features.base_features)
            build = features.build_timing_partition; calls = []
            def fail_second(con,minimum):
                calls.append(1)
                if len(calls)==2:raise OSError(errno.ENOSPC,"simulated partition disk full")
                return build(con,minimum)
            with patch("src.features.build_timing_partition",side_effect=fail_second):
                with self.assertRaises(OSError):ctx.run("S04",features.combat_timing)
            self.assertEqual(len(calls),2)
            self.assertEqual(digest(target),old)
            self.assertEqual(ctx.manifest()["S04"]["status"],"resource_limited")
            self.assertEqual(list(ctx.temp.iterdir()),[unrelated])
            self.assertEqual(unrelated.read_text(),"not owned by S04")
            ctx.run("S04",features.combat_timing)
            self.assertEqual(ctx.require("S04")["status"],"completed")

    def test_partition_config_rejects_non_integer_or_unbounded_counts(self):
        with tempfile.TemporaryDirectory(prefix="pubg-timing-config-") as folder:
            root = Path(folder); cfg = fixture(root)
            for value in (0,257,True,1.5,"16"):
                cfg["timing"]["partitions"] = value; write_config(root,cfg)
                with self.assertRaisesRegex(ValueError,"timing.partitions"):
                    Context(root,"development")

    def test_600000_events_at_128mib_without_sampling(self):
        with tempfile.TemporaryDirectory(prefix="pubg-timing-128mib-") as folder:
            root=Path(folder);cfg=fixture(root)
            cfg["runtime"]["duckdb_memory"]="128MiB"
            cfg["timing"]["partitions"]=16;write_config(root,cfg)
            ctx=Context(root,"development",progress=lambda _:None)
            synthetic_timing(ctx)
            features.combat_timing(ctx)
            with ctx.db() as con:
                ctx.view(con,"p","player_match")
                row=con.execute("""SELECT count(*),count(distinct row_id),sum(event_kill_count),
                    min(first_kill_time),min(avg_kill_time),max(avg_kill_time),
                    sum(early_kills),sum(mid_kills),sum(late_kills) FROM p""").fetchone()
                self.assertEqual(row,(200000,200000,600000,0.,100.,100.,200000,200000,200000))
            audit=pd.read_csv(ctx.path("tables/timing_audit.csv")).iloc[0]
            self.assertEqual((audit.input_events,audit.unique_events,audit.phase_eligible),(600000,600000,600000))
            self.assertFalse(list(ctx.temp.glob("pubg-timing-*")))
            self.assertFalse(list(ctx.temp.glob("pubg-sql-*")))

    def test_duplicate_metadata_fails_before_replacing_base(self):
        with tempfile.TemporaryDirectory(prefix="pubg-feature-join-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development",progress=lambda _:None)
            for stage,fn in (("S01",ingest),("S02",clean_split),("S03",features.base_features)):
                ctx.run(stage,fn)
            target=ctx.data/"base.parquet";old=digest(target)
            metadata=pd.read_parquet(ctx.data/"match_metadata.parquet")
            pd.concat([metadata,metadata.iloc[:1]]).to_parquet(ctx.data/"match_metadata.parquet",index=False)
            with self.assertRaisesRegex(ValueError,"match key is not unique"):features.base_features(ctx)
            self.assertEqual(digest(target),old)
            with self.assertRaisesRegex(ValueError,"match key is not unique"):features.combat_timing(ctx)
            metadata.iloc[1:].to_parquet(ctx.data/"match_metadata.parquet",index=False)
            with self.assertRaisesRegex(ValueError,"missing metadata"):features.base_features(ctx)
            self.assertEqual(digest(target),old)


if __name__=="__main__":unittest.main()
