#!/usr/bin/env bash
# Replay the prepared full NE57 real-data case in a new private directory.
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
[[ $# == 2 ]] || { echo 'usage: run_real_full_domain.sh PREPARED_STAGE NEW_RUN_ROOT' >&2; exit 2; }
stage=$(realpath -e "$1")
run=$(realpath -m "$2")
[[ ! -e $run && ! -L $run ]] || { echo 'existing run root rejected' >&2; exit 2; }
. "$repo/tests/intel_toolchain.sh"
unset F_UFMTENDIAN
ulimit -s unlimited
runtime=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/metgrid_netcdf_runtime.YPWjEW/install/lib
export LD_LIBRARY_PATH="$runtime:${LD_LIBRARY_PATH:-}"
python3 "$repo/tests/replay_real_full_domain.py" "$stage" "$run" "$repo"
# Fortran checks the full domain/time contract and all bytes of both output files.
nf=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install
nc=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install
verify_hash() {
  [[ $(sha256sum "$1" | cut -d' ' -f1) == "$2" ]] || { echo "pinned input mismatch: $1" >&2; exit 2; }
}
verify_hash "$nf/include/netcdf.mod" cc68297dd646da94b3ec959ce45c2fa99e0bc7abd2a631b0a5f53192dc7fa15a
verify_hash "$nf/bin/nf-config" e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5
verify_hash "$nf/lib/libnetcdff.a" f610d7ebedf48d17023e9b8377d74d93542bde40d091ec7a5518bb30d17c8a39
verify_hash "$nc/lib/libnetcdf.a" f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288
sha256sum "$nf/include/netcdf.mod" "$nf/bin/nf-config" "$nf/lib/libnetcdff.a" "$nc/lib/libnetcdf.a" \
  "$repo/tests/verify_real_full_domain.f90" "$repo/tests/run_real_full_domain.sh" \
  "$repo/tests/intel_toolchain.sh" > "$run/validation_inputs.sha256"
read -r -a libs <<<"$($nf/bin/nf-config --flibs)"
met=met_em.d01.2026-08-16_13:00:00.nc
for level in O0 O2; do
  build="$run/verify-$level"
  mkdir "$build"
  cd "$build"
  pwd -P > build.cwd
  if [[ $level == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  argv=("$CLOUD_BAL_FC" "${flags[@]}" -I "$nf/include" "$repo/tests/verify_real_full_domain.f90" "${libs[@]}" -o verify.exe)
  python3 - "${argv[@]}" > compiler_argv.json <<'PY'
import json,sys
print(json.dumps(sys.argv[1:]))
PY
  "${argv[@]}" > compile.log 2>&1
  argv=("$build/verify.exe" "$stage/$met" "$run/$met" "$stage/real/wrfinput_d01" "$run/real/wrfinput_d01")
  python3 - "${argv[@]}" > execution_argv.json <<'PY'
import json,sys
print(json.dumps(sys.argv[1:]))
PY
  "${argv[@]}" > verify.log 2>&1
  rg -q 'PASS_SCOPED:' verify.log
done
sha256sum -c "$run/validation_inputs.sha256"
python3 - "$run" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1])
def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()
files={str(p):digest(p) for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
receipt={'status':'PASS_SCOPED','scope':'full real-data metgrid/real replay and Fortran full-file/domain checks',
         'fortran_profiles':['O0','O2'],'model_builds':'pinned prebuilt; not rebuilt at O0/O2',
         'artifacts_sha256':files}
(root/'validation_manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
PY
