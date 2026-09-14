#!/usr/bin/env bash
# Fresh-workdir CP01 item-5 boundary reftime mutation test.
set -euo pipefail

snapshot_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(realpath -e "${CLOUD_BAL_WORKSPACE_ROOT:-$snapshot_dir/..}")
source "$snapshot_dir/tests/intel_toolchain.sh"

mkdir -p "$snapshot_dir/scratch"
test_root=$(mktemp -d "$snapshot_dir/scratch/boundary_reftime.XXXXXX")
printf 'test_root=%s\n' "$test_root"

source_manifest="$test_root/source_hashes.sha256"
sha256sum "$snapshot_dir"/src/common/*.f90 \
  "$snapshot_dir/tests/test_boundary_reftime.f90" \
  "$snapshot_dir/tests/verify_only_reftime.py" \
  "$snapshot_dir/tests/intel_toolchain.sh" \
  "$snapshot_dir/tests/qbal_real_cases_20260816.tsv" \
  "$snapshot_dir/tests/run_boundary_reftime_contract.sh" > "$source_manifest"

manifest="$snapshot_dir/tests/qbal_real_cases_20260816.tsv"
IFS=$'\t' read -r case_id valid_time background_time laps_stamp \
  fua fua_hash fsf fsf_hash lw3 lw3_hash vrz vrz_hash vrt vrt_hash \
  < <(awk -F '\t' '$1=="20260816T130000Z" {print; exit}' "$manifest")
[[ $case_id == 20260816T130000Z ]]
epoch=$(date -u -d "$valid_time" +%s)
background_epoch=$(date -u -d "$background_time" +%s)
static_file="$workspace_root/ANAL/NE57/DABA/static.nest7grid"

IFS=$'\t' read -r _ _ _ _ _ _ fsf12 fsf12_hash _ _ _ _ _ _ \
  < <(awk -F '\t' '$1=="20260816T120000Z" {print; exit}' "$manifest")
IFS=$'\t' read -r _ _ _ _ _ _ fsf14 fsf14_hash _ _ _ _ _ _ \
  < <(awk -F '\t' '$1=="20260816T140000Z" {print; exit}' "$manifest")

inputs_manifest="$test_root/inputs.sha256"
printf '%s  %s\n' \
  "$fua_hash" "$workspace_root/$fua" \
  "$fsf_hash" "$workspace_root/$fsf" \
  "$fsf12_hash" "$workspace_root/$fsf12" \
  "$fsf14_hash" "$workspace_root/$fsf14" \
  "$lw3_hash" "$workspace_root/$lw3" \
  "$vrz_hash" "$workspace_root/$vrz" \
  "$vrt_hash" "$workspace_root/$vrt" \
  '384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b' "$static_file" \
  > "$inputs_manifest"
sha256sum -c "$inputs_manifest" > "$test_root/input_identity_pre.log"

nf_config="$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config"
read -r -a nf_fflags <<<"$($nf_config --fflags)"
read -r -a nf_flibs <<<"$($nf_config --flibs)"

mutate_reftime() {
  local target=$1 value=$2
  python3 - "$target" "$value" <<'PY'
import sys
import netCDF4

path, value = sys.argv[1], float(sys.argv[2])
with netCDF4.Dataset(path, "r+") as dataset:
    dataset.variables["reftime"][:] = value
PY
}

verify_only_reftime() {
  python3 "$snapshot_dir/tests/verify_only_reftime.py" "$1" "$2" "$3" "$4"
}

for mode in O0 O2; do
  build_root="$test_root/$mode"
  mkdir -p "$build_root"
  cd "$build_root"
  if [[ $mode == O0 ]]; then
    flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  else
    flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi

  compile() {
    local source=$1 object=$2
    "$CLOUD_BAL_FC" -c "${flags[@]}" -module "$build_root" -I "$build_root" \
      "${nf_fflags[@]}" "$source" -o "$object"
  }
  compile "$snapshot_dir/src/common/cloud_bal_state.f90" "$build_root/cloud_bal_state.o"
  compile "$snapshot_dir/src/common/cloud_bal_grid_geometry.f90" "$build_root/cloud_bal_grid_geometry.o"
  compile "$snapshot_dir/src/common/cloud_bal_column_physics.f90" "$build_root/cloud_bal_column_physics.o"
  compile "$snapshot_dir/src/common/cloud_bal_balance_operator.f90" "$build_root/cloud_bal_balance_operator.o"
  compile "$snapshot_dir/src/common/cloud_bal_pipeline.f90" "$build_root/cloud_bal_pipeline.o"
  compile "$snapshot_dir/src/common/cloud_bal_pressure_analysis.f90" "$build_root/cloud_bal_pressure_analysis.o"
  compile "$snapshot_dir/src/common/cloud_bal_real_netcdf.f90" "$build_root/cloud_bal_real_netcdf.o"
  "$CLOUD_BAL_FC" "${flags[@]}" -module "$build_root" -I "$build_root" \
    "${nf_fflags[@]}" "$snapshot_dir/tests/test_boundary_reftime.f90" \
    "$build_root"/*.o "${nf_flibs[@]}" -o "$build_root/test_boundary_reftime"

  # The manifest's 13 UTC row is the center FSF; derive 12/14 UTC rows by ID.
  fsf_before_path="$workspace_root/$fsf12"
  fsf_center_path="$workspace_root/$fsf"
  fsf_after_path="$workspace_root/$fsf14"
  fua_path="$workspace_root/$fua"
  lw3_path="$workspace_root/$lw3"
  vrz_path="$workspace_root/$vrz"
  vrt_path="$workspace_root/$vrt"

  common_args=("$fua_path" "$fsf_center_path" "PLACEHOLDER_BEFORE" "PLACEHOLDER_CENTER" \
    "PLACEHOLDER_AFTER" "$lw3_path" "$vrz_path" "$vrt_path" "$static_file" "$epoch")
  positive_dir="$build_root/positive"
  mkdir -p "$positive_dir"
  cp "$fsf_before_path" "$positive_dir/before.fsf"
  cp "$fsf_center_path" "$positive_dir/center.fsf"
  cp "$fsf_after_path" "$positive_dir/after.fsf"
  "$build_root/test_boundary_reftime" "${common_args[0]}" "${common_args[1]}" \
    "$positive_dir/before.fsf" "$positive_dir/center.fsf" "$positive_dir/after.fsf" \
    "${common_args[@]:5}" POSITIVE \
    > "$build_root/positive.log" 2>&1
  rg -F -q 'POSITIVE_MANUFACTURED_BOUNDARY STATUS_OK REASON_NONE' "$build_root/positive.log"
  rg -F -q 'BOUNDARY_AUTHORITY=MANUFACTURED_TEST_ONLY' "$build_root/positive.log"
  rg -F -q 'PHYSICAL_AUTHORITY=NONE' "$build_root/positive.log"

  for label in before center after; do
    case_dir="$build_root/mutation_$label"
    mkdir -p "$case_dir"
    cp "$fsf_before_path" "$case_dir/before.fsf"
    cp "$fsf_center_path" "$case_dir/center.fsf"
    cp "$fsf_after_path" "$case_dir/after.fsf"
    mutated_reftime=$((background_epoch + 3600))
    case "$label" in
      before)
        valid_epoch=$((epoch - 3600))
        mutate_reftime "$case_dir/before.fsf" "$mutated_reftime"
        verify_only_reftime "$fsf_before_path" "$case_dir/before.fsf" "$mutated_reftime" "$valid_epoch" \
          > "$case_dir/identity.log"
        cmp -s "$fsf_center_path" "$case_dir/center.fsf"
        cmp -s "$fsf_after_path" "$case_dir/after.fsf"
        ;;
      center)
        valid_epoch=$epoch
        mutate_reftime "$case_dir/center.fsf" "$mutated_reftime"
        cmp -s "$fsf_before_path" "$case_dir/before.fsf"
        verify_only_reftime "$fsf_center_path" "$case_dir/center.fsf" "$mutated_reftime" "$valid_epoch" \
          > "$case_dir/identity.log"
        cmp -s "$fsf_after_path" "$case_dir/after.fsf"
        ;;
      after)
        valid_epoch=$((epoch + 3600))
        mutate_reftime "$case_dir/after.fsf" "$mutated_reftime"
        cmp -s "$fsf_before_path" "$case_dir/before.fsf"
        cmp -s "$fsf_center_path" "$case_dir/center.fsf"
        verify_only_reftime "$fsf_after_path" "$case_dir/after.fsf" "$mutated_reftime" "$valid_epoch" \
          > "$case_dir/identity.log"
        ;;
    esac
    "$build_root/test_boundary_reftime" "${common_args[0]}" "${common_args[1]}" \
      "$case_dir/before.fsf" "$case_dir/center.fsf" "$case_dir/after.fsf" \
      "${common_args[@]:5}" NEGATIVE > "$case_dir/result.log" 2>&1
    rg -F -q 'NEGATIVE_REFTIME STATUS_FAILED REASON_METADATA STATE_UNCHANGED' "$case_dir/result.log"
    printf '%s %s STATUS_FAILED REASON_METADATA STATE_UNCHANGED\n' "$mode" "$label"
  done
  printf '%s POSITIVE_MANUFACTURED_BOUNDARY STATUS_OK REASON_NONE\n' "$mode"
done

sha256sum -c "$source_manifest" > "$test_root/source_identity_post.log"
sha256sum -c "$inputs_manifest" > "$test_root/input_identity_post.log"
printf 'BOUNDARY_REFTIME_CONTRACT_PASS case=%s valid=%s forecast_ref=%s artifacts=%s\n' \
  "$case_id" "$valid_time" "$background_time" "$test_root"
