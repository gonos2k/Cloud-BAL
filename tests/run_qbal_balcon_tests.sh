#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo_root/tests/intel_toolchain.sh"
mkdir -p "$repo_root/scratch"
build_root=$(mktemp -d "$repo_root/scratch/qbal_balcon.XXXXXX")
cleanup() {
  if [[ "${CLOUD_BAL_KEEP_TEST_OUTPUT:-0}" == 1 ]]; then
    printf 'BALCON test scratch: %s\n' "$build_root"
  else
    rm -rf -- "$build_root"
  fi
}
trap cleanup EXIT

qbal_source="$repo_root/src/balance/qbalpe.f"
wind_source="$repo_root/src/common/cloud_bal_wind_modes.f90"
balcon_test_source="$repo_root/tests/test_qbal_balcon.f90"
reverse_test_source="$repo_root/tests/test_qbal_reverse_output.f90"
utility_root="$repo_root/../klaps-v5.0_/src/lib"
qbal_source_hash=$(sha256sum "$qbal_source" | awk '{print $1}')
core_source="$build_root/qbal_core.f"
awk '/^[[:space:]]*subroutine diagnose\(/ {capture=1} capture {print}' \
  "$qbal_source" > "$core_source"

projection_bypass_source="$build_root/final_projection_bypass.f"
reverse_phi_omitted_source="$build_root/reverse_phi_assignment_omitted.f"
python3 - "$core_source" "$projection_bypass_source" "$reverse_phi_omitted_source" <<'PY'
from pathlib import Path
import sys

core, projection, reverse = map(Path, sys.argv[1:])
source = core.read_text(encoding="utf-8")
cases = [
    (projection,
     "       call leib_sub(nx,ny,nz,erf,tau,erru,influence\n"
     "     .,lat,dx,dy,ps,p,dp,u,ucont,v,vcont,\n"
     "     . om,omcont,omb,l,lmax,continuity_status)\n",
     "c NEGATIVE CONTROL: final continuity projection bypassed.\n"
     "       ucont=u\n       vcont=v\n       omcont=om\n"
     "       continuity_status=1\n", "final projection"),
    (reverse,
     "          phi(i,j,k)=(phis(i-1,j-1,k-1)+phis(i,j-1,k-1)+\n"
     "     &               phis(i-1,j,k-1)+phis(i,j,k-1))*.25\n",
     "c NEGATIVE CONTROL: reverse PHI assignment omitted.\n", "reverse PHI"),
]
for path, target, replacement, name in cases:
    if source.count(target) != 1:
        raise SystemExit(f"{name} mutation target count is not one")
    path.write_text(source.replace(target, replacement), encoding="utf-8")
PY

fixed_o2=()
skip_next=0
for flag in "${CLOUD_BAL_FIXED_72_FLAGS[@]}"; do
  if ((skip_next)); then skip_next=0; continue; fi
  if [[ "$flag" == -check ]]; then skip_next=1; continue; fi
  fixed_o2+=("${flag/-O0/-O2}")
done

input_hashes="$build_root/input_hashes.json"
python3 - "$input_hashes" "$repo_root" "$build_root" "$CLOUD_BAL_FC" \
  "$cloud_bal_imf" "$cloud_bal_intlc" "$cloud_bal_setvars" "$cloud_bal_fc_version" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

output, root, scratch, compiler, imf, intlc, setvars, version = sys.argv[1:]
files = [
    root + "/src/balance/qbalpe.f", root + "/src/common/cloud_bal_wind_modes.f90",
    root + "/tests/test_qbal_balcon.f90", root + "/tests/test_qbal_reverse_output.f90",
    root + "/tests/run_qbal_balcon_tests.sh", root + "/tests/intel_toolchain.sh",
    root + "/../klaps-v5.0_/src/lib/move.f", root + "/../klaps-v5.0_/src/lib/zero.f",
    root + "/../klaps-v5.0_/src/lib/array_diagnosis.f", scratch + "/qbal_core.f",
    scratch + "/final_projection_bypass.f", scratch + "/reverse_phi_assignment_omitted.f",
    compiler, imf, intlc, setvars,
]
def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
Path(output).write_text(json.dumps({"version": version, "files": {
    path: digest(path) for path in files}}, indent=2) + "\n", encoding="utf-8")
PY

results_tsv="$build_root/results.tsv"
: > "$results_tsv"
projection_expected='QBAL forced continuity reduction rejected'
projection_driver_expected='BALCON localized residual candidate rejected'
reverse_expected='reverse A-grid manufactured oracle failed'
run_variant() {
  local level=$1 variant=$2 core_path=$3 expected=$4 driver_expected=$5
  local level_root variant_root
  level_root="$build_root/$level"
  variant_root="$level_root/$variant"
  local executable="$variant_root/test_qbal_balcon" log_path="$variant_root/test.log"
  mkdir "$variant_root"
  (
    cd "$variant_root"
    "$CLOUD_BAL_FC" -c "${fixed_flags[@]}" -I "$level_root" "$core_path"
    "$CLOUD_BAL_FC" "${free_flags[@]}" \
      "$level_root/test_qbal_balcon.o" "$level_root/test_qbal_reverse_output.o" \
      "$level_root/cloud_bal_wind_modes.o" "$level_root/move.o" "$level_root/zero.o" \
      "$level_root/array_diagnosis.o" "$(basename "$core_path" .f).o" -o "$executable"
  )
  local return_code=0
  if "$executable" > "$log_path" 2>&1; then return_code=0; else return_code=$?; fi
  if [[ -n "$expected" ]]; then
    if ((return_code != 128)) || ! rg -F -q -- "$expected" "$log_path"; then
      printf '%s %s did not produce expected rejection: %s\n' \
        "$level" "$variant" "$expected" >&2
      tail -40 "$log_path" >&2
      return 1
    fi
    if [[ -n "$driver_expected" ]] && ! rg -F -q -- "$driver_expected" "$log_path"; then
      printf '%s %s did not produce expected driver rejection: %s\n' \
        "$level" "$variant" "$driver_expected" >&2
      tail -40 "$log_path" >&2
      return 1
    fi
    printf 'BALCON Intel %s %s rejected as expected: %s\n' "$level" "$variant" "$expected"
    printf '%s\t%s\tREJECTED\t%s\t%s\t%s\n' \
      "$level" "$variant" "$return_code" "$log_path" "$expected" >> "$results_tsv"
  else
    if ((return_code != 0)); then
      printf '%s %s failed unexpectedly\n' "$level" "$variant" >&2
      tail -40 "$log_path" >&2
      return 1
    fi
    printf 'Full BALCON Intel %s tests passed\n' "$level"
    printf '%s\t%s\tPASS\t%s\t%s\t\n' \
      "$level" "$variant" "$return_code" "$log_path" >> "$results_tsv"
  fi
}

for level in O0 O2; do
  if [[ "$level" == O0 ]]; then
    fixed_flags=("${CLOUD_BAL_FIXED_72_FLAGS[@]}")
    free_flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  else
    fixed_flags=("${fixed_o2[@]}")
    free_flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  level_root="$build_root/$level"
  mkdir "$level_root"
  (
    cd "$level_root"
    "$CLOUD_BAL_FC" -c "${free_flags[@]}" "$wind_source"
    "$CLOUD_BAL_FC" -c "${free_flags[@]}" "$balcon_test_source"
    "$CLOUD_BAL_FC" -c "${free_flags[@]}" "$reverse_test_source"
    for utility in move zero array_diagnosis; do
      "$CLOUD_BAL_FC" -c "${fixed_flags[@]}" "$utility_root/$utility.f"
    done
  )
  run_variant "$level" normal "$core_source" "" ""
  run_variant "$level" final_projection_bypass "$projection_bypass_source" \
    "$projection_expected" "$projection_driver_expected"
  run_variant "$level" reverse_phi_assignment_omitted "$reverse_phi_omitted_source" \
    "$reverse_expected" ""
done

if [[ "$(sha256sum "$qbal_source" | awk '{print $1}')" != "$qbal_source_hash" ]]; then
  printf 'production qbal source changed during scratch tests\n' >&2
  exit 1
fi

python3 - "$build_root/manifest.json" "$input_hashes" "$results_tsv" \
  "$cloud_bal_fc_version" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

manifest_path, hashes_path, results_path, version = sys.argv[1:]
before = json.loads(Path(hashes_path).read_text(encoding="utf-8"))
def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
after = {path: digest(path) for path in before["files"]}
if after != before["files"]:
    raise SystemExit("an input changed during the scratch build")
rows = []
for line in Path(results_path).read_text(encoding="utf-8").splitlines():
    level, variant, status, code, log, expected = line.split("\t")
    rows.append({"level": level, "variant": variant, "status": status,
                 "return_code": int(code), "log": log,
                 "expected_rejection": expected or None})
if len(rows) != 6:
    raise SystemExit("negative-control receipt count is not six runs")
files = before["files"]
entry = lambda path: {"path": path, "sha256": files[path]}
compiler = next(path for path in files if path.endswith("/bin/ifx"))
runtime = [entry(path) for path in files if path.endswith(("libimf.so", "libintlc.so.5"))]
source_paths = [path for path in files if path.endswith((
    "qbalpe.f", "cloud_bal_wind_modes.f90", "test_qbal_balcon.f90",
    "test_qbal_reverse_output.f90", "move.f", "zero.f", "array_diagnosis.f",
    "qbal_core.f"))]
scratch = Path(hashes_path).parent
mutations = [
    ("final_projection_bypass", scratch / "final_projection_bypass.f", 1,
     "QBAL forced continuity reduction rejected"),
    ("reverse_phi_assignment_omitted", scratch / "reverse_phi_assignment_omitted.f", 1,
     "reverse A-grid manufactured oracle failed"),
]
manifest = {
    "schema": 1, "runner": "tests/run_qbal_balcon_tests.sh",
    "runner_sha256": files[next(path for path in files if path.endswith("/run_qbal_balcon_tests.sh"))],
    "compiler": {"path": compiler, "version": version, "sha256": files[compiler]},
    "runtime": runtime, "sources": [entry(path) for path in source_paths],
    "mutations": [{"name": name, "path": str(path), "sha256": digest(path),
                   "replacement_count": count, "expected_rejection": expected}
                  for name, path, count, expected in mutations],
    "levels": ["O0", "O2"], "results": rows,
    "toolchain": {"setvars": entry(next(path for path in files if path.endswith("/setvars.sh"))),
                   "intel_toolchain": entry(next(path for path in files if path.endswith("/intel_toolchain.sh")))},
}
Path(manifest_path).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY
