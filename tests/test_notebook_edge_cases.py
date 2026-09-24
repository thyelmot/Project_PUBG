import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
import pandas as pd

from src.data.io import get_duckdb_connection, copy_query_to_parquet, publish_file
from src.data.batch_ingest import ingest_sources
from src.analysis.mode_analysis import analyze_behavior_by_mode
from src.analysis.rq1 import run_rq1_analysis
from src.analysis.clustering import execute_rq2_clustering, prepare_clustering_matrix
from src.evaluation.metrics import compute_hierarchical_metrics
from src.features.registry import FeatureRegistry
from src.features.historical import build_historical_features
from src.features.placement import compute_normalized_placement


class TestNotebookEdgeCases(unittest.TestCase):
    def test_local_sql_write_preserves_checkpoint_on_failed_validation_or_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "team's project"
            root.mkdir()
            con = get_duckdb_connection(root / "local-temp")
            output = root / "drive" / "result.parquet"
            try:
                copy_query_to_parquet(con, "SELECT 1 AS value", output, expected_rows=1)
                original = output.read_bytes()
                with self.assertRaisesRegex(ValueError, "Row count"):
                    copy_query_to_parquet(con, "SELECT * FROM range(2)", output, expected_rows=1)
                self.assertEqual(output.read_bytes(), original)
                with patch("src.data.io.publish_file", wraps=publish_file) as publish:
                    copy_query_to_parquet(con, "SELECT 2 AS value", output)
                    self.assertTrue(publish.call_args.args[0].is_relative_to(root / "local-temp"))
                original = output.read_bytes()
                with patch("src.data.io.shutil.copyfile", side_effect=OSError("Drive unavailable")):
                    with self.assertRaisesRegex(OSError, "Drive unavailable"):
                        copy_query_to_parquet(con, "SELECT 3 AS value", output)
                self.assertEqual(output.read_bytes(), original)
            finally:
                con.close()

    def test_resume_does_not_erase_unvisited_checkpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with zipfile.ZipFile(root / "test.zip", "w") as archive:
                archive.writestr("agg_match_stats.csv", "match_id\nm1\n")
                archive.writestr("kill_match_stats.csv", "match_id\nm1\n")
            data = {"source": {"archive_filename": "test.zip"}, "discovery": {
                "agg_patterns": ["**/agg*.csv"], "kill_patterns": ["**/kill*.csv"]}}
            schemas = {k: {"required_columns": {"match_id": "string"}} for k in ("aggregate", "deaths")}
            con = get_duckdb_connection(root / "temp")
            try:
                ingest_sources(con, root / "raw", root / "stage", data, schemas)
                with patch("src.data.batch_ingest.hash_file", side_effect=OSError("disconnected")):
                    with self.assertRaisesRegex(OSError, "disconnected"):
                        ingest_sources(con, root / "raw", root / "stage", data, schemas)
                manifest = json.loads((root / "stage/batch_manifest.json").read_text())
                self.assertFalse(manifest["complete"])
                self.assertEqual(len(manifest["shards"]), 2)
                with patch("src.data.batch_ingest.convert_csv_batches", side_effect=AssertionError("must reuse")):
                    ingest_sources(con, root / "raw", root / "stage", data, schemas)
            finally:
                con.close()

    def test_constant_modes_empty_rq1_and_empty_metrics(self):
        data = pd.DataFrame({"party_size": [1] * 20 + [2] * 20, "player_assists": [0] * 40,
                             "walk_ratio": [np.nan] * 40})
        result = analyze_behavior_by_mode(data, ["player_assists", "walk_ratio"])
        self.assertEqual(result["mode_differences"]["player_assists"]["p_value"], 1.0)
        with tempfile.TemporaryDirectory() as directory:
            table = run_rq1_analysis(data.iloc[:2], FeatureRegistry(), Path(directory) / "rq1.csv")
            self.assertTrue(table.empty)
            self.assertIn("target", table.columns)
        empty = pd.DataFrame(columns=["match_id", "team_id", "target_actual", "target_predicted"])
        metrics = compute_hierarchical_metrics(empty.astype({"target_actual": float, "target_predicted": float}))
        self.assertEqual(metrics["match_aware"]["n_matches"], 0)

    def test_clustering_missing_values_small_cohort_and_outcome_alignment(self):
        profiles = pd.DataFrame({"player_name": ["a", "b", "c", "d"], "games_played": [5] * 4,
                                 "mean_kills": [0., 0.1, 9., 10.], "mean_assists": [np.nan] * 4})
        outcomes = pd.DataFrame({"player_name": ["d", "c", "b", "a"], "mean_survive_time": [100, 90, 1, 0],
                                 "mean_normalized_placement": [1., .9, .1, 0.], "win_rate": [1, 1, 0, 0]})
        self.assertTrue(np.isfinite(prepare_clustering_matrix(profiles)).all())
        with tempfile.TemporaryDirectory() as directory:
            result = execute_rq2_clustering(profiles, outcomes, 2, Path(directory))
            self.assertEqual(sorted(result["outcome_comparison"]["mean_survival"]), [0.5, 95.0])
            result = execute_rq2_clustering(profiles.iloc[:1], outcomes, 4, Path(directory))
            self.assertEqual(result["status"], "skipped_insufficient_profiles")
            self.assertTrue(pd.read_csv(Path(directory) / "cluster_profile.csv").empty)
        self.assertNotIn("cluster_label", profiles)

    def test_history_excludes_simultaneous_matches_and_normalizes_timezone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = pd.DataFrame({"match_id": ["m1", "m2", "m3"], "player_name": ["p"] * 3,
                                 "team_id": ["t"] * 3,
                                 "date": ["2017-01-01T00:00:00+0000", "2017-01-01T07:00:00+0700",
                                          "2017-01-02T00:00:00+0000"]})
            for col in ["player_survive_time", "normalized_placement", "player_kills", "player_dmg",
                        "player_dist_walk", "player_dist_ride", "player_assists", "player_dbno"]:
                data[col] = 1.
            source, output = root / "features.parquet", root / "history.parquet"
            data.to_parquet(source)
            con = get_duckdb_connection(root / "temp")
            try:
                for grade in ["Grade A", "Grade B"]:
                    build_historical_features(con, source, output, grade)
                    counts = pd.read_parquet(output).set_index("match_id")["hist_games_played"]
                    self.assertEqual(counts.to_dict(), {"m1": 0, "m2": 0, "m3": 2})
            finally:
                con.close()
        placement = compute_normalized_placement(pd.Series([1, 2, 3]), pd.Series([2, 2, 2]))
        self.assertTrue(pd.isna(placement.iloc[2]["normalized_placement"]))


if __name__ == "__main__":
    unittest.main()
