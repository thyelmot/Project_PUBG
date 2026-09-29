"""Tests for Phase VI (Giai đoạn 3: Notebook 01, Ingest và Schema) per PUBG_IMPLEMENTATION_PLAN.md Section 19."""

import json
import shutil
import tempfile
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pyarrow.parquet as pq

from src.data.batch_ingest import convert_csv_batches, ingest_sources, finalize_ingest
from src.data.inventory import inventory_sources, update_inventory_with_staged_counts
from src.data.io import get_duckdb_connection, read_json
from src.data.schema import validate_shard_schema, generate_schema_report
from src.utils.config import load_config, resolve_paths


class TestW02Inventory(unittest.TestCase):
    """Checklist item 1 & 2: Inventory mọi shard, byte, rows, checksum, nguồn; download date/version không suy đoán."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.raw_dir = Path(self.tmpdir.name) / "raw"
        self.raw_dir.mkdir(parents=True)
        self.con = get_duckdb_connection()

        # Create mock aggregate and death shards
        agg_sub = self.raw_dir / "aggregate"
        agg_sub.mkdir()
        self.agg_csv1 = agg_sub / "agg_match_stats_0.csv"
        pd.DataFrame({
            "date": ["2017-11-20T10:00:00+0000", "2017-11-20T10:01:00+0000"],
            "game_size": [100, 100], "match_id": ["m1", "m1"],
            "match_mode": ["tpp", "tpp"], "party_size": [4, 4],
            "player_assists": [0, 1], "player_dbno": [0, 0],
            "player_dist_ride": [0.0, 50.0], "player_dist_walk": [100.0, 200.0],
            "player_dmg": [50.0, 150.0], "player_kills": [0, 2],
            "player_name": ["Alice", "Bob"], "player_survive_time": [300.0, 600.0],
            "team_id": ["t1", "t1"], "team_placement": [10, 10],
        }).to_csv(self.agg_csv1, index=False)

        kill_sub = self.raw_dir / "deaths"
        kill_sub.mkdir()
        self.kill_csv1 = kill_sub / "kill_match_stats_final_0.csv"
        pd.DataFrame({
            "match_id": ["m1"], "time": [250.0], "killer_name": ["Bob"],
            "victim_name": ["Charlie"], "killed_by": ["AKM"],
        }).to_csv(self.kill_csv1, index=False)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_inventory_sources_discovers_shards_and_hashes(self):
        inv = inventory_sources(
            raw_root=self.raw_dir,
            agg_patterns=["**/agg_match_stats*.csv"],
            kill_patterns=["**/kill_match_stats*.csv"],
            con=self.con,
            compute_hash=True,
        )
        self.assertEqual(inv["total_files"], 2)
        self.assertEqual(len(inv["aggregate_shards"]), 1)
        self.assertEqual(len(inv["death_shards"]), 1)
        self.assertEqual(inv["aggregate_shards"][0]["row_count"], 2)
        self.assertEqual(inv["death_shards"][0]["row_count"], 1)
        self.assertIsNotNone(inv["aggregate_shards"][0]["sha256"])
        self.assertEqual(len(inv["aggregate_shards"][0]["sha256"]), 64)
        self.assertGreater(inv["total_bytes"], 0)

    def test_source_info_unspeculated_version_and_date(self):
        inv = inventory_sources(
            raw_root=self.raw_dir,
            agg_patterns=["**/agg_match_stats*.csv"],
            kill_patterns=["**/kill_match_stats*.csv"],
            con=self.con,
            compute_hash=False,
        )
        s_info = inv["source_info"]
        self.assertIsNone(s_info["download_date"])
        self.assertIsNone(s_info["version"])

    def test_update_inventory_with_staged_counts(self):
        inv = {
            "aggregate_shards": [{"filename": "agg_0.csv", "relative_path": "aggregate/agg_0.csv", "row_count": -1}],
            "death_shards": [{"filename": "kill_0.csv", "relative_path": "deaths/kill_0.csv", "row_count": -1}],
            "total_aggregate_rows": 0,
            "total_death_rows": 0,
        }
        manifest = {
            "shards": [
                {"source": "aggregate/agg_0.csv", "rows": 100},
                {"source": "deaths/kill_0.csv", "rows": 50},
            ]
        }
        updated = update_inventory_with_staged_counts(inv, manifest)
        self.assertEqual(updated["aggregate_shards"][0]["row_count"], 100)
        self.assertEqual(updated["aggregate_shards"][0]["status"], "valid")
        self.assertEqual(updated["death_shards"][0]["row_count"], 50)
        self.assertEqual(updated["total_aggregate_rows"], 100)
        self.assertEqual(updated["total_death_rows"], 50)


class TestW02SchemaValidation(unittest.TestCase):
    """Checklist item 3: Kiểm tra required/optional columns, alias có kiểm soát và đơn vị cần xác minh."""

    def setUp(self):
        self.required_agg = {
            "match_id": "string", "player_name": "string", "player_kills": "int64",
            "player_survive_time": "float64", "team_placement": "int64",
        }
        self.aliases = {
            "player_name": ["playerName", "player_name"],
            "match_id": ["matchId", "match_id"],
        }
        self.units = {
            "player_survive_time": "seconds",
            "player_dist_walk": "meters",
        }

    def test_validate_shard_schema_exact_match(self):
        cols = ["match_id", "player_name", "player_kills", "player_survive_time", "team_placement"]
        res = validate_shard_schema(cols, self.required_agg, self.aliases, units=self.units)
        self.assertTrue(res["is_valid"])
        self.assertEqual(len(res["missing_columns"]), 0)
        self.assertIn("player_survive_time", res["units_verified"])

    def test_validate_shard_schema_controlled_aliases(self):
        cols = ["matchId", "playerName", "player_kills", "player_survive_time", "team_placement"]
        res = validate_shard_schema(cols, self.required_agg, self.aliases)
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["column_mapping"]["matchId"], "match_id")
        self.assertEqual(res["column_mapping"]["playerName"], "player_name")

    def test_validate_shard_schema_missing_required_column(self):
        cols = ["match_id", "player_kills"]  # missing player_name, survive_time, team_placement
        res = validate_shard_schema(cols, self.required_agg, self.aliases)
        self.assertFalse(res["is_valid"])
        self.assertIn("player_name", res["missing_columns"])
        self.assertIn("player_survive_time", res["missing_columns"])

    def test_generate_schema_report_summarizes_contracts(self):
        schema_cfg = {
            "version": "3.0",
            "aggregate": {
                "required_columns": self.required_agg,
                "optional_columns": {},
                "aliases": self.aliases,
                "units": self.units,
            },
            "deaths": {"required_columns": {"match_id": "string"}, "optional_columns": {}, "aliases": {}, "units": {}},
        }
        validations = {
            "agg_0": {"is_valid": True, "kind": "aggregate", "missing_columns": [], "column_mapping": {}},
            "agg_1": {"is_valid": False, "kind": "aggregate", "missing_columns": ["player_name"], "column_mapping": {}},
        }
        rep = generate_schema_report(schema_cfg, validations)
        self.assertFalse(rep["all_shards_valid"])
        self.assertEqual(rep["summary"]["valid_shards"], 1)
        self.assertEqual(rep["summary"]["invalid_shards"], 1)


class TestW02BatchIngestReconciliation(unittest.TestCase):
    """Checklist items 4, 5, 6: Tách missing gốc và lỗi parse, kiểm tra count nguyên, đối soát rows."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.tmpdir.name)
        self.con = get_duckdb_connection()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_original_missing_and_parse_errors_separated(self):
        """Empty string is original_missing; invalid text in numeric column is parse_error."""
        csv_file = self.work_dir / "test_shard.csv"
        df = pd.DataFrame({
            "match_id": ["m1", "m2", "m3", "m4"],
            "player_name": ["Alice", "Bob", "", "David"],
            "player_kills": ["2", "invalid_num", "", "5"],
            "player_survive_time": ["100.5", "200.0", "bad_float", ""],
        })
        df.to_csv(csv_file, index=False)

        schema = {
            "required_columns": {
                "match_id": "string",
                "player_name": "string",
                "player_kills": "int64",
                "player_survive_time": "float64",
            },
            "aliases": {},
        }

        output_pq = self.work_dir / "out.parquet"
        result_meta = {}
        with open(csv_file, "rb") as stream:
            rows = convert_csv_batches(
                self.con, stream, output_pq, schema, batch_rows=2,
                work_dir=self.work_dir, resume_key="sig_test", result_metadata=result_meta
            )

        self.assertEqual(rows, 4)
        audit = result_meta["parse_audit"]

        # Check player_kills: 2 valid, 1 original_missing, 1 parse_error
        self.assertEqual(audit["player_kills"]["valid"], 2)
        self.assertEqual(audit["player_kills"]["original_missing"], 1)
        self.assertEqual(audit["player_kills"]["parse_errors"], 1)
        self.assertIn("invalid_num", audit["player_kills"]["sample_parse_errors"])

        # Check player_survive_time: 2 valid, 1 original_missing, 1 parse_error
        self.assertEqual(audit["player_survive_time"]["valid"], 2)
        self.assertEqual(audit["player_survive_time"]["original_missing"], 1)
        self.assertEqual(audit["player_survive_time"]["parse_errors"], 1)

    def test_count_must_be_strictly_integer(self):
        """Float count (e.g., 3.5 kills) must be flagged as parse_error to prevent silent rounding."""
        csv_file = self.work_dir / "float_kills.csv"
        df = pd.DataFrame({
            "match_id": ["m1", "m2"],
            "player_name": ["Alice", "Bob"],
            "player_kills": ["2", "3.5"],
            "player_survive_time": ["100.0", "200.0"],
        })
        df.to_csv(csv_file, index=False)

        schema = {
            "required_columns": {
                "match_id": "string", "player_name": "string",
                "player_kills": "int64", "player_survive_time": "float64",
            },
            "aliases": {},
        }

        output_pq = self.work_dir / "out_int_check.parquet"
        result_meta = {}
        with open(csv_file, "rb") as stream:
            convert_csv_batches(
                self.con, stream, output_pq, schema, batch_rows=10,
                work_dir=self.work_dir, resume_key="sig_int", result_metadata=result_meta
            )

        audit = result_meta["parse_audit"]
        self.assertEqual(audit["player_kills"]["parse_errors"], 1)
        self.assertEqual(audit["player_kills"]["valid"], 1)

    def test_sensitive_player_columns_masked_in_sample_errors(self):
        """Player names, killer names, victim names must never appear in sample_parse_errors."""
        csv_file = self.work_dir / "sensitive.csv"
        df = pd.DataFrame({
            "match_id": ["m1"],
            "player_name": ["SecretPlayer123"],
            "player_kills": ["bad_val"],
            "player_survive_time": ["100.0"],
        })
        df.to_csv(csv_file, index=False)

        schema = {
            "required_columns": {
                "match_id": "string", "player_name": "string",
                "player_kills": "int64", "player_survive_time": "float64",
            },
            "aliases": {},
        }
        output_pq = self.work_dir / "out_sens.parquet"
        result_meta = {}
        with open(csv_file, "rb") as stream:
            convert_csv_batches(
                self.con, stream, output_pq, schema, batch_rows=10,
                work_dir=self.work_dir, resume_key="sig_sens", result_metadata=result_meta
            )
        audit = result_meta["parse_audit"]
        self.assertEqual(len(audit["player_name"]["sample_parse_errors"]), 0)


if __name__ == "__main__":
    unittest.main()
