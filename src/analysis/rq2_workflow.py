"""Disk-backed profiles and explicit decision gates for notebook 07."""
from pathlib import Path
from itertools import combinations
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score
from src.data.io import (get_duckdb_connection, copy_query_to_parquet, read_parquet_df,
                         atomic_write_csv, atomic_write_json, read_json)
from src.data.checkpoints import CheckpointManager
from src.utils.hashing import hash_file, hash_dict
from src.models.compute import make_kmeans, compute_info
from src.features.profiles import profile_keys, filter_profiles_by_retention
from src.analysis.clustering import (CORE_PROFILE_FEATURES, prepare_clustering_matrix,
                                     run_k_diagnostics, execute_rq2_clustering)


def positive_int(value, name, minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError(f"Set {name} to an integer >= {minimum} in configs/rq2.yaml; no automatic default")
    return value


def validate_mode(cfg, paths):
    rq2 = cfg['rq2']
    if rq2.get('algorithm') != 'kmeans':
        raise ValueError('This workflow implements KMeans only; changing estimator requires a separate review')
    mode = rq2.get('mode_strategy')
    if mode not in ('overall', 'player_mode', 'per_mode'):
        raise ValueError('Review notebook 05 mode_summary.csv and mode_analysis.json, then set mode_strategy: overall/player_mode/per_mode')
    if rq2.get('profile_level') not in ('auto', mode):
        raise ValueError('profile_level conflicts with mode_strategy')
    if not str(rq2.get('mode_decision_reason') or '').strip():
        raise ValueError('Record mode_decision_reason based on behavioral EDA before profiling')
    evidence = paths['manifests'] / 'mode_analysis.json'
    if not evidence.is_file():
        raise FileNotFoundError('Run notebook 05 first: mode_analysis.json is missing')
    return mode, read_json(evidence)


def aggregate_profiles(source, profile_path, outcome_path, *, mode, mapping=None,
                       temp_dir=None, memory_limit='4GB', threads=4):
    """Preserve existing profile formulas, ddof=1 and legacy ratio fill policy.

    No player-match table is materialized in Pandas. Only reduced profiles are read later.
    """
    con = get_duckdb_connection(temp_dir, memory_limit, threads)
    try:
        if mode not in ('overall', 'player_mode', 'per_mode'):
            raise ValueError('Unknown mode strategy')
        safe_source = Path(source).resolve().as_posix().replace("'", "''")
        con.execute(f"CREATE VIEW input AS SELECT * FROM read_parquet('{safe_source}')")
        columns = {r[0] for r in con.execute('DESCRIBE input').fetchall()}
        mode_sql = ''
        keys = ['player_name']
        if mode != 'overall':
            keys.append('team_size_mode')
            if 'team_size_mode' in columns:
                mode_sql = ', team_size_mode'
            elif mapping and 'party_size' in columns:
                cases = []
                for size, label in mapping.items():
                    if str(size) not in ('1', '2', '3', '4') or label not in ('Solo', 'Duo', 'Squad'):
                        raise ValueError('Verify party_size_mapping: integer sizes and Solo/Duo/Squad labels required')
                    cases.append(f"WHEN party_size = {int(size)} THEN '{label}'")
                mode_sql = ', CASE ' + ' '.join(cases) + ' END AS team_size_mode'
            else:
                raise ValueError('Missing verified team_size_mode; set party_size_mapping after schema verification. match_mode is not team size.')
        means = {'player_kills': 'mean_kills', 'player_dmg': 'mean_damage',
                 'damage_per_kill': 'mean_damage_per_kill', 'player_dist_walk': 'mean_walk_distance',
                 'player_dist_ride': 'mean_ride_distance', 'walk_ratio': 'mean_walk_ratio',
                 'player_assists': 'mean_assists', 'player_dbno': 'mean_dbno', 'assist_ratio': 'mean_assist_ratio'}
        fields = list(means) + ['early_kill_ratio', 'mid_kill_ratio', 'late_kill_ratio', 'early_kills',
                               'player_survive_time', 'normalized_placement', 'team_placement']
        missing = set(fields + ['player_name']) - columns
        if missing:
            raise ValueError(f'Missing required profile columns: {sorted(missing)}')
        con.execute('CREATE VIEW valid AS SELECT player_name, ' + ', '.join(fields) + mode_sql +
                    " FROM input WHERE player_name IS NOT NULL AND length(trim(player_name)) > 0")
        if mode != 'overall' and con.execute("SELECT count(*) FROM valid WHERE team_size_mode IS NULL OR team_size_mode NOT IN ('Solo','Duo','Squad')").fetchone()[0]:
            raise ValueError('Unmapped team_size_mode; verify mapping instead of dropping rows')
        aggregates = [
            'count(*) AS games_played',
            'count(*) FILTER (WHERE player_kills > 0) AS kill_active_matches',
            'count(*) FILTER (WHERE player_assists > 0 OR player_dbno > 0) AS support_active_matches',
            'count(*) FILTER (WHERE early_kill_ratio IS NOT NULL OR early_kills > 0) AS timing_observed_matches'
        ]
        for col, alias in means.items():
            expr = f'avg({col})'
            if col in ('damage_per_kill', 'walk_ratio', 'assist_ratio'):
                expr = f'coalesce({expr}, 0.0)'
            aggregates.append(f'{expr} AS {alias}')
        aggregates += ['coalesce(stddev_samp(player_kills), 0.0) AS std_kills',
                       'coalesce(stddev_samp(player_dmg), 0.0) AS std_damage']
        for phase in ('early', 'mid', 'late'):
            aggregates.append(f'coalesce(avg({phase}_kill_ratio) FILTER (WHERE player_kills > 0), 0.0) AS avg_{phase}_kill_ratio')
        aggregates += ['avg(CASE WHEN early_kills > 0 THEN 1.0 ELSE 0.0 END) AS early_combat_match_ratio',
                       'avg(player_survive_time) AS mean_survive_time',
                       'avg(normalized_placement) AS mean_normalized_placement',
                       'avg(CASE WHEN team_placement = 1 THEN 1.0 ELSE 0.0 END) AS win_rate']
        con.execute('CREATE TABLE aggregated AS SELECT ' + ', '.join(keys + aggregates) + ' FROM valid GROUP BY ' + ', '.join(keys))
        count = con.execute('SELECT count(*) FROM aggregated').fetchone()[0]
        denominator_cols = ['kill_active_matches', 'support_active_matches', 'timing_observed_matches']
        for destination, names in ((profile_path, denominator_cols + CORE_PROFILE_FEATURES),
                                   (outcome_path, ['mean_survive_time', 'mean_normalized_placement', 'win_rate'])):
            query = 'SELECT ' + ', '.join(keys + ['games_played'] + names) + ' FROM aggregated ORDER BY ' + ', '.join(keys)
            copy_query_to_parquet(con, query, destination, expected_rows=count)
        return count
    finally:
        con.close()


def load_profiles(cfg, paths):
    mode, evidence = validate_mode(cfg, paths)
    source = paths['processed'] / 'player_match_features.parquet'
    profile_path = paths['processed'] / 'player_profile_features.parquet'
    outcome_path = paths['processed'] / 'player_profile_outcomes.parquet'
    signature = hash_dict({'source': hash_file(source), 'mode': mode,
                           'mapping': cfg['rq2'].get('party_size_mapping'),
                           'implementation': hash_file(Path(__file__)), 'version': 1})
    manager = CheckpointManager(paths['checkpoints'] / 'checkpoint_manifest.json')
    if not manager.is_compatible('rq2_profiles', signature):
        manager.invalidate_descendants('rq2_profiles')
        manager.mark_running('rq2_profiles', signature)
        aggregate_profiles(source, profile_path, outcome_path, mode=mode,
                           mapping=cfg['rq2'].get('party_size_mapping'), temp_dir=paths['temp_dir'],
                           **{k: cfg['runtime']['duckdb'][k] for k in ('memory_limit', 'threads')})
        manager.commit('rq2_profiles', signature, {'profiles': profile_path, 'outcomes': outcome_path},
                       {'mode': mode, 'mode_evidence': evidence,
                        'ratio_policy': 'legacy fill-zero preserved; requires separate missing-semantics review'})
    return read_parquet_df(profile_path), read_parquet_df(outcome_path)


def profile_groups(profiles, cfg):
    if cfg['rq2']['mode_strategy'] == 'per_mode':
        yield from profiles.groupby('team_size_mode', sort=True)
    else:
        yield 'Overall', profiles


def compute_profile_coverage_table(profiles, cfg, paths):
    """Compute feature coverage and valid denominator counts per mode/cohort."""
    records = []
    for mode, group in profile_groups(profiles, cfg):
        n_prof = len(group)
        rec = {
            'mode': mode,
            'total_profiles': n_prof,
            'total_matches': int(group['games_played'].sum()) if 'games_played' in group else 0,
            'kill_active_matches': int(group['kill_active_matches'].sum()) if 'kill_active_matches' in group else 0,
            'support_active_matches': int(group['support_active_matches'].sum()) if 'support_active_matches' in group else 0,
            'timing_observed_matches': int(group['timing_observed_matches'].sum()) if 'timing_observed_matches' in group else 0,
        }
        for feat in CORE_PROFILE_FEATURES:
            if feat in group.columns:
                valid = int(group[feat].notna().sum())
                rec[f"{feat}_valid_n"] = valid
                rec[f"{feat}_valid_pct"] = round(float(valid / n_prof * 100.0), 2) if n_prof else 0.0
        records.append(rec)
    table = pd.DataFrame(records)
    atomic_write_csv(paths['tables'] / 'rq2_profile_coverage.csv', table)
    return table


def retention_table(profiles, cfg, paths):
    compute_profile_coverage_table(profiles, cfg, paths)
    records = []
    for mode, group in profile_groups(profiles, cfg):
        for threshold in cfg['rq2']['min_games_candidates']:
            positive_int(threshold, 'min_games_candidates')
            eligible = group[group.games_played >= threshold]
            records.append({'mode': mode, 'min_games': threshold, 'profiles_total': len(group),
                            'profiles_retained': len(eligible), 'players_retained': eligible.player_name.nunique(),
                            'retained_fraction': len(eligible) / len(group) if len(group) else 0,
                            'player_match_rows_retained': int(eligible.games_played.sum())})
    table = pd.DataFrame(records)
    atomic_write_csv(paths['tables'] / 'rq2_retention.csv', table)
    return table


def diagnostics(profiles, cfg, paths):
    rq2 = cfg['rq2']
    threshold = positive_int(rq2.get('minimum_games_threshold'), 'minimum_games_threshold')
    candidates = rq2['candidate_k_range']
    for k in candidates:
        positive_int(k, 'candidate_k_range', 2)
    records, sensitivity = [], []
    for mode, group in profile_groups(profiles, cfg):
        eligible = group[group.games_played >= threshold]
        X = prepare_clustering_matrix(eligible, rq2['scaler'])
        table = run_k_diagnostics(X, k_range=candidates, random_state=rq2['random_state'], device=rq2.get('device', 'cpu'))
        table['mode'] = mode
        table['min_games'] = threshold
        table['n_profiles'] = len(eligible)
        table['diagnostic_sample_n'] = min(len(eligible), 10000)
        table['seed'] = rq2['random_state']
        table['device'] = rq2.get('device', 'cpu')
        table['sample_rule'] = 'uniform_without_replacement; KMeans fits all eligible profiles'
        records.append(table)
        for k in candidates:
            comparison = threshold_sensitivity(group, rq2, k)
            comparison['mode'] = mode
            sensitivity.append(comparison)
    table = pd.concat(records, ignore_index=True) if records else pd.DataFrame()
    atomic_write_csv(paths['tables'] / 'k_diagnostics.csv', table)
    atomic_write_csv(paths['tables'] / 'rq2_min_games_stability.csv', pd.concat(sensitivity, ignore_index=True)
                     if sensitivity else pd.DataFrame())
    atomic_write_json(paths['manifests'] / 'rq2_diagnostics.json',
                      {'profile_checksum': hash_file(paths['processed'] / 'player_profile_features.parquet'),
                       'compute': compute_info(rq2.get('device', 'cpu')),
                       'settings': {k: rq2.get(k) for k in ('mode_strategy', 'minimum_games_threshold', 'min_games_candidates', 'candidate_k_range', 'scaler', 'random_state', 'device')}})
    return table


def threshold_sensitivity(group, rq2, k):
    # C4: compare only common player/profile keys, keeping K fixed.
    labelled_by_threshold = {}
    for threshold in rq2['min_games_candidates']:
        subset = group[group.games_played >= positive_int(threshold, 'min_games_candidates')]
        X = prepare_clustering_matrix(subset, rq2['scaler'])
        if len(X) < k or len(np.unique(X, axis=0)) < k:
            labelled_by_threshold[threshold] = None
            continue
        labelled = subset[profile_keys(subset)].copy()
        labelled['label'] = make_kmeans(rq2.get('device', 'cpu'), n_clusters=k, random_state=rq2['random_state'], n_init=10).fit_predict(X)
        labelled_by_threshold[threshold] = labelled
    comparisons = []
    for a, b in combinations(labelled_by_threshold, 2):
        left, right = labelled_by_threshold[a], labelled_by_threshold[b]
        common = None if left is None or right is None else left.merge(right, on=profile_keys(left), validate='one_to_one')
        valid = common is not None and len(common) >= 2
        comparisons.append({'min_games_a': a, 'min_games_b': b, 'k': k,
                            'n_common': len(common) if common is not None else 0,
                            'adjusted_rand_index': adjusted_rand_score(common.label_x, common.label_y) if valid else None,
                            'status': 'completed' if valid else 'insufficient_common_profiles'})
    return pd.DataFrame(comparisons, columns=['min_games_a', 'min_games_b', 'k', 'n_common', 'adjusted_rand_index', 'status'])


def final_clustering(profiles, outcomes, cfg, paths):
    rq2 = cfg['rq2']
    validate_mode(cfg, paths)
    threshold = positive_int(rq2.get('minimum_games_threshold'), 'minimum_games_threshold')
    if not str(rq2.get('selection_reason') or '').strip():
        raise ValueError('Record selection_reason for min-games and K using retention/stability/behavioral diagnostics')
    receipt = read_json(paths['manifests'] / 'rq2_diagnostics.json')
    settings = {k: rq2.get(k) for k in ('mode_strategy', 'minimum_games_threshold', 'min_games_candidates', 'candidate_k_range', 'scaler', 'random_state', 'device')}
    if receipt.get('compute') != compute_info(rq2.get('device', 'cpu')):
        raise ValueError('Compute backend changed; rerun diagnostics before final clustering')
    if receipt['settings'] != settings or receipt['profile_checksum'] != hash_file(paths['processed'] / 'player_profile_features.parquet'):
        raise ValueError('Profiles/settings changed; rerun diagnostics before final clustering')
    diagnostic_table = pd.read_csv(paths['tables'] / 'k_diagnostics.csv')
    groups = list(profile_groups(profiles, cfg))
    if profiles.empty:
        raise ValueError('No eligible profiles; notebook cannot be marked completed')
    selections = {}
    for mode, group in groups:
        chosen = rq2.get('n_clusters_by_mode', {}).get(mode) if rq2['mode_strategy'] == 'per_mode' else rq2.get('n_clusters')
        positive_int(chosen, f'n_clusters ({mode})', 2)
        if chosen not in rq2['candidate_k_range'] or not ((diagnostic_table['mode'] == mode) & (diagnostic_table['k'] == chosen)).any():
            raise ValueError(f'K={chosen} for {mode} has no matching diagnostics')
        X = prepare_clustering_matrix(group[group.games_played >= threshold], rq2['scaler'])
        if len(X) < chosen or len(np.unique(X, axis=0)) < chosen:
            raise ValueError(f'Insufficient distinct profiles for {mode}; notebook cannot be marked completed')
        selections[mode] = chosen
    manager = CheckpointManager(paths['checkpoints'] / 'checkpoint_manifest.json')
    signature = hash_dict({'settings': rq2, 'profiles': receipt['profile_checksum'], 'implementation': hash_file(Path(__file__))})
    manager.invalidate_descendants('rq2_clustering')
    manager.mark_running('rq2_clustering', signature)
    artifacts = {'profiles': paths['processed'] / 'player_profile_features.parquet',
                 'outcomes': paths['processed'] / 'player_profile_outcomes.parquet',
                 'retention': paths['tables'] / 'rq2_retention.csv',
                 'coverage': paths['tables'] / 'rq2_profile_coverage.csv',
                 'diagnostics': paths['tables'] / 'k_diagnostics.csv',
                 'threshold_stability': paths['tables'] / 'rq2_min_games_stability.csv',
                 'diagnostic_receipt': paths['manifests'] / 'rq2_diagnostics.json'}
    for mode, group in groups:
        target = paths['tables'] if rq2['mode_strategy'] != 'per_mode' else paths['tables'] / 'rq2' / mode
        eligible, eligible_outcomes = filter_profiles_by_retention(group, outcomes, threshold)
        result = execute_rq2_clustering(eligible, eligible_outcomes, selections[mode], target,
                                       scaler_type=rq2['scaler'], random_state=rq2['random_state'], device=rq2.get('device', 'cpu'))
        if result.get('status', 'completed') != 'completed':
            raise ValueError(f'Clustering did not complete for {mode}')
        sensitivity = pd.read_csv(paths['tables'] / 'rq2_min_games_stability.csv')
        atomic_write_csv(target / 'c4_min_games_sensitivity.csv',
                         sensitivity[(sensitivity['mode'] == mode) & (sensitivity['k'] == selections[mode])])
        for name in ('cluster_profile.csv', 'cluster_centers_standardized.csv', 'cluster_assignments.csv',
                     'clustering_robustness.csv', 'c5_outcome_comparison.csv', 'c4_min_games_sensitivity.csv',
                     'fitted_clustering_artifacts.joblib', 'c2_sample_indices.npy'):
            artifacts[f'{mode}/{name}'] = target / name
    decision_path = paths['manifests'] / 'rq2_decisions.json'
    atomic_write_json(decision_path, {'config': rq2, 'mode_evidence': read_json(paths['manifests'] / 'mode_analysis.json'),
                                    'compute': receipt['compute'],
                                    'run_ids': {mode: f"rq2_{mode.lower()}_kmeans_k{k}_{rq2.get('device', 'cpu')}" for mode, k in selections.items()},
                                    'profile_checksum': receipt['profile_checksum'],
                                    'scope': 'full eligible descriptive profiles; no heldout generalization claim'})
    artifacts['decisions'] = decision_path
    manager.commit('rq2_clustering', signature, artifacts)
    return artifacts
