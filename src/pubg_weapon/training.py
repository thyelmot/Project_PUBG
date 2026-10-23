"""Validation-based tuning and a frozen list of final experiments."""
import importlib.metadata
import platform
import resource
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import accuracy_score, f1_score
from sklearn.utils.class_weight import compute_sample_weight
from threadpoolctl import threadpool_limits

from .io import file_sha256, new_directory, read_json, write_json
from .models import build_model, feature_columns
from .config import TARGET


def peak_rss_mb():
    """Process high-water RSS, not an isolated per-model allocation."""
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (1024 ** 2 if platform.system() == 'Darwin' else 1024)


def metrics(y_true, prediction, classes, probabilities=None, probability_classes=None):
    result = {'macro_f1': f1_score(y_true, prediction, labels=classes, average='macro', zero_division=0),
            'weighted_f1': f1_score(y_true, prediction, labels=classes, average='weighted', zero_division=0),
            'accuracy': accuracy_score(y_true, prediction)}
    roles = {'AR': 'Mid_Range', 'LMG': 'Mid_Range', 'DMR': 'Long_Range', 'SR': 'Long_Range',
             'SMG': 'Close_Range', 'Shotgun': 'Close_Range', 'Other': 'Close_Range'}
    actual_roles = [roles[label] for label in y_true]
    predicted_roles = [roles[label] for label in prediction]
    result['tactical_role_accuracy'] = accuracy_score(actual_roles, predicted_roles)
    result['tactical_role_macro_f1'] = f1_score(actual_roles, predicted_roles,
        labels=['Close_Range', 'Mid_Range', 'Long_Range'], average='macro', zero_division=0)
    if probabilities is not None:
        labels = np.asarray(probability_classes)
        top = labels[np.argsort(probabilities, axis=1, kind='stable')[:, -min(2, len(labels)):]]
        result['top_2_accuracy'] = float(np.mean((np.asarray(y_true)[:, None] == top).any(axis=1)))
    return result


def history_subset_metrics(frame, prediction, classes, probabilities, probability_classes, name):
    rows = []
    for has_prior in (0, 1):
        mask = frame.has_prior_kill.to_numpy() == has_prior
        row = {'name': name, 'has_prior_kill': has_prior, 'rows': int(mask.sum())}
        if mask.any():
            row.update(metrics(frame.loc[mask, TARGET], np.asarray(prediction)[mask], classes,
                               probabilities[mask], probability_classes))
        rows.append(row)
    return rows


def parameter_grid(family, quick):
    if family == 'random_forest':
        return [{'n_estimators': 20, 'max_depth': 10}] if quick else [
            {'n_estimators': 200, 'max_depth': 18, 'min_samples_leaf': 5, 'max_samples': 0.2},
            {'n_estimators': 300, 'max_depth': 18, 'min_samples_leaf': 5, 'max_samples': 0.15}]
    if family == 'hist_gradient_boosting':
        return [{'max_iter': 30, 'max_leaf_nodes': 15}] if quick else [
            {'max_iter': 150, 'learning_rate': 0.1, 'max_leaf_nodes': 31},
            {'max_iter': 250, 'learning_rate': 0.05, 'max_leaf_nodes': 15}]
    return [{}]


def run_training(processed, output, quick=False, jobs=2, with_placement=False, main_feature_set="loadout_history"):
    if main_feature_set not in ('full', 'loadout_history'):
        raise ValueError('Main feature set must be full or loadout_history')
    if jobs < 1:
        raise ValueError('jobs must be positive')
    processed = Path(processed)
    data_manifest = read_json(processed / 'dataset_manifest.json')
    if 'source_match_splits_sha256' not in data_manifest:
        raise ValueError('Dataset has no fixed source holdout; rerun EDA and preprocessing')
    if data_manifest.get('history_policy') != 'strict_prior_timestamp_before_train_cap':
        raise ValueError('Dataset lacks causal history; rerun preprocessing')
    for name in ('train', 'validation'):
        if file_sha256(processed / f'{name}.parquet') != data_manifest['files'][name]:
            raise ValueError(f'{name} data checksum mismatch')
    train, val = (pd.read_parquet(processed / f'{name}.parquet') for name in ('train', 'validation'))
    classes = data_manifest['classes']
    if set(train[TARGET].unique()) != set(classes):
        raise ValueError('Train classes do not match manifest')
    if set(val[TARGET].unique()) - set(classes):
        raise ValueError('Validation contains unseen target classes')
    if set(train.match_id) & set(val.match_id):
        raise ValueError('Match leakage between train and validation')
    output = new_directory(output)
    trials, experiments = [], []

    def fit(family, balanced, params, feature_set):
        columns = feature_columns(feature_set, with_placement)
        model = build_model(family, balanced, feature_set, with_placement, jobs, **params)
        fit_train = train
        weights = {}
        if balanced and family == 'hist_gradient_boosting':
            weights['model__sample_weight'] = compute_sample_weight('balanced', fit_train[TARGET])
        started = time.perf_counter()
        with threadpool_limits(limits=jobs), warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter('always', ConvergenceWarning)
            warnings.simplefilter('always', RuntimeWarning)
            model.fit(fit_train[columns], fit_train[TARGET], **weights)
            prediction = model.predict(val[columns])
            probabilities = model.predict_proba(val[columns])
        row = {'family': family, 'balanced': balanced, 'feature_set': feature_set, 'params': params,
               'interpretation': 'retrospective' if with_placement else 'event_context',
               'seconds': time.perf_counter() - started,
               'process_peak_rss_mb': peak_rss_mb(),
               'training_rows': len(fit_train),
               'warnings': [str(w.message) for w in captured
                            if isinstance(w.message, (ConvergenceWarning, RuntimeWarning))],
               'library_warnings': [str(w.message) for w in captured
                                    if not isinstance(w.message, (ConvergenceWarning, RuntimeWarning))],
               **metrics(val[TARGET], prediction, classes, probabilities, model.classes_)}
        trials.append(row)
        print(f'{family} balanced={balanced} features={feature_set} macro_f1={row["macro_f1"]:.4f}', flush=True)
        return model, row

    def save(model, row):
        name = f'{row["family"]}_{"balanced" if row["balanced"] else "plain"}_{row["feature_set"]}'
        model_path = output / f'{name}.joblib'
        joblib.dump(model, model_path)
        experiments.append({**row, 'name': name, 'pipeline': model_path.name,
                            'sha256': file_sha256(model_path),
                            'columns': feature_columns(row['feature_set'], with_placement)})

    families = ['majority', 'logistic', 'naive_bayes', 'decision_tree', 'random_forest', 'hist_gradient_boosting']
    for family in families:
        variants = [True] if family == 'logistic' else [False]
        if family in ('decision_tree', 'random_forest', 'hist_gradient_boosting'):
            variants = [False, True]
        for balanced in variants:
            best = None
            for params in parameter_grid(family, quick):
                model, row = fit(family, balanced, params, main_feature_set)
                if best is None or row['macro_f1'] > best[1]['macro_f1']:
                    best = model, row
            save(*best)
    full = list(experiments)
    best = max(full, key=lambda r: r['macro_f1'])
    # Freeze family, parameters and balancing so ablation changes only the features.
    for feature_set in ('distance', 'context', 'full', 'loadout_history'):
        if feature_set != main_feature_set:
            save(*fit(best['family'], best['balanced'], best['params'], feature_set))
    ablation = {letter: next(r['name'] for r in experiments
        if r['feature_set'] == feature_set and r['family'] == best['family'] and r['balanced'] == best['balanced'])
        for letter, feature_set in zip('ABCD', ('distance', 'context', 'full', 'loadout_history'))}
    selection = {'best': best['name'], 'ablation': ablation,
        'main_feature_set': main_feature_set, 'selection_metric': 'validation_macro_f1',
        'with_placement': with_placement, 'interpretation': 'retrospective' if with_placement else 'event_context'}
    write_json(output / 'experiments.json', experiments)
    write_json(output / 'selection.json', selection)
    # Keep rejected candidates as well: a clean winner must not hide failed trials.
    write_json(output / 'trials.json', trials)
    pd.json_normalize(trials).to_csv(output / 'validation_metrics.csv', index=False)
    write_json(output / 'metadata.json', {'quick': quick, 'jobs': jobs, 'python': platform.python_version(),
        'versions': {p: importlib.metadata.version(p) for p in ('numpy', 'pandas', 'scikit-learn', 'pyarrow', 'joblib')},
        'processed': str(processed.resolve()), 'dataset_manifest_sha256': file_sha256(processed / 'dataset_manifest.json'),
        'experiments_sha256': file_sha256(output / 'experiments.json'),
        'selection_sha256': file_sha256(output / 'selection.json'),
        'trials_sha256': file_sha256(output / 'trials.json'),
        'classes': classes, 'train_rows': len(train), 'validation_rows': len(val)})
    return selection
