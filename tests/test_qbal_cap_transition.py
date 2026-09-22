#!/usr/bin/env python3
"""Reproduce the legacy lower-transport cap transition around 95 kPa.

The driver is deliberately kept outside this test.  Callers pass one or two
fresh Intel builds of ``diagnose_qbal_lower_transport``; the optional second
build is used to compare O0 and O2 arithmetic.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import subprocess
import tempfile

import numpy as np


RD = 287.05
GRAVITY = 9.80665
TEMPERATURE = 300.0
SAMPLE_HEIGHT = 10.0
P_LEVEL = 95000.0
P_NEXT = 90000.0
P_TOP = 5000.0
LEGACY_JUMP = 0.5 * ((8.0 + 6.0) - (4.0 + 6.0)) * (P_LEVEL - P_NEXT)


def _write_input(path: Path, surface_u: float, p10: float) -> None:
    """Write the small three-node stream accepted by the Fortran driver."""
    nn, nz, nt, ne = 3, 3, 1, 3
    lat0 = math.radians(38.0)
    lon0 = math.radians(126.0)
    delta = 1.0e-5
    lat = np.array([lat0 - delta, lat0 + delta, lat0], dtype=np.float64)
    lon = np.array([lon0, lon0, lon0 - delta], dtype=np.float64)
    terrain = np.zeros(nn, dtype=np.float64)
    pressure = np.array([P_LEVEL, P_NEXT, P_TOP], dtype=np.float64)
    ps_value = p10 * math.exp(GRAVITY * SAMPLE_HEIGHT / (RD * TEMPERATURE))
    ps = np.full((3, nn), ps_value, dtype=np.float64)
    heights = np.empty((3, nn, nz), dtype=np.float64)
    for time in range(3):
        heights[time, :, :] = RD * TEMPERATURE / GRAVITY * np.log(
            ps[time, :, None] / pressure[None, :]
        )

    # U is [8, 6, 2] at [95, 90, 5] kPa; V is identically zero.
    u = np.broadcast_to(
        np.array([8.0, 6.0, 2.0], dtype=np.float64)[None, None, :],
        (3, nn, nz),
    ).copy()
    v = np.zeros_like(u)
    surface_u_values = np.full((nn, 3), surface_u, dtype=np.float64)
    surface_v_values = np.zeros_like(surface_u_values)
    omega = np.zeros((3, nn), dtype=np.float64)

    # The first edge is vertical in the equal-area chart.  Its outward normal
    # is eastward, making its known transport per chart edge length easy to
    # inspect while the other two edges close the triangle.
    parameters = np.array([lat0, lon0, 6371200.0, 0.0, lon0], dtype=np.float64)
    triangles = np.array([[1], [2], [3]], dtype="<i4")
    edges = np.array([[1, 2, 3], [2, 3, 1]], dtype="<i4")
    incidence = np.array([[1], [2], [3]], dtype="<i4")
    with path.open("wb") as stream:
        stream.write(np.array([nn, nz, nt, ne], dtype="<i4").tobytes())
        stream.write(np.array([0, 3600, 7200], dtype="<i8").tobytes())
        for value in (
            parameters,
            lat,
            lon,
            terrain,
            pressure,
            ps,
            heights,
            u,
            v,
            surface_u_values,
            surface_v_values,
            omega,
        ):
            stream.write(np.asarray(value, dtype="<f8").tobytes())
        for value in (triangles, edges, incidence):
            stream.write(value.tobytes())

        # Current surface-thermo mode reads T/r at the surface and T/r at all
        # pressure levels.  The dry, isothermal profile is HT-consistent.
        stream.write(np.full((nn, 3), TEMPERATURE, dtype="<f8").tobytes())
        stream.write(np.zeros((nn, 3), dtype="<f8").tobytes())
        stream.write(np.full((3, nn, nz), TEMPERATURE, dtype="<f8").tobytes())
        stream.write(np.zeros((3, nn, nz), dtype="<f8").tobytes())


def _read_output(path: Path) -> dict[str, np.ndarray]:
    nn, nz, nt, ne = 3, 3, 1, 3
    counts = [
        2 * nn,
        3 * nn,
        3 * ne,
        3 * ne,
        3 * ne,
        nt,
        nt,
        nt,
        nt,
        3 * nt,
        nt,
        nt,
    ]
    names = (
        "xy",
        "p10",
        "covered",
        "lower",
        "missing",
        "area",
        "surface",
        "volume_rate",
        "bound",
        "top",
        "known",
        "residual",
    )
    with path.open("rb") as stream:
        raw = np.fromfile(stream, dtype="<f8", count=sum(counts))
        mapped = np.fromfile(stream, dtype="<i4", count=3 * nn).reshape(3, nn)
        domain = np.fromfile(stream, dtype="<f8", count=2)
        unknown = np.fromfile(stream, dtype="<i4", count=2)
        thermo = np.fromfile(stream, dtype="<f8", count=15 * nn).reshape(3, nn, 5)
        defects = np.fromfile(stream, dtype="<f8", count=3 * nn * (nz - 1))
        cap_audit = np.fromfile(stream, dtype="<f8", count=15 * ne)
        if stream.read(1):
            raise AssertionError(f"{path}: unexpected trailing output")
    if raw.size != sum(counts):
        raise AssertionError(f"{path}: incomplete output stream")
    values = dict(zip(names, np.split(raw, np.cumsum(counts)[:-1])))
    for name, width in (
        ("p10", nn),
        ("covered", ne),
        ("lower", ne),
        ("missing", ne),
        ("top", nt),
    ):
        values[name] = values[name].reshape(3, width)
    values["xy"] = values["xy"].reshape(nn, 2)
    values["mapped"] = mapped
    values["domain"] = domain
    values["unknown"] = unknown
    values["thermo"] = thermo
    values["defects"] = defects.reshape(3, nn, nz - 1)
    if cap_audit.size:
        if cap_audit.size != 15 * ne:
            raise AssertionError(f"{path}: incomplete cap-audit output")
        values["cap_audit"] = cap_audit.reshape(3, ne, 5)
    return values


def _run_case(
    executable: Path,
    surface_u: float,
    p10: float,
    artifact_dir: Path | None,
    label: str,
    audit: bool = False,
) -> dict[str, np.ndarray]:
    if artifact_dir is None:
        context = tempfile.TemporaryDirectory()
        root = Path(context.name)
    else:
        root = artifact_dir / label
        root.mkdir(parents=True, exist_ok=False)
        context = None
    try:
        input_path = root / "input.bin"
        output_path = root / "result.bin"
        _write_input(input_path, surface_u, p10)
        command = [str(executable.resolve()), str(input_path), str(output_path), "surface-thermo"]
        if audit:
            command.append("cap-audit")
        if artifact_dir is None:
            completed = subprocess.run(command, check=True, capture_output=True, text=True)
        else:
            log_path = root / "run.log"
            with log_path.open("w", encoding="utf-8") as log:
                completed = subprocess.run(
                    command,
                    check=False,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            if completed.returncode:
                raise subprocess.CalledProcessError(completed.returncode, command)
        return _read_output(output_path)
    finally:
        if context is not None:
            context.cleanup()


def _check_single_level(
    executable: Path, artifact_dir: Path | None, level_name: str
) -> dict[str, dict[str, np.ndarray]]:
    outputs: dict[str, dict[str, np.ndarray]] = {}
    for surface_u in (4.0, 8.0):
        surface_name = f"surface_u{int(surface_u)}"
        for side, p10 in (("below", P_LEVEL - 1.0e-6), ("above", P_LEVEL + 1.0e-6)):
            label = f"{level_name}_{surface_name}_{side}"
            outputs[f"{surface_name}_{side}"] = _run_case(
                executable, surface_u, p10, artifact_dir, label
            )

    for name, result in outputs.items():
        side = "below" if name.endswith("below") else "above"
        expected_p10 = P_LEVEL + (-1.0e-6 if side == "below" else 1.0e-6)
        np.testing.assert_allclose(result["p10"], expected_p10, rtol=0.0, atol=2.0e-9)
        np.testing.assert_array_equal(result["mapped"], 1)
        np.testing.assert_array_equal(result["unknown"], [3, 0])
        np.testing.assert_array_equal(np.isfinite(result["residual"]), False)
        np.testing.assert_equal(np.isfinite(result["domain"][1]), False)
        np.testing.assert_allclose(result["thermo"][:, :, 0], TEMPERATURE, rtol=0.0, atol=2.0e-12)
        np.testing.assert_allclose(result["defects"], 0.0, rtol=0.0, atol=2.0e-8)

    # The provisional fourth argument must preserve the legacy thermo stream
    # byte layout and append exactly 5*ne*3 doubles.  Future profile APIs can
    # replace this audit payload without changing the reproducer below.
    audit = _run_case(
        executable,
        4.0,
        P_LEVEL - 1.0e-6,
        artifact_dir,
        f"{level_name}_cap_audit",
        audit=True,
    )
    base = outputs["surface_u4_below"]
    for field in ("xy", "p10", "covered", "lower", "missing", "area", "surface", "volume_rate", "bound", "top", "known", "residual", "mapped", "domain", "unknown", "thermo", "defects"):
        np.testing.assert_allclose(
            audit[field], base[field], rtol=0.0, atol=2.0e-8, equal_nan=True,
            err_msg=f"cap-audit changed legacy {field} stream",
        )
    assert audit["cap_audit"].shape == (3, 3, 5)
    np.testing.assert_array_equal(np.isfinite(audit["cap_audit"][:, :, 0]), True)

    below = outputs["surface_u4_below"]
    above = outputs["surface_u4_above"]
    edge_lengths = np.linalg.norm(
        below["xy"][np.array([1, 2, 0])] - below["xy"][np.array([0, 1, 2])], axis=1
    )
    legacy_transport = below["covered"][0] + below["lower"][0]
    above_transport = above["covered"][0] + above["lower"][0]
    jump_per_length = (above_transport - legacy_transport) / edge_lengths
    np.testing.assert_allclose(jump_per_length[0], LEGACY_JUMP, rtol=0.0, atol=2.0e-3)

    control_below = outputs["surface_u8_below"]
    control_above = outputs["surface_u8_above"]
    control_jump_per_length = (
        control_above["covered"][0]
        + control_above["lower"][0]
        - control_below["covered"][0]
        - control_below["lower"][0]
    ) / edge_lengths
    np.testing.assert_allclose(control_jump_per_length[0], 0.0, rtol=0.0, atol=2.0e-3)
    return outputs


def check_drivers(executables: list[Path], artifact_dir: Path | None = None) -> None:
    if not 1 <= len(executables) <= 2:
        raise ValueError("pass one or two Intel driver builds")
    runs = [
        _check_single_level(executable, artifact_dir, f"level_{index}")
        for index, executable in enumerate(executables)
    ]
    if len(runs) == 2:
        for name in runs[0]:
            for field in ("p10", "covered", "lower", "known", "thermo", "defects"):
                np.testing.assert_allclose(
                    runs[0][name][field],
                    runs[1][name][field],
                    rtol=2.0e-12,
                    atol=2.0e-5,
                    err_msg=f"O0/O2 mismatch in {name}/{field}",
                )
    print(f"Legacy cap transition: {len(executables)} Intel driver level(s) passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path, nargs="+", help="one or two Intel driver builds")
    parser.add_argument("--artifact-dir", type=Path, help="retain input/output/log files")
    args = parser.parse_args()
    if not 1 <= len(args.executable) <= 2:
        parser.error("pass one or two Intel driver builds")
    check_drivers(args.executable, args.artifact_dir)
