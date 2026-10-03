import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd

from src.data.io import copy_query_to_parquet
from src.features.combat_timing import (
    evaluate_combat_timing_research_gate,
    extract_and_aggregate_combat_timing,
    merge_player_match_and_timing,
)
from src.features.registry import FeatureRegistry


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
        deaths_df = pd.DataFrame(deaths_records)
        deaths_df["source_file"] = "deaths_shard_0.csv"
        deaths_df["source_row"] = np.arange(1, len(deaths_df) + 1)
        deaths_df.to_parquet(self.deaths_pq, index=False)

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.test_dir)

    def test_event_filtering_and_audit(self):
        """Verify that self-kills, missing IDs, negative time, and unmatched matches are filtered."""
        timing_pq = self.test_dir / "combat_timing.parquet"
        audit_dir = self.test_dir / "audit"

        audit = extract_and_aggregate_combat_timing(
            self.con, [self.deaths_pq], self.meta_pq, timing_pq, audit_dir,
            player_match_base_parquet=self.base_pq,
        )

        self.assertEqual(audit["total_death_events"], 11)
        self.assertEqual(audit["self_kills"], 1)
        self.assertEqual(audit["missing_killer_or_victim"], 2)
        self.assertEqual(audit["negative_or_nan_time"], 1)
        self.assertEqual(audit["unmatched_match"], 1)
        # Victim/cause are optional in the core contract; a named credited killer remains eligible.
        self.assertEqual(audit["valid_absolute_events"], 7)
        self.assertEqual(audit["enemy_kill_eligibility_status"], "pending_team_or_cause_evidence")
        self.assertEqual(audit["event_time_unit_status"], "pending_source_or_consistency_evidence")
        self.assertEqual(audit["min_duration_threshold_status"], "pending_real_data_evidence")
        self.assertEqual(audit["short_duration_events"], 1)  # m2 event
        self.assertEqual(audit["out_of_range_time_events"], 1)  # 650s in 600s match
        self.assertEqual(audit["valid_phase_events"], 5)
        self.assertEqual(audit["matched_match_events"], 10)
        self.assertEqual(audit["match_join_denominator"], 11)
        self.assertEqual(audit["matched_killer_roster_events"], 6)
        self.assertEqual(audit["named_killer_event_denominator"], 10)
        self.assertFalse(audit["enemy_kill_eligibility_verified"])

        # Audit file persisted
        audit_csv = audit_dir / "event_join_audit.csv"
        self.assertTrue(audit_csv.exists())
        audit_df = pd.read_csv(audit_csv)
        self.assertEqual(audit_df["valid_absolute_events"].iloc[0], 7)
        self.assertEqual(audit_df["event_identity_status"].iloc[0], "source_lineage_available")
        ledger = pd.read_parquet(audit_dir / "event_validation_ledger.parquet")
        self.assertEqual(len(ledger), 11)
        self.assertTrue(ledger["event_source_key"].str.startswith("deaths_shard_0.csv:").all())
        self.assertIn("flag_environment_cause", ledger.columns)
        self.assertIn("flag_potential_replay", ledger.columns)

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
        self.assertEqual(same_sec["sum_kill_time"], 240.0)
        self.assertEqual(same_sec["phase_eligible_kill_count"], 2)
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
        self.assertEqual(missing_p["timing_coverage_status"], "aggregate_kill_event_missing")
        self.assertTrue(pd.isna(missing_p["early_kills"]))
        self.assertTrue(pd.isna(missing_p["phase_eligible_kill_count"]))

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
        self.assertEqual(len(disc_df), len(self.base_df))
        self.assertIn("timing_coverage_status", disc_df.columns)
        self.assertIn("kill_discrepancy_signed", disc_df.columns)

        cov_csv = self.test_dir / "event_timing_coverage.csv"
        self.assertTrue(cov_csv.exists())
        cov_df = pd.read_csv(cov_csv)
        categories = set(cov_df["category"].tolist())
        self.assertIn("confirmed_no_kill_no_event", categories)
        self.assertIn("aggregate_kill_event_missing", categories)
        self.assertIn("event_count_exact", categories)
        self.assertIn("phase_eligible_event_count", cov_df.columns)

    def test_global_reduce_phase_boundaries_and_pending_gates(self):
        shard_rows = [
            ["m1", 100.0, "Boundary", "V1", "M416"],
            ["m1", 200.0, "Boundary", "V2", "M416"],
            ["m1", 400.0, "Boundary", "V3", "M416"],
            ["m1", 600.0, "Boundary", "V4", "M416"],
        ]
        columns = ["match_id", "time", "killer_name", "victim_name", "killed_by"]
        shards = []
        for index, rows in enumerate((shard_rows[:2], shard_rows[2:])):
            frame = pd.DataFrame(rows, columns=columns)
            frame["source_file"] = f"boundary_{index}.csv"
            frame["source_row"] = np.arange(1, len(frame) + 1)
            path = self.test_dir / f"boundary_{index}.parquet"
            frame.to_parquet(path, index=False)
            shards.append(path)

        timing_pq = self.test_dir / "boundary_timing.parquet"
        audit = extract_and_aggregate_combat_timing(
            self.con, shards, self.meta_pq, timing_pq, self.test_dir / "boundary_audit"
        )
        row = pd.read_parquet(timing_pq).query("killer_name == 'Boundary'").iloc[0]
        self.assertEqual(row["event_kill_count"], 4)
        self.assertEqual(row["sum_kill_time"], 1300.0)
        self.assertEqual(row["first_kill_time"], 100.0)
        self.assertEqual(row["avg_kill_time"], 325.0)
        self.assertEqual((row["early_kills"], row["mid_kills"], row["late_kills"]), (1, 1, 2))
        self.assertEqual(row["phase_eligible_kill_count"], 4)
        self.assertEqual(audit["valid_phase_events"], 4)

    def test_potential_replay_is_audited_without_deduplication(self):
        repeated = pd.DataFrame([
            {"match_id": "m1", "time": 90.0, "killer_name": "Replay", "victim_name": "Victim", "killed_by": "M416", "source_file": "a.csv", "source_row": 1},
            {"match_id": "m1", "time": 90.0, "killer_name": "Replay", "victim_name": "Victim", "killed_by": "M416", "source_file": "b.csv", "source_row": 9},
        ])
        path = self.test_dir / "replayed.parquet"
        repeated.to_parquet(path, index=False)
        timing_pq = self.test_dir / "replayed_timing.parquet"
        audit = extract_and_aggregate_combat_timing(
            self.con, [path], self.meta_pq, timing_pq, self.test_dir / "replayed_audit"
        )
        row = pd.read_parquet(timing_pq).iloc[0]
        self.assertEqual(row["event_kill_count"], 2)
        self.assertEqual(audit["potential_replayed_event_rows"], 2)

    def test_missing_source_lineage_is_explicitly_pending(self):
        no_lineage = pd.DataFrame([
            {"match_id": "m1", "time": 10.0, "killer_name": "P_Normal", "victim_name": None, "killed_by": None},
        ])
        path = self.test_dir / "no_lineage.parquet"
        no_lineage.to_parquet(path, index=False)
        audit = extract_and_aggregate_combat_timing(
            self.con, [path], self.meta_pq, self.test_dir / "no_lineage_timing.parquet",
            self.test_dir / "no_lineage_audit",
        )
        self.assertEqual(audit["valid_absolute_events"], 1)
        self.assertEqual(audit["event_identity_status"], "pending_source_lineage")
        self.assertIn("pending/unavailable", audit["event_identity_policy"])

    def test_optional_victim_and_cause_columns_do_not_block_core_timing(self):
        minimal = pd.DataFrame([
            {"match_id": "m1", "time": 10.0, "killer_name": "P_Normal", "source_file": "minimal.csv", "source_row": 1},
        ])
        path = self.test_dir / "minimal_deaths.parquet"
        minimal.to_parquet(path, index=False)
        audit = extract_and_aggregate_combat_timing(
            self.con, [path], self.meta_pq, self.test_dir / "minimal_timing.parquet",
            self.test_dir / "minimal_audit", player_match_base_parquet=self.base_pq,
        )
        self.assertEqual(audit["valid_absolute_events"], 1)
        self.assertEqual(audit["victim_field_audit_status"], "column_unavailable")
        self.assertEqual(audit["self_kill_audit_status"], "column_unavailable")
        self.assertEqual(audit["victim_roster_audit_status"], "column_unavailable")
        self.assertEqual(audit["environment_cause_audit_status"], "column_unavailable")

    def test_null_source_values_are_partial_lineage_not_verified(self):
        partial = pd.DataFrame([
            {"match_id": "m1", "time": 10.0, "killer_name": "P_Normal", "source_file": "a.csv", "source_row": 1},
            {"match_id": "m1", "time": 20.0, "killer_name": "P_Normal", "source_file": None, "source_row": None},
        ])
        path = self.test_dir / "partial_lineage.parquet"
        partial.to_parquet(path, index=False)
        audit_dir = self.test_dir / "partial_lineage_audit"
        audit = extract_and_aggregate_combat_timing(
            self.con, [path], self.meta_pq, self.test_dir / "partial_lineage_timing.parquet", audit_dir,
        )
        self.assertEqual(audit["event_identity_status"], "partial_source_lineage_pending")
        self.assertEqual(audit["missing_source_lineage_events"], 1)
        ledger = pd.read_parquet(audit_dir / "event_validation_ledger.parquet")
        self.assertEqual(ledger["flag_missing_source_lineage"].sum(), 1)
        self.assertTrue(ledger.loc[ledger["flag_missing_source_lineage"] == 1, "event_source_key"].iloc[0].startswith("pending_unverified_row:"))

    def test_duplicate_source_identity_is_preserved_and_pending(self):
        duplicate_identity = pd.DataFrame([
            {"match_id": "m1", "time": 10.0, "killer_name": "P_Normal", "victim_name": "A", "source_file": "same.csv", "source_row": 7},
            {"match_id": "m1", "time": 20.0, "killer_name": "P_Normal", "victim_name": "B", "source_file": "same.csv", "source_row": 7},
        ])
        path = self.test_dir / "duplicate_identity.parquet"
        duplicate_identity.to_parquet(path, index=False)
        audit_dir = self.test_dir / "duplicate_identity_audit"
        timing_path = self.test_dir / "duplicate_identity_timing.parquet"
        audit = extract_and_aggregate_combat_timing(
            self.con, [path], self.meta_pq, timing_path, audit_dir,
        )
        self.assertEqual(audit["event_identity_status"], "source_lineage_conflict_pending")
        self.assertEqual(audit["duplicate_source_identity_events"], 2)
        self.assertEqual(len(pd.read_parquet(audit_dir / "event_validation_ledger.parquet")), 2)
        self.assertEqual(pd.read_parquet(timing_path)["event_kill_count"].iloc[0], 2)

    def test_metadata_duplicate_check_uses_canonical_trimmed_match_id(self):
        metadata = pd.DataFrame([
            {"match_id": "m1", "estimated_match_duration": 600.0},
            {"match_id": " m1", "estimated_match_duration": 600.0},
        ])
        path = self.test_dir / "duplicate_canonical_metadata.parquet"
        metadata.to_parquet(path, index=False)
        with self.assertRaisesRegex(ValueError, "one row per match_id"):
            extract_and_aggregate_combat_timing(
                self.con, [self.deaths_pq], path, self.test_dir / "unused.parquet",
                self.test_dir / "unused_audit",
            )

    def test_research_gate_requires_status_and_evidence(self):
        pending = evaluate_combat_timing_research_gate({"combat_timing": {}})
        self.assertFalse(pending["ready"])
        self.assertEqual(pending["reason_code"], "RUN-04")
        null_evidence = evaluate_combat_timing_research_gate({"combat_timing": {
            "event_time_unit_status": "verified",
            "event_time_unit_evidence": None,
            "enemy_kill_eligibility_status": "verified",
            "enemy_kill_eligibility_evidence": False,
            "min_valid_duration_status": "verified",
            "min_valid_duration_evidence": "fixture threshold contract",
        }})
        self.assertFalse(null_evidence["ready"])
        self.assertEqual(null_evidence["reason_code"], "RUN-04")
        verified = evaluate_combat_timing_research_gate({"combat_timing": {
            "event_time_unit_status": "verified",
            "event_time_unit_evidence": "fixture schema contract",
            "enemy_kill_eligibility_status": "verified",
            "enemy_kill_eligibility_evidence": "fixture roster contract",
            "min_valid_duration_status": "verified",
            "min_valid_duration_evidence": "fixture threshold contract",
        }})
        self.assertTrue(verified["ready"])

    def test_enemy_verified_audit_requires_evidence(self):
        audit = extract_and_aggregate_combat_timing(
            self.con, [self.deaths_pq], self.meta_pq,
            self.test_dir / "enemy_gate_timing.parquet", self.test_dir / "enemy_gate_audit",
            features_config={"combat_timing": {"enemy_kill_eligibility_status": "verified"}},
        )
        self.assertFalse(audit["enemy_kill_eligibility_verified"])

    def test_registry_preserves_pending_units_and_duration_lineage(self):
        registry = FeatureRegistry()
        first = registry.get("first_kill_time")
        early = registry.get("early_kills")
        self.assertIn("pending", first.unit)
        self.assertIn("enemy eligibility is pending", registry.get("event_kill_count").description)
        self.assertIn("estimated_match_duration", early.depends_on)
        self.assertTrue(early.requires_survival)
        self.assertIn("survival", early.forbidden_targets)


class TestNotebook04Execution(unittest.TestCase):
    def test_actual_notebook_04_runs_with_scientific_outputs(self):
        root = Path(__file__).resolve().parent.parent
        notebook = root / "notebooks" / "04_combat_timing.ipynb"
        document = json.loads(notebook.read_text(encoding="utf-8"))
        markdown = "\n".join(
            "".join(cell["source"])
            for cell in document["cells"]
            if cell["cell_type"] == "markdown"
        )
        for marker in (
            "victim_name", "pending_real_data_evidence", "Event ledger",
            "many-to-one", "aggregate_kill_event_missing", "mẫu số player-match", "không phải Gate G4",
        ):
            self.assertIn(marker, markdown)

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            program = r'''import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
nb = json.load(open(sys.argv[1], encoding="utf-8"))
scope = {"PUBG_INSTALL_DEPENDENCIES": False, "__name__": "__main__"}
for index, cell in enumerate(nb["cells"]):
    if cell["cell_type"] != "code":
        continue
    exec(compile("".join(cell["source"]), f"{sys.argv[1]}-cell-{index}", "exec"), scope)
    tags = cell.get("metadata", {}).get("tags", [])
    if "storage-options" in tags:
        scope.update(PUBG_STORAGE_MODE="runtime", PUBG_REQUIRE_EXISTING_PROJECT=False)
    if "bootstrap" in tags:
        import pandas as pd
        from src.data.io import atomic_write_parquet
        from src.data.checkpoints import CheckpointManager
        paths = scope["paths"]
        staging = paths["interim"] / "staging_shards"
        staging.mkdir(parents=True, exist_ok=True)
        base = paths["interim"] / "player_match_base.parquet"
        meta = paths["interim"] / "match_metadata.parquet"
        death = staging / "kill_fixture.parquet"
        base_rows = [
            {"row_id": "r1", "match_id": "m1", "player_name": "A", "team_id": "t1", "date": "2017-11-01", "match_mode": "squad", "party_size": 4, "perspective_mode": "tpp", "team_size_mode": "squad", "observed_team_count": 2, "estimated_match_duration": 600.0, "player_kills": 2, "player_dmg": 200.0, "player_dist_walk": 1000.0, "player_dist_ride": 0.0, "player_assists": 1, "player_dbno": 1, "player_survive_time": 600.0, "team_placement": 1, "normalized_placement": 1.0, "valid_placement": True, "placement_validity_flag": "VALID", "damage_per_kill": 100.0, "total_distance": 1000.0, "walk_ratio": 1.0, "assist_ratio": 1/3},
            {"row_id": "r2", "match_id": "m1", "player_name": "B", "team_id": "t2", "date": "2017-11-01", "match_mode": "squad", "party_size": 4, "perspective_mode": "tpp", "team_size_mode": "squad", "observed_team_count": 2, "estimated_match_duration": 600.0, "player_kills": 0, "player_dmg": 0.0, "player_dist_walk": 100.0, "player_dist_ride": 0.0, "player_assists": 0, "player_dbno": 0, "player_survive_time": 300.0, "team_placement": 2, "normalized_placement": 0.0, "valid_placement": True, "placement_validity_flag": "VALID", "damage_per_kill": None, "total_distance": 100.0, "walk_ratio": 1.0, "assist_ratio": None},
            {"row_id": "r3", "match_id": "m1", "player_name": "C", "team_id": "t2", "date": "2017-11-01", "match_mode": "squad", "party_size": 4, "perspective_mode": "tpp", "team_size_mode": "squad", "observed_team_count": 2, "estimated_match_duration": 600.0, "player_kills": 1, "player_dmg": 90.0, "player_dist_walk": 400.0, "player_dist_ride": 0.0, "player_assists": 0, "player_dbno": 0, "player_survive_time": 350.0, "team_placement": 2, "normalized_placement": 0.0, "valid_placement": True, "placement_validity_flag": "VALID", "damage_per_kill": 90.0, "total_distance": 400.0, "walk_ratio": 1.0, "assist_ratio": 0.0},
            {"row_id": "r4", "match_id": "m2", "player_name": "D", "team_id": "t1", "date": "2017-11-02", "match_mode": "solo", "party_size": 1, "perspective_mode": "tpp", "team_size_mode": "solo", "observed_team_count": 2, "estimated_match_duration": 45.0, "player_kills": 1, "player_dmg": 100.0, "player_dist_walk": 50.0, "player_dist_ride": 0.0, "player_assists": 0, "player_dbno": 0, "player_survive_time": 45.0, "team_placement": 1, "normalized_placement": 1.0, "valid_placement": True, "placement_validity_flag": "VALID", "damage_per_kill": 100.0, "total_distance": 50.0, "walk_ratio": 1.0, "assist_ratio": 0.0},
        ]
        meta_rows = [
            {"match_id": "m1", "estimated_match_duration": 600.0, "observed_team_count": 2, "match_mode": "squad", "party_size": 4},
            {"match_id": "m2", "estimated_match_duration": 45.0, "observed_team_count": 2, "match_mode": "solo", "party_size": 1},
        ]
        event_rows = [
            {"source_file": "fixture.csv", "source_row": 1, "match_id": "m1", "time": 100.0, "killer_name": "A", "victim_name": "B", "killed_by": "M416"},
            {"source_file": "fixture.csv", "source_row": 2, "match_id": "m1", "time": 100.0, "killer_name": "A", "victim_name": "C", "killed_by": "M416"},
            {"source_file": "fixture.csv", "source_row": 3, "match_id": "m1", "time": 650.0, "killer_name": "C", "victim_name": None, "killed_by": None},
            {"source_file": "fixture.csv", "source_row": 4, "match_id": "m2", "time": 20.0, "killer_name": "D", "victim_name": "X", "killed_by": "M416"},
            {"source_file": "fixture.csv", "source_row": 5, "match_id": "m1", "time": 200.0, "killer_name": "B", "victim_name": "B", "killed_by": "Falling"},
            {"source_file": "fixture.csv", "source_row": 6, "match_id": "missing", "time": 50.0, "killer_name": "Ghost", "victim_name": "A", "killed_by": "M416"},
        ]
        atomic_write_parquet(base, pd.DataFrame(base_rows))
        atomic_write_parquet(meta, pd.DataFrame(meta_rows))
        atomic_write_parquet(death, pd.DataFrame(event_rows))
        checkpoints = CheckpointManager(paths["checkpoints"] / "checkpoint_manifest.json")
        checkpoints.commit("notebook/01_download_validate.ipynb", "fixture-g1", {"deaths": death})
        checkpoints.commit("notebook/03_build_player_match.ipynb", "fixture-g3", {"base": base})
        if sys.argv[2] == "verified":
            import yaml
            config_path = scope["PROJECT_ROOT"] / "configs" / "features.yaml"
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            timing = config["combat_timing"]
            timing.update({
                "event_time_unit_status": "verified",
                "event_time_unit_evidence": "temporary fixture schema contract",
                "enemy_kill_eligibility_status": "verified",
                "enemy_kill_eligibility_evidence": "temporary fixture roster contract",
                "min_valid_duration_status": "verified",
                "min_valid_duration_evidence": "temporary fixture threshold contract",
            })
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
'''
            pending_workspace = workspace / "pending"
            pending_workspace.mkdir()
            pending_run = subprocess.run(
                [sys.executable, "-c", program, str(notebook), "pending"],
                cwd=pending_workspace,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
            self.assertNotEqual(pending_run.returncode, 0)
            self.assertIn("RUN-04", pending_run.stdout + pending_run.stderr)
            pending_project = next(pending_workspace.rglob("checkpoint_manifest.json")).parents[2]
            pending_manifest = json.loads(next(pending_project.rglob("checkpoint_manifest.json")).read_text(encoding="utf-8"))
            self.assertEqual(pending_manifest["stages"]["notebook/04_combat_timing.ipynb"]["status"], "blocked")
            self.assertEqual(pending_manifest["stages"]["notebook/04_combat_timing.ipynb"]["reason_code"], "RUN-04")
            self.assertEqual(pending_manifest["stages"]["combat_timing_diagnostics"]["status"], "completed")
            self.assertFalse(any(pending_project.rglob("player_match_features.parquet")))

            verified_workspace = workspace / "verified"
            verified_workspace.mkdir()
            run = subprocess.run(
                [sys.executable, "-c", program, str(notebook), "verified"],
                cwd=verified_workspace,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            for marker in (
                "BẢNG 04-A", "BẢNG 04-B", "BẢNG 04-C", "BẢNG 04-D",
                "BẢNG 04-E", "BẢNG 04-F", "BẢNG 04-G", "BẢNG 04-H",
                "BẢNG 04-I", "BẢNG 04-J", "BẢNG 04-K", "BẢNG 04-L",
                "BẢNG 04-M", "HÌNH V04-01", "HÌNH V04-02", "HÌNH V04-03",
                "không gọi đây là Gate G4",
            ):
                self.assertIn(marker, run.stdout)

            project = next(verified_workspace.rglob("player_match_features.parquet")).parents[2]
            final = pd.read_parquet(next(project.rglob("player_match_features.parquet")))
            discrepancy = pd.read_csv(next(project.rglob("kill_discrepancy.csv")))
            audit = pd.read_csv(next(project.rglob("event_join_audit.csv"))).iloc[0]
            checkpoints = json.loads(next(project.rglob("checkpoint_manifest.json")).read_text(encoding="utf-8"))
            self.assertEqual(len(final), 4)
            self.assertEqual(len(discrepancy), 4)
            self.assertEqual(audit["event_time_unit_status"], "verified")
            self.assertEqual(audit["enemy_kill_eligibility_status"], "verified")
            self.assertEqual(audit["valid_absolute_events"], 4)
            self.assertEqual(audit["valid_phase_events"], 2)
            stage = checkpoints["stages"]["notebook/04_combat_timing.ipynb"]
            self.assertEqual(stage["status"], "completed")
            self.assertEqual(len(stage["artifacts"]), 9)
            for name in (
                "nb04_absolute_timing_distribution.png",
                "nb04_phase_event_counts.png",
                "nb04_player_match_coverage.png",
            ):
                image = next(project.rglob(name))
                self.assertEqual(image.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
