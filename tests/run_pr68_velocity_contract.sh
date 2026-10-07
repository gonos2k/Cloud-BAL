#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
source "$script_dir/intel_toolchain.sh"
source_file=${PR68_VELOCITY_SOURCE:-/var/tmp/pr67_budget_capture_20261007/source/module_mp_kdm6_combined_research.f90}
expected_source_sha256=9efc09257a46102073b6d5a3d7cd12eb9ecd485526bc6e9cb349e4b2b037680d
if [[ ! -f $source_file ]]; then
  printf 'captured PR67 combined research source is required: %s\n' "$source_file" >&2
  exit 2
fi
actual_source_sha256=$(sha256sum "$source_file" | cut -d' ' -f1)
if [[ $actual_source_sha256 != "$expected_source_sha256" ]]; then
  printf 'unexpected captured source hash: %s\n' "$actual_source_sha256" >&2
  exit 2
fi
scratch_root=/var/tmp
work_dir=$(mktemp -d "$scratch_root/cloud_bal_pr68_velocity.XXXXXX")
printf 'WORK_DIR %s\n' "$work_dir"
cp "$source_file" "$work_dir/module_mp_kdm6_combined_research.f90"
patch --fuzz=0 -p0 -d "$work_dir" < "$repo_root/docs/evidence/pr68_velocity_contract_20261007.patch" >"$work_dir/patch.log"
python3 - "$work_dir/module_mp_kdm6_combined_research.f90" "$work_dir" <<'PY'
from pathlib import Path
import re,sys
source=Path(sys.argv[1]).read_text()
out=Path(sys.argv[2])
calls=re.findall(r'(?ms)^\s*call slope_kdm6\(.*?^\s*ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax\)',source)
if len(calls)!=7:
    raise SystemExit(f'expected seven slope_kdm6 calls, got {len(calls)}')
if any('terminal_velocity_mass,terminal_velocity_number' not in call for call in calls):
    raise SystemExit('a slope_kdm6 call does not write the named terminal velocities')
if source.count('call kdm6_velocity_rates(terminal_velocity_mass,terminal_velocity_number') != 3:
    raise SystemExit('expected rate refresh at initial, rain-minor, and ice-minor transport points')
if 'write(pr67_unit) mass_velocity_rate(its:ite,kts:kte,4)' not in source:
    raise SystemExit('process observer does not capture the ice mass transport rate')
if re.search(r'work1\(i,k,[1-4]\)\s*=\s*work1\(i,k,[1-4]\)/delz',source) or re.search(
        r'workn\(i,k,[1-2]\)\s*=\s*workn\(i,k,[1-2]\)/delz',source):
    raise SystemExit('terminal-speed conversion still mutates work1/workn')
if re.search(r'(?:terminal_velocity_mass|terminal_velocity_number)\([^\n]*\)\s*=\s*[^\n]*/delz',source):
    raise SystemExit('terminal velocity array mutated by delz conversion')
if 'real, intent(in) :: delz(ims:ime,kms:kme)' not in source:
    raise SystemExit('rate helper does not preserve full-grid delz bounds')
for fragment in ('max(mass_velocity_rate(i,k,1),number_velocity_rate(i,k,1)',
                 'falk(i,k,1) = dend(i,k)*qrs(i,k,1)*mass_velocity_rate(i,k,1)',
                 'falkn(i,k,1) = nrs(i,k,1)*number_velocity_rate(i,k,1)',
                 'falk(i,k,4) = dend(i,k)*qci(i,k,2)*mass_velocity_rate(i,k,4)',
                 'falkn(i,k,2) = nci(i,k,2)*number_velocity_rate(i,k,2)'):
    if fragment not in source:
        raise SystemExit('transport wiring check failed: '+fragment)
helper=re.search(r'(?ms)^\s*subroutine kdm6_velocity_rates\b.*?^\s*end subroutine kdm6_velocity_rates\s*$',source)
if not helper:
    raise SystemExit('velocity conversion helper not found')
(out/'kdm6_velocity_rates.f90').write_text(helper.group(0)+'\n')
PY
for opt in O0 O2; do
  build_dir="$work_dir/$opt"
  mkdir "$build_dir"
  cp "$work_dir/kdm6_velocity_rates.f90" "$script_dir/test_pr68_velocity_contract.f90" "$build_dir/"
  cd "$build_dir"
  if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  "$CLOUD_BAL_FC" "${flags[@]}" -c kdm6_velocity_rates.f90
  "$CLOUD_BAL_FC" "${flags[@]}" -c test_pr68_velocity_contract.f90
  "$CLOUD_BAL_FC" "${flags[@]}" -o test.exe test_pr68_velocity_contract.o kdm6_velocity_rates.o
  ./test.exe > run.log 2>&1
  cat run.log
done
python3 - "$repo_root" "$work_dir" "$source_file" <<'PY'
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

repo = Path(sys.argv[1])
work = Path(sys.argv[2])
source = Path(sys.argv[3])

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

compiler = os.environ["CLOUD_BAL_FC"]
version = subprocess.check_output(
    [compiler, "--version"], text=True, stderr=subprocess.STDOUT).splitlines()[0]
receipt = {
    "schema": "pr68_velocity_contract_validation_v1",
    "date_utc": "2026-10-07",
    "captured_source": str(source),
    "captured_source_sha256": sha(source),
    "patch": "docs/evidence/pr68_velocity_contract_20261007.patch",
    "patch_sha256": sha(repo / "docs/evidence/pr68_velocity_contract_20261007.patch"),
    "patched_source_sha256": sha(work / "module_mp_kdm6_combined_research.f90"),
    "compiler": version,
    "scratch_work_dir": str(work),
    "checks": {
        "seven_slope_calls_named": "PASS",
        "three_transport_refreshes_wired": "PASS",
        "nonuniform_dz_and_halo_bounds": "PASS",
        "separate_mass_number_rates": "PASS",
        "repeated_minor_loop_refresh": "PASS",
        "zero_speed": "PASS",
        "pinned_intel_O0": "PASS",
        "pinned_intel_O2": "PASS",
    },
}
for optimization in ("O0", "O2"):
    receipt["checks"][f"{optimization}_log_sha256"] = sha(
        work / optimization / "run.log")
(work / "validation.json").write_text(
    json.dumps(receipt, indent=2) + "\n")
PY
printf 'PR68 VELOCITY CONTRACT O0/O2 PASS\n'
