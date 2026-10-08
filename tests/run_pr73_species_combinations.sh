#!/usr/bin/env bash
# Exploratory whole-KDM6 matrix probe. It currently stops at mask 5 in
# ProgB_param; this is not the independent property-stage matrix gate.
set -euo pipefail
ulimit -c 0

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source_file=${PR73_KDM6_SOURCE:-$repo_root/docs/evidence/pr72_combined_native_first_reject_20261008/frozen_combined_source.F}
native_run_dir=${PR73_NATIVE_RUN_DIR:-/var/tmp/pr72_combined_native_final_run_20261008}
evidence_path=${PR73_EVIDENCE_PATH:-$repo_root/docs/evidence/pr73_species_combinations_20261008.json}
if [[ ! -f $source_file ]]; then
  printf 'Frozen PR72 KDM6 source is required: %s\n' "$source_file" >&2
  exit 2
fi
if [[ -e $evidence_path || -L $evidence_path ]]; then
  printf 'refusing to overwrite PR73 evidence: %s\n' "$evidence_path" >&2
  exit 2
fi
trace_path=$native_run_dir/kdm6_first_call_pre.raw
wrfinput_path=$native_run_dir/wrfinput_d01
if [[ ! -f $trace_path || ! -f $wrfinput_path ]]; then
  printf 'PR72 native input trace and staged WRF input are required under %s\n' "$native_run_dir" >&2
  exit 2
fi
source "$repo_root/tests/intel_toolchain.sh"
work_dir=$(mktemp -d /var/tmp/pr73_species_combinations.XXXXXX)
printf 'WORK_DIR %s\n' "$work_dir"
fixture=$repo_root/tests/fixtures/kdm6_wrapper
test_source=$repo_root/tests/test_pr73_species_combinations.f90

build_case() (
  mask=$1
  opt=$2
  label=$(printf 'mask_%02d_%s' "$mask" "$opt")
  build_dir=$work_dir/$label
  mkdir "$build_dir"
  cp "$fixture/"*.F "$fixture/wrf_debug_stub.f90" "$build_dir/"
  cp "$test_source" "$build_dir/test_pr73_species_combinations.f90"
  cp "$source_file" "$build_dir/module_mp_kdm6.F"
  cd "$build_dir"
  if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  compile() { "$CLOUD_BAL_FC" "${flags[@]}" "$@" >>build.log 2>&1; }
  define=(-DTEST_CANDIDATE -DTEST_EOS_CONSISTENT -DTEST_PR72_STATE_ORACLE "-DPR73_MASK=$mask")
  compile -free -fpp -c module_wrf_error.F
  compile -free -fpp -c module_model_constants.F
  compile -free -fpp -c module_mp_radar.F
  compile -free -fpp "${define[@]}" -DRWORDSIZE=4 -convert big_endian -c module_mp_kdm6.F
  "$CLOUD_BAL_FC" "${CLOUD_BAL_FIXED_FLAGS[@]}" -fixed -fpp -c libmassv.F >>build.log 2>&1
  compile -c wrf_debug_stub.f90
  compile -fpp "${define[@]}" -c test_pr73_species_combinations.f90
  compile -o test.exe test_pr73_species_combinations.o module_mp_kdm6.o module_mp_radar.o module_model_constants.o libmassv.o wrf_debug_stub.o
  set +e
  ./test.exe >run.log 2>&1
  status=$?
  set -e
  printf '%s\n' "$status" >exit_status.txt
  if [[ $status != 0 ]]; then cat run.log >&2; exit 1; fi
  grep -q "PR73_COMBO $(printf '%02d' "$mask") " run.log
  grep -q 'KDM6_NUMBER_WRAPPER CANDIDATE PASS' run.log
  grep '^PR73_COMBO ' run.log >combo_rows.txt
  printf 'PASS\n' >outcome.txt
)

for opt in O0 O2; do
  for mask in $(seq 0 15); do
    build_case "$mask" "$opt"
  done
done

python3 "$repo_root/tools/pr73_native_input_pair_audit.py" \
  --trace "$trace_path" --wrfinput "$wrfinput_path" --source "$source_file" \
  --output "$work_dir/native_first_unpaired.json" >"$work_dir/native_audit.log"

python3 - "$work_dir" "$repo_root" "$CLOUD_BAL_FC" "$source_file" "$evidence_path" "$trace_path" "$wrfinput_path" <<'PY'
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

root, repo = map(Path, sys.argv[1:3])
compiler, source_file, evidence_path = sys.argv[3], Path(sys.argv[4]), Path(sys.argv[5])
trace_path, wrfinput_path = map(Path, sys.argv[6:8])
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
source_hash = sha(source_file)
if source_hash != "1fbd9d5cbc32dc5772682078b4efc63b3dafb28a79499e318faf9520fc55e819":
    raise SystemExit(f"frozen PR72 source hash mismatch: {source_hash}")
cases = {}
for opt in ("O0", "O2"):
    for mask in range(16):
        label = f"mask_{mask:02d}_{opt}"
        directory = root / label
        rows = (directory / "combo_rows.txt").read_text().splitlines()
        if len(rows) != 1:
            raise SystemExit(f"expected one EOS-consistent density row in {label}")
        for row in rows:
            fields = row.split()
            if len(fields) != 30 or fields[0] != "PR73_COMBO" or int(fields[1]) != mask:
                raise SystemExit(f"invalid combo row in {label}: {row}")
            values = [float(value) for value in fields[2:]]
            if not all(math.isfinite(value) for value in values):
                raise SystemExit(f"nonfinite returned state in {label}")
        cases[label] = {
            "mask": mask,
            "present": {name: bool(mask & bit) for name, bit in
                        (("rain", 1), ("cloud", 2), ("ice", 4), ("graupel", 8))},
            "source_sha256": sha(directory / "module_mp_kdm6.F"),
            "object_sha256": sha(directory / "module_mp_kdm6.o"),
            "executable_sha256": sha(directory / "test.exe"),
            "exit_status": int((directory / "exit_status.txt").read_text()),
            "outcome": (directory / "outcome.txt").read_text().strip(),
            "run_log_sha256": sha(directory / "run.log"),
            "run_log": str(directory / "run.log"),
        }
result = {
    "schema": "pr73_species_property_combinations_v1",
    "classification": "KDM6 local full-module property-state matrix; not a native host or scientific validation",
    "source": str(source_file),
    "source_sha256": source_hash,
    "test_source_sha256": sha(repo / "tests/test_pr73_species_combinations.f90"),
    "runner_sha256": sha(repo / "tests/run_pr73_species_combinations.sh"),
    "toolchain_profile_sha256": sha(repo / "tests/intel_toolchain.sh"),
    "compiler": compiler,
    "compiler_version": subprocess.run([compiler, "--version"], check=True,
                                         text=True, capture_output=True).stdout.splitlines()[0],
    "work_dir": str(root),
    "native_first_unpaired_audit": json.loads((root / "native_first_unpaired.json").read_text()),
    "native_artifact_hashes": {"first_call_pre_trace_sha256": sha(trace_path),
                               "staged_wrfinput_sha256": sha(wrfinput_path)},
    "optimization_profiles": ["O0", "O2"],
    "matrix": {"bit_order": ["rain", "cloud", "ice", "graupel"],
               "combination_count": 16, "cases_per_optimization": 16},
    "cases": cases,
    "limitations": [
        "Property absence means an exact-zero mass/moment pair at the KDM6 interface.",
        "The test does not identify the upstream producer of the native QI/NI mismatch.",
        "Graupel density outside 100-900 kg m-3 remains unresolved.",
    ],
}
receipt = root / "species_combinations_validation.json"
receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
evidence_path.parent.mkdir(parents=True, exist_ok=True)
evidence_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print("PR73_FULL_KDM6_COMBINATION_MATRIX_PASS")
print("PR73_RECEIPT", receipt)
print("PR73_EVIDENCE", evidence_path)
PY
