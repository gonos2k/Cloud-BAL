#!/usr/bin/env bash
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
workspace=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
artifact_root=/var/tmp/pr78_cp06a_spatial.V9LYrN
inputs=$artifact_root/inputs.json
coupled=$artifact_root/O2/coupled.nc
profile=${1:?usage: run_pr94_hydro_current_generation.sh O0|O2 NEW_RUN_ROOT}
run=$(realpath -m "${2:?usage: run_pr94_hydro_current_generation.sh O0|O2 NEW_RUN_ROOT}")
[[ $profile == O0 || $profile == O2 ]]
[[ ! -e $run && ! -L $run ]]
[[ $(sha256sum "$inputs" | cut -d' ' -f1) == f655339a0bd682b14df9afde0fb007a5124327f9771fd0c9630f801836c2480e ]]
[[ $(sha256sum "$coupled" | cut -d' ' -f1) == 2fba48293d11c33d93b63b60d874ffbd3431e4397c92806996732e5d11def260 ]]

. "$repo/tests/intel_toolchain.sh"
nf_config=$workspace/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config
nf_fortran_lib=$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a
nf_c_lib=$workspace/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a
[[ -x $nf_config && -f $nf_fortran_lib && -f $nf_c_lib ]]
read -r -a nf_flags <<<"$("$nf_config" --fflags)"
read -r -a nf_libs <<<"$("$nf_config" --flibs)"
if [[ $profile == O0 ]]; then compiler_flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else compiler_flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi

mapfile -t args < <(python3 - "$inputs" <<'PY'
import json,sys
print("\n".join(json.load(open(sys.argv[1]))["driver_arguments"]))
PY
)
[[ ${#args[@]} == 13 ]]
python3 - "$inputs" <<'PY'
import hashlib,json,sys
from pathlib import Path
m=json.loads(Path(sys.argv[1]).read_text())
for table in ("authority_hashes","input_hashes"):
    for name,expected in m[table].items():
        p=Path(name)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
            raise SystemExit(f"input manifest mismatch: {p}")
PY

mkdir -p "$run/source/common" "$run/source/tests" "$run/build"
sources=(cloud_bal_state cloud_bal_grid_geometry cloud_bal_column_physics \
  cloud_bal_balance_operator cloud_bal_pipeline cloud_bal_real_netcdf)
for name in "${sources[@]}"; do cp "$repo/src/common/$name.f90" "$run/source/common/"; done
cp "$repo/tests/pr94_hydro_current_generation.f90" "$run/source/tests/"
source_files=()
for name in "${sources[@]}"; do source_files+=("$run/source/common/$name.f90"); done
source_files+=("$run/source/tests/pr94_hydro_current_generation.f90")
input_files=("$inputs" "$coupled" "${args[@]:0:12}")
sha256sum "${source_files[@]}" > "$run/source_pre.sha256"
sha256sum "${input_files[@]}" > "$run/input_pre.sha256"
printf 'profile=%s\ncompiler=%s\ncompiler_version=%s\ncompiler_sha256=%s\n' \
  "$profile" "$CLOUD_BAL_FC" "$("$CLOUD_BAL_FC" --version 2>&1 | sed -n '1p')" \
  "$(sha256sum "$CLOUD_BAL_FC" | cut -d' ' -f1)" > "$run/build/profile.txt"
printf 'netcdf_fortran_sha256=%s\nnetcdf_c_sha256=%s\n' \
  "$(sha256sum "$nf_fortran_lib" | cut -d' ' -f1)" \
  "$(sha256sum "$nf_c_lib" | cut -d' ' -f1)" >> "$run/build/profile.txt"
build_workdir=$(cd "$run/build" && pwd -P)
[[ $build_workdir == "$run/build" ]]
printf 'build_working_directory=%s\n' "$build_workdir" >> "$run/build/profile.txt"
objects=()
for name in "${sources[@]}"; do
  object="$run/build/$name.o"
  (cd "$run/build" && "$CLOUD_BAL_FC" -c "${compiler_flags[@]}" \
    -module "$run/build" -I "$run/build" "${nf_flags[@]}" \
    "$run/source/common/$name.f90" -o "$object") >"$run/build/$name.compile.log" 2>&1
  objects+=("$object")
done
(cd "$run/build" && "$CLOUD_BAL_FC" "${compiler_flags[@]}" \
  -module "$run/build" -I "$run/build" "${nf_flags[@]}" \
  "$run/source/tests/pr94_hydro_current_generation.f90" \
  "${objects[@]}" "${nf_libs[@]}" -o "$run/build/pr94-hydro-current") >"$run/build/link.log" 2>&1
"$run/build/pr94-hydro-current" "${args[@]}" "$coupled" "$run/build/hydro_candidate.nc" \
  >"$run/build/run.log" 2>&1
cat "$run/build/run.log"
sha256sum "${source_files[@]}" > "$run/source_post.sha256"
sha256sum "${input_files[@]}" > "$run/input_post.sha256"
cmp "$run/source_pre.sha256" "$run/source_post.sha256"
cmp "$run/input_pre.sha256" "$run/input_post.sha256"
sha256sum "$run/build/pr94-hydro-current" "$run/build/hydro_candidate.nc" \
  "$run/build/profile.txt" > "$run/artifacts.sha256"
printf 'candidate=%s\n' "$run/build/hydro_candidate.nc"
