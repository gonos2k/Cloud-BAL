#!/usr/bin/env python3
"""Reproduce P01 hour-two return and surface timing from portable native captures."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[1]
COMPACT = ROOT / 'docs/evidence/cp02_protected_process_20261106/native/compact'
BUNDLE = ROOT / 'docs/evidence/cp02_sedimentation_conservation_20261109'
FONT = Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')
FONT_SHA = '48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733'
POINT = 'RN1_10942'
LEVELS = (8, 12, 16)
COORDS = ('native_column_ids', 'native_i_1based', 'native_j_1based', 'point_ids',
          'point_native_corner_indices', 'point_corner_weights')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path, expected_steps, expected_units):
    with np.load(path, allow_pickle=False) as source:
        data = {key: source[key].copy() for key in (*COORDS, 'actual_timestep', 'native_values', 'point_values', 'units')}
    if not np.array_equal(data['actual_timestep'], expected_steps) or str(data['units']) != expected_units:
        raise ValueError(f'invalid steps or units: {path}')
    ids = data['point_ids']
    matches = np.flatnonzero(ids == POINT)
    if len(matches) != 1:
        raise ValueError('point ID must occur exactly once')
    i = int(matches[0]); indices = data['point_native_corner_indices'][i]; weights = data['point_corner_weights'][i]
    native = data['native_values']; points = data['point_values']
    if (native.ndim != 3 or points.shape != (*native.shape[:2], len(ids)) or
            np.any(indices < 0) or np.any(indices >= native.shape[2]) or
            len(set(indices.tolist())) != 4 or np.any(weights <= 0) or
            not np.isclose(weights.sum(), 1, rtol=0, atol=1e-12) or
            not np.isfinite(native).all() or not np.isfinite(points).all()):
        raise ValueError('invalid native, point or corner values')
    corners = native[:, :, indices].astype(np.float64)
    weighted = np.sum(corners * weights, axis=-1)
    if not np.allclose(weighted, points[:, :, i], rtol=1e-13, atol=1e-18):
        raise ValueError('point values disagree with native weighted corners')
    return data, corners, weighted, i


def require_matching(a, b):
    for key in COORDS:
        if not np.array_equal(a[key], b[key]):
            raise ValueError(f'coordinate mismatch: {key}')


def bins(steps, qr, cumulative, previous):
    """Mean returns over 30 calls and surface difference from preceding boundary."""
    if not np.array_equal(steps, np.arange(181, 361)) or qr.shape != (180,) or cumulative.shape != (180,):
        raise ValueError('requires contiguous 181–360 samples')
    if not np.isfinite(qr).all() or not np.isfinite(cumulative).all() or not np.isfinite(previous):
        raise ValueError('nonfinite inputs')
    result = []
    for start in range(0, 180, 30):
        end = start + 30
        baseline = previous if start == 0 else cumulative[start - 1]
        result.append((int(steps[start]), int(steps[end - 1]), float(qr[start:end].mean()),
                       float(cumulative[end - 1] - baseline)))
    return result


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def run(compact, bundle):
    if sha(FONT) != FONT_SHA:
        raise ValueError('pinned Nanum Gothic font differs')
    font_manager.fontManager.addfont(str(FONT))
    plt.rcParams.update({'font.family': font_manager.FontProperties(fname=str(FONT)).get_name(),
                         'axes.unicode_minus': False, 'savefig.dpi': 170})
    science = bundle / 'science'; figures = bundle / 'figures'
    science.mkdir(parents=True, exist_ok=True); figures.mkdir(parents=True, exist_ok=True)
    arrays = {}; paths = []; ref = None
    for arm in ('OLD', 'FIX'):
        data = {}
        for channel, hour in (('state_return_QR', 2), ('surface_rain_cumulative', 1), ('surface_rain_cumulative', 2)):
            path = compact / arm / channel / f'lead_{hour:02d}' / f'{channel}.npz'; paths.append(path)
            record, corners, weighted, point_index = load(path, np.arange((hour-1)*180+1, hour*180+1),
                                                         'kg kg-1' if channel == 'state_return_QR' else 'mm')
            if ref is None: ref = record
            else: require_matching(ref, record)
            data[channel, hour] = (corners, weighted)
        arrays[arm] = data
    point_index = int(np.flatnonzero(ref['point_ids'] == POINT)[0])
    indices = ref['point_native_corner_indices'][point_index]
    weights = ref['point_corner_weights'][point_index]
    rows = []; surface_rows = []; summaries = []
    for arm in ('OLD', 'FIX'):
        corners, values = arrays[arm]['state_return_QR', 2]
        surf_corners, surface = arrays[arm]['surface_rain_cumulative', 2]
        prev_corners, prev = arrays[arm]['surface_rain_cumulative', 1]
        for t, step in enumerate(range(181, 361)):
            for k in LEVELS:
                row = {'arm': arm, 'step': step, 'minute_in_hour': (step-180)/3, 'native_k_1based': k,
                       'point_qr_mg_kg': values[t, k-1]*1e6}
                row.update({f'corner{c+1}_qr_mg_kg': corners[t, k-1, c]*1e6 for c in range(4)})
                rows.append(row)
        for t, step in enumerate(range(181, 361)):
            prior = prev[-1, 0] if t == 0 else surface[t-1, 0]
            native_prior = prev_corners[-1, 0] if t == 0 else surf_corners[t-1, 0]
            row = {'arm': arm, 'step': step, 'baseline_step': step-1,
                   'point_rainnc_cumulative_mm': surface[t, 0],
                   'point_increment_mm': surface[t, 0] - prior}
            row.update({f'corner{c+1}_increment_mm': surf_corners[t, 0, c]-native_prior[c] for c in range(4)})
            surface_rows.append(row)
        data_bins = bins(np.arange(181,361), values[:, 11]*1e6, surface[:, 0], prev[-1, 0])
        for idx, (first,last,mean,increment) in enumerate(data_bins):
            summaries.append({'arm': arm, 'minute_start': idx*10, 'minute_end': (idx+1)*10,
                              'first_step': first, 'last_step': last, 'baseline_step': first-1,
                              'n_calls': last-first+1, 'mean_return_qr_k12_mg_kg': mean,
                              'rainnc_increment_mm': increment})
    write_csv(science / 'p01_return_corners.csv', rows)
    write_csv(science / 'p01_10min_bins.csv', summaries)
    write_csv(science / 'p01_surface_calls.csv', surface_rows)
    fig, axes = plt.subplots(4, 1, figsize=(11, 11), sharex=True, gridspec_kw={'height_ratios':[1,1,1,.8]})
    x = np.arange(1,181)/3
    colors = {'OLD':'#2166ac', 'FIX':'#d14932'}
    for ax, k in zip(axes, LEVELS):
        for arm in ('OLD','FIX'):
            corners, values = arrays[arm]['state_return_QR', 2]
            for c in range(4): ax.plot(x, corners[:, k-1, c]*1e6, color=colors[arm], alpha=.18, lw=.7)
            ax.plot(x, values[:, k-1]*1e6, color=colors[arm], lw=2, label=arm)
        ax.axvspan(50,60,color='#f5d69b',alpha=.35); ax.set_ylabel(f'k={k}\nQR (mg/kg)'); ax.grid(alpha=.2)
    for arm in ('OLD','FIX'):
        subset = [r for r in summaries if r['arm'] == arm]
        offset = -1.6 if arm == 'OLD' else 1.6
        axes[-1].bar(np.arange(5,60,10)+offset, [r['rainnc_increment_mm'] for r in subset], width=3.1, color=colors[arm], label=arm)
    axes[-1].axvspan(50,60,color='#f5d69b',alpha=.35); axes[-1].set_ylabel('RAINNC\n10-min Δ (mm)'); axes[-1].set_xlabel('Minutes within forecast hour 2 ((itimestep - 180) / 3)'); axes[-1].grid(axis='y',alpha=.2)
    axes[0].legend(ncol=2,frameon=False); fig.suptitle('P01 RN1_10942: native return states and surface timing', fontsize=14)
    fig.text(.5,.015,'Solid: weighted point; faint: four native corners. Shaded: final 10 minutes. Model index k, not physical height.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.035,1,.97)); fig.savefig(figures/'p01_return_and_surface.png'); plt.close(fig)
    receipt = {'point_id': POINT, 'steps': [181,360], 'time_definition':'hour 2 call n occupies ((n-181)/3, (n-180)/3] minutes; bins contain 30 returns',
               'bin_surface_definition':'cumulative at last step minus cumulative at immediately preceding step, including step 180 baseline',
               'native_corners':[{'id':str(ref['native_column_ids'][j]),'i':int(ref['native_i_1based'][j]),'j':int(ref['native_j_1based'][j]),'weight':float(w)} for j,w in zip(indices,weights)],
               'sources':[{ 'path':str(p.relative_to(ROOT)), 'sha256':sha(p)} for p in paths],
               'font_sha256':sha(FONT), 'renderer_sha256':sha(Path(__file__)), 'numpy':np.__version__, 'matplotlib':matplotlib.__version__,
               'outputs':{str(p.relative_to(bundle)):sha(p) for p in (science/'p01_return_corners.csv',science/'p01_10min_bins.csv',science/'p01_surface_calls.csv',figures/'p01_return_and_surface.png')},
               'limitations':'Selected point and original corners only; RAINNC excludes RAINC. Not a vertical mass budget or causal attribution.'}
    (science/'p01_timing_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact', type=Path, default=COMPACT); parser.add_argument('--bundle', type=Path, default=BUNDLE)
    args = parser.parse_args(); run(args.compact, args.bundle)
