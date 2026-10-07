#!/usr/bin/env python3
"""Decode focused QR/NR records from the PR68 same-call KDM6 observer."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import stat
from pathlib import Path
from typing import Any

import numpy as np

from native_kdm6_trace import read_dump
from pr68_prepare_rain_observer import instrument


MAGIC = "PR68R001"
REAL_FIELDS = (
    "qr", "nr", "qc", "nc", "ni", "nccn", "temperature_k",
    "qcrmin", "nrmin", "dtcld", "qr_trial", "nr_trial", "limiter_value",
    "limiter_source", "praut", "pracw", "prevp", "piacr", "pgacr",
    "psacr", "pmulrs", "pmulrg", "paacw", "pseml", "pgeml", "nraut",
    "nrcol", "niacr", "nraci", "nsacr", "ngacr", "nseml", "ngeml",
)
INT_FIELDS = ("event", "i", "j", "k", "loop", "mstep", "pending")
EVENT_NAMES = {
    0: "entry_after_nonnegative_clamp",
    1: "after_rain_sedimentation",
    2: "after_ice_sedimentation",
    3: "after_freezing_transfer",
    4: "cold_process_rates_before_limit",
    5: "cold_process_rates_after_limit",
    6: "after_cold_process_update",
    7: "cold_full_evap_number_reclassification",
    8: "warm_process_rates_before_limit",
    9: "warm_process_rates_after_limit",
    10: "after_warm_process_update",
    11: "warm_full_evap_number_reclassification",
    12: "after_rain_to_cloud_classification",
    13: "after_final_qr_nr_threshold",
    14: "after_rain_slope_number_repair",
    15: "terminal_kdm62d_return",
}
COLD_RATE_FIELDS = (
    "praut", "pracw", "prevp", "piacr", "pgacr", "psacr", "pmulrs",
    "pmulrg", "nraut", "nrcol", "niacr", "nraci", "nsacr", "ngacr",
)
WARM_RATE_FIELDS = (
    "praut", "pracw", "prevp", "paacw", "pseml", "pgeml", "nraut",
    "nrcol", "nseml", "ngeml",
)


class TraceError(ValueError):
    """The focused observer capture is malformed or incomplete."""


def _f32(value: float) -> float:
    return float(np.float32(value))


def _sum_f32(values: tuple[float, ...]) -> float:
    total = _f32(values[0])
    for value in values[1:]:
        total = _f32(total + _f32(value))
    return total


def _trial(record: dict[str, Any], cold: bool) -> tuple[float, float]:
    if cold:
        qr_rates = ("praut", "pracw", "prevp", "piacr", "pgacr", "psacr", "pmulrs", "pmulrg")
        qr_signs = (1, 1, 1, -1, -1, -1, -1, -1)
        nr_rates = ("nraut", "nrcol", "niacr", "nraci", "nsacr", "ngacr")
        nr_signs = (1, -1, -1, -1, -1, -1)
    else:
        qr_rates = ("praut", "pracw", "prevp", "paacw", "paacw", "pseml", "pgeml")
        qr_signs = (1, 1, 1, 1, 1, -1, -1)
        nr_rates = ("nraut", "nrcol", "nseml", "ngeml")
        nr_signs = (1, -1, 1, 1)
    qr_rate = _sum_f32(tuple(record[name] * sign for name, sign in zip(qr_rates, qr_signs, strict=True)))
    nr_rate = _sum_f32(tuple(record[name] * sign for name, sign in zip(nr_rates, nr_signs, strict=True)))
    return (_f32(_f32(record["qr"]) + _f32(qr_rate * _f32(record["dtcld"]))),
            _f32(_f32(record["nr"]) + _f32(nr_rate * _f32(record["dtcld"]))))


def _limiter_source(record: dict[str, Any], cold: bool) -> float:
    terms = ((-record["nraut"], record["nraci"], record["nrcol"],
              record["niacr"], record["nsacr"], record["ngacr"]) if cold else
             (-record["nraut"], record["nrcol"], -record["nseml"], -record["ngeml"]))
    return _f32(_sum_f32(terms) * _f32(record["dtcld"]))


def _same_f32(actual: float, expected: float) -> bool:
    return np.float32(actual).tobytes() == np.float32(expected).tobytes()


def _check_file_hash(path: Path, expected: str, label: str) -> None:
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected.lower()):
        raise TraceError(f"{label} is not a SHA256 hex digest")
    try:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError as exc:
        raise TraceError(f"{label} file is missing: {path}") from exc
    if actual != expected:
        raise TraceError(f"{label} file hash does not match the recorded identity: {path}")


def failure_coordinates(mask: np.ndarray, bounds: dict[str, int]) -> list[list[int]]:
    """Map a J,K,I active-tile mask into global Fortran I,J,K coordinates."""
    expected_shape = (bounds["jte"] - bounds["jts"] + 1,
                      bounds["kte"] - bounds["kts"] + 1,
                      bounds["ite"] - bounds["its"] + 1)
    if mask.shape != expected_shape or mask.ndim != 3:
        raise TraceError(f"failure mask shape {mask.shape} does not match active bounds {expected_shape}")
    j_index, k_index, i_index = np.nonzero(mask)
    coords = [[int(bounds["its"] + i), int(bounds["jts"] + j), int(bounds["kts"] + k)]
              for j, k, i in zip(j_index, k_index, i_index, strict=True)]
    return sorted(coords, key=lambda xyz: (xyz[1], xyz[0], xyz[2]))


def _receipt_hash(path: Path, receipt_path: Path) -> tuple[dict[str, Any], str]:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (receipt.get("returncode") != 0 or receipt.get("input_integrity") != "PASS" or
            receipt.get("output_isolation") != "PASS"):
        raise TraceError("run receipt does not report successful isolated execution")
    run_root = Path(receipt["run_root"]).resolve()
    try:
        relative = path.resolve().relative_to(run_root).as_posix()
    except ValueError as exc:
        raise TraceError(f"receipt-bound file is outside its run root: {path}") from exc
    matches = [row for row in receipt.get("outputs", []) if row.get("path") == relative]
    try:
        file_stat = path.lstat()
    except FileNotFoundError as exc:
        raise TraceError(f"receipt-bound file is missing: {path}") from exc
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if (len(matches) != 1 or not stat.S_ISREG(file_stat.st_mode) or path.is_symlink() or
            file_stat.st_nlink != 1 or matches[0].get("nlink") != 1 or
            digest != matches[0].get("sha256")):
        raise TraceError(f"file is not uniquely hash-bound by the run receipt: {relative}")
    return receipt, digest


def derive_targets(pre_path: Path, post_path: Path, receipt_path: Path) -> dict[str, Any]:
    """Derive focused source coordinates from the receipt-bound PR67 post-state."""
    _, pre_hash = _receipt_hash(pre_path, receipt_path)
    receipt, post_hash = _receipt_hash(post_path, receipt_path)
    pre, post = read_dump(pre_path), read_dump(post_path)
    if (pre["stage"] != 1 or post["stage"] != 2 or pre["itimestep"] != 1 or
            post["itimestep"] != 1 or pre["bounds"] != post["bounds"]):
        raise TraceError("baseline public KDM6 pre/post headers do not match first call")
    qr, nr = post["fields"]["QR"], post["fields"]["NR"]
    if not np.isfinite(qr).all() or not np.isfinite(nr).all():
        raise TraceError("baseline QR/NR contains a nonfinite value")
    mask = (qr > 0.0) & (nr == 0.0)
    coords = failure_coordinates(mask, post["bounds"])
    if len(coords) != 25:
        raise TraceError(f"expected exactly 25 first-call QR-positive/NR-zero cells, found {len(coords)}")
    return {
        "schema": "pr68_kdm6_failure_targets_v1",
        "baseline_run_root": receipt["run_root"],
        "baseline_receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        "baseline_pre_sha256": pre_hash,
        "baseline_post_sha256": post_hash,
        "itimestep": post["itimestep"],
        "bounds": post["bounds"],
        "array_axis_order": "J,K,I",
        "coordinate_order": "global Fortran I,J,K",
        "mask_sha256_jki": hashlib.sha256(np.ascontiguousarray(mask).tobytes()).hexdigest(),
        "coordinates_ijk": coords,
        "count": len(coords),
        "limitation": "The coordinates are derived from the KDM6 post-call mask; PR67 separately reports that the same 25 cells coincide with the active nonfinite reflectivity mask.",
    }


def read_capture(path: Path) -> list[dict[str, Any]]:
    """Read the whitespace-delimited Fortran event stream and validate it."""
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        parts = raw_line.split()
        if not parts:
            continue
        if parts[0] != MAGIC or len(parts) != 1 + len(INT_FIELDS) + len(REAL_FIELDS):
            raise TraceError(f"malformed PR68 record at line {line_number}")
        try:
            values = [int(value) for value in parts[1:1 + len(INT_FIELDS)]]
            floats = [float(value.replace("D", "E")) for value in parts[1 + len(INT_FIELDS):]]
        except ValueError as exc:
            raise TraceError(f"invalid numeric value at line {line_number}") from exc
        record = dict(zip(INT_FIELDS, values))
        record.update(zip(REAL_FIELDS, floats))
        if record["event"] not in EVENT_NAMES or record["pending"] not in (0, 1):
            raise TraceError(f"unknown event or pending flag at line {line_number}")
        if not all(math.isfinite(record[name]) for name in REAL_FIELDS):
            raise TraceError(f"nonfinite state or tendency at line {line_number}")
        if min(record["i"], record["j"], record["k"]) < 1 or min(record["loop"], record["mstep"]) < 0:
            raise TraceError(f"out-of-domain coordinate or negative loop at line {line_number}")
        if record["dtcld"] <= 0.0:
            raise TraceError(f"invalid cloud timestep at line {line_number}")
        record["event_name"] = EVENT_NAMES[record["event"]]
        record["qr_positive_nr_zero"] = record["qr"] > 0.0 and record["nr"] == 0.0
        if record["event"] in (4, 5):
            record["supported_rate_fields"] = list(COLD_RATE_FIELDS)
        elif record["event"] in (8, 9):
            record["supported_rate_fields"] = list(WARM_RATE_FIELDS)
        else:
            record["supported_rate_fields"] = []
        records.append(record)
    if not records:
        raise TraceError("observer capture is empty")
    return records


def _receipt_output(summary_path: Path, run_summary: dict[str, Any], capture_path: Path) -> None:
    run_root = Path(run_summary["run_root"]).resolve()
    try:
        relative = capture_path.resolve().relative_to(run_root).as_posix()
    except ValueError as exc:
        raise TraceError("observer capture is outside its run root") from exc
    matches = [row for row in run_summary.get("outputs", []) if row.get("path") == relative]
    capture_stat = capture_path.lstat()
    digest = hashlib.sha256(capture_path.read_bytes()).hexdigest()
    if (len(matches) != 1 or matches[0].get("sha256") != digest or
            matches[0].get("nlink") != 1 or capture_stat.st_nlink != 1 or
            not stat.S_ISREG(capture_stat.st_mode) or capture_path.is_symlink()):
        raise TraceError(f"capture is not uniquely bound by run summary {summary_path}")


def _run_executable_hash(summary: dict[str, Any], summary_path: Path) -> str:
    declared = summary.get("executable_sha256")
    if isinstance(declared, str) and len(declared) == 64:
        return declared
    nested = summary.get("executable")
    if isinstance(nested, dict):
        source = Path(nested.get("source", ""))
        before, after = nested.get("sha256_before"), nested.get("sha256_after")
        try:
            metadata = source.lstat()
        except FileNotFoundError as exc:
            raise TraceError(f"run executable source is missing: {source}") from exc
        if (not source.is_absolute() or source.is_symlink() or not stat.S_ISREG(metadata.st_mode) or
                metadata.st_nlink != nested.get("nlink") or metadata.st_nlink != 1 or
                before != after or not isinstance(before, str) or len(before) != 64 or
                hashlib.sha256(source.read_bytes()).hexdigest() != before):
            raise TraceError(f"run executable source differs from its nested summary identity: {source}")
        return before
    run_root = Path(summary["run_root"]).resolve()
    matches = []
    for row in summary.get("inputs", []):
        try:
            candidate = Path(row["path"]).resolve()
        except (KeyError, OSError):
            continue
        if candidate == (run_root / "wrf.exe").resolve():
            if row.get("sha256_before") != row.get("sha256_after"):
                raise TraceError(f"executable changed during run {summary_path}")
            matches.append(row.get("sha256_before"))
    if len(matches) != 1 or not isinstance(matches[0], str):
        raise TraceError(f"run summary does not uniquely bind its executable: {summary_path}")
    return matches[0]


def audit_capture(
    capture_path: Path,
    target_manifest_path: Path,
    observer_summary_path: Path,
    control_summary_path: Path,
    *,
    selected_source_sha256: str,
    observer_source_sha256: str,
    control_object_sha256: str,
    observer_object_sha256: str,
    control_executable_sha256: str,
    observer_executable_sha256: str,
    selected_source_path: Path | None = None,
    observer_source_path: Path | None = None,
    control_object_path: Path | None = None,
    observer_object_path: Path | None = None,
    control_executable_path: Path | None = None,
    observer_executable_path: Path | None = None,
) -> dict[str, Any]:
    """Require full target coverage, terminal records, and neutral matched runs."""
    targets = json.loads(target_manifest_path.read_text(encoding="utf-8"))
    if targets.get("schema") != "pr68_kdm6_failure_targets_v1" or targets.get("count") != 25:
        raise TraceError("target manifest is not the expected 25-cell PR67 failure set")
    target_coords = {tuple(row) for row in targets.get("coordinates_ijk", [])}
    if len(target_coords) != 25:
        raise TraceError("target manifest does not contain 25 distinct coordinates")
    observer = json.loads(observer_summary_path.read_text(encoding="utf-8"))
    control = json.loads(control_summary_path.read_text(encoding="utf-8"))
    hashes = (selected_source_sha256, observer_source_sha256, control_object_sha256,
              observer_object_sha256, control_executable_sha256, observer_executable_sha256)
    if any(len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()) for value in hashes):
        raise TraceError("a source, object, or executable identity is not a SHA256 hex digest")
    if (observer.get("returncode") != 0 or control.get("returncode") != 0 or
            observer.get("input_integrity") != "PASS" or control.get("input_integrity") != "PASS" or
            observer.get("output_isolation") != "PASS" or control.get("output_isolation") != "PASS"):
        raise TraceError("matched native run summaries are incomplete or failed isolation")
    if (_run_executable_hash(observer, observer_summary_path) != observer_executable_sha256 or
            _run_executable_hash(control, control_summary_path) != control_executable_sha256):
        raise TraceError("native run executable identity does not match the declared build identity")
    identity_paths = (selected_source_path, observer_source_path, control_object_path,
                      observer_object_path, control_executable_path, observer_executable_path)
    identity_hashes = (selected_source_sha256, observer_source_sha256, control_object_sha256,
                       observer_object_sha256, control_executable_sha256, observer_executable_sha256)
    if any(path is not None for path in identity_paths):
        if any(path is None for path in identity_paths):
            raise TraceError("source/object/executable identity binding requires all six artifact paths")
        for path, digest, label in zip(identity_paths, identity_hashes,
                                       ("selected source", "observer source", "control object",
                                        "observer object", "control executable", "observer executable"),
                                       strict=True):
            _check_file_hash(path, digest, label)
        expected_source = instrument(
            selected_source_path.read_text(encoding="utf-8"), selected_source_sha256,
            [tuple(row) for row in targets["coordinates_ijk"]],
        )
        if observer_source_path.read_text(encoding="utf-8") != expected_source:
            raise TraceError("observer source is not the generated derivative of selected source and target manifest")
    _receipt_output(observer_summary_path, observer, capture_path)
    for name in ("kdm6_first_call_pre.raw", "kdm6_first_call_post.raw"):
        obs = next((r for r in observer.get("outputs", []) if r.get("path") == name), None)
        ctl = next((r for r in control.get("outputs", []) if r.get("path") == name), None)
        if not obs or not ctl or obs.get("sha256") != ctl.get("sha256") or obs.get("nlink") != 1 or ctl.get("nlink") != 1:
            raise TraceError(f"observer changed or lost matched native output {name}")
        _receipt_output(observer_summary_path, observer, Path(observer["run_root"]) / name)
        _receipt_output(control_summary_path, control, Path(control["run_root"]) / name)
    records = read_capture(capture_path)
    by_cell: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    for record in records:
        key = (record["i"], record["j"], record["k"])
        if key not in target_coords:
            raise TraceError(f"observer emitted out-of-manifest coordinate {key}")
        by_cell.setdefault(key, []).append(record)
    if set(by_cell) != target_coords:
        raise TraceError("observer capture does not cover the exact target coordinate set")
    details = []
    for coords, samples in sorted(by_cell.items(), key=lambda row: (row[0][1], row[0][0], row[0][2])):
        events = [sample["event"] for sample in samples]
        if len(events) != len(set(events)):
            raise TraceError(f"duplicate source checkpoint for {coords}: {events}")
        if not events or events[0] != 0 or events[-1] != 15:
            raise TraceError(f"missing call endpoint for {coords}: {events}")
        indexed = {sample["event"]: sample for sample in samples}
        branch_event = 4 if 4 in indexed else 8 if 8 in indexed else None
        if branch_event is None:
            raise TraceError(f"missing limiter branch checkpoint for {coords}")
        cold = indexed[branch_event]["temperature_k"] <= 273.15
        expected_events = ((0, 1, 2, 3, 4, 5, 6, 7, 12, 13, 14, 15) if cold else
                           (0, 1, 2, 3, 8, 9, 10, 11, 12, 13, 14, 15))
        if tuple(events) != expected_events:
            raise TraceError(f"checkpoint labels do not match source temperature branch for {coords}: {events}")
        bad_index = next((idx for idx, row in enumerate(samples) if row["qr_positive_nr_zero"]), None)
        details.append({
            "i_j_k": list(coords),
            "loop_mstep_start": [samples[0]["loop"], samples[0]["mstep"]],
            "loop_mstep_terminal": [samples[-1]["loop"], samples[-1]["mstep"]],
            "event_count": len(events),
            "events": [EVENT_NAMES[event] for event in events],
            "first_qr_positive_nr_zero": EVENT_NAMES[samples[bad_index]["event"]] if bad_index is not None else None,
            "first_bad_record": samples[bad_index] if bad_index is not None else None,
        })
    first_bad = [row for row in details if row["first_qr_positive_nr_zero"] is not None]
    if len(first_bad) != 25 or any(row["first_qr_positive_nr_zero"] not in (
            "after_cold_process_update", "after_warm_process_update") for row in first_bad):
        raise TraceError("the expected all-cell process-update QR-positive/NR-zero transition was not observed")
    accepted_trials = []
    for row in details:
        indexed = {sample["event"]: sample for sample in by_cell[tuple(row["i_j_k"])]}
        cold = 4 in indexed
        before_event, after_event, update_event = (4, 5, 6) if cold else (8, 9, 10)
        before, after, updated = indexed[before_event], indexed[after_event], indexed[update_event]
        if not (_same_f32(before["qr_trial"], _trial(before, cold)[0]) and
                _same_f32(before["nr_trial"], _trial(before, cold)[1]) and
                _same_f32(after["qr_trial"], _trial(after, cold)[0]) and
                _same_f32(after["nr_trial"], _trial(after, cold)[1])):
            raise TraceError(f"captured trial does not reconstruct from source rates for {row['i_j_k']}")
        expected_value = _f32(max(_f32(before["nrmin"]), _f32(before["nr"])))
        expected_source = _limiter_source(before, cold)
        if not (_same_f32(before["limiter_value"], expected_value) and
                _same_f32(before["limiter_source"], expected_source) and
                before["limiter_source"] > before["limiter_value"] and
                _same_f32(after["limiter_source"], before["limiter_source"]) and
                _same_f32(after["limiter_value"], before["limiter_value"])):
            raise TraceError(f"captured source, max reserve, or limiter gate differs from source arithmetic for {row['i_j_k']}")
        number_fields = ("nraut", "nraci", "nrcol", "niacr", "nsacr", "ngacr") if cold else (
            "nraut", "nrcol", "nseml", "ngeml")
        factor = _f32(_f32(before["limiter_value"]) / _f32(before["limiter_source"]))
        if not all(_same_f32(after[name], _f32(before[name] * factor)) for name in number_fields):
            raise TraceError(f"captured number tendency does not match source limiter factor for {row['i_j_k']}")
        if not (_same_f32(updated["qr"], max(after["qr_trial"], 0.0)) and
                _same_f32(updated["nr"], max(after["nr_trial"], 0.0))):
            raise TraceError(f"native max update does not match post-limit trial for {row['i_j_k']}")
        accepted_trials.append({"nr_trial": after["nr_trial"], "nrmin": after["nrmin"]})
        number_source_fields = ("nraut",) if cold else ("nraut", "nseml", "ngeml")
        number_sink_fields = ("nrcol", "niacr", "nraci", "nsacr", "ngacr") if cold else ("nrcol",)
        qr_mass_source_terms = ("praut", "pracw", "prevp") if cold else (
            "praut", "pracw", "prevp", "paacw", "paacw")
        qr_mass_sink_terms = ("piacr", "pgacr", "psacr", "pmulrs", "pmulrg") if cold else (
            "pseml", "pgeml")
        row["process_limiter"] = {
            "branch": "cold" if cold else "warm",
            "branch_temperature_k": before["temperature_k"],
            "number_state_and_trial_units": "# m^-3 (source-required internal convention)",
            "number_tendency_units": "# m^-3 s^-1 (source-required internal convention)",
            "dtcld": after["dtcld"],
            "pre_limit": {
                "qr": before["qr"], "nr": before["nr"],
                "qr_trial": before["qr_trial"], "nr_trial": before["nr_trial"],
                "limiter_value": before["limiter_value"],
                "limiter_source": before["limiter_source"],
            },
            "post_limit_rates": {
                field: after[field] for field in
                set((*number_source_fields, *number_sink_fields,
                     *qr_mass_source_terms, *qr_mass_sink_terms))
            },
            "post_limit_number_source_terms": list(number_source_fields),
            "post_limit_number_source_rate": sum(after[field] for field in number_source_fields),
            "post_limit_number_sink_rates": {
                field: after[field] for field in number_sink_fields
            },
            "post_limit_number_sink_terms": list(number_sink_fields),
            "post_limit_number_sink_total": sum(after[field] for field in number_sink_fields),
            "post_limit_number_net_rate": sum(after[field] for field in number_source_fields) -
                                          sum(after[field] for field in number_sink_fields),
            "post_limit_qr_mass_source_terms": list(qr_mass_source_terms),
            "post_limit_qr_mass_sink_terms": list(qr_mass_sink_terms),
            "post_limit_qr_mass_rate": sum(after[field] for field in qr_mass_source_terms) -
                                       sum(after[field] for field in qr_mass_sink_terms),
            "post_limit_trial": {
                "qr": after["qr_trial"], "nr": after["nr_trial"],
            },
            "after_update": {"qr": updated["qr"], "nr": updated["nr"]},
            "later_checkpoints": {
                EVENT_NAMES[event]: {"qr": indexed[event]["qr"], "nr": indexed[event]["nr"]}
                for event in ((6, 7, 12, 13, 14, 15) if cold else (10, 11, 12, 13, 14, 15))
            },
        }
    cold_count = sum(row["process_limiter"]["branch"] == "cold" for row in details)
    warm_count = len(details) - cold_count
    return {
        "schema": "pr68_kdm6_rain_origin_audit_v1",
        "selected_generated_source_sha256": selected_source_sha256,
        "observer_source_sha256": observer_source_sha256,
        "control_object_sha256": control_object_sha256,
        "observer_object_sha256": observer_object_sha256,
        "control_executable_sha256": control_executable_sha256,
        "observer_executable_sha256": observer_executable_sha256,
        "target_manifest_sha256": hashlib.sha256(target_manifest_path.read_bytes()).hexdigest(),
        "observer_capture_sha256": hashlib.sha256(capture_path.read_bytes()).hexdigest(),
        "observer_run_summary_sha256": hashlib.sha256(observer_summary_path.read_bytes()).hexdigest(),
        "control_run_summary_sha256": hashlib.sha256(control_summary_path.read_bytes()).hexdigest(),
        "pre_post_state_neutrality": {
            name: next(row["sha256"] for row in observer["outputs"] if row["path"] == name)
            for name in ("kdm6_first_call_pre.raw", "kdm6_first_call_post.raw")
        },
        "target_count": len(details),
        "number_unit_basis": {
            "internal_kdm6_state_and_trial": "# m^-3, inferred from the selected KDM6 process and PSD source formulas",
            "internal_kdm6_tendencies": "# m^-3 s^-1",
            "selected_kdm6_source_basis": "nraut=(3.5e9)*den*praut and n0r=nrs/(rslope*rslopemu*g1pmr); the number tendency is multiplied by dtcld before updating nrs",
            "public_host_qnrain": "# kg^-1 per Registry/Registry.EM_COMMON QNRAIN definition",
            "host_to_internal_adapter": "partial: the selected wrapper copies NR into NRS directly; the runtime host conversion path into this wrapper is not source-bound by this observer capture",
        },
        "first_bad_event_counts": {
            EVENT_NAMES[event]: sum(row["first_qr_positive_nr_zero"] == EVENT_NAMES[event] for row in first_bad)
            for event in (6, 10)
        },
        "branch_counts": {"cold": cold_count, "warm": warm_count},
        "accepted_number_trial_vs_reserve": {
            "negative_count": sum(item["nr_trial"] < 0.0 for item in accepted_trials),
            "zero_count": sum(item["nr_trial"] == 0.0 for item in accepted_trials),
            "positive_count": sum(item["nr_trial"] > 0.0 for item in accepted_trials),
            "below_nrmin_count": sum(item["nr_trial"] < item["nrmin"] for item in accepted_trials),
            "at_or_above_nrmin_count": sum(item["nr_trial"] >= item["nrmin"] for item in accepted_trials),
            "minimum_nr_trial": min(item["nr_trial"] for item in accepted_trials),
            "maximum_nr_trial": max(item["nr_trial"] for item in accepted_trials),
            "minimum_nrmin": min(item["nrmin"] for item in accepted_trials),
            "maximum_nrmin": max(item["nrmin"] for item in accepted_trials),
        },
        "cells": details,
        "cause": "The active temperature branch applies its aggregate rain-number limiter to the available NR. The reconstructed post-limit number trial is nonpositive while the independent QR mass trial remains positive; the source max(...,0) updates therefore yield QR-positive/NR-zero. The branch-specific donor and sink terms are reported without assigning the aggregate limiter to one constituent process. Subsequent transfer, threshold, slope-repair, and terminal checkpoints record whether that pair changes later in the call.",
        "interpretation_limit": "This establishes the source-path origin and captured native rate arithmetic for the selected 25 cells. It does not establish that QR-positive/NR-zero is physically admissible or prescribe a conservative repair.",
    }


def summarize(path: Path) -> dict[str, Any]:
    records = read_capture(path)
    by_cell: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    for record in records:
        by_cell.setdefault((record["i"], record["j"], record["k"]), []).append(record)
    cells = []
    for coords, samples in sorted(by_cell.items(), key=lambda item: (item[0][1], item[0][0], item[0][2])):
        bad = [sample for sample in samples if sample["qr_positive_nr_zero"]]
        cells.append({
            "i_j_k": list(coords),
            "event_count": len(samples),
            "first_qr_positive_nr_zero": bad[0]["event_name"] if bad else None,
            "events": samples,
        })
    return {
        "schema": "pr68_kdm6_rain_process_trace_v1",
        "source_observer_capture": str(path),
        "record_count": len(records),
        "cell_count": len(cells),
        "events_by_name": {
            EVENT_NAMES[event]: sum(record["event"] == event for record in records)
            for event in sorted(EVENT_NAMES)
        },
        "cells": cells,
        "interpretation_limit": "The observer records native states and named process tendencies at source checkpoints. A difference between checkpoints alone is not attributed to a process unless the recorded source tendency or transfer identifies it.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--audit-targets", type=Path)
    parser.add_argument("--observer-summary", type=Path)
    parser.add_argument("--control-summary", type=Path)
    parser.add_argument("--selected-source-sha256")
    parser.add_argument("--observer-source-sha256")
    parser.add_argument("--control-object-sha256")
    parser.add_argument("--observer-object-sha256")
    parser.add_argument("--control-executable-sha256")
    parser.add_argument("--observer-executable-sha256")
    parser.add_argument("--selected-source", type=Path)
    parser.add_argument("--observer-source", type=Path)
    parser.add_argument("--control-object", type=Path)
    parser.add_argument("--observer-object", type=Path)
    parser.add_argument("--control-executable", type=Path)
    parser.add_argument("--observer-executable", type=Path)
    args = parser.parse_args()
    if args.audit_targets:
        required = (args.observer_summary, args.control_summary, args.selected_source_sha256,
                    args.observer_source_sha256, args.control_object_sha256,
                    args.observer_object_sha256, args.control_executable_sha256,
                    args.observer_executable_sha256, args.selected_source,
                    args.observer_source, args.control_object, args.observer_object,
                    args.control_executable, args.observer_executable)
        if any(value is None for value in required):
            parser.error("audit mode requires run summaries and all source/object/executable hashes")
        report = audit_capture(
            args.capture, args.audit_targets, args.observer_summary, args.control_summary,
            selected_source_sha256=args.selected_source_sha256,
            observer_source_sha256=args.observer_source_sha256,
            control_object_sha256=args.control_object_sha256,
            observer_object_sha256=args.observer_object_sha256,
            control_executable_sha256=args.control_executable_sha256,
            observer_executable_sha256=args.observer_executable_sha256,
            selected_source_path=args.selected_source,
            observer_source_path=args.observer_source,
            control_object_path=args.control_object,
            observer_object_path=args.observer_object,
            control_executable_path=args.control_executable,
            observer_executable_path=args.observer_executable,
        )
    else:
        report = summarize(args.capture)
    rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
