#!/usr/bin/env python3
"""Render frozen CP02 rain-cohort diagnostics without pooling samples."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import SymLogNorm
from matplotlib.ticker import FuncFormatter
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
COHORTS = ROOT / "docs/evidence/cp02_rain_number_process_20261104/newcohorts"
OUTPUT = ROOT / "docs/evidence/cp02_rain_number_process_20261104/figures"
COMPONENTS = ROOT / "docs/evidence/cp02_rain_number_process_20261104/science/precipitation_components.csv"
FONT = Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")
FONT_SHA256 = "48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733"
POINT_IDS = ("P01", "P02", "FA03", "H3_L01", "H3_L05", "H3_L1", "H3_FA01", "H3_FA5", "H3_H5")
PACKER = ROOT / "tools/pack_cp02_selected_npz.py"
PACKER_SPEC = importlib.util.spec_from_file_location("cp02_selected_parts", PACKER)
if PACKER_SPEC is None or PACKER_SPEC.loader is None:
    raise RuntimeError("cannot load verified selected-array loader")
parts = importlib.util.module_from_spec(PACKER_SPEC)
PACKER_SPEC.loader.exec_module(parts)
CASES = ("ORIGINAL", "B1", "B1_RAIN_NUMBER_PRIOR")
LABELS = {"reference": "RN1 기준자료", "ORIGINAL": "규준실험", "B1": "현재 B1", "B1_RAIN_NUMBER_PRIOR": "비 입자수 후보"}
COLORS = {"reference": "#202020", "ORIGINAL": "#79858c", "B1": "#1769a3", "B1_RAIN_NUMBER_PRIOR": "#c34528"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configure_font(path: Path = FONT) -> None:
    if not path.is_file() or digest(path) != FONT_SHA256:
        raise ValueError(f"missing or changed pinned Korean font: {path}")
    font_manager.fontManager.addfont(str(path))
    plt.rcParams.update({"font.family": font_manager.FontProperties(fname=str(path)).get_name(), "axes.unicode_minus": False, "figure.dpi": 130, "savefig.dpi": 130})


def load_series(path: Path) -> dict[str, dict[str, np.ndarray]]:
    """Validate the redundant threshold rows and retain the actual six-hour series."""
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 9 * 6 * 6 * 3:
        raise ValueError("expected 972 transition rows")
    values = {}
    seen = set()
    for row in rows:
        point, lead, case = row["point_id"], int(row["lead_hour"]), row["case"]
        threshold = float(row["threshold_mm"])
        key = (point, lead, case, threshold)
        if point not in POINT_IDS or lead not in range(1, 7) or case not in CASES or threshold not in (0.1, 0.5, 1.0, 2.5, 5.0, 10.0) or key in seen:
            raise ValueError(f"unexpected or duplicated transition row {key}")
        seen.add(key)
        obs, forecast = float(row["reference_mm"]), float(row["forecast_mm"])
        if not np.isfinite([obs, forecast]).all():
            raise ValueError(f"non-finite value in {key}")
        for component, value in (("reference", obs), (case, forecast)):
            series_key = (point, lead, component)
            if series_key in values and values[series_key] != value:
                raise ValueError(f"inconsistent repeated value in {series_key}")
            values[series_key] = value
    return {point: {case: np.array([values[point, lead, case] for lead in range(1, 7)])
                    for case in ("reference", *CASES)} for point in POINT_IDS}


def panel_grid(title: str):
    fig, axes = plt.subplots(3, 3, figsize=(15, 10), sharex=True, constrained_layout=True)
    fig.suptitle(title, fontsize=16, fontweight="bold")
    return fig, axes.flat


def load_components(path: Path, series: dict) -> dict:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 9 * 6 * 2:
        raise ValueError("expected 108 point-hour component rows")
    values = {}
    for row in rows:
        point, lead, case = row["point_id"], int(row["lead_hour"]), row["case"]
        key = (point, lead, case)
        if point not in POINT_IDS or lead not in range(1, 7) or case not in ("IMPROVED_BG_FIXED", "B1_RAIN_NUMBER_PRIOR") or key in values:
            raise ValueError(f"unexpected or duplicate component row {key}")
        rainc, rainnc, total = (float(row[k]) for k in ("RAINC_hour_mm", "RAINNC_hour_mm", "total_hour_mm"))
        residual, bound = (float(row[k]) for k in ("total_reconstruction_residual_mm", "roundoff_bound_mm"))
        canonical = series[point]["B1" if case == "IMPROVED_BG_FIXED" else case][lead - 1]
        if not np.isfinite([rainc, rainnc, total, residual, bound]).all() or bound < 0 or abs(residual) > bound or not np.isclose(total, rainc + rainnc, rtol=1e-12, atol=1e-14) or not np.isclose(total, canonical, rtol=1e-12, atol=1e-14):
            raise ValueError(f"inconsistent rain components {key}")
        values[key] = np.array([rainc, rainnc, total])
    return {point: np.array([values[point, lead, "B1_RAIN_NUMBER_PRIOR"] - values[point, lead, "IMPROVED_BG_FIXED"] for lead in range(1, 7)]) for point in POINT_IDS}


def plot_components(components: dict, output: Path) -> None:
    fig, axes = panel_grid("후보 - 현재 B1: 시간 강수량 성분 · 대칭 로그 축")
    names = ("RAINC (적운)", "RAINNC (비적운)", "총 강수량")
    colors = ("#8c529c", "#1769a3", "#c34528")
    limit = max(max(float(np.max(np.abs(value))) for value in components.values()) * 1.08, .01)
    for point, ax in zip(POINT_IDS, axes):
        for column, (name, color) in enumerate(zip(names, colors)):
            ax.plot(range(1, 7), components[point][:, column], label=name, color=color, marker="o", markersize=3, linewidth=1.5)
        ax.axhline(0, color="#555555", linewidth=.7); ax.set_yscale("symlog", linthresh=.01); ax.set_ylim(-limit, limit)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
        ax.set_title(point, loc="left", fontweight="bold"); ax.set_xticks(range(1, 7)); ax.set_xlabel("예측시간 (h)"); ax.set_ylabel("시간 강수량 차이 (mm)"); ax.grid(alpha=.23)
    fig.legend(*fig.axes[0].get_legend_handles_labels(), loc="outside lower center", ncols=3, fontsize=9)
    fig.savefig(output, metadata={"Software": "CP02 scientific renderer"}); plt.close(fig)


def plot_amounts(series: dict, output: Path) -> None:
    fig, axes = panel_grid("선정 지점별 시간 강수량 · 기준자료 및 실험")
    for point, ax in zip(POINT_IDS, axes):
        for key in ("reference", *CASES):
            ax.plot(range(1, 7), series[point][key], color=COLORS[key], label=LABELS[key], marker="o", markersize=3, linewidth=1.5, linestyle="--" if key == "reference" else "-")
        ax.set_title(point, loc="left", fontweight="bold")
        ax.set_xticks(range(1, 7)); ax.set_xlabel("예측시간 (h)"); ax.set_ylabel("시간 강수량 (mm)")
        ax.set_ylim(bottom=0); ax.grid(alpha=.23)
    fig.legend(*fig.axes[0].get_legend_handles_labels(), loc="outside lower center", ncols=4, fontsize=9)
    fig.savefig(output, metadata={"Software": "CP02 scientific renderer"}); plt.close(fig)


def plot_differences(series: dict, output: Path) -> None:
    fig, axes = panel_grid("선정 지점별 강수량 차이 · 현재 B1 기준 · 대칭 로그 축")
    keys = ("reference", "ORIGINAL", "B1_RAIN_NUMBER_PRIOR")
    extent = max(float(np.max(np.abs(series[p][key] - series[p]["B1"]))) for p in POINT_IDS for key in keys)
    limit = max(extent * 1.08, 0.01)
    for point, ax in zip(POINT_IDS, axes):
        for key in keys:
            ax.plot(range(1, 7), series[point][key] - series[point]["B1"], color=COLORS[key], label=f"{LABELS[key]} - 현재 B1", marker="o", markersize=3, linewidth=1.5, linestyle="--" if key == "reference" else "-")
        ax.axhline(0, color="#555555", linewidth=.7); ax.set_yscale("symlog", linthresh=.01); ax.set_ylim(-limit, limit)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
        ax.set_title(point, loc="left", fontweight="bold"); ax.set_xticks(range(1, 7)); ax.set_xlabel("예측시간 (h)"); ax.set_ylabel("시간 강수량 차이 (mm)"); ax.grid(alpha=.23)
    fig.legend(*fig.axes[0].get_legend_handles_labels(), loc="outside lower center", ncols=3, fontsize=9)
    fig.savefig(output, metadata={"Software": "CP02 scientific renderer"}); plt.close(fig)


def plot_threshold_examples(series: dict, examples: tuple, output: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), constrained_layout=True)
    fig.suptitle("개별 지점 · 예측시간별 강수와 판정 임계값", fontsize=16, fontweight="bold")
    keys = ("reference", *CASES)
    for (point, lead, threshold), ax in zip(examples, axes.flat):
        amounts = [float(series[point][key][lead - 1]) for key in keys]
        ax.bar(range(4), amounts, color=[COLORS[key] for key in keys], width=.65)
        ax.axhline(threshold, color="#875600", linestyle="--", linewidth=1.5, label=f"임계값 {threshold:g} mm")
        ax.set_title(f"{point}  |  +{lead} h", loc="left", fontweight="bold")
        ax.set_xticks(range(4), ["RN1 기준자료", "규준실험", "현재 B1", "비 입자수 후보"])
        ax.set_ylabel("시간 강수량 (mm)"); ax.set_ylim(0, max(*amounts, threshold) * 1.3)
        for x, amount in enumerate(amounts):
            ax.annotate(f"{amount:.4g}", (x, amount), xytext=(0, 4), textcoords="offset points", ha="center", fontsize=9)
        ax.legend(loc="upper right"); ax.grid(axis="y", alpha=.23)
    fig.savefig(output, metadata={"Software": "CP02 scientific renderer"}); plt.close(fig)


def plot_prior(output: Path) -> None:
    fig, ax = plt.subplots(figsize=(13, 7), constrained_layout=True)
    ax.axis("off")
    fig.suptitle("빗방울 크기분포 사전가정과 입자수 혼합비", fontsize=19, fontweight="bold")
    ax.text(.5, .86, r"감마 분포: μ = 1  |  물의 밀도 $\rho_w$ = 1000 kg m⁻³", ha="center", fontsize=16, transform=ax.transAxes)
    ax.text(.5, .68, r"$N_r = \frac{q_r\,\lambda^3}{4000\pi}$", ha="center", va="center", fontsize=28, transform=ax.transAxes)
    ax.text(.5, .58, r"$q_r$: kg kg$^{-1}$    ·    $N_r$: kg$^{-1}$    ·    $\lambda$: m$^{-1}$", ha="center", fontsize=12, transform=ax.transAxes)
    ax.text(.5, .47, r"$D_m = \frac{5}{\lambda}$" + "     →     " + r"$\lambda = 5799.56895\ \mathrm{m^{-1}}$" + "     ↔     " + r"$D_m = 0.8621\ \mathrm{mm}$", ha="center", va="center", fontsize=20, transform=ax.transAxes)
    ax.text(.5, .37, r"래퍼 $N_r$ (kg$^{-1}$, 입자수 혼합비) → 내부 $n_r$ (m$^{-3}$, 수농도): $n_r = \mathrm{REAL32}(N_r \times DEN)$", ha="center", fontsize=13, transform=ax.transAxes)
    ax.text(.5, .28, "고정된 $q_r$에서 λ가 커지면 $N_r$이 증가하고 질량가중 평균 직경은 감소", ha="center", fontsize=14, transform=ax.transAxes)
    ax.text(.5, .17, "낙하속도 직경 지수 b = 0.8 · 증발은 수농도에 따라 달라질 수 있음", ha="center", fontsize=13, transform=ax.transAxes)
    ax.text(.5, .055, "q와 N은 동일한 모형 공기 질량 기준 · 연구용 가정이며 관측 입자 크기분포가 아님", ha="center", fontsize=12, color="#9b351f", transform=ax.transAxes)
    fig.savefig(output, metadata={"Software": "CP02 scientific renderer"}); plt.close(fig)


def final_cond_vapor(prior: np.ndarray, baseline: np.ndarray, indices: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Reproduce source float32 multiplication at each corner, then pair and map."""
    if prior.shape != baseline.shape or prior.ndim != 6 or prior.shape[0] != 2 or prior.shape[2] != 1 or prior.shape[-1] != 11:
        raise ValueError("unexpected FINALCOND dimensions or microphysics loop count")
    if indices.ndim != 2 or indices.shape[1] != 4 or weights.shape != indices.shape or np.any(indices < 0) or np.any(indices >= prior.shape[-2]) or not np.isfinite(weights).all() or np.any(weights < 0) or not np.allclose(weights.sum(axis=1), 1, rtol=0, atol=1e-12):
        raise ValueError("invalid native corner indices or weights")
    def increment(data):
        pre = data[0, :, 0]
        return -np.multiply(pre[..., 7], pre[..., 8], dtype=np.float32)
    delta = increment(prior).astype(np.float64) - increment(baseline).astype(np.float64)
    return np.einsum("...pc,pc->...p", np.take(delta, indices, axis=-1), weights, optimize=True)


def process_panels(directory: Path) -> dict:
    history = np.load(directory / "point_history.npz", allow_pickle=False)
    baseline = parts.load_partarrays(directory / "selected_B1_parts/selected_B1.parts.json", names=["final_cond"])
    prior = parts.load_partarrays(directory / "selected_NR_PRIOR_parts/selected_NR_PRIOR.parts.json", names=["final_cond"])
    point_names = list(history["points"].astype(str))
    expected = ("P01", "FA03", "H3_L01", "H3_L05", "H3_FA01")
    if len(set(point_names)) != len(point_names) or any(p not in point_names for p in expected):
        raise ValueError("missing or duplicate selected points in process history")
    def field(array: str, fields: str, name: str):
        field_names = list(history[fields].astype(str))
        return np.asarray(history[array][..., field_names.index(name)], dtype=np.float64)
    variables = (
        ("낙하 과정 빗물 변화 차이", "kg/kg per call", field("sedimentation", "sedimentation_fields", "qrs1")),
        ("PREVP 수증기 성분 차이", "kg/kg per call", field("components", "component_fields", "prevp_qv_component")),
        ("FINALCOND 수증기 성분 차이", "kg/kg per call", final_cond_vapor(prior["final_cond"], baseline["final_cond"], history["corner_indices"], history["corner_weights"])),
        ("RETURN 빗물 상태 차이", "kg/kg", field("return_difference", "state_fields", "QR")),
        ("호출 사이 빗물 차이 변화", "kg/kg", field("between_call", "state_fields", "QR")),
        ("RETURN 온도 상태 차이", "K", field("return_difference", "state_fields", "TK")),
    )
    shape = variables[0][2].shape
    if len(shape) != 3 or shape[1:] != (39, len(point_names)) or any(a.shape != (shape[0] - (i == 4), *shape[1:]) or not np.isfinite(a).all() for i, (_, _, a) in enumerate(variables)):
        raise ValueError("unexpected process history shape or non-finite values")
    if shape[0] != 540:
        raise ValueError("expected a validated 540-step, three-hour capture")
    indexes = [point_names.index(p) for p in expected]
    limits = [max(float(np.max(np.abs(a[..., indexes]))), 1e-30) for _, _, a in variables]
    return {point: [(title, unit, array[..., index], limit) for (title, unit, array), limit in zip(variables, limits)] for point, index in zip(expected, indexes)}


def plot_process_point(point: str, panels: list, output: Path) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(17, 9), constrained_layout=True)
    fig.suptitle(f"{point} · 비 입자수 후보 - 현재 B1 · 모형 과정 진단", fontsize=17, fontweight="bold")
    for ax, (title, unit, array, limit) in zip(axes.flat, panels):
        first = 2 if "호출 사이" in title else 1
        hours = np.arange(first, first + array.shape[0]) / 180
        norm = SymLogNorm(linthresh=limit / 1000, vmin=-limit, vmax=limit)
        image = ax.pcolormesh(hours, np.arange(1, 40), array.T, shading="auto", cmap="coolwarm", norm=norm)
        ax.set_title(title); ax.set_xlabel("예측시간 (h)"); ax.set_ylabel("모형 연직층 번호 (1 = 최하층)")
        fig.colorbar(image, ax=ax, label=unit, ticks=[-limit, -limit / 100, 0, limit / 100, limit], format=FuncFormatter(lambda value, _: f"{value:.2g}"))
    fig.savefig(output, metadata={"Software": "CP02 scientific renderer"}); plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--process-input", type=Path, help="validated three-hour analysis directory")
    args = parser.parse_args()
    configure_font()
    source = COHORTS / "point_transitions.csv"
    series = load_series(source)
    components = load_components(COMPONENTS, series)
    panels = process_panels(args.process_input) if args.process_input else None
    args.output.mkdir(parents=True, exist_ok=True)
    outputs = ("hourly_amounts.png", "hourly_differences_from_b1.png", "gamma_prior.png", "threshold_examples_1.png", "threshold_examples_2.png", "rain_components.png")
    plot_amounts(series, args.output / outputs[0]); plot_differences(series, args.output / outputs[1]); plot_prior(args.output / outputs[2])
    plot_threshold_examples(series, (("P01", 2, .1), ("P01", 3, .1), ("FA03", 2, 5), ("H3_L01", 3, .1)), args.output / outputs[3])
    plot_threshold_examples(series, (("H3_L05", 3, .5), ("H3_L1", 3, .5), ("H3_FA01", 3, .1), ("H3_FA5", 3, 5)), args.output / outputs[4])
    plot_components(components, args.output / outputs[5])
    process_files = ()
    if args.process_input:
        process_files = tuple(f"process_{point}.png" for point in panels)
        for point, name in zip(panels, process_files):
            plot_process_point(point, panels[point], args.output / name)
        outputs += process_files
    gallery = "# CP02 빗방울 수 과정 진단\n\n선정 지점의 총 시간 강수량 진단이며 전체 표본의 성능 점수가 아닙니다. 서로 다른 지점과 시간을 평균하지 않았습니다. 총 강수량은 RAINC를 포함하며, KDM6 표면 강수 과정은 RAINNC에 해당합니다.\n\n"
    if process_files:
        gallery += "과정도는 비 입자수 후보에서 현재 B1을 뺀 값입니다. 낙하 변화는 포착된 비·눈·싸락눈 낙하 계산 범위이며, PREVP와 FINALCOND는 개별 호출의 수증기 성분입니다. RETURN 온도는 실제 래퍼 반환 상태의 차이입니다. 호출 사이 변화는 수송만을 뜻하지 않습니다. 연직축은 고도가 아닌 모형층 번호입니다. 변수별 색상 범위는 모든 선정 지점에서 같습니다.\n\n"
    gallery += "\n\n".join(f"![{name}]({name})" for name in outputs) + "\n"
    (args.output / "gallery.md").write_text(gallery, encoding="utf-8")
    metadata = {"input": {"path": str(source.relative_to(ROOT)), "sha256": digest(source)}, "component_input": {"path": str(COMPONENTS.relative_to(ROOT)), "sha256": digest(COMPONENTS)}, "font": {"path": str(FONT), "sha256": digest(FONT)}, "renderer_sha256": digest(Path(__file__)), "matplotlib_version": matplotlib.__version__, "outputs": {name: digest(args.output / name) for name in (*outputs, "gallery.md")}}
    if args.process_input:
        manifests = [args.process_input / f"selected_{case}_parts/selected_{case}.parts.json" for case in ("B1", "NR_PRIOR")]
        metadata["process_inputs"] = {"point_history_sha256": digest(args.process_input / "point_history.npz"), "parts_loader_sha256": digest(PACKER), "selected": [{"manifest": path.name, "manifest_sha256": digest(path), "logical_npz_sha256": json.loads(path.read_text(encoding="utf-8"))["source_sha256"]} for path in manifests]}
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with zipfile.ZipFile(args.output / "offline_gallery.zip", "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in (*outputs, "gallery.md", "metadata.json"):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(info, (args.output / name).read_bytes())
    print(json.dumps(metadata["outputs"], indent=2))


if __name__ == "__main__":
    main()
