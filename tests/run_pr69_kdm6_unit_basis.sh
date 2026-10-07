#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
fixture="$script_dir/fixtures/kdm6_wrapper"
source "$script_dir/intel_toolchain.sh"
work_dir=$(mktemp -d /var/tmp/pr69_kdm6_unit_basis.XXXXXX)
printf 'WORK_DIR %s\n' "$work_dir"
cp "$script_dir/intel_toolchain.sh" "$work_dir/intel_toolchain.sh"
cp "$script_dir/test_pr69_kdm6_unit_basis.f90" "$work_dir/test.f90"
cp "$repo_root/patches/kdm6_unit_basis_pr69.patch" "$work_dir/unit_basis.patch"
cp -r "$fixture" "$work_dir/fixture"
python3 - "$work_dir/fixture" <<'VERIFY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1])
for name,record in json.loads((root/'origin.json').read_text())['files'].items():
    if hashlib.sha256((root/name).read_bytes()).hexdigest()!=record['sha256']:
        raise SystemExit('fixture hash mismatch: '+name)
VERIFY
build_one() (
  label=$1
  opt=$2
  build_dir="$work_dir/${label}_${opt}"
  mkdir "$build_dir"
  cd "$build_dir"
  pwd > build_cwd.log
  cp "$work_dir/fixture/"*.F .
  cp "$work_dir/fixture/wrf_debug_stub.f90" .
  cp "$work_dir/test.f90" .
  if [[ $label == candidate ]]; then
    patch --fuzz=0 -p1 < "$work_dir/unit_basis.patch" >unit_basis_patch.log 2>&1
  fi
  if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  define=()
  [[ $label != candidate ]] || define=(-DTEST_CANDIDATE)
  if [[ $label != candidate && $opt == O0 ]]; then define+=(-DTEST_REFERENCE_O0); fi
  if [[ $label == original_scaled && $opt == O2 ]]; then define+=(-DTEST_REFERENCE_ALL); fi
  [[ $label != original_unscaled ]] || define+=(-DTEST_ORIGINAL_UNSCALED)
  "$CLOUD_BAL_FC" "${flags[@]}" -free -fpp -c module_wrf_error.F
  "$CLOUD_BAL_FC" "${flags[@]}" -free -fpp -c module_model_constants.F
  "$CLOUD_BAL_FC" "${flags[@]}" -free -fpp -c module_mp_radar.F
  "$CLOUD_BAL_FC" "${flags[@]}" -free -fpp -DRWORDSIZE=4 -convert big_endian -c module_mp_kdm6.F
  "$CLOUD_BAL_FC" "${flags[@]}" -fixed -fpp -c libmassv.F
  "$CLOUD_BAL_FC" "${flags[@]}" -c wrf_debug_stub.f90
  "$CLOUD_BAL_FC" "${flags[@]}" -fpp "${define[@]}" -c test.f90
  "$CLOUD_BAL_FC" "${flags[@]}" -o test.exe test.o module_mp_kdm6.o module_mp_radar.o module_model_constants.o libmassv.o wrf_debug_stub.o
  ./test.exe >run.log 2>&1
)
for opt in O0 O2; do
  build_one candidate "$opt" >"$work_dir/candidate_${opt}.log" 2>&1
done
for label in original_scaled original_unscaled; do
  build_one "$label" O0 >"$work_dir/${label}_O0.log" 2>&1
done
if build_one original_scaled O2 >"$work_dir/original_scaled_O2.log" 2>&1; then
  printf 'ORIGINAL_SCALED_O2 all-density baseline PASS\n'
else
  first_input=$(sed -n '/^INPUT /{p;q;}' "$work_dir/original_scaled_O2/run.log")
  error_line=$(grep -m1 'forrtl: error' "$work_dir/original_scaled_O2/run.log" || true)
  source_line=$(grep -m1 'kdm62d.*module_mp_kdm6.F' "$work_dir/original_scaled_O2/run.log" || true)
  printf 'ORIGINAL_SCALED_O2 baseline FAIL_OPEN\n%s\n%s\n%s\n' "$first_input" "$error_line" "$source_line"
fi
python3 - "$work_dir" <<'PY'
import math
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
fields = 23
densities = (0.25, 0.5, 1.0, 2.0)
reference_densities = (0.25, 0.5, 1.0, 2.0)
def read_cases(path):
    result = {}
    for line in path.read_text().splitlines():
        parts = line.split()
        if not parts or parts[0] != "INPUT":
            continue
        if len(parts) != 2 + 4 + fields:
            raise SystemExit(f"unexpected field count in {path}: {len(parts)}")
        density = float(parts[1])
        inputs = [float(value) for value in parts[2:6]]
        values = [float(value) for value in parts[6:]]
        if not all(math.isfinite(value) for value in inputs + values):
            raise SystemExit(f"non-finite parsed output in {path}")
        result[density] = (inputs, values)
    expected_densities = densities if path.parent.name.startswith("candidate") or path.parent.name.endswith("_O0") else reference_densities[1:]
    if set(result) != set(expected_densities):
        raise SystemExit(f"missing density cases in {path}: {sorted(result)}")
    return result

def close(a, b, rel=3.0e-5, abs_tol=1.0e-12):
    return abs(a - b) <= max(abs_tol, rel * max(abs(a), abs(b), 1.0e-20))

candidate_o0 = read_cases(root / "candidate_O0" / "run.log")
candidate_o2 = read_cases(root / "candidate_O2" / "run.log")
scaled = read_cases(root / "original_scaled_O0" / "run.log")
unscaled = read_cases(root / "original_unscaled_O0" / "run.log")
for density in reference_densities:
    for index, (actual, expected) in enumerate(zip(candidate_o0[density][1][7:11], scaled[density][1][7:11]), 8):
        if not close(actual, expected):
            raise SystemExit(f"converted-vs-volumetric number mismatch O0 rho={density} field={index}: {actual} vs {expected}")
for density in densities:
    for index, (actual, expected) in enumerate(zip(candidate_o2[density][1], candidate_o0[density][1]), 1):
        if not close(actual, expected):
            raise SystemExit(f"O0/O2 candidate mismatch rho={density} field={index}: {actual} vs {expected}")
for index, (actual, expected) in enumerate(zip(candidate_o0[1.0][1][7:11], unscaled[1.0][1][7:11]), 8):
    if not close(actual, expected):
        raise SystemExit(f"direct-copy control mismatch at rho=1 field={index}")
for density in (0.25, 0.5, 2.0):
    if not any(not close(candidate_o0[density][1][index], unscaled[density][1][index]) for index in (7,8,9,10)):
        raise SystemExit(f"direct-copy negative control insensitive at rho={density}")
if close(candidate_o0[0.25][1][13], scaled[0.25][1][13]):
    raise SystemExit("mixed-carrier cloud-radius mismatch was not detected")
print("number conversion/helper checks PASS; direct-copy negative control PASS")
print("mixed-carrier KDM closure correctly FAIL_OPEN: cloud radius differs at rho_dry=0.25")
print("see ORIGINAL_SCALED_O2 status above; no density case is silently omitted from its executable")
PY
printf 'PR69 KDM6 UNIT BASIS EVIDENCE COMPLETE; PHYSICAL UNIT CLOSURE FAIL_OPEN\n'
