import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd

from src.analysis.eda import (
    compute_distribution_summary,
    compute_sql_distribution_summary,
    compute_sql_correlation_matrices,
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

    def test_sql_correlations_use_pairwise_n_and_average_ranks_for_ties(self):
        columns = ["player_kills", "player_dmg", "player_assists"]
        pearson, spearman, pair_n = compute_sql_correlation_matrices(self.con, self.pq_path, columns)
        expected = self.df[columns].corr(method="spearman")

        self.assertEqual(list(pearson.columns), columns)
        self.assertEqual(int(pair_n.loc["player_kills", "player_dmg"]), len(self.df))
        self.assertAlmostEqual(
            spearman.loc["player_kills", "player_assists"],
            expected.loc["player_kills", "player_assists"],
            places=10,
        )

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


class TestNotebook0506Execution(unittest.TestCase):
    def test_actual_notebooks_05_and_06_run_sequentially_on_fixture(self):
        root = Path(__file__).resolve().parent.parent
        notebook_05 = root / "notebooks" / "05_eda.ipynb"
        notebook_06 = root / "notebooks" / "06_rq1_analysis.ipynb"
        program = r'''import json, sys
from pathlib import Path
import pandas as pd
import yaml
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
        from src.data.io import atomic_write_parquet
        from src.data.checkpoints import CheckpointManager
        paths = scope["paths"]
        checkpoints = CheckpointManager(paths["checkpoints"] / "checkpoint_manifest.json")
        nb05 = checkpoints.load_manifest().get("stages", {}).get("notebook/05_eda.ipynb", {})
        if nb05.get("status") == "completed":
            continue
        runtime_path = scope["PROJECT_ROOT"] / "configs" / "runtime.yaml"
        runtime_cfg = yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
        runtime_cfg["mode"] = "development"
        runtime_path.write_text(yaml.safe_dump(runtime_cfg, sort_keys=False), encoding="utf-8")
        rows = []
        for i in range(180):
            mode = ("solo", "duo", "squad")[i % 3]
            kills = i % 5
            survive = 240.0 + i * 11.0
            walk = 300.0 + i * 17.0
            ride = float((i % 4) * 120)
            assists = 0 if mode == "solo" else i % 4
            total = walk + ride
            rows.append({
                "row_id": f"r{i}", "match_id": f"m{i // 15}", "player_name": f"p{i % 60}",
                "date": f"2017-11-{1 + i // 60:02d}",
                "team_id": f"t{i // 3}", "team_size_mode": mode.title(), "perspective_mode": "tpp",
                "party_size": {"solo": 1, "duo": 2, "squad": 4}[mode], "game_size": 72,
                "player_kills": kills, "player_dmg": float(kills * 80 + i % 7),
                "player_dist_walk": walk, "player_dist_ride": ride, "total_distance": total,
                "walk_ratio": walk / total, "player_assists": assists, "player_dbno": assists,
                "assist_ratio": assists / (assists + kills) if assists + kills else None,
                "damage_per_kill": (kills * 80 + i % 7) / kills if kills else None,
                "player_survive_time": survive, "kills_per_minute": kills / (survive / 60.0),
                "damage_per_minute": (kills * 80 + i % 7) / (survive / 60.0),
                "walk_velocity": walk / survive, "ride_velocity": ride / survive,
                "team_placement": i % 12 + 1, "normalized_placement": 1.0 - (i % 12) / 11.0,
                "valid_placement": True, "placement_validity_flag": "VALID",
                "event_kill_count": kills, "first_kill_time": 60.0 + i if kills else None,
                "avg_kill_time": 120.0 + i if kills else None,
                "early_kill_ratio": 1.0 / kills if kills else None,
                "mid_kill_ratio": (kills - 1.0) / kills if kills else None,
                "late_kill_ratio": 0.0 if kills else None, "has_kill": bool(kills),
            })
        final = paths["processed"] / "player_match_features.parquet"
        meta = paths["interim"] / "match_metadata.parquet"
        split = paths["interim"] / "split_assignments.parquet"
        atomic_write_parquet(final, pd.DataFrame(rows))
        atomic_write_parquet(meta, pd.DataFrame({"match_id": sorted({row["match_id"] for row in rows})}))
        match_ids = sorted({row["match_id"] for row in rows})
        atomic_write_parquet(split, pd.DataFrame({
            "match_id": match_ids,
            "split": ["train"] * 8 + ["validation"] * 2 + ["test"] * 2,
        }))
        checkpoints.commit("notebook/02_data_quality_and_structure.ipynb", "fixture-nb02", {"splits": split})
        checkpoints.commit(
            "notebook/04_combat_timing.ipynb", "fixture-nb04", {"features": final, "metadata": meta}
        )
'''
        with tempfile.TemporaryDirectory() as directory:
            run = subprocess.run(
                [sys.executable, "-c", program, str(notebook_05)],
                cwd=directory,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "MPLBACKEND": "Agg"},
                timeout=180,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("STAGE NB05 HOÀN TẤT TRONG SCOPE DEVELOPMENT", run.stdout)
            run_06 = subprocess.run(
                [sys.executable, "-c", program, str(notebook_06)],
                cwd=directory,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "MPLBACKEND": "Agg"},
                timeout=180,
            )
            self.assertEqual(run_06.returncode, 0, run_06.stdout + run_06.stderr)
            self.assertIn("STAGE NB06 HOÀN TẤT TRONG SCOPE DEVELOPMENT", run_06.stdout)
            project = next(Path(directory).rglob("eda_structural_overview.csv")).parents[2]
            pair_n = pd.read_csv(next(project.rglob("eda_correlation_pair_n.csv")))
            self.assertIn("feature", pair_n.columns)
            self.assertTrue(any(project.rglob("eda_vif_diagnostics.csv")))
            catalog = pd.read_csv(next(project.rglob("eda_catalog_status.csv")))
            self.assertEqual(set(catalog["chart_id"]), {
                *(f"A{i:02d}" for i in range(1, 7)), *(f"B{i:02d}" for i in range(1, 11)),
                *(f"C{i:02d}" for i in range(1, 7)), *(f"D{i:02d}" for i in range(1, 9)),
                "E01", "E02", *(f"F{i:02d}" for i in range(1, 8)),
                *(f"G{i:02d}" for i in range(1, 7)), *(f"H{i:02d}" for i in range(1, 8)),
                "I01", "I02", "I03",
            })
            self.assertEqual(set(catalog.loc[catalog["chart_id"].isin(["I02", "I03"]), "status"]), {"deferred_to_nb08_or_nb02"})
            self.assertEqual(pd.read_parquet(next(project.rglob("eda_development_scope.parquet")))["match_id"].nunique(), 10)
            mode_summary = pd.read_csv(next(project.rglob("eda_mode_comparison_summary.csv")))
            self.assertEqual(set(mode_summary.game_mode_label), {"Solo", "Duo", "Squad"})
            mode_manifest = json.loads(next(project.rglob("mode_analysis.json")).read_text(encoding="utf-8"))
            self.assertEqual(mode_manifest["sample_n"], 150)
            rq1 = pd.read_csv(next(project.rglob("rq1_relationship_summary.csv")))
            self.assertEqual(set(rq1["analysis_scope"]), {"development"})
            self.assertLessEqual(int(rq1["n_observations"].max()), 150)
            self.assertTrue(any(project.rglob("rq1_scatter_density.png")))
            for name in (
                "eda_group_a_structure.png", "eda_group_b_missing_and_zeros.png",
                "eda_group_c_raw_distributions.png", "eda_group_d_derived_distributions.png",
                "eda_group_e_mode_comparisons.png", "eda_group_f_correlation_heatmaps.png",
                "eda_group_g_timing_by_placement.png", "eda_group_h_retention_curve.png",
                "eda_group_a_catalog_supplement.png", "eda_groups_bc_catalog_supplement.png",
                "eda_group_d_catalog_supplement.png", "eda_group_f_behavior_vs_outcome.png",
                "eda_group_g_behavior_vs_outcome.png", "eda_group_h_timing_catalog_supplement.png",
            ):
                image = next(project.rglob(name))
                self.assertEqual(image.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
