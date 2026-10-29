import copy
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import cp02_xmm6_producer as producer


class ProducerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        capture = producer.EVIDENCE / 'captures/OFF'
        prepare = producer.EVIDENCE / 'runtime/prepare.json'
        _, _, cls.records = producer.read_new_stage(capture, 'OFF', prepare)
        selection = producer.validate_selection(ROOT / 'docs/evidence/cp02_kdm6_controls_20261029/selection.json')
        old_root = ROOT / 'docs/evidence/cp02_kdm6_controls_20261029'
        summaries = {row['arm']: row for row in producer.load_json(old_root / 'analysis/summary.json')['arms']}
        _, old = producer.read_prior_stage(old_root / 'captures/OFF', 'OFF', summaries)
        outer, _ = producer.validate_outer_continuity(cls.records, old, selection)
        cls.inner = producer.validate_inner_records(cls.records, producer.selected_targets(selection), outer)
        cls.preclamp = producer.prior.validate_events(cls.records, 'OFF')

    def test_observations_and_mutations(self):
        self.assertEqual(len(producer.validate_producers(self.records, 'OFF', self.inner, self.preclamp)), 2)
        for mode in ('missing', 'sequence', 'source', 'register', 'target', 'pc', 'frame', 'rhs', 'presum_frame'):
            with self.subTest(mode=mode):
                records = copy.deepcopy(self.records)
                events = next(r['producer_events'] for r in records if r['producer_events'])
                if mode == 'missing': events.pop()
                elif mode == 'sequence': events[0], events[1] = events[1], events[0]
                elif mode == 'source': events[0]['source']['raw_hex'] = '00000000'
                elif mode == 'register': events[0]['scalar_registers']['xmm6']['raw_hex'] = '00000000'
                elif mode == 'target': events[0]['inner_event_id'] += 1
                elif mode == 'pc': events[0]['pc_hex'] = '0x25f4498'
                elif mode == 'frame': events[0]['frame_rbx_raw_hex'] = '00' * 0x500
                elif mode == 'presum_frame':
                    record = next(r for r in records if r['producer_events'])
                    record['preclamp_events'][0]['frame_rbx_hex'] = '0x1'
                elif mode == 'rhs':
                    event = next(e for e in events if e['role'] == 'before_compare')
                    item = event['scalar_registers']['xmm3']
                    item.update(raw_hex='0000803f', value_f32=1.0, finite=True)
                    event['registers_at_breakpoint'] = re.sub(
                        r'(^zmm3\s+.*?v16_int32 = \{)0x[0-9a-f]+',
                        r'\g<1>0x3f800000', event['registers_at_breakpoint'], flags=re.MULTILINE)
                with self.assertRaises((ValueError, KeyError)):
                    producer.validate_producers(records, 'OFF', self.inner, self.preclamp)

    def test_receipt_filename_and_content_integrity(self):
        source = producer.EVIDENCE / 'captures/OFF'
        prepare = producer.EVIDENCE / 'runtime/prepare.json'
        for mode in ('missing', 'filename', 'hash', 'rank', 'maps_filename'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                capture = Path(tmp) / 'OFF'
                shutil.copytree(source, capture)
                receipt_file = capture / 'receipt.json'
                receipt = json.loads(receipt_file.read_text())
                item = receipt['captures'][0]
                path = capture / Path(item['path']).name
                if mode == 'missing': path.unlink()
                elif mode == 'filename':
                    new = path.with_name(path.name.replace('_pid', '_rank999_pid'))
                    path.rename(new)
                    item['path'] = str(new)
                elif mode == 'hash': path.write_bytes(path.read_bytes() + b'x')
                elif mode == 'rank': item['rank'] = '999'
                elif mode == 'maps_filename':
                    record = json.loads(gzip.decompress(path.read_bytes()))
                    old = capture / Path(record['proc_maps_file']).name
                    new = old.with_name(old.name.replace('_pid', '_rank999_pid'))
                    old.rename(new)
                    record['proc_maps_file'] = str(new)
                    raw = json.dumps(record).encode()
                    data = gzip.compress(raw)
                    path.write_bytes(data)
                    item.update(sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data),
                                uncompressed_sha256=hashlib.sha256(raw).hexdigest(), uncompressed_size_bytes=len(raw))
                receipt_file.write_text(json.dumps(receipt))
                with self.assertRaises((ValueError, OSError)):
                    producer.read_new_stage(capture, 'OFF', prepare)

    def test_default_cli_three_arms_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'analysis'
            cmd = [sys.executable, str(ROOT / 'tools/cp02_xmm6_producer.py'), '--output', str(output)]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            rows = (output / 'producer.csv').read_text().splitlines()
            self.assertEqual(len(rows), 7)
            summary = json.loads((output / 'summary.json').read_text())
            self.assertEqual([r['arm'] for r in summary['arms']], ['OFF', 'HYDRO', 'LIQUID'])
            manifest = (output / 'artifact_manifest.json').read_bytes()
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((output / 'artifact_manifest.json').read_bytes(), manifest)


if __name__ == '__main__':
    unittest.main()
