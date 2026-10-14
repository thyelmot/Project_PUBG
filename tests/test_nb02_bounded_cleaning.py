"""NB02 operational regressions; synthetic data only, no research sampling."""
import tempfile
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

import duckdb
import pandas as pd

from src.data.cleaning import BUSINESS_COLUMNS, audit_and_clean_aggregate_data
from src.data.io import get_duckdb_connection
from src.analysis.eda import count_parquet_player_timestamp_overlaps, run_chronology_audit


class TestBoundedCleaning(unittest.TestCase):
    def test_streamed_chronology_matches_pandas_across_batches_and_timezones(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            con = get_duckdb_connection(root / "spill", memory_limit="64MB", threads=1)
            self.addCleanup(con.close)
            players = pd.DataFrame({
                "player_name": ["Alice", "Alice", "Alice", "Bob", "Bob", None, "Carol", "Carol"],
                "match_id": ["m1", "m1", "m2", "m3", "m4", "m5", None, "m6"],
                "date": [
                    "2017-11-20T10:00:00Z", "2017-11-20T10:00:00+0000",
                    "2017-11-20T11:00:00+01:00",
                    "2017-11-20T10:00:00.000000100Z", "2017-11-20T10:00:00.000000200Z",
                    "2017-11-20", "2017-11-20", "bad-date",
                ],
            })
            path = root / "players.parquet"
            players.to_parquet(path, index=False)
            meta = pd.DataFrame({"match_date": ["2017-11-20", "2017-11-21", "2017-11-22"]})
            for batch_size in (1, 2, 5, 50000):
                overlap = count_parquet_player_timestamp_overlaps(con, path, batch_size)
                self.assertEqual(overlap, 1)
                for exact in (False, True):
                    for grade in (None, "Grade A", "Grade B", "Grade C"):
                        expected = run_chronology_audit(meta, exact, grade, player_match_df=players)
                        actual = run_chronology_audit(meta, exact, grade, player_timestamp_overlap_count=overlap)
                        self.assertEqual(actual, expected)
            self.assertEqual(con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name LIKE '_chronology_%'").fetchone()[0], 0)
            with self.assertRaises(ValueError):
                count_parquet_player_timestamp_overlaps(con, path, 0)
            with patch("src.data.cleaning._materialize_groups", side_effect=duckdb.OutOfMemoryException("synthetic overlap OOM")):
                with self.assertRaises(duckdb.OutOfMemoryException):
                    count_parquet_player_timestamp_overlaps(con, path, 2)
            self.assertEqual(con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name LIKE '_chronology_%'").fetchone()[0], 0)

    def test_chronology_prefers_match_date_and_handles_empty_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            con = get_duckdb_connection(root / "spill")
            self.addCleanup(con.close)
            players = pd.DataFrame({"match_id": ["m1", "m2"], "player_name": ["A", "A"],
                                    "date": ["2017-11-20", "2017-11-20"], "match_date": [None, None]})
            path = root / "players.parquet"
            players.to_parquet(path, index=False)
            self.assertEqual(count_parquet_player_timestamp_overlaps(con, path, 1), 0)
            players.iloc[:0].to_parquet(path, index=False)
            self.assertEqual(count_parquet_player_timestamp_overlaps(con, path, 1), 0)

    def test_cross_shard_representative_matches_original_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            con = get_duckdb_connection(root / "spill", memory_limit="64MB", threads=1)
            self.addCleanup(con.close)
            base = dict(zip(BUSINESS_COLUMNS, [
                "m", "Alice", "t", "2017-11-20", "tpp", 1, 2,
                0, 0, None, 100.0, 50.0, 0, 300.0, 1,
            ]))
            rows = [dict(base, source_file=file, source_row=row, extra=extra)
                    for file, row, extra in [
                        ("b.csv", 1, "b"), ("a.csv", 99, "a"),
                        ("a.csv", None, "null_row"), (None, 0, "null_file"),
                    ]]
            paths = [root / "a.parquet", root / "b.parquet"]
            pd.DataFrame(rows[:2]).to_parquet(paths[0], index=False)
            pd.DataFrame(rows[2:]).to_parquet(paths[1], index=False)
            summary = audit_and_clean_aggregate_data(
                con, paths, root / "clean.parquet", root / "removal.csv",
            )
            business = ", ".join(f'"{column}"' for column in BUSINESS_COLUMNS)
            expected = con.execute(f"""
                SELECT source_file, source_row, extra FROM raw_aggregate_view
                QUALIFY row_number() OVER (
                    PARTITION BY {business} ORDER BY source_file, source_row
                ) = 1
            """).fetchall()
            actual = con.execute("SELECT source_file, source_row, extra FROM step1_dedup").fetchall()
            self.assertEqual(actual, expected)
            self.assertEqual(actual, [("a.csv", 99.0, "a")])
            self.assertEqual(summary["exact_duplicates"], 3)
            self.assertEqual(summary["clean_rows"], 1)
            # Rerun on the same connection/output must replace, not append.
            proxy = Mock(wraps=con)
            failures = set()

            def execute(query, *args, **kwargs):
                # Force both global grouping and a partial-bucket retry. This
                # checks correctness without relying on a particular DuckDB OOM.
                if query.startswith("CREATE OR REPLACE TEMP TABLE") and "WHERE TRUE" in query:
                    marker = "global"
                elif query.startswith("INSERT INTO _pubg_dedup_rows") and "% 32 = 2" in query:
                    marker = "partial"
                else:
                    marker = None
                if marker and marker not in failures:
                    failures.add(marker)
                    raise duckdb.OutOfMemoryException("synthetic grouping exhaustion")
                return con.execute(query, *args, **kwargs)

            proxy.execute.side_effect = execute
            repeated = audit_and_clean_aggregate_data(
                proxy, list(reversed(paths)), root / "clean.parquet", root / "removal.csv",
            )
            self.assertEqual(repeated, summary)
            self.assertEqual(failures, {"global", "partial"})

    def test_wide_synthetic_shard_under_bounded_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            con = get_duckdb_connection(root / "spill", memory_limit="64MB", threads=1)
            self.addCleanup(con.close)
            shard = root / "wide.parquet"
            safe_path = shard.as_posix().replace("'", "''")
            # Fixture construction is not the operation under test.
            con.execute("SET memory_limit = '256MB'")
            con.execute(f"""
                COPY (SELECT
                    'm' || i::VARCHAR || repeat('x', 256) AS match_id,
                    'p' || i::VARCHAR || repeat('y', 256) AS player_name,
                    't' AS team_id, '2017-11-20' AS date, 'tpp' AS match_mode,
                    1 AS party_size, 2 AS game_size, 0 AS player_assists,
                    0 AS player_dbno, 0.0 AS player_dist_ride,
                    100.0 AS player_dist_walk, 50.0 AS player_dmg,
                    0 AS player_kills, 300.0 AS player_survive_time,
                    1 AS team_placement, 'a.csv' AS source_file, i AS source_row
                    FROM range(300000) t(i)
                ) TO '{safe_path}' (FORMAT PARQUET, ROW_GROUP_SIZE 50000)
            """)
            con.execute("SET memory_limit = '128MB'")
            summary = audit_and_clean_aggregate_data(
                con, [shard], root / "clean.parquet", root / "removal.csv",
            )
            self.assertEqual(summary["total_raw_rows"], 300000)
            self.assertEqual(summary["clean_rows"], 300000)
            self.assertEqual(summary["dropped_rows"], 0)


if __name__ == "__main__":
    unittest.main()
