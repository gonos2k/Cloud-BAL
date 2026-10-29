import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "tools/cp02_precip_control_mapping.py"
SPEC = importlib.util.spec_from_file_location("cp02_precip_control_mapping", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def valid_points():
    roles = (
        ["lost_hit"] * 4
        + ["retained_hit"] * 4
        + ["removed_false_alarm"] * 4
        + ["RN1_positive_reference_all_forecasts_below5mm"] * 4
        + ["payload_positive_rain_reflectivity_invalid_proxy"] * 2
        + ["payload_positive_snow_reflectivity_invalid_proxy"] * 2
    )
    return [
        {"point_id": f"P{index + 1:02d}", "role": role,
         "latitude": 33.0 + index * 0.01, "longitude": 126.0 + index * 0.01,
         "sourcegrid_point_j_zero_based": index, "sourcegrid_point_i_zero_based": index + 1}
        for index, role in enumerate(roles)
    ]


def test_accepts_exact_twenty_unique_classified_source_columns():
    MODULE.validate_capture_points(valid_points())


def test_rejects_empty_or_short_selection():
    with pytest.raises(ValueError, match="exactly 20"):
        MODULE.validate_capture_points([])


def test_rejects_duplicate_point_id():
    points = valid_points()
    points[-1]["point_id"] = points[0]["point_id"]
    with pytest.raises(ValueError, match="IDs"):
        MODULE.validate_capture_points(points)


def test_rejects_duplicate_original_grid_column():
    points = valid_points()
    points[-1]["sourcegrid_point_j_zero_based"] = points[0]["sourcegrid_point_j_zero_based"]
    points[-1]["sourcegrid_point_i_zero_based"] = points[0]["sourcegrid_point_i_zero_based"]
    with pytest.raises(ValueError, match="source-grid indices"):
        MODULE.validate_capture_points(points)


def test_rejects_wrong_category_counts():
    points = valid_points()
    points[0]["role"] = "retained_hit"
    with pytest.raises(ValueError, match="category counts"):
        MODULE.validate_capture_points(points)


def test_rejects_malformed_point_entry():
    points = valid_points()
    points[0] = None
    with pytest.raises(ValueError, match="entries must be mappings"):
        MODULE.validate_capture_points(points)


def test_rejects_nonfinite_coordinates():
    points = valid_points()
    points[0]["latitude"] = float("nan")
    with pytest.raises(ValueError, match="finite numbers"):
        MODULE.validate_capture_points(points)


def test_rejects_boolean_source_index():
    points = valid_points()
    points[0]["sourcegrid_point_j_zero_based"] = True
    with pytest.raises(ValueError, match="source-grid indices"):
        MODULE.validate_capture_points(points)
