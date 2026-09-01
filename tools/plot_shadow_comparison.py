#!/usr/bin/env python3
"""Plot reproducible background/proposal comparisons from one SHADOW file."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import netCDF4
import numpy as np


PRECIPITATION = ("rain", "snow", "graupel")

def stamp(dataset: netCDF4.Dataset) -> str:
    decision = (
        "HYDROMETEOR ENGINEERING VALID"
        if int(getattr(dataset, "pipeline_status")) == 20
        else "REJECTED"
    )
    target = array(dataset, "omega_target_authority").astype(bool)
    scope = "DYNAMIC BALANCE EVALUATED" if np.any(target) else "HYDROMETEOR-ONLY; WIND NOT AUTHORIZED"
    return f"{decision} DIAGNOSTIC PROPOSAL — {scope} — NOT OPERATIONAL"


def array(dataset: netCDF4.Dataset, name: str) -> np.ndarray:
    return np.asarray(np.ma.getdata(dataset[name][:]), dtype=float)


def save_figure(figure: plt.Figure, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp.{os.getpid()}")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            figure.savefig(stream, format="png", dpi=150)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        if temporary.exists() and not temporary.is_symlink():
            temporary.unlink()


def shared_limits(left: np.ndarray, right: np.ndarray) -> tuple[float, float]:
    finite = np.concatenate((left[np.isfinite(left)], right[np.isfinite(right)]))
    if finite.size == 0:
        return 0.0, 1.0
    low, high = np.percentile(finite, (1.0, 99.0))
    if high <= low:
        high = low + 1.0
    return float(low), float(high)


def symmetric_limit(field: np.ndarray) -> float:
    finite = np.abs(field[np.isfinite(field)])
    return max(float(np.percentile(finite, 99.0)) if finite.size else 0.0, 1.0e-9)


def add_map(
    axis: plt.Axes,
    longitude: np.ndarray,
    latitude: np.ndarray,
    field: np.ndarray,
    title: str,
    limits: tuple[float, float],
    cmap: str,
    radar: np.ndarray,
    target: np.ndarray,
) -> None:
    image = axis.pcolormesh(
        longitude, latitude, field, shading="auto", cmap=cmap,
        vmin=limits[0], vmax=limits[1], rasterized=True,
    )
    if np.any(radar):
        axis.contour(longitude, latitude, radar, levels=[0.5], colors="black", linewidths=0.35)
    if np.any(target):
        axis.contour(longitude, latitude, target, levels=[0.5], colors="magenta", linewidths=0.5)
    axis.set_title(title)
    axis.set_xlabel("longitude")
    axis.set_ylabel("latitude")
    plt.colorbar(image, ax=axis, shrink=0.82)


def precipitation(dataset: netCDF4.Dataset, prefix: str) -> np.ndarray:
    return 1.0e3 * sum(array(dataset, f"{prefix}_{name}") for name in PRECIPITATION)


def horizontal_figure(dataset: netCDF4.Dataset, output: Path) -> None:
    longitude = array(dataset, "longitude")
    latitude = array(dataset, "latitude")
    target = array(dataset, "omega_target_authority").astype(bool)
    radar = array(dataset, "radar_valid").astype(bool)
    counts = np.count_nonzero(target, axis=(1, 2))
    if not np.any(counts):
        counts = np.count_nonzero(radar, axis=(1, 2))
    level = int(np.argmax(counts))
    pressure = array(dataset, "pressure")[level] / 100.0

    u0, v0 = array(dataset, "background_u"), array(dataset, "background_v")
    u1, v1 = array(dataset, "candidate_u"), array(dataset, "candidate_v")
    speed0 = np.hypot(u0[level], v0[level])
    speed1 = np.hypot(u1[level], v1[level])
    wind_change = np.hypot(u1[level] - u0[level], v1[level] - v0[level])
    omega0 = array(dataset, "background_omega")[level]
    omega1 = array(dataset, "candidate_omega")[level]
    precip0 = precipitation(dataset, "background")[level]
    precip1 = precipitation(dataset, "candidate")[level]

    pairs = (
        (speed0, speed1, wind_change, "wind speed", "m s-1", "viridis", "magma"),
        (omega0, omega1, omega1 - omega0, "omega", "Pa s-1", "RdBu_r", "RdBu_r"),
        (precip0, precip1, precip1 - precip0, "precipitating water", "g kg-1 dryair", "Blues", "RdBu_r"),
    )
    fig, axes = plt.subplots(3, 3, figsize=(17, 15), constrained_layout=True)
    for row, (before, after, change, name, unit, base_cmap, change_cmap) in enumerate(pairs):
        base_limits = shared_limits(before, after)
        change_limit = symmetric_limit(change)
        add_map(axes[row, 0], longitude, latitude, before, f"background {name} [{unit}]", base_limits, base_cmap, radar[level], target[level])
        add_map(axes[row, 1], longitude, latitude, after, f"proposal {name} [{unit}]", base_limits, base_cmap, radar[level], target[level])
        change_limits = (0.0, change_limit) if name == "wind speed" else (-change_limit, change_limit)
        change_title = "horizontal wind increment magnitude" if name == "wind speed" else "proposal − background"
        add_map(axes[row, 2], longitude, latitude, change, f"{change_title} [{unit}]", change_limits, change_cmap, radar[level], target[level])

    fig.suptitle(
        f"{stamp(dataset)}\n{pressure:.0f} hPa; "
        "black=direct radar, magenta=dynamic target",
        fontsize=15,
    )
    save_figure(fig, output)
    plt.close(fig)


def section(dataset: netCDF4.Dataset, field: np.ndarray, along_x: bool, fixed: int) -> np.ndarray:
    return field[:, fixed, :] if along_x else field[:, :, fixed]


def vertical_figure(dataset: netCDF4.Dataset, output: Path) -> None:
    radar_valid = array(dataset, "radar_valid").astype(bool)
    reflectivity = np.where(radar_valid, array(dataset, "radar_dbz"), np.nan)
    peak = np.nanargmax(reflectivity)
    level, y_index, x_index = np.unravel_index(peak, reflectivity.shape)
    u = array(dataset, "background_u")[level, y_index, x_index]
    v = array(dataset, "background_v")[level, y_index, x_index]
    along_x = abs(u) >= abs(v)
    fixed = y_index if along_x else x_index
    horizontal = np.arange(reflectivity.shape[2 if along_x else 1]) * float(
        getattr(dataset, "grid_dx_m" if along_x else "grid_dy_m")
    ) / 1000.0
    pressure = array(dataset, "pressure") / 100.0

    precip0 = precipitation(dataset, "background")
    precip1 = precipitation(dataset, "candidate")
    omega0 = array(dataset, "background_omega")
    omega1 = array(dataset, "candidate_omega")
    target = array(dataset, "omega_target")
    panels = (
        (section(dataset, reflectivity, along_x, fixed), "radar reflectivity [dBZ]", (0.0, 60.0), "turbo"),
        (section(dataset, precip0, along_x, fixed), "background precipitation [g kg-1]", shared_limits(precip0, precip1), "Blues"),
        (section(dataset, precip1, along_x, fixed), "proposal precipitation [g kg-1]", shared_limits(precip0, precip1), "Blues"),
        (section(dataset, precip1 - precip0, along_x, fixed), "proposal − background precipitation", (-symmetric_limit(precip1 - precip0), symmetric_limit(precip1 - precip0)), "RdBu_r"),
        (section(dataset, target, along_x, fixed), "diagnosed omega target [Pa s-1]", (-symmetric_limit(target), symmetric_limit(target)), "RdBu_r"),
        (section(dataset, omega0, along_x, fixed), "background omega [Pa s-1]", shared_limits(omega0, omega1), "RdBu_r"),
        (section(dataset, omega1, along_x, fixed), "proposal omega [Pa s-1]", shared_limits(omega0, omega1), "RdBu_r"),
        (section(dataset, omega1 - omega0, along_x, fixed), "proposal − background omega", (-symmetric_limit(omega1 - omega0), symmetric_limit(omega1 - omega0)), "RdBu_r"),
    )
    fig, axes = plt.subplots(2, 4, figsize=(21, 10), constrained_layout=True)
    for axis, (field, title, limits, cmap) in zip(axes.flat, panels):
        image = axis.pcolormesh(horizontal, pressure, field, shading="auto", cmap=cmap, vmin=limits[0], vmax=limits[1], rasterized=True)
        axis.invert_yaxis()
        axis.set_title(title)
        axis.set_xlabel("distance along grid axis [km]")
        axis.set_ylabel("pressure [hPa]")
        plt.colorbar(image, ax=axis, shrink=0.82)
    direction = "west–east" if along_x else "south–north"
    fig.suptitle(
        f"{stamp(dataset)}\n{direction} section through maximum direct echo",
        fontsize=15,
    )
    save_figure(fig, output)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diagnostic", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    stem = args.diagnostic.stem
    with netCDF4.Dataset(args.diagnostic, "r") as dataset:
        if getattr(dataset, "result_authority", "") != "DIAGNOSTIC_PROPOSAL_ONLY":
            raise ValueError("only diagnostic-only SHADOW proposals may be plotted")
        horizontal_figure(dataset, args.output_directory / f"{stem}_horizontal.png")
        vertical_figure(dataset, args.output_directory / f"{stem}_vertical.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
