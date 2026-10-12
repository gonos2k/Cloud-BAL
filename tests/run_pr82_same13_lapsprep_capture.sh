#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
workspace_root=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
prepared=$workspace_root/Cloud-BAL/scratch/cp02_maintained_derived_O0_qej27s72/matched_control_chain13_O0.b07iv296/prepared
scratch_root=${CLOUD_BAL_TEST_SCRATCH_ROOT:-/var/tmp}
mkdir -p "$scratch_root"
run_root=$(mktemp -d "$scratch_root/pr82_same13_lapsprep_capture.XXXXXX")
sha256sum "$repo_root/tests/run_pr82_same13_lapsprep_capture.sh" "$repo_root/tests/intel_toolchain.sh" \
  "$repo_root/tools/build_upstream_producer.sh" \
  "$workspace_root/klaps-v5.0_/src/lapsprep/lapsprep.f90" \
  "$workspace_root/klaps-v5.0_/src/lapsprep/module_lapsprep_wps.f90" \
  > "$run_root/runner_source_inputs.sha256"
private_repo=$run_root/Cloud-BAL
mkdir -p "$private_repo"
tar -C "$repo_root" --exclude='./.git' --exclude='./scratch' --exclude='./graphify-out' \
  --exclude='./.pytest_cache' -cf - . | tar -C "$private_repo" -xf -

python3 - "$private_repo/src/lapsprep/lapsprep.f90" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
source = path.read_text(encoding="utf-8")
anchor = """        CASE ('wps ')
          cloud_bal_wps_output=' '
"""
replacement = """        CASE ('wps ')
          cloud_bal_wps_output=' '
          BLOCK
            CHARACTER(LEN=2048) :: capture_path
            INTEGER :: capture_status,capture_unit
            CALL GET_ENVIRONMENT_VARIABLE('CLOUD_BAL_PR82_INVENTORY',capture_path,STATUS=capture_status)
            IF (capture_status==0 .AND. LEN_TRIM(capture_path)>0) THEN
              OPEN(NEWUNIT=capture_unit,FILE=TRIM(capture_path),STATUS='NEW', &
                   FORM='UNFORMATTED',ACCESS='SEQUENTIAL',ACTION='WRITE',IOSTAT=capture_status)
              IF (capture_status/=0) STOP 82
              WRITE(capture_unit,IOSTAT=capture_status) x,y,z3
              IF (capture_status==0) WRITE(capture_unit,IOSTAT=capture_status) &
                p,t,ht,u,v,rh,mr,lwc,rai,sno,ice,pic,psfc,slp,tskin,snocov
              CLOSE(capture_unit)
              IF (capture_status/=0) STOP 82
            ELSE IF (capture_status/=1) THEN
              STOP 82
            END IF
          END BLOCK
"""
if source.count(anchor) != 1:
    raise SystemExit("unique actual WPS caller insertion point not found")
path.write_text(source.replace(anchor, replacement), encoding="utf-8")
PY

input_hashes=$run_root/input_before.sha256
(cd "$prepared" && find static lapsprd -type f -print0 | sort -z | xargs -0 sha256sum) > "$input_hashes"
mkdir -p "$run_root/stage"
cp -aL "$prepared"/. "$run_root/stage/"
output_wps=$run_root/captured_baseline.wps
inventory=$run_root/lapsprep_inventory.bin
build_output=$(CLOUD_BAL_WORKSPACE_ROOT="$workspace_root" \
  CLOUD_BAL_BUILD_SCRATCH_ROOT="$run_root/builds" \
  bash "$private_repo/tools/build_upstream_producer.sh" lapsprep O2)
printf '%s\n' "$build_output" > "$run_root/build_console.log"
build_dir=$(sed -n '1p' "$run_root/build_console.log")
. "$repo_root/tests/intel_toolchain.sh"
exe=$build_dir/run_verified.sh
[[ -x $exe ]]
env -u CLOUD_BAL_SHADOW_EXPERIMENT -u CLOUD_BAL_STAGE_MODE -u CLOUD_BAL_STAGE_CONTEXT \
  LAPS_DATA_ROOT="$run_root/stage" CLOUD_BAL_WPS_OUTPUT="$output_wps" \
  CLOUD_BAL_PR82_INVENTORY="$inventory" \
  "$exe" 262281300 > "$run_root/lapsprep.log" 2>&1
(cd "$run_root/stage" && find static lapsprd -type f -print0 | sort -z | xargs -0 sha256sum) > "$run_root/input_after.sha256"
cmp "$run_root/input_before.sha256" "$run_root/input_after.sha256"
[[ -s $inventory && -s $output_wps ]]
sha256sum -c "$run_root/runner_source_inputs.sha256" > "$run_root/runner_source_inputs.check.log"
sha256sum "$private_repo/src/lapsprep/lapsprep.f90" "$inventory" "$output_wps" \
  "$build_dir/inputs.sha256" "$build_dir/runtime.sha256" "$build_dir/executable.sha256" \
  > "$run_root/artifacts.sha256"
printf 'capture_root=%s\nbuild_dir=%s\ninventory=%s\noutput_wps=%s\n' \
  "$run_root" "$build_dir" "$inventory" "$output_wps"
