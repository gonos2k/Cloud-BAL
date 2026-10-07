from __future__ import annotations

import struct
import importlib.util
import unittest
from pathlib import Path

import numpy as np

_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "native_kdm6_call_geometry.py"
_SPEC = importlib.util.spec_from_file_location("native_kdm6_call_geometry", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
ARRAY_NAMES, STAGES, audit, parse_geometry = (
    _MODULE.ARRAY_NAMES, _MODULE.STAGES, _MODULE.audit, _MODULE.parse_geometry
)


BOUNDS = (0, 1, 0, 1, 1, 3, 0, 1, 0, 1, 1, 2)
EXTENTS = (2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 2, 2, 2, 2)
ARRAYS = {
    "mu1": np.full((2, 2), 100000.0),
    "mu2": np.full((2, 2), 90000.0),
    "mub": np.full((2, 2), 10000.0),
    "c1h": np.full((3,), -0.1),
    "c2h": np.full((3,), 0.0),
    "c3f": np.array([1.0, 0.5, 0.0]),
    "c4f": np.zeros((3,)),
    "dnw": np.full((3,), 0.5),
    "msftx": np.ones((2, 2)),
    "msfty": np.ones((2, 2)),
}


def encode_record(stage: str, *, arrays=None, bounds=BOUNDS, extents=EXTENTS,
                  timestep=1, dx=5000.0) -> bytes:
    arrays = ARRAYS if arrays is None else arrays
    data = bytearray(b"PR63GEO2")
    data.extend(stage.encode("ascii"))
    data.extend(struct.pack(">3i6f", timestep, 4, 2, 20.0, 20.0, dx, 5000.0, 9.81, 5000.0))
    data.extend(struct.pack(">12i", *bounds))
    data.extend(struct.pack(">15i", *extents))
    for name in ARRAY_NAMES:
        data.extend(np.asarray(arrays[name], dtype=">f4").tobytes(order="F"))
    return bytes(data)


def valid_capture() -> bytes:
    return encode_record(STAGES[0]) + encode_record(STAGES[1])


class NativeGeometryParserTests(unittest.TestCase):
    def test_valid_pair_parses_fixed_order_records(self):
        records = parse_geometry(valid_capture())
        self.assertEqual([r["stage"] for r in records], list(STAGES))
        self.assertEqual(records[0]["arrays"]["mu2"].shape, (2, 2))
        self.assertEqual(records[0]["timestep"], 1)

    def test_wrong_magic_is_rejected(self):
        raw = b"BADMAGIC" + valid_capture()[8:]
        with self.assertRaisesRegex(ValueError, "magic"):
            parse_geometry(raw)

    def test_truncated_array_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "truncated"):
            parse_geometry(valid_capture()[:-1])

    def test_nonfinite_array_is_rejected(self):
        arrays = {name: value.copy() for name, value in ARRAYS.items()}
        arrays["mu1"][0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            parse_geometry(encode_record(STAGES[0], arrays=arrays) + encode_record(STAGES[1]))

    def test_invalid_inclusive_bounds_are_rejected(self):
        bad_bounds = (0, 1, 0, 1, 1, 3, 0, 1, 0, 1, 1, 4)
        with self.assertRaisesRegex(ValueError, "outside memory"):
            parse_geometry(encode_record(STAGES[0], bounds=bad_bounds) + encode_record(STAGES[1]))

    def test_vertical_extent_mismatch_is_rejected(self):
        bad_extents = (*EXTENTS[:6], 2, *EXTENTS[7:])
        with self.assertRaisesRegex(ValueError, "vertical coefficient shape"):
            parse_geometry(encode_record(STAGES[0], extents=bad_extents) + encode_record(STAGES[1]))

    def test_record_stage_order_is_required(self):
        raw = encode_record(STAGES[1]) + encode_record(STAGES[0])
        with self.assertRaisesRegex(ValueError, "expected stage"):
            parse_geometry(raw)

    def test_pre_post_geometry_must_match(self):
        arrays = {name: value.copy() for name, value in ARRAYS.items()}
        arrays["mu2"][0, 0] += 1
        with self.assertRaisesRegex(ValueError, "changed across microphysics"):
            parse_geometry(encode_record(STAGES[0]) + encode_record(STAGES[1], arrays=arrays))

    def test_pre_post_scalar_metadata_must_match(self):
        with self.assertRaisesRegex(ValueError, "scalar metadata differ"):
            parse_geometry(encode_record(STAGES[0]) + encode_record(STAGES[1], dx=10000.0))

    def test_trailing_data_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "trailing bytes"):
            parse_geometry(valid_capture() + b"x")

    def test_nonfinite_tolerances_fail_before_attempting_file_reads(self):
        missing = Path("/path/that/must/not/be/read")
        for kwargs in ({"layer_tolerance_pa": float("nan")},
                       {"column_tolerance_pa": float("inf")}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "finite and positive"):
                audit(missing, missing, missing, missing, **kwargs)


if __name__ == "__main__":
    unittest.main()
