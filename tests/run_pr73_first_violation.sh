#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source_file=$repo_root/docs/evidence/pr72_combined_native_first_reject_20261008/frozen_combined_source.F
evidence_dir=${PR73_EVIDENCE_DIR:-$repo_root/docs/evidence/pr73_first_violation_20261008}
if [[ -e $evidence_dir || -L $evidence_dir ]]; then
  printf 'refusing to overwrite PR73 evidence: %s\n' "$evidence_dir" >&2
  exit 2
fi
source "$repo_root/tests/intel_toolchain.sh"
work_dir=$(mktemp -d /var/tmp/pr73_first_violation.XXXXXX)
mkdir -p "$evidence_dir"
printf 'WORK_DIR %s\n' "$work_dir"
python3 "$repo_root/tools/pr73_first_violation.py" "$source_file" \
  "$work_dir/module_mp_kdm6_first_violation.F" \
  --receipt "$work_dir/composition.json" >"$work_dir/transform.log"
python3 "$repo_root/tests/test_pr73_first_violation.py" >"$work_dir/python_test.log"

fixture=$repo_root/tests/fixtures/kdm6_wrapper
test_source=$repo_root/tests/test_pr72_species_property_state.f90
for opt in O0 O2; do
  build_dir=$work_dir/ice_mass_only_$opt
  mkdir "$build_dir"
  cp "$fixture/"*.F "$fixture/wrf_debug_stub.f90" "$build_dir/"
  cp "$test_source" "$build_dir/test_pr73_first_violation.f90"
  cp "$work_dir/module_mp_kdm6_first_violation.F" "$build_dir/module_mp_kdm6.F"
  cd "$build_dir"
  if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  compile() { "$CLOUD_BAL_FC" "${flags[@]}" "$@" >>build.log 2>&1; }
  define=(-DTEST_CANDIDATE -DTEST_EOS_CONSISTENT -DTEST_PR72_STATE_ORACLE -DTEST_ICE_MASS_ONLY)
  compile -free -fpp -c module_wrf_error.F
  compile -free -fpp -c module_model_constants.F
  compile -free -fpp -c module_mp_radar.F
  compile -free -fpp "${define[@]}" -DRWORDSIZE=4 -convert big_endian -c module_mp_kdm6.F
  "$CLOUD_BAL_FC" "${CLOUD_BAL_FIXED_FLAGS[@]}" -fixed -fpp -c libmassv.F >>build.log 2>&1
  compile -c wrf_debug_stub.f90
  compile -fpp "${define[@]}" -c test_pr73_first_violation.f90
  compile -o test.exe test_pr73_first_violation.o module_mp_kdm6.o module_mp_radar.o \
    module_model_constants.o libmassv.o wrf_debug_stub.o
  set +e
  ./test.exe >run.log 2>&1
  status=$?
  set -e
  printf '%s\n' "$status" >exit_status.txt
  if [[ $status == 0 ]]; then
    printf 'mass-only case unexpectedly passed\n' >&2
    exit 1
  fi
  grep -Fq 'KDM6_FIRST_VIOLATION|stage=KDM62D_INITIAL_PREFLIGHT|species=ice|state=mass_only' run.log
  grep -Fq '|q_unit=kg kg-1|n=' run.log
  grep -Fq '|n_unit=m-3|b=null|b_unit=m3 kg-1' run.log
  grep -Fq '|i=1|call_lat_index=0|k=1|scope_i=1:3|scope_k=1:1' run.log
  grep -Fq '|index_origin=KDM62D_dummy_bounds|j_global_mapping=unclaimed' run.log
  ! grep -q 'floating divide by zero' run.log
  grep 'KDM6_FIRST_VIOLATION' run.log >first_violation.txt
done

python3 - "$work_dir" "$repo_root" "$CLOUD_BAL_FC" "$evidence_dir" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

work, repo = map(Path, sys.argv[1:3])
compiler, evidence = sys.argv[3], Path(sys.argv[4])
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
cases = {}
for opt in ("O0", "O2"):
    case = work / f"ice_mass_only_{opt}"
    line = (case / "first_violation.txt").read_text().strip()
    cases[opt] = {
        "exit_status": int((case / "exit_status.txt").read_text()),
        "run_log": str(case / "run.log"),
        "run_log_sha256": sha(case / "run.log"),
        "first_violation_line": line,
        "executable_sha256": sha(case / "test.exe"),
        "object_sha256": sha(case / "module_mp_kdm6.o"),
    }
composition = json.loads((work / "composition.json").read_text())
receipt = {
    "schema": "pr73_first_violation_intel_receipt_v1",
    "status": "PASS_SCOPED_TEST_FIXTURE",
    "compiler": compiler,
    "source": str(repo / "docs/evidence/pr72_combined_native_first_reject_20261008/frozen_combined_source.F"),
    "source_sha256": composition["input_sha256"],
    "instrumented_source_sha256": composition["output_sha256"],
    "composition": composition["diagnostic"],
    "cases": cases,
    "limitations": [
        "Intel wrapper fixture only; no fresh partialhost native run was performed by this receipt.",
        "call_lat_index is captured from KDM62D lat; global-j mapping is unclaimed.",
        "This records a controlled state rejection, not a completed model timestep or physical validation.",
    ],
}
(evidence / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
(evidence / "composition.json").write_text(json.dumps(composition, indent=2, sort_keys=True) + "\n")
(evidence / "python_test.log").write_bytes((work / "python_test.log").read_bytes())
for opt in ("O0", "O2"):
    case = work / f"ice_mass_only_{opt}"
    (evidence / f"{opt}_first_violation.txt").write_bytes((case / "first_violation.txt").read_bytes())
print(f"PR73_FIRST_VIOLATION_EVIDENCE {evidence}")
print(f"PR73_FIRST_VIOLATION_RECEIPT_SHA256 {sha(evidence / 'receipt.json')}")
PY
