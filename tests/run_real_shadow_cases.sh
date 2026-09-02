#!/usr/bin/env bash
# Publish every prepared real-data case as one immutable Intel SHADOW generation.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(cd "$repo_root/.." && pwd)
. "$repo_root/tests/output_safety.sh"
manifest=$repo_root/tests/qbal_real_cases_20260816.tsv
publication_root=$(cloud_bal_output_under \
  "${1:-$repo_root/scratch/publications/real_shadow}" \
  "$repo_root/scratch/publications")
mkdir -p "$repo_root/scratch"
build_root=$(mktemp -d "$repo_root/scratch/real_shadow_build.XXXXXX")
static_file=$workspace_root/ANAL/NE57/DABA/static.nest7grid
nf_config=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config
expected_nf_config_sha=e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5
expected_static_sha=384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b
netcdff_archive=$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a
netcdf_archive=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a
expected_netcdff_sha=f610d7ebedf48d17023e9b8377d74d93542bde40d091ec7a5518bb30d17c8a39
expected_netcdf_sha=f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288

. "$repo_root/tests/intel_toolchain.sh"
"$repo_root/tests/run_real_input_inventory.sh"

cloud_bal_require_clean_source
source_commit=$(git -C "$repo_root" rev-parse HEAD)

verify_input() {
  local path=$1 expected=$2 actual full lexical resolved
  full=$workspace_root/$path
  lexical=$(realpath -ms "$full")
  resolved=$(realpath -e "$full")
  [[ $resolved == "$lexical" ]] || {
    printf 'input path contains a symlink: %s\n' "$path" >&2
    exit 2
  }
  [[ -f $full && ! -L $full ]] || {
    printf 'input is not a regular non-symlink file: %s\n' "$path" >&2
    exit 2
  }
  actual=$(sha256sum "$full" | cut -d' ' -f1)
  [[ $actual == "$expected" ]] || {
    printf 'input changed or hash mismatch: %s\n' "$path" >&2
    exit 2
  }
}

mkdir -p "$build_root"
build_receipt=$build_root/build_provenance.tsv
: > "$build_receipt"

pin_build_file() {
  local label=$1 path expected=${3:-} actual
  path=$(realpath "$2")
  actual=$(sha256sum "$path" | cut -d' ' -f1)
  if [[ -n $expected && $actual != "$expected" ]]; then
    printf 'unpinned build input: %s\n' "$path" >&2
    exit 2
  fi
  printf '%s\t%s\t%s\n' "$label" "$path" "$actual" >> "$build_receipt"
}

verify_build_files() {
  local label path expected actual
  while IFS=$'\t' read -r label path expected; do
    actual=$(sha256sum "$path" | cut -d' ' -f1)
    [[ $actual == "$expected" ]] || {
      printf 'build input changed during run: %s\n' "$path" >&2
      exit 2
    }
  done < "$build_receipt"
}

pin_build_file compiler "$CLOUD_BAL_FC" "$cloud_bal_fc_sha256"
pin_build_file setvars "$cloud_bal_setvars" "$cloud_bal_expected_setvars_sha256"
pin_build_file nf_config "$nf_config" "$expected_nf_config_sha"
pin_build_file static_grid "$static_file" "$expected_static_sha"
pin_build_file link_netcdff "$netcdff_archive" "$expected_netcdff_sha"
pin_build_file link_netcdf "$netcdf_archive" "$expected_netcdf_sha"
verify_build_files

nf_fflags_text=$($nf_config --fflags)
nf_flibs_text=$($nf_config --flibs)
read -r -a nf_fflags <<<"$nf_fflags_text"
read -r -a nf_flibs <<<"$nf_flibs_text"
"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" \
  -module "$build_root" -I "$build_root" "${nf_fflags[@]}" \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/src/common/cloud_bal_column_physics.f90" \
  "$repo_root/src/common/cloud_bal_balance_operator.f90" \
  "$repo_root/src/common/cloud_bal_pipeline.f90" \
  "$repo_root/src/common/cloud_bal_real_netcdf.f90" \
  "$repo_root/tests/real_shadow_driver.f90" \
  "${nf_flibs[@]}" -o "$build_root/real_shadow_driver"
driver=$build_root/real_shadow_driver
ldd_output=$(ldd "$driver")
if [[ $ldd_output == *"not found"* ]]; then
  printf 'unresolved runtime dependency:\n%s\n' "$ldd_output" >&2
  exit 2
fi
pin_build_file driver "$driver"
runtime_index=0
while IFS= read -r runtime_path; do
  runtime_index=$((runtime_index + 1))
  pin_build_file "runtime_$runtime_index" "$runtime_path"
done < <(printf '%s\n' "$ldd_output" | awk '{for(i=1;i<=NF;i++) if ($i ~ /^\//) print $i}' | sort -u)
verify_build_files

expected_count=$(($(wc -l < "$manifest") - 1))
mapfile -t case_ids < <(tail -n +2 "$manifest" | cut -f1)
[[ ${#case_ids[@]} -eq $expected_count && $expected_count -gt 0 ]] || exit 2
products=(RUN_SUMMARY.json)
for case_id in "${case_ids[@]}"; do
  products+=("$case_id.nc" "$case_id.json" "$case_id.log")
done
last_epoch=$(date -u -d "$(tail -n 1 "$manifest" | cut -f2)" +%s)
transaction_id="radar-shadow-${case_ids[0]}-${case_ids[-1]}-${source_commit:0:12}"
transaction_id="$transaction_id-$(date -u +%Y%m%dT%H%M%S)-$$"
staging=$(python3 "$repo_root/tools/cloud_bal_transaction.py" begin \
  "$publication_root" "$transaction_id" "${products[@]}" \
  --source-commit "$source_commit" \
  --configuration "radar-only-shadow-ifx-2026-v3" \
  --valid-time "$last_epoch")
trap 'if [[ -d $staging ]]; then mv "$staging" "$staging.failed.$$"; fi' EXIT

case_count=0
hydrometeor_valid_count=0
rejected_count=0
while IFS=$'\t' read -r case_id valid_time background_time laps_stamp \
    fua fua_hash fsf fsf_hash lw3 lw3_hash vrz vrz_hash vrt vrt_hash; do
  [[ $case_id == case_id ]] && continue
  case_count=$((case_count + 1))
  epoch=$(date -u -d "$valid_time" +%s)
  diagnostic=$(python3 "$repo_root/tools/cloud_bal_transaction.py" resolve \
    "$publication_root" "$transaction_id" "$case_id.nc")
  report=$(python3 "$repo_root/tools/cloud_bal_transaction.py" resolve \
    "$publication_root" "$transaction_id" "$case_id.json")
  log=$(python3 "$repo_root/tools/cloud_bal_transaction.py" resolve \
    "$publication_root" "$transaction_id" "$case_id.log")
  temporary=$diagnostic.tmp.$$
  report_temporary=$report.tmp.$$

  printf 'CASE %s START\n' "$case_id"
  verify_input "$fua" "$fua_hash"
  verify_input "$fsf" "$fsf_hash"
  verify_input "$lw3" "$lw3_hash"
  verify_input "$vrz" "$vrz_hash"
  verify_input "$vrt" "$vrt_hash"
  verify_input "ANAL/NE57/DABA/static.nest7grid" "$expected_static_sha"
  set +e
  "$build_root/real_shadow_driver" \
    "$workspace_root/$fua" "$workspace_root/$fsf" \
    "$workspace_root/$lw3" "$workspace_root/$vrz" \
    "$workspace_root/$vrt" "$static_file" "$temporary" "$epoch" \
    >"$log" 2>&1
  driver_status=$?
  set -e
  case $driver_status in
    0) hydrometeor_valid_count=$((hydrometeor_valid_count + 1)) ;;
    3) rejected_count=$((rejected_count + 1)) ;;
    *)
      sed -n '1,160p' "$log" >&2
      printf 'CASE %s failed before a valid proposal was written (status %d)\n' \
        "$case_id" "$driver_status" >&2
      exit "$driver_status"
      ;;
  esac
  [[ -f $temporary ]] || {
    printf 'CASE %s did not write its diagnostic proposal\n' "$case_id" >&2
    exit 2
  }
  python3 "$repo_root/tools/validate_shadow_diagnostics.py" "$temporary" >/dev/null
  mv -f "$temporary" "$diagnostic"
  python3 "$repo_root/tools/validate_shadow_diagnostics.py" \
    "$diagnostic" --json "$report_temporary" >/dev/null
  mv -f "$report_temporary" "$report"
  verify_input "$fua" "$fua_hash"
  verify_input "$fsf" "$fsf_hash"
  verify_input "$lw3" "$lw3_hash"
  verify_input "$vrz" "$vrz_hash"
  verify_input "$vrt" "$vrt_hash"
  verify_input "ANAL/NE57/DABA/static.nest7grid" "$expected_static_sha"
  if [[ $driver_status -eq 0 ]]; then
    decision=HYDROMETEOR_ENGINEERING_VALID_WITH_TRAJECTORY_ASSUMPTION
  else
    decision=REJECTED
  fi
  printf 'CASE %s NUMERICALLY_VALID %s %s\n' \
    "$case_id" "$decision" "$diagnostic"
done < "$manifest"

[[ $case_count -eq $expected_count && $case_count -gt 0 ]] || {
  printf 'executed %d of %d manifest cases\n' "$case_count" "$expected_count" >&2
  exit 2
}
python3 - "$staging/RUN_SUMMARY.json" "$source_commit" "$manifest" \
  "$CLOUD_BAL_FC" "$cloud_bal_fc_version" "$nf_config" "$static_file" \
  "$driver" "${CLOUD_BAL_REPRO_FLAGS[*]}" "$nf_fflags_text" \
  "$nf_flibs_text" "$build_receipt" \
  "$case_count" "$hydrometeor_valid_count" "$rejected_count" <<'PY'
import csv
import hashlib
import json
import sys
from pathlib import Path

path, commit, manifest, compiler, compiler_version, nf_config, static_file, \
    driver, compiler_flags, nf_fflags, nf_flibs, build_receipt, \
    count, hydrometeor_valid, rejected = sys.argv[1:]

def sha256(value):
    digest = hashlib.sha256()
    with Path(value).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

with Path(manifest).open(newline="", encoding="utf-8") as stream:
    cases = list(csv.DictReader(stream, delimiter="\t"))
build_files = []
with Path(build_receipt).open(encoding="utf-8") as stream:
    for line in stream:
        label, value, expected = line.rstrip("\n").split("\t")
        resolved = Path(value).resolve()
        if sha256(resolved) != expected:
            raise SystemExit("build input changed: " + str(resolved))
        build_files.append({"label": label, "path": str(resolved), "sha256": expected})
summary = {
    "contract": "radar_only_shadow_ifx_2026_v3",
    "source_commit": commit,
    "source_tree_clean": True,
    "input_manifest": str(Path(manifest).resolve()),
    "input_manifest_sha256": sha256(manifest),
    "input_cases": cases,
    "compiler": str(Path(compiler).resolve()),
    "compiler_version": compiler_version,
    "compiler_sha256": sha256(compiler),
    "compiler_flags": compiler_flags,
    "netcdf_fortran_config": str(Path(nf_config).resolve()),
    "netcdf_fortran_config_sha256": sha256(nf_config),
    "netcdf_fortran_fflags": nf_fflags,
    "netcdf_fortran_flibs": nf_flibs,
    "driver": str(Path(driver).resolve()),
    "driver_sha256": sha256(driver),
    "build_files": build_files,
    "static_grid": str(Path(static_file).resolve()),
    "static_grid_sha256": sha256(static_file),
    "case_count": int(count),
    "hydrometeor_valid_count": int(hydrometeor_valid),
    "rejected_count": int(rejected),
    "trajectory_horizontal_frame": "INPUT_WIND_NATIVE_UNRESOLVED",
    "storm_motion_provenance": "NOT_AVAILABLE_ZERO_TRANSLATION_ASSUMPTION",
    "trajectory_science_assessed": False,
    "numerical_contract": "PASS",
    "science_assessed": False,
    "promotion_eligible": False,
}
Path(path).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
PY
"$repo_root/tests/run_real_input_inventory.sh"
verify_build_files
if [[ $(git -C "$repo_root" rev-parse HEAD) != "$source_commit" ]] || \
   [[ -n $(git -C "$repo_root" status --porcelain --untracked-files=normal) ]]; then
  printf 'source tree changed during the real-data run\n' >&2
  exit 2
fi
python3 "$repo_root/tools/cloud_bal_transaction.py" commit \
  "$publication_root" "$transaction_id" >/dev/null
current=$(cloud_bal_current_evidence "$publication_root" "$manifest")
printf 'REAL RADAR-ONLY ENGINEERING CONTRACT PASS: %d/%d cases, Intel ifx only\n' \
  "$case_count" "$case_count"
printf 'HYDROMETEOR ENGINEERING VALID_WITH_TRAJECTORY_ASSUMPTION %d/%d REJECTED %d/%d\n' \
  "$hydrometeor_valid_count" "$case_count" "$rejected_count" "$case_count"
printf 'DYNAMIC BALANCE NOT_AUTHORIZED %d/%d\n' "$case_count" "$case_count"
printf 'SCIENCE_UNASSESSED PROMOTION_BLOCKED\n'
printf 'HASH-VERIFIED GENERATION (TRUSTED SINGLE-USER MODEL) %s\n' "$current"
printf 'COOPERATIVE ATOMIC PUBLICATION SUCCESS\n'
