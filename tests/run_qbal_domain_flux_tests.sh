#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo/tests/intel_toolchain.sh"
build=$(mktemp -d "$repo/../domain_flux.XXXXXX")
trap 'rm -rf "$build"' EXIT
for level in O0 O2; do
  mkdir "$build/$level"
  if [[ $level == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  (
    cd "$build/$level"
    "$CLOUD_BAL_FC" "${flags[@]}" "$repo/tests/qbal_domain_flux.f90" \
      "$repo/tests/test_qbal_domain_flux.f90" -o test_domain_flux
    ./test_domain_flux
  )
done
printf 'Pinned Intel O0/O2 domain flux checks passed in %s\n' "$build"
