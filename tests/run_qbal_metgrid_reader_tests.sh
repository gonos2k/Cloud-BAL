#!/usr/bin/env bash
# Compile the pinned, unmodified WPS metgrid reader in a fresh scratch directory.
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
if [[ $# != 4 ]]; then
  echo 'usage: run_qbal_metgrid_reader_tests.sh WPS_ROOT LAPSPREP_ROOT MANIFEST_SHA256 RUN_ROOT' >&2
  exit 2
fi
wps_root=$(cd "$1" && pwd -P)
lapsprep_root=$(cd "$2" && pwd -P)
manifest_sha=$3
run_root=$(realpath -m "$4")
[[ ! -e $run_root && ! -L $run_root ]] || { echo 'existing run root rejected' >&2; exit 2; }
. "$repo_root/tests/intel_toolchain.sh"
# These approved LAPSPREP fixtures are little endian; prevent runtime overrides.
unset F_UFMTENDIAN
cc=/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin/icx
[[ $(sha256sum "$cc" | cut -d' ' -f1) == 9fe05a4aef59abce8d8f0631964dd0f12932345d0d38fc9e9d6f6af844e94b33 ]]
# This ordered list binds exactly the source files used by both builds.
(cd "$wps_root" && sha256sum -c "$repo_root/tests/wps_reader_sources.sha256")
mkdir -p "$(dirname "$run_root")"
mkdir "$run_root"
sha256sum "$CLOUD_BAL_FC" "$cc" "$cloud_bal_imf" "$cloud_bal_intlc" \
  "$cloud_bal_setvars" "$repo_root/tests/intel_toolchain.sh" \
  "$repo_root/tests/verify_qbal_metgrid_reader.f90" \
  "$repo_root/tests/verify_qbal_metgrid_reader.py" \
  "$repo_root/tests/run_qbal_metgrid_reader_tests.sh" \
  "$repo_root/tests/wps_reader_sources.sha256" > "$run_root/build_inputs.sha256"
python3 "$repo_root/tests/verify_qbal_metgrid_reader.py" prepare \
  "$lapsprep_root" "$manifest_sha" "$run_root"
for level in O0 O2; do
  build="$run_root/$level"
  mkdir "$build"
  cd "$build"
  pwd -P > build.cwd
  if [[ $level == O0 ]]; then
    flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  else
    flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  record_argv() {
    python3 - "$@" >> compiler_argv.jsonl <<'PY'
import json, sys
print(json.dumps(sys.argv[1:]))
PY
    "$@"
  }
  objects=()
  while read -r expected source; do
    filename=${source##*/}
    object=${filename%.*}.o
    if [[ $source == *.c ]]; then
      record_argv "$cc" -c -"$level" -D_UNDERSCORE "$wps_root/$source" -o "$object"
    else
      record_argv "$CLOUD_BAL_FC" -c "${flags[@]}" -free -fpp -D_METGRID \
        -convert little_endian -module "$build" -I "$build" "$wps_root/$source" -o "$object"
    fi
    objects+=("$object")
  done < "$repo_root/tests/wps_reader_sources.sha256"
  record_argv "$CLOUD_BAL_FC" "${flags[@]}" -convert little_endian -I "$build" \
    "$repo_root/tests/verify_qbal_metgrid_reader.f90" "${objects[@]}" -o verify_reader.exe
  # Prove the comparator detects a reader that corrupts time or returned data.
  for mutation in time slab; do
    python3 "$repo_root/tests/verify_qbal_metgrid_reader.py" mutate \
      "$wps_root/metgrid/src/read_met_module.F" "$mutation" "$build/read_met_$mutation.F"
    record_argv "$CLOUD_BAL_FC" -c "${flags[@]}" -free -fpp -D_METGRID \
      -convert little_endian -module "$build" -I "$build" "read_met_$mutation.F" -o "read_met_$mutation.o"
    mutant_objects=()
    for object in "${objects[@]}"; do
      [[ $object == read_met_module.o ]] || mutant_objects+=("$object")
    done
    record_argv "$CLOUD_BAL_FC" "${flags[@]}" -convert little_endian -I "$build" \
      "$repo_root/tests/verify_qbal_metgrid_reader.f90" "${mutant_objects[@]}" \
      "read_met_$mutation.o" -o "verify_reader_$mutation.exe"
  done
  python3 "$repo_root/tests/verify_qbal_metgrid_reader.py" run "$run_root" "$level"
done
(cd "$wps_root" && sha256sum -c "$repo_root/tests/wps_reader_sources.sha256")
sha256sum -c "$run_root/build_inputs.sha256"
python3 "$repo_root/tests/verify_qbal_metgrid_reader.py" finish \
  "$run_root" "$wps_root" "$repo_root"
