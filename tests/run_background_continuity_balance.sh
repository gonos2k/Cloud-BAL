#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo_root/tests/intel_toolchain.sh"
scratch_root=$(realpath -m "${CLOUD_BAL_TEST_SCRATCH_ROOT:-/var/tmp}")
repo_resolved=$(realpath -e "$repo_root")
case "$scratch_root/" in
  "$repo_resolved/"*)
    printf 'test scratch root must be outside the source tree: %s\n' "$scratch_root" >&2
    exit 2
    ;;
esac
mkdir -p "$scratch_root"
build_root=$(mktemp -d "$scratch_root/background_continuity_balance.XXXXXX")
compiler_sha=$(sha256sum "$CLOUD_BAL_FC" | cut -d' ' -f1)
source_files=(
  "$repo_root/src/common/cloud_bal_state.f90"
  "$repo_root/src/common/cloud_bal_grid_geometry.f90"
  "$repo_root/src/common/cloud_bal_balance_operator.f90"
  "$repo_root/tests/test_background_continuity_balance.f90"
)

for profile in checked optimized; do
  profile_dir=$build_root/$profile
  mkdir -p "$profile_dir"
  profile_flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  if [[ $profile == optimized ]]; then
    profile_flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  {
    printf 'profile\t%s\nworking_directory\t%s\ncompiler\t%s\ncompiler_sha256\t%s\nflags\t%s\n' \
      "$profile" "$profile_dir" "$CLOUD_BAL_FC" "$compiler_sha" \
      "${profile_flags[*]}" > "$profile_dir/validation.tsv"
    for source_file in "${source_files[@]}"; do
      printf 'source_sha256\t%s\t%s\n' "$(sha256sum "$source_file" | cut -d' ' -f1)" \
        "$source_file" >> "$profile_dir/validation.tsv"
    done
    cd "$profile_dir"
    "$CLOUD_BAL_FC" "${profile_flags[@]}" -module . -I . \
      "${source_files[@]}" -o ./test_background_continuity_balance
    ./test_background_continuity_balance
  } 2>&1 | tee "$profile_dir/run.log"
done
printf 'Validation artifacts retained at %s\n' "$build_root"
