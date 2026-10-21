import sys
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr96_column_closure import f32_bits, f32_from_bits, half_ulp, nearest_f32, parse_trace, reduce_rows


class LiquidStoreClosureTests(unittest.TestCase):
    def test_exact_midpoint_rounds_to_even(self):
        bits, value, distance = nearest_f32(Fraction(1) + Fraction(1, 2**24))
        self.assertEqual(bits, 0x3F800000)
        self.assertEqual(value, 1.0)
        self.assertEqual(distance, Fraction(1, 2**24))

    def test_binade_edge_uses_larger_half_spacing(self):
        self.assertEqual(half_ulp(0x3F800000), Fraction(1, 2**24))

    def test_full_evaporation_requires_exact_qc_clear_transfer(self):
        row = full_evaporation_row()
        result = reduce_rows([row], {1: 1.0})
        self.assertEqual(result["events_by_tag"], {"CONDFULL": 1})
        self.assertEqual(result["total_stored_minus_approved_kg"], 0.0)
        self.assertTrue(result["r32_rne_pass"])

        row["bits"][2] = 0xBC800000
        row["transfer"] = -0.015625
        corrupted = reduce_rows([row], {1: 1.0})
        self.assertFalse(corrupted["r32_rne_pass"])
        self.assertTrue(any(item.get("species") == "QC" for item in corrupted["r32_rne_mismatches"]))


def full_evaporation_row():
    import struct
    rate, dtcld, transfer = -0.0015625, 20.0, -0.03125
    q_before, qc_before, q_after, qc_after = 1.0, 0.03125, 1.03125, 0.0
    product = f32_from_bits(f32_bits(rate)) * f32_from_bits(f32_bits(dtcld))
    values = (rate, dtcld, transfer, product, q_before, qc_before,
              q_after, qc_after, 0.0, 0.0, 0.0)
    line = "".join(f"{v:24.16E}" for v in values)
    raw_bits = (rate, dtcld, transfer, q_before, qc_before, q_after, qc_after)
    prefix = "CONDFULL" + f"{117:8d}{141:8d}{1:8d}{1:8d}"
    prefix += "".join(f"{f32_bits(value):9X}" for value in raw_bits)
    return parse_trace_from_text(prefix + line)[0]


def parse_trace_from_text(line):
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "trace.raw"
        path.write_text(line + "\n")
        return parse_trace(path)


if __name__ == "__main__":
    unittest.main()
