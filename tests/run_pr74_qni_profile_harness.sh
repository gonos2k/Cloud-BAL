#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_root/tests/intel_toolchain.sh"
source_file=/var/tmp/pr73_pbl_research/source_after/module_bl_shinhong_pr65.F
expected_source_sha=5fbe821bb3b82e406fee459e5b2d745156ea1a030b5f0ecd2c7191025f296553
actual_source_sha=$(sha256sum "$source_file" | cut -d' ' -f1)
if [[ $actual_source_sha != $expected_source_sha ]]; then printf 'unexpected research source hash: %s\n' "$actual_source_sha" >&2; exit 2; fi
work_root=$(mktemp -d /var/tmp/pr74_qni_profile_harness.XXXXXX)
printf 'WORK_ROOT %s\n' "$work_root"
for opt in O0 O2; do
  build=$work_root/$opt; mkdir "$build"
  cp "$source_file" "$build/module_bl_shinhong.F"
  cp "$repo_root/tests/fixtures/kdm6_wrapper/module_wrf_error.F" \
     "$repo_root/tests/fixtures/kdm6_wrapper/module_model_constants.F" \
     "$repo_root/tests/fixtures/kdm6_wrapper/wrf_debug_stub.f90" \
     "$repo_root/tests/test_pr74_shinhong_qni_driver.f90" "$build/"
  cd "$build"
  if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  "$CLOUD_BAL_FC" "${flags[@]}" -free -fpp -c module_wrf_error.F module_model_constants.F >build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -free -fpp -c module_bl_shinhong.F >>build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -c wrf_debug_stub.f90 >>build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -c test_pr74_shinhong_qni_driver.f90 >>build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -o test.exe test_pr74_shinhong_qni_driver.o module_bl_shinhong.o module_model_constants.o wrf_debug_stub.o >>build.log 2>&1
  ./test.exe | tee run.log
  sha256sum module_bl_shinhong.o test.exe build.log run.log
done
