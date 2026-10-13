#!/usr/bin/env bash
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
workspace=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
baseline=$workspace/Cloud-BAL/scratch/cp02_baseline_real_ybn5ww3w
real_exe=$workspace/../KIM-meso/KIM_RDPS_MODL_V2026.2/main/real.exe
mpi=$workspace/../local/mpi/2021.18/bin/mpirun
runtime=$workspace/Cloud-BAL/scratch/metgrid_netcdf_runtime.YPWjEW/install/lib
if [[ $# != 4 ]]; then
  echo 'usage: run_pr83_same13_off_real_boundary.sh MET_EM_13 MET_EM_14 MET_EM_15 NEW_RUN_ROOT' >&2
  exit 2
fi
met13=$(realpath -e "$1")
met14=$(realpath -e "$2")
met15=$(realpath -e "$3")
run=$(realpath -m "$4")
[[ ! -e $run && ! -L $run ]] || { echo 'existing boundary run root rejected' >&2; exit 2; }
[[ $(sha256sum "$met13" | cut -d' ' -f1) == ${CLOUD_BAL_PR83_OFF_MET13_SHA256:?set exact OFF 13 UTC metgrid product SHA256} ]]
[[ $(sha256sum "$met14" | cut -d' ' -f1) == 4015054ed0b059142873a6a0d7d153ff0297156166fb58e72774f0ac28a3938d ]]
[[ $(sha256sum "$met15" | cut -d' ' -f1) == fc61a3885e6cdbbdead9c63b8b67c84018167e253a951e3412d3f1e1bdd6f3ab ]]
[[ $(sha256sum "$real_exe" | cut -d' ' -f1) == fa76d4bb17c0c63ecfed12a09ed912ba149248c1378f45b1938b16d2f729bdff ]]
[[ $(sha256sum "$baseline/namelist.input" | cut -d' ' -f1) == 62857360c047e0ed8e8d10286fd7d0286adf35866f1491248019fe1733b89400 ]]
. "$repo/tests/intel_toolchain.sh"
unset F_UFMTENDIAN
ulimit -s unlimited
export LD_LIBRARY_PATH="$runtime:${LD_LIBRARY_PATH:-}"
mkdir "$run"
cp "$met13" "$run/met_em.d01.2026-08-16_13:00:00.nc"
cp "$met14" "$run/met_em.d01.2026-08-16_14:00:00.nc"
cp "$met15" "$run/met_em.d01.2026-08-16_15:00:00.nc"
cp "$baseline/namelist.input" "$run/namelist.input"
cp "$real_exe" "$run/real.exe"
cp "$workspace/Cloud-BAL/scratch/pr83_same13_off_real_20261013a/wrfinput_d01" \
  "$run/single_time_wrfinput_d01"
python3 - "$run/namelist.input" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
for old, new in ((" end_hour                            = 13,", " end_hour                            = 15,"),
                 (" interval_seconds                    = 10800,", " interval_seconds                    = 3600,")):
    if text.count(old) != 1:
        raise SystemExit(f"unique required namelist setting not found: {old.strip()}")
    text = text.replace(old, new)
if " start_hour                          = 13," not in text:
    raise SystemExit("start time must remain 13 UTC")
if " use_sh_qv                           = .true.," not in text:
    raise SystemExit("direct-QV use_sh_qv setting changed")
if " sfcp_to_sfcp                        = .true.," not in text:
    raise SystemExit("surface pressure setting changed")
path.write_text(text)
PY
python3 "$repo/tests/pr82_same13_real_boundary_readback.py" \
  --inputs "$run/met_em.d01.2026-08-16_13:00:00.nc" \
  "$run/met_em.d01.2026-08-16_14:00:00.nc" \
  "$run/met_em.d01.2026-08-16_15:00:00.nc" \
  --namelist "$run/namelist.input" \
  --validate-inputs-only "$run/input_contract.json"
sha256sum "$met13" "$met14" "$met15" "$run/met_em.d01.2026-08-16_13:00:00.nc" \
  "$run/met_em.d01.2026-08-16_14:00:00.nc" "$run/met_em.d01.2026-08-16_15:00:00.nc" \
  "$baseline/namelist.input" "$run/namelist.input" "$real_exe" "$run/real.exe" \
  "$run/single_time_wrfinput_d01" \
  "$repo/tests/run_pr83_same13_off_real_boundary.sh" \
  "$repo/tests/pr82_same13_real_boundary_readback.py" "$repo/tests/intel_toolchain.sh" \
  > "$run/inputs.pre.sha256"
set +e
(cd "$run" && "$mpi" -n 1 ./real.exe > real.log 2>&1)
run_status=$?
set -e
printf '%s\n' "$run_status" > "$run/real.exit.status"
if ((run_status != 0)); then
  echo "real.exe failed with status $run_status; retained diagnostics: $run" >&2
  exit "$run_status"
fi
[[ -s $run/wrfinput_d01 && -s $run/wrfbdy_d01 ]]
python3 "$repo/tests/pr82_same13_real_boundary_readback.py" \
  --verify-output "$run/input_contract.json" "$run/wrfinput_d01" "$run/wrfbdy_d01" \
  "$run/single_time_wrfinput_d01"
sha256sum "$met13" "$met14" "$met15" "$run/met_em.d01.2026-08-16_13:00:00.nc" \
  "$run/met_em.d01.2026-08-16_14:00:00.nc" "$run/met_em.d01.2026-08-16_15:00:00.nc" \
  "$baseline/namelist.input" "$run/namelist.input" "$real_exe" "$run/real.exe" \
  "$run/single_time_wrfinput_d01" \
  "$repo/tests/run_pr83_same13_off_real_boundary.sh" \
  "$repo/tests/pr82_same13_real_boundary_readback.py" "$repo/tests/intel_toolchain.sh" \
  > "$run/inputs.post.sha256"
cmp "$run/inputs.pre.sha256" "$run/inputs.post.sha256"
printf 'real_boundary_run=%s\n' "$run"
