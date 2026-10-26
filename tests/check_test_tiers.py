#!/usr/bin/env python3
"""Validate discovery and report the tier assigned to every Python test."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
TIERS = ("portable", "linux", "native", "realdata")


def registry() -> dict[str, tuple[str, str]]:
    exceptions = json.loads((TESTS / "test_tier_exceptions.json").read_text())
    mapping: dict[str, tuple[str, str]] = {}
    for tier, entries in exceptions.items():
        if tier not in TIERS[1:]:
            raise ValueError(f"unsupported exception tier: {tier}")
        for entry in entries:
            if not isinstance(entry, dict) or len(entry) != 1:
                raise ValueError(f"each {tier} exception must map one test name to a reason")
            name, reason = next(iter(entry.items()))
            if not reason.strip():
                raise ValueError(f"tier exception needs a reason: {name}")
            if name in mapping:
                raise ValueError(f"test assigned to multiple tiers: {name}")
            mapping[name] = (tier, reason)

    discovered = {path.name for path in TESTS.glob("test_*.py")}
    unknown = sorted(set(mapping) - discovered)
    if unknown:
        raise ValueError(f"tier exceptions name missing tests: {', '.join(unknown)}")
    script_tests = json.loads((TESTS / "python_script_test_allowlist.json").read_text())
    if len(script_tests) != len(set(script_tests)):
        raise ValueError("duplicate script-style test allowlist entry")
    unknown_scripts = sorted(set(script_tests) - discovered)
    if unknown_scripts:
        raise ValueError(f"script-style allowlist names missing tests: {', '.join(unknown_scripts)}")
    return {name: mapping.get(name, ("portable", "")) for name in sorted(discovered)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=TIERS, default="portable")
    parser.add_argument("--list", action="store_true", help="print selected test paths")
    args = parser.parse_args()

    try:
        assigned = registry()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))

    for name, (tier, reason) in assigned.items():
        if args.list:
            if tier == args.tier:
                print(f"tests/{name}")
        elif tier == args.tier:
            print(f"RUN {tier:8} tests/{name}" + (f" — {reason}" if reason else ""))
        else:
            print(f"SKIP {tier:8} tests/{name} (select --tier {tier}; {reason})")
    summary = f"Registered {len(assigned)} Python tests; selected tier: {args.tier}"
    if args.list:
        print(summary, file=sys.stderr)
    else:
        print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
