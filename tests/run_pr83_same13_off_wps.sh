#!/usr/bin/env bash
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
workspace=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
retained=/var/tmp/pr81_joint_thermo.HbL5ry
inputs=$retained/inputs.json.archive
source_snapshot=$retained/source_snapshot
inventory=/var/tmp/pr82_same13_lapsprep_capture.WA4vyK/lapsprep_inventory.bin
baseline=$workspace/Cloud-BAL/scratch/cp02_baseline_native_ruoww1a5/baseline_O0.wps
if (($# != 1)); then
  echo "usage: $0 NEW_SCRATCH_DIRECTORY" >&2
  exit 2
fi
run=$1
[[ ! -e $run && ! -L $run ]] || { echo "fresh scratch path required: $run" >&2; exit 2; }
[[ -s $inputs && -s $inventory && -s $baseline ]]
[[ -s $retained/source_pre.sha256 && -s $retained/source_post.sha256 ]]
cmp "$retained/source_pre.sha256" "$retained/source_post.sha256"
sha256sum --check "$retained/source_pre.sha256"
. "$repo/tests/intel_toolchain.sh"

nf_config=$workspace/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config
nf_lib=$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a
nc_lib=$workspace/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a
[[ $(sha256sum "$nf_config" | cut -d' ' -f1) == e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5 ]]
[[ $(sha256sum "$nf_lib" | cut -d' ' -f1) == f610d7ebedf48d17023e9b8377d74d93542bde40d091ec7a5518bb30d17c8a39 ]]
[[ $(sha256sum "$nc_lib" | cut -d' ' -f1) == f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288 ]]
read -r -a nf_flags <<<"$("$nf_config" --fflags)"
read -r -a nf_libs <<<"$("$nf_config" --flibs)"

mkdir -p "$(dirname "$run")"
mkdir "$run"
mkdir -p "$run/source/src/common" "$run/source/src/lapsprep" "$run/build"
for name in cloud_bal_state cloud_bal_grid_geometry cloud_bal_column_physics \
  cloud_bal_balance_operator cloud_bal_pipeline cloud_bal_real_netcdf; do
  cp "$source_snapshot/src/common/$name.f90" "$run/source/src/common/"
done
for name in module_constants module_date_pack module_laps_static; do
  cp "$workspace/klaps-v5.0_/src/lapsprep/$name.f90" "$run/source/src/lapsprep/"
done
cp "$repo/src/lapsprep/module_setup.f90" "$repo/src/lapsprep/module_lapsprep_wps.f90" \
  "$repo/src/common/cloud_bal_wps_adapter.f90" \
  "$repo/tests/pr83_off_candidate_wps_hook.f90" \
  "$repo/tests/pr83_same13_off_driver.f90" "$run/source/src/lapsprep/"
source_files=(
  "$run/source/src/common/cloud_bal_state.f90"
  "$run/source/src/common/cloud_bal_grid_geometry.f90"
  "$run/source/src/common/cloud_bal_column_physics.f90"
  "$run/source/src/common/cloud_bal_balance_operator.f90"
  "$run/source/src/common/cloud_bal_pipeline.f90"
  "$run/source/src/common/cloud_bal_real_netcdf.f90"
  "$run/source/src/lapsprep/module_constants.f90"
  "$run/source/src/lapsprep/module_date_pack.f90"
  "$run/source/src/lapsprep/module_laps_static.f90"
  "$run/source/src/lapsprep/module_setup.f90"
  "$run/source/src/lapsprep/module_lapsprep_wps.f90"
  "$run/source/src/lapsprep/cloud_bal_wps_adapter.f90"
  "$run/source/src/lapsprep/pr83_off_candidate_wps_hook.f90"
  "$run/source/src/lapsprep/pr83_same13_off_driver.f90"
)
sha256sum "${source_files[@]}" > "$run/source_pre.sha256"

build=$run/build
read -r -a nf_flags <<<"$("$nf_config" --fflags)"
read -r -a nf_libs <<<"$("$nf_config" --flibs)"
for source in "${source_files[@]}"; do
  object=$(basename "${source%.f90}.o")
  flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  if [[ $(basename "$source") == module_lapsprep_wps.f90 ]]; then flags+=( -convert big_endian ); fi
  (cd "$build" && "$CLOUD_BAL_FC" -c "${flags[@]}" -module "$build" -I "$build" \
    "${nf_flags[@]}" "$source" -o "$object") > "$build/$object.log" 2>&1
done
objects=()
for source in "${source_files[@]}"; do objects+=("$(basename "${source%.f90}.o")"); done
(cd "$build" && "$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" -module "$build" -I "$build" \
  "${objects[@]}" "${nf_libs[@]}" -o "$build/pr83-same13-off") > "$build/link.log" 2>&1
sha256sum "$build/pr83-same13-off" > "$run/executable.sha256"

mapfile -t args < <(python3 - "$inputs" <<'PY'
import json, sys
print("\n".join(json.load(open(sys.argv[1]))["driver_arguments"]))
PY
)
[[ ${#args[@]} == 13 ]]
driver_inputs=("${args[@]:0:12}")
[[ ${#driver_inputs[@]} == 12 ]]
python3 - "$inputs" <<'PY'
import hashlib, json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text())
arguments, expected = data["driver_arguments"], data["input_hashes"]
if len(arguments) != 13 or len(expected) != 12:
    raise SystemExit("frozen same13 producer manifest has unexpected argument/input inventory")
for path in arguments[:12]:
    file = Path(path)
    if not file.is_file():
        raise SystemExit(f"missing frozen same13 driver input: {file}")
    actual = hashlib.sha256(file.read_bytes()).hexdigest()
    if expected.get(path) != actual:
        raise SystemExit(f"frozen same13 driver input hash mismatch: {file}")
PY
sha256sum "$inputs" "$inventory" "$baseline" "$nf_config" "$nf_lib" "$nc_lib" \
  "$retained/source_pre.sha256" "$repo/tests/intel_toolchain.sh" \
  "$repo/tests/run_pr83_same13_off_wps.sh" "$repo/tests/pr83_same13_off_driver.f90" \
  "$repo/tests/pr83_same13_off_wps_readback.py" "$repo/tests/pr83_off_candidate_wps_hook.f90" \
  "$repo/tests/pr82_same13_native_readback.py" "$repo/tools/compare_baseline.py" \
  "${driver_inputs[@]}" > "$run/inputs.pre.sha256"
lsx=${args[9]}
laps_root=${lsx%/lapsprd/lsx/*}
[[ -f $lsx ]]
wps=$run/build/same13_off.wps
witness=$run/build/canonical_mapped_witness.raw
inventory_sha=$(sha256sum "$inventory" | cut -d' ' -f1)
[[ $inventory_sha == ee5c4e56384d4830d4979875f6db1416e28987d3673358d0373e73f60a550603 ]]
env CLOUD_BAL_PR82_LAPS_ROOT="$laps_root" CLOUD_BAL_PR82_INVENTORY="$inventory" \
  "$build/pr83-same13-off" "${args[@]}" "$wps" "$witness" > "$run/build/run.log" 2>&1
[[ -s $wps ]]
python3 "$repo/tests/pr83_same13_off_wps_readback.py" "$wps" "$baseline" "$inventory" "$witness" \
  "$run/build/readback.json"
sha256sum "${source_files[@]}" > "$run/source_post.sha256"
sha256sum "$inputs" "$inventory" "$baseline" "$nf_config" "$nf_lib" "$nc_lib" \
  "$retained/source_pre.sha256" "$repo/tests/intel_toolchain.sh" \
  "$repo/tests/run_pr83_same13_off_wps.sh" "$repo/tests/pr83_same13_off_driver.f90" \
  "$repo/tests/pr83_same13_off_wps_readback.py" "$repo/tests/pr83_off_candidate_wps_hook.f90" \
  "$repo/tests/pr82_same13_native_readback.py" "$repo/tools/compare_baseline.py" \
  "${driver_inputs[@]}" > "$run/inputs.post.sha256"
cmp "$run/source_pre.sha256" "$run/source_post.sha256"
cmp "$run/inputs.pre.sha256" "$run/inputs.post.sha256"
printf 'off_wps=%s\n' "$wps"
