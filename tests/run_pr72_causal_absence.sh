#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_root/tests/intel_toolchain.sh"
work_dir=$(mktemp -d /var/tmp/pr72_causal_absence.XXXXXX)
printf 'WORK_DIR %s\n' "$work_dir"
fixture=$repo_root/tests/fixtures/kdm6_wrapper
test_source=$repo_root/tests/test_pr71_unit_process_integration.f90

build_case() (
  label=$1
  module_source=$2
  build_dir=$work_dir/$label
  mkdir "$build_dir"
  cp "$fixture/"*.F "$fixture/wrf_debug_stub.f90" "$test_source" "$build_dir/"
  cp "$module_source" "$build_dir/module_mp_kdm6.F"
  cd "$build_dir"
  printf 'WORKDIR %s\n' "$PWD" >build.log
  compile() {
    printf 'ARGV' >>build.log
    printf ' %q' "$CLOUD_BAL_FC" "$@" >>build.log
    printf '\n' >>build.log
    "$CLOUD_BAL_FC" "$@" >>build.log 2>&1
  }
  define=(-DTEST_CANDIDATE -DTEST_EOS_CONSISTENT -DTEST_ABSENT_GRAUPEL)
  compile "${CLOUD_BAL_FREE_FLAGS[@]}" -free -fpp -c module_wrf_error.F
  compile "${CLOUD_BAL_FREE_FLAGS[@]}" -free -fpp -c module_model_constants.F
  compile "${CLOUD_BAL_FREE_FLAGS[@]}" -free -fpp -c module_mp_radar.F
  compile "${CLOUD_BAL_FREE_FLAGS[@]}" -free -fpp "${define[@]}" -DRWORDSIZE=4 -convert big_endian -c module_mp_kdm6.F
  compile "${CLOUD_BAL_FIXED_FLAGS[@]}" -fixed -fpp -c libmassv.F
  compile "${CLOUD_BAL_FREE_FLAGS[@]}" -c wrf_debug_stub.f90
  compile "${CLOUD_BAL_FREE_FLAGS[@]}" -fpp "${define[@]}" -c test_pr71_unit_process_integration.f90
  compile "${CLOUD_BAL_FREE_FLAGS[@]}" -o test.exe test_pr71_unit_process_integration.o module_mp_kdm6.o module_mp_radar.o module_model_constants.o libmassv.o wrf_debug_stub.o
  set +e
  ./test.exe >run.log 2>&1
  status=$?
  set -e
  printf '%s\n' "$status" >exit_status.txt
  if [[ $status == 0 ]]; then
    grep -q 'KDM6_NUMBER_WRAPPER CANDIDATE PASS' run.log
    printf '%s\n' PASS >outcome.txt
  elif grep -q 'forrtl: error (73): floating divide by zero' run.log; then
    printf '%s\n' FPE73 >outcome.txt
  elif grep -q 'KDM6 cold rain process rejected an infeasible moment state' run.log; then
    printf '%s\n' INFEASIBLE_MOMENT_STATE >outcome.txt
  else
    printf 'unexpected outcome %s\n' "$label" >&2
    cat run.log >&2
    exit 1
  fi
)

build_case pr70 /var/tmp/pr72_causal_pr70.F
build_case pr71 /var/tmp/pr72_causal_pr71.F
build_case pr72_native /var/tmp/pr72_causal_pr72_native.F
python3 - "$work_dir" "$repo_root" "$CLOUD_BAL_FC" <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

root, repo = map(Path, sys.argv[1:3])
compiler = sys.argv[3]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
result = {
    "schema": "pr72_causal_eos_graupel_absence_v1",
    "fixture": "tests/test_pr71_unit_process_integration.f90",
    "defines": ["TEST_CANDIDATE", "TEST_EOS_CONSISTENT", "TEST_ABSENT_GRAUPEL"],
    "compiler": compiler,
    "compiler_version": subprocess.run([compiler, "--version"], check=True, text=True,
                                        capture_output=True).stdout.splitlines()[0],
    "compiler_profile_sha256": sha(repo / "tests/intel_toolchain.sh"),
    "runner_sha256": sha(repo / "tests/run_pr72_causal_absence.sh"),
    "harness_sha256": sha(repo / "tests/test_pr71_unit_process_integration.f90"),
    "work_dir": str(root),
    "source_runs": {},
}
for label in ("pr70", "pr71", "pr72_native"):
    directory = root / label
    module = directory / "module_mp_kdm6.F"
    executable = directory / "test.exe"
    result["source_runs"][label] = {
        "source_sha256": sha(module),
        "object_sha256": sha(directory / "module_mp_kdm6.o"),
        "executable_sha256": sha(executable),
        "build_argv": (directory / "build.log").read_text().splitlines()[1:],
        "exit_status": int((directory / "exit_status.txt").read_text()),
        "outcome": (directory / "outcome.txt").read_text().strip(),
        "run_log_sha256": sha(directory / "run.log"),
        "run_log": str(directory / "run.log"),
    }
    if label == "pr71":
        expected = "FPE73"
    elif label in ("pr70", "pr72_native"):
        expected = "INFEASIBLE_MOMENT_STATE"
    else:
        expected = "PASS"
    if result["source_runs"][label]["outcome"] != expected:
        raise SystemExit(f"unexpected {label} outcome")
result["source_runs"]["pr71"]["failed_source_line"] = 2106
receipt = root / "causal_receipt.json"
receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(receipt)
for label, run in result["source_runs"].items():
    print(label, run["source_sha256"], run["outcome"], run["executable_sha256"])
PY
