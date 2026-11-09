#!/usr/bin/env python3
"""Recount signed native-column gaps and limited-interface events from sealed CSVs."""
import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools'))
import cp02_protected_process_capture as capture

HERE = Path(__file__).resolve().parent


def update(stat, field, value, weight):
    stat[field + '_net'] += weight * value
    stat[field + '_positive'] += weight * max(value, 0)
    stat[field + '_negative'] += weight * min(value, 0)
    stat[field + '_absolute'] += weight * abs(value)
    stat[field + '_max_abs_unweighted'] = max(stat[field + '_max_abs_unweighted'], abs(value))


def memberships(cohort):
    roles = defaultdict(set)
    points = defaultdict(list)
    for ix, point in enumerate(cohort.point_ids):
        point_roles = set(cohort.point_roles.get(point, ()))
        for ci, weight in zip(cohort.point_cells[ix], cohort.point_weights[ix]):
            cell = cohort.cells[int(ci)]
            roles[cell].update(point_roles)
            points[cell].append((point, float(weight), point_roles))
    return roles, points


def groups(cell, step, roles, points):
    native = {'all_unique_columns'} | roles[cell]
    result = [(x, 1.0) for x in native]
    weighted = []
    for point, weight, point_roles in points[cell]:
        weighted.extend((label, weight) for label in
                        ({'point/' + point} | {'role_point_sum/' + role for role in point_roles}))
    result += weighted
    if step >= 721:
        result += [('h5/' + name, weight) for name, weight in result]
    if cell in {(140, 79), (141, 79), (140, 80), (141, 80)} and 330 <= step <= 360:
        result.append(('P01_330_360_native', 1.0))
        result.append(('P01_330_360_weighted', next(weight for point, weight, _ in points[cell] if point == 'RN1_10942')))
        if step >= 331:
            result.extend((('P01_331_360_native', 1.0), ('P01_331_360_weighted', next(weight for point, weight, _ in points[cell] if point == 'RN1_10942'))))
    return result


def analyze(arm, roles, points):
    data = defaultdict(lambda: defaultdict(float))
    for kind in ('substeps', 'events'):
        with gzip.open(HERE / 'full' / arm / f'{arm}_{kind}.csv.gz', 'rt', newline='') as stream:
            for row in csv.DictReader(stream):
                cell = (int(row['i']), int(row['j']))
                step = int(row['step'])
                for group, weight in groups(cell, step, roles, points):
                    stat = data[(group, row['species'])]
                    if kind == 'events':
                        stat['limited_interface_count_weighted'] += weight
                        update(stat, 'limited_interface_gap', float(row['gap']), weight)
                    else:
                        stat['column_substeps_weighted'] += weight
                        gap = float(row['transfer_gap'])
                        rounding = float(row['rounding_residual'])
                        stored = float(row['column_change'])
                        bottom = rounding - stored - gap
                        nominal = float(row['nominal_ground_flux'])
                        ground = float(row['ground_fall_increment'])
                        update(stat, 'column_substep_gap', gap, weight)
                        update(stat, 'storage_rounding', rounding, weight)
                        update(stat, 'nominal_minus_capped_bottom', nominal - bottom, weight)
                        update(stat, 'fall_increment_minus_nominal', ground - nominal, weight)
    for stat in data.values():
        stat['nonlimited_interface_gap_net'] = stat['column_substep_gap_net'] - stat['limited_interface_gap_net']
    return data


def main():
    _, cohort, _ = capture.load_contract()
    roles, points = memberships(cohort)
    output = HERE / 'signed_gaps'
    output.mkdir(exist_ok=False)
    for arm in ('OLD', 'FIX'):
        data = analyze(arm, roles, points)
        fields = sorted({key for stat in data.values() for key in stat})
        with (output / f'{arm}_signed_gaps.csv').open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(('group', 'species', *fields))
            for (group, species), stat in sorted(data.items()):
                writer.writerow((group, species, *(stat.get(field, 0) for field in fields)))
    (output / 'receipt.json').write_text(json.dumps({'status': 'PASS', 'source_full_receipt_sha256': capture.sha256(HERE / 'full/receipt.json'), 'helper_sha256': capture.sha256(Path(__file__)), 'limits': 'Positive and negative column-substep sums can hide cancellation across interfaces. Positive/negative limited-interface sums cover only raw>upper-POST events. The remaining signed gap is not assumed to be rounding: upper POST can include inflow and a capped upper outflow can produce a negative gap. Storage residual absolute sum/max are observed float32-scale residuals, not interface-rounding bounds. Native role groups deduplicate columns; weighted role-point sums may overlap across points/roles.'}, indent=2) + '\n')

if __name__ == '__main__':
    main()
