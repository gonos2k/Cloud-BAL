#!/usr/bin/env bash
set -euo pipefail
repo=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr91_host_store_20261020/Cloud-BAL
cd /var/tmp/pr91_c12_t3_source_replay_20261020
. "$repo/tests/intel_toolchain.sh"
for level in O0 O2; do
  if [[ $level == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  "$CLOUD_BAL_FC" "${flags[@]}" -free store_module.f90 driver.f90 -o "$level.exe"
  "./$level.exe" | tee "$level.txt"
done
