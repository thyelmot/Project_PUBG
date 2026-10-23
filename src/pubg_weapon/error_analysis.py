"""Shared validation/test error tables; raw causes remain audit metadata only."""
import numpy as np
import pandas as pd

from .config import TARGET
from .training import metrics


def other_component(cause):
    if cause == 'Punch':
        return 'Punch'
    if cause in ('Pan', 'Sickle', 'Crowbar', 'Machete'):
        return 'melee'
    if cause in ('P92', 'P1911', 'P18C', 'R1895', 'R45'):
        return 'pistols'
    if cause == 'Grenade' or 'Molotov' in cause or cause == 'death.Buff_FireDOT_C':
        return 'grenades_fire'
    if cause == 'Crossbow':
        return 'Crossbow'
    if cause in ('Hit by Car', 'Uaz', 'Dacia', 'Motorbike (SideCar)', 'Motorbike',
                 'Pickup Truck', 'Buggy', 'Boat', 'Van', 'Aquarail', 'death.PG117_A_01_C'):
        return 'vehicles'
    return 'merged_rare_weapon'


def write_error_tables(frame, prediction, classes, output):
    errors = pd.DataFrame({'actual': frame[TARGET].to_numpy(), 'predicted': prediction,
                           'distance_m': frame.kill_distance_m.to_numpy()})
    wrong = errors.loc[errors.actual != errors.predicted]
    wrong.groupby(['actual', 'predicted']).agg(count=('distance_m', 'size'),
        median_distance_m=('distance_m', 'median')).sort_values('count', ascending=False).to_csv(output / 'confused_pairs.csv')
    errors['distance_bin'] = pd.cut(errors.distance_m, [-np.inf, 50, 150, 300, np.inf],
        labels=['0-50', '>50-150', '>150-300', '>300'])
    rows = []
    for name, part in errors.groupby('distance_bin', observed=False):
        scores = metrics(part.actual, part.predicted, classes) if len(part) else {
            'accuracy': np.nan, 'macro_f1': np.nan, 'weighted_f1': np.nan}
        rows.append({'distance_bin': name, 'rows': len(part), **scores})
    pd.DataFrame(rows).to_csv(output / 'distance_metrics.csv', index=False)
    other = errors.loc[errors.actual == 'Other'].copy()
    other['cause'] = frame.cause_for_audit.to_numpy()[errors.actual == 'Other']
    other['component'] = other.cause.map(other_component)
    other['correct'] = other.predicted == 'Other'
    for key in ('component', 'cause'):
        other.groupby(key).distance_m.describe().to_csv(output / f'other_{key}_distances.csv')
    summary = other.groupby('component').agg(rows=('correct', 'size'), accuracy=('correct', 'mean'))
    summary.to_csv(output / 'other_components.csv')
    routes = other.loc[~other.correct].groupby(['component', 'predicted']).size().rename('count').reset_index()
    routes['fraction_of_component'] = routes['count'] / routes.component.map(summary.rows)
    routes['fraction_of_component_errors'] = routes['count'] / routes.groupby('component')['count'].transform('sum')
    routes.to_csv(output / 'other_confused_destinations.csv', index=False)
