#!/usr/bin/env python3
"""Run one test and make unittest skips visible in the tier summary."""
from __future__ import annotations

import re
import subprocess
import sys
import json
from pathlib import Path


def main() -> int:
    test_path = Path(sys.argv[1])
    allowlist_path = Path(__file__).with_name("python_script_test_allowlist.json")
    script_tests = set(json.loads(allowlist_path.read_text(encoding="utf-8")))
    is_script_test = test_path.name in script_tests
    command = ([sys.executable, str(test_path)] if is_script_test
               else [sys.executable, "-m", "pytest", "-q", str(test_path)])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    output = result.stdout + result.stderr
    print(output, end="")
    if result.returncode:
        if not is_script_test and result.returncode == 5:
            print(f"No pytest cases executed for {test_path}", file=sys.stderr)
        print(f"FAIL {test_path}")
        return result.returncode

    pytest_skipped = re.search(r"^\s*(\d+) skipped(?:\s|$)", output, re.MULTILINE)
    ran = re.search(r"Ran (\d+) tests?", output)
    skipped = re.search(r"OK \(skipped=(\d+)\)", output)
    if ran and skipped:
        count, skip_count = int(ran.group(1)), int(skipped.group(1))
        if count == skip_count:
            print(f"TIER_RESULT: SKIP {test_path}: all {count} unittest cases skipped")
            return 0
        if skip_count:
            print(f"TIER_RESULT: PASS {test_path}: {count - skip_count} passed, {skip_count} skipped")
            return 0
    pytest_summary = re.search(r"(\d+) passed(?:, (\d+) skipped)?", output)
    if pytest_summary:
        passed = int(pytest_summary.group(1))
        skip_count = int(pytest_summary.group(2) or 0)
        if passed == 0 and skip_count:
            print(f"TIER_RESULT: SKIP {test_path}: all {skip_count} pytest cases skipped")
            return 0
        print(f"TIER_RESULT: PASS {test_path}: {passed} passed, {skip_count} skipped")
        return 0
    if pytest_skipped:
        print(f"TIER_RESULT: SKIP {test_path}: all {pytest_skipped.group(1)} pytest cases skipped")
        return 0
    if not is_script_test:
        print(f"No pytest cases executed for {test_path}", file=sys.stderr)
        return 5
    print(f"TIER_RESULT: PASS {test_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
