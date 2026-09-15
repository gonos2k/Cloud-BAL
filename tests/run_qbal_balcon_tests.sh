#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo_root/tests/intel_toolchain.sh"
mkdir -p "$repo_root/scratch"
build_root=$(mktemp -d "$repo_root/scratch/qbal_balcon.XXXXXX")
cleanup() {
  if [[ "${CLOUD_BAL_KEEP_TEST_OUTPUT:-0}" == 1 ]]; then
    printf 'BALCON test scratch: %s\n' "$build_root"
  else
    rm -rf -- "$build_root"
  fi
}
trap cleanup EXIT
# Keep every routine after DIAGNOSE, including the complete BALCON and both
# BALSTAGGER branches. No numerical routine is replaced in this harness.
awk '/^[[:space:]]*subroutine diagnose\(/ {capture=1} capture {print}' \
  "$repo_root/src/balance/qbalpe.f" > "$build_root/qbal_core.f"
fixed_o2=()
skip_next=0
for flag in "${CLOUD_BAL_FIXED_72_FLAGS[@]}"; do
  if ((skip_next)); then skip_next=0; continue; fi
  if [[ "$flag" == -check ]]; then skip_next=1; continue; fi
  fixed_o2+=("${flag/-O0/-O2}")
done
for level in O0 O2; do
  if [[ "$level" == O0 ]]; then
    fixed_flags=("${CLOUD_BAL_FIXED_72_FLAGS[@]}")
    free_flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  else
    fixed_flags=("${fixed_o2[@]}")
    free_flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  mkdir "$build_root/$level"
  (
    cd "$build_root/$level"
    "$CLOUD_BAL_FC" -c "${free_flags[@]}" "$repo_root/src/common/cloud_bal_wind_modes.f90"
    "$CLOUD_BAL_FC" -c "${fixed_flags[@]}" "$build_root/qbal_core.f"
    for utility in move zero array_diagnosis; do
      "$CLOUD_BAL_FC" -c "${fixed_flags[@]}" "$repo_root/../klaps-v5.0_/src/lib/$utility.f"
    done
    "$CLOUD_BAL_FC" "${free_flags[@]}" "$repo_root/tests/test_qbal_balcon.f90" \
      "$repo_root/tests/test_qbal_reverse_output.f90" \
      cloud_bal_wind_modes.o qbal_core.o move.o zero.o array_diagnosis.o -o test_qbal_balcon
    ./test_qbal_balcon
  )
  printf 'Full BALCON Intel %s tests passed\n' "$level"
done
