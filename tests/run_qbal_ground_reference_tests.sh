#!/usr/bin/env bash
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo/tests/intel_toolchain.sh"
mkdir -p "$repo/scratch"
build=$(mktemp -d "$repo/scratch/ground_reference.XXXXXX")

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
      "$repo/tests/qbal_thickness_attribution.f90" -o qbal_thickness_attribution.o
    "$CLOUD_BAL_FC" "${flags[@]}" -module "$PWD" -I "$PWD" -c \
      "$repo/tests/qbal_ground_reference.f90" -o qbal_ground_reference.o
    "$CLOUD_BAL_FC" "${flags[@]}" -module "$PWD" -I "$PWD" \
      qbal_thickness_attribution.o qbal_ground_reference.o \
      "$repo/tests/test_qbal_ground_reference.f90" -o test_qbal_ground_reference
    ./test_qbal_ground_reference
  )
done

printf 'Pinned Intel O0/O2 ground-reference evidence: %s\n' "$build"
