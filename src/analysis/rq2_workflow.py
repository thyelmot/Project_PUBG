"""Disk-backed profiles and explicit decision gates for notebook 07."""
import gc
from pathlib import Path
from itertools import combinations
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score
from src.data.io import (get_duckdb_connection, copy_query_to_parquet, read_parquet_df,
                         atomic_write_csv, atomic_write_json, read_json)
from src.data.checkpoints import CheckpointManager
from src.utils.hashing import hash_file, hash_dict, hash_source_files
from src.utils.runtime import collect_runtime_info
from src.models.compute import make_kmeans, compute_info
from src.features.profiles import PROFILE_AUDIT_COLUMNS, PROFILE_MEANS, profile_aggregate_expressions, profile_keys, filter_profiles_by_retention
from src.analysis.clustering import (CORE_PROFILE_FEATURES, prepare_clustering_matrix,
                                     run_k_diagnostics, execute_rq2_clustering)


def positive_int(value, name, minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError(f"Set {name} to an integer >= {minimum} in configs/rq2.yaml; no automatic default")
    return value


def validate_mode(cfg, paths, source, split_path):
    rq2 = cfg['rq2']
    if rq2.get('algorithm') != 'kmeans':
        raise ValueError('This workflow implements KMeans only; changing estimator requires a separate review')
    if rq2.get('scaler') != 'standard':
        raise ValueError('C1 main requires StandardScaler; use sensitivity_scalers for RobustScaler evidence')
    experiments = rq2.get('experiments', {})
    supported = {'c1_main_clustering', 'c2_hierarchical_validation', 'c3_games_played_sensitivity',
                 'c4_min_games_sensitivity', 'c5_outcome_comparison',
                 'timing_exclusion_sensitivity', 'scaler_sensitivity'}
    unknown = sorted(set(experiments) - supported)
    if unknown or any(type(value) is not bool for value in experiments.values()):
        raise ValueError(f'Unsupported or non-boolean RQ2 experiment flags: {unknown}')
    if experiments.get('timing_exclusion_sensitivity'):
        if not rq2.get('timing_exclusion_features') or not str(rq2.get('timing_sensitivity_reason') or '').strip():
            raise ValueError('Timing sensitivity requires configured features and timing_sensitivity_reason evidence')
    if experiments.get('scaler_sensitivity'):
        if not rq2.get('sensitivity_scalers') or not str(rq2.get('scaler_sensitivity_reason') or '').strip():
            raise ValueError('Scaler sensitivity requires sensitivity_scalers and scaler_sensitivity_reason evidence')
    if rq2.get('log_transform_features') and not str(rq2.get('log_transform_reason') or '').strip():
        raise ValueError('Log transforms require log_transform_reason evidence from development diagnostics')
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
    record = read_json(evidence)
    expected = {
        'scope': 'development',
        'source_checksum': hash_file(source),
        'split_checksum': hash_file(split_path),
    }
    if any(record.get(key) != value for key, value in expected.items()):
        raise ValueError('mode_analysis.json is stale or lacks compatible source/split hashes; rerun notebook 05')
    return mode, record


def aggregate_profiles(source, profile_path, outcome_path, *, mode, mapping=None,
                       split_path=None, allowed_splits=None,
                       temp_dir=None, memory_limit='4GB', threads=4):
    """Build disk-backed profiles while preserving missing-value semantics.

    No player-match table is materialized in Pandas. Only reduced profiles are read later.
    """
    con = get_duckdb_connection(temp_dir, memory_limit, threads)
    try:
        if mode not in ('overall', 'player_mode', 'per_mode'):
            raise ValueError('Unknown mode strategy')
        safe_source = Path(source).resolve().as_posix().replace("'", "''")
        con.execute(f"CREATE VIEW source_input AS SELECT * FROM read_parquet('{safe_source}')")
        source_columns = {r[0] for r in con.execute('DESCRIBE source_input').fetchall()}
        if split_path is not None:
            if 'match_id' not in source_columns:
                raise ValueError('Development profiles require match_id in player_match_features')
            allowed_splits = tuple(allowed_splits or ())
            if not allowed_splits or 'test' in allowed_splits or any(x not in ('train', 'validation') for x in allowed_splits):
                raise ValueError('Development scope must contain train/validation only and must exclude test')
            safe_split = Path(split_path).resolve().as_posix().replace("'", "''")
            if con.execute(f"SELECT count(*) - count(DISTINCT match_id) FROM read_parquet('{safe_split}')").fetchone()[0]:
                raise ValueError('split_assignments must contain one row per match_id')
            split_sql = ', '.join("'" + item.replace("'", "''") + "'" for item in allowed_splits)
            con.execute(f"CREATE VIEW input AS SELECT s.* FROM source_input s INNER JOIN read_parquet('{safe_split}') p USING (match_id) WHERE p.split IN ({split_sql})")
        else:
            con.execute('CREATE VIEW input AS SELECT * FROM source_input')
        columns = {r[0] for r in con.execute('DESCRIBE input').fetchall()}
        mode_sql = ''
        keys = ['player_name']
        if mode != 'overall':
            keys.append('team_size_mode')
            if 'team_size_mode' in columns:
                mode_sql = ", CASE WHEN lower(team_size_mode)='solo' THEN 'Solo' WHEN lower(team_size_mode)='duo' THEN 'Duo' WHEN lower(team_size_mode)='squad' THEN 'Squad' ELSE team_size_mode END AS team_size_mode"
            elif mapping and 'party_size' in columns:
                cases = []
                for size, label in mapping.items():
                    if str(size) not in ('1', '2', '3', '4') or label not in ('Solo', 'Duo', 'Squad'):
                        raise ValueError('Verify party_size_mapping: integer sizes and Solo/Duo/Squad labels required')
                    cases.append(f"WHEN party_size = {int(size)} THEN '{label}'")
                mode_sql = ', CASE ' + ' '.join(cases) + ' END AS team_size_mode'
            else:
                raise ValueError('Missing verified team_size_mode; set party_size_mapping after schema verification. match_mode is not team size.')
        means = PROFILE_MEANS
        fields = list(means) + ['early_kill_ratio', 'mid_kill_ratio', 'late_kill_ratio', 'early_kills',
                               'phase_eligible_kill_count', 'timing_coverage_status',
                               'player_survive_time', 'normalized_placement', 'team_placement']
        missing = set(fields + ['player_name']) - columns
        if missing:
            raise ValueError(f'Missing required profile columns: {sorted(missing)}')
        con.execute('CREATE VIEW valid AS SELECT player_name, ' + ', '.join(fields) + mode_sql +
                    " FROM input WHERE player_name IS NOT NULL AND length(trim(player_name)) > 0")
        if mode != 'overall' and con.execute("SELECT count(*) FROM valid WHERE team_size_mode IS NULL OR team_size_mode NOT IN ('Solo','Duo','Squad')").fetchone()[0]:
            raise ValueError('Unmapped team_size_mode; verify mapping instead of dropping rows')
        aggregates = profile_aggregate_expressions()
        con.execute('CREATE TABLE aggregated AS SELECT ' + ', '.join(keys + aggregates) + ' FROM valid GROUP BY ' + ', '.join(keys))
        count = con.execute('SELECT count(*) FROM aggregated').fetchone()[0]
        for destination, names in ((profile_path, PROFILE_AUDIT_COLUMNS + ['mean_damage_per_kill'] + CORE_PROFILE_FEATURES),
                                   (outcome_path, ['mean_survive_time_valid_matches', 'mean_normalized_placement_valid_matches',
                                                   'win_rate_valid_matches', 'mean_survive_time',
                                                   'mean_normalized_placement', 'win_rate'])):
            query = 'SELECT ' + ', '.join(keys + ['games_played'] + names) + ' FROM aggregated ORDER BY ' + ', '.join(keys)
            copy_query_to_parquet(con, query, destination, expected_rows=count)
        return count
    finally:
        con.close()


def load_profiles(cfg, paths, scope='development'):
    source = paths['processed'] / 'player_match_features.parquet'
    split_path = paths['interim'] / 'split_assignments.parquet'
    if scope not in ('development', 'full_descriptive'):
        raise ValueError('RQ2 scope must be development or full_descriptive')
    mode, evidence = validate_mode(cfg, paths, source, split_path)
    suffix = '_development' if scope == 'development' else ''
    profile_path = paths['processed'] / f'player_profile_features{suffix}.parquet'
    outcome_path = paths['processed'] / f'player_profile_outcomes{suffix}.parquet'
    allowed_splits = tuple(cfg['eda']['scope']['allowed_development_splits']) if scope == 'development' else None
    signature = hash_dict({'source': hash_file(source), 'mode': mode,
                           'scope': scope, 'split': hash_file(split_path), 'allowed_splits': allowed_splits,
                           'mode_evidence': hash_file(paths['manifests'] / 'mode_analysis.json'),
                           'mapping': cfg['rq2'].get('party_size_mapping'),
                           'implementation': hash_source_files([Path(__file__), Path(__file__).parents[1] / 'features' / 'profiles.py']), 'version': 2})
    manager = CheckpointManager(paths['checkpoints'] / 'checkpoint_manifest.json')
    stage = f'rq2_profiles_{scope}'
    if not manager.is_compatible(stage, signature):
        manager.invalidate_descendants(stage)
        manager.mark_running(stage, signature)
        aggregate_profiles(source, profile_path, outcome_path, mode=mode,
                           mapping=cfg['rq2'].get('party_size_mapping'),
                           split_path=split_path if scope == 'development' else None,
                           allowed_splits=allowed_splits, temp_dir=paths['temp_dir'],
                           **{k: cfg['runtime']['duckdb'][k] for k in ('memory_limit', 'threads')})
        manager.commit(stage, signature, {'profiles': profile_path, 'outcomes': outcome_path},
                       {'mode': mode, 'scope': scope, 'allowed_splits': allowed_splits,
                        'source_checksum': hash_file(source), 'split_checksum': hash_file(split_path),
                        'mode_evidence_checksum': hash_file(paths['manifests'] / 'mode_analysis.json'),
                        'mode_evidence': evidence,
                        'ratio_policy': 'structural and data-error missing preserved; imputation occurs only in the fitted clustering pipeline'})
    return read_parquet_df(profile_path), read_parquet_df(outcome_path)


def profile_groups(profiles, cfg):
    if cfg['rq2']['mode_strategy'] == 'per_mode':
        yield from profiles.groupby('team_size_mode', sort=True)
    else:
        yield 'Overall', profiles


def record_resource_audit(profiles, cfg, paths, stage):
    rows = []
    for mode, group in profile_groups(profiles, cfg):
        n = len(group)
        rows.append({'mode': mode, 'profiles': n, 'features': len(CORE_PROFILE_FEATURES),
                     'feature_matrix_mb': round(n * len(CORE_PROFILE_FEATURES) * 8 / 2**20, 3),
                     'c2_pairwise_gb_estimate': round(n * n * 8 / 2**30, 3)})
    path = paths['manifests'] / 'rq2_resource_audit.json'
    receipt = read_json(path) if path.is_file() else {}
    signature = hash_dict({'modes': rows, 'c2_max_profiles': cfg['rq2'].get('c2_max_profiles'),
                           'k_diagnostic_sample_size': cfg['rq2'].get('k_diagnostic_sample_size')})
    if receipt.get(stage, {}).get('signature') == signature:
        return receipt[stage]
    receipt[stage] = {'runtime': collect_runtime_info(), 'modes': rows,
                      'c2_max_profiles': cfg['rq2'].get('c2_max_profiles'),
                      'k_diagnostic_sample_size': cfg['rq2'].get('k_diagnostic_sample_size'),
                      'signature': signature}
    atomic_write_json(path, receipt)
    return receipt[stage]


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
    minimum_games_diagnostics(profiles, cfg, paths)
    return table


def minimum_games_diagnostics(profiles, cfg, paths):
    """Describe threshold reliability/stability without using outcomes."""
    records = []
    for mode, group in profile_groups(profiles, cfg):
        for threshold in cfg['rq2']['min_games_candidates']:
            positive_int(threshold, 'min_games_candidates')
            eligible = group[group.games_played >= threshold]
            for feature in CORE_PROFILE_FEATURES:
                values = eligible[feature].replace([np.inf, -np.inf], np.nan)
                count_col = f'{feature}_valid_matches'
                records.append({
                    'mode': mode, 'min_games': threshold, 'feature': feature,
                    'profiles_total': len(group), 'profiles_retained': len(eligible),
                    'valid_profiles': int(values.notna().sum()),
                    'profile_coverage': float(values.notna().mean()) if len(values) else 0.0,
                    'valid_match_fraction': (
                        float(eligible[count_col].sum() / eligible.games_played.sum())
                        if count_col in eligible and eligible.games_played.sum() else np.nan
                    ),
                    'feature_mean': float(values.mean()) if values.notna().any() else np.nan,
                    'feature_std': float(values.std(ddof=1)) if values.notna().sum() > 1 else np.nan,
                    'estimated_matrix_mb': float(len(eligible) * len(CORE_PROFILE_FEATURES) * 8 / 1024 ** 2),
                })
    table = pd.DataFrame(records)
    atomic_write_csv(paths['tables'] / 'rq2_min_games_stability.csv', table)
    return table


def diagnostics(profiles, cfg, paths):
    rq2 = cfg['rq2']
    if rq2.get('minimum_games_threshold') is None:
        raise ValueError('Set minimum_games_threshold after reviewing rq2_retention.csv and rq2_min_games_stability.csv')
    threshold = positive_int(rq2.get('minimum_games_threshold'), 'minimum_games_threshold')
    candidates = rq2['candidate_k_range']
    resource_audit = record_resource_audit(profiles, cfg, paths, 'development_diagnostics')
    manager = CheckpointManager(paths['checkpoints'] / 'checkpoint_manifest.json')
    artifacts = {
        'diagnostics': paths['tables'] / 'k_diagnostics.csv',
        'threshold_stability': paths['tables'] / 'rq2_min_games_stability.csv',
        'diagnostic_receipt': paths['manifests'] / 'rq2_diagnostics.json',
    }
    profile_path = paths['processed'] / 'player_profile_features_development.parquet'
    threshold_stability_path = artifacts['threshold_stability']
    if not threshold_stability_path.is_file():
        raise FileNotFoundError('Run retention_table first and review rq2_min_games_stability.csv')
    code_hash = hash_source_files([
        Path(__file__), Path(__file__).with_name('clustering.py'),
        Path(__file__).parents[1] / 'models' / 'compute.py',
    ])
    signature = hash_dict({
        'profiles': hash_file(profile_path),
        'threshold_stability': hash_file(threshold_stability_path),
        'settings': {k: rq2.get(k) for k in (
            'mode_strategy', 'minimum_games_threshold', 'min_games_candidates',
            'candidate_k_range', 'k_diagnostic_sample_size', 'scaler', 'log_transform_features',
            'random_state', 'device')},
        'code': code_hash,
    })
    if manager.is_compatible('rq2_diagnostics', signature):
        return pd.read_csv(artifacts['diagnostics'])
    manager.invalidate_descendants('rq2_diagnostics')
    manager.mark_running('rq2_diagnostics', signature)
    for k in candidates:
        positive_int(k, 'candidate_k_range', 2)
    records = []
    for mode, group in profile_groups(profiles, cfg):
        eligible = group[group.games_played >= threshold]
        X = prepare_clustering_matrix(eligible, rq2['scaler'], rq2.get('log_transform_features'))
        table = run_k_diagnostics(X, k_range=candidates, random_state=rq2['random_state'],
                                  sample_size_for_silhouette=rq2.get('k_diagnostic_sample_size'),
                                  device=rq2.get('device', 'cpu'))
        table['mode'] = mode
        table['min_games'] = threshold
        table['n_profiles'] = len(eligible)
        table['seed'] = rq2['random_state']
        table['device'] = rq2.get('device', 'cpu')
        table['sample_rule'] = ('full_eligible' if rq2.get('k_diagnostic_sample_size') is None or
                                len(eligible) <= rq2['k_diagnostic_sample_size'] else
                                'uniform_without_replacement_configured_cap; KMeans fits all eligible profiles')
        records.append(table)
    table = pd.concat(records, ignore_index=True) if records else pd.DataFrame()
    atomic_write_csv(paths['tables'] / 'k_diagnostics.csv', table)
    atomic_write_json(paths['manifests'] / 'rq2_diagnostics.json',
                      {'profile_checksum': hash_file(profile_path),
                       'source_checksum': hash_file(paths['processed'] / 'player_match_features.parquet'),
                       'split_checksum': hash_file(paths['interim'] / 'split_assignments.parquet'),
                       'mode_evidence_checksum': hash_file(paths['manifests'] / 'mode_analysis.json'),
                       'diagnostics_checksum': hash_file(paths['tables'] / 'k_diagnostics.csv'),
                       'threshold_stability_checksum': hash_file(paths['tables'] / 'rq2_min_games_stability.csv'),
                       'code_hash': code_hash, 'scope': 'development',
                       'compute': compute_info(rq2.get('device', 'cpu')),
                       'resource_audit': resource_audit,
                       'settings': {k: rq2.get(k) for k in ('mode_strategy', 'minimum_games_threshold', 'min_games_candidates', 'candidate_k_range', 'k_diagnostic_sample_size', 'scaler', 'log_transform_features', 'random_state', 'device')},
                       'signature': signature})
    manager.commit('rq2_diagnostics', signature, artifacts)
    return table


def threshold_sensitivity(group, rq2, k):
    # C4: compare only common player/profile keys, keeping K fixed.
    labelled_by_threshold = {}
    for threshold in rq2['min_games_candidates']:
        subset = group[group.games_played >= positive_int(threshold, 'min_games_candidates')]
        X = prepare_clustering_matrix(subset, rq2['scaler'], rq2.get('log_transform_features'))
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
                            'n_profiles_a': len(left) if left is not None else 0,
                            'n_profiles_b': len(right) if right is not None else 0,
                            'n_common': len(common) if common is not None else 0,
                            'common_coverage_a': len(common) / len(left) if common is not None and len(left) else 0.0,
                            'common_coverage_b': len(common) / len(right) if common is not None and len(right) else 0.0,
                            'adjusted_rand_index': adjusted_rand_score(common.label_x, common.label_y) if valid else None,
                            'status': 'completed' if valid else 'insufficient_common_profiles'})
    return pd.DataFrame(comparisons, columns=['min_games_a', 'min_games_b', 'k', 'n_profiles_a', 'n_profiles_b',
                                              'n_common', 'common_coverage_a', 'common_coverage_b',
                                              'adjusted_rand_index', 'status'])


def final_clustering(profiles, outcomes, cfg, paths):
    rq2 = cfg['rq2']
    source = paths['processed'] / 'player_match_features.parquet'
    split_path = paths['interim'] / 'split_assignments.parquet'
    validate_mode(cfg, paths, source, split_path)
    threshold = positive_int(rq2.get('minimum_games_threshold'), 'minimum_games_threshold')
    if not str(rq2.get('selection_reason') or '').strip():
        raise ValueError('Record selection_reason for min-games and K using retention/stability/behavioral diagnostics')
    receipt = read_json(paths['manifests'] / 'rq2_diagnostics.json')
    settings = {k: rq2.get(k) for k in ('mode_strategy', 'minimum_games_threshold', 'min_games_candidates', 'candidate_k_range', 'k_diagnostic_sample_size', 'scaler', 'log_transform_features', 'random_state', 'device')}
    if receipt.get('compute') != compute_info(rq2.get('device', 'cpu')):
        raise ValueError('Compute backend changed; rerun diagnostics before final clustering')
    development_path = paths['processed'] / 'player_profile_features_development.parquet'
    code_hash = hash_source_files([
        Path(__file__), Path(__file__).with_name('clustering.py'),
        Path(__file__).parents[1] / 'models' / 'compute.py',
    ])
    integrity = {
        'profile_checksum': hash_file(development_path),
        'source_checksum': hash_file(source),
        'split_checksum': hash_file(split_path),
        'mode_evidence_checksum': hash_file(paths['manifests'] / 'mode_analysis.json'),
        'diagnostics_checksum': hash_file(paths['tables'] / 'k_diagnostics.csv'),
        'threshold_stability_checksum': hash_file(paths['tables'] / 'rq2_min_games_stability.csv'),
        'code_hash': code_hash,
        'scope': 'development',
    }
    if receipt['settings'] != settings or any(receipt.get(key) != value for key, value in integrity.items()):
        raise ValueError('Profiles/settings changed; rerun diagnostics before final clustering')
    diagnostic_table = pd.read_csv(paths['tables'] / 'k_diagnostics.csv')
    selection_groups = list(profile_groups(profiles, cfg))
    if profiles.empty:
        raise ValueError('No eligible profiles; notebook cannot be marked completed')
    selections = {}
    for mode, group in selection_groups:
        chosen = rq2.get('n_clusters_by_mode', {}).get(mode) if rq2['mode_strategy'] == 'per_mode' else rq2.get('n_clusters')
        if chosen is None:
            raise ValueError(f'Set n_clusters for {mode} after reviewing k_diagnostics.csv; K cannot be selected from outcomes')
        positive_int(chosen, f'n_clusters ({mode})', 2)
        if chosen not in rq2['candidate_k_range'] or not ((diagnostic_table['mode'] == mode) & (diagnostic_table['k'] == chosen)).any():
            raise ValueError(f'K={chosen} for {mode} has no matching diagnostics')
        X = prepare_clustering_matrix(group[group.games_played >= threshold], rq2['scaler'], rq2.get('log_transform_features'))
        if len(X) < chosen or len(np.unique(X, axis=0)) < chosen:
            raise ValueError(f'Insufficient distinct profiles for {mode}; notebook cannot be marked completed')
        selections[mode] = chosen
    full_profiles, full_outcomes = load_profiles(cfg, paths, scope='full_descriptive')
    resource_audit = record_resource_audit(full_profiles, cfg, paths, 'full_descriptive_fit')
    available_ram = resource_audit['runtime'].get('available_ram_gb')
    if (rq2.get('experiments', {}).get('c2_hierarchical_validation', True) and
            rq2.get('c2_max_profiles') is None and isinstance(available_ram, (int, float)) and
            any(row['c2_pairwise_gb_estimate'] > available_ram * 0.25 for row in resource_audit['modes'])):
        raise ValueError('C2 full pairwise estimate exceeds 25% available RAM; review rq2_resource_audit.json and set c2_max_profiles with a reason')
    groups = list(profile_groups(full_profiles, cfg))
    manager = CheckpointManager(paths['checkpoints'] / 'checkpoint_manifest.json')
    full_profile_checksum = hash_file(paths['processed'] / 'player_profile_features.parquet')
    signature = hash_dict({'settings': rq2, 'development_profiles': receipt['profile_checksum'],
                           'full_profiles': full_profile_checksum,
                           'diagnostics': receipt.get('signature'), 'code': code_hash})
    if manager.is_compatible('rq2_clustering', signature):
        restored = manager.restore('rq2_clustering')
        return {name: Path(path) for name, path in restored['artifacts'].items()}
    manager.mark_running('rq2_clustering', signature)
    artifacts = {'profiles': paths['processed'] / 'player_profile_features.parquet',
                 'outcomes': paths['processed'] / 'player_profile_outcomes.parquet',
                 'development_profiles': development_path,
                 'development_outcomes': paths['processed'] / 'player_profile_outcomes_development.parquet',
                 'retention': paths['tables'] / 'rq2_retention.csv',
                 'coverage': paths['tables'] / 'rq2_profile_coverage.csv',
                 'diagnostics': paths['tables'] / 'k_diagnostics.csv',
                 'threshold_stability': paths['tables'] / 'rq2_min_games_stability.csv',
                 'diagnostic_receipt': paths['manifests'] / 'rq2_diagnostics.json',
                 'resource_audit': paths['manifests'] / 'rq2_resource_audit.json'}
    for mode, group in groups:
        target = paths['tables'] if rq2['mode_strategy'] != 'per_mode' else paths['tables'] / 'rq2' / mode
        eligible, eligible_outcomes = filter_profiles_by_retention(group, full_outcomes, threshold)
        mode_stage = f'rq2_clustering/{mode}'
        mode_signature = hash_dict({'parent': signature, 'mode': mode, 'k': selections[mode]})
        names = ('cluster_profile.csv', 'cluster_centers_standardized.csv', 'cluster_assignments.csv',
                 'clustering_robustness.csv', 'c5_outcome_comparison.csv', 'c4_min_games_sensitivity.csv',
                 'fitted_clustering_artifacts.joblib', 'c2_sample_indices.npy')
        mode_artifacts = {name: target / name for name in names}
        if manager.is_compatible(mode_stage, mode_signature):
            for name, path in mode_artifacts.items():
                artifacts[f'{mode}/{name}'] = path
            continue
        manager.mark_running(mode_stage, mode_signature)
        result = execute_rq2_clustering(eligible, eligible_outcomes, selections[mode], target,
                                       scaler_type=rq2['scaler'], random_state=rq2['random_state'],
                                       device=rq2.get('device', 'cpu'), c2_max_profiles=rq2.get('c2_max_profiles'),
                                       log_transform_features=rq2.get('log_transform_features'),
                                       experiments=rq2.get('experiments'),
                                       timing_exclusion_features=(rq2.get('timing_exclusion_features') if
                                           rq2.get('experiments', {}).get('timing_exclusion_sensitivity') else None),
                                       sensitivity_scalers=(rq2.get('sensitivity_scalers') if
                                           rq2.get('experiments', {}).get('scaler_sensitivity') else None))
        if result.get('status', 'completed') != 'completed':
            raise ValueError(f'Clustering did not complete for {mode}')
        if rq2.get('experiments', {}).get('c4_min_games_sensitivity', True):
            sensitivity = threshold_sensitivity(group, rq2, selections[mode])
            c4_status, c4_reason = 'completed', 'common_profile_keys_only'
        else:
            sensitivity = pd.DataFrame(columns=['min_games_a', 'min_games_b', 'k', 'n_profiles_a', 'n_profiles_b',
                                                 'n_common', 'common_coverage_a', 'common_coverage_b',
                                                 'adjusted_rand_index', 'status'])
            c4_status, c4_reason = 'skipped', 'disabled_by_config'
        sensitivity['mode'] = mode
        atomic_write_csv(target / 'c4_min_games_sensitivity.csv', sensitivity)
        robustness_path = target / 'clustering_robustness.csv'
        robustness = pd.read_csv(robustness_path)
        robustness.loc[len(robustness)] = {'comparison': 'C4_Min_Games_Sensitivity', 'metric': 'Adjusted_Rand_Index',
                                           'value': sensitivity['adjusted_rand_index'].mean() if len(sensitivity) else np.nan,
                                           'n_sample': sensitivity['n_common'].max() if len(sensitivity) else 0,
                                           'population_size': len(group), 'seed': rq2['random_state'],
                                           'sampling_rule': 'common_profile_keys' if len(sensitivity) else 'not_run',
                                           'sample_identity_sha256': None, 'scope': 'supporting_sensitivity',
                                           'status': c4_status, 'reason': c4_reason}
        atomic_write_csv(robustness_path, robustness)
        manager.commit(mode_stage, mode_signature, mode_artifacts, {'mode': mode, 'k': selections[mode]})
        for name, path in mode_artifacts.items():
            artifacts[f'{mode}/{name}'] = path
        gc.collect()
    decision_path = paths['manifests'] / 'rq2_decisions.json'
    atomic_write_json(decision_path, {'config': rq2, 'mode_evidence': read_json(paths['manifests'] / 'mode_analysis.json'),
                                    'compute': receipt['compute'],
                                    'run_ids': {mode: f"rq2_{mode.lower()}_kmeans_k{k}_{rq2.get('device', 'cpu')}_{manager.load_manifest()['stages'][f'rq2_clustering/{mode}']['completed_at']}" for mode, k in selections.items()},
                                    'profile_checksum': receipt['profile_checksum'],
                                    'full_profile_checksum': full_profile_checksum,
                                    'selection_scope': 'development: train+validation only',
                                    'fit_scope': 'full eligible descriptive profiles after decision lock',
                                    'claim_scope': 'descriptive only; no heldout generalization claim'})
    artifacts['decisions'] = decision_path
    manager.commit('rq2_clustering', signature, artifacts)
    return artifacts
