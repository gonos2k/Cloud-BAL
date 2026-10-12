#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
workspace_root=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
retained=/var/tmp/pr81_joint_thermo.HbL5ry
inputs_json=$retained/inputs.json.archive
coupled_nc=$retained/coupled.nc.archive
expected_candidate=/var/tmp/pr81_joint_thermo.HbL5ry/O2/joint_candidate.nc
baseline_wps=${CLOUD_BAL_PR82_BASELINE_WPS:-$workspace_root/Cloud-BAL/scratch/cp02_baseline_native_ruoww1a5/baseline_O0.wps}
expected_candidate_sha=135c2315d0953182d248ff650ad50fcab7c0b21075b208e693a04fd7f8487ef1
spec_path=$retained/thermo_density_prior_v4_spec.md.archive
spec_sha=3af8a49e2e270f0966d0bc68f33ced6a58678408efb1517428f6684beb69588d

[[ -f $inputs_json && -f $coupled_nc && -f $expected_candidate && -f $spec_path && -f $baseline_wps ]]
inventory=${CLOUD_BAL_PR82_INVENTORY:?set CLOUD_BAL_PR82_INVENTORY to the pinned same-time LAPSPREP capture}
[[ -s $inventory ]]
[[ $(sha256sum "$expected_candidate" | cut -d' ' -f1) == "$expected_candidate_sha" ]]
[[ $(sha256sum "$spec_path" | cut -d' ' -f1) == "$spec_sha" ]]
verify_bound_inputs() {
  python3 - "$inputs_json" <<'PY'
import hashlib,json,sys
from pathlib import Path
d=json.loads(Path(sys.argv[1]).read_text())
for group in ('authority_hashes','input_hashes'):
 for filename,expected in d[group].items():
  p=Path(filename)
  if not p.is_file(): raise SystemExit(f'missing frozen PR81 input: {p}')
  h=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
  if h.hexdigest()!=expected: raise SystemExit(f'frozen PR81 input hash mismatch: {p}')
PY
}
verify_bound_inputs
. "$repo_root/tests/intel_toolchain.sh"

nf_config=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config
netcdf_fortran_lib=$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a
netcdf_c_lib=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a
[[ $(sha256sum "$nf_config" | cut -d' ' -f1) == e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5 ]]
[[ $(sha256sum "$netcdf_fortran_lib" | cut -d' ' -f1) == f610d7ebedf48d17023e9b8377d74d93542bde40d091ec7a5518bb30d17c8a39 ]]
[[ $(sha256sum "$netcdf_c_lib" | cut -d' ' -f1) == f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288 ]]
read -r -a nf_flags <<<"$("$nf_config" --fflags)"
read -r -a nf_libs <<<"$("$nf_config" --flibs)"

scratch_root=${CLOUD_BAL_TEST_SCRATCH_ROOT:-/var/tmp}
mkdir -p "$scratch_root"
run_root=$(mktemp -d "$scratch_root/pr82_same13_candidate_wps.XXXXXX")
case "$run_root" in
  *[!A-Za-z0-9_./-]*) echo "unsafe generated scratch path: $run_root" >&2; exit 2 ;;
esac
[[ ! -e "$run_root/build/joint_candidate.nc" && ! -L "$run_root/build/joint_candidate.nc" ]]
mkdir -p "$run_root/source/src/common" "$run_root/source/src/lapsprep" "$run_root/build"

source_snapshot=$retained/source_snapshot
for name in cloud_bal_state cloud_bal_grid_geometry cloud_bal_column_physics \
  cloud_bal_balance_operator cloud_bal_pipeline cloud_bal_real_netcdf; do
  cp "$source_snapshot/src/common/$name.f90" "$run_root/source/src/common/"
done
cp "$source_snapshot/tests/pr81_joint_thermo_retained.f90" "$run_root/source/pr82_private_driver.f90"
for name in module_constants module_date_pack module_laps_static; do
  cp "$workspace_root/klaps-v5.0_/src/lapsprep/$name.f90" "$run_root/source/src/lapsprep/"
done
cp "$repo_root/src/lapsprep/module_setup.f90" "$repo_root/src/lapsprep/module_lapsprep_wps.f90" \
   "$repo_root/src/common/cloud_bal_wps_adapter.f90" \
   "$repo_root/tests/pr82_candidate_wps_hook.f90" "$run_root/source/src/lapsprep/"

python3 - "$run_root/source/pr82_private_driver.f90" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
use='  USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state,write_shadow_diagnostics\n'
if s.count(use)!=1: raise SystemExit('driver import insertion point is not unique')
s=s.replace(use,use+'  USE pr82_candidate_wps_hook, ONLY: write_pr82_candidate_wps\n')
anchor="  IF (writer_status/=STATUS_OK) ERROR STOP 'joint candidate writer rejected the receipt'\n"
call='''  IF (writer_status/=STATUS_OK) ERROR STOP 'joint candidate writer rejected the receipt'
  BLOCK
    CHARACTER(LEN=2048) :: wps_output
    CHARACTER(LEN=2048) :: candidate_hash_path,hash_line
    CHARACTER(LEN=128) :: expected_candidate_sha
    INTEGER :: wps_status,env_status,hash_unit
    CALL GET_ENVIRONMENT_VARIABLE('CLOUD_BAL_PR82_WPS_OUTPUT',wps_output,STATUS=env_status)
    IF (env_status/=0 .OR. LEN_TRIM(wps_output)==0) ERROR STOP 'missing isolated PR82 WPS output path'
    CALL GET_ENVIRONMENT_VARIABLE('CLOUD_BAL_PR82_CANDIDATE_SHA256',expected_candidate_sha,STATUS=env_status)
    IF (env_status/=0 .OR. TRIM(expected_candidate_sha)/='135c2315d0953182d248ff650ad50fcab7c0b21075b208e693a04fd7f8487ef1') &
      ERROR STOP 'unexpected PR81 candidate identity before WPS write'
    CALL GET_ENVIRONMENT_VARIABLE('CLOUD_BAL_PR82_HASH_FILE',candidate_hash_path,STATUS=env_status)
    IF (env_status/=0 .OR. LEN_TRIM(candidate_hash_path)==0) ERROR STOP 'missing candidate hash receipt path'
    CALL EXECUTE_COMMAND_LINE('sha256sum "'//TRIM(output_path)//'" > "'//TRIM(candidate_hash_path)//'"', &
      EXITSTAT=env_status)
    IF (env_status/=0) ERROR STOP 'candidate identity check failed before WPS write'
    OPEN(NEWUNIT=hash_unit,FILE=TRIM(candidate_hash_path),STATUS='OLD',ACTION='READ',IOSTAT=env_status)
    IF (env_status/=0) ERROR STOP 'candidate hash receipt could not be opened'
    READ(hash_unit,'(A)',IOSTAT=env_status) hash_line
    CLOSE(hash_unit)
    IF (env_status/=0 .OR. hash_line(1:64)/=TRIM(expected_candidate_sha)) &
      ERROR STOP 'candidate bytes differ from pinned PR81 artifact before WPS write'
    CALL write_pr82_candidate_wps(background,candidate,TRIM(wps_output),wps_status)
    IF (wps_status/=STATUS_OK) ERROR STOP 'PR82 existing WPS writer rejected candidate transfer'
  END BLOCK
'''
if s.count(anchor)!=1: raise SystemExit('candidate writer insertion point is not unique')
p.write_text(s.replace(anchor,call))
PY

source_files=(
  "$run_root/source/src/common/cloud_bal_state.f90"
  "$run_root/source/src/common/cloud_bal_grid_geometry.f90"
  "$run_root/source/src/common/cloud_bal_column_physics.f90"
  "$run_root/source/src/common/cloud_bal_balance_operator.f90"
  "$run_root/source/src/common/cloud_bal_pipeline.f90"
  "$run_root/source/src/common/cloud_bal_real_netcdf.f90"
  "$run_root/source/src/lapsprep/module_constants.f90"
  "$run_root/source/src/lapsprep/module_date_pack.f90"
  "$run_root/source/src/lapsprep/module_laps_static.f90"
  "$run_root/source/src/lapsprep/module_setup.f90"
  "$run_root/source/src/lapsprep/module_lapsprep_wps.f90"
  "$run_root/source/src/lapsprep/cloud_bal_wps_adapter.f90"
  "$run_root/source/src/lapsprep/pr82_candidate_wps_hook.f90"
  "$run_root/source/pr82_private_driver.f90"
)
sha256sum "${source_files[@]}" > "$run_root/source_pre.sha256"
sha256sum "$repo_root/tests/run_pr82_same13_candidate_wps.sh" \
  "$repo_root/tests/pr82_candidate_wps_readback.py" \
  "$repo_root/tests/pr82_candidate_wps_hook.f90" \
  "$repo_root/tests/intel_toolchain.sh" \
  > "$run_root/runner_inputs.pre.sha256"
sha256sum "$inputs_json" "$coupled_nc" "$spec_path" "$baseline_wps" "$expected_candidate" "$inventory" \
  > "$run_root/input_pre.sha256"

build=$run_root/build
cd "$build"
pwd -P > "$run_root/build.cwd"
for source in "${source_files[@]}"; do
  object=$(basename "${source%.f90}.o")
  compile_flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  if [[ $(basename "$source") == module_lapsprep_wps.f90 ]]; then
    compile_flags+=( -convert big_endian )
  fi
  "$CLOUD_BAL_FC" -c "${compile_flags[@]}" -module "$build" -I "$build" \
    "${nf_flags[@]}" "$source" -o "$object" >"$object.log" 2>&1
done
objects=()
for source in "${source_files[@]}"; do objects+=("$(basename "${source%.f90}.o")"); done
"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" -module "$build" -I "$build" \
  "${objects[@]}" "${nf_libs[@]}" -o "$build/pr82-candidate-wps" >link.log 2>&1
sha256sum "$build/pr82-candidate-wps" > "$run_root/executable.sha256"

mapfile -t driver_args < <(PR82_INPUTS_JSON="$inputs_json" python3 -c \
  'import json,os; print("\n".join(json.load(open(os.environ["PR82_INPUTS_JSON"]))["driver_arguments"]))')
[[ ${#driver_args[@]} == 13 ]]
lsx=${driver_args[9]}
root=${lsx%/lapsprd/lsx/*}
[[ -f $lsx ]]
candidate_out=$run_root/build/joint_candidate.nc
wps_out=$run_root/build/candidate.wps
env CLOUD_BAL_PR82_LAPS_ROOT="$root" CLOUD_BAL_PR82_INVENTORY="$inventory" \
  CLOUD_BAL_PR82_WPS_OUTPUT="$wps_out" \
  CLOUD_BAL_PR82_CANDIDATE_SHA256="$expected_candidate_sha" \
  CLOUD_BAL_PR82_HASH_FILE="$run_root/build/candidate.prewrite.sha256" \
  "$build/pr82-candidate-wps" "${driver_args[@]}" "$coupled_nc" "$candidate_out" \
  > "$run_root/build/run.log" 2>&1
[[ $(sha256sum "$candidate_out" | cut -d' ' -f1) == "$expected_candidate_sha" ]]
[[ -s $wps_out ]]
python3 "$repo_root/tests/pr82_candidate_wps_readback.py" "$expected_candidate" \
  "$baseline_wps" "$wps_out" "$inventory" "$run_root/build/readback.json"
sha256sum "${source_files[@]}" > "$run_root/source_post.sha256"
sha256sum "$repo_root/tests/run_pr82_same13_candidate_wps.sh" \
  "$repo_root/tests/pr82_candidate_wps_readback.py" \
  "$repo_root/tests/pr82_candidate_wps_hook.f90" \
  "$repo_root/tests/intel_toolchain.sh" \
  > "$run_root/runner_inputs.post.sha256"
cmp "$run_root/runner_inputs.pre.sha256" "$run_root/runner_inputs.post.sha256"
sha256sum "$inputs_json" "$coupled_nc" "$spec_path" "$baseline_wps" "$expected_candidate" "$inventory" \
  > "$run_root/input_post.sha256"
cmp "$run_root/source_pre.sha256" "$run_root/source_post.sha256"
cmp "$run_root/input_pre.sha256" "$run_root/input_post.sha256"
verify_bound_inputs
cat "$run_root/build/readback.json"
printf 'run_root=%s\n' "$run_root"
