#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
runner=$(readlink -f "${BASH_SOURCE[0]}")
artifact=${1:-/var/tmp/cloud_bal_pr64_actual_phase.f69Ky7/actual-ne57-phase_phi-shadow.nc}
profile=${2:-O0}
case "$profile" in O0|O2) ;; *) echo "profile must be O0 or O2" >&2; exit 2 ;; esac
test -f "$artifact" && test ! -L "$artifact"

reader=$repo_root/tests/check_pressure_geopotential_shadow.py
validator=$repo_root/tests/check_pressure_candidate_shadow.py
shared=$repo_root/tools/validate_shadow_diagnostics.py
copy_helper=$repo_root/tests/netcdf_test_copy.py
original_receipt=$(dirname "$artifact")/receipt.json

/usr/bin/python3 - "$original_receipt" "$artifact" "$profile" <<'PY'
import json
import sys
from pathlib import Path
receipt = json.loads(Path(sys.argv[1]).read_text())
assert Path(receipt["artifact_path"]) == Path(sys.argv[2]), receipt["artifact_path"]
assert receipt["compiler"]["profile"] == sys.argv[3], receipt["compiler"]["profile"]
assert receipt["status"] == "FAIL_OPEN", receipt["status"]
assert receipt["artifact_sha256"] == "ba4e8466903492b905a6f042257d8183614c9536fe0c0211acab7fcef4951991"
PY

run_root=$(mktemp -d "/var/tmp/cloud_bal_pr65_phi_mutations.${profile}.XXXXXX")
mkdir "$run_root/tmp"
printf 'PR65 Phi full mutation run: %s\n' "$run_root"

/usr/bin/python3 - "$run_root/runtime_paths.txt" <<'PY'
import netCDF4
import numpy
import numpy.core._multiarray_umath
import sys
from pathlib import Path
paths = [
    Path(sys.executable), Path(netCDF4.__file__), Path(netCDF4._netCDF4.__file__),
    Path(numpy.__file__), Path(numpy.core._multiarray_umath.__file__),
]
Path(sys.argv[1]).write_text("".join(f"{p}\n" for p in paths))
PY

hash_paths=("$artifact" "$original_receipt" "$reader" "$validator" "$shared" "$copy_helper" "$runner")
while IFS= read -r path; do hash_paths+=("$path"); done < "$run_root/runtime_paths.txt"
sha256sum "${hash_paths[@]}" > "$run_root/hash_pre.sha256"
artifact_pre=$(sha256sum "$artifact" | cut -d' ' -f1)
receipt_pre=$(sha256sum "$original_receipt" | cut -d' ' -f1)
runner_pre=$(sha256sum "$runner" | cut -d' ' -f1)

set +e
TMPDIR="$run_root/tmp" /usr/bin/python3 "$reader" "$artifact" \
  >"$run_root/full_mutation_suite.log" 2>&1
suite_status=$?
set -e

sha256sum "${hash_paths[@]}" > "$run_root/hash_post.sha256"
artifact_post=$(sha256sum "$artifact" | cut -d' ' -f1)
receipt_post=$(sha256sum "$original_receipt" | cut -d' ' -f1)
runner_post=$(sha256sum "$runner" | cut -d' ' -f1)
if ! cmp -s "$run_root/hash_pre.sha256" "$run_root/hash_post.sha256"; then guard_status=1; else guard_status=0; fi

/usr/bin/python3 - "$run_root" "$artifact" "$profile" "$suite_status" "$guard_status" \
  "$artifact_pre" "$artifact_post" "$receipt_pre" "$receipt_post" "$runner_pre" "$runner_post" \
  "$runner" "$reader" "$validator" "$shared" "$copy_helper" <<'PY'
import hashlib
import json
import platform
import sys
from pathlib import Path

root, artifact = Path(sys.argv[1]), Path(sys.argv[2])
profile, status, guard_status = sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
artifact_pre, artifact_post, prior_pre, prior_post, runner_pre, runner_post = sys.argv[6:12]
runner, reader, validator, shared, copy_helper = sys.argv[12:17]
log = root / "full_mutation_suite.log"
receipt = {
    "status": "PASS" if status == 0 and guard_status == 0 else "FAIL",
    "scope": "complete pressure-geopotential independent replay and mutation suite on retained PR64 artifact; no rebuild",
    "profile_label": profile,
    "artifact_path": str(artifact),
    "artifact_sha256_pre": artifact_pre,
    "artifact_sha256_post": artifact_post,
    "artifact_hash_guard_exit": 0 if artifact_pre == artifact_post else 1,
    "prior_full_run_receipt_path": str(artifact.parent / "receipt.json"),
    "prior_full_run_receipt_sha256_pre": prior_pre,
    "prior_full_run_receipt_sha256_post": prior_post,
    "prior_full_run_receipt_preserved": prior_pre == prior_post,
    "runner_path": runner,
    "runner_sha256_pre": runner_pre,
    "runner_sha256_post": runner_post,
    "suite_command": ["/usr/bin/python3", reader, str(artifact)],
    "suite_exit": status,
    "full_hash_guard_exit": guard_status,
    "hash_pre_manifest": str(root / "hash_pre.sha256"),
    "hash_post_manifest": str(root / "hash_post.sha256"),
    "suite_log": str(log),
    "suite_log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
    "tool_paths": [reader, validator, shared, copy_helper],
    "python": {"path": "/usr/bin/python3", "version": platform.python_version(), "platform": platform.platform()},
    "run_directory": str(root),
}
(root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2))
if receipt["status"] != "PASS":
    raise SystemExit(1)
PY
cat "$run_root/full_mutation_suite.log"
