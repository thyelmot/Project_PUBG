import shutil
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

from src.analysis.rq1 import run_rq1_analysis, generate_rq1_interpretations, classify_correlation_strength
from src.features.registry import FeatureRegistry


class TestW07RQ1Bivariate(unittest.TestCase):
    """Tests for W07 (Phase XI - Notebook 06): RQ1 Bivariate Analysis & Task Allowlists."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.registry = FeatureRegistry()

        # Build mock dataset with clear relationships:
        # - walk distance strongly positively correlates with survival and placement
        # - kills correlates with damage and placement
        # - Solo, Duo, Squad modes
        np.random.seed(42)
        n = 120

        records = []
        for i in range(n):
            mode = "solo" if i < 40 else "duo" if i < 80 else "squad"
            party_size = 1 if mode == "solo" else 2 if mode == "duo" else 4
            surv = 100.0 + i * 15.0 + np.random.normal(0, 10)
            walk = surv * 1.5 + np.random.normal(0, 20)
            kills = int(np.random.poisson(lam=max(0.5, surv / 500.0)))
            dmg = float(kills * 100.0 + np.random.uniform(0, 50))
            assists = 0 if mode == "solo" else int(np.random.poisson(lam=1.0))
            dbno = 0 if mode == "solo" else int(np.random.poisson(lam=1.2))
            placement = max(0.0, min(1.0, (surv - 100.0) / 1800.0))

            records.append({
                "match_id": f"m_{i // 10}",
                "player_name": f"P_{i}",
                "team_id": f"t_{i // 2}",
                "team_size_mode": mode,
                "party_size": party_size,
                "player_survive_time": surv,
                "normalized_placement": placement,
                "player_dist_walk": max(0.0, walk),
                "player_dist_ride": 0.0,
                "total_distance": max(0.0, walk),
                "walk_ratio": 1.0,
                "player_kills": kills,
                "player_dmg": dmg,
                "damage_per_kill": dmg / kills if kills > 0 else np.nan,
                "player_assists": assists,
                "player_dbno": dbno,
                "assist_ratio": assists / (assists + kills) if (assists + kills) > 0 else np.nan,
                "event_kill_count": kills,
                "first_kill_time": 100.0 if kills > 0 else np.nan,
                "avg_kill_time": 200.0 if kills > 0 else np.nan,
                "has_kill": kills > 0,
                "early_kills": kills if kills > 0 else 0,
                "mid_kills": 0,
                "late_kills": 0,
                "early_kill_ratio": 1.0 if kills > 0 else np.nan,
                "mid_kill_ratio": 0.0 if kills > 0 else np.nan,
                "late_kill_ratio": 0.0 if kills > 0 else np.nan,
                "kills_per_minute": (kills / (surv / 60.0)) if surv > 0 else np.nan,
                "damage_per_minute": (dmg / (surv / 60.0)) if surv > 0 else np.nan,
                "walk_velocity": (walk / surv) if surv > 0 else np.nan,
                "ride_velocity": 0.0,
            })

        self.df = pd.DataFrame(records)
        self.pq_path = self.test_dir / "player_match_features.parquet"
        self.df.to_parquet(self.pq_path, index=False)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_allowlist_enforcement_under_d01(self):
        """Verify D01: Survival MUST NOT use phase timing features as primary valid predictors."""
        out_csv = self.test_dir / "rq1_test.csv"
        rq1_df = run_rq1_analysis(self.df, self.registry, out_csv)

        self.assertFalse(rq1_df.empty)

        # Check Survival target
        surv_df = rq1_df[rq1_df["target"] == "player_survive_time"]

        # Phase timing features (early_kills, early_kill_ratio) MUST NOT be primary valid
        phase_rows = surv_df[surv_df["feature"].isin(["early_kills", "early_kill_ratio", "mid_kill_ratio", "late_kill_ratio"])]
        for _, row in phase_rows.iterrows():
            self.assertFalse(row["is_primary_valid"])
            self.assertTrue(row["target_derived"])

        # Target-derived diagnostics (kills_per_minute) MUST NOT be primary valid
        kpm_rows = surv_df[surv_df["feature"] == "kills_per_minute"]
        if not kpm_rows.empty:
            self.assertFalse(kpm_rows["is_primary_valid"].iloc[0])

        # Core combat/movement (player_kills, player_dist_walk) MUST be primary valid
        walk_rows = surv_df[surv_df["feature"] == "player_dist_walk"]
        self.assertTrue(walk_rows["is_primary_valid"].iloc[0])

    def test_mode_segmentation(self):
        """Verify that analysis computes statistics for Overall and individual modes."""
        out_csv = self.test_dir / "rq1_modes.csv"
        rq1_df = run_rq1_analysis(self.df, self.registry, out_csv, min_observations_per_mode=20)

        modes = set(rq1_df["mode"].unique())
        self.assertIn("Overall", modes)
        self.assertIn("Solo", modes)
        self.assertIn("Duo", modes)
        self.assertIn("Squad", modes)

        # In Solo, assists are constant 0 -> notes reflect zero variance
        solo_assists = rq1_df[(rq1_df["mode"] == "Solo") & (rq1_df["feature"] == "player_assists")]
        if not solo_assists.empty:
            self.assertTrue(pd.isna(solo_assists["pearson_r"].iloc[0]))
            self.assertIn("Constant", solo_assists["notes"].iloc[0])

    def test_interpretations_and_limitations(self):
        """Verify structured interpretations and methodology limitations generation."""
        out_csv = self.test_dir / "rq1_report.csv"
        out_json = self.test_dir / "rq1_interpretations.json"

        rq1_df = run_rq1_analysis(self.df, self.registry, out_csv)
        interp = generate_rq1_interpretations(rq1_df, output_json_path=out_json)

        self.assertIn("primary_findings", interp)
        self.assertIn("player_survive_time", interp["primary_findings"])
        self.assertIn("methodological_limitations", interp)
        self.assertTrue(len(interp["methodological_limitations"]) >= 4)
        self.assertTrue(out_json.exists())

    def test_strength_classification(self):
        """Verify standard scientific correlation magnitude classification."""
        self.assertEqual(classify_correlation_strength(0.05), "negligible")
        self.assertEqual(classify_correlation_strength(-0.25), "weak")
        self.assertEqual(classify_correlation_strength(0.42), "moderate")
        self.assertEqual(classify_correlation_strength(-0.75), "strong")
        self.assertEqual(classify_correlation_strength(np.nan), "unspecified")


if __name__ == "__main__":
    unittest.main()
