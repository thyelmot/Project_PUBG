"""One locked final test evaluation, reports and error analysis."""
from itertools import combinations
from pathlib import Path

import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.metrics import ConfusionMatrixDisplay, classification_report, confusion_matrix, f1_score, make_scorer
from threadpoolctl import threadpool_limits

from .bootstrap import bootstrap_macro_f1, paired_difference
from .config import SEED
from .error_analysis import write_error_tables
from .io import file_sha256, new_directory, read_json, write_json
from .config import TARGET
from .training import history_subset_metrics, metrics


def run_evaluation(processed, run, output, jobs=2):
    processed, run, output = Path(processed), Path(run), Path(output)
    if jobs < 1:
        raise ValueError('jobs must be positive')
    metadata = read_json(run / 'metadata.json')
    manifest = read_json(processed / 'dataset_manifest.json')
    if manifest.get('audit_cause_column') != 'cause_for_audit':
        raise ValueError('Dataset lacks Other audit causes; rerun preprocessing before evaluation')
    if 'source_match_splits_sha256' not in manifest:
        raise ValueError('Dataset has no fixed source holdout; rerun EDA and preprocessing')
    if file_sha256(processed / 'dataset_manifest.json') != metadata['dataset_manifest_sha256']:
        raise ValueError('Dataset differs from the frozen training dataset')
    for filename in ('experiments', 'selection'):
        if file_sha256(run / f'{filename}.json') != metadata[f'{filename}_sha256']:
            raise ValueError(f'Frozen {filename} was modified')
    experiments, selection = read_json(run / 'experiments.json'), read_json(run / 'selection.json')
    for experiment in experiments:
        if file_sha256(run / experiment['pipeline']) != experiment['sha256']:
            raise ValueError(f'Pipeline checksum mismatch: {experiment["name"]}')
    if output.exists():
        raise FileExistsError(output)
    # Exclusive creation also prevents two processes evaluating the same run.
    with (run / 'evaluation_started.json').open('x') as stream:
        stream.write('{"status": "started"}\n')
    output = new_directory(output)
    if file_sha256(processed / 'test.parquet') != manifest['files']['test']:
        raise ValueError('Test data checksum mismatch')
    test = pd.read_parquet(processed / 'test.parquet')
    classes = metadata['classes']
    if set(test[TARGET].unique()) - set(classes):
        raise ValueError('Test contains unseen target classes')
    rows, per_class, predictions, best_prediction = [], [], {}, None
    history_rows = []
    main_feature_set = selection.get("main_feature_set", "full")
    with threadpool_limits(limits=jobs):
        for experiment in experiments:
            pipeline = joblib.load(run / experiment['pipeline'])
            prediction = pipeline.predict(test[experiment['columns']])
            probabilities = pipeline.predict_proba(test[experiment['columns']])
            if 'has_prior_kill' in test:
                history_rows.extend(history_subset_metrics(test, prediction, classes, probabilities, pipeline.classes_, experiment['name']))
            predictions[experiment['name']] = prediction
            rows.append({'name': experiment['name'], 'family': experiment['family'],
                         'balanced': experiment['balanced'], 'feature_set': experiment['feature_set'],
                         'interpretation': selection['interpretation'],
                         **metrics(test[TARGET], prediction, classes, probabilities, pipeline.classes_)})
            report = classification_report(test[TARGET], prediction, labels=classes, output_dict=True, zero_division=0)
            for label in classes:
                per_class.append({'name': experiment['name'], 'class': label, **report[label]})
            if experiment['name'] == selection['best']:
                best_prediction = prediction
        all_metrics = pd.DataFrame(rows).set_index('name')
        draws = bootstrap_macro_f1(test[TARGET], predictions, test.match_id, classes)
        intervals = draws.quantile([0.025, 0.975])
        all_metrics['macro_f1_ci95_low'] = intervals.loc[0.025]
        all_metrics['macro_f1_ci95_high'] = intervals.loc[0.975]
        draws.to_csv(output / 'bootstrap_macro_f1.csv', index=False)
        full_names = all_metrics.index[all_metrics.feature_set == main_feature_set]
        all_metrics.loc[full_names].to_csv(output / 'test_metrics.csv')
        scores = all_metrics.macro_f1.to_dict()
        pd.DataFrame([paired_difference(draws, scores, before, after)
            for before, after in combinations(full_names, 2)]).to_csv(output / 'paired_model_differences.csv', index=False)
        ablation_names = selection['ablation']
        pd.DataFrame([{'ablation_change': f'{before}->{after}',
            **paired_difference(draws, scores, ablation_names[before], ablation_names[after])}
            for before, after in zip(list(ablation_names)[:-1], list(ablation_names)[1:])]).to_csv(output / 'ablation_gains.csv', index=False)
        ablation = all_metrics.loc[list(selection['ablation'].values())].copy()
        ablation.insert(0, 'ablation', list(selection['ablation']))
        ablation.to_csv(output / 'ablation.csv')
        pd.DataFrame(history_rows).to_csv(output / 'history_subset_metrics.csv', index=False)
        pd.DataFrame(per_class).to_csv(output / 'per_class_metrics.csv', index=False)
        matrix = confusion_matrix(test[TARGET], best_prediction, labels=classes)
        pd.DataFrame(matrix, index=classes, columns=classes).to_csv(output / 'confusion_matrix.csv')
        fig, ax = plt.subplots(figsize=(9, 8))
        ConfusionMatrixDisplay(matrix, display_labels=classes).plot(ax=ax, colorbar=False, xticks_rotation=45)
        fig.tight_layout()
        fig.savefig(output / 'confusion_matrix.png')
        plt.close(fig)
        write_error_tables(test, best_prediction, classes, output)
        importance_experiment = max((e for e in experiments
            if e['feature_set'] == main_feature_set and e['family'] in
            ('decision_tree', 'random_forest', 'hist_gradient_boosting')), key=lambda e: e['macro_f1'])
        importance_pipeline = joblib.load(run / importance_experiment['pipeline'])
        importance_sample = test.sample(min(2000, len(test)), random_state=SEED)
        importance = permutation_importance(importance_pipeline, importance_sample[importance_experiment['columns']],
            importance_sample[TARGET], n_repeats=3, random_state=SEED, n_jobs=1,
            scoring=make_scorer(f1_score, labels=classes, average='macro', pos_label=None, zero_division=0))
        importance_frame = pd.DataFrame({'feature': importance_experiment['columns'],
            'importance_mean': importance.importances_mean, 'importance_std': importance.importances_std})
        importance_frame.sort_values('importance_mean', ascending=False).to_csv(output / 'feature_importance.csv', index=False)
        fig, ax = plt.subplots(figsize=(9, 6))
        importance_frame.sort_values('importance_mean').plot.barh(x='feature', y='importance_mean', ax=ax, legend=False)
        ax.set(xlabel='Decrease in macro-F1 after permutation', ylabel='')
        fig.tight_layout()
        fig.savefig(output / 'feature_importance.png')
        plt.close(fig)
    result = {'best_selected_on_validation': selection['best'], 'test_rows': len(test),
              'bootstrap': {'unit': 'match_id', 'repeats': 1000, 'seed': SEED,
                            'confidence': 0.95, 'method': 'paired_percentile',
                            'matches': int(test.match_id.nunique())},
              'interpretation': selection['interpretation'], 'importance_rows': len(importance_sample),
              'importance_method': 'permutation_macro_f1_3_repeats',
              'importance_model_selected_on_validation': importance_experiment['name'],
              'best_metrics': all_metrics.loc[selection['best']].to_dict(),
              'run_metadata_sha256': file_sha256(run / 'metadata.json')}
    write_json(output / 'evaluation_summary.json', result)
    write_json(run / 'evaluation_complete.json', {'output': str(output.resolve())})
    return result
