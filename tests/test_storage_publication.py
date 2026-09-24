import errno
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

import duckdb
import pyarrow.parquet as pq

from src.data.io import publish_file, atomic_write_json, check_storage_writable
from src.data.batch_ingest import convert_csv_batches, ingest_sources, staged_paths


class TestStoragePublication(unittest.TestCase):
    def test_missing_upload_rename_falls_back_to_verified_new_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "local", root / "shared" / "result.parquet"
            source.write_bytes(b"closed parquet contents")

            def missing_upload(path, target):
                path.unlink()  # Exact ENOENT case: uploaded source disappears before rename.
                raise FileNotFoundError(errno.ENOENT, "missing upload", str(path))

            with patch.object(Path, "replace", missing_upload), patch("src.data.io.time.sleep"):
                publish_file(source, output)
            self.assertEqual(output.read_bytes(), source.read_bytes())
            self.assertFalse(list(output.parent.glob("*.uploading_*")))

    def test_reported_rename_failure_may_have_already_published(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "local", Path(directory) / "output"
            source.write_bytes(b"new")
            replace = Path.replace

            def late_error(path, target):
                replace(path, target)
                raise FileNotFoundError(errno.ENOENT, "late FUSE reply")

            with patch.object(Path, "replace", late_error), patch("src.data.io.time.sleep") as sleep:
                publish_file(source, output)
            self.assertEqual(output.read_bytes(), b"new")
            sleep.assert_not_called()

    def test_interrupted_direct_copy_does_not_leave_official_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "local", Path(directory) / "output"
            source.write_bytes(b"complete data")

            def interrupted(source_stream, target_stream, **kwargs):
                target_stream.write(b"incomplete")
                raise OSError(errno.ENOSPC, "Drive full")

            with patch.object(Path, "replace", side_effect=FileNotFoundError(errno.ENOENT, "rename")), \
                    patch("src.data.io.time.sleep"), \
                    patch("src.data.io.shutil.copyfile", side_effect=lambda src, dst: Path(dst).write_bytes(Path(src).read_bytes())), \
                    patch("src.data.io.shutil.copyfileobj", side_effect=interrupted):
                with self.assertRaises(OSError) as raised:
                    publish_file(source, output)
            self.assertEqual(raised.exception.errno, errno.ENOSPC)
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), b"complete data")

    def test_corrupted_upload_is_not_committed(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "local", Path(directory) / "output"
            source.write_bytes(b"correct")

            def corrupt(source_path, target_path):
                Path(target_path).write_bytes(b"corrupt")  # Same size, wrong checksum.

            with patch("src.data.io.shutil.copyfile", side_effect=corrupt), \
                    patch("src.data.io.time.sleep"), patch.object(Path, "replace") as replace:
                with self.assertRaisesRegex(OSError, "checksum"):
                    publish_file(source, output)
            replace.assert_not_called()
            self.assertFalse(output.exists())

    def test_existing_checkpoint_preserved_and_manifest_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "checkpoint.json"
            atomic_write_json(output, {"old": True})
            original = output.read_bytes()
            error = FileNotFoundError(errno.ENOENT, "rename unavailable")
            with patch.object(Path, "replace", side_effect=error), patch("src.data.io.time.sleep"):
                with self.assertRaises(FileExistsError):
                    atomic_write_json(output, {"new": True})
            self.assertEqual(output.read_bytes(), original)

            replace = Path.replace
            attempts = []

            def once(path, target):
                attempts.append(path)
                if len(attempts) == 1:
                    raise error
                return replace(path, target)

            with patch.object(Path, "replace", once), patch("src.data.io.time.sleep"):
                atomic_write_json(output, {"new": True})
            self.assertEqual(json.loads(output.read_text()), {"new": True})
            self.assertEqual(len(attempts), 2)

    def test_preflight_rejects_unwritable_checkpoint_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(Path, "replace", side_effect=FileNotFoundError(errno.ENOENT, "rename")), \
                    patch("src.data.io.time.sleep"):
                with self.assertRaisesRegex(OSError, "No CSV conversion started"):
                    check_storage_writable(Path(directory))
            self.assertFalse(list(Path(directory).iterdir()))

    def test_failed_publication_retained_and_resume_rejects_corrupt_local_copy(self):
        schema = {"required_columns": {"match_id": "string"}}
        for corrupt in (False, True, "row_count"):
            with self.subTest(corrupt=corrupt), tempfile.TemporaryDirectory() as directory, duckdb.connect() as con:
                root = Path(directory)
                output, work = root / "drive" / "shard.parquet", root / "temp"
                csv = b"match_id\n001\nNA\n"
                with patch("src.data.batch_ingest.publish_file", side_effect=OSError("Drive unavailable")):
                    with self.assertRaisesRegex(OSError, "Drive unavailable"):
                        convert_csv_batches(con, io.BytesIO(csv), output, schema, 1, work, resume_key="source1")
                partial, = work.glob("*.partial")
                self.assertFalse(output.exists())
                self.assertEqual(pq.ParquetFile(partial).metadata.num_rows, 2)
                if corrupt == "row_count":
                    receipt, = work.glob("*.ready.json")
                    saved = json.loads(receipt.read_text())
                    saved["rows"] = 999
                    receipt.write_text(json.dumps(saved))
                    convert_csv_batches(con, io.BytesIO(csv), output, schema, 1, work, resume_key="source1")
                elif corrupt:
                    partial.write_bytes(b"damaged local copy")
                    convert_csv_batches(con, io.BytesIO(csv), output, schema, 1, work, resume_key="source1")
                else:
                    with patch("src.data.batch_ingest.pd.read_csv", side_effect=AssertionError("must not reconvert")):
                        convert_csv_batches(con, io.BytesIO(csv), output, schema, 1, work, resume_key="source1")
                self.assertEqual(pq.read_table(output).column("match_id").to_pylist(), ["001", "NA"])
                self.assertFalse(list(work.iterdir()))

    def test_ingest_completes_with_parquet_rename_failure_and_blocks_early_gate(self):
        with tempfile.TemporaryDirectory() as directory, duckdb.connect() as con:
            root = Path(directory)
            stage = root / "stage"
            stage.mkdir()
            (stage / "batch_manifest.json").write_text('{"complete": false, "shards": []}')
            notebook = Path(__file__).resolve().parents[1] / "notebooks/01_download_validate.ipynb"
            cells = json.loads(notebook.read_text(encoding="utf-8"))["cells"]
            gate = next("".join(c["source"]) for c in cells
                        if c["cell_type"] == "code" and 'ckpt_mgr.commit("schema"' in "".join(c["source"]))
            manager = Mock()
            with self.assertRaisesRegex(RuntimeError, "01"):
                exec(gate, {"paths": {"checkpoints": root / "checkpoints"}, "PROJECT_ROOT": root, "staging_dir": stage,
                            "_PUBG_CELL_PROGRESS": {"01_download_validate.ipynb": 5},
                            "staged_paths": staged_paths, "ckpt_mgr": manager})
            manager.commit.assert_not_called()

            with zipfile.ZipFile(root / "data.zip", "w") as archive:
                archive.writestr("agg.csv", "match_id\nm1\n")
                archive.writestr("kill.csv", "match_id\nm1\n")
            config = {"source": {"archive_filename": "data.zip"},
                      "discovery": {"agg_patterns": ["agg.csv"], "kill_patterns": ["kill.csv"]}}
            schemas = {kind: {"required_columns": {"match_id": "string"}} for kind in ("aggregate", "deaths")}
            replace = Path.replace

            def parquet_rename_fails(path, target):
                if Path(target).suffix == ".parquet":
                    raise FileNotFoundError(errno.ENOENT, "shortcut rename failed")
                return replace(path, target)

            with patch.object(Path, "replace", parquet_rename_fails), patch("src.data.io.time.sleep"):
                result = ingest_sources(con, root / "raw", stage, config, schemas, work_dir=root / "local")
            self.assertTrue(result["complete"])
            self.assertEqual(len(staged_paths(stage, "aggregate")), 1)
            self.assertEqual(len(staged_paths(stage, "deaths")), 1)


if __name__ == "__main__":
    unittest.main()
