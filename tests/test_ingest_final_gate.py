import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import duckdb
import pandas as pd

from src.data.batch_ingest import (
    ingest_sources, finalize_ingest, verify_staged_record, StagingIntegrityError,
    convert_csv_batches,
)
from src.data.io import publish_file
from src.utils.hashing import hash_file


class TestIngestFinalGate(unittest.TestCase):
    def test_late_manifest_error_reuses_remote_and_cleans_local_recovery(self):
        from src.data.io import atomic_write_json
        with tempfile.TemporaryDirectory() as directory, duckdb.connect() as con:
            root = Path(directory)
            data, schema = self.fixture(root)
            args = (con, root / "raw", root / "stage", data, schema)

            def late_error(path, content, *args, **kwargs):
                atomic_write_json(path, content, *args, **kwargs)
                if Path(path).name == "batch_manifest.json" and len(content.get("shards", [])) == 1:
                    raise OSError("late manifest error")

            with patch("src.data.batch_ingest.atomic_write_json", side_effect=late_error):
                with self.assertRaisesRegex(OSError, "late manifest"):
                    ingest_sources(*args, work_dir=root / "temp")
            self.assertTrue(list((root / "temp").glob("*.partial")))
            with patch("src.data.batch_ingest.convert_csv_batches", wraps=convert_csv_batches) as convert:
                ingest_sources(*args, work_dir=root / "temp")
            self.assertEqual(convert.call_count, 1)
            self.assertFalse(list((root / "temp").glob("*.partial")))

    def test_disappearing_upload_is_republished_without_reconversion(self):
        with tempfile.TemporaryDirectory() as directory, duckdb.connect() as con:
            root = Path(directory)
            data, schema = self.fixture(root)
            removed = []

            def disappears_once(local, target):
                publish_file(local, target)
                if not removed:
                    Path(target).unlink()
                    removed.append(target)

            with patch("src.data.batch_ingest.publish_file", side_effect=disappears_once), \
                    patch("src.data.batch_ingest.time.sleep"), \
                    patch("src.data.batch_ingest.convert_csv_batches", wraps=convert_csv_batches) as convert:
                result = ingest_sources(con, root / "raw", root / "stage", data, schema, work_dir=root / "temp")
            self.assertTrue(result["complete"])
            self.assertEqual(convert.call_count, 2)  # One conversion per input, no extra aggregate pass.
            self.assertFalse(list((root / "temp").glob("*.partial")))

    def test_failed_manifest_commit_keeps_local_copy_for_resume(self):
        from src.data.io import atomic_write_json
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as directory, duckdb.connect() as con:
            root = Path(directory)
            data, schema = self.fixture(root)
            args = (con, root / "raw", root / "stage", data, schema)

            def fail_commit(path, content, *args, **kwargs):
                if Path(path).name == "batch_manifest.json" and len(content.get("shards", [])) == 1:
                    raise OSError("manifest write failed")
                return atomic_write_json(path, content, *args, **kwargs)

            with patch("src.data.batch_ingest.atomic_write_json", side_effect=fail_commit):
                with self.assertRaisesRegex(OSError, "manifest write failed"):
                    ingest_sources(*args, work_dir=root / "temp")
            self.assertEqual(len(list((root / "temp").glob("*.partial"))), 1)
            with patch("src.data.batch_ingest.pq.ParquetWriter", wraps=pq.ParquetWriter) as writer:
                result = ingest_sources(*args, work_dir=root / "temp")
            self.assertTrue(result["complete"])
            self.assertEqual(writer.call_count, 1)  # Only deaths need conversion.

    def test_renamed_source_alias_must_not_be_unlinked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local, target = root / "local", root / "output"
            local.write_bytes(b"verified contents")
            original_replace, original_unlink = Path.replace, Path.unlink
            aliases = {}

            def rename(path, destination):
                result = original_replace(path, destination)
                aliases[path] = Path(destination)
                return result

            def stale_unlink(path, *args, **kwargs):
                return original_unlink(aliases.get(path, path), *args, **kwargs)

            with patch.object(Path, "replace", rename), patch.object(Path, "unlink", stale_unlink):
                publish_file(local, target)
            self.assertEqual(target.read_bytes(), b"verified contents")

    def fixture(self, root):
        with zipfile.ZipFile(root / "data.zip", "w") as archive:
            archive.writestr("agg.csv", "match_id\nm1\nm2\n")
            archive.writestr("kill.csv", "match_id\nm1\n")
        data = {"source": {"archive_filename": "data.zip"},
                "discovery": {"agg_patterns": ["agg.csv"], "kill_patterns": ["kill.csv"]}}
        schema = {kind: {"required_columns": {"match_id": "string"}} for kind in ("aggregate", "deaths")}
        return data, schema

    def test_final_gate_repairs_only_missing_or_changed_shard(self):
        for failure in ("missing", "changed"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory, duckdb.connect() as con:
                root = Path(directory)
                data, schema = self.fixture(root)
                args = (con, root / "raw", root / "stage", data, schema)
                result = ingest_sources(*args, work_dir=root / "temp")
                record = next(s for s in result["shards"] if s["kind"] == "aggregate")
                target = root / "stage" / record["file"]
                if failure == "missing":
                    target.unlink()
                else:
                    pd.DataFrame({"match_id": ["wrong", "data"]}).to_parquet(target)
                with patch("src.data.batch_ingest.time.sleep"), \
                        patch("src.data.batch_ingest.convert_csv_batches", wraps=convert_csv_batches) as convert:
                    repaired = finalize_ingest(*args, work_dir=root / "temp")
                self.assertEqual(convert.call_count, 1)
                self.assertTrue(repaired["complete"])
                self.assertEqual(pd.read_parquet(target)["match_id"].tolist(), ["m1", "m2"])

    def test_transient_checksum_read_is_retried_without_rewriting_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "data.parquet"
            pd.DataFrame({"id": [1]}).to_parquet(target)
            record = {"rows": 1, "sha256": hash_file(target)}
            with patch("src.data.batch_ingest.hash_file", side_effect=["0" * 64, record["sha256"]]) as hashed, \
                    patch("src.data.batch_ingest.time.sleep"):
                verify_staged_record(target, record)
            self.assertEqual(hashed.call_count, 2)

    def test_changed_destination_cannot_become_the_expected_checksum(self):
        with tempfile.TemporaryDirectory() as directory, duckdb.connect() as con:
            root = Path(directory)
            data, schema = self.fixture(root)

            def changed_after_publish(local, target):
                publish_file(local, target)
                Path(target).write_bytes(b"changed after verified upload")

            with patch("src.data.batch_ingest.publish_file", side_effect=changed_after_publish), \
                    patch("src.data.batch_ingest.time.sleep"):
                with self.assertRaises(StagingIntegrityError):
                    ingest_sources(con, root / "raw", root / "stage", data, schema, work_dir=root / "temp")
            manifest = json.loads((root / "stage/batch_manifest.json").read_text())
            self.assertFalse(manifest["complete"])
            self.assertFalse(manifest["shards"])

    def test_persistent_fault_stops_after_one_repair_pass(self):
        with tempfile.TemporaryDirectory() as directory, duckdb.connect() as con:
            root = Path(directory)
            data, schema = self.fixture(root)
            args = (con, root / "raw", root / "stage", data, schema)
            result = ingest_sources(*args, work_dir=root / "temp")
            target = root / "stage" / result["shards"][0]["file"]
            target.unlink()
            with patch("src.data.batch_ingest.time.sleep"), \
                    patch("src.data.batch_ingest.ingest_sources", side_effect=OSError("Drive unavailable")) as repair:
                with self.assertRaisesRegex(OSError, "Drive unavailable"):
                    finalize_ingest(*args, work_dir=root / "temp")
            self.assertEqual(repair.call_count, 1)


if __name__ == "__main__":
    unittest.main()
