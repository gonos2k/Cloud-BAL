#!/usr/bin/env bash
set -euo pipefail

run_logged_command() {
  local output_log=$1
  local -a pipeline_status
  shift

  "$@" 2>&1 | tee "$output_log"
  pipeline_status=("${PIPESTATUS[@]}")
  if (( pipeline_status[1] != 0 )); then
    printf 'preflight output capture failed: tee exit=%d\n' "${pipeline_status[1]}" >&2
    return 125
  fi
  return "${pipeline_status[0]}"
}

if [[ ${BASH_SOURCE[0]} != "$0" ]]; then
  return 0
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=${CLOUD_BAL_WORKSPACE_ROOT:-/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50}
scratch_root=${CLOUD_BAL_TEST_SCRATCH_ROOT:-/var/tmp}
run_root=$(mktemp -d "$scratch_root/cloud_bal_pr65_observation_preflight.XXXXXX")
printf 'PR65 observation preflight directory: %s\n' "$run_root"

. "$repo_root/tests/intel_toolchain.sh"
profile_flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
nf_config=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config
netcdf_fortran_lib=$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a
netcdf_c_lib=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a
verify_hash() {
  local path=$1 expected=$2 actual
  test -f "$path" && test ! -L "$path"
  actual=$(sha256sum "$path" | cut -d' ' -f1)
  if [[ $actual != "$expected" ]]; then
    printf 'input hash mismatch: %s expected=%s actual=%s\n' "$path" "$expected" "$actual" >&2
    return 1
  fi
}
verify_hash "$nf_config" e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5
verify_hash "$netcdf_fortran_lib" f610d7ebedf48d17023e9b8377d74d93542bde40d091ec7a5518bb30d17c8a39
verify_hash "$netcdf_c_lib" f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288
read -r -a nf_fflags <<<"$("$nf_config" --fflags)"
read -r -a nf_flibs <<<"$("$nf_config" --flibs)"

IFS=$'\t' read -r _ valid_time _ _ fua fua_hash fsf fsf_hash lw3 lw3_hash vrz vrz_hash vrt vrt_hash \
  < <(sed -n '2p' "$repo_root/tests/qbal_real_cases_20260816.tsv")
valid_epoch=$(date -u -d "$valid_time" +%s)
static_file=$workspace_root/ANAL/NE57/DABA/static.nest7grid
static_hash=384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b
inputs=("$workspace_root/$fua" "$workspace_root/$fsf" "$workspace_root/$lw3" \
  "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file")
expected_hashes=("$fua_hash" "$fsf_hash" "$lw3_hash" "$vrz_hash" "$vrt_hash" "$static_hash")
for index in "${!inputs[@]}"; do verify_hash "${inputs[$index]}" "${expected_hashes[$index]}"; done

cd "$run_root"
sources=(cloud_bal_state cloud_bal_grid_geometry cloud_bal_column_physics \
  cloud_bal_balance_operator cloud_bal_pipeline cloud_bal_real_netcdf cloud_bal_pressure_analysis)
source_files=()
for source in "${sources[@]}"; do source_files+=("$repo_root/src/common/$source.f90"); done
program_source=$repo_root/tests/pr65_observation_joint_preflight.f90
source_files+=("$program_source")
profile_files=("$repo_root/tests/intel_toolchain.sh" "$repo_root/tests/run_pr65_observation_joint_preflight.sh" \
  "$repo_root/tests/qbal_real_cases_20260816.tsv" "$cloud_bal_setvars" "$CLOUD_BAL_FC" \
  "$cloud_bal_imf" "$cloud_bal_intlc" "$nf_config" "$netcdf_fortran_lib" "$netcdf_c_lib")
sha256sum "${source_files[@]}" > source_prebuild.sha256
sha256sum "${inputs[@]}" > inputs_prebuild.sha256
sha256sum "${profile_files[@]}" > profile_prebuild.sha256
record_command() { printf '%q ' "$@" >> commands.txt; printf '\n' >> commands.txt; }
record_command "$CLOUD_BAL_FC" --version
objects=()
for source in "${sources[@]}"; do
  object="$run_root/$source.o"
  record_command "$CLOUD_BAL_FC" -c "${profile_flags[@]}" -module "$run_root" -I "$run_root" \
    "${nf_fflags[@]}" "$repo_root/src/common/$source.f90" -o "$object"
  "$CLOUD_BAL_FC" -c "${profile_flags[@]}" -module "$run_root" -I "$run_root" \
    "${nf_fflags[@]}" "$repo_root/src/common/$source.f90" -o "$object"
  objects+=("$object")
done
record_command "$CLOUD_BAL_FC" "${profile_flags[@]}" -module "$run_root" -I "$run_root" \
  "${nf_fflags[@]}" "$program_source" "${objects[@]}" "${nf_flibs[@]}" \
  -o "$run_root/pr65_observation_joint_preflight"
"$CLOUD_BAL_FC" "${profile_flags[@]}" -module "$run_root" -I "$run_root" \
  "${nf_fflags[@]}" "$program_source" "${objects[@]}" "${nf_flibs[@]}" \
  -o "$run_root/pr65_observation_joint_preflight"
sha256sum "${source_files[@]}" > source_postbuild.sha256
sha256sum "${inputs[@]}" > inputs_postbuild.sha256
sha256sum "${profile_files[@]}" > profile_postbuild.sha256
cmp source_prebuild.sha256 source_postbuild.sha256
cmp inputs_prebuild.sha256 inputs_postbuild.sha256
cmp profile_prebuild.sha256 profile_postbuild.sha256

printf 'compiler=%s\ncompiler_version=%s\ncompiler_sha256=%s\nprofile=O0\n' \
  "$CLOUD_BAL_FC" "$cloud_bal_fc_version" "$cloud_bal_fc_sha256" > toolchain.txt
{
  printf 'netcdf_config=%s\n' "$nf_config"
  printf 'netcdf_fortran_archive=%s\n' "$netcdf_fortran_lib"
  printf 'netcdf_c_archive=%s\n' "$netcdf_c_lib"
  printf 'profile_flags='; printf '%s ' "${profile_flags[@]}"; printf '\n'
  printf 'netcdf_fortran_flags='; printf '%s ' "${nf_fflags[@]}"; printf '\n'
  printf 'netcdf_link_flags='; printf '%s ' "${nf_flibs[@]}"; printf '\n'
} >> toolchain.txt
record_command "$repo_root/tests/run_pr65_observation_joint_preflight.sh"
record_command "$nf_config" --fflags
record_command "$nf_config" --flibs
cat toolchain.txt
sha256sum "${inputs[@]}"
sha256sum "${source_files[@]}"
sha256sum "${objects[@]}" > objects_pre_run.sha256
sha256sum "$run_root/pr65_observation_joint_preflight" > executable_pre_run.sha256
record_command "$run_root/pr65_observation_joint_preflight" \
  "${inputs[0]}" "${inputs[1]}" "${inputs[2]}" "${inputs[3]}" "${inputs[4]}" \
  "$static_file" "$valid_epoch"
if run_logged_command preflight.log \
  "$run_root/pr65_observation_joint_preflight" \
  "${inputs[0]}" "${inputs[1]}" "${inputs[2]}" "${inputs[3]}" "${inputs[4]}" \
  "$static_file" "$valid_epoch"; then
  preflight_exit=0
else
  preflight_exit=$?
fi
sha256sum "${source_files[@]}" > source_postrun.sha256
sha256sum "${inputs[@]}" > inputs_postrun.sha256
sha256sum "${profile_files[@]}" > profile_postrun.sha256
sha256sum "${objects[@]}" > objects_postrun.sha256
sha256sum "$run_root/pr65_observation_joint_preflight" > executable_postrun.sha256
cmp source_prebuild.sha256 source_postrun.sha256
cmp inputs_prebuild.sha256 inputs_postrun.sha256
cmp profile_prebuild.sha256 profile_postrun.sha256
cmp objects_pre_run.sha256 objects_postrun.sha256
cmp executable_pre_run.sha256 executable_postrun.sha256
python3 - "$run_root" "$preflight_exit" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
preflight_exit = int(sys.argv[2])

def manifest(path):
    rows = []
    for line in (root / path).read_text().splitlines():
        digest, file_path = line.split(maxsplit=1)
        rows.append({"path": file_path.lstrip("*"), "sha256": digest})
    return rows

def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

receipt = {
    "status": "BLOCKED" if preflight_exit == 0 else "PREFLIGHT_ERROR",
    "scope": "actual NE57 retained-observation producer stage plus one-column Phi research postanalysis; no phase or wind admission",
    "preflight_exit": preflight_exit,
    "run_directory": str(root),
    "compiler": {
        "path": Path(root / "toolchain.txt").read_text().splitlines()[0].split("=", 1)[1],
        "version": Path(root / "toolchain.txt").read_text().splitlines()[1].split("=", 1)[1],
        "sha256": Path(root / "toolchain.txt").read_text().splitlines()[2].split("=", 1)[1],
        "profile": "O0 pinned Cloud-BAL Intel profile",
    },
    "source_prebuild": manifest("source_prebuild.sha256"),
    "source_postbuild": manifest("source_postbuild.sha256"),
    "source_postrun": manifest("source_postrun.sha256"),
    "actual_inputs_prebuild": manifest("inputs_prebuild.sha256"),
    "actual_inputs_postbuild": manifest("inputs_postbuild.sha256"),
    "actual_inputs_postrun": manifest("inputs_postrun.sha256"),
    "toolchain_and_runner_prebuild": manifest("profile_prebuild.sha256"),
    "toolchain_and_runner_postrun": manifest("profile_postrun.sha256"),
    "objects_pre_run": manifest("objects_pre_run.sha256"),
    "objects_postrun": manifest("objects_postrun.sha256"),
    "executable_sha256_pre_run": manifest("executable_pre_run.sha256"),
    "executable_sha256_postrun": manifest("executable_postrun.sha256"),
    "toolchain_flags": (root / "toolchain.txt").read_text(),
    "commands": (root / "commands.txt").read_text().splitlines(),
    "preflight_log_sha256": file_hash(root / "preflight.log"),
}
# Archive identities are already listed as pinned entries in the toolchain/profile
# manifest; retain their manifest rows explicitly in the receipt.
receipt["netcdf_and_intel_runtime_inputs"] = [
    row for row in receipt["toolchain_and_runner_prebuild"]
    if any(name in row["path"] for name in ("nf-config", "libnetcdff.a", "libnetcdf.a", "libimf.so", "libintlc.so"))
]
receipt["runtime_dependency_scope"] = (
    "partial: receipt hashes selected Intel/NetCDF configuration and libraries; "
    "it is not a complete process loader/runtime dependency closure"
)
(root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
PY
exit "$preflight_exit"
