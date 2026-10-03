"""Tests for Phase VII (Giai đoạn 4: Notebook 02, Cleaning, Roster, Chronology, Split)
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

from src.data.cleaning import audit_and_clean_aggregate_data
from src.data.match_metadata import build_match_metadata
from src.analysis.eda import run_chronology_audit
from src.models.splits import create_split_assignments
from src.data.io import get_duckdb_connection, atomic_write_parquet, read_json


class TestCleaningAndRemovalLedger(unittest.TestCase):
    """Checklist items 1134-1140: Deduplication, identity key conflicts, domain errors,
    sequential removal cascade reconciliation, separate overlapping error flags, task validity.
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.tmpdir.name)
        self.con = get_duckdb_connection()

        # Build synthetic aggregate data covering various anomalies
        records = [
            # 0. Clean record 1
            ["m1", "Alice", "t1", "2017-11-20T10:00:00+0000", "tpp", 2, 4, 1, 0, 50.0, 100.0, 150.0, 1, 300.0, 1],
            # 1. Clean record 2
            ["m1", "Bob", "t1", "2017-11-20T10:00:00+0000", "tpp", 2, 4, 0, 0, 0.0, 120.0, 50.0, 0, 250.0, 1],
            # 2. Exact duplicate of clean record 2 (should be removed in Step 1)
            ["m1", "Bob", "t1", "2017-11-20T10:00:00+0000", "tpp", 2, 4, 0, 0, 0.0, 120.0, 50.0, 0, 250.0, 1],
            # 3. Missing match_id (should be removed in Step 2)
            [None, "Charlie", "t2", "2017-11-20T10:00:00+0000", "tpp", 2, 4, 0, 0, 0.0, 10.0, 0.0, 0, 100.0, 2],
            # 4. Missing team_id (should be removed in Step 2)
            ["m1", "David", None, "2017-11-20T10:00:00+0000", "tpp", 2, 4, 0, 0, 0.0, 20.0, 0.0, 0, 100.0, 2],
            # 5. Missing player_name (KEPT for match/team outcome in RQ1, but player_name is null)
            ["m1", None, "t2", "2017-11-20T10:00:00+0000", "tpp", 2, 4, 0, 0, 0.0, 30.0, 0.0, 0, 100.0, 2],
            # 6. Negative damage (should be removed in Step 3)
            ["m1", "Eve", "t2", "2017-11-20T10:00:00+0000", "tpp", 2, 4, 0, 0, 0.0, 50.0, -10.0, 0, 100.0, 2],
            # 7. Non-positive placement (0) (should be removed in Step 3)
            ["m1", "Frank", "t2", "2017-11-20T10:00:00+0000", "tpp", 2, 4, 0, 0, 0.0, 50.0, 0.0, 0, 100.0, 0],
            # 8. NaN distance (should be removed in Step 3)
            ["m1", "Grace", "t2", "2017-11-20T10:00:00+0000", "tpp", 2, 4, 0, 0, np.nan, 50.0, 0.0, 0, 100.0, 2],
            # 9 & 10: Identity key conflict: same (match_id, player_name) with distinct stats
            # (neither should be picked arbitrarily by keep='first'; both quarantined in Step 4)
            ["m2", "Heidi", "t3", "2017-11-21T10:00:00+0000", "tpp", 1, 2, 0, 0, 0.0, 100.0, 50.0, 0, 200.0, 2],
            ["m2", "Heidi", "t3", "2017-11-21T10:00:00+0000", "tpp", 1, 2, 0, 0, 0.0, 200.0, 100.0, 1, 400.0, 1],
            # 11. Clean record in m2
            ["m2", "Ivan", "t4", "2017-11-21T10:00:00+0000", "tpp", 1, 2, 0, 0, 0.0, 500.0, 300.0, 2, 600.0, 1],
        ]
        columns = [
            "match_id", "player_name", "team_id", "date", "match_mode", "party_size", "game_size",
            "player_assists", "player_dbno", "player_dist_ride", "player_dist_walk",
            "player_dmg", "player_kills", "player_survive_time", "team_placement"
        ]
        df = pd.DataFrame(records, columns=columns)
        self.shard_pq = self.work_dir / "shard_0.parquet"
        atomic_write_parquet(self.shard_pq, df)

        self.cleaned_pq = self.work_dir / "cleaned.parquet"
        self.removal_csv = self.work_dir / "removal_log.csv"
        self.error_flags_csv = self.work_dir / "error_flags.csv"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_audit_and_clean_sequential_cascade_reconciliation(self):
        summary = audit_and_clean_aggregate_data(
            self.con,
            [self.shard_pq],
            self.cleaned_pq,
            self.removal_csv,
            self.error_flags_csv,
        )

        # Total raw rows was 12
        self.assertEqual(summary["total_raw_rows"], 12)

        # Removal log must exist and be strictly reconcilable
        df_removal = pd.read_csv(self.removal_csv)
        self.assertIn("rows_before", df_removal.columns)
        self.assertIn("rows_removed", df_removal.columns)
        self.assertIn("rows_after", df_removal.columns)

        # Check step-by-step invariant: rows_before - rows_removed = rows_after
        for _, row in df_removal[df_removal["stage"] == "cleaning"].iterrows():
            if row["reason"] not in ("total_dropped_records", "validated_clean_records"):
                self.assertEqual(row["rows_before"] - row["rows_removed"], row["rows_after"])

        # Step removals:
        # Step 1 (exact dup): row 2 is exact dup of row 1 -> 1 removed
        self.assertEqual(summary["step_removals"]["r1_exact"], 1)
        # Step 2 (missing keys): row 3 (null match_id), row 4 (null team_id) -> 2 removed
        self.assertEqual(summary["step_removals"]["r2_keys"], 2)
        # Step 3 removes only invalid core behavior; target-invalid and missing-behavior rows remain.
        self.assertEqual(summary["step_removals"]["r3_domain"], 1)
        # Step 4 (identity key conflict): rows 9 & 10 (Heidi conflict in m2) -> 2 removed
        self.assertEqual(summary["step_removals"]["r4_conflicts"], 2)

        # Total dropped = 1 + 2 + 1 + 2 = 6; task-specific invalidity is not global deletion.
        # Retained rows remain available to every task whose own validity condition they satisfy.
        self.assertEqual(summary["clean_rows"], 6)
        self.assertEqual(summary["dropped_rows"], 6)

        # Verify cleaned parquet content
        clean_df = pd.read_parquet(self.cleaned_pq)
        self.assertEqual(len(clean_df), 6)
        self.assertTrue((clean_df["player_kills"] >= 0).all())
        self.assertEqual(int((clean_df["team_placement"] <= 0).sum()), 1)
        # Player name null retained
        self.assertEqual(int(clean_df["player_name"].isna().sum()), 1)
        # Validity flags present
        self.assertIn("valid_survival", clean_df.columns)
        self.assertIn("valid_placement", clean_df.columns)
        self.assertTrue(clean_df["valid_survival"].all())
        self.assertEqual(int((~clean_df["valid_placement"]).sum()), 1)
        self.assertEqual(int(clean_df["has_behavior_missing"].sum()), 1)
        conflicts = pd.read_parquet(self.work_dir / "identity_conflicts.parquet")
        self.assertEqual(len(conflicts), 2)
        self.assertIn("normalized_player_name", conflicts.columns)
        task_ledger = pd.read_csv(self.work_dir / "task_exclusion_ledger.csv")
        placement = task_ledger.loc[task_ledger["task"] == "placement"].iloc[0]
        self.assertEqual(int(placement["affected_rows"]), 1)

    def test_overlapping_error_flags_separate_from_removal_ledger(self):
        audit_and_clean_aggregate_data(
            self.con,
            [self.shard_pq],
            self.cleaned_pq,
            self.removal_csv,
            self.error_flags_csv,
        )

        df_flags = pd.read_csv(self.error_flags_csv)
        flags_dict = dict(zip(df_flags["flag_name"], df_flags["affected_rows"]))

        self.assertEqual(flags_dict["exact_duplicates"], 1)
        self.assertEqual(flags_dict["missing_match_id"], 1)
        self.assertEqual(flags_dict["missing_team_id"], 1)
        self.assertEqual(flags_dict["missing_player_name"], 1)
        self.assertEqual(flags_dict["invalid_domain_values"], 1)
        self.assertEqual(flags_dict["invalid_placement_target"], 1)
        self.assertEqual(flags_dict["missing_behavior_values"], 1)
        self.assertEqual(flags_dict["key_conflicts"], 2)

        # Sum of diagnostic flags is 1+1+1+1+3+2 = 9, which is DIFFERENT from total dropped (8),
        # because missing_player_name was flagged but NOT dropped, and other checks might overlap.
        # This confirms that diagnostic flags are never conflated with the sequential cascade.
        self.assertNotEqual(df_flags["affected_rows"].sum(), 6)


    def test_lineage_does_not_prevent_business_duplicate_removal(self):
        row = pd.read_parquet(self.shard_pq).iloc[[0]]
        staged = pd.concat([row, row], ignore_index=True)
        staged["source_file"] = ["part_a.csv", "part_b.csv"]
        staged["source_row"] = [1, 99]
        staged_path = self.work_dir / "staged_with_lineage.parquet"
        atomic_write_parquet(staged_path, staged)

        summary = audit_and_clean_aggregate_data(
            self.con,
            [staged_path],
            self.work_dir / "lineage_cleaned.parquet",
            self.work_dir / "lineage_removal.csv",
            self.work_dir / "lineage_flags.csv",
        )

        self.assertEqual(summary["exact_duplicates"], 1)
        self.assertEqual(summary["step_removals"]["r1_exact"], 1)
        cleaned = pd.read_parquet(self.work_dir / "lineage_cleaned.parquet")
        self.assertEqual(len(cleaned), 1)
        self.assertIn("source_file", cleaned.columns)
        ledger = pd.read_csv(self.work_dir / "lineage_removal.csv")
        self.assertTrue({"rule", "example_count", "version"}.issubset(ledger.columns))

class TestMatchMetadataAndRosterAudit(unittest.TestCase):
    """Checklist items 1139, 1141: Roster completeness, date/mode/party_size conflicts,
    no MIN/MODE concealing of intra-match contradictions.
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.tmpdir.name)
        self.con = get_duckdb_connection()

        # m1: Complete roster (2 teams, 2 players, max_placement=2, matches observed teams)
        # m2: Date conflict (different dates within same match)
        # m3: Incomplete roster (1 team observed, placement=10)
        data = [
            # m1
            ["m1", "Alice", "t1", "2017-11-20T10:00:00+0000", "tpp", 1, 2, 0, 0, 0.0, 100.0, 50.0, 0, 300.0, 1, True, True],
            ["m1", "Bob", "t2", "2017-11-20T10:00:00+0000", "tpp", 1, 2, 0, 0, 0.0, 100.0, 50.0, 0, 200.0, 2, True, True],
            # m2: date conflict & mode conflict
            ["m2", "Charlie", "t3", "2017-11-21T10:00:00+0000", "tpp", 1, 2, 0, 0, 0.0, 100.0, 50.0, 0, 400.0, 1, True, True],
            ["m2", "David", "t4", "2017-11-22T15:00:00+0000", "fpp", 1, 2, 0, 0, 0.0, 100.0, 50.0, 0, 300.0, 2, True, True],
            # m3: incomplete roster
            ["m3", "Eve", "t5", "2017-11-23T10:00:00+0000", "tpp", 1, 20, 0, 0, 0.0, 100.0, 50.0, 0, 500.0, 10, True, True],
        ]
        cols = [
            "match_id", "player_name", "team_id", "date", "match_mode", "party_size", "game_size",
            "player_assists", "player_dbno", "player_dist_ride", "player_dist_walk",
            "player_dmg", "player_kills", "player_survive_time", "team_placement", "valid_survival", "valid_placement"
        ]
        self.cleaned_pq = self.work_dir / "cleaned.parquet"
        atomic_write_parquet(self.cleaned_pq, pd.DataFrame(data, columns=cols))

        self.meta_pq = self.work_dir / "meta.parquet"
        self.audit_json = self.work_dir / "match_audit.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_match_metadata_conflict_audit_and_roster(self):
        total_matches = build_match_metadata(self.con, self.cleaned_pq, self.meta_pq, self.audit_json)
        self.assertEqual(total_matches, 3)

        meta_df = pd.read_parquet(self.meta_pq).set_index("match_id")

        # m1 has no conflicts and is roster complete
        self.assertFalse(meta_df.loc["m1", "has_date_conflict"])
        self.assertFalse(meta_df.loc["m1", "has_mode_conflict"])
        self.assertTrue(meta_df.loc["m1", "is_roster_complete"])

        # m2 has date conflict and mode conflict
        self.assertTrue(meta_df.loc["m2", "has_date_conflict"])
        self.assertTrue(meta_df.loc["m2", "has_mode_conflict"])
        self.assertTrue(meta_df.loc["m2", "has_metadata_conflict"])
        self.assertTrue(pd.isna(meta_df.loc["m2", "match_date"]))
        self.assertIn("missing_team_id_rows", meta_df.columns)
        self.assertIn("team_placement_conflict_count", meta_df.columns)

        # m3 has incomplete roster: 1 team observed vs placement 10
        self.assertFalse(meta_df.loc["m3", "is_roster_complete"])

        # Audit report json check
        audit_data = read_json(self.audit_json)
        self.assertEqual(audit_data["total_matches"], 3)
        self.assertEqual(audit_data["date_conflicts"], 1)
        self.assertEqual(audit_data["mode_conflicts"], 1)
        self.assertEqual(audit_data["roster_complete_matches"], 2)  # m1 and m2


class TestChronologyAudit(unittest.TestCase):
    """Checklist items 1142-1145: Timestamp audit, Grade A/B/C assignment per research spec v3.0,
    withholding Grade A when exact completion order lacks evidence even if tie ratio is low.
    """

    def test_grade_b_for_cross_day_chronology_without_exact_intra_day_order(self):
        # 3 matches across 3 distinct days with 0 tie ratio
        meta_df = pd.DataFrame({
            "match_date": ["2017-11-20T10:00:00+0000", "2017-11-21T12:00:00+0000", "2017-11-22T14:00:00+0000"]
        })
        # Low tie ratio (0.0), but has_exact_order_evidence=False
        report = run_chronology_audit(meta_df, has_exact_order_evidence=False)
        self.assertEqual(report["grade"], "Grade B")
        self.assertEqual(report["historical_modeling_status"], "eligible_cross_day")
        self.assertEqual(report["policy"], "strictly_earlier_days_only")
        self.assertEqual(report["timestamp_tie_ratio"], 0.0)
        self.assertEqual(report["timezone_normalized"], "UTC")
        self.assertEqual(report["source_timestamp_semantics"], "pending_source_evidence")
        self.assertFalse(report["has_exact_order_evidence"])
        self.assertIn("strictly earlier days only", report["description"])

    def test_grade_a_requires_explicit_evidence(self):
        meta_df = pd.DataFrame({
            "match_date": ["2017-11-20T10:00:00+0000", "2017-11-21T12:00:00+0000", "2017-11-22T14:00:00+0000"]
        })
        # With explicit evidence
        report = run_chronology_audit(meta_df, has_exact_order_evidence=True)
        self.assertEqual(report["grade"], "Grade A")
        self.assertEqual(report["historical_modeling_status"], "eligible_granular")
        self.assertEqual(report["policy"], "exact_order")

    def test_same_player_timestamp_overlap_is_reported(self):
        meta_df = pd.DataFrame({
            "match_date": [
                "2017-11-20T10:00:00+0000",
                "2017-11-21T10:00:00+0000",
                "2017-11-22T10:00:00+0000",
            ]
        })
        players = pd.DataFrame({
            "match_id": ["m1", "m2", "m3"],
            "player_name": ["Alice", "Alice", "Bob"],
            "date": [
                "2017-11-20T10:00:00+0000",
                "2017-11-20T10:00:00+0000",
                "2017-11-22T10:00:00+0000",
            ],
        })
        report = run_chronology_audit(
            meta_df, has_exact_order_evidence=True, player_match_df=players
        )
        self.assertEqual(report["same_player_timestamp_overlap_count"], 1)
        self.assertEqual(report["grade"], "Grade B")
    def test_grade_c_when_insufficient_days_or_missing_dates(self):
        # Only 2 days observed
        meta_df = pd.DataFrame({
            "match_date": ["2017-11-20T10:00:00+0000", "2017-11-20T12:00:00+0000", "2017-11-21T14:00:00+0000"]
        })
        report = run_chronology_audit(meta_df)
        self.assertEqual(report["grade"], "Grade C")
        self.assertEqual(report["historical_modeling_status"], "blocked")

        # Missing / unparseable date
        meta_df_err = pd.DataFrame({
            "match_date": ["2017-11-20T10:00:00+0000", None, "2017-11-22T14:00:00+0000"]
        })
        report_err = run_chronology_audit(meta_df_err)
        self.assertEqual(report_err["grade"], "Grade C")
        self.assertEqual(report_err["historical_modeling_status"], "blocked")


class TestSplitAssignments(unittest.TestCase):
    """Checklist items 1146-1148: Match isolation, date ranges, split intersections,
    train/val/test ratio enforcement, manifest metadata.
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.tmpdir.name)
        self.con = get_duckdb_connection()

        # Create 10 matches
        dates = [f"2017-11-{20 + i:02d}T10:00:00+0000" for i in range(10)]
        meta_data = pd.DataFrame({
            "match_id": [f"m_{i}" for i in range(10)],
            "match_date": dates,
            "observed_player_count": [100] * 10,
        })
        self.meta_pq = self.work_dir / "meta.parquet"
        atomic_write_parquet(self.meta_pq, meta_data)

        self.split_pq = self.work_dir / "split_assignments.parquet"
        self.manifest_json = self.work_dir / "split_manifest.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_group_by_match_split_isolation(self):
        manifest = create_split_assignments(
            self.con,
            self.meta_pq,
            self.split_pq,
            self.manifest_json,
            strategy="group_by_match",
            train_ratio=0.70,
            val_ratio=0.15,
            test_ratio=0.15,
            random_state=42,
        )

        self.assertTrue(manifest["match_isolation_verified"])
        self.assertEqual(manifest["split_intersections"]["train_val"], 0)
        self.assertEqual(manifest["split_intersections"]["train_test"], 0)
        self.assertEqual(manifest["split_intersections"]["val_test"], 0)

        df_split = pd.read_parquet(self.split_pq)
        self.assertEqual(len(df_split), 10)
        # 10 matches: 7 train, 1 val, 2 test
        counts = df_split["split"].value_counts().to_dict()
        self.assertEqual(counts["train"], 7)
        self.assertEqual(counts["validation"], 1)
        self.assertEqual(counts["test"], 2)

    def test_chronological_split_date_ordering(self):
        manifest = create_split_assignments(
            self.con,
            self.meta_pq,
            self.split_pq,
            self.manifest_json,
            strategy="chronological",
            train_ratio=0.70,
            val_ratio=0.15,
            test_ratio=0.15,
        )

        self.assertIn("date_ranges", manifest)
        train_end = manifest["date_ranges"]["train"]["end"]
        val_start = manifest["date_ranges"]["validation"]["start"]
        val_end = manifest["date_ranges"]["validation"]["end"]
        test_start = manifest["date_ranges"]["test"]["start"]

        # Chronological invariant: train_end <= val_start and val_end <= test_start
        self.assertLessEqual(train_end, val_start)
        self.assertLessEqual(val_end, test_start)


    def test_grade_b_keeps_each_utc_day_in_one_split(self):
        dates = [
            "2017-11-20T10:00:00+0000", "2017-11-20T12:00:00+0000",
            "2017-11-21T10:00:00+0000", "2017-11-21T12:00:00+0000",
            "2017-11-22T10:00:00+0000", "2017-11-22T12:00:00+0000",
            "2017-11-23T10:00:00+0000", "2017-11-24T10:00:00+0000",
        ]
        meta = pd.DataFrame({
            "match_id": [f"day_match_{index}" for index in range(len(dates))],
            "match_date": dates,
            "observed_player_count": [10] * len(dates),
        })
        atomic_write_parquet(self.meta_pq, meta)
        manifest = create_split_assignments(
            self.con,
            self.meta_pq,
            self.split_pq,
            self.manifest_json,
            strategy="chronological",
            train_ratio=0.5,
            val_ratio=0.25,
            test_ratio=0.25,
            chronology_grade="Grade B",
        )
        assigned = pd.read_parquet(self.split_pq).merge(meta, on="match_id")
        assigned["day"] = pd.to_datetime(assigned["match_date"], utc=True).dt.date
        self.assertTrue((assigned.groupby("day")["split"].nunique() == 1).all())
        self.assertEqual(manifest["boundary_policy"], "whole_utc_day_blocks")
        self.assertFalse(manifest["tie_blocks_split"])

class TestNotebook02Execution(unittest.TestCase):
    def test_actual_notebooks_01_and_02_run_with_scientific_outputs(self):
        root = Path(__file__).resolve().parent.parent
        notebook01 = root / "notebooks" / "01_download_validate.ipynb"
        notebook02 = root / "notebooks" / "02_data_quality_and_structure.ipynb"

        document = json.loads(notebook02.read_text(encoding="utf-8"))
        markdown = "\n".join(
            "".join(cell["source"])
            for cell in document["cells"]
            if cell["cell_type"] == "markdown"
        )
        for marker in (
            "Bối cảnh khoa học", "Identity", "Roster", "Chronology audit",
            "Khóa split", "Trực quan kiểm toán", "Gate G2", "giới hạn", "bàn giao",
        ):
            self.assertIn(marker, markdown)

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            raw = workspace / "Data_PUBG"
            (raw / "aggregate").mkdir(parents=True)
            (raw / "deaths").mkdir()

            dates = [
                "2017-11-20T10:00:00+0000", "2017-11-20T12:00:00+0000",
                "2017-11-21T10:00:00+0000", "2017-11-22T10:00:00+0000",
                "2017-11-23T10:00:00+0000", "2017-11-24T10:00:00+0000",
            ]
            rows = []
            for index, date in enumerate(dates, start=1):
                for team, placement in (("t1", 1), ("t2", 2)):
                    rows.append({
                        "date": date, "game_size": 2, "match_id": f"m{index}",
                        "match_mode": "tpp", "party_size": 1,
                        "player_assists": 0, "player_dbno": 0,
                        "player_dist_ride": 0.0, "player_dist_walk": 100.0 + index,
                        "player_dmg": 50.0 + index, "player_kills": 1,
                        "player_name": f"p{index}_{team}", "player_survive_time": 300.0,
                        "team_id": team, "team_placement": placement,
                    })
            rows.append(dict(rows[0]))
            invalid_target = dict(rows[9])
            invalid_target["player_name"] = "placement_invalid"
            invalid_target["team_id"] = "t3"
            invalid_target["team_placement"] = 0
            rows.append(invalid_target)
            rows[7]["player_dmg"] = None
            conflict_a = dict(rows[-4])
            conflict_a["player_name"] = "conflict_player"
            conflict_b = dict(conflict_a)
            conflict_b["player_dmg"] = 999.0
            rows.extend([conflict_a, conflict_b])
            pd.DataFrame(rows).to_csv(raw / "aggregate" / "agg_match_stats_0.csv", index=False)
            pd.DataFrame({
                "match_id": ["m1"], "time": [120.0], "killer_name": ["p1_t1"],
                "victim_name": ["p1_t2"], "killed_by": ["AKM"],
            }).to_csv(raw / "deaths" / "kill_match_stats_final_0.csv", index=False)

            program = '''import json, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
nb = json.load(open(sys.argv[1], encoding="utf-8"))
scope = {"PUBG_INSTALL_DEPENDENCIES": False, "PUBG_BATCH_ROWS": 4, "__name__": "__main__"}
for index, cell in enumerate(nb["cells"]):
    if cell["cell_type"] == "code":
        exec(compile("".join(cell["source"]), f"{sys.argv[1]}-cell-{index}", "exec"), scope)
        if "storage-options" in cell.get("metadata", {}).get("tags", []):
            scope.update(PUBG_STORAGE_MODE="runtime", PUBG_REQUIRE_EXISTING_PROJECT=False)
'''
            run01 = subprocess.run(
                [sys.executable, "-c", program, str(notebook01)],
                cwd=workspace, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120,
            )
            self.assertEqual(run01.returncode, 0, run01.stdout + run01.stderr)
            inventory_path = next(workspace.rglob("source_inventory.json"))
            project = inventory_path.parents[2]

            import yaml
            rq3_path = project / "configs" / "rq3.yaml"
            rq3 = yaml.safe_load(rq3_path.read_text(encoding="utf-8"))
            rq3["split"].update({
                "strategy": "auto",
                "train_ratio": 0.5,
                "validation_ratio": 0.25,
                "test_ratio": 0.25,
            })
            rq3_path.write_text(
                yaml.safe_dump(rq3, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )

            run02 = subprocess.run(
                [sys.executable, "-c", program, str(notebook02)],
                cwd=workspace, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=180,
            )
            self.assertEqual(run02.returncode, 0, run02.stdout + run02.stderr)
            for marker in (
                "BẢNG 02-A", "BẢNG 02-B", "BẢNG 02-C", "BẢNG 02-D",
                "BẢNG 02-E", "BẢNG 02-F1", "BẢNG 02-G", "BẢNG 02-H",
                "BẢNG 02-I", "BẢNG 02-J1", "BẢNG 02-K", "BẢNG 02-L",
                "HÌNH V02-01", "HÌNH V02-02", "HÌNH V02-03", "HÌNH V02-04",
                "Gate G2 hoàn tất",
            ):
                self.assertIn(marker, run02.stdout)

            chronology = json.loads(next(project.rglob("chronology_report.json")).read_text(encoding="utf-8"))
            split_manifest = json.loads(next(project.rglob("split_manifest.json")).read_text(encoding="utf-8"))
            checkpoints = json.loads(next(project.rglob("checkpoint_manifest.json")).read_text(encoding="utf-8"))
            self.assertEqual(chronology["grade"], "Grade B")
            self.assertEqual(split_manifest["strategy"], "chronological")
            self.assertEqual(split_manifest["boundary_policy"], "whole_utc_day_blocks")
            self.assertFalse(split_manifest["tie_blocks_split"])
            self.assertTrue(split_manifest["match_isolation_verified"])
            self.assertTrue(all(value == 0 for value in split_manifest["split_intersections"].values()))
            stage = checkpoints["stages"]["notebook/02_data_quality_and_structure.ipynb"]
            self.assertEqual(stage["status"], "completed")
            for artifact in (
                "identity_conflicts", "task_exclusions", "removal_waterfall",
                "roster_distribution", "matches_per_day", "split_distribution",
            ):
                self.assertIn(artifact, stage["artifacts"])
            for name in (
                "nb02_removal_waterfall.png", "nb02_roster_distribution.png",
                "nb02_matches_per_day.png", "nb02_split_distribution.png",
            ):
                image = next(project.rglob(name))
                self.assertEqual(image.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

if __name__ == "__main__":
    unittest.main()
