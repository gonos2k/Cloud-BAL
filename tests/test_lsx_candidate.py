#!/usr/bin/env python3
"""Bounded read-only contract tests for an LSX surface candidate."""

from __future__ import annotations

import hashlib
import importlib.util
import argparse
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import netCDF4
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "tools/check_qbal_real_inputs.py"
CHECKER_SPEC = importlib.util.spec_from_file_location("qbal_input_checker", CHECKER_PATH)
assert CHECKER_SPEC is not None and CHECKER_SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(CHECKER_SPEC)
CHECKER_SPEC.loader.exec_module(CHECKER)

# Reuse the established LT1 fixture helpers instead of duplicating navigation and
# epoch encoding.  The LSX writer below only supplies its z=1 surface contract.
LT1_PATH = Path(__file__).with_name("test_lt1_candidate.py")
LT1_SPEC = importlib.util.spec_from_file_location("lt1_candidate_fixtures", LT1_PATH)
assert LT1_SPEC is not None and LT1_SPEC.loader is not None
LT1 = importlib.util.module_from_spec(LT1_SPEC)
LT1_SPEC.loader.exec_module(LT1)


VALID_TIME = LT1.VALID_TIME
REFERENCE_TIME = LT1.REFERENCE_TIME
FILL = np.float32(1.0e37)
LSX_NAME = "262281200.lsx"
LSX_SHAPE = (1, 1, 283, 235)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_lsx(
    path: Path,
    *,
    fields: tuple[str, ...] = ("t", "ps"),
    inventory: bool = True,
    inventory_dtype: str = "i2",
    z: int = 1,
    valtime: str = VALID_TIME,
    reftime: str = VALID_TIME,
) -> None:
    """Write only the two LSX fields consumed by the content contract."""
    with netCDF4.Dataset(path, "w", format="NETCDF4") as dataset:
        LT1.write_common_dimensions(dataset, z=z)
        options = {"zlib": True, "complevel": 1, "fill_value": FILL}
        field_values = {"t": np.float32(280.0), "ps": np.float32(100000.0)}
        field_units = {"t": "degrees kelvin", "ps": "pascals"}
        laps_units = {"t": "K", "ps": "PA"}
        for name in fields:
            variable = dataset.createVariable(
                name, "f4", ("record", "z", "y", "x"), **options
            )
            variable.units = field_units[name]
            variable.LAPS_var = name.upper()
            variable.LAPS_units = laps_units[name]
            variable.lvl_coord = "AGL"
            variable.valid_range = np.asarray(
                (0.0, 350.0) if name == "t" else (0.0, 120000.0),
                dtype=np.float32,
            )
            variable[:] = field_values[name]
            if inventory:
                written = dataset.createVariable(
                    f"{name}_fcinv", inventory_dtype, ("record", "z"),
                    fill_value=np.int16(0),
                )
                written[:] = np.int16(1)

        surfacelevel = dataset.createVariable("level", "f4", ("z",))
        surfacelevel.units = "none"
        surfacelevel[:] = np.float32(0.0)
        for name, value in (("imax", 235), ("jmax", 283), ("kmax", 24), ("kdim", 24)):
            scalar = dataset.createVariable(name, "i4", ())
            scalar.assignValue(value)
        LT1.write_navigation(dataset)
        LT1.write_times(dataset, valtime, reftime)


def make_case(root: Path, label: str) -> tuple[Path, Path]:
    case_root = root / label
    case_root.mkdir()
    return case_root / LSX_NAME, case_root / "reference.fsf"


def make_pristine_case(root: Path, label: str = "pristine") -> tuple[Path, Path]:
    lsx, fsf = make_case(root, label)
    write_lsx(lsx)
    # FSF is deliberately an independently written background-cycle reference.
    LT1.write_fsf(fsf, reftime=REFERENCE_TIME)
    return lsx, fsf


def inspect(lsx: Path, fsf: Path) -> dict[str, object]:
    before = (digest(lsx), digest(fsf))
    result = CHECKER.inspect_lsx_candidate(lsx, fsf, VALID_TIME, REFERENCE_TIME)
    after = (digest(lsx), digest(fsf))
    assert before == after, "candidate checker modified read-only input"
    return result


def require_status(result: dict[str, object], expected: str, label: str) -> None:
    assert result.get("status") == expected, f"{label}: {result}"
    assert result.get("scope") == "LSX_CONTENT_ONLY", f"{label}: {result}"
    assert result.get("generation_status") == "BLOCKED", f"{label}: {result}"
    assert result.get("promotion_allowed") is False, f"{label}: {result}"
    assert isinstance(result.get("findings"), list), f"{label}: findings missing"


def test_lsx_candidate_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-bal-lsx-candidate-") as directory:
        root = Path(directory)
        pristine, fsf = make_pristine_case(root)
        require_status(inspect(pristine, fsf), "PASS", "valid LSX")

        # Required fields and metadata.
        for label, fields in (("missing_t", ("ps",)), ("missing_ps", ("t",))):
            candidate, reference = make_case(root, label)
            write_lsx(candidate, fields=fields)
            LT1.write_fsf(reference, reftime=REFERENCE_TIME)
            require_status(inspect(candidate, reference), "FAIL", label)

        for label, attribute, value in (
            ("bad_t_units", "units", "celsius"),
            ("bad_t_laps_var", "LAPS_var", "TSF"),
            ("bad_t_laps_units", "LAPS_units", "DEGC"),
            ("bad_t_level", "lvl_coord", "MSL"),
            ("bad_ps_units", "units", "hPa"),
            ("bad_ps_laps_var", "LAPS_var", "PSFC"),
            ("bad_ps_laps_units", "LAPS_units", "HPA"),
            ("bad_ps_level", "lvl_coord", "MSL"),
        ):
            candidate, reference = make_pristine_case(root, label)
            field = "ps" if label.startswith("bad_ps") else "t"
            with netCDF4.Dataset(candidate, "r+") as dataset:
                setattr(dataset.variables[field], attribute, value)
            require_status(inspect(candidate, reference), "FAIL", label)

        # Times, missing values, and finite/range checks.
        for label, mutate in (
            ("bad_valtime", lambda ds: ds.variables["valtime"].__setitem__(0, LT1._epoch("2026-08-16T13:00:00Z"))),
            ("bad_reftime", lambda ds: ds.variables["reftime"].__setitem__(0, LT1._epoch(REFERENCE_TIME))),
            ("nan_t", lambda ds: _set_raw(ds.variables["t"], np.nan)),
            ("masked_t", lambda ds: _set_raw(ds.variables["t"], FILL)),
            ("nan_ps", lambda ds: _set_raw(ds.variables["ps"], np.nan)),
            ("masked_ps", lambda ds: _set_raw(ds.variables["ps"], FILL)),
            ("low_t", lambda ds: ds.variables["t"].__setitem__((0, 0, 0, 0), np.float32(149.0))),
            ("high_ps", lambda ds: ds.variables["ps"].__setitem__((0, 0, 0, 0), np.float32(110001.0))),
        ):
            candidate, reference = make_pristine_case(root, label)
            with netCDF4.Dataset(candidate, "r+") as dataset:
                mutate(dataset)
            require_status(inspect(candidate, reference), "FAIL", label)

        # Surface inventory and scalar writer contract.
        for label, kwargs in (
            ("missing_inventory", {"inventory": False}),
            ("wrong_inventory_dtype", {"inventory_dtype": "i4"}),
            ("wrong_z_dimension", {"z": 2}),
        ):
            candidate, reference = make_case(root, label)
            write_lsx(candidate, **kwargs)
            LT1.write_fsf(reference, reftime=REFERENCE_TIME)
            require_status(inspect(candidate, reference), "FAIL", label)
        candidate, reference = make_pristine_case(root, "nonone_inventory")
        with netCDF4.Dataset(candidate, "r+") as dataset:
            dataset.variables["ps_fcinv"][0, 0] = np.int16(0)
        require_status(inspect(candidate, reference), "FAIL", "nonone_inventory")

        for label, scalar, value in (
            ("bad_imax", "imax", 234), ("bad_jmax", "jmax", 282),
            ("bad_kmax", "kmax", 22), ("bad_kdim", "kdim", 22),
        ):
            candidate, reference = make_pristine_case(root, label)
            with netCDF4.Dataset(candidate, "r+") as dataset:
                dataset.variables[scalar][...] = value
            require_status(inspect(candidate, reference), "FAIL", label)

        candidate, reference = make_pristine_case(root, "bad_surfacelevel")
        with netCDF4.Dataset(candidate, "r+") as dataset:
            dataset.variables["level"][0] = np.float32(1.0)
        require_status(inspect(candidate, reference), "FAIL", "bad_surfacelevel")

        candidate, reference = make_pristine_case(root, "bad_surfacelevel_units")
        with netCDF4.Dataset(candidate, "r+") as dataset:
            dataset.variables["level"].units = "meters"
        require_status(inspect(candidate, reference), "FAIL", "bad_surfacelevel_units")

        # Navigation must match the independently written FSF exactly, except
        # for the documented decimal rounding of La1/Lo1 in the legacy CDL.
        rounded, rounded_reference = make_pristine_case(root, "rounded_navigation")
        with netCDF4.Dataset(rounded, "r+") as dataset:
            dataset.variables["La1"][0] = np.float32(31.344505310058594)
            dataset.variables["Lo1"][0] = np.float32(119.79931640625)
        with netCDF4.Dataset(rounded_reference, "r+") as dataset:
            dataset.variables["La1"][0] = np.float32(31.34450912475586)
            dataset.variables["Lo1"][0] = np.float32(119.79930114746094)
        require_status(inspect(rounded, rounded_reference), "PASS", "rounded_navigation")

        for label, name, value in (
            ("shifted_la1", "La1", np.float32(31.34452)),
            ("shifted_lo1", "Lo1", np.float32(119.7994)),
            ("nan_la1", "La1", np.float32(np.nan)),
            ("nan_lo1", "Lo1", np.float32(np.nan)),
        ):
            candidate, reference = make_pristine_case(root, label)
            with netCDF4.Dataset(candidate, "r+") as dataset:
                dataset.variables[name][0] = value
            require_status(inspect(candidate, reference), "FAIL", label)

        candidate, reference = make_pristine_case(root, "bad_navigation")
        with netCDF4.Dataset(candidate, "r+") as dataset:
            dataset.variables["Nx"][0] = np.int16(234)
        require_status(inspect(candidate, reference), "FAIL", "bad_navigation")

        # The filename and inode relationship are part of promotion safety.
        wrong_name, wrong_reference = make_case(root, "wrong_filename")
        wrong_name = wrong_name.with_name("surface.lsx")
        write_lsx(wrong_name)
        LT1.write_fsf(wrong_reference, reftime=REFERENCE_TIME)
        require_status(inspect(wrong_name, wrong_reference), "FAIL", "wrong_filename")

        hardlink_root = root / "hardlink_to_fsf"
        hardlink_root.mkdir()
        hardlink = hardlink_root / LSX_NAME
        hardlink_reference = hardlink_root / "reference.fsf"
        LT1.write_fsf(hardlink_reference, reftime=REFERENCE_TIME)
        hardlink.unlink(missing_ok=True)
        hardlink.symlink_to(hardlink_reference)
        require_status(inspect(hardlink, hardlink_reference), "FAIL", "symlink_to_fsf")

        link_root = root / "hardlink"
        link_root.mkdir()
        linked_candidate = link_root / LSX_NAME
        linked_reference = link_root / "reference.fsf"
        LT1.write_fsf(linked_reference, reftime=REFERENCE_TIME)
        linked_candidate.hardlink_to(linked_reference)
        require_status(inspect(linked_candidate, linked_reference), "FAIL", "hardlink_to_fsf")


def _set_raw(variable: netCDF4.Variable, value: float) -> None:
    variable.set_auto_mask(False)
    variable[0, 0, 0, 0] = np.float32(value)


def test_cli_real_references() -> None:
    """Synthetic LSX with pinned actual FSF navigation; not producer output."""
    workspace = REPO_ROOT.parent
    manifest = REPO_ROOT / "tests/qbal_real_cases_20260816.tsv"
    # Use the checker default manifest rather than a separate case inventory.
    parsed = subprocess.run([sys.executable, str(CHECKER_PATH), "--help"],
                            capture_output=True, text=True, check=True)
    assert "--inspect-lsx" in parsed.stdout
    with manifest.open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    with tempfile.TemporaryDirectory(prefix="lsx-cli-") as directory:
        root = Path(directory)
        for row in rows:
            reference = workspace / row["fsf_path"]
            before = digest(reference)
            assert before == row["fsf_sha256"]
            candidate = root / f'{row["laps_stamp"]}.lsx'
            write_lsx(candidate, valtime=row["valid_time_utc"], reftime=row["valid_time_utc"])
            with netCDF4.Dataset(reference) as fsf, netCDF4.Dataset(candidate, "r+") as lsx:
                for name in LT1.NAV_VALUES.keys() | {"grid_type", "x_dim", "y_dim"}:
                    source, target = fsf.variables[name], lsx.variables[name]
                    source.set_auto_maskandscale(False)
                    target[:] = source[:]
                    for attr in source.ncattrs():
                        if attr != "_FillValue":
                            target.setncattr(attr, source.getncattr(attr))
            command = [sys.executable, str(CHECKER_PATH), "--inspect-lsx",
                       str(candidate), "--case-id", row["case_id"]]
            run = subprocess.run(command, capture_output=True, text=True)
            result = json.loads(run.stdout)
            assert run.returncode == 0, result
            require_status(result, "PASS", row["case_id"])
            assert result["producer_provenance"] == "NOT_VERIFIED"
            assert before == digest(reference)
            invalid = subprocess.run(command + ["--inspect-lt1", str(candidate)],
                                     capture_output=True, text=True)
            assert invalid.returncode == 2
            assert json.loads(invalid.stdout)["status"] == "FAIL"
    print("Synthetic LSX CLI with four pinned FSF references passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-real-inputs", action="store_true")
    args = parser.parse_args()
    test_lsx_candidate_contract()
    if args.with_real_inputs:
        test_cli_real_references()
    print("LSX candidate contract tests passed")
