#!/usr/bin/env bash
set -euo pipefail
mode=${1:?mode required}
case "$mode" in OFF|HYDRO|LIQUID_RADAR_RH1) ;; *) exit 2;; esac
repo=/var/tmp/cloudbal-current-forecast-paper
ws=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
root=$ws/scratch/current_forecast_paper_20261029/run.PomEr8
old=$ws/Cloud-BAL/scratch/cp02_actual12_liquid_wps.HisIOM
r="$root/native_$mode"
test -s "$root/init_$mode/outputs.sha256"
mkdir -p "$r/metgrid" "$r/real" "$r/tmp"
rsync -aL --exclude='LAPS:*' --exclude='met_em*' --exclude='*.log' --exclude='executable.path' "$old/metgrid_HYDRO/" "$r/metgrid/"
cp "$root/init_$mode/output.wps" "$r/metgrid/LAPS:2026-08-16_12:00"
rsync -aL --exclude='wrfinput*' --exclude='wrfbdy*' --exclude='met_em.d01.2026-08-16_12:00:00.nc' --exclude='rsl.*' --exclude='*.log' --exclude='executable.path' "$old/real_HYDRO/" "$r/real/"
metexe=$ws/Cloud-BAL/scratch/cp02_native_12_15.B4Lwmh/metgrid/metgrid.exe
realexe=$ws/Cloud-BAL/scratch/cp02_host_process_domain_fm547n5i/host/main/real.exe
printf '%s  %s\n' 3107306ad0f8702e818eb84d8d4f9c96561b3632ffbaf2b157b5e284e1a18afe "$metexe" 58118b30f35f1e817cd500fc0047ee3e0b334975a3231faf3a46b3a5728c5c10 "$realexe" | sha256sum -c - > "$r/executables_check.log"
(cd "$r/metgrid" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$r/metgrid_inputs.sha256"
. "$repo/tests/intel_toolchain.sh"
export LD_LIBRARY_PATH="$ws/Cloud-BAL/scratch/metgrid_netcdf_runtime.YPWjEW/install/lib:${LD_LIBRARY_PATH:-}" OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE TMPDIR="$r/tmp"
ulimit -s unlimited
(cd "$r/metgrid" && timeout 600 "$metexe" > "$r/metgrid.log" 2>&1)
test -s "$r/metgrid/met_em.d01.2026-08-16_12:00:00.nc"
cp "$r/metgrid/met_em.d01.2026-08-16_12:00:00.nc" "$r/real/"
(cd "$r/real" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$r/real_inputs.sha256"
(cd "$r/real" && timeout 600 "$realexe" > "$r/real.log" 2>&1)
test -s "$r/real/wrfinput_d01"
grep -q 'SUCCESS COMPLETE REAL_EM INIT' "$r/real/rsl.out.0000"
sha256sum "$r/real/wrfinput_d01" "$r/metgrid/met_em.d01.2026-08-16_12:00:00.nc" > "$r/outputs.sha256"
