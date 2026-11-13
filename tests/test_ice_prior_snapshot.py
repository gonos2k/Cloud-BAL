"""Focused boundary checks for actual-style coherent snapshot assembly."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('snapshot_assembler', ROOT / 'tools/assemble_ice_prior_snapshot.py')
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


def identity(path):
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def write_json(path, value):
    path.write_text(json.dumps(value))


class SnapshotBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ice-snapshot-test.')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        verification = self.root / 'run.json'
        write_json(verification, {'status': 'attested'})
        self.context = {'schema': 'coherent_ice_snapshot_context_v1', 'shape_zyx': [2, 4, 3],
                        'grid_sha256': 'a' * 64, 'mass_basis': 'dry_air', 'field_units': snapshot.FIELD_UNITS.copy(),
                        'executable_sha256': 'b' * 64,
                        'microphysics_source_sha256': 'c' * 64, 'capture_script_sha256': 'd' * 64,
                        'cycle_start': '2026-08-16_06:00:00', 'valid_time': '2026-08-16_12:00:00',
                        'target_step': 1080, 'time_step_seconds': 20,
                        'run_verification': [identity(verification)]}
        self.context_path = self.root / 'context.json'
        write_json(self.context_path, self.context)
        self.ranks = []
        for rank in range(8):
            i, j = rank % 2 + 1, rank // 2 + 1
            bounds = {'ids': 1, 'ide': 4, 'jds': 1, 'jde': 5, 'kds': 1, 'kde': 3,
                      'ims': 1, 'ime': 3, 'jms': 1, 'jme': 4, 'kms': 1, 'kme': 2,
                      'its': i, 'ite': i, 'jts': j, 'jte': j, 'kts': 1, 'kte': 2}
            chunks = [np.array([100 * rank + n + 1, 100 * rank + n + 2], dtype='<f4').tobytes()
                      for n in range(9)]
            raw = b''.join(chunks)
            binary = self.root / f'rank{rank}.bin'
            binary.write_bytes(raw)
            metadata = {'rank': rank, 'target_step': 1080, 'event': 'kdm_wrapper_return',
                        'dtype': 'little-endian IEEE-754 float32',
                        'field_order': 'field-major; each field ordered j,k,i with i contiguous',
                        'full_bounds_fortran_1based': bounds,
                        'processed_domain_intersection_fortran_1based': {'i': [i, i], 'j': [j, j], 'k': [1, 2]},
                        'cell_count': 2, 'binary_sha256': hashlib.sha256(raw).hexdigest(),
                        'fields': [{'name': name, 'argument_1based': arg, 'offset_bytes': n * 8,
                                    'bytes': 8, 'base': hex(4096 + n * 128),
                                    'sha256': hashlib.sha256(chunks[n]).hexdigest()}
                                   for n, (name, arg) in enumerate(snapshot.FIELDS)]}
            meta = self.root / f'rank{rank}.json'
            write_json(meta, metadata)
            self.ranks.append({'rank': rank, 'metadata': identity(meta), 'binary': identity(binary), 'compression': 'none'})
        self.manifest = {'schema': 'coherent_ice_snapshot_manifest_v1', 'context': identity(self.context_path), 'ranks': self.ranks}
        self.manifest_path = self.root / 'manifest.json'
        self.save_manifest()
        self.output = self.root / 'snapshot.npz'
        self.receipt = self.root / 'receipt.json'

    def save_manifest(self):
        write_json(self.manifest_path, self.manifest)

    def assemble(self):
        return snapshot.assemble(self.manifest_path, self.output, self.receipt)

    def test_assembles_rank_fields_without_inventing_uncovered_values(self):
        self.assemble()
        with np.load(self.output, allow_pickle=False) as data:
            self.assertEqual(set(data.files), {n for n, _ in snapshot.FIELDS} | {'coverage'})
            self.assertEqual(int(data['coverage'].sum()), 16)
            self.assertTrue(np.isnan(data['QI'][:, :, 2]).all())
            self.assertEqual(data['NI'][1, 2, 1], np.float32(504))
        details = json.loads(self.receipt.read_text())
        self.assertEqual((details['captured_cells'], details['uncovered_cells']), (16, 8))
        self.assertEqual(details['snapshot_sha256'], identity(self.output)['sha256'])

    def test_accepts_hash_bound_gzip_without_changing_raw_identity(self):
        rank = self.ranks[0]
        original = Path(rank['binary']['path'])
        compressed = self.root / 'rank0.gz'
        compressed.write_bytes(gzip.compress(original.read_bytes(), mtime=0))
        rank['binary'] = identity(compressed)
        rank['compression'] = 'gzip'
        self.save_manifest()
        self.assemble()
        self.assertTrue(self.output.is_file())

    def test_relative_manifest_and_context_paths(self):
        for rank in self.ranks:
            for key in ('metadata', 'binary'):
                rank[key]['path'] = Path(rank[key]['path']).name
        self.context['run_verification'][0]['path'] = 'run.json'
        write_json(self.context_path, self.context)
        self.manifest['context'] = identity(self.context_path)
        self.manifest['context']['path'] = 'context.json'
        self.save_manifest()
        self.assemble()
        self.assertTrue(self.receipt.exists())

    def test_rejects_wrong_return_boundary_or_field_map(self):
        for key, value in [('event', 'kdm_wrapper_entry'), ('target_step', 1)]:
            meta_path = Path(self.ranks[0]['metadata']['path'])
            meta = json.loads(meta_path.read_text())
            before = meta[key]
            meta[key] = value
            write_json(meta_path, meta)
            self.ranks[0]['metadata'] = identity(meta_path)
            self.save_manifest()
            with self.assertRaises(ValueError):
                self.assemble()
            meta[key] = before
            write_json(meta_path, meta)
            self.ranks[0]['metadata'] = identity(meta_path)
        meta = json.loads(meta_path.read_text())
        meta['fields'][0]['argument_1based'] = 6
        write_json(meta_path, meta)
        self.ranks[0]['metadata'] = identity(meta_path)
        self.save_manifest()
        with self.assertRaises(ValueError):
            self.assemble()
        self.assertFalse(self.output.exists())

    def test_rejects_wrong_basis_and_units(self):
        for key, value in [('mass_basis', 'moist_air'),
                           ('field_units', {**snapshot.FIELD_UNITS, 'NI': 'm-3'})]:
            old = self.context[key]
            self.context[key] = value
            write_json(self.context_path, self.context)
            self.manifest['context'] = identity(self.context_path)
            self.save_manifest()
            with self.assertRaisesRegex(ValueError, 'basis and exact field-unit'):
                self.assemble()
            self.context[key] = old
        self.assertFalse(self.output.exists())

    def test_rejects_overlap_and_corrupt_rank_bytes(self):
        metadata = Path(self.ranks[1]['metadata']['path'])
        d = json.loads(metadata.read_text())
        d['full_bounds_fortran_1based']['its'] = d['full_bounds_fortran_1based']['ite'] = 1
        d['processed_domain_intersection_fortran_1based']['i'] = [1, 1]
        write_json(metadata, d)
        self.ranks[1]['metadata'] = identity(metadata)
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            self.assemble()
        Path(self.ranks[0]['binary']['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.assemble()
        self.assertFalse(self.receipt.exists())

    def test_refuses_overwrite_and_rechecks_inputs_before_publication(self):
        self.output.write_bytes(b'preserve')
        with self.assertRaisesRegex(ValueError, 'must be new'):
            self.assemble()
        self.assertEqual(self.output.read_bytes(), b'preserve')
        self.output.unlink()
        actual = snapshot.load_rank
        def mutate(*args):
            result = actual(*args)
            if args[0]['rank'] == 7:
                self.context_path.write_text('{}')
            return result
        with mock.patch.object(snapshot, 'load_rank', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                self.assemble()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.receipt.exists())


if __name__ == '__main__':
    unittest.main()
