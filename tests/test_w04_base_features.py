"""Tests for Phase VIII (Giai đoạn 5: Notebook 03, Feature cơ sở và target)
per PUBG_IMPLEMENTATION_PLAN.md Section 19.
"""

import json
import shutil
import subprocess
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
        for source_row, record in enumerate(agg_records, start=1):
            record.extend(["agg_fixture.csv", source_row])
        agg_cols = [
            "match_id", "player_name", "team_id", "date", "match_mode", "party_size", "game_size",
            "player_assists", "player_dbno", "player_dist_ride", "player_dist_walk",
            "player_dmg", "player_kills", "player_survive_time", "team_placement",
            "valid_survival", "valid_placement", "source_file", "source_row"
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

        self.split_pq = self.work_dir / "split_assignments.parquet"
        atomic_write_parquet(self.split_pq, pd.DataFrame({
            "match_id": ["m1", "m2", "m3"],
            "split": ["train", "validation", "test"],
        }))
        self.base_pq = self.work_dir / "player_match_base.parquet"
        self.val_csv = self.work_dir / "feature_validation_base.csv"
        self.dict_csv = self.work_dir / "feature_dictionary.csv"
        self.schema_json = self.work_dir / "player_match_base_schema.json"
        self.parts_manifest = self.work_dir / "player_match_base_parts_manifest.json"

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
            split_assignments_parquet=self.split_pq,
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
        for column in (
            "formula", "unit", "dtype", "level", "denominator",
            "allowed_targets", "forbidden_targets", "version",
        ):
            self.assertIn(column, df_dict.columns)
        self.assertEqual(len(df_dict[df_dict["group"] != "historical"]), 26)
        self.assertEqual(len(df_dict[df_dict["group"] == "historical"]), 18)
        self.assertFalse({"ride_ratio", "dbno_ratio", "team_kills"} & set(df_dict["feature_name"]))

        self.assertTrue(df_base["row_id"].notna().all())
        self.assertTrue(df_base["row_id"].is_unique)
        self.assertIn("source_file", df_base.columns)
        self.assertIn("source_row", df_base.columns)
        self.assertTrue(self.schema_json.is_file())
        self.assertTrue(self.parts_manifest.is_file())
        schema = json.loads(self.schema_json.read_text(encoding="utf-8"))
        parts = json.loads(self.parts_manifest.read_text(encoding="utf-8"))
        self.assertEqual(schema["row_count"], 6)
        self.assertEqual(parts["row_count"], 6)
        self.assertEqual(parts["row_count_from_parts"], 6)
        self.assertEqual(sum(part["rows"] for part in parts["parts"]), 6)

    def test_consumer_notebook_04_integration(self):
        """Verify that Notebook 04 (merge_player_match_and_timing) cleanly consumes
        Notebook 03 output (player_match_base.parquet) without re-calculating base features.
        """
        build_player_match_base(
            con=self.con,
            cleaned_aggregate_parquet=self.clean_pq,
            match_metadata_parquet=self.meta_pq,
            output_base_parquet=self.base_pq,
            split_assignments_parquet=self.split_pq,
        )

        # Mock timing parquet from Notebook 04
        timing_records = [
            ["m1", "Alice", 1, 150.0, 150.0, 150.0, 1, 1, 0, 0, 1.0, 0.0, 0.0, True],
        ]
        timing_cols = [
            "match_id", "killer_name", "event_kill_count", "sum_kill_time", "first_kill_time", "avg_kill_time",
            "phase_eligible_kill_count", "early_kills", "mid_kills", "late_kills",
            "early_kill_ratio", "mid_kill_ratio", "late_kill_ratio", "has_kill"
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


class TestNotebook03Execution(unittest.TestCase):
    def test_actual_notebook_03_runs_with_scientific_outputs(self):
        root = Path(__file__).resolve().parent.parent
        notebook = root / "notebooks" / "03_build_player_match.ipynb"
        document = json.loads(notebook.read_text(encoding="utf-8"))
        markdown = "\n".join(
            "".join(cell["source"])
            for cell in document["cells"]
            if cell["cell_type"] == "markdown"
        )
        for marker in (
            "Bối cảnh khoa học", "Feature Registry", "structural missing",
            "Grain", "Ví dụ tính tay", "Mode audit", "Trực quan kiểm toán",
            "Gate G3", "giới hạn", "bàn giao",
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
        clean = paths["interim"] / "cleaned_aggregate.parquet"
        meta = paths["interim"] / "match_metadata.parquet"
        split = paths["interim"] / "split_assignments.parquet"

        specs = [
            ("m1", "tpp", 1, "train"),
            ("m2", "duo-fpp", 2, "train"),
            ("m3", "squad-tpp", 4, "validation"),
            ("m4", "custom", 3, "test"),
        ]
        rows = []
        for match_index, (match_id, mode, party_size, split_name) in enumerate(specs, start=1):
            for player_index, (team_id, placement) in enumerate((("t1", 1), ("t2", 2)), start=1):
                player = None if match_id == "m4" and player_index == 2 else f"{match_id}_p{player_index}"
                kills = 0 if player_index == 2 else match_index
                damage = 0.0 if kills == 0 else float(match_index * 100)
                walk = 0.0 if match_id == "m4" else float(100 * player_index)
                ride = 0.0 if player_index == 1 else 50.0
                assists = 0 if player_index == 2 else 1
                survive = -1.0 if match_id == "m4" and player_index == 1 else float(200 + 10 * match_index)
                raw_placement = 0 if match_id == "m4" and player_index == 2 else placement
                rows.append({
                    "match_id": match_id, "player_name": player, "team_id": team_id,
                    "source_file": "fixture.parquet", "source_row": len(rows) + 1,
                    "date": f"2017-11-{19 + match_index:02d}T10:00:00+0000",
                    "match_mode": mode, "party_size": party_size, "game_size": 2,
                    "player_kills": kills, "player_dmg": damage,
                    "player_dist_walk": walk, "player_dist_ride": ride,
                    "player_assists": assists, "player_dbno": 0,
                    "player_survive_time": survive, "team_placement": raw_placement,
                    "valid_survival": survive >= 0, "valid_placement": raw_placement in (1, 2),
                })
        atomic_write_parquet(clean, pd.DataFrame(rows))
        meta_rows = []
        for match_index, (match_id, mode, party_size, split_name) in enumerate(specs, start=1):
            meta_rows.append({
                "match_id": match_id,
                "match_date": f"2017-11-{19 + match_index:02d}T10:00:00+0000",
                "match_mode": mode, "party_size": party_size, "game_size": 2,
                "observed_team_count": 2, "observed_player_count": 2,
                "max_observed_placement": 2, "estimated_match_duration": 300.0,
                "missing_team_id_rows": 0, "team_placement_conflict_count": 0,
                "is_roster_complete": True, "has_metadata_conflict": False,
            })
        atomic_write_parquet(meta, pd.DataFrame(meta_rows))
        atomic_write_parquet(split, pd.DataFrame({
            "match_id": [item[0] for item in specs],
            "split": [item[3] for item in specs],
        }))
        CheckpointManager(paths["checkpoints"] / "checkpoint_manifest.json").commit(
            "notebook/02_data_quality_and_structure.ipynb",
            "fixture-g2",
            {"cleaned": clean, "metadata": meta, "split": split},
        )
'''
            run = subprocess.run(
                [sys.executable, "-c", program, str(notebook)],
                cwd=workspace,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            for marker in (
                "BẢNG 03-A", "BẢNG 03-B", "BẢNG 03-C", "BẢNG 03-D",
                "BẢNG 03-E", "BẢNG 03-F", "BẢNG 03-G1", "BẢNG 03-G2",
                "BẢNG 03-G3", "BẢNG 03-H", "BẢNG 03-I", "BẢNG 03-J",
                "BẢNG 03-K", "BẢNG 03-L", "HÌNH V03-01", "HÌNH V03-02",
                "HÌNH V03-03", "Kiểm tra NB03 hoàn tất, chưa chứng nhận G3",
            ):
                self.assertIn(marker, run.stdout)

            project = next(workspace.rglob("player_match_base.parquet")).parents[2]
            base = pd.read_parquet(next(project.rglob("player_match_base.parquet")))
            dictionary = pd.read_csv(next(project.rglob("feature_dictionary.csv")))
            validation = pd.read_csv(next(project.rglob("feature_validation_base.csv")))
            schema = json.loads(next(project.rglob("player_match_base_schema.json")).read_text(encoding="utf-8"))
            parts = json.loads(next(project.rglob("player_match_base_parts_manifest.json")).read_text(encoding="utf-8"))
            checkpoints = json.loads(next(project.rglob("checkpoint_manifest.json")).read_text(encoding="utf-8"))

            self.assertEqual(len(base), 8)
            self.assertTrue(base["row_id"].notna().all())
            self.assertTrue(base["row_id"].is_unique)
            self.assertEqual(len(dictionary[dictionary["group"] != "historical"]), 26)
            self.assertEqual(len(dictionary[dictionary["group"] == "historical"]), 18)
            self.assertIn("structural_missing_count", validation.columns)
            self.assertIn("other_missing_count", validation.columns)
            self.assertEqual(schema["row_count"], 8)
            self.assertEqual(parts["row_count_from_parts"], 8)
            stage = checkpoints["stages"]["notebook/03_build_player_match.ipynb"]
            self.assertEqual(stage["status"], "completed")
            for artifact in (
                "player_match_base", "feature_dictionary", "feature_validation",
                "base_schema", "parts_manifest", "feature_distributions",
                "mode_distribution", "task_coverage",
            ):
                self.assertIn(artifact, stage["artifacts"])
            for name in (
                "nb03_feature_distributions.png",
                "nb03_mode_distribution.png",
                "nb03_task_coverage.png",
            ):
                image = next(project.rglob(name))
                self.assertEqual(image.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
if __name__ == "__main__":
    unittest.main()
