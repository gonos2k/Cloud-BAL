#!/usr/bin/env python3
"""Plot actual QBAL input fields against a test-only balanced candidate."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
import numpy as np
from netCDF4 import Dataset

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402


LEVEL_PA = 55000.0


def plot(path: Path, output: Path, title: str) -> None:
    with Dataset(path) as dataset:
        pressure = np.asarray(dataset["pressure"][:], dtype=np.float64)
        k = int(np.argmin(np.abs(pressure - LEVEL_PA)))
        lon = np.asarray(dataset["longitude"][:], dtype=np.float64)
        lat = np.asarray(dataset["latitude"][:], dtype=np.float64)
        omega0 = np.asarray(dataset["background_omega"][k], dtype=np.float64)
        omega1 = np.asarray(dataset["candidate_omega"][k], dtype=np.float64)
        u0 = np.asarray(dataset["background_u"][k], dtype=np.float64)
        v0 = np.asarray(dataset["background_v"][k], dtype=np.float64)
        u1 = np.asarray(dataset["candidate_u"][k], dtype=np.float64)
        v1 = np.asarray(dataset["candidate_v"][k], dtype=np.float64)
        beta = np.asarray(dataset["balance_beta"][k], dtype=np.float64)
        original_hydro = np.asarray(
            dataset["original_total_hydrometeor"][k], dtype=np.float64
        ) * 1000.0
        proposal_hydro = np.asarray(
            dataset["proposal_total_hydrometeor"][k], dtype=np.float64
        ) * 1000.0
        radar = np.asarray(dataset["radar_dbz"][k], dtype=np.float64)
        boundary = np.asarray(dataset["omega_bottom_boundary"][:], dtype=np.float64)
        residual0 = np.asarray(dataset["continuity_background"][k], dtype=np.float64)
        residual1 = np.asarray(dataset["continuity_candidate"][k], dtype=np.float64)
        residual_increment = np.asarray(
            dataset["continuity_projected_increment"][k], dtype=np.float64
        )

    domega = omega1 - omega0
    wind_increment = np.hypot(u1 - u0, v1 - v0)
    support = np.argwhere(beta > 0.0)
    if support.size == 0:
        raise ValueError("balance support is empty")
    j0, i0 = np.maximum(support.min(axis=0) - 4, 0)
    j1, i1 = np.minimum(support.max(axis=0) + 5, beta.shape)
    zoom = np.s_[j0:j1, i0:i1]
    fig, axes = plt.subplots(3, 4, figsize=(20, 13), constrained_layout=True)
    panels = [
        (original_hydro, "Original QBAL-input hydrometeor", "viridis", 0.0, 15.0,
         None, "g kg$^{-1}$", False),
        (proposal_hydro, "Radar-column mass proposal", "viridis", 0.0, 15.0,
         None, "g kg$^{-1}$", False),
        (radar, "S-band composite reflectivity", "turbo", 0.0, 65.0, None, "dBZ", False),
        (boundary, "FSF PS-tendency/advection test boundary", "RdBu_r", None, None,
         TwoSlopeNorm(vmin=-5.0, vcenter=0.0, vmax=5.0), "Pa s$^{-1}$", False),
        (omega0, "QBAL-input omega", "RdBu_r", None, None,
         TwoSlopeNorm(vmin=-2.0, vcenter=0.0, vmax=2.0), "Pa s$^{-1}$", False),
        (omega1, "Numerical-test candidate omega", "RdBu_r", None, None,
         TwoSlopeNorm(vmin=-2.0, vcenter=0.0, vmax=2.0), "Pa s$^{-1}$", False),
        (domega, "Candidate - input omega (support zoom)", "RdBu_r", None, None,
         TwoSlopeNorm(vmin=-0.02, vcenter=0.0, vmax=0.02), "Pa s$^{-1}$", True),
        (wind_increment, "Horizontal wind increment (support zoom)", "magma", 0.0, 0.5,
         None, "m s$^{-1}$", True),
        (beta, "Compact balance support (zoom)", "Greys", 0.0, 1.0, None, "0–1", True),
        (residual0, "Input continuity residual (zoom)", "RdBu_r", None, None,
         TwoSlopeNorm(vmin=-1.0e-3, vcenter=0.0, vmax=1.0e-3), "s$^{-1}$", True),
        (residual1, "Candidate continuity residual (zoom)", "RdBu_r", None, None,
         TwoSlopeNorm(vmin=-1.0e-3, vcenter=0.0, vmax=1.0e-3), "s$^{-1}$", True),
        (residual_increment, "Projected increment residual (zoom)", "RdBu_r", None, None,
         TwoSlopeNorm(vmin=-1.0e-6, vcenter=0.0, vmax=1.0e-6), "s$^{-1}$", True),
    ]
    for axis, (values, label, cmap, vmin, vmax, norm, unit, use_zoom) in zip(
        axes.ravel(), panels
    ):
        kwargs = {"cmap": cmap, "shading": "auto", "rasterized": True}
        if norm is None:
            kwargs.update(vmin=vmin, vmax=vmax)
        else:
            kwargs["norm"] = norm
        if use_zoom:
            image = axis.pcolormesh(lon[zoom], lat[zoom], values[zoom], **kwargs)
        else:
            image = axis.pcolormesh(lon, lat, values, **kwargs)
        axis.set_title(label)
        axis.set_xlabel("longitude")
        axis.set_ylabel("latitude")
        fig.colorbar(image, ax=axis, shrink=0.82, label=unit)
    fig.suptitle(
        f"{title} at {pressure[k] / 100:.0f} hPa\n"
        "Actual KLAPS QBAL input geometry; manufactured target/boundary; science authority NONE",
        fontsize=14,
    )
    fig.savefig(output, dpi=150)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("diagnostic", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--title", required=True)
    args = parser.parse_args()
    plot(args.diagnostic, args.output, args.title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
