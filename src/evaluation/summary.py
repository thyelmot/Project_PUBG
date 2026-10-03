"""Read-only report views of selected artifacts; no raw access, fitting or publication."""
import math
from pathlib import Path
import pandas as pd
from src.data.io import read_json


PRIVATE_FIELDS = {'player_name', 'killer_name', 'victim_name', 'player_id', 'row_id', 'match_id',
                  'team_id', 'source_row', 'examples', 'sample_records', 'token', 'cookie', 'password'}
DISPLAY_ROWS = 100


def public_frame(frame):
    """No player/row identity columns in a report, even when present in a selected table."""
    return frame.drop(columns=[c for c in frame if c.lower() in PRIVATE_FIELDS], errors='ignore')


def metadata_frame(value, prefix=''):
    """Aggregate metadata only; do not dump lists of source records or player identifiers."""
    rows = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in PRIVATE_FIELDS or any(word in key.lower() for word in ('secret', 'credential')):
                continue
            field = prefix + str(key)
            if isinstance(item, dict):
                rows.extend(metadata_frame(item, field+'.').to_dict('records'))
            elif isinstance(item, list):
                rows.append({'Thuộc tính': field, 'Giá trị': f'{len(item)} mục; không công bố record định danh'})
            else:
                rows.append({'Thuộc tính': field, 'Giá trị': 'unknown/null' if item is None else str(item)})
    return pd.DataFrame(rows, columns=['Thuộc tính', 'Giá trị'])


def release_table(release, key):
    item = release['manifest']['tables'][key]
    path = release['root']/item['path']
    # ponytail: previews cap memory, not official statistics; full artifacts remain unchanged.
    frame = pd.read_csv(path, nrows=None if item.get('row_count', 0) <= 10000 else DISPLAY_ROWS)
    if key == 'ablation_error/metrics':
        mode_item = release['manifest']['tables'].get('rq3_prediction/mode_metrics')
        units = pd.Series(dtype=object)
        if mode_item:
            saved = pd.read_csv(release['root']/mode_item['path'], usecols=['experiment_id', 'unit']).drop_duplicates()
            units = saved.loc[~saved.experiment_id.duplicated(keep=False)].set_index('experiment_id').unit
        frame['MAE/RMSE unit'] = frame.experiment_id.map(units).fillna('unknown hoặc conflicting units')
        frame['R2 unit'] = 'không đơn vị'
    return public_frame(frame)


def release_metadata(release, key):
    item = release['manifest']['metadata'].get(key)
    if item and Path(item['path']).suffix == '.json':
        return read_json(release['root']/item['path'])
    return {}


def key_findings(release):
    """Neutral statements directly from saved rows, no new metrics, causal claims or winner."""
    manifest = release['manifest']
    rows = []
    for key, item in manifest['tables'].items():
        if key not in {'rq1/summary_table', 'ablation_error/comparisons'}:
            continue
        # Read all *summary* rows in batches. Never select top findings from a capped preview.
        for chunk in pd.read_csv(release['root']/item['path'], chunksize=1000):
            for record in chunk.to_dict('records'):
                if key == 'rq1/summary_table':
                    if not record.get('is_primary_valid') or record.get('status') != 'valid':
                        continue
                    coefficient = record.get('spearman_rho')
                    if not isinstance(coefficient, (int, float)) or not math.isfinite(coefficient):
                        continue
                    text = f"{record['feature']} và {record['target']}: Spearman={coefficient:.4g}; chỉ liên hệ, không nhân quả."
                    rows.append({'Phát biểu từ số đo': text, 'Mode': record['mode'], 'N dòng': record['n_observations'],
                        'N trận': None, 'Đơn vị': 'hệ số [-1,1]', 'Scope': record['analysis_scope'],
                        'Uncertainty': 'Chưa có CI association', 'Run': manifest['official_run_ids']['rq1'],
                        'Nguồn bảng': key, 'SHA256': item['sha256'], 'Giới hạn': record.get('notes')})
                elif record.get('aggregation') == 'micro' and record.get('metric') == 'mae':
                    delta, low, high = (record.get(field) for field in ('delta', 'ci_lower', 'ci_upper'))
                    if not isinstance(delta, (int, float)) or not math.isfinite(delta):
                        continue
                    finite_ci = all(isinstance(x, (int, float)) and math.isfinite(x) for x in (low, high))
                    ci = f'CI95% [{low:.4g}, {high:.4g}]' if finite_ci else 'CI chưa có; không khẳng định chiều cải thiện'
                    text = f"{record['candidate']} so với {record['reference']}: delta MAE={delta:.4g} (candidate - reference)."
                    rows.append({'Phát biểu từ số đo': text, 'Mode': 'cohort của cặp đã khóa', 'N dòng': record['n_rows'],
                        'N trận': record['n_matches'], 'Đơn vị': record['unit'], 'Scope': record['scope'],
                        'Uncertainty': ci, 'Run': record['candidate_run_id'], 'Nguồn bảng': key, 'SHA256': item['sha256'],
                        'Giới hạn': 'Hồi cứu; CI chứa 0 không chứng minh cải thiện; player lặp có thể phụ thuộc xuyên trận.'})
    return pd.DataFrame(rows)


def render_summary_section(release, number):
    """One independent, inspectable view for each of the 12 required research sections."""
    from IPython.display import display, Markdown, Image
    manifest = release['manifest']
    selected = manifest['tables']
    matrix = pd.DataFrame(manifest['required_matrix'])
    tables, keys = [], []
    provenance = release['selection']['provenance']
    if number == 1:
        tables.append(('Phiên bản và phạm vi', pd.DataFrame([{'Release': manifest['release_id'],
            'Scope': manifest['data_scope'], 'Trạng thái': manifest['status'], 'Report ready': manifest['report_ready'],
            'Manifest': str(release['manifest_path']), 'Tính toàn vẹn': 'Đã xác minh từng file',
            'Độ đầy đủ': 'Required tasks completed hoặc conditional exception có lý do'}])))
        for name in ('source_inventory', 'cohort'):
            tables.append((name, metadata_frame(release_metadata(release, provenance.get(name)))))
        cohort = release_metadata(release, provenance.get('cohort'))
        tables.append(('Counts không suy diễn', pd.DataFrame([{'Thuộc tính': name,
            'Giá trị': cohort.get(name, 'unknown; xem ledger theo task nếu có'), 'Nguồn': provenance.get('cohort')}
            for name in ('rows', 'matches', 'players', 'mode', 'date_range')])))
        keys = [k for k in selected if k.endswith('/cohorts')]
    elif number == 2:
        keys = [k for k, item in selected.items() if any(name in Path(item['path']).name for name in
            ('data_quality', 'removal_ledger', 'join_audit', 'roster', 'missing', 'coverage'))]
        for key in manifest['metadata']:
            if any(word in key.lower() for word in ('chronology', 'leakage_checks', 'data_quality', 'join_audit')):
                tables.append((key, metadata_frame(release_metadata(release, key))))
        tables.append(('DQ không suy ra từ checksum', pd.DataFrame([
            {'Nhóm kiểm tra': name, 'Trạng thái': 'selected evidence' if any(name in k.lower() for k in keys) else 'not_in_release',
             'Giới hạn': 'Thiếu evidence thì không tính lại từ raw hoặc khẳng định DQ hoàn tất.'}
            for name in ('missing', 'removal', 'join', 'roster')])))
    elif number == 3:
        keys = [k for k in selected if k == 'rq1/summary_table']
    elif number == 4:
        keys = [k for k in selected if k.startswith('rq2_clustering/') and not k.endswith('cluster_assignments.csv')]
        tables.append(('C1-C5 từng mode', matrix.loc[matrix.component.str.contains('/C', regex=False)]))
        tables.append(('Thiết kế RQ2', metadata_frame(release_metadata(release, 'rq2_clustering/decisions'))))
    elif number in (5, 6):
        prefix = ('s1_', 's2_') if number == 5 else ('p1_', 'p2_', 'p3_')
        for key in ('ablation_error/metrics', 'ablation_error/features', 'rq3_prediction/mode_metrics'):
            if key in selected:
                frame = release_table(release, key)
                frame = frame.loc[frame.experiment_id.str.startswith(prefix)]
                tables.append((key, frame))
        task_prefix = ('s1', 's2') if number == 5 else ('p1', 'p2', 'p3')
        tables.append(('Trạng thái task và ngoại lệ', matrix.loc[matrix.component.str.startswith(task_prefix)]))
    elif number == 7:
        for key in ('ablation_error/comparisons', 'ablation_error/features'):
            if key in selected:
                frame = release_table(release, key)
                column = 'candidate' if key.endswith('comparisons') else 'experiment_id'
                tables.append((key, frame.loc[frame[column].str.startswith(('t0_', 't1_'))]))
    elif number == 8:
        keys = [k for k in ('ablation_error/ablation', 'ablation_error/importance') if k in selected]
    elif number == 9:
        keys = [k for k in ('ablation_error/errors', 'ablation_error/residuals', 'ablation_error/error_analysis') if k in selected]
    elif number == 10:
        keys = [k for k in ('ablation_error/comparisons',) if k in selected]
        for key in manifest['metadata']:
            if key.startswith('ablation_error/bootstrap_'):
                tables.append((key, metadata_frame(release_metadata(release, key))))
    elif number == 11:
        tables.append(('Phát biểu có truy nguồn; không chọn winner', key_findings(release)))
    elif number == 12:
        tables.append(('Nhiệm vụ không hoàn thành và lý do', matrix.loc[matrix.status != 'completed']))
        tables.append(('Hình không dùng cho báo cáo chính thức', pd.DataFrame([
            {'ID': k, 'Scope': v['scope'], 'Report ready': v['report_ready'], 'Caption': v['caption']}
            for k, v in manifest['figures'].items() if not v['report_ready']])))
        tables.append(('Test exposure và phiên bản', pd.DataFrame([{'Prior test exposure': manifest.get('prior_test_exposure'),
            'Release': manifest['release_id'], 'Scope': manifest['data_scope'], 'Raw cần cho tái huấn luyện': True}])))
    else:
        raise ValueError('Summary section must be 1..12')
    for key in keys:
        tables.append((key, release_table(release, key)))
    if not tables:
        tables.append(('Thiếu artifact', pd.DataFrame([{'Trạng thái': 'pending', 'Lý do': 'Không có bảng selected cho phần này; không suy diễn số.'}])))
    for key, frame in tables:
        display(Markdown(f'Bảng 12-{number:02d}. {key}; release `{manifest["release_id"]}`, scope `{manifest["data_scope"]}`.'))
        display(public_frame(frame).head(DISPLAY_ROWS))
        if key in selected:
            display(Markdown(f'Nguồn: `{selected[key]["path"]}`; SHA-256 `{selected[key]["sha256"]}`. '
                f'N lưu = {selected[key].get("row_count", "unknown")}; tối đa {DISPLAY_ROWS} dòng xem, không cắt artifact hoặc tính metric trên preview.'))
        elif key in manifest['metadata']:
            info = manifest['metadata'][key]
            display(Markdown(f'Nguồn metadata: `{info["path"]}`; SHA-256 `{info["sha256"]}`. Null/unknown không được suy ra 0.'))
        elif len(frame) > DISPLAY_ROWS:
            display(Markdown(f'N = {len(frame)}; chỉ xem {DISPLAY_ROWS} dòng đầu, không chọn phát biểu từ preview.'))
    shown = []
    for key, item in manifest['figures'].items():
        source = item['source_table']
        section = (3 if source.startswith('rq1/') else 4 if source.startswith('rq2_') else
                   10 if source.endswith('/comparisons') else 8 if source.endswith('/ablation') else
                   9 if 'error' in source or 'residual' in source else 6)
        if section == number and (item['report_ready'] or release['fixture']):
            display(Markdown(f'Hình `{key}`: {item["caption"]}\n\nNguồn `{source}`, SHA `{item["source_table_sha256"]}`; '
                f'scope `{item["scope"]}`, sampling `{item["sampling"]}`, version `{item["version"]}`. '
                + ('Chỉ preview fixture, không xuất như hình official.' if release['fixture'] else 'Chỉ hình report_ready đã khóa.')))
            display(Image(filename=str(release['root']/item['path'])))
            shown.append(key)
    return {'section': number, 'tables': [key for key, _ in tables], 'figures': shown}
