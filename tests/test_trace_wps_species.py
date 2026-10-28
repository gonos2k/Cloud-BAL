"""Exercise the WPS readback receipt gate with real WPS and NetCDF products."""
import importlib.util
import json
import struct
from pathlib import Path

import numpy as np
import pytest
from netCDF4 import Dataset


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "docs/evidence/cp02_initial_species_20261027/trace_wps_species.py"
NX, NY, LEVELS = 235, 283, 20
DATE = "2026-08-16_12:00:00.0000"
PRESSURES = np.asarray(range(5000, 100001, 5000), dtype=np.float32)
PROJECTION = b"SWCORNER" + struct.pack("<8f", 0, 0, 1, 1, 0, 30, 60, 6371)


def _record(stream, payload):
    marker = struct.pack("<i", len(payload))
    stream.write(marker + payload + marker)


def _write_wps(path, offset=0.0, changed_record=None):
    with path.open("wb") as stream:
        for species_index, field in enumerate(("QR", "QS")):
            base = (species_index + 1) * 1e-4
            for k, pressure in enumerate(PRESSURES):
                _record(stream, struct.pack("<i", 5))
                metadata = bytearray(156)
                metadata[0:24] = DATE.encode("ascii").ljust(24, b" ")
                metadata[60:69] = field.encode("ascii").ljust(9, b" ")
                metadata[69:94] = b"kg kg{-1}".ljust(25, b" ")
                struct.pack_into("<f", metadata, 140, pressure)
                struct.pack_into("<iii", metadata, 144, NX, NY, 3)
                _record(stream, metadata)
                _record(stream, PROJECTION)
                _record(stream, struct.pack("<i", 0))
                values = np.full((NY, NX), base + k * 1e-6, dtype="<f4")
                if changed_record == (species_index, k):
                    values[0, 0] += offset
                _record(stream, values.tobytes())


def _write_shadow(path):
    with Dataset(path, "w") as shadow:
        shadow.createDimension("pressure_level", LEVELS)
        shadow.createDimension("south_north", NY)
        shadow.createDimension("west_east", NX)
        pressure = shadow.createVariable("pressure", "f4", ("pressure_level",))
        pressure[:] = PRESSURES
        for species_index, species in enumerate(("rain", "snow")):
            values = shadow.createVariable(
                f"candidate_{species}",
                "f4",
                ("pressure_level", "south_north", "west_east"),
            )
            values[:] = np.stack([
                np.full(
                    (NY, NX),
                    (species_index + 1) * 1e-4 + k * 1e-6,
                    dtype=np.float32,
                )
                for k in range(LEVELS)
            ])
            background = shadow.createVariable(
                f"background_{species}",
                "f4",
                ("pressure_level", "south_north", "west_east"),
            )
            background[:] = values[:]


def _load_script():
    spec = importlib.util.spec_from_file_location("trace_wps_species", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def run_trace(tmp_path, monkeypatch):
    module = _load_script()
    archive = tmp_path / "archive"
    pair = archive / "pair"
    pair.mkdir(parents=True)
    for arm in ("HYDRO", "LIQUID_RADAR_RH1"):
        _write_wps(pair / f"{arm}_vapor2.wps")
        _write_shadow(pair / f"{arm}_vapor2.wps.shadow.nc")
    original = archive / "cp02_native_12_15.B4Lwmh/metgrid/LAPS:2026-08-16_12:00"
    original.parent.mkdir(parents=True)
    _write_wps(original)
    monkeypatch.setattr(module, "ARCHIVE", archive)
    monkeypatch.setattr(module, "PAIR", pair)

    def invoke(output):
        monkeypatch.setattr("sys.argv", [str(SCRIPT), "--output", str(output)])
        module.main()

    return module, pair, original, invoke


def test_trace_wps_species_writes_receipt_when_all_checks_are_equal(run_trace, tmp_path):
    _, _, _, invoke = run_trace
    output = tmp_path / "readback.json"

    invoke(output)

    assert output.exists()
    receipt = json.loads(output.read_text())
    assert receipt["status"] == "PASS_SCOPED_WPS_READBACK"
    assert len(receipt["checks"]) == 3
    assert all(len(rows) == 40 for rows in receipt["checks"].values())
    assert all(
        row["exact_equal"]
        for rows in receipt["checks"].values()
        for row in rows
    )


def test_trace_wps_species_off_only_mismatch_fails_without_receipt(run_trace, tmp_path):
    _, _, original, invoke = run_trace
    _write_wps(original, offset=1e-5, changed_record=(0, 0))
    output = tmp_path / "readback.json"

    message = "ACTUAL_OFF_WPS_VS_HYDRO_SHADOW_BACKGROUND WPS differs from shadow"
    with pytest.raises(ValueError, match=message):
        invoke(output)

    assert not output.exists()


def test_trace_wps_species_candidate_mismatch_still_fails_without_receipt(
    run_trace, tmp_path
):
    _, pair, _, invoke = run_trace
    _write_wps(pair / "HYDRO_vapor2.wps", offset=1e-5, changed_record=(0, 0))
    output = tmp_path / "readback.json"

    with pytest.raises(ValueError, match="HYDRO WPS differs from shadow"):
        invoke(output)

    assert not output.exists()
