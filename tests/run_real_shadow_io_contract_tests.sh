#!/usr/bin/env bash
# Focused Intel/NetCDF tests for the real SHADOW adapter and writer authority.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_lexical=$(realpath -ms "${CLOUD_BAL_WORKSPACE_ROOT:-$repo_root/..}")
workspace_root=$(realpath -e "$workspace_lexical")
[[ $workspace_root == "$workspace_lexical" ]] || {
  printf 'workspace root cannot contain a symlink: %s\n' "$workspace_lexical" >&2
  exit 2
}
mkdir -p "$repo_root/scratch"
test_tmp=$(mktemp -d "$repo_root/scratch/real_shadow_io_tests.XXXXXX")
cleanup_test_tmp() {
  if [[ "${CLOUD_BAL_KEEP_TEST_ARTIFACTS:-0}" == 1 ]]; then
    printf 'preserving real SHADOW test artifacts: %s\n' "$test_tmp"
  else
    rm -rf -- "$test_tmp"
  fi
}
trap cleanup_test_tmp EXIT

. "$repo_root/tests/intel_toolchain.sh"
cd "$test_tmp"
python3 "$repo_root/tests/test_pressure_continuity_oracle.py"

nf_config=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config
netcdff_archive=$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a
netcdf_archive=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a
expected_nf_config_sha=e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5
expected_netcdff_sha=f610d7ebedf48d17023e9b8377d74d93542bde40d091ec7a5518bb30d17c8a39
expected_netcdf_sha=f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288

verify_hash() {
  local path=$1 expected=$2 actual
  [[ -f $path && ! -L $path ]] || {
    printf 'required pinned file is unavailable: %s\n' "$path" >&2
    exit 2
  }
  actual=$(sha256sum "$path" | cut -d' ' -f1)
  [[ $actual == "$expected" ]] || {
    printf 'pinned file hash mismatch: %s\n' "$path" >&2
    exit 2
  }
}

verify_hash "$nf_config" "$expected_nf_config_sha"
verify_hash "$netcdff_archive" "$expected_netcdff_sha"
verify_hash "$netcdf_archive" "$expected_netcdf_sha"

read -r -a nf_fflags <<<"$($nf_config --fflags)"
read -r -a nf_flibs <<<"$($nf_config --flibs)"

sources=(
  cloud_bal_state
  cloud_bal_grid_geometry
  cloud_bal_column_physics
  cloud_bal_balance_operator
  cloud_bal_pipeline
  cloud_bal_real_netcdf
  cloud_bal_pressure_analysis
)
objects=()
for source in "${sources[@]}"; do
  object=$test_tmp/$source.o
  "$CLOUD_BAL_FC" -c "${CLOUD_BAL_FREE_FLAGS[@]}" \
    -module "$test_tmp" -I "$test_tmp" "${nf_fflags[@]}" \
    "$repo_root/src/common/$source.f90" -o "$object"
  objects+=("$object")
done
wps_sources=(
  "$repo_root/tests/wps_module_stubs.f90"
  "$repo_root/src/common/cloud_bal_wps_adapter.f90"
  "$repo_root/src/lapsprep/module_lapsprep_wps.f90"
)
for source_path in "${wps_sources[@]}"; do
  source_name=$(basename "$source_path" .f90)
  object="$test_tmp/$source_name.o"
  "$CLOUD_BAL_FC" -c "${CLOUD_BAL_FREE_FLAGS[@]}" \
    -module "$test_tmp" -I "$test_tmp" "${nf_fflags[@]}" \
    "$source_path" -o "$object"
  objects+=("$object")
done

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" "${nf_fflags[@]}" \
  "$repo_root/tests/test_real_shadow_io_contract.f90" "${objects[@]}" \
  "${nf_flibs[@]}" -o "$test_tmp/test_real_shadow_io_contract"

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" "${nf_fflags[@]}" \
  "$repo_root/tests/test_real_shadow_reader.f90" "${objects[@]}" \
  "${nf_flibs[@]}" -o "$test_tmp/test_real_shadow_reader"

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" "${nf_fflags[@]}" \
  "$repo_root/tests/test_analysis_shadow_reader.f90" "${objects[@]}" \
  "${nf_flibs[@]}" -o "$test_tmp/test_analysis_shadow_reader"

(
  cd "$test_tmp"
  ./test_real_shadow_io_contract
  python3 "$repo_root/tests/test_pressure_transition_payload.py" \
    transition-replay-same-domain.nc transition-replay-one-center.nc
  python3 "$repo_root/tests/check_full_transition_shadow.py" \
    transition-full-same-domain.nc transition-full-one-center.nc
  python3 "$repo_root/tools/validate_shadow_diagnostics.py" sigma-noop-shadow.nc
  python3 "$repo_root/tests/check_pressure_candidate_shadow.py" pressure-candidate-shadow.nc
  python3 "$repo_root/tests/check_pressure_candidate_shadow.py" pressure-thermo-candidate-shadow.nc
  python3 "$repo_root/tests/check_pressure_candidate_shadow.py" pressure-outer-candidate-shadow.nc
  python3 "$repo_root/tests/check_pressure_geopotential_shadow.py" geopotential-candidate-shadow.nc
  python3 "$repo_root/tests/check_pressure_geopotential_shadow.py" geopotential-outer-candidate-shadow.nc
  python3 "$repo_root/tests/check_pressure_geopotential_shadow.py" surface-geopotential-shadow.nc
  python3 "$repo_root/tests/check_pressure_geometry_shadow.py" variable-pressure-shadow.nc
  python3 "$repo_root/tests/check_transition_replay_probe.py" transition-state-replay-probe.nc
  python3 "$repo_root/tests/check_transition_thermo_scope.py" transition-state-replay-probe.nc
  python3 "$repo_root/tests/check_transition_geopotential_scope.py" transition-state-replay-probe.nc
  python3 "$repo_root/tests/test_transition_geostrophic_scope.py" transition-state-replay-probe.nc
  python3 "$repo_root/tests/check_pressure_geostrophic_shadow.py" geopotential-candidate-shadow.nc
  python3 "$repo_root/tests/check_pressure_geostrophic_shadow.py" geopotential-outer-candidate-shadow.nc
  python3 "$repo_root/tests/check_thermo_shadow.py" thermo-shadow.nc
  python3 "$repo_root/tests/check_thermo_shadow.py" outer-thermo-shadow.nc
  python3 "$repo_root/tests/test_radar_ledger_validator.py" outer-thermo-shadow.nc
  python3 "$repo_root/tools/validate_shadow_diagnostics.py" pipeline_pressure_candidate.nc
  python3 "$repo_root/tests/check_pipeline_wps_mapping.py" .
  [[ -s verified-shadow.nc ]]
  [[ ! -e unverified-shadow.nc ]]
  [[ ! -e nonfinite-residual.nc ]]
)

# Recompile the writer path at O2; do not reuse O0 objects as optimized evidence.
o2_dir="$test_tmp/o2"
mkdir -p "$o2_dir"
o2_objects=()
for source in "${sources[@]}"; do
  object="$o2_dir/$source.o"
  "$CLOUD_BAL_FC" -c "${CLOUD_BAL_REPRO_FLAGS[@]}" \
    -module "$o2_dir" -I "$o2_dir" "${nf_fflags[@]}" \
    "$repo_root/src/common/$source.f90" -o "$object"
  o2_objects+=("$object")
done
for source_path in "${wps_sources[@]}"; do
  source_name=$(basename "$source_path" .f90)
  object="$o2_dir/$source_name.o"
  "$CLOUD_BAL_FC" -c "${CLOUD_BAL_REPRO_FLAGS[@]}" \
    -module "$o2_dir" -I "$o2_dir" "${nf_fflags[@]}" \
    "$source_path" -o "$object"
  o2_objects+=("$object")
done
"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" \
  -module "$o2_dir" -I "$o2_dir" "${nf_fflags[@]}" \
  "$repo_root/tests/test_real_shadow_io_contract.f90" "${o2_objects[@]}" \
  "${nf_flibs[@]}" -o "$o2_dir/test_real_shadow_io_contract"
"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" \
  -module "$o2_dir" -I "$o2_dir" "${nf_fflags[@]}" \
  "$repo_root/tests/test_analysis_shadow_reader.f90" "${o2_objects[@]}" \
  "${nf_flibs[@]}" -o "$o2_dir/test_analysis_shadow_reader"
(
  cd "$o2_dir"
  ./test_real_shadow_io_contract
  python3 "$repo_root/tests/test_pressure_transition_payload.py" \
    transition-replay-same-domain.nc transition-replay-one-center.nc
  python3 "$repo_root/tests/check_full_transition_shadow.py" \
    transition-full-same-domain.nc transition-full-one-center.nc
  python3 "$repo_root/tools/validate_shadow_diagnostics.py" sigma-noop-shadow.nc
  python3 "$repo_root/tests/check_pressure_candidate_shadow.py" pressure-candidate-shadow.nc
  python3 "$repo_root/tests/check_pressure_candidate_shadow.py" pressure-thermo-candidate-shadow.nc
  python3 "$repo_root/tests/check_pressure_candidate_shadow.py" pressure-outer-candidate-shadow.nc
  python3 "$repo_root/tests/check_pressure_geopotential_shadow.py" geopotential-candidate-shadow.nc
  python3 "$repo_root/tests/check_pressure_geopotential_shadow.py" geopotential-outer-candidate-shadow.nc
  python3 "$repo_root/tests/check_pressure_geopotential_shadow.py" surface-geopotential-shadow.nc
  python3 "$repo_root/tests/check_pressure_geometry_shadow.py" variable-pressure-shadow.nc
  python3 "$repo_root/tests/check_transition_replay_probe.py" transition-state-replay-probe.nc
  python3 "$repo_root/tests/check_transition_thermo_scope.py" transition-state-replay-probe.nc
  python3 "$repo_root/tests/check_transition_geopotential_scope.py" transition-state-replay-probe.nc
  python3 "$repo_root/tests/test_transition_geostrophic_scope.py" transition-state-replay-probe.nc
  python3 "$repo_root/tests/check_pressure_geostrophic_shadow.py" geopotential-candidate-shadow.nc
  python3 "$repo_root/tests/check_pressure_geostrophic_shadow.py" geopotential-outer-candidate-shadow.nc
  python3 "$repo_root/tests/check_thermo_shadow.py" thermo-shadow.nc
  python3 "$repo_root/tests/check_thermo_shadow.py" outer-thermo-shadow.nc
  python3 "$repo_root/tools/validate_shadow_diagnostics.py" pipeline_pressure_candidate.nc
  python3 "$repo_root/tests/check_pipeline_wps_mapping.py" .
)

manifest=$repo_root/tests/qbal_real_cases_20260816.tsv
IFS=$'\t' read -r case_id valid_time background_time laps_stamp \
  fua fua_hash fsf fsf_hash lw3 lw3_hash vrz vrz_hash vrt vrt_hash \
  < <(sed -n '2p' "$manifest")

verify_hash "$workspace_root/$fua" "$fua_hash"
verify_hash "$workspace_root/$fsf" "$fsf_hash"
verify_hash "$workspace_root/$lw3" "$lw3_hash"
verify_hash "$workspace_root/$vrz" "$vrz_hash"
verify_hash "$workspace_root/$vrt" "$vrt_hash"
static_file=$workspace_root/ANAL/NE57/DABA/static.nest7grid
verify_hash "$static_file" 384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b
epoch=$(date -u -d "$valid_time" +%s)

"$test_tmp/test_real_shadow_reader" \
  "$workspace_root/$fua" "$workspace_root/$fsf" "$workspace_root/$lw3" \
  "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file" "$epoch"

# Build a temporary direct-product tree from the pinned real case.  The
# copied analysis products are retimed to the valid time, while the legacy
# FUA/FSF pair remains on its earlier forecast reference.  This exercises the
# separate product policy without changing any preserved input.
analysis_root=$test_tmp/direct-inputs
python3 - "$analysis_root" "$workspace_root/$fua" "$workspace_root/$fsf" \
  "$workspace_root/$lw3" "$workspace_root/$vrz" "$workspace_root/$vrt" \
  "$static_file" "$epoch" <<'PY'
import shutil
import sys
from pathlib import Path

import netCDF4
import numpy as np

root = Path(sys.argv[1])
fua, fsf, lw3, vrz, vrt, static, epoch = sys.argv[2:]
epoch = int(epoch)
for directory in (
    root / "lapsprd/fua/wrf", root / "lapsprd/fsf/wrf", root / "lapsprd/lw3",
    root / "lapsprd/vrz", root / "lapsprd/vrt", root / "lapsprd/lt1",
    root / "lapsprd/lq3", root / "lapsprd/lwc", root / "lapsprd/lsx",
    root / "static",
):
    directory.mkdir(parents=True, exist_ok=True)

stamp = "262281200"
paths = {
    root / "lapsprd/fua/wrf/2622806000600.fua": fua,
    root / "lapsprd/fsf/wrf/2622806000600.fsf": fsf,
    root / f"lapsprd/lw3/{stamp}.lw3": lw3,
    root / f"lapsprd/vrz/{stamp}.vrz": vrz,
    root / f"lapsprd/vrt/{stamp}.vrt": vrt,
    root / "static/static.nest7grid": static,
}
for destination, source in paths.items():
    shutil.copy2(source, destination)

for extension in ("lt1", "lq3", "lwc"):
    destination = root / f"lapsprd/{extension}/{stamp}.{extension}"
    shutil.copy2(fua, destination)
    with netCDF4.Dataset(destination, "r+") as dataset:
        dataset.variables["reftime"][:] = epoch
        if extension == "lt1":
            dataset.variables["t3"].units = "degrees kelvin"
        if extension == "lwc":
            for name in ("lwc", "ice", "rai", "sno", "pic"):
                dataset.variables[name].units = "kg/meter**3"

with netCDF4.Dataset(fsf) as source, netCDF4.Dataset(
    root / f"lapsprd/lsx/{stamp}.lsx", "w", format="NETCDF3_64BIT_OFFSET"
) as dataset:
    # Preserve raw PSFC above the legacy 100000 Pa valid_range attribute.
    # The Fortran reader validates physical values independently of that tag.
    source.set_auto_maskandscale(False)
    dataset.createDimension("record", 1)
    dataset.createDimension("z", 1)
    dataset.createDimension("x", 235)
    dataset.createDimension("y", 283)
    dataset.createDimension("nav", 1)
    for name, value, units in (
        ("reftime", epoch, "seconds since (1970-1-1 00:00:00.0)"),
        ("valtime", epoch, "seconds since (1970-1-1 00:00:00.0)"),
    ):
        variable = dataset.createVariable(name, "f8", ("record",))
        variable.units = units
        variable[:] = value
    for name, source_name, units in (("t", "tsf", "degrees kelvin"),
                                     ("ps", "psf", "pascals")):
        variable = dataset.createVariable(name, "f4", ("record", "z", "y", "x"))
        variable.units = units
        variable[:] = source.variables[source_name][:]
    mr = dataset.createVariable("mr", "f4", ("record", "z", "y", "x"))
    mr.units = "grams/kilogram"
    mr[:] = np.float32(8.0)
    for name, units in (("Dx", "kilometers"), ("Dy", "kilometers")):
        variable = dataset.createVariable(name, "f4", ("nav",))
        variable.units = units
        variable[:] = np.float32(5.0)
PY

"$test_tmp/test_analysis_shadow_reader" "$analysis_root"
"$o2_dir/test_analysis_shadow_reader" "$analysis_root"

# Every analysis product follows the same exact reference-time policy.  Mutate
# one product at a time so the reader must reject each mismatched reference;
# FUA/FSF are intentionally absent from the first direct call.
for product in lw3 vrz vrt lt1 lq3 lwc lsx; do
  product_path="$analysis_root/lapsprd/$product/262281200.$product"
  product_backup="$test_tmp/$product-time-backup"
  cp "$product_path" "$product_backup"
  python3 - "$product_path" "$epoch" <<'PY'
import sys
import netCDF4

path, epoch = sys.argv[1], int(sys.argv[2])
with netCDF4.Dataset(path, "r+") as dataset:
    dataset.variables["reftime"][:] = epoch - 3600
PY
  "$test_tmp/test_analysis_shadow_reader" "$analysis_root" REJECT_TIME
  "$o2_dir/test_analysis_shadow_reader" "$analysis_root" REJECT_TIME
  cp "$product_backup" "$product_path"
done

# Nonfinite payloads in active direct products must be converted to invalid
# coverage and rejected with a controlled status.  Exercise each IEEE class
# through both pinned reader binaries so optimized evaluation cannot hide a
# NaN/Inf comparison failure.
for payload_case in \
  'lwc:NaN' 'lwc:+inf' 'lwc:-inf' \
  'lsx:NaN' 'lsx:+inf' 'lsx:-inf'; do
  payload_product=${payload_case%%:*}
  payload_value=${payload_case##*:}
  payload_path="$analysis_root/lapsprd/$payload_product/262281200.$payload_product"
  payload_backup="$test_tmp/$payload_product-payload-backup"
  cp "$payload_path" "$payload_backup"
  if [[ $payload_product == lwc ]]; then
    payload_kind=LWC
    python3 - "$payload_path" "$payload_value" \
      "$analysis_root/lapsprd/lw3/262281200.lw3" \
      "$analysis_root/lapsprd/lsx/262281200.lsx" <<'PY'
import sys

import netCDF4
import numpy as np

payload_path, payload_value, lw3_path, lsx_path = sys.argv[1:]
values = {"NaN": np.nan, "+inf": np.inf, "-inf": -np.inf}
with netCDF4.Dataset(lw3_path) as lw3, netCDF4.Dataset(lsx_path) as lsx:
    lw3.set_auto_maskandscale(False)
    lsx.set_auto_maskandscale(False)
    levels = np.asarray(lw3.variables["level"][:], dtype=np.float64) * 100.0
    surface_pressure = np.asarray(lsx.variables["ps"][0, 0], dtype=np.float64)
active = levels[:, None, None] < surface_pressure[None, :, :]
active_index = np.argwhere(active)
if active_index.size == 0:
    raise SystemExit("no active direct LWC cell available for payload test")
raw_level, j, i = (int(value) for value in active_index[0])
with netCDF4.Dataset(payload_path, "r+") as dataset:
    dataset.set_auto_maskandscale(False)
    dataset.variables["lwc"][0, raw_level, j, i] = np.float32(values[payload_value])
PY
  else
    payload_kind=LSX_PS
    python3 - "$payload_path" "$payload_value" <<'PY'
import sys

import netCDF4
import numpy as np

payload_path, payload_value = sys.argv[1:]
values = {"NaN": np.nan, "+inf": np.inf, "-inf": -np.inf}
with netCDF4.Dataset(payload_path, "r+") as dataset:
    dataset.set_auto_maskandscale(False)
    dataset.variables["ps"][0, 0, 0, 0] = np.float32(values[payload_value])
PY
  fi
  printf 'running direct analysis payload case product=%s value=%s mode=REJECT_PAYLOAD readers=O0/O2\n' \
    "$payload_product" "$payload_value"
  "$test_tmp/test_analysis_shadow_reader" "$analysis_root" REJECT_PAYLOAD "$payload_kind"
  "$o2_dir/test_analysis_shadow_reader" "$analysis_root" REJECT_PAYLOAD "$payload_kind"
  cp "$payload_backup" "$payload_path"
done

# LT1 HT uses the pressure level and LSX PS to define activity.  Select cells
# from raw, unmasked values so an extreme inactive payload is ignored while an
# extreme active payload rejects the complete direct case.
lt1_path="$analysis_root/lapsprd/lt1/262281200.lt1"
lsx_path="$analysis_root/lapsprd/lsx/262281200.lsx"
for ht_sign in positive negative; do
  for ht_case in inactive active; do
    ht_backup="$test_tmp/lt1-ht-${ht_sign}-${ht_case}-backup.nc"
    cp "$lt1_path" "$ht_backup"
    python3 - "$lt1_path" "$analysis_root/lapsprd/lw3/262281200.lw3" "$lsx_path" "$ht_sign" "$ht_case" <<'PY_HT'
import sys

import netCDF4
import numpy as np

lt1_path, lw3_path, lsx_path, sign, case = sys.argv[1:]
with netCDF4.Dataset(lw3_path) as lw3, netCDF4.Dataset(lsx_path) as lsx:
    lw3.set_auto_maskandscale(False)
    lsx.set_auto_maskandscale(False)
    levels = np.asarray(lw3.variables["level"][:], dtype=np.float64) * 100.0
    surface_pressure = np.asarray(lsx.variables["ps"][0, 0], dtype=np.float64)
active = levels[:, None, None] < surface_pressure[None, :, :]
candidates = np.argwhere(active if case == "active" else ~active)
if candidates.size == 0:
    raise SystemExit(f"no {case} LT1 HT cell selected from raw level and LSX PS")
raw_level, j, i = (int(value) for value in candidates[0])
with netCDF4.Dataset(lt1_path, "r+") as lt1:
    lt1.set_auto_maskandscale(False)
    extreme = np.finfo(np.float32).max * (1.0 if sign == "positive" else -1.0)
    lt1.variables["ht"][0, raw_level, j, i] = np.float32(extreme)
print(f"LT1 HT {sign} {case} cell raw_level={raw_level} y={j} x={i}")
PY_HT
    printf 'running LT1 HT %s %s-domain float32 maximum regression readers=O0/O2\n' \
      "$ht_sign" "$ht_case"
    if [[ $ht_case == active ]]; then
      "$test_tmp/test_analysis_shadow_reader" "$analysis_root" REJECT_PAYLOAD LT1_HT
      "$o2_dir/test_analysis_shadow_reader" "$analysis_root" REJECT_PAYLOAD LT1_HT
    else
      "$test_tmp/test_analysis_shadow_reader" "$analysis_root" INACTIVE_HT
      "$o2_dir/test_analysis_shadow_reader" "$analysis_root" INACTIVE_HT
    fi
    cp "$ht_backup" "$lt1_path"
  done
done

# The shared reader allows absent surface vapor; consumers enforce any anchor
# requirement. Absence must never manufacture valid surface-vapor coverage.
cp "$lsx_path" "$test_tmp/lsx-mr-backup"
python3 - "$lsx_path" <<'PY_MR'
import sys
import netCDF4

with netCDF4.Dataset(sys.argv[1], "r+") as dataset:
    dataset.renameVariable("mr", "removed_mr")
PY_MR
"$test_tmp/test_analysis_shadow_reader" "$analysis_root" OPTIONAL_MR
"$o2_dir/test_analysis_shadow_reader" "$analysis_root" OPTIONAL_MR
cp "$test_tmp/lsx-mr-backup" "$lsx_path"

canonical_spacing_fsf=$test_tmp/canonical-spacing.fsf
cp "$workspace_root/$fsf" "$canonical_spacing_fsf"
python3 - "$canonical_spacing_fsf" <<'PY'
import sys
import netCDF4

with netCDF4.Dataset(sys.argv[1], "r+") as dataset:
    dataset.variables["Dx"][:] = 5.0
    dataset.variables["Dy"][:] = 5.0
PY
"$test_tmp/test_real_shadow_reader" \
  "$workspace_root/$fua" "$canonical_spacing_fsf" "$workspace_root/$lw3" \
  "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file" "$epoch"

retained_omega_lw3=$test_tmp/retained-omega-outside-domain.lw3
cp "$workspace_root/$lw3" "$retained_omega_lw3"
python3 - "$retained_omega_lw3" "$workspace_root/$fsf" <<'PY'
import sys

import netCDF4
import numpy as np

lw3_path, fsf_path = sys.argv[1:]
with netCDF4.Dataset(fsf_path) as surface_file:
    surface_pressure = np.asarray(surface_file.variables["psf"][0, 0], dtype=np.float64)
with netCDF4.Dataset(lw3_path, "r+") as wind_file:
    levels = np.asarray(wind_file.variables["level"][:], dtype=np.float64) * 100.0
    om = wind_file.variables["om"]
    fill = np.float32(getattr(om, "_FillValue", 1.0e37))
    outside = np.all(levels[-3:, None, None] > surface_pressure, axis=0)
    if not np.any(outside):
        raise SystemExit("no column leaves three outside levels")
    j, i = np.argwhere(outside)[0]
    # Raw levels are top-to-bottom in the file; these map to canonical k=1..3.
    om[0, -1, int(j), int(i)] = np.float32(17.25)
    om[0, -2, int(j), int(i)] = fill
    om[0, -3, int(j), int(i)] = np.float32(125.0)
PY
"$test_tmp/test_real_shadow_reader" \
  "$workspace_root/$fua" "$workspace_root/$fsf" "$retained_omega_lw3" \
  "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file" "$epoch" RETAINED

malformed_lw3=$test_tmp/permuted-om.lw3
python3 - "$malformed_lw3" "$epoch" <<'PY'
import sys

import netCDF4
import numpy as np

path, epoch = sys.argv[1], int(sys.argv[2])
with netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET") as dataset:
    for name, size in (("record", 1), ("z", 22), ("x", 235), ("y", 283), ("nav", 1)):
        dataset.createDimension(name, size)
    for name, value, units in (
        ("reftime", epoch, "seconds since (1970-1-1 00:00:00.0)"),
        ("valtime", epoch, "seconds since (1970-1-1 00:00:00.0)"),
        ("Dx", 5000.0, "kilometers"),
        ("Dy", 5000.0, "kilometers"),
    ):
        dimension = "record" if name in ("valtime", "reftime") else "nav"
        dtype = "f8" if name in ("valtime", "reftime") else "f4"
        variable = dataset.createVariable(name, dtype, (dimension,))
        variable.units = units
        variable[:] = value
    level = dataset.createVariable("level", "f4", ("z",))
    level.units = "hectopascals"
    level[:] = np.arange(50.0, 1150.0, 50.0, dtype=np.float32)
    bad = dataset.createVariable("om", "f4", ("record", "z", "x", "y"))
    bad.units = "pascals / second"
    bad[:] = 0.0
    for name in ("u3", "v3"):
        variable = dataset.createVariable(name, "f4", ("record", "z", "y", "x"))
        variable.units = "meters / second"
        variable[:] = 0.0
PY

"$test_tmp/test_real_shadow_reader" \
  "$workspace_root/$fua" "$workspace_root/$fsf" "$malformed_lw3" \
  "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file" "$epoch" REJECT

missing_reftime_lw3=$test_tmp/missing-reftime.lw3
python3 - "$missing_reftime_lw3" "$workspace_root/$lw3" <<'PY'
import shutil
import sys

import netCDF4

destination, source = sys.argv[1:]
shutil.copy2(source, destination)
with netCDF4.Dataset(destination, "r+") as dataset:
    dataset.renameVariable("reftime", "removed_reftime")
PY
"$test_tmp/test_real_shadow_reader" \
  "$workspace_root/$fua" "$workspace_root/$fsf" "$missing_reftime_lw3" \
  "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file" "$epoch" REJECT

malformed_reftime_lw3=$test_tmp/malformed-reftime.lw3
cp "$workspace_root/$lw3" "$malformed_reftime_lw3"
python3 - "$malformed_reftime_lw3" <<'PY'
import sys
import netCDF4

with netCDF4.Dataset(sys.argv[1], "r+") as dataset:
    dataset.variables["reftime"].units = "hours since 1970-01-01 00:00:00"
PY
"$test_tmp/test_real_shadow_reader" \
  "$workspace_root/$fua" "$workspace_root/$fsf" "$malformed_reftime_lw3" \
  "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file" "$epoch" REJECT

nan_reftime_lw3=$test_tmp/nan-reftime.lw3
cp "$workspace_root/$lw3" "$nan_reftime_lw3"
python3 - "$nan_reftime_lw3" <<'PY'
import sys
import netCDF4
import numpy as np

with netCDF4.Dataset(sys.argv[1], "r+") as dataset:
    dataset.variables["reftime"][:] = np.nan
PY
"$test_tmp/test_real_shadow_reader" \
  "$workspace_root/$fua" "$workspace_root/$fsf" "$nan_reftime_lw3" \
  "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file" "$epoch" REJECT

future_fsf=$test_tmp/future-reference.fsf
cp "$workspace_root/$fsf" "$future_fsf"
python3 - "$future_fsf" "$epoch" <<'PY'
import sys
import netCDF4

with netCDF4.Dataset(sys.argv[1], "r+") as dataset:
    dataset.variables["reftime"][:] = int(sys.argv[2]) + 3600
PY
"$test_tmp/test_real_shadow_reader" \
  "$workspace_root/$fua" "$future_fsf" "$workspace_root/$lw3" \
  "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file" "$epoch" REJECT

for mismatch_source in fua fsf; do
  mismatched_fua="$workspace_root/$fua"
  mismatched_fsf="$workspace_root/$fsf"
  if [[ $mismatch_source == fua ]]; then
    mismatched_fua=$test_tmp/mismatched.fua
    cp "$workspace_root/$fua" "$mismatched_fua"
    mismatch_path=$mismatched_fua
  else
    mismatched_fsf=$test_tmp/mismatched.fsf
    cp "$workspace_root/$fsf" "$mismatched_fsf"
    mismatch_path=$mismatched_fsf
  fi
  python3 - "$mismatch_path" "$epoch" <<'PY'
import sys
import netCDF4

with netCDF4.Dataset(sys.argv[1], "r+") as dataset:
    dataset.variables["reftime"][:] = int(sys.argv[2]) - 3600
PY
  "$test_tmp/test_real_shadow_reader" \
    "$mismatched_fua" "$mismatched_fsf" "$workspace_root/$lw3" \
    "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file" "$epoch" REJECT
done

# OM is a required field inside the PSFC/pressure-defined physical domain.  A
# missing lowest active value or an isolated interior hole must reject the
# complete case; neither is allowed to shrink above_ground implicitly.
for hole_kind in bottom interior; do
  om_hole_lw3=$test_tmp/${hole_kind}-om-hole.lw3
  cp "$workspace_root/$lw3" "$om_hole_lw3"
  python3 - "$om_hole_lw3" "$workspace_root/$fsf" "$hole_kind" <<'PY'
import sys

import netCDF4
import numpy as np

lw3_path, fsf_path, hole_kind = sys.argv[1:]
with netCDF4.Dataset(fsf_path) as surface_file:
    surface_pressure = np.asarray(surface_file.variables["psf"][0, 0], dtype=np.float64)
with netCDF4.Dataset(lw3_path, "r+") as wind_file:
    levels = np.asarray(wind_file.variables["level"][:], dtype=np.float64) * 100.0
    om = wind_file.variables["om"]
    fill = np.float32(getattr(om, "_FillValue", 1.0e37))
    for j, i in np.argwhere(np.sum(levels[:, None, None] < surface_pressure, axis=0) >= 3):
        active = np.flatnonzero(levels < surface_pressure[j, i])
        raw_level = int(active[-1] if hole_kind == "bottom" else active[-2])
        om[0, raw_level, int(j), int(i)] = fill
        break
    else:
        raise SystemExit("no column has enough active levels for the OM-hole test")
PY
  "$test_tmp/test_real_shadow_reader" \
    "$workspace_root/$fua" "$workspace_root/$fsf" "$om_hole_lw3" \
    "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file" "$epoch" \
    REJECT_COVERAGE
done

# The fixed PSFC/pressure domain must also reject holes in other required core
# fields instead of adapting the domain to whichever field is incomplete.
for core_case in lw3:u3 fua:sh; do
  source_kind=${core_case%%:*}
  variable_name=${core_case##*:}
  if [ "$source_kind" = lw3 ]; then
    source_path="$workspace_root/$lw3"
  else
    source_path="$workspace_root/$fua"
  fi
  core_hole=$test_tmp/${variable_name}-core-hole.nc
  cp "$source_path" "$core_hole"
  python3 - "$core_hole" "$workspace_root/$fsf" "$variable_name" <<'PY'
import sys

import netCDF4
import numpy as np

path, fsf_path, variable_name = sys.argv[1:]
with netCDF4.Dataset(fsf_path) as surface_file:
    surface_pressure = np.asarray(surface_file.variables["psf"][0, 0], dtype=np.float64)
with netCDF4.Dataset(path, "r+") as source_file:
    levels = np.asarray(source_file.variables["level"][:], dtype=np.float64) * 100.0
    field = source_file.variables[variable_name]
    fill = np.float32(getattr(field, "_FillValue", 1.0e37))
    for j, i in np.argwhere(np.sum(levels[:, None, None] < surface_pressure, axis=0) >= 3):
        active = np.flatnonzero(levels < surface_pressure[j, i])
        field[0, int(active[-2]), int(j), int(i)] = fill
        break
    else:
        raise SystemExit("no column has enough active levels for the core-hole test")
PY
  if [ "$source_kind" = lw3 ]; then
    "$test_tmp/test_real_shadow_reader" \
      "$workspace_root/$fua" "$workspace_root/$fsf" "$core_hole" \
      "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file" "$epoch" \
      REJECT_COVERAGE
  else
    "$test_tmp/test_real_shadow_reader" \
      "$core_hole" "$workspace_root/$fsf" "$workspace_root/$lw3" \
      "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file" "$epoch" \
      REJECT_COVERAGE
  fi
done

invalid_surface=$test_tmp/invalid-surface.fsf
cp "$workspace_root/$fsf" "$invalid_surface"
python3 - "$invalid_surface" <<'PY'
import sys
import netCDF4

with netCDF4.Dataset(sys.argv[1], "r+") as dataset:
    dataset.variables["tsf"][0, 0, 0, 0] = 1000.0
PY
"$test_tmp/test_real_shadow_reader" \
  "$workspace_root/$fua" "$invalid_surface" "$workspace_root/$lw3" \
  "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file" "$epoch" RETAINED_REJECT

subterrain_static=$test_tmp/subterrain-static.nc
python3 - "$subterrain_static" "$static_file" <<'PY'
import sys

import netCDF4
import numpy as np

path, source_path = sys.argv[1:]
with netCDF4.Dataset(source_path) as source, \
     netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET") as target:
    for name, size in (("record", 1), ("z", 1), ("x", 235), ("y", 283)):
        target.createDimension(name, size)
    for name in ("lat", "lon"):
        source_variable = source.variables[name]
        variable = target.createVariable(name, "f4", ("record", "z", "y", "x"))
        variable.units = source_variable.units
        variable[:] = source_variable[:]
    topography = target.createVariable("avg", "f4", ("record", "z", "y", "x"))
    topography.units = "meters MSL"
    topography[:] = np.float32(9000.0)
PY

"$test_tmp/test_real_shadow_reader" \
  "$workspace_root/$fua" "$workspace_root/$fsf" "$workspace_root/$lw3" \
  "$workspace_root/$vrz" "$workspace_root/$vrt" "$subterrain_static" "$epoch" REJECT

validate_diagnostic() {
  local diagnostic=$1
  python3 "$repo_root/tools/validate_shadow_diagnostics.py" "$diagnostic" >/dev/null
  python3 - "$diagnostic" <<'PY'
import sys

import netCDF4

with netCDF4.Dataset(sys.argv[1]) as dataset:
    expected = {
        "contract": "real_radar_only_shadow_v3",
        "diagnostic_schema_version": 5,
        "cloud_bal_schema_version": 5,
        "omega_target_error_contract": "diagonal_pressure_omega_v1",
        "schema_extensions": (
            "verified_operational_identity_v1,radar_no_echo_masks_v1,"
            "pressure_geometry_v2,omega_boundary_contract_v2"
        ),
        "requested_mode": 1,
        "operational_state_verified": 1,
        "operational_state_changed": 0,
        "balance_support_variable": "candidate_balance_support",
        "pressure_interface_semantics": "SURFACE_CLIPPED_CONTROL_VOLUME_BOUNDARY",
        "above_ground_mask_provenance": "PSFC_PRESSURE_CENTER_AND_STATIC_TERRAIN_HEIGHT",
        "grid_spacing_adapter_policy": "KM_TO_M_OR_PINNED_LEGACY_NUMERIC_METERS",
        "radar_valid_semantics": "ECHO_ONLY",
    }
    for name, value in expected.items():
        if getattr(dataset, name, None) != value:
            raise SystemExit(f"writer metadata mismatch: {name}")
    if "candidate_balance_support" not in dataset.variables:
        raise SystemExit("candidate balance support variable is absent")
    for name in (
        "pressure_interface", "cell_dp", "level_spacing_dp",
        "pressure_mass_measure", "dry_air_mass_measure",
        "surface_pressure",
        "omega_top_boundary", "omega_bottom_boundary",
        "omega_top_boundary_valid", "omega_bottom_boundary_valid",
        "omega_top_boundary_quality", "omega_top_boundary_source",
        "omega_bottom_boundary_quality", "omega_bottom_boundary_source",
        "radar_coverage", "radar_no_echo", "radar_missing",
    ):
        if name not in dataset.variables:
            raise SystemExit(f"pressure/boundary variable is absent: {name}")
PY
}

# Exercise both audit and optimized writers on the full real state.  The O2
# build catches allocation and stack behavior that the small fixture cannot.
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" "${nf_fflags[@]}" \
  "$repo_root/tests/real_shadow_driver.f90" "${objects[@]}" \
  "${nf_flibs[@]}" -o "$test_tmp/real_shadow_driver_o0"

diagnostic_o0=$test_tmp/diagnostic-o0.nc
if ! "$test_tmp/real_shadow_driver_o0" \
  "$workspace_root/$fua" "$workspace_root/$fsf" "$workspace_root/$lw3" \
  "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file" \
  "$diagnostic_o0" "$epoch" >"$test_tmp/driver-o0.log" 2>&1; then
  sed -n '1,200p' "$test_tmp/driver-o0.log" >&2
  exit 1
fi
validate_diagnostic "$diagnostic_o0"

bad_radar_marker=$test_tmp/bad-radar-marker.nc
cp "$diagnostic_o0" "$bad_radar_marker"
python3 - "$bad_radar_marker" <<'PY'
import sys
import netCDF4
import numpy as np

with netCDF4.Dataset(sys.argv[1], "r+") as dataset:
    above = np.asarray(dataset.variables["above_ground"][:], dtype=bool)
    radar = np.asarray(dataset.variables["radar_valid"][:], dtype=bool)
    location = tuple(np.argwhere(above & ~radar)[0])
    dataset.variables["radar_dbz"][location] = 5.0
PY
if python3 "$repo_root/tools/validate_shadow_diagnostics.py" \
    "$bad_radar_marker" >/dev/null 2>&1; then
  printf 'validator accepted an invalid inactive-radar payload\n' >&2
  exit 1
fi

bad_flux_ledger=$test_tmp/bad-flux-ledger.nc
cp "$diagnostic_o0" "$bad_flux_ledger"
python3 - "$bad_flux_ledger" <<'PY'
import sys
import netCDF4

with netCDF4.Dataset(sys.argv[1], "r+") as dataset:
    dataset.setncattr("flux_deposited", -1.0)
PY
if python3 "$repo_root/tools/validate_shadow_diagnostics.py" \
    "$bad_flux_ledger" >/dev/null 2>&1; then
  printf 'validator accepted a negative flux-ledger term\n' >&2
  exit 1
fi

bad_no_echo_change=$test_tmp/bad-no-echo-change.nc
cp "$diagnostic_o0" "$bad_no_echo_change"
python3 - "$bad_no_echo_change" <<'PY'
import sys
import netCDF4
import numpy as np

with netCDF4.Dataset(sys.argv[1], "r+") as dataset:
    no_echo = np.asarray(dataset.variables["radar_no_echo"][:], dtype=bool)
    location = tuple(np.argwhere(no_echo)[0])
    dataset.variables["candidate_rain"][location] = np.float32(1.0e-4)
    dataset.variables["column_changed"][location] = np.int32(1)
    dataset.variables["overall_changed"][location] = np.int32(1)
    dataset.variables["hydro_support"][location] = np.int32(1)
PY
if python3 "$repo_root/tools/validate_shadow_diagnostics.py" \
    "$bad_no_echo_change" >/dev/null 2>&1; then
  printf 'validator accepted a hydrometeor change in a no-echo cell\n' >&2
  exit 1
fi

"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" "${nf_fflags[@]}" \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/src/common/cloud_bal_column_physics.f90" \
  "$repo_root/src/common/cloud_bal_grid_geometry.f90" \
  "$repo_root/src/common/cloud_bal_balance_operator.f90" \
  "$repo_root/src/common/cloud_bal_pipeline.f90" \
  "$repo_root/src/common/cloud_bal_real_netcdf.f90" \
  "$repo_root/src/common/cloud_bal_pressure_analysis.f90" \
  "$repo_root/tests/real_shadow_driver.f90" "${nf_flibs[@]}" \
  -o "$test_tmp/real_shadow_driver_o2"

diagnostic_o2=$test_tmp/diagnostic-o2.nc
if ! "$test_tmp/real_shadow_driver_o2" \
  "$workspace_root/$fua" "$workspace_root/$fsf" "$workspace_root/$lw3" \
  "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file" \
  "$diagnostic_o2" "$epoch" >"$test_tmp/driver-o2.log" 2>&1; then
  sed -n '1,200p' "$test_tmp/driver-o2.log" >&2
  exit 1
fi
validate_diagnostic "$diagnostic_o2"
cmp -s "$diagnostic_o0" "$diagnostic_o2" || {
  printf '%s\n' 'O0/O2 SHADOW diagnostics differ' >&2
  exit 1
}

printf 'Real SHADOW I/O contract suite passed with pinned Intel/NetCDF inputs (%s)\n' \
  "$case_id"
