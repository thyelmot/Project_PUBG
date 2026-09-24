import shutil
import sys
import unittest
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.io import get_duckdb_connection, atomic_write_parquet
from src.data.inventory import inventory_sources
from src.data.schema import convert_shard_to_parquet, validate_shard_schema
from src.data.cleaning import audit_and_clean_aggregate_data
from src.data.match_metadata import build_match_metadata
from src.models.splits import create_split_assignments
from src.features.combat_timing import extract_and_aggregate_combat_timing, merge_player_match_and_timing
from src.data.checkpoints import CheckpointManager


class TestDataAndFeaturesPipeline(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(__file__).resolve().parent / ".tmp_test_pipeline"
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.con = get_duckdb_connection(temp_dir=self.test_dir / "duckdb_temp")

        # Create Synthetic Raw Data
        self.raw_agg_csv = self.test_dir / "raw_agg_0.csv"
        self.raw_kill_csv = self.test_dir / "raw_kill_0.csv"

        # 2 matches: m1 (duration 600s, 2 teams), m2 (duration 900s, 3 teams)
        agg_data = [
            # match_id, player_name, team_id, date, match_mode, party_size, game_size, assists, dbno, ride, walk, dmg, kills, survive, placement
            ["m1", "Alice", "t1", "2017-11-20T10:00:00+0000", "tpp", 2, 4, 1, 1, 100.0, 500.0, 300.0, 2, 600.0, 1],
            ["m1", "Bob", "t1", "2017-11-20T10:00:00+0000", "tpp", 2, 4, 0, 0, 0.0, 0.0, 0.0, 0, 500.0, 1], # 0 kills, 0 dist
            ["m1", "Charlie", "t2", "2017-11-20T10:00:00+0000", "tpp", 2, 4, 0, 0, 0.0, 200.0, 50.0, 0, 300.0, 2],
            ["m1", "David", "t2", "2017-11-20T10:00:00+0000", "tpp", 2, 4, 0, 0, 0.0, 100.0, 0.0, 0, 150.0, 2],
            # Duplicate row to test deduplication
            ["m1", "David", "t2", "2017-11-20T10:00:00+0000", "tpp", 2, 4, 0, 0, 0.0, 100.0, 0.0, 0, 150.0, 2],
            # Match 2
            ["m2", "Eve", "t3", "2017-11-21T12:00:00+0000", "tpp", 1, 3, 0, 0, 500.0, 1000.0, 450.0, 3, 900.0, 1],
            ["m2", "Frank", "t4", "2017-11-21T12:00:00+0000", "tpp", 1, 3, 0, 0, 0.0, 300.0, 100.0, 1, 500.0, 2],
            ["m2", "Grace", "t5", "2017-11-21T12:00:00+0000", "tpp", 1, 3, 0, 0, 0.0, 100.0, 0.0, 0, 200.0, 3],
        ]
        agg_cols = [
            "match_id", "player_name", "team_id", "date", "match_mode", "party_size", "game_size",
            "player_assists", "player_dbno", "player_dist_ride", "player_dist_walk",
            "player_dmg", "player_kills", "player_survive_time", "team_placement"
        ]
        pd.DataFrame(agg_data, columns=agg_cols).to_csv(self.raw_agg_csv, index=False)

        # Deaths: Alice kills David at 100s (early in 600s), Charlie at 350s (mid in 600s)
        # Self-kill: Frank kills Frank at 500s (should be filtered out!)
        # Eve kills Grace at 800s (late in 900s)
        kill_data = [
            ["m1", 100.0, "Alice", "David", "M416"],
            ["m1", 350.0, "Alice", "Charlie", "AKM"],
            ["m2", 500.0, "Frank", "Frank", "Grenade"], # suicide
            ["m2", 800.0, "Eve", "Grace", "Kar98k"],
        ]
        kill_cols = ["match_id", "time", "killer_name", "victim_name", "killed_by"]
        pd.DataFrame(kill_data, columns=kill_cols).to_csv(self.raw_kill_csv, index=False)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_full_m1_m2_pipeline(self):
        # 1. Schema conversion to Parquet
        agg_pq = self.test_dir / "agg_0.parquet"
        kill_pq = self.test_dir / "kill_0.parquet"

        agg_schema = {
            "date": "VARCHAR",
            "game_size": "BIGINT",
            "match_id": "VARCHAR",
            "match_mode": "VARCHAR",
            "party_size": "BIGINT",
            "player_assists": "BIGINT",
            "player_dbno": "BIGINT",
            "player_dist_ride": "DOUBLE",
            "player_dist_walk": "DOUBLE",
            "player_dmg": "DOUBLE",
            "player_kills": "BIGINT",
            "player_name": "VARCHAR",
            "player_survive_time": "DOUBLE",
            "team_id": "VARCHAR",
            "team_placement": "BIGINT",
        }
        agg_map = {c: c for c in agg_schema}
        convert_shard_to_parquet(self.con, self.raw_agg_csv, agg_pq, agg_schema, agg_map)

        kill_schema = {"match_id": "VARCHAR", "time": "DOUBLE", "killer_name": "VARCHAR", "victim_name": "VARCHAR", "killed_by": "VARCHAR"}
        kill_map = {c: c for c in kill_schema}
        convert_shard_to_parquet(self.con, self.raw_kill_csv, kill_pq, kill_schema, kill_map)

        # 2. Cleaning & Deduplication
        cleaned_pq = self.test_dir / "cleaned_agg.parquet"
        removal_csv = self.test_dir / "removal.csv"
        clean_res = audit_and_clean_aggregate_data(self.con, [agg_pq], cleaned_pq, removal_csv)
        self.assertEqual(clean_res["exact_duplicates"], 1)
        self.assertEqual(clean_res["clean_rows"], 7)

        # 3. Match Metadata
        meta_pq = self.test_dir / "match_metadata.parquet"
        build_match_metadata(self.con, cleaned_pq, meta_pq)
        meta_df = pd.read_parquet(meta_pq)
        self.assertEqual(len(meta_df), 2)
        m1_meta = meta_df[meta_df["match_id"] == "m1"].iloc[0]
        self.assertEqual(m1_meta["observed_team_count"], 2)
        self.assertEqual(m1_meta["estimated_match_duration"], 600.0)
        # Splitting matches into multiple buckets must preserve exact statistics.
        from unittest.mock import patch
        with patch("src.data.match_metadata.math.ceil", return_value=3):
            build_match_metadata(self.con, cleaned_pq, meta_pq)
        pd.testing.assert_frame_equal(
            meta_df.sort_values("match_id").reset_index(drop=True),
            pd.read_parquet(meta_pq).sort_values("match_id").reset_index(drop=True),
        )

        # 4. Split Assignments
        split_pq = self.test_dir / "splits.parquet"
        split_json = self.test_dir / "split_manifest.json"
        create_split_assignments(self.con, meta_pq, split_pq, split_json, train_ratio=0.5, val_ratio=0.5, test_ratio=0.0)
        split_df = pd.read_parquet(split_pq)
        self.assertEqual(len(split_df), 2)
        # Check match isolation: m1 and m2 are in separate splits
        self.assertNotEqual(split_df[split_df["match_id"] == "m1"]["split"].iloc[0],
                            split_df[split_df["match_id"] == "m2"]["split"].iloc[0])

        # 5. Combat Timing
        timing_pq = self.test_dir / "combat_timing.parquet"
        audit_dir = self.test_dir / "audit"
        timing_audit = extract_and_aggregate_combat_timing(self.con, [kill_pq], meta_pq, timing_pq, audit_dir)
        # Suicide was excluded: Frank kills Frank -> excluded
        self.assertEqual(timing_audit["valid_enemy_kills"], 3)
        timing_df = pd.read_parquet(timing_pq)
        alice_timing = timing_df[(timing_df["match_id"] == "m1") & (timing_df["killer_name"] == "Alice")].iloc[0]
        self.assertEqual(alice_timing["event_kill_count"], 2)
        self.assertEqual(alice_timing["first_kill_time"], 100.0)
        self.assertEqual(alice_timing["avg_kill_time"], 225.0) # (100 + 350) / 2
        self.assertEqual(alice_timing["early_kills"], 1) # 100 < 200s
        self.assertEqual(alice_timing["mid_kills"], 1)   # 200 <= 350 < 400s
        self.assertEqual(alice_timing["late_kills"], 0)

        # 6. Merge Player Match Features
        final_pq = self.test_dir / "player_match_features.parquet"
        discrepancy_csv = self.test_dir / "kill_discrepancy.csv"
        final_rows = merge_player_match_and_timing(self.con, cleaned_pq, meta_pq, timing_pq, final_pq, discrepancy_csv)
        self.assertEqual(final_rows, 7) # Invariant: exact same row count as cleaned aggregate

        final_df = pd.read_parquet(final_pq)
        bob = final_df[final_df["player_name"] == "Bob"].iloc[0]
        self.assertTrue(np.isnan(bob["walk_ratio"])) # 0 dist -> NaN
        self.assertTrue(np.isnan(bob["damage_per_kill"])) # 0 kills -> NaN
        self.assertEqual(bob["event_kill_count"], 0)
        self.assertFalse(bob["has_kill"])
        self.assertTrue(np.isnan(bob["first_kill_time"]))

        alice = final_df[final_df["player_name"] == "Alice"].iloc[0]
        self.assertEqual(alice["normalized_placement"], 1.0) # Rank 1 of 2 teams -> 1 - (1-1)/(2-1) = 1.0
        david = final_df[final_df["player_name"] == "David"].iloc[0]
        self.assertEqual(david["normalized_placement"], 0.0) # Rank 2 of 2 teams -> 1 - (2-1)/(2-1) = 0.0

        # 7. Checkpoint Manager Test
        ckpt_path = self.test_dir / "checkpoint_manifest.json"
        mgr = CheckpointManager(manifest_path=ckpt_path)
        mgr.mark_running("player_match_features", "sig123")
        self.assertFalse(mgr.is_compatible("player_match_features", "sig123")) # running is not completed
        mgr.commit("player_match_features", "sig123", {"final_dataset": final_pq})
        self.assertTrue(mgr.is_compatible("player_match_features", "sig123"))

        # Test invalidation
        invalidated = mgr.invalidate_descendants("player_match_features")
        self.assertIn("eda", invalidated)
        self.assertIn("rq1", invalidated)
        self.assertIn("rq3_prediction", invalidated)

    def test_cleaning_rejects_missing_stage_01_output(self):
        with self.assertRaisesRegex(FileNotFoundError, "Run notebook 01"):
            audit_and_clean_aggregate_data(
                self.con, [], self.test_dir / "cleaned.parquet", self.test_dir / "removal.csv"
            )


if __name__ == "__main__":
    unittest.main()
