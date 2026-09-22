#!/usr/bin/env bash
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo/tests/intel_toolchain.sh"
mkdir -p "$repo/scratch"
build=$(mktemp -d "$repo/scratch/relative_pressure_force.XXXXXX")

for level in O0 O2; do
  mkdir "$build/$level"
  if [[ $level == O0 ]]; then
    flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  else
    flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  (
    cd "$build/$level"
    "$CLOUD_BAL_FC" "${flags[@]}" -module "$PWD" -I "$PWD" -c \
      "$repo/tests/qbal_relative_pressure_force.f90" \
      -o qbal_relative_pressure_force.o
    "$CLOUD_BAL_FC" "${flags[@]}" -module "$PWD" -I "$PWD" \
      qbal_relative_pressure_force.o \
      "$repo/tests/test_qbal_relative_pressure_force.f90" \
      -o test_qbal_relative_pressure_force
    ./test_qbal_relative_pressure_force
  )
done

printf 'Pinned Intel O0/O2 evidence: %s\n' "$build"
