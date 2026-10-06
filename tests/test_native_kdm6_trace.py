import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from native_kdm6_trace import FIELDS_2D, FIELDS_3D, TraceError, summarize_pair


def write_dump(path: Path, stage: int, timestep: int = 1, *,
               bounds: tuple[int, ...] | None = None,
               params: tuple[float, ...] = (20.0, 1.0e8, 750.0, 50.0, 0.5),
               nonfinite_field: str | None = None,
               bad_field_name: bool = False,
               little_endian: bool = False) -> None:
    bounds = bounds or (1, 3, 1, 2, 1, 2, 1, 3, 1, 2, 1, 2, 1, 3, 1, 2, 1, 2)
    ny, nz, nx = 2, 2, 3
    endian = "<" if little_endian else ">"
    with path.open("wb") as stream:
        stream.write(b"KDM6TRC1")
        stream.write(struct.pack(endian + "20i", stage, timestep, *bounds))
        stream.write(struct.pack(endian + "5f", *params))
        for index, name in enumerate(FIELDS_3D):
            field_name = name.encode("ascii").ljust(8)
            stream.write(b"\xff" + field_name[1:] if bad_field_name and index == 0 else field_name)
            values = np.zeros((ny, nz, nx), dtype=np.dtype(endian + "f4"))
            if name == "TH":
                values.fill(300.0)
                if stage == 2:
                    values[0, 0, 0] = 302.0
            if name == "PII":
                values.fill(0.99)
            if name == "QC":
                values[0, 0, 0] = 0.1
            if name == "NC" and stage == 2:
                values[0, 0, 0] = 10.0
            if name == nonfinite_field:
                values[0, 0, 0] = np.nan
            stream.write(values.tobytes())
        for name in FIELDS_2D:
            stream.write(name.encode("ascii").ljust(8))
            stream.write(np.ones((ny, nx), dtype=np.dtype(endian + "f4")).tobytes())


class NativeKdm6TraceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pre = self.root / "pre.raw"
        self.post = self.root / "post.raw"
        write_dump(self.pre, 1)
        write_dump(self.post, 2)

    def tearDown(self):
        self.temp.cleanup()

    def test_summarizes_pair_gaps_and_changes(self):
        summary = summarize_pair(self.pre, self.post, expected_timestep=1)
        self.assertEqual(summary["pre_positive_mass_zero_moment"]["QC"]["positive_mass_zero_moment"], 1)
        self.assertEqual(summary["post_positive_mass_zero_moment"]["QC"]["positive_mass_zero_moment"], 0)
        self.assertEqual(summary["pre_to_post"]["NC"]["changed_cells"], 1)
        self.assertEqual(summary["pre_to_post"]["T_K"]["changed_cells"], 1)
        self.assertAlmostEqual(summary["pre_to_post"]["T_K"]["max_abs_change"], 1.98, places=4)
        self.assertEqual(summary["pre"]["active_shape_xyz"], [3, 2, 2])

    def test_rejects_truncated_payload(self):
        self.post.write_bytes(self.post.read_bytes()[:-4])
        with self.assertRaisesRegex(TraceError, "truncated XLAND data"):
            summarize_pair(self.pre, self.post)

    def test_rejects_bad_magic(self):
        self.pre.write_bytes(b"BADMAGIC" + self.pre.read_bytes()[8:])
        with self.assertRaisesRegex(TraceError, "wrong trace magic"):
            summarize_pair(self.pre, self.post)

    def test_rejects_non_ascii_field_name(self):
        write_dump(self.pre, 1, bad_field_name=True)
        with self.assertRaisesRegex(TraceError, "invalid ASCII field name"):
            summarize_pair(self.pre, self.post)

    def test_rejects_wrong_timestep(self):
        with self.assertRaisesRegex(TraceError, "wrong timestep"):
            summarize_pair(self.pre, self.post, expected_timestep=2)

    def test_rejects_pre_post_time_mismatch(self):
        write_dump(self.post, 2, timestep=2)
        with self.assertRaisesRegex(TraceError, "timestep mismatch"):
            summarize_pair(self.pre, self.post)

    def test_rejects_inverted_tile(self):
        bounds = (1, 3, 1, 2, 1, 2, 1, 3, 1, 2, 1, 2, 2, 1, 1, 2, 1, 2)
        write_dump(self.pre, 1, bounds=bounds)
        with self.assertRaisesRegex(TraceError, "inverted active i tile"):
            summarize_pair(self.pre, self.post)

    def test_rejects_little_endian_header(self):
        write_dump(self.pre, 1, little_endian=True)
        with self.assertRaises(TraceError):
            summarize_pair(self.pre, self.post)

    def test_rejects_nonpositive_call_parameter(self):
        write_dump(self.pre, 1, params=(0.0, 1.0e8, 750.0, 50.0, 0.5))
        with self.assertRaisesRegex(TraceError, "parameters must be finite and positive"):
            summarize_pair(self.pre, self.post)

    def test_retains_nonfinite_counts_with_json_safe_stats(self):
        write_dump(self.pre, 1, nonfinite_field="DEN")
        summary = summarize_pair(self.pre, self.post)
        self.assertEqual(summary["fields"]["DEN"]["pre"]["nonfinite"], 1)
        self.assertEqual(summary["fields"]["DEN"]["pre"]["min"], 0.0)
        self.assertNotIn("NaN", __import__("json").dumps(summary, allow_nan=False))


if __name__ == "__main__":
    unittest.main()
