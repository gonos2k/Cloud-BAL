#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo_root/tests/intel_toolchain.sh"
mkdir -p "$repo_root/scratch"
build_root=$(mktemp -d "$repo_root/scratch/qbal_profile_face.XXXXXX")

for level in O0 O2; do
  mkdir "$build_root/$level"
  if [[ $level == O0 ]]; then
    flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  else
    flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  log="$build_root/$level/profile_face.log"
  (
    cd "$build_root/$level"
    "$CLOUD_BAL_FC" "${flags[@]}" \
      "$repo_root/tests/qbal_physical_boundary.f90" \
      "$repo_root/tests/qbal_pressure_flux.f90" \
      "$repo_root/tests/qbal_profile_reconstruction.f90" \
      "$repo_root/tests/qbal_sloping_geometry.f90" \
      "$repo_root/tests/qbal_profile_face.f90" \
      "$repo_root/tests/test_qbal_profile_face.f90" \
      -o test_qbal_profile_face
    ./test_qbal_profile_face
  ) >"$log" 2>&1
  printf 'QBAL_PROFILE_FACE_%s_LOG=%s\n' "$level" "$log"
  cat "$log"
done

printf 'Pinned Intel O0/O2 profile-face evidence: %s\n' "$build_root"
