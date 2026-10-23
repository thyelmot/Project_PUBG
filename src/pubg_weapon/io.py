"""Chunked input, reproducible match sampling and artifact metadata."""
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .config import CHUNK_SIZE, ROOT, SEED
from .config import RAW_COLUMNS
from .splits import source_partition

TEXT_COLUMNS = ('killed_by', 'killer_name', 'victim_name', 'map', 'match_id')


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def read_json(path):
    return json.loads(Path(path).read_text())


def file_sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def new_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    return path


def read_chunks(source, chunk_size=CHUNK_SIZE):
    if chunk_size < 1:
        raise ValueError('chunk_size must be positive')
    for frame in pd.read_csv(source, usecols=list(RAW_COLUMNS), chunksize=chunk_size,
                             dtype={c: 'string' for c in TEXT_COLUMNS}):
        for col in set(RAW_COLUMNS) - set(TEXT_COLUMNS):
            frame[col] = pd.to_numeric(frame[col], errors='coerce').astype('float64')
        yield frame.loc[:, list(RAW_COLUMNS)]


def sample_matches(source, output, n_matches, chunk_size=CHUNK_SIZE, seed=SEED):
    """Two full scans: choose unique matches, then retain every selected event."""
    if n_matches < 10:
        raise ValueError('At least 10 matches are required for grouped splitting')
    ids, weapon_counts, source_rows = set(), Counter(), 0
    for chunk in pd.read_csv(source, usecols=['match_id', 'killed_by'], dtype='string', chunksize=chunk_size):
        ids.update(chunk.match_id.dropna().str.strip().loc[lambda s: s.ne('')])
        weapon_counts.update(chunk.killed_by.dropna().str.strip())
        source_rows += len(chunk)
    if len(ids) < 10:
        raise ValueError('Source contains fewer than 10 valid matches')
    selected = np.random.default_rng(seed).choice(sorted(ids), min(n_matches, len(ids)), replace=False)
    selected_set = set(selected)
    output = Path(output)
    development_path = ROOT / 'configs' / 'development_matches.csv'
    development_ids = set(pd.read_csv(development_path).match_id)
    source_partition(ids, development_ids).to_csv(output / 'source_match_splits.csv', index=False)
    vocabulary = pd.DataFrame(weapon_counts.most_common(), columns=['killed_by', 'count'])
    vocabulary['fraction'] = vocabulary['count'] / vocabulary['count'].sum()
    vocabulary.to_csv(output / 'source_weapon_counts.csv', index=False)
    pd.DataFrame({'match_id': sorted(selected)}).to_csv(output / 'sampled_matches.csv', index=False)
    writer = None
    rows = 0
    try:
        for frame in read_chunks(source, chunk_size):
            frame['match_id'] = frame.match_id.str.strip()
            frame = frame.loc[frame.match_id.isin(selected_set)]
            if frame.empty:
                continue
            table = pa.Table.from_pandas(frame, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(output / 'sampled_events.parquet', table.schema)
            writer.write_table(table)
            rows += len(frame)
    finally:
        if writer is not None:
            writer.close()
    if not rows:
        raise ValueError('No events selected')
    manifest = {'source': str(Path(source).resolve()), 'source_bytes': Path(source).stat().st_size,
                'source_sha256': file_sha256(source), 'source_rows': source_rows, 'seed': seed, 'available_matches': len(ids),
                'sampled_matches': len(selected), 'sampled_rows': rows, 'columns': list(RAW_COLUMNS),
                'sample_sha256': file_sha256(output / 'sampled_events.parquet'),
                'split_seed': SEED,
                'prior_development_matches_excluded_from_test': len(ids & development_ids),
                'source_match_splits_sha256': file_sha256(output / 'source_match_splits.csv'),
                'source_weapon_counts_sha256': file_sha256(output / 'source_weapon_counts.csv')}
    write_json(output / 'source_manifest.json', manifest)
    return manifest
