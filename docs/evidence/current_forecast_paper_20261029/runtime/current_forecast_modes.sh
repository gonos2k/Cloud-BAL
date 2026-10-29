#!/usr/bin/env bash
set -euo pipefail
repo=/var/tmp/cloudbal-current-forecast-paper
ws=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
src=$ws/Cloud-BAL/scratch/cp02_maintained_derived_O0_qej27s72/matched_control_chain12_O0.ym17bs9h/prepared
root=$ws/scratch/current_forecast_paper_20261029/run.PomEr8
build=/var/tmp/upstream_lapsprep_build.mRUsUm
. "$repo/tests/intel_toolchain.sh"
export OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE OMP_STACKSIZE=128M LANG=C
ulimit -s unlimited
(cd "$src" && find static lapsprd -type f -print0 | sort -z | xargs -0 sha256sum) > "$root/initial_source_before.sha256"
for mode in OFF HYDRO LIQUID_RADAR_RH1; do
 d="$root/init_$mode"; mkdir "$d"; cp -aL "$src" "$d/input"; mkdir "$d/work"
 python3 - "$d/input/static/lapsprep.nl" <<'PY'
import sys
from pathlib import Path
p=Path(sys.argv[1]); s=p.read_text(); assert s.count('wps_output_vapor=.false.')==1
p.write_text(s.replace('wps_output_vapor=.false.', 'wps_output_vapor=.true.'))
PY
 (cd "$d/input" && find static lapsprd -type f -print0 | sort -z | xargs -0 sha256sum) > "$d/inputs_before.sha256"
 (cd "$d/work" && env -u CLOUD_BAL_STAGE_MODE -u CLOUD_BAL_STAGE_CONTEXT CLOUD_BAL_SHADOW_EXPERIMENT="$mode" LAPS_DATA_ROOT="$d/input" TMPDIR="$d/work" CLOUD_BAL_WPS_OUTPUT="$d/output.wps" "$build/run_verified.sh" 262281200 > "$d/lapsprep.log" 2>&1)
 (cd "$d/input" && find static lapsprd -type f -print0 | sort -z | xargs -0 sha256sum) > "$d/inputs_after.sha256"
 cmp "$d/inputs_before.sha256" "$d/inputs_after.sha256"
 test -s "$d/output.wps"
 if [[ $mode != OFF ]]; then test -s "$d/output.wps.shadow.nc"; fi
 sha256sum "$d/output.wps" "$d/input/static/lapsprep.nl" > "$d/outputs.sha256"
 [[ $mode == OFF ]] || sha256sum "$d/output.wps.shadow.nc" >> "$d/outputs.sha256"
done
(cd "$src" && find static lapsprd -type f -print0 | sort -z | xargs -0 sha256sum) > "$root/initial_source_after.sha256"
cmp "$root/initial_source_before.sha256" "$root/initial_source_after.sha256"
