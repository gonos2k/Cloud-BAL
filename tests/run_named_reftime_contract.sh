#!/usr/bin/env bash
# Narrow CP01 time-policy test for the current reader.
# The live source tree is never modified; every object and mutation is scratch.
set -euo pipefail

snapshot_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(realpath -e "${CLOUD_BAL_WORKSPACE_ROOT:-$snapshot_dir/..}")
source "$snapshot_dir/tests/intel_toolchain.sh"

mkdir -p "$snapshot_dir/scratch"
test_root=$(mktemp -d "$snapshot_dir/scratch/reftime_contract.XXXXXX")
printf 'test_root=%s\n' "$test_root"

source_manifest=$test_root/source_hashes.sha256
sha256sum "$snapshot_dir"/src/common/*.f90 \
  "$snapshot_dir/tests/test_real_shadow_reader.f90" \
  "$snapshot_dir/tests/intel_toolchain.sh" \
  "$snapshot_dir/tests/qbal_real_cases_20260816.tsv" \
  "$snapshot_dir/tests/run_named_reftime_contract.sh" > "$source_manifest"

manifest=$snapshot_dir/tests/qbal_real_cases_20260816.tsv
IFS=$'\t' read -r case_id valid_time background_time laps_stamp \
  fua fua_hash fsf fsf_hash lw3 lw3_hash vrz vrz_hash vrt vrt_hash \
  < <(awk -F '\t' '$1=="20260816T130000Z" {print; exit}' "$manifest")
[[ $case_id == 20260816T130000Z ]]
epoch=$(date -u -d "$valid_time" +%s)
background_epoch=$(date -u -d "$background_time" +%s)
static_file=$workspace_root/ANAL/NE57/DABA/static.nest7grid

inputs_manifest=$test_root/inputs.sha256
printf '%s  %s\n' \
  "$fua_hash" "$workspace_root/$fua" \
  "$fsf_hash" "$workspace_root/$fsf" \
  "$lw3_hash" "$workspace_root/$lw3" \
  "$vrz_hash" "$workspace_root/$vrz" \
  "$vrt_hash" "$workspace_root/$vrt" \
  '384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b' "$static_file" \
  > "$inputs_manifest"
sha256sum -c "$inputs_manifest" > "$test_root/input_identity_pre.log"

nf_config=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config
read -r -a nf_fflags <<<"$($nf_config --fflags)"
read -r -a nf_flibs <<<"$($nf_config --flibs)"

for mode in O0 O2; do
  test_tmp=$test_root/$mode
  mkdir -p "$test_tmp"
  cd "$test_tmp"
  pwd > "$test_tmp/build_cwd.log"
  flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  [[ $mode == O2 ]] && flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")

  compile() {
    local source=$1 object=$2
    "$CLOUD_BAL_FC" -c "${flags[@]}" -module "$test_tmp" -I "$test_tmp" \
      "${nf_fflags[@]}" "$source" -o "$object"
  }
  compile "$snapshot_dir/src/common/cloud_bal_state.f90" "$test_tmp/cloud_bal_state.o"
  compile "$snapshot_dir/src/common/cloud_bal_grid_geometry.f90" "$test_tmp/cloud_bal_grid_geometry.o"
  compile "$snapshot_dir/src/common/cloud_bal_column_physics.f90" "$test_tmp/cloud_bal_column_physics.o"
  compile "$snapshot_dir/src/common/cloud_bal_balance_operator.f90" "$test_tmp/cloud_bal_balance_operator.o"
  compile "$snapshot_dir/src/common/cloud_bal_pipeline.f90" "$test_tmp/cloud_bal_pipeline.o"
  compile "$snapshot_dir/src/common/cloud_bal_pressure_analysis.f90" "$test_tmp/cloud_bal_pressure_analysis.o"
  compile "$snapshot_dir/src/common/cloud_bal_real_netcdf.f90" "$test_tmp/cloud_bal_real_netcdf.o"
  "$CLOUD_BAL_FC" "${flags[@]}" -module "$test_tmp" -I "$test_tmp" \
    "${nf_fflags[@]}" "$snapshot_dir/tests/test_real_shadow_reader.f90" \
    "$test_tmp"/*.o "${nf_flibs[@]}" -o "$test_tmp/test_real_shadow_reader"

  fua_path=$workspace_root/$fua
  fsf_path=$workspace_root/$fsf
  lw3_path=$workspace_root/$lw3
  vrz_path=$workspace_root/$vrz
  vrt_path=$workspace_root/$vrt

  "$test_tmp/test_real_shadow_reader" "$fua_path" "$fsf_path" "$lw3_path" \
    "$vrz_path" "$vrt_path" "$static_file" "$epoch" > "$test_tmp/positive.log" 2>&1

  mutate_reftime() {
    local source=$1 target=$2 value=$3
    cp "$source" "$target"
    python3 - "$target" "$value" <<'PY'
import sys
import netCDF4

path, value = sys.argv[1], float(sys.argv[2])
with netCDF4.Dataset(path, "r+") as dataset:
    dataset.variables["reftime"][:] = value
PY
  }

  expect_reject() {
    local label=$1 marker=$2 input_fua=$3 input_fsf=$4 input_lw3=$5
    local log=$test_tmp/$label.log
    if "$test_tmp/test_real_shadow_reader" "$input_fua" "$input_fsf" "$input_lw3" \
        "$vrz_path" "$vrt_path" "$static_file" "$epoch" > "$log" 2>&1; then
      printf 'accepted mutation: %s\n' "$label" >&2
      exit 1
    fi
    rg -F -q "$marker" "$log" || {
      printf 'wrong diagnostic for %s; wanted %s\n' "$label" "$marker" >&2
      cat "$log" >&2
      exit 1
    }
    printf '%s %s REJECT (%s)\n' "$mode" "$label" "$marker"
  }

  expect_accept() {
    local label=$1 input_fua=$2 input_fsf=$3 input_lw3=$4
    local log=$test_tmp/$label.log
    if ! "$test_tmp/test_real_shadow_reader" "$input_fua" "$input_fsf" "$input_lw3" \
        "$vrz_path" "$vrt_path" "$static_file" "$epoch" > "$log" 2>&1; then
      printf 'rejected edge case: %s\n' "$label" >&2
      cat "$log" >&2
      exit 1
    fi
    rg -F -q 'Real SHADOW reader contract test passed' "$log" || {
      printf 'missing success diagnostic for %s\n' "$label" >&2
      cat "$log" >&2
      exit 1
    }
    printf '%s %s ACCEPT\n' "$mode" "$label"
  }

  analysis_plus_half=$test_tmp/analysis-reftime-plus-half.lw3
  mutate_reftime "$lw3_path" "$analysis_plus_half" "${epoch}.5"
  expect_accept analysis_reftime_plus_half "$fua_path" "$fsf_path" "$analysis_plus_half"

  analysis_minus_half=$test_tmp/analysis-reftime-minus-half.lw3
  mutate_reftime "$lw3_path" "$analysis_minus_half" "$((epoch - 1)).5"
  expect_accept analysis_reftime_minus_half "$fua_path" "$fsf_path" "$analysis_minus_half"

  analysis_plus_outside=$test_tmp/analysis-reftime-plus-outside.lw3
  mutate_reftime "$lw3_path" "$analysis_plus_outside" "${epoch}.5001"
  expect_reject analysis_reftime_plus_outside adapter_error=reftime-mismatch \
    "$fua_path" "$fsf_path" "$analysis_plus_outside"

  analysis_minus_outside=$test_tmp/analysis-reftime-minus-outside.lw3
  mutate_reftime "$lw3_path" "$analysis_minus_outside" "$((epoch - 1)).4999"
  expect_reject analysis_reftime_minus_outside adapter_error=reftime-mismatch \
    "$fua_path" "$fsf_path" "$analysis_minus_outside"

  analysis_shifted=$test_tmp/analysis-reftime-shifted.lw3
  mutate_reftime "$lw3_path" "$analysis_shifted" "$((epoch + 3600))"
  expect_reject analysis_reftime_changed adapter_error=reftime-mismatch \
    "$fua_path" "$fsf_path" "$analysis_shifted"

  missing_reftime=$test_tmp/missing-reftime.lw3
  cp "$lw3_path" "$missing_reftime"
  python3 - "$missing_reftime" <<'PY'
import sys
import netCDF4

with netCDF4.Dataset(sys.argv[1], "r+") as dataset:
    dataset.renameVariable("reftime", "renamed_reftime")
PY
  expect_reject analysis_reftime_missing adapter_error=reftime-read \
    "$fua_path" "$fsf_path" "$missing_reftime"

  analysis_nonfinite=$test_tmp/analysis-reftime-nonfinite.lw3
  mutate_reftime "$lw3_path" "$analysis_nonfinite" nan
  expect_reject analysis_reftime_nonfinite adapter_error=reftime-read \
    "$fua_path" "$fsf_path" "$analysis_nonfinite"

  future_fsf=$test_tmp/future-reference.fsf
  mutate_reftime "$fsf_path" "$future_fsf" "$((epoch + 3600))"
  expect_reject fsf_reftime_future adapter_error=reftime-future \
    "$fua_path" "$future_fsf" "$lw3_path"

  future_fua=$test_tmp/future-reference.fua
  mutate_reftime "$fua_path" "$future_fua" "$((epoch + 3600))"
  expect_reject fua_reftime_future adapter_error=reftime-future \
    "$future_fua" "$fsf_path" "$lw3_path"

  future_boundary_fsf=$test_tmp/future-reference-boundary.fsf
  future_boundary_fua=$test_tmp/future-reference-boundary.fua
  mutate_reftime "$fsf_path" "$future_boundary_fsf" "${epoch}.5"
  mutate_reftime "$fua_path" "$future_boundary_fua" "${epoch}.5"
  expect_accept fsf_reftime_future_plus_half "$future_boundary_fua" \
    "$future_boundary_fsf" "$lw3_path"

  future_outside_fsf=$test_tmp/future-reference-outside.fsf
  future_outside_fua=$test_tmp/future-reference-outside.fua
  mutate_reftime "$fsf_path" "$future_outside_fsf" "${epoch}.5001"
  mutate_reftime "$fua_path" "$future_outside_fua" "${epoch}.5001"
  expect_reject fsf_reftime_future_plus_outside adapter_error=reftime-future \
    "$future_outside_fua" "$future_outside_fsf" "$lw3_path"

  mismatch_fua=$test_tmp/mismatched-cycle.fua
  mutate_reftime "$fua_path" "$mismatch_fua" "$((epoch - 3600))"
  expect_reject fua_cycle_mismatch adapter_error=forecast-cycle-mismatch \
    "$mismatch_fua" "$fsf_path" "$lw3_path"

  pair_plus_half=$test_tmp/pair-cycle-plus-half.fua
  mutate_reftime "$fua_path" "$pair_plus_half" "$background_epoch.5"
  expect_accept fua_cycle_plus_half "$pair_plus_half" "$fsf_path" "$lw3_path"

  pair_minus_half=$test_tmp/pair-cycle-minus-half.fua
  mutate_reftime "$fua_path" "$pair_minus_half" "$((background_epoch - 1)).5"
  expect_accept fua_cycle_minus_half "$pair_minus_half" "$fsf_path" "$lw3_path"

  pair_plus_outside=$test_tmp/pair-cycle-plus-outside.fua
  mutate_reftime "$fua_path" "$pair_plus_outside" "$background_epoch.5001"
  expect_reject fua_cycle_plus_outside adapter_error=forecast-cycle-mismatch \
    "$pair_plus_outside" "$fsf_path" "$lw3_path"

  pair_minus_outside=$test_tmp/pair-cycle-minus-outside.fua
  mutate_reftime "$fua_path" "$pair_minus_outside" "$((background_epoch - 1)).4999"
  expect_reject fua_cycle_minus_outside adapter_error=forecast-cycle-mismatch \
    "$pair_minus_outside" "$fsf_path" "$lw3_path"

  sha256sum -c "$inputs_manifest" > "$test_tmp/input_identity_post.log"
done

sha256sum -c "$source_manifest" > "$test_root/source_identity_post.log"
sha256sum -c "$inputs_manifest" > "$test_root/input_identity_post.log"
printf 'REFTIME_NAMED_PASS case=%s valid=%s forecast_ref=%s artifacts=%s\n' \
  "$case_id" "$valid_time" "$background_time" "$test_root"
