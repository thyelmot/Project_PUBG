"""Full compressed-page validation, not a footer-only acceptance test."""
import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from src.data.io import copy_query_to_parquet, get_duckdb_connection, validate_parquet_file
from src.data.checkpoints import CheckpointManager


class TestNB03ParquetIntegrity(unittest.TestCase):
    def test_notebook_grain_decode_failure_records_failed_and_blocks_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            name = "03_build_player_match.ipynb"
            manager = CheckpointManager(root / "checkpoint.json")
            manager.begin_notebook(name, [], signature="sig", writer_id="owner")
            notebook = json.loads((Path(__file__).resolve().parents[1] / "notebooks" / name).read_text(encoding="utf-8"))
            code = "".join(next(c for c in notebook["cells"] if c.get("id") == "cell-012")["source"])
            scope = {"paths": {}, "PROJECT_ROOT": root,
                     "_PUBG_CELL_PROGRESS": {name: 10},
                     "schema_json": root / "schema.json", "parts_manifest_json": root / "parts.json",
                     "read_json": Mock(return_value={}), "base_pq": root / "base.parquet",
                     "con": Mock(), "_pubg_checkpoint": manager, "_pubg_signature": "sig", "_pubg_writer": "owner"}
            scope["con"].execute.side_effect = duckdb.Error("ZSTD Decompression failure")
            with self.assertRaisesRegex(duckdb.Error, "ZSTD Decompression failure"):
                exec(code, scope)
            record = manager.load_manifest()["stages"]["notebook/" + name]
            self.assertEqual(record["status"], "failed")
            self.assertFalse(record["artifacts"])
            with self.assertRaisesRegex(RuntimeError, "cell"):
                exec(code, scope)

    def test_corrupt_compressed_page_with_readable_footer_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrupt.parquet"
            values = np.random.default_rng(42).integers(0, 2**50, size=10000, dtype=np.int64)
            pq.write_table(pa.table({"value": values}), path, compression="zstd", use_dictionary=False)
            content = bytearray(path.read_bytes())
            frame_start = content.index(b"\x28\xb5\x2f\xfd")
            content[frame_start:frame_start + 4] = b"\xff" * 4
            path.write_bytes(content)
            # Footer count and file existence falsely suggest a usable file.
            with pq.ParquetFile(path) as parquet:
                self.assertEqual(parquet.metadata.num_rows, 10000)
            with self.assertRaisesRegex(ValueError, "Parquet data is unreadable"):
                validate_parquet_file(path)

    def test_actual_duckdb_reader_failure_is_checked_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            con = get_duckdb_connection(root / "temp")
            self.addCleanup(con.close)
            output = root / "base.parquet"
            copy_query_to_parquet(con, "SELECT 1 AS value", output, 1)
            original = output.read_bytes()
            proxy = Mock(wraps=con)

            def execute(query, *args, **kwargs):
                if "bit_xor(hash(COLUMNS(*)))" in query:
                    raise duckdb.Error("ZSTD Decompression failure")
                return con.execute(query, *args, **kwargs)

            proxy.execute.side_effect = execute
            with patch("src.data.io.publish_file") as publish:
                with self.assertRaisesRegex(ValueError, "ZSTD Decompression failure"):
                    copy_query_to_parquet(proxy, "SELECT 2 AS value", output, 1)
                publish.assert_not_called()
            self.assertEqual(output.read_bytes(), original)

    def test_valid_empty_and_multicolumn_outputs_decode_without_schema_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            con = get_duckdb_connection(root / "temp")
            self.addCleanup(con.close)
            output = root / "base.parquet"
            for query, expected in (("SELECT i, 'text' AS name, NULL::DOUBLE AS missing FROM range(50003) t(i)", 50003),
                                    ("SELECT 1 AS value WHERE false", 0)):
                self.assertEqual(copy_query_to_parquet(con, query, output, expected), expected)
                self.assertEqual(validate_parquet_file(output, expected, con=con), expected)


if __name__ == "__main__":
    unittest.main()
