#!/usr/bin/env python3
"""Descriptive recount of retained selected-cell arrays; no policy changes."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def quantiles(values):
    q = np.quantile(values, [0, .01, .1, .25, .5, .75, .9, .99, 1])
    return dict(zip(['min', 'p01', 'p10', 'p25', 'median', 'p75', 'p90', 'p99', 'max'], map(float, q)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--diagnostic', required=True, type=Path)
    ap.add_argument('--policy', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    policy = json.loads(args.policy.read_text())
    lower, upper, cap = policy['lower'][1], policy['upper'][1], policy['number_cap'][1]
    with np.load(args.diagnostic, allow_pickle=False) as z:
        shape = z['selected_fixed_mask'].shape
        flat = z['selected_flat_indices']
        assert np.array_equal(flat, np.flatnonzero(z['selected_fixed_mask']))
        aqi, aqs, bqi, bqs, bni = (z[n].astype(np.float64) for n in ('analysis_qi_selected', 'analysis_qs_selected', 'background_qi_selected', 'background_qs_selected', 'background_ni_selected'))
        ad, bd = (z[n].astype(np.float32) for n in ('analysis_density_selected', 'background_density_selected'))
        status = z['status'][z['selected_fixed_mask']]
    target = aqi + aqs
    total = bqi + bqs
    present = (bqi > 0) & (bni > 0)
    mean = np.zeros_like(total)
    fraction = np.zeros_like(total)
    alpha = np.zeros_like(total)
    np.divide(bqi, bni, out=mean, where=present)
    np.divide(bqi, total, out=fraction, where=total > 0)
    np.divide(target, total, out=alpha, where=total > 0)
    # Match audit.py: float64 fraction*target -> REAL32 qi -> float64 qi/mean
    # -> REAL32 NI -> REAL32 NI*density. Density inputs are file proxies.
    qi32 = (fraction * target).astype(np.float32)
    ni = np.zeros_like(total)
    np.divide(qi32.astype(np.float64), mean, out=ni, where=present)
    ni32 = ni.astype(np.float32)
    target_volume = np.multiply(ni32, ad, dtype=np.float32)
    substitution_volume = np.multiply(ni32, bd, dtype=np.float32)
    cap_group = target_volume.astype(np.float64) > cap
    mismatch = (bqi == 0) & (bni > 0)
    badmean = present & ((mean < lower) | (mean > upper))
    feasible_group = cap_group & ~badmean
    # Continuous REAL64 bound on candidate mean m for fixed REAL32 qi and
    # analysis density: max(lower, qi*density/cap) <= m <= upper.
    # This does not replay discrete REAL32 rounding or change policy.
    needed_mean = qi32.astype(np.float64) * ad.astype(np.float64) / cap
    empty = feasible_group & (np.maximum(lower, needed_mean) > upper)
    nonempty = feasible_group & ~empty
    ratio = ad.astype(np.float64) / bd.astype(np.float64)
    assert np.all(total[cap_group] > 0) and np.all(present[cap_group])
    assert np.all(status[cap_group] == -10)
    stats = {
        'scope': 'Descriptive fixed-mask analysis; input density is file proxy. Alpha and density substitution are algebraic diagnostics, not an applied initialization. Continuous REAL64 feasibility is not native replay.',
        'inputs': {str(args.diagnostic): sha(args.diagnostic), str(args.policy): sha(args.policy)},
        'source_script_sha256': sha(Path(__file__)),
        'selected': int(len(flat)),
        'qi_zero_ni_positive': {'count': int(mismatch.sum()), 'qs_zero': int((mismatch & (bqs == 0)).sum()), 'qs_positive': int((mismatch & (bqs > 0)).sum()), 'qs_negative': int((mismatch & (bqs < 0)).sum())},
        'cap_flag': {'count': int(cap_group.sum()), 'alpha_target_over_background_total': quantiles(alpha[cap_group]), 'analysis_over_background_density': quantiles(ratio[cap_group]), 'substitute_background_density_still_above': int((cap_group & (substitution_volume > cap)).sum()), 'substitute_background_density_at_or_below': int((cap_group & (substitution_volume <= cap)).sum()), 'already_bad_background_mean': int((cap_group & badmean).sum())},
        'continuous_real64_feasibility': {'group': int(feasible_group.sum()), 'empty': int(empty.sum()), 'nonempty': int(nonempty.sum()), 'formula': 'max(policy_lower, REAL64(stored_qi_REAL32)*REAL64(analysis_density_REAL32)/cap) <= policy_upper', 'empty_required_mean_over_upper_minus_one': quantiles(needed_mean[empty] / upper - 1), 'empty_required_mean_kg_per_particle': quantiles(needed_mean[empty])},
    }
    # Extreme and central examples are deterministic and not selected for acceptance.
    ids = np.flatnonzero(cap_group)
    rows = []
    for label, n in [('min_alpha',ids[np.argmin(alpha[ids])]), ('median_alpha',ids[np.argsort(alpha[ids])[len(ids)//2]]), ('max_alpha',ids[np.argmax(alpha[ids])])]:
        rows.append((label,n))
    for n in np.flatnonzero(empty):
        rows.append(('continuous_empty',n))
    path = args.out / 'representative_cells.csv'
    with path.open('w', newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['selection','i_1based','j_1based','k_1based','analysis_qi','analysis_qs','background_qi','background_qs','background_ni','analysis_density','background_density','alpha','background_mean','stored_qi','stored_ni','target_volume','substituted_volume','required_mean','mean_upper'])
        for label,n in rows:
            k,j,i=np.unravel_index(flat[n],shape)
            writer.writerow([label,i+1,j+1,k+1,aqi[n],aqs[n],bqi[n],bqs[n],bni[n],ad[n],bd[n],alpha[n],mean[n],qi32[n],ni32[n],target_volume[n],substitution_volume[n],needed_mean[n],upper])
    stats['representative_cells_sha256'] = sha(path)
    diagnostics = args.out / 'cap_diagnostics.npz'
    np.savez_compressed(diagnostics,
        full_flat_indices=flat[cap_group],
        alpha=alpha[cap_group],
        analysis_over_background_density=ratio[cap_group],
        background_mean=mean[cap_group],
        qi32=qi32[cap_group],
        ni32=ni32[cap_group],
        target_volume=target_volume[cap_group],
        background_density_substituted_volume=substitution_volume[cap_group],
        bad_background_mean=badmean[cap_group],
        continuous_empty=empty[cap_group])
    stats['cap_diagnostics'] = {
        'sha256': sha(diagnostics),
        'count': int(cap_group.sum()),
        'scope': 'Fixed selected cells with REAL32 proposed NI times REAL32 analysis density proxy above frozen cap. Flat indices are zero-based C order in (k,j,i) full domain. Flags are descriptive; continuous_empty excludes bad background mean and is REAL64 feasibility, not native replay.'}
    (args.out / 'recount.json').write_text(json.dumps(stats, indent=2, allow_nan=False)+'\n')
    print(json.dumps(stats, indent=2, allow_nan=False))

if __name__ == '__main__':
    main()
