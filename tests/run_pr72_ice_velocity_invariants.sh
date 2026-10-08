#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source_file=${PR72_KDM6_SOURCE:-/var/tmp/pr68_velocity_native_20261007/source/module_mp_kdm6_combined_research.f90}
process_patch=$repo_root/docs/evidence/pr70_coupled_process_cutoff_search_20261008.patch
validity_patch=$repo_root/docs/evidence/pr71_particle_output_contract_20261008.patch
count_patch=$repo_root/docs/evidence/pr71_step_count_contract_20261008_v2.patch
work_root=$(mktemp -d /var/tmp/pr72_ice_velocity_invariants.XXXXXX)
printf 'WORK_ROOT %s\n' "$work_root"
source "$repo_root/tests/intel_toolchain.sh"
[[ $(sha256sum "$source_file" | cut -d' ' -f1) == 97e9892ff527a318f6266140eecc03238485a68b050c61bbaca7ea94f28bfdaa ]]
composed=$work_root/pr71_checked.F
python3 "$repo_root/tools/pr71_compose_guarded_kdm6.py" \
  "$source_file" "$process_patch" "$validity_patch" "$count_patch" "$composed" \
  --expected-validity-patch-sha256 94ea6189c85cd0856a28aac2663ad70091c3259fc448d48bd021adf42ff9ae45 \
  --expected-step-count-patch-sha256 7bc37047bf616b50ebb506f130a2f1f0535e0a5afc26bb26183a27ee188ebb24 \
  >"$work_root/pr71_compose.log"
[[ $(sha256sum "$composed" | cut -d' ' -f1) == 6245969c87f6568cad3b6c6afddc0d1bdfe84a31baa1cee10a465b663c88d716 ]]
fixed=$work_root/pr72_ice_fixed.F
python3 "$repo_root/tools/pr72_ice_velocity_invariants.py" \
  "$composed" "$fixed" "$work_root/pr72_ice.patch" "$work_root/pr72_ice_receipt.json" \
  --expected-source-sha256 6245969c87f6568cad3b6c6afddc0d1bdfe84a31baa1cee10a465b663c88d716 \
  >"$work_root/pr72_ice_compose.log"
[[ $(sha256sum "$fixed" | cut -d' ' -f1) == f396c9270791addcd4aed9fdc59f5a6d3f9287f1af8f759d3a0cbc36b1e78f85 ]]

fixture=$repo_root/tests/fixtures/kdm6_wrapper
for opt in O0 O2; do
  build=$work_root/$opt
  mkdir "$build"
  cp "$fixture/"*.F "$fixture/wrf_debug_stub.f90" "$repo_root/tests/test_pr72_ice_velocity_invariants.f90" "$build/"
  cp "$fixed" "$build/module_mp_kdm6.F"
  cd "$build"
  if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  "$CLOUD_BAL_FC" "${flags[@]}" -free -fpp -c module_wrf_error.F >build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -free -fpp -c module_model_constants.F >>build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -free -fpp -c module_mp_radar.F >>build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -free -fpp -DRWORDSIZE=4 -convert big_endian -c module_mp_kdm6.F >>build.log 2>&1
  "$CLOUD_BAL_FC" "${CLOUD_BAL_FIXED_FLAGS[@]}" -fixed -fpp -c libmassv.F >>build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -c wrf_debug_stub.f90 >>build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -c test_pr72_ice_velocity_invariants.f90 >>build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -o test.exe test_pr72_ice_velocity_invariants.o \
    module_mp_kdm6.o module_mp_radar.o module_model_constants.o libmassv.o wrf_debug_stub.o >>build.log 2>&1
  ./test.exe | tee run.log
  grep -q '^PR72_ICE_VELOCITY_INVARIANTS PASS$' run.log
done
