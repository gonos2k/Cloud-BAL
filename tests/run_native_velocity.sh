#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo_root/tests/intel_toolchain.sh"

build_dir=$(mktemp -d "$repo_root/scratch/native_velocity_build.XXXXXX")
trap 'rm -rf -- "$build_dir"' EXIT

(
  cd "$build_dir"
  "$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
    -module "$build_dir" -I "$build_dir" \
    "$repo_root/src/common/cloud_bal_native_velocity.f90" \
    "$repo_root/tests/test_native_velocity.f90" \
    -o "$build_dir/test_native_velocity_o0"
)
"$build_dir/test_native_velocity_o0"

o2_dir="$build_dir/o2"
mkdir -p "$o2_dir"
(
  cd "$o2_dir"
  "$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" \
    -module "$o2_dir" -I "$o2_dir" \
    "$repo_root/src/common/cloud_bal_native_velocity.f90" \
    "$repo_root/tests/test_native_velocity.f90" \
    -o "$o2_dir/test_native_velocity_o2"
)
"$o2_dir/test_native_velocity_o2"

printf '%s\n' 'Native velocity Intel O0/O2 tests passed'
