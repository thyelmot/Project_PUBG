"""Disjoint match splits and train-only stratified size reduction."""
import pandas as pd
import numpy as np
from sklearn.model_selection import GroupShuffleSplit

from .config import SEED


def source_partition(match_ids, development_ids=(), seed=SEED):
    """Reserve one holdout from the full source, independent of cohort size."""
    ids = pd.DataFrame({'match_id': sorted(set(match_ids))})
    eligible = ids.loc[~ids.match_id.isin(set(development_ids))]
    test_count = int(np.ceil(len(ids) * 0.15))
    if len(ids) < 10 or len(eligible) <= test_count:
        raise ValueError('Not enough unseen matches to reserve a final holdout')
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_count, random_state=seed)
    _, test_idx = next(splitter.split(eligible, groups=eligible.match_id))
    test_ids = set(eligible.iloc[test_idx].match_id)
    rest = ids.loc[~ids.match_id.isin(test_ids)]
    splitter = GroupShuffleSplit(n_splits=1, train_size=int(len(ids) * 0.70), random_state=seed)
    train_idx, validation_idx = next(splitter.split(rest, groups=rest.match_id))
    result = ids.assign(split='test').set_index('match_id')
    result.loc[rest.iloc[train_idx].match_id, 'split'] = 'train'
    result.loc[rest.iloc[validation_idx].match_id, 'split'] = 'validation'
    return result.reset_index()


def split_matches(frame, assignments):
    if frame.match_id.nunique() < 10:
        raise ValueError('At least 10 cleaned matches are required')
    if not assignments.match_id.is_unique or set(assignments.split) != {'train', 'validation', 'test'}:
        raise ValueError('Invalid fixed split manifest')
    if set(frame.match_id) - set(assignments.match_id):
        raise ValueError('Matches absent from fixed split manifest')
    parts = {name: frame.loc[frame.match_id.isin(assignments.loc[assignments.split.eq(name), 'match_id'])].copy()
             for name in ('train', 'validation', 'test')}
    if any(part.empty for part in parts.values()):
        raise ValueError('Fixed split has no events in a partition; sample more matches or change cohort seed')
    sets = [set(part.match_id) for part in parts.values()]
    if any(sets[i] & sets[j] for i, j in ((0, 1), (0, 2), (1, 2))):
        raise ValueError('Match leakage between splits')
    return parts


def cap_train(frame, max_rows, seed=SEED):
    if max_rows < 1:
        raise ValueError('max_train_rows must be positive')
    if len(frame) <= max_rows:
        return frame.copy()
    counts = frame.weapon_group.value_counts().sort_index()
    if max_rows < len(counts):
        raise ValueError('max_train_rows must allow at least one row per class')
    desired = counts * max_rows / len(frame)
    quotas = np.floor(desired).astype(int).clip(lower=1)
    while quotas.sum() > max_rows:
        eligible = quotas[quotas > 1].index
        quotas.loc[(quotas - desired).loc[eligible].idxmax()] -= 1
    while quotas.sum() < max_rows:
        eligible = quotas[quotas < counts].index
        quotas.loc[(desired - quotas).loc[eligible].idxmax()] += 1
    selected = pd.concat([frame.loc[frame.weapon_group.eq(label)].sample(n=int(quota), random_state=seed)
                          for label, quota in quotas.items()])
    return selected.sample(frac=1, random_state=seed).copy()
