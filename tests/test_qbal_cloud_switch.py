#!/usr/bin/env python3
"""Protect the paired replay's single-input-change claim."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from diagnose_qbal_cloud_switch import paired_inputs


class PairedCloudInputTest(unittest.TestCase):
    def test_only_switch_may_change(self):
        with TemporaryDirectory() as tmp:
            on, off = Path(tmp)/'on', Path(tmp)/'off'
            for root, switch in ((on, 1), (off, 0)):
                (root/'static').mkdir(parents=True)
                (root/'lapsprd/lq3').mkdir(parents=True)
                (root/'replay').mkdir()
                (root/'static/moisture_switch.nl').write_text(f'CLOUD_SWITCH = {switch},\n')
                (root/'static/same.dat').write_bytes(b'common input')
                (root/'lapsprd/lq3/result').write_bytes(bytes([switch]))
                (root/'replay/previous.log').write_bytes(bytes([switch]))
            count, digest = paired_inputs(on, off)
            self.assertEqual(count, 2)
            self.assertEqual(len(digest), 64)
            (off/'static/same.dat').write_bytes(b'changed input')
            with self.assertRaisesRegex(ValueError, 'paired input differs'):
                paired_inputs(on, off)


if __name__ == '__main__':
    unittest.main()
