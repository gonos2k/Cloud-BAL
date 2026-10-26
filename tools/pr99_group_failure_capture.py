#!/usr/bin/env python3
"""Validate and classify bounded PR99 grouped-candidate failure events."""
from __future__ import annotations

import argparse
import json
import re
import shlex
import struct
from pathlib import Path
from typing import Any


HEX_COUNTS = {
    "HEX64_CANDIDATE": 2,
    "HEX32_STORED": 2,
    "HEX32_CARRIERS_DT": 4,
    "HEX32_BASE": 2,
    "HEX64_SOURCE_RATE": 2,
    "HEX64_TRANSPORT_RATE": 2,
    "HEX64_MASS_BOUNDS": 2,
    "HEX64_NUMBER_BOUNDS": 2,
    "HEX64_INACTIVE_MASS_LIMIT": 1,
}
TEXT_ROWS = {
    "R64_CANDIDATE": 2,
    "R32_STORED": 2,
    "R32_CARRIERS": 4,
    "R32_BASE": 2,
    "R64_SOURCE_RATE": 2,
    "R64_TRANSPORT_RATE": 2,
    "R64_MASS_BOUNDS": 2,
    "R64_NUMBER_BOUNDS": 2,
    "R64_INACTIVE_MASS_LIMIT": 1,
}
BOOLEAN_VALUES = {"T": True, ".TRUE.": True, "F": False, ".FALSE.": False}
FAILURE_MARKER = "PR99_GROUP_FAILURE_V1"
POST_RETRY_MARKER = "PR99_GROUP_POST_RETRY_V1"


def _expand_wire_marker(fields: list[str], line_number: int) -> tuple[list[str], int] | None:
    """Split Intel list-directed marker concatenation and return expected row width."""
    token = fields[0]
    if token.startswith(FAILURE_MARKER):
        suffix = token[len(FAILURE_MARKER):]
        if suffix:
            match = re.fullmatch(r"(.+)(SOURCE_FIRST|BASELINE)", suffix)
            if match is None:
                raise ValueError(f"malformed concatenated PR99 failure marker at line {line_number}")
            fields = [FAILURE_MARKER, match.group(1), match.group(2), *fields[1:]]
        return fields, 13
    if token.startswith(POST_RETRY_MARKER):
        suffix = token[len(POST_RETRY_MARKER):]
        if suffix:
            fields = [POST_RETRY_MARKER, suffix, *fields[1:]]
        return fields, 8
    return None


def _read_records(path: Path) -> list[tuple[int, list[str]]]:
    """Normalize wrapped list-directed PR99 headers into logical rows."""
    physical = path.read_text().splitlines()
    records: list[tuple[int, list[str]]] = []
    line_index = 0
    while line_index < len(physical):
        line_number = line_index + 1
        fields = shlex.split(physical[line_index])
        line_index += 1
        if not fields:
            continue
        expanded = _expand_wire_marker(fields, line_number)
        if expanded is None:
            records.append((line_number, fields))
            continue
        fields, expected_count = expanded
        marker = fields[0]
        while len(fields) < expected_count:
            if line_index >= len(physical):
                raise ValueError(f"truncated PR99 header continuation at line {line_number}")
            continuation_number = line_index + 1
            continuation = shlex.split(physical[line_index])
            line_index += 1
            if not continuation:
                continue
            # Only integer columns followed by one boolean can continue these
            # numeric list-directed headers. A marker or data row here is an
            # interleaved/truncated header, not another record to consume.
            bool_index = 12 if marker == FAILURE_MARKER else 7
            for token in continuation:
                next_index = len(fields)
                if next_index > bool_index:
                    raise ValueError(f"overlong PR99 header continuation at line {continuation_number}")
                if next_index == bool_index:
                    if token.upper() not in BOOLEAN_VALUES:
                        raise ValueError(f"malformed PR99 header continuation at line {continuation_number}")
                else:
                    try:
                        int(token)
                    except ValueError as error:
                        raise ValueError(
                            f"malformed PR99 header continuation at line {continuation_number}") from error
                fields.append(token)
                if len(fields) > expected_count:
                    raise ValueError(f"overlong PR99 header continuation at line {continuation_number}")
        records.append((line_number, fields))
    return records


def parse_bool(token: str, line_number: int) -> bool:
    try:
        return BOOLEAN_VALUES[token.upper()]
    except KeyError as error:
        raise ValueError(f"invalid boolean token at line {line_number}") from error


def exact_real64(token: str) -> float:
    return struct.unpack(">d", bytes.fromhex(token))[0]


def _parse_failure(fields: list[str], line_number: int) -> dict[str, Any]:
    if len(fields) != 13:
        raise ValueError(f"malformed PR99 failure header at line {line_number}")
    _, run_id, attempt, timestep, rk, cell, pair, i, j, k, predicate, stage, store_ok = fields
    attempt = attempt.strip()
    if store_ok.upper() not in BOOLEAN_VALUES:
        raise ValueError(f"invalid store status at line {line_number}")
    row = {"run_id": run_id, "attempt": attempt, "timestep": int(timestep),
            "rk": int(rk), "cell": int(cell), "pair": int(pair), "i": int(i), "j": int(j),
            "k": int(k), "group_predicate": int(predicate), "store_failure_stage": int(stage),
            "store_succeeded": parse_bool(store_ok, line_number), "hex": {}, "text": {},
            "options": {}}
    row["key"] = (run_id, row["timestep"], row["rk"], row["cell"], row["pair"], row["group_predicate"])
    return row


def parse_capture(path: Path, *, timestep: int = 32, rk: int | None = None) -> dict[str, Any]:
    """Parse a complete PR99 event sequence and bind each post-retry status."""
    if not isinstance(timestep, int) or isinstance(timestep, bool) or timestep < 1:
        raise ValueError("requested PR99 timestep must be a positive integer")
    if rk is not None and (not isinstance(rk, int) or isinstance(rk, bool) or rk not in (1, 2, 3)):
        raise ValueError("requested PR99 RK stage must be an integer from 1 through 3")
    events: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line_number, fields in _read_records(path):
        marker = fields[0]
        if marker == FAILURE_MARKER:
            if current is not None:
                events.append(current)
            current = _parse_failure(fields, line_number)
            continue
        if marker == POST_RETRY_MARKER:
            if len(fields) != 8:
                raise ValueError(f"malformed PR99 post-retry row at line {line_number}")
            _, run_id, event_timestep, event_rk, cell, pair, predicate, feasible = fields
            key = (run_id, int(event_timestep), int(event_rk), int(cell), int(pair), int(predicate))
            # The host emits this directly after fallback in the same
            # evaluate_joint_candidate call. Bind it to the one pending event;
            # the attempt label is carried by that event's pre-retry row.
            if current is None or current["key"] != key or "post_retry_feasible" in current:
                raise ValueError(f"unmatched, duplicate, or interleaved PR99 post-retry row at line {line_number}")
            current["post_retry_feasible"] = parse_bool(feasible, line_number)
            continue
        if current is None:
            raise ValueError(f"PR99 data row without an event at line {line_number}")
        if "post_retry_feasible" in current:
            raise ValueError(f"PR99 row follows post-graupel-mixture status at line {line_number}")
        if marker.startswith("HEX"):
            if marker in current["hex"] or len(fields) != HEX_COUNTS.get(marker, -1) + 1:
                raise ValueError(f"malformed or duplicate {marker} at line {line_number}")
            values = [value.upper() for value in fields[1:]]
            if any(not value or any(char not in "0123456789ABCDEF" for char in value)
                   for value in values):
                raise ValueError(f"invalid hexadecimal payload at line {line_number}")
            current["hex"][marker] = values
        elif marker.startswith("OPT_"):
            if len(fields) != 2 or marker in current["options"]:
                raise ValueError(f"malformed or duplicate {marker} at line {line_number}")
            current["options"][marker] = parse_bool(fields[1], line_number)
        elif marker == "CELLS_AND_PAIRS":
            if len(fields) != 3 or "group_shape" in current:
                raise ValueError(f"malformed group shape at line {line_number}")
            current["group_shape"] = [int(fields[1]), int(fields[2])]
        elif marker in TEXT_ROWS:
            if len(fields) != TEXT_ROWS[marker] + 1 or marker in current["text"]:
                raise ValueError(f"malformed or duplicate {marker} at line {line_number}")
            current["text"][marker] = fields[1:]
        else:
            raise ValueError(f"unknown PR99 row {marker!r} at line {line_number}")

    if current is not None:
        events.append(current)
    if not events:
        raise ValueError("capture contains no PR99 grouped failure events")
    required_options = {
        "OPT_joint_constrained_storage", "OPT_joint_quantum_absence",
        "OPT_normal_q_adjustment", "OPT_strict_mass_pair", "OPT_inactive_mass_pair",
        "OPT_inactive_q_quantum_pair", "OPT_bulk_volume_quantum_storage",
        "OPT_number_pair_bounds", "OPT_source_first_fallback",
    }
    for event in events:
        event["key"] = (event["run_id"], event["timestep"], event["rk"], event["cell"],
                        event["pair"], event["group_predicate"])
        if set(event["hex"]) != set(HEX_COUNTS):
            raise ValueError(f"incomplete PR99 exact-bit payload for {event['key']}")
        if (set(event["options"]) != required_options or "group_shape" not in event or
                set(event["text"]) != set(TEXT_ROWS)):
            raise ValueError(f"incomplete PR99 options or group shape for {event['key']}")
        if "post_retry_feasible" not in event:
            raise ValueError(f"PR99 event is missing its post-graupel-mixture status for {event['key']}")
        if event["attempt"] not in {"BASELINE", "SOURCE_FIRST"}:
            raise ValueError(f"unknown PR99 attempt label {event['attempt']!r}")
        if event["group_predicate"] not in {1, 2}:
            raise ValueError(f"unknown PR99 grouped predicate {event['group_predicate']}")
        if (event["timestep"] != timestep or event["rk"] not in {1, 2, 3}
                or (rk is not None and event["rk"] != rk)
                or event["store_failure_stage"] < 0):
            requested_rk = f", RK{rk}" if rk is not None else ""
            raise ValueError(
                f"PR99 event does not match requested T{timestep}{requested_rk} selection "
                f"or has an invalid RK/store stage: {event['key']}")
        if (event["pair"] not in {1, 2, 3, 4} or event["cell"] < 1
                or event["cell"] > event["group_shape"][0]
                or event["pair"] > event["group_shape"][1]):
            raise ValueError(f"PR99 event index is outside recorded group shape for {event['key']}")
        if event["store_succeeded"] != (event["store_failure_stage"] == 0):
            raise ValueError(f"inconsistent PR99 store status/stage for {event['key']}")
        pair = event["pair"]
        options = event["options"]
        expected_options = {
            "OPT_joint_constrained_storage": True,
            "OPT_joint_quantum_absence": True,
            "OPT_normal_q_adjustment": True,
            "OPT_strict_mass_pair": pair == 4,
            "OPT_inactive_mass_pair": pair == 2,
            "OPT_inactive_q_quantum_pair": pair == 2,
            "OPT_bulk_volume_quantum_storage": True,
            "OPT_number_pair_bounds": True,
        }
        if any(options[name] != expected for name, expected in expected_options.items()):
            raise ValueError(f"inconsistent PR99 pair options for {event['key']}")
        number_bounds = [exact_real64(value) for value in event["hex"]["HEX64_NUMBER_BOUNDS"]]
        if any(not (value == value and abs(value) != float("inf")) for value in number_bounds):
            raise ValueError(f"nonfinite exact PR99 volume bounds for {event['key']}")
        event["number_bounds_r64"] = number_bounds
        if pair in {2, 4} and number_bounds != [0.0, 0.0]:
            raise ValueError(f"unexpected PR99 volume bounds for pair {pair}")
        if pair in {1, 3} and (number_bounds[0] <= 0.0 or number_bounds[1] < number_bounds[0]):
            raise ValueError(f"invalid PR99 volume bounds for pair {pair}")
        if options["OPT_source_first_fallback"] != (event["attempt"] == "SOURCE_FIRST"):
            raise ValueError(f"inconsistent PR99 host attempt flag for {event['key']}")
        event["attempt_scope"] = (
            "SOURCE_FIRST is the host-wide ANY(source_first_pair) flag at this grouped attempt; "
            "the captured row does not show whether this pair was selected"
            if event["attempt"] == "SOURCE_FIRST" else
            "BASELINE means the host-wide ANY(source_first_pair) flag was false at this attempt")
        event["post_graupel_mixture_feasible"] = event.pop("post_retry_feasible")
        event["post_graupel_mixture_scope"] = (
            "feasibility after the inner try_graupel_mixture_trial fallback in the same "
            "evaluate_joint_candidate call; not the later outer RK3 source-first reevaluation")
        event["grouped_predicate_input"] = (
            "stored REAL32 pair" if event["store_succeeded"] else
            "(-1,-1) REAL32 sentinel installed by form_candidate after store failure")
        event["classification"] = (
            "store_rejection" if event["store_failure_stage"] > 0 else
            "post_store_grouped_moment_failure" if event["group_predicate"] == 1 else
            "post_store_volume_number_failure")
    if any("post_graupel_mixture_feasible" not in row for row in events):
        raise ValueError("PR99 event is missing its post-graupel-mixture status")
    return {"schema": "pr99_group_failure_capture_v1", "event_count": len(events),
            "events": events,
            "cause_scope": "first grouped predicate and bounded direct-input record; no aggregate physical conclusion"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timestep", type=int, default=32)
    parser.add_argument("--rk", type=int, choices=(1, 2, 3))
    args = parser.parse_args()
    result = parse_capture(args.capture, timestep=args.timestep, rk=args.rk)
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
