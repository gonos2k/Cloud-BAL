#!/usr/bin/env python3
"""Audit source-carrier sedimentation changes against executed surface fall."""
import argparse
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
NATIVE = HERE.parent / 'native'
sys.path.insert(0, str(NATIVE / 'runs'))
from read_frames import frames

ARMS = ('FIX', 'CONSERVATIVE', 'ICE_FIXED')
SPECIES = ('rain', 'snow', 'graupel', 'ice')
SPAN_FIELDS = ('warm10_to_core6_QC', 'warm10_to_core6_QR', 'warm10_to_core6_QS', 'warm10_to_core6_QG',
               'ice21_to_core6_QV', 'ice21_to_core6_TK', 'ice21_to_core6_QI',
               'core8_to_cond11_QV', 'core8_to_cond11_TK', 'core8_to_cond11_QC', 'core8_to_cond11_QI')


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def phase_counts(arm):
    schema = json.loads((NATIVE / 'schema/schema.json').read_text())
    counts = {int(p): len(v['fields']) for p, v in schema['phases'].items()}
    override = schema['arm_overrides']['FIX' if arm == 'FIX' else 'CONSERVATIVE and ICE_FIXED']
    for phase in override['absent_phases']:
        counts.pop(phase)
    if arm != 'FIX':
        counts[10] = len(override['phase_10_fields'])
    return counts


def audit_frame(arm, header, records):
    rank, call, step, j, its, ite, kts, kte = header
    if (kts, kte) != (1, 39):
        raise ValueError('expected 39 levels')
    grouped = {}
    for phase, i, k, loop, loops, sub, mstep, values in records:
        if phase not in (9, 10, 13, 14, 20, 21):
            continue
        if not (its <= i <= ite and kts <= k <= kte and 1 <= loop <= loops):
            raise ValueError('invalid record coordinates')
        group = grouped.setdefault(i, {})
        key = (phase, loop, loops, k, sub, mstep)
        if key in group:
            raise ValueError('duplicate process key')
        group[key] = values.astype(np.float64)
    out = []
    for i, group in sorted(grouped.items()):
        loop_counts = {key[2] for key in group}
        if len(loop_counts) != 1:
            raise ValueError('inconsistent loop count')
        loops = loop_counts.pop()
        for species in range(4):
            pre_phase, post_phase = (9, 10) if species < 3 else (20, 21)
            q_index = 5 + species if species < 3 else 3
            rho_index, dz_index = (10, 11) if species < 3 else (5, 6)
            pre_keys = {key[1:] for key in group if key[0] == pre_phase}
            post_keys = {key[1:] for key in group if key[0] == post_phase}
            complete = pre_keys == post_keys and bool(pre_keys)
            total = 0.0
            for loop in range(1, loops + 1):
                subkeys = {key for key in pre_keys if key[0] == loop}
                msteps = {key[4] for key in subkeys}
                if len(msteps) != 1:
                    complete = False
                    continue
                mstep = next(iter(msteps))
                expected = {(loop, loops, k, sub, mstep) for sub in range(1, mstep + 1) for k in range(kts, kte + 1)}
                if subkeys != expected:
                    complete = False
                for key in sorted(subkeys & post_keys):
                    pre, post = group[(pre_phase, *key)], group[(post_phase, *key)]
                    if pre[rho_index] != post[rho_index] or pre[dz_index] != post[dz_index]:
                        raise ValueError('carrier changed within substep')
                    if pre[rho_index] <= 0 or pre[dz_index] <= 0:
                        raise ValueError('nonpositive source carrier')
                    total += pre[rho_index] * pre[dz_index] * (post[q_index] - pre[q_index])
            # Legacy top-down incoming cap reads the already-updated upper level.
            # This is a float64 reconstruction from captured REAL32 operands,
            # not a captured shared interface transfer.
            cap_count, cap_gap = 0, 0.0
            if arm == 'FIX' and species < 3 and complete:
                for loop in range(1, loops + 1):
                    mstep = next(key[4] for key in pre_keys if key[0] == loop)
                    for sub in range(1, mstep + 1):
                        for k in range(kts, kte):
                            lower = group[(9, loop, loops, k, sub, mstep)]
                            upper = group[(10, loop, loops, k + 1, sub, mstep)]
                            requested = upper[22 + species] * lower[12] * upper[11]
                            allowed = upper[q_index] * lower[10] * lower[11]
                            if requested > allowed:
                                cap_count += 1
                                cap_gap += requested - allowed
            export, export_loops = 0.0, 0
            for loop in range(1, loops + 1):
                key13 = (13, loop, loops, kts, 0, 0)
                key14 = (14, loop, loops, kts, 0, 0)
                if key13 not in group or key14 not in group:
                    continue
                before, after = group[key13], group[key14]
                if not np.array_equal(before[:10], after[:10]):
                    raise ValueError('surface pre/post fall changed')
                if before[4] <= 0 or before[7] <= 0 or before[9] <= 0:
                    raise ValueError('invalid executed surface fall')
                export += before[species] * before[7] * before[9]
                export_loops += 1
            available = export_loops == loops
            out.append({'arm': arm, 'step': step, 'rank': rank, 'call': call, 'j': j, 'i': i,
                        'species': SPECIES[species], 'loops': loops, 'surface_loops': export_loops,
                        'state_complete': int(complete), 'surface_complete': int(available),
                        'legacy_incoming_cap_count': cap_count if arm == 'FIX' and species < 3 and complete else '',
                        'legacy_incoming_cap_gap_kg_m2': cap_gap if arm == 'FIX' and species < 3 and complete else '',
                        'state_change_kg_m2': total if complete else '',
                        'executed_export_kg_m2': export if available else '',
                        'residual_kg_m2': total + export if complete and available else ''})
    return out


def span_frame(records):
    """Observed ordered endpoint differences, each kept as a separate span."""
    groups = {}
    for phase, i, k, loop, loops, sub, mstep, values in records:
        if phase not in (6, 8, 10, 11, 21):
            continue
        # Only the last actual substep is the sedimentation endpoint.
        if phase in (10, 21) and (mstep < 1 or sub != mstep):
            continue
        key = (i, k, loop, loops)
        group = groups.setdefault(key, {})
        if phase in group:
            raise ValueError('duplicate span endpoint')
        group[phase] = values.astype(np.float64)
    pairs = ((10, 3, 6, 4), (10, 5, 6, 6), (10, 6, 6, 7), (10, 7, 6, 8),
             (21, 1, 6, 1), (21, 2, 6, 2), (21, 3, 6, 5),
             (8, 1, 11, 1), (8, 2, 11, 2), (8, 4, 11, 4), (8, 5, 11, 5))
    result = []
    for (i, k, loop, loops), values in groups.items():
        for field, (a, ai, b, bi) in enumerate(pairs):
            if a in values and b in values:
                result.append((i, k, field, float(values[b][bi] - values[a][ai])))
    return result


def run(arm, folder, output, mode, proof=None):
    if os.path.lexists(output):
        raise FileExistsError(output)
    if arm not in ARMS:
        raise ValueError('invalid arm')
    if mode == 'probe':
        receipt = folder / 'probe_receipt.json'
        if json.loads(receipt.read_text()).get('status') != 'PASS':
            raise ValueError('probe not closed and passed')
    else:
        if proof is None or json.loads(proof.read_text()).get('status') != 'PASS':
            raise ValueError('full audit requires PASS comparability proof')
        proof_data = json.loads(proof.read_text())
        source_receipt = NATIVE / 'source/source_receipt.json'
        source = NATIVE / 'source' / f'module_mp_kdm6_{arm}.f90'
        schema = NATIVE / 'schema/schema.json'
        if proof_data.get('schema_sha256') != sha(schema) or proof_data.get('source_receipt_sha256') != sha(source_receipt):
            raise ValueError('proof does not bind current schema and source receipt')
        arm_proof = proof_data.get('arms', {}).get(arm, {})
        if arm_proof.get('source_sha256') != sha(source) or json.loads(source_receipt.read_text())['arms'][arm]['source_sha256'] != sha(source):
            raise ValueError('proof does not bind actual source')
        capture = NATIVE / 'compact' / arm / 'capture_receipt.json'
        audit = NATIVE / 'compact' / arm / 'audit_receipt.json'
        history = folder / 'history_comparison.json'
        run_receipt = folder / 'run_receipt.json'
        for path, name in ((capture, 'capture_receipt_sha256'), (audit, 'audit_receipt_sha256'),
                           (history, 'history_comparison_sha256'), (run_receipt, 'run_receipt_sha256')):
            if sha(path) != arm_proof.get(name) or json.loads(path.read_text()).get('status') not in ('PASS', 'COMPLETE'):
                raise ValueError('full proof component mismatch: ' + name)
        inventory_path = NATIVE / 'compact' / arm / 'raw_inventory.json'
        inventory_hash = sha(inventory_path)
        if any(json.loads(p.read_text()).get('raw_inventory_sha256') != inventory_hash for p in (capture, audit)):
            raise ValueError('raw inventory not bound by receipts')
        inventory = json.loads(inventory_path.read_text())
        raw_entries = {entry['name']: entry for entry in inventory if entry['name'].startswith('cp04_t') and entry['name'].endswith('.bin')}
        receipt = proof
    raw = sorted(folder.glob('cp04_t*.bin'))
    if not raw:
        raise ValueError('no process frames')
    source_hashes = {str(p.resolve()): sha(p) for p in raw}
    if mode == 'full':
        if set(raw_entries) != {p.name for p in raw}:
            raise ValueError('raw inventory frame scope mismatch')
        for path in raw:
            entry = raw_entries[path.name]
            if source_hashes[str(path.resolve())] != entry['sha256'] or path.stat().st_size != entry['size_bytes']:
                raise ValueError('raw inventory frame hash mismatch')
        for path in (capture, audit, history, run_receipt, inventory_path, source_receipt, source, schema):
            source_hashes[str(path.resolve())] = sha(path)
    source_hashes[str(receipt.resolve())] = sha(receipt)
    counts = phase_counts(arm)
    selected_path = HERE.parent / 'cohorts/results/selected_points.csv'
    cohort_receipt = selected_path.parent / 'receipt.json'
    native_selector = NATIVE / 'source/columns.csv'
    native_source_receipt = NATIVE / 'source/source_receipt.json'
    cohort = json.loads(cohort_receipt.read_text())
    if cohort.get('status') != 'COMPLETE' or cohort['outputs'].get(selected_path.name) != sha(selected_path):
        raise ValueError('selected points do not match completed cohort receipt')
    if json.loads(native_source_receipt.read_text())['selector_sha256'] != sha(native_selector):
        raise ValueError('native selector differs from source receipt')
    for path in (selected_path, cohort_receipt, native_selector, native_source_receipt):
        source_hashes[str(path.resolve())] = sha(path)
    column_points, point_corners = {}, {}
    with selected_path.open(newline='') as stream:
        for selected in csv.DictReader(stream):
            j0 = int(selected['native_j0_fortran_one_based'])
            i0 = int(selected['native_i0_fortran_one_based'])
            point = selected['flat_index_yx']
            corners = []
            for dj, di, field in ((0,0,'weight_j0_i0'), (0,1,'weight_j0_i1'),
                                   (1,0,'weight_j1_i0'), (1,1,'weight_j1_i1')):
                i, j, weight = i0 + di, j0 + dj, float(selected[field])
                column_points.setdefault((i, j), []).append((selected['cohort'], point))
                corners.append((i, j, weight))
            if abs(sum(x[2] for x in corners) - 1) > 1e-12 or any(x[2] < 0 for x in corners):
                raise ValueError('invalid bilinear weights')
            point_corners[point] = (selected['cohort'], corners)
    with native_selector.open(newline='') as stream:
        native_cells = {(int(r['wrf_i_1based']), int(r['wrf_j_1based'])) for r in csv.DictReader(stream)}
    if set(column_points) != native_cells or len(native_cells) != 77:
        raise ValueError('selected-point corners differ from native selector')
    rows, seen = [], set()
    ordered_cells = sorted(native_cells)
    cell_index = {cell:index for index, cell in enumerate(ordered_cells)}
    span_sums, span_counts = {}, {}
    for path in raw:
        for header, records in frames(path, counts):
            step, j = header[2], header[3]
            lead = 1 if step <= 180 else 5 if step <= 900 else 6
            if lead not in span_sums:
                span_sums[lead] = np.zeros((77, 39, len(SPAN_FIELDS)), dtype=np.float64)
                span_counts[lead] = np.zeros((77, 39, len(SPAN_FIELDS)), dtype=np.int32)
            for i, k, field, value in span_frame(records):
                cell = cell_index[(i, j)]
                span_sums[lead][cell, k-1, field] += value
                span_counts[lead][cell, k-1, field] += 1
            for row in audit_frame(arm, header, records):
                key = tuple(row[k] for k in ('step', 'rank', 'call', 'j', 'i', 'species'))
                if key in seen:
                    raise ValueError('duplicate call/column/species')
                seen.add(key)
                points = column_points.get((row['i'], row['j']))
                if not points:
                    raise ValueError('column outside selected points')
                row['point_roles'] = ';'.join(role + ':' + point for role, point in points)
                row['low_new_fa_corner'] = int(any(role.startswith('new_h6_') for role, _ in points))
                rows.append(row)
    rows.sort(key=lambda r: tuple(r[k] for k in ('step', 'rank', 'call', 'j', 'i', 'species')))
    if mode == 'probe' and ({r['step'] for r in rows} != {1, 2, 3} or len(rows) != 3 * 77 * 4):
        raise ValueError('incomplete probe coverage')
    if mode == 'full':
        expected_steps = set(range(1,181)) | set(range(721,1081))
        if {r['step'] for r in rows} != expected_steps or len(rows) != 540 * 77 * 4:
            raise ValueError('incomplete full coverage')
    # Align columns by actual model step, never by sediment substep ordinal.
    index = {}
    for r in rows:
        key = (r['step'], r['i'], r['j'], r['species'])
        if key in index:
            raise ValueError('duplicate column owner at step')
        index[key] = r
    weighted = []
    for step in sorted({r['step'] for r in rows}):
        for point, (role, corners) in sorted(point_corners.items(), key=lambda item: int(item[0])):
            for species in SPECIES:
                parts = [(index.get((step, i, j, species)), w) for i, j, w in corners if w > 0]
                complete = all(r is not None and r['residual_kg_m2'] != '' for r, _ in parts)
                item = {'arm':arm, 'step':step, 'flat_index_yx':point, 'role':role,
                        'species':species, 'all_positive_weight_corners_valid':int(complete)}
                for name in ('state_change_kg_m2', 'executed_export_kg_m2', 'residual_kg_m2'):
                    item[name] = sum(w * r[name] for r, w in parts) if complete else ''
                weighted.append(item)
    hourly = {}
    for r in rows:
        lead = 1 if r['step'] <= 180 else 5 if r['step'] <= 900 else 6
        key = (lead, r['i'], r['j'], r['species'])
        item = hourly.setdefault(key, {'arm':arm, 'lead_hour':lead, 'i':r['i'], 'j':r['j'],
                          'species':r['species'], 'calls':0, 'residual_available':0,
                          'state_change_sum_available_kg_m2':0., 'executed_export_sum_available_kg_m2':0.,
                          'residual_sum_available_kg_m2':0.})
        item['calls'] += 1
        if r['residual_kg_m2'] != '':
            item['residual_available'] += 1
            for field in ('state_change', 'executed_export', 'residual'):
                item[field + '_sum_available_kg_m2'] += r[field + '_kg_m2']
    for item in hourly.values():
        if not item['residual_available']:
            for field in ('state_change', 'executed_export', 'residual'):
                item[field + '_sum_available_kg_m2'] = ''
    output.mkdir(parents=True, exist_ok=False)
    try:
        with (output / 'calls.csv.gz').open('xb') as f:
            with gzip.GzipFile(filename='', mode='wb', fileobj=f, mtime=0) as z:
                with io.TextIOWrapper(z, encoding='utf-8', newline='') as text:
                    writer = csv.DictWriter(text, fieldnames=list(rows[0]), lineterminator='\n')
                    writer.writeheader(); writer.writerows(rows)
        for name, values in (('weighted_points.csv.gz', weighted), ('column_hour.csv.gz', list(hourly.values()))):
            with (output / name).open('xb') as f:
                with gzip.GzipFile(filename='', mode='wb', fileobj=f, mtime=0) as z:
                    with io.TextIOWrapper(z, encoding='utf-8', newline='') as text:
                        writer = csv.DictWriter(text, fieldnames=list(values[0]), lineterminator='\n')
                        writer.writeheader(); writer.writerows(values)
        for lead in sorted(span_sums):
            count = span_counts[lead]
            sums = np.where(count > 0, span_sums[lead], np.nan)
            np.savez_compressed(output / f'spans_h{lead:02d}.npz',
                                i=np.array([c[0] for c in ordered_cells], dtype=np.int32),
                                j=np.array([c[1] for c in ordered_cells], dtype=np.int32),
                                k=np.arange(1, 40, dtype=np.int32),
                                fields=np.array(SPAN_FIELDS), sums=sums, counts=count,
                                present=count > 0)
        summary = {}
        for species in SPECIES:
            rr = [r for r in rows if r['species'] == species]
            valid = [r for r in rr if r['residual_kg_m2'] != '']
            residuals = [r['residual_kg_m2'] for r in valid]
            summary[species] = {'calls': len(rr), 'state_complete': sum(r['state_complete'] for r in rr),
                                'surface_complete': sum(r['surface_complete'] for r in rr),
                                'residual_available': len(valid),
                                'legacy_incoming_cap_calls': sum(r['legacy_incoming_cap_count'] > 0 for r in rr if r['legacy_incoming_cap_count'] != '') if arm == 'FIX' and species != 'ice' else None,
                                'low_new_fa_corner_cap_calls': sum(r['legacy_incoming_cap_count'] > 0 and r['low_new_fa_corner'] for r in rr if r['legacy_incoming_cap_count'] != '') if arm == 'FIX' and species != 'ice' else None,
                                'residual_min_kg_m2': min(residuals) if residuals else None,
                                'residual_max_kg_m2': max(residuals) if residuals else None,
                                'minimum_event': min(valid, key=lambda r:r['residual_kg_m2']) if valid else None}
        event = summary['rain']['minimum_event']
        proof_records = []
        if event is not None:
            for path in raw:
                for header, records in frames(path, counts):
                    rank, call, step, j, *_ = header
                    if (rank, call, step, j) != (event['rank'], event['call'], event['step'], event['j']):
                        continue
                    for phase, i, k, loop, loops, sub, mstep, values in records:
                        if i == event['i'] and phase in (9, 10, 13, 14):
                            proof_records.append({'phase': phase, 'i': i, 'k': k, 'loop': loop, 'loops': loops,
                                                  'substep': sub, 'mstep': mstep,
                                                  'values': [float(v) for v in values]})
                    if proof_records:
                        break
                if proof_records:
                    break
            if not proof_records:
                raise ValueError('selected event raw records missing')
        (output / 'rain_extreme_records.json').write_text(json.dumps({'event':event, 'records':proof_records}, indent=2, allow_nan=False) + '\n')
        (output / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
        for name, digest in source_hashes.items():
            if sha(name) != digest:
                raise ValueError('input changed during audit')
        receipt_data = {'status':'PASS', 'mode':mode, 'arm':arm, 'inputs':source_hashes,
                        'auditor_sha256':sha(__file__), 'parser_sha256':sha(NATIVE / 'runs/read_frames.py'),
                        'schema_sha256':sha(NATIVE / 'schema/schema.json'),
                        'outputs':{p.name:sha(p) for p in sorted(output.iterdir())}}
        (output / 'receipt.json').write_text(json.dumps(receipt_data, indent=2) + '\n')
    except BaseException:
        import shutil
        shutil.rmtree(output)
        raise
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arm', choices=ARMS, required=True)
    p.add_argument('--folder', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--mode', choices=('probe', 'full'), required=True)
    p.add_argument('--proof', type=Path)
    a = p.parse_args()
    print(json.dumps(run(a.arm, a.folder, a.output, a.mode, a.proof), indent=2))


if __name__ == '__main__':
    main()
