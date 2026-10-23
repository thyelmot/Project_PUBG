"""Source inspection and train-only label-aware plots."""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import CHUNK_SIZE, SAMPLE_MATCHES, SEED
from .io import new_directory, sample_matches, write_json
from .preprocessing import COORDS, PLACEHOLDERS


def counts(series, name):
    result = series.value_counts(dropna=False).rename_axis(name).reset_index(name='count')
    result['fraction'] = result['count'] / len(series)
    return result


def run_eda(source, output, n_matches=SAMPLE_MATCHES, chunk_size=CHUNK_SIZE, seed=SEED):
    output = new_directory(output)
    manifest = sample_matches(source, output, n_matches, chunk_size, seed)
    frame = pd.read_parquet(output / 'sampled_events.parquet')
    counts(frame.killed_by, 'killed_by').to_csv(output / 'weapon_counts.csv', index=False)
    counts(frame['map'], 'map').to_csv(output / 'map_counts.csv', index=False)
    killer = frame.killer_name.astype('string').str.strip().str.lower()
    audit = {'rows': len(frame), 'missing_killer': int((killer.isna() | killer.isin(PLACEHOLDERS)).sum()),
             'missing_coordinates': int(frame[COORDS].isna().any(axis=1).sum()),
             'zero_killer_position': int(((frame.killer_position_x == 0) & (frame.killer_position_y == 0)).sum()),
             'zero_victim_position': int(((frame.victim_position_x == 0) & (frame.victim_position_y == 0)).sum()),
             'invalid_time': int((frame.time.isna() | ~frame.time.between(0, 2700, inclusive='right')).sum()),
             'invalid_map': int((~frame['map'].astype('string').str.strip().isin(['ERANGEL', 'MIRAMAR'])).sum())}
    write_json(output / 'quality_audit.json', audit)
    pd.DataFrame([{'rule': rule, 'rows': value, 'fraction_of_input': value / len(frame)}
        for rule, value in audit.items() if rule != 'rows']).to_csv(output / 'quality_audit.csv', index=False)
    phase = np.select([frame.time < 300, frame.time <= 1200], ['early', 'mid'], default='late')
    bias = pd.DataFrame({'map': frame['map'].astype('string').str.strip().fillna('<missing>'),
        'time_phase': np.where(frame.time.between(0, 2700, inclusive='right'), phase, 'invalid'),
        'down_and_out': frame.killed_by.astype('string').str.strip().eq('Down and Out').fillna(False)})
    for keys, name in [(['map'], 'map'), (['time_phase'], 'phase'), (['map', 'time_phase'], 'map_phase')]:
        bias.groupby(keys).agg(rows=('down_and_out', 'size'), down_and_out_rows=('down_and_out', 'sum'),
            down_and_out_fraction=('down_and_out', 'mean')).to_csv(output / f'down_and_out_by_{name}.csv')
    counts(bias.time_phase, 'time_phase').to_csv(output / 'time_phase_counts.csv', index=False)
    fig, ax = plt.subplots()
    frame.time.hist(bins=50, ax=ax)
    ax.set(xlabel='Event time (seconds)', ylabel='Events')
    fig.tight_layout()
    fig.savefig(output / 'time_distribution.png')
    plt.close(fig)
    return manifest


def plot_train_distributions(train, output):
    output = Path(output)
    counts(train.weapon_group, 'weapon_group').to_csv(output / 'train_class_counts.csv', index=False)
    fig, ax = plt.subplots(figsize=(9, 5))
    train.boxplot(column='kill_distance_m', by='weapon_group', showfliers=False, ax=ax)
    ax.set(xlabel='Weapon group', ylabel='Distance (m)', title='Kill distance by weapon group — train')
    fig.suptitle('')
    fig.tight_layout()
    fig.savefig(output / 'train_distance_by_class.png')
    plt.close(fig)
