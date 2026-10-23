"""Validation-only debugging; the real test partition is never read."""
from pathlib import Path
from itertools import combinations
import warnings

import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.inspection import permutation_importance
from sklearn.metrics import classification_report, confusion_matrix, ConfusionMatrixDisplay, f1_score, make_scorer
from sklearn.utils.class_weight import compute_sample_weight
from threadpoolctl import threadpool_limits

from .config import SEED
from .bootstrap import bootstrap_macro_f1, paired_difference
from .error_analysis import write_error_tables
from .io import file_sha256, new_directory, read_json, write_json
from .models import build_model, feature_columns
from .config import TARGET
from .splits import cap_train
from .training import history_subset_metrics, metrics, peak_rss_mb


def run_diagnostics(processed, run, output, jobs=2):
    if jobs < 1:
        raise ValueError('jobs must be positive')
    processed, run = Path(processed), Path(run)
    metadata = read_json(run / 'metadata.json')
    manifest = read_json(processed / 'dataset_manifest.json')
    if file_sha256(processed / 'dataset_manifest.json') != metadata['dataset_manifest_sha256']:
        raise ValueError('Dataset differs from training dataset')
    for name in ('train', 'validation'):
        if file_sha256(processed / f'{name}.parquet') != manifest['files'][name]:
            raise ValueError(f'{name} data checksum mismatch')
    if file_sha256(run / 'experiments.json') != metadata['experiments_sha256']:
        raise ValueError('Frozen experiments were modified')
    if file_sha256(run / 'selection.json') != metadata['selection_sha256']:
        raise ValueError('Frozen selection was modified')
    train, val = (pd.read_parquet(processed / f'{name}.parquet') for name in ('train', 'validation'))
    if set(train.match_id) & set(val.match_id):
        raise ValueError('Match leakage between train and validation')
    output = new_directory(output)
    classes = manifest['classes']
    experiments, selection = read_json(run / 'experiments.json'), read_json(run / 'selection.json')
    rows, class_rows, best_prediction = [], [], None
    history_rows = []
    predictions = {}
    main_feature_set = selection.get("main_feature_set", "full")
    for split_name, frame in (('train', train), ('validation', val)):
        frame.groupby(TARGET, observed=True).kill_distance_m.describe().to_csv(output / f'{split_name}_distance_by_class.csv')
    with threadpool_limits(limits=jobs), warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter('always', ConvergenceWarning)
        warnings.simplefilter('always', RuntimeWarning)
        for experiment in experiments:
            if file_sha256(run / experiment['pipeline']) != experiment['sha256']:
                raise ValueError('Pipeline checksum mismatch')
            pipeline = joblib.load(run / experiment['pipeline'])
            columns = experiment['columns']
            sample = cap_train(train, min(20_000, len(train)))
            prediction = pipeline.predict(val[columns])
            predictions[experiment['name']] = prediction
            train_prediction = pipeline.predict(sample[columns])
            scores = metrics(val[TARGET], prediction, classes)
            training = metrics(sample[TARGET], train_prediction, classes)
            if not np.isclose(scores['macro_f1'], experiment['macro_f1'], atol=1e-12):
                raise ValueError('Reloaded pipeline does not reproduce validation score')
            probabilities = pipeline.predict_proba(val[columns])
            if not np.isfinite(probabilities).all() or not np.allclose(probabilities.sum(axis=1), 1):
                raise ValueError(f'Invalid predicted probabilities: {experiment["name"]}')
            if not set(prediction) <= set(classes):
                raise ValueError('Predicted unknown weapon group')
            scores = metrics(val[TARGET], prediction, classes, probabilities, pipeline.classes_)
            if 'has_prior_kill' in val:
                history_rows.extend(history_subset_metrics(val, prediction, classes, probabilities, pipeline.classes_, experiment['name']))
            rows.append({'name': experiment['name'], 'family': experiment['family'], 'balanced': experiment['balanced'],
                'feature_set': experiment['feature_set'], 'interpretation': selection['interpretation'],
                **scores, 'train_macro_f1': training['macro_f1'],
                'macro_f1_gap': training['macro_f1'] - scores['macro_f1'], 'train_metric_rows': len(sample),
                'predicted_classes': len(set(prediction))})
            report = classification_report(val[TARGET], prediction, labels=classes, output_dict=True, zero_division=0)
            for label in classes:
                class_rows.append({'name': experiment['name'], 'class': label, **report[label],
                                   'predicted_count': int(np.sum(prediction == label))})
            matrix = confusion_matrix(val[TARGET], prediction, labels=classes)
            pd.DataFrame(matrix, index=classes, columns=classes).to_csv(output / f'{experiment["name"]}_confusion.csv')
            if experiment['name'] == selection['best']:
                best_prediction = prediction
                fig, ax = plt.subplots(figsize=(9, 8))
                ConfusionMatrixDisplay(matrix, display_labels=classes).plot(ax=ax, colorbar=False, xticks_rotation=45)
                fig.tight_layout()
                fig.savefig(output / 'best_confusion.png')
                plt.close(fig)
        write_error_tables(val, best_prediction, classes, output)
        tree = max((e for e in experiments if e["feature_set"] == main_feature_set and e['family'] in
            ('decision_tree', 'random_forest', 'hist_gradient_boosting')), key=lambda e: e['macro_f1'])
        pipeline = joblib.load(run / tree['pipeline'])
        importance_sample = val.sample(min(2000, len(val)), random_state=SEED)
        importance = permutation_importance(pipeline, importance_sample[tree['columns']], importance_sample[TARGET],
            n_repeats=3, random_state=SEED, n_jobs=1,
            scoring=make_scorer(f1_score, labels=classes, average='macro', pos_label=None, zero_division=0))
        pd.DataFrame({'feature': tree['columns'], 'importance_mean': importance.importances_mean,
            'importance_std': importance.importances_std}).sort_values('importance_mean', ascending=False).to_csv(
                output / 'feature_importance.csv', index=False)
        # Identical model/data size: only training labels differ in this signal check.
        control_train = cap_train(train, min(20_000, len(train)))
        columns = feature_columns(main_feature_set, selection['with_placement'])
        controls = {}
        for mode in ('real_labels', 'shuffled_labels'):
            target = control_train[TARGET].to_numpy().copy()
            if mode == 'shuffled_labels':
                target = np.random.default_rng(SEED).permutation(target)
            control = build_model('hist_gradient_boosting', True, feature_set=main_feature_set, with_placement=selection['with_placement'],
                                  max_iter=30, max_leaf_nodes=15)
            control.fit(control_train[columns], target, model__sample_weight=compute_sample_weight('balanced', target))
            controls[mode] = metrics(val[TARGET], control.predict(val[columns]), classes)
    blocked = [str(w.message) for w in captured if isinstance(w.message, (ConvergenceWarning, RuntimeWarning))]
    pd.DataFrame(history_rows).to_csv(output / 'history_subset_metrics.csv', index=False)
    scores = {row['name']: row['macro_f1'] for row in rows}
    draws = bootstrap_macro_f1(val[TARGET], predictions, val.match_id, classes)
    draws.to_csv(output / 'bootstrap_macro_f1.csv', index=False)
    table = pd.DataFrame(rows).set_index('name')
    table['macro_f1_ci95_low'] = draws.quantile(0.025)
    table['macro_f1_ci95_high'] = draws.quantile(0.975)
    table.to_csv(output / 'validation_diagnostics.csv')
    main_names = table.index[table.feature_set.eq(main_feature_set)]
    pd.DataFrame([paired_difference(draws, scores, before, after)
        for before, after in combinations(main_names, 2)]).to_csv(output / 'paired_model_differences.csv', index=False)
    ablation = selection['ablation']
    changes = zip(list(ablation)[:-1], list(ablation)[1:])
    pd.DataFrame([{'ablation_change': f'{before}->{after}',
        **paired_difference(draws, scores, ablation[before], ablation[after])}
        for before, after in changes]).to_csv(output / 'ablation_gains.csv', index=False)
    ablation_table = table.loc[list(ablation.values())].copy()
    ablation_table.insert(0, 'ablation', list(ablation))
    ablation_table.to_csv(output / 'ablation.csv')
    pd.DataFrame(class_rows).to_csv(output / 'per_class_metrics.csv', index=False)
    summary = {'status': 'passed' if not blocked else 'failed', 'test_read': False,
        'interpretation': selection['interpretation'],
        'train_rows': len(train), 'validation_rows': len(val), 'train_metric_rows': min(20_000, len(train)),
        'selected_on_validation': selection['best'], 'controls': controls,
        'signal_macro_f1_difference': controls['real_labels']['macro_f1'] - controls['shuffled_labels']['macro_f1'],
        'importance_model': tree['name'], 'importance_rows': len(importance_sample),
        'process_peak_rss_mb': peak_rss_mb(), 'blocking_warnings': blocked,
        'library_warnings': sorted({str(w.message) for w in captured
            if not isinstance(w.message, (ConvergenceWarning, RuntimeWarning))})}
    write_json(output / 'diagnostics_summary.json', summary)
    if blocked:
        raise RuntimeError(f'Diagnostics emitted blocking warnings: {blocked}')
    return summary
