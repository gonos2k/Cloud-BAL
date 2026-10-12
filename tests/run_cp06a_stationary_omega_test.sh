#!/usr/bin/env bash
# Focused pinned-Intel checks for the stationary continuity omega producer.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=${CLOUD_BAL_WORKSPACE_ROOT:-/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50}
scratch_root=${CLOUD_BAL_TEST_SCRATCH_ROOT:-$workspace_root/Cloud-BAL/scratch}
mkdir -p "$scratch_root"
run_root=$(mktemp -d "$scratch_root/cp06a_stationary_omega_test.XXXXXX")
printf 'focused test directory: %s\n' "$run_root"
. "$repo_root/tests/intel_toolchain.sh"

source_files=("$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/src/common/cloud_bal_grid_geometry.f90" \
  "$repo_root/src/common/cloud_bal_balance_operator.f90" \
  "$repo_root/tests/test_stationary_omega_diagnosis.f90")

run_profile() {
  local profile=$1
  local -n flags=$2
  local build_dir="$run_root/$profile"
  mkdir -p "$build_dir"
  "$CLOUD_BAL_FC" "${flags[@]}" -module "$build_dir" -I "$build_dir" \
    "${source_files[@]}" -o "$build_dir/test.exe" >"$build_dir/build.log" 2>&1
  "$build_dir/test.exe" >"$build_dir/test.log" 2>&1
  cat "$build_dir/test.log"
  sha256sum "$build_dir/test.exe" >"$build_dir/executable.sha256"
}

run_profile O0 CLOUD_BAL_FREE_FLAGS
run_profile O2 CLOUD_BAL_REPRO_FLAGS
{
  printf 'compiler='; "$CLOUD_BAL_FC" --version 2>&1 | sed -n '1p'
  printf 'compiler_sha256='; sha256sum "$CLOUD_BAL_FC" | cut -d' ' -f1
  printf 'setvars_sha256='; sha256sum /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/setvars.sh | cut -d' ' -f1
  sha256sum "${source_files[@]}" "$repo_root/tests/run_cp06a_stationary_omega_test.sh"
  for profile in O0 O2; do cat "$run_root/$profile/executable.sha256"; done
} | tee "$run_root/receipt.txt"
printf 'receipt=%s\n' "$run_root/receipt.txt"
