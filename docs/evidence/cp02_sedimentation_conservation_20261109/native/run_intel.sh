#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/../../../.." && pwd)
evidence="$repo/docs/evidence/cp02_sedimentation_conservation_20261109/native"
scratch_root="${1:?pass a fresh external scratch directory}"
mkdir "$scratch_root"
cd "$scratch_root"
export TMPDIR="$scratch_root"
source "$repo/tests/intel_toolchain.sh"
printf 'compiler: '; "$CLOUD_BAL_FC" --version | head -1
sha256sum "$evidence/source/module_mp_kdm6_FIX_baseline.f90" "$evidence/source/module_mp_kdm6_FIX.f90" "$repo/patches/kdm6_conservative_sedimentation.patch"
cp "$evidence/source/module_mp_kdm6_FIX_baseline.f90" module_mp_kdm6_FIX.f90
patch --batch -p1 < "$repo/patches/kdm6_conservative_sedimentation.patch"
cmp module_mp_kdm6_FIX.f90 "$evidence/source/module_mp_kdm6_FIX.f90"
python "$evidence/run_kernel_test.py" module_mp_kdm6_FIX.f90 kernel_driver.F90
python "$evidence/run_kernel_test.py" "$evidence/source/module_mp_kdm6_FIX_baseline.f90" baseline_driver.F90 --baseline
cp "$evidence/float32_cap.F90" float32_cap.F90
for opt in O0 O2; do
  if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  printf '\n%s\n' "compile and run $opt with pinned profile"
  "$CLOUD_BAL_FC" "${flags[@]}" kernel_driver.F90 -o "kernel_$opt"
  "./kernel_$opt"
  printf "candidate %s exit 0\n" "$opt"
  "$CLOUD_BAL_FC" "${flags[@]}" baseline_driver.F90 -o "baseline_$opt"
  if "./baseline_$opt"; then
    printf "ERROR: baseline unexpectedly passed\n"; exit 1
  else
    status=$?
    printf "baseline %s exit %s (expected failure)\n" "$opt" "$status"
    [[ $status == 1 ]] || exit 1
    printf "Baseline failure expected and observed\n"
  fi
  "$CLOUD_BAL_FC" "${flags[@]}" float32_cap.F90 -o "cap_$opt"
  "./cap_$opt"
  printf "cap counterexample %s exit 0\n" "$opt"
done
