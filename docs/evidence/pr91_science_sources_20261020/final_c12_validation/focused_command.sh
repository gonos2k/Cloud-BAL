#!/usr/bin/env bash
set -euo pipefail
repo=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr91_host_store_20261020/Cloud-BAL
out="$repo/docs/evidence/pr91_science_sources_20261020/final_c12_validation"
runroot=/var/tmp/pr91_final_c12_focused_20261020
mkdir -p "$out" "$runroot/pytest-tmp" "$runroot/joint-o0" "$runroot/joint-o2"
cd "$repo"
source tests/intel_toolchain.sh
printf 'ifx_version=%s\nifx_sha256=%s\nprofile_sha256=%s\n' "$($CLOUD_BAL_FC --version | sed -n '1p')" "$(sha256sum "$CLOUD_BAL_FC" | cut -d' ' -f1)" "$(sha256sum tests/intel_toolchain.sh | cut -d' ' -f1)" > "$out/toolchain.txt"
export TMPDIR="$runroot/pytest-tmp"
pytest -q \
  tests/test_pr91_history_response.py \
  tests/test_pr91_host_store_replay.py \
  tests/test_pr91_host_store_trace.py \
  tests/test_pr91_source_store_contract.py \
  tests/test_pr91_source_first_diffusion.py \
  tests/test_pr91_source_first_diffusion_c11.py \
  tests/test_pr90_joint_store_reason.py \
  tests/test_pr90_rain_failure_replay.py \
  tests/test_pr90_rain_final_psd.py \
  tests/test_pr90_rain_producer_trace.py \
  tests/test_pr90_rain_public_roundtrip.py \
  tests/test_pr90_warm_rain_output.py \
  tests/test_pr85_kdm6_warm_process.py \
  tests/test_pr87_cloud_public_store.py \
  tests/test_pr87_qn_density_storage.py \
  tests/test_pr87_rain_density_storage.py \
  tests/test_pr87_rain_public_store.py \
  tests/test_pr87_rain_storage_contract.py \
  tests/test_pr87_rain_volume_store.py \
  tests/test_pr87_source_storage_failures.py | tee "$out/pytest.log"
for level in o0 o2; do
  scratch="$runroot/joint-$level"
  if [[ $level == o0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  (cd "$scratch" && "$CLOUD_BAL_FC" "${flags[@]}" -module "$scratch" -I "$scratch" \
    "$repo/src/common/cloud_bal_joint_transport.f90" \
    "$repo/tests/test_joint_qnb_transport.f90" -o "$scratch/test_joint_qnb_transport" && \
    "$scratch/test_joint_qnb_transport") | tee "$out/joint_transport_${level}.log"
done
