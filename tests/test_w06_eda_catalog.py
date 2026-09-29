import shutil
import tempfile
import unittest
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd

from src.analysis.eda import (
    compute_distribution_summary,
    compute_sql_distribution_summary,
    run_structural_eda,
    compute_player_retention_diagnostics,
    compute_combat_phase_by_placement_tier,
    analyze_parquet_distributions,
)
from src.analysis.mode_analysis import analyze_behavior_by_mode, format_mode_differences_table


class TestW06EDACatalog(unittest.TestCase):
    """Tests for W06 (Phase X - Notebook 05): Full EDA Catalog A01-I03."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.con = duckdb.connect(database=":memory:")

        # Create mock player_match_features dataset with known properties across Solo, Duo, Squad
        records = []
        # Solo players (party_size=1, team_size_mode='solo', 0 assists, high kills)
        for i in range(25):
            records.append({
                "match_id": f"m_solo_{i % 5}",
                "player_name": f"P_Solo_{i % 10}",
                "team_id": f"t_{i}",
                "team_size_mode": "solo",
                "party_size": 1,
                "player_kills": i % 6,
                "player_dmg": float((i % 6) * 105.0),
                "damage_per_kill": 105.0 if (i % 6) > 0 else np.nan,
                "player_dist_walk": 1000.0 + i * 20.0,
                "player_dist_ride": 500.0 if i % 2 == 0 else 0.0,
                "total_distance": 1000.0 + i * 20.0 + (500.0 if i % 2 == 0 else 0.0),
                "walk_ratio": 1.0 if i % 2 != 0 else (1000.0 + i * 20.0) / (1500.0 + i * 20.0),
                "player_assists": 0,
                "player_dbno": 0,
                "assist_ratio": 0.0 if (i % 6) > 0 else np.nan,
                "player_survive_time": 200.0 + i * 40.0,
                "team_placement": (i % 10) + 1,
                "normalized_placement": 1.0 - (i % 10) / 10.0,
                "placement_validity_flag": "VALID",
                "event_kill_count": i % 6,
                "first_kill_time": 120.0 if (i % 6) > 0 else np.nan,
                "avg_kill_time": 250.0 if (i % 6) > 0 else np.nan,
                "early_kills": 1 if (i % 6) > 0 else 0,
                "mid_kills": (i % 6) - 1 if (i % 6) > 1 else 0,
                "late_kills": 0,
                "early_kill_ratio": 1.0 / (i % 6) if (i % 6) > 0 else np.nan,
                "mid_kill_ratio": ((i % 6) - 1.0) / (i % 6) if (i % 6) > 1 else (0.0 if (i % 6) == 1 else np.nan),
                "late_kill_ratio": 0.0 if (i % 6) > 0 else np.nan,
                "has_kill": (i % 6) > 0,
            })

        # Squad players (party_size=4, team_size_mode='squad', high assists & DBNO)
        for i in range(35):
            records.append({
                "match_id": f"m_squad_{i % 5}",
                "player_name": f"P_Squad_{i % 15}",
                "team_id": f"t_sq_{i // 4}",
                "team_size_mode": "squad",
                "party_size": 4,
                "player_kills": i % 4,
                "player_dmg": float((i % 4) * 90.0 + 50.0),
                "damage_per_kill": (float((i % 4) * 90.0 + 50.0) / (i % 4)) if (i % 4) > 0 else np.nan,
                "player_dist_walk": 800.0 + i * 30.0,
                "player_dist_ride": 800.0 if i % 2 == 0 else 100.0,
                "total_distance": 800.0 + i * 30.0 + (800.0 if i % 2 == 0 else 100.0),
                "walk_ratio": (800.0 + i * 30.0) / (800.0 + i * 30.0 + (800.0 if i % 2 == 0 else 100.0)),
                "player_assists": (i % 3) + 1,  # Assists are consistently > 0
                "player_dbno": (i % 4) + 1,     # DBNO is consistently > 0
                "assist_ratio": float((i % 3) + 1) / float((i % 3) + 1 + (i % 4)),
                "player_survive_time": 400.0 + i * 30.0,
                "team_placement": (i % 8) + 1,
                "normalized_placement": 1.0 - (i % 8) / 8.0,
                "placement_validity_flag": "VALID",
                "event_kill_count": i % 4,
                "first_kill_time": 180.0 if (i % 4) > 0 else np.nan,
                "avg_kill_time": 350.0 if (i % 4) > 0 else np.nan,
                "early_kills": 0,
                "mid_kills": 1 if (i % 4) > 0 else 0,
                "late_kills": (i % 4) - 1 if (i % 4) > 1 else 0,
                "early_kill_ratio": 0.0 if (i % 4) > 0 else np.nan,
                "mid_kill_ratio": 1.0 / (i % 4) if (i % 4) > 0 else np.nan,
                "late_kill_ratio": ((i % 4) - 1.0) / (i % 4) if (i % 4) > 1 else (0.0 if (i % 4) == 1 else np.nan),
                "has_kill": (i % 4) > 0,
            })

        self.df = pd.DataFrame(records)
        self.pq_path = self.test_dir / "player_match_features.parquet"
        self.df.to_parquet(self.pq_path, index=False)

    def tearDown(self):
        self.con.close()
        shutil.rmtree(self.test_dir)

    def test_distribution_summary_in_memory_and_sql(self):
        """Verify that in-memory and SQL distribution summaries yield consistent results."""
        cols = ["player_kills", "player_dmg", "player_dist_walk", "normalized_placement"]

        df_mem = compute_distribution_summary(self.df, cols)
        self.assertEqual(len(df_mem), 4)
        kills_mem = df_mem[df_mem["feature"] == "player_kills"].iloc[0]
        self.assertAlmostEqual(kills_mem["mean"], self.df["player_kills"].mean(), places=3)
        self.assertAlmostEqual(kills_mem["median"], self.df["player_kills"].median(), places=3)

        # SQL streaming on DuckDB
        df_sql = compute_sql_distribution_summary(self.con, self.pq_path, cols)
        self.assertEqual(len(df_sql), 4)
        kills_sql = df_sql[df_sql["feature"] == "player_kills"].iloc[0]
        self.assertAlmostEqual(kills_sql["mean"], self.df["player_kills"].mean(), places=3)
        self.assertAlmostEqual(kills_sql["min"], self.df["player_kills"].min(), places=3)
        self.assertAlmostEqual(kills_sql["max"], self.df["player_kills"].max(), places=3)

    def test_mode_analysis_computes_effect_sizes_and_n(self):
        """Verify that mode analysis computes Kruskal-Wallis H, N, and effect size eta^2."""
        res = analyze_behavior_by_mode(self.df, ["player_assists", "player_dbno"], mode_col="team_size_mode")

        self.assertIn("mode_differences", res)
        diff_table = format_mode_differences_table(res["mode_differences"])
        self.assertEqual(len(diff_table), 2)

        # Assists differ substantially between Solo (all 0) and Squad (>0)
        assists_diff = res["mode_differences"]["player_assists"]
        self.assertTrue(assists_diff["is_significant"])
        self.assertTrue(assists_diff["effect_size_eta_sq"] > 0.14)  # Large effect size
        self.assertEqual(assists_diff["effect_magnitude"], "large")
        self.assertEqual(assists_diff["n_observations"], 60)

        # Recommendation should be per_mode
        self.assertEqual(res["recommended_rq2_strategy"], "per_mode")

    def test_combat_phase_by_placement_tier(self):
        """Verify computation of combat phase ratios across placement tiers (Chart H06)."""
        df_h06 = compute_combat_phase_by_placement_tier(self.con, self.pq_path)
        self.assertTrue(len(df_h06) > 0)
        self.assertIn("placement_tier", df_h06.columns)
        self.assertIn("avg_early_ratio", df_h06.columns)
        self.assertIn("avg_mid_ratio", df_h06.columns)
        self.assertIn("avg_late_ratio", df_h06.columns)

    def test_player_retention_diagnostics(self):
        """Verify candidate retention thresholds 1, 5, 10, 20, 50 (Chart A02 / I01)."""
        retention_df = compute_player_retention_diagnostics(
            self.con, self.pq_path, thresholds=[1, 2, 5, 10]
        )
        self.assertEqual(len(retention_df), 4)
        self.assertIn("threshold", retention_df.columns)
        self.assertIn("eligible_players", retention_df.columns)
        self.assertIn("player_retention_pct", retention_df.columns)
        # Threshold 1 retention should be 100%
        thresh_1 = retention_df[retention_df["threshold"] == 1].iloc[0]
        self.assertEqual(thresh_1["player_retention_pct"], 100.0)

    def test_analyze_parquet_distributions_integration(self):
        """Verify full pipeline of analyze_parquet_distributions."""
        dist_df, mode_res = analyze_parquet_distributions(
            self.pq_path, ["player_assists", "player_dbno"]
        )
        self.assertEqual(len(dist_df), 2)
        self.assertIn("summary_table", mode_res)
        self.assertIn("mode_differences", mode_res)
        self.assertEqual(mode_res["recommended_rq2_strategy"], "per_mode")


    def test_eda_config_covers_catalog_a01_to_i03(self):
        """Verify that configs/eda.yaml covers all 9 groups from A01 to I03 per spec."""
        import yaml
        config_path = Path("configs/eda.yaml")
        self.assertTrue(config_path.exists())
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        catalog = cfg.get("catalog", {})
        expected_groups = [
            "structural", "raw_distributions", "derived_ratios", "mode_comparison",
            "correlation", "behavior_vs_survival", "behavior_vs_placement",
            "combat_timing", "historical"
        ]
        for grp in expected_groups:
            self.assertIn(grp, catalog, f"Group '{grp}' must be in eda.yaml catalog")

        # Collect all chart IDs
        all_ids = set()
        for grp, charts in catalog.items():
            for c in charts:
                all_ids.add(c["id"])

        # Check key IDs
        for expected_id in ["A01", "A06", "B01", "B10", "C01", "C06", "D01", "D08", "E01", "E02", "F01", "G01", "H01", "H06", "I01", "I03"]:
            self.assertIn(expected_id, all_ids, f"Expected chart ID '{expected_id}' not found in catalog")

    def test_vif_calculation_and_collinearity_handling(self):
        """Verify VIF calculation on numerical predictors, correctly flagging multicollinearity."""
        from src.analysis.correlation import compute_vif_summary

        # Add collinear predictor: total_dist = walk + ride
        vif_df = compute_vif_summary(
            self.df,
            ["player_dist_walk", "player_dist_ride", "total_distance", "player_kills"]
        )
        self.assertIn("vif", vif_df.columns)
        self.assertIn("tolerance", vif_df.columns)
        self.assertIn("multicollinearity_severity", vif_df.columns)

        # total_distance is exactly walk + ride -> extreme multicollinearity
        total_dist_row = vif_df[vif_df["feature"] == "total_distance"].iloc[0]
        self.assertEqual(total_dist_row["multicollinearity_severity"], "extreme")

        # Non-collinear features should have low or moderate VIF
        vif_noncollinear = compute_vif_summary(
            self.df,
            ["player_dist_walk", "player_kills"]
        )
        for _, row in vif_noncollinear.iterrows():
            self.assertTrue(np.isfinite(row["vif"]))
            self.assertIn(row["multicollinearity_severity"], ["low", "moderate"])

    def test_format_mode_differences_table_effect_size_columns(self):
        """Verify format_mode_differences_table populates valid effect size values."""
        res = analyze_behavior_by_mode(self.df, ["player_assists", "player_dbno"], mode_col="team_size_mode")
        table = format_mode_differences_table(res["mode_differences"])

        self.assertIn("effect_size_eta_sq", table.columns)
        self.assertIn("effect_size_eta_squared", table.columns)
        self.assertIn("effect_magnitude", table.columns)
        self.assertIn("effect_size_magnitude", table.columns)

        for _, row in table.iterrows():
            self.assertFalse(np.isnan(row["effect_size_eta_sq"]))
            self.assertFalse(np.isnan(row["effect_size_eta_squared"]))
            self.assertNotEqual(row["effect_magnitude"], "unknown")
            self.assertNotEqual(row["effect_size_magnitude"], "unknown")


if __name__ == "__main__":
    unittest.main()
