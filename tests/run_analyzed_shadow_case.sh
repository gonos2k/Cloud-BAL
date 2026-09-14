#!/usr/bin/env bash
# Run one direct pressure-analysis experiment. Never publish or install.
set -euo pipefail
[[ $# == 3 || $# == 4 ]] || { echo 'Usage: bash run_analyzed_shadow_case.sh RUNTIME STAMP EPOCH [--thermo-liquid-radar|--thermo-liquid-radar-phi|--thermo-liquid-radar-surface-phi]' >&2; exit 2; }
experiment_args=()
if [[ $# == 4 ]]; then
  [[ $4 == --thermo-liquid-radar || $4 == --thermo-liquid-radar-phi || $4 == --thermo-liquid-radar-surface-phi ]] || { echo 'Unknown experiment option' >&2; exit 2; }
  experiment_args+=("$4")
fi
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
runtime=$(realpath -e "$1")
stamp=$2
epoch=$3
[[ $runtime == "$repo_root/scratch/"* && $stamp =~ ^[0-9]{9}$ && $epoch =~ ^[0-9]+$ ]] || exit 2
source "$repo_root/tests/intel_toolchain.sh"
build=$(mktemp -d "$repo_root/scratch/analyzed_shadow.XXXXXX")
printf '%s\n' "$build"
cd "$build"
nf_config="$repo_root/../klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config"
[[ $(sha256sum "$nf_config" | cut -d' ' -f1) == e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5 ]]
netcdff="$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a"
netcdf="$repo_root/../klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a"
[[ $(sha256sum "$netcdff" | cut -d' ' -f1) == f610d7ebedf48d17023e9b8377d74d93542bde40d091ec7a5518bb30d17c8a39 ]]
[[ $(sha256sum "$netcdf" | cut -d' ' -f1) == f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288 ]]
read -r -a nf_flags <<<"$("$nf_config" --fflags)"
read -r -a nf_libs <<<"$("$nf_config" --flibs)"
sources=()
for name in cloud_bal_state cloud_bal_column_physics cloud_bal_grid_geometry \
            cloud_bal_balance_operator cloud_bal_pipeline cloud_bal_real_netcdf \
            cloud_bal_pressure_analysis; do
  sources+=("$repo_root/src/common/$name.f90")
done
sources+=("$repo_root/tests/real_shadow_driver.f90")
inputs=("$runtime/static/static.nest7grid")
for kind in lw3 vrz vrt lt1 lq3 lwc lsx; do
  inputs+=("$runtime/lapsprd/$kind/$stamp.$kind")
done
python3 - "$repo_root" "${inputs[@]}" <<'PY'
import sys
import netCDF4
import numpy as np
sys.path.insert(0, sys.argv[1] + "/tools")
from check_qbal_real_inputs import inspect_navigation
with netCDF4.Dataset(sys.argv[-1]) as reference:
    for path in sys.argv[3:-1]:
        findings = []
        with netCDF4.Dataset(path) as candidate:
            inspect_navigation(candidate, reference, findings)
        if findings:
            raise SystemExit(f"{path}: {findings}")
    # Static Latin1/2 carry obsolete degrees_east labels. Compare its encoded
    # numbers exactly; product-to-product unit checks above remain strict.
    with netCDF4.Dataset(sys.argv[2]) as static:
        for name in ("Nx", "Ny", "La1", "Lo1", "LoV", "Latin1", "Latin2", "Dx", "Dy"):
            if not np.array_equal(static[name][:], reference[name][:]):
                raise SystemExit(f"static navigation mismatch: {name}")
print("Existing-product navigation matches static grid")
PY
sha256sum "${sources[@]}" "${inputs[@]}" "$nf_config" "$netcdff" "$netcdf" \
  "$CLOUD_BAL_FC" "$repo_root/tests/run_analyzed_shadow_case.sh" "$repo_root/tools/check_qbal_real_inputs.py" \
  "$repo_root/tools/validate_shadow_diagnostics.py" \
  > "$build/inputs.sha256"
"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" \
  -module "$build" -I "$build" "${nf_flags[@]}" \
  "${sources[@]}" "${nf_libs[@]}" -o "$build/driver" > "$build/build.log" 2>&1
ulimit -s unlimited
# Deliberately nonexistent FUA/FSF arguments prove no background fallback.
set +e
OMP_NUM_THREADS=1 timeout 300 "$build/driver" \
  "$build/unused.fua" "$build/unused.fsf" \
  "$runtime/lapsprd/lw3/$stamp.lw3" "$runtime/lapsprd/vrz/$stamp.vrz" \
  "$runtime/lapsprd/vrt/$stamp.vrt" "$runtime/static/static.nest7grid" \
  "$build/shadow.nc" "$epoch" \
  "$runtime/lapsprd/lt1/$stamp.lt1" "$runtime/lapsprd/lq3/$stamp.lq3" \
  "$runtime/lapsprd/lwc/$stamp.lwc" "$runtime/lapsprd/lsx/$stamp.lsx" \
  "${experiment_args[@]}" \
  > "$build/run.log" 2>&1
run_status=$?
set -e
if [[ $run_status == 0 ]]; then
  python3 "$repo_root/tools/validate_shadow_diagnostics.py" "$build/shadow.nc" \
    --json "$build/validation.json" > "$build/validation.log" 2>&1 || run_status=$?
  if [[ $run_status != 0 ]]; then
    tail -25 "$build/validation.log"
  fi
fi
sha256sum -c --quiet "$build/inputs.sha256"
printf 'experiment_exit=%s\n' "$run_status"
tail -25 "$build/run.log"
exit "$run_status"
