#!/usr/bin/env bash
set -euo pipefail
bundle=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$bundle/../../../.." && pwd)
source "$root/tests/intel_toolchain.sh"
work=$(mktemp -d "$root/../first-row-replay.XXXXXXXX")
printf 'WORK_DIR %s\n' "$work"
source_file=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_activation_path_20261110/Cloud-BAL/docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90
fixture="$root/tests/fixtures/kdm6_wrapper"
radar="$root/docs/evidence/ice_stage_contract_20261111/native/full/module_mp_radar.F"
python3 "$bundle/input.py" "$work/input.bin"
python3 "$bundle/prepare.py" "$source_file" "$work/instrumented.f90"
for opt in O0 O2; do
 for mode in original instrumented; do
  mkdir "$work/${opt}_${mode}"
  cd "$work/${opt}_${mode}"
  cp "$work/input.bin" .
  cp "$fixture/"{module_wrf_error.F,module_model_constants.F,libmassv.F,wrf_debug_stub.f90} .
  cp "$radar" .
  if [[ $mode == original ]]; then cp "$source_file" module_mp_kdm6.F; else cp "$work/instrumented.f90" module_mp_kdm6.F; fi
  flags=(-"$opt" -fp-model strict -fimf-arch-consistency=true -no-ftz -fpe0 -traceback)
  "$CLOUD_BAL_FC" "${flags[@]}" -free -fpp -c module_wrf_error.F module_model_constants.F module_mp_radar.F > build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -free -fpp -DRWORDSIZE=4 -convert big_endian -real-size 32 -i4 -c module_mp_kdm6.F >> build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -fixed -fpp -c libmassv.F >> build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -convert big_endian -c wrf_debug_stub.f90 "$bundle/driver.f90" >> build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -o row.exe driver.o module_mp_kdm6.o module_mp_radar.o module_model_constants.o libmassv.o wrf_debug_stub.o >> build.log 2>&1
  ./row.exe > run.log 2>&1
 done
 cmp "$work/${opt}_original/terminal.bin" "$work/${opt}_instrumented/terminal.bin"
 python3 "$bundle/compare.py" "$work/${opt}_original/terminal.bin" > "$work/${opt}_comparison.json"
 echo "$opt original/instrumented and native terminal words identical"
done
