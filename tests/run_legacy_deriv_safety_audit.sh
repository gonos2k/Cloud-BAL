#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_lexical=$(realpath -ms "${CLOUD_BAL_WORKSPACE_ROOT:-$repo_root/..}")
workspace_root=$(realpath -e "$workspace_lexical")
[[ $workspace_root == "$workspace_lexical" ]] || {
  printf 'workspace root cannot contain a symlink: %s\n' "$workspace_lexical" >&2
  exit 2
}
temporary=$(mktemp -d "${TMPDIR:-/tmp}/cloud-bal-legacy-safety.XXXXXX")
trap 'rm -rf -- "$temporary"' EXIT

python3 -m unittest discover \
  -s "$repo_root/tests" \
  -p 'test_legacy_deriv_safety.py'

set +e
python3 "$repo_root/tools/audit_legacy_deriv_safety.py" \
  --source "$workspace_root/klaps-v5.0_/src/deriv/laps_deriv_sub.f" \
  --makefile "$workspace_root/klaps-v5.0_/src/deriv/Makefile" \
  --make-config "$workspace_root/klaps-v5.0_/src/include/makefile.inc" \
  --job-script "$workspace_root/ANAL/NE57/SHEL/klps_lc05_anal_all_ajob.csh" \
  --namelist "$workspace_root/ANAL/NE57/DABA/namelist/deriv.nl" \
  --binary "$workspace_root/ANAL/NE57/EXET/klps_anal_derv.exe" \
  --emit-patch "$temporary/legacy-deriv-safety.patch" \
  --output "$temporary/audit.json"
audit_status=$?
set -e

if [[ $audit_status -ne 2 ]]; then
  printf 'expected fail-closed BLOCKED (exit 2), got %d\n' "$audit_status" >&2
  exit 1
fi

python3 - "$temporary/audit.json" "$temporary/legacy-deriv-safety.patch" <<'PY'
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
patch = Path(sys.argv[2]).read_text(encoding="utf-8")
required = {
    "source_authority",
    "binary_legacy_calls",
    "ifx_configuration",
    "production_provenance",
}
actual = set(report.get("blocked_stages", []))
if report.get("status") != "BLOCKED" or actual != required:
    raise SystemExit(
        f"unexpected production audit result; expected={sorted(required)}, actual={sorted(actual)}"
    )
if "l_evap_radar = .false." not in patch:
    raise SystemExit("generated review patch does not lock evaporation off")
if "l_flag_bogus_w = .false." not in patch:
    raise SystemExit("generated review patch does not lock cloud bogus-w off")
if "if(.false. .and. l_evap_radar)then" not in patch:
    raise SystemExit("generated review patch lacks constant-false call guard")
print("LEGACY DERIV SAFETY AUDIT PASS: current production correctly BLOCKED")
print("blocked stages:", ", ".join(report["blocked_stages"]))
PY
