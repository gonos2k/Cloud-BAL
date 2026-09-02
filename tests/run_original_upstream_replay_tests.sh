#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_lexical=$(realpath -ms "${CLOUD_BAL_WORKSPACE_ROOT:-$repo_root/..}")
workspace_root=$(realpath -e "$workspace_lexical")
[[ $workspace_root == "$workspace_lexical" ]] || {
  printf 'workspace root cannot contain a symlink: %s\n' "$workspace_lexical" >&2
  exit 2
}
allowed_root=$repo_root/scratch/original_upstream_replay
mkdir -p "$allowed_root"

python3 "$repo_root/tests/test_original_upstream_replay.py"

run_root=$(mktemp -d "$allowed_root/dry_run.XXXXXX")
cleanup() {
  case $run_root in
    "$allowed_root"/dry_run.*)
      chmod -R u+w "$run_root"
      rm -rf -- "$run_root"
      ;;
  esac
}
trap cleanup EXIT

status=0
tool_stdout=$(python3 "$repo_root/tools/original_upstream_replay.py" \
  --workspace-root "$workspace_root" \
  --root "$run_root") || status=$?
if [[ $status -ne 3 ]]; then
  printf 'expected deterministic BLOCKED status 3, got %s\n' "$status" >&2
  printf '%s\n' "$tool_stdout" >&2
  exit 1
fi

python3 - "$run_root/PRE_QBAL_MANIFEST.json" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert manifest["contract"] == "original_klaps_pre_qbal_generation_v1"
assert manifest["authority"] == "original_klaps_source"
assert manifest["source_tree"] == "klaps-v5.0_"
assert manifest["compiler_family"] == "Intel"
assert manifest["generation_status"] == "BLOCKED"
assert len(manifest["replay_harness_sha256"]) == 64
assert len(manifest["replay_spec_sha256"]) == 64
assert len(manifest["case_manifest_sha256"]) == 64
assert manifest["execution_started"] is False
assert manifest["final_bigfile_allowed_as_input"] is False
assert len(manifest["cases"]) == 4
assert all(case["status"] == "BLOCKED" for case in manifest["cases"])
assert all(case["input_closure_sha256"] is None for case in manifest["cases"])
assert all(case["vrt_completion_gate"]["status"] == "PASS"
           for case in manifest["cases"])
assert all(set(case["products"]) == {"lt1", "lq3", "lw3", "lco", "lsx"}
           for case in manifest["cases"])
assert all(item["status"] == "PASS" for item in manifest["executables"])
expected_configuration = {
    "environment": manifest["environment"],
    "assets": [
        {"role": item["role"], "sha256": item["sha256"]}
        for item in manifest["assets"]
    ],
    "executables": [
        {"stage": item["stage"], "sha256": item["sha256"]}
        for item in manifest["executables"]
    ],
}
import hashlib
encoded = json.dumps(
    expected_configuration, ensure_ascii=True, separators=(",", ":"), sort_keys=True
).encode("utf-8")
assert manifest["configuration_sha256"] == hashlib.sha256(encoded).hexdigest()
assert manifest["sandbox_gate"]["status"] in {"PASS", "BLOCKED"}
assert "DECLARED_RUNTIME_LIBRARY_CLOSURE_MISSING" in manifest["blockers"]
assert "UPSTREAM_EXECUTION_NOT_AUTHORIZED" in manifest["blockers"]
print("Original-upstream replay dry-run: 4/4 VRT complete; execution BLOCKED safely")
PY

manifest_sha=$(sha256sum "$run_root/PRE_QBAL_MANIFEST.json" | cut -d' ' -f1)
checker_report=$run_root/checker.json
checker_status=0
python3 "$repo_root/tools/check_qbal_real_inputs.py" \
  --workspace-root "$workspace_root" \
  --pre-qbal-root "$run_root" \
  --pre-qbal-manifest-sha256 "$manifest_sha" > "$checker_report" || \
  checker_status=$?
if [[ $checker_status -ne 3 ]]; then
  printf 'expected checker BLOCKED status 3, got %s\n' "$checker_status" >&2
  exit 1
fi
python3 - "$checker_report" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["overall_status"] == "BLOCKED_PENDING_ORIGINAL_UPSTREAM_REGENERATION"
assert all(case["prepared_status"] == "PASS" for case in report["cases"])
assert all(case["direct_qbal_status"] == "BLOCKED" for case in report["cases"])
print("Direct-QBAL checker accepts the receipt structure and remains BLOCKED")
PY
