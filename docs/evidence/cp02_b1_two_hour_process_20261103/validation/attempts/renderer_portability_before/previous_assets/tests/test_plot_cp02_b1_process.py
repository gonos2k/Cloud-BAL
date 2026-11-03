from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import plot_cp02_b1_process as renderer


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def make_inputs(root: Path) -> list[str]:
    cohorts = root / "cohorts"
    cohorts.mkdir()
    fields = ["point_id", "diagnostic_group"] + [
        f"{case}_plus{lead}_mm" for case in ("RN1", "OLD", "FIX") for lead in (1, 2)
    ]
    selected = cohorts / "selected_points.csv"
    with selected.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for index in range(1, 5):
            writer.writerow({"point_id": f"P0{index}", "diagnostic_group": "test"})
    write_json(cohorts / "receipt.json", {"artifacts": {"selected_points.csv": {
        "sha256": digest(selected), "size_bytes": selected.stat().st_size,
    }}})

    scores = root / "scores.csv"
    score_fields = ["lead_hour", "case", "threshold_mm", "CSI", "hit", "miss", "false_alarm"]
    with scores.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=score_fields)
        writer.writeheader()
        for case in renderer.CASES:
            for lead in renderer.LEADS:
                for threshold in renderer.THRESHOLDS:
                    writer.writerow({"lead_hour": lead, "case": case, "threshold_mm": threshold,
                                     "CSI": 1, "hit": 1, "miss": 0, "false_alarm": 0})

    analysis_dir = root / "analysis"
    analysis_dir.mkdir()
    pair = analysis_dir / "pair_summary.json"
    write_json(pair, {"status": "PASS_BOTH_ARMS"})
    analysis_receipt = root / "analysis_receipt.json"
    write_json(analysis_receipt, {"status": "PASS_BOTH_ARMS", "analysis_outputs": [{
        "path": str(pair.resolve()), "sha256": digest(pair), "bytes": pair.stat().st_size,
    }]})
    components = root / "components.csv"
    components.write_text("dummy\n", encoding="utf-8")
    component_receipt = root / "components_receipt.json"
    write_json(component_receipt, {
        "status": "PASS_KEYED_LATENT_COMPONENT_DERIVATION",
        "run_receipt_sha256": digest(analysis_receipt),
        "output_sha256": digest(components), "output_bytes": components.stat().st_size,
    })
    return ["--cohorts", str(cohorts), "--scores", str(scores),
            "--analysis-dir", str(analysis_dir), "--analysis-receipt", str(analysis_receipt),
            "--components", str(components), "--components-receipt", str(component_receipt),
            "--out", str(root / "figures")]


def test_invalid_component_receipt_does_not_touch_existing_output(tmp_path: Path, monkeypatch) -> None:
    argv = make_inputs(tmp_path)
    out = tmp_path / "figures"
    out.mkdir()
    sentinel = out / "keep.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    argv[argv.index("--components-receipt") + 1] = str(tmp_path / "bad_components_receipt.json")
    write_json(tmp_path / "bad_components_receipt.json", {"status": "FAIL"})
    monkeypatch.setattr(sys, "argv", ["plot_cp02_b1_process.py", *argv])
    with pytest.raises(FileExistsError):
        renderer.main()
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_invalid_component_receipt_rejected_before_output_creation(tmp_path: Path, monkeypatch) -> None:
    argv = make_inputs(tmp_path)
    receipt_path = Path(argv[argv.index("--components-receipt") + 1])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["output_sha256"] = "0" * 64
    write_json(receipt_path, receipt)
    monkeypatch.setattr(sys, "argv", ["plot_cp02_b1_process.py", *argv])
    with pytest.raises(ValueError, match="integrated component CSV"):
        renderer.main()
    assert not (tmp_path / "figures").exists()
    assert not list(tmp_path.glob(".figures.stage-*"))


def test_failed_analysis_receipt_rejected_before_output_creation(tmp_path: Path, monkeypatch) -> None:
    argv = make_inputs(tmp_path)
    analysis_receipt = Path(argv[argv.index("--analysis-receipt") + 1])
    receipt = json.loads(analysis_receipt.read_text(encoding="utf-8"))
    receipt["status"] = "FAIL_NOT_BOTH_ARMS"
    write_json(analysis_receipt, receipt)
    monkeypatch.setattr(sys, "argv", ["plot_cp02_b1_process.py", *argv])
    with pytest.raises(ValueError, match="passing analysis receipt"):
        renderer.main()
    assert not (tmp_path / "figures").exists()
    assert not list(tmp_path.glob(".figures.stage-*"))
