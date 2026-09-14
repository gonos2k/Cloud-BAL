#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
fixture="$script_dir/fixtures/kdm6_wrapper"
source "$script_dir/intel_toolchain.sh"
work_dir=$(mktemp -d "$repo_root/scratch/kdm6_number_wrapper_internal.XXXXXX")
printf 'WORK_DIR %s\n' "$work_dir"
cp "$script_dir/run_kdm6_number_wrapper.sh" "$work_dir/runner_snapshot.sh"
cp "$script_dir/intel_toolchain.sh" "$work_dir/intel_toolchain.sh"
cp "$script_dir/test_kdm6_number_wrapper.f90" "$work_dir/test.f90"
cp -r "$fixture" "$work_dir/fixture"
cp "$repo_root/patches/kdm6_number_basis.patch" "$work_dir/number.patch"
cp "$repo_root/patches/kdm6_diagnostic_initialization.patch" "$work_dir/diagnostic.patch"
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
    patch --fuzz=0 -p1 < "$work_dir/number.patch" >number_patch.log 2>&1
  fi
  patch --fuzz=0 -p1 < "$work_dir/diagnostic.patch" >diagnostic_patch.log 2>&1
  if [[ $opt == O0 ]]; then
    flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  else
    flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  define=()
  [[ $label != candidate ]] || define=(-DTEST_CANDIDATE)
  [[ $label != original_unscaled ]] || define=(-DTEST_ORIGINAL_UNSCALED)
  set -x
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
  for label in candidate original_scaled original_unscaled; do
    build_one "$label" "$opt" >"$work_dir/${label}_${opt}.log" 2>&1
  done
done
python3 - "$work_dir" <<'PY'
import math
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
fields = 23
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
        if any(value <= 0.0 for value in inputs[1:]):
            raise SystemExit(f"missing positive NC/NI/NR input in {path} rho={density}")
        result[density] = (inputs, values)
    if set(result) != {0.5, 1.0, 2.0}:
        raise SystemExit(f"missing density cases in {path}: {sorted(result)}")
    return result

def close(a, b, rel=3.0e-5, abs_tol=1.0e-12):
    return abs(a - b) <= max(abs_tol, rel * max(abs(a), abs(b), 1.0e-20))

for opt in ("O0", "O2"):
    candidate = read_cases(root / f"candidate_{opt}" / "run.log")
    scaled = read_cases(root / f"original_scaled_{opt}" / "run.log")
    unscaled = read_cases(root / f"original_unscaled_{opt}" / "run.log")
    for density in (0.5, 1.0, 2.0):
        c_values = candidate[density][1]
        s_values = scaled[density][1]
        for index, (actual, expected) in enumerate(zip(c_values, s_values), 1):
            if not close(actual, expected):
                raise SystemExit(
                    f"scaled metamorphic mismatch {opt} rho={density} field={index}: "
                    f"candidate={actual:.9e} original_scaled={expected:.9e}"
                )
    # The unscaled original is a negative control.  It must agree at rho=1,
    # while at rho=.5 and 2 at least one number or radius field must differ.
    if any(not close(a, b) for a, b in zip(candidate[1.0][1], unscaled[1.0][1])):
        raise SystemExit(f"unscaled negative control unexpectedly differs at rho=1 for {opt}")
    for density in (0.5, 2.0):
        for field in (8, 9, 10):
            if close(candidate[density][1][field], unscaled[density][1][field]):
                raise SystemExit(
                    f"unscaled negative control did not change number field={field} "
                    f"at rho={density} for {opt}"
                )
    print(f"{opt} scaled wrapper metamorphic PASS; NC/NI/NR negative control is sensitive at rho=.5/2")
PY

printf 'KDM6 NUMBER WRAPPER O0/O2 SCALED METAMORPHIC PASS\n'
