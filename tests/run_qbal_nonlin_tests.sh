#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo_root/tests/intel_toolchain.sh"

mkdir -p "$repo_root/scratch"
build_root=$(mktemp -d "$repo_root/scratch/qbal_nonlin.XXXXXX")
keep_output=${CLOUD_BAL_KEEP_TEST_OUTPUT:-0}
cleanup() {
  if [[ "$keep_output" == 1 ]]; then
    printf 'QBAL nonlinear test scratch retained: %s\n' "$build_root"
  else
    rm -rf -- "$build_root"
  fi
}
trap cleanup EXIT

python3 "$repo_root/tests/extract_qbal_nonlin_caller.py" \
  "$repo_root/src/balance/qbalpe.f" "$build_root/caller_fragment.f"
awk '
  /^[[:space:]]*subroutine nonlin\(/ {capture=1}
  capture && /^[[:space:]]*subroutine fthree\(/ {exit}
  capture {print}
' "$repo_root/src/balance/qbalpe.f" > "$build_root/nonlin.f"
test -s "$build_root/nonlin.f"
grep -Eq '^[[:space:]]*subroutine nonlin\(' "$build_root/nonlin.f"
grep -Eq '^[[:space:]]*subroutine qbal_omega_face_delta\(' "$build_root/nonlin.f"

# Runtime -check all disables ifx optimization; retain it only in O0.
fixed_o2=()
skip_next=0
for flag in "${CLOUD_BAL_FIXED_72_FLAGS[@]}"; do
  if (( skip_next )); then skip_next=0; continue; fi
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
  level_dir="$build_root/$level"
  mkdir -p "$level_dir"
  (
    cd "$level_dir"
    "$CLOUD_BAL_FC" -c "${fixed_flags[@]}" "$build_root/nonlin.f" -o nonlin.o
    "$CLOUD_BAL_FC" -c "${fixed_flags[@]}" "$build_root/caller_fragment.f" -o caller_fragment.o
    "$CLOUD_BAL_FC" "${free_flags[@]}" "$repo_root/tests/test_qbal_nonlin.f90" \
      nonlin.o -o test_qbal_nonlin
    "$CLOUD_BAL_FC" "${free_flags[@]}" "$repo_root/tests/test_qbal_nonlin_caller.f90" \
      nonlin.o caller_fragment.o -o test_qbal_nonlin_caller
    ./test_qbal_nonlin
    ./test_qbal_nonlin_caller
  )
  printf 'QBAL nonlinear Intel %s tests passed\n' "$level"
done
