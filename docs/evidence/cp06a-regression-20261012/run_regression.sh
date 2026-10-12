#!/usr/bin/env bash
set -euo pipefail
repo=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/cloudbal-cp06a-pr-work
. "$repo/tests/intel_toolchain.sh"
run=$(mktemp -d /var/tmp/cloudbal-cp06a-regression.XXXXXX)
printf 'scratch=%s\n' "$run"
cd "$run"
for profile in O0 O2; do
 flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
 if [[ $profile == O2 ]]; then flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
 mkdir "$profile"
 cd "$profile"
 for module in cloud_bal_state cloud_bal_column_physics cloud_bal_grid_geometry cloud_bal_balance_operator cloud_bal_pipeline; do
  "$CLOUD_BAL_FC" "${flags[@]}" -module . -I . -c "$repo/src/common/$module.f90" -o "$module.o"
 done
 for name in test_balance_operator test_balance_partial_faces test_pipeline test_prebalance_wind; do
  "$CLOUD_BAL_FC" "${flags[@]}" -module . -I . "$repo/tests/$name.f90" ./*.o -o "$name"
  ./$name
 done
 cd ..
done
