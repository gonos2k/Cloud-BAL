#!/usr/bin/env bash
set -euo pipefail
repo=/var/tmp/cloudbal-current-forecast-paper
ws=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
src=$ws/Cloud-BAL/scratch/cp02_maintained_derived_O0_qej27s72/matched_control_chain12_O0.ym17bs9h/prepared
build=/var/tmp/upstream_lapsprep_build.mRUsUm
root=$(mktemp -d /var/tmp/current_forecast_off.XXXXXX)
printf '%s\n' "$root"
. "$repo/tests/intel_toolchain.sh"
sha256sum -c "$build/inputs.sha256" > "$root/build_input_check.log"
sha256sum -c "$build/runtime.sha256" > "$root/runtime_check.log"
sha256sum -c "$build/executable.sha256" > "$root/executable_check.log"
(cd "$src" && find static lapsprd -type f -print0 | sort -z | xargs -0 sha256sum) > "$root/source_before.sha256"
cp -aL "$src" "$root/input"
(cd "$root/input" && find static lapsprd -type f -print0 | sort -z | xargs -0 sha256sum) > "$root/copy_before.sha256"
cmp "$root/source_before.sha256" "$root/copy_before.sha256"
mkdir "$root/work"
export OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE OMP_STACKSIZE=128M LANG=C LAPS_DATA_ROOT="$root/input" TMPDIR="$root/work"
ulimit -s unlimited
(cd "$root/work" && env -u CLOUD_BAL_STAGE_MODE -u CLOUD_BAL_STAGE_CONTEXT -u CLOUD_BAL_SHADOW_EXPERIMENT CLOUD_BAL_WPS_OUTPUT="$root/current_off_legacy.wps" "$build/run_verified.sh" 262281200 > "$root/lapsprep.log" 2>&1)
(cd "$src" && find static lapsprd -type f -print0 | sort -z | xargs -0 sha256sum) > "$root/source_after.sha256"
(cd "$root/input" && find static lapsprd -type f -print0 | sort -z | xargs -0 sha256sum) > "$root/copy_after.sha256"
cmp "$root/source_before.sha256" "$root/source_after.sha256"
cmp "$root/copy_before.sha256" "$root/copy_after.sha256"
test -s "$root/current_off_legacy.wps"
sha256sum "$root/current_off_legacy.wps" "$ws/Cloud-BAL/scratch/cp02_native_12_18_AkoPPp/metgrid/LAPS:2026-08-16_12:00" "$build/inputs.sha256" "$build/runtime.sha256" "$build/executable.sha256" > "$root/results.sha256"
