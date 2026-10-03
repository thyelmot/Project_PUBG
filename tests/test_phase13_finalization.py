"""Actual NB11 cells, explicitly nonofficial isolated release, fail-closed G5."""
import copy
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import nbformat
import pandas as pd
import test_phase_d_prediction as core_tests
import test_phase12_comparisons as notebook_tests
from src.analysis.rq1 import run_rq1_analysis
from src.analysis.rq2_workflow import load_profiles, retention_table, diagnostics, final_clustering
from src.data.checkpoints import CheckpointManager
from src.data.io import atomic_write_json, read_json
from src.evaluation.finalize import (CATEGORIES, artifact_metadata, inspect_finalization,
                                    publish_final_release, verify_final_manifest_integrity, export_locked_rq1)
from src.features.registry import FeatureRegistry
from src.utils.hashing import hash_dict, hash_file


class TestPhase13Finalization(unittest.TestCase):
    def test_actual_notebook_release_guards_resume_immutability_and_portability(self):
        fixture = core_tests.TestPhaseDPrediction()
        fixture.setUp()
        runner = notebook_tests.TestPhase12Comparisons()
        try:
            paths = fixture.paths
            cfg = fixture.development_config()
            cfg['rq3']['evaluation']['bootstrap']['replicates'] = 20
            cfg['models']['linear']['sgd_regressor']['enabled'] = False
            cfg['models']['nonlinear_candidates']['hist_gradient_boosting']['enabled'] = False
            cfg['rq2'].update(device='cpu', minimum_games_threshold=1, min_games_candidates=[1, 2],
                candidate_k_range=[2], n_clusters=2, n_clusters_by_mode={'Duo': 2}, selection_reason='Synthetic fixture only')
            for key in ['interim', 'temp_dir']:
                paths[key] = fixture.root/key
                paths[key].mkdir()
            fixture.df['player_name'] = ['p'+str(index % 4) for index in range(len(fixture.df))]
            fixture.df['timing_coverage_status'] = fixture.df.has_kill.map({1: 'event_count_exact', 0: 'confirmed_no_kill_no_event'})
            fixture.df['phase_eligible_kill_count'] = fixture.df.player_kills
            fixture.df['team_placement'] = 2 - fixture.df.normalized_placement
            source = paths['processed']/'player_match_features.parquet'
            fixture.df.drop(columns='split').to_parquet(source, index=False)
            split = paths['interim']/'split_assignments.parquet'
            fixture.df[['match_id', 'split']].drop_duplicates().to_parquet(split, index=False)
            atomic_write_json(paths['manifests']/'mode_analysis.json', {'recommended_rq2_strategy': 'per_mode',
                'scope': 'development', 'source_checksum': hash_file(source), 'split_checksum': hash_file(split)})
            profiles, outcomes = load_profiles(cfg, paths)
            retention_table(profiles, cfg, paths)
            diagnostics(profiles, cfg, paths)
            final_clustering(profiles, outcomes, cfg, paths)
            rq1_path = paths['tables']/'rq1_relationship_summary.csv'
            run_rq1_analysis(fixture.df.loc[fixture.df.split != 'test'], FeatureRegistry(), rq1_path, analysis_scope='development')
            manager = CheckpointManager(paths['checkpoints']/'checkpoint_manifest.json')
            manager.commit('rq1', 'fixture_actual_rq1_execution', {'summary': rq1_path}, metadata={'run_id': 'fixture_rq1_execution_001'})
            atomic_write_json(paths['manifests']/'historical_status.json', {'grade': 'Grade C', 'status': 'blocked', 'reason_code': 'blocked_by_chronology'})
            runner.execute_notebook(fixture, cfg, '09_rq3_prediction.ipynb', approve=True)
            runner.execute_notebook(fixture, cfg, '10_ablation_error_analysis.ipynb')
            exported = export_locked_rq1(paths, cfg)
            self.assertGreater(len(exported), 3)
            self.assertTrue(pd.read_csv(rq1_path).analysis_scope.eq('full_descriptive_locked').all())
            self.assertEqual(export_locked_rq1(paths, cfg), exported)
            recipe = read_json(paths['manifests']/'rq3_selection_lock.json')
            provenance_files = {'source_inventory': {'coverage_status': 'synthetic_fixture', 'sources': []},
                'cohort': {'scope': 'synthetic', 'rows': 120, 'matches': 30},
                'feature_registry': {'features': [entry.name for entry in FeatureRegistry().list_all()]},
                'decisions': recipe['decision'], 'environment': {'python_version': 'fixture', 'packages': {'fixture': True}},
                'leakage_checks': {'status': 'passed', 'code_hash': recipe['code_hash'], 'tests': ['isolated NB09/NB10 G4 train-only fixture']},
                'descriptive_design': read_json(paths['manifests']/'full_descriptive_design_receipt.json'),
                'chronology': {'grade': 'Grade C', 'reason': 'fixture has no temporal evidence'}}
            committed_provenance = {'split': split}
            for key, value in provenance_files.items():
                file = paths['manifests']/('fixture_'+key+'.json')
                atomic_write_json(file, value)
                committed_provenance[key] = file
            manager.commit('fixture_provenance', 'explicit_fixture_evidence', committed_provenance)
            stages = manager.load_manifest()['stages']
            selection = {'format_version': '1.0', 'approved': True, 'approved_by': 'isolated synthetic reviewer, NOT production',
                'data_scope': 'synthetic_fixture', 'config_hash': hash_dict(cfg), 'g4_hash': recipe['recipe_hash'],
                'stage_signatures': {key: stages[key]['signature'] for key in ['rq1', 'rq2_clustering', 'rq3_prediction', 'ablation_error', 'fixture_provenance']},
                'artifacts': {c: {} for c in CATEGORIES}, 'figure_metadata': {},
                'provenance': {key: key for key in committed_provenance if key != 'chronology'},
                'chronology': {'grade': 'Grade C', 'artifact': 'chronology'}}
            for stage in selection['stage_signatures']:
                for artifact, relative in stages[stage]['artifacts'].items():
                    file = (manager.manifest_path.parent/relative).resolve()
                    category = ('metadata' if stage == 'fixture_provenance' else 'figures' if file.suffix == '.png'
                        else 'predictions' if file.suffix == '.parquet' and file.name.startswith('predictions_final_')
                        else 'models' if file.suffix == '.joblib' else 'tables' if file.suffix == '.csv' else 'metadata')
                    key = artifact if stage == 'fixture_provenance' else stage+'/'+artifact
                    selection['artifacts'][category][key] = {'stage': stage, 'artifact': artifact, 'sha256': hash_file(file)}
            # Use only one verified figure, not unselected development plots.
            selection['artifacts']['figures'] = {'forest': selection['artifacts']['figures']['ablation_error/figure_forest']}
            selection['figure_metadata']['forest'] = {'research_question': 'RQ3', 'source_experiment': 'p2_ols_no_direct_survival',
                'source_table': 'ablation_error/comparisons', 'purpose': 'Paired delta/CI fixture validation',
                'caption': 'Fixture CPU, 20 dòng/5 trận; CI chứa 0 không khẳng định chiều cải thiện; không kết quả PUBG.',
                'scope': 'synthetic_fixture', 'sampling': {'sampled': False}, 'report_ready': False}
            receipt = paths['manifests']/'finalization_selection.json'
            with self.assertRaisesRegex(ValueError, 'pending'):
                inspect_finalization(paths, cfg)
            atomic_write_json(receipt, selection)
            checked = inspect_finalization(paths, cfg)
            self.assertTrue(checked['fixture'])
            self.assertGreater(len(checked['matrix']), 20)
            bad_variants = []
            bad = copy.deepcopy(selection); bad['data_scope'] = 'development'; bad_variants.append((bad, 'Development'))
            bad = copy.deepcopy(selection); bad['stage_signatures']['rq1'] = 'stale'; bad_variants.append((bad, 'stale'))
            bad = copy.deepcopy(selection); bad['artifacts']['predictions'] = {}; bad_variants.append((bad, 'predictions missing'))
            bad = copy.deepcopy(selection); bad['figure_metadata'] = {}; bad_variants.append((bad, 'Figure manifest'))
            bad = copy.deepcopy(selection); bad['figure_metadata']['forest']['report_ready'] = True; bad_variants.append((bad, 'Synthetic figure'))
            bad = copy.deepcopy(selection); bad['provenance'].pop('leakage_checks'); bad_variants.append((bad, 'provenance missing'))
            bad = copy.deepcopy(selection); bad['artifacts']['tables']['rq1/summary_table']['required_columns'] = ['missing_column']; bad_variants.append((bad, 'schema missing'))
            for bad, message in bad_variants:
                atomic_write_json(receipt, bad)
                with self.assertRaisesRegex(ValueError, message):
                    inspect_finalization(paths, cfg)
                self.assertFalse((paths['manifests']/'final_results_manifest.json').exists())
            atomic_write_json(receipt, selection)
            fixture.notebook_options = {'PUBG_EXPORT_LOCKED_DESCRIPTIVE': True}
            # Stray model/table must never enter selected release.
            (paths['tables']/'stale_unselected.csv').write_text('bad\n1\n', encoding='utf-8')
            (paths['models']/'stale_unselected.joblib').write_bytes(b'old')
            with patch('src.models.linear.LinearModelWrapper.fit', side_effect=AssertionError('NB11 cannot fit')):
                notebook, scope = runner.execute_notebook(fixture, cfg, '11_finalize_results.ipynb')
            manifest, locked_path = scope['manifest'], scope['release_manifest_path']
            self.assertEqual(manifest['status'], 'fixture_locked')
            self.assertFalse(manifest['report_ready'])
            self.assertTrue(verify_final_manifest_integrity(locked_path)[0])
            self.assertTrue(all('stale_unselected' not in str(item) for c in CATEGORIES for item in manifest[c].values()))
            before = hash_file(locked_path)
            resumed, resumed_path = publish_final_release(paths, cfg)
            self.assertEqual(resumed_path, locked_path)
            missing = copy.deepcopy(selection)
            missing['artifacts']['predictions'] = {}
            atomic_write_json(receipt, missing)
            with self.assertRaisesRegex(ValueError, 'predictions missing'):
                runner.execute_notebook(fixture, cfg, '11_finalize_results.ipynb')
            atomic_write_json(receipt, selection)
            # Overwriting mutable inputs cannot destroy prior release.
            original_rq1 = rq1_path.read_bytes()
            rq1_path.write_text('corrupted canonical\n', encoding='utf-8')
            self.assertTrue(verify_final_manifest_integrity(locked_path)[0])
            with self.assertRaisesRegex(ValueError, 'corrupt'):
                inspect_finalization(paths, cfg)
            self.assertEqual(hash_file(locked_path), before)
            rq1_path.write_bytes(original_rq1)
            selection['approved_by'] += '; second reviewed release'
            atomic_write_json(receipt, selection)
            canonical = paths['manifests']/'final_results_manifest.json'
            canonical_hash = hash_file(canonical)
            from src.evaluation import finalize
            real_publish = finalize.publish_file
            def failing_publish(source, target):
                if 'releases' in Path(target).parts:
                    raise OSError('fixture mount publication failure')
                return real_publish(source, target)
            with patch('src.evaluation.finalize.publish_file', side_effect=failing_publish):
                with self.assertRaisesRegex(OSError, 'publication failure'):
                    publish_final_release(paths, cfg)
            self.assertEqual(hash_file(canonical), canonical_hash)
            self.assertTrue(verify_final_manifest_integrity(locked_path)[0])
            newer, newer_path = publish_final_release(paths, cfg)
            self.assertNotEqual(newer_path, locked_path)
            self.assertTrue(verify_final_manifest_integrity(locked_path)[0])
            self.assertTrue(verify_final_manifest_integrity(newer_path)[0])
            with tempfile.TemporaryDirectory() as portable:
                copied = Path(portable)/manifest['release_id']
                shutil.copytree(locked_path.parent, copied)
                self.assertEqual(verify_final_manifest_integrity(copied/locked_path.name), (True, []))
                original = (copied/manifest['figures']['forest']['path']).read_bytes()
                (copied/manifest['figures']['forest']['path']).write_bytes(b'broken PNG')
                self.assertFalse(verify_final_manifest_integrity(copied/locked_path.name)[0])
                (copied/manifest['figures']['forest']['path']).write_bytes(original)
            evidence = os.environ.get('PUBG_PHASE13_EVIDENCE_DIR')
            if evidence:
                destination = Path(evidence)
                destination.mkdir(parents=True, exist_ok=True)
                nbformat.write(notebook, destination/'11_fixture.ipynb')
                from nbconvert import HTMLExporter
                html, _ = HTMLExporter().from_notebook_node(notebook)
                (destination/'11_fixture.html').write_text(html, encoding='utf-8')
                shutil.copytree(locked_path.parent, destination/'release', dirs_exist_ok=True)
        finally:
            fixture.tearDown()

    def test_empty_invalid_and_legacy_manifests_are_not_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'final.json'
            for value in [{}, {'format_version': '4.0', **{c: {} for c in CATEGORIES}}, {'format_version': '3.0'}]:
                atomic_write_json(path, value)
                self.assertFalse(verify_final_manifest_integrity(path)[0])
            self.assertFalse(verify_final_manifest_integrity(Path(directory)/'missing.json')[0])


if __name__ == '__main__':
    unittest.main()
