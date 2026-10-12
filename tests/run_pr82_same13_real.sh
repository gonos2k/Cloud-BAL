#!/usr/bin/env bash
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
workspace=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
baseline=$workspace/Cloud-BAL/scratch/cp02_baseline_real_ybn5ww3w
real_exe=$workspace/../KIM-meso/KIM_RDPS_MODL_V2026.2/main/real.exe
mpi=$workspace/../local/mpi/2021.18/bin/mpirun
runtime=$workspace/Cloud-BAL/scratch/metgrid_netcdf_runtime.YPWjEW/install/lib
if [[ $# != 2 ]]; then
  echo 'usage: run_pr82_same13_real.sh CANDIDATE_MET_EM NEW_RUN_ROOT' >&2
  exit 2
fi
met_em=$(realpath -e "$1")
run=$(realpath -m "$2")
[[ ! -e $run && ! -L $run ]] || { echo 'existing real run root rejected' >&2; exit 2; }
[[ $(sha256sum "$met_em" | cut -d' ' -f1) == ${CLOUD_BAL_PR82_MET_EM_SHA256:?set exact candidate met_em SHA256} ]]
[[ $(sha256sum "$real_exe" | cut -d' ' -f1) == fa76d4bb17c0c63ecfed12a09ed912ba149248c1378f45b1938b16d2f729bdff ]]
[[ $(sha256sum "$baseline/namelist.input" | cut -d' ' -f1) == 62857360c047e0ed8e8d10286fd7d0286adf35866f1491248019fe1733b89400 ]]
rg -q 'use_sh_qv[[:space:]]*=[[:space:]]*\.true\.' "$baseline/namelist.input"
. "$repo/tests/intel_toolchain.sh"
unset F_UFMTENDIAN
ulimit -s unlimited
export LD_LIBRARY_PATH="$runtime:${LD_LIBRARY_PATH:-}"
mkdir "$run"
cp "$met_em" "$run/met_em.d01.2026-08-16_13:00:00.nc"
cp "$baseline/namelist.input" "$run/namelist.input"
cp "$real_exe" "$run/real.exe"
sha256sum "$met_em" "$run/met_em.d01.2026-08-16_13:00:00.nc" \
  "$baseline/namelist.input" "$run/namelist.input" "$real_exe" "$run/real.exe" \
  "$repo/tests/run_pr82_same13_real.sh" "$repo/tests/pr82_same13_real_readback.py" \
  "$repo/tests/intel_toolchain.sh" > "$run/inputs.pre.sha256"
(
  cd "$run"
  "$mpi" -n 1 ./real.exe > real.log 2>&1
)
[[ -s $run/wrfinput_d01 ]]
python3 "$repo/tests/pr82_same13_real_readback.py" \
  "$run/met_em.d01.2026-08-16_13:00:00.nc" "$run/wrfinput_d01" "$run/readback.json"
sha256sum "$met_em" "$run/met_em.d01.2026-08-16_13:00:00.nc" \
  "$baseline/namelist.input" "$run/namelist.input" "$real_exe" "$run/real.exe" \
  "$repo/tests/run_pr82_same13_real.sh" "$repo/tests/pr82_same13_real_readback.py" \
  "$repo/tests/intel_toolchain.sh" > "$run/inputs.post.sha256"
cmp "$run/inputs.pre.sha256" "$run/inputs.post.sha256"
cat "$run/readback.json"
printf 'real_run=%s\n' "$run"
