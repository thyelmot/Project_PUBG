"""Tests for Phase VIII (Giai đoạn 5: Notebook 03, Feature cơ sở và target)
per PUBG_IMPLEMENTATION_PLAN.md Section 19.
"""

import json
import shutil
import tempfile
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np

from src.features.combat import compute_combat_features
from src.features.movement import compute_movement_features
from src.features.support import compute_support_features
from src.features.placement import compute_normalized_placement
from src.features.base import build_player_match_base
from src.features.combat_timing import merge_player_match_and_timing
from src.features.registry import FeatureRegistry
from src.data.io import get_duckdb_connection, atomic_write_parquet


class TestFeatureFormulasAndZeroDenominators(unittest.TestCase):
    """Checklist items 1167-1169: Formulas, division by zero semantics, normalized placement without clipping."""

    def test_combat_damage_per_kill_zero_division(self):
        df = pd.DataFrame({
            "player_kills": [0, 2, 5],
            "player_dmg": [100.0, 300.0, 500.0],
        })
        res = compute_combat_features(df)
        self.assertTrue(np.isnan(res.loc[0, "damage_per_kill"]))  # 0 kills -> NaN
        self.assertEqual(res.loc[1, "damage_per_kill"], 150.0)
        self.assertEqual(res.loc[2, "damage_per_kill"], 100.0)

    def test_movement_walk_ratio_zero_distance(self):
        df = pd.DataFrame({
            "player_dist_walk": [0.0, 500.0, 300.0],
            "player_dist_ride": [0.0, 0.0, 700.0],
        })
        res = compute_movement_features(df)
        self.assertEqual(res.loc[0, "total_distance"], 0.0)
        self.assertTrue(np.isnan(res.loc[0, "walk_ratio"]))  # 0 distance -> NaN
        self.assertEqual(res.loc[1, "walk_ratio"], 1.0)
        self.assertEqual(res.loc[2, "walk_ratio"], 0.3)

    def test_support_assist_ratio_zero_combat(self):
        df = pd.DataFrame({
            "player_assists": [0, 1, 3],
            "player_dbno": [0, 1, 2],
            "player_kills": [0, 1, 0],
        })
        res = compute_support_features(df)
        self.assertTrue(np.isnan(res.loc[0, "assist_ratio"]))  # 0 assists + 0 kills -> NaN
        self.assertEqual(res.loc[1, "assist_ratio"], 0.5)      # 1 / (1 + 1)
        self.assertEqual(res.loc[2, "assist_ratio"], 1.0)      # 3 / (3 + 0)

    def test_normalized_placement_formula_and_no_clipping_errors(self):
        team_placement = pd.Series([1, 100, 50, 0, 105, 5])
        observed_team_count = pd.Series([100, 100, 99, 100, 100, 1])  # 1 is invalid (N_teams <= 1)
        is_roster_complete = pd.Series([True, True, True, True, True, True])

        res = compute_normalized_placement(team_placement, observed_team_count, is_roster_complete)

        # Placement 1 of 100 teams -> 1.0 - 0 = 1.0
        self.assertEqual(res.loc[0, "normalized_placement"], 1.0)
        self.assertTrue(res.loc[0, "placement_valid"])

        # Placement 100 of 100 teams -> 1.0 - 1.0 = 0.0
        self.assertEqual(res.loc[1, "normalized_placement"], 0.0)
        self.assertTrue(res.loc[1, "placement_valid"])

        # Placement 50 of 99 teams -> 1.0 - 49.0 / 98.0 = 0.5
        self.assertEqual(res.loc[2, "normalized_placement"], 0.5)
        self.assertTrue(res.loc[2, "placement_valid"])

        # Invalid placement 0 (out of bounds) -> NaN and NOT valid (not clipped)
        self.assertTrue(np.isnan(res.loc[3, "normalized_placement"]))
        self.assertFalse(res.loc[3, "placement_valid"])

        # Invalid placement 105 (greater than N_teams 100) -> NaN and NOT valid (not clipped to 0.0)
        self.assertTrue(np.isnan(res.loc[4, "normalized_placement"]))
        self.assertFalse(res.loc[4, "placement_valid"])

        # Invalid N_teams = 1 -> NaN and NOT valid
        self.assertTrue(np.isnan(res.loc[5, "normalized_placement"]))
        self.assertFalse(res.loc[5, "placement_valid"])

    def test_normalized_placement_rejects_incomplete_roster(self):
        team_placement = pd.Series([1, 2])
        observed_team_count = pd.Series([10, 10])
        is_roster_complete = pd.Series([False, True])

        res = compute_normalized_placement(team_placement, observed_team_count, is_roster_complete)
        # Roster incomplete -> rejected (NaN, invalid)
        self.assertTrue(np.isnan(res.loc[0, "normalized_placement"]))
        self.assertFalse(res.loc[0, "placement_valid"])

        # Roster complete -> valid
        self.assertFalse(np.isnan(res.loc[1, "normalized_placement"]))
        self.assertTrue(res.loc[1, "placement_valid"])


class TestBuildPlayerMatchBasePipeline(unittest.TestCase):
    """Checklist items 1164-1174: Intermediate output schema, row preservation,
    perspective_mode / team_size_mode separation, non-standard party_size handling, dictionary & validation summary.
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.tmpdir.name)
        self.con = get_duckdb_connection()

        # Synthetic cleaned aggregate data
        agg_records = [
            # match_id, player_name, team_id, date, match_mode, party_size, game_size, assists, dbno, ride, walk, dmg, kills, survive, placement, valid_survival, valid_placement
            # m1: solo tpp (party_size=1)
            ["m1", "Alice", "t1", "2017-11-20T10:00:00+0000", "tpp", 1, 2, 0, 0, 0.0, 500.0, 150.0, 1, 400.0, 1, True, True],
            ["m1", "Bob", "t2", "2017-11-20T10:00:00+0000", "tpp", 1, 2, 0, 0, 0.0, 200.0, 50.0, 0, 250.0, 2, True, True],
            # m2: squad fpp (party_size=4)
            ["m2", "Charlie", "t3", "2017-11-21T12:00:00+0000", "squad-fpp", 4, 3, 1, 1, 100.0, 1000.0, 300.0, 2, 600.0, 1, True, True],
            ["m2", "David", "t4", "2017-11-21T12:00:00+0000", "squad-fpp", 4, 3, 0, 0, 0.0, 300.0, 100.0, 0, 300.0, 2, True, True],
            # m3: custom / non-standard party_size (party_size=3 -> team_size_mode='unknown')
            ["m3", "Eve", "t5", "2017-11-22T14:00:00+0000", "custom-event", 3, 10, 0, 0, 0.0, 0.0, 0.0, 0, 100.0, 1, True, True],
            # Anonymous player (player_name is null) in m3
            ["m3", None, "t6", "2017-11-22T14:00:00+0000", "custom-event", 3, 10, 0, 0, 0.0, 50.0, 0.0, 0, 80.0, 2, True, True],
        ]
        agg_cols = [
            "match_id", "player_name", "team_id", "date", "match_mode", "party_size", "game_size",
            "player_assists", "player_dbno", "player_dist_ride", "player_dist_walk",
            "player_dmg", "player_kills", "player_survive_time", "team_placement",
            "valid_survival", "valid_placement"
        ]
        self.clean_pq = self.work_dir / "cleaned_aggregate.parquet"
        atomic_write_parquet(self.clean_pq, pd.DataFrame(agg_records, columns=agg_cols))

        # Synthetic match metadata
        meta_records = [
            ["m1", "2017-11-20T10:00:00+0000", "tpp", 1, 2, 2, 2, 2, 400.0, True, False, False, False, False],
            ["m2", "2017-11-21T12:00:00+0000", "squad-fpp", 4, 3, 2, 2, 2, 600.0, True, False, False, False, False],
            ["m3", "2017-11-22T14:00:00+0000", "custom-event", 3, 10, 2, 2, 2, 100.0, True, False, False, False, False],
        ]
        meta_cols = [
            "match_id", "match_date", "match_mode", "party_size", "game_size",
            "observed_team_count", "observed_player_count", "max_observed_placement",
            "estimated_match_duration", "is_roster_complete",
            "has_date_conflict", "has_mode_conflict", "has_party_size_conflict", "has_game_size_conflict"
        ]
        self.meta_pq = self.work_dir / "match_metadata.parquet"
        atomic_write_parquet(self.meta_pq, pd.DataFrame(meta_records, columns=meta_cols))

        self.base_pq = self.work_dir / "player_match_base.parquet"
        self.val_csv = self.work_dir / "feature_validation_base.csv"
        self.dict_csv = self.work_dir / "feature_dictionary.csv"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_build_player_match_base_row_preservation_and_schema(self):
        rows = build_player_match_base(
            con=self.con,
            cleaned_aggregate_parquet=self.clean_pq,
            match_metadata_parquet=self.meta_pq,
            output_base_parquet=self.base_pq,
            validation_csv_path=self.val_csv,
            dictionary_csv_path=self.dict_csv,
        )

        # Invariant: Exact row preservation (6 rows in clean_pq -> 6 rows in base_pq)
        self.assertEqual(rows, 6)

        df_base = pd.read_parquet(self.base_pq)
        self.assertEqual(len(df_base), 6)

        # Invariant: perspective_mode and team_size_mode decoupling
        self.assertIn("perspective_mode", df_base.columns)
        self.assertIn("team_size_mode", df_base.columns)

        m1_alice = df_base[df_base["player_name"] == "Alice"].iloc[0]
        self.assertEqual(m1_alice["perspective_mode"], "tpp")
        self.assertEqual(m1_alice["team_size_mode"], "solo")
        self.assertEqual(m1_alice["damage_per_kill"], 150.0)
        self.assertEqual(m1_alice["walk_ratio"], 1.0)
        self.assertEqual(m1_alice["normalized_placement"], 1.0)

        m2_charlie = df_base[df_base["player_name"] == "Charlie"].iloc[0]
        self.assertEqual(m2_charlie["perspective_mode"], "fpp")
        self.assertEqual(m2_charlie["team_size_mode"], "squad")
        self.assertEqual(m2_charlie["total_distance"], 1100.0)
        self.assertEqual(m2_charlie["assist_ratio"], 1.0 / 3.0)

        # Non-standard party_size=3 maps to 'unknown' (never coerced to 1/2/4)
        m3_eve = df_base[df_base["player_name"] == "Eve"].iloc[0]
        self.assertEqual(m3_eve["team_size_mode"], "unknown")
        self.assertTrue(np.isnan(m3_eve["damage_per_kill"]))
        self.assertTrue(np.isnan(m3_eve["walk_ratio"]))
        self.assertTrue(np.isnan(m3_eve["assist_ratio"]))

        # Validation CSV check
        self.assertTrue(self.val_csv.is_file())
        df_val = pd.read_csv(self.val_csv)
        self.assertIn("feature_name", df_val.columns)
        self.assertIn("null_pct", df_val.columns)
        self.assertIn("zero_rate", df_val.columns)

        # Dictionary CSV check
        self.assertTrue(self.dict_csv.is_file())
        df_dict = pd.read_csv(self.dict_csv)
        self.assertIn("feature_name", df_dict.columns)
        self.assertIn("allowed_tasks", df_dict.columns)
        self.assertIn("missing_semantics", df_dict.columns)

    def test_consumer_notebook_04_integration(self):
        """Verify that Notebook 04 (merge_player_match_and_timing) cleanly consumes
        Notebook 03 output (player_match_base.parquet) without re-calculating base features.
        """
        build_player_match_base(
            con=self.con,
            cleaned_aggregate_parquet=self.clean_pq,
            match_metadata_parquet=self.meta_pq,
            output_base_parquet=self.base_pq,
        )

        # Mock timing parquet from Notebook 04
        timing_records = [
            ["m1", "Alice", 1, 150.0, 150.0, 1, 0, 0, 1.0, 0.0, 0.0, True],
        ]
        timing_cols = [
            "match_id", "killer_name", "event_kill_count", "first_kill_time", "avg_kill_time",
            "early_kills", "mid_kills", "late_kills", "early_kill_ratio", "mid_kill_ratio", "late_kill_ratio", "has_kill"
        ]
        timing_pq = self.work_dir / "combat_timing.parquet"
        atomic_write_parquet(timing_pq, pd.DataFrame(timing_records, columns=timing_cols))

        final_pq = self.work_dir / "player_match_features.parquet"
        discrepancy_csv = self.work_dir / "discrepancy.csv"

        # Call with 5-arg clean signature (consuming base_pq)
        merged_rows = merge_player_match_and_timing(
            con=self.con,
            base_or_cleaned_parquet=self.base_pq,
            timing_or_meta_parquet=timing_pq,
            output_or_timing_parquet=final_pq,
            discrepancy_or_output_path=discrepancy_csv,
        )

        self.assertEqual(merged_rows, 6)
        df_final = pd.read_parquet(final_pq)
        self.assertEqual(len(df_final), 6)
        # All base features are preserved
        self.assertIn("normalized_placement", df_final.columns)
        self.assertIn("damage_per_kill", df_final.columns)
        self.assertIn("team_size_mode", df_final.columns)
        # Timing features and diagnostics are added
        self.assertIn("early_kills", df_final.columns)
        self.assertIn("kills_per_minute", df_final.columns)
        self.assertIn("kill_discrepancy", df_final.columns)


if __name__ == "__main__":
    unittest.main()
