#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
artifact_root=/var/tmp/pr78_cp06a_spatial.V9LYrN
inputs_json=$artifact_root/inputs.json
coupled_nc=$artifact_root/O2/coupled.nc
spec_path=$repo_root/docs/CP06_A_FORCE_PRIOR_SPEC_20261012.md
spec_sha256=1b7bda6720da205dc312193c2bd864c0c9c8546ac44734541a570edca3e8a9aa
scratch_root=${CLOUD_BAL_TEST_SCRATCH_ROOT:-/var/tmp}
mkdir -p "$scratch_root"
run_root=$(mktemp -d "$scratch_root/pr80_force_retained.XXXXXX")
printf 'retained force-prior probe directory: %s\n' "$run_root"
. "$repo_root/tests/intel_toolchain.sh"

nf_config=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config
netcdf_fortran_lib=$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a
netcdf_c_lib=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a
[[ -f $inputs_json && -f $coupled_nc && -x $nf_config && -f $netcdf_fortran_lib && -f $netcdf_c_lib ]] || {
  printf 'pinned CP06-A input artifact or NetCDF library is unavailable\n' >&2
  exit 2
}
[[ -f $spec_path && $(sha256sum "$spec_path" | cut -d' ' -f1) == "$spec_sha256" ]] || {
  printf 'predeclared force-prior specification is missing or differs from its saved hash\n' >&2
  exit 2
}
read -r -a nf_fflags <<<"$("$nf_config" --fflags)"
read -r -a nf_flibs <<<"$("$nf_config" --flibs)"
mapfile -t driver_args < <(PR80_INPUTS_JSON="$inputs_json" python -c \
  'import json,os; print("\n".join(json.load(open(os.environ["PR80_INPUTS_JSON"]))["driver_arguments"]))')
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
cp "$repo_root/tests/pr80_force_retained.f90" "$repo_root/tests/run_pr80_force_retained.sh" \
  "$repo_root/tests/intel_toolchain.sh" "$source_dir/tests/"
cp "$spec_path" "$source_dir/docs/"
source_files=()
for name in "${source_names[@]}"; do source_files+=("$source_dir/src/common/$name.f90"); done
source_files+=("$source_dir/tests/pr80_force_retained.f90" "$source_dir/tests/run_pr80_force_retained.sh" \
  "$source_dir/tests/intel_toolchain.sh" "$source_dir/docs/$(basename "$spec_path")")
git -C "$repo_root" rev-parse HEAD > "$run_root/worktree_head.txt"
sha256sum "$repo_root/src/common/"*.f90 "$repo_root/tests/pr80_force_retained.f90" \
  > "$run_root/worktree_source_pre.sha256"
reader_input_files=("${driver_args[@]:0:12}")
input_files=("$inputs_json" "$coupled_nc" "$spec_path" "${reader_input_files[@]}")
sha256sum "${source_files[@]}" > "$run_root/source_pre.sha256"
sha256sum "${input_files[@]}" > "$run_root/input_pre.sha256"
cp "$inputs_json" "$run_root/inputs.json.archive"
cp "$coupled_nc" "$run_root/coupled.nc.archive"
cp "$spec_path" "$run_root/force_prior_spec.md.archive"
sha256sum "$run_root/inputs.json.archive" "$run_root/coupled.nc.archive" \
  "$run_root/force_prior_spec.md.archive" > "$run_root/archive.sha256"

run_profile() {
  local profile=$1
  local -n flags=$2
  local build_dir="$run_root/$profile"
  mkdir -p "$build_dir"
  printf 'profile=%s\ncompiler=%s\ncompiler_version=%s\ncompiler_sha256=%s\n' \
    "$profile" "$CLOUD_BAL_FC" "$("$CLOUD_BAL_FC" --version 2>&1 | sed -n '1p')" \
    "$(sha256sum "$CLOUD_BAL_FC" | cut -d' ' -f1)" > "$build_dir/profile.txt"
  printf 'netcdf_fortran_config=%s\nnetcdf_fortran_sha256=%s\nnetcdf_c_sha256=%s\n' \
    "$nf_config" "$(sha256sum "$netcdf_fortran_lib" | cut -d' ' -f1)" \
    "$(sha256sum "$netcdf_c_lib" | cut -d' ' -f1)" >> "$build_dir/profile.txt"
  local objects=()
  for name in "${source_names[@]}"; do
    local object="$build_dir/$name.o"
    "$CLOUD_BAL_FC" -c "${flags[@]}" -module "$build_dir" -I "$build_dir" \
      "${nf_fflags[@]}" "$source_dir/src/common/$name.f90" -o "$object" \
      >"$build_dir/$name.compile.log" 2>&1
    objects+=("$object")
  done
  "$CLOUD_BAL_FC" "${flags[@]}" -module "$build_dir" -I "$build_dir" \
    "${nf_fflags[@]}" "$source_dir/tests/pr80_force_retained.f90" \
    "${objects[@]}" "${nf_flibs[@]}" -o "$build_dir/pr80-force-retained" \
    >"$build_dir/link.log" 2>&1
  sha256sum "$build_dir/pr80-force-retained" > "$build_dir/executable.sha256"
  cp "$build_dir/pr80-force-retained" "$run_root/archive.$profile.exe"
  set +e
  "$build_dir/pr80-force-retained" "${driver_args[@]}" "$coupled_nc" \
    "$build_dir/retained_wind_v1.bin" >"$build_dir/run.log" 2>&1
  local rc=$?
  set -e
  printf 'exit_status=%s\n' "$rc" > "$build_dir/exit_status.txt"
  cat "$build_dir/run.log"
  [[ $rc == 0 ]] || return "$rc"
  cp "$build_dir/retained_wind_v1.bin.summary.txt" "$run_root/$profile.diagnostics.txt"
  if [[ -f $build_dir/retained_wind_v1.bin ]]; then
    cp "$build_dir/retained_wind_v1.bin" "$run_root/archive.$profile.retained_wind_v1.bin"
    sha256sum "$build_dir/retained_wind_v1.bin" > "$build_dir/wind_artifact.sha256"
    [[ -f $build_dir/retained_wind_v1.bin.pipeline.nc ]] || {
      printf 'full pipeline writer did not create its diagnostic NetCDF\n' >&2
      return 1
    }
    sha256sum "$build_dir/retained_wind_v1.bin.pipeline.nc" > "$build_dir/pipeline_writer_artifact.sha256"
  fi
}

run_profile O2 CLOUD_BAL_REPRO_FLAGS
run_profile O0 CLOUD_BAL_FREE_FLAGS
sha256sum "${source_files[@]}" > "$run_root/source_post.sha256"
sha256sum "${input_files[@]}" > "$run_root/input_post.sha256"
sha256sum "$repo_root/src/common/"*.f90 "$repo_root/tests/pr80_force_retained.f90" \
  > "$run_root/worktree_source_post.sha256"
cmp "$run_root/source_pre.sha256" "$run_root/source_post.sha256"
cmp "$run_root/input_pre.sha256" "$run_root/input_post.sha256"
cmp "$run_root/archive.sha256" <(sha256sum "$run_root/inputs.json.archive" \
  "$run_root/coupled.nc.archive" "$run_root/force_prior_spec.md.archive")

{
  printf 'retained_candidate=%s\n' "$coupled_nc"
  printf 'source_snapshot_identity=pre_post_hashes_equal\n'
  printf 'worktree_head='; cat "$run_root/worktree_head.txt"
  if cmp -s "$run_root/worktree_source_pre.sha256" "$run_root/worktree_source_post.sha256"; then
    printf 'worktree_source_changed_during_run=F\n'
  else
    printf 'worktree_source_changed_during_run=T\n'
  fi
  printf 'artifact_scope=wind_component_probe_plus_full_producer_writer_roundtrip_diagnostic_only\n'
  printf 'science_authority=NONE\n'
  for profile in O2 O0; do
    printf '%s_exit_status=' "$profile"; cat "$run_root/$profile/exit_status.txt"
    printf '%s_executable_sha256=' "$profile"; cat "$run_root/$profile/executable.sha256"
    printf '%s_pipeline_writer_sha256=' "$profile"; cat "$run_root/$profile/pipeline_writer_artifact.sha256"
  done
} | tee "$run_root/receipt.txt"
printf 'receipt=%s\n' "$run_root/receipt.txt"
