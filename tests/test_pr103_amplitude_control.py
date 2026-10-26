from pathlib import Path
import sys
import json
import shutil
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr103_amplitude_control as amplitude
from pr103_amplitude_control import build_amplitude_control


def test_single_global_scale_matches_stored_norm_before_storage():
    h = np.zeros(4, dtype=np.float32)
    p = np.array([3, 4, 8, 2], dtype=np.float32)
    n = np.array([0, 0, 6, 8], dtype=np.float32)
    free = np.array([True, True, True, True])

    result = build_amplitude_control(h, p, n, free)

    assert result.scale == pytest.approx(10.0 / np.sqrt(93.0))
    np.testing.assert_allclose(result.ideal, p * result.scale)
    assert result.ideal_norm == result.target_norm
    assert abs(result.stored_norm - result.target_norm) <= (
        result.storage_bound + result.norm_evaluation_bound)


def test_exterior_is_zero_and_storage_perturbation_is_bounded():
    h = np.array([0.1, -0.2, 3.0], dtype=np.float32)
    p = np.array([0.2, -0.3, 9.0], dtype=np.float32)
    n = np.array([0.4, -0.4, 8.0], dtype=np.float32)
    free = np.array([True, True, False])

    result = build_amplitude_control(h, p, n, free)

    assert result.stored[2] == h[2]
    assert result.ideal_norm == pytest.approx(result.target_norm)
    assert abs(result.stored_norm - result.ideal_norm) <= (
        result.storage_bound + result.norm_evaluation_bound)


def test_continuous_reconstruction_error_is_reported_not_fitted():
    h = np.zeros(2, dtype=np.float32)
    p = np.array([1.0, 2.0], dtype=np.float32)
    n = np.array([3.0, 4.0], dtype=np.float32)
    p_cont = np.array([1.0, 2.0000002], dtype=np.float64)

    result = build_amplitude_control(h, p, n, np.ones(2, dtype=bool), p_cont)

    assert result.scale == pytest.approx(np.sqrt(5.0))
    assert result.continuous_reference_error_bound > 0.0


def test_readback_bound_accounts_for_subtraction_at_large_background():
    h = np.array([1.0e10], dtype=np.float32)
    p = np.nextafter(h, np.float32(np.inf))
    n = h + np.float32(8192.0)

    result = build_amplitude_control(h, p, n, np.ones(1, dtype=bool))

    assert result.scale == pytest.approx(8.0)
    assert abs(result.stored_norm - result.target_norm) <= (
        result.storage_bound + result.arithmetic_bound + result.norm_evaluation_bound)


def test_rejects_zero_target_and_non_real32_inputs():
    h = np.zeros(2, dtype=np.float32)
    p = np.array([1.0, 2.0], dtype=np.float32)
    with pytest.raises(ValueError):
        build_amplitude_control(h, p, h, np.ones(2, dtype=bool))
    with pytest.raises(ValueError):
        build_amplitude_control(h.astype(np.float64), p, p,
                                np.ones(2, dtype=bool))


def test_pr102_receipt_binds_archived_n_by_hash_across_staged_path(tmp_path):
    staged_n = tmp_path / "staged_n"
    staged_n.write_bytes(b"archived structured candidate")
    pr99_receipt = tmp_path / "pr99.json"
    pr99_receipt.write_text("{}")
    receipt = {
        "schema": "pr102_wind_structure_proposal_v1",
        "status": "PROPOSAL_REQUIRES_NATIVE_CONSUMER_AND_SOURCE_CAPTURE",
        "role": "COUPLED",
        "candidate": {"path": "/archived/candidate", "sha256": amplitude._sha256(staged_n)},
        "pr99_projection_receipt": {"path": str(pr99_receipt),
                                    "sha256": amplitude._sha256(pr99_receipt)},
    }
    receipt_path = tmp_path / "pr102.json"
    receipt_path.write_text(json.dumps(receipt))

    amplitude._verify_pr102_receipt(receipt_path, staged_n, pr99_receipt)
    staged_n.write_bytes(b"changed")
    with pytest.raises(ValueError, match="candidate hash"):
        amplitude._verify_pr102_receipt(receipt_path, staged_n, pr99_receipt)


def test_archived_structured_run_passes_existing_640_second_closure_gate(tmp_path):
    root = Path(__file__).resolve().parents[1]
    evidence = root / "docs/evidence/pr102_execution_20261025"
    closed_run = evidence / "postclosure_20261026"
    run_root = tmp_path / "structured_run"
    run_root.mkdir()
    shutil.copyfile(closed_run / "struct_640_receipt.json", run_root / "receipt.json")
    shutil.copyfile(closed_run / "struct_640_preflight.json", run_root / "preflight.json")

    receipt, preflight = amplitude.pr102_response._closed_structured_run(
        run_root, json.loads((evidence / "preflight.json").read_text()))

    assert receipt["timestep_count"] == 32
    assert preflight["duration_seconds"] == 640
    assert receipt["candidate_wrfinput_sha256"] == (
        "b26e5f3d712732c3459d59b82a4b44fe53eebd9be1fd450d13640d2d8398343f")


@pytest.mark.parametrize("existing_sidecar", [False, True])
def test_failed_receipt_publication_removes_only_new_outputs(tmp_path, monkeypatch,
                                                            existing_sidecar):
    output = tmp_path / "wrfinput_d01"
    sidecar = output.with_suffix(".proposal.json")
    if existing_sidecar:
        sidecar.write_text("preserved prior receipt")
    names = ("hydro", "coupled", "original_p", "structured", "pr99_receipt",
             "pr102_receipt", "structured_run_receipt", "execution_preflight",
             "constants_receipt", "boundary")
    args = SimpleNamespace(**{name: tmp_path / name for name in names}, output=output)
    monkeypatch.setattr(amplitude.argparse.ArgumentParser, "parse_args", lambda _: args)

    def materialize(*_args):
        output.write_bytes(b"new candidate")
        return {"not_json_serializable": object()}

    monkeypatch.setattr(amplitude, "propose", materialize)
    with pytest.raises(FileExistsError if existing_sidecar else TypeError):
        amplitude.main()
    assert not output.exists()
    if existing_sidecar:
        assert sidecar.read_text() == "preserved prior receipt"
    else:
        assert not sidecar.exists()
