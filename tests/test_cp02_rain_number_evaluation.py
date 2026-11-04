"""The candidate is admitted only by the complete per-lead CSI contract."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("nr_evaluation", ROOT / "tools/cp02_rain_number_evaluation.py")
evaluate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate)


def complete_arrays():
    obs = np.linspace(0, 15, 3688)
    return {h: {key: obs.copy() for key in (*evaluate.CASES, "reference")} for h in range(13, 19)}


def test_exact_tie_preserves_every_protected_cell():
    categorical, continuous, constraints = evaluate.compare_scores(complete_arrays())
    assert len(categorical) == 108 and len(continuous) == 18 and len(constraints) == 26
    assert len({(r["lead_hour"], r["threshold_mm"]) for r in constraints}) == 26
    assert all(r["satisfied"] for r in constraints)
    assert sum(r["goal"] == "preserve_current_B1" for r in constraints) == 11
    assert sum(r["goal"] == "recover_low_threshold_vs_ORIGINAL" for r in constraints) == 15


def test_a_better_strong_score_cannot_hide_weak_regression():
    arrays = complete_arrays()
    # Make every experiment miss strong rain, then recover it only in candidate.
    for values in arrays.values():
        for case in evaluate.CASES:
            values[case][values["reference"] >= 10] = 0
        values[evaluate.CANDIDATE][values["reference"] >= 10] = values["reference"][values["reference"] >= 10]
    # Losing these lower-intensity events at +2 h violates one or more weak cells.
    values = arrays[14]
    values[evaluate.CANDIDATE][(values["reference"] >= .1) & (values["reference"] < 10)] = 0
    scores, _, constraints = evaluate.compare_scores(arrays)
    strong = {r["case"]: r["CSI"] for r in scores if r["lead_hour"] == 2 and r["threshold_mm"] == 10}
    assert strong[evaluate.CANDIDATE] > strong["ORIGINAL"]
    assert any(not r["satisfied"] for r in constraints if r["lead_hour"] == 2)


@pytest.mark.parametrize("damage", ["missing_hour", "nonfinite", "short_case"])
def test_missing_verification_cannot_qualify(damage):
    arrays = complete_arrays()
    if damage == "missing_hour":
        arrays.pop(18)
    elif damage == "nonfinite":
        arrays[14][evaluate.CANDIDATE][0] = np.nan
    else:
        arrays[14][evaluate.CANDIDATE] = arrays[14][evaluate.CANDIDATE][:-1]
    with pytest.raises(ValueError):
        evaluate.compare_scores(arrays)


def test_empty_plan_scope_rejected_before_publication(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"schema": "b1_rain_number_evaluation_v1", "candidate": evaluate.CANDIDATE,
                                "thresholds_mm": [], "leads_hours": list(range(1, 7)), "constraint_count": 26}))
    output = tmp_path / "analysis"
    with pytest.raises(ValueError, match="scope differs"):
        evaluate.run(plan, evaluate.identity(plan)["sha256"], tmp_path, tmp_path / "missing_gate", output)
    assert not output.exists()


def test_changed_policy_is_rejected_before_forecast_read(tmp_path):
    artifacts = {}
    for name in ("policy", "initialization", "candidate_preflight"):
        path = tmp_path / f"{name}.json"
        path.write_text("{}\n")
        artifacts[name] = evaluate.identity(path)
    plan_data = {"schema": "b1_rain_number_evaluation_v1", "candidate": evaluate.CANDIDATE,
                 "thresholds_mm": list(evaluate.THRESHOLDS), "leads_hours": list(range(1, 7)),
                 "constraint_count": 26, "bound_artifacts": artifacts}
    plan_data.update({k: "a" * 64 for k in ("input_sha256", "executable_sha256", "boundary_sha256", "namelist_sha256")})
    plan_data["policy_sha256"] = artifacts["policy"]["sha256"]
    plan, gate = tmp_path / "plan.json", tmp_path / "gate.json"
    plan.write_text(json.dumps(plan_data))
    gate.write_text(json.dumps({**plan_data, "status": "COMPLETE", "case": evaluate.CANDIDATE}))
    (tmp_path / "policy.json").write_text('{"changed":true}\n')
    output = tmp_path / "analysis"
    with pytest.raises(ValueError, match="frozen identity"):
        evaluate.run(plan, evaluate.identity(plan)["sha256"], tmp_path, gate, output)
    assert not output.exists()
