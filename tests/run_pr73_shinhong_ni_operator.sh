#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source_file=${PR73_SHINHONG_SOURCE:-/var/tmp/pr73_pbl_research/source_after/module_bl_shinhong_pr65.F}
evidence_path=${PR73_SHINHONG_OPERATOR_EVIDENCE:-$repo_root/docs/evidence/pr73_shinhong_ni_operator_20261008.json}
if [[ ! -f $source_file ]]; then
  printf 'PR73 Shinhong research source is required: %s\n' "$source_file" >&2
  exit 2
fi
if [[ -e $evidence_path || -L $evidence_path ]]; then
  printf 'refusing to overwrite PR73 operator evidence: %s\n' "$evidence_path" >&2
  exit 2
fi
source "$repo_root/tests/intel_toolchain.sh"
source_hash=$(sha256sum "$source_file" | cut -d' ' -f1)
if [[ $source_hash != 5fbe821bb3b82e406fee459e5b2d745156ea1a030b5f0ecd2c7191025f296553 ]]; then
  printf 'unexpected research Shinhong source hash: %s\n' "$source_hash" >&2
  exit 2
fi
work_dir=$(mktemp -d /var/tmp/pr73_shinhong_ni_operator.XXXXXX)
printf 'WORK_DIR %s\n' "$work_dir"
for opt in O0 O2; do
  build_dir=$work_dir/$opt
  mkdir "$build_dir"
  cp "$source_file" "$build_dir/module_bl_shinhong.F"
  cp "$repo_root/tests/fixtures/kdm6_wrapper/module_wrf_error.F" \
     "$repo_root/tests/fixtures/kdm6_wrapper/module_model_constants.F" \
     "$repo_root/tests/fixtures/kdm6_wrapper/wrf_debug_stub.f90" "$build_dir/"
  cp "$repo_root/tests/test_pr73_shinhong_ni_operator.f90" "$build_dir/"
  cd "$build_dir"
  if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  "$CLOUD_BAL_FC" "${flags[@]}" -free -fpp -c module_wrf_error.F module_model_constants.F >build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -free -fpp -c module_bl_shinhong.F >>build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -c wrf_debug_stub.f90 >>build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -c test_pr73_shinhong_ni_operator.f90 >>build.log 2>&1
  "$CLOUD_BAL_FC" "${flags[@]}" -o test.exe \
    test_pr73_shinhong_ni_operator.o module_bl_shinhong.o module_model_constants.o wrf_debug_stub.o >>build.log 2>&1
  ./test.exe >run.log 2>&1
  cat run.log
done

python3 - "$repo_root" "$work_dir" "$source_file" "$CLOUD_BAL_FC" "$evidence_path" <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

repo, work = map(Path, sys.argv[1:3])
source, compiler, output = Path(sys.argv[3]), sys.argv[4], Path(sys.argv[5])
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
profiles = {}
for opt in ("O0", "O2"):
    build = work / opt
    profiles[opt] = {
        "module_object_sha256": sha(build / "module_bl_shinhong.o"),
        "executable_sha256": sha(build / "test.exe"),
        "build_log_sha256": sha(build / "build.log"),
        "run_log_sha256": sha(build / "run.log"),
        "observed": (build / "run.log").read_text().strip(),
    }
    if "PR73_SHINHONG_QNI_SAME_OPERATOR_PASS" not in profiles[opt]["observed"]:
        raise SystemExit(f"missing operator pass marker at {opt}")
result = {
    "schema": "pr73_shinhong_qni_same_operator_v1",
    "classification": "pinned-ifx numerical routine test on research source; not coupled WRF runtime validation",
    "source": str(source),
    "source_sha256": sha(source),
    "patch_sha256": sha(repo / "docs/evidence/pr73_shinhong_ni_research.patch"),
    "fixture_sha256": sha(repo / "tests/test_pr73_shinhong_ni_operator.f90"),
    "runner_sha256": sha(repo / "tests/run_pr73_shinhong_ni_operator.sh"),
    "toolchain_profile_sha256": sha(repo / "tests/intel_toolchain.sh"),
    "compiler": compiler,
    "compiler_version": subprocess.run([compiler, "--version"], check=True, text=True,
                                         capture_output=True).stdout.splitlines()[0],
    "optimization_profiles": ["O0 strict with runtime checks", "O2 strict"],
    "work_dir": str(work),
    "profiles": profiles,
    "assertion": "QI and scaled QNI (2**30 times QI, within an ice PSD mean-mass interval) receive proportionally matched, nonzero tendencies; division of QNI tendency by 2**30 matches QI exactly with QNI alone and when NC occupies channel 4 and QNI channel 5 simultaneously. Both channels create a positive recipient tendency from zero initial values, and a 60 s update remains nonnegative. Optional output halos are zeroed. A supplied disabled QNI output and QNI enabled without the optional paired QI tendency are both fully zeroed after sentinel initialization.",
    "limitations": ["The test calls the selected Shinhong routine with a manufactured profile; it does not build the WRF driver or validate native QI/QNI at (133,2,1).", "It does not establish the production dry-air carrier or whole-scheme conservation."],
}
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print("PR73_OPERATOR_RECEIPT", output)
PY
