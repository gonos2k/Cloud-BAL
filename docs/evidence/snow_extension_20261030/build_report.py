#!/usr/bin/env python3
"""Build the extension report only from hash-sealed scoring outputs."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ANALYSIS = HERE / "analysis"
FIGURES = HERE / "figures"
OUTPUT = ROOT / "docs/SNOW_HEAVY_EXTENSION_20261030.md"
PLAN_SHA256 = "36e094ac84d698351cdc477ec0bb58fd7580e0676e9ed830236a7d52b0818642"
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
LEADS = tuple(range(1, 7))
FAMILIES = ("CONTROL", "IMPROVED")
FACTORS = (0, 25, 50, 75, 125, 150, 175, 200, 250, 300)
NEW_FACTORS = FACTORS[6:]
VARIANTS = tuple(f"{family}_SNOW_{factor:03d}" for family in FAMILIES for factor in FACTORS)
NEW_CASES = tuple(f"{family}_SNOW_{factor:03d}" for family in FAMILIES for factor in NEW_FACTORS)
CASES = ("ORIGINAL", "CURRENT_HYDRO", "IMPROVED_BG_FIXED", *VARIANTS)
ELIGIBLE = tuple(case for case in CASES if case != "CURRENT_HYDRO")
BASE_CASES = ("ORIGINAL", "CURRENT_HYDRO", "IMPROVED_BG_FIXED",
              *(f"{family}_SNOW_{factor:03d}" for family in FAMILIES for factor in FACTORS[:6]))
LABELS = {"ORIGINAL": "규준 실험", "CURRENT_HYDRO": "기존 HYDRO (참고)",
          "IMPROVED_BG_FIXED": "기존 개선안 B1"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(name: str) -> list[dict[str, str]]:
    with (ANALYSIS / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def read_csv_path(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def label(case: str) -> str:
    if case in LABELS:
        return LABELS[case]
    family, _, suffix = case.split("_")
    return f"{'규준 계열' if family == 'CONTROL' else '개선 계열'} α={int(suffix) / 100:g}"


def table(headers: list[str], rows: list[list[str]]) -> str:
    return "\n".join(["| " + " | ".join(headers) + " |",
                      "| " + " | ".join(["---"] * len(headers)) + " |",
                      *["| " + " | ".join(row) + " |" for row in rows]])


def validate() -> tuple[dict, list[dict], list[dict], list[dict], dict, tuple[str, ...]]:
    receipt = json.loads((ANALYSIS / "receipt.json").read_text(encoding="utf-8"))
    if receipt.get("status") not in ("COMPLETE", "PARTIAL"):
        raise ValueError("score receipt does not contain usable tables")
    for name, item in receipt["analysis_outputs"].items():
        path = ANALYSIS / name
        if (path.is_symlink() or not path.is_file() or path.stat().st_size != item["size_bytes"]
                or digest(path) != item["sha256"]):
            raise ValueError(f"changed analysis output: {name}")
    if digest(HERE / "selection_plan.json") != PLAN_SHA256:
        raise ValueError("frozen selection plan hash mismatch")
    categorical = read_csv("categorical_scores.csv")
    continuous = read_csv("continuous_scores.csv")
    choices = read_csv("selection_scores.csv")
    selection = json.loads((ANALYSIS / "selection.json").read_text(encoding="utf-8"))
    scored_cases = tuple(case for case in CASES if any(row["case"] == case for row in continuous))
    if not set(BASE_CASES).issubset(scored_cases):
        raise ValueError("previous 14 eligible cases and CURRENT_HYDRO context are required")
    if len(categorical) != len(scored_cases) * 36 or len(continuous) != len(scored_cases) * 6:
        raise ValueError("score tables must cover each completed case across all windows and thresholds")
    cat = {(int(row["lead_hour"]), row["case"], float(row["threshold_mm"])): row for row in categorical}
    cont = {(int(row["lead_hour"]), row["case"]): row for row in continuous}
    if len(cat) != len(scored_cases) * 36 or len(cont) != len(scored_cases) * 6:
        raise ValueError("duplicate categorical or continuous score keys")
    if set(cat) != {(lead, case, threshold) for lead in LEADS for case in scored_cases for threshold in THRESHOLDS}:
        raise ValueError("categorical score coverage differs from frozen design")
    if set(cont) != {(lead, case) for lead in LEADS for case in scored_cases}:
        raise ValueError("continuous score coverage differs from frozen design")
    all_eligible = set(CASES) - {"CURRENT_HYDRO"}
    if {row["case"] for row in choices} != all_eligible:
        raise ValueError("selection table must retain all 22 eligible candidates, including failures")
    ranked_rows = [row for row in choices if row.get("rank") not in (None, "")]
    order = selection.get("selection_order")
    if order != [row["case"] for row in sorted(ranked_rows, key=lambda row: int(row["rank"]))]:
        raise ValueError("selection order differs from ranked score rows")
    if not order or selection.get("selected_case") != order[0]:
        raise ValueError("selection JSON fields do not identify the top-ranked case")
    return receipt, categorical, continuous, choices, selection, scored_cases


def build() -> str:
    receipt, categorical, continuous, choices, selection, scored_cases = validate()
    cat = {(int(row["lead_hour"]), row["case"], float(row["threshold_mm"])): row for row in categorical}
    cont = {(int(row["lead_hour"]), row["case"]): row for row in continuous}
    selected = selection["selected_case"]
    ranked = sorted((row for row in choices if row.get("rank") not in (None, "")),
                    key=lambda row: int(row["rank"]))
    unranked = sorted((row for row in choices if row.get("rank") in (None, "")),
                      key=lambda row: row["case"])
    def score(case: str, threshold: float, field: str) -> str:
        row = cat.get((1, case, threshold))
        if row is None or row[field] in ("", "None"):
            return "—"
        return f"{float(row[field]):.4f}"
    primary_table = table(["순위", "상태", "α", "실험", "CSI@10", "적중 H", "누락 M", "오경보 F", "CSI@5", "RMSE (mm)"],
        [[row.get("rank") or "미순위", row.get("runtime_status", "미완료"), f"{float(row['alpha']):g}",
          label(row["case"]), score(row["case"], 10.0, "CSI"),
          (cat[(1, row["case"], 10.0)]["hit"] if (1, row["case"], 10.0) in cat else "—"),
          (cat[(1, row["case"], 10.0)]["miss"] if (1, row["case"], 10.0) in cat else "—"),
          (cat[(1, row["case"], 10.0)]["false_alarm"] if (1, row["case"], 10.0) in cat else "—"),
          score(row["case"], 5.0, "CSI"), row.get("lead1_RMSE_mm") or "—"]
         for row in (*ranked, *unranked)])
    comparison_cases = ("ORIGINAL", *NEW_CASES)
    comparison_rows = []
    for case in comparison_cases:
        alpha = 1.0 if case == "ORIGINAL" else int(case.rsplit("_", 1)[-1]) / 100
        values = ["—" if (lead, case, 10.0) not in cat or cat[(lead, case, 10.0)]["CSI"] in ("", "None")
                  else f"{float(cat[(lead, case, 10.0)]['CSI']):.4f}" for lead in LEADS]
        status = "완료" if (1, case, 10.0) in cat else "미완료 · 미순위"
        comparison_rows.append([label(case), f"{alpha:g}", status, *values])
    new_cases_control_table = table(["실험", "α", "상태", *[f"+{lead} h CSI@10" for lead in LEADS]],
                                    comparison_rows)
    lead_sections = []
    for lead in LEADS:
        rows = []
        for case in scored_cases:
            cells = []
            for threshold in THRESHOLDS:
                row = cat[(lead, case, threshold)]
                csi = "—" if row["CSI"] in ("", "None") else f"{float(row['CSI']):.4f}"
                cells.append(f"{csi} ({row['hit']}/{row['miss']}/{row['false_alarm']})")
            rows.append([label(case), *cells])
        lead_sections.extend([f"### +{lead}시간 · {lead + 11:02d}–{lead + 12:02d} UTC",
          table(["실험", *[f"≥{threshold:g} mm: CSI (H/M/FA)" for threshold in THRESHOLDS]], rows)])
    error_rows = [[f"+{lead} h", label(case), f"{float(cont[(lead, case)]['MAE_mm']):.4f}",
                   f"{float(cont[(lead, case)]['RMSE_mm']):.4f}"] for lead in LEADS for case in scored_cases]
    c10 = float(cat[(1, selected, 10.0)]["CSI"])
    c5 = float(cat[(1, selected, 5.0)]["CSI"])
    far10 = float(cat[(1, selected, 10.0)]["FAR"])
    selected_csi_2h = float(cat[(2, selected, 10.0)]["CSI"])
    original_csi_2h = float(cat[(2, "ORIGINAL", 10.0)]["CSI"])
    b1_csi_2h = float(cat[(2, "IMPROVED_BG_FIXED", 10.0)]["CSI"])
    selected_csi_6h = float(cat[(6, selected, 10.0)]["CSI"])
    original_csi_6h = float(cat[(6, "ORIGINAL", 10.0)]["CSI"])
    b1_csi_6h = float(cat[(6, "IMPROVED_BG_FIXED", 10.0)]["CSI"])
    b1c10 = float(cat[(1, "IMPROVED_BG_FIXED", 10.0)]["CSI"])
    b1c5 = float(cat[(1, "IMPROVED_BG_FIXED", 5.0)]["CSI"])
    b1far10 = float(cat[(1, "IMPROVED_BG_FIXED", 10.0)]["FAR"])
    selected_10 = cat[(1, selected, 10.0)]
    original_10 = cat[(1, "ORIGINAL", 10.0)]
    observed_10 = int(selected_10["hit"]) + int(selected_10["miss"])
    if observed_10 != int(original_10["hit"]) + int(original_10["miss"]):
        raise ValueError("paired cases disagree on observed ≥10-mm events")
    strong_score_math = (
        f"+1시간 ≥10 mm에서 공통 관측 사건 수 $O=H+M$는 {observed_10}개다. "
        f"{label(selected)}의 CSI는 $H/(O+FA)={selected_10['hit']}/({observed_10}+{selected_10['false_alarm']})="
        f"{c10:.4f}$, 규준 실험은 ${original_10['hit']}/({observed_10}+{original_10['false_alarm']})="
        f"{float(original_10['CSI']):.4f}$다. 총 적중 수 변화는 "
        f"{int(selected_10['hit']) - int(original_10['hit']):+d}개, 오경보 수 변화는 "
        f"{int(selected_10['false_alarm']) - int(original_10['false_alarm']):+d}개다. "
        "이는 임계값 점수식의 산술 비교이며, 새 적중 전이 수나 미세물리 과정의 인과 귀속을 뜻하지 않는다.")
    transitions_path = HERE / "review" / "independent_transitions.csv"
    transitions = read_csv_path(transitions_path)
    transition_rows = {(row["baseline_case"], int(row["lead_hour"]), float(row["threshold_mm"])): row
                       for row in transitions if row["selected_case"] == selected}
    expected_transitions = {
        "ORIGINAL": (13, 0, 15, 0),
        "IMPROVED_BG_FIXED": (10, 0, 15, 0),
    }
    for baseline, expected in expected_transitions.items():
        row = transition_rows.get((baseline, 1, 10.0))
        actual = tuple(int(row[field]) for field in
                       ("new_hits", "lost_hits", "new_false_alarms", "removed_false_alarms")) if row else None
        if actual != expected:
            raise ValueError(f"independent lead-1 transition counts differ for {baseline}: {actual}")
    transition_text = (
        "격자별 전이 집계에서 +1시간 ≥10 mm의 규준 대비 적중 변화는 새 적중 13·적중 소실 0, "
        "오경보 변화는 새 오경보 15·제거 0이다. B1 대비 각각 10·0 및 15·0이다. "
        "이는 점수 차이를 설명하는 격자별 전이 집계다. 자세한 행은 "
        "[격자별 전이표](evidence/snow_extension_20261030/review/independent_transitions.csv)에 있다.")
    selected_rmse = float(cont[(1, selected)]["RMSE_mm"])
    b1_rmse = float(cont[(1, "IMPROVED_BG_FIXED")]["RMSE_mm"])
    selected_alpha = float(next(row["alpha"] for row in choices if row["case"] == selected))
    error_context = (f" +1시간 RMSE는 {selected_rmse:.4f} mm로 B1보다 "
                     f"{selected_rmse - b1_rmse:+.4f} mm이며 연속 오차 맥락으로 함께 보고한다. "
                     "RMSE는 CSI@10, CSI@5, FAR@10이 모두 동률일 때만 뒤따르는 순위 기준이다.")
    endpoint_context = (" 선정 배율은 시험한 최댓값 α=3.0이다. 더 높은 배율은 시험하지 않아 이 결과로 반응 정점이나 고배율 이후 단조성을 주장할 수 없다."
                       if selected_alpha == 3.0 else "")
    figure_names = ("strong_precipitation_csi.png", "selected_threshold_csi.png",
                    "new_cases_vs_control_csi.png",
                    "snow_extension_maps_leads_1_3.png", "snow_extension_maps_leads_4_6.png")
    figure_manifest_path = FIGURES / "figure_manifest.json"
    figure_manifest = json.loads(figure_manifest_path.read_text(encoding="utf-8"))
    if figure_manifest.get("status") != "COMPLETE" or figure_manifest.get("selected_case") != selected:
        raise ValueError("figure manifest does not match the selected scored case")
    for name in figure_names:
        path = FIGURES / name
        if (not path.is_file() or figure_manifest.get("figure_sha256", {}).get(name)
                != digest(path)):
            raise ValueError(f"missing or changed finalized figure: {name}")

    parts = [
      "# 고강수 임계값 중심 초기 눈 혼합비 민감도 확장",
      "## 요약",
      f"2026년 8월 16일 12 UTC 사례에서 기존 14개 적격 실험에 CONTROL·IMPROVED 두 계열의 α=1.75, 2.0, 2.5, 3.0 예보 8개를 추가 편성했다. 완료 사례의 공통 RN1 분석점 3,688개에서 한 시간 지상 총강수를 검증했다. 완료된 {len(selection['selection_order'])}개 적격 실험 중 **{label(selected)}**가 사전 지정 순위 1위다. +1시간 CSI@10 mm={c10:.4f}, CSI@5 mm={c5:.4f}, FAR@10 mm={far10:.4f}다. 동일 사례에서 설정을 고른 탐색 결과이며 독립 검증 성능을 뜻하지 않는다.",
      "## 1. 목적과 설계",
      "기존 배율 상단 α=1.5를 넘어 초기 눈 양의 고배율 반응을 비교한다. CONTROL은 규준 초기장과 기존 WRF 실행파일, IMPROVED는 기존 개선안 B1 초기장과 수정 WRF 실행파일을 사용한다. 계열 안에서 native 초기 QSNOW만 float64 곱셈 후 native float32로 변환하고 다른 207개 변수와 전체 변수 메타데이터는 기준과 동일하게 유지했다. 두 계열의 차이는 초기장과 실행파일 변경을 함께 포함한다. 기존 12개 배율 실험과 신규 8개, 기준 2개를 합쳐 22개를 선정 대상으로 삼으며 기존 HYDRO는 참고 점수만 제공한다.",
      "| 계열 | 기준 | 확장 배율 | 실행파일 |\n| --- | --- | --- | --- |\n| 규준 계열 | 규준 실험 | 1.75, 2.0, 2.5, 3.0 | 기존 WRF |\n| 개선 계열 | 기존 개선안 B1 | 1.75, 2.0, 2.5, 3.0 | 수정 WRF |",
      r"초기 조작은 $q_s^{(\alpha)}=\operatorname{REAL32}[\alpha\operatorname{REAL64}(q_s^{(1)})]$이다. QSNOW 이외 변수는 유지하므로 초기 물 변화량은 $\Delta q_{water}=q_s^{(\alpha)}-q_s^{(1)}\simeq(\alpha-1)q_s^{(1)}$ (float32 반올림 차이 제외)다. 다른 수종·열역학 변수를 보상하지 않는 진단 개입이며 보존적 물·에너지 초기화가 아니다.",
      r"검증량은 지상 강설이 아닌 누적 총강수 $C=RAINC+RAINNC$의 연속 시각 간 한 시간 증가량 $P_h=C(t_0+h)-C(t_0+h-1)$이다. +6시간은 17–18 UTC 강수이며 0–6시간 누적강수는 아니다. CSI=$H/(H+M+F)$, FAR=$F/(H+F)$다. H/M/F는 적중/누락/오경보 개수다. [NCEP/EMC 강수 검증 점수 설명](https://www.emc.ncep.noaa.gov/mmb/SREF/pcpverif/scores/docs/QandA.html) (2026-10-30 확인).",
      "## 2. 사전 지정 선정 기준",
      "22개 적격 후보 가운데 완료된 6시간 예보만 +1시간 CSI@10 mm 내림차순, CSI@5 mm 내림차순, FAR@10 mm 오름차순, RMSE 오름차순, |α−1| 오름차순, 실험 ID 오름차순으로 순위화한다. 미완료 사례는 점수와 순위에서 제외하고 상태를 별도 표기한다. 수치 허용오차는 0이다. 미정의 CSI는 정의된 점수 아래, 미정의 FAR는 정의된 FAR 뒤에 둔다. 선정의 우선 기준은 강한 강수 CSI이며 RMSE는 앞선 CSI/FAR가 모두 동률일 때에만 순위 동점 처리 기준이다. 10 mm h⁻¹는 본 연구의 고강수 임계값이지 공식 특보 구간은 아니다.",
      "## 3. 결과",
      "### 3.1 강한 강수 점수 및 선정",
      f"**{label(selected)}**가 선정되었다. B1과 비교하면 CSI@10 변화 {c10-b1c10:+.4f}, CSI@5 변화 {c5-b1c5:+.4f}, FAR@10 변화 {far10-b1far10:+.4f}다. 선정은 사전 지정한 강수 사건 점수와 동점 처리 순서에 따랐다.{error_context}{endpoint_context}",
      strong_score_math,
      transition_text,
      f"고정한 +1시간 CSI@10 기준이 모든 예측시간의 승자를 뜻하지 않는다. +2시간 CSI@10은 선정 실험 {selected_csi_2h:.4f}, 규준 {original_csi_2h:.4f}, B1 {b1_csi_2h:.4f}이고, +6시간은 각각 {selected_csi_6h:.4f}, {original_csi_6h:.4f}, {b1_csi_6h:.4f}다. 각 lead의 점수는 개별로 해석하며 시간 평균으로 합치지 않는다.",
      "### 3.2 신규 고배율 실험과 규준 실험 비교",
      "다음 표는 규준 실험과 새로 편성한 α=1.75, 2.0, 2.5, 3.0의 두 계열 8개 실험을 비교한다. 각 lead의 CSI@10을 별도로 보여주며 시간이나 임계값에 걸친 평균 점수는 사용하지 않는다. 미완료 실험은 점수 없이 상태를 표시한다.",
      new_cases_control_table,
      "![신규 8개 실험 − 규준 실험의 CSI 차이](evidence/snow_extension_20261030/figures/new_cases_vs_control_csi.png)",
      "### 3.3 시각 자료",
      "전체 적격 사례의 고강수 CSI@10 시간별 분포와 기준·선정 실험의 임계값별 CSI를 보인다. 시간별 총강수 지도는 RN1 분석, 규준 실험, 기존 개선안 B1, 선정 실험을 공통 색 구간으로 비교한다.",
      "![예측시간·실험별 CSI at 10 mm](evidence/snow_extension_20261030/figures/strong_precipitation_csi.png)",
      "![선정·기준 사례의 임계값별 CSI](evidence/snow_extension_20261030/figures/selected_threshold_csi.png)",
      "![+1–+3시간 강수 분포](evidence/snow_extension_20261030/figures/snow_extension_maps_leads_1_3.png)",
      "![+4–+6시간 강수 분포](evidence/snow_extension_20261030/figures/snow_extension_maps_leads_4_6.png)",
      "## 4. 기상학적 해석 및 한계",
      "초기 QSNOW 증가는 얼음상 수상체 저장량을 바꾸며, 가능한 후속 융해·승화·낙하·수송 및 수증기·온도 반응은 지상 총강수에 영향을 줄 수 있다. WRF의 일반 미세물리 문서는 열·수분 경향과 지상 강수 및 관련 상변화 과정을 설명한다 ([WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html), [NCAR WRF Physics tutorial](https://www2.mmm.ucar.edu/wrf/wrf_tutorial_linked_files/Overview_of_Physics.pdf); 2026-10-30 확인). 이 일반 문헌은 해당 문서 사례의 KDM6 처리 코드나 점수 변화의 과정별 원인을 입증하지 않는다. 과정별 기여는 분리 측정하지 않았다. CSI와 FAR는 사건 위치 및 빈도를 반영하므로 한 지표의 개선이 다른 임계값·예측시간의 개선을 보장하지 않는다. RN1은 처리된 분석자료이지 관측 진실값이 아니다. 동일 사례에서 설정을 골라 선택 편향이 있고, 보존량·운영 적합성을 입증하지 않는다.",
      "```mermaid\nflowchart LR\n Q[초기 QSNOW 배율] --> S[얼음상 저장량 변화]\n S --> M[가능한 미세물리 과정<br/>기여 미분리]\n M --> P[시간별 지상 총강수]\n P --> C[임계값별 적중·누락·오경보]\n C --> R[사례 내 배율 순위]\n```",
      "## 5. 참고 문헌 및 자료",
      "- [NCEP/EMC 강수 검증 점수 설명](https://www.emc.ncep.noaa.gov/mmb/SREF/pcpverif/scores/docs/QandA.html) (2026-10-30 확인).",
      "- [WRF Physics 사용자 안내서](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html) (2026-10-30 확인).",
      "- [NCAR WRF Overview of Physics tutorial, February 2025](https://www2.mmm.ucar.edu/wrf/wrf_tutorial_linked_files/Overview_of_Physics.pdf) (2026-10-30 확인).",
      f"[고정 선정 계획](evidence/snow_extension_20261030/selection_plan.json) SHA-256 `{PLAN_SHA256}` · [전체 임계값×lead 점수 36표 및 시간별 오차 부록](SNOW_EXTENSION_FULL_SCORES_20261030.md) · [분석 영수증](evidence/snow_extension_20261030/analysis/receipt.json) · [전체 순위표](evidence/snow_extension_20261030/analysis/selection_scores.csv) · [격자별 전이표](evidence/snow_extension_20261030/review/independent_transitions.csv) · [그림 영수증](evidence/snow_extension_20261030/figures/figure_manifest.json). 점수는 {len(scored_cases)}개 완료 사례, 여섯 1시간 창, 여섯 임계값, 시간당 3,688개 paired point를 포함한다. 지도는 공통 점만 표시하며 추가 보간하지 않는다.",
      "## 부록 A. 전체 시간·임계값별 CSI와 혼동계수",
      "아래에는 점수화된 모든 사례(기존 HYDRO 참고 사례 포함)를 시간·임계값별로 제시한다. 각 셀은 CSI와 적중/누락/오경보 수(H/M/FA)이며, 각 시간은 3,688개 paired point를 사용한다. 임계값별 결과는 개별로 해석하며 평균하지 않는다. —는 미정의 점수다.", *lead_sections,
      "## 부록 B. 시간별 강수량 오차",
      table(["시간", "실험", "MAE (mm)", "RMSE (mm)"], error_rows),
      "## 부록 C. 전체 적격 사례 선정 순위",
      "아래 22개 후보는 결과 확인 전에 고정한 +1시간 CSI@10, CSI@5, FAR@10 순서와 동점 기준으로 순위를 매겼다. 본문은 규준 실험과 신규 8개 확장 사례의 직접 비교를 앞세우며, 전체 기존 사례 순위는 이 부록에 보존한다.",
      primary_table
    ]
    return "\n\n".join(parts) + "\n"


def main() -> None:
    OUTPUT.write_text(build(), encoding="utf-8")
    selection = json.loads((ANALYSIS / "selection.json").read_text(encoding="utf-8"))
    (HERE / "report_receipt.json").write_text(json.dumps({
        "report": str(OUTPUT.relative_to(ROOT)), "report_sha256": digest(OUTPUT),
        "builder_sha256": digest(Path(__file__)), "analysis_receipt_sha256": digest(ANALYSIS / "receipt.json"),
        "independent_transitions_sha256": digest(HERE / "review" / "independent_transitions.csv"),
        "selection_plan_sha256": PLAN_SHA256, "selected_case": selection["selected_case"],
        "scope": "23 scored cases; 22 eligible cases; six hourly windows and thresholds."
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
