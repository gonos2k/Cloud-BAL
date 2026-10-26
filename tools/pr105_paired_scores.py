#!/usr/bin/env python3
"""Reduce station scores from the completed, receipt-bound PR104 comparison."""

import argparse
import importlib.util
import json
from pathlib import Path


READER_PATH = Path(__file__).with_name("pr104_validtime_observation.py")
SPEC = importlib.util.spec_from_file_location("pr105_observation_reader", READER_PATH)
READER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(READER)

SUPERVISOR_ARMS = {"H": "HYDRO", "A": "AMPLITUDE", "N": "STRUCTURED"}


def _sha256_text(value: object, label: str) -> str:
    if (not isinstance(value, str) or len(value) != 64 or
            any(char not in "0123456789abcdef" for char in value)):
        raise ValueError(f"invalid SHA-256 for {label}")
    return value


def _closed_cohort_arms(cohort: dict) -> dict[str, dict]:
    if cohort.get("all_requested_forecasts_complete") is not True:
        raise ValueError("the requested H/A/N cohort is incomplete")
    rows = cohort.get("arms")
    if not isinstance(rows, list):
        raise ValueError("closed cohort arm records are missing")
    by_arm = {}
    for row in rows:
        arm = row.get("arm") if isinstance(row, dict) else None
        if arm not in SUPERVISOR_ARMS.values() or arm in by_arm:
            raise ValueError("closed cohort arm records are invalid")
        if (row.get("status") != "CLOSED" or row.get("requested_forecast_complete") is not True or
                row.get("completed_steps") != 180 or row.get("final_completed_step") != 180):
            raise ValueError(f"closed cohort arm is not a complete 180-step forecast: {arm}")
        receipt = row.get("closed_receipt")
        if not isinstance(receipt, dict) or not receipt.get("path"):
            raise ValueError(f"closed cohort receipt is missing: {arm}")
        expected_receipt_hash = _sha256_text(receipt.get("sha256"), f"{arm} cohort receipt")
        if READER.sha256(Path(receipt["path"])) != expected_receipt_hash:
            raise ValueError(f"closed cohort receipt identity changed: {arm}")
        by_arm[arm] = row
    if set(by_arm) != set(SUPERVISOR_ARMS.values()):
        raise ValueError("closed cohort must contain exactly HYDRO, AMPLITUDE, and STRUCTURED")
    return by_arm


def _validate_arm_bindings(dispatch: dict, cohort_arms: dict[str, dict], result: dict,
                           payload: dict) -> None:
    recipe = dispatch["recipes"]["observation"]
    recipe_before = _sha256_text(recipe.get("recipe_sha256_before"), "observation recipe before")
    recipe_after = _sha256_text(recipe.get("recipe_sha256_after"), "observation recipe after")
    if recipe_before != recipe_after:
        raise ValueError("observation recipe changed during postprocessing")

    pins_before, pins_after = result.get("pins_before"), result.get("pins_after")
    if not isinstance(pins_before, dict) or not isinstance(pins_after, dict) or pins_before != pins_after:
        raise ValueError("postclosure source pins are missing or changed")
    if pins_before.get("postclosure_recipe") != recipe_before:
        raise ValueError("dispatched observation recipe differs from the pinned postclosure recipe")

    closed_arms = result.get("closed_arms")
    reader_arms = payload.get("arms")
    if not isinstance(closed_arms, dict) or not isinstance(reader_arms, dict):
        raise ValueError("closed arm source records are missing")
    if set(closed_arms) != set(SUPERVISOR_ARMS) or set(reader_arms) != set(SUPERVISOR_ARMS):
        raise ValueError("closed observation provenance must contain exactly H, A, and N")

    for arm, supervisor_arm in SUPERVISOR_ARMS.items():
        closed = closed_arms[arm]
        reader = reader_arms[arm]
        cohort_row = cohort_arms[supervisor_arm]
        receipt_sha = _sha256_text(cohort_row["closed_receipt"].get("sha256"),
                                   f"{supervisor_arm} cohort receipt")
        history_sha = _sha256_text(closed.get("history_sha256"), f"{arm} closed history")
        if closed.get("arm") != supervisor_arm:
            raise ValueError(f"closed result arm name differs from cohort arm: {arm}")
        if closed.get("receipt_sha256") != receipt_sha:
            raise ValueError(f"closed result receipt differs from cohort receipt: {arm}")
        if (closed.get("history_path") != reader.get("history_path") or
                history_sha != reader.get("history_sha256")):
            raise ValueError(f"reader history source differs from closed arm pin: {arm}")
        if not isinstance(closed.get("history_bytes"), int) or closed["history_bytes"] <= 0:
            raise ValueError(f"closed history size is invalid: {arm}")
        if reader.get("valid_time_utc") != "2026-08-16T14:00:00Z":
            raise ValueError(f"reader history valid time differs from requested 14Z: {arm}")
        if pins_before.get(f"{arm}_receipt") != receipt_sha:
            raise ValueError(f"postclosure receipt pin differs from cohort receipt: {arm}")
        if pins_before.get(f"{arm}_history") != history_sha:
            raise ValueError(f"postclosure history pin differs from closed arm history: {arm}")


def reduce_closed_result(dispatch_path: Path, result_path: Path) -> dict:
    dispatch_hash = READER.sha256(dispatch_path)
    dispatch = json.loads(dispatch_path.read_text())
    observation = dispatch.get("recipes", {}).get("observation", {})
    if dispatch.get("status") != "POSTPROCESS_CLOSED" or observation.get("returncode") != 0:
        raise ValueError("a completed observation postprocessor is required")
    cohort_path = Path(dispatch["cohort"]["path"])
    cohort_hash = READER.sha256(cohort_path)
    if cohort_hash != dispatch["cohort"]["sha256"]:
        raise ValueError("closed cohort identity changed")
    cohort_arms = _closed_cohort_arms(json.loads(cohort_path.read_text()))
    result_hash = READER.sha256(result_path)
    if result_hash != observation["stdout_sha256"]:
        raise ValueError("observation result is not the dispatched closed result")
    result = json.loads(result_path.read_text())
    if result.get("schema") != "pr104_postclosure_observation_summary_v1":
        raise ValueError("observation result has an unexpected schema")
    if result.get("pins_unchanged") is not True:
        raise ValueError("closed observation provenance is incomplete")
    payload = result["reader_result"]
    if payload.get("schema") != "pr104_explicit_valid_time_observation_v1":
        raise ValueError("reader result has an unexpected schema")
    if payload["valid_time_utc"] != "2026-08-16T14:00:00Z":
        raise ValueError("expected the requested 14Z observation comparison")
    _validate_arm_bindings(dispatch, cohort_arms, result, payload)
    rows = payload["matched_station_records_by_arm"]
    pairs = {f"{x}_minus_{y}": READER.paired_operator_difference(rows[x], rows[y], f"{x} - {y}")
             for x, y in (("N", "A"), ("A", "H"), ("N", "H"))}
    arm_sources = {}
    for arm, supervisor_arm in SUPERVISOR_ARMS.items():
        closed = result["closed_arms"][arm]
        reader = payload["arms"][arm]
        cohort_row = cohort_arms[supervisor_arm]
        arm_sources[arm] = {
            "supervisor_arm": supervisor_arm,
            "receipt": {"path": cohort_row["closed_receipt"]["path"],
                        "sha256": cohort_row["closed_receipt"]["sha256"]},
            "history": {"path": closed["history_path"], "sha256": closed["history_sha256"],
                        "bytes": closed["history_bytes"], "valid_time_utc": reader["valid_time_utc"]},
        }
    for path, digest in ((dispatch_path, dispatch_hash), (cohort_path, cohort_hash), (result_path, result_hash)):
        if READER.sha256(path) != digest:
            raise ValueError(f"input changed during paired reduction: {path}")
    for cohort_arm in cohort_arms.values():
        receipt = cohort_arm["closed_receipt"]
        receipt_path = Path(receipt["path"])
        if READER.sha256(receipt_path) != receipt["sha256"]:
            raise ValueError(f"input changed during paired reduction: {receipt_path}")
    return {"schema": "pr105_closed_paired_scores_v1", "valid_time_utc": payload["valid_time_utc"],
            "source_result": {"path": str(result_path), "sha256": result_hash},
            "dispatch": {"path": str(dispatch_path), "sha256": dispatch_hash},
            "closed_arm_sources": arm_sources,
            "closure_validation": "Upstream PR104 receipts establish current C2 180-step closures and exact history timestamps; this reducer checks their receipt, recipe, and history-source bindings without reopening WRF fields.",
            "pairs": pairs, "observation_skill": "NOT_EVALUATED",
            "scope": "All common stations, no additional exclusions; surface temperature only, not cloud-support validation."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dispatch", required=True, type=Path)
    parser.add_argument("--closed-result", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = reduce_closed_result(args.dispatch, args.closed_result)
    text = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(text)


if __name__ == "__main__":
    main()
