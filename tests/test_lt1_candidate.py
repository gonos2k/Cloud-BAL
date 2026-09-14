#!/usr/bin/env python3
"""Bounded read-only contract tests for an LT1 temperature candidate."""

from __future__ import annotations

import hashlib
import importlib.util
import csv
import argparse
import json
import shutil
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


VALID_TIME = "2026-08-16T12:00:00Z"
REFERENCE_TIME = "2026-08-16T06:00:00Z"
FILL = np.float32(1.0e37)
LEVELS = np.arange(50.0, 1100.1, 50.0, dtype=np.float32)
SHAPE = (1, 22, 283, 235)
NAV_VALUES = {
    "Nx": np.int16(235),
    "Ny": np.int16(283),
    "La1": np.float32(31.344505),
    "Lo1": np.float32(119.79932),
    "LoV": np.float32(126.0),
    "Latin1": np.float32(30.0),
    "Latin2": np.float32(60.0),
    "Dx": np.float32(5000.0),
    "Dy": np.float32(5000.0),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_chars(variable: netCDF4.Variable, text: str) -> None:
    values = np.full(variable.shape, b" ", dtype="S1")
    encoded = np.frombuffer(text.encode("ascii"), dtype="S1")
    values[0, : min(values.shape[-1], encoded.size)] = encoded[: values.shape[-1]]
    variable[:] = values


def write_navigation(dataset: netCDF4.Dataset, *, dimension_labels: bool = True) -> None:
    for name, value in NAV_VALUES.items():
        dtype = "i2" if name in ("Nx", "Ny") else "f4"
        variable = dataset.createVariable(name, dtype, ("nav",))
        variable[:] = value
    for name, units in (
        ("La1", "degrees_north"),
        ("Lo1", "degrees_east"),
        ("LoV", "degrees_east"),
        ("Latin1", "degrees_north"),
        ("Latin2", "degrees_north"),
        ("Dx", "kilometers"),
        ("Dy", "kilometers"),
    ):
        dataset.variables[name].units = units
    grid_type = dataset.createVariable("grid_type", "S1", ("nav", "namelen"))
    write_chars(grid_type, "secant lambert conformal")
    if dimension_labels:
        x_dim = dataset.createVariable("x_dim", "S1", ("nav", "namelen"))
        y_dim = dataset.createVariable("y_dim", "S1", ("nav", "namelen"))
        write_chars(x_dim, "x")
        write_chars(y_dim, "y")


def write_times(dataset: netCDF4.Dataset, valtime: str, reftime: str) -> None:
    val = dataset.createVariable("valtime", "f8", ("record",))
    ref = dataset.createVariable("reftime", "f8", ("record",))
    val.units = "seconds since (1970-1-1 00:00:00.0)"
    ref.units = "seconds since (1970-1-1 00:00:00.0)"
    val[:] = _epoch(valtime)
    ref[:] = _epoch(reftime)


def _epoch(value: str) -> float:
    from datetime import datetime, timezone

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).timestamp()


def write_common_dimensions(dataset: netCDF4.Dataset, z: int = 22) -> None:
    dataset.createDimension("record", 1)
    dataset.createDimension("z", z)
    dataset.createDimension("x", 235)
    dataset.createDimension("y", 283)
    dataset.createDimension("nav", 1)
    dataset.createDimension("namelen", 132)


def write_scalars(dataset: netCDF4.Dataset, *, wrong: bool = False) -> None:
    values = {"imax": 234 if wrong else 235, "jmax": 283, "kmax": 44, "kdim": 44}
    for name, value in values.items():
        variable = dataset.createVariable(name, "i4", ())
        variable.assignValue(value)


def write_lt1(
    path: Path,
    *,
    fields: tuple[str, ...] = ("t3", "ht"),
    inventory: bool = True,
    dtype: str = "f4",
    wrong_scalars: bool = False,
    dimension_labels: bool = True,
    valtime: str = VALID_TIME,
    reftime: str = VALID_TIME,
) -> None:
    with netCDF4.Dataset(path, "w", format="NETCDF4") as dataset:
        write_common_dimensions(dataset, z=22)
        options = {"zlib": True, "complevel": 1, "fill_value": FILL}
        field_values = {"t3": np.float32(280.0), "ht": np.float32(1000.0)}
        field_units = {"t3": "degrees Kelvin", "ht": "meters"}
        laps_units = {"t3": "K", "ht": "METERS"}
        for name in fields:
            variable = dataset.createVariable(name, dtype, ("record", "z", "y", "x"), **options)
            variable.units = field_units[name]
            variable.LAPS_units = laps_units[name]
            variable.LAPS_var = name.upper()
            variable.lvl_coord = "HPA"
            variable.valid_range = np.asarray(
                (0.0, 100.0 if name == "t3" else 100000.0), dtype=np.float32
            )
            values = np.full(SHAPE, field_values[name], dtype=np.dtype(dtype))
            values[:, -1, :, :] = np.asarray(FILL, dtype=np.dtype(dtype))
            variable[:] = values
            if inventory:
                fcinv = dataset.createVariable(
                    f"{name}_fcinv", "i2", ("record", "z"), fill_value=np.int16(0)
                )
                fcinv[:] = np.int16(1)
        level = dataset.createVariable("level", "f4", ("z",))
        level.units = "hectopascals"
        level[:] = LEVELS
        write_scalars(dataset, wrong=wrong_scalars)
        write_navigation(dataset, dimension_labels=dimension_labels)
        write_times(dataset, valtime, reftime)


def write_fsf(
    path: Path,
    *,
    include_psf: bool = True,
    valtime: str = VALID_TIME,
    reftime: str = REFERENCE_TIME,
    dimension_labels: bool = True,
) -> None:
    with netCDF4.Dataset(path, "w", format="NETCDF4") as dataset:
        write_common_dimensions(dataset, z=1)
        options = {"zlib": True, "complevel": 1, "fill_value": FILL}
        if include_psf:
            psf = dataset.createVariable("psf", "f4", ("record", "z", "y", "x"), **options)
            psf.units = "pascals"
            psf.LAPS_units = "PA"
            psf.LAPS_var = "PSF"
            psf.lvl_coord = "AGL"
            psf.valid_range = np.asarray((0.0, 100000.0), dtype=np.float32)
            psf[:] = np.float32(100000.0)
        tsf = dataset.createVariable("tsf", "f4", ("record", "z", "y", "x"), **options)
        tsf.units = "kelvins"
        tsf.LAPS_units = "K"
        tsf.LAPS_var = "TSF"
        tsf.lvl_coord = "AGL"
        tsf[:] = np.float32(280.0)
        level = dataset.createVariable("level", "f4", ("z",))
        level.units = "hectopascals"
        level[:] = np.float32(0.0)
        write_scalars(dataset)
        write_navigation(dataset, dimension_labels=dimension_labels)
        write_times(dataset, valtime, reftime)


def copy_fixture(source: Path, target: Path) -> Path:
    shutil.copy2(source, target)
    return target


def mutate(path: Path, function) -> Path:
    with netCDF4.Dataset(path, "r+") as dataset:
        function(dataset)
    return path


def inspect(lt1: Path, fsf: Path) -> dict[str, object]:
    before = (digest(lt1), digest(fsf))
    result = CHECKER.inspect_lt1_candidate(lt1, fsf, VALID_TIME, REFERENCE_TIME)
    after = (digest(lt1), digest(fsf))
    assert before == after, "candidate checker modified read-only input"
    return result


def require_status(result: dict[str, object], expected: str, label: str) -> None:
    assert result.get("status") == expected, f"{label}: {result}"
    assert isinstance(result.get("findings"), list), f"{label}: findings missing"


def make_variants(root: Path, pristine_lt1: Path, pristine_fsf: Path) -> dict[str, tuple[Path, Path]]:
    variants: dict[str, tuple[Path, Path]] = {
        "validmaskedbelowground": (pristine_lt1, pristine_fsf),
    }

    activefill = copy_fixture(pristine_lt1, root / "activefill.lt1")
    with netCDF4.Dataset(activefill, "r+") as dataset:
        dataset.variables["t3"].set_auto_mask(False)
        dataset.variables["t3"][0, 0, 0, 0] = FILL
    variants["activefill"] = (activefill, pristine_fsf)

    nan_file = copy_fixture(pristine_lt1, root / "nan.lt1")
    with netCDF4.Dataset(nan_file, "r+") as dataset:
        dataset.variables["t3"].set_auto_mask(False)
        dataset.variables["t3"][0, 0, 0, 0] = np.float32(np.nan)
    variants["nan"] = (nan_file, pristine_fsf)

    negative = copy_fixture(pristine_lt1, root / "negativeT.lt1")
    with netCDF4.Dataset(negative, "r+") as dataset:
        dataset.variables["t3"][0, 0, 0, 0] = np.float32(-1.0)
    variants["negativeT"] = (negative, pristine_fsf)

    missing = root / "missingfield.lt1"
    write_lt1(missing, fields=("t3",))
    variants["missingfield"] = (missing, pristine_fsf)

    units = copy_fixture(pristine_lt1, root / "units.lt1")
    variants["units"] = (mutate(units, lambda ds: setattr(ds.variables["t3"], "units", "celsius")), pristine_fsf)

    wrong_dtype = root / "dtype.lt1"
    write_lt1(wrong_dtype, dtype="f8")
    variants["dtype"] = (wrong_dtype, pristine_fsf)

    reversed_levels = copy_fixture(pristine_lt1, root / "reversedlevels.lt1")
    variants["reversedlevels"] = (mutate(reversed_levels, lambda ds: ds.variables["level"].__setitem__(slice(None), LEVELS[::-1])), pristine_fsf)

    stale = copy_fixture(pristine_lt1, root / "staletime.lt1")
    variants["staletime"] = (mutate(stale, lambda ds: ds.variables["valtime"].__setitem__(0, _epoch("2026-08-16T13:00:00Z"))), pristine_fsf)

    ref = copy_fixture(pristine_lt1, root / "ref.lt1")
    variants["ref"] = (mutate(ref, lambda ds: ds.variables["reftime"].__setitem__(0, _epoch("2026-08-16T05:00:00Z"))), pristine_fsf)

    missing_inventory = root / "missinginventory.lt1"
    write_lt1(missing_inventory, inventory=False)
    variants["missinginventory"] = (missing_inventory, pristine_fsf)

    non1_inventory = copy_fixture(pristine_lt1, root / "non1inventory.lt1")
    mutate(non1_inventory, lambda ds: ds.variables["t3_fcinv"].__setitem__((0, 0), np.int16(0)))
    variants["non1inventory"] = (non1_inventory, pristine_fsf)

    wrong_scalars = root / "wrongscalarcounts.lt1"
    write_lt1(wrong_scalars, wrong_scalars=True)
    variants["wrongscalarcounts"] = (wrong_scalars, pristine_fsf)

    nav_mismatch = copy_fixture(pristine_lt1, root / "gridnavmismatch.lt1")
    mutate(nav_mismatch, lambda ds: ds.variables["Nx"].__setitem__(0, np.int16(234)))
    variants["gridnavmismatch"] = (nav_mismatch, pristine_fsf)

    swapped_dims = copy_fixture(pristine_lt1, root / "swapped_dims.lt1")
    with netCDF4.Dataset(swapped_dims, "r+") as dataset:
        write_chars(dataset.variables["x_dim"], "y")
        write_chars(dataset.variables["y_dim"], "x")
    variants["swapped_dim_labels"] = (swapped_dims, pristine_fsf)

    missing_dims = root / "missing_dims.lt1"
    write_lt1(missing_dims, dimension_labels=False)
    variants["missing_dim_labels"] = (missing_dims, pristine_fsf)

    realistic_psf = copy_fixture(pristine_fsf, root / "realistic_psf.fsf")
    with netCDF4.Dataset(realistic_psf, "r+") as dataset:
        dataset.variables["psf"][:] = np.float32(100975.0)
    variants["realistic_psf"] = (pristine_lt1, realistic_psf)

    low_psfc = copy_fixture(pristine_fsf, root / "low_psfc.fsf")
    with netCDF4.Dataset(low_psfc, "r+") as dataset:
        dataset.variables["psf"][:] = np.float32(50000.0)
    low_lt1 = root / "low_psfc.lt1"
    write_lt1(low_lt1)
    with netCDF4.Dataset(low_lt1, "r+") as dataset:
        for name in ("t3", "ht"):
            dataset.variables[name].set_auto_mask(False)
            dataset.variables[name][:, 10:, :, :] = FILL
    variants["low_psfc_active10"] = (low_lt1, low_psfc)

    psf_fill = copy_fixture(pristine_fsf, root / "psf_fill.fsf")
    with netCDF4.Dataset(psf_fill, "r+") as dataset:
        dataset.variables["psf"].set_auto_mask(False)
        dataset.variables["psf"][0, 0, 0, 0] = FILL
    variants["psf_fill"] = (pristine_lt1, psf_fill)

    psf_nan = copy_fixture(pristine_fsf, root / "psf_nan.fsf")
    with netCDF4.Dataset(psf_nan, "r+") as dataset:
        dataset.variables["psf"].set_auto_mask(False)
        dataset.variables["psf"][0, 0, 0, 0] = np.float32(np.nan)
    variants["psf_nan"] = (pristine_lt1, psf_nan)

    packed_t3 = copy_fixture(pristine_lt1, root / "packed_t3.lt1")
    mutate(packed_t3, lambda ds: setattr(ds.variables["t3"], "scale_factor", np.float32(1.0)))
    variants["packed_t3"] = (packed_t3, pristine_fsf)

    packed_psf = copy_fixture(pristine_fsf, root / "packed_psf.fsf")
    mutate(packed_psf, lambda ds: setattr(ds.variables["psf"], "add_offset", np.float32(0.0)))
    variants["packed_psf"] = (pristine_lt1, packed_psf)

    missing_psf = root / "PSFCmissing.fsf"
    write_fsf(missing_psf, include_psf=False)
    variants["PSFCmissing"] = (pristine_lt1, missing_psf)
    return variants


def manifest_row(case_id: str) -> dict[str, str]:
    manifest = REPO_ROOT / "tests/qbal_real_cases_20260816.tsv"
    with manifest.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if row["case_id"] == case_id:
                return row
    raise AssertionError(f"missing manifest case {case_id}")


def write_synthetic_lt1_for_fsf(path: Path, fsf_path: Path) -> None:
    """Create content-only LT1 data with copied navigation and valid active cells."""
    write_lt1(path)
    with netCDF4.Dataset(fsf_path, "r") as fsf, netCDF4.Dataset(path, "r+") as lt1:
        for name in (*NAV_VALUES, "grid_type", "x_dim", "y_dim"):
            source = np.ma.asarray(fsf.variables[name][:]).filled(b" ")
            lt1.variables[name][:] = source


def run_checker_cli(*arguments: str) -> tuple[int, dict[str, object]]:
    process = subprocess.run(
        [sys.executable, str(CHECKER_PATH), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError(
            f"checker CLI did not return JSON: stdout={process.stdout!r} stderr={process.stderr!r}"
        ) from error
    return process.returncode, result


def test_lt1_candidate_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-bal-lt1-candidate-") as directory:
        root = Path(directory)
        pristine_lt1 = root / "pristine.lt1"
        pristine_fsf = root / "pristine.fsf"
        write_lt1(pristine_lt1)
        write_fsf(pristine_fsf)
        variants = make_variants(root, pristine_lt1, pristine_fsf)
        require_status(inspect(*variants["validmaskedbelowground"]), "PASS", "valid masked below ground")
        require_status(inspect(*variants["realistic_psf"]), "PASS", "realistic PSFC with stale valid_range")
        require_status(inspect(*variants["low_psfc_active10"]), "PASS", "500 hPa PSFC active levels")
        for label, paths in variants.items():
            if label in ("validmaskedbelowground", "realistic_psf", "low_psfc_active10"):
                continue
            require_status(inspect(*paths), "FAIL", label)


def test_lt1_candidate_cli(with_real_reference: bool = False) -> None:
    case_id = "20260816T120000Z"
    row = manifest_row(case_id)
    with tempfile.TemporaryDirectory(prefix="cloud-bal-lt1-cli-") as directory:
        root = Path(directory)
        workspace = root / "workspace"
        copied_manifest = workspace / "tests/qbal_real_cases_20260816.tsv"
        copied_manifest.parent.mkdir(parents=True)
        shutil.copy2(REPO_ROOT / "tests/qbal_real_cases_20260816.tsv", copied_manifest)
        synthetic = root / "synthetic.lt1"
        write_lt1(synthetic)

        status, result = run_checker_cli(
            "--workspace-root", str(workspace),
            "--manifest", str(copied_manifest),
            "--inspect-lt1", str(synthetic),
        )
        assert status == 2 and result["status"] == "FAIL"
        assert any("requires --case-id" in item for item in result["findings"])

        status, result = run_checker_cli(
            "--workspace-root", str(workspace),
            "--manifest", str(copied_manifest),
            "--inspect-lt1", str(synthetic), "--case-id", case_id,
        )
        assert status == 2 and result["status"] == "FAIL"
        assert any("regular non-hardlinked files required" in item for item in result["findings"])

        pristine_fsf = root / "pristine.fsf"
        write_fsf(pristine_fsf)
        copied_fsf = workspace / row["fsf_path"]
        copied_fsf.parent.mkdir(parents=True)
        shutil.copy2(pristine_fsf, copied_fsf)
        status, result = run_checker_cli(
            "--workspace-root", str(workspace),
            "--manifest", str(copied_manifest),
            "--inspect-lt1", str(synthetic), "--case-id", case_id,
        )
        assert status == 2 and result["status"] == "FAIL"
        assert any("FSF does not match pinned case hash" in item for item in result["findings"])

        if not with_real_reference:
            return
        real_workspace = REPO_ROOT.parent
        pinned_fsf = real_workspace / row["fsf_path"]
        if not pinned_fsf.is_file():
            raise AssertionError(f"explicit real-reference test input is missing: {pinned_fsf}")
        real_synthetic = root / "synthetic-real-reference.lt1"
        write_synthetic_lt1_for_fsf(real_synthetic, pinned_fsf)
        status, result = run_checker_cli(
            "--workspace-root", str(real_workspace),
            "--manifest", str(REPO_ROOT / "tests/qbal_real_cases_20260816.tsv"),
            "--inspect-lt1", str(real_synthetic), "--case-id", case_id,
        )
        assert status == 0, result
        assert result["status"] == "PASS"
        assert result["scope"] == "LT1_CONTENT_ONLY"
        assert result["generation_status"] == "BLOCKED"
        assert result["promotion_allowed"] is False
        assert result["case_id"] == case_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-real-reference", action="store_true")
    args = parser.parse_args()
    test_lt1_candidate_contract()
    test_lt1_candidate_cli(args.with_real_reference)
    print("LT1 candidate contract tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
