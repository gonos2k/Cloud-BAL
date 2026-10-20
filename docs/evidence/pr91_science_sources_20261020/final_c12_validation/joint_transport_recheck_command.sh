#!/usr/bin/env bash
set -euo pipefail
repo=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr91_host_store_20261020/Cloud-BAL
out="$repo/docs/evidence/pr91_science_sources_20261020/final_c12_validation"
runroot=/var/tmp/pr91_c12_joint_transport_log_20261020
mkdir -p "$out" "$runroot/o0" "$runroot/o2"
cd "$repo"
source tests/intel_toolchain.sh
for level in o0 o2; do
  scratch="$runroot/$level"
  if [[ $level == o0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  (cd "$scratch" && "$CLOUD_BAL_FC" "${flags[@]}" -module "$scratch" -I "$scratch" \
    "$repo/src/common/cloud_bal_joint_transport.f90" \
    "$repo/tests/test_joint_qnb_transport.f90" -o "$scratch/test_joint_qnb_transport" && \
    "$scratch/test_joint_qnb_transport") 2>&1 | tee "$out/joint_transport_${level}_combined.log"
done
