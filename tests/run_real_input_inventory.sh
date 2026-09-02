#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_lexical=$(realpath -ms "${CLOUD_BAL_WORKSPACE_ROOT:-$repo_root/..}")
workspace_root=$(realpath -e "$workspace_lexical")
[[ $workspace_root == "$workspace_lexical" ]] || {
  printf 'workspace root cannot contain a symlink: %s\n' "$workspace_lexical" >&2
  exit 2
}
mkdir -p "$repo_root/scratch"
report=$(mktemp "$repo_root/scratch/qbal_input_inventory.XXXXXX.json")
trap 'rm -f "$report"' EXIT

status=0
python3 "$repo_root/tools/check_qbal_real_inputs.py" \
  --workspace-root "$workspace_root" > "$report" || status=$?

if [[ $status -ne 3 ]]; then
  printf 'expected fail-closed BLOCKED status 3, got %s\n' "$status" >&2
  sed -n '1,120p' "$report" >&2
  exit 1
fi

python3 - "$report" "$repo_root" <<'PY'
import importlib.util
import json
import sys
from pathlib import Path

module_path = Path(sys.argv[2]) / "tools/check_qbal_real_inputs.py"
spec = importlib.util.spec_from_file_location("qbal_inputs", module_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

with open(sys.argv[1], encoding="utf-8") as stream:
    report = json.load(stream)

assert report["final_bigfile_allowed_as_input"] is False
assert report["manifest_sha256"] == module.EXPECTED_MANIFEST_SHA256
assert report["overall_status"] == \
    "BLOCKED_PENDING_ORIGINAL_UPSTREAM_REGENERATION"
assert len(report["cases"]) == 4
assert all(case["prepared_status"] == "PASS" for case in report["cases"])
assert all(case["direct_qbal_status"] == "BLOCKED" for case in report["cases"])
assert all(item["status"] == "PASS" for item in report["static"])

for case in report["cases"]:
    kinds = {item["kind"]: item for item in case["prepared"]}
    assert kinds["vrz"]["radar_usable_ge0_cells_before_terrain"] > 0
    assert kinds["vrz"]["radar_no_echo_minus10_cells"] > 0
    assert kinds["vrt"]["bright_band_tid2_cells"] > 0

for forbidden in (
    "/tmp/bigfile/input.nc",
    "/tmp/LAPS:2026-08-16_12:00",
    "/tmp/KLBG:2026-08-16_12:00",
    "/tmp/met_em.d01.nc",
    "/tmp/lapsprep/wps/file",
    "/tmp/balance/lw3/file",
):
    assert module.forbidden_reason(Path(forbidden)) is not None
assert module.forbidden_reason(Path("/tmp/lapsprd/lco/262281200.lco")) is None

workspace = Path(sys.argv[2]).parent
_, error = module.contained_input(workspace, "../../tmp/external.fua", "fua")
assert error is not None
_, error = module.contained_input(
    workspace, "ANAL/NE57/DAOU/00/lapsprd/vrz/x", "fua"
)
assert error is not None

print("Four real hourly prepared-input sets pass; direct QBAL closure is BLOCKED as designed")
PY
