#!/usr/bin/env python3
"""Write a hash-bound receipt for one successful face-observer component replay."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from native_kdm6_trace import read_dump


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def rows(path: Path, prefix: str) -> int:
    return sum(line.startswith(prefix) for line in path.read_text(encoding="ascii").splitlines())


def manifest(args: argparse.Namespace) -> dict:
    replay_post = args.run_dir / "replay_post.raw"
    face = args.run_dir / "pr98_sed_face.raw"
    rain = args.run_dir / "pr87_rain_sedimentation_budget.raw"
    ice = args.run_dir / "pr85_ice_sedimentation_budget.raw"
    cutoff = args.run_dir / "pr85_kdm6_cutoff_budget.raw"
    liquid = args.run_dir / "pr97_liquid_columns.raw"
    log = args.run_dir / "replay.log"
    if not all(path.is_file() for path in (replay_post, face, rain, ice, cutoff, liquid, log)):
        raise ValueError("face replay did not emit all call artifacts")
    if sha256(replay_post) != sha256(args.native_post):
        raise ValueError("face replay did not preserve all 17 fields and XLAND")
    native, replay = read_dump(args.native_post), read_dump(replay_post)
    if native["bounds"] != replay["bounds"] or native["fields"].keys() != replay["fields"].keys():
        raise ValueError("face replay returned-state headers differ")
    for name in native["fields"]:
        if not (native["fields"][name] == replay["fields"][name]).all():
            raise ValueError(f"face replay returned-state field differs: {name}")
    completion = "REPLAY COMPLETED FULL ACTIVE TILE"
    if completion not in log.read_text(encoding="ascii", errors="replace"):
        raise ValueError("face replay log lacks full-tile completion marker")
    build = json.loads(args.build_manifest.read_text(encoding="utf-8"))
    if (build.get("schema") != "pr98_face_observer_build_v1" or
            build.get("linked_executable_sha256") != sha256(args.executable) or
            build.get("prepared_source_sha256") != sha256(args.prepared_source) or
            build.get("observer_source_sha256") != sha256(args.observer_source)):
        raise ValueError("face replay executable is not bound to the observer build receipt")
    area = args.history
    return {
        "schema": "pr98_face_replay_v1",
        "completion_marker": completion, "completion_marker_observed": True,
        "arm": args.arm, "executable_path": str(args.executable.resolve()),
        "executable_sha256": sha256(args.executable),
        "original_pr97_diagnostic_source_sha256": sha256(args.original_source),
        "build_manifest_sha256": sha256(args.build_manifest), "build_manifest": build,
        "prepared_source_path": str(args.prepared_source.resolve()),
        "prepared_source_sha256": sha256(args.prepared_source),
        "observer_source_sha256": sha256(args.observer_source),
        "build_link_argv_sha256": sha256(args.link_argv),
        "compiler_profile": "tests/intel_toolchain.sh (pinned Intel 2026.0 ifx)",
        "compiler_profile_sha256": sha256(args.profile),
        "omp_threads": 1, "unlimited_stack": True,
        "pre_sha256": sha256(args.pre), "native_post_sha256": sha256(args.native_post),
        "replay_post_sha256": sha256(replay_post),
        "all_17_fields_and_XLAND_byte_equal": True,
        "face_rows_sha256": sha256(face), "accepted_face_records": rows(face, "PR98_SED_FACE"),
        "rain_rows_sha256": sha256(rain), "rain_stage_rows": rows(rain, "PR87_RAIN_SED"),
        "rain_face_summary_rows": rows(rain, "PR98_SED_FACE_SUM"),
        "ice_rows_sha256": sha256(ice), "ice_stage_rows": rows(ice, "PR85_ICE_SED"),
        "ice_face_summary_rows": rows(ice, "PR98_SED_FACE_SUM"),
        "cutoff_rows_sha256": sha256(cutoff),
        "liquid_columns_sha256": sha256(liquid),
        "history_sha256": sha256(area), "history_path": str(area.resolve()),
        "log_sha256": sha256(log), "scratch_directory": str(args.run_dir.resolve()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("arm", "run-dir", "executable", "build-manifest", "original-source", "prepared-source",
                 "observer-source", "link-argv", "profile", "pre", "native-post", "history", "output"):
        parser.add_argument("--" + name, type=Path if name != "arm" else str, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(manifest(args), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
