#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build_root=${PR71_NATIVE_BUILD_ROOT:-/var/tmp/pr71_guarded_native_20261008/build}
build_receipt=${PR71_NATIVE_BUILD_RECEIPT:-/var/tmp/pr71_guarded_native_20261008/build_receipt.json}
reference_run=/var/tmp/pr70_native_volume_trace_20261008_v3/run
reference_receipt=$reference_run/run_receipt.json
evidence_path=${PR71_NATIVE_EVIDENCE_PATH:-$repo_root/docs/evidence/pr71_guarded_native_integration_20261008.json}
source_receipt=${PR71_NATIVE_SOURCE_RECEIPT:-/var/tmp/pr71_guarded_native_source.diePOE/composed_checked.F.composition.json}
observer_source=${PR71_NATIVE_OBSERVER_SOURCE:-/var/tmp/pr71_guarded_native_source.diePOE/native_observer.F}
observer_patch=${PR71_NATIVE_OBSERVER_PATCH:-/var/tmp/pr71_guarded_native_source.diePOE/native_observer.patch}
expected_combined_sha256=6245969c87f6568cad3b6c6afddc0d1bdfe84a31baa1cee10a465b663c88d716
expected_observer_sha256=e6f9dbf8960111737aa2e56e7a02043f649cba79bebbf2a1b047bafec4ca806e
timeout_seconds=${PR71_NATIVE_TIMEOUT_SECONDS:-900}

for path in "$evidence_path"; do
  if [[ -e $path || -L $path ]]; then
    printf 'refusing to overwrite native evidence: %s\n' "$path" >&2
    exit 2
  fi
done
[[ -f $build_receipt && -f $reference_receipt && -f $source_receipt ]]
[[ $(sha256sum "$observer_source" | cut -d' ' -f1) == "$expected_observer_sha256" ]]
[[ $(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["checked_source_sha256"])' "$source_receipt") == "$expected_combined_sha256" ]]

run_root=$(mktemp -d /var/tmp/pr71_guarded_native_run.XXXXXX)
printf 'RUN_ROOT %s\n' "$run_root"
python3 - "$reference_run" "$reference_receipt" "$run_root" "$build_root/executable/wrf.exe" <<'PY'
import hashlib,json,shutil,sys
from pathlib import Path

source_root,receipt_path,run_root,executable=map(Path,sys.argv[1:])
receipt=json.loads(receipt_path.read_text())
if receipt.get("input_integrity") != "PASS":
    raise SystemExit("retained native inputs are not integrity-verified")
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
    raise SystemExit("staged executable hash mismatch")
PY

source "$repo_root/tests/intel_toolchain.sh"
python3 - "$repo_root" "$run_root" "$reference_receipt" "$build_receipt" \
  "$evidence_path" "$source_receipt" "$observer_source" "$observer_patch" \
  "$timeout_seconds" <<'PY'
from __future__ import annotations
import hashlib,json,os,re,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path

repo,run_root,reference_receipt,build_receipt,evidence,source_receipt,observer_source,observer_patch=map(Path,sys.argv[1:9])
timeout_seconds=int(sys.argv[9])
reference=json.loads(reference_receipt.read_text())
build=json.loads(build_receipt.read_text())
composition=json.loads(source_receipt.read_text())
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
if build.get("schema") != "pr71_partialhost_native_build_v1":
    raise SystemExit("unexpected partialhost build receipt schema")
if build["source"]["sha256"] != "e6f9dbf8960111737aa2e56e7a02043f649cba79bebbf2a1b047bafec4ca806e":
    raise SystemExit("built observer source differs from the frozen source")
if build["link"]["executable_sha256"] != sha(run_root/"wrf.exe"):
    raise SystemExit("staged executable differs from fresh partialhost build")
if composition.get("checked_source_sha256") != "6245969c87f6568cad3b6c6afddc0d1bdfe84a31baa1cee10a465b663c88d716":
    raise SystemExit("guarded composition receipt source hash mismatch")
link_driver=Path(build["link"]["argv"][0])
link_version=subprocess.run([str(link_driver),"-V"],text=True,capture_output=True,check=False)

sys.path.insert(0,str(repo/"tools"))
import run_isolated_native
prior_command=reference["command"]
if len(prior_command)!=3 or prior_command[:2]!=["bash","-c"]:
    raise SystemExit("retained native launch command has unexpected shape")
command=["timeout","--signal=TERM","--kill-after=30s",f"{timeout_seconds}s",*prior_command]
inputs=[run_root/item["path"] for item in reference["input_after"]]
expected_output_names=[item["path"] for item in reference["outputs"]]
result=run_isolated_native.run_isolated(run_root,inputs,expected_output_names,command)
log_paths=[run_root/name for name in ("candidate_run.log","rsl.out.0000","rsl.error.0000")]
logs={path.name:path.read_text(errors="replace") for path in log_paths if path.is_file()}
log_text="\n".join(logs.values())
log_lines=log_text.splitlines()
step_rejects=[]
for index,line in enumerate(log_lines):
    if "PR71_STEP_COUNT_REJECT" in line:
        marker=re.search(r"PR71_STEP_COUNT_REJECT(_ICE)?\s+i,k,rate,dt=",line)
        if marker:
            payload=line[marker.end():]
            if index+1<len(log_lines): payload += " " + log_lines[index+1]
            numbers=re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?",payload)
            if len(numbers)>=4:
                step_rejects.append({"kind":"ICE" if marker.group(1) else "LIQUID",
                    "i":int(numbers[0]),"k":int(numbers[1]),
                    "rate":float(numbers[2].replace("D","E").replace("d","e")),
                    "dt":float(numbers[3].replace("D","E").replace("d","e")),
                    "diagnostic_lines":log_lines[index:index+2]})
fatal_lines=[line.strip() for line in log_text.splitlines()
    if "invalid PR71 KDM6" in line or "ERROR STOP" in line]
present={item["path"]:item["sha256"] for item in result["outputs"]}
missing=[name for name in expected_output_names if name not in present]
if result["input_integrity"]!="PASS":
    status="INPUT_INTEGRITY_FAILURE"
elif step_rejects and fatal_lines and result["returncode"]!=0:
    status="EXPECTED_STEP_COUNT_CONTRACT_REJECT"
elif "timed out" in log_text.lower() or result["returncode"] in (124,137,143):
    status="INCOMPLETE_TIMEOUT"
elif result["returncode"]==0:
    status="PARTIALHOST_FIRSTCALL_RETURNED"
else:
    status="UNCLASSIFIED_NATIVE_FAILURE"
receipt={
    "schema":"pr71_guarded_native_integration_v1",
    "recorded_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
    "host_scope":"partialhost; selected KDM6 object rebuilt and linked with retained host objects and libraries",
    "native_status":status,"scientific_approval":"FAIL_OPEN",
    "full_physics_conclusion":"NOT_ESTABLISHED",
    "source_lineage":{
        "composition_receipt":str(source_receipt),"composition_receipt_sha256":sha(source_receipt),
        "combined_source_sha256":composition["checked_source_sha256"],
        "base_source_sha256":composition["base_pr71_source_sha256"],
        "step_count_patch_sha256":composition["step_count_patch_sha256"],
        "observer_source":str(observer_source),"observer_source_sha256":sha(observer_source),
        "observer_patch":str(observer_patch),"observer_patch_sha256":sha(observer_patch),
    },
    "build_receipt_path":str(build_receipt),"build_receipt_sha256":sha(build_receipt),
    "link_driver":{"path":str(link_driver),"sha256":sha(link_driver),
        "version_output":(link_version.stdout+link_version.stderr).strip(),
        "version_returncode":link_version.returncode},
    "partialhost_build":build,
    "retained_input_run_receipt":str(reference_receipt),"retained_input_run_receipt_sha256":sha(reference_receipt),
    "run_root":str(run_root),"run_command":command,"timeout_seconds":timeout_seconds,
    "run_returncode":result["returncode"],"input_integrity":result["input_integrity"],
    "inputs":result["inputs"],"outputs_present_sha256":present,"expected_output_paths_missing":missing,
    "output_isolation":result["output_isolation"],"output_issues":result["output_issues"],
    "step_count_rejections":step_rejects,"fatal_lines":fatal_lines,
    "native_log_paths":{name:str(run_root/name) for name in logs},
    "native_log_sha256":{name:sha(run_root/name) for name in logs},
    "limitations":[
        "This is a partialhost research firstcall with retained host objects and external libraries; it is not a complete clean host rebuild.",
        "The declared-path runner checks only the listed inputs and outputs and is not an OS sandbox.",
        "A controlled step-count rejection verifies integer-domain protection before NINT; it does not establish physical validity or model closure.",
    ],
    "isolation_receipt":result,
}
evidence.parent.mkdir(parents=True,exist_ok=True)
with evidence.open("x",encoding="utf-8") as stream:
    json.dump(receipt,stream,indent=2,sort_keys=True);stream.write("\n")
print(f"PR71_NATIVE_STATUS {status}")
print(f"PR71_NATIVE_RETURN_CODE {result['returncode']}")
print(f"PR71_NATIVE_INPUT_INTEGRITY {result['input_integrity']}")
print(f"PR71_NATIVE_STEP_COUNT_REJECT {step_rejects[:1]}")
print(f"PR71_NATIVE_OUTPUTS_PRESENT {len(present)} MISSING {len(missing)}")
print(f"PR71_NATIVE_EVIDENCE {evidence}")
PY
