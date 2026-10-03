from datetime import datetime, timezone
import os
import csv
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from src.data.io import atomic_write_json, publish_file, read_json
from src.utils.hashing import hash_file
from src.utils.hashing import hash_dict
from src.data.checkpoints import CheckpointManager

CATEGORIES = ('tables', 'figures', 'models', 'predictions', 'metadata')


def artifact_metadata(path):
    """Read schemas/counts without collecting a large dataset into RAM."""
    path = Path(path)
    if not path.is_file() or not path.stat().st_size:
        raise ValueError(f'Missing/empty selected artifact: {path}')
    details = {'sha256': hash_file(path), 'byte_size': path.stat().st_size}
    if path.suffix == '.csv':
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.reader(stream)
            details['columns'] = next(reader, [])
            scope_positions = [index for index, name in enumerate(details['columns']) if name in {'scope', 'analysis_scope'}]
            scopes, count = set(), 0
            for row in reader:
                if len(row) != len(details['columns']):
                    raise ValueError(f'CSV cardinality/schema mismatch: {path}')
                count += 1
                scopes.update(row[index] for index in scope_positions)
            details['row_count'] = count
            if scope_positions:
                details['observed_scopes'] = sorted(scopes)
        if not details['columns']:
            raise ValueError(f'Empty CSV schema: {path}')
    elif path.suffix == '.parquet':
        import pyarrow.parquet as pq
        parquet = pq.ParquetFile(path)
        details.update(columns=parquet.schema_arrow.names, row_count=parquet.metadata.num_rows)
    elif path.suffix == '.json':
        read_json(path)
    return details


def _resolve(base, path):
    return (Path(base) / Path(path)).resolve()


def _committed(manager, stage, signature):
    record = manager.load_manifest()['stages'].get(stage, {})
    if not signature or not manager.is_compatible(stage, signature):
        raise ValueError(f'{stage}: incomplete/stale/corrupt; rerun its producer first')
    return record, {name: _resolve(manager.manifest_path.parent, path)
                    for name, path in record['artifacts'].items()}


def export_locked_rq1(paths, cfg):
    """Full descriptive export of the allowlist frozen in G4, never reselection.

    Optional explicit operation before final receipt review, not a side effect of
    read-only release verification. Synthetic approval still produces a fixture.
    """
    from src.models.rq3_selection import validate_selection_lock
    from src.analysis.rq1 import run_rq1_analysis, generate_rq1_interpretations
    from src.features.registry import FeatureRegistry
    recipe = read_json(paths['manifests'] / 'rq3_selection_lock.json')
    validate_selection_lock(paths, cfg, recipe)
    design = recipe['decision'].get('descriptive_design', {})
    if (design.get('rq1') != 'full_descriptive_locked' or design.get('no_reselection') is not True
            or design.get('rq2_config_hash') != hash_dict(cfg['rq2'])):
        raise ValueError('Register descriptive RQ1/RQ2 design in G4 BEFORE test; no post-test approval')
    source = Path(recipe['inputs']['features']['path'])
    signature = hash_dict({'g4': recipe['recipe_hash'], 'source': hash_file(source), 'design': design})
    manager = CheckpointManager(paths['checkpoints'] / 'checkpoint_manifest.json')
    if manager.is_compatible('rq1', signature):
        return {key: Path(value) for key, value in manager.restore('rq1')['artifacts'].items()}
    manager.mark_running('rq1', signature)
    try:
        table_path = paths['tables'] / 'rq1_relationship_summary.csv'
        table = run_rq1_analysis(source, FeatureRegistry(), table_path, analysis_scope='full_descriptive_locked')
        interpretations = paths['manifests'] / 'rq1_interpretations.json'
        generate_rq1_interpretations(table, output_json_path=interpretations)
        design_path = paths['manifests'] / 'full_descriptive_design_receipt.json'
        atomic_write_json(design_path, {**design, 'g4_hash': recipe['recipe_hash'], 'approved_before_test': True,
                         'rq2': cfg['rq2'], 'source_sha256': hash_file(source), 'scope': 'full_descriptive_locked'})
        import matplotlib.pyplot as plt
        artifacts = {'summary_table': table_path, 'interpretations': interpretations, 'descriptive_design': design_path}
        # Existing statistics only; do not inspect outcomes to choose features again.
        for target in table.target.unique():
            data = table.loc[table.target.eq(target) & table.is_primary_valid & table.status.eq('valid')]
            if data.empty:
                continue
            fig, ax = plt.subplots(figsize=(12, max(5, data.feature.nunique() * .35)))
            pivot = data.pivot(index='feature', columns='mode', values='spearman_rho')
            pivot.plot.barh(ax=ax)
            ax.axvline(0, color='black', linewidth=1)
            ax.set_xlabel('Spearman rho (không đơn vị); không có CI đã hiệu chỉnh')
            ax.set_ylabel('Đặc trưng hợp lệ theo allowlist G4')
            label = recipe['decision'].get('data_scope', 'Full descriptive locked')
            ax.set_title(f'RQ1 mô tả theo mode: {target}\n{label}; pair N={data.n_observations.min()}-{data.n_observations.max()}')
            fig.tight_layout()
            path = paths['figures'] / f'rq1_full_{target}.png'
            fig.savefig(path, dpi=150, bbox_inches='tight')
            plt.close(fig)
            artifacts['figure_' + target] = path
        manager.commit('rq1', signature, artifacts, metadata={'run_id': 'rq1_' + uuid.uuid4().hex,
                       'analysis_scope': 'full_descriptive_locked', 'g4_hash': recipe['recipe_hash']})
        return artifacts
    except Exception as error:
        manager.record_failure('rq1', signature, str(error), resource_limited=isinstance(error, MemoryError))
        raise


def inspect_finalization(paths, cfg):
    """Validate an explicit reviewer receipt; no model selection, fitting or test reads.

    finalization_selection.json lists checkpoint signatures, selected artifacts and
    figures. It is not an authorization to waive arbitrary research requirements.
    Missing production evidence keeps G5 closed; a synthetic receipt stays nonofficial.
    """
    from src.evaluation.comparisons import comparison_context
    selection_path = paths['manifests'] / 'finalization_selection.json'
    if not selection_path.is_file():
        raise ValueError(f'G5 pending: review required matrix and create {selection_path}; no automatic approval')
    selection = read_json(selection_path)
    if selection.get('format_version') != '1.0' or selection.get('approved') is not True or not selection.get('approved_by'):
        raise ValueError('G5 requires a versioned explicit reviewer receipt')
    fixture = selection.get('data_scope') == 'synthetic_fixture'
    if not fixture and (selection.get('data_scope') != 'full' or cfg['runtime']['mode'] != 'full'):
        raise ValueError('Development is not official full-data; G5 closed')
    context = comparison_context(paths, cfg)
    recipe, manager = context['recipe'], context['manager']
    if selection.get('config_hash') != hash_dict(cfg) or selection.get('g4_hash') != recipe['recipe_hash']:
        raise ValueError('G5 selection config/G4 stale')
    signatures = selection.get('stage_signatures', {})
    stages = ('rq1', 'rq2_clustering', 'rq3_prediction', 'ablation_error')
    if not set(stages).issubset(signatures):
        raise ValueError('Required checkpoint signatures missing')
    committed, records = {}, {}
    for stage in signatures:
        records[stage], committed[stage] = _committed(manager, stage, signatures.get(stage))
    if signatures['rq3_prediction'] != recipe['recipe_hash'] or signatures['ablation_error'] != context['signature']:
        raise ValueError('G5 prediction/comparison lineage mismatch')
    rq2_runs, rq2_files = select_rq2_results(paths, cfg)
    rq2_decisions = read_json(paths['manifests'] / 'rq2_decisions.json')
    if (rq2_decisions['mode_evidence'].get('source_checksum') != recipe['inputs']['features']['sha256']
            or rq2_decisions['mode_evidence'].get('split_checksum') != recipe['inputs']['split']['sha256']):
        raise ValueError('RQ2 source/split lineage differs from G4')
    selected = selection.get('artifacts', {})
    if set(selected) != set(CATEGORIES) or any(not isinstance(selected[c], dict) for c in CATEGORIES):
        raise ValueError('G5 requires all five explicit artifact categories')
    files, rows = {c: {} for c in CATEGORIES}, []
    for category in CATEGORIES:
        for key, item in selected[category].items():
            stage, artifact = item.get('stage'), item.get('artifact')
            if stage not in committed or artifact not in committed[stage]:
                raise ValueError(f'Uncommitted selected artifact: {category}/{key}')
            path = committed[stage][artifact]
            details = artifact_metadata(path)
            if item.get('sha256') != details['sha256']:
                raise ValueError(f'Selection checksum stale: {key}')
            required_columns = item.get('required_columns', [])
            if not set(required_columns).issubset(details.get('columns', [])):
                raise ValueError(f'Required schema missing: {key}')
            expected = {'.csv', '.parquet'} if category == 'tables' else {'.png', '.svg'} if category == 'figures' else {'.parquet'} if category == 'predictions' else None
            if expected is not None and path.suffix not in expected:
                raise ValueError(f'Artifact category/schema mismatch: {key}')
            files[category][key] = {'source': path, **details, 'stage': stage,
                                    'upstream_signature': signatures[stage]}
            if category == 'tables' and not fixture and (path.name.startswith('rq3_development_') or
                    any('development' in value.lower() for value in details.get('observed_scopes', []))):
                raise ValueError('Development tables may only be archived as diagnostic metadata, not official metrics')
            rows.append({'component': key, 'required': True, 'status': 'verified', 'reason': 'selected compatible checkpoint',
                         'run_id': item.get('run_id'), 'scope': selection['data_scope'], 'artifact': str(path),
                         'sha256': details['sha256'], 'upstream_signature': signatures[stage]})
    # Mandatory names link to actual producer paths, not reviewer-defined surrogate tables.
    required_tables = {'rq1': paths['tables'] / 'rq1_relationship_summary.csv',
                       'metrics': paths['tables'] / 'rq3_metrics_evaluation.csv',
                       'comparisons': paths['tables'] / 'rq3_paired_comparisons.csv',
                       'ablation': paths['tables'] / 'ablation_results.csv',
                       'errors': paths['tables'] / 'rq3_errors_evaluation.csv',
                       'importance': paths['tables'] / 'rq3_importance_evaluation.csv'}
    required_tables['features'] = paths['tables'] / 'rq3_features_evaluation.csv'
    import pandas as pd
    for name, path in required_tables.items():
        if path.resolve() not in {x['source'] for x in files['tables'].values()}:
            raise ValueError(f'Required table missing from selection: {name}')
    rq1 = pd.read_csv(required_tables['rq1'])
    rq1_columns = {'feature', 'target', 'mode', 'n_observations', 'pearson_r', 'spearman_rho', 'is_primary_valid', 'analysis_scope', 'status'}
    if rq1.empty or not rq1_columns.issubset(rq1.columns):
        raise ValueError('Required RQ1 schema/content missing')
    if not fixture and not rq1.analysis_scope.eq('full_descriptive_locked').all():
        raise ValueError('RQ1 development cannot enter official release')
    if not fixture and records['rq1'].get('metadata', {}).get('g4_hash') != recipe['recipe_hash']:
        raise ValueError('RQ1 full descriptive execution must reference the current G4 lock')
    rq1_run = records['rq1'].get('metadata', {}).get('run_id')
    if not rq1_run:
        raise ValueError('RQ1 actual execution run_id missing; rerun updated NB06')
    run_ids = {'rq1': rq1_run, **rq2_runs}
    matrix = [{'component': 'RQ1', 'required': True, 'status': 'completed', 'reason': 'compatible selected scope', 'run_id': run_ids['rq1']}]
    for mode, run_id in read_json(paths['manifests'] / 'rq2_decisions.json')['run_ids'].items():
        fitted = paths['tables'] / 'rq2' / mode / 'fitted_clustering_artifacts.joblib'
        if fitted.resolve() not in {item['source'] for item in files['models'].values()}:
            raise ValueError(f'Required RQ2 fitted imputer/scaler/centroids missing: {mode}')
        for filename in RQ2_RESULT_TABLES:
            path = paths['tables'] / 'rq2' / mode / filename
            if path.resolve() not in {x['source'] for x in files['tables'].values()}:
                raise ValueError(f'Required RQ2 table missing: {mode}/{filename}')
        status = pd.read_csv(paths['tables'] / 'rq2' / mode / 'clustering_robustness.csv')
        for component in ('C1_Main_KMeans', 'C2_Hierarchical_vs_KMeans', 'C3_Games_Played_Sensitivity', 'C4_Min_Games_Sensitivity', 'C5_Outcome_Comparison'):
            match = status.loc[status.comparison.eq(component)]
            if len(match) != 1 or match.iloc[0]['status'] != 'completed':
                raise ValueError(f'Required RQ2 task unresolved: {mode}/{component}')
            matrix.append({'component': f'{mode}/{component}', 'required': True, 'status': 'completed', 'reason': str(match.iloc[0]['reason']), 'run_id': run_id})
    registry = read_json(paths['manifests'] / 'rq3_development_registry.json')['experiments']
    required_models = {'s1_retrospective_survival', 'p1_ols_direct_survival', 'p2_ols_no_direct_survival',
                       't0_timing_ols', 't1_timing_ols'}
    required_models.update(f'{task}_baseline_{kind}' for task in ('s1', 'p1', 'p2') for kind in ('mean', 'median'))
    anchor = cfg['rq3']['experiments']['ablation_full_task']
    required_models.update(f'{anchor}_validation_ablation_{group}' for group in ('combat', 'movement', 'support', 'timing'))
    if not required_models.issubset(recipe['models']):
        raise ValueError('Required baselines/S/P/timing/ablation matrix incomplete')
    for key, model in recipe['models'].items():
        record = registry.get(key, {})
        if record.get('status') != 'completed' or record.get('run_id') != model['run_id']:
            raise ValueError(f'Actual experiment execution missing: {key}')
        for category, path in [('models', Path(model['model_path'])), ('predictions', context['files'][key])]:
            if path.resolve() not in {x['source'] for x in files[category].values()}:
                raise ValueError(f'Required selected {category} missing: {key}')
        if not any(item['sha256'] == model['metadata_hash'] for item in files['metadata'].values()):
            raise ValueError(f'Required fitted preprocessing/feature metadata missing: {key}')
        run_ids[key] = model['run_id']
        matrix.append({'component': key, 'required': True, 'status': 'completed', 'reason': 'G4 selected execution', 'run_id': model['run_id']})
    metrics = pd.read_csv(required_tables['metrics'])
    features = pd.read_csv(required_tables['features'])
    errors = pd.read_csv(required_tables['errors'])
    importance = pd.read_csv(required_tables['importance'])
    schemas = [(metrics, {'experiment_id', 'aggregation', 'mae', 'rmse', 'r2', 'n_rows', 'n_matches', 'scope'}),
               (features, {'experiment_id', 'run_id', 'cohort_hash', 'model_hash', 'recipe_hash', 'train_n', 'test_n'}),
               (errors, {'experiment_id', 'slice_category', 'n_observations', 'n_matches', 'status', 'unit', 'recipe_hash'}),
               (importance, {'experiment_id', 'importance_type', 'status'})]
    for table, columns in schemas:
        if table.empty or not columns.issubset(table.columns) or set(table.experiment_id) != set(recipe['models']):
            raise ValueError('Required metric/feature/error/importance schema or selected coverage missing')
    for key, model in recipe['models'].items():
        row = features.loc[features.experiment_id.eq(key)]
        if (len(row) != 1 or row.iloc[0].run_id != model['run_id'] or row.iloc[0].cohort_hash != model['cohort_hash']
                or row.iloc[0].model_hash != model['model_hash'] or row.iloc[0].recipe_hash != recipe['recipe_hash']):
            raise ValueError(f'Feature/cohort/run provenance mismatch: {key}')
        if set(metrics.loc[metrics.experiment_id.eq(key)].aggregation) != {'micro', 'match_aware', 'team_aware'}:
            raise ValueError('Hierarchical metric coverage missing')
    if not errors.recipe_hash.eq(recipe['recipe_hash']).all():
        raise ValueError('Error-analysis recipe mismatch')
    for task in ('s2', 'p3'):
        if any(model['task'] == task for model in recipe['models'].values()):
            continue
        chronology = selection.get('chronology', {})
        entries = [x for x in registry.values() if x.get('task') == task]
        if chronology.get('grade') != 'Grade C' or not entries or any(x.get('status') != 'blocked' or x.get('reason_code') != 'blocked_by_chronology' or x.get('metrics') is not None for x in entries):
            raise ValueError(f'{task}: no Grade C blocked exception; complete history or provide verified chronology')
        matrix.append({'component': task, 'required': 'conditional A/B', 'status': 'blocked', 'reason': 'Grade C; no future prediction', 'run_id': None})
    # Preserve optional failures explicitly, never fabricate metrics.
    for key, entry in registry.items():
        if key not in recipe['models'] and entry.get('status') != 'completed':
            if not entry.get('reason_code'):
                raise ValueError(f'Unresolved experiment reason missing: {key}')
            matrix.append({'component': key, 'required': False, 'status': entry['status'], 'reason': entry['reason_code'], 'run_id': entry.get('run_id')})
            if entry.get('metrics') is not None:
                raise ValueError('Incomplete experiment must not contain official scores')
            if entry['status'] == 'resource_limited':
                candidates = [item['source'] for group in files.values() for item in group.values()
                              if item['source'].name == 'rq3_development_resources.csv']
                evidence = pd.read_csv(candidates[0]) if candidates else pd.DataFrame()
                if evidence.empty or not {'experiment_id', 'status', 'reason_code'}.issubset(evidence.columns):
                    raise ValueError('Resource-limited candidate evidence missing')
                evidence = evidence.loc[evidence.experiment_id.eq(key)]
                if evidence.empty or not evidence.status.eq('resource_limited').all():
                    raise ValueError('Resource-limited status/evidence mismatch')
    comparisons = pd.read_csv(required_tables['comparisons'])
    if comparisons.empty or not {'reference', 'candidate', 'metric', 'aggregation', 'delta', 'ci_lower', 'ci_upper', 'n_rows', 'recipe_hash'}.issubset(comparisons.columns):
        raise ValueError('Comparison/uncertainty schema missing')
    if not comparisons.recipe_hash.eq(recipe['recipe_hash']).all():
        raise ValueError('Comparison recipe mismatch')
    for pair in recipe['decision']['comparisons']:
        subset = comparisons.loc[comparisons.reference.eq(pair['reference']) & comparisons.candidate.eq(pair['candidate'])]
        if set(subset.metric) != {'mae', 'rmse', 'r2'} or not (subset.n_rows > 0).all():
            raise ValueError('Required comparison coverage incomplete')
        finite_ci = subset.loc[subset.aggregation.eq('micro') & subset.metric.isin(['mae', 'rmse'])]
        if len(finite_ci) != 2 or finite_ci[['ci_lower', 'ci_upper']].isna().any().any():
            raise ValueError('Required uncertainty missing; G5 closed')
    figures = selection.get('figure_metadata', {})
    if not figures or set(figures) != set(files['figures']):
        raise ValueError('Figure manifest empty/incomplete')
    for key, figure in figures.items():
        required = ('research_question', 'source_experiment', 'source_table', 'purpose', 'caption', 'scope', 'sampling', 'report_ready')
        if any(field not in figure for field in required) or not figure['caption'] or not figure['purpose']:
            raise ValueError(f'Figure metadata incomplete: {key}')
        if figure['source_table'] not in files['tables'] or figure['source_experiment'] not in run_ids:
            raise ValueError(f'Figure source not selected: {key}')
        if fixture and figure['report_ready']:
            raise ValueError('Synthetic figure cannot be report_ready')
        if figure['report_ready'] and figure['scope'] not in {'locked_test', 'full_descriptive_locked'}:
            raise ValueError('Development/diagnostic figure cannot be report_ready')
        sampling = figure['sampling']
        if not isinstance(sampling, dict) or 'sampled' not in sampling or (sampling['sampled'] and
                any(field not in sampling for field in ('n', 'seed', 'rule', 'population', 'reason'))):
            raise ValueError('Figure sampling disclosure incomplete')
    provenance = selection.get('provenance', {})
    for key in ('source_inventory', 'split', 'cohort', 'feature_registry', 'decisions', 'environment', 'leakage_checks', 'descriptive_design'):
        if key not in provenance or provenance[key] not in files['metadata']:
            raise ValueError(f'Required provenance missing: {key}')
    # Reviewed hashes are pinned to the current G4 data/split and source tree.
    metadata_paths = {key: item['source'] for key, item in files['metadata'].items()}
    if metadata_paths[provenance['split']] != Path(recipe['inputs']['split']['path']).resolve():
        raise ValueError('Split provenance differs from G4')
    leakage = read_json(metadata_paths[provenance['leakage_checks']])
    design = read_json(metadata_paths[provenance['descriptive_design']])
    if leakage.get('status') != 'passed' or leakage.get('code_hash') != recipe['code_hash'] or not leakage.get('tests'):
        raise ValueError('Leakage evidence incomplete/stale')
    if design.get('g4_hash') != recipe['recipe_hash'] or design.get('no_reselection') is not True:
        raise ValueError('Full descriptive design not locked to G4; no test reselection allowed')
    chronology_file = selection.get('chronology', {}).get('artifact')
    if any(row['status'] == 'blocked' and row['required'] == 'conditional A/B' for row in matrix):
        if chronology_file not in metadata_paths or read_json(metadata_paths[chronology_file]).get('grade') != 'Grade C':
            raise ValueError('Grade C chronology evidence missing/mismatched')
        if not fixture:
            from src.features.history_workflow import verify_chronology, inputs
            from src.data.io import get_duckdb_connection
            chronology_path = metadata_paths[chronology_file]
            if chronology_path != inputs(paths)['chronology_checksum'].resolve():
                raise ValueError('Grade C exception must use authoritative NB02 chronology report')
            connection = get_duckdb_connection()
            try:
                if verify_chronology(connection, inputs(paths)['source_checksum'], inputs(paths)['metadata_checksum'], read_json(chronology_path)) != 'Grade C':
                    raise ValueError('Grade C exception does not match verified metadata')
            finally:
                connection.close()
    inventory = read_json(metadata_paths[provenance['source_inventory']])
    if not fixture:
        shards = inventory.get('aggregate_shards', []) + inventory.get('death_shards', [])
        if (not inventory.get('aggregate_shards') or not inventory.get('death_shards')
                or inventory.get('total_files') != len(shards)):
            raise ValueError('Full source coverage unresolved')
        for source in shards:
            staged = source.get('staged_file')
            if (source.get('status') != 'valid' or source.get('row_count', -1) < 0
                    or not staged or not source.get('staged_sha256')
                    or hash_file(staged) != source['staged_sha256']):
                raise ValueError('Full source inventory/staged coverage changed/incomplete')
        if inventory.get('storage_format') == 'zip_streaming':
            archive = inventory.get('source_info', {})
            if not archive.get('archive_sha256') or hash_file(archive['archive_path']) != archive['archive_sha256']:
                raise ValueError('Full archive source checksum missing/changed')
        else:
            for source in shards:
                if not source.get('sha256') or hash_file(Path(inventory['raw_root'])/source['relative_path']) != source['sha256']:
                    raise ValueError('Full raw source changed')
        environment = read_json(metadata_paths[provenance['environment']])
        environment = environment.get('runtime', environment)
        if not environment.get('packages') or not environment.get('python_version'):
            raise ValueError('Environment/package provenance missing')
        if design.get('approved_before_test') is not True or not design.get('rq1') or not design.get('rq2'):
            raise ValueError('Descriptive recipe approval before test missing')
        frozen_design = recipe['decision'].get('descriptive_design', {})
        if frozen_design.get('rq1') != 'full_descriptive_locked' or frozen_design.get('rq2_config_hash') != hash_dict(cfg['rq2']):
            raise ValueError('Descriptive design not registered before G4/test')
        snapshot = read_json(metadata_paths[provenance['environment']])
        if snapshot.get('config') != {key: value for key, value in cfg.items() if key != '_project_root'}:
            raise ValueError('Environment/config snapshot stale')
    if not any(item['source'] == (paths['manifests'] / 'rq3_selection_lock.json').resolve() for item in files['metadata'].values()):
        raise ValueError('G4 locked recipe missing from selected release metadata')
    if not fixture and recipe['decision'].get('data_scope') != 'full':
        raise ValueError('Only explicitly full-scope G4 can be promoted to production G5')
    for row in rows:
        source = Path(row['artifact'])
        matches = [model['run_id'] for key, model in recipe['models'].items()
                   if source in {Path(model['model_path']).resolve(), context['files'][key].resolve()}]
        row['run_id'] = matches[0] if matches else run_ids['rq1'] if row['upstream_signature'] == signatures['rq1'] else ', '.join(rq2_runs.values()) if row['upstream_signature'] == signatures['rq2_clustering'] else recipe['recipe_hash']
    return {'selection': selection, 'selection_path': selection_path, 'files': files, 'matrix': matrix,
            'artifact_rows': rows, 'run_ids': run_ids, 'signature': hash_dict(selection), 'fixture': fixture,
            'manager': manager, 'records': records}


def publish_final_release(paths, cfg, inspected=None):
    """Copy only selected files; publish canonical manifest last after read-back validation."""
    current = inspect_finalization(paths, cfg)
    if inspected is not None and inspected['signature'] != current['signature']:
        raise ValueError('G5 inputs changed after inspection')
    inspected = current
    manager, signature = current['manager'], current['signature']
    if manager.is_compatible('finalization', signature):
        record = manager.load_manifest()['stages']['finalization']
        manifest_path = _resolve(manager.manifest_path.parent, record['artifacts']['release_manifest'])
        valid, errors = verify_final_manifest_integrity(manifest_path)
        if not valid:
            raise ValueError(f'Locked release corrupt: {errors}')
        return read_json(manifest_path), manifest_path
    manager.mark_running('finalization', signature)
    release_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '_' + uuid.uuid4().hex[:8]
    release_root = paths['manifests'] / 'releases' / release_id
    release_root.mkdir(parents=True, exist_ok=False)
    output = release_root / 'final_results_manifest.json'
    manifest = {'format_version': '4.0', 'release_id': release_id, 'finalized_at': datetime.now(timezone.utc).isoformat(),
                'status': 'fixture_locked' if current['fixture'] else 'LOCKED', 'report_ready': not current['fixture'],
                'data_scope': current['selection']['data_scope'], 'official_run_ids': current['run_ids'],
                'required_matrix': current['matrix'], 'selection_hash': signature,
                'prior_test_exposure': read_json(paths['manifests'] / 'rq3_selection_lock.json')['prior_test_exposure'],
                'upstream_records': current['records'], **{c: {} for c in CATEGORIES}}
    try:
        required_bytes = sum(item['byte_size'] for group in current['files'].values() for item in group.values())
        if shutil.disk_usage(release_root).free < required_bytes * 1.2:
            raise MemoryError('Release snapshot exceeds measured free volume space; not Drive account quota; no partial promotion')
        for category in CATEGORIES:
            for index, (key, info) in enumerate(current['files'][category].items()):
                source = info['source']
                target = release_root / category / f'{index:04d}_{source.name}'
                publish_file(source, target)
                if hash_file(target) != info['sha256']:
                    raise ValueError(f'Release read-back failed: {key}')
                manifest[category][key] = {k: v for k, v in info.items() if k != 'source'}
                manifest[category][key]['path'] = target.relative_to(release_root).as_posix()
                if category == 'figures':
                    manifest[category][key].update(current['selection']['figure_metadata'][key], version=release_id)
                    table_key = manifest[category][key]['source_table']
                    manifest[category][key]['source_table_sha256'] = current['files']['tables'][table_key]['sha256']
        selected_file = release_root / 'selection.json'
        publish_file(current['selection_path'], selected_file)
        manifest['metadata']['release_selection'] = {'path': 'selection.json', **artifact_metadata(selected_file)}
        figure_path = release_root / 'figure_manifest.json'
        atomic_write_json(figure_path, {'format_version': '1.0', 'release_id': release_id, 'figures': manifest['figures']})
        manifest['metadata']['figure_manifest'] = {'path': 'figure_manifest.json', **artifact_metadata(figure_path)}
        project = Path(__file__).parents[2]
        for source in [*sorted((project / 'src').rglob('*.py')), *sorted((project / 'configs').glob('*.yaml')),
                       project / 'PUBG_RESEARCH_SPEC.md']:
            relative = source.relative_to(project)
            target = release_root / 'reproduction' / relative
            publish_file(source, target)
            manifest['metadata']['reproduction/' + relative.as_posix()] = {
                'path': target.relative_to(release_root).as_posix(), **artifact_metadata(target)}
        manifest['manifest_hash'] = hash_dict(manifest)
        atomic_write_json(output, manifest)
        valid, errors = verify_final_manifest_integrity(output)
        if not valid:
            raise ValueError(f'Release validation failed: {errors}')
        # Canonical is a copy with paths rebased to immutable content; never mutable sources.
        canonical = {**manifest, **{c: {key: {**item, 'path': 'releases/' + release_id + '/' + item['path']}
                                  for key, item in manifest[c].items()} for c in CATEGORIES}}
        canonical_path = paths['manifests'] / 'final_results_manifest.json'
        # A long copy can overlap a user's source/config edit. Recheck before promotion.
        if inspect_finalization(paths, cfg)['signature'] != signature:
            raise ValueError('Inputs changed during release publication')
        canonical['manifest_hash'] = hash_dict({key: value for key, value in canonical.items() if key != 'manifest_hash'})
        atomic_write_json(canonical_path, canonical)
        valid, errors = verify_final_manifest_integrity(canonical_path)
        if not valid:
            raise ValueError(f'Canonical read-back failed: {errors}')
        manager.commit('finalization', signature, {'release_manifest': output, 'figure_manifest': figure_path,
                       'final_results_manifest': canonical_path}, metadata={'release_id': release_id, 'report_ready': manifest['report_ready']})
        return manifest, output
    except Exception as error:
        manager.record_failure('finalization', signature, str(error), resource_limited=isinstance(error, (MemoryError, OSError)))
        raise

RQ2_RESULT_TABLES = {'cluster_profile.csv', 'cluster_centers_standardized.csv',
                     'cluster_assignments.csv', 'clustering_robustness.csv',
                     'c4_min_games_sensitivity.csv', 'c5_outcome_comparison.csv'}


def select_rq2_results(paths, cfg):
    """Only completed, compatible RQ2 artifacts can enter the final report."""
    manager = CheckpointManager(paths['checkpoints'] / 'checkpoint_manifest.json')
    record = manager.load_manifest()['stages'].get('rq2_clustering', {})
    if not manager.is_compatible('rq2_clustering', record.get('signature')):
        raise ValueError('RQ2 is incomplete/stale or its artifacts changed. Complete notebook 07 first.')
    decisions = read_json(paths['manifests'] / 'rq2_decisions.json')
    # YAML permits integer mapping keys; JSON receipts serialize them as strings.
    # Compare canonical JSON content, without relaxing any research setting.
    if hash_dict(decisions['config']) != hash_dict(cfg['rq2']):
        raise ValueError('RQ2 config differs from the completed run. Rerun notebook 07 with the selected settings.')
    runs = decisions.get('run_ids')
    if not runs:
        raise ValueError('RQ2 run IDs missing. Complete the updated notebook 07 first.')
    artifacts = {name: (manager.manifest_path.parent / path).resolve()
                 for name, path in record['artifacts'].items()}
    if cfg['rq2']['mode_strategy'] == 'per_mode':
        for mode in runs:
            if mode not in ('Solo', 'Duo', 'Squad'):
                raise ValueError(f'Invalid RQ2 mode: {mode}')
            for filename in RQ2_RESULT_TABLES:
                if artifacts.get(f'{mode}/{filename}') != (paths['tables'] / 'rq2' / mode / filename).resolve():
                    raise ValueError(f'Missing official per-mode output: {mode}/{filename}')
    return {f'rq2/{mode}': run for mode, run in runs.items()}, artifacts


def build_final_results_manifest(
    artifacts_root: Path,
    reports_root: Path,
    official_run_ids: Dict[str, str],
    output_manifest_path: Path,
    rq2_artifacts: Optional[Dict[str, Path]] = None,
    *,
    selected_artifacts=None,
) -> Dict[str, Any]:
    """Legacy integrity inventory, NOT G5. Explicit selection replaces directory scans.

    Official publication uses inspect_finalization/publish_final_release instead.
    """
    if selected_artifacts is None:
        raise ValueError('Explicit selected_artifacts required; directory existence is not G5')
    if output_manifest_path.is_file() and read_json(output_manifest_path).get('format_version') == '4.0':
        raise ValueError('An integrity inventory cannot replace a locked research release')
    manifest = {'format_version': '3.1', 'report_ready': False, 'status': 'integrity_inventory_only',
                'finalized_at': datetime.now(timezone.utc).isoformat(), 'official_run_ids': official_run_ids,
                **{c: {} for c in CATEGORIES}}
    for category, selected in selected_artifacts.items():
        if category not in CATEGORIES:
            raise ValueError(f'Unknown artifact category: {category}')
        for key, path in selected.items():
            path = Path(path)
            manifest[category][key] = {'path': Path(os.path.relpath(path.resolve(), output_manifest_path.parent.resolve())).as_posix(),
                                      **artifact_metadata(path)}
    if not any(manifest[c] for c in CATEGORIES):
        raise ValueError('Empty manifest is not an integrity inventory or complete release')
    atomic_write_json(output_manifest_path, manifest)
    return manifest


def verify_final_manifest_integrity(manifest_path: Path) -> Tuple[bool, List[str]]:
    """Read-only: format/completeness first, then every selected checksum/schema."""
    errors = []
    try:
        manifest_path = Path(manifest_path)
        manifest = read_json(manifest_path)
        if manifest.get('format_version') not in {'3.1', '4.0'}:
            return False, ['Unsupported legacy manifest; rerun updated Notebook 11']
        if any(not isinstance(manifest.get(c), dict) for c in CATEGORIES):
            return False, ['Missing/invalid artifact categories']
        if not any(manifest[c] for c in CATEGORIES):
            return False, ['Empty manifest']
        if manifest['format_version'] == '4.0':
            if manifest.get('manifest_hash') != hash_dict({key: value for key, value in manifest.items() if key != 'manifest_hash'}):
                return False, ['Manifest content hash mismatch']
            if (not manifest.get('release_id') or not manifest.get('official_run_ids')
                    or not manifest.get('required_matrix') or not all(manifest[c] for c in CATEGORIES)):
                return False, ['Incomplete release matrix/categories/selected run coverage']
            if manifest.get('status') not in {'LOCKED', 'fixture_locked'}:
                return False, ['Release is not locked']
            if manifest.get('report_ready') != (manifest.get('status') == 'LOCKED'):
                return False, ['Release scope/report-ready mismatch']
            if any(row.get('required') is True and row.get('status') != 'completed' for row in manifest['required_matrix']):
                return False, ['Required task unresolved']
            if manifest.get('data_scope') not in {'full', 'synthetic_fixture'}:
                return False, ['Invalid release scope']
            if (manifest['data_scope'] == 'synthetic_fixture') != (manifest['status'] == 'fixture_locked'):
                return False, ['Synthetic/official scope mismatch']
        for category in CATEGORIES:
            for name, item in manifest[category].items():
                path = Path(item['path'])
                if manifest['format_version'] == '4.0':
                    if path.is_absolute() or '..' in path.parts:
                        errors.append(f'Unsafe release path: {name}')
                        continue
                path = _resolve(manifest_path.parent, path)
                try:
                    details = artifact_metadata(path)
                    if any(details.get(field) != item.get(field) for field in ('sha256', 'byte_size')):
                        errors.append(f'Checksum/size mismatch: {name}')
                    if any(field in item and details.get(field) != item[field] for field in ('columns', 'row_count', 'observed_scopes')):
                        errors.append(f'Schema/count mismatch: {name}')
                except (OSError, ValueError, csv.Error):
                    errors.append(f'Missing/corrupt file: {name}')
        if manifest['format_version'] == '4.0' and not errors:
            selected = manifest['metadata'].get('release_selection')
            if not selected or hash_dict(read_json(_resolve(manifest_path.parent, selected['path']))) != manifest.get('selection_hash'):
                errors.append('Release selection hash mismatch')
            for name, item in manifest['figures'].items():
                if any(field not in item for field in ('caption', 'source_table', 'source_experiment', 'version', 'sampling', 'report_ready')):
                    errors.append(f'Incomplete figure metadata: {name}')
                elif item['source_table'] not in manifest['tables'] or item['source_experiment'] not in manifest['official_run_ids']:
                    errors.append(f'Unselected figure source: {name}')
                elif item.get('source_table_sha256') != manifest['tables'][item['source_table']]['sha256']:
                    errors.append(f'Figure source checksum mismatch: {name}')
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as error:
        errors.append(f'Invalid/missing manifest: {error}')
    return not errors, errors


def load_locked_release(manifest_path, *, allow_fixture=False):
    """Read a selected snapshot, never consult current config/checkpoints or fit models."""
    if not isinstance(allow_fixture, bool):
        raise ValueError('allow_fixture must be an explicit boolean')
    manifest_path = Path(manifest_path).expanduser().resolve()
    manifest = read_json(manifest_path)
    if manifest.get('format_version') != '4.0':
        raise ValueError('Summary requires a complete format 4.0 release, not a legacy integrity inventory')
    fixture = manifest.get('status') == 'fixture_locked'
    if fixture and not allow_fixture:
        raise ValueError('Synthetic fixture is not an official report; opt in only for logic testing')
    for category in CATEGORIES:
        for key, item in manifest.get(category, {}).items():
            path = (manifest_path.parent / item['path']).resolve()
            if not path.is_relative_to(manifest_path.parent):
                raise ValueError(f'Release path escapes snapshot: {key}')
    valid, errors = verify_final_manifest_integrity(manifest_path)
    if not valid:
        raise ValueError(f'Release integrity/completeness failed: {errors}')
    selection = read_json(manifest_path.parent / manifest['metadata']['release_selection']['path'])
    if (selection.get('approved') is not True or not selection.get('approved_by')
            or selection.get('data_scope') != manifest['data_scope']):
        raise ValueError('Locked selection scope/approval inconsistent')
    matrix = manifest['required_matrix']
    components = [row['component'] for row in matrix]
    if len(set(components)) != len(components) or 'RQ1' not in components:
        raise ValueError('Required release coverage missing/duplicated')
    runs = set(manifest['official_run_ids'].values())
    for row in matrix:
        if row.get('required') is True and (row.get('status') != 'completed' or row.get('run_id') not in runs):
            raise ValueError(f'Required execution unresolved: {row["component"]}')
        if row.get('status') != 'completed' and not row.get('reason'):
            raise ValueError('Excluded task reason missing')
    for key in selection['provenance'].values():
        if key not in manifest['metadata']:
            raise ValueError(f'Locked provenance missing: {key}')
    def frozen_metadata(filename):
        matches = [item for item in manifest['metadata'].values() if Path(item['path']).name.endswith(filename)]
        if len(matches) != 1:
            raise ValueError(f'Locked evidence missing/ambiguous: {filename}')
        return read_json(manifest_path.parent / matches[0]['path'])
    recipe = frozen_metadata('rq3_selection_lock.json')
    for key, model in recipe['models'].items():
        rows = [row for row in matrix if row['component'] == key and row.get('required') is True]
        if len(rows) != 1 or rows[0].get('run_id') != model['run_id'] or manifest['official_run_ids'].get(key) != model['run_id']:
            raise ValueError(f'Locked model coverage missing/mismatched: {key}')
    rq2 = frozen_metadata('rq2_decisions.json')
    for mode, run_id in rq2['run_ids'].items():
        for component in ('C1_Main_KMeans', 'C2_Hierarchical_vs_KMeans', 'C3_Games_Played_Sensitivity', 'C4_Min_Games_Sensitivity', 'C5_Outcome_Comparison'):
            if not any(row['component'] == mode+'/'+component and row.get('run_id') == run_id and row.get('required') is True for row in matrix):
                raise ValueError(f'Locked C1-C5 coverage missing: {mode}/{component}')
    audit = [{'category': category, 'artifact': key, 'path': item['path'], 'sha256': item['sha256'],
              'rows': item.get('row_count'), 'integrity': 'verified', 'scope': manifest['data_scope']}
             for category in CATEGORIES for key, item in manifest[category].items()]
    return {'manifest': manifest, 'selection': selection, 'manifest_path': manifest_path,
            'root': manifest_path.parent, 'fixture': fixture, 'audit': audit}
