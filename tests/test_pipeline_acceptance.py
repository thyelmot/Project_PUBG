"""D6 local acceptance; synthetic CPU evidence, never PUBG/CUDA certification."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import nbformat
import numpy as np
import pandas as pd

from src import analysis, features, modeling, preprocessing, reporting
from src.io import Context, digest, read_json, software_versions, write_json
from src.kaggle_runtime import prepare_handoff, restore_handoff, verify_handoff, code_files
from test_data_features import ROOT, fixture, write_config
from test_model_dataflow import decimal_db
from test_s02_outofcore import reference_metadata
import reference_features_v56 as old_features
import reference_analysis_v57 as old_analysis
import reference_clustering_v58 as old_clustering
import reference_modeling_v58 as old_modeling
import reference_reporting_v59 as old_reporting


# Registered before comparisons; DB uses a separate high-precision oracle.
RTOL, ATOL = 1e-9, 1e-10
STAGES = [preprocessing.ingest, preprocessing.clean_split, features.base_features,
          features.combat_timing, analysis.eda, analysis.relationship,
          analysis.clustering, modeling.prediction, modeling.comparisons, reporting.finalize]


def acceptance_fixture(root):
    cfg = fixture(root)
    cfg["source"].update(dataset="pubg-d6-synthetic", version=1,
                         license="Synthetic logic fixture; not PUBG source")
    cfg["runtime"].update(duckdb_memory="128MiB", threads=2, temp_directory=str(root / "scratch"))
    cfg["timing"]["partitions"] = 7
    for section in ("preprocessing", "features", "rq2", "rq3"):
        cfg[section]["decision_mode"] = "auto"
    cfg["preprocessing"].update(chronology_evidence=None, chronology_grade=None, chronology_reason=None)
    cfg["report"]["bootstrap_replicates"] = 20
    write_config(root, cfg)
    raw = root / "raw_fixture"
    for path in sorted(raw.glob("agg*.csv")):
        frame = pd.read_csv(path)
        day = frame.match_id.str.removeprefix("match").astype(int)
        player = frame.player_name.str.removeprefix("player").astype(int)
        frame["party_size"] = day.mod(3).map({0: 1, 1: 2, 2: 4})
        team = player // frame.party_size
        frame["team_id"] = "team" + team.astype(str)
        frame["team_placement"] = (team + day) % (8 // frame.party_size) + 1
        frame["player_name"] = "Người_" + player.astype(str)
        frame["player_dmg"] = frame.player_dmg.astype(float)
        frame.loc[(day == 4) & (player == 0), "team_id"] = None
        frame.loc[(day == 5) & (player == 0), "player_survive_time"] = -1
        frame.loc[(day == 6) & (player == 0), "player_name"] = None
        frame.loc[(day == 7) & (player == 0), "player_dmg"] = np.inf
        frame.to_csv(path, index=False)
    source = pd.read_csv(raw / "agg_match_stats_0.csv")
    replay = source.loc[source.match_id.eq("match3")].iloc[:1].copy()
    conflict = source.loc[source.match_id.eq("match9")].iloc[:1].copy()
    conflict["player_dmg"] += 1
    other = raw / "agg_match_stats_1.csv"
    pd.concat([pd.read_csv(other), replay, conflict], ignore_index=True).to_csv(other, index=False)
    for path in sorted(raw.glob("kill*.csv")):
        events = pd.read_csv(path)
        events["killer_name"] = events.killer_name.str.replace("player", "Người_", regex=False)
        events.to_csv(path, index=False)
    return cfg


def tree_hashes(root):
    return {p.relative_to(root).as_posix(): digest(p) for p in root.rglob("*") if p.is_file()}


class PipelineAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="pubg-d6-chain-")
        cls.review = Path(tempfile.mkdtemp(prefix="pubg-d6-evidence-"))
        cls.contexts = []
        for variant in ("reference", "current"):
            root = Path(cls.folder.name) / variant
            acceptance_fixture(root)
            ctx = Context(root, "development", progress=lambda _: None)
            functions = STAGES if variant == "current" else [
                preprocessing.ingest, preprocessing.clean_split, old_features.base_features,
                old_features.combat_timing, old_analysis.eda, old_analysis.relationship,
                old_clustering.clustering, old_modeling.prediction, old_modeling.comparisons,
                old_reporting.finalize]
            raw = tree_hashes(root / "raw_fixture")
            with patch("src.preprocessing.build_match_metadata", reference_metadata) if variant == "reference" else patch("src.preprocessing.build_match_metadata", wraps=preprocessing.build_match_metadata):
                for index, function in enumerate(functions, 1):
                    ctx.run(f"S{index:02d}", function)
            if raw != tree_hashes(root / "raw_fixture"):
                raise AssertionError("Raw fixture mutated")
            cls.contexts.append(ctx)
        write_json({"scope": "synthetic CPU, not PUBG/full-data/CUDA", "software": software_versions(),
                    "sql_limit": "128MiB", "threads": 2, "rtol": RTOL, "atol": ATOL,
                    "reference": "composed frozen v56/v57/v58/v59 helpers; current ingest/S02 with old metadata query",
                    "production_config_changed": False}, cls.review / "environment.json")

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def compare(self, a, b, keys=None):
        # Physical file order/run IDs are provenance, not cohort equivalence.
        for frame in (a, b):
            if "run_id" in frame:
                frame.drop(columns="run_id", inplace=True)
        self.assertEqual(list(a), list(b))
        if keys is None:
            keys = [c for c in a if not pd.api.types.is_float_dtype(a[c])]
        if keys:
            self.assertFalse(a.duplicated(keys).any(), "Comparison keys must be unique")
            self.assertFalse(b.duplicated(keys).any(), "Comparison keys must be unique")
            a = a.sort_values(keys, na_position="first").reset_index(drop=True)
            b = b.sort_values(keys, na_position="first").reset_index(drop=True)
        pd.testing.assert_frame_equal(a.isna(), b.isna(), check_exact=True)
        exact = [c for c in a if not pd.api.types.is_float_dtype(a[c])]
        pd.testing.assert_frame_equal(a[exact], b[exact], check_exact=True)
        pd.testing.assert_frame_equal(a, b, rtol=RTOL, atol=ATOL)

    def test_whole_chain_tables_predictions_and_independent_db(self):
        old, new = self.contexts
        compared = []
        for name, key in (("aggregate", "source_file"), ("event", "source_file"),
                          ("cleaned", "row_id"), ("match_metadata", "match_id"),
                          ("split", "match_id"), ("base", "row_id"),
                          ("player_match", "row_id"), ("kill_discrepancy", "row_id")):
            keys = [key, "source_row"] if key == "source_file" else [key]
            with self.subTest(dataset=name):
                self.compare(pd.read_parquet(old.data / (name + ".parquet")),
                             pd.read_parquet(new.data / (name + ".parquet")), keys)
            compared.append(name)
        tables = ("removal_ledger", "quality_flags", "identity_conflicts", "split_summary",
                  "feature_validation", "feature_dictionary", "timing_coverage",
                  "timing_discrepancy_summary", "timing_phase_summary", "timing_audit",
                  "eda_statistics", "mode_statistics", "rq1_relationships", "profile_retention",
                  "profile_coverage", "cluster_sizes", "cluster_centers", "cluster_outcomes",
                  "cluster_assignments", "coefficients", "model_cohorts", "model_metrics",
                  "validation_metrics", "timing_comparison", "timing_ci", "error_analysis")
        for name in tables:
            with self.subTest(table=name):
                self.compare(pd.read_csv(old.path("tables/" + name + ".csv")),
                             pd.read_csv(new.path("tables/" + name + ".csv")))
        for split in ("validation", "test"):
            for experiment in ("s1_mean", "s1_median", "s1_linear", "p2_mean", "p2_median", "p2_linear", "t0_linear"):
                name = f"predictions/{split}_{experiment}.parquet"
                self.compare(pd.read_parquet(old.path(name)), pd.read_parquet(new.path(name)), ["row_id"])
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
        with new.disk_db() as con:
            frame = analysis.profiles(con, new, True)
        diagnostic = pd.read_csv(new.path("tables/k_diagnostics.csv"))
        for mode, group in frame.groupby("team_size_mode"):
            group = group.sort_values("player_name")
            X = StandardScaler().fit_transform(SimpleImputer(strategy="mean", add_indicator=True, keep_empty_features=True).fit_transform(group[analysis.PROFILE_FEATURES]))
            for k in (2, 3):
                labels = analysis.kmeans("cpu", k, 42).fit(X).labels_
                actual = diagnostic.loc[diagnostic["mode"].eq(mode) & diagnostic.k.eq(k), "davies_bouldin"].item()
                np.testing.assert_allclose(actual, decimal_db(X, labels), rtol=RTOL, atol=ATOL)
        self.compare(pd.read_csv(old.path("tables/k_diagnostics.csv")).drop(columns="davies_bouldin"),
                     diagnostic.drop(columns="davies_bouldin"))
        selected = [read_json(c.path("manifests/cluster_selection.json"))["clusters"] for c in self.contexts]
        self.assertEqual(*selected)
        self.assertEqual(set(selected[0]), {"Solo", "Duo", "Squad"})
        ledger = pd.read_csv(new.path("tables/removal_ledger.csv"))
        self.assertTrue((ledger.before == ledger.removed + ledger.after).all())
        self.assertTrue(ledger.removed.gt(0).any())
        self.assertFalse(read_json(new.path("manifests/selection.json"))["test_accessed_at_approval"])
        write_json({"status": "passed", "canonical_datasets": compared, "tables": list(tables),
                    "prediction_frames": 14, "modes": sorted(selected[0]),
                    "davies_bouldin": "Decimal60 independent oracle, not old cancellation-prone metric",
                    "tolerance": {"rtol": RTOL, "atol": ATOL}}, self.review / "parity.json")

    def test_fresh_restore_reuses_all_stages_and_report_is_read_only(self):
        ctx = self.contexts[1]
        prepare_handoff(ctx)
        reference = "synthetic/d6-local/versions/1"
        _, evidence = verify_handoff(ctx.root, "development", reference)
        self.assertIn("not Kaggle save proof", evidence["environment"])
        target = Path(self.folder.name) / "restored"
        restore_handoff(ctx.root, target, "development", ctx.cfg["source"]["directory"], reference)
        restored = Context(target, "development", progress=lambda _: None)
        before = tree_hashes(target)
        for index in range(1, 11):
            restored.run(f"S{index:02d}", lambda _: self.fail("Verified stage recomputed after restore"))
        pointer = read_json(restored.path("manifests/final_results.json"))
        with patch("IPython.display.display"), patch("IPython.display.Image"), patch("sklearn.pipeline.Pipeline.fit", side_effect=AssertionError("report must not fit")):
            reporting.display_release(target / pointer["manifest"])
        self.assertEqual(before, tree_hashes(target))
        write_json({"status": "passed", "reused_stages": 10, "report_tree_unchanged": True,
                    "saved_version_verified": False}, self.review / "restore.json")

    def test_real_process_exit_between_partitions_requires_explicit_takeover(self):
        with tempfile.TemporaryDirectory(prefix="pubg-d6-interrupted-") as folder:
            root = Path(folder) / "project"
            acceptance_fixture(root)
            ctx = Context(root, "development", progress=lambda _: None)
            for index, function in enumerate(STAGES[:3], 1):
                ctx.run(f"S{index:02d}", function)
            good = {p: digest(p) for p in ctx.data.glob("*.parquet")}
            script = """import os,sys
from pathlib import Path
from src.io import Context
from src.features import combat_timing
def progress(event):
    if event['step']=='timing partition' and event.get('partition')==2: os._exit(73)
ctx=Context(Path(sys.argv[1]),'development',progress=progress)
ctx.run('S04',combat_timing)
"""
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
            result = subprocess.run([sys.executable, "-B", "-c", script, str(root)], cwd=ROOT,
                                    env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 73, result.stderr)
            self.assertEqual(ctx.manifest()["S04"]["status"], "running")
            self.assertFalse((ctx.data / "player_match.parquet").exists())
            self.assertEqual(good, {p: digest(p) for p in good})
            with self.assertRaises(RuntimeError):
                prepare_handoff(ctx)
            with self.assertRaises(RuntimeError):
                Context(root, "development", progress=lambda _: None).run("S04", features.combat_timing)
            # Only the child we started has exited; never take over a live user run.
            resumed = Context(root, "development", force_takeover=True, progress=lambda _: None)
            resumed.run("S04", features.combat_timing)
            resumed.require("S04")
            self.assertEqual(good, {p: digest(p) for p in good})
            expected = pd.read_parquet(self.contexts[1].data / "player_match.parquet")
            self.compare(expected, pd.read_parquet(resumed.data / "player_match.parquet"), ["row_id"])
            self.assertFalse(list(resumed.out.glob("checkpoints/*.lock")))
            write_json({"status": "passed", "child_exit": 73, "partial_stage_completed": False,
                        "takeover": "explicit only after owned child exited", "partition_resume": False,
                        "orphan_scratch_auto_deleted": False}, self.review / "interruption.json")

    def test_upload_archive_notebook_and_source_are_bound(self):
        nb = nbformat.read(ROOT / "notebooks/PUBG_COURSEWORK.ipynb", as_version=4)
        self.assertEqual((len(nb.cells), sum(c.cell_type == "code" for c in nb.cells)), (48, 16))
        self.assertFalse(any(c.outputs for c in nb.cells if c.cell_type == "code"))
        h = hashlib.sha256()
        for p in sorted((ROOT / "src").glob("*.py")):
            h.update(p.name.encode()); h.update(p.read_bytes())
        self.assertTrue(any(h.hexdigest() in c.source for c in nb.cells))
        with zipfile.ZipFile(ROOT / "kaggle_code.zip") as archive:
            self.assertIsNone(archive.testzip())
            names = archive.namelist()
            self.assertEqual(len(names), len(set(names)))
            self.assertEqual(len(names), len(code_files(ROOT)))
            self.assertFalse(any(n.startswith(("tests/", "data/", "outputs/", "artifacts/")) for n in names))
            for name in names:
                self.assertEqual(archive.read(name), (ROOT / name).read_bytes(), name)


if __name__ == "__main__":
    unittest.main()
