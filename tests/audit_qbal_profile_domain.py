#!/usr/bin/env python3
"""Audit shared NE57 LW3 fixed-knot support from the PR39 prepared stream.

This is a diagnostic reader.  Face selection uses only ``p10`` from the PR39
arrays and ``p``, ``PS``, ``HT``, ``U3/V3``, coordinates, edges and incidence
from the prepared stream.  It deliberately does not read any flux output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


TIME_LABELS = ("12", "13", "14")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read(stream, dtype: str, count: int) -> np.ndarray:
    value = np.fromfile(stream, dtype=dtype, count=count)
    if value.size != count:
        raise ValueError(f"prepared stream ended while reading {count} {dtype} values")
    return value


def _validate_mesh(
    nn: int,
    nt: int,
    ne: int,
    pressure: np.ndarray,
    triangles: np.ndarray,
    edges: np.ndarray,
    incidence: np.ndarray,
) -> None:
    """Reject malformed pressure levels or a non-manifold triangle mesh."""
    if not np.isfinite(pressure).all() or np.any(pressure <= 0) or not np.all(np.diff(pressure) < 0):
        raise ValueError("regular pressure knots must be finite, positive, and strictly descending")
    if triangles.shape != (nt, 3) or edges.shape != (ne, 2) or incidence.shape != (nt, 3):
        raise ValueError("prepared mesh extents do not match the header")
    if np.any(triangles < 0) or np.any(triangles >= nn):
        raise ValueError("triangle vertex is outside the node range")
    if np.any(edges < 0) or np.any(edges >= nn):
        raise ValueError("edge endpoint is outside the node range")
    if np.any(incidence == 0) or np.any(np.abs(incidence) > ne):
        raise ValueError("incidence edge index is outside 1..ne")
    if any(len(np.unique(row)) != 3 for row in triangles):
        raise ValueError("triangle has duplicate vertices")
    if any(row[0] == row[1] for row in edges):
        raise ValueError("edge has identical endpoints")
    if len(np.unique(np.sort(edges, axis=1), axis=0)) != ne:
        raise ValueError("duplicate geometric edge")
    occurrences: list[list[tuple[int, int]]] = [[] for _ in range(ne)]
    for cell, row in enumerate(incidence):
        edge_ids = np.abs(row) - 1
        if len(np.unique(edge_ids)) != 3:
            raise ValueError("triangle has a duplicate incidence edge")
        vertices = triangles[cell]
        directed_edges = {(int(vertices[k]), int(vertices[(k + 1) % 3])) for k in range(3)}
        for signed_edge in row:
            edge_id = abs(int(signed_edge)) - 1
            endpoint_pair = edges[edge_id] if signed_edge > 0 else edges[edge_id, ::-1]
            if tuple(endpoint_pair) not in directed_edges:
                raise ValueError("signed edge does not follow its triangle boundary")
            occurrences[edge_id].append((cell, int(np.sign(signed_edge))))
    for edge_id, uses in enumerate(occurrences):
        if len(uses) == 0:
            raise ValueError(f"orphan edge {edge_id}")
        cells = [cell for cell, _ in uses]
        signs = [sign for _, sign in uses]
        if len(cells) != len(set(cells)):
            raise ValueError(f"edge {edge_id} is repeated in one triangle")
        if len(uses) == 1:
            continue
        if len(uses) != 2 or cells[0] == cells[1] or sorted(signs) != [-1, 1]:
            raise ValueError(f"edge {edge_id} is not exactly one boundary or two opposite internal uses")


def read_prepared(path: Path) -> dict[str, np.ndarray | int]:
    """Read the exact little-endian layout written by PR39's Python driver."""
    with path.open("rb") as stream:
        nn, nz, nt, ne = _read(stream, "<i4", 4).tolist()
        if min(nn, nz, nt, ne) < 1 or nz < 2:
            raise ValueError("prepared header dimensions must be positive")
        times = _read(stream, "<i8", 3)
        parameters = _read(stream, "<f8", 5)
        read_real = lambda count: _read(stream, "<f8", count)

        lat = read_real(nn)
        lon = read_real(nn)
        terrain = read_real(nn)
        pressure = read_real(nz)
        ps = read_real(3 * nn).reshape(3, nn)
        height = read_real(3 * nz * nn).reshape(3, nn, nz)
        u = read_real(3 * nz * nn).reshape(3, nn, nz)
        v = read_real(3 * nz * nn).reshape(3, nn, nz)
        surface_u = read_real(3 * nn).reshape(3, nn)
        surface_v = read_real(3 * nn).reshape(3, nn)
        omega = read_real(3 * nn).reshape(3, nn)
        triangles = _read(stream, "<i4", 3 * nt).reshape(nt, 3) - 1
        edges = _read(stream, "<i4", 2 * ne).reshape(ne, 2) - 1
        incidence = _read(stream, "<i4", 3 * nt).reshape(nt, 3)
        # The thermodynamic PR39 stream appends LSX T/MR and LT1/LQ3
        # profile fields after the mesh.  They are not needed for this
        # domain audit, but consuming their exact extent guards the layout.
        _read(stream, "<f8", 6 * nn + 6 * nz * nn)
        if stream.read(1):
            raise ValueError("prepared stream has unexpected trailing bytes")

    _validate_mesh(nn, nt, ne, pressure, triangles, edges, incidence)
    return {
        "nn": nn,
        "nz": nz,
        "nt": nt,
        "ne": ne,
        "times": times,
        "parameters": parameters,
        "lat": lat,
        "lon": lon,
        "terrain": terrain,
        "pressure": pressure,
        "ps": ps,
        "height": height,
        "u": u,
        "v": v,
        "surface_u": surface_u,
        "surface_v": surface_v,
        "omega": omega,
        "triangles": triangles,
        "edges": edges,
        "incidence": incidence,
    }


def _regular_cap(pressure: np.ndarray, min_ps: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return q and p(q), where p(q) is the largest regular knot <= min PS."""
    q = np.empty(min_ps.shape, dtype=np.int32)
    for j, row in enumerate(min_ps):
        for edge, value in enumerate(row):
            candidates = np.flatnonzero(pressure <= value)
            if candidates.size == 0:
                raise ValueError("an edge has no regular knot at or below its minimum PS")
            q[j, edge] = candidates[0]
    return q, pressure[q]


def _selected_raw_winds(case: dict[str, np.ndarray | int], edge_ids: np.ndarray) -> dict[str, np.ndarray]:
    """Return source LW3 winds without duplicating the Fortran chart transform."""
    endpoint_nodes = np.asarray(case["edges"])[edge_ids]
    return {
        "endpoint_nodes_zero": endpoint_nodes,
        "raw_u": np.asarray(case["u"])[:, endpoint_nodes, :],
        "raw_v": np.asarray(case["v"])[:, endpoint_nodes, :],
        "raw_surface_u": np.asarray(case["surface_u"])[:, endpoint_nodes],
        "raw_surface_v": np.asarray(case["surface_v"])[:, endpoint_nodes],
    }


def audit_domain(arrays_path: Path, prepared_path: Path) -> tuple[dict, dict[str, np.ndarray]]:
    """Build the pressure and HT-domain inventory without consulting flux output."""
    report_path = arrays_path.with_name("report.json")
    source_report = json.loads(report_path.read_text(encoding="utf-8"))
    expected_hashes = source_report.get("artifact_sha256", {})
    for name, path in (("prepared.bin", prepared_path), ("arrays.npz", arrays_path)):
        expected = expected_hashes.get(name)
        if expected is None:
            raise ValueError(f"source report has no hash for {name}")
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"{name} hash differs from source report")
    arrays = np.load(arrays_path, allow_pickle=False)
    p10 = np.asarray(arrays["p10"], dtype=np.float64)
    edges = np.asarray(arrays["edges"], dtype=np.int32)
    incidence = np.asarray(arrays["incidence"], dtype=np.int32)
    chart_xy = np.asarray(arrays["xy"], dtype=np.float64)
    case = read_prepared(prepared_path)
    stream_edges = np.asarray(case["edges"], dtype=np.int32)
    stream_incidence = np.asarray(case["incidence"], dtype=np.int32)
    if not np.array_equal(edges, stream_edges) or not np.array_equal(incidence, stream_incidence):
        raise ValueError("arrays.npz mesh differs from prepared stream mesh")
    nn, ne, nt = int(case["nn"]), int(case["ne"]), int(case["nt"])
    if p10.shape != (3, nn) or chart_xy.shape != (nn, 2):
        raise ValueError("unexpected PR39 array extent")

    signs = np.bincount(
        np.abs(incidence).ravel() - 1,
        weights=np.sign(incidence).ravel(),
        minlength=ne,
    )
    internal = signs == 0
    ps = np.asarray(case["ps"])
    pressure = np.asarray(case["pressure"])
    endpoint_ps = ps[:, edges]
    endpoint_p10 = p10[:, edges]
    min_endpoint_ps = endpoint_ps.min(axis=2)
    q_index, p_cap = _regular_cap(pressure, min_endpoint_ps)

    # The requested pressure domain is inclusive in p10 at existing knots,
    # while "strictly above ground" is explicit at each endpoint.
    pressure_domain = (
        np.all(endpoint_p10 >= pressure[-1], axis=2)
        & np.all(endpoint_p10 <= p_cap[:, :, None], axis=2)
        & np.all(endpoint_p10 < endpoint_ps, axis=2)
    )

    # HT-AVG is evaluated at q and q+1.  Since pressure decreases with k,
    # monotonic HT means HT[k+1] > HT[k] through the existing profile.
    height = np.asarray(case["height"])
    terrain = np.asarray(case["terrain"])
    ht_minus_avg_q = np.full((3, ne, 2), np.nan)
    ht_minus_avg_next = np.full((3, ne, 2), np.nan)
    ht_above_ground = np.zeros((3, ne), dtype=bool)
    ht_monotonic = np.zeros((3, ne), dtype=bool)
    brackets_10m = np.zeros((3, ne), dtype=bool)
    for j in range(3):
        for edge in range(ne):
            nodes = edges[edge]
            q = q_index[j, edge]
            if q >= pressure.size - 1:
                raise ValueError("cap knot has no existing next regular knot")
            ht = height[j, nodes, q:] - terrain[nodes, None]
            ht_minus_avg_q[j, edge] = ht[:, 0]
            ht_minus_avg_next[j, edge] = ht[:, 1]
            ht_above_ground[j, edge] = np.all(ht[:, 0] > 0)
            ht_monotonic[j, edge] = np.isfinite(ht).all() and np.all(np.diff(ht, axis=1) > 0)
            brackets_10m[j, edge] = np.all((ht[:, 0] <= 10) & (ht[:, 1] >= 10))
    strict_ht_domain = pressure_domain & ht_above_ground & ht_monotonic

    def first(mask: np.ndarray) -> int | None:
        values = np.flatnonzero(mask)
        return int(values[0]) if values.size else None

    pressure_internal = pressure_domain & internal[None, :]
    strict_internal = strict_ht_domain & internal[None, :]
    strict_bracket_internal = strict_internal & brackets_10m
    selected_pressure = first(pressure_internal[1])
    selected_strict = first(strict_internal[1])
    # Prefer the optional 0-10 m bracket only when it exists; otherwise use
    # the lowest strict above-ground face and state that fallback explicitly.
    selected_preferred = first(strict_bracket_internal[1])
    selection_fallback = selected_preferred is None
    if selection_fallback:
        selected_preferred = selected_strict
    if selected_pressure is None or selected_strict is None:
        raise ValueError("no eligible internal 13 UTC face")

    selected_ids = np.array(
        [selected_pressure, selected_strict, selected_preferred], dtype=np.int32
    )
    winds = _selected_raw_winds(case, selected_ids)
    selected_nodes = np.asarray(case["edges"])[selected_ids]
    selected_q = q_index[:, selected_ids]

    counts = {
        "pressure_only": {
            label: int(pressure_domain[j].sum()) for j, label in enumerate(TIME_LABELS)
        },
        "pressure_only_internal": {
            label: int(pressure_internal[j].sum()) for j, label in enumerate(TIME_LABELS)
        },
        "strict_ht": {label: int(strict_ht_domain[j].sum()) for j, label in enumerate(TIME_LABELS)},
        "strict_ht_internal": {
            label: int(strict_internal[j].sum()) for j, label in enumerate(TIME_LABELS)
        },
        "strict_ht_bracket10m_internal": {
            label: int(strict_bracket_internal[j].sum()) for j, label in enumerate(TIME_LABELS)
        },
        "all_three_pressure_only": int(pressure_domain.all(axis=0).sum()),
        "all_three_pressure_only_internal": int((pressure_domain.all(axis=0) & internal).sum()),
        "all_three_strict_ht": int(strict_ht_domain.all(axis=0).sum()),
        "all_three_strict_ht_internal": int((strict_ht_domain.all(axis=0) & internal).sum()),
        "all_three_strict_ht_bracket10m_internal": int(
            (strict_bracket_internal.all(axis=0) & internal).sum()
        ),
    }

    def selected_record(edge: int, label: str) -> dict:
        nodes = edges[edge]
        return {
            "criterion": label,
            "edge_index_zero_based": int(edge),
            "edge_index_fortran": int(edge + 1),
            "node_indices_zero_based": nodes.tolist(),
            "node_indices_fortran": (nodes + 1).tolist(),
            "incident_triangle_indices_zero_based": np.flatnonzero(
                np.any(np.abs(incidence) == edge + 1, axis=1)
            ).tolist(),
            "node_latitude_degrees": np.rad2deg(np.asarray(case["lat"])[nodes]).tolist(),
            "node_longitude_degrees": np.rad2deg(np.asarray(case["lon"])[nodes]).tolist(),
            "node_chart_xy_m": chart_xy[nodes].tolist(),
            "node_terrain_m": np.asarray(case["terrain"])[nodes].tolist(),
            "endpoint_ps_pa_by_time": endpoint_ps[:, edge].tolist(),
            "endpoint_p10_pa_by_time": endpoint_p10[:, edge].tolist(),
            "minimum_endpoint_ps_pa_by_time": min_endpoint_ps[:, edge].tolist(),
            "cap_knot_index_zero_based_by_time": q_index[:, edge].tolist(),
            "cap_knot_pressure_pa_by_time": p_cap[:, edge].tolist(),
            "ht_minus_avg_at_cap_m_by_time": ht_minus_avg_q[:, edge].tolist(),
            "ht_minus_avg_at_next_knot_m_by_time": ht_minus_avg_next[:, edge].tolist(),
            "pressure_only_eligible_by_time": pressure_domain[:, edge].tolist(),
            "strict_ht_eligible_by_time": strict_ht_domain[:, edge].tolist(),
            "brackets_0_10m_by_time": brackets_10m[:, edge].tolist(),
        }

    report = {
        "status": "DIAGNOSTIC_DOMAIN_INVENTORY",
        "selection_uses_flux_output": False,
        "selection_inputs": [
            "arrays.npz:p10",
            "prepared.bin:PS,p,HT,edges,incidence,lat,lon,terrain,U3,V3",
        ],
        "selection_excludes": ["covered", "lower", "missing", "top", "known", "residual"],
        "times": np.asarray(case["times"]).tolist(),
        "time_labels": list(TIME_LABELS),
        "dimensions": {"nodes": nn, "regular_knots": int(pressure.size), "edges": ne, "triangles": nt},
        "pressure_knots_pa": pressure.tolist(),
        "p_top_pa": float(pressure[-1]),
        "domain_definition": (
            "For every endpoint, p_top <= p10 <= largest existing regular p with "
            "p <= min(endpoint PS), and p10 < endpoint PS. No underground or synthetic knot is used."
        ),
        "counts": counts,
        "selected_pressure_only_13_internal": selected_record(selected_pressure, "pressure_only_lowest_internal_13"),
        "selected_strict_ht_13_internal": selected_record(selected_strict, "strict_ht_lowest_internal_13"),
        "selected_preferred_13_internal": selected_record(
            selected_preferred,
            "strict_ht_lowest_internal_13_with_both_0_10m_bracket_when_available",
        ),
        "selection_fallback_to_lowest_strict": selection_fallback,
        "frame_chart_context": {
            "raw_wind_fields": "LW3 U3/V3 values as supplied in the prepared stream",
            "chart_conversion_owner": "PR40 Fortran driver; this Python inventory stores raw source winds only",
            "wind_frame_status": "CONDITIONAL_GRID_RELATIVE_SOURCE_CONTRACT; LW3 frame metadata and historical executable identity were not independently revalidated",
            "rotation": "u_east=cos(theta)*u_grid+sin(theta)*v_grid; v_north=-sin(theta)*u_grid+cos(theta)*v_grid",
            "theta": "theta=cone*(longitude-lambda0)",
            "chart": "x=R*cos(phi0)*(lambda-lambda0); y=R*(sin(phi)-sin(phi0))/cos(phi0)",
            "chart_wind": "U=cos(phi0)/cos(phi)*u_east; V=cos(phi)/cos(phi0)*v_north",
            "parameters_header": np.asarray(case["parameters"]).tolist(),
            "phi0_degrees": float(np.rad2deg(np.asarray(case["parameters"])[0])),
            "lambda0_degrees": float(np.rad2deg(np.asarray(case["parameters"])[1])),
            "radius_m": float(np.asarray(case["parameters"])[2]),
            "cone": float(np.asarray(case["parameters"])[3]),
        },
        "input_sha256": {"prepared.bin": sha256(prepared_path), "arrays.npz": sha256(arrays_path)},
        "source_report": str(arrays_path.with_name("report.json")),
    }

    payload = {
        "pressure_domain": pressure_domain,
        "strict_ht_domain": strict_ht_domain,
        "internal": internal,
        "brackets_10m": brackets_10m,
        "min_endpoint_ps_pa": min_endpoint_ps,
        "p_cap_pa": p_cap,
        "cap_knot_index": q_index,
        "endpoint_ps_pa": endpoint_ps,
        "endpoint_p10_pa": endpoint_p10,
        "ht_minus_avg_at_cap_m": ht_minus_avg_q,
        "ht_minus_avg_at_next_knot_m": ht_minus_avg_next,
        "pressure_knots_pa": pressure,
        "selected_edge_ids_zero_based": selected_ids,
        "selected_edge_ids_fortran": selected_ids + 1,
        "selected_node_ids_zero_based": selected_nodes,
        "selected_node_latitude_rad": np.asarray(case["lat"])[selected_nodes],
        "selected_node_longitude_rad": np.asarray(case["lon"])[selected_nodes],
        "selected_node_chart_xy_m": chart_xy[selected_nodes],
        "selected_node_terrain_m": np.asarray(case["terrain"])[selected_nodes],
        "selected_cap_knot_index": selected_q,
        "selected_endpoint_ps_pa": endpoint_ps[:, selected_ids],
        "selected_endpoint_p10_pa": endpoint_p10[:, selected_ids],
        **winds,
    }
    return report, payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arrays", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report, payload = audit_domain(args.arrays.resolve(), args.prepared.resolve())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "domain.json"
    npz_path = args.output_dir / "domain.npz"
    np.savez_compressed(npz_path, **payload)
    report["artifact_sha256"] = {npz_path.name: sha256(npz_path)}
    json_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], indent=2))
    print(json.dumps({key: report[key]["edge_index_zero_based"] for key in (
        "selected_pressure_only_13_internal", "selected_strict_ht_13_internal", "selected_preferred_13_internal"
    )}, indent=2))


if __name__ == "__main__":
    main()
