#!/usr/bin/env bash
# Build/run the actual lapsprep caller against a small numerical NetCDF tree.
# This is an isolated contract test, not a full KLAPS operational replay.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(cd "$repo_root/.." && pwd)
scratch_root="$repo_root/scratch"
mkdir -p "$scratch_root"
test_tmp=$(mktemp -d "$scratch_root/lapsprep_vapor_tests.XXXXXX")
if [[ ${CLOUD_BAL_KEEP_TEST_OUTPUT:-0} == 1 ]]; then
  trap 'printf "lapsprep vapor test artifacts retained: %s\n" "$test_tmp"' EXIT
else
  trap 'rm -rf -- "$test_tmp"' EXIT
fi

. "$repo_root/tests/intel_toolchain.sh"

nf_config="$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config"
netcdff_archive="$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a"
netcdf_archive="$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a"
[[ -x "$nf_config" && -f "$netcdff_archive" && -f "$netcdf_archive" ]] || {
  printf 'pinned NetCDF Fortran/C archives are unavailable\n' >&2
  exit 2
}
verify_hash() {
  local path=$1 expected=$2 actual
  actual=$(sha256sum "$path" | cut -d' ' -f1)
  [[ $actual == "$expected" ]] || {
    printf 'pinned dependency hash mismatch: %s\n' "$path" >&2
    exit 2
  }
}
verify_hash "$nf_config" e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5
verify_hash "$netcdff_archive" f610d7ebedf48d17023e9b8377d74d93542bde40d091ec7a5518bb30d17c8a39
verify_hash "$netcdf_archive" f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288
read -r -a nf_fflags <<<"$($nf_config --fflags)"
read -r -a nf_flibs <<<"$($nf_config --flibs)"

build="$test_tmp/build"

compile() {
  local output_build=$1 source=$2 object=$3
  shift 3
  if ! "$CLOUD_BAL_FC" -c "$@" \
      -module "$output_build" -I "$output_build" "${nf_fflags[@]}" \
      "$repo_root/$source" -o "$output_build/$object" \
      >"$output_build/$object.log" 2>&1; then
    cat "$output_build/$object.log" >&2
    exit 1
  fi
}

link() {
  local output_build=$1
  shift
  if ! "$CLOUD_BAL_FC" "$@" \
      "$output_build/lapsprep.o" "$output_build/wps.o" "$output_build/setup.o" \
      "$output_build/contracts.o" "$output_build/moisture.o" "$output_build/stubs.o" \
      "$output_build/cloud_bal_wps_adapter.o" \
      "$output_build/cloud_bal_pressure_analysis.o" \
      "$output_build/cloud_bal_real_netcdf.o" \
      "$output_build/cloud_bal_stage_payload.o" \
      "$output_build/cloud_bal_stage_context.o" \
      "$output_build/cloud_bal_lapsprep_adapter.o" \
      "$output_build/cloud_bal_pipeline.o" \
      "$output_build/cloud_bal_balance_operator.o" \
      "$output_build/cloud_bal_column_physics.o" \
      "$output_build/cloud_bal_grid_geometry.o" \
      "$output_build/cloud_bal_state.o" \
      "${nf_flibs[@]}" -o "$output_build/lapsprep.exe" \
      >"$output_build/link.log" 2>&1; then
    cat "$output_build/link.log" >&2
    exit 1
  fi
}

build_executable() {
  local output_build=$1
  shift
  mkdir -p "$output_build"
  compile "$output_build" tests/lapsprep_vapor_stubs.f90 stubs.o "$@"
  compile "$output_build" src/common/cloud_bal_field_contracts.f90 contracts.o "$@"
  compile "$output_build" src/common/cloud_bal_moisture.f90 moisture.o "$@"
  compile "$output_build" src/common/cloud_bal_state.f90 cloud_bal_state.o "$@"
  compile "$output_build" src/common/cloud_bal_grid_geometry.f90 cloud_bal_grid_geometry.o "$@"
  compile "$output_build" src/common/cloud_bal_column_physics.f90 cloud_bal_column_physics.o "$@"
  compile "$output_build" src/common/cloud_bal_balance_operator.f90 cloud_bal_balance_operator.o "$@"
  compile "$output_build" src/common/cloud_bal_pipeline.f90 cloud_bal_pipeline.o "$@"
  compile "$output_build" src/common/cloud_bal_real_netcdf.f90 cloud_bal_real_netcdf.o "$@"
  compile "$output_build" src/common/cloud_bal_stage_payload.f90 cloud_bal_stage_payload.o "$@"
  compile "$output_build" src/common/cloud_bal_stage_context.f90 cloud_bal_stage_context.o "$@"
  compile "$output_build" src/common/cloud_bal_lapsprep_adapter.f90 cloud_bal_lapsprep_adapter.o "$@"
  compile "$output_build" src/common/cloud_bal_pressure_analysis.f90 cloud_bal_pressure_analysis.o "$@"
  compile "$output_build" src/common/cloud_bal_wps_adapter.f90 cloud_bal_wps_adapter.o "$@"
  compile "$output_build" src/lapsprep/module_setup.f90 setup.o "$@"
  compile "$output_build" src/lapsprep/module_lapsprep_wps.f90 wps.o "$@"
  compile "$output_build" src/lapsprep/lapsprep.f90 lapsprep.o "$@"
  link "$output_build" "$@"
}

build_executable "$build" "${CLOUD_BAL_FREE_FLAGS[@]}"
build_o2="$test_tmp/build-o2"
build_executable "$build_o2" "${CLOUD_BAL_REPRO_FLAGS[@]}"

make_fixture() {
  local root=$1 case_name=$2
  python3 "$repo_root/tests/lapsprep_vapor_fixture.py" "$root" "$case_name"
}

run_success() {
  local root=$1 output=$2 resolved=$3 log=$4 executable
  executable=${5:-$build/lapsprep.exe}
  if [[ $resolved == yes ]]; then
    if ! env -u CLOUD_BAL_SHADOW_EXPERIMENT \
        LAPS_DATA_ROOT="$root" CLOUD_BAL_WPS_OUTPUT="$output" \
        "$executable" 260010300 >"$log" 2>&1; then
      cat "$log" >&2
      exit 1
    fi
  else
    if ! env -u CLOUD_BAL_SHADOW_EXPERIMENT -u CLOUD_BAL_WPS_OUTPUT \
        LAPS_DATA_ROOT="$root" \
        "$executable" 260010300 >"$log" 2>&1; then
      cat "$log" >&2
      exit 1
    fi
  fi
  [[ -s "$output" ]] || { cat "$log" >&2; printf 'missing WPS output: %s\n' "$output" >&2; exit 1; }
}

run_rejected() {
  local root=$1 output=$2 log=$3 pattern=$4
  set +e
  env -u CLOUD_BAL_SHADOW_EXPERIMENT \
    LAPS_DATA_ROOT="$root" CLOUD_BAL_WPS_OUTPUT="$output" \
    "$build/lapsprep.exe" 260010300 >"$log" 2>&1
  local status=$?
  set -e
  if (( status == 0 )) || [[ -e "$output" ]]; then
    cat "$log" >&2
    printf 'invalid fixture unexpectedly succeeded or wrote output: %s\n' "$root" >&2
    exit 1
  fi
  if [[ -n "$pattern" ]] && ! grep -Eq "$pattern" "$log"; then
    cat "$log" >&2
    printf 'invalid fixture failed for an unexpected reason: %s\n' "$root" >&2
    exit 1
  fi
}

run_shadow_rejected() {
  local root=$1 experiment=$2 output=$3 log=$4 pattern=$5
  set +e
  if [[ -n "$output" ]]; then
    CLOUD_BAL_SHADOW_EXPERIMENT="$experiment" CLOUD_BAL_WPS_OUTPUT="$output" \
      LAPS_DATA_ROOT="$root" "$build/lapsprep.exe" 260010300 >"$log" 2>&1
  else
    env -u CLOUD_BAL_WPS_OUTPUT CLOUD_BAL_SHADOW_EXPERIMENT="$experiment" \
      LAPS_DATA_ROOT="$root" "$build/lapsprep.exe" 260010300 >"$log" 2>&1
  fi
  local status=$?
  set -e
  if (( status == 0 )); then
    cat "$log" >&2
    printf 'invalid shadow fixture unexpectedly succeeded: %s\n' "$experiment" >&2
    exit 1
  fi
  if [[ -n "$output" ]] && [[ -e "$output" || -e "$output.shadow.nc" ]]; then
    cat "$log" >&2
    printf 'invalid shadow fixture created output: %s\n' "$experiment" >&2
    exit 1
  fi
  if [[ -n "$pattern" ]] && ! grep -Eq "$pattern" "$log"; then
    cat "$log" >&2
    printf 'invalid shadow fixture failed for an unexpected reason: %s\n' "$experiment" >&2
    exit 1
  fi
}

assert_surface_winds() {
  CLOUD_BAL_REPO_ROOT="$repo_root" python3 - "$1" <<'PY'
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(os.environ["CLOUD_BAL_REPO_ROOT"]) / "tools"))
from compare_baseline import read_wps

fields = read_wps(Path(sys.argv[1]))
for field, expected in (("UU", 50.0), ("VV", -50.0)):
    key = next((key for key in fields if key[0] == field and key[1] == 200100.0), None)
    if key is None or not np.allclose(fields[key][2], expected, rtol=0.0, atol=1.0e-6):
        raise SystemExit(f"{field} surface wind did not select the greatest valid pressure")
PY
}

assert_subterrain_vapor() {
  CLOUD_BAL_REPO_ROOT="$repo_root" python3 - "$1" <<'PY'
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(os.environ["CLOUD_BAL_REPO_ROOT"]) / "tools"))
from compare_baseline import read_wps

fields = read_wps(Path(sys.argv[1]))
expected = {
    50000.0: 0.008,
    40000.0: 0.002 / (1.0 - 0.002),
    30000.0: 0.003 / (1.0 - 0.003),
}
for level, value in expected.items():
    key = next((key for key in fields if key[0] == "QV" and key[1] == level), None)
    if key is None or fields[key][0] != "kg kg{-1}":
        raise SystemExit(f"missing QV output or units at {level}")
    if not np.allclose(fields[key][2], value, rtol=0.0, atol=2.0e-7):
        raise SystemExit(f"unexpected QV values at {level}: {fields[key][2]}")
PY
}

assert_subterrain_contracts() {
  local log=$1
  python3 - "$log" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="ascii")
if not re.search(r"Input contract SH .*?kg kg-1\s+2\s+0\.666", text, re.S):
    raise SystemExit("subterrain SH validity metadata was falsely promoted to complete")
for field, units in (("PSFC", "Pa"), ("MR_SFC", r"g kg-1")):
    if not re.search(rf"Input contract {field} .*?{units}\s+1\s+1\.0+", text, re.S):
        raise SystemExit(f"subterrain fixture did not provide a complete {field} contract")
PY
  grep -q 'WPS below-ground SH surface extrapolation cells=4' "$log" || {
    cat "$log" >&2
    printf '%s\n' 'subterrain fixture did not fill exactly one pressure slab' >&2
    exit 1
  }
}

default_root="$test_tmp/default"
make_fixture "$default_root" default
default_output="$default_root/lapsprd/lapsprep/wps/LAPS:2026-01-01_03:00"
run_success "$default_root" "$default_output" no "$test_tmp/default.log"
python3 "$repo_root/tests/test_lapsprep_vapor.py" default "$default_output"

resolved_root="$test_tmp/resolved"
make_fixture "$resolved_root" strict-vapor
resolved_output="$resolved_root/resolved-output.wps"
run_success "$resolved_root" "$resolved_output" yes "$test_tmp/resolved.log"
python3 "$repo_root/tests/test_lapsprep_vapor.py" vapor "$resolved_output"

fallback_root="$test_tmp/default-vapor"
make_fixture "$fallback_root" strict-vapor
fallback_output="$fallback_root/lapsprd/lapsprep/wps/LAPS:2026-01-01_03:00"
run_success "$fallback_root" "$fallback_output" no "$test_tmp/default-vapor.log"
python3 "$repo_root/tests/test_lapsprep_vapor.py" vapor "$fallback_output"

for case_name in wps-missing-om wps-missing-vv wps-invalid-om wps-invalid-vv; do
  root="$test_tmp/$case_name"
  make_fixture "$root" "$case_name"
  output="$root/lapsprd/lapsprep/wps/LAPS:2026-01-01_03:00"
  run_success "$root" "$output" no "$test_tmp/$case_name.log"
  cmp -s "$fallback_output" "$output" || {
    printf 'WPS-only %s output differs from the complete vapor baseline\n' "$case_name" >&2
    exit 1
  }
  printf 'lapsprep WPS-only omega regression passed: %s\n' "$case_name"
done

for case_name in mixed-missing-om mixed-missing-vv mixed-invalid-om mixed-invalid-vv; do
  root="$test_tmp/$case_name"
  make_fixture "$root" "$case_name"
  if [[ $case_name == *-missing-* ]]; then
    omega_pattern='ncvarid|invalid_(lw3_field: om|surface_field: vv)'
  else
    omega_pattern='invalid_(lw3_field: om|surface_field: vv)'
  fi
  run_rejected "$root" "$root/rejected-output.wps" "$test_tmp/$case_name.log" \
    "$omega_pattern"
  printf 'lapsprep mixed-output omega rejection passed: %s\n' "$case_name"
done

for case_name in missing-u3 missing-v3 invalid-u3 invalid-v3; do
  root="$test_tmp/$case_name"
  make_fixture "$root" "$case_name"
  field=${case_name##*-}
  if [[ $case_name == missing-* ]]; then
    wind_pattern="ncvarid|invalid_lw3_field: $field"
  else
    wind_pattern="invalid_lw3_field: $field"
  fi
  run_rejected "$root" "$root/rejected-output.wps" "$test_tmp/$case_name.log" \
    "$wind_pattern"
  printf 'lapsprep wind rejection passed: %s\n' "$case_name"
done

ascending_root="$test_tmp/ascending-vapor"
make_fixture "$ascending_root" ascending-vapor
ascending_output="$ascending_root/lapsprd/lapsprep/wps/LAPS:2026-01-01_03:00"
run_success "$ascending_root" "$ascending_output" no "$test_tmp/ascending-vapor.log"
python3 "$repo_root/tests/test_lapsprep_vapor.py" vapor "$ascending_output"
printf '%s\n' 'lapsprep ascending-pressure mapping regression passed'

for case_name in duplicate-pressure nonmonotonic-pressure; do
  root="$test_tmp/$case_name"
  make_fixture "$root" "$case_name"
  run_rejected "$root" "$root/rejected-output.wps" "$test_tmp/$case_name.log" \
    'nonmonotonic_pressure_levels'
  printf 'lapsprep pressure-order rejection passed: %s\n' "$case_name"
done

for case_name in make-sfc-uv ascending-make-sfc-uv; do
  root="$test_tmp/$case_name"
  make_fixture "$root" "$case_name"
  output="$root/lapsprd/lapsprep/wps/LAPS:2026-01-01_03:00"
  run_success "$root" "$output" no "$test_tmp/$case_name.log"
  assert_surface_winds "$output"
  printf 'lapsprep make_sfc_uv pressure-order regression passed: %s\n' "$case_name"
done

for case_name in subterrain-sh subterrain-sh-negative ascending-subterrain-sh; do
  root="$test_tmp/$case_name"
  make_fixture "$root" "$case_name"
  output="$root/lapsprd/lapsprep/wps/LAPS:2026-01-01_03:00"
  run_success "$root" "$output" no "$test_tmp/$case_name.log"
  assert_subterrain_vapor "$output"
  assert_subterrain_contracts "$test_tmp/$case_name.log"
  printf 'lapsprep subterrain SH fallback regression passed: %s\n' "$case_name"
done

# Rectangular WPS below-terrain coverage is independent of optional QV.
for optimization in o0 o2; do
  root="$test_tmp/subterrain-no-qv-$optimization"
  make_fixture "$root" subterrain-sh
  sed -i 's/WPS_OUTPUT_VAPOR=.true./WPS_OUTPUT_VAPOR=.false./' "$root/static/lapsprep.nl"
  executable="$build/lapsprep.exe"
  [[ $optimization != o2 ]] || executable="$build_o2/lapsprep.exe"
  output="$root/lapsprd/lapsprep/wps/LAPS:2026-01-01_03:00"
  run_success "$root" "$output" no "$test_tmp/subterrain-no-qv-$optimization.log" "$executable"
  python3 "$repo_root/tests/test_lapsprep_vapor.py" default "$output"
done

hotstart_root="$test_tmp/hotstart-vapor"
make_fixture "$hotstart_root" hotstart-vapor
hotstart_output="$hotstart_root/lapsprd/lapsprep/wps/LAPS:2026-01-01_03:00"
run_success "$hotstart_root" "$hotstart_output" no "$test_tmp/hotstart-vapor.log"
python3 "$repo_root/tests/test_lapsprep_vapor.py" hotstart-vapor "$hotstart_output"

hotstart_o2_root="$test_tmp/hotstart-vapor-o2"
make_fixture "$hotstart_o2_root" hotstart-vapor
hotstart_o2_output="$hotstart_o2_root/lapsprd/lapsprep/wps/LAPS:2026-01-01_03:00"
run_success "$hotstart_o2_root" "$hotstart_o2_output" no "$test_tmp/hotstart-vapor-o2.log" \
  "$build_o2/lapsprep.exe"
python3 "$repo_root/tests/test_lapsprep_vapor.py" hotstart-vapor "$hotstart_o2_output"

for case_name in missing-sh nan inf bad-t bad-mr; do
  root="$test_tmp/reject-$case_name"
  make_fixture "$root" "$case_name"
  rejected_output="$root/rejected-output.wps"
  log="$test_tmp/reject-$case_name.log"
  set +e
  env -u CLOUD_BAL_SHADOW_EXPERIMENT \
    LAPS_DATA_ROOT="$root" CLOUD_BAL_WPS_OUTPUT="$rejected_output" \
    "$build/lapsprep.exe" 260010300 >"$log" 2>&1
  status=$?
  set -e
  if (( status == 0 )); then
    cat "$log" >&2
    printf 'invalid %s fixture unexpectedly succeeded\n' "$case_name" >&2
    exit 1
  fi
  rejection_pattern='WPS QV requires complete SH, MR_SFC, T3, and T_SFC inputs'
  if [[ $case_name == nan || $case_name == inf ]]; then rejection_pattern='invalid_sh_field'; fi
  grep -q "$rejection_pattern" "$log" || {
    cat "$log" >&2
    printf 'invalid %s fixture did not fail at the pre-output contract gate\n' "$case_name" >&2
    exit 1
  }
  [[ ! -e "$rejected_output" ]] || {
    printf 'invalid %s fixture created output before rejection\n' "$case_name" >&2
    exit 1
  }
  printf 'lapsprep vapor rejection passed: %s\n' "$case_name"
done

for case_name in subterrain-missing-sh subterrain-aboveground subterrain-equality \
  subterrain-nan subterrain-inf subterrain-high subterrain-bad-psfc; do
  root="$test_tmp/reject-$case_name"
  make_fixture "$root" "$case_name"
  rejection_pattern='invalid_sh_field'
  if [[ $case_name == subterrain-missing-sh || $case_name == subterrain-bad-psfc ]]; then
    rejection_pattern='WPS QV requires complete SH, MR_SFC, T3, and T_SFC inputs'
  fi
  run_rejected "$root" "$root/rejected-output.wps" "$test_tmp/reject-$case_name.log" \
    "$rejection_pattern"
  printf 'lapsprep subterrain SH rejection passed: %s\n' "$case_name"
done

strict_root="$test_tmp/reject-strict-bad-t"
make_fixture "$strict_root" strict-bad-t
strict_output="$strict_root/rejected-output.wps"
strict_log="$test_tmp/reject-strict-bad-t.log"
set +e
env -u CLOUD_BAL_SHADOW_EXPERIMENT \
  LAPS_DATA_ROOT="$strict_root" CLOUD_BAL_WPS_OUTPUT="$strict_output" \
  "$build/lapsprep.exe" 260010300 >"$strict_log" 2>&1
status=$?
set -e
if (( status == 0 )) || [[ -e "$strict_output" ]]; then
  cat "$strict_log" >&2
  printf '%s\n' 'strict invalid T3 fixture unexpectedly succeeded or wrote output' >&2
  exit 1
fi
printf '%s\n' 'lapsprep vapor rejection passed: strict-bad-t'

shadow_unknown_root="$test_tmp/shadow-unknown"
make_fixture "$shadow_unknown_root" default
shadow_unknown_output="$shadow_unknown_root/shadow-unknown.wps"
run_shadow_rejected "$shadow_unknown_root" UNKNOWN "$shadow_unknown_output" \
  "$test_tmp/shadow-unknown.log" 'Invalid CLOUD_BAL_SHADOW_EXPERIMENT'
printf '%s\n' 'lapsprep SHADOW rejection passed: unknown experiment'

shadow_missing_output_root="$test_tmp/shadow-missing-output"
make_fixture "$shadow_missing_output_root" strict-vapor
run_shadow_rejected "$shadow_missing_output_root" HYDRO '' \
  "$test_tmp/shadow-missing-output.log" 'SHADOW requires an explicit separate WPS output path'
printf '%s\n' 'lapsprep SHADOW rejection passed: missing output path'

shadow_nonwps_root="$test_tmp/shadow-nonwps"
make_fixture "$shadow_nonwps_root" default
sed -i "s/OUTPUT_FORMAT='wps'/OUTPUT_FORMAT='cdf'/" \
  "$shadow_nonwps_root/static/lapsprep.nl"
shadow_nonwps_output="$shadow_nonwps_root/shadow-nonwps.wps"
run_shadow_rejected "$shadow_nonwps_root" HYDRO "$shadow_nonwps_output" \
  "$test_tmp/shadow-nonwps.log" 'SHADOW requires WPS-only/QV and unmodified legacy inputs'
printf '%s\n' 'lapsprep SHADOW rejection passed: non-WPS output'

shadow_mixed_root="$test_tmp/shadow-mixed"
make_fixture "$shadow_mixed_root" mixed-missing-om
shadow_mixed_output="$shadow_mixed_root/shadow-mixed.wps"
run_shadow_rejected "$shadow_mixed_root" HYDRO "$shadow_mixed_output" \
  "$test_tmp/shadow-mixed.log" 'SHADOW requires WPS-only/QV and unmodified legacy inputs'
printf '%s\n' 'lapsprep SHADOW rejection passed: mixed output'

shadow_hotstart_root="$test_tmp/shadow-hotstart"
make_fixture "$shadow_hotstart_root" hotstart-vapor
shadow_hotstart_output="$shadow_hotstart_root/shadow-hotstart.wps"
run_shadow_rejected "$shadow_hotstart_root" HYDRO "$shadow_hotstart_output" \
  "$test_tmp/shadow-hotstart.log" 'SHADOW requires WPS-only/QV and unmodified legacy inputs'
printf '%s\n' 'lapsprep SHADOW rejection passed: legacy hot-start'

shadow_missing_qv_root="$test_tmp/shadow-missing-qv"
make_fixture "$shadow_missing_qv_root" missing-sh
shadow_missing_qv_output="$shadow_missing_qv_root/shadow-missing-qv.wps"
run_shadow_rejected "$shadow_missing_qv_root" HYDRO "$shadow_missing_qv_output" \
  "$test_tmp/shadow-missing-qv.log" 'WPS QV requires complete SH, MR_SFC, T3, and T_SFC inputs'
printf '%s\n' 'lapsprep SHADOW rejection passed: missing QV input'

printf '%s\n' 'actual lapsprep caller vapor regression passed'
