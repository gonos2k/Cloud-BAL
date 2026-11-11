#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$root/tests/intel_toolchain.sh"
test_tmp=$(mktemp -d "${TMPDIR:-/tmp}/ice-snow-initialization.XXXXXXXX")
trap 'rm -rf "$test_tmp"' EXIT
cd "$test_tmp"
for profile in audit repro; do
  if [[ $profile == audit ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  "$CLOUD_BAL_FC" "${flags[@]}" "$root/src/common/cloud_bal_state.f90" \
    "$root/src/common/cloud_bal_microphysics_initialization.f90" \
    "$root/tests/test_ice_snow_initialization.f90" -o "$test_tmp/test_$profile"
  "$test_tmp/test_$profile"
done
