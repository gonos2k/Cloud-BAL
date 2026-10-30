#!/usr/bin/env bash
set -euo pipefail
mode=${1:?mode}
case "$mode" in OFF|HYDRO|LIQUID_RADAR_RH1) ;; *) exit 2;; esac
label=${FORECAST_LABEL:-$mode}
repo=/var/tmp/cloudbal-current-forecast-paper
ws=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
root=$ws/scratch/current_forecast_paper_20261029/run.PomEr8
exe=$ws/Cloud-BAL/scratch/cp02_host_unit_contract_x3bcr8ui/host/main/wrf.exe
old=$ws/Cloud-BAL/scratch/cp02_six_hour_20260914/off/run
out=$root/forecast_$label
mkdir "$out"
rsync -aL --exclude='wrfinput*' --exclude='wrfout*' --exclude='rsl.*' --exclude='launcher.log' --exclude='run.exit' "$old/" "$out/"
cp "$root/native_$mode/real/wrfinput_d01" "$out/wrfinput_d01"
cd "$out"
printf '%s  %s\n' 74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45 wrfbdy_d01 eced598028b71b996c0c22cf7bd4bacb067087575ec06c4b65d71ab4913156df namelist.input de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168 "$exe" | sha256sum -c - > "$root/$label.fixed_check.log"
sha256sum namelist.input wrfinput_d01 wrfbdy_d01 physical_history.txt > "$root/$label.inputs.sha256"
find . -maxdepth 1 -type f -print0 | sort -z | xargs -0 sha256sum > "$root/$label.all_inputs.sha256"
. "$repo/tests/intel_toolchain.sh"
export OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
ulimit -s unlimited
printf 'start_utc=%s\n' "$(date -u +%FT%TZ)" > "$root/$label.run_metadata.txt"
set +e
timeout 14400 mpirun -np 8 "$exe" > launcher.log 2>&1
rc=$?
set -e
printf 'exit=%s\nend_utc=%s\n' "$rc" "$(date -u +%FT%TZ)" >> "$root/$label.run_metadata.txt"
sha256sum -c "$root/$label.inputs.sha256" > "$root/$label.postcheck.log"
sha256sum -c "$root/$label.all_inputs.sha256" > "$root/$label.all_postcheck.log"
exit "$rc"
