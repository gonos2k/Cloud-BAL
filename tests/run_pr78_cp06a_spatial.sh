#!/usr/bin/env bash
# Run the bounded retained-input CP06-A spatial producer with pinned Intel.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(realpath -e "${CLOUD_BAL_WORKSPACE_ROOT:-$repo_root/../../..}")
receipt_tool=$repo_root/tests/pr78_cp06a_spatial_receipt.py
run_root=$(mktemp -d "${PR78_CP06A_RUN_PREFIX:-/var/tmp/pr78_cp06a_spatial}.XXXXXX")
printf 'run_root=%s\n' "$run_root"

python3 "$receipt_tool" "$workspace_root" "$repo_root" "$run_root/inputs.json"
spec_path=$repo_root/docs/CP06_A_BACKGROUND_PRIOR_V2_SPEC_20261012.md
cp "$spec_path" "$run_root/experiment_spec.md"
spec_sha=$(sha256sum "$run_root/experiment_spec.md" | cut -d' ' -f1)
python3 - "$run_root/inputs.json" "$spec_path" "$spec_sha" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
receipt_path, spec_path, spec_sha = sys.argv[1:]
receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
receipt["experiment_spec"] = str(Path(spec_path).resolve())
receipt["experiment_spec_sha256"] = spec_sha
Path(receipt_path).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
PY
mapfile -t driver_args < <(python3 - "$run_root/inputs.json" <<'PY'
import json
import sys
for item in json.load(open(sys.argv[1], encoding="utf-8"))["driver_arguments"]:
    print(item)
PY
)

. "$repo_root/tests/intel_toolchain.sh"
nf_config=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config
netcdf_fortran_lib=$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a
netcdf_c_lib=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a
[[ $(sha256sum "$nf_config" | cut -d' ' -f1) == \
  e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5 ]]
[[ $(sha256sum "$netcdf_fortran_lib" | cut -d' ' -f1) == \
  f610d7ebedf48d17023e9b8377d74d93542bde40d091ec7a5518bb30d17c8a39 ]]
[[ $(sha256sum "$netcdf_c_lib" | cut -d' ' -f1) == \
  f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288 ]]
read -r -a nf_fflags <<<"$($nf_config --fflags)"
read -r -a nf_flibs <<<"$($nf_config --flibs)"

source_files=(
  "$repo_root/src/common/cloud_bal_state.f90"
  "$repo_root/src/common/cloud_bal_grid_geometry.f90"
  "$repo_root/src/common/cloud_bal_column_physics.f90"
  "$repo_root/src/common/cloud_bal_balance_operator.f90"
  "$repo_root/src/common/cloud_bal_pipeline.f90"
  "$repo_root/src/common/cloud_bal_real_netcdf.f90"
  "$repo_root/tests/pr78_cp06a_spatial.f90"
)
bound_files=("${source_files[@]}" "$repo_root/tests/intel_toolchain.sh" \
  "$repo_root/tests/run_pr78_cp06a_spatial.sh" "$receipt_tool" "$nf_config" \
  "$netcdf_fortran_lib" "$netcdf_c_lib" "$cloud_bal_imf" "$cloud_bal_intlc")
sha256sum "${bound_files[@]}" > "$run_root/source_pre.sha256"
printf '%s  %s\n' "$spec_sha" "$spec_path" > "$run_root/spec_pre.sha256"
for profile in O0 O2; do
  build_root=$run_root/$profile
  mkdir -p "$build_root"
  cd "$build_root"
  if [[ $profile == O0 ]]; then
    flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  else
    flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  {
    printf 'profile=%s\n' "$profile"
    printf 'compiler=%s\n' "$CLOUD_BAL_FC"
    printf 'compiler_version=%s\n' "$cloud_bal_fc_version"
    printf 'compiler_sha256=%s\n' "$cloud_bal_fc_sha256"
    printf 'nf_config=%s\n' "$nf_config"
    printf 'flags=%s\n' "${flags[*]}"
    sha256sum "$repo_root/tests/intel_toolchain.sh" "$repo_root/tests/run_pr78_cp06a_spatial.sh" \
      "$repo_root/tests/pr78_cp06a_spatial_receipt.py" "$nf_config" \
      "$netcdf_fortran_lib" "$netcdf_c_lib" "$spec_path" \
      "$cloud_bal_imf" "$cloud_bal_intlc" "${source_files[@]}"
  } > "$build_root/build_provenance.txt"
  compile_command=("$CLOUD_BAL_FC" "${flags[@]}" -module "$build_root" -I "$build_root" \
    "${nf_fflags[@]}" "${source_files[@]}" "${nf_flibs[@]}" \
    -o "$build_root/pr78_cp06a_spatial")
  printf 'compile_command=' >> "$build_root/build_provenance.txt"
  printf '%q ' "${compile_command[@]}" >> "$build_root/build_provenance.txt"
  printf '\n' >> "$build_root/build_provenance.txt"
  if ! "${compile_command[@]}" > "$build_root/compile.log" 2>&1; then
    cat "$build_root/compile.log" >&2
    exit 2
  fi
  sha256sum "$build_root/pr78_cp06a_spatial" > "$build_root/executable.sha256"
  "$build_root/pr78_cp06a_spatial" "${driver_args[@]}" "$build_root" preflight \
    > "$build_root/preflight.log" 2>&1
  sha256sum "$build_root/pre_candidate_support.bin" > "$build_root/pre_candidate_support.sha256"
  "$build_root/pr78_cp06a_spatial" "${driver_args[@]}" "$build_root" run \
    > "$build_root/run.log" 2>&1
  cat "$build_root/run.log"
done
sha256sum "${bound_files[@]}" > "$run_root/source_post.sha256"
if ! diff -u "$run_root/source_pre.sha256" "$run_root/source_post.sha256"; then
  printf 'source changed during CP06-A O0/O2 run\n' >&2
  exit 2
fi
printf '%s  %s\n' "$spec_sha" "$spec_path" > "$run_root/spec_post.sha256"
if ! diff -u "$run_root/spec_pre.sha256" "$run_root/spec_post.sha256"; then
  printf 'CP06-A v2 spec changed during run\n' >&2
  exit 2
fi
python3 "$receipt_tool" "$workspace_root" "$repo_root" "$run_root/unused.json" \
  --verify-run "$run_root"
printf 'input_receipt=%s\n' "$run_root/inputs.json"
printf 'O0_run=%s\n' "$run_root/O0/run.log"
printf 'O2_run=%s\n' "$run_root/O2/run.log"
