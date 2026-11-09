#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/../../../.." && pwd)
evidence="$repo/docs/evidence/cp02_first_ice_velocity_20261109/native"
scratch="${1:?pass a fresh external scratch directory}"
mkdir "$scratch"
scratch=$(cd "$scratch" && pwd)
case "$scratch/" in "$repo/"*) echo 'scratch must be outside checkout' >&2; exit 2;; esac
export TMPDIR="$scratch"
source "$repo/tests/intel_toolchain.sh"
cd "$scratch"
printf 'compiler: '; "$CLOUD_BAL_FC" --version | head -1
sha256sum "$evidence/source/"*.f90 "$repo/patches/kdm6_first_ice_velocity.patch"
cp "$evidence/source/module_mp_kdm6_FIX_control.f90" module_mp_kdm6_FIX.f90
patch --batch -p1 < "$repo/patches/kdm6_first_ice_velocity.patch"
cmp module_mp_kdm6_FIX.f90 "$evidence/source/module_mp_kdm6_FIX_new.f90"
python "$evidence/run_kernel_test.py" module_mp_kdm6_FIX.f90 kernel.F90
python "$evidence/make_coupled.py" module_mp_kdm6_FIX.f90 coupled.F90 slope_module.f90
inputs=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_grouped_forecast_20261105/runtime/native_build/inputs
for opt in O0 O2; do
 mkdir "$opt"; cd "$opt"
 if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
 "$CLOUD_BAL_FC" "${flags[@]}" ../kernel.F90 -o kernel
 ./kernel
 "$CLOUD_BAL_FC" "${flags[@]}" -free -fpp -c ../slope_module.f90 > module.log 2>&1
 "$CLOUD_BAL_FC" "${flags[@]}" ../coupled.F90 slope_module.o -o coupled > link.log 2>&1
 ./coupled
 printf '%s PASS\n' "$opt"
 cd ..
done
