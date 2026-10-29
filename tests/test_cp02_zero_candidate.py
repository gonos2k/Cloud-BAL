import copy
import gzip
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import cp02_zero_candidate as candidate


class ZeroCandidateTests(unittest.TestCase):
    def test_sign_rule_and_negative_zero_bits(self):
        for raw, expected in (('00000000', 'min'), ('00000080', 'min'), ('000080b3', 'max')):
            value = struct.unpack('<f', bytes.fromhex(raw))[0]
            self.assertEqual(candidate.branch(value), expected)
            self.assertEqual(struct.pack('<f', value).hex(), raw)
        with self.assertRaises(ValueError): candidate.branch(float('nan'))

    def test_uninitialized_raw_can_be_nonfinite(self):
        self.assertTrue(candidate.math.isnan(candidate.raw32({'raw_hex': '0000c07f', 'value_f32': None, 'finite': False})))
        with self.assertRaises(ValueError): candidate.raw32({'raw_hex': '0000c07f', 'value_f32': 0.0, 'finite': False})

    def test_same_value_b_store_is_still_a_write(self):
        paths = (candidate.EVIDENCE / 'captures/OFF').glob('raw_*.json.gz')
        records = [json.loads(gzip.decompress(p.read_bytes())) for p in paths]
        record = next(r for r in records if str(r['rank']) == '1')
        first = next(e for e in record['b_events'] if e['role'] == 'watch_access')
        record['b_events'][0]['value'] = copy.deepcopy(first['after'])
        first['before'] = copy.deepcopy(first['after'])
        rows = candidate.validate_candidate(records, None, 'OFF')
        candidate.validate_b(records, rows)
        row = next(r for r in rows if r['rank'] == '1')
        self.assertEqual(row['b_last_write_before_candidate_pc'], '0x25e5c77')
        self.assertNotIn('0x25e5c7d', row['b_changed_access_pcs'])

    def test_cli_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'out'
            cmd = [sys.executable, str(ROOT / 'tools/cp02_zero_candidate.py'), '--output', str(out)]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            self.assertEqual(len((out / 'candidate.csv').read_text().splitlines()), 7)
            manifest = (out / 'artifact_manifest.json').read_bytes()
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertEqual((out / 'artifact_manifest.json').read_bytes(), manifest)

    def test_rehashed_mutations_fail_before_publication(self):
        original = candidate.EVIDENCE / 'captures'
        for mode in ('callback', 'call', 'sequence', 'pc', 'frame', 'raw64', 'double', 'b_access', 'b_writer', 'b_order'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / 'captures'; root.mkdir()
                shutil.copytree(original / 'OFF', root / 'OFF')
                for arm in ('HYDRO', 'LIQUID'):
                    (root / arm).symlink_to(original / arm, target_is_directory=True)
                receipt_path = root / 'OFF/receipt.json'; receipt = json.loads(receipt_path.read_text())
                item = next(i for i in receipt['captures'] if str(i['rank']) == '1')
                path = root / 'OFF' / Path(item['path']).name
                record = json.loads(gzip.decompress(path.read_bytes())); events = record['candidate_events']
                if mode == 'callback': events[1]['callback_ordinal'] = 0
                elif mode == 'call': events[1]['selected_inner_id'] += 1
                elif mode == 'sequence': events[1], events[2] = events[2], events[1]
                elif mode == 'pc': events[1]['pc_hex'] = '0x25ef8dc'
                elif mode == 'frame': events[1]['frame_rbx_raw_hex'] = '00' * 0x960
                elif mode == 'raw64': events[1]['scalar_registers']['xmm2']['raw_hex64'] = '000000000000f03f'
                elif mode == 'double': events[0]['operands']['array_0xe8'].update(raw_hex='000000000000f03f', value_f64=1.0)
                elif mode == 'b_writer': record['b_events'][1]['scalar_registers']['xmm1'].update(raw_hex='0000803f', value_f32=1.0)
                elif mode == 'b_order': record['b_events'][1], record['b_events'][2] = record['b_events'][2], record['b_events'][1]
                else: record['b_events'][-1]['after']['raw_hex'] = '0000803f'
                raw = json.dumps(record).encode(); data = gzip.compress(raw); path.write_bytes(data)
                item.update(sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data),
                            uncompressed_sha256=hashlib.sha256(raw).hexdigest(), uncompressed_size_bytes=len(raw))
                receipt_path.write_text(json.dumps(receipt))
                out = Path(tmp) / 'out'
                result = subprocess.run([sys.executable, str(ROOT / 'tools/cp02_zero_candidate.py'),
                                         '--capture-root', str(root), '--output', str(out)], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0, mode)
                self.assertFalse(out.exists(), mode)


if __name__ == '__main__': unittest.main()
