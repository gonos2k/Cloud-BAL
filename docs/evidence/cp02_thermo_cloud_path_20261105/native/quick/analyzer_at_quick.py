#!/usr/bin/env python3
"""Strict readers and arithmetic for selected-cell CP04 KDM6 diagnostics."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

import numpy as np

FRAME_MAGIC = b'C4FR0001'
FRAME_HEADER = struct.Struct('>8i')
RECORD_HEADER = struct.Struct('>7i')
INT = struct.Struct('>i')


@dataclass(frozen=True)
class Frame:
    rank: int
    call_id: int
    timestep: int
    j: int
    its: int
    ite: int
    kts: int
    kte: int
    constants: tuple[float, ...]


@dataclass(frozen=True)
class Record:
    phase: int
    i: int
    k: int
    loop: int
    loops: int
    substep: int
    mstep: int
    values: np.ndarray


def _read_exact(stream, count):
    result = stream.read(count)
    if len(result) != count:
        raise ValueError('truncated CP04 frame or record')
    return result


def iter_frames(path, field_counts, rank):
    """Yield frame header and its records, refusing malformed binary payloads.

    Field counts come from the separately pinned schema, not the input stream.
    Coverage and cross-file ownership require validation by the caller.
    """
    with Path(path).open('rb', buffering=1024 * 1024) as stream:
        while magic := stream.read(len(FRAME_MAGIC)):
            if magic != FRAME_MAGIC:
                raise ValueError('invalid CP04 frame marker')
            header = FRAME_HEADER.unpack(_read_exact(stream, FRAME_HEADER.size))
            constants = struct.unpack('>10f', _read_exact(stream, 40))
            if not np.isfinite(constants).all():
                raise ValueError('nonfinite CP04 constants')
            frame = Frame(*header, constants)
            if frame.rank != rank or frame.call_id < 1 or not 1 <= frame.timestep <= 360:
                raise ValueError('invalid rank, call or timestep')
            if frame.its > frame.ite or frame.kts > frame.kte or frame.j < 1:
                raise ValueError('invalid core bounds')
            records = []
            while True:
                phase = INT.unpack(_read_exact(stream, INT.size))[0]
                if phase == -1:
                    break
                if phase not in field_counts:
                    raise ValueError('unknown CP04 phase')
                i, k, loop, loops, substep, mstep, count = RECORD_HEADER.unpack(
                    _read_exact(stream, RECORD_HEADER.size))
                if count != field_counts[phase]:
                    raise ValueError('incorrect CP04 field count')
                if not frame.its <= i <= frame.ite or not frame.kts <= k <= frame.kte:
                    raise ValueError('record outside frame core')
                if phase in (1, 2):
                    if loop != 0 or loops != 0:
                        raise ValueError('entry record has invalid loop')
                elif not 1 <= loop <= loops:
                    raise ValueError('invalid process loop')
                if phase in (9, 10):
                    if not 1 <= substep <= mstep:
                        raise ValueError('invalid sedimentation substep')
                elif substep != 0 or mstep != 0:
                    raise ValueError('unexpected substep')
                values = np.frombuffer(_read_exact(stream, count * 4), dtype='>f4')
                if not np.isfinite(values).all():
                    raise ValueError('nonfinite CP04 payload')
                records.append(Record(phase, i, k, loop, loops, substep, mstep, values))
            yield frame, records


def exner_decomposition(old_theta, old_exner, new_theta, new_exner):
    """Decompose rounded TH*PII change into two algebraic terms and residual."""
    a, b, c, d = (np.asarray(x, dtype=np.float32) for x in
                  (old_theta, old_exner, new_theta, new_exner))
    old_product = np.multiply(a, b, dtype=np.float32).astype(np.float64)
    new_product = np.multiply(c, d, dtype=np.float32).astype(np.float64)
    theta_term = d.astype(np.float64) * (c.astype(np.float64) - a.astype(np.float64))
    exner_term = a.astype(np.float64) * (d.astype(np.float64) - b.astype(np.float64))
    residual = (new_product - old_product) - (theta_term + exner_term)
    return theta_term, exner_term, residual


def validate_frame(frame, records, selected_i):
    """Validate all selected levels, required phases and complete actual substeps."""
    expected_i = set(selected_i)
    if not expected_i or any(i < frame.its or i > frame.ite for i in expected_i):
        raise ValueError('selected cells do not match frame core')
    seen = set()
    loops_by_cell = {}
    sediment = {}
    pending = {}
    for rec in records:
        if rec.i not in expected_i:
            raise ValueError('unselected cell in frame')
        key = (rec.phase, rec.i, rec.k, rec.loop, rec.substep)
        if key in seen:
            raise ValueError('duplicate phase record')
        seen.add(key)
        if rec.phase not in (1, 2):
            cell = (rec.i, rec.k)
            if cell in loops_by_cell and loops_by_cell[cell] != rec.loops:
                raise ValueError('inconsistent process loop count')
            loops_by_cell[cell] = rec.loops
        if rec.phase in (9, 10):
            cell = (rec.i, rec.k, rec.loop)
            if cell in sediment and sediment[cell] != rec.mstep:
                raise ValueError('inconsistent sedimentation substep count')
            sediment[cell] = rec.mstep
            expected = pending.get(cell, 1)
            if rec.phase == 9:
                if rec.substep != expected:
                    raise ValueError('sedimentation pre order differs')
                pending[cell] = -expected
            else:
                if expected != -rec.substep:
                    raise ValueError('sedimentation post without matching pre')
                pending[cell] = rec.substep + 1
        if rec.phase in (13, 14) and rec.k != frame.kts:
            raise ValueError('surface phase above bottom level')
    for i in expected_i:
        for k in range(frame.kts, frame.kte + 1):
            for phase in (1, 2):
                if (phase, i, k, 0, 0) not in seen:
                    raise ValueError('missing entry phase')
            loops = loops_by_cell.get((i, k), 0)
            if not loops:
                raise ValueError('missing process phases')
            for loop in range(1, loops + 1):
                for phase in (3, 4, 5, 6, 7, 8, 11, 12):
                    if (phase, i, k, loop, 0) not in seen:
                        raise ValueError('missing mandatory process phase')
                mstep = sediment.get((i, k, loop))
                if mstep is None:
                    raise ValueError('missing sedimentation')
                for substep in range(1, mstep + 1):
                    for phase in (9, 10):
                        if (phase, i, k, loop, substep) not in seen:
                            raise ValueError('missing sedimentation phase/substep')
                for first, second in ((13, 14),):
                    if ((first, i, k, loop, 0) in seen) != ((second, i, k, loop, 0) in seen):
                        raise ValueError('unpaired conditional surface phase')


def read_selected_state(paths, stage, cells, steps, levels, owners, calls):
    """Read the CP04 16-field wrapper blocks with complete core ownership."""
    import re
    cell_index = {cell: n for n, cell in enumerate(cells)}
    if len(cell_index) != len(cells):
        raise ValueError('duplicate native cell')
    shape = (steps, levels, len(cells))
    result = np.empty((*shape, 16), dtype=np.float32)
    present = np.zeros(shape, dtype=bool)
    block_header = struct.Struct('>8s15i')
    row_type = np.dtype([('i', '>i4'), ('j', '>i4'), ('k', '>i4'), ('values', '>f4', (16,))])
    stage_name = {6: 'entry', 7: 'return'}[stage]
    blocks = set()
    for path in paths:
        match = re.fullmatch(rf'state_selected_{stage_name}_rank(\d+)\.bin', Path(path).name)
        if not match:
            raise ValueError('invalid selected-state filename')
        rank = int(match.group(1))
        with Path(path).open('rb') as stream:
            while raw := stream.read(block_header.size):
                if len(raw) != block_header.size:
                    raise ValueError('truncated selected-state header')
                magic, sid, fr, call, step, ilo, ihi, jlo, jhi, klo, khi, si, sj, sk, fields, count = block_header.unpack(raw)
                key = (step, rank, call)
                if (magic != b'CBSP0001' or sid != stage or fr != rank or
                    (ilo, ihi, jlo, jhi, klo, khi) != calls.get(key) or
                    (si, sj, sk, fields) != (1, 1, 1, 16) or count < 0 or key in blocks):
                    raise ValueError('invalid or duplicate selected-state block')
                blocks.add(key)
                rows = np.frombuffer(_read_exact(stream, count * row_type.itemsize), dtype=row_type)
                if not np.isfinite(rows['values']).all():
                    raise ValueError('nonfinite wrapper state')
                for row in rows:
                    i, j, k = (int(row[v]) for v in ('i', 'j', 'k'))
                    ci = cell_index.get((i, j))
                    if ci is None or not 1 <= k <= levels or owners.get((step, i, j, k)) != (rank, call):
                        raise ValueError('wrapper row not owned by rank/core')
                    ix = (step - 1, k - 1, ci)
                    if present[ix]:
                        raise ValueError('duplicate wrapper row')
                    present[ix] = True
                    result[ix] = row['values']
    if not present.all():
        raise ValueError('incomplete wrapper coverage')
    product = np.multiply(result[..., 0], result[..., 15], dtype=np.float32)
    if not np.array_equal(product.view('u4'), result[..., 13].view('u4')):
        raise ValueError('wrapper TK differs from float32 TH*PII')
    return result


def read_process(paths, schema, cells, steps, levels, owners, calls, loops=1):
    """Read selected CP04 phases, enforcing actual frame and cell coverage."""
    import re
    if loops != 1:
        raise ValueError('this analyzer requires verified one-loop physics')
    counts = {int(k): len(v['fields']) for k, v in schema['phases'].items()}
    if set(counts) != set(range(1, 18)):
        raise ValueError('unexpected phase inventory')
    indexes = {cell: n for n, cell in enumerate(cells)}
    if len(indexes) != len(cells):
        raise ValueError('duplicate selected cell')
    shape = (steps, levels, len(cells))
    mandatory = (1, 2, 3, 4, 5, 6, 7, 8, 11, 12)
    values = {p: np.empty((*shape, counts[p]), dtype=np.float32) for p in mandatory}
    optional = {p: np.full((*shape, counts[p]), np.nan, dtype=np.float32) for p in (15, 16, 17)}
    surface = np.full((2, steps, len(cells), counts[13]), np.nan, dtype=np.float32)
    sed_pre = np.empty((*shape, 3), dtype=np.float32)
    sed_net = np.zeros((*shape, 3), dtype=np.float64)
    sed_msteps = np.zeros(shape, dtype=np.int32)
    seen = np.zeros(shape, dtype=bool)
    frame_keys = set()
    constants = None
    phase_counts = {p: 0 for p in counts}
    for path in paths:
        match = re.fullmatch(r'cp04_rank(\d+)\.bin', Path(path).name)
        if not match:
            raise ValueError('invalid CP04 filename')
        rank = int(match.group(1))
        for frame, records in iter_frames(path, counts, rank):
            if frame.timestep > steps or frame.kts != 1 or frame.kte != levels:
                raise ValueError('CP04 frame outside requested capture')
            bounds = calls.get((frame.timestep, rank, frame.call_id))
            if bounds is None or (frame.its, frame.ite, frame.kts, frame.kte) != (bounds[0], bounds[1], bounds[4], bounds[5]) or not bounds[2] <= frame.j <= bounds[3]:
                raise ValueError('CP04 frame is not an owning call')
            key = (frame.timestep, rank, frame.call_id, frame.j)
            if key in frame_keys:
                raise ValueError('duplicate CP04 frame')
            frame_keys.add(key)
            if constants is None:
                constants = frame.constants
            elif constants != frame.constants:
                raise ValueError('CP04 source constants changed')
            selected_i = [i for i, j in cells if j == frame.j and frame.its <= i <= frame.ite]
            validate_frame(frame, records, selected_i)
            for i in selected_i:
                ci = indexes[i, frame.j]
                for k in range(1, levels + 1):
                    if owners.get((frame.timestep, i, frame.j, k)) != (rank, frame.call_id):
                        raise ValueError('CP04 record conflicts with core owner')
                    ix = (frame.timestep - 1, k - 1, ci)
                    if seen[ix]:
                        raise ValueError('duplicate CP04 cell coverage')
                    seen[ix] = True
            for rec in records:
                if rec.phase not in (1, 2) and rec.loops != loops:
                    raise ValueError('unexpected actual process loop count')
                ix = (frame.timestep - 1, rec.k - 1, indexes[rec.i, frame.j])
                phase_counts[rec.phase] += 1
                if rec.phase in mandatory:
                    values[rec.phase][ix] = rec.values
                elif rec.phase in optional:
                    optional[rec.phase][ix] = rec.values
                elif rec.phase in (13, 14):
                    surface[rec.phase - 13, frame.timestep - 1, indexes[rec.i, frame.j]] = rec.values
                elif rec.phase == 9:
                    sed_pre[ix] = rec.values[5:8]
                    sed_msteps[ix] = rec.mstep
                elif rec.phase == 10:
                    sed_net[ix] += rec.values[5:8].astype(np.float64) - sed_pre[ix].astype(np.float64)
    if not seen.all():
        raise ValueError('incomplete actual CP04 cell coverage')
    return values, optional, surface, sed_net, sed_msteps, phase_counts, constants


def validate_wrapper_binding(entry, returned, raw, clamped):
    """Cross-check pressure, thermodynamic, mass and density-converted numbers."""
    for wrapper, internal in ((14, 0), (1, 1), (13, 2), (12, 3), (2, 4), (4, 5),
                              (3, 6), (5, 7), (6, 8), (11, 15)):
        if not np.array_equal(entry[..., wrapper].view('u4'), raw[..., internal].view('u4')):
            raise ValueError('wrapper and internal entry differ')
    for wrapper, internal in ((8, 9), (9, 10), (7, 11), (10, 12)):
        product = np.multiply(entry[..., wrapper], entry[..., 12], dtype=np.float32)
        if not np.array_equal(product.view('u4'), raw[..., internal].view('u4')):
            raise ValueError('internal number density conversion differs')
    for field, lo, hi in ((9, 0, None), (10, 0, 1.e6), (11, 1.e8, 2.e10), (12, 0, None), (15, 0, None)):
        expected = np.maximum(raw[..., field], np.float32(lo))
        if hi is not None:
            expected = np.minimum(expected, np.float32(hi))
        if not np.array_equal(expected, clamped[..., field]):
            raise ValueError('internal entry clamp differs')
    for field in (14, 15):
        if not np.array_equal(entry[..., field].view('u4'), returned[..., field].view('u4')):
            raise ValueError('wrapper pressure or Exner changed within KDM6 call')


def process_arithmetic(values):
    """Verify captured update statements and return selected signed components."""
    before, after, latent = values[6], values[8], values[7]
    rates, precond, postcond = values[5], values[11], values[12]
    f = np.float32
    q_expected = f(before[..., 1] + f(before[..., 16] * before[..., 17]))
    t_expected = f(before[..., 2] - f(f(latent[..., 1] / latent[..., 2]) * latent[..., 3]))
    q_cond = f(precond[..., 1] - f(precond[..., 9] * precond[..., 10]))
    t_cond = f(precond[..., 2] + f(f(f(precond[..., 9] * precond[..., 11]) / precond[..., 12]) * precond[..., 10]))
    for expected, actual in ((q_expected, after[..., 1]), (t_expected, after[..., 2]),
                             (q_cond, postcond[..., 1]), (t_cond, postcond[..., 2])):
        if not np.array_equal(expected.view('u4'), actual.view('u4')):
            raise ValueError('captured source update does not reproduce float32 arithmetic')
    # Source-order contribution of rain evaporation. Residual includes other
    # terms and finite-precision interaction; it is not a causal attribution.
    evap_q = f(-f(rates[..., 2] * before[..., 17]))
    q_change = after[..., 1].astype(np.float64) - before[..., 1].astype(np.float64)
    return {
        'prevp_q': evap_q,
        'prevp_q_residual': q_change - evap_q.astype(np.float64),
        'latent_temperature_change': after[..., 2].astype(np.float64) - before[..., 2].astype(np.float64),
        'condensation_q_change': postcond[..., 1].astype(np.float64) - precond[..., 1].astype(np.float64),
        'condensation_temperature_change': postcond[..., 2].astype(np.float64) - precond[..., 2].astype(np.float64),
    }


def read_corners(path):
    import csv
    import math
    groups = {}
    with Path(path).open(newline='', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            point = row['point_id']
            cell = (int(row['wrf_i_1based']), int(row['wrf_j_1based']))
            weight = float(row['weight'])
            if not math.isfinite(weight) or weight <= 0:
                raise ValueError('corner weight must be finite and positive')
            groups.setdefault(point, []).append((row['corner'], cell, weight))
    cells = sorted({cell for rows in groups.values() for _, cell, _ in rows})
    if len(groups) != 39 or len(cells) != 123:
        raise ValueError('cohort dimensions differ')
    lookup = {cell: n for n, cell in enumerate(cells)}
    indices, weights = [], []
    for point, rows in groups.items():
        if len(rows) != 4 or {r[0] for r in rows} != {'00', '01', '10', '11'} or not math.isclose(sum(r[2] for r in rows), 1, abs_tol=1e-12, rel_tol=0):
            raise ValueError(f'invalid point corners: {point}')
        indices.append([lookup[r[1]] for r in rows])
        weights.append([r[2] for r in rows])
    return list(groups), cells, np.array(indices), np.array(weights)


def weighted(values, indices, weights):
    """Require all four corners; NaN means a conditional observation is absent."""
    sample = np.take(values, indices, axis=-2).astype(np.float64)
    return np.einsum('...pcf,pc->...pf', sample, weights, optimize=True)


def sha256(path):
    import hashlib
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(roots):
    """Capture identities of every raw stream needed for reproducible replay."""
    patterns = ('state_calls_rank*.txt', 'state_selected_entry_rank*.bin',
                'state_selected_return_rank*.bin', 'cp04_rank*.bin', 'surface_cp04_rank*.bin',
                'launch_receipt.json')
    result = {}
    for arm, root in roots.items():
        files = []
        for pattern in patterns:
            paths = sorted(Path(root).glob(pattern))
            if not paths:
                raise ValueError(f'{arm} missing inputs matching {pattern}')
            files.extend(paths)
        result[arm] = [{'path': str(p.resolve()), 'size_bytes': p.stat().st_size, 'sha256': sha256(p)} for p in files]
    return result


def verify_inventory(inventories):
    for items in inventories.values():
        for item in items:
            path = Path(item['path'])
            if path.stat().st_size != item['size_bytes'] or sha256(path) != item['sha256']:
                raise ValueError(f'capture input changed: {path}')


def read_surface(paths, cells, steps, owners):
    import re
    row = struct.Struct('>8s5i3f')
    index = {cell: n for n, cell in enumerate(cells)}
    result = np.empty((steps, len(cells), 3), dtype=np.float32)
    seen = np.zeros((steps, len(cells)), dtype=bool)
    for path in paths:
        match = re.fullmatch(r'surface_cp04_rank(\d+)\.bin', Path(path).name)
        if not match:
            raise ValueError('invalid surface filename')
        rank = int(match.group(1))
        with Path(path).open('rb') as stream:
            while raw := stream.read(row.size):
                if len(raw) != row.size:
                    raise ValueError('truncated surface return')
                magic, fr, call, step, j, i, rainncv, rain, sr = row.unpack(raw)
                ci = index.get((i, j))
                if (magic != b'C4SR0001' or fr != rank or ci is None or not 1 <= step <= steps or
                    owners.get((step, i, j, 1)) != (rank, call) or seen[step-1, ci]):
                    raise ValueError('invalid or duplicate surface return')
                if not np.isfinite((rainncv, rain, sr)).all():
                    raise ValueError('nonfinite surface return')
                seen[step-1, ci] = True
                result[step-1, ci] = rainncv, rain, sr
    if not seen.all():
        raise ValueError('incomplete surface return coverage')
    return result


def validate_surface(surface, returned):
    before, after = surface
    present = np.isfinite(before[..., 0])
    if not np.array_equal(present, np.isfinite(after[..., 0])):
        raise ValueError('surface masks disagree')
    x = before[present]
    y = after[present]
    delta = np.float32(np.float32(np.float32(np.float32(x[:, 4] * x[:, 7]) / x[:, 8]) * x[:, 9]) * np.float32(1000.))
    for col in (10, 11):
        expected = np.float32(x[:, col] + delta)
        if not np.array_equal(expected.view('u4'), y[:, col].view('u4')):
            raise ValueError('surface accumulation differs from source arithmetic')
    if not np.array_equal(after[..., 10][present].view('u4'), returned[..., 1][present].view('u4')):
        raise ValueError('conditional surface rain differs from wrapper return')


def validate_surface_reference(path, receipt_path, arm, cells, returned, steps):
    import csv
    import json
    receipt = json.loads(Path(receipt_path).read_text())
    if (receipt.get('status') != 'PASS' or receipt['cohort_sha256']['point_corners.csv'] !=
            'b5d4de1d9209048e6e157ec8d5fe801f8464ee0b9fe307f5656cff32e09923fa' or
            receipt['outputs']['native_surface.csv']['sha256'] != sha256(path)):
        raise ValueError('surface reference receipt does not bind cohort and CSV')
    index = {cell: n for n, cell in enumerate(cells)}
    observed = set()
    with Path(path).open(newline='', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            if row['arm'] != arm:
                continue
            hour = int(row['hour'])
            cell = (int(row['wrf_i_1based']), int(row['wrf_j_1based']))
            if hour not in (0, 1, 2) or cell not in index or (hour, cell) in observed:
                raise ValueError('invalid or duplicate native surface reference')
            observed.add((hour, cell))
            raw = bytes.fromhex(row['RAINNC_float32_le_hex'])
            if len(raw) != 4 or not np.isfinite(np.frombuffer(raw, dtype='<f4')[0]):
                raise ValueError('invalid RAINNC reference word')
            if hour:
                if hour * 180 > steps:
                    raise ValueError('capture does not reach reference hour')
                captured = returned[hour * 180 - 1, index[cell], 1]
                if np.asarray(captured, dtype='<f4').tobytes() != raw:
                    raise ValueError('surface RAINNC differs from same-arm history word')
    if len(observed) != 3 * len(cells):
        raise ValueError('incomplete native surface reference')
    return 2 * len(cells)


def analyze_arm(root, arm, output, schema, cells, indices, weights, steps, surface_reference=None, surface_receipt=None):
    from cp02_rain_number_process import read_owners
    root = Path(root)
    owners, calls = read_owners(sorted(root.glob('state_calls_rank*.txt')), cells, steps, 39)
    entry = read_selected_state(sorted(root.glob('state_selected_entry_rank*.bin')), 6, cells, steps, 39, owners, calls)
    returned = read_selected_state(sorted(root.glob('state_selected_return_rank*.bin')), 7, cells, steps, 39, owners, calls)
    phases, optional, surface, sediment, mstep, counts, constants = read_process(
        sorted(root.glob('cp04_rank*.bin')), schema, cells, steps, 39, owners, calls)
    validate_wrapper_binding(entry, returned, phases[1], phases[2])
    satdt = phases[4]
    actual = np.float32(np.float32(np.maximum(satdt[..., 1], np.float32(constants[0])) - satdt[..., 4]) / satdt[..., 7])
    if not np.array_equal(actual.view('u4'), satdt[..., 6].view('u4')):
        raise ValueError('liquid SATDT differs from source arithmetic')
    components = process_arithmetic(phases)
    surface_return = read_surface(sorted(root.glob('surface_cp04_rank*.bin')), cells, steps, owners)
    validate_surface(surface, surface_return)
    reference_matches = (validate_surface_reference(surface_reference, surface_receipt, arm, cells, surface_return, steps)
                         if surface_reference is not None else None)
    products = {'entry': weighted(entry, indices, weights),
                'return': weighted(returned, indices, weights),
                'sedimentation_net': weighted(sediment, indices, weights),
                'sedimentation_mstep': np.take(mstep, indices, axis=-1),
                'surface_return': weighted(surface_return[:, None], indices, weights)[:, 0],
                'surface_conditional': np.stack([weighted(surface[i, :, None], indices, weights)[:, 0] for i in (0, 1)])}
    terms = exner_decomposition(returned[:-1, ..., 0], returned[:-1, ..., 15],
                                 entry[1:, ..., 0], entry[1:, ..., 15])
    for name, term in zip(('between_theta', 'between_exner', 'between_product_roundoff'), terms):
        products[name] = weighted(term[..., None], indices, weights)[..., 0]
    for phase, array in phases.items():
        products[f'phase_{phase}'] = weighted(array, indices, weights)
    for phase, array in optional.items():
        products[f'phase_{phase}'] = weighted(array, indices, weights)
    for name, array in components.items():
        products[name] = weighted(array[..., None], indices, weights)[..., 0]
    for name, array in {
        'gap_post_update_to_pre_cond_q': phases[11][..., 1].astype(np.float64) - phases[8][..., 1],
        'gap_post_update_to_pre_cond_t': phases[11][..., 2].astype(np.float64) - phases[8][..., 2],
        'gap_post_cond_to_return_q': returned[..., 1].astype(np.float64) - phases[12][..., 1],
        'gap_post_cond_to_return_t': returned[..., 13].astype(np.float64) - phases[12][..., 2],
    }.items():
        products[name] = weighted(array[..., None], indices, weights)[..., 0]
    native_path = Path(output) / f'{arm}_native_wrapper.npz'
    np.savez_compressed(native_path, entry=entry, returned=returned)
    path = Path(output) / f'{arm}_point_timeseries.npz'
    np.savez_compressed(path, **products)
    return {'coverage_cell_steps': int(steps * 39 * len(cells)), 'phase_counts': counts,
            'source_constants': constants, 'output_sha256': sha256(path), 'output_bytes': path.stat().st_size,
            'RAINNC_history_word_matches': reference_matches, 'native_wrapper_sha256': sha256(native_path), 'native_wrapper_bytes': native_path.stat().st_size}


def paired_results(output, points, cells):
    """Compute paired per-point differences, preserving observed source phases."""
    import csv
    with np.load(Path(output) / 'B1_point_timeseries.npz', allow_pickle=False) as a, \
         np.load(Path(output) / 'DM065_point_timeseries.npz', allow_pickle=False) as b:
        pair = {}
        for field in ('entry', 'return', 'phase_3', 'phase_4', 'phase_5', 'phase_7',
                      'phase_11', 'phase_12', 'sedimentation_net', 'prevp_q',
                      'prevp_q_residual', 'latent_temperature_change', 'condensation_q_change',
                      'condensation_temperature_change', 'gap_post_update_to_pre_cond_q',
                      'gap_post_update_to_pre_cond_t', 'gap_post_cond_to_return_q',
                      'gap_post_cond_to_return_t', 'between_theta', 'between_exner',
                      'between_product_roundoff', 'surface_return'):
            pair[field + '_difference'] = b[field] - a[field]
        pair['within_call_difference'] = pair['return_difference'] - pair['entry_difference']
        pair['between_call_difference'] = pair['entry_difference'][1:] - pair['return_difference'][:-1]
        first = []
        for point_index, point in enumerate(points):
            for level in range(pair['entry_difference'].shape[1]):
                for field_index, field in enumerate(('TH', 'QV', 'QC', 'QR', 'QI', 'QS', 'QG', 'NN',
                                                     'NC', 'NI', 'NR', 'BG', 'DEN', 'TK', 'P', 'PII')):
                    series = pair['entry_difference'][:, level, point_index, field_index]
                    hits = np.flatnonzero(series != 0)
                    first.append((point, level + 1, field, int(hits[0] + 1) if hits.size else '',
                                  int((hits[0] + 1) * 20) if hits.size else '',
                                  float(series[hits[0]]) if hits.size else ''))
        np.savez_compressed(Path(output) / 'paired_differences.npz', **pair)
        with (Path(output) / 'first_weighted_entry_difference.csv').open('x', newline='') as stream:
            writer = csv.writer(stream, lineterminator='\n')
            writer.writerow(('point_id', 'level_1based', 'wrapper_field', 'first_step', 'step_end_lead_seconds', 'weighted_difference'))
            writer.writerows(first)
    with np.load(Path(output) / 'B1_native_wrapper.npz', allow_pickle=False) as a, \
         np.load(Path(output) / 'DM065_native_wrapper.npz', allow_pickle=False) as b:
        av, bv = a['entry'], b['entry']
        fields = ('TH', 'QV', 'QC', 'QR', 'QI', 'QS', 'QG', 'NN', 'NC', 'NI', 'NR', 'BG', 'DEN', 'TK', 'P', 'PII')
        with (Path(output) / 'first_native_entry_difference.csv').open('x', newline='') as stream:
            writer = csv.writer(stream, lineterminator='\n')
            writer.writerow(('i_1based', 'j_1based', 'level_1based', 'wrapper_field', 'first_step', 'step_end_lead_seconds', 'difference'))
            for ci, (i, j) in enumerate(cells):
                for k in range(av.shape[1]):
                    for fi, field in enumerate(fields):
                        hits = np.flatnonzero(av[:, k, ci, fi] != bv[:, k, ci, fi])
                        step = int(hits[0]) if hits.size else None
                        writer.writerow((i, j, k + 1, field, step + 1 if step is not None else '',
                                         (step + 1) * 20 if step is not None else '',
                                         float(np.float64(bv[step, k, ci, fi]) - av[step, k, ci, fi]) if step is not None else ''))
    return {name: {'sha256': sha256(Path(output) / name), 'size_bytes': (Path(output) / name).stat().st_size}
            for name in ('paired_differences.npz', 'first_weighted_entry_difference.csv', 'first_native_entry_difference.csv')}


def main():
    import argparse
    import json
    import os
    import shutil
    import tempfile
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--b1', required=True)
    parser.add_argument('--dm065', required=True)
    parser.add_argument('--history-gate', required=True)
    parser.add_argument('--source-freeze', required=True)
    parser.add_argument('--surface-reference', required=True)
    parser.add_argument('--surface-receipt', required=True)
    parser.add_argument('--schema', required=True)
    parser.add_argument('--corners', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if sha256(args.surface_reference) != '19bf49cd1a673a1a9b3064669d2740455d750b51e224eec0bb1cecaf26fdd3aa' or sha256(args.surface_receipt) != 'ea30ce9690ffa799fdf96f2ca2132ca953790f94deb77443641ae5e174eff516':
        raise ValueError('frozen surface reference pin differs')
    schema_pin = '64496e9f19ec0042762a7b8fa7d4f8006ea617a45433434242706c223db2210c'
    corner_pin = 'b5d4de1d9209048e6e157ec8d5fe801f8464ee0b9fe307f5656cff32e09923fa'
    if sha256(args.schema) != schema_pin or sha256(args.corners) != corner_pin:
        raise ValueError('frozen schema or cohort pin differs')
    source_freeze = json.loads(Path(args.source_freeze).read_text())
    for path, expected in source_freeze['sha256'].items():
        if sha256(path) != expected:
            raise ValueError(f'frozen physics source changed: {path}')
    schema = json.loads(Path(args.schema).read_text())
    gate_path = Path(args.history_gate)
    gate = json.loads(gate_path.read_text())
    if gate.get('status') != 'PASS':
        raise ValueError('history parity gate is not PASS')
    roots = {'B1': Path(args.b1), 'DM065': Path(args.dm065)}
    for arm, root in roots.items():
        launch = json.loads((root / 'launch_receipt.json').read_text())
        if launch.get('status') != 'PASS' or not launch.get('inputs_unchanged'):
            raise ValueError(f'{arm} forecast receipt is not PASS')
    output = Path(args.output)
    if os.path.lexists(output):
        raise FileExistsError(f'output exists: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.cp04-', dir=output.parent))
    try:
        pins = {'schema_sha256': schema_pin, 'corners_sha256': corner_pin,
                'history_gate_sha256': sha256(gate_path), 'analyzer_sha256': sha256(Path(__file__)),
                'source_freeze_sha256': sha256(args.source_freeze),
                'surface_reference_sha256': sha256(args.surface_reference),
                'surface_receipt_sha256': sha256(args.surface_receipt),
                'owner_reader_sha256': sha256(Path(__file__).with_name('cp02_rain_number_process.py'))}
        inventories = inventory(roots)
        (temporary / 'input_manifest.json').write_text(json.dumps({'pins': pins, 'arms': inventories}, indent=2, sort_keys=True) + '\n')
        points, cells, indices, weights = read_corners(args.corners)
        results = {}
        for arm, root in roots.items():
            results[arm] = analyze_arm(root, arm, temporary, schema, cells, indices, weights, 360, args.surface_reference, args.surface_receipt)
            print(f'{arm} full coverage validated', flush=True)
        paired = paired_results(temporary, points, cells)
        if results['B1']['source_constants'] != results['DM065']['source_constants']:
            raise ValueError('two cases used different microphysics constants')
        verify_inventory(inventories)
        for path, expected in source_freeze['sha256'].items():
            if sha256(path) != expected:
                raise ValueError(f'frozen physics source changed: {path}')
        if sha256(args.surface_reference) != pins['surface_reference_sha256'] or sha256(args.surface_receipt) != pins['surface_receipt_sha256']:
            raise ValueError('surface reference changed during analysis')
        if sha256(args.schema) != schema_pin or sha256(args.corners) != corner_pin or sha256(gate_path) != pins['history_gate_sha256']:
            raise ValueError('frozen source changed during analysis')
        receipt = {'status': 'PASS_FULL_CAPTURE', 'steps': 360, 'levels': 39, 'unique_native_cells': 123,
                   'point_ids': points, 'native_cells_i_j_1based': cells, 'point_corner_indices': indices.tolist(),
                   'point_corner_weights': weights.tolist(), 'manifest_sha256': sha256(temporary / 'input_manifest.json'),
                   'arms': results, 'paired_outputs': paired, 'limitations': 'Time labels are step ends; entry is sampled during that step and is not asserted at its end. Fixed Eulerian sample, not trajectories; between-call net is not pure transport; arithmetic component terms are not causal attribution; conditional absence remains NaN.'}
        (temporary / 'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
        if os.path.lexists(output):
            raise FileExistsError('output appeared during analysis')
        os.rename(temporary, output)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(json.dumps({'status': receipt['status'], 'receipt_sha256': sha256(output / 'receipt.json')}))


if __name__ == '__main__':
    main()
