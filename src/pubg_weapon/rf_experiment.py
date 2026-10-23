"""Systematic RF regularization, sub-bootstrapping, tempered weights, and feature pruning on validation."""
import importlib.metadata
from itertools import combinations
from pathlib import Path
import time
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import classification_report, f1_score
from threadpoolctl import threadpool_limits

from .bootstrap import bootstrap_macro_f1, paired_difference
from .io import file_sha256, new_directory, read_json, write_json
from .models import build_model, feature_columns, tempered_class_weights
from .config import TARGET
from .splits import cap_train
from .training import metrics, peak_rss_mb


def candidate_specs(n_estimators, targets):
    return [
        ('depth12_leaf20', 'full', 'balanced_subsample',
         {'n_estimators': n_estimators, 'max_depth': 12, 'min_samples_leaf': 20}),
        ('subboot_d18_leaf5_ms015', 'full', 'balanced_subsample',
         {'n_estimators': n_estimators, 'max_depth': 18, 'min_samples_leaf': 5, 'max_samples': 0.15}),
        ('subboot_d18_leaf5_ms020', 'full', 'balanced_subsample',
         {'n_estimators': n_estimators, 'max_depth': 18, 'min_samples_leaf': 5, 'max_samples': 0.20}),
        ('tempered_d18_leaf5_ms020', 'full', tempered_class_weights(targets, alpha=0.85, max_ratio=12.0),
         {'n_estimators': n_estimators, 'max_depth': 18, 'min_samples_leaf': 5, 'max_samples': 0.20}),
        ('tempered_d16_leaf8_ms020', 'full', tempered_class_weights(targets, alpha=0.80, max_ratio=12.0),
         {'n_estimators': n_estimators, 'max_depth': 16, 'min_samples_leaf': 8, 'max_samples': 0.20}),
        ('tempered_d14_leaf12_ms025', 'full', tempered_class_weights(targets, alpha=0.75, max_ratio=10.0),
         {'n_estimators': n_estimators, 'max_depth': 14, 'min_samples_leaf': 12, 'max_samples': 0.25}),
        ('no_pos_d16_leaf8_ms020', 'no_position', tempered_class_weights(targets, alpha=0.80, max_ratio=12.0),
         {'n_estimators': n_estimators, 'max_depth': 16, 'min_samples_leaf': 8, 'max_samples': 0.20}),
    ]


def run_rf_experiment(processed, baseline_run, output, jobs=2):
    processed, baseline_run = Path(processed), Path(baseline_run)
    if jobs < 1:
        raise ValueError('jobs must be positive')
    manifest = read_json(processed / 'dataset_manifest.json')
    metadata = read_json(baseline_run / 'metadata.json')
    if 'source_match_splits_sha256' not in manifest:
        raise ValueError('Dataset has no fixed source holdout')
    if file_sha256(processed / 'dataset_manifest.json') != metadata['dataset_manifest_sha256']:
        raise ValueError('Dataset differs from the frozen pilot')
    if file_sha256(baseline_run / 'experiments.json') != metadata['experiments_sha256']:
        raise ValueError('Frozen experiments were modified')
    for package, version in metadata['versions'].items():
        if importlib.metadata.version(package) != version:
            raise ValueError(f'Baseline library version mismatch: {package}')
    baseline = next(e for e in read_json(baseline_run / 'experiments.json')
        if e['family'] == 'random_forest' and e['balanced'] and e['feature_set'] == 'full')
    if baseline['columns'] != feature_columns('full') or baseline['interpretation'] != 'event_context':
        raise ValueError('Baseline must use main full features without placement')
    if file_sha256(baseline_run / baseline['pipeline']) != baseline['sha256']:
        raise ValueError('Baseline pipeline checksum mismatch')
    for name in ('train', 'validation'):
        if file_sha256(processed / f'{name}.parquet') != manifest['files'][name]:
            raise ValueError(f'{name} data checksum mismatch')
    train, val = (pd.read_parquet(processed / f'{name}.parquet') for name in ('train', 'validation'))
    if set(train.match_id) & set(val.match_id):
        raise ValueError('Match leakage between train and validation')
    classes = manifest['classes']
    if set(train[TARGET].unique()) != set(classes) or set(val[TARGET].unique()) - set(classes):
        raise ValueError('Classes differ from the frozen manifest')
    output = new_directory(output)
    sample = cap_train(train, min(20_000, len(train)))
    baseline_model = joblib.load(baseline_run / baseline['pipeline'])
    baseline_params = baseline_model.named_steps['model'].get_params(deep=False)
    n_estimators = baseline_params['n_estimators']
    candidates = [('baseline', 'full', baseline_params['class_weight'], baseline_params),
                  *candidate_specs(n_estimators, train[TARGET])]
    rows, class_rows, predictions, blocking = [], [], {}, []
    with threadpool_limits(limits=jobs):
        for name, fset, cw, params in candidates:
            cols = feature_columns(fset)
            fit_seconds = None
            oob_f1 = None
            with warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter('always', ConvergenceWarning)
                warnings.simplefilter('always', RuntimeWarning)
                if name == 'baseline':
                    model = baseline_model
                else:
                    use_oob = n_estimators >= 50 or params.get('max_samples') is not None
                    model = build_model('random_forest', balanced=False, feature_set=fset, jobs=jobs,
                                        class_weight=cw, oob_score=use_oob, **params)
                    started = time.perf_counter()
                    model.fit(train[cols], train[TARGET])
                    fit_seconds = time.perf_counter() - started
                    if use_oob and hasattr(model.named_steps['model'], 'oob_decision_function_'):
                        rf_est = model.named_steps['model']
                        oob_pred = rf_est.classes_[np.argmax(rf_est.oob_decision_function_, axis=1)]
                        oob_f1 = float(f1_score(train[TARGET], oob_pred, labels=classes,
                                                average='macro', zero_division=0))
                predicted = model.predict(val[cols])
                scores = metrics(val[TARGET], predicted, classes)
                training = metrics(sample[TARGET], model.predict(sample[cols]), classes)
                probabilities = model.predict_proba(val[cols])
            if name == 'baseline' and not np.isclose(scores['macro_f1'], baseline['macro_f1'], atol=1e-12):
                raise ValueError('Baseline pipeline does not reproduce validation macro-F1')
            if not np.isfinite(probabilities).all() or not np.allclose(probabilities.sum(axis=1), 1):
                raise ValueError(f'Invalid predicted probabilities: {name}')
            if not set(predicted) <= set(classes):
                raise ValueError(f'Predicted unknown weapon group: {name}')
            forest = model.named_steps['model']
            depths = [float(tree.get_depth()) for tree in forest.estimators_]
            leaves = [float(tree.get_n_leaves()) for tree in forest.estimators_]
            model_warnings = [str(w.message) for w in captured
                              if isinstance(w.message, (ConvergenceWarning, RuntimeWarning))]
            library_warnings = sorted({str(w.message) for w in captured
                                       if not isinstance(w.message, (ConvergenceWarning, RuntimeWarning))})
            blocking.extend(model_warnings)
            path = baseline_run / baseline['pipeline'] if name == 'baseline' else output / f'{name}.joblib'
            if name != 'baseline':
                joblib.dump(model, path)
            predictions[name] = predicted
            weight_scheme = cw
            if isinstance(cw, dict):
                weight_scheme = 'custom' if name == 'baseline' else 'tempered_power'
            rows.append({'name': name, 'feature_set': fset,
                'weight_scheme': weight_scheme,
                'params': params, **scores,
                'train_macro_f1': training['macro_f1'],
                'macro_f1_gap': training['macro_f1'] - scores['macro_f1'],
                'oob_macro_f1': oob_f1,
                'oob_macro_f1_gap': (oob_f1 - scores['macro_f1']) if oob_f1 is not None else None,
                'fit_seconds': fit_seconds, 'process_peak_rss_mb': peak_rss_mb(),
                'mean_tree_depth': float(np.mean(depths)), 'mean_tree_leaves': float(np.mean(leaves)),
                'pipeline_sha256': file_sha256(path), 'warnings': model_warnings,
                'library_warnings': library_warnings})
            report = classification_report(val[TARGET], predicted, labels=classes, output_dict=True, zero_division=0)
            for label in classes:
                class_rows.append({'name': name, 'class': label, **report[label]})
            print(f'{name}: val_macro_f1={scores["macro_f1"]:.6f} train_gap={rows[-1]["macro_f1_gap"]:.6f} '
                  f'oob_f1={oob_f1 if oob_f1 is not None else -1:.6f} leaves={rows[-1]["mean_tree_leaves"]:.1f}',
                  flush=True)
        draws = bootstrap_macro_f1(val[TARGET], predictions, val.match_id, classes)
    scores = {row['name']: row['macro_f1'] for row in rows}
    names = [row['name'] for row in rows]
    differences = [paired_difference(draws, scores, before, after)
                   for before, after in combinations(names, 2)]
    for row in rows:
        low, high = draws[row['name']].quantile([.025, .975])
        row.update(macro_f1_ci95_low=float(low), macro_f1_ci95_high=float(high))
    pd.json_normalize(rows).to_csv(output / 'validation_metrics.csv', index=False)
    pd.DataFrame(class_rows).to_csv(output / 'per_class_metrics.csv', index=False)
    pd.DataFrame(differences).to_csv(output / 'paired_differences.csv', index=False)
    draws.to_csv(output / 'bootstrap_macro_f1.csv', index=False)
    summary = {'status': 'failed' if blocking else 'passed', 'test_read': False,
        'evaluation_split': 'validation', 'interpretation': 'event_context',
        'train_rows': len(train), 'train_metric_rows': len(sample), 'validation_rows': len(val),
        'validation_matches': int(val.match_id.nunique()),
        'bootstrap': {'unit': 'match_id', 'repeats': 1000, 'seed': 42, 'confidence': .95},
        'dataset_manifest_sha256': file_sha256(processed / 'dataset_manifest.json'),
        'baseline_metadata_sha256': file_sha256(baseline_run / 'metadata.json'),
        'versions': metadata['versions'], 'results': rows, 'paired_differences': differences,
        'best_on_validation': max(rows, key=lambda row: row['macro_f1'])['name'],
        'blocking_warnings': blocking}
    write_json(output / 'summary.json', summary)
    if blocking:
        raise RuntimeError(f'RF experiment emitted blocking warnings: {blocking}')
    return summary
