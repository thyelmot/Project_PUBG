"""Unit tests for Section 20 Phase C: Historical Features, Gate G7, and Leakage Auditing."""
import unittest
import tempfile
from pathlib import Path
import duckdb
import pandas as pd
import numpy as np

from src.features.historical import (
    build_historical_features,
    compute_history_depth_diagnostics,
    audit_historical_leakage,
)
from src.models.registry import create_canonical_experiment_matrix
from src.data.checkpoints import CheckpointManager


class TestPhaseCHistorical(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.con = duckdb.connect()

        # Create synthetic fixture with multiple days and players
        # Player 1 has 2 matches on Day 1, 1 match on Day 2, 1 match on Day 3
        # Player 2 has 1 match on Day 1 only (cold start on Day 1)
        data = {
            "match_id": ["m1", "m2", "m3", "m4", "m5"],
            "player_name": ["p1", "p1", "p1", "p2", "p1"],
            "team_id": ["t1", "t1", "t1", "t2", "t1"],
            "date": [
                "2017-10-01T10:00:00+0000", # p1 Day 1, match 1 (kills=2, dmg=200)
                "2017-10-01T15:00:00+0000", # p1 Day 1, match 2 (kills=4, dmg=400)
                "2017-10-02T12:00:00+0000", # p1 Day 2, match 3 (kills=6, dmg=600)
                "2017-10-01T10:00:00+0000", # p2 Day 1, match 1 (kills=0, dmg=50)
                "2017-10-03T18:00:00+0000", # p1 Day 3, match 4 (kills=8, dmg=800)
            ],
            "player_kills": [2, 4, 6, 0, 8],
            "player_dmg": [200.0, 400.0, 600.0, 50.0, 800.0],
            "player_dist_walk": [100.0, 200.0, 300.0, 50.0, 400.0],
            "player_dist_ride": [0.0, 500.0, 0.0, 0.0, 1000.0],
            "player_assists": [0, 1, 2, 0, 1],
            "player_dbno": [1, 2, 3, 0, 2],
            "player_survive_time": [500.0, 1000.0, 1200.0, 300.0, 1500.0],
            "normalized_placement": [0.3, 0.6, 0.8, 0.1, 0.95],
        }
        self.df = pd.DataFrame(data)
        self.source_pq = self.root / "player_match_features.parquet"
        self.df.to_parquet(self.source_pq, index=False)

    def tearDown(self):
        self.con.close()
        self.temp_dir.cleanup()

    def test_strict_previous_days_window(self):
        """Test that matches on day D strictly use only matches from days < D."""
        out_pq = self.root / "hist_strict_prev.parquet"
        res = build_historical_features(
            self.con,
            self.source_pq,
            out_pq,
            chronology_grade="Grade B",
            min_history_threshold=1,
        )
        self.assertEqual(res["status"], "completed")

        hist_df = pd.read_parquet(out_pq).sort_values(by=["player_name", "date"]).reset_index(drop=True)

        # For p1:
        p1_df = hist_df[hist_df["player_name"] == "p1"].reset_index(drop=True)
        # Day 1 match 1 (m1): 0 prior days
        self.assertEqual(p1_df.loc[0, "hist_games_played"], 0)
        self.assertTrue(pd.isna(p1_df.loc[0, "hist_kills_mean"]))
        # Day 1 match 2 (m2): same day as m1 -> 0 prior days! Zero same-day leakage!
        self.assertEqual(p1_df.loc[1, "hist_games_played"], 0)
        self.assertTrue(pd.isna(p1_df.loc[1, "hist_kills_mean"]))
        # Day 2 match 3 (m3): prior day is Day 1 (m1 and m2, total 2 matches)
        self.assertEqual(p1_df.loc[2, "hist_games_played"], 2)
        # Mean kills: (2 + 4) / 2 = 3.0
        self.assertAlmostEqual(p1_df.loc[2, "hist_kills_mean"], 3.0)
        # Mean damage: (200 + 400) / 2 = 300.0
        self.assertAlmostEqual(p1_df.loc[2, "hist_dmg_mean"], 300.0)

        # Day 3 match 4 (m5): prior days are Day 1 (m1, m2) and Day 2 (m3), total 3 matches
        self.assertEqual(p1_df.loc[3, "hist_games_played"], 3)
        # Mean kills: (2 + 4 + 6) / 3 = 4.0
        self.assertAlmostEqual(p1_df.loc[3, "hist_kills_mean"], 4.0)

    def test_cold_start_means_are_nan_not_zero(self):
        """Test that players with 0 prior history have mean = NaN, not 0.0."""
        out_pq = self.root / "hist_cold_start.parquet"
        build_historical_features(
            self.con,
            self.source_pq,
            out_pq,
            chronology_grade="Grade B",
            min_history_threshold=1,
        )
        hist_df = pd.read_parquet(out_pq)
        cold_start_rows = hist_df[hist_df["hist_games_played"] == 0]
        self.assertGreater(len(cold_start_rows), 0)
        for _, row in cold_start_rows.iterrows():
            self.assertTrue(pd.isna(row["hist_kills_mean"]))
            self.assertTrue(pd.isna(row["hist_dmg_mean"]))
            self.assertTrue(pd.isna(row["hist_survive_mean"]))
            self.assertTrue(pd.isna(row["hist_placement_mean"]))

    def test_gate_g7_when_threshold_is_none(self):
        """Test that when min_history_threshold is None, diagnostics are run and Gate G7 is pending."""
        out_pq = self.root / "hist_gate_g7.parquet"
        cov_csv = self.root / "history_coverage.csv"
        audit_csv = self.root / "leakage_audit.csv"

        res = build_historical_features(
            self.con,
            self.source_pq,
            out_pq,
            chronology_grade="Grade B",
            min_history_threshold=None,
            coverage_table_path=cov_csv,
            leakage_audit_path=audit_csv,
        )
        self.assertEqual(res["gate_status"], "G7_PENDING")
        self.assertTrue(cov_csv.is_file())
        self.assertTrue(audit_csv.is_file())

        cov_df = pd.read_csv(cov_csv)
        self.assertIn("threshold", cov_df.columns)
        self.assertIn("eligible_rows", cov_df.columns)

    def test_grade_c_blocking_and_manifest_recording(self):
        """Test that Chronology Grade C safely blocks S2 and P3 tasks in registry and checkpoints."""
        out_pq = self.root / "hist_grade_c.parquet"
        manifest_path = self.root / "checkpoint_manifest.json"
        reg = create_canonical_experiment_matrix()
        ckpt_mgr = CheckpointManager(manifest_path=manifest_path)

        res = build_historical_features(
            self.con,
            self.source_pq,
            out_pq,
            chronology_grade="Grade C",
            min_history_threshold=2,
            checkpoint_mgr=ckpt_mgr,
            registry=reg,
        )

        self.assertEqual(res["status"], "blocked")
        self.assertEqual(res["reason_code"], "blocked_by_chronology")
        self.assertTrue(out_pq.is_file())  # Feasibility dataset is still generated for audit

        # Verify registry tasks updated to blocked
        s2 = reg.get("s2_historical_survival")
        p3 = reg.get("p3_historical_placement")
        self.assertEqual(s2.status, "blocked")
        self.assertEqual(s2.reason_code, "blocked_by_chronology")
        self.assertEqual(p3.status, "blocked")
        self.assertEqual(p3.reason_code, "blocked_by_chronology")

        # Verify checkpoints manifest recorded blocked stages
        manifest = ckpt_mgr.load_manifest()
        self.assertEqual(manifest["stages"]["s2_historical_survival"]["status"], "blocked")
        self.assertEqual(manifest["stages"]["p3_historical_placement"]["status"], "blocked")

    def test_leakage_audit_clean_pass(self):
        """Test that audit_historical_leakage reports 0 leakage violations."""
        out_pq = self.root / "hist_leakage_audit.parquet"
        audit_csv = self.root / "audit_result.csv"
        build_historical_features(
            self.con,
            self.source_pq,
            out_pq,
            chronology_grade="Grade B",
            min_history_threshold=1,
            leakage_audit_path=audit_csv,
        )
        audit_df = pd.read_csv(audit_csv)
        self.assertEqual(audit_df.loc[0, "audit_status"], "PASSED")
        self.assertEqual(audit_df.loc[0, "leakage_count"], 0)


if __name__ == "__main__":
    unittest.main()
