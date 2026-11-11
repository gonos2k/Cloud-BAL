#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
bundle=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$bundle/../../../../.." && pwd)
fixture="$root/tests/fixtures/kdm6_wrapper"
source "$root/tests/intel_toolchain.sh"
printf '%s  %s\n' \
  5f24e3b5a74dd26499faf1f0bb69b8e7b05e87a56b4746fbfe4fca110020b6b7 "$bundle/module_mp_radar.F" \
  5b80377fecdc18a5f0ad38d3b6c15cfc86ad5d76701adbbbb08a08698d0f7062 "$fixture/module_model_constants.F" \
  449be0d252beba8c5a42ade42fceb2e582239d1a36db79ef3ad902f0ed82ede1 "$fixture/libmassv.F" \
  2ed7dc6e90e0fe442ffee84512b4998d31c8ec3400d3a7ab6078404065f784a6 "$fixture/module_wrf_error.F" \
  8e778d1af7818cce2920526ef8bdf9b79d0c838162b1c09461966fdce384ca86 "$fixture/wrf_debug_stub.f90" | sha256sum -c
work=$(mktemp -d "$root/../ice-column.XXXXXXXX")
printf 'WORK_DIR %s\n' "$work"
python3 "$bundle/inputs.py" "$bundle/../../cases/profiles.json" "$work/inputs"
cd "$work"
python3 "$bundle/prepare.py" "$root/docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90" > instrument.log
for opt in O0 O2; do
 if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
 for mode in original instrumented; do
  mkdir "$work/${opt}_${mode}"
  cd "$work/${opt}_${mode}"
  cp "$fixture/"{module_wrf_error.F,module_model_constants.F,libmassv.F,wrf_debug_stub.f90} .
  cp "$bundle/module_mp_radar.F" .
  if [[ $mode == original ]]; then cp "$root/docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90" module_mp_kdm6.F; else cp "$work/instrumented.f90" module_mp_kdm6.F; fi
  "$CLOUD_BAL_FC" "${flags[@]}" -free -fpp -c module_wrf_error.F module_model_constants.F module_mp_radar.F >build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -free -fpp -DRWORDSIZE=4 -convert big_endian -c module_mp_kdm6.F >>build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -fixed -fpp -c libmassv.F >>build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -c wrf_debug_stub.f90 "$bundle/driver.f90" >>build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -o column.exe driver.o module_mp_kdm6.o module_mp_radar.o module_model_constants.o libmassv.o wrf_debug_stub.o >>build.log 2>&1
  for input in "$work"/inputs/*.txt; do
   case_name=$(basename "$input" .txt); mkdir "$case_name"; cd "$case_name"
   ../column.exe < "$input" > run.log 2>&1
   cd ..
  done
 done
 for input in "$work"/inputs/*.txt; do
  case_name=$(basename "$input" .txt)
  cmp "$work/${opt}_original/$case_name/terminal.bin" "$work/${opt}_instrumented/$case_name/terminal.bin"
 done
 printf '%s terminal byte comparisons PASS\n' "$opt"
done
