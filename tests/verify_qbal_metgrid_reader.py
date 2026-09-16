#!/usr/bin/env python3
"""Stage hash-bound WPS files and record actual Fortran-reader executions.

All field/geometry/time comparisons are in verify_qbal_metgrid_reader.f90.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

LOOKUP_DATE = "2023-05-18_03:33:20"
VALID_DATE = "2023-05-18_03:33:20.0000"


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def prepare(source, expected_hash, root):
    manifest_path = source / "manifest.json"
    if sha256(manifest_path) != expected_hash:
        raise ValueError("LAPSPREP manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text())
    if manifest["status"] != "PASS_SCOPED":
        raise ValueError("LAPSPREP handoff has not passed")
    for name, expected in manifest["artifacts_sha256"].items():
        path = (source / name).resolve()
        if not path.is_relative_to(source) or sha256(path) != expected:
            raise ValueError(f"LAPSPREP artifact mismatch: {name}")
    cases = []
    for result in manifest["results"]:
        level = result["level"]
        if level not in ("O0", "O2"):
            raise ValueError("unknown producer optimization")
        for suffix, report in (("", result["verify"]),
                               ("-geometry", result["alternate_geometry"])):
            if report["status"] != "PASS_SCOPED" or report["time"]["wps"] != VALID_DATE:
                raise ValueError("unapproved source time/geometry case")
            name = level + suffix
            original = source / name / "wps.out"
            expected = manifest["artifacts_sha256"][f"{name}/wps.out"]
            directory = root / "inputs" / name
            directory.mkdir(parents=True)
            staged = directory / f"LAPS:{LOOKUP_DATE}"
            shutil.copyfile(original, staged)
            if sha256(staged) != expected:
                raise ValueError("staged WPS hash mismatch")
            cases.append({"name": name, "original": str(original),
                          "path": str(staged), "sha256": expected})
    if sorted(item["name"] for item in cases) != ["O0", "O0-geometry", "O2", "O2-geometry"]:
        raise ValueError("expected four unique approved handoffs")
    write_json(root / "inputs.json", {"manifest": str(manifest_path),
               "manifest_sha256": expected_hash, "cases": cases,
               "verified_artifacts": len(manifest["artifacts_sha256"])})


def run(root, level):
    inputs = json.loads((root / "inputs.json").read_text())
    executable = root / level / "verify_reader.exe"
    results = []
    failures = {
        "wrong-second": "FAIL: metgrid reader time mismatch",
        "lost-seconds": "FAIL: metgrid reader time mismatch",
        "wrong-lookup": "FAIL: metgrid reader could not open WPS input",
        "truncated": "FAIL: WPS unexpected EOF in slab record",
        "partial-trailing-record": "FAIL: WPS unexpected EOF in version record",
        "reader-time-mutation": "FAIL: metgrid reader time mismatch",
        "reader-slab-mutation": "FAIL: record 1 slab: bits differ at (1,1)",
    }

    def execute(name, prefix, date, expected_time, success, binary=executable):
        directory = root / level / name
        directory.mkdir()
        argv = [str(binary), str(prefix), date, expected_time]
        result = subprocess.run(argv, cwd=directory, capture_output=True, text=True, timeout=60)
        output = result.stdout + result.stderr
        (directory / "run.log").write_text(output)
        if success:
            valid = result.returncode == 0 and "PASS_SCOPED" in output
        else:
            valid = result.returncode != 0 and failures[name] in output
        results.append({"name": name, "argv": argv, "returncode": result.returncode,
                        "expected_success": success, "expected_message": "PASS_SCOPED" if success else failures[name],
                        "matched": valid})
        if not valid:
            raise RuntimeError(f"unexpected reader result: {name}\n{output}")

    for case in inputs["cases"]:
        path = Path(case["path"])
        if sha256(path) != case["sha256"]:
            raise ValueError("staged input changed")
        execute(case["name"], path.parent / "LAPS", LOOKUP_DATE, VALID_DATE, True)
    original = Path(inputs["cases"][0]["path"])
    prefix = original.parent / "LAPS"
    execute("wrong-second", prefix, LOOKUP_DATE, "2023-05-18_03:33:21.0000", False)
    execute("lost-seconds", prefix, LOOKUP_DATE, "2023-05-18_03:33:00.0000", False)
    execute("wrong-lookup", prefix, "2023-05-18_03:34", VALID_DATE, False)
    # Truncate the final slab, retaining its record header. No numerical formula here.
    truncated = root / level / "truncated-input"
    truncated.mkdir()
    (truncated / f"LAPS:{LOOKUP_DATE}").write_bytes(original.read_bytes()[:-8])
    execute("truncated", truncated / "LAPS", LOOKUP_DATE, VALID_DATE, False)
    trailing = root / level / "trailing-input"
    trailing.mkdir()
    (trailing / f"LAPS:{LOOKUP_DATE}").write_bytes(original.read_bytes() + b"\x00")
    execute("partial-trailing-record", trailing / "LAPS", LOOKUP_DATE, VALID_DATE, False)
    for mutation in ("time", "slab"):
        execute(f"reader-{mutation}-mutation", prefix, LOOKUP_DATE, VALID_DATE, False,
                root / level / f"verify_reader_{mutation}.exe")
    write_json(root / level / "results.json", results)


def finish(root, wps, repo):
    inputs = json.loads((root / "inputs.json").read_text())
    if sha256(Path(inputs["manifest"])) != inputs["manifest_sha256"]:
        raise ValueError("upstream manifest changed")
    for case in inputs["cases"]:
        for name in ("original", "path"):
            if sha256(Path(case[name])) != case["sha256"]:
                raise ValueError("WPS input changed")
    results = {level: json.loads((root / level / "results.json").read_text())
               for level in ("O0", "O2")}
    sources = {}
    for line in (repo / "tests/wps_reader_sources.sha256").read_text().splitlines():
        expected, name = line.split()
        if sha256(wps / name) != expected:
            raise ValueError("WPS source changed")
        sources[name] = expected
    write_json(root / "manifest.json", {
        "status": "PASS_SCOPED", "scope": "unmodified WPS v4.6.0 metgrid reader before interpolation",
        "wps_commit": "335c76a111f84503e8b963abaf273ea8053645bb",
        "wps_sources_sha256": sources, "input": inputs, "results": results,
        "test_sources_sha256": {name: sha256(repo / "tests" / name) for name in
            ("intel_toolchain.sh", "run_qbal_metgrid_reader_tests.sh",
             "verify_qbal_metgrid_reader.f90", "verify_qbal_metgrid_reader.py",
             "wps_reader_sources.sha256")},
        "artifacts_sha256": {str(path.relative_to(root)): sha256(path)
                             for path in sorted(root.rglob("*")) if path.is_file()},
        "limitations": ["Reader modules compiled standalone in serial _METGRID mode; not full metgrid/real execution.",
                        "Official WPS source identity is not a provenance claim for the installed KLFS executable.",
                        "No remapping, native omega/W, startup/halo, physical budgets or forecasts tested.",
                        "Original LAPSPREP/writer artifacts reused unchanged; not rebuilt in this test."]})
    print("PASS_SCOPED: actual WPS reader O0/O2; 8 normal and 14 negative executions")


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    if command == "prepare":
        prepare(Path(args[0]).resolve(), args[1], Path(args[2]).resolve())
    elif command == "run":
        run(Path(args[0]).resolve(), args[1])
    elif command == "mutate":
        source, kind, output = args
        text = Path(source).read_text()
        anchor = "read(unit=input_unit,err=1001,end=1001) fg_data % slab"
        if text.count(anchor) != 3:
            raise ValueError("reader mutation anchor changed")
        statement = {"time": "fg_data % hdate(18:19) = '00'",
                     "slab": "fg_data % slab(1,1) = fg_data % slab(1,1) + 1.0"}[kind]
        Path(output).write_text(text.replace(anchor, anchor + "\n         " + statement))
    elif command == "finish":
        finish(*(Path(arg).resolve() for arg in args))
    else:
        raise SystemExit("unknown command")
