#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "$0")" && pwd -P)
repo_root=$(cd "$script_dir/.." && pwd -P)
deps_root=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/klaps-v5.0_/baseline/20260818_rdr_input/deps
fixture="$script_dir/fixtures/pr110_static_reader"
if [[ $# -lt 1 || $# -gt 2 ]]; then
  printf 'usage: run_pr110_static_reader.sh SCRATCH_PARENT [ACTUAL_STATIC_FILE]\n' >&2
  exit 2
fi
mkdir -p "$1"
scratch_parent=$(cd "$1" && pwd -P)
case "$scratch_parent/" in "$repo_root/"*) printf 'scratch parent must be outside the source tree\n' >&2; exit 2 ;; esac
scratch=$(mktemp -d "$scratch_parent/pr110_static_reader.XXXXXX")
. "$script_dir/intel_toolchain.sh"
nf_config="$deps_root/netcdf-fortran-ifx/install/bin/nf-config"
verify_hash() {
  local path=$1 expected=$2 actual
  actual=$(sha256sum "$path" | cut -d' ' -f1)
  [[ "$actual" == "$expected" ]] || { printf 'pinned dependency hash mismatch: %s\n' "$path" >&2; exit 2; }
}
verify_hash "$nf_config" e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5
verify_hash "$deps_root/netcdf-fortran-ifx/install/lib/libnetcdff.a" f610d7ebedf48d17023e9b8377d74d93542bde40d091ec7a5518bb30d17c8a39
verify_hash "$deps_root/netcdf-c-gcc/install/lib/libnetcdf.a" f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288
read -r -a nf_fflags <<<"$("$nf_config" --fflags)"
read -r -a nf_flibs <<<"$("$nf_config" --flibs)"
python3 "$fixture/create_fixtures.py" "$scratch/fixtures"
mkdir -p "$scratch/actual/static"
if [[ $# == 2 ]]; then
  [[ -f $2 ]] || { printf 'actual static fixture is missing: %s\n' "$2" >&2; exit 2; }
  actual_static=$(readlink -f "$2")
  verify_hash "$actual_static" 384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b
  ln -s "$actual_static" "$scratch/actual/static/static.nest7grid"
fi
for optimization in O0 O2; do
  build="$scratch/$optimization"
  mkdir -p "$build"
  flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  [[ $optimization == O2 ]] && flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  (cd "$build" && "$CLOUD_BAL_FC" "${flags[@]}" "${nf_fflags[@]}" \
    -c "$repo_root/src/lapsprep/module_laps_static.f90" -o module_laps_static.o)
  (cd "$build" && "$CLOUD_BAL_FC" "${flags[@]}" "${nf_fflags[@]}" \
    "$fixture/reader_driver.f90" module_laps_static.o "${nf_flibs[@]}" -o reader)
  "$build/reader" "$scratch/fixtures/float_ok" synthetic
  if [[ $# == 2 ]]; then "$build/reader" "$scratch/actual"; fi
  for case_name in double_dx double_lat double_avg bad_lat_rank missing_lat zero_dx negative_dx nan_dx zero_dy negative_dy nan_dy long_dx swapped_lat_axes long_trailing_lat_axis bad_grid_type_length bad_grid_type_rank missing_file; do
    output="$build/$case_name.log"
    if "$build/reader" "$scratch/fixtures/$case_name" >"$output" 2>&1; then
      printf 'expected rejection for %s at %s\n' "$case_name" "$optimization" >&2
      exit 1
    fi
    grep -q 'laps_static:' "$output"
  done
done
printf 'PR110 static reader O0/O2 PASS\n'
