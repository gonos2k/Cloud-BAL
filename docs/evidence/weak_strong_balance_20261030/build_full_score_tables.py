#!/usr/bin/env python3
"""Build the complete weak/strong score appendix from sealed scorer outputs."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ANALYSIS = HERE / "analysis"
REPORT = ROOT / "docs/WEAK_STRONG_BALANCE_FULL_SCORES_20261030.md"
LEADS = tuple(range(1, 7))
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
CASES = (
    "ORIGINAL", "CONTROL_SNOW_300", "IMPROVED_BG_FIXED", "IMPROVED_SNOW_080",
    "GATE_G50_90", "EQ_G50_90", "GATE_G75_95", "EQ_G75_95",
    "GATE_G90_99", "EQ_G90_99", "FIXED_ORIGINAL_100", "ORIGINAL_B1_100",
)
LABELS = {
    "ORIGINAL": "ORIGINAL · 규준 기준",
    "CONTROL_SNOW_300": "CONTROL α=3 (참고)",
    "IMPROVED_BG_FIXED": "B1 입력 + 수정 실행파일",
    "IMPROVED_SNOW_080": "IMPROVED α=0.8 (참고)",
    "GATE_G50_90": "Gate 50–90%",
    "EQ_G50_90": "Equal mass 50–90%",
    "GATE_G75_95": "Gate 75–95%",
    "EQ_G75_95": "Equal mass 75–95%",
    "GATE_G90_99": "Gate 90–99%",
    "EQ_G90_99": "Equal mass 90–99%",
    "FIXED_ORIGINAL_100": "Fixed executable / ORIGINAL input",
    "ORIGINAL_B1_100": "ORIGINAL executable / B1 input",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(name: str) -> list[dict[str, str]]:
    with (ANALYSIS / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def table(headers: list[str], rows: list[list[str]]) -> str:
    return "\n".join(["| " + " | ".join(headers) + " |",
                      "| " + " | ".join("---" for _ in headers) + " |",
                      *["| " + " | ".join(row) + " |" for row in rows]])


def fmt(row: dict[str, str], field: str, places: int = 6) -> str:
    value = row.get(field, "")
    if value in ("", "None", "nan", "NaN"):
        return "—"
    return f"{float(value):.{places}f}"


def main() -> None:
    receipt_path = ANALYSIS / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("status") != "COMPLETE" or receipt.get("cases") != list(CASES):
        raise ValueError("complete receipt for the frozen 12-context design is required")
    plan_sha256 = "17e8833f2f28da76e1474f82440a88889bd55ba723ef9cd6618d06a0eb786248"
    plan_path = HERE / "selection_plan.json"
    if digest(plan_path) != plan_sha256 or receipt.get("plan", {}).get("sha256") != plan_sha256:
        raise ValueError("frozen selection plan hash mismatch")
    for name, record in receipt.get("analysis_outputs", {}).items():
        path = ANALYSIS / name
        if (path.is_symlink() or not path.is_file()
                or path.stat().st_size != record.get("size_bytes")
                or digest(path) != record.get("sha256")):
            raise ValueError(f"analysis output hash mismatch: {name}")
    cat_rows = read_csv("categorical_scores.csv")
    cont_rows = read_csv("continuous_scores.csv")
    cat = {(int(row["lead_hour"]), row["case"], float(row["threshold_mm"])): row
           for row in cat_rows}
    cont = {(int(row["lead_hour"]), row["case"]): row for row in cont_rows}
    expected_cat = {(lead, case, threshold) for lead in LEADS for case in CASES
                    for threshold in THRESHOLDS}
    expected_cont = {(lead, case) for lead in LEADS for case in CASES}
    if len(cat) != len(cat_rows) or set(cat) != expected_cat or len(cont) != len(cont_rows) or set(cont) != expected_cont:
        raise ValueError("score tables do not cover the complete 12 × 6 × threshold design")

    parts = [
        "# Weak/strong-balance experiment: complete score tables",
        "",
        "This appendix reports every threshold and lead separately for all 12 scored contexts. "
        "ORIGINAL is the paired baseline. The three prior cases are context references; only the eight "
        "new frozen-plan cases enter qualification. No scores are averaged across thresholds, leads, or cases.",
        "",
        "All hourly amounts are differences between consecutive cumulative WRF precipitation histories, "
        "scored at the common 3,688-point RN1 mask. CSI = H/(H+M+FA); FAR = FA/(H+FA). H, M, and FA "
        "denote hits, misses, and false alarms. The table retains undefined ratios as `—`.",
        "",
        "## Categorical scores",
        "",
    ]
    for threshold in THRESHOLDS:
        parts.extend([f"### ≥{threshold:g} mm per one-hour window", ""])
        for lead in LEADS:
            rows = []
            example = cat[(lead, CASES[0], threshold)]
            for case in CASES:
                row = cat[(lead, case, threshold)]
                base = cat[(lead, "ORIGINAL", threshold)]
                delta = "—" if row["CSI"] in ("", "None") or base["CSI"] in ("", "None") else f"{float(row['CSI'])-float(base['CSI']):+.6f}"
                rows.append([LABELS[case], fmt(row, "CSI"), delta, fmt(row, "ETS"), fmt(row, "POD"),
                             fmt(row, "FAR"), str(row["hit"]), str(row["miss"]), str(row["false_alarm"])])
            parts.extend([f"#### +{lead} h · {example['window_start_utc'][11:16]}–{example['window_end_utc'][11:16]} UTC",
                          table(["Case", "CSI", "ΔCSI vs ORIGINAL", "ETS", "POD", "FAR", "H", "M", "FA"], rows), ""])
    parts.extend(["## Continuous errors", "",
                  "Mean forecast, mean reference, MAE, and RMSE are calculated independently for each lead; "
                  "no pooled or across-lead error summary is used here.", ""])
    for lead in LEADS:
        rows = []
        for case in CASES:
            row, base = cont[(lead, case)], cont[(lead, "ORIGINAL")]
            rows.append([LABELS[case], fmt(row, "mean_forecast_mm"), fmt(row, "mean_reference_mm"),
                         fmt(row, "MAE_mm"), fmt(row, "RMSE_mm"),
                         f"{float(row['RMSE_mm'])-float(base['RMSE_mm']):+.6f}"])
        parts.extend([f"### +{lead} h", table(["Case", "Mean forecast (mm)", "Mean RN1 (mm)", "MAE (mm)",
                                                "RMSE (mm)", "ΔRMSE vs ORIGINAL"], rows), ""])

    for name, title in (("admission_constraints.csv", "Admission checks"),
                        ("gate_equal_mass_comparison.csv", "Gate and equal-mass pairs"),
                        ("factorial_difference_in_differences.csv", "Executable/input factorial contrasts"),
                        ("csi_change_exact_counts.csv", "Exact CSI algebra by hit and false-alarm counts")):
        path = ANALYSIS / name
        if path.exists():
            rows = read_csv(name)
            parts.extend([f"## {title}", "", "```csv", path.read_text(encoding="utf-8").rstrip(), "```", ""])
    parts.extend(["## Disjoint observed-intensity diagnostics", "",
                  "These auxiliary tables stratify verified points by disjoint RN1 intensity bins; they do not replace or relax the frozen CSI admission rule.",
                  "- [Observed-band hit/false-alarm transitions](evidence/weak_strong_balance_20261030/analysis/observation_band_transitions.csv)",
                  "- [Observed and forecast intensity-bin counts](evidence/weak_strong_balance_20261030/analysis/observed_forecast_bin_counts.csv)", ""])
    parts.extend(["## Source bindings", "",
                  f"- Scoring receipt SHA-256: `{digest(receipt_path)}`",
                  f"- Frozen plan SHA-256: `{receipt['plan']['sha256']}`",
                  "- Categorical source: [categorical_scores.csv](evidence/weak_strong_balance_20261030/analysis/categorical_scores.csv)",
                  "- Continuous source: [continuous_scores.csv](evidence/weak_strong_balance_20261030/analysis/continuous_scores.csv)",
                  "- Full source hashes and array pins: [receipt.json](evidence/weak_strong_balance_20261030/analysis/receipt.json)"])
    REPORT.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    (HERE / "full_tables_receipt.json").write_text(json.dumps({
        "report": REPORT.relative_to(ROOT).as_posix(), "report_sha256": digest(REPORT),
        "builder_sha256": digest(Path(__file__)), "analysis_receipt_sha256": digest(receipt_path),
        "categorical_rows": len(cat_rows), "continuous_rows": len(cont_rows),
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
