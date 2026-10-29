#!/usr/bin/env bash
set -euo pipefail
root=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/current_forecast_paper_20261029/run.PomEr8
finished() { [[ -f $1 ]] && grep -q '^end_utc=' "$1"; }
while ! finished "$root/original_run_metadata.txt" && ! finished "$root/OFF.run_metadata.txt"; do sleep 10; done
bash /var/tmp/current_forecast_wrf.sh HYDRO > /var/tmp/current_forecast_wrf_hydro.log 2>&1 &
hydro_pid=$!
while :; do
 count=0
 for f in "$root/original_run_metadata.txt" "$root/OFF.run_metadata.txt" "$root/HYDRO.run_metadata.txt"; do
   if finished "$f"; then count=$((count+1)); fi
 done
 (( count >= 2 )) && break
 if ! kill -0 "$hydro_pid" 2>/dev/null && ! finished "$root/HYDRO.run_metadata.txt"; then
   printf 'HYDRO failed before launch; aborting queue\n' >&2; exit 1
 fi
 sleep 10
done
bash /var/tmp/current_forecast_wrf.sh LIQUID_RADAR_RH1 > /var/tmp/current_forecast_wrf_liquid.log 2>&1 &
liquid_pid=$!
wait "$hydro_pid"
wait "$liquid_pid"
