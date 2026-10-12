#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
artifact_root=/var/tmp/pr78_cp06a_spatial.V9LYrN
inputs_json=$artifact_root/inputs.json
coupled_nc=$artifact_root/O2/coupled.nc
spec_path=$repo_root/docs/CP06_A_THERMO_DENSITY_PRIOR_SPEC_V4_20261012.md
spec_sha256=3af8a49e2e270f0966d0bc68f33ced6a58678408efb1517428f6684beb69588d
scratch_root=${CLOUD_BAL_TEST_SCRATCH_ROOT:-/var/tmp}
mkdir -p "$scratch_root"
run_root=$(mktemp -d "$scratch_root/pr81_joint_thermo.XXXXXX")
printf 'joint thermo retained trial directory: %s\n' "$run_root"
. "$repo_root/tests/intel_toolchain.sh"

nf_config=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config
netcdf_fortran_lib=$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a
netcdf_c_lib=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a
[[ -f $inputs_json && -f $coupled_nc && -x $nf_config && -f $netcdf_fortran_lib && -f $netcdf_c_lib ]] || {
  printf 'pinned CP06-A input artifact or NetCDF library is unavailable\n' >&2
  exit 2
}
[[ -f $spec_path && $(sha256sum "$spec_path" | cut -d' ' -f1) == "$spec_sha256" ]] || {
  printf 'predeclared v4 thermo-density specification is missing or differs from its saved hash\n' >&2
  exit 2
}
read -r -a nf_fflags <<<"$("$nf_config" --fflags)"
read -r -a nf_flibs <<<"$("$nf_config" --flibs)"
mapfile -t driver_args < <(PR81_INPUTS_JSON="$inputs_json" python -c \
  'import json,os; print("\n".join(json.load(open(os.environ["PR81_INPUTS_JSON"]))["driver_arguments"]))')
[[ ${#driver_args[@]} == 13 ]] || { printf 'inputs.json does not contain the 13-argument real reader binding\n' >&2; exit 2; }

python - "$inputs_json" <<'PY'
import hashlib
import json
import pathlib
import sys

manifest = json.loads(pathlib.Path(sys.argv[1]).read_text())
for group in ("authority_hashes", "input_hashes"):
    for filename, expected in manifest[group].items():
        path = pathlib.Path(filename)
        if not path.is_file():
            raise SystemExit(f"missing hash-bound CP06-A input: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            raise SystemExit(f"CP06-A input hash mismatch: {path} expected={expected} actual={actual}")
PY

source_names=(cloud_bal_state cloud_bal_grid_geometry cloud_bal_column_physics \
  cloud_bal_balance_operator cloud_bal_pipeline cloud_bal_real_netcdf)
source_dir=$run_root/source_snapshot
mkdir -p "$source_dir/src/common" "$source_dir/tests" "$source_dir/docs"
for name in "${source_names[@]}"; do cp "$repo_root/src/common/$name.f90" "$source_dir/src/common/"; done
cp "$repo_root/tests/pr81_joint_thermo_retained.f90" "$repo_root/tests/intel_toolchain.sh" \
  "$source_dir/tests/"
cp "$spec_path" "$source_dir/docs/"
source_files=()
for name in "${source_names[@]}"; do source_files+=("$source_dir/src/common/$name.f90"); done
source_files+=("$source_dir/tests/pr81_joint_thermo_retained.f90" \
  "$source_dir/tests/intel_toolchain.sh" "$source_dir/docs/$(basename "$spec_path")")
input_files=("$inputs_json" "$coupled_nc" "$spec_path" "${driver_args[@]:0:12}")
sha256sum "${source_files[@]}" > "$run_root/source_pre.sha256"
sha256sum "${input_files[@]}" > "$run_root/input_pre.sha256"
cp "$inputs_json" "$run_root/inputs.json.archive"
cp "$coupled_nc" "$run_root/coupled.nc.archive"
cp "$spec_path" "$run_root/thermo_density_prior_v4_spec.md.archive"

build_dir=$run_root/O2
mkdir -p "$build_dir"
printf 'profile=O2\ncompiler=%s\ncompiler_version=%s\ncompiler_sha256=%s\n' \
  "$CLOUD_BAL_FC" "$("$CLOUD_BAL_FC" --version 2>&1 | sed -n '1p')" \
  "$(sha256sum "$CLOUD_BAL_FC" | cut -d' ' -f1)" > "$build_dir/profile.txt"
printf 'netcdf_fortran_config=%s\nnetcdf_fortran_sha256=%s\nnetcdf_c_sha256=%s\n' \
  "$nf_config" "$(sha256sum "$netcdf_fortran_lib" | cut -d' ' -f1)" \
  "$(sha256sum "$netcdf_c_lib" | cut -d' ' -f1)" >> "$build_dir/profile.txt"
objects=()
for name in "${source_names[@]}"; do
  object=$build_dir/$name.o
  "$CLOUD_BAL_FC" -c "${CLOUD_BAL_REPRO_FLAGS[@]}" -module "$build_dir" -I "$build_dir" \
    "${nf_fflags[@]}" "$source_dir/src/common/$name.f90" -o "$object" \
    >"$build_dir/$name.compile.log" 2>&1
  objects+=("$object")
done
"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" -module "$build_dir" -I "$build_dir" \
  "${nf_fflags[@]}" "$source_dir/tests/pr81_joint_thermo_retained.f90" \
  "${objects[@]}" "${nf_flibs[@]}" -o "$build_dir/pr81-joint-thermo" \
  >"$build_dir/link.log" 2>&1
sha256sum "$build_dir/pr81-joint-thermo" > "$build_dir/executable.sha256"
set +e
"$build_dir/pr81-joint-thermo" "${driver_args[@]}" "$coupled_nc" \
  "$build_dir/joint_candidate.nc" >"$build_dir/run.log" 2>&1
run_status=$?
set -e
cat "$build_dir/run.log"
sha256sum "${source_files[@]}" > "$run_root/source_post.sha256"
sha256sum "${input_files[@]}" > "$run_root/input_post.sha256"
cmp "$run_root/source_pre.sha256" "$run_root/source_post.sha256"
cmp "$run_root/input_pre.sha256" "$run_root/input_post.sha256"
sha256sum "$run_root/inputs.json.archive" "$run_root/coupled.nc.archive" \
  "$run_root/thermo_density_prior_v4_spec.md.archive" > "$run_root/archive.sha256"
{
  printf 'retained_candidate=%s\n' "$coupled_nc"
  printf 'source_head='; git -C "$repo_root" rev-parse HEAD
  printf 'source_snapshot_identity=pre_post_hashes_equal\n'
  printf 'input_snapshot_identity=pre_post_hashes_equal\n'
  printf 'compiler_profile=Intel O2 pinned\n'
  printf 'artifact_scope=single joint thermo-density/Phi/force candidate plus over-cap rollback\n'
  printf 'science_authority=NONE\n'
  printf 'exit_status=%s\n' "$run_status"
  printf 'run_log_sha256='; sha256sum "$build_dir/run.log" | cut -d' ' -f1
  if [[ -f $build_dir/joint_candidate.nc ]]; then
    printf 'joint_candidate_writer_sha256='; sha256sum "$build_dir/joint_candidate.nc" | cut -d' ' -f1
  fi
  cat "$build_dir/executable.sha256"
} | tee "$run_root/receipt.txt"
printf 'receipt=%s\n' "$run_root/receipt.txt"
exit "$run_status"
