#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
evidence_dir=${PR73_NATIVE_EVIDENCE_DIR:-$repo_root/docs/evidence/pr73_native_first_violation_20261008}
if [[ -e $evidence_dir || -L $evidence_dir ]]; then
  printf 'refusing to overwrite PR73 native evidence: %s\n' "$evidence_dir" >&2
  exit 2
fi
source "$repo_root/tests/intel_toolchain.sh"
work_root=$(mktemp -d /var/tmp/pr73_native_first_violation.XXXXXX)
printf 'WORK_ROOT %s\n' "$work_root"
mkdir -p "$evidence_dir"
python3 "$repo_root/tools/pr73_first_violation.py" \
  "$repo_root/docs/evidence/pr72_combined_native_first_reject_20261008/frozen_combined_source.F" \
  "$work_root/module_mp_kdm6_first_violation.F" \
  --receipt "$work_root/composition.json" >"$work_root/transform.log"

python3 - "$repo_root" "$work_root" "$CLOUD_BAL_FC" "$evidence_dir" <<'PY'
from __future__ import annotations
import hashlib
import difflib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

repo, work, compiler, evidence = map(Path, sys.argv[1:])
proof = repo / "docs/evidence/pr72_combined_native_first_reject_20261008/receipt.json"
prior = json.loads(proof.read_text())
prior_run = prior["run"]
prior_input_manifest = json.dumps(
    [{"path": item["path"], "sha256": item["sha256_expected"]}
     for item in prior_run["input_hashes"]],
    sort_keys=True, separators=(",", ":")).encode()
build_proof_path = proof.parent / "partialhost_build_receipt.json"
build_proof = json.loads(build_proof_path.read_text())
base_build = Path(build_proof["base"])
fresh_build = work / "build"
fresh_compile = fresh_build / "compile"
fresh_main = fresh_build / "link/main"
shutil.copytree(base_build, fresh_build)

source = work / "module_mp_kdm6_first_violation.F"
compile_log = fresh_compile / "pr73_compile.log"
compile_record = build_proof["compile"]
compile_argv = list(compile_record["argv"])
compile_argv[compile_argv.index("module_mp_kdm6.f90")] = str(source)
compile_argv[compile_argv.index("module_mp_kdm6.o")] = str(fresh_compile / "module_mp_kdm6.o")
compile_argv.insert(compile_argv.index("-c"), "-free")
with compile_log.open("wb") as stream:
    subprocess.run(compile_argv, cwd=fresh_compile, check=True, stdout=stream, stderr=subprocess.STDOUT)
archive_path = fresh_main / "libwrflib_pr65.a"
archive_before_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
update_argv = list(build_proof["archive"]["update_argv"])
update_argv[-2:] = [str(archive_path), str(fresh_compile / "module_mp_kdm6.o")]
archive_log = fresh_main / "pr73_archive_update.log"
with archive_log.open("wb") as stream:
    subprocess.run(update_argv, cwd=fresh_main, check=True, stdout=stream, stderr=subprocess.STDOUT)
archive_after_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
archive_member = subprocess.run(
    ["/usr/bin/ar", "p", str(archive_path), build_proof["archive"]["member_name"]],
    cwd=fresh_main, check=True, stdout=subprocess.PIPE,
).stdout
archive_members = subprocess.run(["/usr/bin/ar", "t", str(archive_path)],
                                 cwd=fresh_main, check=True, stdout=subprocess.PIPE, text=True).stdout.splitlines()
object_sha = hashlib.sha256((fresh_compile / "module_mp_kdm6.o").read_bytes()).hexdigest()
if hashlib.sha256(archive_member).hexdigest() != object_sha:
    raise SystemExit("fresh archive member differs from the compiled KDM6 object")
link_argv = [item.replace(str(base_build), str(fresh_build)) for item in build_proof["link"]["argv"]]
link_log = fresh_main / "pr73_link.log"
with link_log.open("wb") as stream:
    subprocess.run(link_argv, cwd=fresh_main, check=True, stdout=stream, stderr=subprocess.STDOUT)
executable = fresh_build / "executable/wrf.exe"
executable_sha = hashlib.sha256(executable.read_bytes()).hexdigest()

run_root = work / "run"
run_root.mkdir()
expected_inputs = {}
for item in prior_run["input_hashes"]:
    name = item["path"]
    source_path = Path(item["staged_path"])
    target = run_root / name
    if source_path.is_symlink() or not source_path.is_file():
        raise SystemExit(f"retained native input is not a regular file: {source_path}")
    shutil.copy2(source_path, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != item["sha256_expected"]:
        raise SystemExit(f"staged input hash mismatch: {name}")
    expected_inputs[name] = digest
shutil.copy2(executable, run_root / "wrf.exe")
staged_executable_sha = hashlib.sha256((run_root / "wrf.exe").read_bytes()).hexdigest()
if staged_executable_sha != executable_sha:
    raise SystemExit("staged executable hash mismatch")

command = prior_run["command"]
required_post_call = [
    "pr67_kdm6_process.raw",
    "pr69_water.raw",
    "kdm6_first_call_post.raw",
    "wrfout_d01_2026-08-16_12:00:20",
]
outputs = list(dict.fromkeys(
    [item["path"] for item in prior_run["output_hashes"]] + required_post_call
))
input_paths = [run_root / name for name in expected_inputs] + [run_root / "wrf.exe"]
sys.path.insert(0, str(repo / "tools"))
import run_isolated_native
result = run_isolated_native.run_isolated(run_root, input_paths, outputs, command)
logs = {}
for name in ("candidate_run.log", "rsl.out.0000", "rsl.error.0000"):
    path = run_root / name
    if path.is_file():
        logs[name] = path.read_text(errors="replace")
all_log_text = "\n".join(logs.values())
violation_lines = [line.strip() for line in all_log_text.splitlines()
                   if "KDM6_FIRST_VIOLATION|" in line]
violation_lines = [line[line.index("KDM6_FIRST_VIOLATION|"):] for line in violation_lines]
if result["input_integrity"] != "PASS":
    raise SystemExit("native input integrity failed")
if len(violation_lines) != 1:
    raise SystemExit(f"expected one first-violation line, found {len(violation_lines)}")
pretrace = run_root / "kdm6_first_call_pre.raw"
expected_pretrace = prior_run["baseline_first_call_pretrace"]["baseline_sha256"]
pretrace_sha = hashlib.sha256(pretrace.read_bytes()).hexdigest() if pretrace.is_file() else None
present_outputs = {item["path"] for item in result["outputs"]}
missing_post_call = [name for name in required_post_call if name not in present_outputs]
frozen_source = repo / "docs/evidence/pr72_combined_native_first_reject_20261008/frozen_combined_source.F"
patch_text = "".join(difflib.unified_diff(
    frozen_source.read_text(errors="replace").splitlines(keepends=True),
    source.read_text(errors="replace").splitlines(keepends=True),
    fromfile="frozen_combined_source.F", tofile="instrumented_source.F"))
record = {
    "schema": "pr73_native_first_violation_v1",
    "status": "CAPTURED_CONTROLLED_FIRST_REJECTION" if result["returncode"] else "UNEXPECTED_NATIVE_SUCCESS",
    "native_status": "REJECTED" if result["returncode"] and violation_lines else "UNCLASSIFIED",
    "source_sha256": prior["source"]["source_sha256"],
    "instrumented_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "durable_source_artifacts": {
        "instrumented_source": "instrumented_source.F",
        "instrumented_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_patch": "source.patch",
        "source_patch_sha256": hashlib.sha256(patch_text.encode()).hexdigest(),
    },
    "build_receipt_sha256": hashlib.sha256(build_proof_path.read_bytes()).hexdigest(),
    "pr72_input_receipt_sha256": hashlib.sha256(proof.read_bytes()).hexdigest(),
    "staged_input_manifest_sha256": hashlib.sha256(prior_input_manifest).hexdigest(),
    "compiler": str(compiler),
    "partialhost_build_scope": "fresh copy of retained PR72 partialhost host objects/archive; KDM6 recompiled and archived, then relinked",
    "run_root": str(run_root),
    "run_command": command,
    "returncode": result["returncode"],
    "input_integrity": result["input_integrity"],
    "scientific_input_count": len(expected_inputs),
    "guarded_input_count_including_executable": len(result["inputs"]),
    "input_hashes_before_after": result["inputs"],
    "source_composition": json.loads((work / "composition.json").read_text()),
    "build_artifacts": {
        "compile_argv": compile_argv,
        "compile_log": str(compile_log),
        "compile_log_sha256": hashlib.sha256(compile_log.read_bytes()).hexdigest(),
        "object_path": str(fresh_compile / "module_mp_kdm6.o"),
        "object_sha256": object_sha,
        "archive_update_argv": update_argv,
        "archive_update_log_sha256": hashlib.sha256(archive_log.read_bytes()).hexdigest(),
        "archive_path": str(archive_path),
        "archive_sha256_before": archive_before_sha,
        "archive_sha256_after": archive_after_sha,
        "archive_member_count": len(archive_members),
        "archive_member_name": build_proof["archive"]["member_name"],
        "archive_member_sha256": hashlib.sha256(archive_member).hexdigest(),
        "link_argv": link_argv,
        "link_log_sha256": hashlib.sha256(link_log.read_bytes()).hexdigest(),
        "executable_path": str(executable),
        "executable_sha256": executable_sha,
        "staged_executable_sha256": staged_executable_sha,
        "compiler_profile": {
            "ifx_path": str(compiler),
            "ifx_sha256": hashlib.sha256(compiler.read_bytes()).hexdigest(),
            "ifx_version": subprocess.run([str(compiler), "--version"], check=True,
                                           stdout=subprocess.PIPE, text=True).stdout.splitlines()[0],
            "link_driver": link_argv[0],
            "link_driver_sha256": hashlib.sha256(Path(link_argv[0]).read_bytes()).hexdigest(),
            "pinned_toolchain_script": str(repo / "tests/intel_toolchain.sh"),
            "pinned_toolchain_script_sha256": hashlib.sha256(
                (repo / "tests/intel_toolchain.sh").read_bytes()).hexdigest(),
            "pinned_intel_setvars": "/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/setvars.sh",
            "pinned_intel_setvars_sha256": hashlib.sha256(Path(
                "/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/setvars.sh").read_bytes()).hexdigest(),
        },
    },
    "output_isolation": result["output_isolation"],
    "output_issues": result["output_issues"],
    "outputs_present": result["outputs"],
    "required_post_call_outputs": required_post_call,
    "missing_required_post_call_outputs": missing_post_call,
    "completion_status": (
        "INCOMPLETE_REQUIRED_POST_CALL_OUTPUTS" if missing_post_call
        else "REQUIRED_POST_CALL_OUTPUTS_PRESENT"
    ),
    "required_output_guard_status": "FAIL" if missing_post_call else "PASS",
    "first_violation_line": violation_lines[0],
    "baseline_first_call_pretrace": {
        "expected_sha256": expected_pretrace,
        "captured_sha256": pretrace_sha,
        "matches_baseline": pretrace_sha == expected_pretrace,
    },
    "log_sha256": {name: hashlib.sha256((run_root / name).read_bytes()).hexdigest() for name in logs},
    "limitations": [
        "Partialhost research run, not a clean full-physics host build or production-source equivalence claim.",
        "Only declared input and output paths are monitored by the isolated runner.",
        "call_lat_index is the KDM62D lat argument; global-j mapping and geographic latitude are unclaimed.",
        "This is a controlled admission rejection before PSD work, not a completed model timestep or physics validation.",
    ],
    "isolation_receipt": result,
}
if record["status"] != "CAPTURED_CONTROLLED_FIRST_REJECTION" or not record["baseline_first_call_pretrace"]["matches_baseline"]:
    raise SystemExit("native status or pretrace comparison failed")
(evidence / "native_receipt.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
(evidence / "instrumented_source.F").write_bytes(source.read_bytes())
(evidence / "source.patch").write_text(patch_text)
for name, path in (("compile.log", compile_log), ("archive_update.log", archive_log), ("link.log", link_log)):
    shutil.copy2(path, evidence / name)
for name, body in logs.items():
    (evidence / name).write_text(body)
print(f"PR73_NATIVE_STATUS {record['status']}")
print(f"PR73_NATIVE_FIRST_VIOLATION {violation_lines[0]}")
print(f"PR73_NATIVE_INPUT_INTEGRITY {result['input_integrity']}")
print(f"PR73_NATIVE_OUTPUT_ISOLATION {result['output_isolation']}")
print(f"PR73_NATIVE_COMPLETION {record['completion_status']}")
print(f"PR73_NATIVE_MISSING_POST_CALL {missing_post_call}")
PY
