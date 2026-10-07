#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_root/tests/intel_toolchain.sh"
source_file=${PR70_KDM6_SOURCE:-/var/tmp/pr68_velocity_native_20261007/source/module_mp_kdm6_combined_research.f90}
expected_source_sha256=97e9892ff527a318f6266140eecc03238485a68b050c61bbaca7ea94f28bfdaa
patch_file=$repo_root/docs/evidence/pr70_coupled_process_cutoff_search_20261008.patch
if [[ ! -f $source_file ]]; then
  printf 'captured PR68 KDM6 source is required: %s\n' "$source_file" >&2
  exit 2
fi
actual_source_sha256=$(sha256sum "$source_file" | cut -d' ' -f1)
if [[ $actual_source_sha256 != "$expected_source_sha256" ]]; then
  printf 'unexpected captured PR68 source hash: %s\n' "$actual_source_sha256" >&2
  exit 2
fi

work_dir=$(mktemp -d /var/tmp/cloud_bal_pr70_process.XXXXXX)
printf 'WORK_DIR %s\n' "$work_dir"
cp "$source_file" "$work_dir/module_mp_kdm6_combined_research.f90"
patch --fuzz=0 -p0 -d "$work_dir" < "$patch_file" > "$work_dir/patch.log"
python3 - "$work_dir/module_mp_kdm6_combined_research.f90" "$work_dir" <<'PY'
from pathlib import Path
import re
import sys

source_path, work_dir = map(Path, sys.argv[1:3])
source = source_path.read_text()
checks = (
    "call kdm6_rain_process_fraction(rain_q_fixed,rain_q_process",
    "factor,rain_process_feasible,rain_process_search_status)",
    "call kdm6_rain_process_state_valid(rain_q_fixed,rain_n_fixed,brs(i,k)",
    "KDM6 cold process status=UNSUPPORTED_VOLUME_RATE",
    "KDM6 cold process status=NO_FEASIBLE_STEP",
    "KDM6 cold process status=SEARCH_FAILURE",
    "KDM6 stored cold endpoint status=INVALID_STORED_STATE",
    "if (q(3).eq.0.0)",
    "if (n(3).ne.0.0) then",
    "call clip(real(t_fixed,8),real(t_process,8),lo,hi,valid_interval)",
    "if (t_trial.le.0.0)",
    "if (temperature.le.0.0) return",
)
for fragment in checks:
    if fragment not in source:
        raise SystemExit(f"PR70 source check missing: {fragment}")
if "q_fixed(3)/rho_min-bg_fixed" in source:
    raise SystemExit("stale PR69 helper unexpectedly remains")
blocks=[]
for name,kind in (
    ("kdm6_mass_volume_rate","subroutine"),
    ("kdm6_rain_process_fraction","subroutine"),
    ("kdm6_rain_process_state_valid","subroutine"),
    ("constrain_process_margin","subroutine"),
    ("kdm6_shared_pair_fraction","real function"),
):
    pattern=rf"(?ms)^\s*{re.escape(kind)} {name}\b.*?^\s*end (?:subroutine|function) {name}\s*$"
    match=re.search(pattern,source)
    if not match:
        raise SystemExit(f"missing source helper: {name}")
    blocks.append(match.group().strip())
(work_dir/"pr70_helper.f90").write_text(
    "module pr70_helper\ncontains\n"+"\n\n".join(blocks)+"\nend module pr70_helper\n")
print("PR70 source coupling and helper extraction checks passed")
PY
python3 "$repo_root/tests/generate_pr70_source_harness.py" \
  "$work_dir/module_mp_kdm6_combined_research.f90" \
  "$work_dir/pr70_helper.f90" "$work_dir/test_pr70_source_excerpt.f90"

for opt in O0 O2; do
  build_dir="$work_dir/$opt"
  mkdir "$build_dir"
  cp "$work_dir/pr70_helper.f90" "$repo_root/tests/test_pr70_cutoff_search.f90" \
    "$work_dir/test_pr70_source_excerpt.f90" "$build_dir/"
  cd "$build_dir"
  if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  run_logged() {
    local label=$1
    shift
    printf '%q ' "$@" > "$label.argv"
    printf '\n' >> "$label.argv"
    if ! "$@" > "$label.log" 2>&1; then
      cat "$label.log" >&2
      return 1
    fi
  }
  run_logged helper.compile "$CLOUD_BAL_FC" "${flags[@]}" -c pr70_helper.f90
  run_logged cutoff.compile "$CLOUD_BAL_FC" "${flags[@]}" -c test_pr70_cutoff_search.f90
  run_logged cutoff.link "$CLOUD_BAL_FC" "${flags[@]}" -o cutoff.exe test_pr70_cutoff_search.o pr70_helper.o
  run_logged cutoff.run ./cutoff.exe
  cat cutoff.run.log
  run_logged excerpt.compile "$CLOUD_BAL_FC" "${flags[@]}" -c test_pr70_source_excerpt.f90
  run_logged excerpt.link "$CLOUD_BAL_FC" "${flags[@]}" -o excerpt.exe test_pr70_source_excerpt.o pr70_helper.o
  run_logged excerpt.run ./excerpt.exe
  cat excerpt.run.log
  printf './excerpt.exe bad-temperature\n' > excerpt.bad_temperature.argv
  set +e
  ./excerpt.exe bad-temperature > excerpt.bad_temperature.log 2>&1
  bad_temperature_status=$?
  set -e
  if [[ $bad_temperature_status -eq 0 ]] || ! grep -Fq "status=INVALID_STORED_STATE" excerpt.bad_temperature.log; then
    cat excerpt.bad_temperature.log >&2
    printf 'nonpositive stored Kelvin temperature was not rejected by the source-extracted gate\n' >&2
    exit 1
  fi
done

python3 - "$repo_root" "$work_dir" "$source_file" <<'PY'
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
repo,work,source=map(Path,sys.argv[1:4])
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
bound={
  "captured_source":source,
  "patch":repo/"docs/evidence/pr70_coupled_process_cutoff_search_20261008.patch",
  "runner":repo/"tests/run_pr70_coupled_process.sh",
  "source_harness_generator":repo/"tests/generate_pr70_source_harness.py",
  "cutoff_test":repo/"tests/test_pr70_cutoff_search.f90",
  "report":repo/"docs/PR70_CUTOFF_SEARCH_20261008.md",
  "prior_temperature_reproduction_receipt":repo/"docs/evidence/pr70_temperature_finite_only_repro_20261008.json",
  "patched_source":work/"module_mp_kdm6_combined_research.f90",
  "generated_helper":work/"pr70_helper.f90",
  "generated_source_harness":work/"test_pr70_source_excerpt.f90",
  "patch_log":work/"patch.log",
}
for opt in ("O0","O2"):
  for file in ("cutoff.exe","excerpt.exe"):
    bound[f"{opt}_{file}"]=work/opt/file
  for name in ("helper.compile","cutoff.compile","cutoff.link","cutoff.run",
               "excerpt.compile","excerpt.link","excerpt.run","excerpt.bad_temperature"):
    bound[f"{opt}_{name}_log"]=work/opt/(name+".log")
    bound[f"{opt}_{name}_argv"]=work/opt/(name+".argv")
receipt={
 "schema":"pr70_coupled_process_cutoff_validation_v1",
 "session_day":"2026-10-08",
 "timezone":"Asia/Seoul",
 "recorded_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
 "captured_source_sha256":sha(source),
 "patch_sha256":sha(bound["patch"]),
 "patched_source_sha256":sha(bound["patched_source"]),
 "prior_temperature_reproduction_receipt":{
   "path":"docs/evidence/pr70_temperature_finite_only_repro_20261008.json",
   "sha256":sha(bound["prior_temperature_reproduction_receipt"]),
   "result":"REPRODUCED"},
 "compiler":subprocess.check_output([os.environ["CLOUD_BAL_FC"],"--version"],text=True,stderr=subprocess.STDOUT).splitlines()[0],
 "compiler_flags":{
   "O0":["-stand","f08","-warn","all","-check","all","-fpe0","-traceback","-O0","-fp-model","strict","-fimf-arch-consistency=true","-no-ftz"],
   "O2":["-stand","f08","-warn","all","-fpe0","-traceback","-O2","-fp-model","strict","-fimf-arch-consistency=true","-no-ftz"]},
 "scratch_work_dir":str(work),
 "files_sha256":{key:sha(path) for key,path in bound.items()},
 "commands_argv":{str(path.relative_to(work)):path.read_text().strip() for path in bound.values() if path.name.endswith(".argv")},
 "checks":{
   "captured_source_identity":"PASS",
   "strict_qcrmin_cutoff_counterexample":"PASS",
   "created_activity_interval_after_q_zero":"PASS",
   "exact_q_n_zero_breakpoint":"PASS",
   "pending_cleanup_pretransfer_exception_and_posttransfer_stored_gate":"PASS",
   "finite_nonpositive_kelvin_is_rejected":"PASS",
   "temperature_zero_breakpoint_and_positive_crossing":"PASS",
   "source_extracted_stored_nonpositive_kelvin_rejection":"PASS",
   "rain_zero_mass_orphan_number_rejected":"PASS",
   "no_feasible_step_distinct_from_search_failure":"PASS",
   "stored_state_predicate_independent_of_step_search":"PASS",
   "source_extracted_native_cold_update_O0_O2":"PASS",
   "Intel_ifx_O0":"PASS",
   "Intel_ifx_O2":"PASS"}}
(work/"validation_receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
PY
cp "$work_dir/validation_receipt.json" "$repo_root/docs/evidence/pr70_coupled_process_cutoff_validation_20261008.json"
printf 'PR70 coupled-process validation passed; receipt: docs/evidence/pr70_coupled_process_cutoff_validation_20261008.json\n'
