import shutil
import tempfile
import unittest
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd

from src.data.io import copy_query_to_parquet
from src.features.combat_timing import (
    extract_and_aggregate_combat_timing,
    merge_player_match_and_timing,
)


class TestW05CombatTiming(unittest.TestCase):
    """Rigorous tests for W05 (Phase IX - Notebook 04): Combat Timing & Event Aggregation."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.con = duckdb.connect(database=":memory:")

        # 1. Setup mock match metadata for 3 matches:
        # - m1: standard valid match, duration = 600.0s, 2 teams
        # - m2: short match (< 60s), duration = 45.0s, 2 teams
        # - m3: standard match, duration = 1200.0s, 2 teams
        meta_df = pd.DataFrame([
            {"match_id": "m1", "observed_team_count": 2, "estimated_match_duration": 600.0, "match_mode": "squad", "party_size": 4},
            {"match_id": "m2", "observed_team_count": 2, "estimated_match_duration": 45.0, "match_mode": "squad", "party_size": 4},
            {"match_id": "m3", "observed_team_count": 2, "estimated_match_duration": 1200.0, "match_mode": "squad", "party_size": 4},
        ])
        self.meta_pq = self.test_dir / "match_metadata.parquet"
        meta_df.to_parquet(self.meta_pq, index=False)

        # 2. Setup mock player_match_base for testing merge
        self.base_df = pd.DataFrame([
            # m1 players
            {"match_id": "m1", "player_name": "P_Normal", "team_id": "t1", "date": "2017-11-01", "match_mode": "squad",
             "party_size": 4, "perspective_mode": "tpp", "team_size_mode": "squad", "observed_team_count": 2,
             "estimated_match_duration": 600.0, "player_kills": 2, "player_dmg": 200.0, "player_dist_walk": 1000.0,
             "player_dist_ride": 500.0, "player_assists": 0, "player_dbno": 1, "player_survive_time": 600.0,
             "team_placement": 1, "normalized_placement": 1.0, "placement_validity_flag": "VALID",
             "damage_per_kill": 100.0, "total_distance": 1500.0, "walk_ratio": 0.6667, "assist_ratio": 0.0},
            {"match_id": "m1", "player_name": "P_SameSec", "team_id": "t1", "date": "2017-11-01", "match_mode": "squad",
             "party_size": 4, "perspective_mode": "tpp", "team_size_mode": "squad", "observed_team_count": 2,
             "estimated_match_duration": 600.0, "player_kills": 2, "player_dmg": 220.0, "player_dist_walk": 800.0,
             "player_dist_ride": 0.0, "player_assists": 1, "player_dbno": 2, "player_survive_time": 500.0,
             "team_placement": 1, "normalized_placement": 1.0, "placement_validity_flag": "VALID",
             "damage_per_kill": 110.0, "total_distance": 800.0, "walk_ratio": 1.0, "assist_ratio": 0.3333},
            {"match_id": "m1", "player_name": "P_OutOfRange", "team_id": "t2", "date": "2017-11-01", "match_mode": "squad",
             "party_size": 4, "perspective_mode": "tpp", "team_size_mode": "squad", "observed_team_count": 2,
             "estimated_match_duration": 600.0, "player_kills": 1, "player_dmg": 95.0, "player_dist_walk": 500.0,
             "player_dist_ride": 0.0, "player_assists": 0, "player_dbno": 0, "player_survive_time": 400.0,
             "team_placement": 2, "normalized_placement": 0.0, "placement_validity_flag": "VALID",
             "damage_per_kill": 95.0, "total_distance": 500.0, "walk_ratio": 1.0, "assist_ratio": 0.0},
            {"match_id": "m1", "player_name": "P_ZeroKills", "team_id": "t2", "date": "2017-11-01", "match_mode": "squad",
             "party_size": 4, "perspective_mode": "tpp", "team_size_mode": "squad", "observed_team_count": 2,
             "estimated_match_duration": 600.0, "player_kills": 0, "player_dmg": 0.0, "player_dist_walk": 100.0,
             "player_dist_ride": 0.0, "player_assists": 0, "player_dbno": 0, "player_survive_time": 120.0,
             "team_placement": 2, "normalized_placement": 0.0, "placement_validity_flag": "VALID",
             "damage_per_kill": np.nan, "total_distance": 100.0, "walk_ratio": 1.0, "assist_ratio": np.nan},
            {"match_id": "m1", "player_name": "P_MissingEvents", "team_id": "t2", "date": "2017-11-01", "match_mode": "squad",
             "party_size": 4, "perspective_mode": "tpp", "team_size_mode": "squad", "observed_team_count": 2,
             "estimated_match_duration": 600.0, "player_kills": 3, "player_dmg": 300.0, "player_dist_walk": 900.0,
             "player_dist_ride": 0.0, "player_assists": 0, "player_dbno": 1, "player_survive_time": 450.0,
             "team_placement": 2, "normalized_placement": 0.0, "placement_validity_flag": "VALID",
             "damage_per_kill": 100.0, "total_distance": 900.0, "walk_ratio": 1.0, "assist_ratio": 0.0},
            # m2 player (short match)
            {"match_id": "m2", "player_name": "P_ShortMatch", "team_id": "t1", "date": "2017-11-01", "match_mode": "squad",
             "party_size": 4, "perspective_mode": "tpp", "team_size_mode": "squad", "observed_team_count": 2,
             "estimated_match_duration": 45.0, "player_kills": 1, "player_dmg": 100.0, "player_dist_walk": 50.0,
             "player_dist_ride": 0.0, "player_assists": 0, "player_dbno": 1, "player_survive_time": 45.0,
             "team_placement": 1, "normalized_placement": 1.0, "placement_validity_flag": "VALID",
             "damage_per_kill": 100.0, "total_distance": 50.0, "walk_ratio": 1.0, "assist_ratio": 0.0},
        ])
        self.base_pq = self.test_dir / "player_match_base.parquet"
        self.base_df.to_parquet(self.base_pq, index=False)

        # 3. Setup mock raw death events to test edge cases:
        deaths_records = [
            # Valid kills for P_Normal: 1 early (100s), 1 mid (350s). Match duration = 600s.
            {"match_id": "m1", "time": 100.0, "killer_name": "P_Normal", "victim_name": "Victim_A", "killed_by": "M416"},
            {"match_id": "m1", "time": 350.0, "killer_name": "P_Normal", "victim_name": "Victim_B", "killed_by": "SCAR-L"},

            # P_SameSec: 2 kills at the EXACT same second (120.0s) against different victims! Both early.
            {"match_id": "m1", "time": 120.0, "killer_name": "P_SameSec", "victim_name": "Victim_C", "killed_by": "Grenade"},
            {"match_id": "m1", "time": 120.0, "killer_name": "P_SameSec", "victim_name": "Victim_D", "killed_by": "Grenade"},

            # P_OutOfRange: 1 kill at 650.0s (> estimated_match_duration 600.0s)
            {"match_id": "m1", "time": 650.0, "killer_name": "P_OutOfRange", "victim_name": "Victim_E", "killed_by": "Kar98k"},

            # P_ShortMatch: 1 kill in m2 (duration = 45s < 60s)
            {"match_id": "m2", "time": 20.0, "killer_name": "P_ShortMatch", "victim_name": "Victim_F", "killed_by": "Punch"},

            # Invalid events that MUST be excluded from aggregation and audited:
            # - Self-kill (suicide)
            {"match_id": "m1", "time": 300.0, "killer_name": "SuicideGuy", "victim_name": "SuicideGuy", "killed_by": "Falling"},
            # - Missing killer name
            {"match_id": "m1", "time": 250.0, "killer_name": None, "victim_name": "Victim_G", "killed_by": "Bluezone"},
            # - Missing victim name
            {"match_id": "m1", "time": 260.0, "killer_name": "Killer_X", "victim_name": "", "killed_by": "Drown"},
            # - Negative time
            {"match_id": "m1", "time": -5.0, "killer_name": "BadTimer", "victim_name": "Victim_H", "killed_by": "AKM"},
            # - Unmatched match
            {"match_id": "m_unknown", "time": 150.0, "killer_name": "Ghost", "victim_name": "Victim_I", "killed_by": "UMP9"},
        ]
        self.deaths_pq = self.test_dir / "deaths_shard_0.parquet"
        pd.DataFrame(deaths_records).to_parquet(self.deaths_pq, index=False)

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.test_dir)

    def test_event_filtering_and_audit(self):
        """Verify that self-kills, missing IDs, negative time, and unmatched matches are filtered."""
        timing_pq = self.test_dir / "combat_timing.parquet"
        audit_dir = self.test_dir / "audit"

        audit = extract_and_aggregate_combat_timing(
            self.con, [self.deaths_pq], self.meta_pq, timing_pq, audit_dir
        )

        self.assertEqual(audit["total_death_events"], 11)
        self.assertEqual(audit["self_kills"], 1)
        self.assertEqual(audit["missing_killer_or_victim"], 2)
        self.assertEqual(audit["negative_or_nan_time"], 1)
        self.assertEqual(audit["unmatched_match"], 1)
        # 11 - (1 + 2 + 1 + 1) = 6 valid absolute events
        self.assertEqual(audit["valid_absolute_events"], 6)
        self.assertEqual(audit["valid_enemy_kills"], 6)
        self.assertEqual(audit["short_duration_events"], 1)  # m2 event
        self.assertEqual(audit["out_of_range_time_events"], 1)  # 650s in 600s match
        # 6 valid absolute - 1 short duration - 1 out-of-range = 4 valid phase events
        self.assertEqual(audit["valid_phase_events"], 4)

        # Audit file persisted
        audit_csv = audit_dir / "event_join_audit.csv"
        self.assertTrue(audit_csv.exists())
        audit_df = pd.read_csv(audit_csv)
        self.assertEqual(audit_df["valid_absolute_events"].iloc[0], 6)

    def test_preserves_multiple_kills_in_same_second(self):
        """Verify that events are not deduplicated by (match_id, killer_name, time)."""
        timing_pq = self.test_dir / "combat_timing.parquet"
        audit_dir = self.test_dir / "audit"
        extract_and_aggregate_combat_timing(
            self.con, [self.deaths_pq], self.meta_pq, timing_pq, audit_dir
        )

        timing_df = pd.read_parquet(timing_pq)
        same_sec = timing_df[(timing_df["match_id"] == "m1") & (timing_df["killer_name"] == "P_SameSec")].iloc[0]
        self.assertEqual(same_sec["event_kill_count"], 2)
        self.assertEqual(same_sec["early_kills"], 2)
        self.assertEqual(same_sec["early_kill_ratio"], 1.0)
        self.assertEqual(same_sec["first_kill_time"], 120.0)
        self.assertEqual(same_sec["avg_kill_time"], 120.0)

    def test_absolute_timing_preserved_when_out_of_range(self):
        """Verify time > duration does not discard absolute timing, but yields NULL phase ratios."""
        timing_pq = self.test_dir / "combat_timing.parquet"
        audit_dir = self.test_dir / "audit"
        extract_and_aggregate_combat_timing(
            self.con, [self.deaths_pq], self.meta_pq, timing_pq, audit_dir
        )

        timing_df = pd.read_parquet(timing_pq)
        oor = timing_df[(timing_df["match_id"] == "m1") & (timing_df["killer_name"] == "P_OutOfRange")].iloc[0]
        self.assertEqual(oor["event_kill_count"], 1)
        self.assertEqual(oor["first_kill_time"], 650.0)
        self.assertEqual(oor["avg_kill_time"], 650.0)
        self.assertTrue(oor["has_kill"])
        # Phase timing: not phase eligible
        self.assertEqual(oor["early_kills"], 0)
        self.assertEqual(oor["mid_kills"], 0)
        self.assertEqual(oor["late_kills"], 0)
        self.assertTrue(pd.isna(oor["early_kill_ratio"]))
        self.assertTrue(pd.isna(oor["mid_kill_ratio"]))
        self.assertTrue(pd.isna(oor["late_kill_ratio"]))

    def test_short_match_duration_yields_null_phase_ratios(self):
        """Verify match duration < 60s preserves absolute timing but yields NULL phase ratios."""
        timing_pq = self.test_dir / "combat_timing.parquet"
        audit_dir = self.test_dir / "audit"
        extract_and_aggregate_combat_timing(
            self.con, [self.deaths_pq], self.meta_pq, timing_pq, audit_dir
        )

        timing_df = pd.read_parquet(timing_pq)
        short_p = timing_df[(timing_df["match_id"] == "m2") & (timing_df["killer_name"] == "P_ShortMatch")].iloc[0]
        self.assertEqual(short_p["event_kill_count"], 1)
        self.assertEqual(short_p["first_kill_time"], 20.0)
        self.assertTrue(pd.isna(short_p["early_kill_ratio"]))
        self.assertTrue(pd.isna(short_p["mid_kill_ratio"]))
        self.assertTrue(pd.isna(short_p["late_kill_ratio"]))

    def test_merge_player_match_and_timing_invariants(self):
        """Verify merge preserves row count, handles 0-kill semantics, and exports full audits."""
        timing_pq = self.test_dir / "combat_timing.parquet"
        audit_dir = self.test_dir / "audit"
        extract_and_aggregate_combat_timing(
            self.con, [self.deaths_pq], self.meta_pq, timing_pq, audit_dir
        )

        out_pq = self.test_dir / "player_match_features.parquet"
        discrepancy_csv = self.test_dir / "kill_discrepancy.csv"
        merged_rows = merge_player_match_and_timing(
            self.con, self.base_pq, timing_pq, out_pq, discrepancy_csv
        )

        # 1. Row count preservation
        self.assertEqual(merged_rows, len(self.base_df))
        df = pd.read_parquet(out_pq)
        self.assertEqual(len(df), len(self.base_df))

        # 2. Zero-kill player semantics
        zero_p = df[df["player_name"] == "P_ZeroKills"].iloc[0]
        self.assertEqual(zero_p["event_kill_count"], 0)
        self.assertFalse(zero_p["has_kill"])
        self.assertTrue(pd.isna(zero_p["first_kill_time"]))
        self.assertTrue(pd.isna(zero_p["avg_kill_time"]))
        self.assertTrue(pd.isna(zero_p["early_kill_ratio"]))
        self.assertTrue(pd.isna(zero_p["mid_kill_ratio"]))
        self.assertTrue(pd.isna(zero_p["late_kill_ratio"]))
        self.assertFalse(zero_p["has_event_record"])
        self.assertEqual(zero_p["kill_discrepancy"], 0)

        # 3. Missing event record player (player_kills = 3, but 0 death records)
        missing_p = df[df["player_name"] == "P_MissingEvents"].iloc[0]
        self.assertEqual(missing_p["player_kills"], 3)
        self.assertEqual(missing_p["event_kill_count"], 0)
        self.assertFalse(missing_p["has_kill"])
        self.assertTrue(pd.isna(missing_p["first_kill_time"]))
        self.assertFalse(missing_p["has_event_record"])
        self.assertEqual(missing_p["kill_discrepancy"], 3)

        # 4. Normal player phase ratio sum == 1.0
        normal_p = df[df["player_name"] == "P_Normal"].iloc[0]
        self.assertAlmostEqual(
            normal_p["early_kill_ratio"] + normal_p["mid_kill_ratio"] + normal_p["late_kill_ratio"],
            1.0,
            places=5,
        )

        # 5. Check discrepancy and coverage tables
        self.assertTrue(discrepancy_csv.exists())
        disc_df = pd.read_csv(discrepancy_csv)
        self.assertTrue(len(disc_df) >= 2)  # 0 discrepancy and 3 discrepancy

        cov_csv = self.test_dir / "event_timing_coverage.csv"
        self.assertTrue(cov_csv.exists())
        cov_df = pd.read_csv(cov_csv)
        categories = set(cov_df["category"].tolist())
        self.assertIn("kills_zero_no_event", categories)
        self.assertIn("kills_pos_missing_event", categories)
        self.assertIn("kills_pos_exact_match", categories)


if __name__ == "__main__":
    unittest.main()
