from __future__ import annotations

import struct
import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "native_kdm6_call_geometry.py"
_SPEC = importlib.util.spec_from_file_location("native_kdm6_call_geometry", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
ARRAY_NAMES, STAGES, active_geometry_measure, audit, parse_geometry = (
    _MODULE.ARRAY_NAMES, _MODULE.STAGES, _MODULE.active_geometry_measure,
    _MODULE.audit, _MODULE.parse_geometry
)

TRACE_FIELDS_3D = ("TH", "PII", "DEN", "P", "DELZ", "Q", "QC", "QR", "QI",
                   "QS", "QG", "NN", "NC", "NI", "NR", "BG", "DIAGRHOG")
TRACE_FIELDS_2D = ("XLAND",)


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
                  timestep=1, dx=5000.0, dtm=20.0, dt=20.0) -> bytes:
    arrays = ARRAYS if arrays is None else arrays
    data = bytearray(b"PR63GEO2")
    data.extend(stage.encode("ascii"))
    data.extend(struct.pack(">3i6f", timestep, 4, 2, dtm, dt, dx, 5000.0, 9.81, 5000.0))
    data.extend(struct.pack(">12i", *bounds))
    data.extend(struct.pack(">15i", *extents))
    for name in ARRAY_NAMES:
        data.extend(np.asarray(arrays[name], dtype=">f4").tobytes(order="F"))
    return bytes(data)


def valid_capture() -> bytes:
    return encode_record(STAGES[0]) + encode_record(STAGES[1])


def encode_kdm_trace(stage: int, duration: float) -> bytes:
    bounds = (0, 1, 0, 1, 1, 3, 0, 1, 0, 1, 1, 3, 0, 1, 0, 1, 1, 2)
    data = bytearray(b"KDM6TRC1")
    data.extend(struct.pack(">20i", stage, 1, *bounds))
    data.extend(struct.pack(">5f", duration, 1.0, 1.0, 1.0, 1.0))
    for name in TRACE_FIELDS_3D:
        value = 50000.0 if name == "DELZ" else 100000.0 if name == "P" else 1.0
        array = np.full((2, 3, 2), value, dtype=">f4")
        data.extend(name.encode("ascii").ljust(8, b" "))
        data.extend(array.tobytes())
    for name in TRACE_FIELDS_2D:
        array = np.ones((2, 2), dtype=">f4")
        data.extend(name.encode("ascii").ljust(8, b" "))
        data.extend(array.tobytes())
    return bytes(data)


def audit_fixture(root: Path, *, dtm: float, grid_dt: float, kdm_dt: float) -> tuple[Path, ...]:
    arrays = {name: value.copy() for name, value in ARRAYS.items()}
    arrays["c1h"][:] = -1.0
    arrays["c3f"][:] = (1.0, 0.5, 0.0)
    geometry = root / "pr63_geometry.raw"
    pre = root / "kdm_pre.raw"
    post = root / "kdm_post.raw"
    executable = root / "wrf.exe"
    receipt_path = root / "run-isolation.json"
    geometry.write_bytes(
        encode_record(STAGES[0], arrays=arrays, dtm=dtm, dt=grid_dt)
        + encode_record(STAGES[1], arrays=arrays, dtm=dtm, dt=grid_dt)
    )
    pre.write_bytes(encode_kdm_trace(1, kdm_dt))
    post.write_bytes(encode_kdm_trace(2, kdm_dt))
    executable.write_bytes(b"synthetic executable identity")

    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    receipt = {
        "returncode": 0,
        "input_integrity": "PASS",
        "output_isolation": "PASS",
        "inputs": [{"path": str(executable), "sha256_before": sha256(executable),
                    "sha256_after": sha256(executable)}],
        "outputs": [{"path": path.name, "sha256": sha256(path), "nlink": 1}
                    for path in (geometry, pre, post)],
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return geometry, pre, post, receipt_path


class NativeGeometryParserTests(unittest.TestCase):
    def test_valid_pair_parses_fixed_order_records(self):
        records = parse_geometry(valid_capture())
        self.assertEqual([r["stage"] for r in records], list(STAGES))
        self.assertEqual(records[0]["arrays"]["mu2"].shape, (2, 2))
        self.assertEqual(records[0]["timestep"], 1)

    def test_active_hybrid_measure_matches_kdm_active_shape(self):
        records = parse_geometry(valid_capture())
        with tempfile.TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "kdm_pre.raw"
            trace_path.write_bytes(encode_kdm_trace(1, 20.0))
            kdm = _MODULE._load_trace_reader()(trace_path)
        measure = active_geometry_measure(records[0], kdm)
        self.assertEqual(measure["dp"].shape, (2, 2, 2))
        self.assertEqual(measure["area"].shape, (2, 2))
        self.assertTrue(np.all(measure["dp"] > 0.0))
        self.assertTrue(np.all(measure["dry_mass"] > 0.0))

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

    def test_whole_audit_rejects_binary_call_duration_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = audit_fixture(Path(tmp), dtm=20.0, grid_dt=25.0, kdm_dt=10.0)
            with self.assertRaisesRegex(ValueError, "call-duration mismatch"):
                audit(*paths)

    def test_whole_audit_accepts_dtm_match_with_different_grid_dt_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = audit_fixture(Path(tmp), dtm=20.0, grid_dt=25.0, kdm_dt=20.0)
            report = audit(*paths)
        self.assertTrue(report["call_duration_identity"]["matched"])
        self.assertEqual(report["call_duration_identity"]["host_dtm_s"], 20.0)
        self.assertEqual(report["call_duration_identity"]["kdm6_delt_s"], 20.0)
        self.assertEqual(report["call_duration_identity"]["grid_dt_s_metadata"], 25.0)

    def test_trailing_data_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "trailing bytes"):
            parse_geometry(valid_capture() + b"x")

    def test_nonfinite_tolerances_fail_before_attempting_file_reads(self):
        missing = Path("/path/that/must/not/be/read")
        for kwargs in ({"layer_tolerance_pa": float("nan")},
                       {"column_tolerance_pa": float("inf")}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "finite and positive"):
                audit(missing, missing, missing, missing, **kwargs)

    def test_run_root_executable_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = audit_fixture(Path(tmp), dtm=20.0, grid_dt=20.0, kdm_dt=20.0)
            executable = Path(tmp) / "wrf.exe"
            target = Path(tmp) / "executable-target"
            executable.rename(target)
            executable.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "run-root executable"):
                audit(*paths)


if __name__ == "__main__":
    unittest.main()
