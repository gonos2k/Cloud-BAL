import copy
import importlib.util
from pathlib import Path
import struct

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "docs/evidence/cp02_radar_inputs_20261028/analyze_radar_inputs.py"
SPEC = importlib.util.spec_from_file_location("analyze_radar_inputs", SCRIPT)
analyzer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyzer)
INNER_EVIDENCE = ROOT / "docs/evidence/cp02_inner_capture_20261028/hydro_capture.json.gz"


def scalar(width, type_name, raw):
    return {"status": "readable", "type": type_name, "raw_bytes_le_hex": raw.hex()}


def radar_array(name, value=0):
    kind, width = analyzer.RADAR_ARRAYS[name]
    if kind == "real":
        raw = struct.pack("<d", float(value))
        type_name = "real(kind=8)"
    elif kind == "logical":
        raw = struct.pack("<i", int(bool(value)))
        type_name = "logical(kind=4)"
    else:
        raw = struct.pack("<i", int(value))
        type_name = "integer(kind=4)"
    return {
        "status": "readable", "type": type_name, "bounds_i_j_k": [[1, 235], [1, 283], [1, 22]],
        "points": [{"fortran_i": i, "fortran_j": j,
                    "levels": [{"fortran_k": k, **scalar(width, type_name, raw)} for k in range(1, 23)]}
                   for i, j in canonical_points()],
    }


def typed_array(kind, width, value):
    if kind == "real" and width == 4:
        raw, type_name = struct.pack("<f", float(value)), "real(kind=4)"
    elif kind == "real":
        raw, type_name = struct.pack("<d", float(value)), "real(kind=8)"
    else:
        raw = struct.pack("<i", int(bool(value)) if kind == "logical" else int(value))
        type_name = f"{kind}(kind={width})"
    return {"status": "readable", "type": type_name, "bounds_i_j_k": [[1, 235], [1, 283], [1, 22]],
            "points": [{"fortran_i": i, "fortran_j": j,
                        "levels": [{"fortran_k": k, **scalar(width, type_name, raw)} for k in range(1, 23)]}
                       for i, j in canonical_points()]}


def canonical_points():
    capture = analyzer.INNER.read_capture(INNER_EVIDENCE)
    state = next(r for r in capture["records"] if r["stage"] == "derive_entry_state_in")
    return [(point["fortran_i"], point["fortran_j"]) for point in state["points"]]


def fake_background():
    return {(i, j, k): {"losthit_rank": str(n), "lat": "0", "lon": "0",
                        "background_rain": "0", "background_snow": "0"}
            for n, (i, j) in enumerate(canonical_points(), 1) for k in range(1, 23)}


def fake_capture():
    capture = analyzer.INNER.read_capture(INNER_EVIDENCE)
    original = next(r for r in capture["records"] if r["stage"] == "derive_entry_state_in")
    state = copy.deepcopy(original)
    state["stage"] = "actual_input_state"
    for point in state["points"]:
        for level in point["levels"]:
            level["above_ground"] = {"value": False, "raw_bytes_le_hex": "00000000"}
    for record in capture["records"]:
        if record["stage"] in ("diagnose_radar_cells_pre", "diagnose_radar_cells_post",
                                "publish_hydrometeor_candidate_pre", "publish_hydrometeor_candidate_post"):
            pre = record["stage"].endswith("_pre")
            label = record["stage"][:-4] if pre else record["stage"][:-5]
            radar = {"inputs": {name: radar_array(name) for name in analyzer.RADAR_ARRAYS}}
            if pre:
                radar["actual_input_state"] = copy.deepcopy(state)
                radar["cfg"] = {"status": "readable", "fields": {"example": scalar(4, "integer(kind=4)", b"\0" * 4)}}
                if record["stage"] == "diagnose_radar_cells_pre":
                    radar["actual_observation_state"] = {
                        "radar_reflectivity": {"value": typed_array("real", 4, 0),
                                               "valid": typed_array("logical", 4, False),
                                               "quality": typed_array("integer", 4, 0),
                                               "source": typed_array("integer", 4, 0)},
                        "precipitation_phase": {"value": typed_array("integer", 4, 0),
                                                "valid": typed_array("logical", 4, False),
                                                "quality": typed_array("integer", 4, 0),
                                                "source": typed_array("integer", 4, 0)},
                    }
                radar["status_storage"] = {"slot_address": "0x900", "pointer_value": "0x1000",
                                           "raw_bytes_le_hex": "0010000000000000"}
            else:
                radar["status_return"] = {"status": "readable", "type": "integer(kind=4)",
                                          "address": "0x1000", "raw_bytes_le_hex": "14000000", "value": 20}
            record["radar"] = radar
    capture["radar_local_records"] = []
    return capture


def test_joins_all_canonical_samples_and_marks_unexecuted_local_calls_not_captured():
    report = analyzer.validate_radar(fake_capture(), fake_background())
    assert report["sample_count"] == 440
    assert report["observed_hit_count"] == 0
    assert report["profiles"][0]["density_entry.status"] == "NOT_CAPTURED"
    assert report["profiles"][0]["density_entry.pressure"] == "NOT_CAPTURED"
    assert "density_entry.rho_d" not in report["profiles"][0]


def test_observed_hit_requires_local_actual_operand_records():
    capture = fake_capture()
    for stage in ("diagnose_radar_cells_post", "publish_hydrometeor_candidate_pre"):
        radar = next(r for r in capture["records"] if r["stage"] == stage)["radar"]
        first = radar["inputs"]["radar_observed"]["points"][0]["levels"][0]
        first["raw_bytes_le_hex"] = "01000000"
    with pytest.raises(ValueError, match="density-entry keys differ from observed radar hits"):
        analyzer.validate_radar(capture, fake_background())


def test_status_return_raw_bytes_must_match_success_value():
    capture = fake_capture()
    radar = next(r for r in capture["records"] if r["stage"] == "diagnose_radar_cells_post")["radar"]
    radar["status_return"]["raw_bytes_le_hex"] = "01000000"
    with pytest.raises(ValueError, match="raw bytes disagree"):
        analyzer.validate_radar(capture, fake_background())


def test_empty_boundary_array_rejected():
    capture = fake_capture()
    radar = next(r for r in capture["records"] if r["stage"] == "publish_hydrometeor_candidate_pre")["radar"]
    radar["inputs"]["phase_uncertain"]["points"] = []
    with pytest.raises(ValueError, match="expected 20 canonical points"):
        analyzer.validate_radar(capture, fake_background())


def test_above_ground_without_observed_radar_does_not_infer_local_work():
    capture = fake_capture()
    state = next(r for r in capture["records"] if r["stage"] == "diagnose_radar_cells_pre")["radar"]["actual_input_state"]
    state["points"][0]["levels"][0]["above_ground"] = {"value": True, "raw_bytes_le_hex": "01000000"}
    report = analyzer.validate_radar(capture, fake_background())
    assert report["local_record_counts"]["density_entry"] == 0


def test_visited_local_chain_requires_successful_complete_order():
    capture = fake_capture()
    i, j = canonical_points()[0]

    def values(names):
        result = {}
        for name in names:
            width = analyzer.LOCAL_WIDTHS[name]
            if name == "allocation_status":
                raw, type_name = struct.pack("<i", 20), "integer(kind=4)"
            else:
                raw, type_name = struct.pack("<d", 0.5), "real(kind=8)"
            result[name] = scalar(width, type_name, raw)
        return result

    stages = analyzer.LOCAL_FIELDS
    for stage in ("diagnose_radar_cells_post", "publish_hydrometeor_candidate_pre"):
        observed = next(r for r in capture["records"] if r["stage"] == stage)["radar"]["inputs"]["radar_observed"]
        point = next(p for p in observed["points"] if (p["fortran_i"], p["fortran_j"]) == (i, j))
        point["levels"][0]["raw_bytes_le_hex"] = "01000000"
    capture["radar_local_records"] = [
        {"stage": stage, "fortran_i": i, "fortran_j": j, "fortran_k": 1,
         "parent_derive_call": 1, "diagnose_frame_address": "0x1234", "values": values(names)}
        for stage, names in stages.items()
    ]
    report = analyzer.validate_radar(capture, fake_background())
    assert report["local_record_counts"] == {"density_entry": 1, "density_return": 1,
                                             "phase_allocation_return": 1, "store_after": 1}
    capture["radar_local_records"].pop()
    with pytest.raises(ValueError, match="missing subsequent store_after"):
        analyzer.validate_radar(capture, fake_background())


def test_local_rho_and_allocation_returns_must_remain_in_order():
    capture = fake_capture()
    i, j = canonical_points()[0]
    stages = analyzer.LOCAL_FIELDS
    records = [{"stage": stage, "fortran_i": i, "fortran_j": j, "fortran_k": 1,
                "parent_derive_call": 1, "diagnose_frame_address": "0x1234",
                "values": {name: scalar(analyzer.LOCAL_WIDTHS[name],
                                        "integer(kind=4)" if name == "allocation_status" else "real(kind=8)",
                                        struct.pack("<i", 20) if name == "allocation_status" else struct.pack("<d", 0.5))
                           for name in fields}}
               for stage, fields in stages.items()]
    for stage in ("diagnose_radar_cells_post", "publish_hydrometeor_candidate_pre"):
        radar = next(r for r in capture["records"] if r["stage"] == stage)["radar"]
        point = next(p for p in radar["inputs"]["radar_observed"]["points"] if (p["fortran_i"], p["fortran_j"]) == (i, j))
        point["levels"][0]["raw_bytes_le_hex"] = "01000000"
    capture["radar_local_records"] = [records[0], records[2], records[1], records[3]]
    with pytest.raises(ValueError, match="phase_allocation_return did not follow density_return"):
        analyzer.validate_radar(capture, fake_background())


def test_duplicate_local_record_rejected():
    capture = fake_capture()
    i, j = canonical_points()[0]
    capture["radar_local_records"] = [
        {"stage": "density_entry", "fortran_i": i, "fortran_j": j, "fortran_k": 1,
         "parent_derive_call": 1, "diagnose_frame_address": "0x1234",
         "values": {name: scalar(width, "real(kind=8)", b"\0" * width)
                    for name, width in (("pressure", 8), ("temperature", 8), ("vapor", 8))}}
    ] * 2
    with pytest.raises(ValueError, match="duplicate sample"):
        analyzer.validate_radar(capture, fake_background())


def test_real4_raw_value_is_decoded_as_finite_float():
    value = scalar(4, "real(kind=4)", struct.pack("<f", 12.5))
    assert analyzer.raw_value(value, 4, "reflectivity", "real") == 12.5
    invalid = scalar(4, "real(kind=4)", bytes.fromhex("0000c07f"))
    with pytest.raises(ValueError, match=r"non-finite REAL\*4"):
        analyzer.raw_value(invalid, 4, "reflectivity", "real")


def test_actual_observation_state_raw_types_and_profiles_are_validated():
    capture = fake_capture()
    pre = next(r for r in capture["records"] if r["stage"] == "diagnose_radar_cells_pre")["radar"]
    pre["actual_observation_state"] = {
        "radar_reflectivity": {
            "value": typed_array("real", 4, 12.5), "valid": typed_array("logical", 4, True),
            "quality": typed_array("integer", 4, 1), "source": typed_array("integer", 4, 2), "units": "dBZ",
        },
        "precipitation_phase": {
            "value": typed_array("integer", 4, 1), "valid": typed_array("logical", 4, True),
            "quality": typed_array("integer", 4, 1), "source": typed_array("integer", 4, 2), "units": "category",
        },
    }
    report = analyzer.validate_radar(capture, fake_background())
    assert report["actual_observation_state"] == "CAPTURED"
    assert report["actual_observation_metadata"]["radar_reflectivity"]["units"] == "dBZ"
    assert report["profiles"][0]["actual_observation.radar_reflectivity.value"] == 12.5
    del pre["actual_observation_state"]["radar_reflectivity"]["valid"]
    with pytest.raises(ValueError, match="missing valid"):
        analyzer.validate_radar(capture, fake_background())
