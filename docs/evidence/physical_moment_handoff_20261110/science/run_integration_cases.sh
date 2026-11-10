#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
work=$(mktemp -d "$repo/../cloud-bal-physical-cases.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
source "$repo/tests/intel_toolchain.sh"
for mode in audit repro; do
  mkdir "$work/$mode"
  cd "$work/$mode"
  if [[ $mode == audit ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  "$CLOUD_BAL_FC" "${flags[@]}" "$repo/src/common/cloud_bal_state.f90" \
    "$repo/src/common/cloud_bal_column_physics.f90" \
    "$repo/src/common/cloud_bal_microphysics_initialization.f90" \
    "$repo/docs/evidence/physical_moment_handoff_20261110/science/integration_cases.f90" -o integration_cases
  printf '%s: ' "$mode"
  ./integration_cases
done
