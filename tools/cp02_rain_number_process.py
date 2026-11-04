#!/usr/bin/env python3
"""Strict CP03 process-record decoder and coverage accumulator.

CP03 records are selected-cell diagnostics, not a complete water budget.
Array axes are (timestep, microphysics loop, level, native cell).
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import struct

import numpy as np

SCHEMA_SHA256 = '3427340bf76f9d4fb662f9891ae5029546c4bdc78d5a5c3e71ed49f03610d87f'
FIELD_COUNTS = {1: 21, 2: 26, 3: 12, 4: 12, 5: 11, 6: 11}


class TraceError(ValueError):
    """A selected process trace violates its capture contract."""


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _integer(token, where):
    try:
        # int() also accepts underscores, which Fortran list output cannot contain.
        if not token or not token.lstrip('+-').isdigit() or token in ('+', '-'):
            raise ValueError
        return int(token, 10)
    except ValueError as exc:
        raise TraceError(f'{where}: invalid integer {token!r}') from exc


def records(lines, source='<stream>'):
    """Decode list-directed wrapped records, rejecting unknown/truncated input."""
    pending = []
    start = 0
    expected = None
    for number, line in enumerate(lines, 1):
        words = line.split()
        if not words:
            continue
        if words[0] == 'CP03':
            if pending:
                raise TraceError(f'{source}:{number}: new record before prior record completed')
            pending = words
            start = number
        elif pending:
            pending.extend(words)
        else:
            raise TraceError(f'{source}:{number}: unknown record marker {words[0]!r}')
        if len(pending) >= 13 and expected is None:
            header = [_integer(w, f'{source}:{start}') for w in pending[1:13]]
            phase, rank, call, step, loop, loops, i, j, k, substep, mstep, count = header
            if phase not in FIELD_COUNTS or count != FIELD_COUNTS.get(phase):
                raise TraceError(f'{source}:{start}: unknown phase or wrong field count')
            expected = 13 + count
        if expected is not None and len(pending) > expected:
            raise TraceError(f'{source}:{start}: excess payload')
        if expected is not None and len(pending) == expected:
            integers = [_integer(w, f'{source}:{start}') for w in pending[13:]]
            if any(v < -(1 << 31) or v >= (1 << 31) for v in integers):
                raise TraceError(f'{source}:{start}: transfer word outside signed int32')
            raw = np.asarray(integers, dtype=np.int32)
            values = raw.view(np.float32)
            if not np.isfinite(values).all():
                raise TraceError(f'{source}:{start}: nonfinite transfer word')
            yield header, raw, values
            pending, expected = [], None
    if pending:
        raise TraceError(f'{source}:{start}: truncated record')


def check_schema(path):
    if sha256(path) != SCHEMA_SHA256:
        raise TraceError('CP03 schema differs from the pinned native schema')


class ProcessAccumulator:
    """Validate actual records against owners and retain dense diagnostic data.

    owners maps (step,i,j,k) to (rank,call_id); loops is the independently
    validated number of microphysics loops for this capture. Surface absence is
    represented by its mask, never filled with a numerical zero observation.
    """
    def __init__(self, cells, steps, levels, loops, owners):
        self.cells = tuple(cells)
        if len(set(self.cells)) != len(self.cells) or not self.cells:
            raise TraceError('selected cells must be nonempty and unique')
        self.cell_index = {cell: n for n, cell in enumerate(self.cells)}
        self.steps, self.levels, self.loops, self.owners = steps, levels, loops, owners
        if min(steps, levels, loops) < 1:
            raise TraceError('invalid dimensions')
        shape = (steps, loops, levels, len(cells))
        self.shape = shape
        self.mstep = np.zeros(shape, dtype=np.int32)
        # One word per 64 actual sedimentation substeps; grows as needed.
        self.bits = np.zeros((2, 1, *shape), dtype=np.uint64)
        self.sed_sum = np.zeros((2, *shape, 16), dtype=np.float64)
        self.sed_pending = np.zeros(shape, dtype=np.int32)
        self.sed_pre_fall = np.zeros((*shape, 5), dtype=np.float32)
        self.final = np.full((2, *shape, 11), np.nan, dtype=np.float32)
        self.final_mask = np.zeros((2, *shape), dtype=bool)
        self.surface = np.full((2, steps, loops, len(cells), 12), np.nan, dtype=np.float32)
        self.surface_mask = np.zeros((2, steps, loops, len(cells)), dtype=bool)
        self.counts = {p: 0 for p in FIELD_COUNTS}

    def add(self, header, values, file_rank=None):
        phase, rank, call, step, loop, loops, i, j, k, substep, mstep, count = header
        if phase not in FIELD_COUNTS or count != FIELD_COUNTS[phase] or len(values) != count:
            raise TraceError('invalid phase or field count')
        if not np.isfinite(values).all():
            raise TraceError('nonfinite value')
        if file_rank is not None and rank != file_rank:
            raise TraceError('record rank differs from filename')
        if loops != self.loops or not (1 <= step <= self.steps and 1 <= loop <= loops and 1 <= k <= self.levels):
            raise TraceError('step, loop or level outside capture')
        ci = self.cell_index.get((i, j))
        if ci is None or self.owners.get((step, i, j, k)) != (rank, call):
            raise TraceError('record is not owned by its rank/call core')
        ix = (step - 1, loop - 1, k - 1, ci)
        if phase in (1, 2):
            if not (1 <= substep <= mstep):
                raise TraceError('invalid sedimentation substep')
            old = int(self.mstep[ix])
            if old and old != mstep:
                raise TraceError('inconsistent sedimentation mstep')
            self.mstep[ix] = mstep
            word, offset = divmod(substep - 1, 64)
            if word >= self.bits.shape[1]:
                extra = np.zeros((2, word + 1 - self.bits.shape[1], *self.shape), dtype=np.uint64)
                self.bits = np.concatenate((self.bits, extra), axis=1)
            bit = np.uint64(1) << np.uint64(offset)
            bix = (phase - 1, word, *ix)
            if self.bits[bix] & bit:
                raise TraceError('duplicate sedimentation phase/substep')
            self.bits[bix] |= bit
            if phase == 1:
                if self.sed_pending[ix]:
                    raise TraceError('sedimentation PRE before previous POST')
                self.sed_pending[ix] = substep
                self.sed_pre_fall[ix] = values[16:21]
            else:
                if self.sed_pending[ix] != substep:
                    raise TraceError('sedimentation POST lacks matching PRE')
                expected_fall = np.float32(self.sed_pre_fall[ix] + values[21:26])
                if not np.array_equal(expected_fall, values[16:21]):
                    raise TraceError('sedimentation fall accumulation differs from source arithmetic')
                self.sed_pending[ix] = 0
            self.sed_sum[(phase - 1, *ix)] += values[:16].astype(np.float64)
        elif phase in (3, 4):
            if k != 1 or substep != 0 or mstep != 0 or values[4] <= 0:
                raise TraceError('invalid conditional surface record')
            six = (phase - 3, step - 1, loop - 1, ci)
            if self.surface_mask[six]:
                raise TraceError('duplicate surface phase')
            self.surface_mask[six] = True
            self.surface[six] = values
        else:
            if substep != 0 or mstep != 0:
                raise TraceError('invalid final condensation key')
            fix = (phase - 5, *ix)
            if self.final_mask[fix]:
                raise TraceError('duplicate final condensation phase')
            self.final_mask[fix] = True
            self.final[fix] = values
        self.counts[phase] += 1

    def finish(self):
        if not self.final_mask.all():
            raise TraceError('incomplete final condensation coverage')
        if not np.array_equal(self.surface_mask[0], self.surface_mask[1]):
            raise TraceError('incomplete conditional surface phase pair')
        if self.sed_pending.any():
            raise TraceError('incomplete sedimentation PRE/POST pair')
        pre, post = self.surface
        mask = self.surface_mask[0]
        if not np.array_equal(pre[mask, :10], post[mask, :10]):
            raise TraceError('surface phase inputs changed across update')
        pre, post = self.final
        if not np.array_equal(pre[..., [3, 7, 8, 9, 10]], post[..., [3, 7, 8, 9, 10]]):
            raise TraceError('final condensation inputs changed across update')
        if not (self.mstep > 0).all():
            raise TraceError('missing sedimentation coverage')
        if not np.all(self.mstep == self.mstep[:, :, :1, :]):
            raise TraceError('sedimentation mstep varies within a column')
        for wi in range(self.bits.shape[1]):
            remaining = np.clip(self.mstep.astype(np.int64) - wi * 64, 0, 64)
            # Avoid shifting by 64 (undefined/wrapped for uint64).
            expected = np.zeros(self.shape, dtype=np.uint64)
            full = remaining == 64
            partial = (remaining > 0) & ~full
            expected[full] = np.iinfo(np.uint64).max
            expected[partial] = (np.left_shift(np.uint64(1), remaining[partial].astype(np.uint64)) - np.uint64(1))
            if not (np.array_equal(self.bits[0, wi], expected) and np.array_equal(self.bits[1, wi], expected)):
                raise TraceError('missing or incomplete sedimentation phase/substep')
        return {'counts': self.counts, 'sedimentation_delta': self.sed_sum[1] - self.sed_sum[0],
                'final': self.final, 'surface': self.surface, 'surface_mask': self.surface_mask[0],
                'mstep': self.mstep}


def arithmetic_residuals(result):
    """Reconstruct captured source operations with REAL32 rounding per operation."""
    before, after = result['final']
    q, t, qc, _, _, _, _, pcond, dt, xl, cpm = np.moveaxis(before, -1, 0)
    q_expected = np.float32(q - np.float32(pcond * dt))
    qc_expected = np.maximum(np.float32(qc + np.float32(pcond * dt)), np.float32(0))
    t_expected = np.float32(t + np.float32(np.float32(np.float32(pcond * xl) / cpm) * dt))
    surface_pre, surface_post = result['surface']
    valid = result['surface_mask']
    surf = surface_pre[valid]
    actual_surf = surface_post[valid]
    increment = np.float32(np.float32(np.float32(np.float32(surf[:, 4] * surf[:, 7]) / surf[:, 8]) * surf[:, 9]) * np.float32(1000))
    return {
        'cond_q': np.float32(after[..., 0] - q_expected),
        'cond_qc': np.float32(after[..., 2] - qc_expected),
        'cond_t': np.float32(after[..., 1] - t_expected),
        'surface_rain': np.float32(actual_surf[:, 10] - np.float32(surf[:, 10] + increment)),
        'surface_rainncv': np.float32(actual_surf[:, 11] - np.float32(surf[:, 11] + increment)),
    }


class LegacyAccumulator:
    """Dense per-phase legacy trace, preserving conditional phase absence."""
    REQUIRED = frozenset(('ENTRY_RAW', 'ENTRY_CLAMPED', 'SATURATION', 'SATDT',
                          'PROCESS_RATES', 'PRE_UPDATE', 'LATENT_INPUT', 'POST_STEP',
                          'SURFACE_RETURN'))

    def __init__(self, cells, steps, levels, loops, owners):
        import importlib.util
        spec = importlib.util.spec_from_file_location('cp02_b1_process_trace', Path(__file__).with_name('cp02_b1_process_trace.py'))
        legacy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(legacy)
        self.legacy = legacy
        self.cells = tuple(cells)
        self.cell_index = {cell: n for n, cell in enumerate(cells)}
        self.steps, self.levels, self.loops, self.owners = steps, levels, loops, owners
        self.shape = (steps, loops, levels, len(cells))
        self.arrays = {}
        self.masks = {}
        for phase, (keys, fields, _) in legacy.SCHEMAS.items():
            surface = 'k' not in keys
            shape = (steps, len(cells)) if surface else self.shape
            # Mixed REAL32/REAL64 PREVP_FORMULA needs float64 to retain n0r.
            dtype = np.float64 if phase == 'PREVP_FORMULA' else np.float32
            self.arrays[phase] = np.full((*shape, len(fields)), np.nan, dtype=dtype)
            self.masks[phase] = np.zeros(shape, dtype=bool)

    def add(self, record, file_rank=None):
        phase = record['phase']
        data = dict(zip(record['key_fields'], record['key']))
        rank, call, step = data['rank'], data['call_id'], data['itimestep']
        i, j = data['i'], data['j']
        ci = self.cell_index.get((i, j))
        k = data.get('k', 1)
        if file_rank is not None and rank != file_rank:
            raise TraceError('legacy record rank differs from filename')
        if not (1 <= step <= self.steps and 1 <= k <= self.levels) or ci is None:
            raise TraceError('legacy record outside selected capture')
        if self.owners.get((step, i, j, k)) != (rank, call):
            raise TraceError('legacy record is not owned by its rank/call core')
        if 'k' not in data:
            ix = (step - 1, ci)
        else:
            loop = data['loop']
            if phase in ('ENTRY_RAW', 'ENTRY_CLAMPED'):
                if loop != 0:
                    raise TraceError('entry phase has nonzero loop')
                loop = 1
            if not 1 <= loop <= self.loops:
                raise TraceError('legacy loop outside selected capture')
            ix = (step - 1, loop - 1, k - 1, ci)
        if self.masks[phase][ix]:
            raise TraceError(f'duplicate legacy {phase} record')
        self.masks[phase][ix] = True
        self.arrays[phase][ix] = tuple(record['values'].values())

    def finish(self):
        for phase in self.REQUIRED:
            mask = self.masks[phase]
            # Entry occurs outside the loop and is indexed in the first slot.
            if phase in ('ENTRY_RAW', 'ENTRY_CLAMPED'):
                mask = mask[:, 0]
            if not mask.all():
                raise TraceError(f'incomplete legacy {phase} coverage')
        if not np.array_equal(self.masks['PREVP_FORMULA'], self.masks['PREVP_RAW']):
            raise TraceError('PREVP formula/raw conditional phases do not pair')
        for phase in ('PREVP_QR_CAP', 'PREVP_SAT_CAP'):
            if np.any(self.masks[phase] & ~self.masks['PREVP_RAW']):
                raise TraceError(f'{phase} lacks PREVP_RAW')
        return {'values': self.arrays, 'masks': self.masks,
                'counts': {key: int(mask.sum()) for key, mask in self.masks.items()}}


def read_owners(paths, cells, steps, levels):
    """Derive selected core ownership from the actual per-rank call records."""
    import re
    owners = {}
    calls = {}
    for path in paths:
        match = re.fullmatch(r'state_calls_rank(\d+)\.txt', Path(path).name)
        if not match:
            raise TraceError(f'{path}: invalid call filename')
        file_rank = int(match.group(1))
        with Path(path).open(encoding='ascii') as stream:
            for number, line in enumerate(stream, 1):
                words = line.split()
                if len(words) != 21:
                    raise TraceError(f'{path}:{number}: invalid call field count')
                v = [_integer(w, f'{path}:{number}') for w in words]
                step, rank, call = v[:3]
                ids, ide, jds, jde, kds, kde = v[3:9]
                ims, ime, jms, jme, kms, kme = v[9:15]
                its, ite, jts, jte, kts, kte = v[15:21]
                if not (rank == file_rank and call > 0 and 1 <= step <= steps and
                        ids <= its <= ite < ide and ims <= its <= ite <= ime and
                        jds <= jts <= jte < jde and jms <= jts <= jte <= jme and
                        kds <= kts <= kte < kde and kms <= kts <= kte <= kme and
                        1 <= kts <= kte <= levels):
                    raise TraceError(f'{path}:{number}: invalid rank/call/tile bounds')
                key = (step, rank, call)
                if key in calls:
                    raise TraceError(f'{path}:{number}: duplicate call')
                calls[key] = tuple(v[15:21])
                for i, j in cells:
                    if its <= i <= ite and jts <= j <= jte:
                        for k in range(kts, kte + 1):
                            cell_key = (step, i, j, k)
                            if cell_key in owners:
                                raise TraceError(f'{path}:{number}: overlapping selected cores')
                            owners[cell_key] = (rank, call)
    if len(owners) != steps * levels * len(cells):
        raise TraceError('call inventory lacks complete selected core coverage')
    return owners, calls


def read_selected_state(paths, stage, cells, steps, levels, owners, calls):
    """Read complete CBSP0001 selected state; preserve original REAL32 words."""
    import re
    if stage not in (6, 7):
        raise TraceError('unsupported selected state stage')
    cell_index = {cell: n for n, cell in enumerate(cells)}
    shape = (steps, levels, len(cells))
    values = np.full((*shape, 14), np.nan, dtype=np.float32)
    present = np.zeros(shape, dtype=bool)
    header_format = struct.Struct('>8s15i')
    row_type = np.dtype([('i', '>i4'), ('j', '>i4'), ('k', '>i4'), ('v', '>f4', (14,))])
    blocks = set()
    stage_name = {6: 'entry', 7: 'return'}[stage]
    for path in paths:
        match = re.fullmatch(rf'state_selected_{stage_name}_rank(\d+)\.bin', Path(path).name)
        if not match:
            raise TraceError(f'{path}: invalid selected-state filename')
        file_rank = int(match.group(1))
        with Path(path).open('rb') as stream:
            while raw := stream.read(header_format.size):
                if len(raw) != header_format.size:
                    raise TraceError(f'{path}: truncated block header')
                magic, sid, rank, call, step, ilo, ihi, jlo, jhi, klo, khi, istride, jstride, kstride, fields, count = header_format.unpack(raw)
                key = (step, rank, call)
                if (magic != b'CBSP0001' or sid != stage or rank != file_rank or
                    (ilo, ihi, jlo, jhi, klo, khi) != calls.get(key) or
                    (istride, jstride, kstride, fields) != (1, 1, 1, 14) or count < 0):
                    raise TraceError(f'{path}: invalid selected-state block header')
                # One block per selected call, even if it contains no rows.
                if key in blocks:
                    raise TraceError(f'{path}: duplicate selected-state block')
                blocks.add(key)
                data = stream.read(count * row_type.itemsize)
                if len(data) != count * row_type.itemsize:
                    raise TraceError(f'{path}: truncated selected-state payload')
                rows = np.frombuffer(data, dtype=row_type)
                if not np.isfinite(rows['v']).all():
                    raise TraceError(f'{path}: nonfinite selected-state payload')
                for row in rows:
                    i, j, k = int(row['i']), int(row['j']), int(row['k'])
                    ci = cell_index.get((i, j))
                    if ci is None or not 1 <= k <= levels or owners.get((step, i, j, k)) != (rank, call):
                        raise TraceError(f'{path}: selected-state row outside owning core')
                    ix = (step - 1, k - 1, ci)
                    if present[ix]:
                        raise TraceError(f'{path}: duplicate selected-state row')
                    present[ix] = True
                    values[ix] = row['v']
    if not present.all():
        raise TraceError('incomplete selected-state coverage')
    return values


def weighted_cells(values, corners):
    """Apply four pinned native-corner weights; last two axes are cell, field."""
    indices, weights = corners
    selected = np.take(values, indices, axis=-2).astype(np.float64)
    return np.einsum('...pcf,pc->...pf', selected, weights, optimize=True)


def call_ledger(b1_entry, b1_return, prior_entry, prior_return, corners):
    """Split paired state divergence into within- and between-call changes."""
    entry = weighted_cells(prior_entry.astype(np.float64) - b1_entry, corners)
    returned = weighted_cells(prior_return.astype(np.float64) - b1_return, corners)
    within = returned - entry
    between = entry[1:] - returned[:-1]
    total = returned[-1] - entry[0]
    sum_within = np.sum(within, axis=0, dtype=np.float64)
    sum_between = np.sum(between, axis=0, dtype=np.float64)
    residual = total - sum_within - sum_between
    # Include weighted operands as well as every summand; gamma_n conservatively
    # covers the four weighted products, reductions, differences and time sums.
    operand = sum(np.sum(weighted_cells(np.abs(x), corners), axis=0, dtype=np.float64)
                  for x in (b1_entry, b1_return, prior_entry, prior_return))
    magnitude = operand + np.sum(np.abs(within), axis=0) + np.sum(np.abs(between), axis=0) + np.abs(total)
    n = 8 * b1_entry.shape[0] + 32
    eps = np.finfo(np.float64).eps / 2
    gamma = n * eps / (1 - n * eps)
    bound = gamma * magnitude
    if np.any(np.abs(residual) > bound):
        raise TraceError('paired state ledger exceeds its floating-point bound')
    return {'entry_difference': entry, 'return_difference': returned,
            'within_call': within, 'between_call': between,
            'sum_within_call': sum_within, 'sum_between_call': sum_between,
            'total': total, 'residual': residual, 'roundoff_bound': bound}


def read_corners(path):
    import csv
    grouped = {}
    with Path(path).open(newline='', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            point = row['point_id']
            cell = (int(row['wrf_i_1based']), int(row['wrf_j_1based']))
            weight = float(row['weight'])
            if not math.isfinite(weight) or weight < 0:
                raise TraceError('invalid corner weight')
            grouped.setdefault(point, []).append((cell, weight, row['corner']))
    cells = sorted({cell for rows in grouped.values() for cell, _, _ in rows})
    if len(grouped) != 9 or len(cells) != 36:
        raise TraceError('expected nine points and 36 disjoint native corners')
    index = {cell: n for n, cell in enumerate(cells)}
    indices, weights = [], []
    for point, rows in grouped.items():
        if len(rows) != 4 or {r[2] for r in rows} != {'00', '01', '10', '11'}:
            raise TraceError(f'{point}: invalid corner set')
        if not math.isclose(sum(r[1] for r in rows), 1, rel_tol=0, abs_tol=1e-12):
            raise TraceError(f'{point}: weights do not sum to one')
        indices.append([index[r[0]] for r in rows])
        weights.append([r[1] for r in rows])
    return list(grouped), cells, (np.array(indices), np.array(weights))


def check_inventory(root, inventory):
    """Pin every exact trace/inventory input before decoding any one of them."""
    import re
    root = Path(root)
    patterns = ('state_calls_rank*.txt', 'state_selected_entry_rank*.bin',
                'state_selected_return_rank*.bin', 'cp03_rank*.bits', 'kdm6_trace_rank*.bits')
    actual = {path.name: path for pattern in patterns for path in root.glob(pattern)}
    if not actual or set(actual) != set(inventory):
        raise TraceError(f'{root}: input inventory differs from manifest')
    for name, digest in inventory.items():
        if not re.fullmatch('[0-9a-f]{64}', digest) or sha256(actual[name]) != digest:
            raise TraceError(f'{actual[name]}: input SHA-256 mismatch')
    for prefix, suffix in (('state_calls_rank', '.txt'), ('state_selected_entry_rank', '.bin'),
                           ('state_selected_return_rank', '.bin')):
        if {f'{prefix}{rank}{suffix}' for rank in range(8)} - set(actual):
            raise TraceError(f'{root}: missing one or more rank files for {prefix}')
    return actual


def load_arm(root, inventory, cells, steps=540, levels=39):
    import re
    files = check_inventory(root, inventory)
    by_pattern = lambda expression: sorted((path for name, path in files.items() if re.fullmatch(expression, name)), key=lambda p: p.name)
    owners, calls = read_owners(by_pattern(r'state_calls_rank\d+\.txt'), cells, steps, levels)
    selected_ranks = {rank for rank, _ in owners.values()}
    for prefix in ('cp03_rank', 'kdm6_trace_rank'):
        found = {int(re.fullmatch(prefix + r'(\d+)\.bits', name).group(1)) for name in files
                 if re.fullmatch(prefix + r'(\d+)\.bits', name)}
        if found != selected_ranks:
            raise TraceError(f'{root}: {prefix} rank coverage differs from selected owners')
    states = {}
    for stage, name in ((6, 'entry'), (7, 'return')):
        states[name] = read_selected_state(by_pattern(rf'state_selected_{name}_rank\d+\.bin'),
                                           stage, cells, steps, levels, owners, calls)
    cp03 = ProcessAccumulator(cells, steps, levels, 1, owners)
    for path in by_pattern(r'cp03_rank\d+\.bits'):
        rank = int(re.search(r'rank(\d+)', path.name).group(1))
        with path.open(encoding='ascii') as stream:
            for header, _, values in records(stream, str(path)):
                cp03.add(header, values, rank)
    process = cp03.finish()
    residuals = arithmetic_residuals(process)
    legacy = LegacyAccumulator(cells, steps, levels, 1, owners)
    for path in by_pattern(r'kdm6_trace_rank\d+\.bits'):
        rank = int(re.search(r'rank(\d+)', path.name).group(1))
        with path.open(encoding='ascii') as stream:
            for record in legacy.legacy.iter_fortran_records(stream, str(path)):
                legacy.add(record, rank)
    legacy_result = legacy.finish()
    entry = legacy_result['values']['ENTRY_RAW'][:, 0]
    for state_field, legacy_field in ((1, 0), (13, 1), (12, 2), (2, 3), (4, 4),
                                      (3, 5), (5, 6), (6, 7), (11, 14)):
        if not np.array_equal(states['entry'][..., state_field].view(np.uint32),
                              entry[..., legacy_field].view(np.uint32)):
            raise TraceError('selected state entry differs from legacy entry bits')
    check_number_conversion(states['entry'], entry, legacy_result['values']['ENTRY_CLAMPED'][:, 0])
    return {'state': states, 'process': process, 'legacy': legacy_result, 'residuals': residuals}


def check_number_conversion(state, raw, clamped):
    """Check wrapper per-airmass number fields and internal volume conversion."""
    density = state[..., 12]
    for state_field, legacy_field in ((8, 8), (9, 9), (7, 10), (10, 11)):
        converted = np.float32(state[..., state_field] * density)
        if not np.array_equal(converted.view(np.uint32), raw[..., legacy_field].view(np.uint32)):
            raise TraceError('number concentration density conversion differs from source')
    for field, lo, hi in ((8, 0., None), (9, 0., 1.e6), (10, 1.e8, 2.e10), (11, 0., None)):
        expected = np.maximum(raw[..., field], np.float32(lo))
        if hi is not None:
            expected = np.minimum(expected, np.float32(hi))
        if not np.array_equal(expected, clamped[..., field]):
            raise TraceError('number concentration clamp differs from source')
    if not np.array_equal(np.maximum(raw[..., 14], np.float32(0)), clamped[..., 14]):
        raise TraceError('graupel moment clamp differs from source')


def process_components(legacy):
    values = legacy['values']
    prevp = values['PROCESS_RATES'][..., 2]
    before = values['PRE_UPDATE']
    latent = values['LATENT_INPUT']
    after = values['POST_STEP']
    dt = before[..., 16]
    q_component = np.float32(-np.float32(prevp * dt))
    t_component = np.float32(np.float32(np.float32(latent[..., 4] * prevp) / latent[..., 2]) * dt)
    q_change = np.float32(after[..., 0] - before[..., 0])
    t_change = np.float32(after[..., 1] - before[..., 1])
    return np.stack((q_component, np.float32(q_change - q_component),
                     t_component, np.float32(t_change - t_component)), axis=-1)


SURFACE_REFERENCE_SHA256 = 'aaca56f222daa36e2fe5143d3b2f42759e2fd19449ecbe18c8455d215474f123'
CORNERS_SHA256 = 'aa5da1ef6cdb8773addb139ef4cc385d3ea9e2b9d490368f79fd77086bca4b1b'
STATE_FIELDS = ('TH', 'QV', 'QC', 'QR', 'QI', 'QS', 'QG', 'NN', 'NC', 'NI', 'NR', 'BG', 'DEN', 'TK')
RATE_FIELDS = ('praut', 'pracw', 'prevp', 'piacr', 'pgacr', 'psacr', 'pmulrs', 'pmulrg',
               'pseml', 'pgeml', 'psevp', 'pgevp', 'psdep', 'pgdep', 'pinud', 'pidep')


def check_surface_history(path, data, cells, steps):
    """Cross-bind KDM6 rain to RAINNC history at all full-hour boundaries."""
    import csv
    if steps != 540:
        raise TraceError('surface history requires the full three-hour capture')
    expected_cases = {'B1': 'IMPROVED_BG_FIXED', 'NR_PRIOR': 'B1_RAIN_NUMBER_PRIOR'}
    cell_index = {cell: n for n, cell in enumerate(cells)}
    seen = set()
    initial = {}
    with Path(path).open(newline='', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            case = row['case']
            arms = [arm for arm, name in expected_cases.items() if name == case]
            hour = int(row['valid_hour_utc'])
            cell = (int(row['i_1based']), int(row['j_1based']))
            if len(arms) != 1 or hour not in (12, 13, 14, 15) or cell not in cell_index:
                raise TraceError('surface reference contains unexpected case/hour/cell')
            arm = arms[0]
            key = (arm, hour, cell)
            if key in seen:
                raise TraceError('duplicate surface history reference')
            seen.add(key)
            try:
                word = bytes.fromhex(row['RAINNC_f32_le_hex'])
                if len(word) != 4:
                    raise ValueError
                value = struct.unpack('<f', word)[0]
            except (ValueError, struct.error) as exc:
                raise TraceError('invalid surface history transfer bits') from exc
            if not math.isfinite(value) or float(row['RAINNC_cumulative_mm']) != value:
                raise TraceError('surface history decimal/bit mismatch')
            if hour == 12:
                initial[(arm, cell)] = value
            else:
                actual = data[arm]['legacy']['values']['SURFACE_RETURN'][(hour - 12) * 180 - 1, cell_index[cell], 1]
                if struct.pack('<f', actual) != word:
                    raise TraceError(f'{arm}: KDM6 rain differs from history at {hour} UTC {cell}')
    if len(seen) != 2 * 4 * len(cells):
        raise TraceError('surface reference lacks complete case/hour/cell coverage')
    return {'records': len(seen), 'hourly_boundary_records': 2 * 3 * len(cells),
            'hourly_boundary_bitwise_equal': True,
            'initial_rainnc': {arm: [initial[(arm, cell)] for cell in cells] for arm in expected_cases}}


def write_profiles(path, points, rates, components, state):
    """Write compact point/lead/layer summaries and first numeric differences."""
    import csv
    quantities = [(name, rates[..., n]) for n, name in enumerate(RATE_FIELDS)]
    quantities += [(name, components[..., n]) for n, name in enumerate(
        ('prevp_qv_component', 'qv_other_residual', 'prevp_temperature_component', 'temperature_other_residual'))]
    quantities += [(f'{name}_return', state[..., STATE_FIELDS.index(name)]) for name in ('QV', 'QR', 'TK')]
    with Path(path).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(('point_id', 'lead_hour', 'level_1based', 'quantity', 'mean_difference',
                         'maximum_absolute_difference', 'first_nonzero_step'))
        for name, array in quantities:
            # All arrays are timestep, level, point after removing singleton loop.
            for start in range(0, array.shape[0], 180):
                block = array[start:start + 180]
                for k in range(block.shape[1]):
                    for p, point in enumerate(points):
                        values = block[:, k, p]
                        first = np.flatnonzero(values != 0)
                        writer.writerow((point, start // 180 + 1, k + 1, name,
                                         float(np.mean(values, dtype=np.float64)),
                                         float(np.max(np.abs(values))),
                                         int(first[0] + start + 1) if first.size else ''))


def write_first_native_differences(path, points, cells, corners, b1, prior):
    """First bitwise and numeric divergence, retaining the actual corner."""
    import csv
    stages = (('entry', STATE_FIELDS, b1['state']['entry'], prior['state']['entry']),
              ('return', STATE_FIELDS, b1['state']['return'], prior['state']['return']),
              ('process_rate', RATE_FIELDS, b1['legacy']['values']['PROCESS_RATES'][:, 0],
               prior['legacy']['values']['PROCESS_RATES'][:, 0]))
    with Path(path).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(('point_id', 'stage', 'field', 'comparison', 'step_1based',
                         'seconds', 'level_1based', 'i_1based', 'j_1based', 'b1', 'nr_prior'))
        for stage, fields, left, right in stages:
            for point_index, point in enumerate(points):
                indices = corners[0][point_index]
                for field_index, field in enumerate(fields):
                    a = np.take(left[..., field_index], indices, axis=2)
                    b = np.take(right[..., field_index], indices, axis=2)
                    for comparison, mask in (('bitwise', a.view(np.uint32) != b.view(np.uint32)),
                                             ('numeric', a != b)):
                        found = np.argwhere(mask)
                        if not found.size:
                            writer.writerow((point, stage, field, comparison, '', '', '', '', '', '', ''))
                            continue
                        t, k, c = map(int, found[0])
                        i, j = cells[int(indices[c])]
                        writer.writerow((point, stage, field, comparison, t + 1, (t + 1) * 20,
                                         k + 1, i, j, float(a[t, k, c]), float(b[t, k, c])))


def _publish_new_directory(source, target):
    """Publish atomically, serializing concurrent publications of this target."""
    import fcntl
    import os
    lock = Path(target).parent / f'.{Path(target).name}.publish.lock'
    with lock.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        if os.path.lexists(target):
            raise FileExistsError(f'output already exists: {target}')
        os.rename(source, target)



def analyze(manifest_path, schema_path, corners_path, output_path, steps=540):
    import json
    import os
    import shutil
    import tempfile
    manifest_path, output_path = Path(manifest_path), Path(output_path)
    if os.path.lexists(output_path):
        raise TraceError('output already exists')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest_hash = sha256(manifest_path)
    if (manifest.get('format') != 'CP03_PAIR_INPUT_V1' or manifest.get('case_id') is None or
        manifest.get('physics') != 'FIX' or manifest.get('time_step_seconds') != 20 or
        manifest.get('steps') != steps or set(manifest.get('arms', {})) != {'B1', 'NR_PRIOR'}):
        raise TraceError('invalid paired case/physics/timing manifest')
    check_schema(schema_path)
    if sha256(corners_path) != CORNERS_SHA256:
        raise TraceError('corner map differs from final cohort pin')
    points, cells, corners = read_corners(corners_path)
    reference = manifest.get('surface_reference')
    if steps == 540 and (not isinstance(reference, dict) or reference.get('sha256') != SURFACE_REFERENCE_SHA256 or
                         sha256(reference['path']) != SURFACE_REFERENCE_SHA256):
        raise TraceError('missing or mismatched native surface reference pin')
    # Verify both inventories before opening any trace for analysis.
    source_files = {}
    for arm in ('B1', 'NR_PRIOR'):
        item = manifest['arms'][arm]
        paths = check_inventory(item['root'], item['files'])
        source_files[arm] = [{'path': str(path.resolve()), 'sha256': item['files'][name],
                              'bytes': path.stat().st_size} for name, path in sorted(paths.items())]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f'.{output_path.name}.', dir=output_path.parent))
    try:
        data = {arm: load_arm(manifest['arms'][arm]['root'], manifest['arms'][arm]['files'], cells, steps)
                for arm in ('B1', 'NR_PRIOR')}
        arithmetic = {}
        for arm, result in data.items():
            arithmetic[arm] = {name: float(np.max(np.abs(v))) if v.size else 0.0
                               for name, v in result['residuals'].items()}
            if any(not math.isfinite(v) or v != 0 for v in arithmetic[arm].values()):
                raise TraceError(f'{arm}: reconstructed source arithmetic residual is nonzero')
        surface_check = check_surface_history(reference['path'], data, cells, steps) if steps == 540 else None
        b1, prior = data['B1'], data['NR_PRIOR']
        ledger = call_ledger(b1['state']['entry'], b1['state']['return'],
                             prior['state']['entry'], prior['state']['return'], corners)
        rates = weighted_cells(prior['legacy']['values']['PROCESS_RATES'].astype(np.float64) -
                               b1['legacy']['values']['PROCESS_RATES'], corners)[:, 0]
        components = weighted_cells(process_components(prior['legacy']).astype(np.float64) -
                                    process_components(b1['legacy']), corners)[:, 0]
        state = ledger['return_difference']
        sediment = weighted_cells(prior['process']['sedimentation_delta'] -
                                   b1['process']['sedimentation_delta'], corners)[:, 0]
        surface_b1 = weighted_cells(b1['legacy']['values']['SURFACE_RETURN'], corners)
        surface_prior = weighted_cells(prior['legacy']['values']['SURFACE_RETURN'], corners)
        precipitation = weighted_cells(prior['legacy']['values']['SURFACE_RETURN'].astype(np.float64) -
                                        b1['legacy']['values']['SURFACE_RETURN'], corners)
        baseline = (np.asarray([surface_check['initial_rainnc']['B1'],
                                surface_check['initial_rainnc']['NR_PRIOR']], dtype=np.float32)
                    if surface_check else np.empty((2, 0), dtype=np.float32))
        np.savez_compressed(temp / 'point_history.npz', rates=rates, components=components,
                            sedimentation=sediment, surface_return=precipitation, surface_b1=surface_b1, surface_nr_prior=surface_prior,
                            surface_hour_boundary_steps=np.arange(180, steps + 1, 180),
                            surface_hour_b1=surface_b1[179::180], surface_hour_nr_prior=surface_prior[179::180],
                            surface_initial_rainnc_native=baseline,
                            surface_return_fields=np.asarray(('rainncv', 'rain', 'sr')),
                            **ledger,
                            points=np.asarray(points), cells=np.asarray(cells),
                            corner_indices=corners[0], corner_weights=corners[1],
                            state_fields=np.asarray(STATE_FIELDS), rate_fields=np.asarray(RATE_FIELDS),
                            sedimentation_fields=np.asarray(('q', 't', 'qci1', 'qci2', 'qrs1', 'qrs2',
                                                             'qrs3', 'nrs1', 'den', 'dend', 'delz',
                                                             'dtcld', 'brs', 'nci1', 'nci2', 'nci3')),
                            component_fields=np.asarray(('prevp_qv_component', 'qv_other_residual',
                                                         'prevp_temperature_component', 'temperature_other_residual')))
        write_profiles(temp / 'point_lead_layer.csv', points, rates, components, state)
        write_first_native_differences(temp / 'first_native_differences.csv', points, cells, corners, b1, prior)
        for arm, result in data.items():
            legacy, process = result['legacy'], result['process']
            raw = {'entry': result['state']['entry'], 'return': result['state']['return'],
                   'sedimentation_delta': process['sedimentation_delta'], 'mstep': process['mstep'],
                   'final_cond': process['final'], 'surface_conditional': process['surface'],
                   'surface_conditional_mask': process['surface_mask']}
            for name in ('ENTRY_RAW', 'ENTRY_CLAMPED', 'SATURATION', 'SATDT',
                         'PREVP_FORMULA', 'PREVP_RAW', 'PREVP_QR_CAP', 'PREVP_SAT_CAP',
                         'PROCESS_RATES', 'PRE_UPDATE', 'LATENT_INPUT', 'POST_STEP', 'SURFACE_RETURN'):
                raw[name] = legacy['values'][name]
                raw[name + '_mask'] = legacy['masks'][name]
            np.savez_compressed(temp / f'selected_{arm}.npz', **raw)
        for arm in ('B1', 'NR_PRIOR'):
            check_inventory(manifest['arms'][arm]['root'], manifest['arms'][arm]['files'])
        if sha256(manifest_path) != manifest_hash or sha256(corners_path) != CORNERS_SHA256:
            raise TraceError('input manifest or corners changed during analysis')
        check_schema(schema_path)
        if steps == 540 and sha256(reference['path']) != reference['sha256']:
            raise TraceError('surface reference changed during analysis')
        receipt = {'status': 'PASS_FULL_CAPTURE' if steps == 540 else 'PASS_FIXTURE_ONLY',
                   'format': 'CP03_PAIR_ANALYSIS_V1', 'case_id': manifest['case_id'],
                   'physics': 'FIX', 'steps': steps, 'time_step_seconds': 20,
                   'levels': 39, 'points': points, 'native_cells': len(cells),
                   'schema_sha256': SCHEMA_SHA256, 'corners_sha256': CORNERS_SHA256,
                   'input_manifest_sha256': manifest_hash, 'input_manifest_path': str(manifest_path.resolve()), 'source_files': source_files,
                   'surface_reference': reference, 'surface_history_check': surface_check,
                   'phase_counts': {arm: {'cp03': data[arm]['process']['counts'],
                                          'legacy': data[arm]['legacy']['counts']} for arm in data},
                   'source_arithmetic_max_abs_residual': arithmetic,
                   'ledger_max_abs_residual': float(np.max(np.abs(ledger['residual']))),
                   'interpretation': 'Selected rain/snow/graupel sweep; conditional surface absence is unknown; between-call changes are not pure transport; no complete water budget.'}
        (temp / 'coverage_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
        _publish_new_directory(temp, output_path)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return receipt


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--schema', required=True, type=Path)
    parser.add_argument('--corners', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    receipt = analyze(args.manifest, args.schema, args.corners, args.output)
    print(f"{receipt['status']}: {receipt['steps']} steps, {receipt['native_cells']} cells")


if __name__ == '__main__':
    main()
