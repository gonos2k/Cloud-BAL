#!/usr/bin/env python3
"""Fail closed on missing independent authority for a retained-observation case.

This checks declaration completeness and time matching. It does not authenticate
the cited artifacts or approve the science.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EXPECTED_TIME = "2026-08-16T12:00:00Z"
READY = "AUTHORIZED"
CONDITIONAL = "CONDITIONAL"
MISSING = "MISSING"
AUTHORITY_NAMES = (
    "radar_analysis", "external_source", "physical_boundary",
    "phase_exchange", "common_air_moments",
)


def _validate_declaration(declaration: Any) -> dict[str, Any]:
    if not isinstance(declaration, dict):
        raise ValueError("declaration must be a JSON object")
    if type(declaration.get("schema_version")) is not int or \
            declaration["schema_version"] != 1:
        raise ValueError("expected schema_version 1")
    if declaration.get("valid_time") != EXPECTED_TIME:
        raise ValueError(f"valid_time must be the exact case time {EXPECTED_TIME}")
    if declaration.get("scope") != "ALL_OBSERVATIONS":
        raise ValueError("scope must be ALL_OBSERVATIONS")

    authorities = declaration.get("authorities")
    if not isinstance(authorities, dict):
        raise ValueError("authorities must be a JSON object")
    for name in AUTHORITY_NAMES:
        authority = authorities.get(name)
        if not isinstance(authority, dict):
            raise ValueError(f"authorities.{name} must be a JSON object")
        evidence_id = authority.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            raise ValueError(f"authorities.{name}.evidence_id must be a nonempty string")
        status = authority.get("status")
        if status is not None and not isinstance(status, str):
            raise ValueError(f"authorities.{name}.status must be a string")
        if "valid_time" in authority and not isinstance(authority["valid_time"], str):
            raise ValueError(f"authorities.{name}.valid_time must be a string")

    for name, required_flags in (
        ("radar_analysis", ("per_cell", "error_bound")),
        ("external_source", ("per_cell",)),
        ("physical_boundary", ("per_cell",)),
    ):
        authority = authorities[name]
        for flag in required_flags:
            if type(authority.get(flag)) is not bool:
                raise ValueError(f"authorities.{name}.{flag} must be a boolean")

    if "wind" in authorities:
        authority = authorities["wind"]
        if not isinstance(authority, dict):
            raise ValueError("authorities.wind must be a JSON object")
        evidence_id = authority.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            raise ValueError("authorities.wind.evidence_id must be a nonempty string")
        if "status" in authority and not isinstance(authority["status"], str):
            raise ValueError("authorities.wind.status must be a string")
        if "valid_time" in authority and not isinstance(authority["valid_time"], str):
            raise ValueError("authorities.wind.valid_time must be a string")
        if "error_bound" in authority and type(authority["error_bound"]) is not bool:
            raise ValueError("authorities.wind.error_bound must be a boolean")

    wind = declaration.get("wind")
    if not isinstance(wind, dict):
        raise ValueError("wind must be a JSON object")
    wind_mode = wind.get("mode")
    if not isinstance(wind_mode, str) or not wind_mode.strip():
        raise ValueError("wind.mode must be a nonempty string")
    return declaration


def _read_declaration(path: Path) -> dict[str, Any]:
    return _validate_declaration(json.loads(path.read_text(encoding="utf-8")))


def _authority_gate(declaration: dict[str, Any], name: str, *,
                    needs_per_cell: bool = False,
                    needs_error_bound: bool = False) -> list[str]:
    authority = declaration.get("authorities", {}).get(name)
    if not isinstance(authority, dict):
        return [f"{name}: declaration missing"]
    failures = []
    if authority.get("status") != READY:
        failures.append(f"{name}: status is {authority.get('status', 'MISSING')}")
    if authority.get("valid_time") != EXPECTED_TIME:
        failures.append(f"{name}: exact 12 UTC valid-time evidence missing")
    if not authority.get("evidence_id"):
        failures.append(f"{name}: evidence_id missing")
    if needs_per_cell and authority.get("per_cell") is not True:
        failures.append(f"{name}: per-cell values/provenance missing")
    if needs_error_bound and authority.get("error_bound") is not True:
        failures.append(f"{name}: independent error bound missing")
    return failures


def evaluate(declaration: dict[str, Any]) -> dict[str, Any]:
    declaration = _validate_declaration(declaration)
    failures: list[str] = []
    failures += _authority_gate(declaration, "radar_analysis", needs_per_cell=True,
                                needs_error_bound=True)
    failures += _authority_gate(declaration, "external_source", needs_per_cell=True)
    failures += _authority_gate(declaration, "physical_boundary", needs_per_cell=True)
    failures += _authority_gate(declaration, "phase_exchange")
    failures += _authority_gate(declaration, "common_air_moments")

    wind = declaration.get("wind", {})
    wind_mode = wind.get("mode") if isinstance(wind, dict) else None
    wind_failures: list[str] = []
    if wind_mode == "FIXED_BACKGROUND":
        # A fixed wind is allowed for the thermodynamic conditional path, but
        # it cannot count as a completed wind-analysis component.
        pass
    elif wind_mode in {"OBSERVATION", "BACKGROUND_PRIOR", "PAIRED_MODEL"}:
        authority = declaration.get("authorities", {}).get("wind")
        if not isinstance(authority, dict):
            wind_failures.append("wind: authority declaration missing")
        else:
            if authority.get("status") != READY:
                wind_failures.append(f"wind: status is {authority.get('status', 'MISSING')}")
            if authority.get("valid_time") != EXPECTED_TIME:
                wind_failures.append("wind: exact 12 UTC target missing")
            if not authority.get("evidence_id"):
                wind_failures.append("wind: evidence_id missing")
            if wind_mode in {"OBSERVATION", "BACKGROUND_PRIOR"} and \
                    authority.get("error_bound") is not True:
                wind_failures.append("wind: independent target/prior uncertainty missing")
    else:
        wind_failures.append("wind: unsupported or missing mode")
    failures += wind_failures

    return {
        "status": "READY_FOR_CANDIDATE_EVALUATION" if not failures else "BLOCKED",
        "scope": "ALL_OBSERVATIONS",
        "valid_time": EXPECTED_TIME,
        "wind_mode": wind_mode or "MISSING",
        "wind_component_complete": wind_mode != "FIXED_BACKGROUND" and not wind_failures,
        "failed_gates": failures,
        "interpretation": (
            "Declaration completeness only; cited evidence is not authenticated and "
            "this result is not scientific approval."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("declaration", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = evaluate(_read_declaration(args.declaration))
    except (OSError, TypeError, ValueError) as error:
        result = {"status": "INVALID_DECLARATION", "error": str(error)}
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["status"] == "READY_FOR_CANDIDATE_EVALUATION" else 2


if __name__ == "__main__":
    raise SystemExit(main())
