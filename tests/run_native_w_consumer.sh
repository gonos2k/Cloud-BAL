#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(cd "$repo_root/.." && pwd)
. "$repo_root/tests/intel_toolchain.sh"

nf_config="$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config"
netcdff_archive="$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a"
netcdf_archive="$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a"
[[ -x "$nf_config" && -f "$netcdff_archive" && -f "$netcdf_archive" ]] || {
  printf '%s\n' 'pinned NetCDF Fortran/C archives are unavailable' >&2
  exit 2
}
verify_hash() {
  local path=$1 expected=$2 actual
  actual=$(sha256sum "$path" | cut -d' ' -f1)
  [[ $actual == "$expected" ]] || {
    printf 'pinned dependency hash mismatch: %s\n' "$path" >&2
    exit 2
  }
}
verify_hash "$nf_config" e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5
verify_hash "$netcdff_archive" f610d7ebedf48d17023e9b8377d74d93542bde40d091ec7a5518bb30d17c8a39
verify_hash "$netcdf_archive" f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288
read -r -a nf_fflags <<<"$($nf_config --fflags)"
read -r -a nf_flibs <<<"$($nf_config --flibs)"

test_tmp=$(mktemp -d "$repo_root/scratch/native_w_consumer.XXXXXX")
trap 'rm -rf -- "$test_tmp"' EXIT

run_case() {
  local label=$1
  local -a flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  local build="$test_tmp/$label"
  mkdir -p "$build"
  if [[ $label == o2 ]]; then
    flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  (
    cd "$build"
    "$CLOUD_BAL_FC" "${flags[@]}" -c -module "$build" -I "$build" \
      "${nf_fflags[@]}" "$repo_root/src/common/cloud_bal_native_velocity.f90" \
      -o "$build/cloud_bal_native_velocity.o"
    "$CLOUD_BAL_FC" "${flags[@]}" -c -module "$build" -I "$build" \
      "${nf_fflags[@]}" "$repo_root/src/common/cloud_bal_native_w_consumer.f90" \
      -o "$build/cloud_bal_native_w_consumer.o"
    "$CLOUD_BAL_FC" "${flags[@]}" -c -module "$build" -I "$build" \
      "${nf_fflags[@]}" "$repo_root/tests/test_native_w_consumer.f90" \
      -o "$build/test_native_w_consumer.o"
    "$CLOUD_BAL_FC" "${flags[@]}" -c -module "$build" -I "$build" \
      "${nf_fflags[@]}" "$repo_root/src/native/cloud_bal_apply_native_w.f90" \
      -o "$build/cloud_bal_apply_native_w.o"
    "$CLOUD_BAL_FC" "${flags[@]}" \
      "$build/cloud_bal_native_velocity.o" "$build/cloud_bal_native_w_consumer.o" \
      "$build/test_native_w_consumer.o" "${nf_flibs[@]}" \
      -o "$build/test_native_w_consumer.exe"
    "$CLOUD_BAL_FC" "${flags[@]}" \
      "$build/cloud_bal_native_velocity.o" "$build/cloud_bal_native_w_consumer.o" \
      "$build/cloud_bal_apply_native_w.o" "${nf_flibs[@]}" \
      -o "$build/cloud_bal_apply_native_w.exe"
    mkdir -p "$build/runtime"
    "$build/test_native_w_consumer.exe" "$build/runtime"
    "$build/cloud_bal_apply_native_w.exe" "$build/runtime/wrfinput_d01" \
      "$build/runtime/native_w_increment.nc" 2026-08-16_12:00:00 --off
  )
}

run_case o0
run_case o2
printf '%s\n' 'Native W consumer Intel O0/O2 tests passed'
