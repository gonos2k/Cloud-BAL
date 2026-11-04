#!/usr/bin/env python3
"""Render receipt-bound native CP02 state-path diagnostics."""
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
import numpy as np

def preferred_font() -> tuple[str | None, Path | None]:
    for family in ("NanumGothic", "NanumBarunGothic", "Noto Sans CJK KR"):
        matches = [entry for entry in font_manager.fontManager.ttflist if entry.name == family]
        if matches:
            return family, Path(matches[0].fname)
    return None, None


FONT_FAMILY, FONT_PATH = preferred_font()
if FONT_FAMILY:
    plt.rcParams["font.family"] = FONT_FAMILY
plt.rcParams["axes.unicode_minus"] = False

POINTS = ("P01", "P02", "P03", "P04", "FA01", "FA02", "FA03", "FA04")
PATH_COMPONENTS = (("D_entry", "incoming"), ("within_delta", "inside KDM6"),
                   ("between_delta", "between calls: outside KDM6"))


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_analysis(folder: Path) -> dict:
    receipt_path = folder / "receipt.json"
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise ValueError("native analysis receipt is missing or is a symlink")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("status") != "complete" or receipt.get("selected_point_ids") != list(POINTS):
        raise ValueError("complete native analysis for all eight frozen points is required")
    required = {"global_checkpoint_comparison.csv", "selected_ledger_summary.csv",
                "selected_point_first_differences.csv", "selected_history.npz", "earliest_divergence.json",
                "ledger_summary.json"}
    outputs = {record["path"]: record for record in receipt.get("outputs", [])}
    if not required.issubset(outputs):
        raise ValueError("native analysis receipt omits required state-path outputs")
    for name in required:
        path, record = folder / name, outputs[name]
        if path.is_symlink() or not path.is_file() or path.stat().st_size != record.get("size_bytes") or sha256(path) != record.get("sha256"):
            raise ValueError(f"native analysis output hash mismatch: {name}")
    return receipt


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _load_history(folder: Path) -> dict[str, np.ndarray]:
    with np.load(folder / "selected_history.npz", allow_pickle=False) as archive:
        values = {key: np.asarray(archive[key]) for key in archive.files}
    for name, expected_shape in (("D_entry", (360, 39, 8, 14)), ("D_return", (360, 39, 8, 14)),
                                 ("within_delta", (360, 39, 8, 14)), ("between_delta", (359, 39, 8, 14))):
        if name not in values or values[name].shape != expected_shape:
            raise ValueError(f"selected_history.npz: {name} must have shape {expected_shape}")
    if tuple(values.get("point_ids", ())) != POINTS:
        raise ValueError("selected_history.npz point ordering differs from frozen cohort ordering")
    fields = tuple(str(v) for v in values.get("fields", ()))
    if len(fields) != 14 or len(set(fields)) != 14:
        raise ValueError("selected_history.npz must retain fourteen uniquely named public fields")
    if any(not np.isfinite(values[name]).all() for name in ("D_entry", "D_return", "within_delta", "between_delta")):
        raise ValueError("selected_history.npz contains non-finite plotted differences")
    return values


def checkpoint_layout(schema: dict) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    public = tuple(schema["global_stages"]["entry"]["fields_float32"])
    private = tuple(schema["global_stages"]["pre_update"]["fields_float32"])
    if len(public) != 14 or len(private) != 15:
        raise ValueError("schema must preserve 14 public and 15 private fields")
    return public, private, ("entry", "wrapper_return"), ("pre_update", "post_process", "kdm62d_return")


def draw_first_numeric(rows: list[dict[str, str]], schema: dict, earliest: dict, out: Path) -> Path:
    public, private, public_stages, private_stages = checkpoint_layout(schema)
    expected = {(stage, field) for stage, fields in (("entry", public), ("wrapper_return", public),
                ("pre_update", private), ("post_process", private), ("kdm62d_return", private)) for field in fields}
    by_key = {(row["stage"], row["field"]): row for row in rows}
    if len(rows) != 73 or set(by_key) != expected:
        raise ValueError("global checkpoint table must preserve 14 public fields × 2 and 15 private fields × 3")
    fig, axes = plt.subplots(1, 2, figsize=(14, 8), gridspec_kw={"width_ratios": [2, 3]})
    fig.subplots_adjust(left=.09, right=.98, bottom=.16, top=.84, wspace=.3)
    palette = matplotlib.colors.ListedColormap(("#f5f5f5", "#fdb863", "#5ab4ac"))
    for ax, fields, stages, title in ((axes[0], public, public_stages, "Public host-field representation"),
                                      (axes[1], private, private_stages, "Private KDM62D representation")):
        matrix = np.zeros((len(fields), len(stages)), dtype=np.int8)
        labels = np.empty((len(fields), len(stages)), dtype=object)
        for y, field in enumerate(fields):
            for x, stage in enumerate(stages):
                row = by_key[stage, field]
                numeric, bitwise = int(row["numeric_different"]), int(row["bitwise_different"])
                matrix[y, x] = 2 if numeric else (1 if bitwise else 0)
                labels[y, x] = f"{numeric}\n({bitwise})"
        ax.imshow(matrix, cmap=palette, vmin=0, vmax=2, aspect="auto")
        ax.set_xticks(range(len(stages)), [stage.replace("_", "\n") for stage in stages])
        ax.set_yticks(range(len(fields)), fields, fontsize=7)
        ax.set_title(title)
        for y in range(len(fields)):
            for x in range(len(stages)):
                ax.text(x, y, labels[y, x], ha="center", va="center", fontsize=6)
    from matplotlib.patches import Patch
    axes[0].set_xlabel("Fixed schema stage order")
    axes[1].set_xlabel("Fixed schema stage order")
    axes[0].set_ylabel("Cell value: numeric differences (bitwise differences)")
    first = earliest.get("earliest_deterministic_numeric_difference")
    first_text = "No numeric difference" if first is None else (
        f"Earliest numeric difference: {first['stage']} · {first['field']} · t={first['timestep']}, "
        f"k/j/i={first['k']}/{first['j']}/{first['i']}\n"
        f"OLD={first['old']:.10g}; current B1={first['fix']:.10g}; signed-zero-only={first['signed_zero_only']}")
    fig.suptitle("OLD / current B1 native checkpoint differences\nCheckpoint order is deterministic bookkeeping, not causal chronology", y=.99)
    fig.legend(handles=[Patch(color="#f5f5f5", label="equal"), Patch(color="#fdb863", label="bitwise-only (incl. signed zero)"),
                        Patch(color="#5ab4ac", label="numeric difference")], loc="upper center", bbox_to_anchor=(.5, .91),
               ncol=3, frameon=False)
    fig.text(.5, .025, first_text, ha="center", va="bottom", fontsize=8)
    path = out / "native_global_numeric_divergence.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def draw_path_component(values: dict[str, np.ndarray], field: str, points: tuple[str, ...], out: Path,
                        first_timesteps: int | None = None) -> Path:
    fields = [str(x) for x in values["fields"]]
    if field not in fields:
        raise ValueError(f"required public field is absent: {field}")
    fi = fields.index(field)
    field_limit = max(float(np.max(np.abs(values[key][:first_timesteps, :, :, fi])))
                      for key, _ in PATH_COMPONENTS) if first_timesteps else max(
                          float(np.max(np.abs(values[key][:, :, :, fi]))) for key, _ in PATH_COMPONENTS)
    field_limit = field_limit or 1e-30
    fig, axes = plt.subplots(len(points), len(PATH_COMPONENTS), figsize=(15, 3.8 * len(points)), constrained_layout=True)
    for row_index, point in enumerate(points):
        pi = POINTS.index(point)
        for col_index, (array_key, label) in enumerate(PATH_COMPONENTS):
            ax = axes[row_index, col_index]
            data = values[array_key][:first_timesteps, :, pi, fi].T if first_timesteps else values[array_key][:, :, pi, fi].T
            if array_key == "between_delta":
                x_end = data.shape[1] + 1
                x_extent = (1.5, x_end + .5)
                times = values.get("between_time", np.arange(2, 361))
                if not np.array_equal(times, np.arange(2, 361)):
                    raise ValueError("between_delta axis must explicitly represent timesteps 2 through 360")
            else:
                x_extent = (.5, data.shape[1] + .5)
            image = ax.imshow(data, origin="lower", aspect="auto", interpolation="nearest", cmap="RdBu_r", vmin=-field_limit, vmax=field_limit,
                              extent=(x_extent[0], x_extent[1], 0.5, 39.5))
            ax.set(title=f"{point} · {label}", xlabel="KDM6 timestep", ylabel="Native model level k")
            fig.colorbar(image, ax=ax, label=f"Δ{field} (field-native units)", shrink=.8,
                         format=matplotlib.ticker.FormatStrFormatter("%g"))
    window_label = f"First {first_timesteps} timesteps; " if first_timesteps else ""
    fig.suptitle(f"Selected native state path · {field}\n{window_label}four corner values bilinear-weighted per point; no level/time averaging")
    suffix = f"_first{first_timesteps}" if first_timesteps else ""
    path = out / f"native_path_{field.lower()}{suffix}.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def draw_temperature_distinction(values: dict[str, np.ndarray], out: Path) -> Path:
    fields = [str(x) for x in values["fields"]]
    wanted = ("TH_PUBLIC_RAW", "T_K_DERIVED_TH_TIMES_PII")
    if any(name not in fields for name in wanted):
        raise ValueError("public TH and derived actual-temperature fields must both be retained")
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    for row, field in enumerate(wanted):
        fi = fields.index(field)
        for col, (array_key, label) in enumerate(PATH_COMPONENTS):
            ax = axes[row, col]
            for pi, point in enumerate(POINTS):
                data = values[array_key][:, :, pi, fi]
                scale = float(np.max(np.abs(data))) or 1e-30
                ax.plot(np.arange(1, data.shape[0] + 1), np.max(np.abs(data), axis=1),
                        label=f"{point}: max_k |Δ|", alpha=.8)
                ax.set_yscale("log")
                ax.set_ylim(bottom=max(scale * 1e-12, 1e-35))
            ax.set(title=f"{field} · {label}", xlabel="KDM6 timestep", ylabel=f"max_k |Δ{field}| (native units)")
            ax.grid(alpha=.2)
    axes[0, 0].legend(frameon=False, fontsize=7, ncol=2)
    fig.suptitle("Potential temperature TH and derived actual temperature are distinct fields\nAll eight points remain separate; per-point max over levels is labeled")
    path = out / "native_th_vs_actual_temperature_path.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def render(analysis: Path, output: Path) -> dict:
    if os.path.lexists(output):
        raise FileExistsError(output)
    receipt = verify_analysis(analysis)
    rows = read_csv(analysis / "global_checkpoint_comparison.csv")
    schema = json.loads((Path(__file__).resolve().parents[1] / "docs/evidence/cp02_state_path_20261104/native/state_schema.json").read_text(encoding="utf-8"))
    earliest = json.loads((analysis / "earliest_divergence.json").read_text(encoding="utf-8"))
    history = _load_history(analysis)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".native-state-path-figures-", dir=output.parent))
    try:
        figures = [draw_first_numeric(rows, schema, earliest, temp),
                   draw_path_component(history, "QV_PUBLIC_RAW", POINTS, temp),
                   draw_path_component(history, "QV_PUBLIC_RAW", ("P01", "P02"), temp, first_timesteps=20),
                   draw_path_component(history, "QR_PUBLIC_RAW", POINTS, temp),
                   draw_temperature_distinction(history, temp)]
        ledger = json.loads((analysis / "ledger_summary.json").read_text(encoding="utf-8"))
        metadata = {"scope": "native state-path evidence; no predictive-skill attribution",
                    "analysis_receipt_sha256": sha256(analysis / "receipt.json"),
                    "renderer_sha256": sha256(Path(__file__)),
                    "font": ({"family": FONT_FAMILY, "path": str(FONT_PATH), "sha256": sha256(FONT_PATH)}
                             if FONT_PATH else {"family": "Matplotlib default", "path": None, "sha256": None}),
                    "native_capture_pair_gate": receipt.get("global_stage_validation"),
                    "ledger_interpretation": ledger,
                    "inputs": {name: record["sha256"] for name, record in {
                        "global_checkpoint_comparison.csv": next(r for r in receipt["outputs"] if r["path"] == "global_checkpoint_comparison.csv"),
                        "selected_history.npz": next(r for r in receipt["outputs"] if r["path"] == "selected_history.npz"),
                        "ledger_summary.json": next(r for r in receipt["outputs"] if r["path"] == "ledger_summary.json")}.items()},
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
