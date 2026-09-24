import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import duckdb
import pyarrow.parquet as pq

from src.data.batch_ingest import convert_csv_batches, ingest_sources, staged_paths


class TestBatchIngest(unittest.TestCase):
    def test_zip_batches_resume_integrity_and_no_extraction(self):
        schema = {"required_columns": {"match_id": "string", "value": "float64"},
                  "aliases": {"match_id": ["matchId"]}}
        data = {"source": {"archive_filename": "fixture.zip"}, "discovery": {
            "agg_patterns": ["**/agg_match_stats*.csv"],
            "kill_patterns": ["**/kill_match_stats*.csv"]}}
        with tempfile.TemporaryDirectory() as directory, duckdb.connect() as con:
            root = Path(directory)
            raw, staging = root / "raw", root / "staging"
            archive = root / "fixture.zip"
            with zipfile.ZipFile(archive, "w") as z:
                # Same basename in different directories must not overwrite each other.
                z.writestr("a/agg_match_stats.csv", "matchId,value\n001,1\nNA,2\n001,bad\n")
                z.writestr("b/agg_match_stats.csv", 'matchId,value\n"multi\nline",4\n')
                z.writestr("kill_match_stats.csv", "matchId,value\n001,5\n")
            schemas = {"aggregate": schema, "deaths": schema}
            actual = convert_csv_batches
            calls = []

            def interrupted(*args, **kwargs):
                calls.append(args[2])
                if len(calls) == 2:
                    raise RuntimeError("simulated interruption")
                return actual(*args, **kwargs)

            with patch("src.data.batch_ingest.convert_csv_batches", side_effect=interrupted):
                with self.assertRaisesRegex(RuntimeError, "simulated"):
                    ingest_sources(con, raw, staging, data, schemas, batch_rows=2)
            with self.assertRaisesRegex(RuntimeError, "01"):
                staged_paths(staging, "aggregate")
            saved = calls[0]
            timestamp = saved.stat().st_mtime_ns
            with patch("src.data.batch_ingest.convert_csv_batches", wraps=actual) as convert:
                result = ingest_sources(con, raw, staging, data, schemas, batch_rows=2)
                self.assertEqual(convert.call_count, 2)
            self.assertEqual(saved.stat().st_mtime_ns, timestamp)
            self.assertTrue(result["complete"])
            self.assertEqual(sum(s["rows"] for s in result["shards"]), 5)
            self.assertEqual(len(staged_paths(staging, "aggregate")), 2)
            self.assertFalse(list(raw.rglob("*.csv")))
            table = pq.read_table(saved)
            self.assertEqual(table.column("match_id").to_pylist(), ["001", "NA", "001"])
            self.assertEqual(table.column("value").to_pylist(), [1., 2., None])
            metadata = pq.ParquetFile(saved).metadata
            self.assertEqual(metadata.num_row_groups, 2)
            self.assertEqual(metadata.row_group(0).column(0).compression, "ZSTD")
            # Corrupt output is rebuilt, while unrelated stale files are ignored.
            saved.write_bytes(b"broken")
            (staging / "agg_stale.parquet").write_bytes(b"old")
            with patch("src.data.batch_ingest.convert_csv_batches", wraps=actual) as convert:
                ingest_sources(con, raw, staging, data, schemas, batch_rows=1)
                self.assertEqual(convert.call_count, 1)
            self.assertEqual(len(staged_paths(staging, "aggregate")), 2)
            with patch("src.data.batch_ingest.convert_csv_batches", side_effect=AssertionError("must reuse")):
                ingest_sources(con, raw, staging, data, schemas, batch_rows=10)
            # Reject traversal even though archive members are never extracted.
            with zipfile.ZipFile(archive, "a") as z:
                z.writestr("../escape.csv", "bad")
            with self.assertRaisesRegex(ValueError, "Unsafe ZIP"):
                ingest_sources(con, raw, staging, data, schemas)

    def test_failed_conversion_preserves_previous_output(self):
        schema = {"required_columns": {"match_id": "string", "value": "float64"}}
        with tempfile.TemporaryDirectory() as directory, duckdb.connect() as con:
            output = Path(directory) / "data.parquet"
            convert_csv_batches(con, io.BytesIO(b"match_id,value\na,1\n"), output, schema, 1)
            original = output.read_bytes()
            for contents in [b"wrong,value\na,1\n", b'match_id,value\na,1\n"broken,2\n']:
                with self.assertRaises(Exception):
                    convert_csv_batches(con, io.BytesIO(contents), output, schema, 1)
                self.assertEqual(output.read_bytes(), original)
                self.assertFalse(output.with_suffix(".parquet.partial").exists())
            with self.assertRaises(ValueError):
                convert_csv_batches(con, io.BytesIO(b""), output, schema, 0)


if __name__ == "__main__":
    unittest.main()
