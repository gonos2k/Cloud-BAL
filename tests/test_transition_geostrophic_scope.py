"""Analytic tests of the original/seed geostrophic diagnostic, not science gates."""

from pathlib import Path
import sys
import tempfile
import shutil

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import validate_shadow_diagnostics as validator


def fixture(path):
    shape = (3, 4, 4)
    k, j, i = np.indices(shape)
    phi = (100000 + 512 * i - 1024 * j).astype(np.float32)
    old = np.ones(shape, dtype=bool)
    old[0] = False
    final = np.ones(shape, dtype=bool)
    latitude = np.full(shape[1:], 45.0)
    fields = {f"{prefix}_{name}": np.full(shape, speed, dtype=np.float32)
              for prefix in ("background", "candidate")
              for name, speed in (("u", 10.0), ("v", -5.0))}
    # Existing cells preserve their original reference. Only new cells use seed.
    transition = {"candidate_above_ground": final,
                  "transition_seed_above_ground": final.astype(np.int32)}
    for name, value in (("u", fields["background_u"]),
                        ("v", fields["background_v"]), ("geopotential", phi)):
        transition[f"transition_seed_{name}"] = value.copy()
        for suffix, number in (("valid", 1), ("quality", 0), ("source", 1)):
            transition[f"transition_seed_{name}_{suffix}"] = np.full(shape, number, dtype=np.int32)
    f = 1.458423e-4 * np.sin(np.pi / 4)
    rms = np.sqrt(((-f * -5 + 0.25)**2 + (f * 10 - 0.5)**2) / 2)
    with netCDF4.Dataset(path, "w") as ds:
        for name, size in zip(("z", "y", "x"), shape):
            ds.createDimension(name, size)
        ds.setncatts({
            "pressure_geostrophic_contract": "pressure_geostrophic_original_seed_final_v3",
            "pressure_geostrophic_reference": "original_retained_seed_added_cells_v1",
            "pressure_geostrophic_scope": validator.PRESSURE_GEOSTROPHIC_SCOPE,
            "pressure_geostrophic_units": "m s-2",
            "pressure_geostrophic_science_assessed": np.int32(0),
            "pressure_geostrophic_requested_cells": np.int32(final.size),
            "pressure_geostrophic_evaluated_cells": np.int32(final.size),
            "pressure_geostrophic_partial_coverage": np.int32(0),
            "reference_full_geostrophic_rms": np.float64(rms),
            "candidate_full_geostrophic_rms": np.float64(rms),
        })
        for name in ("geostrophic_validation_support", "geostrophic_stencil_support",
                     "geopotential_support"):
            var = ds.createVariable(name, "i4", ("z", "y", "x"))
            var.units = "1"
            var[:] = 1
        for prefix in ("background", "candidate"):
            var = ds.createVariable(f"{prefix}_geopotential", "f4", ("z", "y", "x"))
            var[:] = np.where(old, phi, np.nan) if prefix == "background" else phi
            for suffix, number in (("valid", 1), ("quality", 0), ("source", 1)):
                var = ds.createVariable(f"{prefix}_geopotential_{suffix}", "i4", ("z", "y", "x"))
                var[:] = old.astype(np.int32) * number if prefix == "background" else number
    for name in ("background_u", "background_v"):
        fields[name][~old] = np.nan
    return old, latitude, fields, transition


def assess(path, inputs, *, include_transition=True):
    old, latitude, fields, transition = inputs
    failures = []
    kwargs = {}
    if include_transition:
        kwargs = {"transition_inputs": transition,
                  "transition_replay": {"candidate_above_ground": transition["candidate_above_ground"]}}
    with netCDF4.Dataset(path) as ds:
        result = validator.validate_pressure_geostrophic_extension(
            ds, old.shape, old, latitude, fields, np.zeros_like(old),
            True, True, True, 8, 2048.0, 2048.0,
            lambda condition, message: failures.append(message) if not condition else None,
            **kwargs,
        )
    return result, failures


def test_transition_reference_and_retained_seed_independence(tmp_path):
    path = tmp_path / "geostrophic.nc"
    inputs = fixture(path)
    result, failures = assess(path, inputs)
    assert result[:2] == (True, True), failures
    assert result[2].all(), "new bottom cells must participate"
    old, _, _, transition = inputs
    for name in ("u", "v", "geopotential"):
        transition[f"transition_seed_{name}"][old] = np.nan
        transition[f"transition_seed_{name}_source"][old] = 0
    result, failures = assess(path, inputs)
    assert result[:2] == (True, True), failures


def test_transition_requires_seed_and_honest_reference(tmp_path):
    path = tmp_path / "geostrophic.nc"
    inputs = fixture(path)
    assert not assess(path, inputs, include_transition=False)[0][1]
    transition = inputs[3]
    transition["transition_seed_u_source"][0, 0, 0] = 0
    assert not assess(path, inputs)[0][1]
    transition["transition_seed_u_source"][0, 0, 0] = 1
    transition["transition_seed_u"][0, 0, 0] += 5
    assert not assess(path, inputs)[0][1], "forged seed must change the reference RMS"


def test_transition_cannot_hide_original_changes_or_downgrade(tmp_path):
    path = tmp_path / "geostrophic.nc"
    inputs = fixture(path)
    inputs[2]["background_u"][1, 1, 1] += 5
    assert not assess(path, inputs)[0][1]
    inputs[2]["background_u"][1, 1, 1] -= 5
    with netCDF4.Dataset(path, "r+") as ds:
        ds.pressure_geostrophic_contract = "pressure_geostrophic_original_final_v2"
        ds.original_full_geostrophic_rms = ds.reference_full_geostrophic_rms
        ds.delncattr("reference_full_geostrophic_rms")
        ds.delncattr("pressure_geostrophic_reference")
    assert not assess(path, inputs)[0][1], "v2 cannot hide new-cell evaluation"


def test_transition_rejects_malformed_seed_and_omitted_support(tmp_path):
    path = tmp_path / "geostrophic.nc"
    inputs = fixture(path)
    transition = inputs[3]
    quality = transition["transition_seed_u_quality"]
    transition["transition_seed_u_quality"] = quality.astype(float) + 0.5
    assert not assess(path, inputs)[0][1]
    transition["transition_seed_u_quality"] = quality
    seed = transition["transition_seed_u"]
    transition["transition_seed_u"] = np.full(seed.shape, "invalid")
    assert not assess(path, inputs)[0][1]
    transition["transition_seed_u"] = seed
    with netCDF4.Dataset(path, "r+") as ds:
        # The halo still covers this cell; explicit Phi support is required.
        ds["geopotential_support"][0, 1, 1] = 0
    assert not assess(path, inputs)[0][1]


def check_probe(source):
    # Upgrade a numerical copy, not a production writer acceptance or new-cell
    # generation. The full transition gate must still reject this artifact.
    with tempfile.TemporaryDirectory(prefix="transition-geostrophic-probe-") as directory:
        path = Path(directory) / "probe.nc"
        shutil.copyfile(source, path)
        with netCDF4.Dataset(path, "r+") as ds:
            ds.pressure_geostrophic_contract = "pressure_geostrophic_original_seed_final_v3"
            ds.pressure_geostrophic_reference = "original_retained_seed_added_cells_v1"
            ds.reference_full_geostrophic_rms = np.float64(ds.original_full_geostrophic_rms)
            ds.delncattr("original_full_geostrophic_rms")
        summary, failures = validator.validate(path)
        assert "pressure transition requires complete exact stored-state replay" in failures, failures
        assert summary["promotion_eligible"] is False
        assert not [failure for failure in failures if "geostrophic" in failure], failures
        with netCDF4.Dataset(path, "r+") as ds:
            ds.reference_full_geostrophic_rms += np.float64(1.0)
        _, failures = validator.validate(path)
        assert any("geostrophic" in failure for failure in failures), failures


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="transition-geostrophic-") as directory:
        for test in (test_transition_reference_and_retained_seed_independence,
                     test_transition_requires_seed_and_honest_reference,
                     test_transition_cannot_hide_original_changes_or_downgrade,
                     test_transition_rejects_malformed_seed_and_omitted_support):
            test(Path(directory))
    if len(sys.argv) > 1:
        check_probe(Path(sys.argv[1]))
    print("Transition geostrophic scope tests passed")
