import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import io
import numpy as np
import pandas as pd
from src.analysis.eda import analyze_parquet_distributions, compute_distribution_summary
from src.analysis.mode_analysis import analyze_behavior_by_mode
from src.analysis.rq1 import run_rq1_analysis
from src.features.registry import FeatureRegistry
from src.data.checkpoints import CheckpointManager
from src.data.download_data import download_file_with_checksum


class SafeColabFixTests(unittest.TestCase):
    def test_projected_statistics_equal_full_dataframe(self):
        rng = np.random.default_rng(42)
        frame = pd.DataFrame({"party_size": np.repeat([1, 2, 4], 70),
            "player_kills": rng.integers(0, 6, 210).astype(float),
            "player_dmg": rng.normal(100, 40, 210), "player_assists": 0.,
            "player_survive_time": rng.uniform(10, 900, 210),
            "normalized_placement": rng.random(210), "unused_text": "large identifier"})
        frame.loc[::7, "player_kills"] = np.nan
        cols = ["player_kills", "player_dmg", "player_assists", "missing"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "data.parquet"
            frame.to_parquet(source, index=False)
            with patch("src.data.io.read_parquet_df", wraps=__import__("src.data.io", fromlist=["read_parquet_df"]).read_parquet_df) as reader:
                actual, modes = analyze_parquet_distributions(source, cols)
                self.assertTrue(all(len(call.kwargs["columns"]) <= 2 for call in reader.call_args_list))
            pd.testing.assert_frame_equal(actual, compute_distribution_summary(frame, cols))
            expected_modes = analyze_behavior_by_mode(frame, cols)
            pd.testing.assert_frame_equal(modes.pop("summary_table"), expected_modes.pop("summary_table"))
            self.assertEqual(modes, expected_modes)
            registry = FeatureRegistry()
            expected = run_rq1_analysis(frame, registry, root / "old.csv")
            from src.data.io import read_parquet_df
            with patch("src.analysis.rq1.read_parquet_df", wraps=read_parquet_df) as reader:
                actual = run_rq1_analysis(source, registry, root / "new.csv")
                self.assertTrue(all(len(call.kwargs["columns"]) <= 2 for call in reader.call_args_list))
            pd.testing.assert_frame_equal(actual, expected)
            no_mode = frame.drop(columns="party_size")
            no_mode.to_parquet(source, index=False)
            pd.testing.assert_frame_equal(run_rq1_analysis(source, registry, root / "new.csv"),
                                          run_rq1_analysis(no_mode, registry, root / "old.csv"))

    def test_checkpoint_skips_only_redundant_running_write(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = CheckpointManager(Path(directory) / "manifest.json")
            manager.begin_notebook("01", [])
            with patch.object(manager, "save_manifest", wraps=manager.save_manifest) as save:
                manager.begin_notebook("01", [])
                save.assert_not_called()
            manager.commit("notebook/01", "notebook_v1", {})
            manager.begin_notebook("02", ["01"])
            manager.commit("notebook/02", "notebook_v1", {})
            manager.begin_notebook("01", [])
            self.assertEqual(manager.load_manifest()["stages"]["notebook/02"]["status"], "stale")
            with self.assertRaises(RuntimeError):
                manager.begin_notebook("02", ["01"])

    def test_checkpoint_recovers_missing_drive_manifest_from_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint_manifest.json"
            manager = CheckpointManager(path)
            manager.begin_notebook("01", [])
            path.unlink()

            recovered = CheckpointManager(path).load_manifest()

            self.assertEqual(recovered["stages"]["notebook/01"]["status"], "running")
            self.assertTrue(path.is_file())

    def test_download_uses_configured_local_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            response = io.BytesIO(b"payload")
            response.headers = {"Content-Length": "7"}
            from src.data.io import publish_file
            with patch("urllib.request.urlopen", return_value=response), patch("src.data.download_data.publish_file", wraps=publish_file) as publish:
                download_file_with_checksum("https://example.org/data", root / "data.zip", temp_dir=root / "scratch")
                self.assertEqual(publish.call_args.args[0].parent, root / "scratch")
            self.assertEqual((root / "data.zip").read_bytes(), b"payload")
            self.assertEqual(list((root / "scratch").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
