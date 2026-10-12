#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo_root/tests/intel_toolchain.sh"
run_root=$(mktemp -d "${CLOUD_BAL_TEST_SCRATCH_ROOT:-/var/tmp}/thermo-density.XXXXXX")
printf 'thermodynamic density-prior test directory: %s\n' "$run_root"
mkdir -p "$run_root/source"
cp "$repo_root/src/common/cloud_bal_state.f90" "$repo_root/src/common/cloud_bal_column_physics.f90" \
  "$repo_root/tests/test_thermo_density_prior.f90" "$run_root/source/"
sha256sum "$run_root/source/"* > "$run_root/source.pre.sha256"
for profile in O0 O2; do
  flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  if [[ $profile == O2 ]]; then flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  mkdir -p "$run_root/$profile"
  cd "$run_root/$profile"
  "$CLOUD_BAL_FC" "${flags[@]}" -module . -I . "$run_root/source/cloud_bal_state.f90" \
    "$run_root/source/cloud_bal_column_physics.f90" "$run_root/source/test_thermo_density_prior.f90" \
    -o test-thermo-density > compile.log 2>&1
  ./test-thermo-density | tee run.log
done
sha256sum "$run_root/source/"* > "$run_root/source.post.sha256"
cmp "$run_root/source.pre.sha256" "$run_root/source.post.sha256"
