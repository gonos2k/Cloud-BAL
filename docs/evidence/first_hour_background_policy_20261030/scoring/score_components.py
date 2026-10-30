"""Pure score and remapping helpers for the paired producer first-hour experiment.

The caller must independently validate producer/build/input/runtime receipts and
pass source-bound reference arrays before using these helpers. This module has no
CLI or output-publication path and does not authorize a forecast or scoring run.
"""
from datetime import datetime, timezone

import numpy as np


def remap_one_hour(directory, inventory, mask, lat, lon, scorer):
    """Use the pinned historical operator for two checked WRF histories."""
    ev = scorer.evaluator
    snapshots, identities = {}, []
    for hour in (12, 13):
        path = directory / f'wrfout_d01_2026-08-16_{hour:02d}:00:00'
        snapshot, identity = scorer.checked_snapshot(path, datetime(2026, 8, 16, hour, tzinfo=timezone.utc), inventory)
        snapshots[hour] = snapshot
        identities.append(identity)
    if (not np.array_equal(snapshots[12]['lat'], snapshots[13]['lat'])
        or not np.array_equal(snapshots[12]['lon'], snapshots[13]['lon'])):
        raise ValueError('grid changed within run')
    ev.CASES = ('candidate',)
    ev.COMPARE_HOURS = (13,)
    reset = ev.check_resets({'candidate': snapshots})
    x0,x1=inventory['grid']['crop_x_inclusive']; y0,y1=inventory['grid']['crop_y_inclusive']
    ys,xs=slice(y0-2,y1),slice(x0-2,x1)
    mapping=ev.build_curvilinear_mapping(snapshots[12]['lat'][ys,xs],snapshots[12]['lon'][ys,xs],lat,lon,mask)
    remapped = []
    for hour in (12, 13):
        total,valid=ev.raw_total(snapshots[hour])
        remapped.append(ev.remap_field(total[ys,xs],valid[ys,xs],mapping))
    if not np.array_equal(mask & mapping['valid'] & remapped[0][1] & remapped[1][1],mask):
        raise ValueError('incomplete valid mask')
    diff=remapped[1][0]-remapped[0][0]
    if np.any(diff[mask] < -ev.NEGATIVE_TOLERANCE_MM):raise ValueError('negative hourly precipitation')
    return {'values': np.maximum(diff[mask], 0), 'history_identities': identities, 'reset': reset,
            'latitude': snapshots[12]['lat'], 'longitude': snapshots[12]['lon'],
            'mapping_residual_max_deg': mapping['residual_max_deg']}


def score_arrays(values, scorer):
    """Categorical and continuous scores plus producer/reference transitions."""
    names=('PRODUCER_H','PRODUCER_BG','FIX_H','ORIGINAL','FIX_ORIGINAL')
    if set(values) != set(names)|{'reference'}:raise ValueError('unexpected array names')
    for name, value in values.items():
        value=np.asarray(value)
        if value.shape!=(3688,) or not np.isfinite(value).all():raise ValueError(f'invalid array {name}')
    categorical=[];continuous=[];transitions=[]
    for name in names:
        error=values[name]-values['reference']
        continuous.append({'case':name,'points':len(error),'mean_forecast_mm':float(np.mean(values[name])),
            'mean_reference_mm':float(np.mean(values['reference'])),'mean_error_mm':float(np.mean(error)),
            'MAE_mm':float(np.mean(np.abs(error))),'RMSE_mm':float(np.sqrt(np.mean(error**2)))})
        categorical.extend({'case':name,'threshold_mm':t,'points':len(error),**scorer.scores(values[name],values['reference'],t)} for t in scorer.THRESHOLDS)
    for baseline in ('PRODUCER_H','FIX_H','ORIGINAL','FIX_ORIGINAL'):
        transitions.extend({'baseline':baseline,'candidate':'PRODUCER_BG','threshold_mm':t,
                            **scorer.transitions(values[baseline],values['PRODUCER_BG'],values['reference'],t)} for t in scorer.THRESHOLDS)
    return categorical, continuous, transitions
