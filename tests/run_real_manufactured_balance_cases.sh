#!/usr/bin/env bash
# Exercise nonzero balance on the four pinned real NE57 geometries.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_lexical=$(realpath -ms "${CLOUD_BAL_WORKSPACE_ROOT:-$repo_root/..}")
workspace_root=$(realpath -e "$workspace_lexical")
[[ $workspace_root == "$workspace_lexical" ]] || {
  printf 'workspace root cannot contain a symlink: %s\n' "$workspace_lexical" >&2
  exit 2
}
. "$repo_root/tests/output_safety.sh"
. "$repo_root/tests/intel_toolchain.sh"

manifest=$repo_root/tests/qbal_real_manufactured_cases_20260816.tsv
expected_manifest_sha=f0340bb511febbdc29627ccd9c9344e4d47c08dbe9f3d345337c6399c200063a
publication_root=$(cloud_bal_output_under \
  "${1:-$repo_root/scratch/publications/real_manufactured_balance}" \
  "$repo_root/scratch/publications")
mkdir -p "$repo_root/scratch"
build_root=$(mktemp -d "$repo_root/scratch/real_manufactured_build.XXXXXX")
static_file=$workspace_root/ANAL/NE57/DABA/static.nest7grid
static_sha=384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b
nf_config=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config
expected_nf_config_sha=e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5
netcdff_archive=$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a
netcdf_archive=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a
expected_netcdff_sha=f610d7ebedf48d17023e9b8377d74d93542bde40d091ec7a5518bb30d17c8a39
expected_netcdf_sha=f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288

cloud_bal_require_clean_source
source_commit=$(git -C "$repo_root" rev-parse HEAD)
[[ $(sha256sum "$manifest" | cut -d' ' -f1) == "$expected_manifest_sha" ]] || {
  printf 'real-geometry case manifest is not the reviewed manifest\n' >&2
  exit 2
}
python3 - "$manifest" "$repo_root/tools/check_qbal_real_inputs.py" \
  "$workspace_root" <<'PY'
import csv
import hashlib
import importlib.util
import sys
from pathlib import Path

import netCDF4

manifest, checker_path, workspace = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("qbal_inputs", checker_path)
checker = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(checker)
with manifest.open(encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream, delimiter="\t"))
expected_ids = [f"20260816T{hour:02d}0000Z" for hour in range(12, 16)]
expected_times = [f"2026-08-16T{hour:02d}:00:00Z" for hour in range(12, 16)]
if [row["case_id"] for row in rows] != expected_ids:
    raise SystemExit("unexpected case IDs or ordering")
if [row["valid_time_utc"] for row in rows] != expected_times:
    raise SystemExit("unexpected case times or ordering")
path_fields = [name for name in rows[0] if name.endswith("_path")]
for row in rows:
    for name in path_fields:
        reason = checker.forbidden_reason(Path(row[name]))
        if reason is not None:
            raise SystemExit(f"forbidden {name}: {reason}")
    cycle_times = []
    for name in ("fua_path", "fsf_before_path", "fsf_center_path", "fsf_after_path"):
        with netCDF4.Dataset(workspace / row[name]) as dataset:
            cycle_times.append(float(dataset.variables["reftime"][0]))
    if len(set(cycle_times)) != 1 or cycle_times[0] != 1786831200.0:
        raise SystemExit("FUA/FSF model-cycle lineage mismatch")
PY

verify_input() {
  local relative=$1 expected=$2 path actual lexical resolved
  path=$workspace_root/$relative
  lexical=$(realpath -ms "$path")
  resolved=$(realpath -e "$path")
  [[ $resolved == "$lexical" ]] || {
    printf 'input path contains a symlink: %s\n' "$relative" >&2
    exit 2
  }
  [[ -f $path && ! -L $path && $(stat -c '%h' "$path") -eq 1 ]] || {
    printf 'invalid pinned input: %s\n' "$relative" >&2
    exit 2
  }
  actual=$(sha256sum "$path" | cut -d' ' -f1)
  [[ $actual == "$expected" ]] || {
    printf 'input hash mismatch: %s\n' "$relative" >&2
    exit 2
  }
}

verify_input ANAL/NE57/DABA/static.nest7grid "$static_sha"
build_receipt=$build_root/build_provenance.tsv
: > "$build_receipt"

pin_build_file() {
  local label=$1 path expected=${3:-} actual
  path=$(realpath -e "$2")
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
pin_build_file static_grid "$static_file" "$static_sha"
pin_build_file link_netcdff "$netcdff_archive" "$expected_netcdff_sha"
pin_build_file link_netcdf "$netcdf_archive" "$expected_netcdf_sha"
verify_build_files
read -r -a nf_fflags <<<"$($nf_config --fflags)"
read -r -a nf_flibs <<<"$($nf_config --flibs)"
"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" \
  -module "$build_root" -I "$build_root" "${nf_fflags[@]}" \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/src/common/cloud_bal_column_physics.f90" \
  "$repo_root/src/common/cloud_bal_balance_operator.f90" \
  "$repo_root/src/common/cloud_bal_grid_geometry.f90" \
  "$repo_root/src/common/cloud_bal_pipeline.f90" \
  "$repo_root/src/common/cloud_bal_real_netcdf.f90" \
  "$repo_root/tests/real_manufactured_balance_driver.f90" \
  "${nf_flibs[@]}" -o "$build_root/driver"
ldd_output=$(ldd "$build_root/driver")
[[ $ldd_output != *"not found"* ]] || {
  printf 'unresolved runtime dependency:\n%s\n' "$ldd_output" >&2
  exit 2
}
pin_build_file driver "$build_root/driver"
runtime_index=0
while IFS= read -r runtime_path; do
  runtime_index=$((runtime_index + 1))
  pin_build_file "runtime_$runtime_index" "$runtime_path"
done < <(printf '%s\n' "$ldd_output" | \
  awk '{for(i=1;i<=NF;i++) if ($i ~ /^\//) print $i}' | sort -u)
verify_build_files

mapfile -t case_ids < <(tail -n +2 "$manifest" | cut -f1)
[[ ${#case_ids[@]} -eq 4 ]] || {
  printf 'the real-geometry contract requires exactly four cases\n' >&2
  exit 2
}
products=(RUN_SUMMARY.json)
for case_id in "${case_ids[@]}"; do
  products+=("$case_id.nc" "$case_id.json" "$case_id.log" "$case_id.png")
done
last_epoch=$(date -u -d "$(tail -n 1 "$manifest" | cut -f2)" +%s)
transaction_id="real-mms-${source_commit:0:12}-$(date -u +%Y%m%dT%H%M%S)-$$"
staging=$(python3 "$repo_root/tools/cloud_bal_transaction.py" begin \
  "$publication_root" "$transaction_id" "${products[@]}" \
  --source-commit "$source_commit" \
  --configuration real-geometry-manufactured-balance-ifx-2026-v1 \
  --valid-time "$last_epoch")
trap 'if [[ -d $staging ]]; then mv "$staging" "$staging.failed.$$"; fi' EXIT

case_count=0
while IFS=$'\t' read -r case_id valid_time fua fua_hash \
    fsf_before fsf_before_hash fsf_center fsf_center_hash \
    fsf_after fsf_after_hash lw3 lw3_hash vrz vrz_hash vrt vrt_hash; do
  [[ $case_id == case_id ]] && continue
  case_count=$((case_count + 1))
  for pair in \
    "$fua:$fua_hash" "$fsf_before:$fsf_before_hash" \
    "$fsf_center:$fsf_center_hash" "$fsf_after:$fsf_after_hash" \
    "$lw3:$lw3_hash" "$vrz:$vrz_hash" "$vrt:$vrt_hash"; do
    verify_input "${pair%%:*}" "${pair##*:}"
  done
  epoch=$(date -u -d "$valid_time" +%s)
  diagnostic=$(python3 "$repo_root/tools/cloud_bal_transaction.py" resolve \
    "$publication_root" "$transaction_id" "$case_id.nc")
  report=$(python3 "$repo_root/tools/cloud_bal_transaction.py" resolve \
    "$publication_root" "$transaction_id" "$case_id.json")
  log=$(python3 "$repo_root/tools/cloud_bal_transaction.py" resolve \
    "$publication_root" "$transaction_id" "$case_id.log")
  figure=$(python3 "$repo_root/tools/cloud_bal_transaction.py" resolve \
    "$publication_root" "$transaction_id" "$case_id.png")
  diagnostic_tmp=$build_root/$case_id.nc
  report_tmp=$build_root/$case_id.json
  figure_tmp=$build_root/$case_id.png
  figure_repeat=$build_root/$case_id.repeat.png

  "$build_root/driver" "$workspace_root/$fua" "$workspace_root/$fsf_before" \
    "$workspace_root/$fsf_center" "$workspace_root/$fsf_after" \
    "$workspace_root/$lw3" "$workspace_root/$vrz" "$workspace_root/$vrt" \
    "$static_file" "$diagnostic_tmp" "$epoch" 0.1 >"$log" 2>&1
  python3 "$repo_root/tools/validate_real_manufactured_balance.py" \
    "$diagnostic_tmp" "$log" --json "$report_tmp" >/dev/null
  python3 "$repo_root/tools/plot_real_manufactured_balance.py" \
    "$diagnostic_tmp" "$figure_tmp" --title "$case_id"
  python3 "$repo_root/tools/plot_real_manufactured_balance.py" \
    "$diagnostic_tmp" "$figure_repeat" --title "$case_id"
  cmp "$figure_tmp" "$figure_repeat"
  mv "$diagnostic_tmp" "$diagnostic"
  mv "$report_tmp" "$report"
  mv "$figure_tmp" "$figure"

  for pair in \
    "$fua:$fua_hash" "$fsf_before:$fsf_before_hash" \
    "$fsf_center:$fsf_center_hash" "$fsf_after:$fsf_after_hash" \
    "$lw3:$lw3_hash" "$vrz:$vrz_hash" "$vrt:$vrt_hash"; do
    verify_input "${pair%%:*}" "${pair##*:}"
  done
  printf 'CASE %s NUMERICAL_REAL_GEOMETRY_PASS\n' "$case_id"
done < "$manifest"
[[ $case_count -eq 4 ]] || exit 2

python3 - "$staging/RUN_SUMMARY.json" "$source_commit" "$manifest" \
  "$CLOUD_BAL_FC" "$cloud_bal_fc_version" "$build_root/driver" \
  "$build_receipt" "$nf_config" "${CLOUD_BAL_REPRO_FLAGS[*]}" <<'PY'
import csv
import hashlib
import json
import sys
from pathlib import Path

output, commit, manifest, compiler, version, driver, build_receipt, nf_config, flags = sys.argv[1:]
with Path(manifest).open(encoding="utf-8", newline="") as stream:
    cases = list(csv.DictReader(stream, delimiter="\t"))
reports = []
for case in cases:
    path = Path(output).parent / f"{case['case_id']}.json"
    reports.append(json.loads(path.read_text(encoding="utf-8")))
build_files = []
with Path(build_receipt).open(encoding="utf-8") as stream:
    for line in stream:
        label, path, expected = line.rstrip("\n").split("\t")
        actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit("build input changed: " + path)
        build_files.append({"label": label, "path": path, "sha256": expected})
summary = {
    "schema": 1,
    "contract": "real_geometry_manufactured_balance_ifx_2026_v1",
    "source_commit": commit,
    "source_tree_clean": True,
    "compiler": str(Path(compiler).resolve()),
    "compiler_version": version,
    "compiler_sha256": hashlib.sha256(Path(compiler).read_bytes()).hexdigest(),
    "compiler_flags": flags,
    "netcdf_fortran_config": str(Path(nf_config).resolve()),
    "netcdf_fortran_config_sha256": hashlib.sha256(Path(nf_config).read_bytes()).hexdigest(),
    "driver_sha256": hashlib.sha256(Path(driver).read_bytes()).hexdigest(),
    "build_files": build_files,
    "input_manifest_sha256": hashlib.sha256(Path(manifest).read_bytes()).hexdigest(),
    "input_cases": cases,
    "background_reftime_utc": "2026-08-16T06:00:00Z",
    "case_count": len(cases),
    "case_decisions": [report["decision"] for report in reports],
    "evidence_authority": "NUMERICAL_REAL_GEOMETRY_ONLY",
    "science_authority": "NONE",
    "balance_scope": "TARGET_INCREMENT_PROJECTION_ONLY",
    "target_kind": "MANUFACTURED_TEST",
    "boundary_authority": "MANUFACTURED_TEST_ONLY",
    "surface_wind_frame": "UNRESOLVED_NATIVE",
    "wave_proxy_scope": "NEIGHBOR_JUMP_ENGINEERING_GUARD_ONLY",
    "forecast_wave_response_assessed": False,
    "operational_promotion_eligible": False,
    "all_cases_passed": len(cases) == 4 and all(
        report["decision"] == "NUMERICAL_REAL_GEOMETRY_PASS" for report in reports
    ),
}
if not summary["all_cases_passed"]:
    raise SystemExit("not every real-geometry case passed")
Path(output).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
PY

verify_build_files
for pair in $(tail -n +2 "$manifest" | cut -f3-16 | tr '\t' '\n' | paste - - -d:); do
  verify_input "${pair%%:*}" "${pair##*:}"
done
if [[ $(git -C "$repo_root" rev-parse HEAD) != "$source_commit" ]] || \
   [[ -n $(git -C "$repo_root" status --porcelain --untracked-files=all) ]]; then
  printf 'source tree changed during the real-data numerical run\n' >&2
  exit 2
fi
python3 "$repo_root/tools/cloud_bal_transaction.py" commit \
  "$publication_root" "$transaction_id" >/dev/null
staging=
trap - EXIT
python3 "$repo_root/tools/verify_real_manufactured_balance_generation.py" \
  "$publication_root" "$manifest" --repo "$repo_root"
