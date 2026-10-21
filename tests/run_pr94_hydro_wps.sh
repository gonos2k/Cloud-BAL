#!/usr/bin/env bash
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
workspace=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
candidate=${1:?usage: run_pr94_hydro_wps.sh HYDRO.nc NEW_RUN_ROOT}
run=$(realpath -m "$2")
inputs=/var/tmp/pr78_cp06a_spatial.V9LYrN/inputs.json
inventory=/var/tmp/pr82_same13_lapsprep_capture.WA4vyK/lapsprep_inventory.bin
baseline=/var/tmp/pr82_same13_lapsprep_capture.WA4vyK/captured_baseline.wps
nf_config=$workspace/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config
nf_lib=$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a
nc_lib=$workspace/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a
candidate_sha=${CLOUD_BAL_PR94_SOURCE_CANDIDATE_SHA256:-5e69e8b1c2f36119cead2ca4b6ca632a8898a2fa1082d9faa9dd1ea5075b7535}

[[ ! -e $run && ! -L $run ]]
[[ $(sha256sum "$candidate" | cut -d' ' -f1) == "$candidate_sha" ]]
[[ $(sha256sum "$nf_config" | cut -d' ' -f1) == e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5 ]]
[[ $(sha256sum "$nf_lib" | cut -d' ' -f1) == f610d7ebedf48d17023e9b8377d74d93542bde40d091ec7a5518bb30d17c8a39 ]]
[[ $(sha256sum "$nc_lib" | cut -d' ' -f1) == f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288 ]]
[[ $(sha256sum "$inventory" | cut -d' ' -f1) == ee5c4e56384d4830d4979875f6db1416e28987d3673358d0373e73f60a550603 ]]

. "$repo/tests/intel_toolchain.sh"
mkdir -p "$run/source/common" "$run/source/lapsprep" "$run/build"
printf 'build_working_directory=%s\n' "$(cd "$run/build" && pwd -P)" > "$run/build/build_context.txt"
source_snapshot=/var/tmp/pr81_joint_thermo.HbL5ry/source_snapshot
for name in cloud_bal_state cloud_bal_grid_geometry cloud_bal_column_physics \
  cloud_bal_balance_operator cloud_bal_pipeline cloud_bal_real_netcdf; do
  cp "$repo/src/common/$name.f90" "$run/source/common/"
done
for name in module_constants module_date_pack module_laps_static; do
  cp "$workspace/klaps-v5.0_/src/lapsprep/$name.f90" "$run/source/lapsprep/"
done
cp "$repo/src/lapsprep/module_setup.f90" "$repo/src/lapsprep/module_lapsprep_wps.f90" \
   "$repo/src/common/cloud_bal_wps_adapter.f90" "$repo/tests/pr82_candidate_wps_hook.f90" \
   "$repo/tests/pr94_hydro_wps_hook.f90" "$repo/tests/pr94_hydro_wps_driver.f90" \
   "$run/source/lapsprep/"
source_files=(
  "$run/source/common/cloud_bal_state.f90"
  "$run/source/common/cloud_bal_grid_geometry.f90"
  "$run/source/common/cloud_bal_column_physics.f90"
  "$run/source/common/cloud_bal_balance_operator.f90"
  "$run/source/common/cloud_bal_pipeline.f90"
  "$run/source/common/cloud_bal_real_netcdf.f90"
  "$run/source/lapsprep/module_constants.f90"
  "$run/source/lapsprep/module_date_pack.f90"
  "$run/source/lapsprep/module_laps_static.f90"
  "$run/source/lapsprep/module_setup.f90"
  "$run/source/lapsprep/module_lapsprep_wps.f90"
  "$run/source/lapsprep/cloud_bal_wps_adapter.f90"
  "$run/source/lapsprep/pr82_candidate_wps_hook.f90"
  "$run/source/lapsprep/pr94_hydro_wps_hook.f90"
  "$run/source/lapsprep/pr94_hydro_wps_driver.f90"
)
sha256sum "${source_files[@]}" > "$run/source_pre.sha256"
read -r -a nf_flags <<<"$("$nf_config" --fflags)"
read -r -a nf_libs <<<"$("$nf_config" --flibs)"
for source in "${source_files[@]}"; do
  object=$(basename "${source%.f90}.o")
  flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  if [[ $(basename "$source") == module_lapsprep_wps.f90 ]]; then flags+=( -convert big_endian ); fi
  (cd "$run/build" && "$CLOUD_BAL_FC" -c "${flags[@]}" -module "$run/build" -I "$run/build" \
    "${nf_flags[@]}" "$source" -o "$object") > "$run/build/$object.log" 2>&1
done
objects=()
for source in "${source_files[@]}"; do objects+=("$(basename "${source%.f90}.o")"); done
(cd "$run/build" && "$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" -module "$run/build" -I "$run/build" \
  "${objects[@]}" "${nf_libs[@]}" -o "$run/build/pr94-hydro-wps") > "$run/build/link.log" 2>&1

mapfile -t args < <(python3 - "$inputs" <<'PY'
import json, sys
print("\n".join(json.load(open(sys.argv[1]))["driver_arguments"]))
PY
)
[[ ${#args[@]} == 13 ]]
python3 - "$inputs" <<'PY'
import hashlib, json, sys
from pathlib import Path
data=json.loads(Path(sys.argv[1]).read_text())
for path,expected in data["input_hashes"].items():
    h=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if h != expected: raise SystemExit(f"PR78 source input hash mismatch: {path}")
PY
python3 - "$candidate" <<'PY'
import sys
import netCDF4
import numpy as np
path = sys.argv[1]
with netCDF4.Dataset(path) as dataset:
    if int(dataset.getncattr("requested_mode")) != 1:
        raise SystemExit("source candidate is not HYDRO mode")
    if int(dataset.getncattr("valid_time_epoch")) != 1786885200:
        raise SystemExit("source candidate valid time mismatch")
    pairs = {
        "temperature": "temperature", "vapor": "vapor",
        "cloud_water": "cloud_water", "cloud_ice": "cloud_ice",
        "rain": "rain", "snow": "snow", "graupel": "graupel",
        "geopotential": "geopotential", "surface_pressure": "surface_pressure",
        "surface_temperature": "surface_temperature", "surface_vapor": "surface_vapor",
        "surface_height": "surface_height",
    }
    for candidate, background in pairs.items():
        left = dataset[f"candidate_{candidate}_valid"][:]
        right = dataset[f"background_{background}_valid"][:]
        if not np.array_equal(left, right):
            raise SystemExit(f"candidate/background validity mismatch: {candidate}")
    for name in ("u", "v", "omega"):
        if not np.array_equal(dataset[f"candidate_{name}"][:], dataset[f"background_{name}"][:]):
            raise SystemExit(f"HYDRO product unexpectedly changed {name}")
PY
lsx=${args[9]}
laps_root=${lsx%/lapsprd/lsx/*}
witness=$run/build/mapped_witness.raw
wps=$run/build/hydro.wps
env CLOUD_BAL_PR82_LAPS_ROOT="$laps_root" CLOUD_BAL_PR82_INVENTORY="$inventory" \
  "$run/build/pr94-hydro-wps" "${args[@]}" "$candidate" "$wps" "$witness" \
  > "$run/build/run.log" 2>&1
python3 "$repo/tests/pr94_hydro_wps_readback.py" "$wps" "$baseline" "$inventory" \
  "$witness" "$candidate" "$run/build/readback.json"
sha256sum "${source_files[@]}" > "$run/source_post.sha256"
cmp "$run/source_pre.sha256" "$run/source_post.sha256"
sha256sum "$candidate" "$inputs" "$inventory" "$baseline" "$nf_config" "$nf_lib" "$nc_lib" \
  > "$run/input_hashes.sha256"
printf 'hydro_wps=%s\n' "$wps"
