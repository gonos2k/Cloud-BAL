#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=${CLOUD_BAL_WORKSPACE_ROOT:-/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50}
scratch_root=${CLOUD_BAL_TEST_SCRATCH_ROOT:-/var/tmp}
mkdir -p "$scratch_root"
run_root=$(mktemp -d "$scratch_root/cloud_bal_pr73_joint_analysis.XXXXXX")
printf 'PR73 manufactured joint-analysis run directory: %s\n' "$run_root"

. "$repo_root/tests/intel_toolchain.sh"
profile=${PR73_PROFILE:-O0}
case "$profile" in
  O0) profile_flags=("${CLOUD_BAL_FREE_FLAGS[@]}");;
  O2) profile_flags=("${CLOUD_BAL_REPRO_FLAGS[@]}");;
  *) printf 'unsupported PR73_PROFILE: %s (expected O0 or O2)\n' "$profile" >&2; exit 2;;
esac
nf_config=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config
read -r -a nf_fflags <<<"$($nf_config --fflags)"
read -r -a nf_flibs <<<"$($nf_config --flibs)"
{
  printf 'profile=%s\n' "$profile"
  printf 'compiler=%s\n' "$CLOUD_BAL_FC"
  printf 'compiler_version=%s\n' "$cloud_bal_fc_version"
  printf 'compiler_sha256=%s\n' "$cloud_bal_fc_sha256"
  printf 'profile_flags='; printf '%s ' "${profile_flags[@]}"; printf '\n'
  printf 'nf_config=%s\n' "$nf_config"
  printf 'netcdf_fflags='; printf '%s ' "${nf_fflags[@]}"; printf '\n'
  printf 'netcdf_flibs='; printf '%s ' "${nf_flibs[@]}"; printf '\n'
  for source_file in \
      "$repo_root/src/common/cloud_bal_pipeline.f90" \
      "$repo_root/src/common/cloud_bal_real_netcdf.f90" \
      "$repo_root/tests/test_real_shadow_io_contract.f90" \
      "$repo_root/tools/pr73_joint_analysis.py" \
      "$repo_root/tests/check_physical_contract_shadow.py"; do
    sha256sum "$source_file"
  done
} > "$run_root/toolchain.txt"
cd "$run_root"

sources=(cloud_bal_state cloud_bal_grid_geometry cloud_bal_column_physics
         cloud_bal_balance_operator cloud_bal_pipeline cloud_bal_real_netcdf
         cloud_bal_pressure_analysis)
objects=()
for source in "${sources[@]}"; do
  object=$run_root/$source.o
  "$CLOUD_BAL_FC" -c "${profile_flags[@]}" -module "$run_root" -I "$run_root" \
    "${nf_fflags[@]}" "$repo_root/src/common/$source.f90" -o "$object"
  objects+=("$object")
done
for source_path in "$repo_root/tests/wps_module_stubs.f90" \
                   "$repo_root/src/common/cloud_bal_wps_adapter.f90" \
                   "$repo_root/src/lapsprep/module_lapsprep_wps.f90"; do
  source_name=$(basename "$source_path" .f90)
  object=$run_root/$source_name.o
  "$CLOUD_BAL_FC" -c "${profile_flags[@]}" -module "$run_root" -I "$run_root" \
    "${nf_fflags[@]}" "$source_path" -o "$object"
  objects+=("$object")
done
"$CLOUD_BAL_FC" "${profile_flags[@]}" -module "$run_root" -I "$run_root" \
  "${nf_fflags[@]}" "$repo_root/tests/test_real_shadow_io_contract.f90" \
  "${objects[@]}" "${nf_flibs[@]}" -o "$run_root/test_real_shadow_io_contract"

python3 "$repo_root/tools/pr73_joint_analysis.py" \
  "$repo_root/docs/evidence/pr73_joint_fixture_20261008.json" \
  --output "$run_root/trial.json" --physical-control "$run_root/trial.control" > "$run_root/solver.json"
./test_real_shadow_io_contract "$run_root/trial.control" > "$run_root/candidate.log" 2>&1
python3 "$repo_root/tests/check_physical_contract_shadow.py" \
  "$run_root/pr73-estimated-analysis-shadow.nc" > "$run_root/readback.log" 2>&1
cat "$run_root/candidate.log" "$run_root/readback.log"
printf 'trial_json=%s\nartifact=%s\n' "$run_root/trial.json" \
  "$run_root/pr73-estimated-analysis-shadow.nc"
