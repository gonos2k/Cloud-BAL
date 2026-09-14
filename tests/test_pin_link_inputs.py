#!/usr/bin/env python3
"""Reject final-link dependency drift and unsupported input objects."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pin_link_inputs import pin_inputs


class LinkInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.library = self.root / 'runtime archive.a'
        self.library.write_bytes(b'static runtime')
        self.map = self.root / 'link.map'
        self.manifest = self.root / 'inputs.sha256'
        self.map.write_text(f'LOAD {self.library}\nLOAD {self.library}\n')

    def test_exact_repeat_and_unique_dependency(self):
        pin_inputs(self.map, self.manifest)
        pin_inputs(self.map, self.manifest, verify=True)
        self.assertEqual(len(self.manifest.read_text().splitlines()), 1)
        with self.assertRaises(FileExistsError):
            pin_inputs(self.map, self.manifest)

    def test_changed_static_library_rejected(self):
        pin_inputs(self.map, self.manifest)
        self.library.write_bytes(b'changed runtime')
        with self.assertRaisesRegex(ValueError, 'set or bytes changed'):
            pin_inputs(self.map, self.manifest, verify=True)

    def test_dependency_addition_and_removal_rejected(self):
        other = self.root / 'startup.o'
        other.write_bytes(b'startup')
        pin_inputs(self.map, self.manifest)
        for text in (f'LOAD {self.library}\nLOAD {other}\n', f'LOAD {other}\n'):
            self.map.write_text(text)
            with self.assertRaisesRegex(ValueError, 'set or bytes changed'):
                pin_inputs(self.map, self.manifest, verify=True)

    def test_symlink_retarget_is_detected(self):
        alias = self.root / 'library.a'
        alias.symlink_to(self.library)
        self.map.write_text(f'LOAD {alias}\n')
        pin_inputs(self.map, self.manifest)
        self.assertTrue(self.manifest.read_text().endswith(f'  {self.library.resolve()}\n'))
        other = self.root / 'other.a'
        other.write_bytes(b'other runtime')
        alias.unlink()
        alias.symlink_to(other)
        with self.assertRaises(ValueError):
            pin_inputs(self.map, self.manifest, verify=True)

    def test_empty_relative_and_fifo_inputs_rejected(self):
        fifo = self.root / 'fifo'
        os.mkfifo(fifo)
        for text in ('not a link map\n', 'LOAD relative.a\n', f'LOAD {fifo}\n'):
            self.map.write_text(text)
            with self.assertRaises(ValueError):
                pin_inputs(self.map, self.manifest)


if __name__ == '__main__':
    unittest.main()
