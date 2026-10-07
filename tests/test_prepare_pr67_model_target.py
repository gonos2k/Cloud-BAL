from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from prepare_pr67_model_target import require_new_output


class RequireNewOutputTests(unittest.TestCase):
    def test_source_alias_is_rejected_without_changing_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.nc"
            source.write_bytes(b"source bytes")

            with self.assertRaises(FileExistsError):
                require_new_output(source, source)

            self.assertEqual(source.read_bytes(), b"source bytes")

    def test_existing_output_is_rejected_without_changing_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.nc"
            output = Path(temporary) / "output.nc"
            source.write_bytes(b"source bytes")
            output.write_bytes(b"existing control bytes")

            with self.assertRaises(FileExistsError):
                require_new_output(source, output)

            self.assertEqual(source.read_bytes(), b"source bytes")
            self.assertEqual(output.read_bytes(), b"existing control bytes")

    def test_broken_output_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.nc"
            output = Path(temporary) / "output.nc"
            source.write_bytes(b"source bytes")
            output.symlink_to(Path(temporary) / "missing.nc")

            with self.assertRaises(FileExistsError):
                require_new_output(source, output)

            self.assertTrue(output.is_symlink())
            self.assertEqual(source.read_bytes(), b"source bytes")

    def test_source_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            original = Path(temporary) / "original.nc"
            source = Path(temporary) / "source.nc"
            output = Path(temporary) / "output.nc"
            original.write_bytes(b"original bytes")
            source.symlink_to(original)

            with self.assertRaises(ValueError):
                require_new_output(source, output)

            self.assertFalse(output.exists())
            self.assertEqual(original.read_bytes(), b"original bytes")


if __name__ == "__main__":
    unittest.main()
