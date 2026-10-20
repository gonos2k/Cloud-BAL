#!/usr/bin/env python3
"""Replay the captured C18 ice PSD boundary and freezing-base decision."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/pr93_ice_origin_20261020"
PROFILE = ROOT / "tests/intel_toolchain.sh"
SOURCES = (
    ROOT / "tools/pr85_kdm6_psd_boundary.F90",
    ROOT / "tools/pr85_kdm6_freezing_packet.F90",
)


def run_profile(optimization: str, scratch_root: Path) -> str:
    """Build and run one fresh pinned-Intel replay."""
    scratch = Path(tempfile.mkdtemp(prefix=f"pr93_ice_origin_{optimization}_",
                                    dir=scratch_root))
    flags = "CLOUD_BAL_FREE_FLAGS" if optimization == "O0" else "CLOUD_BAL_REPRO_FLAGS"
    command = (
        "source \"$1\"\n"
        "\"$CLOUD_BAL_FC\" \"${" + flags + "[@]}\" \"$2\" \"$3\" \"$4\" -o replay\n"
        "./replay"
    )
    result = subprocess.run(
        ["bash", "-c", command, "pr93_ice_origin", str(PROFILE),
         str(EVIDENCE / "replay.f90"), *(str(path) for path in SOURCES)],
        cwd=scratch, check=True, text=True, capture_output=True,
    )
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch-root", type=Path, default=Path("/var/tmp"))
    args = parser.parse_args()
    results = {mode: run_profile(mode, args.scratch_root) for mode in ("O0", "O2")}
    print(json.dumps({"status": "PASS_REPLAY", "profile": str(PROFILE),
                      "replays": results}, indent=2))


if __name__ == "__main__":
    main()
