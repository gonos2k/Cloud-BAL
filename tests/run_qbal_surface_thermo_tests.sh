#!/usr/bin/env bash
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo/tests/intel_toolchain.sh"
mkdir -p "$repo/scratch"
build=$(mktemp -d "$repo/scratch/surface_thermo.XXXXXX")
for level in O0 O2; do
  mkdir "$build/$level"
  if [[ $level == O0 ]]; then
    flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  else
    flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  (
    cd "$build/$level"
    # Build the canonical state module first so this research kernel always
    # resolves the public moist_gas_density implementation from source.
    "$CLOUD_BAL_FC" "${flags[@]}" -module "$PWD" -I "$PWD" -c \
      "$repo/src/common/cloud_bal_state.f90" -o cloud_bal_state.o
    "$CLOUD_BAL_FC" "${flags[@]}" -module "$PWD" -I "$PWD" -c \
      "$repo/tests/qbal_surface_thermo.f90" -o qbal_surface_thermo.o
    "$CLOUD_BAL_FC" "${flags[@]}" -module "$PWD" -I "$PWD" \
      cloud_bal_state.o qbal_surface_thermo.o \
      "$repo/tests/qbal_lower_transport.f90" \
      "$repo/tests/test_qbal_surface_thermo.f90" -o test_qbal_surface_thermo
    ./test_qbal_surface_thermo
  )
done
printf 'Pinned Intel O0/O2 evidence: %s\n' "$build"
