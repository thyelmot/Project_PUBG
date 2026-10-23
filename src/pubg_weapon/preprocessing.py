"""Label mapping, ordered cleaning and causal feature construction."""
import json

import numpy as np
import pandas as pd

from .config import (MAP_SIZE, MAX_TIME_SECONDS, MIN_CLASS_FRACTION,
                     COORDINATE_UNITS_PER_METER, RAW_COLUMNS)
from .io import read_json

COORDS = ['killer_position_x', 'killer_position_y', 'victim_position_x', 'victim_position_y']
PLACEHOLDERS = {'', '#unknown', 'unknown', 'none', 'null', 'nan', '<na>'}


OTHER = 'Other'
GROUPS = {'AR', 'DMR', 'SR', 'LMG', 'SMG', 'Shotgun', OTHER}


def load_mapping(path):
    mapping = read_json(path)
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError('Label mapping must be a nonempty object')
    if any(v is not None and v not in GROUPS for v in mapping.values()):
        raise ValueError('Unknown weapon group in label mapping')
    return mapping


def check_labels(values, mapping):
    unknown = sorted(set(values.dropna().unique()) - set(mapping))
    if unknown:
        raise ValueError(f'Unmapped killed_by values: {unknown}')


def rare_groups(train_labels, threshold=MIN_CLASS_FRACTION):
    if not 0 <= threshold < 1:
        raise ValueError('Rare class threshold must be in [0, 1)')
    counts = train_labels.value_counts(normalize=True)
    return sorted(c for c, fraction in counts.items() if fraction < threshold and c != OTHER)


def merge_rare(labels, rare):
    return labels.where(~labels.isin(rare), OTHER)


def build_features(frame):
    result = frame[['match_id', 'weapon_group', 'map', 'time']].copy()
    # Audit metadata only; feature_columns() never exposes the raw cause to a model.
    result['cause_for_audit'] = frame.killed_by
    result['kill_distance_m'] = np.hypot(frame.killer_position_x - frame.victim_position_x,
                                          frame.killer_position_y - frame.victim_position_y) / COORDINATE_UNITS_PER_METER
    result['log_kill_distance'] = np.log1p(result.kill_distance_m)
    result['time_phase'] = np.select([frame.time < 300, frame.time <= 1200], ['early', 'mid'], default='late')
    for side in ('killer', 'victim'):
        x, y = frame[f'{side}_position_x'] / MAP_SIZE, frame[f'{side}_position_y'] / MAP_SIZE
        result[f'{side}_x_norm'], result[f'{side}_y_norm'] = x, y
        result[f'{side}_center_dist'] = np.hypot(x - 0.5, y - 0.5)
        # Final placement is retained only for the explicit retrospective experiment.
        rank = frame[f'{side}_placement']
        result[f'{side}_placement'] = rank.where(np.isfinite(rank) & rank.between(1, 100))
    result['placement_gap'] = result.victim_placement - result.killer_placement
    history = build_history(frame.assign(kill_distance_m=result.kill_distance_m))
    return result.join(history)


def build_history(frame):
    """Aggregate complete, effective-label events; equal timestamps never see each other."""
    keys = ['match_id', 'killer_name', 'time']
    counts = frame.groupby(keys + ['weapon_group'], observed=True).size().unstack(fill_value=0)
    counts = counts.reindex(sorted(counts.columns), axis=1).sort_index()
    groups = [counts.index.get_level_values(k) for k in keys[:2]]
    prior = counts.groupby(level=keys[:2]).cumsum() - counts
    history = pd.DataFrame(index=counts.index)
    history['prior_kills_in_match'] = prior.sum(axis=1)
    history['has_prior_kill'] = history.prior_kills_in_match.gt(0).astype('int8')
    # Sorted class columns break modal ties deterministically, independent of row order.
    history['dominant_prior_weapon'] = prior.idxmax(axis=1).where(history.has_prior_kill.eq(1), 'NONE')
    history['last_weapon_group'] = counts.idxmax(axis=1).groupby(groups).shift().fillna('NONE')
    distances = frame.groupby(keys, observed=True).kill_distance_m.mean().reindex(counts.index)
    history['last_kill_distance_m'] = distances.groupby(groups).shift().fillna(0.0)
    times = pd.Series(counts.index.get_level_values('time'), index=counts.index)
    history['time_since_last_kill'] = (times - times.groupby(groups).shift()).fillna(-1.0)
    aligned = history.reindex(pd.MultiIndex.from_frame(frame[keys]))
    aligned.index = frame.index
    return aligned


def clean_events(frame, mapping):
    missing = set(RAW_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f'Missing columns: {sorted(missing)}')
    frame = frame.loc[:, list(RAW_COLUMNS)].copy()
    for col in ['killer_name', 'victim_name', 'match_id', 'map', 'killed_by']:
        frame[col] = frame[col].astype('string').str.strip()
    for col in COORDS + ['time', 'killer_placement', 'victim_placement']:
        frame[col] = pd.to_numeric(frame[col], errors='coerce')
    check_labels(frame.killed_by, mapping)
    audit = [{'rule': 'input', 'before': len(frame), 'removed': 0, 'remaining': len(frame), 'removed_causes': '{}'}]

    def remove(rule, invalid):
        nonlocal frame
        before = len(frame)
        invalid = invalid.fillna(True)
        causes = frame.loc[invalid, 'killed_by'].fillna('<missing>').value_counts().to_dict()
        frame = frame.loc[~invalid].copy()
        audit.append({'rule': rule, 'before': before, 'removed': before - len(frame), 'remaining': len(frame),
                      'removed_causes': json.dumps(causes, sort_keys=True)})

    remove('missing_killer', frame.killer_name.isna() | frame.killer_name.str.lower().isin(PLACEHOLDERS))
    remove('self_kill', frame.killer_name.eq(frame.victim_name).fillna(False))
    remove('zero_coordinates', ((frame.killer_position_x == 0) & (frame.killer_position_y == 0)) |
           ((frame.victim_position_x == 0) & (frame.victim_position_y == 0)))
    valid_numbers = np.isfinite(frame[COORDS + ['time']]).all(axis=1)
    remove('invalid_coordinates_or_time', ~valid_numbers | ~frame[COORDS].ge(0).all(axis=1) |
           ~frame[COORDS].le(MAP_SIZE).all(axis=1) | ~frame.time.between(0, MAX_TIME_SECONDS, inclusive='right'))
    remove('exact_duplicate', frame.duplicated())
    remove('invalid_identity_or_map', frame.match_id.isna() | frame.match_id.eq('') |
           frame.victim_name.isna() | frame.victim_name.str.lower().isin(PLACEHOLDERS) |
           ~frame['map'].isin(['ERANGEL', 'MIRAMAR']))
    frame['weapon_group'] = frame.killed_by.map(mapping)
    remove('environment_or_unknown_weapon', frame.weapon_group.isna())
    if frame.empty:
        raise ValueError('No valid weapon events remain after cleaning')
    audit = pd.DataFrame(audit)
    audit['fraction_of_input'] = audit.removed / audit.before.iloc[0]
    return frame.reset_index(drop=True), audit


def run_preprocessing(eda, output, mapping_path, max_train_rows=1_000_000, seed=42):
    from pathlib import Path
    from .eda import plot_train_distributions
    from .io import file_sha256, new_directory, write_json
    from .splits import cap_train, split_matches

    eda = Path(eda)
    mapping = load_mapping(mapping_path)
    source_manifest = read_json(eda / 'source_manifest.json')
    if file_sha256(eda / 'sampled_events.parquet') != source_manifest['sample_sha256']:
        raise ValueError('Sample data checksum mismatch')
    if file_sha256(eda / 'source_weapon_counts.csv') != source_manifest['source_weapon_counts_sha256']:
        raise ValueError('Source weapon inventory checksum mismatch')
    check_labels(pd.read_csv(eda / 'source_weapon_counts.csv').killed_by, mapping)
    # shortcut: the sampled cohort must fit RAM; use parquet batches if 50k matches exceed memory.
    raw = pd.read_parquet(eda / 'sampled_events.parquet')
    sample_causes = raw.killed_by.astype('string').str.strip().fillna('<missing>').value_counts()
    frame, audit = clean_events(raw, mapping)
    del raw
    if file_sha256(eda / 'source_match_splits.csv') != source_manifest['source_match_splits_sha256']:
        raise ValueError('Fixed source split checksum mismatch')
    parts = split_matches(frame, assignments=pd.read_csv(eda / 'source_match_splits.csv'))
    rare = rare_groups(parts['train'].weapon_group)
    for part in parts.values():
        part['weapon_group'] = merge_rare(part.weapon_group, rare)
    classes = sorted(parts['train'].weapon_group.unique())
    if len(classes) < 2:
        raise ValueError('At least two training classes are required')
    for name in ('validation', 'test'):
        unseen = set(parts[name].weapon_group.unique()) - set(classes)
        if unseen:
            raise ValueError(f'{name} has classes absent from train: {sorted(unseen)}; increase sampled matches')
    output = new_directory(output)
    split_manifest = pd.concat([part[['match_id']].drop_duplicates().assign(split=name)
                                for name, part in parts.items()], ignore_index=True)
    split_manifest.to_csv(output / 'split_manifest.csv', index=False)
    audit.to_csv(output / 'cleaning_counts.csv', index=False)
    source_counts = pd.read_csv(eda / 'source_weapon_counts.csv').set_index('killed_by')['count']
    label_step_counts = json.loads(audit.iloc[-1].removed_causes)
    pd.DataFrame([{'cause': cause, 'source_rows': int(source_counts.get(cause, 0)),
        'source_fraction': float(source_counts.get(cause, 0) / source_manifest['source_rows']),
        'sample_rows': int(sample_causes.get(cause, 0)),
        'sample_fraction': float(sample_causes.get(cause, 0) / audit.before.iloc[0]),
        'removed_at_label_step': int(label_step_counts.get(cause, 0)),
        'removed_at_prior_steps': int(sample_causes.get(cause, 0) - label_step_counts.get(cause, 0))}
        for cause in [k for k, v in mapping.items() if v is None] + ['<missing>']]).to_csv(
            output / 'excluded_label_counts.csv', index=False)
    distribution = pd.concat([part.weapon_group.value_counts(normalize=True).reindex(classes, fill_value=0).rename(name)
                              for name, part in parts.items()], axis=1)
    distribution.to_csv(output / 'split_class_distribution.csv')
    before_cap = len(parts['train'])
    summary, checksums = {}, {}
    for name, part in parts.items():
        features = build_features(part)
        if name == 'train':
            features = cap_train(features, max_train_rows, seed)
        features.to_parquet(output / f'{name}.parquet', index=False)
        checksums[name] = file_sha256(output / f'{name}.parquet')
        summary[name] = {'rows': len(features), 'matches': features.match_id.nunique(),
                         'class_counts': features.weapon_group.value_counts().to_dict()}
        if name == 'train':
            plot_train_distributions(features, output)
    write_json(output / 'label_mapping.json', mapping)
    effective_mapping = {k: ('Other' if v in rare else v) for k, v in mapping.items()}
    write_json(output / 'effective_label_mapping.json', effective_mapping)
    write_json(output / 'dataset_manifest.json', {
        'seed': seed, 'classes': classes, 'rare_groups_merged': rare, 'audit_cause_column': 'cause_for_audit',
        'history_policy': 'strict_prior_timestamp_before_train_cap',
        'min_class_fraction': MIN_CLASS_FRACTION,
        'split_seed': source_manifest['split_seed'],
        'source_match_splits_sha256': source_manifest['source_match_splits_sha256'],
        'train_rows_before_cap': before_cap, 'max_train_rows': max_train_rows,
        'source': source_manifest,
        'label_mapping_sha256': file_sha256(output / 'label_mapping.json'),
        'max_class_deviation_percentage_points': float((distribution.max(axis=1) - distribution.min(axis=1)).max() * 100),
        'splits': summary, 'files': checksums})
    return summary
