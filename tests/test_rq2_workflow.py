"""Small synthetic regression: aggregation parity, resume, decisions and mode keys."""
import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from matplotlib import image as mpimg

from src.analysis.rq2_workflow import (aggregate_profiles, load_profiles, retention_table,
                                       diagnostics, final_clustering)
from src.analysis.clustering import execute_rq2_clustering as real_execute_rq2_clustering
from src.features.profiles import build_player_behavioral_profiles, profile_keys
from src.data.io import atomic_write_json
from src.utils.config import load_config
from src.utils.hashing import hash_file


class TestRQ2Workflow(unittest.TestCase):
    def test_profiles_resume_gates_and_three_mode_strategies(self):
        rng = np.random.RandomState(42)
        records = []
        for mode in ('Solo', 'Duo'):
            for player in range(12):
                for game in range(1 + player % 5):
                    kills = game % 3
                    records.append(dict(match_id=f'{mode}_{player}_{game}', player_name=f'p{player}', team_size_mode=mode, match_mode='tpp',
                        party_size=1 if mode == 'Solo' else 2, player_kills=kills,
                        player_dmg=float(rng.uniform(0, 200)), damage_per_kill=100. if kills else np.nan,
                        player_dist_walk=float(rng.uniform(10, 900)), player_dist_ride=float(player * 20),
                        walk_ratio=.6, player_assists=player % 2, player_dbno=kills, assist_ratio=.3,
                        early_kill_ratio=.3 if kills else np.nan, mid_kill_ratio=.4 if kills else np.nan,
                        late_kill_ratio=.3 if kills else np.nan, early_kills=int(kills > 0),
                        phase_eligible_kill_count=kills if kills else np.nan,
                        timing_coverage_status='event_count_exact' if kills else 'confirmed_no_kill_no_event',
                        player_survive_time=500. + player, normalized_placement=player / 12.,
                        team_placement=player + 1))
        frame = pd.DataFrame(records)
        frame = pd.concat([frame, frame.iloc[:1].assign(player_name=' '),
                           frame.iloc[:1].assign(player_name=None)], ignore_index=True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {name: root / name for name in ('processed', 'interim', 'tables', 'figures', 'manifests', 'checkpoints', 'temp_dir')}
            for path in paths.values():
                path.mkdir()
            source = paths['processed'] / 'player_match_features.parquet'
            frame.to_parquet(source, row_group_size=7, index=False)
            split_path = paths['interim'] / 'split_assignments.parquet'
            split_frame = frame[['match_id']].drop_duplicates().assign(
                split=lambda x: np.where(x['match_id'].str.endswith('_4'), 'test', 'train'))
            split_frame.to_parquet(split_path, index=False)
            atomic_write_json(paths['manifests'] / 'mode_analysis.json', {
                'recommended_rq2_strategy': 'player_mode', 'scope': 'development',
                'source_checksum': hash_file(source), 'split_checksum': hash_file(split_path),
            })
            cfg = load_config()
            cfg['rq2']['device'] = 'cpu'  # Synthetic CPU regression, not a GPU claim.
            cfg['rq2']['mode_strategy'] = None
            cfg['runtime']['duckdb'] = {'memory_limit': '256MB', 'threads': 1}
            with self.assertRaisesRegex(ValueError, 'mode_strategy'):
                load_profiles(cfg, paths)
            cfg['rq2'].update(mode_decision_reason='Synthetic test only', minimum_games_threshold=1,
                min_games_candidates=[1, 2, 3], candidate_k_range=[2, 3], n_clusters=2,
                n_clusters_by_mode={'Solo': 2, 'Duo': 2}, selection_reason='Synthetic test only')
            for strategy in ('overall', 'player_mode', 'per_mode'):
                with self.subTest(strategy=strategy):
                    cfg['rq2']['mode_strategy'] = strategy
                    profiles, outcomes = load_profiles(cfg, paths)
                    development_matches = set(split_frame.loc[split_frame['split'] != 'test', 'match_id'])
                    expected = build_player_behavioral_profiles(
                        frame[frame['match_id'].isin(development_matches)], group_by_mode=strategy != 'overall')
                    for actual, reference in zip((profiles, outcomes), expected):
                        keys = profile_keys(actual)
                        actual = actual.sort_values(keys).reset_index(drop=True)
                        reference = reference.sort_values(keys).reset_index(drop=True)[actual.columns]
                        pd.testing.assert_frame_equal(actual, reference, check_dtype=False, atol=1e-10, rtol=1e-10)
                    with patch('src.analysis.rq2_workflow.aggregate_profiles', side_effect=AssertionError('Unexpected rebuild')):
                        load_profiles(cfg, paths)
                    retention_table(profiles, cfg, paths)
                    cfg['rq2']['minimum_games_threshold'] = None
                    with self.assertRaisesRegex(ValueError, 'minimum_games_threshold'):
                        diagnostics(profiles, cfg, paths)
                    cfg['rq2']['minimum_games_threshold'] = 1
                    diagnostic_table = diagnostics(profiles, cfg, paths)
                    self.assertFalse(diagnostic_table.empty)
                    self.assertTrue({'inertia', 'silhouette_score', 'davies_bouldin_score',
                                     'min_cluster_share', 'max_cluster_share',
                                     'seed_stability_ari'}.issubset(diagnostic_table.columns))
                    if strategy != 'per_mode':
                        cfg['rq2']['n_clusters'] = None
                        with self.assertRaisesRegex(ValueError, 'k_diagnostics.csv'):
                            final_clustering(profiles, outcomes, cfg, paths)
                        cfg['rq2']['n_clusters'] = 2
                    cfg['rq2']['minimum_games_threshold'] = 2
                    with self.assertRaisesRegex(ValueError, 'rerun diagnostics'):
                        final_clustering(profiles, outcomes, cfg, paths)
                    cfg['rq2']['minimum_games_threshold'] = 1
                    artifacts = final_clustering(profiles, outcomes.sample(frac=1, random_state=1), cfg, paths)
                    self.assertTrue(all(path.is_file() for path in artifacts.values()))
                    full_profiles = pd.read_parquet(paths['processed'] / 'player_profile_features.parquet')
                    self.assertGreater(full_profiles['games_played'].sum(), profiles['games_played'].sum())
                    decisions = json.loads((paths['manifests'] / 'rq2_decisions.json').read_text(encoding='utf-8'))
                    self.assertEqual(decisions['selection_scope'], 'development: train+validation only')
                    self.assertIn('no heldout generalization', decisions['claim_scope'])
                    if strategy == 'overall':
                        diagnostic_path = paths['tables'] / 'k_diagnostics.csv'
                        original = diagnostic_path.read_bytes()
                        diagnostic_path.write_bytes(original + b'\n')
                        with self.assertRaisesRegex(ValueError, 'rerun diagnostics'):
                            final_clustering(profiles, outcomes, cfg, paths)
                        diagnostic_path.write_bytes(original)
                    assignment_paths = [p for p in artifacts.values() if p.name == 'cluster_assignments.csv']
                    self.assertEqual(sum(len(pd.read_csv(p)) for p in assignment_paths), len(profiles))
                    for path in assignment_paths:
                        keys = ['player_name'] + (['team_size_mode'] if strategy != 'overall' else [])
                        self.assertFalse(pd.read_csv(path).duplicated(keys).any())
                    if strategy == 'per_mode':
                        solo_path = paths['tables'] / 'rq2' / 'Solo' / 'cluster_assignments.csv'
                        duo_path = paths['tables'] / 'rq2' / 'Duo' / 'cluster_assignments.csv'
                        solo_before = solo_path.read_bytes()
                        duo_path.write_bytes(duo_path.read_bytes() + b'\n')
                        rebuilt_modes = []
                        def tracked_execute(*args, **kwargs):
                            rebuilt_modes.append(Path(args[3]).name)
                            return real_execute_rq2_clustering(*args, **kwargs)
                        with patch('src.analysis.rq2_workflow.execute_rq2_clustering', side_effect=tracked_execute):
                            final_clustering(profiles, outcomes, cfg, paths)
                        self.assertEqual(rebuilt_modes, ['Duo'])
                        self.assertEqual(solo_path.read_bytes(), solo_before)
            # Execute notebook 07 stage cells in a fresh scope; no bootstrap,
            # network, real data, or All-in-One execution is involved.
            project = Path(__file__).resolve().parents[1]
            notebook = json.loads((project / 'notebooks/07_rq2_clustering.ipynb').read_text(encoding='utf-8'))
            notebook_text = json.dumps(notebook, ensure_ascii=False)
            self.assertIn('BẢNG 07-O', notebook_text)
            self.assertFalse(any(token in notebook_text for token in ('Ã¡', 'Ä‘', 'Æ°', 'á»')))
            scope = {'paths': paths, 'PROJECT_ROOT': root}
            with patch('src.utils.config.load_config', return_value=cfg), \
                    patch('src.utils.config.resolve_paths', return_value=paths), \
                    patch('matplotlib.pyplot.show'):
                for cell in notebook['cells']:
                    if cell['cell_type'] == 'code' and not cell.get('metadata', {}).get('tags'):
                        exec(compile(''.join(cell['source']), 'notebook07-synthetic', 'exec'), scope)
            manifest = json.loads((paths['checkpoints'] / 'checkpoint_manifest.json').read_text(encoding='utf-8'))
            record = manifest['stages']['notebook/07_rq2_clustering.ipynb']
            self.assertEqual(record['status'], 'completed')
            self.assertTrue(record['checksums'])
            catalog = pd.read_csv(paths['tables'] / 'rq2_figure_catalog.csv')
            self.assertEqual(set(catalog['figure_id']), {'07-01', '07-02', '07-03', '07-04', '07-05', '07-06'})
            self.assertTrue(catalog[['caption', 'how_to_read', 'limitation']].notna().all().all())
            figures = list(paths['figures'].rglob('*.png'))
            self.assertEqual(len(figures), 10)
            self.assertTrue(all(path.stat().st_size > 1000 for path in figures))
            for path in figures:
                pixels = mpimg.imread(path)
                self.assertGreaterEqual(min(pixels.shape[:2]), 400)
                self.assertTrue(np.isfinite(pixels).all())
            for mode in ('Solo', 'Duo'):
                status = pd.read_csv(paths['tables'] / 'rq2' / mode / 'clustering_robustness.csv')
                expected = {'C1_Main_KMeans', 'C2_Hierarchical_vs_KMeans',
                            'C3_Games_Played_Sensitivity', 'C4_Min_Games_Sensitivity',
                            'C5_Outcome_Comparison'}
                self.assertTrue(expected.issubset(set(status['comparison'])))
                self.assertTrue(status.loc[status['comparison'].isin(expected), ['status', 'reason']].notna().all().all())
            resource = json.loads((paths['manifests'] / 'rq2_resource_audit.json').read_text(encoding='utf-8'))
            self.assertIn('available_ram_gb', resource['full_descriptive_fit']['runtime'])
            from src.evaluation.finalize import select_rq2_results, build_final_results_manifest, verify_final_manifest_integrity
            runs, selected = select_rq2_results(paths, cfg)
            self.assertEqual(set(runs), {'rq2/Solo', 'rq2/Duo'})
            final_path = paths['manifests'] / 'final_results_manifest.json'
            locked = build_final_results_manifest(root, root, runs, final_path, rq2_artifacts=selected,
                selected_artifacts={"tables": {'rq2/'+key: file for key, file in selected.items() if file.suffix == '.csv'}})
            self.assertIn('rq2/Solo/cluster_profile.csv', locked['tables'])
            self.assertIn('rq2/Duo/cluster_profile.csv', locked['tables'])
            self.assertNotIn('cluster_profile.csv', locked['tables'])  # stale overall table remains on disk, not official
            self.assertTrue(verify_final_manifest_integrity(final_path)[0])
            cfg['rq2']['device'] = 'cuda'
            with self.assertRaisesRegex(ValueError, 'config differs'):
                select_rq2_results(paths, cfg)
            cfg['rq2']['device'] = 'cpu'
            # Corrupted persisted profiles must be rebuilt, not trusted on resume.
            (paths['processed'] / 'player_profile_features_development.parquet').write_bytes(b'corrupt')
            rebuilt, _ = load_profiles(cfg, paths)
            self.assertEqual(len(rebuilt), 24)
            # Camera perspective is never accepted as team-size mode.
            frame.drop(columns='team_size_mode').to_parquet(source, index=False)
            with self.assertRaisesRegex(ValueError, 'verified team_size_mode'):
                aggregate_profiles(source, root / 'p.parquet', root / 'o.parquet',
                                   mode='player_mode', temp_dir=paths['temp_dir'])
            aggregate_profiles(source, root / 'p.parquet', root / 'o.parquet', mode='player_mode',
                               mapping={1: 'Solo', 2: 'Duo'}, temp_dir=paths['temp_dir'])
            self.assertEqual(set(pd.read_parquet(root / 'p.parquet').team_size_mode), {'Solo', 'Duo'})


if __name__ == '__main__':
    unittest.main()
