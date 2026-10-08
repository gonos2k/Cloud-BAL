#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source_file=${PR71_STEP_COUNT_BASE:-/var/tmp/pr71_same_source_native_20261008_v2/rebased/composed_pr71_base.F}
patch_file=${PR71_STEP_COUNT_PATCH:-$repo_root/docs/evidence/pr71_step_count_contract_20261008_v2.patch}
receipt_file=${PR71_STEP_COUNT_RECEIPT:-$repo_root/docs/evidence/pr71_step_count_contract_20261008_v3.json}

source "$repo_root/tests/intel_toolchain.sh"
work_dir=$(mktemp -d /var/tmp/pr71_step_count_contract.XXXXXX)
printf 'WORK_DIR %s\n' "$work_dir"

python3 "$repo_root/tools/pr71_step_count_contract.py" \
  "$source_file" "$work_dir/module_mp_kdm6_checked.F" \
  --patch-out "$patch_file" --harness-out "$work_dir/step_count_test.f90" \
  >"$work_dir/transform.log"
python3 "$repo_root/tests/test_pr71_step_count_contract.py" \
  "$work_dir/module_mp_kdm6_checked.F" "$source_file" \
  >"$work_dir/source_audit.log"

for profile in O0 O2; do
  build_dir=$work_dir/$profile
  mkdir "$build_dir"
  cd "$build_dir"
  if [[ $profile == O0 ]]; then
    flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  else
    flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  printf 'ARGV' >build.log
  printf ' %q' "$CLOUD_BAL_FC" "${flags[@]}" -free \
    -o step_count_test.exe "$work_dir/step_count_test.f90" >>build.log
  printf '\n' >>build.log
  "$CLOUD_BAL_FC" "${flags[@]}" -free -o step_count_test.exe \
    "$work_dir/step_count_test.f90" >>build.log 2>&1
  ./step_count_test.exe >run.log 2>&1
  grep -q 'PR71_STEP_COUNT_CONTRACT_PASS' run.log
done

if [[ -e $receipt_file || -L $receipt_file ]]; then
  printf 'refusing to overwrite step-count receipt: %s\n' "$receipt_file" >&2
  exit 2
fi
PR71_STEP_COUNT_REPO=$repo_root PR71_STEP_COUNT_WORK=$work_dir \
PR71_STEP_COUNT_SOURCE=$source_file PR71_STEP_COUNT_PATCH=$patch_file \
PR71_STEP_COUNT_RECEIPT=$receipt_file PR71_STEP_COUNT_COMPILER=$CLOUD_BAL_FC \
python3 - <<'PY'
import hashlib, json, os, subprocess
from pathlib import Path

repo=Path(os.environ["PR71_STEP_COUNT_REPO"])
work=Path(os.environ["PR71_STEP_COUNT_WORK"])
source=Path(os.environ["PR71_STEP_COUNT_SOURCE"])
patch=Path(os.environ["PR71_STEP_COUNT_PATCH"])
receipt=Path(os.environ["PR71_STEP_COUNT_RECEIPT"])
compiler=os.environ["PR71_STEP_COUNT_COMPILER"]
sha=lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
version=subprocess.run([compiler,"--version"],check=True,text=True,capture_output=True).stdout.splitlines()[0]
result={
  "schema":"pr71_checked_step_count_v1",
  "scope":"integer representability of the existing warm-rain and ice terminal-velocity substep counts; no physical CFL or velocity policy",
  "base_source":{"path":str(source),"sha256":sha(source)},
  "candidate_source":{"path":str(work/"module_mp_kdm6_checked.F"),"sha256":sha(work/"module_mp_kdm6_checked.F")},
  "patch":{"path":str(patch),"sha256":sha(patch)},
  "generator":{"path":str(repo/"tools/pr71_step_count_contract.py"),"sha256":sha(repo/"tools/pr71_step_count_contract.py")},
  "source_audit":{"path":str(repo/"tests/test_pr71_step_count_contract.py"),"sha256":sha(repo/"tests/test_pr71_step_count_contract.py"),"output":(work/"source_audit.log").read_text().strip()},
  "runner":{"path":str(repo/"tests/run_pr71_step_count_contract.sh"),"sha256":sha(repo/"tests/run_pr71_step_count_contract.sh")},
  "harness":{"path":str(work/"step_count_test.f90"),"sha256":sha(work/"step_count_test.f90")},
  "toolchain":{"compiler":compiler,"version":version,"profile_sha256":sha(repo/"tests/intel_toolchain.sh")},
  "profiles":{},
}
for profile in ("O0","O2"):
  directory=work / profile
  result["profiles"][profile]={
    "build_log":{"path":str(directory/"build.log"),"sha256":sha(directory/"build.log")},
    "run_log":{"path":str(directory/"run.log"),"sha256":sha(directory/"run.log")},
    "run_output":(directory/"run.log").read_text().strip(),
    "executable_sha256":sha(directory/"step_count_test.exe"),
  }
payload=(json.dumps(result,indent=2,sort_keys=True)+"\n").encode()
with receipt.open("xb") as stream:
  stream.write(payload)
print(f"PR71_STEP_COUNT_RECEIPT {receipt}")
PY
printf 'PATCH %s\nRECEIPT %s\n' "$patch_file" "$receipt_file"
