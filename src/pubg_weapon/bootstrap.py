"""Paired cluster bootstrap: resample entire matches, never individual events."""
import numpy as np
import pandas as pd

from .config import SEED


def bootstrap_macro_f1(actual, predictions, match_ids, classes, repeats=1000, seed=SEED):
    if repeats < 2 or not predictions or len(classes) == 0 or len(set(classes)) != len(classes):
        raise ValueError('Bootstrap requires >=2 repeats, predictions and distinct classes')
    group, matches = pd.factorize(pd.Series(match_ids), sort=True)
    if len(matches) < 2 or (group < 0).any() or len(group) != len(actual):
        raise ValueError('Bootstrap requires >=2 nonmissing matches aligned with targets')
    labels = pd.Index(classes)
    truth = labels.get_indexer(actual)
    if (truth < 0).any():
        raise ValueError('Unknown target class in bootstrap')
    n_groups, n_classes = len(matches), len(classes)
    # Per-match supports and true positives are sufficient for exact macro-F1.
    # This avoids copying all events 1000 times on the large test partition.
    support = np.bincount(group * n_classes + truth, minlength=n_groups * n_classes).reshape(n_groups, n_classes)
    blocks = [support]
    for prediction in predictions.values():
        predicted = labels.get_indexer(prediction)
        if len(predicted) != len(truth) or (predicted < 0).any():
            raise ValueError('Unknown or misaligned predicted classes in bootstrap')
        index = group * n_classes + predicted
        blocks.append(np.bincount(index, minlength=n_groups * n_classes).reshape(n_groups, n_classes))
        blocks.append(np.bincount(index[truth == predicted], minlength=n_groups * n_classes).reshape(n_groups, n_classes))
    counts = np.concatenate(blocks, axis=1).astype(float)
    rng = np.random.default_rng(seed)
    draws = []
    for start in range(0, repeats, 32):
        sampled = rng.integers(n_groups, size=(min(32, repeats - start), n_groups))
        weights = np.stack([np.bincount(row, minlength=n_groups) for row in sampled])
        totals = (weights @ counts).reshape(len(sampled), 1 + 2 * len(predictions), n_classes)
        denominator = totals[:, :1, :] + totals[:, 1::2, :]
        f1 = np.divide(2 * totals[:, 2::2, :], denominator,
                       out=np.zeros_like(denominator), where=denominator != 0)
        draws.append(f1.mean(axis=2))
    return pd.DataFrame(np.concatenate(draws), columns=list(predictions))


def paired_difference(draws, scores, before, after):
    """Positive difference means 'after' is better; zero in CI means inconclusive."""
    low, high = np.quantile(draws[after] - draws[before], [0.025, 0.975])
    return {'before': before, 'after': after, 'macro_f1_difference': scores[after] - scores[before],
            'ci95_low': float(low), 'ci95_high': float(high),
            'conclusion': 'after_higher' if low > 0 else 'before_higher' if high < 0 else 'inconclusive'}
