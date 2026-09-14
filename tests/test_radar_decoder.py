#!/usr/bin/env python3
"""Validate the isolated decoder against raw Cf/Radial input files."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import stat
from pathlib import Path

import netCDF4
import numpy as np


RADIAL = 800
MOMENTS = {
    "Z": "DBZH",
    "V": "VELH",
    "W": "WIDTHH",
}
NODATA = np.float32(131072.0)
SUPPORTED_CALENDARS = {"standard", "gregorian", "proleptic_gregorian"}
CF_SECONDS_UNITS = re.compile(r"^seconds since (.+)$")
UTC_ISO = re.compile(
    r"^(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})T"
    r"(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2}(?:\.[0-9]+)?)Z$"
)


def _fail(message: str) -> None:
    raise AssertionError(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _parse_utc_iso(value: str, label: str) -> float:
    match = UTC_ISO.fullmatch(value)
    _require(match is not None, f"{label}: unsupported UTC ISO-8601 value {value!r}")
    assert match is not None
    try:
        second = float(match.group("second"))
        _require(np.isfinite(second) and 0.0 <= second < 60.0,
                 f"{label}: seconds are outside the supported range")
        parsed = dt.datetime(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
            int(match.group("hour")),
            int(match.group("minute")),
            second=int(second),
            tzinfo=dt.timezone.utc,
        )
        return parsed.timestamp() + second - int(second)
    except ValueError as exc:
        _fail(f"{label}: invalid UTC ISO-8601 value {value!r}: {exc}")
    raise AssertionError("unreachable")


def _parse_cf_seconds_units(units: str, path: Path) -> tuple[str, float]:
    match = CF_SECONDS_UNITS.fullmatch(units)
    _require(match is not None, f"{path}: time units must be CF seconds since UTC origin")
    assert match is not None
    origin_text = match.group(1)
    return origin_text, _parse_utc_iso(origin_text, f"{path}: time units origin")


def _juldate_from_epoch(epoch: float) -> str:
    timestamp = dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc)
    day_of_year = timestamp.timetuple().tm_yday
    return f"{timestamp.year % 100:02d}{day_of_year:03d}{timestamp:%H%M}"


def _time_contract_from_dataset(dataset: netCDF4.Dataset, path: Path) -> dict[str, object]:
    _require("time" in dataset.variables, f"{path}: missing time variable")
    time_variable = dataset.variables["time"]
    units = str(time_variable.getncattr("units"))
    origin_text, origin_epoch = _parse_cf_seconds_units(units, path)
    calendar = str(time_variable.getncattr("calendar")) if "calendar" in time_variable.ncattrs() else "standard"
    _require(calendar in SUPPORTED_CALENDARS, f"{path}: unsupported time calendar {calendar!r}")
    values = np.asarray(time_variable[:], dtype=np.float64)
    _require(values.size > 0, f"{path}: time values are empty")
    _require(np.all(np.isfinite(values)), f"{path}: time values are nonfinite")
    _require(np.all(np.diff(values) >= 0.0), f"{path}: time values decrease")
    coverage_start_text = str(dataset.getncattr("time_coverage_start"))
    coverage_end_text = str(dataset.getncattr("time_coverage_end"))
    coverage_start = _parse_utc_iso(coverage_start_text, f"{path}: time_coverage_start")
    coverage_end = _parse_utc_iso(coverage_end_text, f"{path}: time_coverage_end")
    _require(coverage_end >= coverage_start, f"{path}: time coverage is reversed")
    ray_epoch = origin_epoch + values
    _require(
        float(np.min(ray_epoch)) >= coverage_start - 1.0e-6 and
        float(np.max(ray_epoch)) <= coverage_end + 1.0e-6,
        f"{path}: ray epochs fall outside time coverage",
    )
    return {
        "units": units,
        "origin_text": origin_text,
        "origin_epoch": origin_epoch,
        "calendar": calendar,
        "coverage_start": coverage_start_text,
        "coverage_end": coverage_end_text,
        "coverage_start_epoch": coverage_start,
        "coverage_end_epoch": coverage_end,
        "ray_epoch_start": float(ray_epoch[0]),
        "ray_epoch_end": float(ray_epoch[-1]),
        "juldate": _juldate_from_epoch(origin_epoch),
    }


def read_time_contract(path: Path) -> dict[str, object]:
    with netCDF4.Dataset(path) as dataset:
        dataset.set_auto_maskandscale(False)
        return _time_contract_from_dataset(dataset, path)


def _file_identity(status: os.stat_result) -> dict[str, int]:
    return {
        "device": status.st_dev,
        "inode": status.st_ino,
        "size": status.st_size,
        "mode": status.st_mode,
        "mtime_ns": status.st_mtime_ns,
        "ctime_ns": status.st_ctime_ns,
    }


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        offset += os.write(descriptor, payload[offset:])


def _snapshot_file(source: Path, destination: Path) -> dict[str, object]:
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        source_fd = os.open(source, flags)
    except OSError as exc:
        raise AssertionError(f"cannot open raw input safely: {source}") from exc
    destination_fd = -1
    try:
        before = os.fstat(source_fd)
        _require(stat.S_ISREG(before.st_mode), f"{source}: raw input is not a regular file")
        destination_fd = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
            0o440,
        )
        source_digest = hashlib.sha256()
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            source_digest.update(chunk)
            _write_all(destination_fd, chunk)
        after = os.fstat(source_fd)
        _require(
            _file_identity(before) == _file_identity(after),
            f"{source}: raw input changed while snapshotting",
        )
        os.fsync(destination_fd)
        digest = source_digest.hexdigest()
        return {
            "source_path": str(source),
            "source_sha256": digest,
            "source_identity": _file_identity(before),
            "snapshot_path": str(destination),
            "snapshot_sha256": digest,
        }
    finally:
        if destination_fd >= 0:
            os.close(destination_fd)
        os.close(source_fd)


def snapshot_raw_inputs(raw_root: Path, snapshot_root: Path, timestamp: str) -> dict[str, object]:
    raw_paths = sorted(raw_root.glob(f"RDR_*_FQC_{timestamp}.nc"))
    _require(bool(raw_paths), f"{raw_root}: no raw FQC inputs for requested cycle {timestamp}")
    snapshot_root.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, object]] = []
    for source in raw_paths:
        destination = snapshot_root / source.name
        record = _snapshot_file(source, destination)
        record["time_contract"] = read_time_contract(destination)
        records.append(record)
    return {
        "schema": 1,
        "raw_root": str(raw_root),
        "snapshot_root": str(snapshot_root),
        "requested_cycle": timestamp,
        "files": records,
    }


def _raw_case(path: Path) -> dict[str, object]:
    with netCDF4.Dataset(path) as dataset:
        dataset.set_auto_maskandscale(False)
        dimensions = {name: len(value) for name, value in dataset.dimensions.items()}
        required_dimensions = {"time", "n_points", "range", "sweep"}
        _require(required_dimensions <= dimensions.keys(), f"{path}: missing dimensions")
        moments = {}
        units = {}
        scales = {}
        offsets = {}
        fills = {}
        for output_name, input_name in MOMENTS.items():
            variable = dataset.variables[input_name]
            _require(variable.dimensions == ("n_points",), f"{path}: {input_name} order")
            _require(variable.dtype == np.dtype("int16"), f"{path}: {input_name} type")
            moments[output_name] = np.asarray(variable[:])
            units[output_name] = str(variable.getncattr("units"))
            scales[output_name] = float(variable.scale_factor)
            offsets[output_name] = float(getattr(variable, "add_offset", 0.0))
            fills[output_name] = int(variable._FillValue)
            _require(np.isfinite(scales[output_name]) and scales[output_name] > 0.0,
                     f"{path}: {input_name} scale")
            _require(np.isfinite(offsets[output_name]), f"{path}: {input_name} offset")

        def values(name: str) -> np.ndarray:
            return np.asarray(dataset.variables[name][:])

        rays = values("rays").astype(np.int64)
        bins = values("bins").astype(np.int64)
        sweep_start = values("sweep_start_ray_index").astype(np.int64)
        sweep_end = values("sweep_end_ray_index").astype(np.int64)
        ray_start = values("ray_start_index").astype(np.int64)
        ray_n_gates = values("ray_n_gates").astype(np.int64)
        elevation = values("elevation").astype(np.float64)
        azimuth = values("azimuth").astype(np.float64)
        time = values("time").astype(np.float64)
        range_values = values("range").astype(np.float64)
        nyquist = values("nyquist_velocity").astype(np.float64)
        _require(dataset.variables["nyquist_velocity"].getncattr("units") == "m/s",
                 f"{path}: nyquist units")
        _require(dataset.variables["elevation"].getncattr("units") == "degree" and
                 dataset.variables["azimuth"].getncattr("units") == "degree",
                 f"{path}: angle units")
        _require(dataset.variables["range"].getncattr("units") == "meters",
                 f"{path}: range units")
        _require(np.all(np.isfinite(nyquist)) and np.all(nyquist > 0.0),
                 f"{path}: nyquist values")
        _require(np.all(np.isfinite(elevation)) and np.all(np.abs(elevation) <= 90.0),
                 f"{path}: elevation values")
        _require(np.all(np.isfinite(azimuth)) and np.all((azimuth >= 0.0) & (azimuth <= 360.0)),
                 f"{path}: azimuth values")
        _require(np.all(np.isfinite(time)), f"{path}: time values")
        _require(np.all(np.diff(time) >= 0.0), f"{path}: time ordering")
        _require(-90.0 <= float(dataset.variables["latitude"][:]) <= 90.0 and
                 -180.0 <= float(dataset.variables["longitude"][:]) <= 180.0,
                 f"{path}: site coordinates")
        _require(np.isfinite(float(dataset.variables["altitude"][:])),
                 f"{path}: site altitude")
        _require(np.all(np.isfinite(range_values)) and np.all(np.diff(range_values) > 0.0),
                 f"{path}: range values")
        _require(np.allclose(np.diff(range_values), np.diff(range_values)[0],
                             rtol=0.0, atol=1.0e-3),
                 f"{path}: range spacing")

        ray_cursor = 0
        point_cursor = 0
        for sweep, (ray_count, gate_count) in enumerate(zip(rays, bins)):
            _require(0 < ray_count <= RADIAL, f"{path}: sweep {sweep + 1} ray bound")
            _require(0 < gate_count <= dimensions["range"],
                     f"{path}: sweep {sweep + 1} gate bound")
            _require(sweep_start[sweep] == ray_cursor and
                     sweep_end[sweep] == ray_cursor + ray_count - 1,
                     f"{path}: sweep {sweep + 1} ray index")
            for local_ray in range(int(ray_count)):
                ray = ray_cursor + local_ray
                expected_start = point_cursor + local_ray * int(gate_count)
                _require(ray_start[ray] == expected_start and
                         ray_n_gates[ray] == gate_count,
                         f"{path}: packed index for ray {ray + 1}")
            ray_cursor += int(ray_count)
            point_cursor += int(ray_count) * int(gate_count)
        _require(ray_cursor == dimensions["time"], f"{path}: sum(rays)")
        _require(point_cursor == dimensions["n_points"], f"{path}: sum(rays*bins)")

        time_contract = _time_contract_from_dataset(dataset, path)

        return {
            "dimensions": dimensions,
            "moments": moments,
            "units": units,
            "scales": scales,
            "offsets": offsets,
            "fills": fills,
            "rays": rays,
            "bins": bins,
            "elevation": elevation,
            "azimuth": azimuth,
            "time": time,
            "range": range_values,
            "nyquist": nyquist,
            "time_contract": time_contract,
        }


def validate_case(raw_path: Path, output_root: Path, radar_name: str, juldate: str | None,
                  epoch: float | None) -> dict[str, int]:
    case = _raw_case(raw_path)
    dimensions = case["dimensions"]
    moments = case["moments"]
    units = case["units"]
    scales = case["scales"]
    offsets = case["offsets"]
    fills = case["fills"]
    rays = case["rays"]
    bins = case["bins"]
    elevation = case["elevation"]
    azimuth = case["azimuth"]
    time = case["time"]
    range_values = case["range"]
    nyquist = case["nyquist"]
    time_contract = case["time_contract"]
    assert isinstance(dimensions, dict)
    assert isinstance(moments, dict)
    assert isinstance(units, dict)
    assert isinstance(scales, dict)
    assert isinstance(offsets, dict)
    assert isinstance(fills, dict)
    assert isinstance(rays, np.ndarray)
    assert isinstance(bins, np.ndarray)
    assert isinstance(elevation, np.ndarray)
    assert isinstance(azimuth, np.ndarray)
    assert isinstance(time, np.ndarray)
    assert isinstance(range_values, np.ndarray)
    assert isinstance(nyquist, np.ndarray)
    assert isinstance(time_contract, dict)
    origin_epoch = float(time_contract["origin_epoch"])
    derived_juldate = str(time_contract["juldate"])
    if epoch is not None:
        _require(abs(float(epoch) - origin_epoch) <= 1.0e-6,
                 f"{raw_path}: requested epoch does not match CF time origin")
    if juldate is not None:
        _require(juldate == derived_juldate,
                 f"{raw_path}: requested JULDATE does not match CF time origin")

    output_directory = output_root / "RADR" / "ouda" / radar_name
    point_cursor = 0
    ray_cursor = 0
    truncated = 0
    for sweep_number, (ray_count, source_gate_count) in enumerate(zip(rays, bins), 1):
        ray_count = int(ray_count)
        source_gate_count = int(source_gate_count)
        output_gate_count = min(source_gate_count, 920)
        truncated += source_gate_count > output_gate_count
        output_path = output_directory / f"{derived_juldate}_elev{sweep_number:02d}"
        _require(output_path.is_file(), f"{output_path}: missing decoder output")
        with netCDF4.Dataset(output_path) as output:
            output.set_auto_maskandscale(False)
            expected_dimensions = {
                "radial": 800,
                "Z_bin": 920,
                "V_bin": 920,
                "radarNameLen": 8,
                "siteNameLen": 16,
            }
            _require({name: len(value) for name, value in output.dimensions.items()} ==
                     expected_dimensions, f"{output_path}: dimensions")
            _require(output.getncattr("authority") == "RAW_INPUT_ONLY",
                     f"{output_path}: authority")
            _require(output.getncattr("source_time_units") == time_contract["units"],
                     f"{output_path}: source time units")
            _require(output.getncattr("source_time_calendar") == time_contract["calendar"],
                     f"{output_path}: source time calendar")
            _require(output.getncattr("source_time_coverage_start") == time_contract["coverage_start"],
                     f"{output_path}: source time coverage start")
            _require(output.getncattr("source_time_coverage_end") == time_contract["coverage_end"],
                     f"{output_path}: source time coverage end")
            _require(output.getncattr("decoder_contract") ==
                     "cloud_bal_radar_decoder_raw_moments_v1",
                     f"{output_path}: decoder contract")
            _require(int(output.getncattr("source_gate_count")) == source_gate_count,
                     f"{output_path}: source gate count")
            _require(int(output.getncattr("output_gate_count")) == output_gate_count,
                     f"{output_path}: output gate count")
            _require(int(output.getncattr("gate_data_truncated")) ==
                     int(source_gate_count > output_gate_count),
                     f"{output_path}: truncation flag")
            _require(output.variables["siteName"][:].tobytes() ==
                     radar_name.ljust(16).encode("ascii"),
                     f"{output_path}: site name")
            _require(output.variables["radarName"][:].tobytes() ==
                     radar_name.ljust(8).encode("ascii"),
                     f"{output_path}: radar name")
            expected_units = {"Z": "dBZ", "V": "meter/second", "W": units["W"]}
            for output_name, expected_unit in expected_units.items():
                _require(output.variables[output_name].getncattr("units") == expected_unit,
                         f"{output_path}: {output_name} units")

            for output_name, input_name in MOMENTS.items():
                variable = output.variables[output_name]
                output_bin_dimension = "Z_bin" if output_name == "Z" else "V_bin"
                _require(variable.dimensions == ("radial", output_bin_dimension),
                         f"{output_path}: {output_name} dimension order")
                actual = np.asarray(variable[:])
                raw = moments[output_name][point_cursor:point_cursor + ray_count * source_gate_count]
                raw = raw.reshape(ray_count, source_gate_count)[:, :output_gate_count]
                expected = np.where(
                    raw == fills[output_name],
                    NODATA,
                    raw.astype(np.float32) * scales[output_name] + offsets[output_name],
                )
                _require(np.allclose(actual[:ray_count, :output_gate_count], expected,
                                     rtol=0.0, atol=1.0e-5),
                         f"{output_path}: {output_name} packed decode")
                _require(np.all(actual[:ray_count, output_gate_count:] == NODATA),
                         f"{output_path}: {output_name} clipped tail")
                _require(np.all(actual[ray_count:, :] == 0.0),
                         f"{output_path}: {output_name} unused rays")
                valid_range = np.asarray(variable.getncattr("valid_range"), dtype=np.float64)
                _require(valid_range.shape == (2,) and valid_range[0] <= valid_range[1],
                         f"{output_path}: {output_name} valid range")
                valid = actual[:ray_count, :output_gate_count]
                valid = valid[valid != NODATA]
                _require(np.all(np.isfinite(valid)) and
                         np.all((valid >= valid_range[0]) & (valid <= valid_range[1])),
                         f"{output_path}: {output_name} range coverage")
                _require(float(variable.getncattr("_FillValue")) == float(NODATA),
                         f"{output_path}: {output_name} fill value")

            sweep_ray_slice = slice(ray_cursor, ray_cursor + ray_count)
            radial_time = np.asarray(output.variables["radialTime"][:])
            _require(np.array_equal(radial_time[:ray_count], origin_epoch + time[sweep_ray_slice]),
                     f"{output_path}: radial time")
            _require(np.all(radial_time[ray_count:] == 0.0), f"{output_path}: time tail")
            _require(np.allclose(np.asarray(output.variables["radialAzim"][:ray_count]),
                                 azimuth[sweep_ray_slice], rtol=0.0, atol=1.0e-5),
                     f"{output_path}: radial azimuth")
            _require(np.allclose(np.asarray(output.variables["radialElev"][:ray_count]),
                                 elevation[sweep_ray_slice], rtol=0.0, atol=1.0e-5),
                     f"{output_path}: radial elevation")
            _require(float(output.variables["nyquist"][:]) == float(nyquist[sweep_number - 1]),
                     f"{output_path}: sweep Nyquist")
            _require(int(output.variables["numGatesZ"][:]) == output_gate_count and
                     int(output.variables["numGatesV"][:]) == output_gate_count,
                     f"{output_path}: output gate metadata")
            _require(np.isclose(float(output.variables["firstGateRangeZ"][:]), range_values[0]) and
                     np.isclose(float(output.variables["firstGateRangeV"][:]), range_values[0]),
                     f"{output_path}: first gate range")
            spacing = range_values[1] - range_values[0]
            _require(np.isclose(float(output.variables["gateSizeZ"][:]), spacing) and
                     np.isclose(float(output.variables["gateSizeV"][:]), spacing),
                     f"{output_path}: gate spacing")
            expected_range = (range_values[0] + spacing * (output_gate_count - 1)) / 1000.0
            _require(np.isclose(float(output.variables["unambigRange"][:]), expected_range),
                     f"{output_path}: range extent")
            expected_time = origin_epoch + time[sweep_ray_slice]
            _require(float(output.variables["esStartTime"][:]) == float(expected_time[0]) and
                     float(output.variables["esEndTime"][:]) == float(expected_time[-1]),
                     f"{output_path}: scan time bounds")
            _require(float(output.variables["elevationAngle"][:]) ==
                     float(elevation[ray_cursor + ray_count - 1]),
                     f"{output_path}: elevation angle")
        point_cursor += ray_count * source_gate_count
        ray_cursor += ray_count

    return {"sweeps": len(rays), "rays": int(ray_cursor), "truncated_sweeps": int(truncated)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--snapshot-root", type=Path)
    parser.add_argument("--snapshot-manifest", type=Path)
    parser.add_argument("--juldate")
    parser.add_argument("--epoch", type=float)
    parser.add_argument("--timestamp", default="202608162200")
    args = parser.parse_args()
    if args.snapshot_root is not None:
        _require(args.snapshot_manifest is not None,
                 "--snapshot-manifest is required with --snapshot-root")
        manifest = snapshot_raw_inputs(args.raw_root, args.snapshot_root, args.timestamp)
        args.snapshot_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        print(f"RADAR_DECODER_SNAPSHOT_PASS files={len(manifest['files'])} manifest={args.snapshot_manifest}")
        return 0
    _require(args.output_root is not None, "--output-root is required for validation")
    raw_paths = sorted(args.raw_root.glob(f"RDR_*_FQC_{args.timestamp}.nc"))
    _require(bool(raw_paths), f"{args.raw_root}: no raw FQC inputs")
    totals = {"files": 0, "sweeps": 0, "rays": 0, "truncated_sweeps": 0}
    expected_products: set[str] = set()
    for raw_path in raw_paths:
        radar_name = raw_path.name.split("_", 2)[1]
        with netCDF4.Dataset(raw_path) as dataset:
            sweep_count = len(dataset.dimensions["sweep"])
        derived_juldate = str(read_time_contract(raw_path)["juldate"])
        expected_products.update(
            f"{radar_name}/{derived_juldate}_elev{sweep:02d}"
            for sweep in range(1, sweep_count + 1)
        )
        result = validate_case(raw_path, args.output_root, radar_name, args.juldate, args.epoch)
        totals["files"] += 1
        for key in ("sweeps", "rays", "truncated_sweeps"):
            totals[key] += result[key]
    output_base = args.output_root / "RADR" / "ouda"
    actual_products: set[str] = set()
    _require(output_base.is_dir(), f"{output_base}: missing output tree")
    for path in output_base.rglob("*"):
        _require(not path.is_symlink(), f"{path}: symlink output is forbidden")
        if path.is_file():
            actual_products.add(str(path.relative_to(output_base)))
        else:
            _require(path.is_dir(), f"{path}: unexpected non-directory output")
    _require(actual_products == expected_products,
             "output tree contains missing or unexpected radar products")
    print(
        "RADAR_DECODER_VALIDATION_PASS "
        f"files={totals['files']} sweeps={totals['sweeps']} rays={totals['rays']} "
        f"truncated_sweeps={totals['truncated_sweeps']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
