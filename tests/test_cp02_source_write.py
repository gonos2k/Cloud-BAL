import copy
import gzip
import hashlib
import json
import shutil
import subprocess
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import cp02_source_write as source


class SourceWriteTests(unittest.TestCase):
    def test_shared_event_chronology_and_call_ownership(self):
        inner = {'entry_records': {'P05_00': (None, {'event_id': 2}, None)}}
        event = {'target': 'P05_00', 'event_ordinal': 3, 'inner_call_id': 2}
        record = {'rank': '1', 'outer': {'entry': {'event_ordinal': 1, 'inner_call_id': None},
                                        'return': {'event_ordinal': 5, 'inner_call_id': None}},
                  'inner': [{'event_id': 2, 'inner_call_id': 2, 'event_ordinal': 2,
                             'return': {'event_ordinal': 4, 'inner_call_id': 2}}],
                  'write_events': [event], 'source_events': [], 'producer_events': [], 'preclamp_events': []}
        inner['entry_records']['P05_00'] = (None, record['inner'][0], None)
        source.validate_chronology([record], inner)
        for change in ('duplicate', 'gap', 'inner', 'rank'):
            item = copy.deepcopy(record)
            if change == 'duplicate': item['source_events'].append(copy.deepcopy(event))
            elif change == 'gap': item['write_events'][0]['event_ordinal'] = 6
            elif change == 'inner': item['write_events'][0]['inner_call_id'] = 3
            else: item['rank'] = '3'
            mutated_inner = {'entry_records': {'P05_00': (None, item['inner'][0], None)}}
            with self.subTest(change=change), self.assertRaises(ValueError):
                source.validate_chronology([item], mutated_inner)

    def test_canonical_cli_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'analysis'
            cmd = [sys.executable, str(ROOT / 'tools/cp02_source_write.py'), '--output', str(out)]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            self.assertEqual(len((out / 'source.csv').read_text().splitlines()), 7)
            original = (out / 'artifact_manifest.json').read_bytes()
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertEqual((out / 'artifact_manifest.json').read_bytes(), original)

    def test_mutated_capture_cli_rejects_without_output(self):
        original = source.EVIDENCE / 'captures'
        for mode in ('ordinal', 'call', 'address', 'operator', 'sequence', 'boundary', 'owner', 'frame_chain', 'access_value', 'watch_log'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / 'captures'; root.mkdir()
                shutil.copytree(original / 'OFF', root / 'OFF')
                for arm in ('HYDRO', 'LIQUID'):
                    (root / arm).symlink_to(original / arm, target_is_directory=True)
                receipt_path = root / 'OFF/receipt.json'
                receipt = json.loads(receipt_path.read_text())
                item = next(i for i in receipt['captures'] if str(i['rank']) == '1')
                path = root / 'OFF' / Path(item['path']).name
                record = json.loads(gzip.decompress(path.read_bytes()))
                events = record['source_events']
                if mode == 'ordinal': events[1]['event_ordinal'] = events[0]['event_ordinal']
                elif mode == 'call': events[1]['inner_call_id'] += 1
                elif mode == 'address': events[1]['address_hex'] = '0x1'
                elif mode == 'operator': next(e for e in events if e['role'] == 'before_min_29d')['role'] = 'before_max_97a'
                elif mode == 'sequence': events[1], events[2] = events[2], events[1]
                elif mode == 'boundary':
                    call = record['inner'][0]
                    call['event_ordinal'], events[1]['event_ordinal'] = events[1]['event_ordinal'], call['event_ordinal']
                elif mode == 'frame_chain':
                    event = next(e for e in events if e['role'] == 'before_min_29d')
                    frame = bytearray.fromhex(event['frame_rbx_raw_hex'])
                    struct.pack_into('<f', frame, 0x18, 1.0)
                    event['frame_rbx_raw_hex'] = frame.hex()
                    event['operands']['frame_0x18'].update(raw_hex='0000803f', value_f32=1.0)
                elif mode == 'watch_log':
                    log = root / 'OFF/gdb_rank1.txt'
                    log.write_text(log.read_text().replace('Hardware access (read/write) watchpoint', 'watchpoint'))
                elif mode == 'access_value':
                    event = [e for e in events if e['role'] == 'watch_access'][-1]
                    event['after'].update(raw_hex='0000803f', value_f32=1.0)
                else:
                    arm = events[0]; frame = bytearray.fromhex(arm['frame_rbx_raw_hex'])
                    for key, offset in (('source_base_hex', 0x728), ('qrs_base_hex', 0x1f0)):
                        value = int(arm[key], 16) + 4; arm[key] = hex(value)
                        struct.pack_into('<Q', frame, offset, value)
                    arm['frame_rbx_raw_hex'] = frame.hex()
                raw = json.dumps(record).encode(); data = gzip.compress(raw)
                path.write_bytes(data)
                item.update(sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data),
                            uncompressed_sha256=hashlib.sha256(raw).hexdigest(), uncompressed_size_bytes=len(raw))
                receipt_path.write_text(json.dumps(receipt))
                out = Path(tmp) / 'analysis'
                result = subprocess.run([sys.executable, str(ROOT / 'tools/cp02_source_write.py'),
                    '--capture-root', str(root), '--output', str(out)], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0, mode)
                self.assertFalse(out.exists(), mode)


if __name__ == '__main__':
    unittest.main()
