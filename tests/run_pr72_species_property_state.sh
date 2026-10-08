#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source_file=${PR72_KDM6_SOURCE:-/var/tmp/pr72_causal_pr72_native.F}
evidence_path=${PR72_EVIDENCE_PATH:-$repo_root/docs/evidence/pr72_species_property_state_20261008.json}
if [[ ! -f $source_file ]]; then
  printf 'PR72 native-fixed KDM6 source is required: %s\n' "$source_file" >&2
  exit 2
fi
if [[ -e $evidence_path || -L $evidence_path ]]; then
  printf 'refusing to overwrite PR72 evidence: %s\n' "$evidence_path" >&2
  exit 2
fi
source "$repo_root/tests/intel_toolchain.sh"
work_dir=$(mktemp -d /var/tmp/pr72_species_state.XXXXXX)
printf 'WORK_DIR %s\n' "$work_dir"
python3 "$repo_root/tools/pr72_species_property_state.py" \
  "$source_file" "$work_dir/module_mp_kdm6_properties.F" \
  --receipt "$work_dir/species_state.composition.json" >"$work_dir/transform.log"
fixture=$repo_root/tests/fixtures/kdm6_wrapper
test_source=$repo_root/tests/test_pr72_species_property_state.f90

build_case() (
  label=$1
  module_source=$2
  defines=$3
  expect=$4
  opt=$5
  build_dir=$work_dir/${label}_${opt}
  mkdir "$build_dir"
  cp "$fixture/"*.F "$fixture/wrf_debug_stub.f90" "$build_dir/"
  cp "$test_source" "$build_dir/test_pr72_species_property_state.f90"
  cp "$module_source" "$build_dir/module_mp_kdm6.F"
  cd "$build_dir"
  if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  compile() { "$CLOUD_BAL_FC" "${flags[@]}" "$@" >>build.log 2>&1; }
  define=(-DTEST_CANDIDATE -DTEST_EOS_CONSISTENT -DTEST_PR72_STATE_ORACLE)
  for macro in $defines; do define+=("-D$macro"); done
  compile -free -fpp -c module_wrf_error.F
  compile -free -fpp -c module_model_constants.F
  compile -free -fpp -c module_mp_radar.F
  compile -free -fpp "${define[@]}" -DRWORDSIZE=4 -convert big_endian -c module_mp_kdm6.F
  "$CLOUD_BAL_FC" "${CLOUD_BAL_FIXED_FLAGS[@]}" -fixed -fpp -c libmassv.F >>build.log 2>&1
  compile -c wrf_debug_stub.f90
  compile -fpp "${define[@]}" -c test_pr72_species_property_state.f90
  compile -o test.exe test_pr72_species_property_state.o module_mp_kdm6.o module_mp_radar.o module_model_constants.o libmassv.o wrf_debug_stub.o
  set +e
  ./test.exe >run.log 2>&1
  status=$?
  set -e
  printf '%s\n' "$status" >exit_status.txt
  case "$expect" in
    pass)
      if [[ $status != 0 ]]; then cat run.log >&2; exit 1; fi
      grep -q 'KDM6_NUMBER_WRAPPER CANDIDATE PASS' run.log
      grep '^INPUT ' run.log >input_rows.txt
      printf 'PASS\n' >outcome.txt
      ;;
    mass_only)
      if [[ $status == 0 ]] || ! grep -Fq 'KDM6 unsupported positive mass without number/volume state' run.log; then
        printf 'mass-only state did not fail at preflight\n' >&2; cat run.log >&2; exit 1
      fi
      if grep -q 'floating divide by zero' run.log; then exit 1; fi
      printf 'UNSUPPORTED_MASS_ONLY_REJECTED_BEFORE_PSD\n' >outcome.txt
      ;;
    orphan)
      if [[ $status == 0 ]] || ! grep -Fq 'KDM6 orphan number/volume state without positive mass' run.log; then
        printf 'number-only state did not fail at preflight\n' >&2; cat run.log >&2; exit 1
      fi
      if grep -q 'floating divide by zero' run.log; then exit 1; fi
      printf 'NUMBER_ONLY_ORPHAN_REJECTED_BEFORE_PSD\n' >outcome.txt
      ;;
    invalid)
      if [[ $status == 0 ]] || ! grep -Fq 'KDM6 invalid nonfinite or negative species state' run.log; then
        printf 'negative/nonfinite species state did not fail at preflight\n' >&2; cat run.log >&2; exit 1
      fi
      if grep -q 'floating divide by zero' run.log; then exit 1; fi
      printf 'INVALID_NEGATIVE_OR_NONFINITE_REJECTED_BEFORE_PSD\n' >outcome.txt
      ;;
    *) printf 'unknown expectation: %s\n' "$expect" >&2; exit 2 ;;
  esac
)

for opt in O0 O2; do
  build_case pr72_baseline_active "$source_file" '' pass "$opt"
  build_case pr72_properties_active "$work_dir/module_mp_kdm6_properties.F" '' pass "$opt"
  build_case pr72_clear_all "$work_dir/module_mp_kdm6_properties.F" TEST_CLEAR_WHOLEMODULE pass "$opt"
  build_case pr72_absent_cloud "$work_dir/module_mp_kdm6_properties.F" TEST_ABSENT_CLOUD pass "$opt"
  build_case pr72_absent_ice "$work_dir/module_mp_kdm6_properties.F" TEST_ABSENT_ICE pass "$opt"
  build_case pr72_absent_rain "$work_dir/module_mp_kdm6_properties.F" TEST_ABSENT_RAIN pass "$opt"
  build_case pr72_mass_only "$work_dir/module_mp_kdm6_properties.F" TEST_ICE_MASS_ONLY mass_only "$opt"
  build_case pr72_number_only "$work_dir/module_mp_kdm6_properties.F" TEST_ICE_NUMBER_ORPHAN orphan "$opt"
  build_case pr72_negative_mass "$work_dir/module_mp_kdm6_properties.F" TEST_ICE_NEGATIVE_MASS invalid "$opt"
  build_case pr72_nonfinite_mass "$work_dir/module_mp_kdm6_properties.F" TEST_ICE_NONFINITE_MASS invalid "$opt"
done

python3 - "$work_dir" "$repo_root" "$CLOUD_BAL_FC" "$source_file" "$evidence_path" <<'PY'
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

root, repo = map(Path, sys.argv[1:3])
compiler, source_file, evidence_path = sys.argv[3], Path(sys.argv[4]), Path(sys.argv[5])
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
for opt in ("O0", "O2"):
    base = (root / f"pr72_baseline_active_{opt}" / "input_rows.txt").read_text().splitlines()
    updated = (root / f"pr72_properties_active_{opt}" / "input_rows.txt").read_text().splitlines()
    if len(base) != 1 or base != updated:
        raise SystemExit(f"active source outputs differ at {opt}")
    fields = base[0].split()
    if len(fields) != 29 or not all(math.isfinite(float(value)) for value in fields[1:]):
        raise SystemExit(f"invalid active output row at {opt}")

result = {
  "schema": "pr72_species_property_state_validation_v1",
  "input_source": str(source_file),
  "input_source_sha256": sha(source_file),
  "properties_source_sha256": sha(root / "module_mp_kdm6_properties.F"),
  "transform_sha256": sha(repo / "tools/pr72_species_property_state.py"),
  "driver_sha256": sha(repo / "tests/test_pr72_species_property_state.f90"),
  "runner_sha256": sha(repo / "tests/run_pr72_species_property_state.sh"),
  "compiler": compiler,
  "compiler_version": subprocess.run([compiler,"--version"],check=True,text=True,capture_output=True).stdout.splitlines()[0],
  "compiler_profile_sha256": sha(repo / "tests/intel_toolchain.sh"),
  "work_dir": str(root),
  "optimization_profiles": ["O0", "O2"],
  "cases": {}
}
for opt in ("O0", "O2"):
  for label in ("pr72_baseline_active","pr72_properties_active","pr72_clear_all","pr72_absent_cloud","pr72_absent_ice","pr72_absent_rain","pr72_mass_only","pr72_number_only","pr72_negative_mass","pr72_nonfinite_mass"):
    directory=root/f"{label}_{opt}"
    result["cases"][f"{label}_{opt}"]={
      "source_sha256":sha(directory/"module_mp_kdm6.F"),
      "object_sha256":sha(directory/"module_mp_kdm6.o"),
      "executable_sha256":sha(directory/"test.exe"),
      "exit_status":int((directory/"exit_status.txt").read_text()),
      "outcome":(directory/"outcome.txt").read_text().strip(),
      "run_log_sha256":sha(directory/"run.log"),
      "run_log":str(directory/"run.log"),
    }
receipt=root/"species_state_validation.json"
receipt.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
evidence_path.parent.mkdir(parents=True, exist_ok=True)
evidence_path.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
print("PR72_ACTIVE_OUTPUTS_PRESERVED")
print("PR72_WHOLEMODULE_CLEAR_EXACT_ZERO_PASS")
print("PR72_ABSENT_CLOUD_ICE_RAIN_EXACT_ZERO_PAIRS_PASS")
print("PR72_MASS_ONLY_AND_NUMBER_ONLY_REJECTED_BEFORE_PSD")
print("PR72_INVALID_NEGATIVE_AND_NONFINITE_REJECTED_BEFORE_PSD")
print(receipt)
print(evidence_path)
PY
