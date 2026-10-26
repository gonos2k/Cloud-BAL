#!/usr/bin/env python3
"""Plot saved-time PR103 RMS series from a closed six-arm response JSON."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TIMES = list(range(0, 601, 60))
ARMS = ("OFF", "H", "C", "P", "N", "A")
FIELDS = ("pressure", "Phi", "W", "QC")
REGIONS = ("support", "buffer")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_response(path: Path) -> dict:
    response = json.loads(path.read_text())
    if (response.get("schema") != "pr103_saved_time_response_v1"
            or response.get("status") != "DESCRIPTIVE_ONLY"
            or response.get("times_seconds") != TIMES
            or set(response.get("fields", {})) != set(FIELDS)
            or set(response.get("arms", {})) != set(ARMS)
            or set(response.get("regions", {})) != set(REGIONS)
            or response.get("physical_approval") != "FAIL_OPEN"
            or response.get("observation_skill") != "NOT_EVALUATED"):
        raise ValueError("input is not the fixed-schedule descriptive PR103 response")
    source = response.get("source_receipt", {})
    if source.get("arm") != "A" or source.get("status") != "CLOSED":
        raise ValueError("plot requires the closed A six-arm response")
    for field in FIELDS:
        for arm in ARMS:
            for region in REGIONS:
                values = response.get("metrics", {}).get(field, {}).get(arm, {}).get(region, {}).get("saved_values")
                if (not isinstance(values, list) or len(values) != len(TIMES)
                        or any(isinstance(value, bool) or not isinstance(value, (int, float))
                               or not math.isfinite(value) or value < 0 for value in values)):
                    raise ValueError(f"{field}/{arm}/{region} lacks finite nonnegative values at all fixed times")
                if arm == "OFF" and any(value != 0 for value in values):
                    raise ValueError("OFF plot series must remain zero by definition")
    return response


def _save_figure_fresh(fig, path: Path, *, dpi: int | None = None) -> None:
    created = False
    try:
        with path.open("xb") as stream:
            created = True
            options = {"format": path.suffix.lstrip(".")}
            if dpi is not None:
                options["dpi"] = dpi
            fig.savefig(stream, **options)
    except Exception:
        if created:
            path.unlink(missing_ok=True)
        raise


def plot_response(input_path: Path, output_dir: Path) -> dict:
    if output_dir.exists():
        raise ValueError(f"plot output directory must be fresh: {output_dir}")
    response = _validate_response(input_path)
    output_dir.mkdir(parents=True)
    created = []
    try:
        fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
        try:
            colors = {}
            for ax, field in zip(axes.flat, FIELDS):
                for arm in ARMS:
                    series = response["metrics"][field][arm]
                    line, = ax.plot(TIMES, series["support"]["saved_values"],
                                    label=f"{arm} support", linestyle="-" if arm != "OFF" else ":")
                    colors[arm] = line.get_color()
                    ax.plot(TIMES, series["buffer"]["saved_values"], color=colors[arm],
                            linestyle="--" if arm != "OFF" else ":", label=f"{arm} buffer")
                ax.set_title(f"{field}: RMS(arm − OFF) [{response['fields'][field]}]")
                ax.set_xlabel("saved model seconds")
                ax.set_ylabel("RMS difference")
                ax.set_xlim(0, 600)
                ax.set_xticks(TIMES)
                ax.grid(True, alpha=0.25)
            axes.flat[0].legend(fontsize=7, ncol=2)
            fig.suptitle("PR103 matched C2 saved-history response on fixed support and buffer\n"
                         "Descriptive RMS only; OFF is zero by definition")
            png = output_dir / "pr103_sixarm_alltimes.png"
            pdf = output_dir / "pr103_sixarm_alltimes.pdf"
            _save_figure_fresh(fig, png, dpi=180)
            created.append(png)
            _save_figure_fresh(fig, pdf)
            created.append(pdf)
        finally:
            plt.close(fig)
        receipt = {
            "schema": "pr103_sixarm_history_plot_receipt_v1",
            "status": "COMPLETE",
            "response_path": str(input_path.resolve()),
            "response_sha256": sha256(input_path),
            "plotter_sha256": sha256(Path(__file__).resolve()),
            "times_seconds": TIMES,
            "fields": list(FIELDS),
            "arms": list(ARMS),
            "regions": list(REGIONS),
            "plots": [{"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size}
                      for path in created],
            "physical_approval": "FAIL_OPEN",
            "observation_skill": "NOT_EVALUATED",
            "scope": "Saved 0..600 seconds only; no extrapolation, energy interpretation, or observation-skill claim.",
        }
        receipt_path = output_dir / "plot_receipt.json"
        receipt_created = False
        try:
            with receipt_path.open("x") as stream:
                receipt_created = True
                json.dump(receipt, stream, indent=2, sort_keys=True)
                stream.write("\n")
        except Exception:
            if receipt_created:
                receipt_path.unlink(missing_ok=True)
            raise
        return receipt
    except Exception as exc:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        receipt_path = output_dir / "plot_receipt.json"
        if not receipt_path.exists():
            with receipt_path.open("x") as stream:
                json.dump({"schema": "pr103_sixarm_history_plot_receipt_v1",
                           "status": "FAILED", "error": f"{type(exc).__name__}: {exc}",
                           "response_path": str(input_path.resolve()),
                           "physical_approval": "FAIL_OPEN",
                           "observation_skill": "NOT_EVALUATED"}, stream, indent=2, sort_keys=True)
                stream.write("\n")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="closed six-arm all-saved-time response JSON")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="fresh directory for PNG, PDF, and plot receipt")
    args = parser.parse_args()
    print(json.dumps(plot_response(args.input, args.output_dir), sort_keys=True))


if __name__ == "__main__":
    main()
