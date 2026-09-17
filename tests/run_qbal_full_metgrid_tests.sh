#!/usr/bin/env bash
# Full serial metgrid, with exact time and unchanged approved little-endian input.
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
if [[ $# != 4 ]]; then
  echo 'usage: run_qbal_full_metgrid_tests.sh WPS_ROOT LAPSPREP_ROOT MANIFEST_SHA256 RUN_ROOT' >&2
  exit 2
fi
wps=$(realpath -e "$1")
source_root=$(realpath -e "$2")
manifest_sha=$3
run=$(realpath -m "$4")
[[ ! -e $run && ! -L $run ]] || { echo 'existing run root rejected' >&2; exit 2; }
. "$repo/tests/intel_toolchain.sh"
unset F_UFMTENDIAN
wrf=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/KIM_RDPS_MODL_V2026.2
met_netcdf=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel
nf=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install
nc=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install
verify_hash() {
  [[ $(sha256sum "$1" | cut -d' ' -f1) == "$2" ]] || { echo "pinned dependency mismatch: $1" >&2; exit 2; }
}
verify_hash "$nf/include/netcdf.mod" cc68297dd646da94b3ec959ce45c2fa99e0bc7abd2a631b0a5f53192dc7fa15a
verify_hash "$nf/bin/nf-config" e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5
verify_hash "$nf/lib/libnetcdff.a" f610d7ebedf48d17023e9b8377d74d93542bde40d091ec7a5518bb30d17c8a39
verify_hash "$nc/lib/libnetcdf.a" f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288
mkdir -p "$(dirname "$run")"
mkdir "$run"
sha256sum "$nf/bin/nf-config" "$nf/include/netcdf.mod" "$nf/lib/libnetcdff.a" \
  "$nc/lib/libnetcdf.a" "$repo/tests/intel_toolchain.sh" \
  "$repo/tests/run_qbal_full_metgrid_tests.sh" "$repo/tests/build_qbal_full_metgrid.sh" \
  "$repo/tests/wps_full_sources.sha256" "$repo/tests/wps_link_inputs.sha256" \
  "$repo/tests/verify_qbal_full_metgrid.py" "$repo/tests/verify_qbal_full_metgrid.f90" \
  "$repo/tests/test_metgrid_time.f90" \
  "$repo/tests/verify_qbal_metgrid_reader.py" "$repo/tests/qbal_metgrid_wind_reference.f90" \
  "$repo/tests/create_qbal_metgrid_geo.f90" "$repo/tests/qbal_metgrid.tbl" \
  "$repo/patches/wps_metgrid_exact_time.patch" > "$run/validation_inputs.sha256"
read -r -a libs <<<"$($nf/bin/nf-config --flibs)"
python3 "$repo/tests/verify_qbal_full_metgrid.py" prepare "$source_root" "$manifest_sha" "$run"
for level in O0 O2; do
  build="$run/$level"
  bash "$repo/tests/build_qbal_full_metgrid.sh" "$wps" "$build" "$level" \
    "$wrf" "$met_netcdf" "$repo/patches/wps_metgrid_exact_time.patch"
  cd "$build"
  pwd -P > validation.cwd
  if [[ $level == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  record_argv() {
    python3 - "$@" >> validation_argv.jsonl <<'PY'
import json, sys
print(json.dumps(sys.argv[1:]))
PY
    "$@"
  }
  modules="$build/objects"
  record_argv "$CLOUD_BAL_FC" "${flags[@]}" -I "$modules" -I "$nf/include" \
    "$repo/tests/create_qbal_metgrid_geo.f90" "$modules/module_map_utils.o" \
    "$modules/misc_definitions_module.o" "$modules/constants_module.o" \
    "$modules/module_debug.o" "$modules/parallel_module.o" "$modules/cio.o" "${libs[@]}" -o create_geo.exe
  record_argv "$CLOUD_BAL_FC" "${flags[@]}" -I "$nf/include" \
    "$repo/tests/qbal_metgrid_wind_reference.f90" "$repo/tests/verify_qbal_full_metgrid.f90" \
    "${libs[@]}" -o verify_full.exe
  record_argv "$CLOUD_BAL_FC" "${flags[@]}" -I "$modules" \
    "$repo/tests/test_metgrid_time.f90" "$modules/module_date_pack.o" \
    "$modules/module_debug.o" "$modules/parallel_module.o" "$modules/cio.o" -o test_time.exe
  ./test_time.exe > time-unit.log 2>&1
  rg -q 'METGRID_TIME_TEST_PASS' time-unit.log
  ./create_geo.exe geo_em.d01.nc > create_geo.log 2>&1
  python3 "$repo/tests/verify_qbal_full_metgrid.py" run "$run" "$level" "$repo"
done
sha256sum -c "$run/validation_inputs.sha256"
python3 "$repo/tests/verify_qbal_full_metgrid.py" finish "$run" "$repo"
