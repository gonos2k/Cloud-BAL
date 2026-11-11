#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
test_tmp=$(mktemp -d "${CLOUD_BAL_TEST_SCRATCH_ROOT:-/var/tmp}/phase-consumer.XXXXXX")
trap 'rm -rf "$test_tmp"' EXIT
. "$repo_root/tests/intel_toolchain.sh"
cd "$test_tmp"
python3 "$repo_root/tests/source_extract_phase_consumer.py" \
  "$repo_root/docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90" native_slope.f90
for profile in checked optimized; do
  flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  [[ $profile != optimized ]] || flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  mkdir "$profile"
  cd "$profile"
  "$CLOUD_BAL_FC" "${flags[@]}" -module . -I . \
    "$repo_root/src/common/cloud_bal_state.f90" \
    "$repo_root/src/common/cloud_bal_column_physics.f90" \
    "$repo_root/src/common/cloud_bal_phase_moments.f90" \
    "$repo_root/tests/test_phase_moments.f90" -o test_phase_moments
  ./test_phase_moments
  "$CLOUD_BAL_FC" "${flags[@]}" -module . -I . \
    "$repo_root/src/common/cloud_bal_state.f90" \
    "$repo_root/src/common/cloud_bal_column_physics.f90" \
    "$repo_root/src/common/cloud_bal_phase_moments.f90" \
    "$repo_root/src/common/cloud_bal_microphysics_initialization.f90" \
    "$repo_root/tests/test_phase_initialization_chain.f90" -o test_phase_initialization_chain
  ./test_phase_initialization_chain
  "$CLOUD_BAL_FC" "${flags[@]}" -module . -I . ../native_slope.f90 \
    "$repo_root/tests/test_phase_consumer_native.f90" -o test_phase_consumer_native
  ./test_phase_consumer_native
  cd ..
done
