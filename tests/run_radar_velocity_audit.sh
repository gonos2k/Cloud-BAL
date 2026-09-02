#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "$0")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
. "$repo_root/tests/output_safety.sh"
manifest=$repo_root/tests/qbal_real_cases_20260816.tsv
cloud_bal_require_clean_source
[[ $# -le 1 ]] || { printf 'usage: %s [REPORT]\n' "$0" >&2; exit 2; }
diagnostic_root=$(cloud_bal_current_evidence \
  "$repo_root/scratch/publications/real_shadow" "$manifest")
report=$(cloud_bal_output_under \
  "${1:-$repo_root/scratch/audits/radar_velocity_v1.json}" \
  "$repo_root/scratch/audits")
case $report in
  "$diagnostic_root"|"$diagnostic_root"/*)
    printf 'audit output cannot modify its diagnostic generation\n' >&2
    exit 2
    ;;
esac

set +e
python3 "$repo_root/tools/audit_radar_velocity.py" \
  --diagnostic-root "$diagnostic_root" \
  --json "$report"
status=$?
set -e

if test "$status" -ne 3; then
  echo "FAIL: radar velocity audit must return diagnostic-only status 3" >&2
  exit 1
fi

python3 - "$report" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["case_count"] == 4
assert report["radar_count_per_case"] == 10
assert report["radar_velocity_authority"] is False
assert report["hydrometeor_fall_speed_applied"] is False
assert report["hydrometeor_fall_speed_required_for_authority"] is True
assert report["promotion_eligible"] is False
assert report["velocity_manifest_sha256"] == \
    "2a93b8194a78d91e1ebdb5be6706f0f5fa0c354565cdc80cc862b61b5a3afbf6"
for case in report["cases"]:
    assert len(case["velocity_files"]) == 10
    assert case["usable_velocity_cells"] > 0
    assert case["usable_nyquist_cells"] == 0
    assert case["decision"] == "DIAGNOSTIC_ONLY"
    assert all(item["vertical_mapping"] == "PRESSURE_MATCHED" for item in case["velocity_files"])
print("RADAR VELOCITY AUDIT PASS: 4/4 cases, diagnostic authority remains blocked")
PY
generation_after=$(cloud_bal_current_evidence \
  "$repo_root/scratch/publications/real_shadow" "$manifest")
[[ $generation_after == "$diagnostic_root" ]] || {
  printf 'diagnostic generation changed during radar audit\n' >&2
  exit 2
}
