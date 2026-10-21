from __future__ import annotations

import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr98_prepare_native_capture as capture  # noqa: E402
import pr98_native_capture as reader  # noqa: E402


class NativeCaptureTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        receipt = json.loads(capture.C1_RECEIPT.read_text())
        rows = {row["member"]: row for row in receipt["compiled_overrides"]}
        cls.module_source = Path(rows["module_em.o"]["source_path"]).read_text()
        cls.solve_source = Path(rows["solve_em.o"]["source_path"]).read_text()

    def test_observer_is_inserted_without_rewriting_source_calls(self) -> None:
        module, solve = capture.transform(self.module_source, self.solve_source)
        strip = lambda text: "\n".join(
            line.strip() for line in text.splitlines()
            if line.strip() and "CALL pr98_dump" not in line)
        normalize = lambda text: "\n".join(line.strip() for line in text.splitlines() if line.strip())
        self.assertEqual(strip(module), normalize(self.module_source))
        self.assertEqual(strip(solve), normalize(self.solve_source))
        for operator in ("advu", "advv", "advw", "pgrad", "coriolis", "curvature",
                         "hdifu", "hdifv", "hdifw", "vdifu", "vdifv"):
            self.assertIn(f"pr98_dump3('{operator}_", module)
        self.assertGreaterEqual(module.count("CALL pr98_dump2('geom_msfuy'"), 2)
        for match in re.finditer(r"(?im)^\s*CALL\s+(?:advect_u|advect_weno_u)\s*\(", module):
            preceding = "\n".join(module[:match.start()].splitlines()[-16:])
            self.assertIn("CALL pr98_dump2('geom_msfuy'", preceding)
        for label in ("dyn_ru_final", "dyn_rv_final", "dyn_rw_final"):
            self.assertIn(label, module)
        for label in ("assembled_ru_tend_in", "assembled_ru_tend_out", "assembled_rv_tend_in",
                      "assembled_rv_tend_out", "assembled_rw_tend_in", "assembled_rw_tend_out",
                      "mu_small_in", "mu_small_out", "mudf_small_out", "mu_large_in",
                      "mu_large_out", "dts_small"):
            self.assertIn(label, solve)

    def test_observer_limits_each_operator_and_tile_to_first_snapshot(self) -> None:
        self.assertIn("CHARACTER(160), SAVE :: seen(512)", capture.OBSERVER)
        self.assertIn("IF (TRIM(seen(q)) == TRIM(key)) RETURN", capture.OBSERVER)
        self.assertIn("ACCESS='stream',FORM='unformatted'", capture.OBSERVER)

    def test_stream_reader_respects_fortran_ijk_order_and_bounds(self) -> None:
        source = np.arange(2 * 3 * 4, dtype=">f4").reshape((2, 3, 4), order="F")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "capture.bin"
            path.write_bytes(struct.pack(">12i", 2, 3, 4, 6, 7, 10, 2, 3, 4, 6, 7, 10) +
                             source.tobytes(order="F"))
            metadata, actual = reader.read_capture(path, 3)
        self.assertEqual(metadata["shape_fortran"], [2, 3, 4])
        self.assertEqual(metadata["axes"], ["i", "k", "j"])
        np.testing.assert_array_equal(actual, source)
        self.assertEqual(actual[1, 2, 3], source[1, 2, 3])
        self.assertEqual(reader.summarize(actual)["n"], source.size)


if __name__ == "__main__":
    unittest.main()
