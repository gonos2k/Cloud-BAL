#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source_file=${PR70_KDM6_SOURCE:-/var/tmp/pr68_velocity_native_20261007/source/module_mp_kdm6_combined_research.f90}
process_patch=$repo_root/docs/evidence/pr70_coupled_process_cutoff_search_20261008.patch
process_patch_sha256=5f1b75925ec803838f5b3cfa81012336f4d21727073c5d8c0703fb70ddc37670
patch_file=$repo_root/docs/evidence/pr71_particle_output_contract_20261008.patch
inventory_file=$repo_root/docs/evidence/pr71_particle_output_contract_20261008.output_inventory.json
receipt_file=${PR71_RECEIPT_FILE:-$repo_root/docs/evidence/pr71_particle_output_contract_20261008.json}

source "$repo_root/tests/intel_toolchain.sh"
work_dir=$(mktemp -d /var/tmp/pr71_particle_output_contract.XXXXXX)
if [[ -e $receipt_file && -z ${PR71_RECEIPT_FILE:-} ]]; then
  run_tag=${work_dir##*.}
  receipt_file=$repo_root/docs/evidence/pr71_particle_output_contract_20261008.run_${run_tag}.json
fi
printf 'WORK_DIR %s\n' "$work_dir"

python3 "$repo_root/tools/pr70_compose_selected_kdm6.py" \
  "$source_file" "$process_patch" "$work_dir/composed_pr70.F" \
  --expected-process-patch-sha256 "$process_patch_sha256" >"$work_dir/pr70_compose.log" 2>&1
python3 "$repo_root/tools/pr71_particle_output_contract.py" \
  "$work_dir/composed_pr70.F" "$patch_file" \
  --inventory-out "$inventory_file" >"$work_dir/pr71_generate.log" 2>&1

mkdir "$work_dir/apply"
cp "$work_dir/composed_pr70.F" "$work_dir/apply/composed_pr70.F"
patch --fuzz=0 -p0 -d "$work_dir/apply" <"$patch_file" >"$work_dir/patch.log" 2>&1
PR71_CONTRACT_SOURCE="$work_dir/apply/composed_pr70.F" \
  python3 "$repo_root/tests/test_pr71_particle_output_contract.py" \
  "$work_dir/progb_output_contract_test.f90" >"$work_dir/source_audit.log" 2>&1

cd "$work_dir"
printf 'ARGV' >build.log
printf ' %q' "$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" -free \
  -o progb_output_contract_test.exe progb_output_contract_test.f90 >>build.log
printf '\n' >>build.log
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" -free \
  -o progb_output_contract_test.exe progb_output_contract_test.f90 >>build.log 2>&1
./progb_output_contract_test.exe >run.log 2>&1
cat run.log
PR71_WORK_DIR=$work_dir PR71_PATCH_FILE=$patch_file \
PR71_INVENTORY_FILE=$inventory_file PR71_RECEIPT_FILE=$receipt_file \
PR71_COMPILER=$CLOUD_BAL_FC PR71_REPO_ROOT=$repo_root python3 - <<'PY'
import hashlib
import json
import os
import subprocess
from pathlib import Path

work = Path(os.environ["PR71_WORK_DIR"])
repo = Path(os.environ["PR71_REPO_ROOT"])
patch = Path(os.environ["PR71_PATCH_FILE"])
inventory = Path(os.environ["PR71_INVENTORY_FILE"])
receipt = Path(os.environ["PR71_RECEIPT_FILE"])
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
generated = json.loads(inventory.read_text(encoding="utf-8"))
compiler = os.environ["PR71_COMPILER"]
compiler_version = subprocess.run(
    [compiler, "--version"], check=True, text=True, capture_output=True,
).stdout.splitlines()[0]
result = {
    "source_sha256": generated["source_sha256"],
    "patched_source_sha256": generated["patched_source_sha256"],
    "patch_sha256": sha(patch),
    "inventory_sha256": sha(inventory),
    "compiler": compiler,
    "compiler_version": compiler_version,
    "compiler_profile_sha256": sha(repo / "tests/intel_toolchain.sh"),
    "generator_sha256": sha(repo / "tools/pr71_particle_output_contract.py"),
    "test_sha256": sha(repo / "tests/test_pr71_particle_output_contract.py"),
    "runner_sha256": sha(repo / "tests/run_pr71_particle_output_contract.sh"),
    "harness_sha256": sha(work / "progb_output_contract_test.f90"),
    "executable_sha256": sha(work / "progb_output_contract_test.exe"),
    "work_dir": str(work),
    "harness_path": str(work / "progb_output_contract_test.f90"),
    "executable_path": str(work / "progb_output_contract_test.exe"),
    "build_argv": (work / "build.log").read_text(encoding="utf-8").splitlines()[0],
    "source_audit": (work / "source_audit.log").read_text(encoding="utf-8").strip().splitlines()[-1],
    "compile_log_sha256": sha(work / "build.log"),
    "run_log_sha256": sha(work / "run.log"),
    "logs": {
        "source_audit": {"path": str(work / "source_audit.log"), "sha256": sha(work / "source_audit.log")},
        "compile": {"path": str(work / "build.log"), "sha256": sha(work / "build.log")},
        "run": {"path": str(work / "run.log"), "sha256": sha(work / "run.log")},
    },
    "run_output": (work / "run.log").read_text(encoding="utf-8").strip(),
    "call_sites": generated["call_sites"],
}
payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
if receipt.exists() and receipt.read_bytes() != payload:
    raise SystemExit(f"refusing to overwrite different receipt: {receipt}")
if not receipt.exists():
    with receipt.open("xb") as stream:
        stream.write(payload)
PY
printf 'BUILD_LOG %s\nRUN_LOG %s\n' "$work_dir/build.log" "$work_dir/run.log"
printf 'RECEIPT %s\n' "$receipt_file"
