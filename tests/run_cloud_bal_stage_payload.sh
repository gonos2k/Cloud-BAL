#!/usr/bin/env bash
# Build and run the canonical stage-payload round-trip in a fresh scratch tree.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(cd "$repo_root/.." && pwd)
scratch_root="$repo_root/scratch"
mkdir -p "$scratch_root"
test_tmp=$(mktemp -d "$scratch_root/stage_payload_tests.XXXXXX")
if [[ ${CLOUD_BAL_KEEP_TEST_OUTPUT:-0} == 1 ]]; then
  trap 'printf "stage payload test artifacts retained: %s\n" "$test_tmp"' EXIT
else
  trap 'rm -rf -- "$test_tmp"' EXIT
fi

. "$repo_root/tests/intel_toolchain.sh"

nf_config="$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config"
netcdff_archive="$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a"
netcdf_archive="$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a"
[[ -x "$nf_config" && -f "$netcdff_archive" && -f "$netcdf_archive" ]] || {
  printf 'pinned NetCDF Fortran/C archives are unavailable\n' >&2
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

build="$test_tmp/build"
mkdir -p "$build"
compile() {
  local source=$1 object=$2
  if ! "$CLOUD_BAL_FC" -c "${CLOUD_BAL_FREE_FLAGS[@]}" \
      -module "$build" -I "$build" "${nf_fflags[@]}" \
      "$repo_root/$source" -o "$build/$object" \
      >"$build/$object.log" 2>&1; then
    cat "$build/$object.log" >&2
    exit 1
  fi
}
compile src/common/cloud_bal_state.f90 cloud_bal_state.o
compile src/common/cloud_bal_stage_payload.f90 cloud_bal_stage_payload.o
compile tests/test_cloud_bal_stage_payload.f90 test_cloud_bal_stage_payload.o
if ! "$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
    "$build/cloud_bal_state.o" "$build/cloud_bal_stage_payload.o" \
    "$build/test_cloud_bal_stage_payload.o" "${nf_flibs[@]}" \
    -o "$build/test_cloud_bal_stage_payload.exe" \
    >"$build/link.log" 2>&1; then
  cat "$build/link.log" >&2
  exit 1
fi

if ! "$build/test_cloud_bal_stage_payload.exe" "$test_tmp/payload.nc" \
    >"$test_tmp/test.log" 2>&1; then
  cat "$test_tmp/test.log" >&2
  exit 1
fi
cat "$test_tmp/test.log"

{
  printf 'compiler='; "$CLOUD_BAL_FC" --version 2>&1 | sed -n '1p'
  printf 'compiler_sha256='; sha256sum "$CLOUD_BAL_FC" | cut -d' ' -f1
  printf 'setvars_sha256='; sha256sum /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/setvars.sh | cut -d' ' -f1
  sha256sum "$repo_root/src/common/cloud_bal_state.f90" \
    "$repo_root/src/common/cloud_bal_stage_payload.f90" \
    "$repo_root/tests/test_cloud_bal_stage_payload.f90" \
    "$repo_root/tests/run_cloud_bal_stage_payload.sh" \
    "$build/test_cloud_bal_stage_payload.exe"
  printf 'payload_sha256='; sha256sum "$test_tmp/payload.nc" | cut -d' ' -f1
} >"$test_tmp/receipt.txt"
printf 'stage payload receipt: %s\n' "$test_tmp/receipt.txt"
