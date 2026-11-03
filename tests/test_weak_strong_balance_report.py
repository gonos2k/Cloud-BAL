"""Regression checks for report decisions when strict admission finds no case."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "weak_strong_balance_report", ROOT / "docs/evidence/weak_strong_balance_20261030/build_report.py")
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


def test_no_qualified_case_keeps_baseline_and_marks_strong_only_leader_diagnostic():
    winner = {"status": "NO_QUALIFIED_CANDIDATE", "selected_case": None, "qualified_cases": []}
    ranking = []
    cat = {(1, case, 10.0): {"CSI": "0.90" if case == "GATE_G50_90" else "0.50"}
           for case in report.NEW_CASES}
    checks = {}
    diagnostic = "GATE_G50_90"
    for lead in report.LEADS:
        for threshold in report.WEAK:
            checks[(diagnostic, "weak_CSI_at_least_ORIGINAL", lead, threshold)] = {
                "status": "FAIL" if (lead, threshold) == (2, 0.1) else "PASS"
            }

    outcome, strong_only = report.selection_narrative(winner, ranking, cat, checks)

    assert "적격 후보가 없다" in outcome
    assert "신규 후보를 선정하지 않는다" in outcome
    assert report.CASE_LABELS[diagnostic] in strong_only
    assert "통과하지 못했으므로 적격·선정 후보가 아니며" in strong_only
    assert "적격성 조건을 만족한 후보로 간주되지 않는다" in strong_only
    assert winner["selected_case"] is None

