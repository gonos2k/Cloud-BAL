#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
source "$root/tests/intel_toolchain.sh"
build=$(mktemp -d "$root/../moment-handoff-test.XXXXXX")
trap 'rm -rf "$build"' EXIT
cd "$build"
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  "$root/src/common/cloud_bal_state.f90" \
  "$root/src/common/cloud_bal_microphysics_initialization.f90" \
  "$root/tools/model_moment_driver.f90" -o model_moment_driver
MODEL_MOMENT_DRIVER="$build/model_moment_driver" \
  python3 -m unittest discover -s "$root/tests" -p test_initialize_model_moments.py
