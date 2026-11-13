#!/usr/bin/env python3
"""Assemble hash-bound KDM6 wrapper-return records into an information snapshot."""
import argparse
from datetime import datetime, timedelta
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile

import numpy as np

FIELDS = (('QI', 5), ('QS', 6), ('NI', 10), ('DEN', 14), ('TH', 1),
          ('PII', 15), ('P', 16), ('QV', 2), ('DELZ', 17))
FIELD_UNITS = {'QI': 'kg kg-1 dryair', 'QS': 'kg kg-1 dryair',
               'QV': 'kg kg-1 dryair', 'NI': 'kg-1 dryair',
               'DEN': 'kg m-3 native KDM wrapper density',
               'TH': 'K dry potential temperature', 'PII': '1', 'P': 'Pa', 'DELZ': 'm'}
BOUNDS = ('ids', 'ide', 'jds', 'jde', 'kds', 'kde', 'ims', 'ime',
          'jms', 'jme', 'kms', 'kme', 'its', 'ite', 'jts', 'jte', 'kts', 'kte')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_file(identity, base):
    path = Path(identity['path'])
    if not path.is_absolute():
        path = base / path
    path = path.resolve(strict=True)
    if not path.is_file() or digest(path) != identity['sha256']:
        raise ValueError(f'file identity mismatch: {path}')
    return path


def validate_context(context, base):
    if context.get('schema') != 'coherent_ice_snapshot_context_v1':
        raise ValueError('unsupported snapshot context')
    if context.get('mass_basis') != 'dry_air' or context.get('field_units') != FIELD_UNITS:
        raise ValueError('explicit dry-air basis and exact field-unit definitions required')
    shape = context['shape_zyx']
    if (not isinstance(shape, list) or len(shape) != 3
            or any(type(n) is not int or n <= 0 for n in shape)):
        raise ValueError('invalid mass-grid shape')
    for key in ('grid_sha256', 'executable_sha256', 'microphysics_source_sha256', 'capture_script_sha256'):
        value = context[key]
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError(f'invalid {key}')
    step, seconds = context['target_step'], context['time_step_seconds']
    if type(step) is not int or step <= 0 or type(seconds) is not int or seconds <= 0:
        raise ValueError('positive integer step and interval required')
    start = datetime.strptime(context['cycle_start'], '%Y-%m-%d_%H:%M:%S')
    valid = datetime.strptime(context['valid_time'], '%Y-%m-%d_%H:%M:%S')
    if (start.strftime('%Y-%m-%d_%H:%M:%S') != context['cycle_start']
            or valid.strftime('%Y-%m-%d_%H:%M:%S') != context['valid_time']
            or start + timedelta(seconds=step * seconds) != valid):
        raise ValueError('cycle, nominal time and step do not agree')
    references = context['run_verification']
    if not isinstance(references, list) or not references:
        raise ValueError('linked run verification records required')
    for reference in references:
        checked_file(reference, base)
    return tuple(shape)


def rank_bounds(meta, shape):
    bounds = meta['full_bounds_fortran_1based']
    if set(bounds) != set(BOUNDS) or any(type(bounds[k]) is not int for k in BOUNDS):
        raise ValueError('invalid wrapper bounds')
    nz, ny, nx = shape
    for axis, count in (('i', nx), ('j', ny), ('k', nz)):
        ds, de, ms, me, ts, te = (bounds[axis + suffix] for suffix in ('ds', 'de', 'ms', 'me', 'ts', 'te'))
        if ds != 1 or de != count + 1 or ms > me or ts > te or ts < ms or te > me:
            raise ValueError(f'invalid {axis} domain/memory/tile bounds')
        expected = [max(ds, ts), min(de - 1, te)]
        actual = meta['processed_domain_intersection_fortran_1based'][axis]
        if (not isinstance(actual, list) or len(actual) != 2
                or any(type(value) is not int for value in actual)
                or expected[0] > expected[1] or actual != expected):
            raise ValueError(f'invalid {axis} processed intersection')
    return meta['processed_domain_intersection_fortran_1based']


def load_rank(item, context, shape, base):
    meta_path = checked_file(item['metadata'], base)
    data_path = checked_file(item['binary'], base)
    meta = json.loads(meta_path.read_text())
    if (type(meta['rank']) is not int or type(meta['target_step']) is not int
            or meta['rank'] != item['rank'] or meta['target_step'] != context['target_step']
            or meta['event'] != 'kdm_wrapper_return'
            or meta['dtype'] != 'little-endian IEEE-754 float32'
            or meta['field_order'] != 'field-major; each field ordered j,k,i with i contiguous'):
        raise ValueError('rank boundary or encoding mismatch')
    bounds = rank_bounds(meta, shape)
    (i0, i1), (j0, j1), (k0, k1) = (bounds[k] for k in ('i', 'j', 'k'))
    count = (i1 - i0 + 1) * (j1 - j0 + 1) * (k1 - k0 + 1)
    if (type(meta['cell_count']) is not int or meta['cell_count'] != count
            or any(type(f['argument_1based']) is not int for f in meta['fields'])
            or [(f['name'], f['argument_1based']) for f in meta['fields']] != list(FIELDS)):
        raise ValueError('rank cell count or field mapping mismatch')
    compression = item['compression']
    if compression == 'none':
        raw = data_path.read_bytes()
    elif compression == 'gzip':
        with gzip.open(data_path, 'rb') as stream:
            raw = stream.read()
    else:
        raise ValueError('unsupported rank compression')
    if len(raw) != count * len(FIELDS) * 4 or hashlib.sha256(raw).hexdigest() != meta['binary_sha256']:
        raise ValueError('rank raw binary length or hash mismatch')
    arrays = {}
    for index, field in enumerate(meta['fields']):
        offset = index * count * 4
        try:
            base_address = int(field['base'], 16)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('invalid captured field pointer') from exc
        if base_address <= 0:
            raise ValueError('invalid captured field pointer')
        chunk = raw[offset:offset + count * 4]
        if (type(field['offset_bytes']) is not int or type(field['bytes']) is not int
                or field['offset_bytes'] != offset or field['bytes'] != count * 4
                or hashlib.sha256(chunk).hexdigest() != field['sha256']):
            raise ValueError('rank field offset, length or hash mismatch')
        values = np.frombuffer(chunk, dtype='<f4').reshape((j1 - j0 + 1, k1 - k0 + 1, i1 - i0 + 1)).transpose(1, 0, 2)
        if not np.isfinite(values).all() or (field['name'] in ('DEN', 'PII', 'P', 'DELZ') and np.any(values <= 0)):
            raise ValueError('invalid captured field values')
        arrays[field['name']] = values
    return bounds, arrays


def publish(output, receipt, arrays, details):
    if output.resolve() == receipt.resolve() or output.parent.resolve() != receipt.parent.resolve():
        raise ValueError('output and receipt must have the same parent and distinct names')
    if output.exists() or receipt.exists():
        raise ValueError('output and receipt must be new')
    temporary = []
    created = []
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as stream:
            npz = Path(stream.name)
            temporary.append(npz)
            np.savez_compressed(stream, **arrays)
            stream.flush()
            os.fsync(stream.fileno())
        with np.load(npz, allow_pickle=False) as stored:
            if set(stored.files) != set(arrays):
                raise ValueError('snapshot readback keys mismatch')
            for name, value in arrays.items():
                readback = stored[name]
                if readback.shape != value.shape or readback.dtype != value.dtype or readback.tobytes() != value.tobytes():
                    raise ValueError(f'snapshot bitwise readback mismatch: {name}')
        details['snapshot_sha256'] = digest(npz)
        details['snapshot_file'] = output.name
        with tempfile.NamedTemporaryFile(mode='w', dir=output.parent, delete=False) as stream:
            rec = Path(stream.name)
            temporary.append(rec)
            json.dump(details, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        if json.loads(rec.read_text()) != details:
            raise ValueError('receipt readback mismatch')
        for staged, destination in ((rec, receipt), (npz, output)):
            os.link(staged, destination)
            created.append((destination, staged.stat()))
            descriptor = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except BaseException:
        for path, owned in reversed(created):
            try:
                current = path.lstat()
                if (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino):
                    path.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)


def assemble(manifest_path, output, receipt):
    manifest_path, output, receipt = map(Path, (manifest_path, output, receipt))
    manifest_hash = digest(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('schema') != 'coherent_ice_snapshot_manifest_v1':
        raise ValueError('unsupported snapshot manifest')
    context_path = checked_file(manifest['context'], manifest_path.resolve().parent)
    context = json.loads(context_path.read_text())
    shape = validate_context(context, context_path.parent)
    ranks = manifest['ranks']
    if (len(ranks) != 8 or any(type(x['rank']) is not int for x in ranks)
            or sorted(x['rank'] for x in ranks) != list(range(8))):
        raise ValueError('exactly ranks 0 through 7 are required')
    coverage = np.zeros(shape, dtype=bool)
    arrays = {name: np.full(shape, np.nan, dtype=np.float32) for name, _ in FIELDS}
    for rank in ranks:
        bounds, fields = load_rank(rank, context, shape, manifest_path.resolve().parent)
        (i0, i1), (j0, j1), (k0, k1) = (bounds[k] for k in ('i', 'j', 'k'))
        region = np.s_[k0 - 1:k1, j0 - 1:j1, i0 - 1:i1]
        if coverage[region].any():
            raise ValueError('overlapping rank coverage')
        coverage[region] = True
        for name, values in fields.items():
            arrays[name][region] = values
    arrays['coverage'] = coverage
    checked_file(manifest['context'], manifest_path.resolve().parent)
    for rank in ranks:
        checked_file(rank['metadata'], manifest_path.resolve().parent)
        checked_file(rank['binary'], manifest_path.resolve().parent)
    for reference in context['run_verification']:
        checked_file(reference, context_path.parent)
    if digest(manifest_path) != manifest_hash:
        raise ValueError('manifest changed during assembly')
    details = {
        'schema': 'coherent_ice_snapshot_receipt_v1', 'status': 'PASS',
        'manifest_sha256': manifest_hash, 'context': manifest['context'],
        'snapshot_context': context, 'ranks': ranks,
        'captured_cells': int(coverage.sum()), 'uncovered_cells': int((~coverage).sum()),
        'mass_basis': 'dry_air', 'field_units': FIELD_UNITS,
        'unit_scope': 'Source-contract and ABI interpretation, not an independent density-basis audit. TH times PII is a wrapper-boundary temperature reconstruction, not a claim about exact inner-KDM temperature.',
        'field_roles': {'returned_inout': ['QI', 'QS', 'NI', 'TH', 'QV'],
                        'same_call_inputs': ['DEN', 'PII', 'P', 'DELZ']},
        'scope': 'Numeric capture assembly and linked run records; not independent raw-NetCDF or clock audit, scientific authority, proposal or model initialization.',
        'limitations': 'Clock and independent NI scalar-base identity are not directly established by this artifact. Uncovered cells are invalid.',
    }
    publish(output, receipt, arrays, details)
    return details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('receipt', type=Path)
    args = parser.parse_args()
    print(json.dumps(assemble(args.manifest, args.output, args.receipt), indent=2))


if __name__ == '__main__':
    main()
