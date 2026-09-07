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
trap 'rm -rf "$test_tmp"' EXIT

. "$repo_root/tests/intel_toolchain.sh"

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
)
objects=()
for source in "${sources[@]}"; do
  object=$test_tmp/$source.o
  "$CLOUD_BAL_FC" -c "${CLOUD_BAL_FREE_FLAGS[@]}" \
    -module "$test_tmp" -I "$test_tmp" "${nf_fflags[@]}" \
    "$repo_root/src/common/$source.f90" -o "$object"
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

(
  cd "$test_tmp"
  ./test_real_shadow_io_contract
  [[ -s verified-shadow.nc ]]
  [[ ! -e unverified-shadow.nc ]]
  [[ ! -e nonfinite-residual.nc ]]
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
        ("valtime", epoch, "seconds since (1970-1-1 00:00:00.0)"),
        ("Dx", 5000.0, "kilometers"),
        ("Dy", 5000.0, "kilometers"),
    ):
        dimension = "record" if name == "valtime" else "nav"
        dtype = "f8" if name == "valtime" else "f4"
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
  "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file" "$epoch" REJECT

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
        "cloud_bal_schema_version": 3,
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
  "$repo_root/src/common/cloud_bal_balance_operator.f90" \
  "$repo_root/src/common/cloud_bal_grid_geometry.f90" \
  "$repo_root/src/common/cloud_bal_pipeline.f90" \
  "$repo_root/src/common/cloud_bal_real_netcdf.f90" \
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
