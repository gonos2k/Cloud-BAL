from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import netCDF4

MODULE = Path(__file__).resolve().parents[1] / "tools/pr94_cloud_response.py"
spec = importlib.util.spec_from_file_location("pr94_cloud_response", MODULE)
cloud = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(cloud)


def test_pattern_metrics_reconstructs_projection_and_orthogonal_residual() -> None:
    initial = np.array([1.0, 2.0, 0.0, 0.0])
    current = np.array([-1.0, -2.0, 3.0, 4.0])

    metrics = cloud.pattern_metrics(initial, current)

    assert metrics["cosine_delta_t_vs_delta0"] < 0
    assert metrics["projection_delta_t_onto_delta0"] == -1.0
    assert np.isclose(metrics["orthogonal_residual_rms"], np.sqrt(6.25))
    reconstructed = metrics["projection_delta_t_onto_delta0"] * initial
    residual = current - reconstructed
    assert np.isclose(np.dot(initial, residual), 0.0)
    assert np.allclose(reconstructed + residual, current)


def test_support_and_chebyshev_buffers_are_fixed_and_clipped() -> None:
    targets = []
    remaining = 613
    for j, i in ((1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (3, 2), (4, 1), (4, 2),
                 (5, 1), (5, 2), (6, 1), (6, 2), (7, 1), (7, 2), (8, 1), (8, 2)):
        count = min(39, remaining)
        targets.append({"target_i0": i + 1, "target_j0": j + 1,
                        "native_levels": [{"native_eta_level0": k,
                                           "composed_qc_source_links": [{}] if k < count else []}
                                          for k in range(39)]})
        remaining -= count

    masks = cloud.make_masks({"targets": targets}, (39, 10, 10))

    assert masks["original_613_native_support"].sum() == 613
    assert masks["original_613_native_support"].any(axis=0).sum() == 16
    assert masks["fixed_2_cell_chebyshev_buffer"].shape == (39, 10, 10)
    buffered = masks["fixed_5_cell_chebyshev_buffer"][0]
    assert buffered[0, 0]
    assert buffered[0, 6]
    assert buffered[0, 7]
    assert not buffered[0, 8]
    assert not buffered[0, 9]
    assert masks["full_active_history_domain"].all()


def test_vector_metrics_uses_same_location_values() -> None:
    off = np.array([1.0, -1.0, 2.0])
    coupled = np.array([2.0, 1.0, 0.0])

    metrics = cloud.vector_metrics(off, coupled)

    assert np.isclose(metrics["delta_rms"], np.sqrt(3.0))
    assert np.isclose(metrics["delta_mean"], 1.0 / 3.0)
    assert metrics["delta_max_abs"] == 2.0


def test_horizontal_translation_scan_recovers_shift_on_unchanged_support() -> None:
    baseline = np.zeros((3, 12, 12), dtype=float)
    support = np.zeros_like(baseline, dtype=bool)
    points = [(0, 5, 5, 2.0), (1, 6, 6, -1.0), (2, 5, 6, 3.0)]
    for k, j, i, value in points:
        support[k, j, i] = True
        baseline[k, j, i] = value
    current = np.zeros_like(baseline)
    expected_lag = (-1, 2)
    for k, j, i, value in points:
        current[k, j + expected_lag[0], i + expected_lag[1]] = value

    result = cloud.horizontal_translation_scan(baseline, current, support, max_shift=5)

    best = result["best_uncentered_cosine"]
    assert result["search_domain"]["support_native_values"] == 3
    assert best["lag_dj"] == expected_lag[0]
    assert best["lag_di"] == expected_lag[1]
    assert best["uncentered_cosine"] == 1.0
    assert best["aligned_difference_rms"] == 0.0
    assert all(row["sample_count"] == 3 for row in result["all_lags"])


def test_horizontal_translation_scan_refuses_boundary_crop_and_wrap() -> None:
    baseline = np.zeros((1, 8, 8), dtype=float)
    support = np.zeros_like(baseline, dtype=bool)
    support[0, 0, 0] = True
    baseline[0, 0, 0] = 1.0
    with np.testing.assert_raises_regex(ValueError, "no wrap or crop"):
        cloud.horizontal_translation_scan(baseline, baseline, support, max_shift=1)


def test_fixed_coordinate_samples_do_not_follow_a_moving_maximum() -> None:
    off0 = np.zeros((1, 1, 3)); on0 = np.array([[[1.0, 5.0, 0.0]]])
    off1 = np.zeros((1, 1, 3)); on1 = np.array([[[9.0, 0.0, 2.0]]])
    selected_at_t60 = (0, 0, 1)

    series = [cloud.sample_coordinate(off, on, selected_at_t60)
              for off, on in ((off0, on0), (off1, on1))]

    assert [row["delta"] for row in series] == [5.0, 0.0]
    assert float(np.max(np.abs(on1 - off1))) == 9.0


def test_support_refuses_outer_ring_negative_index_wrapping() -> None:
    composition = {"targets": [{"target_i0": 0, "target_j0": 2, "native_levels": []}]}
    with np.testing.assert_raises_regex(ValueError, "cropped active grid"):
        cloud.make_masks(composition, (39, 10, 10))


def _wind_history(path: Path, field: str, attribute: str, value: float) -> None:
    with netCDF4.Dataset(path, "w") as ds:
        for name, size in (("Time", 1), ("k", 2), ("j", 4), ("i", 4)):
            ds.createDimension(name, size)
        for name in ("U", "V", "W"):
            kwargs = {"fill_value": value} if attribute == "_FillValue" else {}
            var = ds.createVariable(name, "f8", ("Time", "k", "j", "i"), **kwargs)
            var[:] = 2.0
            if attribute == "missing_value":
                var.missing_value = value
            if name == field:
                var[0, 0, 1, 1] = value


def test_face_winds_validate_each_field_and_sentinel_attribute(tmp_path: Path) -> None:
    for field in ("U", "V", "W"):
        for attribute, value in (("_FillValue", -8888.0), ("missing_value", -9999.0)):
            path = tmp_path / f"{field}_{attribute}.nc"
            _wind_history(path, field, attribute, value)
            with np.testing.assert_raises_regex(ValueError, f"{field} contains declared {attribute} sentinel"):
                cloud.read_face_winds(path, 0)

    valid_path = tmp_path / "valid.nc"
    _wind_history(valid_path, "U", "missing_value", -9999.0)
    with netCDF4.Dataset(valid_path, "a") as ds:
        ds["U"][0, 0, 1, 1] = 2.0
    valid = cloud.read_face_winds(valid_path, 0)
    assert all(np.all(values == 2.0) for values in valid.values())

    for field in ("U", "V", "W"):
        for bad in (np.nan, np.inf):
            path = tmp_path / f"{field}_{'nan' if np.isnan(bad) else 'inf'}.nc"
            _wind_history(path, field, "missing_value", -9999.0)
            with netCDF4.Dataset(path, "a") as ds:
                ds[field][0, 0, 1, 1] = bad
            with np.testing.assert_raises_regex(ValueError, f"{field} contains nonfinite"):
                cloud.read_face_winds(path, 0)

    # Identical sentinels in both arms must fail at the reader before subtraction.
    for arm in ("OFF", "COUPLED"):
        path = tmp_path / f"{arm}_sentinel.nc"
        _wind_history(path, "U", "missing_value", -9999.0)
        with np.testing.assert_raises_regex(ValueError, "U contains declared missing_value sentinel"):
            cloud.read_face_winds(path, 0)
