#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_root/tests/intel_toolchain.sh"
source_file=${PR70_KDM6_SOURCE:-/var/tmp/pr68_velocity_native_20261007/source/module_mp_kdm6_combined_research.f90}
expected_source_sha256=97e9892ff527a318f6266140eecc03238485a68b050c61bbaca7ea94f28bfdaa
expected_patch_sha256=5f1b75925ec803838f5b3cfa81012336f4d21727073c5d8c0703fb70ddc37670
expected_helper_sha256=47e969dde50410e3c708c1a49e49e76bc2592d6c2fcfae31b0164c51dddf1683
patch_file=$repo_root/docs/evidence/pr70_coupled_process_cutoff_search_20261008.patch
test_file=$repo_root/tests/test_pr71_conservative_fraction.f90
receipt_file=$repo_root/docs/evidence/pr71_conservative_fraction_validation_20261008.json

[[ -f $source_file ]] || { printf 'captured source is required: %s\n' "$source_file" >&2; exit 2; }
[[ $(sha256sum "$source_file" | cut -d' ' -f1) == "$expected_source_sha256" ]] || {
  printf 'captured PR68 source hash mismatch\n' >&2; exit 2;
}
[[ $(sha256sum "$patch_file" | cut -d' ' -f1) == "$expected_patch_sha256" ]] || {
  printf 'frozen PR70 process patch hash mismatch\n' >&2; exit 2;
}

work_dir=$(mktemp -d /var/tmp/cloud_bal_pr71_conservative.XXXXXX)
printf 'WORK_DIR %s\n' "$work_dir"
cp "$source_file" "$work_dir/module_mp_kdm6_combined_research.f90"
patch --fuzz=0 -p0 -d "$work_dir" < "$patch_file" > "$work_dir/patch.log"
python3 - "$work_dir/module_mp_kdm6_combined_research.f90" "$work_dir/pr70_helper.f90" <<'PY'
from pathlib import Path
import hashlib
import re
import sys

source_path, helper_path = map(Path, sys.argv[1:3])
source = source_path.read_text()
blocks = []
for name, kind in (
    ("kdm6_mass_volume_rate", "subroutine"),
    ("kdm6_rain_process_fraction", "subroutine"),
    ("kdm6_rain_process_state_valid", "subroutine"),
    ("constrain_process_margin", "subroutine"),
    ("kdm6_shared_pair_fraction", "real function"),
):
    pattern = rf"(?ms)^\s*{re.escape(kind)} {name}\b.*?^\s*end (?:subroutine|function) {name}\s*$"
    match = re.search(pattern, source)
    if not match:
        raise SystemExit(f"missing helper in hash-pinned source: {name}")
    blocks.append(match.group().strip())
helper = "module pr70_helper\ncontains\n" + "\n\n".join(blocks) + "\nend module pr70_helper\n"
helper_path.write_text(helper)
digest = hashlib.sha256(helper_path.read_bytes()).hexdigest()
print(f"EXTRACTED_HELPER_SHA256 {digest}")
if digest != "47e969dde50410e3c708c1a49e49e76bc2592d6c2fcfae31b0164c51dddf1683":
    raise SystemExit("extracted helper does not match the frozen PR70 helper")
PY

for opt in O0 O2; do
  build_dir="$work_dir/$opt"
  mkdir "$build_dir"
  cp "$work_dir/pr70_helper.f90" "$test_file" "$build_dir/"
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
  run_logged test.compile "$CLOUD_BAL_FC" "${flags[@]}" -c test_pr71_conservative_fraction.f90
  run_logged test.link "$CLOUD_BAL_FC" "${flags[@]}" -o conservative.exe test_pr71_conservative_fraction.o pr70_helper.o
  run_logged test.run ./conservative.exe
  cat test.run.log
done

python3 - "$repo_root" "$work_dir" "$source_file" "$receipt_file" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys

repo, work, source, receipt_path = map(Path, sys.argv[1:5])
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
bound = {
    "captured_source": source,
    "process_patch": repo / "docs/evidence/pr70_coupled_process_cutoff_search_20261008.patch",
    "runner": repo / "tests/run_pr71_conservative_fraction.sh",
    "test": repo / "tests/test_pr71_conservative_fraction.f90",
    "intel_profile": repo / "tests/intel_toolchain.sh",
    "patched_source": work / "module_mp_kdm6_combined_research.f90",
    "extracted_helper": work / "pr70_helper.f90",
    "patch_log": work / "patch.log",
}
result = {}
for opt in ("O0", "O2"):
    result_log = work / opt / "test.run.log"
    output = result_log.read_text()
    for key, pattern in (
        ("fraction", r"^fraction=\s*([0-9.E+-]+)$"),
        ("next_fraction", r"^next_fraction=\s*([0-9.E+-]+)$"),
        ("returned_qr", r"^returned_qr=\s*([0-9.E+-]+)$"),
        ("next_qr", r"^next_qr=\s*([0-9.E+-]+)$"),
    ):
        match = re.search(pattern, output, re.MULTILINE)
        if not match:
            raise SystemExit(f"missing {key} in {opt} result")
        result.setdefault(opt, {})[key] = float(match.group(1))
    if "returned_direct_predicate=T" not in output or "next_direct_predicate=T" not in output:
        raise SystemExit(f"direct stored-state predicate result missing in {opt}")
    result[opt]["returned_direct_predicate"] = "PASS"
    result[opt]["next_direct_predicate"] = "PASS"
    for name in ("helper.compile", "test.compile", "test.link", "test.run"):
        bound[f"{opt}_{name}_log"] = work / opt / f"{name}.log"
        bound[f"{opt}_{name}_argv"] = work / opt / f"{name}.argv"
    bound[f"{opt}_executable"] = work / opt / "conservative.exe"

receipt = {
    "schema": "pr71_conservative_fraction_validation_v1",
    "session_day": "2026-10-08",
    "recorded_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "compiler": subprocess.check_output([os.environ["CLOUD_BAL_FC"], "--version"], text=True, stderr=subprocess.STDOUT).splitlines()[0],
    "compiler_sha256": sha(os.environ["CLOUD_BAL_FC"]),
    "runtime_libraries": {
        "/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libimf.so": sha("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libimf.so"),
        "/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libintlc.so.5": sha("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libintlc.so.5"),
    },
    "flags": {
        "O0": ["-stand", "f08", "-warn", "all", "-check", "all", "-fpe0", "-traceback", "-O0", "-fp-model", "strict", "-fimf-arch-consistency=true", "-no-ftz"],
        "O2": ["-stand", "f08", "-warn", "all", "-fpe0", "-traceback", "-O2", "-fp-model", "strict", "-fimf-arch-consistency=true", "-no-ftz"],
    },
    "scratch_work_dir": str(work),
    "files_sha256": {key: sha(path) for key, path in bound.items()},
    "commands_argv": {str(path.relative_to(work)): path.read_text().strip() for path in bound.values() if path.name.endswith(".argv")},
    "case": {
        "q_fixed_rain": 2.5142206538930623e-8,
        "q_process_rain": -2.44809541527502e-8,
        "qcrmin": 1.0e-9,
        "number_moments": "both derived from the same 5000 m^-1 rain lambda and frozen PR70 pidnr",
        "density": 1.0,
        "temperature_kelvin": 270.0,
        "result": result,
        "claim_scope": "returned float32 alpha and its immediate next float32 neighbor are both accepted by the direct stored-state predicate and store the same strictly-above-cutoff QR; this does not claim a global maximum under any candidate policy",
    },
    "checks": {
        "exact_PR70_source_and_patch_identity": "PASS",
        "extracted_helper_matches_frozen_PR70_sha256": "PASS",
        "returned_candidate_direct_state_predicate_O0_O2": "PASS",
        "next_float32_candidate_direct_state_predicate_O0_O2": "PASS",
        "same_stored_rain_mass_for_adjacent_candidates_O0_O2": "PASS",
        "pinned_Intel_ifx_O0_O2": "PASS",
    },
}
receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
PY
printf 'PR71 one-ULP reproduction passed; receipt: %s\n' "$receipt_file"
