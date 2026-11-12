#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$root/tests/intel_toolchain.sh"
test_tmp=$(mktemp -d "$root/../ice-background-prior.XXXXXXXX")
trap 'rm -rf "$test_tmp"' EXIT
cd "$test_tmp"
for profile in audit repro; do
  if [[ $profile == audit ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  mkdir "$test_tmp/$profile"
  cd "$test_tmp/$profile"
  "$CLOUD_BAL_FC" "${flags[@]}" -c "$root/src/common/cloud_bal_state.f90" \
    "$root/src/common/cloud_bal_microphysics_initialization.f90"
  for test_name in test_ice_background_prior test_ice_snow_initialization test_microphysics_initialization; do
    "$CLOUD_BAL_FC" "${flags[@]}" cloud_bal_state.o cloud_bal_microphysics_initialization.o \
      "$root/tests/$test_name.f90" -o "$test_name"
    "./$test_name"
  done
  for driver in ice_background_driver model_moment_driver; do
    "$CLOUD_BAL_FC" "${flags[@]}" cloud_bal_state.o cloud_bal_microphysics_initialization.o \
      "$root/tools/$driver.f90" -o "$driver"
  done
  ICE_BACKGROUND_DRIVER="$PWD/ice_background_driver" MODEL_MOMENT_DRIVER="$PWD/model_moment_driver" \
    python3 -m unittest discover -s "$root/tests" -p test_ice_background_prior.py -v
  MODEL_MOMENT_DRIVER="$PWD/model_moment_driver" \
    python3 -m unittest discover -s "$root/tests" -p test_initialize_model_moments.py -v
done
