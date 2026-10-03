"""Canonical 00-12 cells in fresh processes, immutable synthetic inputs only."""
import ast
import base64
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import nbformat
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = sorted((ROOT / "notebooks").glob("[0-1][0-9]_*.ipynb"))


def fixture_selection(paths, cfg):
    """Explicit test approval, from real upstream commits, never a production receipt."""
    from src.data.checkpoints import CheckpointManager
    from src.data.io import atomic_write_json, read_json
    from src.evaluation.finalize import CATEGORIES
    from src.utils.hashing import hash_file, hash_dict
    manager = CheckpointManager(paths["checkpoints"] / "checkpoint_manifest.json")
    recipe = read_json(paths["manifests"] / "rq3_selection_lock.json")
    frame = pd.read_parquet(paths["processed"] / "player_match_features.parquet")
    split = paths["interim"] / "split_assignments.parquet"
    assignments = pd.read_parquet(split)
    assert assignments.match_id.is_unique
    assert frame.row_id.is_unique and len(frame) == 120
    evidence = {
        "source_inventory": paths["manifests"] / "source_inventory.json",
        "split": split,
        "environment": paths["manifests"] / "runtime_snapshot.json",
        "chronology": paths["manifests"] / "chronology_report.json",
        "descriptive_design": paths["manifests"] / "full_descriptive_design_receipt.json",
        "feature_registry": paths["tables"] / "feature_dictionary.csv",
    }
    assert read_json(evidence["chronology"])["grade"] == "Grade C"
    registry = read_json(paths["manifests"] / "rq3_development_registry.json")["experiments"]
    for task in ["s2", "p3"]:
        entries = [entry for entry in registry.values() if entry["task"] == task]
        assert entries and all(entry["status"] == "blocked" and entry["reason_code"] == "blocked_by_chronology"
            and entry.get("metrics") is None for entry in entries)
    records = {
        "cohort": {"scope": "synthetic_fixture", "rows": len(frame), "matches": frame.match_id.nunique()},
        "decisions": recipe["decision"],
        "leakage_checks": {"status": "passed", "code_hash": recipe["code_hash"],
            "tests": ["actual NB02 unique match split", "actual NB03/04 conservation and unique row ID", "NB09 explicit fixture G4 before test"]},
    }
    for key, record in records.items():
        file = paths["manifests"] / ("phase15_fixture_" + key + ".json")
        atomic_write_json(file, record)
        evidence[key] = file
    manager.commit("fixture_provenance", "phase15_synthetic_only", evidence)
    stages = manager.load_manifest()["stages"]
    selected = ["rq1", "rq2_clustering", "rq3_prediction", "ablation_error", "fixture_provenance"]
    selection = {"format_version": "1.0", "approved": True,
        "approved_by": "Phase15 synthetic fixture reviewer; NOT production approval",
        "data_scope": "synthetic_fixture", "config_hash": hash_dict(cfg), "g4_hash": recipe["recipe_hash"],
        "stage_signatures": {stage: stages[stage]["signature"] for stage in selected},
        "artifacts": {category: {} for category in CATEGORIES}, "figure_metadata": {},
        "provenance": {key: key for key in evidence if key != "chronology"},
        "chronology": {"grade": "Grade C", "artifact": "chronology"}}
    for stage in selected:
        for key, relative in stages[stage]["artifacts"].items():
            file = (manager.manifest_path.parent / relative).resolve()
            category = ("metadata" if stage == "fixture_provenance" else "figures" if file.suffix == ".png"
                else "predictions" if file.suffix == ".parquet" and file.name.startswith("predictions_final_")
                else "models" if file.suffix == ".joblib" else "tables" if file.suffix == ".csv" else "metadata")
            name = key if stage == "fixture_provenance" else stage + "/" + key
            selection["artifacts"][category][name] = {"stage": stage, "artifact": key, "sha256": hash_file(file)}
    selection["artifacts"]["figures"] = {"forest": selection["artifacts"]["figures"]["ablation_error/figure_forest"]}
    selection["figure_metadata"]["forest"] = {"research_question": "RQ3", "source_experiment": "p2_ols_no_direct_survival",
        "source_table": "ablation_error/comparisons", "purpose": "Synthetic paired delta and CI audit",
        "caption": "Dữ liệu giả lập CPU; N lấy từ bảng comparisons; không phải kết quả PUBG.",
        "scope": "synthetic_fixture", "sampling": {"sampled": False}, "report_ready": False}
    atomic_write_json(paths["manifests"] / "finalization_selection.json", selection)


def worker(notebook_path, project, output):
    """Execute every code cell, including real bootstrap; mount is the only service mock."""
    import types
    sys.path.insert(0, str(project))
    sys.path.insert(1, str(ROOT / "tests"))
    os.chdir(project)
    colab = types.ModuleType("google.colab")
    colab.drive = types.SimpleNamespace(mount=lambda path: None)
    colab.files = types.SimpleNamespace(download=lambda path: None)
    sys.modules["google.colab"] = colab
    notebook = nbformat.read(notebook_path, as_version=4)
    scope = {"PUBG_INSTALL_DEPENDENCIES": False, "__name__": "__main__"}
    captured = []

    def display(*values, **kwargs):
        for value in values:
            if isinstance(value, pd.DataFrame):
                data = {"text/html": value.to_html(index=False), "text/plain": value.to_string(index=False)}
            elif value.__class__.__name__ == "Image":
                data = {"image/png": base64.b64encode(value.data).decode()}
            elif value.__class__.__name__ == "Markdown":
                data = {"text/markdown": value.data}
            else:
                data = {"text/plain": str(value)}
            captured.append(nbformat.v4.new_output("display_data", data=data))

    with patch("IPython.display.display", side_effect=display):
        for cell in notebook.cells:
            if cell.cell_type != "code":
                continue
            captured.clear()
            stream = io.StringIO()
            print("EXECUTING", notebook_path.name, cell.id, flush=True)
            if notebook_path.name.startswith("09") and "selection_lock = lock_rq3_selection" in cell.source:
                from test_phase11_completion import TestPhase11Completion
                TestPhase11Completion.write_decision(scope["paths"], scope["cfg"])
            if notebook_path.name.startswith("11") and "inspected = inspect_finalization" in cell.source:
                fixture_selection(scope["paths"], scope["cfg"])
            with redirect_stdout(stream), redirect_stderr(stream):
                exec(compile(cell.source, f"{notebook_path.name}:{cell.id}", "exec"), scope)
            cell.outputs = [nbformat.v4.new_output("stream", name="stdout", text=stream.getvalue())] + list(captured)
            cell.execution_count = 1
            if "storage-options" in cell.metadata.get("tags", []):
                scope.update(PUBG_STORAGE_MODE="drive", PUBG_DRIVE_PROJECT_ROOT=str(project),
                    PUBG_REQUIRE_EXISTING_PROJECT=True, PUBG_RUNTIME_TEMP_DIR=str(project.parent / "temp"),
                    PUBG_EXPORT_LOCKED_DESCRIPTIVE=True, PUBG_SUMMARY_ALLOW_FIXTURE=True,
                    PUBG_SUMMARY_MANIFEST=str(project / "artifacts/manifests/final_results_manifest.json"),
                    PUBG_SUMMARY_CODE_ROOT=str(project))
    nbformat.validate(notebook)
    nbformat.write(notebook, output / notebook_path.name)
    from nbconvert import HTMLExporter
    html, _ = HTMLExporter().from_notebook_node(notebook)
    (output / (notebook_path.stem + ".html")).write_text(html, encoding="utf-8")
    if notebook_path.name.startswith("12"):
        assert len(scope["summary_views"]) == 12
    else:
        from src.data.checkpoints import CheckpointManager
        stage = CheckpointManager(scope["paths"]["checkpoints"] / "checkpoint_manifest.json").load_manifest()["stages"]["notebook/" + notebook_path.name]
        assert stage["status"] == "completed", stage


class TestPhase15Integration(unittest.TestCase):
    def test_notebook_schema_ast_and_accented_headings(self):
        self.assertEqual(len(NOTEBOOKS), 13)
        for file in NOTEBOOKS:
            notebook = nbformat.read(file, as_version=4)
            nbformat.validate(notebook)
            for cell in notebook.cells:
                self.assertTrue(cell.source.strip(), (file.name, cell.id))
                if cell.cell_type == "code":
                    ast.parse(cell.source)
                elif cell.source.startswith("#"):
                    self.assertTrue(any(ord(char) > 127 for char in cell.source.splitlines()[0]), (file.name, cell.id))

    def test_actual_00_12_fresh_process_raw_to_locked_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "Project_PUBG"
            for folder in ["src", "configs"]:
                shutil.copytree(ROOT / folder, project / folder, ignore=shutil.ignore_patterns("__pycache__"))
            for name in ["requirements.txt", "README.md", "PUBG_RESEARCH_SPEC.md", "PUBG_IMPLEMENTATION_PLAN.md", "TEAM_DRIVE.md"]:
                shutil.copy2(ROOT / name, project / name)
            modifications = {
                "runtime.yaml": {"mode": "development", "duckdb": {"threads": 1, "memory_limit": "256MB", "temp_directory": str(project.parent / "temp")}},
                "rq2.yaml": {"device": "cpu", "minimum_games_threshold": 1, "min_games_candidates": [1, 2], "candidate_k_range": [2],
                    "n_clusters": 2, "n_clusters_by_mode": {"Duo": 2}, "selection_reason": "Synthetic fixture only; not a research decision", "party_size_mapping": {2: "Duo"}},
                "rq3.yaml": {"device": "cpu", "split": {"strategy": "auto", "train_ratio": .6, "validation_ratio": .2, "test_ratio": .2, "group_column": "match_id", "random_state": 42}},
            }
            for name, updates in modifications.items():
                file = project / "configs" / name
                config = yaml.safe_load(file.read_text(encoding="utf-8"))
                config.update(updates)
                file.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
            for name in ["features.yaml", "preprocessing.yaml", "models.yaml", "rq3.yaml"]:
                file = project / "configs" / name
                config = yaml.safe_load(file.read_text(encoding="utf-8"))
                if name == "features.yaml":
                    for prefix in ["event_time_unit", "enemy_kill_eligibility", "min_valid_duration"]:
                        config["combat_timing"].update({prefix + "_status": "verified", prefix + "_evidence": "Synthetic fixture contract only"})
                elif name == "preprocessing.yaml":
                    config["chronology"]["grade_assignment"] = "Grade C"  # Explicit fixture downgrade tests the conditional branch.
                elif name == "models.yaml":
                    config["linear"]["sgd_regressor"]["enabled"] = False
                    for candidate in config["nonlinear_candidates"].values():
                        candidate["enabled"] = False
                else:
                    config["evaluation"]["bootstrap"]["replicates"] = 20
                file.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
            raw = project / "data/raw"
            raw.mkdir(parents=True)
            rows, events = [], []
            for match in range(30):
                for player in range(4):
                    kills = (match + player) % 4
                    rows.append({"date": f"2017-11-{1 + match % 3:02d}T12:00:00+0000", "game_size": 4,
                        "match_id": f"m{match}", "match_mode": "tpp", "party_size": 2,
                        "player_assists": player % 2, "player_dbno": kills, "player_dist_ride": 20. * player,
                        "player_dist_walk": 100. + 20 * player + match, "player_dmg": kills * 100. + player,
                        "player_kills": kills, "player_name": f"p{player}", "player_survive_time": 1200. - player * 100,
                        "team_id": f"t{player // 2}", "team_placement": 1 + player // 2})
                    for kill in range(kills):
                        events.append({"match_id": f"m{match}", "time": 400. * kill, "killer_name": f"p{player}",
                            "victim_name": f"p{(player + kill + 1) % 4}", "killed_by": "M416"})
            for index in range(2):
                pd.DataFrame(rows[index::2]).to_csv(raw / f"agg_match_stats_{index}.csv", index=False)
                pd.DataFrame(events[index::2]).to_csv(raw / f"kill_match_stats_{index}.csv", index=False)
            output = project / "reports/appendix/phase15_fixture"
            output.mkdir(parents=True)
            env = dict(os.environ, MPLBACKEND="Agg", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
            env.pop("COLAB_RELEASE_TAG", None)
            from src.utils.hashing import hash_file
            before = {file.name: hash_file(file) for file in raw.iterdir()}
            for notebook in NOTEBOOKS:
                run = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(notebook), str(project), str(output)],
                    cwd=project, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
                (output / (notebook.stem + ".log")).write_text(run.stdout + run.stderr, encoding="utf-8")
                if os.environ.get("PUBG_PHASE15_EVIDENCE_DIR"):
                    shutil.copytree(output, Path(os.environ["PUBG_PHASE15_EVIDENCE_DIR"]) / "notebooks", dirs_exist_ok=True)
                self.assertEqual(run.returncode, 0, (run.stdout + run.stderr)[-7000:])
                executed = nbformat.read(output / notebook.name, as_version=4)
                displays = [item.get('data', {}) for cell in executed.cells for item in cell.get('outputs', [])]
                self.assertTrue(any('text/html' in item for item in displays), notebook.name)
                if 1 <= int(notebook.name[:2]) <= 7:
                    self.assertTrue(any('image/png' in item for item in displays), notebook.name)
            self.assertEqual(before, {file.name: hash_file(file) for file in raw.iterdir()})
            visualization = pd.read_csv(project / "reports/tables/eda_visualization_sample.csv")
            games_distribution = pd.read_csv(project / "reports/tables/eda_matches_per_player_distribution.csv")
            self.assertEqual(games_distribution.to_dict("records"), [{"games": 24, "players": 4}])
            teams_distribution = pd.read_csv(project / "reports/tables/eda_teams_per_match_distribution.csv")
            self.assertEqual(teams_distribution.to_dict("records"), [{"teams": 2, "matches": 24}])
            self.assertEqual(len(visualization), 96)  # All train/validation rows, no locked test.
            self.assertFalse({"player_name", "row_id"} & set(visualization.columns))
            catalog = pd.read_csv(project / "reports/tables/eda_catalog_status.csv")
            for sources in catalog.source_table:
                for source in sources.split(";"):
                    self.assertTrue((project / "reports/tables" / source).is_file(), source)
            scatter = catalog[catalog.group.isin(["behavior_vs_survival", "behavior_vs_placement"])]
            self.assertEqual(set(scatter.source_table), {"eda_visualization_sample.csv"})
            self.assertEqual(set(scatter.sample_n), {96})
            self.assertEqual(set(scatter.sample_seed), {42})
            self.assertTrue(scatter.caption.str.contains("Scope=development; N scope=96; n vẽ=96", regex=False).all())
            self.assertTrue(scatter.how_to_read.str.contains("không phải tác động nhân quả", regex=False).all())
            mode_summary = pd.read_csv(project / "reports/tables/eda_mode_comparison_summary.csv")
            self.assertFalse(mode_summary.empty)  # Canonical 'Duo' must not be dropped by lowercase-only SQL.
            mode_manifest = json.loads((project / "artifacts/manifests/mode_analysis.json").read_text(encoding="utf-8"))
            self.assertEqual(mode_manifest["sample_n"], 96)
            figure_catalog = pd.read_csv(project / "reports/tables/eda_figure_catalog.csv")
            self.assertEqual(len(figure_catalog), 14)
            self.assertTrue(figure_catalog.path.map(lambda file: Path(file).is_file()).all())
            self.assertEqual(set(figure_catalog.n_scope), {96})
            self.assertTrue(figure_catalog.caption.str.contains("Scope=development", regex=False).all())
            sampled = figure_catalog[figure_catalog.sampled]
            self.assertEqual(set(sampled.sample_seed), {42})
            self.assertTrue(sampled.sampling_rule.str.contains("[Rr]eservoir").all())
            for sources in figure_catalog.source_table:
                for source in sources.split(";"):
                    self.assertTrue((project / "reports/tables" / source).is_file(), source)
            from src.evaluation.finalize import load_locked_release
            rq2_figures = pd.read_csv(project / "reports/tables/rq2_figure_catalog.csv")
            self.assertEqual(set(rq2_figures.n_profiles), {4})
            k_sampling = json.loads(rq2_figures.set_index("figure_id").loc["07-02", "sampling_details"])
            self.assertEqual(k_sampling[0]["diagnostic_sample_n"], 4)
            release = load_locked_release(project / "artifacts/manifests/final_results_manifest.json", allow_fixture=True)
            self.assertTrue(release["fixture"])
            if os.environ.get("PUBG_PHASE15_EVIDENCE_DIR"):
                destination = Path(os.environ["PUBG_PHASE15_EVIDENCE_DIR"])
                for key in ["tables", "figures"]:
                    shutil.copytree(project / ("reports/tables" if key == "tables" else "figures"), destination / key, dirs_exist_ok=True)
                for key in ["manifests", "interim", "processed"]:
                    source = project / ("artifacts/manifests" if key == "manifests" else "data/" + key)
                    shutil.copytree(source, destination / "audit_sources" / key, dirs_exist_ok=True)
                snapshot = release["root"] / "releases" / release["manifest"]["release_id"]
                shutil.copytree(snapshot, destination / "release", dirs_exist_ok=True)


if __name__ == "__main__":
    if len(sys.argv) == 4:
        sys.stdout.reconfigure(encoding="utf-8")
        worker(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        unittest.main()
