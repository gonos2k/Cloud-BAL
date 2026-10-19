from __future__ import annotations

import gzip
import sys
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr86_process_budget import LedgerError  # noqa: E402
from pr87_admission_reason_summary import _parse_row  # noqa: E402
from pr87_admission_reason_summary import analyze_arm  # noqa: E402


def test_parse_reason_raw_row() -> None:
    row = ("PR87_ADMISSION G 12 8 4 2 1 5 10 1 "
           "0.5 1.25e-6 250.0 10.0")
    group, ids, values = _parse_row(row, 1)
    assert group == "G"
    assert ids == [12, 8, 4, 2, 1, 5, 10, 1]
    assert values == [0.5, 1.25e-6, 250.0, 10.0]


@pytest.mark.parametrize("row", [
    "PR87_ADMISSION NG 1 1 1 1 0 0 0 0 0.5 1.0 1.0 1.0",
    "PR87_ADMISSION G 1 1 1 1 0 12 0 0 0.5 1.0 1.0 1.0 1.0",
    "PR87_ADMISSION AUT 1 1 1 1 0 0 11 0 0.5 1.0 1.0 1.0 1.0",
    "PR87_ADMISSION AUT 1 1 1 1 0 0 0 0 1.0 1.0 1.0 1.0 1.0",
])
def test_parse_reason_raw_rejects_invalid_rows(row: str) -> None:
    with pytest.raises(LedgerError):
        _parse_row(row, 1)


def test_analyze_arm_weights_and_binds_candidate(tmp_path: Path, monkeypatch) -> None:
    pre = b"pre-capture"
    post = b"post-capture"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    raw = ("# PR87_ADMISSION header repeated for each latitude\n"
           "PR87_ADMISSION G 1 4 2 1 1 5 10 1 0.25 0.001 1.2 5.0\n")
    raw_files = {"kdm6_first_call_pre.raw": pre,
                 "kdm6_first_call_post.raw": post,
                 "pr87_admission_reason.raw": raw.encode()}
    outputs = {}
    for name, payload in raw_files.items():
        compressed_name = f"{name}.gz"
        compressed_path = run_dir / compressed_name
        with gzip.open(compressed_path, "wb") as stream:
            stream.write(payload)
        outputs[name] = {
            "path": name,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
            "compressed_path": compressed_name,
            "compressed_sha256": hashlib.sha256(compressed_path.read_bytes()).hexdigest(),
        }
    source_receipt = tmp_path / "frozen_source_receipt.json"
    source_receipt.write_bytes(b"frozen source receipt")
    source_receipt_sha = hashlib.sha256(source_receipt.read_bytes()).hexdigest()
    geometry_root = tmp_path / "frozen_geometry"
    candidate_build = {"status": "PASS_OVERLAY_BUILD", "receipt_path": str(tmp_path / "build.json"),
                       "receipt_sha256": "", "executable_sha256": "candidate-exe"}
    build_path = Path(candidate_build["receipt_path"])
    build_path.write_text(json.dumps({
        "status": "PASS_OVERLAY_BUILD",
        "source_overrides": {"module_mp_kdm6.o": {
            "requested_sha256": "kdm6-source", "staged_sha256": "kdm6-source"}},
    }))
    candidate_build["receipt_sha256"] = hashlib.sha256(build_path.read_bytes()).hexdigest()
    (tmp_path / "preflight.json").write_text(json.dumps({
        "arm": "OFF", "runtime_dir": str(geometry_root),
        "source_receipt": str(source_receipt), "source_receipt_sha256": source_receipt_sha,
        "candidate_build": candidate_build,
    }))
    (tmp_path / "receipt.json").write_text(json.dumps({
        "arm": "OFF", "status": "COMPLETE", "returncode": 0,
        "timestep_count": 1, "final_completed_step": 1,
        "source_receipt_sha256": source_receipt_sha,
        "candidate_build": candidate_build, "candidate_build_unchanged": True,
        "executed_executable_sha256": "candidate-exe",
        "expected_executed_executable_sha256": "candidate-exe",
        "compressed_outputs": list(outputs.values()),
    }))
    frozen = {
        "arm": "OFF",
        "bounds": {"its": 1, "ite": 1, "jts": 4, "jte": 4, "kts": 2, "kte": 2},
        "rho_dry_jki": np.asarray([[[1.2]]]),
        "delz_jki": np.asarray([[[5.0]]]),
        "area_ji": np.asarray([[100.0]]),
        "identities": {
            "receipt": {"sha256": "receipt"},
            "kdm6_first_call_pre.raw": {"sha256": outputs["kdm6_first_call_pre.raw"]["sha256"]},
            "kdm6_first_call_post.raw": {"sha256": outputs["kdm6_first_call_post.raw"]["sha256"]},
        },
        "run_root": geometry_root,
    }
    frozen["identities"]["receipt"]["sha256"] = source_receipt_sha
    monkeypatch.setattr("pr87_admission_reason_summary.load_call_measure", lambda _root: frozen)

    result = analyze_arm(tmp_path, "OFF")
    group = result["groups"]["G"]
    assert group["records"] == 1
    assert group["emitted_proposal_activity_kg"] == pytest.approx(0.6)
    assert group["rejected_activity_kg"] == pytest.approx(0.45)
    assert group["approved_activity_kg"] == pytest.approx(0.15)
    bucket = next(iter(group["rows_by_reason_status"].values()))
    assert bucket["rejected_over_emitted_proposal"] == pytest.approx(0.75)
    assert bucket["approved_over_emitted_proposal"] == pytest.approx(0.25)
    assert bucket["proposal_activity_fraction"] == pytest.approx(1.0)

    receipt_path = tmp_path / "receipt.json"
    for bad_status in ("UNKNOWN", None):
        receipt = json.loads(receipt_path.read_text())
        if bad_status is None:
            receipt.pop("status")
        else:
            receipt["status"] = bad_status
        receipt_path.write_text(json.dumps(receipt))
        with pytest.raises(LedgerError, match="did not complete"):
            analyze_arm(tmp_path, "OFF")

    receipt = json.loads(receipt_path.read_text())
    receipt["status"] = "INCOMPLETE"
    receipt["returncode"] = 1
    receipt["timestep_count"] = 1
    receipt["final_completed_step"] = 1
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(LedgerError, match="did not complete"):
        analyze_arm(tmp_path, "OFF")
    result = analyze_arm(tmp_path, "OFF", allow_first_call_only=True)
    assert result["completed_window"] == "FIRST_CALL_CAPTURE_ONLY_RUN_INCOMPLETE"
