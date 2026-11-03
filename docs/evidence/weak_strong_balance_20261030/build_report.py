#!/usr/bin/env python3
"""Build the weak/strong-balance report from frozen plans and sealed evidence."""
from __future__ import annotations

import csv
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ANALYSIS = HERE / "analysis"
REVIEW = HERE / "review"
FIGURES = HERE / "figures"
PLAN = HERE / "selection_plan.json"
PLAN_SHA256 = "17e8833f2f28da76e1474f82440a88889bd55ba723ef9cd6618d06a0eb786248"
OUTPUT = ROOT / "docs/WEAK_STRONG_BALANCE_REPORT_20261030.md"
FIGURES_OUTPUT = ROOT / "docs/WEAK_STRONG_BALANCE_FIGURES_20261030.md"
LEADS = tuple(range(1, 7))
WEAK = (0.1, 0.5, 1.0)
STRONG = (5.0, 10.0)
NEW_CASES = (
    "GATE_G50_90", "EQ_G50_90", "GATE_G75_95", "EQ_G75_95",
    "GATE_G90_99", "EQ_G90_99", "FIXED_ORIGINAL_100", "ORIGINAL_B1_100",
)
CASE_LABELS = {
    "ORIGINAL": "ORIGINAL",
    "CONTROL_SNOW_300": "CONTROL α=3",
    "IMPROVED_BG_FIXED": "B1 입력 + 수정 실행파일",
    "IMPROVED_SNOW_080": "IMPROVED α=0.8",
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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def table(headers: list[str], rows: list[list[str]]) -> str:
    return "\n".join(["| " + " | ".join(headers) + " |",
                      "| " + " | ".join("---" for _ in headers) + " |",
                      *["| " + " | ".join(row) + " |" for row in rows]])


def image_markdown(caption: str, filename: str, figure_ref: str | None = None) -> str:
    local = f"evidence/weak_strong_balance_20261030/figures/{filename}"
    target = figure_ref.format(name=filename) if figure_ref else local
    return f"![{caption}](<{target}>)" if figure_ref else f"![{caption}]({target})"


def build_figures_index(figure_manifest: dict, figure_ref: str | None) -> None:
    parts = [
        "# Weak/strong-balance figures",
        "",
        "This gallery contains the 38 PNG figures for the single-case initial-QSNOW placement experiment. "
        "All score panels retain lead and threshold separately; maps use paired RN1 points, and all precipitation-difference maps share a zero-centered scale that covers the observed extrema.",
        "",
        "## Initial gate and placement controls",
        "",
        image_markdown("Conceptual path from initial proxy to paired score comparison", "initial_gate_concept.png", figure_ref),
        image_markdown("Initial proxy, spatial α maps, and dry-mass-weighted QSNOW placement", "initial_precip_gate_maps.png", figure_ref),
        "",
        "## Absolute CSI and ORIGINAL-relative ΔCSI by threshold",
        "",
    ]
    for threshold in (0.1, 0.5, 1.0, 2.5, 5.0, 10.0):
        parts.extend([
            f"### ≥{threshold:g} mm",
            "",
            image_markdown(f"Absolute CSI at ≥{threshold:g} mm", f"csi_absolute_{threshold:g}mm.png", figure_ref),
            image_markdown(f"ΔCSI from ORIGINAL at ≥{threshold:g} mm", f"csi_delta_{threshold:g}mm.png", figure_ref),
            "",
        ])
    parts.extend(["## Exact CSI algebra decomposition", ""])
    parts.extend(image_markdown(f"Hit, false-alarm, and net CSI algebra at ≥{threshold:g} mm",
                                f"csi_algebra_decomposition_{threshold:g}mm.png", figure_ref)
                 for threshold in (0.1, 0.5, 1.0, 2.5, 5.0, 10.0))
    parts.extend(["", "## Paired GATE−EQ CSI by threshold", ""])
    parts.extend(image_markdown(f"Spatial gate minus equal-mass CSI at ≥{threshold:g} mm",
                                f"gate_minus_equal_mass_csi_{threshold:g}mm.png", figure_ref)
                 for threshold in (0.1, 0.5, 1.0, 2.5, 5.0, 10.0))
    parts.extend(["", "## Hourly precipitation maps", "",
                  "Each sheet has six lead hours and three columns: RN1, case hourly total, and same-point case−ORIGINAL difference. No spatial interpolation was applied.", ""])
    parts.extend(image_markdown(f"Hourly RN1, case precipitation, and case−ORIGINAL difference: {CASE_LABELS[case]}",
                                f"maps_{case.lower()}.png", figure_ref)
                 for case in ("ORIGINAL", "CONTROL_SNOW_300", "IMPROVED_BG_FIXED", "IMPROVED_SNOW_080",
                              *NEW_CASES))
    parts.extend(["", "## Figure hashes", "",
                  f"Figure manifest SHA-256: `{digest(FIGURES / 'figure_manifest.json')}`.", "",
                  table(["PNG file", "SHA-256"], [[name, value] for name, value in sorted(figure_manifest["files"].items())])])
    FIGURES_OUTPUT.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    (HERE / "figures_doc_receipt.json").write_text(json.dumps({
        "document": FIGURES_OUTPUT.relative_to(ROOT).as_posix(),
        "document_sha256": digest(FIGURES_OUTPUT),
        "builder_sha256": digest(Path(__file__)),
        "figure_manifest_sha256": digest(FIGURES / "figure_manifest.json"),
        "png_count": len(figure_manifest.get("files", {})),
        "figure_ref_template": figure_ref,
    }, indent=2) + "\n")


def fmt(value: str | float | None, places: int = 4) -> str:
    if value in (None, "", "None", "nan", "NaN"):
        return "—"
    return f"{float(value):.{places}f}"


def selection_narrative(winner: dict, ranking: list[dict], cat: dict,
                        check_rows: dict) -> tuple[str, str | None]:
    selected = winner.get("selected_case")
    if selected:
        if not ranking or ranking[0]["case"] != selected:
            raise ValueError("selected case is not the first qualified ranking row")
        return (f"사전 기준을 모두 만족한 설정은 **{CASE_LABELS[selected]}**이며, "
                "아래 우선순위에 따른 적격 설정 중 첫 순위다. 이 순위는 한 사례 안에서의 탐색 결과다.", None)
    if ranking or winner.get("qualified_cases", []):
        raise ValueError("no-qualified status cannot contain ranking candidates")
    diagnostic_case = max(NEW_CASES, key=lambda case: float(cat[(1, case, 10.0)]["CSI"]))
    failed_weak = sum(
        check_rows[(diagnostic_case, "weak_CSI_at_least_ORIGINAL", lead, threshold)]["status"] == "FAIL"
        for lead in LEADS for threshold in WEAK
    )
    diagnostic = (
        f"강한 기준만 비교한 진단 상위는 **{CASE_LABELS[diagnostic_case]}**(+1 h CSI@10 "
        f"{fmt(cat[(1, diagnostic_case, 10.0)]['CSI'])})다. 낮은 임계값 CSI 바닥 조건 "
        f"18개 중 {failed_weak}개를 통과하지 못했으므로 적격·선정 후보가 아니며, "
        "이 진단 비교는 적격성 조건을 만족한 후보로 간주되지 않는다."
    )
    return ("**적격 후보가 없다.** 낮은 임계값 18개 CSI 조건과 +1 h ≥10 mm CSI 엄격 개선을 "
            "함께 통과한 새 설정이 없어 ORIGINAL을 비교 기준으로 둔 채 신규 후보를 선정하지 않는다. "
            "순위 선정을 하지 않았으며 기준을 사후 완화하지 않았다.",
            diagnostic)


def read_and_validate_analysis() -> tuple[dict, list[dict], list[dict], dict, dict]:
    receipt_path = ANALYSIS / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("status") != "COMPLETE" or receipt.get("cases") != [
        "ORIGINAL", "CONTROL_SNOW_300", "IMPROVED_BG_FIXED", "IMPROVED_SNOW_080", *NEW_CASES
    ]:
        raise ValueError("complete score receipt does not match frozen contexts")
    plan_record = receipt.get("plan", {})
    if digest(PLAN) != PLAN_SHA256 or plan_record.get("sha256") != PLAN_SHA256:
        raise ValueError("selection plan hash mismatch")
    for name, record in receipt.get("analysis_outputs", {}).items():
        path = ANALYSIS / name
        if (path.is_symlink() or not path.is_file()
                or path.stat().st_size != record.get("size_bytes")
                or digest(path) != record.get("sha256")):
            raise ValueError(f"analysis output hash mismatch: {name}")
    categorical = read_csv(ANALYSIS / "categorical_scores.csv")
    continuous = read_csv(ANALYSIS / "continuous_scores.csv")
    cat = {(int(row["lead_hour"]), row["case"], float(row["threshold_mm"])): row
           for row in categorical}
    cont = {(int(row["lead_hour"]), row["case"]): row for row in continuous}
    cases = receipt["cases"]
    if len(cat) != len(categorical) or len(cat) != len(cases) * 6 * 6:
        raise ValueError("categorical score coverage incomplete or duplicated")
    if len(cont) != len(continuous) or len(cont) != len(cases) * 6:
        raise ValueError("continuous score coverage incomplete or duplicated")
    return receipt, categorical, continuous, cat, cont


def audit_old_tradeoffs(cat: dict) -> str:
    results_path = REVIEW / "results.csv"
    audit_path = REVIEW / "results.json"
    expected = "096c82ad9facf5932a363dd5c92a124d1b83928c2b76c1df0a5105b9dce286c4"
    context_path = REVIEW / "current_hydro_context.csv"
    if (digest(results_path) != expected
            or digest(audit_path) != "ba835b62e748c4c26e51b3401e6fbdc9d370c18693c152d824789f71183105ee"
            or digest(context_path) != "b0ee07d496ed55848d8f17962f0442b70a898cb5abd8a01406ab71b9f3d8e6c7"):
        raise ValueError("prior trade-off audit hash mismatch")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    observed_path = REVIEW / "prior_observed_band.csv"
    observed_receipt_path = REVIEW / "prior_observed_band_receipt.json"
    if (digest(observed_path) != "13a8ee9988dc9a30501de905984f59806b867010f623b6341624b2d3271c1cf6"
            or digest(observed_receipt_path) != "ff96adedcdf811dc312651a92e66c22d3261c9b76125e012a0a47196f203e1a6"):
        raise ValueError("prior observed-band audit hash mismatch")
    observed_receipt = json.loads(observed_receipt_path.read_text(encoding="utf-8"))
    if (observed_receipt.get("status") != "PASS" or observed_receipt.get("rows") != 540
            or observed_receipt.get("csv_sha256") != digest(observed_path)):
        raise ValueError("prior observed-band receipt does not bind its complete CSV")
    observed_rows = read_csv(observed_path)
    rows = read_csv(results_path)
    selected_cases = {"CONTROL_SNOW_300", "IMPROVED_SNOW_080"}
    cell_rows = [row for row in rows if row["scope"] == "ELIGIBLE_CANDIDATE"
                 and row["case"] in selected_cases]
    index = {(row["case"], int(row["lead_hour"]), float(row["threshold_mm"])): row
             for row in cell_rows}
    ctrl_l1 = [index[("CONTROL_SNOW_300", 1, t)] for t in (0.1, 0.5, 1, 2.5, 5, 10)]
    ctrl_weak_l23 = [index[("CONTROL_SNOW_300", lead, threshold)]
                     for lead in (2, 3) for threshold in WEAK]
    imp_weak = [index[("IMPROVED_SNOW_080", lead, threshold)]
                for lead in (2, 3, 4, 6) for threshold in WEAK]
    imp_strong = [index[("IMPROVED_SNOW_080", lead, threshold)]
                  for lead in LEADS for threshold in STRONG]
    if (not all(float(row["delta_CSI"]) > 0 for row in ctrl_l1)
            or sum(float(row["delta_CSI"]) < 0 for row in ctrl_weak_l23) != 5
            or sum(float(row["delta_CSI"]) < 0 for row in imp_weak) != len(imp_weak)
            or sum(float(row["delta_CSI"]) > 0 for row in imp_strong) != 11):
        raise ValueError("prior CONTROL α=3 trade-off summary does not match the pinned audit")
    observed = {(row["case"], int(row["lead_hour"]), float(row["threshold_mm"]), row["observed_band"]): row
                for row in observed_rows}
    def net_hits(lead: int, band: str) -> int:
        row = observed[("IMPROVED_SNOW_080", lead, 0.1, band)]
        return int(row["hits_gained"]) - int(row["hits_lost"])
    def csi_sign(case: str, lead: int, threshold: float) -> tuple[dict[str, str], float]:
        row = index[(case, lead, threshold)]
        signal = int(row["delta_hit"]) - float(row["baseline_CSI"]) * int(row["delta_false_alarm"])
        return row, signal
    imp_l6_01, imp_l6_01_signal = csi_sign("IMPROVED_SNOW_080", 6, 0.1)
    imp_l6_10, imp_l6_10_signal = csi_sign("IMPROVED_SNOW_080", 6, 10.0)
    ctrl_l6_01, ctrl_l6_01_signal = csi_sign("CONTROL_SNOW_300", 6, 0.1)
    prior_band_summary = (
        f"검증-only 관측 강도별 전이 감사는 +4 h, ≥0.1 mm에서 IMPROVED α=0.8의 순 적중 변화가 "
        f"light {net_hits(4, 'light[0.1,1)'):+d}, moderate {net_hits(4, 'moderate[1,5)'):+d}, "
        f"strong {net_hits(4, 'strong[5,10)'):+d}, very strong {net_hits(4, 'very_strong>=10'):+d}였음을 보인다. "
        f"+6 h에는 각각 {net_hits(6, 'light[0.1,1)'):+d}, {net_hits(6, 'moderate[1,5)'):+d}, "
        f"{net_hits(6, 'strong[5,10)'):+d}, {net_hits(6, 'very_strong>=10'):+d}였다. "
        "따라서 낮은 임계값 CSI 하락을 약한 강도만의 적중 손실로 읽어서는 안 된다. "
        "이 보조 감사는 같은 사례의 원자료 구간을 설명하며 적격성 기준을 변경하지 않는다."
    )
    return (
        "기존 39개 설정의 독립 재산출에서는 CONTROL α=3이 +1 h의 여섯 CSI 임계값 모두에서 "
        "ORIGINAL보다 높았지만 +2–+3 h의 낮은 임계값 6개 셀 중 일부에서는 CSI가 낮았다. "
        f"이 구간에서 낮은 셀은 {sum(float(row['delta_CSI']) < 0 for row in ctrl_weak_l23)}/6이다. "
        "IMPROVED α=0.8은 +2, +3, +4, +6 h의 낮은 임계값 CSI에서 약화가 나타났고, "
        f"그 12개 셀 중 {sum(float(row['delta_CSI']) < 0 for row in imp_weak)}개가 ORIGINAL보다 낮았다. "
        "반면 같은 사례의 ≥5 mm 강수 CSI는 여섯 lead×두 임계값 12개 조합 중 "
        f"{sum(float(row['delta_CSI']) > 0 for row in imp_strong)}개에서 높았다. "
        f"같은 고정 관측 사건 수에서 +6 h IMPROVED α=0.8, ≥0.1 mm는 ΔH={int(imp_l6_01['delta_hit']):+d}, "
        f"ΔFA={int(imp_l6_01['delta_false_alarm']):+d}, ΔH−CSI₀ΔFA={imp_l6_01_signal:+.3f}로 CSI가 낮았다. "
        f"+6 h ≥10 mm에서는 ΔH={int(imp_l6_10['delta_hit']):+d}, ΔFA={int(imp_l6_10['delta_false_alarm']):+d}, "
        f"ΔH−CSI₀ΔFA={imp_l6_10_signal:+.3f}로 CSI가 높았고, CONTROL α=3의 +6 h ≥0.1 mm는 "
        f"ΔH={int(ctrl_l6_01['delta_hit']):+d}, ΔFA={int(ctrl_l6_01['delta_false_alarm']):+d}, "
        f"ΔH−CSI₀ΔFA={ctrl_l6_01_signal:+.3f}였다. 이 exact-count sign check는 CSI 산술이지 물리 인과 귀속이 아니다. "
        + prior_band_summary + " "
        "이 분리는 강한 강수 개선을 약한 강수 전반의 개선으로 일반화할 수 없음을 보여 주며, "
        "현재 검토의 동기를 제공한다. 전 수치는 [재산출 셀표](evidence/weak_strong_balance_20261030/review/results.csv), "
        "기존 HYDRO 별도 맥락은 [참고 셀표](evidence/weak_strong_balance_20261030/review/current_hydro_context.csv), "
        "검증·입력 해시는 [감사 영수증](evidence/weak_strong_balance_20261030/review/results.json), "
        "재산출 코드는 [audit script](evidence/weak_strong_balance_20261030/review/prior_tradeoff_audit.py), "
        "관측 강도 구간 코드는 [band audit](evidence/weak_strong_balance_20261030/review/prior_observed_band_audit.py)와 "
        "[band receipt](evidence/weak_strong_balance_20261030/review/prior_observed_band_receipt.json)을 참조한다."
    )


def main(figure_ref: str | None = None) -> None:
    if figure_ref and (not figure_ref.startswith("https://") or "{name}" not in figure_ref):
        raise ValueError("--figure-ref must be an HTTPS URL template containing {name}")
    receipt, categorical, continuous, cat, cont = read_and_validate_analysis()
    winner = json.loads((ANALYSIS / "winner.json").read_text(encoding="utf-8"))
    constraints = read_csv(ANALYSIS / "admission_constraints.csv")
    passed = {case for case in NEW_CASES
              if all(row["status"] == "PASS" for row in constraints if row["case"] == case)}
    if passed != set(winner.get("qualified_cases", [])):
        raise ValueError("winner status does not agree with strict admission table")
    selected = winner.get("selected_case")
    if selected and (selected not in NEW_CASES or selected not in passed):
        raise ValueError("selected case is not an admitted frozen candidate")

    ranking_path = ANALYSIS / "qualified_ranking.csv"
    ranking = read_csv(ranking_path) if ranking_path.exists() else []
    if winner.get("status") == "QUALIFIED_CANDIDATE" and not ranking:
        raise ValueError("qualified result is missing its ranking table")
    if winner.get("status") == "NO_QUALIFIED_CANDIDATE" and ranking:
        raise ValueError("no qualified case must not have a ranking table")
    if winner.get("status") not in {"QUALIFIED_CANDIDATE", "NO_QUALIFIED_CANDIDATE"}:
        raise ValueError(f"unknown winner state: {winner.get('status')}")
    if (winner.get("selected_case") != (ranking[0]["case"] if ranking else None)
            or [row["case"] for row in ranking] != winner.get("qualified_cases", [])):
        raise ValueError("winner does not match ranked qualified cases")
    check_rows = {(row["case"], row["constraint"], int(row["lead_hour"]),
                   float(row["threshold_mm"])): row for row in constraints}
    weak_table = table(["Case", "Low-threshold cells passed / 18", "Failed", "+1 h CSI@10",
                        "Strong condition", "Admitted"],
                       [[CASE_LABELS[case],
                         str(sum(check_rows[(case, "weak_CSI_at_least_ORIGINAL", lead, threshold)]["status"] == "PASS"
                                 for lead in LEADS for threshold in WEAK)),
                         str(sum(check_rows[(case, "weak_CSI_at_least_ORIGINAL", lead, threshold)]["status"] == "FAIL"
                                 for lead in LEADS for threshold in WEAK)),
                         fmt(cat[(1, case, 10.0)]["CSI"]),
                         check_rows[(case, "lead1_CSI10_strictly_greater_than_ORIGINAL", 1, 10.0)]["status"],
                         "yes" if case in passed else "no"] for case in NEW_CASES])
    ranked_table = "No candidate met both conditions; the criteria were not relaxed." if not ranking else table(
        ["Rank", "Case", "+1 h CSI@10", "+1 h CSI@5", "+1 h FAR@10", "+1 h RMSE (mm)"],
        [[row.get("rank", ""), CASE_LABELS[row["case"]], fmt(row.get("lead1_CSI_at_10mm")),
          fmt(row.get("lead1_CSI_at_5mm")), fmt(row.get("lead1_FAR_at_10mm")), fmt(row.get("lead1_RMSE_mm"))]
         for row in ranking])
    outcome, diagnostic = selection_narrative(winner, ranking, cat, check_rows)
    score_views = []
    for threshold in (0.1, 0.5, 1.0, 2.5, 5.0, 10.0):
        score_views.append(image_markdown(f"≥{threshold:g} mm CSI by lead", f"csi_absolute_{threshold:g}mm.png", figure_ref))
        score_views.append(image_markdown(f"≥{threshold:g} mm CSI difference from ORIGINAL", f"csi_delta_{threshold:g}mm.png", figure_ref))
    body_score_views = [score_views[1], score_views[-2]]
    algebra_views = [image_markdown(f"CSI algebra at ≥{threshold:g} mm", f"csi_algebra_decomposition_{threshold:g}mm.png", figure_ref)
                     for threshold in (0.1, 0.5, 1, 2.5, 5, 10)]
    gate_pair_views = [image_markdown(f"GATE−EQ CSI at ≥{threshold:g} mm", f"gate_minus_equal_mass_csi_{threshold:g}mm.png", figure_ref)
                       for threshold in (0.1, 0.5, 1, 2.5, 5, 10)]
    hourly_map_views = [image_markdown(f"Hourly RN1, forecast, and ORIGINAL difference: {CASE_LABELS[case]}", f"maps_{case.lower()}.png", figure_ref)
                        for case in receipt["cases"]]
    expected_figures = {f"csi_{kind}_{threshold:g}mm.png"
                        for kind in ("absolute", "delta") for threshold in (0.1, 0.5, 1, 2.5, 5, 10)}
    expected_figures |= {f"maps_{case.lower()}.png" for case in receipt["cases"]}
    expected_figures |= {"initial_precip_gate_maps.png", "initial_gate_concept.png"}
    expected_figures |= {f"gate_minus_equal_mass_csi_{threshold:g}mm.png"
                         for threshold in (0.1, 0.5, 1, 2.5, 5, 10)}
    expected_figures |= {f"csi_algebra_decomposition_{threshold:g}mm.png"
                         for threshold in (0.1, 0.5, 1, 2.5, 5, 10)}
    figure_manifest_path = FIGURES / "figure_manifest.json"
    figure_manifest = json.loads(figure_manifest_path.read_text(encoding="utf-8"))
    if figure_manifest.get("status") != "COMPLETE" or not expected_figures.issubset(figure_manifest.get("files", {})):
        raise ValueError("figure manifest lacks required score or gate/map figures")
    for name in expected_figures:
        path = FIGURES / name
        if not path.is_file() or digest(path) != figure_manifest["files"][name]:
            raise ValueError(f"figure is missing or differs from its manifest: {name}")
    gate_manifest_path = HERE / "runtime/frozen/gate_manifest.json"
    if digest(gate_manifest_path) != figure_manifest["initial_gate_source"]["gate_manifest_sha256"]:
        raise ValueError("frozen gate manifest differs from the rendered initial-field figure")
    gate_manifest = json.loads(gate_manifest_path.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    original_input_sha256 = plan["parents"]["original_wrfinput_sha256"]
    if (gate_manifest.get("forecast_output_or_observation_used") is not False
            or gate_manifest.get("source_wrfinput_sha256") != original_input_sha256
            or gate_manifest.get("frozen_map_sha256") != figure_manifest["initial_gate_source"]["source_map_sha256"]):
        raise ValueError("gate manifest does not match the input-only frozen initial map contract")
    gate_controls = gate_manifest["gate_controls"]
    stage3_json_path = REVIEW / "stage3_probe.json"
    stage3_markdown_path = REVIEW / "stage3_probe.md"
    stage3_review_path = REVIEW / "stage3_probe_review.json"
    if (digest(stage3_json_path) != "f2583c72a6f3ac386c0c01b8e3a2ed4b3d32cca412c770ddfe7ecede6c48507a"
            or digest(stage3_markdown_path) != "1fa4c9dbf8d323ec0304b5cfb4b0847adc468b31b65c95415f2316a057c30fe2"
            or digest(stage3_review_path) != "aa29987a64fe443fa436378422a9299eb6710d8e4772f36c8d95bc69cf7eae52"):
        raise ValueError("stage-3 source-probe or review hash mismatch")
    stage3_probe = json.loads(stage3_json_path.read_text(encoding="utf-8"))
    stage3_review = json.loads(stage3_review_path.read_text(encoding="utf-8"))
    if stage3_review.get("result") != "PASS" or not all(stage3_review["checks"].values()):
        raise ValueError("stage-3 probe review did not pass its evidence checks")
    selected_cell = stage3_probe["runtime_capture"]["selected_hydro_cell"]
    selected_mass = float(selected_cell["inner_entry_qrs_kg_kg"])
    sample_counts = stage3_probe["initial_input_samples"]["sample_counts_where_qrain_positive_and_qnrain_zero"]
    sample_text = ", ".join(f"{arm.split('_')[0]} {count}" for arm, count in sample_counts.items())
    stage3_summary = (
        "## 6. 실행파일 교차 해석과 다음 진단 단계\n\n"
        + f"별도의 제한된 KDM6 소스·실행 캡처 검토에서는 HYDRO 선택 셀 {selected_cell['point']}의 첫 내부 호출 입력에서 "
        f"QRAIN 질량은 {selected_mass:.6g} kg kg⁻¹였지만 내부 QNRAIN 수 모멘트는 float32 0이었다. "
        "초기 입력의 네 점·네 격자 모서리·39층 표본에서는 양의 QRAIN과 0 QNRAIN이 각 arm에서 확인됐으나 "
        f"표본 수는 {sample_text}이며 전 영역 빈도나 전체 첫 호출 소비를 뜻하지 않는다. "
        "캡처된 부동소수점 식은 음의 습도 인자와 양의 0을 곱해 음의 0을 만들었다. 소스 순서상 양의 0 피연산자가 $n_{0r}$일 가능성은 있지만, "
        "디버그 심볼이 없어 해당 기계 피연산자와 기호의 대응은 추론이다. BASE–fixed 소스 차이는 zero-rate limiter 조건 한 곳이고, "
        "그 guard는 포화 제한률이 비·수증기와 잠열 온도 항에 미치는 효과를 바꾸지만 누락된 QNRAIN을 생성하지 않는다. "
        "이 독립 소스 조사와 선택 셀 캡처는 위 점수 대비의 원인임을 증명하지 않으며, 강수 skill 향상이나 검증된 수 모멘트 초기화를 주장하지 않는다. "
        "다음 단계는 QRAIN/QNRAIN의 권위 있는 초기화·분석 작성 경로와 의도된 입자 크기분포 또는 관측 제약을 확인하는 것이다. "
        "질량만으로 수 모멘트는 정해지지 않으므로 $n_{r,min}$을 물리적 seed로 간주하지 말고, 후보 정책은 강수·수증기·온도 예산을 함께 검증해야 한다."
    )
    gate_metadata_table = table(
        ["Positive-X percentile interval", "Gate α(x,y) range", "Uniform EQ α", "Initial mass mismatch"],
        [[interval, f"{gate_controls[pair]['gate_alpha_min']:.1f}–{gate_controls[pair]['gate_alpha_max']:.1f}",
          f"{gate_controls[pair]['equal_mass_alpha']:.6f}",
          f"{gate_controls[pair]['relative_mass_difference']:.3e}"]
         for pair, interval in (("G50_90", "50–90%"), ("G75_95", "75–95%"), ("G90_99", "90–99%"))]
    )
    gate50 = cat[(1, "GATE_G50_90", 10.0)]
    eq50 = cat[(1, "EQ_G50_90", 10.0)]
    original50 = cat[(1, "ORIGINAL", 10.0)]
    control50 = cat[(1, "CONTROL_SNOW_300", 10.0)]
    gate50_weak_failures = sum(
        check_rows[("GATE_G50_90", "weak_CSI_at_least_ORIGINAL", lead, threshold)]["status"] == "FAIL"
        for lead in LEADS for threshold in WEAK
    )
    eq50_weak_failures = sum(
        check_rows[("EQ_G50_90", "weak_CSI_at_least_ORIGINAL", lead, threshold)]["status"] == "FAIL"
        for lead in LEADS for threshold in WEAK
    )
    cross_threshold = 0.1
    cross_leads = (2, 3, 4, 6)
    factorial_rows = []
    for lead in cross_leads:
        def simple_contrast(case_a: str, case_b: str) -> str:
            row_a = cat[(lead, case_a, cross_threshold)]
            row_b = cat[(lead, case_b, cross_threshold)]
            delta_csi = float(row_a["CSI"]) - float(row_b["CSI"])
            delta_hit = int(row_a["hit"]) - int(row_b["hit"])
            delta_fa = int(row_a["false_alarm"]) - int(row_b["false_alarm"])
            return f"{delta_csi:+.5f} (ΔH {delta_hit:+d}, ΔFA {delta_fa:+d})"
        factorial_rows.append([
            f"+{lead} h",
            simple_contrast("FIXED_ORIGINAL_100", "ORIGINAL"),
            simple_contrast("IMPROVED_BG_FIXED", "ORIGINAL_B1_100"),
            simple_contrast("ORIGINAL_B1_100", "ORIGINAL"),
            simple_contrast("IMPROVED_BG_FIXED", "FIXED_ORIGINAL_100"),
        ])
    factorial_table = table(
        ["Lead", "Execution change · ORIGINAL input", "Execution change · B1 input",
         "Input change · ORIGINAL executable", "Input change · fixed executable"], factorial_rows)
    contrast_summary = (
        f"+1 h, ≥10 mm에서 GATE_G50_90 CSI는 {float(gate50['CSI']):.6f}, "
        f"짝 EQ_G50_90은 {float(eq50['CSI']):.6f}, ORIGINAL은 {float(original50['CSI']):.6f}, "
        f"기존 CONTROL α=3은 {float(control50['CSI']):.6f}였다. "
        f"공간 게이트가 강한 임계값 CSI에서 균일 질량 대조보다 높았지만, GATE의 낮은 임계값 보호 셀 중 "
        f"{gate50_weak_failures}/18, EQ는 {eq50_weak_failures}/18이 기준을 밑돌아 어느 쪽도 적격이 아니었다. "
        "이 결과는 이 사례에서 강한 임계값 한 셀의 배치 효과와 사전 지정한 전체 균형 조건이 다름을 보인다. "
        "다음 표는 +2, +3, +4, +6 h의 2×2 단순 대비를 분리한다(각 셀은 ΔCSI, ΔH, ΔFA). "
        "같은 입력에서 실행파일을 바꾼 변화는 B1 입력과 ORIGINAL 입력에서 크기가 달랐고, 입력 대비도 실행파일에 따라 달랐다. "
        "이는 이 표본의 점수 대비이며 미세물리 원인이나 일반적 실행파일 효과의 인과 추정이 아니다. "
        "후속 단계는 실행파일 차이에 대응하는 초기화·모델 응답을 보존 수지와 함께 진단해야 한다; "
        "현재 점수만으로 특정 융해·증발 과정이나 물리 인과를 지정할 수 없다."
    )

    report = [
        "# 약한 강수와 강한 강수의 균형: 초기 눈 증가의 공간 배치 실험",
        "",
        "## 초록",
        "2026년 8월 16일 12 UTC의 단일 사례에서 초기 강수 수종 기둥 평균을 기준으로 선택한 고값 영역에 QSNOW를 증가시키고, 초기 건조 공기 질량 가중 QSNOW 총량을 맞춘 균일 증가 대조군과 비교했다. 추가로 실행파일과 초기 입력을 교차한 두 진단 실험을 포함했다. 평가에는 공통 RN1 분석점 3,688개의 시간별 지상 총강수와 여섯 임계값을 사용했다. 낮은 강수 임계값 CSI를 여섯 예측시간 모두에서 기존 ORIGINAL 이상으로 유지하고 +1 h CSI@10 mm를 엄격히 높이는 두 조건을 사전에 고정했다. " + outcome,
        "",
        "## 1. 배경과 연구 질문",
        audit_old_tradeoffs(cat),
        "이 결과는 모든 임계값·시간에서 일관된 개선이 흔하지 않다는 문제를 보여 준다. 이번 실험은 강한 강수 기준에서 유리한 변화가 낮은 강수 임계값 CSI의 시간별 바닥 조건을 만족하는지, 그리고 같은 초기 QSNOW 총량에서 공간 배치만 달라질 때 예보 점수의 차이가 나타나는지 시험한다. 낮은 임계값 CSI에는 큰 강수 사건의 적중도 포함되므로, 이를 관측된 약한 강수 강도만의 검증으로 해석하지 않는다.",
        "",
        "## 2. 설계 및 물리적 정의",
        "### 2.1 초기 강수 수종 게이트",
        "WRF 문서는 수직 좌표를 지표 부근에서 지형 추종하고 지정 고도부터 등압면으로 전이되는 hybrid terrain-following mass coordinate로 설명한다 ([WRF Dynamics: Hybrid Vertical Coordinate](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/dynamics.html), 2026-10-30 확인). 아래 층 가중치 $\\Delta p_d$는 해당 웹페이지 식을 직접 대입한 값이 아니라 이 저장소의 `tools/check_native_hybrid_geometry.py::read_geometry`가 HYBRID_OPT=2 계수와 closure 검사를 적용해 계산한 값이다.",
        r"ORIGINAL 초기장에서 각 수평 기둥의 진단값을 $X=\frac{\sum_k (QRAIN_k+QSNOW_k+QGRAUP_k)\,\Delta p_{d,k}}{\sum_k\Delta p_{d,k}}$로 정의했다. 이는 초기 강수 수종 혼합비의 기둥 평균 proxy이며, 향후 강수량이나 지상 강우 예측량이 아니다. $\Delta p_d$는 HYBRID_OPT=2 계수로 계산한 건조 공기 질량 층 가중치다. 이 계산은 초기 입력장만 사용하며 예보 출력과 관측값은 게이트 설정에 쓰지 않는다.",
        r"양의 $X$ 값의 사전 고정 분위수 두 개 사이에서 로그 $X$를 선형 정규화한 $u$를 만들고 $w=u^2(3-2u)$, $\alpha=1+2w$를 적용한다. 세 마스크 G50–90, G75–95, G90–99의 고-$X$ 끝은 각각 90, 95, 99 백분위다. 바깥쪽 저-$X$ 영역은 $\alpha=1$을 유지하고, 같은 2-D $\alpha$를 모든 QSNOW 질량층에 적용했다. 따라서 이 설정은 약한 초기 강수 기둥의 QSNOW를 낮추는 것이 아니라 기존 눈을 보존하고 선택된 기둥에 더한다.",
        r"$q_s^{gate}=\mathrm{REAL32}[\alpha(x,y)\,\mathrm{REAL64}(q_s^{orig})]$. 여기서 QSNOW는 초기 대기 중 눈 수상체의 혼합비(kg kg$^{-1}$)이며 지상 적설 깊이나 지상 눈 강수량이 아니다. 각 균일 증량 EQ 케이스는 짝 GATE 케이스와 건조 공기 질량 가중 초기 QSNOW 총량이 $10^{-6}$ 상대오차 이내가 되도록 맞췄다. 두 케이스의 눈 총량은 ORIGINAL보다 크다. 이 일치는 **초기 눈 총량 진단값**에만 해당한다. 수증기·비·싸락눈·온도·에너지 보상을 하지 않으며 입자 수농도·크기분포·엔탈피도 고정하지 않으므로 전체 물·에너지 보존이나 초기화의 완전한 보존성을 뜻하지 않는다.",
        image_markdown("초기 X에서 게이트·질량 일치 대조를 거쳐 시간별 CSI를 계산하는 흐름", "initial_gate_concept.png", figure_ref),
        "G50–90, G75–95, G90–99는 양의 초기 X 열의 경험적 백분위 구간을 뜻한다(50–90 mm 강수량 구간이 아니다). 게이트 입력은 ORIGINAL 초기 기둥의 강수 수종 혼합비 진단값이다. 이 값은 지상 강수 관측이나 예보 출력이 아니며 그 자체가 지상 강수의 발생·강도를 보장하지 않는다.",
        image_markdown("초기 강수 수종 게이트, α, 질량 일치 공간 배치", "initial_precip_gate_maps.png", figure_ref),
        gate_metadata_table,
        "열의 α(x,y)는 공간게이트의 범위다. Uniform EQ α는 각 짝 GATE의 초기 건조 질량 가중 QSNOW 총량을 맞추는 별도의 균일 계수다. GATE의 공간 평균 α를 EQ scalar와 동일시하지 않는다.",
        "각 GATE/EQ 짝은 초기 건조 질량 가중 QSNOW 양을 맞춘다. 점수 차이는 이 한 사례에서 배치가 다른 두 초기장에 대한 예보 반응을 나타낸다. 질량 일치는 초기 수상체 분포와 이후 응결·융해·낙하·수송의 동일성을 보장하지 않는다.",
        "### 2.2 두 요인 실행파일/입력 교차 진단",
        "FIXED_ORIGINAL_100은 수정 실행파일과 ORIGINAL 입력을, ORIGINAL_B1_100은 ORIGINAL 실행파일과 B1 입력을 사용한다. ORIGINAL과 B1 자체를 포함하면 실행파일 상태와 입력 계보의 2×2 대조가 된다. CSI·오차 차이와 차이의 차이는 비선형 검증 점수의 통계적 대조다. 단일 미세물리 과정의 인과 기여량으로 해석하지 않는다.",
        "### 2.3 강수 검증 정의",
        r"지상 누적 총강수 $C=RAINC+RAINNC$에서 시간별 한 시간 총강수량 $P_h=C(t_0+h)-C(t_0+h-1)$을 계산했다. 검증량은 눈 강수만이 아니라 강수 전체다. 따라서 +6 h는 17–18 UTC 시간창이며 초기시각부터의 6시간 누적이 아니다. CSI=$H/(H+M+FA)$, FAR=$FA/(H+FA)$다. 낮은 강수 임계값은 0.1, 0.5, 1 mm이고 강한 사건의 사전 지정 지표는 +1 h 10 mm CSI다. 이 임계값은 본 연구 설계값이지 공식 특보 등급이 아니다.",
        "모든 사례는 동일한 처리 RN1 분석의 동일 3,688점과 공통 시간창을 사용했다. 모델−RN1 차이는 예보 오차와 RN1 분석·대표성·품질관리 오차를 함께 포함할 수 있으며 이 자료만으로 두 오차를 분리하지 않는다. 관측 품질과 마스크 coverage의 불확실성이 남아 있으므로 RN1은 독립적인 관측 진실값이나 전국적인 coverage의 보증으로 부르지 않는다.",
        "",
        "## 3. 사전 지정 적격성 및 순위",
        "후보별로 여섯 lead × 낮은 임계값 세 개의 모든 18개 셀(0.1, 0.5, 1 mm)에서 CSI ≥ ORIGINAL이어야 한다(허용오차 0). 동시에 +1 h CSI@10 mm > ORIGINAL이어야 한다(엄격 비교, 허용오차 0). 두 조건은 모두 필수다. CSI의 낮은 임계값 사건에는 강한 강수 적중도 포함될 수 있어 약한 강도 전용 점수는 아니다. 적격 후보가 없으면 개선안을 선정하지 않는다. 통과한 경우에만 +1 h CSI@10 내림차순, CSI@5 내림차순, FAR@10 오름차순, RMSE 오름차순, ID 오름차순으로 순위화한다.",
        weak_table,
        outcome,
        *([diagnostic] if diagnostic else []),
        ranked_table,
        "",
        "## 4. 시간·임계값별 결과",
        "낮은 임계값 바닥과 사전 지정 강한 임계값의 대표 결과를 보인다. 각 lead는 별개의 한 시간 검증이며 threshold·lead 평균은 순위·주장에 사용하지 않았다. 여섯 임계값 전체, 정확한 적중·오경보 분해, paired gate contrasts, 모든 사례의 시간별 지도는 부록 B에 따로 제시한다.",
        contrast_summary,
        factorial_table,
        *body_score_views,
        "### 적중·오경보 변화의 CSI 대수 분해",
        r"같은 관측 지점 집합에서 각 케이스의 관측 사건 수 $O=H+M$는 ORIGINAL과 같다. 기준 및 후보 CSI 분모를 각각 $D_0=O+F_0$, $D_c=O+F_c$라 놓고 $\Delta H=H_c-H_0$, $\Delta F=F_c-F_0$라 하면 $\Delta CSI=H_c/D_c-H_0/D_0=\Delta H/D_c-H_0\Delta F/(D_0D_c)$. 분모가 양수일 때 부호는 $\Delta H-CSI_0\Delta F$의 부호와 같아 적중 변화와 오경보 변화의 크기를 함께 고려한다. 두 항의 합은 관측된 $\Delta CSI$와 같다. 이는 점수식의 정확한 대수 분해이지 모델 물리 과정의 기여도나 인과효과가 아니다.",
        "각 그림은 임계값별로 모든 12개 문맥과 6개 lead를 표시한다. 세 패널은 적중 변화 항, 오경보 변화 항, 순 ΔCSI이며 세 패널의 색 범위는 해당 그림 안에서 공통이고 0 중심이다. 항을 시간·임계값·사례별로 평균하지 않는다.",
        "### 공간 게이트와 균일 질량 대조",
        "각 칸은 같은 초기 QSNOW 건조 질량 진단 총량을 가진 GATE와 EQ 예보 CSI 차이다. +값은 해당 점수에서 공간 게이트가 높고 −값은 균일 대조가 높음을 나타낸다. 이 비교는 초기량을 맞춘 공간배치 실험의 점수 반응이며, 이후 미세물리 과정의 원인 분석은 아니다.",
        gate_pair_views[-1],
        "### 시간별 강수량 분포",
        "모든 hour별 RN1·case·같은 점 ORIG 대비 강수차 지도는 부록 B에 있다. 차이 지도는 새 값을 공간 보간하지 않으며 전 사례·전 예측시간에 공통 영점 중심 색 범위를 쓴다.",
        "",
        "## 5. 해석",
        "각 게이트/EQ 짝은 초기 QSNOW 총량을 제약해 양과 배치의 영향을 구별하도록 설계했다. 점수의 차이가 나타나도 이것은 동일 질량의 두 공간 배치에 따른 **예보 결과 차이**다. 관측점 검증 CSI의 비선형 변화 자체가 눈의 물리과정별 원인을 식별하지 않으며, 개별 융해·증발 과정을 귀속할 진단·플럭스·전체 보존 수지가 없다. 이 사례만으로는 QSNOW 변경 효과와 입자 크기분포·엔탈피 등 다른 미세물리 상태의 변화를 분리할 수 없다.",
        "두 교차 실행 실험도 계산의 검증 결과를 비교하는 실행파일/입력 조합이다. interaction 항은 그 점수 체계에서의 차이의 차이이며, 개별 수정의 보편적 인과효과가 아니다. 여덟 새 예보는 하나의 초기 사례·강수 상황에 대한 진단이다. 독립 사례 예측 성능이나 운영 적합성을 증명하지 않는다.",
        stage3_summary,
        "",
        "## 부록 B. 전체 임계값 그림과 시간별 지도",
        "본 부록은 모든 임계값별 절대 CSI·ORIGINAL 대비 ΔCSI와 정확한 CSI 대수 항을 별도 그림으로 둔다. gate/equal-mass paired CSI도 threshold별로 분리했다. 각 지도는 같은 점 위치의 RN1 분석, case hourly total, case−ORIGINAL ΔP 세 열과 여섯 lead로 구성되며 ΔP는 실제 extrema 전체를 포함하는 공통 zero-centered scale을 사용한다.",
        *score_views,
        *algebra_views,
        *gate_pair_views,
        *hourly_map_views,
        "",
        "## 7. 자료와 재현성",
        f"- 동결 실험·선정 계획: [selection_plan.json](evidence/weak_strong_balance_20261030/selection_plan.json), SHA-256 `{PLAN_SHA256}`.",
        "- 분석 점수·전이·초기장 대조: [analysis outputs](evidence/weak_strong_balance_20261030/analysis/receipt.json) 및 [전체 점수 부록](WEAK_STRONG_BALANCE_FULL_SCORES_20261030.md).",
        "- 기존 설정의 비교 감사: [원자료 셀표](evidence/weak_strong_balance_20261030/review/results.csv) · [감사 영수증](evidence/weak_strong_balance_20261030/review/results.json) · [관측 강도별 전이표](evidence/weak_strong_balance_20261030/review/prior_observed_band.csv) · [전이표 영수증](evidence/weak_strong_balance_20261030/review/prior_observed_band_receipt.json).",
        "- 실행파일의 rain-number 초기화와 zero-rate limiter를 따로 조사한 읽기 전용 source probe: [분석](evidence/weak_strong_balance_20261030/review/stage3_probe.md) · [machine-readable evidence](evidence/weak_strong_balance_20261030/review/stage3_probe.json) · [독립 검토](evidence/weak_strong_balance_20261030/review/stage3_probe_review.json).",
        "- 실행파일, 초기 입력, 공통 입력, 시간별 산출물은 runtime 계획과 사례별 영수증에 SHA-256으로 결속한다. 모든 예보는 pinned Intel 프로파일에서 실행하고 source tree 밖의 scratch 디렉터리를 사용했다.",
        "- 낮은 임계값 점수 전이와 관측 강수구간별 보조 진단은 [observation_band_transitions.csv](evidence/weak_strong_balance_20261030/analysis/observation_band_transitions.csv) 및 [observed_forecast_bin_counts.csv](evidence/weak_strong_balance_20261030/analysis/observed_forecast_bin_counts.csv)에 있다. 이 구간별 진단은 사전 적격성 조건을 바꾸지 않는다.",
        "- [그림 manifest](evidence/weak_strong_balance_20261030/figures/figure_manifest.json)와 이 빌더의 receipt는 생성 이미지와 보고서 hash를 기록한다.",
        "",
        "## 제한 사항",
        "단일 사례의 사후 분석, RN1 처리자료 사용, 공통 점수 마스크의 범위, 초기 QSNOW만 변경하는 진단 개입, 건조 질량 가중 눈 총량만 맞춘 EQ 비교, 전체 물·에너지 수지 미계산, 강수 종별 과정 플럭스 미분리, 실행파일×입력 interaction의 비선형 점수 해석을 포함한다. 점수와 그림은 이 한 사례의 약한/강한 강수 균형을 설명하며 일반 예측 향상을 보증하지 않는다.",
        "",
        "## 부록 A. 재현 자료와 hash inventory",
        "분석 영수증은 아래 데이터·모델·도구 입력과 생성 배열/점수의 SHA-256을 결속한다. 경로는 영수증의 원 경로이며 빌드한 호스트의 파일 위치를 나타낸다.",
    ]
    source_rows = [[str(row["path"]), str(row["sha256"]), str(row.get("size_bytes", ""))]
                   for row in receipt.get("sources", [])]
    report.append(table(["Bound source", "SHA-256", "Bytes"], source_rows))
    report.append(
        "추가 표본 독립성·검증을 의미하지 않는 비교 자료: prior trade-off audit source SHA-256 "
        f"`{digest(REVIEW / 'prior_tradeoff_audit.py')}`, CSV `{digest(REVIEW / 'results.csv')}`, "
        f"audit JSON `{digest(REVIEW / 'results.json')}`. "
        f"관측 강도 audit CSV `{digest(REVIEW / 'prior_observed_band.csv')}`, "
        f"audit receipt `{digest(REVIEW / 'prior_observed_band_receipt.json')}`. "
        f"Stage-3 source probe JSON `{digest(stage3_json_path)}`, Markdown `{digest(stage3_markdown_path)}`, "
        f"review `{digest(stage3_review_path)}`. "
        f"초기 게이트 지도 NPZ SHA-256 `{figure_manifest['initial_gate_source']['source_map_sha256']}`, "
        f"gate manifest SHA-256 `{figure_manifest['initial_gate_source']['gate_manifest_sha256']}`. "
        f"prior observed-band CSV SHA-256 `{digest(REVIEW / 'prior_observed_band.csv')}`, "
        f"receipt SHA-256 `{digest(REVIEW / 'prior_observed_band_receipt.json')}`. "
        "파일별 출력 SHA-256은 [analysis receipt](evidence/weak_strong_balance_20261030/analysis/receipt.json)와 "
        "[figure manifest](evidence/weak_strong_balance_20261030/figures/figure_manifest.json)에 있다."
    )
    OUTPUT.write_text("\n\n".join(report) + "\n", encoding="utf-8")
    build_figures_index(figure_manifest, figure_ref)
    (HERE / "report_receipt.json").write_text(json.dumps({
        "report": OUTPUT.relative_to(ROOT).as_posix(), "report_sha256": digest(OUTPUT),
        "builder_sha256": digest(Path(__file__)),
        "analysis_receipt_sha256": digest(ANALYSIS / "receipt.json"),
        "figure_manifest_sha256": digest(figure_manifest_path),
        "figures_document_sha256": digest(FIGURES_OUTPUT),
        "figures_document_receipt_sha256": digest(HERE / "figures_doc_receipt.json"),
        "figure_ref_template": figure_ref,
        "selection_plan_sha256": PLAN_SHA256, "status": winner["status"],
        "selected_case": selected,
    }, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--figure-ref", help="HTTPS image URL template containing {name}; no URLs are fetched")
    main(parser.parse_args().figure_ref)
