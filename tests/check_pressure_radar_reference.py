#!/usr/bin/env python3
"""Compare actual Fortran reconstruction fixtures with the independent reference."""
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pressure_radar_reference import (
    RadarReferenceConfig, RadarReferenceError, transport_precipitation_flux,
    dry_air_density, moist_gas_density, terminal_velocity,
    omega_to_w,
)

CELL_FIELDS = ("pressure", "temperature", "vapor", "u", "v", "w", "domain",
               "observed", "no_echo", "phase", "zlinear", "rain", "snow", "graupel")
OUTPUT_FIELDS = ("phase", "zlinear", "rain", "snow", "graupel")
LEDGER_FIELDS = ("input", "deposited", "suspended", "boundary_exit", "terrain_intercept",
                 "observation_blocked", "no_echo_blocked", "microphysical_loss")


def read_inputs(path):
    cases = {}
    for line in path.read_text().splitlines():
        row = line.split()
        if not row or row[0] == "FORMAT":
            continue
        tag = row[0]
        if tag == "CASE":
            name = row[1]
            nx, ny, nz = map(int, row[2:])
            assert name not in cases
            case = {key: np.zeros((nz, ny, nx)) for key in CELL_FIELDS}
            case.update(dx=np.zeros((ny, nx)), dy=np.zeros((ny, nx)),
                        pressure_surface=np.zeros((ny, nx)),
                        pressure_interface=np.zeros((nz + 1, ny, nx)),
                        level_spacing_dp=np.zeros((nz - 1, ny, nx)),
                        cell_dp=np.zeros((nz, ny, nx)))
            cases[name] = case
        elif tag == "CONFIG":
            case["config"] = RadarReferenceConfig(
                maximum_horizontal_substep=float(row[1]),
                maximum_transport_substeps=int(row[2]),
                minimum_relative_fall_speed=float(row[3]))
        elif tag == "GRID":
            i, j = (int(value) - 1 for value in row[1:3])
            for key, value in zip(("dx", "dy", "pressure_surface"), row[3:]):
                case[key][j, i] = float(value)
        else:
            i, j, k = (int(value) - 1 for value in row[1:4])
            if tag == "INTERFACE":
                case["pressure_interface"][k:k+2, j, i] = list(map(float, row[4:6]))
                case["cell_dp"][k, j, i] = float(row[6])
            elif tag == "SPACING":
                case["level_spacing_dp"][k, j, i] = float(row[4])
            elif tag == "CELL":
                assert len(row[4:]) == len(CELL_FIELDS)
                for key, value in zip(CELL_FIELDS, row[4:]):
                    case[key][k, j, i] = (value == "T") if key in (
                        "domain", "observed", "no_echo") else float(value)
            else:
                raise AssertionError(f"unknown input record: {tag}")
    for case in cases.values():
        for key in CELL_FIELDS[:6]:
            case[key] = case[key].astype(np.float32)
        for key in ("domain", "observed", "no_echo"):
            case[key] = case[key].astype(bool)
        case["phase"] = case["phase"].astype(np.int32)
    return cases


def read_outputs(path, cases):
    outputs = {}
    for line in path.read_text().splitlines():
        row = line.split()
        if not row or row[0] in ("FORMAT", "ENDCASE"):
            continue
        if row[0] == "RESULT":
            name = row[1]
            assert name in cases and name not in outputs
            result = {key: np.zeros_like(cases[name][key]) for key in OUTPUT_FIELDS}
            result.update(status=int(row[2]), substeps=int(row[3]),
                          ledger=np.asarray(row[4:], dtype=np.float64))
            outputs[name] = result
        elif row[0] == "OUT":
            i, j, k = (int(value) - 1 for value in row[1:4])
            for key, value in zip(OUTPUT_FIELDS, row[4:]):
                result[key][k, j, i] = float(value)
        else:
            raise AssertionError(f"unknown output record: {row[0]}")
    assert set(outputs) == set(cases)
    return outputs


def check(input_path, output_path):
    p = np.array([90000.0, 70000.0], dtype=np.float32).reshape(2, 1, 1)
    t = np.full_like(p, 279.1)
    rv = np.full_like(p, 0.0137)
    omega = np.full_like(p, 0.31781632)
    density = p.astype(float) * (1.0 + rv.astype(float)) / (
        287.05 * t.astype(float) * (1.0 + rv.astype(float) / 0.622))
    w, valid = omega_to_w(omega, p, t, rv)
    assert w.dtype == np.float32 and np.all(valid)
    np.testing.assert_array_equal(w, (-omega.astype(float) / (density * 9.80665)).astype(np.float32))
    cases = read_inputs(input_path)
    outputs = read_outputs(output_path, cases)
    passed = rejected = 0
    actual_results = {}
    for name, case in cases.items():
        expected = outputs[name]
        original = {key: value.copy() for key, value in case.items() if isinstance(value, np.ndarray)}
        try:
            actual = transport_precipitation_flux(**case)
        except RadarReferenceError:
            assert expected["status"] != 20, f"reference rejected valid Fortran case: {name}"
            for field in OUTPUT_FIELDS:
                np.testing.assert_array_equal(expected[field], case[field], err_msg=f"{name}: rollback {field}")
            rejected += 1
            continue
        finally:
            for key, before in original.items():
                np.testing.assert_array_equal(case[key], before, err_msg=f"{name}: immutable input {key}")
        assert expected["status"] == 20, f"reference accepted rejected Fortran case: {name}"
        for field in OUTPUT_FIELDS:
            np.testing.assert_allclose(getattr(actual, field), expected[field], rtol=2e-11,
                                       atol=1e-13, err_msg=f"{name}: {field}")
        ledger = [getattr(actual.ledger, field) for field in LEDGER_FIELDS]
        np.testing.assert_allclose(ledger, expected["ledger"], rtol=2e-11, atol=1e-10,
                                   err_msg=f"{name}: ledger")
        assert actual.ledger.maximum_required_substeps == expected["substeps"], name
        if name == "horizontal_substeps":
            assert_endpoint_footprint(case, actual, phase_code=1, q_name="rain")
            assert_endpoint_centroid(case, actual, phase_code=1, q_name="rain")
        elif name == "horizontal_substeps_fine":
            assert_endpoint_footprint(case, actual, phase_code=1, q_name="rain")
            assert_endpoint_centroid(case, actual, phase_code=1, q_name="rain")
        elif name == "crossing_sources":
            assert_crossing_source_identity(case, actual)
        elif name == "boundary_exit":
            assert_boundary_clipping(case, actual)
        actual_results[name] = actual
        passed += 1
    assert_substep_equivalence(actual_results)
    assert passed == 11 and rejected == 3, (passed, rejected)
    print(f"Independent radar transport reference: {passed} valid / {rejected} rejected cases passed")


def endpoint_scatter(case, *, k, phase_code, q_name):
    """Compute one source level's frozen-source endpoint scatter analytically."""
    ny, nx = case["dx"].shape
    flux = np.zeros((ny, nx), dtype=np.float64)
    zflux = np.zeros((ny, nx), dtype=np.float64)
    boundary = 0.0
    input_flux = 0.0
    sources = np.argwhere(case[q_name][k] > 0.0)
    assert sources.size, f"no {q_name} source at level {k}"
    source_endpoints = []
    for y, x in sources:
        y, x = int(y), int(x)
        p = float(case["pressure"][k, y, x])
        t = float(case["temperature"][k, y, x])
        rv = float(case["vapor"][k, y, x])
        z = max(float(case["zlinear"][k, y, x]), 1.0e-12)
        relative = terminal_velocity(phase_code, p, t, 10.0 * np.log10(z)) - float(case["w"][k, y, x])
        source_flux = dry_air_density(p, t, rv) * float(case[q_name][k, y, x]) * max(relative, 0.0)
        source_flux *= float(case["dx"][y, x]) * float(case["dy"][y, x])
        input_flux += source_flux
        if relative <= float(case["config"].minimum_relative_fall_speed):
            continue
        if case["domain"][k - 1, y, x]:
            pressure_separation = float(case["level_spacing_dp"][k - 1, y, x])
        else:
            pressure_separation = float(case["pressure_interface"][k, y, x] - case["pressure"][k, y, x])
        dz = pressure_separation / (moist_gas_density(p, t, rv) * 9.80665)
        dt = dz / relative
        xstep = float(case["u"][k, y, x]) * dt / float(case["dx"][y, x])
        ystep = float(case["v"][k, y, x]) * dt / float(case["dy"][y, x])
        endpoint_x = (x + 1.0) + xstep
        endpoint_y = (y + 1.0) + ystep
        source_endpoints.append((endpoint_x, endpoint_y))
        base_x = int(np.floor(endpoint_x)) - 1
        base_y = int(np.floor(endpoint_y)) - 1
        fx = endpoint_x - np.floor(endpoint_x)
        fy = endpoint_y - np.floor(endpoint_y)
        for dy_offset in (0, 1):
            for dx_offset in (0, 1):
                weight = ((1.0 - fx) if dx_offset == 0 else fx) * ((1.0 - fy) if dy_offset == 0 else fy)
                yy, xx = base_y + dy_offset, base_x + dx_offset
                if yy < 0 or yy >= ny or xx < 0 or xx >= nx:
                    boundary += weight * source_flux
                else:
                    flux[yy, xx] += weight * source_flux
                    zflux[yy, xx] += weight * source_flux * z
    q_expected = np.zeros((ny, nx), dtype=np.float64)
    z_expected = np.zeros((ny, nx), dtype=np.float64)
    for y, x in zip(*np.where(flux > 0.0)):
        zratio = max(float(zflux[y, x] / flux[y, x]), 1.0e-12)
        p = float(case["pressure"][k - 1, y, x])
        t = float(case["temperature"][k - 1, y, x])
        rv = float(case["vapor"][k - 1, y, x])
        relative = terminal_velocity(phase_code, p, t, 10.0 * np.log10(zratio)) - float(case["w"][k - 1, y, x])
        if relative > float(case["config"].minimum_relative_fall_speed):
            q_expected[y, x] = flux[y, x] / (
                float(case["dx"][y, x]) * float(case["dy"][y, x]) *
                dry_air_density(p, t, rv) * relative)
        z_expected[y, x] = zratio
    return q_expected, z_expected, flux, zflux, boundary, input_flux, source_endpoints


def assert_endpoint_footprint(case, result, *, phase_code, q_name):
    """Require every in-domain endpoint weight, including tiny edge weights."""
    k = int(np.argwhere(case[q_name] > 0.0)[0][0])
    q_expected, z_expected, _, _, _, _, _ = endpoint_scatter(
        case, k=k, phase_code=phase_code, q_name=q_name)
    np.testing.assert_allclose(getattr(result, q_name)[k - 1], q_expected, rtol=2e-11, atol=1e-13,
                               err_msg=f"analytic endpoint {q_name} footprint")
    occupied = q_expected > 0.0
    assert np.count_nonzero(occupied) == 4, f"expected complete bilinear footprint, got {occupied.sum()} cells"
    np.testing.assert_allclose(result.zlinear[k - 1][occupied], z_expected[occupied], rtol=2e-11, atol=1e-10,
                               err_msg="analytic endpoint reflectivity footprint")


def assert_endpoint_centroid(case, result, *, phase_code, q_name):
    k, j, i = (int(value) for value in np.argwhere(case[q_name] > 0.0)[0])
    q_expected, _, flux_expected, _, _, _, endpoints = endpoint_scatter(
        case, k=k, phase_code=phase_code, q_name=q_name)
    assert len(endpoints) == 1
    endpoint_x, endpoint_y = endpoints[0]
    rates = np.zeros_like(flux_expected)
    for y, x in zip(*np.where(getattr(result, q_name)[k - 1] > 0.0)):
        p = float(case["pressure"][k - 1, y, x])
        t = float(case["temperature"][k - 1, y, x])
        rv = float(case["vapor"][k - 1, y, x])
        z = max(float(result.zlinear[k - 1, y, x]), 1.0e-12)
        relative = terminal_velocity(phase_code, p, t, 10.0 * np.log10(z)) - float(case["w"][k - 1, y, x])
        rates[y, x] = getattr(result, q_name)[k - 1, y, x] * dry_air_density(p, t, rv) * relative * (
            float(case["dx"][y, x]) * float(case["dy"][y, x]))
    centroid_x = float(np.sum(rates * (np.arange(rates.shape[1])[None, :] + 1.0)) / np.sum(rates))
    centroid_y = float(np.sum(rates * (np.arange(rates.shape[0])[:, None] + 1.0)) / np.sum(rates))
    np.testing.assert_allclose((centroid_x, centroid_y), (endpoint_x, endpoint_y), rtol=0.0, atol=2e-10,
                               err_msg=f"{q_name}: endpoint centroid")
    np.testing.assert_allclose(np.sum(rates), np.sum(flux_expected), rtol=2e-11, atol=1e-10,
                               err_msg=f"{q_name}: endpoint rate closure")


def assert_crossing_source_identity(case, result):
    """Same-phase sources must carry their own reflectivity through a crossing."""
    k = int(np.argwhere(case["rain"] > 0.0)[0][0])
    q_expected, z_expected, _, _, _, _, endpoints = endpoint_scatter(
        case, k=k, phase_code=1, q_name="rain")
    np.testing.assert_allclose(result.rain[k - 1], q_expected, rtol=2e-11, atol=1e-13,
                               err_msg="crossing source endpoint superposition")
    assert len(endpoints) == 2
    for endpoint_x, endpoint_y in endpoints:
        x = int(round(endpoint_x)) - 1
        y = int(round(endpoint_y)) - 1
        assert result.rain[k - 1, y, x] > 0.0
        np.testing.assert_allclose(result.zlinear[k - 1, y, x], z_expected[y, x], rtol=2e-11, atol=1e-10)
    # The two 1-D paths cross near the middle, but the endpoint z values must
    # remain distinct rather than being mixed by an intermediate remap.
    assert not np.isclose(result.zlinear[k - 1, 0, 1], result.zlinear[k - 1, 0, 3])


def assert_boundary_clipping(case, result):
    """Check analytic out-of-domain bilinear rate accounting."""
    k = int(np.argwhere(case["rain"] > 0.0)[0][0])
    _, _, flux, _, boundary, input_flux, _ = endpoint_scatter(
        case, k=k, phase_code=1, q_name="rain")
    np.testing.assert_allclose(result.ledger.boundary_exit, boundary, rtol=2e-11, atol=1e-10,
                               err_msg="analytic boundary clipping rate")
    np.testing.assert_allclose(result.ledger.observation_blocked, np.sum(flux), rtol=2e-11, atol=1e-10,
                               err_msg="analytic retained boundary rate")
    np.testing.assert_allclose(result.ledger.input, input_flux, rtol=2e-11, atol=1e-10,
                               err_msg="analytic boundary clipping input rate")
    assert np.sum(flux) > 0.0
    assert np.sum(result.rain[k - 1]) == 0.0


def assert_substep_equivalence(actual_results):
    coarse = actual_results["horizontal_substeps"]
    fine = actual_results["horizontal_substeps_fine"]
    for field in OUTPUT_FIELDS:
        np.testing.assert_allclose(getattr(coarse, field), getattr(fine, field), rtol=2e-11, atol=1e-13,
                                   err_msg=f"substep-invariant {field}")
    np.testing.assert_allclose(
        [getattr(coarse.ledger, field) for field in LEDGER_FIELDS],
        [getattr(fine.ledger, field) for field in LEDGER_FIELDS],
        rtol=2e-11, atol=1e-10, err_msg="substep-invariant ledger")
    assert coarse.ledger.maximum_required_substeps == 3
    assert fine.ledger.maximum_required_substeps == 4


if __name__ == "__main__":
    check(Path(sys.argv[1]), Path(sys.argv[2]))
