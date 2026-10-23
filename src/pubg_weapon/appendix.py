"""Appendix C: grouped CV and validation-only experiments on frozen data."""
import json
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import confusion_matrix, f1_score, make_scorer
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.utils.class_weight import compute_sample_weight
from threadpoolctl import threadpool_limits

from .bootstrap import bootstrap_macro_f1, paired_difference
from .io import file_sha256, new_directory, read_json, write_json
from .models import build_model, feature_columns
from .config import TARGET
from .training import metrics, peak_rss_mb

ALPHAS = (0.0, 0.35, 0.50, 0.65, 0.80, 1.0)
MINORITY_DEFINITION = 'train_fraction < 1/K; unweighted mean of validation class recalls; zero_division=0'


class FoldWeightedClassifier(ClassifierMixin, BaseEstimator):
    """Learn exact alpha weights inside fit, including each GridSearchCV fold."""
    def __init__(self, estimator, alpha=1.0):
        self.estimator = estimator
        self.alpha = alpha

    def fit(self, X, y):
        if not np.isfinite(self.alpha) or not 0 <= self.alpha <= 1:
            raise ValueError('alpha must be in [0, 1]')
        targets = pd.Series(np.asarray(y))
        if targets.empty or targets.isna().any():
            raise ValueError('Nonempty, nonmissing targets are required')
        counts = targets.value_counts()
        self.class_weights_ = {label: float((len(targets) / (len(counts) * count)) ** self.alpha)
                               for label, count in counts.items()}
        self.estimator_ = clone(self.estimator)
        self.estimator_.fit(X, y, sample_weight=compute_sample_weight('balanced', y) ** self.alpha)
        self.classes_ = self.estimator_.classes_
        return self

    def predict(self, X):
        return self.estimator_.predict(X)

    def predict_proba(self, X):
        return self.estimator_.predict_proba(X)


def appendix_grid(family):
    if family == 'random_forest':
        return {'max_depth': [14, 18, 22], 'min_samples_leaf': [5, 10], 'max_samples': [0.15, 0.25]}
    if family == 'hist_gradient_boosting':
        return {'learning_rate': [0.05, 0.10], 'max_leaf_nodes': [15, 31, 63], 'min_samples_leaf': [20, 50]}
    raise ValueError(f'Unsupported appendix family: {family}')


def load_inputs(processed, run):
    processed, run = Path(processed), Path(run)
    metadata = read_json(run / 'metadata.json')
    hashes = {'dataset_manifest': file_sha256(processed / 'dataset_manifest.json')}
    if hashes['dataset_manifest'] != metadata['dataset_manifest_sha256']:
        raise ValueError('Frozen dataset manifest mismatch')
    manifest = read_json(processed / 'dataset_manifest.json')
    if manifest.get('history_policy') != 'strict_prior_timestamp_before_train_cap':
        raise ValueError('Frozen causal history dataset is required')
    for name in ('experiments', 'selection'):
        hashes[name] = file_sha256(run / f'{name}.json')
        if hashes[name] != metadata[f'{name}_sha256']:
            raise ValueError(f'Frozen {name} mismatch')
    frames = []
    for name in ('train', 'validation'):
        hashes[name] = file_sha256(processed / f'{name}.parquet')
        if hashes[name] != manifest['files'][name]:
            raise ValueError(f'{name} checksum mismatch')
        frames.append(pd.read_parquet(processed / f'{name}.parquet'))
    train, val = frames
    if set(train.match_id) & set(val.match_id):
        raise ValueError('Match leakage between train and validation')
    classes = manifest['classes']
    if set(train[TARGET]) != set(classes) or set(val[TARGET]) - set(classes):
        raise ValueError('Targets differ from frozen classes')
    experiments = read_json(run / 'experiments.json')
    selection = read_json(run / 'selection.json')
    if selection.get('main_feature_set') != 'loadout_history' or selection['with_placement']:
        raise ValueError('Baseline must use causal D without placement')
    return train, val, classes, experiments, selection, hashes


def balanced_spec(experiments, family):
    return next(e for e in experiments if e['family'] == family and e['balanced']
                and e['feature_set'] == 'loadout_history')


def weighted_pipeline(family, params, alpha, jobs):
    pipeline = build_model(family, False, 'loadout_history', jobs=jobs, **params)
    return pipeline.set_params(model=FoldWeightedClassifier(pipeline.named_steps['model'], alpha))


def prediction_metrics(model, frame, columns, classes):
    prediction = model.predict(frame[columns])
    return prediction, metrics(frame[TARGET], prediction, classes,
                                model.predict_proba(frame[columns]), model.classes_)


def run_grid(train, val, classes, experiments, output, family, jobs):
    spec = balanced_spec(experiments, family)
    columns = feature_columns('loadout_history')
    folds = list(GroupKFold(n_splits=3).split(train[columns], train[TARGET], groups=train.match_id))
    assignments = []
    for fold, (fit_idx, score_idx) in enumerate(folds):
        assert not set(train.iloc[fit_idx].match_id) & set(train.iloc[score_idx].match_id)
        assignments.append(train.iloc[score_idx].groupby('match_id').size().rename('rows').reset_index().assign(fold=fold))
    pd.concat(assignments).to_csv(output / 'appendix_cv_match_folds.csv', index=False)
    grid = {f'model__estimator__{key}': value for key, value in appendix_grid(family).items()}
    model = weighted_pipeline(family, spec['params'], 1.0, jobs)
    search = GridSearchCV(model, grid, scoring={
        'macro_f1': make_scorer(f1_score, labels=classes, average='macro', pos_label=None, zero_division=0),
        'accuracy': 'accuracy'}, refit='macro_f1', cv=folds, n_jobs=1, error_score='raise', verbose=2)
    started = time.perf_counter()
    search.fit(train[columns], train[TARGET])
    result = pd.DataFrame(search.cv_results_)
    result['params_json'] = result.params.map(lambda p: json.dumps(p, sort_keys=True))
    result['family'], result['alpha'], result['training_rows'] = family, 1.0, len(train)
    filename = 'appendix_rf_gridsearch_cv.csv' if family == 'random_forest' else 'appendix_hgb_gridsearch_cv.csv'
    result.drop(columns='params').to_csv(output / filename, index=False)
    _, scores = prediction_metrics(search.best_estimator_, val, columns, classes)
    pd.DataFrame([{'family': family, 'selected_by': 'grouped_cv_macro_f1', 'folds': 3,
        'params_json': json.dumps(search.best_params_, sort_keys=True), 'cv_macro_f1': search.best_score_,
        'alpha': 1.0, 'training_rows': len(train), 'validation_rows': len(val), **scores}]).to_csv(
            output / 'appendix_cv_best_validation.csv', index=False)
    joblib.dump(search.best_estimator_, output / 'appendix_cv_best.joblib')
    return {'family': family, 'candidates': len(result), 'cv_fits': len(result) * 3, 'refits': 1,
            'best_params': search.best_params_, 'best_cv_macro_f1': float(search.best_score_),
            'best_validation_metrics': scores, 'fixed_params': spec['params'],
            'weight_policy': 'exact_alpha_1_weights_learned_inside_each_fold',
            'seconds': time.perf_counter() - started}


def pareto_mask(table):
    scores = table[['macro_f1', 'accuracy']].to_numpy()
    return np.array([not ((scores >= row).all(axis=1) & (scores > row).any(axis=1)).any() for row in scores])


def class_recall_audit(train_targets, actual, prediction, classes):
    counts = pd.Series(train_targets).value_counts().reindex(classes, fill_value=0)
    matrix = confusion_matrix(actual, prediction, labels=classes)
    support = matrix.sum(axis=1)
    recall = np.divide(matrix.diagonal(), support, out=np.zeros(len(classes)), where=support != 0)
    table = pd.DataFrame({'label': classes, 'train_count': counts.to_numpy(),
        'train_fraction': counts.to_numpy() / len(train_targets),
        'is_minority': counts.to_numpy() < len(train_targets) / len(classes),
        'validation_support': support, 'true_positive': matrix.diagonal(),
        'false_negative': support - matrix.diagonal(), 'recall': recall})
    return table, matrix


def verify_alpha_reference(reference, current):
    keys = ['family', 'alpha']
    if len(reference) != 12 or len(current) != 12 or reference.duplicated(keys).any() or current.duplicated(keys).any():
        raise ValueError('Expected 12 unique family/alpha points in reference and rerun')
    reference = reference.set_index(keys).sort_index()
    current = current.set_index(keys).sort_index()
    if not reference.index.equals(current.index):
        raise ValueError('Alpha points differ from frozen reference')
    for column in ('params_json', 'class_weights_json'):
        if reference[column].map(json.loads).tolist() != current[column].map(json.loads).tolist():
            raise ValueError(f'Alpha reference differs: {column}')
    differences = {}
    for column in ('macro_f1', 'weighted_f1', 'accuracy', 'top_2_accuracy',
                   'tactical_role_macro_f1', 'tactical_role_accuracy', 'majority_validation_accuracy'):
        np.testing.assert_allclose(current[column], reference[column], atol=1e-12, rtol=0, err_msg=column)
        differences[column] = float((current[column] - reference[column]).abs().max())
    for column in ('is_pareto', 'exceeds_majority_accuracy', 'meets_plan_balance_target'):
        if not reference[column].equals(current[column]):
            raise ValueError(f'Alpha reference differs: {column}')
    return {'status': 'passed', 'points': 12, 'absolute_tolerance': 1e-12,
            'metric_max_absolute_differences': differences}


def run_alpha(train, val, classes, experiments, output, jobs):
    columns = feature_columns('loadout_history')
    rows, class_rows, confusion_rows = [], [], []
    majority = train[TARGET].value_counts().idxmax()
    majority_accuracy = float(val[TARGET].eq(majority).mean())
    for family in ('random_forest', 'hist_gradient_boosting'):
        spec = balanced_spec(experiments, family)
        for alpha in ALPHAS:
            started = time.perf_counter()
            model = weighted_pipeline(family, spec['params'], alpha, jobs)
            model.fit(train[columns], train[TARGET])
            prediction, scores = prediction_metrics(model, val, columns, classes)
            audit, matrix = class_recall_audit(train[TARGET], val[TARGET], prediction, classes)
            minority = audit.loc[audit.is_minority]
            scores['minority_recall'] = float(minority.recall.mean()) if len(minority) else None
            class_rows.append(audit.assign(family=family, alpha=alpha))
            confusion_rows.extend({'family': family, 'alpha': alpha, 'actual': actual,
                'predicted': predicted, 'count': int(matrix[i, j])}
                for i, actual in enumerate(classes) for j, predicted in enumerate(classes))
            rows.append({'family': family, 'alpha': alpha, 'params_json': json.dumps(spec['params'], sort_keys=True),
                'class_weights_json': json.dumps(model.named_steps['model'].class_weights_, sort_keys=True),
                'minority_classes_json': json.dumps(minority.label.tolist()),
                'minority_definition': MINORITY_DEFINITION,
                'majority_validation_accuracy': majority_accuracy,
                'seconds': time.perf_counter() - started, **scores})
            print(f'alpha {family} alpha={alpha} macro_f1={scores["macro_f1"]:.6f} accuracy={scores["accuracy"]:.6f}', flush=True)
    table = pd.DataFrame(rows)
    table['is_pareto'] = False
    for _, part in table.groupby('family'):
        table.loc[part.index, 'is_pareto'] = pareto_mask(part)
    table['exceeds_majority_accuracy'] = table.accuracy > majority_accuracy
    table['meets_plan_balance_target'] = (table.accuracy > .55) & (table.macro_f1 > .415)
    table.to_csv(output / 'appendix_alpha_tradeoff.csv', index=False)
    per_class = pd.concat(class_rows, ignore_index=True)
    per_class.to_csv(output / 'appendix_alpha_class_recall.csv', index=False)
    pd.DataFrame(confusion_rows).to_csv(output / 'appendix_alpha_confusion.csv', index=False)
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    for ax, (family, part) in zip(axes, table.groupby('family', sort=False)):
        ax.plot(part.accuracy, part.macro_f1, marker='o')
        for row in part.itertuples():
            ax.annotate(f'alpha={row.alpha:g}', (row.accuracy, row.macro_f1), xytext=(4, 5), textcoords='offset points', fontsize=8)
        ax.axvline(majority_accuracy, linestyle='--', color='grey', label='Majority accuracy')
        front = part.loc[part.is_pareto]
        ax.scatter(front.accuracy, front.macro_f1, facecolors='none', edgecolors='black', s=100, label='Pareto')
        ax.set(xlabel='Validation accuracy', title=family)
        ax.legend(fontsize=8)
    axes[0].set_ylabel('Validation macro-F1')
    fig.tight_layout(); fig.savefig(output / 'appendix_alpha_tradeoff.png', dpi=160); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    for ax, (family, part) in zip(axes, per_class.groupby('family', sort=False)):
        for label, curve in part.groupby('label', sort=False):
            ax.plot(curve.alpha, curve.recall, marker='o', label=label)
        aggregate = table.loc[table.family == family]
        ax.plot(aggregate.alpha, aggregate.minority_recall, '--', color='black', label='Minority macro recall')
        ax.set(xlabel='Alpha', ylabel='Validation recall', title=family, ylim=(0, 1))
        ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(output / 'appendix_alpha_minority_recall.png', dpi=160); plt.close(fig)
    return {'fits': len(table), 'majority_validation_accuracy': majority_accuracy,
            'minority_definition': MINORITY_DEFINITION, 'minority_classes': minority.label.tolist(),
            'class_recall_rows': len(per_class), 'confusion_rows': len(confusion_rows),
            'weight_formula': '(N / (K * N_c)) ** alpha; no clipping or normalization',
            'fixed_parameters_source': 'balanced_D_experiment_in_frozen_main_run',
            'rf_weight_note': 'fixed per-training-class sample weights; alpha=1 differs from balanced_subsample'}


def load_frozen_pipeline(run, experiment):
    path = Path(run) / experiment['pipeline']
    if file_sha256(path) != experiment['sha256']:
        raise ValueError('Frozen pipeline checksum mismatch')
    return joblib.load(path)


def run_placement(train, val, classes, experiments, selection, run, output, jobs):
    baseline = next(e for e in experiments if e['name'] == selection['best'])
    context = next(e for e in experiments if e['name'] == selection['ablation']['C'])
    predictions, rows = {}, []
    for label, experiment in [('C', context), ('D', baseline)]:
        pipeline = load_frozen_pipeline(run, experiment)
        prediction, scores = prediction_metrics(pipeline, val, experiment['columns'], classes)
        if not np.isclose(scores['macro_f1'], experiment['macro_f1'], atol=1e-12, rtol=0):
            raise ValueError('Frozen pipeline does not reproduce validation score')
        predictions[label] = prediction
        rows.append({'configuration': label, 'with_placement': False, 'interpretation': 'causal',
                     'family': experiment['family'], **scores})
    columns = feature_columns('loadout_history', with_placement=True)
    model = build_model(baseline['family'], baseline['balanced'], 'loadout_history', True, jobs, **baseline['params'])
    weights = {}
    if baseline['family'] == 'hist_gradient_boosting' and baseline['balanced']:
        weights['model__sample_weight'] = compute_sample_weight('balanced', train[TARGET])
    model.fit(train[columns], train[TARGET], **weights)
    predictions['D+placement'], scores = prediction_metrics(model, val, columns, classes)
    rows.append({'configuration': 'D+placement', 'with_placement': True, 'interpretation': 'retrospective',
                 'family': baseline['family'], **scores})
    table = pd.DataFrame(rows).set_index('configuration')
    draws = bootstrap_macro_f1(val[TARGET], predictions, val.match_id, classes)
    draws.to_csv(output / 'appendix_placement_bootstrap.csv', index=False)
    table['macro_f1_ci95_low'] = draws.quantile(.025)
    table['macro_f1_ci95_high'] = draws.quantile(.975)
    table['delta_macro_f1_vs_D'] = table.macro_f1 - table.loc['D', 'macro_f1']
    table['delta_accuracy_vs_D'] = table.accuracy - table.loc['D', 'accuracy']
    table.loc[['D', 'D+placement']].to_csv(output / 'appendix_placement_comparison.csv')
    table.to_csv(output / 'appendix_context_history_placement.csv')
    gains = []
    for before, after in [('C', 'D'), ('D', 'D+placement')]:
        gains.append({**paired_difference(draws, table.macro_f1.to_dict(), before, after),
                      'accuracy_difference': table.loc[after, 'accuracy'] - table.loc[before, 'accuracy']})
    pd.DataFrame(gains).to_csv(output / 'appendix_history_placement_gains.csv', index=False)
    difference = 2 * draws['D'] - draws['C'] - draws['D+placement']
    low, high = difference.quantile([.025, .975])
    return {'fits': 1, 'family': baseline['family'], 'fixed_params': baseline['params'],
            'baseline': baseline['name'], 'placement_columns': columns[-3:],
            'history_gain_minus_placement_gain': float(2*table.loc['D','macro_f1']-table.loc['C','macro_f1']-table.loc['D+placement','macro_f1']),
            'history_gain_minus_placement_gain_ci95': [float(low), float(high)],
            'interpretation': 'retrospective placement is excluded from the frozen main model'}


def run_appendix(processed, run, output, section, jobs=2):
    if section not in ('rf_grid', 'hgb_grid', 'alpha_placement', 'alpha_recall') or jobs < 1:
        raise ValueError('Invalid appendix section or jobs')
    started = time.perf_counter()
    train, val, classes, experiments, selection, hashes = load_inputs(processed, run)
    output = new_directory(output)
    with threadpool_limits(limits=jobs), warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter('always')
        if section in ('rf_grid', 'hgb_grid'):
            family = 'random_forest' if section == 'rf_grid' else 'hist_gradient_boosting'
            result = run_grid(train, val, classes, experiments, output, family, jobs)
        elif section == 'alpha_recall':
            result = {'alpha': run_alpha(train, val, classes, experiments, output, jobs)}
        else:
            result = {'alpha': run_alpha(train, val, classes, experiments, output, jobs),
                      'placement': run_placement(train, val, classes, experiments, selection, run, output, jobs)}
    blocked = [str(w.message) for w in captured if isinstance(w.message, (ConvergenceWarning, RuntimeWarning))]
    summary = {'status': 'failed' if blocked else 'passed', 'section': section, 'test_read': False,
        'training_rows': len(train), 'validation_rows': len(val), 'train_matches': int(train.match_id.nunique()),
        'validation_matches': int(val.match_id.nunique()), 'classes': classes, 'input_sha256': hashes,
        'main_selection_unchanged': selection['best'], 'seconds': time.perf_counter()-started,
        'process_peak_rss_mb': peak_rss_mb(), 'blocking_warnings': blocked,
        'library_warnings': sorted({str(w.message) for w in captured if not isinstance(w.message,(ConvergenceWarning,RuntimeWarning))}),
        'result': result}
    write_json(output / 'appendix_summary.json', summary)
    if blocked:
        raise RuntimeError(f'Appendix emitted blocking warnings: {blocked}')
    return summary
