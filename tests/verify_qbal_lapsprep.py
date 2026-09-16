#!/usr/bin/env python3
"""Fixtures, metadata preflight and receipts for the Fortran handoff oracle.

The CDF test hook observes the caller's arrays; it is not a native model writer.
Cold LAPSPREP retains pressure-level omega in w; its surface slot is LSX VV
(m/s). WPS has no omega slab.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import subprocess
from pathlib import Path
import shutil
import struct
import sys

import netCDF4
import numpy as np

from verify_qbal_writer import require, verify as verify_writer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from compare_baseline import _records

I4TIME = 2000000000
VALID_TIME = datetime(1960, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=I4TIME)
STAMP = VALID_TIME.strftime("%y%j%H%M")
WPS_TIME = VALID_TIME.strftime("%Y-%m-%d_%H:%M:%S.0000")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight(variant):
    """Validate the reviewed products plus the ancillary file used for pressure."""
    verify_writer(variant / "candidate.bin", variant / "out", I4TIME)
    for extension in ("lt1", "lw3", "lh3", "lq3"):
        directory = variant / "out" / "balance" / extension
        require([p.name for p in directory.glob("*." + extension)] == [f"{STAMP}.{extension}"],
                f"{extension}: filename/time mismatch")
    with netCDF4.Dataset(variant / "out/balance/lh3" / f"{STAMP}.lh3") as ds:
        require(tuple(len(ds.dimensions[n]) for n in ("record", "z", "y", "x")) == (1, 4, 6, 6),
                "lh3: dimensions mismatch")
        for name, expected in (("level", [700., 800., 900., 1000.]),
                               ("reftime", [I4TIME - 315619200]),
                               ("valtime", [I4TIME - 315619200])):
            variable = ds[name]
            expected_units = "hectopascals" if name == "level" else "seconds since (1970-1-1 00:00:00.0)"
            require(variable.units == expected_units, f"lh3: {name}: units mismatch")
            values = variable[:]
            require(not np.ma.getmaskarray(values).any(), f"lh3: {name}: unexpected missing mask")
            require(np.isfinite(np.asarray(values)).all() and np.array_equal(values, expected),
                    f"lh3: {name}: coordinate mismatch")
        require(ds["rhl"].dimensions == ("record", "z", "y", "x")
                and ds["rhl"].units == "percent", "lh3: RH layout/units mismatch")
        rh = ds["rhl"][:]
        require(not np.ma.getmaskarray(rh).any() and np.all(rh == 50.), "lh3: invalid fixture RH")
        inventory = ds["rhl_fcinv"][:]
        require(not np.ma.getmaskarray(inventory).any() and np.all(inventory == 1),
                "lh3: incomplete inventory")


def stage(variant, root, alternate_geometry=False):
    preflight(variant)
    root.mkdir(parents=True, exist_ok=False)
    (root / "static").mkdir()
    shutil.copytree(variant / "out/balance", root / "lapsprd/balance")
    (root / "lapsprd/lsx").mkdir()
    with netCDF4.Dataset(root / "lapsprd/lsx" / f"{STAMP}.lsx", "w", format="NETCDF3_CLASSIC") as ds:
        for name, size in (("record", 1), ("z", 1), ("y", 6), ("x", 6)):
            ds.createDimension(name, size)
        for name in ("reftime", "valtime"):
            variable = ds.createVariable(name, "f8", ("record",))
            variable.units = "seconds since (1970-1-1 00:00:00.0)"
            variable[:] = I4TIME - 315619200
        values = {"u": 2., "v": -2., "t": 280., "rh": 50., "tgd": 285.,
                  "ps": 101000., "msl": 101000., "mr": 8., "vv": 0.}
        for name, value in values.items():
            ds.createVariable(name, "f4", ("record", "z", "y", "x"))[:] = value
    with netCDF4.Dataset(root / "static/static.nest7grid", "w", format="NETCDF3_CLASSIC") as ds:
        for name, size in (("record", 1), ("z", 1), ("y", 6), ("x", 6), ("nav", 1), ("namelen", 132)):
            ds.createDimension(name, size)
        geometry = {"Dx": 10000., "Dy": 10000., "LoV": 127., "Latin1": 45., "Latin2": 45.}
        if alternate_geometry:
            geometry.update(Dx=12000., Dy=14000., LoV=233., Latin1=44., Latin2=46.)
        for name, value in geometry.items():
            ds.createVariable(name, "f4", ("nav",))[:] = value
        ds.createVariable("grid_type", "S1", ("nav", "namelen"))[:] = np.frombuffer(
            b"secant lambert conformal".ljust(132, b" "), dtype="S1")
        latitude = 45.25 if alternate_geometry else 45.
        longitude = 233. if alternate_geometry else 127.
        for name, value in {"lat": np.broadcast_to(np.linspace(latitude, latitude + .5, 6)[:, None], (6, 6)),
                            "lon": np.broadcast_to(np.linspace(longitude, longitude + .5, 6), (6, 6)), "avg": 0.}.items():
            ds.createVariable(name, "f4", ("record", "z", "y", "x"))[:] = value
    (root / "static/lapsprep.nl").write_text(
        "&lapsprep_nl\n HOTSTART=.false., BALANCE=.true., OUTPUT_FORMAT='wps','cdf',\n"
        " GRID_SCALE='NONE', HYDRO_MODE='CONSERVATIVE', CAP_POLICY='KEEP',\n"
        " WIND_COORDINATE='GRID_RELATIVE', MAKE_SFC_UV=.false.,\n"
        " ENFORCE_FIELD_CONTRACTS=.true., WPS_OUTPUT_VAPOR=.true., LWC2VAPOR_THRESH=0.0,\n/\n")
    products = {str(p.relative_to(root)): sha256(p) for p in (root / "lapsprd").rglob("*") if p.is_file()}
    products.update({str(p.relative_to(root)): sha256(p) for p in (root / "static").iterdir()})
    (root / "staged_inputs.json").write_text(json.dumps(products, indent=2) + "\n")
    return STAMP


def verify(variant, root, wps_path):
    preflight(variant)
    for relative, digest in json.loads((root / "staged_inputs.json").read_text()).items():
        require(sha256(root / relative) == digest, f"staged input changed: {relative}")
    for source in (variant / "out/balance").rglob("*"):
        if source.is_file():
            target = root / "lapsprd/balance" / source.relative_to(variant / "out/balance")
            require(sha256(source) == sha256(target), "writer/staged bytes differ")
    # Numerical equations and all reader/WPS value comparisons live in Fortran.
    oracle = Path(os.environ["QBAL_LAPSPREP_ORACLE"]).resolve()
    result = subprocess.run([str(oracle), str((variant / "candidate.bin").resolve()),
                             str((root / "reader_state.bin").resolve()), str(wps_path.resolve()),
                             str((root / "static/static.nest7grid").resolve())],
                            cwd=root, capture_output=True, text=True)
    if result.returncode:
        reasons = [line.removeprefix("FAIL: ") for line in result.stdout.splitlines()
                   if line.startswith("FAIL: ")]
        raise ValueError(reasons[0] if reasons else "Fortran oracle execution failed: " + result.stderr)
    require("PASS_SCOPED" in result.stdout.splitlines(), "Fortran oracle did not report PASS_SCOPED")
    return {"status": "PASS_SCOPED", "scope": "actual cold LAPSPREP caller arrays and five WPS pressure fields",
            "candidate_sha256": sha256(variant / "candidate.bin"),
            "reader_fields": ["ht", "t", "mr", "u", "v", "omega"],
            "wps_fields": ["UU", "VV", "TT", "HGT", "QV"],
            "numerical_oracle": {"language": "Fortran", "executable_sha256": sha256(oracle)},
            "geometry": {"source_static_sha256": sha256(root / "static/static.nest7grid"),
                         "comparison": "source-bound Lambert metadata; float32 bitwise",
                         "spacing": "static meters / 1000 to WPS kilometers",
                         "remapping": "NOT_TESTED"},
            "transformations": {"height": "float32 PHI/9.80665", "vapor": "float32 q/(1-q)",
                                "pressure": "ascending hPa in caller; Pa in WPS", "omega": "pressure slots retain Pa/s; surface slot is LSX VV (m/s); absent from WPS"},
            "time": {"file": VALID_TIME.isoformat(), "wps": WPS_TIME, "lost_seconds": 0,
                     "status": "PASS_SCOPED: exact analysis seconds preserved in WPS"},
            "open": ["time-preserving native handoff", "terrain/missing-mask correspondence", "native seed/startup/halo consumed state",
                     "hotstart omega-to-W and thermodynamics", "full mass closure", "forecast effects"],
            "limitations": ["synthetic all-valid 6x6x4; synthetic LSX/static/RH",
                            "test-only CDF hook is not a native writer; no model startup executed",
                            "field mask/unit preflight belongs to Python gate; analysis time is checked by LAPSPREP"]}


def corrupt_wps_qv(path):
    records = list(_records(path))
    for index in range(0, len(records), 5):
        if records[index + 1][1][60:69].decode("ascii").strip() == "QV":
            endian, slab = records[index + 4]
            slab = bytearray(slab)
            np.frombuffer(slab, dtype=endian + "f4", count=1)[0] += 1.
            records[index + 4] = (endian, slab)
            break
    else:
        raise ValueError("WPS QV control target absent")
    write_wps_records(path, records)


def write_wps_records(path, records):
    with path.open("wb") as stream:
        for endian, payload in records:
            marker = struct.pack(endian + "i", len(payload))
            stream.write(marker + payload + marker)


# Byte mutations only; the independent source-bound expectations live in Fortran.
WPS_GEOMETRY_CONTROLS = {
    "knownloc": (2, 0, b"UNKNOWN ", "WPS KNOWNLOC mismatch"),
    **{name: (2, 8 + 4 * i, value, "WPS geometry: bits differ")
       for i, (name, value) in enumerate(zip(
           ["la1", "lo1", "dx", "dy", "lov", "latin1", "latin2", "earth_radius"],
           [46., 128., 100., 100., 128., 46., 46., 6372.]))},
    "earth_nan": (2, 36, float("nan"), "WPS geometry: nonfinite"),
    "dx_zero": (2, 16, 0., "WPS geometry: nonpositive scale"),
    "dy_negative": (2, 20, -10., "WPS geometry: nonpositive scale"),
    "radius_zero": (2, 36, 0., "WPS geometry: nonpositive scale"),
    "xfcst": (1, 24, 1., "WPS XFCST: bits differ"),
    "xfcst_nan": (1, 24, float("nan"), "WPS XFCST: nonfinite"),
    "last_dx": (-3, 16, 100., "WPS geometry: bits differ"),
}


def corrupt_wps_geometry(path, control):
    records = list(_records(path))
    index, offset, value, expected = WPS_GEOMETRY_CONTROLS[control]
    endian, record = records[index]
    payload = bytearray(record)
    data = value if isinstance(value, bytes) else struct.pack(endian + "f", value)
    payload[offset:offset + len(data)] = data
    records[index] = (endian, payload)
    write_wps_records(path, records)
    return expected


def controls(variant, root, wps_path):
    """Corrupt copied handoff artifacts and require the designated oracle error."""
    verify(variant, root, wps_path)
    negative = root.parent / (root.name + "-negative")
    negative.mkdir(exist_ok=False)
    results = []
    names = ["ht", "t", "mr", "u", "v", "omega"]
    for index, name in enumerate([*names, "pressure", "wps_time", "wps_seconds", "wps_qv", *WPS_GEOMETRY_CONTROLS]):
        target = negative / name
        shutil.copytree(root, target, ignore=shutil.ignore_patterns("build"))
        output = target / "control.wps"
        shutil.copyfile(wps_path, output)
        if name in WPS_GEOMETRY_CONTROLS:
            expected = corrupt_wps_geometry(output, name)
        elif name == "wps_qv":
            corrupt_wps_qv(output)
            expected = "WPS QV 700.0: bits differ"
        elif name in ("wps_time", "wps_seconds"):
            raw = output.read_bytes()
            require(WPS_TIME.encode() in raw, "WPS time control target absent")
            changed_time = (WPS_TIME.replace("03:33:", "03:34:") if name == "wps_time"
                            else WPS_TIME.replace(":20.0000", ":00.0000"))
            output.write_bytes(raw.replace(WPS_TIME.encode(), changed_time.encode()))
            expected = "WPS time mismatch"
        else:
            path = target / "reader_state.bin"
            raw = bytearray(path.read_bytes())
            offset = 12 if name == "pressure" else 32 + index * 5 * 6 * 6 * 4
            value = np.frombuffer(raw, dtype="<f4", count=1, offset=offset)
            value[0] += np.float32(1.)
            path.write_bytes(raw)
            expected = "reader pressure: bits differ" if name == "pressure" else f"reader {name}: bits differ"
        try:
            verify(variant, target, output)
        except ValueError as error:
            require(str(error) == expected, f"{name}: wrong rejection: {error}")
            results.append({"case": name, "status": "REJECTED", "reason": str(error)})
        else:
            raise ValueError(f"undetected handoff corruption: {name}")
    for name in ("level", "reftime", "valtime"):
        target = negative / ("lh3_missing_" + name)
        (target / "out").mkdir(parents=True)
        shutil.copyfile(variant / "candidate.bin", target / "candidate.bin")
        shutil.copytree(variant / "out/balance", target / "out/balance")
        with netCDF4.Dataset(target / "out/balance/lh3" / f"{STAMP}.lh3", "r+") as ds:
            ds[name].setncattr("missing_value", ds[name][:].flat[0].item())
        try:
            preflight(target)
        except ValueError as error:
            require(str(error) == f"lh3: {name}: unexpected missing mask", f"wrong mask rejection: {error}")
            results.append({"case": "lh3_missing_" + name, "status": "REJECTED", "reason": str(error)})
        else:
            raise ValueError(f"undetected ancillary mask: {name}")
    return results


def time_controls(root):
    """Run actual LAPSPREP on malformed source times, without Python preflight."""
    executable = (root / "build/lapsprep.exe").resolve()
    negative = root.parent / (root.name + "-time-negative")
    negative.mkdir(exist_ok=False)
    cases = [("offset_" + str(offset), "lw3", "valtime", offset)
             for offset in (-301, -300, -1, 1, 300, 301)]
    cases += [("lookup_minute", "lt1", "valtime", 60),
              ("surface_time", "lsx", "valtime", 1),
              ("reference_time", "lw3", "reftime", 1),
              ("nan", "lw3", "valtime", float("nan")),
              ("fraction", "lw3", "valtime", .25),
              ("missing", "lw3", "valtime", None),
              ("units", "lw3", "valtime", None),
              ("absent", "lw3", "valtime", None),
              ("dimension", "lw3", "valtime", None)]
    results = []
    for name, extension, variable, offset in cases:
        target = negative / name
        shutil.copytree(root, target, ignore=shutil.ignore_patterns("build", "wps.out", "reader_state.bin"))
        directory = target / "lapsprd" / ("lsx" if extension == "lsx" else "balance/" + extension)
        with netCDF4.Dataset(directory / f"{STAMP}.{extension}", "r+") as ds:
            value = ds[variable]
            if name == "missing":
                value.missing_value = value[:].flat[0]
            elif name == "units":
                value.units = "hours since (1970-1-1 00:00:00.0)"
            elif name == "dimension":
                ds.renameDimension("record", "not_record")
            elif name == "absent":
                ds.renameVariable(variable, "removed_time")
            else:
                value[:] = value[:] + offset
                if name == "lookup_minute" or name.startswith("offset_") or name == "surface_time":
                    ds["reftime"][:] = ds["reftime"][:] + offset
        environment = os.environ.copy()
        for key in ("CLOUD_BAL_STAGE_MODE", "CLOUD_BAL_STAGE_CONTEXT", "CLOUD_BAL_SHADOW_EXPERIMENT"):
            environment.pop(key, None)
        environment.update(LAPS_DATA_ROOT=str(target.resolve()), CLOUD_BAL_WPS_OUTPUT=str((target / "wps.out").resolve()))
        result = subprocess.run([str(executable), STAMP], cwd=target, env=environment,
                                capture_output=True, text=True)
        log = result.stdout + result.stderr
        (target / "lapsprep.log").write_text(log)
        if name.startswith("offset_"):
            expected = "analysis files disagree" if abs(offset) == 1 else "filename minute mismatch"
        else:
            expected = {"lookup_minute": "filename minute mismatch",
                        "surface_time": "analysis files disagree",
                        "reference_time": "reference/valid mismatch",
                        "nan": "valtime: nonfinite", "fraction": "valtime: fractional seconds",
                        "missing": "valtime: missing value", "units": "valtime: invalid units",
                        "absent": "valtime: missing variable",
                        "dimension": "valtime: record dimension required"}[name]
        require(result.returncode != 0 and "LAPSPREP input time: " + expected in log,
                f"{name}: expected production time rejection ({expected}): {log}")
        require(not (target / "wps.out").exists() and not (target / "reader_state.bin").exists(),
                f"{name}: invalid time created output")
        results.append({"case": name, "status": "REJECTED", "exit_status": result.returncode,
                        "reason": expected, "output_created": False})
    return results


if __name__ == "__main__":
    command, *arguments = sys.argv[1:]
    paths = list(map(Path, arguments))
    if command == "stage":
        print(stage(*paths))
    elif command == "stage-geometry":
        print(stage(*paths, alternate_geometry=True))
    elif command == "verify":
        print(json.dumps(verify(*paths), indent=2))
    elif command == "time-controls":
        print(json.dumps(time_controls(*paths), indent=2))
    elif command == "controls":
        print(json.dumps(controls(*paths), indent=2))
    else:
        raise SystemExit("usage: verify_qbal_lapsprep.py stage VARIANT ROOT | verify VARIANT ROOT WPS")
