#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build_root=${PR71_NATIVE_BUILD_ROOT:-/var/tmp/pr71_same_source_native_20261008_v1}
build_receipt=$build_root/build_receipt.json
reference_run=/var/tmp/pr70_native_volume_trace_20261008_v3/run
reference_receipt=$reference_run/run_receipt.json
evidence_path=${PR71_NATIVE_EVIDENCE_PATH:-$repo_root/docs/evidence/pr71_same_source_native_integration_20261008.json}

if [[ -e $evidence_path || -L $evidence_path ]]; then
  printf 'refusing to overwrite PR71 native evidence: %s\n' "$evidence_path" >&2
  exit 2
fi
[[ -f $build_receipt && -f $reference_receipt ]]
run_root=$(mktemp -d /var/tmp/pr71_same_source_native_run.XXXXXX)
printf 'RUN_ROOT %s\n' "$run_root"

python3 - "$reference_run" "$reference_receipt" "$run_root" "$build_root/build/executable/wrf.exe" <<'PY'
import hashlib,json,shutil,sys
from pathlib import Path

source_root,receipt_path,run_root,executable=map(Path,sys.argv[1:])
receipt=json.loads(receipt_path.read_text())
if receipt.get("input_integrity") != "PASS":
    raise SystemExit("retained PR70 run inputs are not integrity-verified")
expected={item["path"]:item["sha256_after"] for item in receipt["input_after"]}
if any(run_root.iterdir()):
    raise SystemExit("fresh native run root is not empty")
for name,digest in expected.items():
    source=source_root/name
    target=run_root/name
    if source.is_symlink() or not source.is_file():
        raise SystemExit(f"retained input is not a regular file: {source}")
    shutil.copy2(source,target)
    actual=hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != digest:
        raise SystemExit(f"staged input hash mismatch for {name}: {actual}")
shutil.copy2(executable,run_root/"wrf.exe")
if hashlib.sha256((run_root/"wrf.exe").read_bytes()).hexdigest() != \
        hashlib.sha256(executable.read_bytes()).hexdigest():
    raise SystemExit("staged native executable hash mismatch")
PY

source "$repo_root/tests/intel_toolchain.sh"
python3 - "$repo_root" "$run_root" "$reference_receipt" "$build_receipt" "$evidence_path" <<'PY'
from __future__ import annotations
import hashlib,json,os,re,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path

repo,run_root,reference_receipt,build_receipt,evidence=map(Path,sys.argv[1:])
reference=json.loads(reference_receipt.read_text())
build=json.loads(build_receipt.read_text())
if build.get("schema") != "pr71_partialhost_native_build_v1":
    raise SystemExit("unexpected native build receipt schema")
if build["source"]["sha256"] != "d57a2bb54ab6e2709820856025c6ae365e8d152e812160abef43ea52d312437b":
    raise SystemExit("observer source does not match the frozen PR71 instrumentation")
if build["link"]["executable_sha256"] != hashlib.sha256((run_root/"wrf.exe").read_bytes()).hexdigest():
    raise SystemExit("staged executable differs from the fresh partialhost build")

sys.path.insert(0,str(repo/"tools"))
import run_isolated_native as module
prior_command=reference["command"]
if len(prior_command) != 3 or prior_command[:2] != ["bash","-c"]:
    raise SystemExit("retained native launch command has an unexpected shape")
command_text=prior_command[2].replace("candidate_run.log","candidate_run.log")
command=["bash","-c",command_text]
input_paths=[run_root/item["path"] for item in reference["input_after"]]
expected_output_names=[item["path"] for item in reference["outputs"]]
result=module.run_isolated(
    run_root,input_paths,expected_output_names,command,
)

log_paths=[run_root/name for name in ("candidate_run.log","rsl.out.0000","rsl.error.0000")]
logs={path.name:path.read_text(errors="replace") for path in log_paths if path.is_file()}
log_text="\n".join(logs.values())
rejects=[]
for line in log_text.splitlines():
    if line.startswith("PR71_PROGB_REJECT "):
        values=line.split()
        if len(values) == 8:
            rejects.append({
                "stage_callsite_index":int(values[1]),"lat":int(values[2]),
                "i":int(values[3]),"k":int(values[4]),"status":int(values[5]),
                "qg_raw":float(values[6]),"bg_raw":float(values[7]),
            })
fatal_lines=[line.strip() for line in log_text.splitlines()
             if "ProgB transient PSD state rejected" in line or
                "ProgB unsupported PSD state rejected" in line or
                "ProgB invalid output status" in line or "ERROR STOP" in line]
present={item["path"]:item["sha256"] for item in result["outputs"]}
missing=[name for name in expected_output_names if name not in present]
native_status=("EXPECTED_CONTRACT_REJECT" if result["returncode"] != 0 and rejects and fatal_lines
               else "UNCLASSIFIED_NATIVE_RESULT")
if result["input_integrity"] != "PASS":
    native_status="INPUT_INTEGRITY_FAILURE"
receipt={
    "schema":"pr71_same_source_native_integration_v1",
    "recorded_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
    "host_scope":"partialhost; fresh selected-KDM6 object/archive-member rebuild linked against retained host objects and external libraries",
    "native_status":native_status,
    "scientific_approval":"FAIL_OPEN",
    "full_physics_conclusion":"NOT_ESTABLISHED",
    "combined_source_sha256":"af26db0eeec3b4cfa08f7ba4df7149af1b2b603704fefa73d979cc50e72b7706",
    "validity_patch_sha256":"72a42906bdd97c31d75f4f333e697054f9cf38ddc31f65dd4885b2a8f486dbfa",
    "observer_patch_sha256":hashlib.sha256((build_root:=Path(build["base"]).parent)/"pr71_rejection_observer.patch").hexdigest(),
    "observer_source_sha256":build["source"]["sha256"],
    "observer_transform_sha256":hashlib.sha256((build_root/"observer_transform.log").read_bytes()).hexdigest(),
    "build_receipt_path":str(build_receipt),
    "build_receipt_sha256":hashlib.sha256(build_receipt.read_bytes()).hexdigest(),
    "partialhost_build":build,
    "retained_input_run_receipt":str(reference_receipt),
    "retained_input_run_receipt_sha256":hashlib.sha256(reference_receipt.read_bytes()).hexdigest(),
    "run_root":str(run_root),
    "run_command":command,
    "run_returncode":result["returncode"],
    "input_integrity":result["input_integrity"],
    "input_hashes_before_after":result["inputs"],
    "output_isolation":result["output_isolation"],
    "output_issues":result["output_issues"],
    "outputs_present_sha256":present,
    "expected_output_paths_missing":missing,
    "first_rejection_diagnostics":rejects[:1],
    "rejection_record_count":len(rejects),
    "fatal_lines":fatal_lines,
    "native_log_sha256":{name:hashlib.sha256((run_root/name).read_bytes()).hexdigest() for name in logs},
    "native_log_paths":{name:str(run_root/name) for name in logs},
    "diagnostic_scope":"Observer-only probe reads status/QG/BG immediately after ProgB and before slope consumers; it does not alter model state. Stage is the ordered ProgB callsite number, not a physical timestep label.",
    "limitations":[
        "Partialhost research run; no clean full-physics build or production-source equivalence claim.",
        "External MPI, WRF, NetCDF and host link dependencies remain retained references; they are not independently rebuilt or hash-pinned as a complete dependency closure.",
        "Only declared paths are monitored by the isolated runner; undeclared native outputs are not protected.",
    ],
    "isolation_receipt":result,
}
evidence.parent.mkdir(parents=True,exist_ok=True)
with evidence.open("x") as stream:
    json.dump(receipt,stream,indent=2,sort_keys=True)
    stream.write("\n")
print(f"PR71_NATIVE_STATUS {native_status}")
print(f"PR71_NATIVE_RETURN_CODE {result['returncode']}")
print(f"PR71_NATIVE_INPUT_INTEGRITY {result['input_integrity']}")
print(f"PR71_NATIVE_OUTPUTS_PRESENT {len(present)} MISSING {len(missing)}")
print(f"PR71_NATIVE_FIRST_REJECTION {rejects[:1]}")
print(f"PR71_NATIVE_FATAL {fatal_lines[:3]}")
print(f"PR71_NATIVE_EVIDENCE {evidence}")
PY
