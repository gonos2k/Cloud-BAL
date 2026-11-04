#!/usr/bin/env python3
"""Render receipt-bound CP02 rain-number evaluation maps and CSI figures."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.ticker import FormatStrFormatter
import numpy as np

def korean_font() -> tuple[str | None, Path | None]:
    preferred = ("NanumGothic", "NanumBarunGothic", "Noto Sans CJK KR")
    for family in preferred:
        matches = [entry for entry in font_manager.fontManager.ttflist if entry.name == family]
        if matches:
            path = Path(matches[0].fname)
            return family, path
    return None, None


KOREAN_FONT, KOREAN_FONT_PATH = korean_font()
if KOREAN_FONT:
    plt.rcParams["font.family"] = KOREAN_FONT
plt.rcParams["axes.unicode_minus"] = False

THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
HOURS = tuple(range(13, 19))
CASES = ("ORIGINAL", "IMPROVED_BG_FIXED", "B1_RAIN_NUMBER_PRIOR")
LABELS = {"ORIGINAL": "규준실험", "IMPROVED_BG_FIXED": "현재 B1", "B1_RAIN_NUMBER_PRIOR": "연구 후보"}
COLORS = {"ORIGINAL": "#666666", "IMPROVED_BG_FIXED": "#2166ac", "B1_RAIN_NUMBER_PRIOR": "#b2182b"}
COMPARATORS = ("ORIGINAL", "IMPROVED_BG_FIXED")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_analysis(folder: Path) -> dict:
    receipt_path = folder / "receipt.json"
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise ValueError("analysis receipt is missing or is a symlink")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("status") != "COMPLETE" or receipt.get("rows") != {"categorical": 108, "continuous": 18, "constraints": 26}:
        raise ValueError("complete 108/18/26-row rain-number analysis is required")
    expected = {"categorical_scores.csv", "continuous_scores.csv", "admission_constraints.csv", "winner.json",
                *(f"hour_{hour}_arrays.npz" for hour in HOURS)}
    outputs = receipt.get("outputs", {})
    if not expected.issubset(outputs):
        raise ValueError("analysis receipt omits required scoring tables or hourly arrays")
    for name in expected:
        path, record = folder / name, outputs[name]
        if path.is_symlink() or not path.is_file() or path.stat().st_size != record.get("size_bytes") or sha256(path) != record.get("sha256"):
            raise ValueError(f"analysis output hash mismatch: {name}")
    return receipt


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def load_scores(folder: Path) -> dict[tuple[str, int, float], float]:
    rows = read_csv(folder / "categorical_scores.csv")
    scores = {(r["case"], int(r["lead_hour"]), float(r["threshold_mm"])): float(r["CSI"]) for r in rows}
    expected = {(case, lead, threshold) for case in CASES for lead in range(1, 7) for threshold in THRESHOLDS}
    if len(rows) != 108 or set(scores) != expected:
        raise ValueError("categorical table must preserve all cases, six leads, and six thresholds")
    return scores


def draw_threshold_figures(scores: dict[tuple[str, int, float], float], out: Path) -> list[Path]:
    outputs = []
    leads = range(1, 7)
    for threshold in THRESHOLDS:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
        for case in CASES:
            axes[0].plot(list(leads), [scores[case, lead, threshold] for lead in leads], marker="o",
                         color=COLORS[case], label=LABELS[case])
        for comparator, color in (("ORIGINAL", "#666666"), ("IMPROVED_BG_FIXED", "#2166ac")):
            axes[1].plot(list(leads), [scores["B1_RAIN_NUMBER_PRIOR", lead, threshold] - scores[comparator, lead, threshold]
                         for lead in leads], marker="o", color=color,
                         label=f"연구 후보 - {LABELS[comparator]}")
        axes[0].set(title="CSI", ylabel="CSI")
        axes[1].set(title="CSI 차이", ylabel="ΔCSI")
        for ax in axes:
            ax.set_xlabel("예보 선행시간 (h)")
            ax.set_xticks(list(leads), [f"+{lead}" for lead in leads])
            ax.grid(alpha=.25)
            ax.legend(frameon=False, fontsize=8)
        fig.suptitle(f"시간강수 CSI - 임계값 ≥ {threshold:g} mm · 각 선행시간 개별 표시")
        path = out / f"rain_number_csi_threshold_{threshold:g}mm.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        outputs.append(path)
    return outputs


def _npz_values(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as arrays:
        values = {key: np.asarray(arrays[key]) for key in arrays.files}
    required = {"reference", *CASES, "latitude", "longitude", "flat_index_yx"}
    if not required.issubset(values) or any(values[key].shape != (3688,) for key in required):
        raise ValueError(f"{path.name}: expected six paired 3,688-point fields and coordinates")
    if len(np.unique(values["flat_index_yx"])) != 3688:
        raise ValueError(f"{path.name}: duplicate paired sample indices")
    if any(not np.isfinite(values[key]).all() for key in required if key != "flat_index_yx"):
        raise ValueError(f"{path.name}: non-finite plotted values")
    return values


def shared_map_scales(hourly: dict[int, dict[str, np.ndarray]]) -> tuple[tuple[float, float], float]:
    if tuple(sorted(hourly)) != HOURS:
        raise ValueError("shared map scales require every valid hour 13 through 18")
    rain = np.concatenate([hourly[h][key] for h in HOURS for key in ("reference", *CASES)])
    if rain.min() < 0:
        raise ValueError("hourly precipitation contains negative values")
    absolute = (float(rain.min()), float(rain.max()))
    delta_limit = max(float(np.max(np.abs(hourly[h]["B1_RAIN_NUMBER_PRIOR"] - hourly[h][case])))
                      for h in HOURS for case in COMPARATORS) or 1e-12
    return absolute, delta_limit


def precipitation_norm(limits: tuple[float, float]):
    low, high = limits
    if high < low:
        raise ValueError("precipitation color limits are reversed")
    cuts = [value for value in (0.1, .5, 1.0, 2.5, 5.0, 10.0) if low < value < high]
    bounds = np.asarray([low, *cuts, high], dtype=float)
    if bounds.size < 2:
        bounds = np.asarray([low, high if high > low else np.nextafter(low, np.inf)])
    colors = ("#ffffff", "#d9f0ff", "#91bfdb", "#4575b4", "#fee090", "#fc8d59", "#d73027")
    cmap = ListedColormap(colors[:bounds.size - 1])
    return cmap, BoundaryNorm(bounds, cmap.N), bounds


def draw_scale_bar_guide(out: Path, absolute_limits: tuple[float, float]) -> Path:
    low, high = absolute_limits
    guide_max = max(high, 10.0)
    amounts = np.asarray([.1, .5, 1, 2.5, 5, 10, guide_max])
    amounts = np.unique(amounts[(amounts > 0) & (amounts <= guide_max)])
    width_scale = 1.0  # scale-bar width in plotted units per mm of rain
    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
    widths = amounts * width_scale
    for amount, width in zip(amounts, widths):
        ax.plot((0, amount), (width, width), color="#2166ac", linewidth=1.5, solid_capstyle="butt")
    ax.plot(amounts, widths, "o", color="#b2182b", markersize=4)
    ax.set(xlim=(0, guide_max * 1.05), ylim=(0, guide_max * width_scale * 1.1),
           xlabel="시간강수량 (mm)", ylabel="표시 scale-bar 폭 (선형 표시 단위)",
           title="시간강수 지도 공통 색상 범위와 선형 scale-bar 대응")
    ax.text(.04, .96, f"모든 lead 공통 절대 범위: {low:g}–{high:g} mm\n선형 대응: bar 폭 = 강수량 × {width_scale:g}",
            transform=ax.transAxes, va="top", ha="left", fontsize=9)
    ax.grid(alpha=.25)
    path = out / "rain_number_map_scale_bar.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def draw_prior_math_figure(out: Path) -> Path:
    fig, ax = plt.subplots(figsize=(15, 4.0), constrained_layout=True)
    ax.set_axis_off()
    boxes = [
        ("초기 상태", "초기 수종 질량 변화 = 0\nNR = 0 → prior"),
        ("선언한 PSD prior", r"$\mu=1,\;\lambda=\sqrt{961\times35000}$" + "\n" +
         r"$\mathrm{pidnr}=(\pi\rho_w/6)\,\Gamma(5)/\Gamma(2)$" + "\n" +
         r"$N_r=q_r\lambda^3/\mathrm{pidnr}$; $\rho_w=1000\;\mathrm{kg\,m^{-3}}$" + "\n" +
         r"$\lambda\approx5799.57\;\mathrm{m}^{-1}$"),
        ("실제 첫 호출", "첫 KDM6 입력\n동일 QR · q_v · T\nNR만 다른 상태\n동일 경계 검증"),
        ("예보 반응", "입도분포 가정 차이\n동반 q_v · T · QR 변화\n전체 미세물리 반응\n과정별 기여는 미분해"),
        ("6시간 평가", "모든 lead·threshold 개별\n보호 9/11 · 회복 3/15\nNO QUALIFIED (12/26)"),
    ]
    x_positions = np.linspace(.1, .9, len(boxes))
    for index, ((heading, body), x) in enumerate(zip(boxes, x_positions)):
        ax.text(x, .52, f"{heading}\n\n{body}", ha="center", va="center", fontsize=9,
                bbox={"boxstyle": "round,pad=.5", "facecolor": "#f4f7fb" if index < 4 else "#fbe9e7",
                      "edgecolor": "#718096" if index < 4 else "#b2182b", "linewidth": 1.4},
                transform=ax.transAxes)
        if index < len(boxes) - 1:
            ax.annotate("", xy=(x_positions[index + 1] - .095, .52), xytext=(x + .095, .52),
                        xycoords=ax.transAxes, textcoords=ax.transAxes,
                        arrowprops={"arrowstyle": "-|>", "color": "#555555", "lw": 1.4})
    ax.text(.5, .08, "초기 prior는 관측된 최적 분포가 아니다. 전체 KDM6 반응을 단일 과정(예: 증발)으로 귀속하지 않는다.",
            ha="center", va="center", transform=ax.transAxes, fontsize=8)
    ax.set_title("B1 rain-number prior: 수식, 상태 차이, 검증 결과", fontsize=13, pad=10)
    path = out / "rain_number_prior_math.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def delta_boundaries(limit: float) -> np.ndarray:
    if limit <= 0:
        limit = 1e-12
    inner = [value for value in (.01, .05, .1, .25, .5, 1, 2.5, 5, 10, 20, 30) if value < limit]
    positive = np.asarray([*inner, limit], dtype=float)
    return np.concatenate((-positive[::-1], [0.0], positive))


def draw_hourly_maps(folder: Path, out: Path) -> tuple[list[Path], tuple[float, float], float, np.ndarray]:
    hourly = {hour: _npz_values(folder / f"hour_{hour}_arrays.npz") for hour in HOURS}
    absolute_limits, delta_limit = shared_map_scales(hourly)
    cmap, norm, _ = precipitation_norm(absolute_limits)
    delta_edges = delta_boundaries(delta_limit)
    delta_cmap = plt.get_cmap("RdBu_r", len(delta_edges) - 1)
    delta_norm = BoundaryNorm(delta_edges, delta_cmap.N)
    outputs = [draw_scale_bar_guide(out, absolute_limits)]
    for hour in HOURS:
        values = hourly[hour]
        lat, lon = values["latitude"], values["longitude"]
        delta_arrays = {case: values["B1_RAIN_NUMBER_PRIOR"] - values[case] for case in COMPARATORS}
        fig, axes = plt.subplots(2, 3, figsize=(15, 8))
        fig.subplots_adjust(left=.06, right=.86, bottom=.08, top=.91, wspace=.26, hspace=.24)
        for ax, key, title in zip(axes.flat[:4], ("reference", *CASES), ("RN1 기준자료", *(LABELS[c] for c in CASES))):
            artist = ax.scatter(lon, lat, c=values[key], s=4, cmap=cmap, norm=norm, rasterized=True)
            ax.set(title=title, xlabel="경도 (°E)", ylabel="위도 (°N)")
            ax.set_aspect("equal", adjustable="datalim")
        for ax, comparator in zip(axes.flat[4:], COMPARATORS):
            artist = ax.scatter(lon, lat, c=delta_arrays[comparator], s=4, cmap=delta_cmap,
                                norm=delta_norm, rasterized=True)
            ax.set(title=f"연구 후보 - {LABELS[comparator]}", xlabel="경도 (°E)", ylabel="위도 (°N)")
            ax.set_aspect("equal", adjustable="datalim")
        abs_cax = fig.add_axes([.89, .55, .018, .31])
        delta_cax = fig.add_axes([.89, .12, .018, .31])
        abs_colorbar = fig.colorbar(axes.flat[3].collections[0], cax=abs_cax,
                                    boundaries=norm.boundaries, label="시간강수량 (mm)")
        abs_colorbar.ax.tick_params(labelsize=8)
        delta_ticks = sorted(set([-delta_limit, -10, -1, -.1, 0, .1, 1, 10, delta_limit]))
        delta_ticks = [tick for tick in delta_ticks if -delta_limit <= tick <= delta_limit]
        delta_colorbar = fig.colorbar(artist, cax=delta_cax, boundaries=delta_edges, ticks=delta_ticks,
                                      label="시간강수량 차이 (mm)")
        delta_colorbar.ax.tick_params(labelsize=8)
        delta_colorbar.ax.yaxis.set_major_formatter(FormatStrFormatter("%g"))
        fig.suptitle(f"2026-08-16 {hour:02d}:00 UTC · +{hour-12} h · 3,688개 실제 paired sample 위치")
        path = out / f"rain_number_hour_{hour}_maps.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        outputs.append(path)
    return outputs, absolute_limits, delta_limit, delta_edges


def render(analysis: Path, output: Path) -> dict:
    if KOREAN_FONT is None:
        raise RuntimeError("A Korean-capable font is required to render these report figures; install NanumGothic, NanumBarunGothic, or Noto Sans CJK KR.")
    if os.path.lexists(output):
        raise FileExistsError(output)
    receipt = verify_analysis(analysis)
    scores = load_scores(analysis)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".rain-number-figures-", dir=output.parent))
    try:
        threshold_figures = draw_threshold_figures(scores, temp)
        math_figure = draw_prior_math_figure(temp)
        map_figures, absolute_limits, delta_limit, delta_edges = draw_hourly_maps(analysis, temp)
        figures = threshold_figures + [math_figure] + map_figures
        metadata = {"scope": "receipt-bound CP02 candidate evaluation; no averaging across leads or thresholds",
                    "analysis_receipt_sha256": sha256(analysis / "receipt.json"),
                    "renderer_sha256": sha256(Path(__file__)),
                    "font": ({"family": KOREAN_FONT, "path": str(KOREAN_FONT_PATH), "sha256": sha256(KOREAN_FONT_PATH)}
                             if KOREAN_FONT_PATH else {"family": "Matplotlib default", "path": None, "sha256": None}),
                    "korean_font_available": KOREAN_FONT is not None,
                    "evaluation_input_bindings": receipt.get("inputs", []),
                    "shared_map_scales": {"absolute_precipitation_mm": list(absolute_limits),
                                           "delta_precipitation_mm": [-delta_limit, delta_limit],
                                           "delta_definition": "B1_RAIN_NUMBER_PRIOR minus comparator; common to both comparators and all six hours",
                                           "delta_color_bins_mm": delta_edges.tolist()},
                    "inputs": {name: receipt["outputs"][name] for name in sorted(receipt["outputs"]) if name in {
                        "categorical_scores.csv", "continuous_scores.csv", "admission_constraints.csv", "winner.json",
                        *(f"hour_{hour}_arrays.npz" for hour in HOURS)}},
                    "outputs": {p.name: {"sha256": sha256(p), "size_bytes": p.stat().st_size} for p in figures}}
        (temp / "render_receipt.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        verify_analysis(analysis)
        temp.rename(output)
        return metadata
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.analysis, args.output)


if __name__ == "__main__":
    main()
