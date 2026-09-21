#!/usr/bin/env python3
"""Prepare actual inputs for pinned Intel read-only face/column diagnostics."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import numpy as np
from netCDF4 import Dataset
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import diagnose_qbal_boundary as boundary


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def surface(path, expected_epoch):
    with Dataset(path) as nc:
        nc.set_auto_maskandscale(False)
        if float(nc['valtime'][0]) != expected_epoch:
            raise ValueError('LSX valid time mismatch')
        var = nc['ps']
        if var.units.strip().lower() != 'pascals':
            raise ValueError('surface pressure units mismatch')
        value = np.asarray(var[:], dtype=np.float64).squeeze().T.copy()
        if not np.isfinite(value).all() or np.any(value == var._FillValue):
            raise ValueError('invalid LSX pressure')
        if np.any(value < var.valid_range[0]) or np.any(value > var.valid_range[1]):
            raise ValueError('LSX pressure outside declared range')
        nav = {key: np.asarray(nc[key][:]).tolist()
               for key in ('Nx', 'Ny', 'La1', 'Lo1', 'LoV', 'Latin1', 'Latin2', 'Dx', 'Dy')}
    return value, nav


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot', 'rows', 'lsx-before', 'lsx-center', 'lsx-after', 'output-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--center-epoch', type=int, required=True)
    args = parser.parse_args()
    sources = {name: getattr(args, name) for name in
               ('snapshot', 'rows', 'lsx_before', 'lsx_center', 'lsx_after')}
    hashes = {name: sha(path) for name, path in sources.items()}
    s = boundary.read_snapshot(args.snapshot)
    r = boundary.read_sparse_rows(args.rows)
    if r.dimensions != s.dimensions or not np.array_equal(s.dx, s.dy):
        raise ValueError('analytic weight requires same shape and dx=dy')
    if not np.array_equal(boundary._stored_active_mask(r), boundary._expected_active_mask(s)):
        raise ValueError('sparse mask differs from snapshot')
    neighbors = boundary._neighbor_indices(r)
    source, direction = np.where(r.coefficients > 0)
    target = neighbors[source, direction]
    if np.any(target < 0):
        raise ValueError('positive coefficient lacks incident row')
    graph = coo_matrix((np.ones(len(source)), (source, target)), shape=(len(r.ijk),)*2).tocsr()
    if (graph != graph.T).nnz:
        raise ValueError('asymmetric positive-edge adjacency')
    nc, labels = connected_components(graph, directed=False)
    label_grid = np.zeros(s.dimensions, dtype='<i4')
    label_grid[tuple((r.ijk-1).T)] = labels + 1
    times = [args.center_epoch-3600, args.center_epoch, args.center_epoch+3600]
    fields = [surface(path, epoch) for path, epoch in zip(
        (args.lsx_before, args.lsx_center, args.lsx_after), times)]
    if fields[0][1] != fields[1][1] or fields[2][1] != fields[1][1]:
        raise ValueError('LSX navigation differs between times')
    if any(a.shape != s.ps.shape for a, _ in fields) or not np.array_equal(fields[1][0], s.ps):
        raise ValueError('LSX center pressure differs from snapshot geometry')
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    prepared = out / 'prepared.bin'
    with prepared.open('wb') as stream:
        stream.write(np.asarray((*s.dimensions, nc), dtype='<i4').tobytes())
        for value in (s.p, s.dp, s.ps, s.dx, s.dy, s.u, s.v, s.w):
            stream.write(np.asarray(value, dtype='<f8').tobytes(order='F'))
        stream.write(label_grid.tobytes(order='F'))
        for value in (fields[0][0], fields[2][0]):
            stream.write(np.asarray(value, dtype='<f8').tobytes(order='F'))
        stream.write(np.asarray((times[0], times[2]), dtype='<i8').tobytes())
    repo = Path(__file__).resolve().parents[1]
    quote = shlex.quote
    script = '\n'.join([
        'set -euo pipefail', '. ' + quote(str(repo/'tests/intel_toolchain.sh')),
        'for level in O0 O2; do', 'mkdir "$level"',
        'if [[ $level == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
        'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi',
        '(cd "$level"', '"$CLOUD_BAL_FC" "${flags[@]}" -convert little_endian ' +
        ' '.join(quote(str(repo/'tests'/name)) for name in
                 ('qbal_physical_boundary.f90', 'diagnose_qbal_physical_boundary.f90')) + ' -o diagnose',
        './diagnose ../prepared.bin result.bin)', 'done'])
    (out/'run_intel.sh').write_text(script+'\n')
    with (out/'intel.log').open('w') as log:
        subprocess.run(['bash', str(out/'run_intel.sh')], cwd=out, check=True, stdout=log, stderr=subprocess.STDOUT)
    if (out/'O0/result.bin').read_bytes() != (out/'O2/result.bin').read_bytes():
        raise ValueError('Intel O0/O2 diagnostic outputs differ')
    nx, ny, nz = s.dimensions
    arrays = {}
    with (out/'O0/result.bin').open('rb') as stream:
        for name, dtype, shape in (
            ('omega_pressure', '<f8', (nz,)), ('omega_spacing', '<f8', (nz-1,)),
            ('mapping', '<i4', (nx, ny, 6)), ('partial_dp', '<f8', (nx, ny)),
            ('retrospective_tendency', '<f8', (nx, ny)), ('column_sums', '<f8', (nx, ny, 6)),
            ('component_face_counts', '<i4', (nc, 2)), ('component_abs_sensitivity', '<f8', (nc, 2))):
            count = int(np.prod(shape)); value = np.fromfile(stream, dtype=dtype, count=count)
            if len(value) != count:
                raise ValueError('truncated Fortran output')
            arrays[name] = value.reshape(shape, order='F')
        if stream.read(1):
            raise ValueError('trailing Fortran output')
    arrays['active_ijk'] = r.ijk
    arrays['active_component'] = labels
    # Retain explicit one-based stored faces and both active incident rows.
    # Zero row IDs mean outside the old active set, not an absent atmosphere.
    ii, jj = np.meshgrid(np.arange(1,nx), np.arange(1,ny), indexing='ij')
    row_ids = np.zeros(s.dimensions, dtype=np.int32)
    row_ids[tuple((r.ijk-1).T)] = np.arange(1,len(r.ijk)+1)
    faces = []; incidents = []; coefficients = []
    for plane in (1,0):  # nearest omega, then partial upper donor q
        kk = arrays['mapping'][1:,1:,plane]-1
        faces.append(np.stack((ii+1,jj+1,kk+1),axis=-1).reshape(-1,3))
        lo = row_ids[ii,jj,kk]
        hi = np.zeros_like(lo)
        inside = kk+1<nz
        hi[inside] = row_ids[ii[inside],jj[inside],kk[inside]+1]
        incidents.append(np.stack((lo,hi),axis=-1).reshape(-1,2))
        hh = s.dx[ii,jj].astype(float)
        coefficients.append(np.stack((np.where(lo>0,-hh,0),np.where(hi>0,hh,0)),axis=-1).reshape(-1,2))
    arrays['face_family_ijk'] = np.stack(faces)
    arrays['face_incident_active_row_ids'] = np.stack(incidents)
    arrays['face_incident_weighted_coefficients'] = np.stack(coefficients)
    np.savez_compressed(out/'arrays.npz', **arrays)
    m = arrays['mapping']; sums = arrays['column_sums']; active_columns = m[:,:,2]>0
    report = {
        'scope': 'READ_ONLY_DIAGNOSTIC / NOT_AUTHORIZED',
        'input_sha256': hashes, 'input_paths': {k: str(v.resolve()) for k,v in sources.items()},
        'source_sha256': {name: sha(repo/'tests'/name) for name in
                          ('qbal_physical_boundary.f90','diagnose_qbal_physical_boundary.f90',
                           'diagnose_qbal_physical_boundary.py','intel_toolchain.sh')},
        'dimensions': list(s.dimensions), 'active_rows': len(r.ijk), 'components': nc,
        'interior_columns': (nx-1)*(ny-1), 'valid_rows_without_support_filter': int(m[:,:,4].sum()),
        'valid_blocks': int(m[:,:,5].sum()),
        'columns_without_active_rows': int((~active_columns[1:,1:]).sum()),
        'first_active_offset_counts': {str(int(x)): int(np.sum((m[:,:,2]-m[:,:,0])[active_columns]==x))
                                       for x in np.unique((m[:,:,2]-m[:,:,0])[active_columns])},
        'surface_q_counts_interior': {str(int(x)): int(np.sum(m[1:,1:,0]==x)) for x in np.unique(m[1:,1:,0])},
        'partial_dp_range_Pa': [float(arrays['partial_dp'].min()), float(arrays['partial_dp'].max())],
        'omega_pressure_Pa': arrays['omega_pressure'].tolist(),
        'omega_spacing_Pa': arrays['omega_spacing'].tolist(), 'legacy_dp_Pa': s.dp[1:].tolist(),
        'top_active_rows': int(np.sum(r.ijk[:,2]==nz)),
        'max_abs_legacy_column_sum_Pa_s': float(np.max(np.abs(sums[:,:,0]))),
        'max_abs_telescope_error_Pa_s': float(np.max(np.abs(sums[:,:,3]))),
        'max_arithmetic_ratio': float(np.max(np.divide(abs(sums[:,:,3]),sums[:,:,4],
                                          out=np.zeros((nx,ny)),where=sums[:,:,4]>0))),
        'component_rows': np.bincount(labels).tolist(),
        'face_family_names': ['nearest_existing_omega_to_ps','partial_upper_omega_at_q'],
        'nonzero_component_face_counts': arrays['component_face_counts'].tolist(),
        'component_abs_sensitivity': arrays['component_abs_sensitivity'].tolist(),
        'retrospective_center_epoch': args.center_epoch,
        'retrospective_tendency_range_Pa_s': [float(arrays['retrospective_tendency'].min()),
                                              float(arrays['retrospective_tendency'].max())],
        'operational_availability': None, 'physical_surface_residual': None,
        'physical_column_residual': None, 'o0_o2_bitwise_equal': True,
        'limitations': ['nearest stored face and partial upper donor are different from the physical surface',
                        'legacy dp telescope is not the physical partial-layer column budget',
                        'wind frame/height, physical surface interpolation and lateral/top authority remain unbound',
                        'valid time is not delivery time; centered LSX tendency is retrospective only',
                        'component sensitivity uses the old D and unnormalized z=h*dp, not kg/s or approved E_s']}
    if hashes != {name: sha(path) for name,path in sources.items()}:
        raise ValueError('source input changed during diagnostic')
    report['output_sha256'] = {name: sha(out/name) for name in ('prepared.bin','O0/result.bin','O2/result.bin','arrays.npz')}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key: report[key] for key in ('active_rows','valid_rows_without_support_filter',
          'valid_blocks','nonzero_component_face_counts','max_abs_telescope_error_Pa_s','o0_o2_bitwise_equal')},indent=2))

if __name__ == '__main__':
    main()
