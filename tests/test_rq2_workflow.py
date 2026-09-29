"""Small synthetic regression: aggregation parity, resume, decisions and mode keys."""
import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.analysis.rq2_workflow import (aggregate_profiles, load_profiles, retention_table,
                                       diagnostics, final_clustering)
from src.features.profiles import build_player_behavioral_profiles, profile_keys
from src.data.io import atomic_write_json
from src.utils.config import load_config


class TestRQ2Workflow(unittest.TestCase):
    def test_profiles_resume_gates_and_three_mode_strategies(self):
        rng = np.random.RandomState(42)
        records = []
        for mode in ('Solo', 'Duo'):
            for player in range(12):
                for game in range(1 + player % 5):
                    kills = game % 3
                    records.append(dict(player_name=f'p{player}', team_size_mode=mode, match_mode='tpp',
                        party_size=1 if mode == 'Solo' else 2, player_kills=kills,
                        player_dmg=float(rng.uniform(0, 200)), damage_per_kill=100. if kills else np.nan,
                        player_dist_walk=float(rng.uniform(10, 900)), player_dist_ride=float(player * 20),
                        walk_ratio=.6, player_assists=player % 2, player_dbno=kills, assist_ratio=.3,
                        early_kill_ratio=.3 if kills else np.nan, mid_kill_ratio=.4 if kills else np.nan,
                        late_kill_ratio=.3 if kills else np.nan, early_kills=int(kills > 0),
                        player_survive_time=500. + player, normalized_placement=player / 12.,
                        team_placement=player + 1))
        frame = pd.DataFrame(records)
        frame = pd.concat([frame, frame.iloc[:1].assign(player_name=' '),
                           frame.iloc[:1].assign(player_name=None)], ignore_index=True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {name: root / name for name in ('processed', 'tables', 'manifests', 'checkpoints', 'temp_dir')}
            for path in paths.values():
                path.mkdir()
            source = paths['processed'] / 'player_match_features.parquet'
            frame.to_parquet(source, row_group_size=7, index=False)
            atomic_write_json(paths['manifests'] / 'mode_analysis.json', {'recommended_rq2_strategy': 'player_mode'})
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
                    expected = build_player_behavioral_profiles(frame, group_by_mode=strategy != 'overall')
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
                    self.assertFalse(diagnostics(profiles, cfg, paths).empty)
                    if strategy != 'per_mode':
                        cfg['rq2']['n_clusters'] = None
                        with self.assertRaisesRegex(ValueError, 'n_clusters'):
                            final_clustering(profiles, outcomes, cfg, paths)
                        cfg['rq2']['n_clusters'] = 2
                    cfg['rq2']['minimum_games_threshold'] = 2
                    with self.assertRaisesRegex(ValueError, 'rerun diagnostics'):
                        final_clustering(profiles, outcomes, cfg, paths)
                    cfg['rq2']['minimum_games_threshold'] = 1
                    artifacts = final_clustering(profiles, outcomes.sample(frac=1, random_state=1), cfg, paths)
                    self.assertTrue(all(path.is_file() for path in artifacts.values()))
                    assignment_paths = [p for p in artifacts.values() if p.name == 'cluster_assignments.csv']
                    self.assertEqual(sum(len(pd.read_csv(p)) for p in assignment_paths), len(profiles))
                    for path in assignment_paths:
                        keys = ['player_name'] + (['team_size_mode'] if strategy != 'overall' else [])
                        self.assertFalse(pd.read_csv(path).duplicated(keys).any())
            # Execute notebook 07 stage cells in a fresh scope; no bootstrap,
            # network, real data, or All-in-One execution is involved.
            project = Path(__file__).resolve().parents[1]
            notebook = json.loads((project / 'notebooks/07_rq2_clustering.ipynb').read_text(encoding='utf-8'))
            scope = {'paths': paths, 'PROJECT_ROOT': root}
            with patch('src.utils.config.load_config', return_value=cfg), patch('src.utils.config.resolve_paths', return_value=paths):
                for cell in notebook['cells']:
                    if cell['cell_type'] == 'code' and not cell.get('metadata', {}).get('tags'):
                        exec(compile(''.join(cell['source']), 'notebook07-synthetic', 'exec'), scope)
            manifest = json.loads((paths['checkpoints'] / 'checkpoint_manifest.json').read_text(encoding='utf-8'))
            record = manifest['stages']['notebook/07_rq2_clustering.ipynb']
            self.assertEqual(record['status'], 'completed')
            self.assertTrue(record['checksums'])
            from src.evaluation.finalize import select_rq2_results, build_final_results_manifest, verify_final_manifest_integrity
            runs, selected = select_rq2_results(paths, cfg)
            self.assertEqual(set(runs), {'rq2/Solo', 'rq2/Duo'})
            final_path = paths['manifests'] / 'final_results_manifest.json'
            locked = build_final_results_manifest(root, root, runs, final_path, rq2_artifacts=selected)
            self.assertIn('rq2/Solo/cluster_profile.csv', locked['tables'])
            self.assertIn('rq2/Duo/cluster_profile.csv', locked['tables'])
            self.assertNotIn('cluster_profile.csv', locked['tables'])  # stale overall table remains on disk, not official
            self.assertTrue(verify_final_manifest_integrity(final_path)[0])
            cfg['rq2']['device'] = 'cuda'
            with self.assertRaisesRegex(ValueError, 'config differs'):
                select_rq2_results(paths, cfg)
            cfg['rq2']['device'] = 'cpu'
            # Corrupted persisted profiles must be rebuilt, not trusted on resume.
            (paths['processed'] / 'player_profile_features.parquet').write_bytes(b'corrupt')
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
