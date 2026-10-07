#!/usr/bin/env bash
set -euo pipefail

if [[ ${BASH_SOURCE[0]} != "$0" ]]; then
  return 0
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=${CLOUD_BAL_WORKSPACE_ROOT:-/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50}
scratch_root=${CLOUD_BAL_TEST_SCRATCH_ROOT:-/var/tmp}
run_root=$(mktemp -d "$scratch_root/cloud_bal_pr67_model_target.XXXXXX")
printf 'PR67 model-target compatibility directory: %s\n' "$run_root"
. "$repo_root/tests/run_pr65_observation_joint_preflight.sh"

. "$repo_root/tests/intel_toolchain.sh"
nf_config=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config
netcdf_fortran_lib=$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a
netcdf_c_lib=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a
target_file=$workspace_root/Cloud-BAL/scratch/cp02_native_omega_remap_6v2c9m1a/LIQUID_MINUS_HYDRO.nc
target_sha256=37ec7c3bc53ef15668abc37ab6d4e071f12b62c634fc9fcefe261a66ae899bef
static_file=$workspace_root/ANAL/NE57/DABA/static.nest7grid
static_sha256=384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b

verify_hash() {
  local path=$1 expected=$2 actual
  test -f "$path" && test ! -L "$path"
  actual=$(sha256sum "$path" | cut -d' ' -f1)
  if [[ $actual != "$expected" ]]; then
    printf 'input hash mismatch: %s expected=%s actual=%s\n' "$path" "$expected" "$actual" >&2
    return 1
  fi
}

load_case() {
  local requested_time=$1
  local case_id valid_time background_reftime laps_stamp
  local fua fua_hash fsf fsf_hash lw3 lw3_hash vrz vrz_hash vrt vrt_hash
  while IFS=$'\t' read -r case_id valid_time background_reftime laps_stamp \
      fua fua_hash fsf fsf_hash lw3 lw3_hash vrz vrz_hash vrt vrt_hash; do
    [[ $valid_time == "$requested_time" ]] || continue
    case_inputs=("$workspace_root/$fua" "$workspace_root/$fsf" "$workspace_root/$lw3" \
      "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file")
    case_hashes=("$fua_hash" "$fsf_hash" "$lw3_hash" "$vrz_hash" "$vrt_hash" "$static_sha256")
    case_epoch=$(date -u -d "$valid_time" +%s)
    return 0
  done < <(sed '1d' "$repo_root/tests/qbal_real_cases_20260816.tsv")
  printf 'requested case not found: %s\n' "$requested_time" >&2
  return 1
}

load_case 2026-08-16T13:00:00Z
case_13_inputs=("${case_inputs[@]}")
case_13_epoch=$case_epoch
case_13_hashes=("${case_hashes[@]}")
load_case 2026-08-16T12:00:00Z
case_12_inputs=("${case_inputs[@]}")
case_12_epoch=$case_epoch
case_12_hashes=("${case_hashes[@]}")
verify_hash "$target_file" "$target_sha256"
for index in "${!case_13_inputs[@]}"; do verify_hash "${case_13_inputs[$index]}" "${case_13_hashes[$index]}"; done
for index in "${!case_12_inputs[@]}"; do verify_hash "${case_12_inputs[$index]}" "${case_12_hashes[$index]}"; done

program_source=$repo_root/tests/pr67_model_target_compatibility.f90
prepare_source=$repo_root/tests/pr67_prepare_model_target_masks.f90
prepare_script=$repo_root/tests/prepare_pr67_model_target.py
prepare_script_test=$repo_root/tests/test_prepare_pr67_model_target.py
source_names=(cloud_bal_state cloud_bal_grid_geometry cloud_bal_column_physics \
  cloud_bal_balance_operator cloud_bal_pipeline cloud_bal_real_netcdf cloud_bal_pressure_analysis)
source_files=()
objects=()
for source in "${source_names[@]}"; do source_files+=("$repo_root/src/common/$source.f90"); done
sha256sum "${source_files[@]}" "$program_source" "$prepare_source" "$prepare_script" \
  "$prepare_script_test" \
  "$repo_root/tests/run_pr67_model_target_compatibility.sh" \
  "$repo_root/tests/intel_toolchain.sh" "$repo_root/tests/run_pr65_observation_joint_preflight.sh" \
  "$repo_root/tests/qbal_real_cases_20260816.tsv" \
  "$cloud_bal_setvars" "$CLOUD_BAL_FC" "$cloud_bal_imf" "$cloud_bal_intlc" "$nf_config" \
  "$netcdf_fortran_lib" "$netcdf_c_lib" > "$run_root/profile_and_sources.before.sha256"
sha256sum "$target_file" "${case_13_inputs[@]}" "${case_12_inputs[@]}" \
  > "$run_root/actual_inputs.before.sha256"
read -r -a nf_fflags <<<"$("$nf_config" --fflags)"
read -r -a nf_flibs <<<"$("$nf_config" --flibs)"

for source in "${source_names[@]}"; do
  object="$run_root/$source.o"
  "$CLOUD_BAL_FC" -c "${CLOUD_BAL_FREE_FLAGS[@]}" -module "$run_root" -I "$run_root" \
    "${nf_fflags[@]}" "$repo_root/src/common/$source.f90" -o "$object"
  objects+=("$object")
done
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" -module "$run_root" -I "$run_root" \
  "${nf_fflags[@]}" "$program_source" "${objects[@]}" "${nf_flibs[@]}" \
  -o "$run_root/pr67_model_target_compatibility"
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" -module "$run_root" -I "$run_root" \
  "${nf_fflags[@]}" "$prepare_source" "${objects[@]}" "${nf_flibs[@]}" \
  -o "$run_root/pr67_prepare_model_target_masks"

cd "$repo_root"
PYTHONDONTWRITEBYTECODE=1 python3 -B "$prepare_script_test"
run_logged_command "$run_root/mask_preparation.log" \
  "$run_root/pr67_prepare_model_target_masks" "${case_13_inputs[@]}" "$case_13_epoch" \
  "$target_file" "$run_root/derived_masks.bin"
derived_target=$run_root/LIQUID_MINUS_HYDRO_13Z_STATE_COMPAT.nc
run_logged_command "$run_root/derived_target_receipt.log" python3 "$prepare_script" \
  "$target_file" "$run_root/derived_masks.bin" "$derived_target"
run_with_default_stack() { ulimit -s 8192; "$@"; }
run_logged_command "$run_root/13Z_original_target_rejection.log" run_with_default_stack \
  "$run_root/pr67_model_target_compatibility" "${case_13_inputs[@]}" "$case_13_epoch" \
  "$target_file" 0
run_logged_command "$run_root/13Z_derived_target_acceptance.log" run_with_default_stack \
  "$run_root/pr67_model_target_compatibility" "${case_13_inputs[@]}" "$case_13_epoch" \
  "$derived_target" 1
run_logged_command "$run_root/12Z_derived_target_rejection.log" run_with_default_stack \
  "$run_root/pr67_model_target_compatibility" "${case_12_inputs[@]}" "$case_12_epoch" \
  "$derived_target" 0

o2_root=$run_root/o2
mkdir -p "$o2_root"
o2_objects=()
for source in "${source_names[@]}"; do
  object="$o2_root/$source.o"
  "$CLOUD_BAL_FC" -c "${CLOUD_BAL_REPRO_FLAGS[@]}" -module "$o2_root" -I "$o2_root" \
    "${nf_fflags[@]}" "$repo_root/src/common/$source.f90" -o "$object"
  o2_objects+=("$object")
done
"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" -module "$o2_root" -I "$o2_root" \
  "${nf_fflags[@]}" "$program_source" "${o2_objects[@]}" "${nf_flibs[@]}" \
  -o "$o2_root/pr67_model_target_compatibility"
run_logged_command "$run_root/O2_13Z_derived_target_acceptance.log" run_with_default_stack \
  "$o2_root/pr67_model_target_compatibility" "${case_13_inputs[@]}" "$case_13_epoch" \
  "$derived_target" 1
run_logged_command "$run_root/O2_12Z_derived_target_rejection.log" run_with_default_stack \
  "$o2_root/pr67_model_target_compatibility" "${case_12_inputs[@]}" "$case_12_epoch" \
  "$derived_target" 0

sha256sum "${source_files[@]}" "$program_source" "$prepare_source" "$prepare_script" \
  "$prepare_script_test" \
  "$repo_root/tests/run_pr67_model_target_compatibility.sh" \
  "$repo_root/tests/intel_toolchain.sh" "$repo_root/tests/run_pr65_observation_joint_preflight.sh" \
  "$repo_root/tests/qbal_real_cases_20260816.tsv" \
  "$cloud_bal_setvars" "$CLOUD_BAL_FC" "$cloud_bal_imf" "$cloud_bal_intlc" "$nf_config" \
  "$netcdf_fortran_lib" "$netcdf_c_lib" > "$run_root/profile_and_sources.after.sha256"
sha256sum "$target_file" "${case_13_inputs[@]}" "${case_12_inputs[@]}" \
  > "$run_root/actual_inputs.after.sha256"
cmp "$run_root/profile_and_sources.before.sha256" "$run_root/profile_and_sources.after.sha256"
cmp "$run_root/actual_inputs.before.sha256" "$run_root/actual_inputs.after.sha256"
sha256sum "${objects[@]}" "$run_root/pr67_model_target_compatibility" \
  "$run_root/pr67_prepare_model_target_masks" "${o2_objects[@]}" \
  "$o2_root/pr67_model_target_compatibility" \
  > "$run_root/compiled_artifacts.sha256"
{
  printf 'compiler=%s\ncompiler_version=%s\ncompiler_sha256=%s\nprofiles=O0_and_O2 pinned Intel\n' \
    "$CLOUD_BAL_FC" "$cloud_bal_fc_version" "$cloud_bal_fc_sha256"
  printf 'netcdf_fortran=%s\n' "$("$nf_config" --version)"
  printf 'target_file=%s\ntarget_sha256=%s\n' "$target_file" "$target_sha256"
  printf 'actual_input_hashes_checked=12Z_and_13Z_and_source_target_pre_and_post\n'
  printf 'reader_process_stack_limit_kib=8192\n'
} > "$run_root/receipt.txt"
cat "$run_root/receipt.txt"
printf 'evidence=%s\n' "$run_root"
