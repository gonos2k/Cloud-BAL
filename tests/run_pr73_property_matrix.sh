#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source_file=$repo_root/docs/evidence/pr72_combined_native_first_reject_20261008/frozen_combined_source.F
evidence_dir=${PR73_PROPERTY_MATRIX_EVIDENCE:-$repo_root/docs/evidence/pr73_property_matrix_20261008}
if [[ -e $evidence_dir || -L $evidence_dir ]]; then
  printf 'refusing to overwrite property matrix evidence: %s\n' "$evidence_dir" >&2
  exit 2
fi
[[ -f $source_file ]]
source "$repo_root/tests/intel_toolchain.sh"
work_root=$(mktemp -d /var/tmp/pr73_property_matrix.XXXXXX)
printf 'WORK_ROOT %s\n' "$work_root"
composed=$work_root/property_matrix_source.F
python3 "$repo_root/tools/pr73_property_matrix_source.py" "$source_file" "$composed" \
  "$work_root/property_matrix_source.patch" "$work_root/source_receipt.json"
fixture=$repo_root/tests/fixtures/kdm6_wrapper
test_source=$repo_root/tests/test_pr73_property_matrix.f90

for opt in O0 O2; do
  build=$work_root/$opt
  mkdir "$build"
  cp "$fixture/"*.F "$fixture/wrf_debug_stub.f90" "$build/"
  cp "$composed" "$build/module_mp_kdm6.F"
  cp "$test_source" "$build/"
  cd "$build"
  if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  compile() { "$CLOUD_BAL_FC" "${flags[@]}" "$@" >>build.log 2>&1; }
  compile -free -fpp -c module_wrf_error.F
  compile -free -fpp -c module_model_constants.F
  compile -free -fpp -c module_mp_radar.F
  compile -free -fpp -DTEST_DIRECT_VOLUME -DTEST_PR73_PROPERTY_MATRIX -DRWORDSIZE=4 \
    -convert big_endian -c module_mp_kdm6.F
  "$CLOUD_BAL_FC" "${CLOUD_BAL_FIXED_FLAGS[@]}" -fixed -fpp -c libmassv.F >>build.log 2>&1
  compile -c wrf_debug_stub.f90
  compile -DTEST_DIRECT_VOLUME -c test_pr73_property_matrix.f90
  compile -o test.exe test_pr73_property_matrix.o module_mp_kdm6.o module_mp_radar.o \
    module_model_constants.o libmassv.o wrf_debug_stub.o
  ./test.exe >run.log 2>&1
  grep -q '^PR73_ACTUAL_KDM6_PROPERTY_MATRIX PASS$' run.log
  [[ $(grep -c 'PR73_REFERENCE_MASK' run.log) == 16 ]]
  [[ $(grep -c 'PR73_REENTRY_MASK' run.log) == 16 ]]
  printf 'PASS %s\n' "$opt"
done

python3 - "$work_root" "$repo_root" "$source_file" "$evidence_dir" "$CLOUD_BAL_FC" <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

work, repo, source, evidence, compiler = map(Path, sys.argv[1:])
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
if sha(source) != "1fbd9d5cbc32dc5772682078b4efc63b3dafb28a79499e318faf9520fc55e819":
    raise SystemExit("frozen source hash mismatch")
result = {
    "schema": "pr73_actual_property_matrix_v1",
    "classification": "actual KDM6 cloud/ice/rain/graupel property and terminal-velocity construction with test-only early return; no timestep/process completion",
    "frozen_source": str(source),
    "frozen_source_sha256": sha(source),
    "source_transform": str(repo / "tools/pr73_property_matrix_source.py"),
    "source_transform_sha256": sha(repo / "tools/pr73_property_matrix_source.py"),
    "test_source": str(repo / "tests/test_pr73_property_matrix.f90"),
    "test_source_sha256": sha(repo / "tests/test_pr73_property_matrix.f90"),
    "runner_sha256": sha(repo / "tests/run_pr73_property_matrix.sh"),
    "source_composition": json.loads((work / "source_receipt.json").read_text()),
    "compiler": str(compiler),
    "compiler_version": subprocess.run([str(compiler), "--version"], check=True,
        text=True, capture_output=True).stdout.splitlines()[0],
    "toolchain_profile_sha256": sha(repo / "tests/intel_toolchain.sh"),
    "optimization_profiles": ["O0", "O2"],
    "mask_order": ["rain", "cloud", "ice", "graupel"],
    "mask_count": 16,
    "per_mask_sequence": "clean reference, then active mask 15 followed by poisoned-output target re-entry; exact property record equality required",
    "checked_actual_properties": ["cloud slope moments", "rain slope and number velocity", "ice slope and number velocity", "graupel status/density/properties/velocity"],
    "cases": {},
    "limitations": [
        "The source transform adds only a preprocessor-guarded capture and early return; production preprocessing has no hook.",
        "The hook returns after terminal velocities are converted to rate arrays and before substep counting, rate application, or microphysical processes; this is a property-stage test, not a full-process success.",
        "The first source n0 reconstruction occurs after physical rate application in this frozen source, so n0r/n0c/n0i are not captured by this early property test.",
        "Graupel active state uses QG/BG=400 kg m-3; broader graupel density support is not established.",
        "Properties are captured from the first active i,k cell and one j call in the test domain."
    ],
}
for opt in ("O0", "O2"):
    directory = work / opt
    log = directory / "run.log"
    source_copy = directory / "module_mp_kdm6.F"
    obj = directory / "module_mp_kdm6.o"
    exe = directory / "test.exe"
    result["cases"][opt] = {
        "result": "PASS",
        "instrumented_source_sha256": sha(source_copy),
        "object_sha256": sha(obj),
        "executable_sha256": sha(exe),
        "build_log_sha256": sha(directory / "build.log"),
        "run_log_sha256": sha(log),
        "run_log": str(log),
        "reference_mask_records": 16,
        "reentry_mask_records": 16,
    }
    if "PR73_ACTUAL_KDM6_PROPERTY_MATRIX PASS" not in log.read_text():
        raise SystemExit(f"missing pass marker in {opt}")
evidence.mkdir(parents=True)
receipt = work / "property_matrix_receipt.json"
receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
(evidence / "receipt.json").write_text(receipt.read_text())
(evidence / "source_transform.patch").write_bytes((work / "property_matrix_source.patch").read_bytes())
for opt in ("O0", "O2"):
    (evidence / f"{opt}_run.log").write_bytes((work / opt / "run.log").read_bytes())
print("PR73_ACTUAL_PROPERTY_MATRIX_O0_O2_PASS")
print("PR73_RECEIPT", receipt)
print("PR73_EVIDENCE", evidence / "receipt.json")
PY
