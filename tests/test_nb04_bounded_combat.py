"""NB04 preserves all events while avoiding wide global audit windows."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import duckdb

from src.data.checkpoints import CheckpointManager
from src.data.cleaning import _materialize_groups
from src.data.io import get_duckdb_connection
from src.features.combat_timing import audit_match_duration, extract_and_aggregate_combat_timing


class TestNB04BoundedCombat(unittest.TestCase):
    def test_team_audit_does_not_filter_or_multiply_events(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            con = get_duckdb_connection(root / "spill", threads=1)
            self.addCleanup(con.close)
            meta, base, death = (root / name for name in ("meta.parquet", "base.parquet", "death.parquet"))
            con.execute("COPY (SELECT 'm' match_id, 600::DOUBLE estimated_match_duration) TO ? (FORMAT PARQUET)", [str(meta)])
            con.execute("COPY (SELECT 'm' match_id, player_name, team_id FROM (VALUES "
                        "('A','t1'),('B','t1'),('C','t2'),('D','t2'),('D','t3'),('E','t2'),('E',NULL)) "
                        "t(player_name,team_id)) TO ? (FORMAT PARQUET)", [str(base)])
            con.execute("COPY (SELECT 'm' match_id, 'A' killer_name, victim_name, 100::DOUBLE AS time "
                        "FROM (VALUES ('B'),('C'),('missing'),('D'),('A'),('E')) t(victim_name)) "
                        "TO ? (FORMAT PARQUET)", [str(death)])
            audit = extract_and_aggregate_combat_timing(con, [death], meta, root / "timing.parquet",
                                                       root / "audit", player_match_base_parquet=base)
            self.assertEqual(audit["team_pair_audit_status"], "available")
            self.assertEqual(audit["same_team_nonself_events"], 1)
            self.assertEqual(audit["different_team_events"], 1)
            self.assertEqual(audit["unknown_team_pair_events"], 3)
            self.assertEqual(audit["total_death_events"], 6)
            self.assertEqual(audit["valid_absolute_events"], 5)  # Only the existing self-kill rule filters.
            self.assertFalse(audit["enemy_kill_eligibility_verified"])

    def test_duration_review_preserves_source_and_does_not_change_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            con = get_duckdb_connection(root / "spill", threads=1)
            self.addCleanup(con.close)
            meta = root / "meta.parquet"
            con.execute("COPY (SELECT match_id, duration::DOUBLE estimated_match_duration FROM "
                        "(VALUES ('null',NULL),('zero',0),('short',30),('normal',600),('huge',63648215000)) "
                        "t(match_id,duration)) TO ? (FORMAT PARQUET)", [str(meta)])
            original = meta.read_bytes()
            summary, cases = audit_match_duration(con, meta, root / "audit")
            self.assertEqual(meta.read_bytes(), original)
            self.assertEqual(con.execute("SELECT sum(match_count) FROM read_csv_auto(?)", [str(summary)]).fetchone()[0], 5)
            self.assertEqual(con.execute("SELECT count(*) FROM read_parquet(?)", [str(cases)]).fetchone()[0], 4)
            self.assertEqual(con.execute("SELECT max(estimated_match_duration) FROM read_parquet(?)",
                                        [str(cases)]).fetchone()[0], 63648215000)
            with self.assertRaises(ValueError):
                audit_match_duration(con, meta, root / "audit", float('nan'))

    def test_bucket_retry_matches_original_windows_including_null_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            con = get_duckdb_connection(root / "spill", threads=1)
            self.addCleanup(con.close)
            con.execute("CREATE TABLE events AS SELECT CASE WHEN i % 5 = 0 THEN NULL ELSE 'm' END AS match_id, "
                        "'killer' AS killer_name, NULL::VARCHAR AS victim_name, (i % 3)::DOUBLE AS time, "
                        "NULL::VARCHAR AS killed_by, CASE WHEN i % 11 = 0 THEN NULL ELSE 'source' END AS source_file, "
                        "(i % 7)::BIGINT AS source_row FROM range(32) t(i)")
            death = root / "death.parquet"
            meta = root / "meta.parquet"
            con.execute("COPY events TO ? (FORMAT PARQUET)", [str(death)])
            con.execute("COPY (SELECT 'm' AS match_id, 600::DOUBLE AS estimated_match_duration) "
                        "TO ? (FORMAT PARQUET)", [str(meta)])
            con.execute("CREATE TABLE expected AS SELECT source_file, source_row, match_id, killer_name, "
                        "victim_name, time, killed_by, CASE WHEN source_file IS NULL THEN 0 "
                        "WHEN count(*) OVER (PARTITION BY source_file, source_row) > 1 THEN 1 ELSE 0 END "
                        "AS flag_duplicate_source_identity, CASE WHEN count(*) OVER (PARTITION BY "
                        "match_id, killer_name, victim_name, time, killed_by) > 1 THEN 1 ELSE 0 END "
                        "AS flag_potential_replay FROM events")
            failed = set()

            class FailFirstCreate:
                def execute(self, sql):
                    if sql.startswith("CREATE OR REPLACE TEMP TABLE"):
                        table = sql.split()[5]
                        if table not in failed:
                            failed.add(table)
                            raise duckdb.OutOfMemoryException("force grouping fallback")
                    return con.execute(sql)

            with patch("src.features.combat_timing._materialize_groups",
                       side_effect=lambda connection, table, query, keys:
                       _materialize_groups(FailFirstCreate(), table, query, keys)):
                extract_and_aggregate_combat_timing(con, [death], meta, root / "timing.parquet", root / "audit")
            self.assertEqual(failed, {"timing_replay_keys", "timing_source_conflicts"})
            actual = ("SELECT source_file, source_row, match_id, killer_name, victim_name, time, killed_by, "
                      "flag_duplicate_source_identity, flag_potential_replay FROM categorized_death_events_view")
            for left, right in ((actual, "SELECT * FROM expected"), ("SELECT * FROM expected", actual)):
                self.assertEqual(con.execute(f"SELECT count(*) FROM (({left}) EXCEPT ALL ({right}))").fetchone()[0], 0)

    def test_low_memory_cross_shard_replay_and_source_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            con = get_duckdb_connection(root / "spill", memory_limit="128MB", threads=1)
            self.addCleanup(con.close)
            # Two shards deliberately repeat content and source identities.
            # NULL victims/causes are equal for the old window partition too.
            con.execute("CREATE TABLE events AS SELECT 'm' AS match_id, 'killer' AS killer_name, "
                        "CASE WHEN i % 7 = 0 THEN NULL ELSE 'victim_' || i END AS victim_name, "
                        "(i % 600)::DOUBLE AS time, NULL::VARCHAR AS killed_by, "
                        "'source_' || (i % 13) AS source_file, i::BIGINT AS source_row "
                        "FROM range(120000) t(i)")
            shards = [root / "a.parquet", root / "b.parquet"]
            for shard in shards:
                con.execute("COPY events TO ? (FORMAT PARQUET, ROW_GROUP_SIZE 50000)", [str(shard)])
            meta = root / "meta.parquet"
            con.execute("COPY (SELECT 'm' AS match_id, 600.0 AS estimated_match_duration) "
                        "TO ? (FORMAT PARQUET)", [str(meta)])
            expected_replay = con.execute("SELECT sum(replayed) FROM (SELECT "
                                          "CASE WHEN count(*) OVER (PARTITION BY match_id, killer_name, "
                                          "victim_name, time, killed_by) > 1 THEN 1 ELSE 0 END replayed "
                                          "FROM events)").fetchone()[0]
            audit = extract_and_aggregate_combat_timing(
                con, shards, meta, root / "timing.parquet", root / "audit")
            self.assertEqual(audit["total_death_events"], 240000)
            self.assertEqual(audit["duplicate_source_identity_events"], 240000)
            # Every event has an identical partner in the other shard.
            self.assertEqual(audit["potential_replayed_event_rows"], 240000)
            self.assertGreater(expected_replay, 0)
            self.assertEqual(audit["valid_absolute_events"], 240000)
            self.assertEqual(audit["valid_phase_events"], 240000)
            self.assertEqual(con.execute("SELECT event_kill_count FROM read_parquet(?)",
                                        [str(root / "timing.parquet")]).fetchone()[0], 240000)
            self.assertEqual(con.execute("SELECT count(*) FROM categorized_death_events_view").fetchone()[0], 240000)
            remaining = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
            self.assertNotIn("timing_replay_keys", remaining)

    def test_notebook_oom_records_resource_limit_and_requires_init(self):
        name = "04_combat_timing.ipynb"
        stage = "notebook/" + name
        notebook = json.loads((Path(__file__).resolve().parents[1] / "notebooks" / name).read_text(encoding="utf-8"))
        source = "".join(next(cell for cell in notebook["cells"]
                              if "audit_summary = extract_and_aggregate_combat_timing(" in "".join(cell["source"]))["source"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = CheckpointManager(root / "checkpoint.json")
            manager.begin_notebook(name, ["01", "03"], signature="sig", writer_id="owner")
            scope = {"PROJECT_ROOT": root, "paths": {"interim": root, "tables": root},
                     "con": Mock(), "death_shards": [], "meta_pq": root / "meta", "base_pq": root / "base",
                     "cfg": {"features": {}}, "_PUBG_CELL_PROGRESS": {name: 5},
                     "_pubg_checkpoint": manager, "_pubg_signature": "sig", "_pubg_writer": "owner",
                     "extract_and_aggregate_combat_timing": Mock(side_effect=duckdb.OutOfMemoryException("fixture OOM"))}
            with self.assertRaises(duckdb.OutOfMemoryException):
                exec(source, scope)
            record = manager.load_manifest()["stages"][stage]
            self.assertEqual(record["status"], "resource_limited")
            self.assertEqual(record["dependencies"], ["notebook/01", "notebook/03"])
            self.assertEqual(scope["_PUBG_CELL_PROGRESS"][name], -1)
            with self.assertRaisesRegex(RuntimeError, "cell"):
                exec(source, scope)


if __name__ == "__main__":
    unittest.main()
