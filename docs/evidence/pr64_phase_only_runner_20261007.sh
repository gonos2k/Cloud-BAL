#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=${CLOUD_BAL_WORKSPACE_ROOT:-/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50}
scratch_root=${CLOUD_BAL_TEST_SCRATCH_ROOT:-/var/tmp}
mkdir -p "$scratch_root"
run_root=$(mktemp -d "$scratch_root/cloud_bal_pr64_actual_phase.XXXXXX")
printf 'PR64 actual-data run directory: %s\n' "$run_root"

. "$repo_root/tests/intel_toolchain.sh"
profile=${PR64_PROFILE:-O0}
case "$profile" in
  O0) profile_flags=("${CLOUD_BAL_FREE_FLAGS[@]}");;
  O2) profile_flags=("${CLOUD_BAL_REPRO_FLAGS[@]}");;
  *) printf 'unsupported PR64_PROFILE: %s (expected O0 or O2)\n' "$profile" >&2; exit 2;;
esac
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
read -r -a nf_fflags <<<"$($nf_config --fflags)"
read -r -a nf_flibs <<<"$($nf_config --flibs)"
{
  printf 'compiler=%s\n' "$CLOUD_BAL_FC"
  printf 'compiler_version=%s\n' "$cloud_bal_fc_version"
  printf 'compiler_sha256=%s\n' "$cloud_bal_fc_sha256"
  printf 'profile=%s\n' "$profile"
  printf 'profile_flags='; printf '%s ' "${profile_flags[@]}"; printf '\n'
  printf 'nf_config=%s\n' "$nf_config"
  printf 'netcdf_fortran_archive=%s\n' "$netcdf_fortran_lib"
  printf 'netcdf_c_archive=%s\n' "$netcdf_c_lib"
  printf 'netcdf_fflags='; printf '%s ' "${nf_fflags[@]}"; printf '\n'
  printf 'netcdf_flibs='; printf '%s ' "${nf_flibs[@]}"; printf '\n'
  printf 'build_recipe=tests/run_pr64_actual_phase_candidate.sh\n'
} > "$run_root/toolchain.txt"

cd "$run_root"
sources=(
  cloud_bal_state
  cloud_bal_grid_geometry
  cloud_bal_column_physics
  cloud_bal_balance_operator
  cloud_bal_pipeline
  cloud_bal_real_netcdf
  cloud_bal_pressure_analysis
)
source_files=()
for source in "${sources[@]}"; do source_files+=("$repo_root/src/common/$source.f90"); done
program_source=$repo_root/tests/test_pr64_actual_phase_candidate.f90
source_files+=("$program_source")
sha256sum "${source_files[@]}" > "$run_root/source_prebuild.sha256"
runner_source=$repo_root/tests/run_pr64_actual_phase_candidate.sh
runner_prebuild_hash=$(sha256sum "$runner_source" | cut -d' ' -f1)
reader_source=$repo_root/tests/check_physical_contract_shadow.py
reader_pre_run_hash=$(sha256sum "$reader_source" | cut -d' ' -f1)
objects=()
for source in "${sources[@]}"; do
  object="$run_root/$source.o"
  "$CLOUD_BAL_FC" -c "${profile_flags[@]}" -module "$run_root" -I "$run_root" \
    "${nf_fflags[@]}" "$repo_root/src/common/$source.f90" -o "$object"
  objects+=("$object")
done
"$CLOUD_BAL_FC" "${profile_flags[@]}" -module "$run_root" -I "$run_root" \
  "${nf_fflags[@]}" "$program_source" \
  "${objects[@]}" "${nf_flibs[@]}" -o "$run_root/test_pr64_actual_phase_candidate"
sha256sum "${source_files[@]}" > "$run_root/source_postbuild.sha256"
source_guard_status=0
cmp -s "$run_root/source_prebuild.sha256" "$run_root/source_postbuild.sha256" || source_guard_status=1
runner_postbuild_hash=$(sha256sum "$runner_source" | cut -d' ' -f1)
[[ $runner_prebuild_hash == "$runner_postbuild_hash" ]] || source_guard_status=1
sha256sum "${objects[@]}" > "$run_root/objects_pre_run.sha256"
sha256sum "$run_root/test_pr64_actual_phase_candidate" > "$run_root/executable_pre_run.sha256"

IFS=$'\t' read -r _ valid_time background_time laps_stamp fua fua_hash fsf fsf_hash \
  lw3 lw3_hash vrz vrz_hash vrt vrt_hash < <(sed -n '2p' "$repo_root/tests/qbal_real_cases_20260816.tsv")
static_file=$workspace_root/ANAL/NE57/DABA/static.nest7grid
static_hash=384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b
valid_epoch=$(date -u -d "$valid_time" +%s)
inputs=("$workspace_root/$fua" "$workspace_root/$fsf" "$workspace_root/$lw3" \
  "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file")
expected_hashes=("$fua_hash" "$fsf_hash" "$lw3_hash" "$vrz_hash" "$vrt_hash" "$static_hash")
for index in "${!inputs[@]}"; do verify_hash "${inputs[$index]}" "${expected_hashes[$index]}"; done
set +e
"$run_root/test_pr64_actual_phase_candidate" \
  "$workspace_root/$fua" "$workspace_root/$fsf" "$workspace_root/$lw3" \
  "$workspace_root/$vrz" "$workspace_root/$vrt" "$static_file" \
  "$valid_epoch" "$run_root/actual-ne57-phase-shadow.nc" \
  > "$run_root/candidate.log" 2>&1
candidate_status=$?
set -e
cat "$run_root/candidate.log"
postrun_status=0
for index in "${!inputs[@]}"; do
  verify_hash "${inputs[$index]}" "${expected_hashes[$index]}" || postrun_status=1
done
if [[ -e "$run_root/actual-ne57-phase-shadow.nc" ]]; then
  set +e
  python3 "$repo_root/tests/check_physical_contract_shadow.py" \
    "$run_root/actual-ne57-phase-shadow.nc" > "$run_root/readback.log" 2>&1
  readback_status=$?
  set -e
  sha256sum "$run_root/actual-ne57-phase-shadow.nc" > "$run_root/artifact.sha256"
  artifact_hash=$(cut -d' ' -f1 "$run_root/artifact.sha256")
else
  readback_status=null
  artifact_hash=null
fi
sha256sum "${source_files[@]}" > "$run_root/source_postrun.sha256"
cmp -s "$run_root/source_prebuild.sha256" "$run_root/source_postrun.sha256" || source_guard_status=1
runner_postrun_hash=$(sha256sum "$runner_source" | cut -d' ' -f1)
[[ $runner_prebuild_hash == "$runner_postrun_hash" ]] || source_guard_status=1
reader_postrun_hash=$(sha256sum "$reader_source" | cut -d' ' -f1)
[[ $reader_pre_run_hash == "$reader_postrun_hash" ]] || source_guard_status=1
sha256sum "${objects[@]}" > "$run_root/objects_postrun.sha256"
cmp -s "$run_root/objects_pre_run.sha256" "$run_root/objects_postrun.sha256" || source_guard_status=1
sha256sum "$run_root/test_pr64_actual_phase_candidate" > "$run_root/executable_postrun.sha256"
cmp -s "$run_root/executable_pre_run.sha256" "$run_root/executable_postrun.sha256" || source_guard_status=1
object_hashes=()
for object in "${objects[@]}"; do object_hashes+=("$(sha256sum "$object" | cut -d' ' -f1)"); done
python3 - "$run_root" "$CLOUD_BAL_FC" "$cloud_bal_fc_version" "$cloud_bal_fc_sha256" \
  "$candidate_status" "$postrun_status" "$readback_status" "$artifact_hash" \
  "$workspace_root/$fua" "$fua_hash" "$workspace_root/$fsf" "$fsf_hash" \
  "$workspace_root/$lw3" "$lw3_hash" "$workspace_root/$vrz" "$vrz_hash" \
  "$workspace_root/$vrt" "$vrt_hash" "$static_file" "$static_hash" \
  "${source_files[@]}" "--objects--" "${objects[@]}" "--object-hashes--" "${object_hashes[@]}" \
  "$source_guard_status" "$profile" "$runner_source" "$runner_prebuild_hash" \
  "$nf_config" "$netcdf_fortran_lib" "$netcdf_c_lib" "$reader_source" \
  "$reader_pre_run_hash" "$reader_postrun_hash" <<'PY'
import json
import sys
from pathlib import Path

root=Path(sys.argv[1])
compiler,version,compiler_hash=sys.argv[2:5]
candidate_status,postrun_status=map(int,sys.argv[5:7])
readback_status=None if sys.argv[7]=='null' else int(sys.argv[7])
artifact_hash=None if sys.argv[8]=='null' else sys.argv[8]
inputs=[]
for i in range(9,21,2):
    inputs.append({'path':sys.argv[i],'sha256':sys.argv[i+1]})
rest=sys.argv[21:]
source_guard_status=int(rest[-10])
profile,runner_path,runner_hash,nf_config,netcdf_fortran_lib,netcdf_c_lib,reader_source,reader_pre_hash,reader_post_hash=rest[-9:]
rest=rest[:-10]
sources=[]; objects=[]; hashes=[]; section='sources'
for item in rest:
    if item=='--objects--': section='objects'; continue
    if item=='--object-hashes--': section='hashes'; continue
    {'sources':sources,'objects':objects,'hashes':hashes}[section].append(item)
objects=[{'path':path,'sha256':hashes[i]} for i,path in enumerate(objects)]
receipt={
  'status':'PASS_SCOPED' if candidate_status==0 and postrun_status==0 and readback_status==0 and source_guard_status==0 else 'FAIL_OPEN',
  'scope':'actual NE57 2026-08-16 12 UTC phase-only contract candidate',
  'candidate_process_exit':candidate_status,'input_postrun_hash_guard_exit':postrun_status,
  'independent_readback_exit':readback_status,'source_prepost_hash_guard_exit':source_guard_status,
  'artifact_sha256':artifact_hash,
  'valid_time_epoch':1786881600,'grid':[235,283,22],
  'sample_cell_fortran_ijk':[143,191,9],
  'source_and_boundary':'predeclared zero; not authenticated physical authority',
  'phase_policy':'single-cell liquid saturation adjustment to RH=1.0',
  'observations':'radar reflectivity and LOS plus categorical cloud observations withheld in the scoped phase-only input using canonical missing radar encoding; all physical background fields retained',
  'wind_driver':'UNAVAILABLE','downstream_wps_real_handoff':'UNAVAILABLE',
  'inputs':inputs,'static_grid_sha256':inputs[-1]['sha256'],
  'compiler':{'path':compiler,'version':version,'sha256':compiler_hash,
              'profile':profile,'flags':(root/'toolchain.txt').read_text().split('profile_flags=',1)[1].splitlines()[0]},
  'netcdf':{'nf_config_path':nf_config,
            'nf_config_sha256':__import__('hashlib').sha256(Path(nf_config).read_bytes()).hexdigest(),
            'netcdf_fortran_archive_path':netcdf_fortran_lib,
            'netcdf_fortran_archive_sha256':__import__('hashlib').sha256(Path(netcdf_fortran_lib).read_bytes()).hexdigest(),
            'netcdf_c_archive_path':netcdf_c_lib,
            'netcdf_c_archive_sha256':__import__('hashlib').sha256(Path(netcdf_c_lib).read_bytes()).hexdigest()},
  'toolchain_recipe_sha256':__import__('hashlib').sha256((root/'toolchain.txt').read_bytes()).hexdigest(),
  'source_prebuild_manifest_sha256':__import__('hashlib').sha256((root/'source_prebuild.sha256').read_bytes()).hexdigest(),
  'source_postbuild_manifest_sha256':__import__('hashlib').sha256((root/'source_postbuild.sha256').read_bytes()).hexdigest(),
  'source_postrun_manifest_sha256':__import__('hashlib').sha256((root/'source_postrun.sha256').read_bytes()).hexdigest(),
  'runner_path':runner_path,'runner_sha256_prebuild':runner_hash,
  'runner_sha256_postrun':__import__('hashlib').sha256(Path(runner_path).read_bytes()).hexdigest(),
  'independent_reader_path':reader_source,'independent_reader_sha256_pre_run':reader_pre_hash,
  'independent_reader_sha256_post_run':reader_post_hash,
  'source_files':[{'path':path,'sha256':__import__('hashlib').sha256(Path(path).read_bytes()).hexdigest()} for path in sources],
  'objects':objects,
  'object_prepost_manifest_sha256':{'pre':__import__('hashlib').sha256((root/'objects_pre_run.sha256').read_bytes()).hexdigest(),
                                    'post':__import__('hashlib').sha256((root/'objects_postrun.sha256').read_bytes()).hexdigest()},
  'executable_prepost_sha256':{'pre':(root/'executable_pre_run.sha256').read_text().split()[0],
                               'post':(root/'executable_postrun.sha256').read_text().split()[0]},
  'executable_sha256':__import__('hashlib').sha256((root/'test_pr64_actual_phase_candidate').read_bytes()).hexdigest(),
}
(root/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
PY
if [[ $postrun_status != 0 ]]; then exit 3; fi
if [[ $source_guard_status != 0 ]]; then exit 4; fi
if [[ $candidate_status != 0 ]]; then exit "$candidate_status"; fi
if [[ $readback_status != 0 ]]; then exit "$readback_status"; fi
printf 'PR64 candidate evidence directory: %s\n' "$run_root"
