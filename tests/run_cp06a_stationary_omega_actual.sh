#!/usr/bin/env bash
# Run the stationary omega diagnostic on the pinned 2026-08-16 13 UTC inputs.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=${CLOUD_BAL_WORKSPACE_ROOT:-/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50}
scratch_root=${CLOUD_BAL_TEST_SCRATCH_ROOT:-$workspace_root/Cloud-BAL/scratch}
mkdir -p "$scratch_root"
run_root=$(mktemp -d "$scratch_root/cp06a_stationary_omega.XXXXXX")
printf 'actual producer run directory: %s\n' "$run_root"
. "$repo_root/tests/intel_toolchain.sh"

nf_config=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config
netcdf_fortran_lib=$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a
netcdf_c_lib=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a
static_path=$workspace_root/ANAL/NE57/DABA/static.nest7grid
static_hash=384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b
case_inputs=()
case_hashes=()
found_case=0
valid_time=1786885200

verify_hash() {
  local path=$1 expected=$2 actual
  [[ -f $path && ! -L $path ]] || { printf 'missing or linked input: %s\n' "$path" >&2; exit 2; }
  actual=$(sha256sum "$path" | cut -d' ' -f1)
  [[ $actual == "$expected" ]] || {
    printf 'input hash mismatch: %s expected=%s actual=%s\n' "$path" "$expected" "$actual" >&2
    exit 2
  }
}

while IFS=$'\t' read -r case_id case_time background_reftime laps_stamp \
    fua fua_hash fsf fsf_hash lw3 lw3_hash vrz vrz_hash vrt vrt_hash; do
  [[ $case_time == 2026-08-16T13:00:00Z ]] || continue
  case_inputs=("$workspace_root/$fua" "$workspace_root/$fsf" "$workspace_root/$lw3" \
    "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_path")
  case_hashes=("$fua_hash" "$fsf_hash" "$lw3_hash" "$vrz_hash" "$vrt_hash" "$static_hash")
  found_case=1
done < "$repo_root/tests/qbal_real_cases_20260816.tsv"
[[ $found_case == 1 ]] || { printf '13 UTC inputs not found\n' >&2; exit 2; }
for index in "${!case_inputs[@]}"; do verify_hash "${case_inputs[$index]}" "${case_hashes[$index]}"; done

[[ -x $nf_config && -f $netcdf_fortran_lib && -f $netcdf_c_lib ]] || {
  printf 'pinned NetCDF Fortran/C libraries are unavailable\n' >&2; exit 2;
}
verify_hash "$nf_config" e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5
verify_hash "$netcdf_fortran_lib" f610d7ebedf48d17023e9b8377d74d93542bde40d091ec7a5518bb30d17c8a39
verify_hash "$netcdf_c_lib" f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288
read -r -a nf_fflags <<<"$("$nf_config" --fflags)"
read -r -a nf_flibs <<<"$("$nf_config" --flibs)"

source_names=(cloud_bal_state cloud_bal_grid_geometry cloud_bal_column_physics \
  cloud_bal_balance_operator cloud_bal_pipeline cloud_bal_real_netcdf)
source_files=()
for source in "${source_names[@]}"; do source_files+=("$repo_root/src/common/$source.f90"); done
source_files+=("$repo_root/tests/cp06a_stationary_omega_actual.f90")

run_profile() {
  local profile=$1
  local -n flags=$2
  local build_dir="$run_root/$profile"
  mkdir -p "$build_dir"
  local objects=()
  for source in "${source_names[@]}"; do
    object="$build_dir/$source.o"
    "$CLOUD_BAL_FC" -c "${flags[@]}" -module "$build_dir" -I "$build_dir" \
      "${nf_fflags[@]}" "$repo_root/src/common/$source.f90" -o "$object" \
      >"$build_dir/$source.compile.log" 2>&1
    objects+=("$object")
  done
  "$CLOUD_BAL_FC" "${flags[@]}" -module "$build_dir" -I "$build_dir" \
    "${nf_fflags[@]}" "$repo_root/tests/cp06a_stationary_omega_actual.f90" \
    "${objects[@]}" "${nf_flibs[@]}" -o "$build_dir/producer.exe" \
    >"$build_dir/producer.link.log" 2>&1
  set +e
  "$build_dir/producer.exe" "${case_inputs[@]}" "$valid_time" \
    "$build_dir/omega_candidate.bin" >"$build_dir/run.log" 2>&1
  rc=$?
  set -e
  printf 'exit_status=%s\n' "$rc" > "$build_dir/exit_status.txt"
}

run_profile O0 CLOUD_BAL_FREE_FLAGS
run_profile O2 CLOUD_BAL_REPRO_FLAGS

{
  printf 'scope=actual processed 2026-08-16 13 UTC LW3 background; fixed i=100:107,j=130:137\n'
  printf 'compiler='; "$CLOUD_BAL_FC" --version 2>&1 | sed -n '1p'
  printf 'compiler_sha256='; sha256sum "$CLOUD_BAL_FC" | cut -d' ' -f1
  printf 'setvars_sha256='; sha256sum /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/setvars.sh | cut -d' ' -f1
  printf 'netcdf_fortran_config_sha256='; sha256sum "$nf_config" | cut -d' ' -f1
  sha256sum "${source_files[@]}" "$repo_root/tests/run_cp06a_stationary_omega_actual.sh" > "$run_root/source_hashes.sha256"
  sha256sum "${case_inputs[@]}" > "$run_root/actual_input_hashes.sha256"
  for profile in O0 O2; do
    printf '%s_exit_status=' "$profile"; cat "$run_root/$profile/exit_status.txt"
    cat "$run_root/$profile/run.log"
    if [[ -f $run_root/$profile/omega_candidate.bin ]]; then
      sha256sum "$run_root/$profile/omega_candidate.bin"
    fi
  done
} | tee "$run_root/receipt.txt"

printf 'receipt=%s\n' "$run_root/receipt.txt"
for profile in O0 O2; do
  [[ $(cat "$run_root/$profile/exit_status.txt") == exit_status=0 ]] || exit 1
done
