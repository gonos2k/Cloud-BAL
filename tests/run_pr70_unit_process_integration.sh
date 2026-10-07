#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source_file=${PR70_KDM6_SOURCE:-/var/tmp/pr68_velocity_native_20261007/source/module_mp_kdm6_combined_research.f90}
patch_file=$repo_root/docs/evidence/pr70_coupled_process_cutoff_search_20261008.patch
expected_source_sha256=97e9892ff527a318f6266140eecc03238485a68b050c61bbaca7ea94f28bfdaa
expected_patch_sha256=5f1b75925ec803838f5b3cfa81012336f4d21727073c5d8c0703fb70ddc37670

source "$repo_root/tests/intel_toolchain.sh"
work_dir=$(mktemp -d /var/tmp/pr70_unit_process_integration.XXXXXX)
printf 'WORK_DIR %s\n' "$work_dir"
actual_source_sha256=$(sha256sum "$source_file" | cut -d' ' -f1)
actual_patch_sha256=$(sha256sum "$patch_file" | cut -d' ' -f1)
if [[ $actual_source_sha256 != "$expected_source_sha256" ]]; then
  printf 'unexpected selected source SHA-256: %s\n' "$actual_source_sha256" >&2
  exit 2
fi
if [[ $actual_patch_sha256 != "$expected_patch_sha256" ]]; then
  printf 'unexpected process patch SHA-256: %s\n' "$actual_patch_sha256" >&2
  exit 2
fi

PR70_KDM6_SOURCE="$source_file" python3 "$repo_root/tests/test_pr70_unit_process_composer.py" >"$work_dir/composer_tests.log" 2>&1
"$repo_root/tests/run_pr70_coupled_process.sh" >"$work_dir/process_search_tests.log" 2>&1
python3 "$repo_root/tools/pr70_compose_selected_kdm6.py" \
  "$source_file" "$patch_file" "$work_dir/composed_module.F" \
  --expected-process-patch-sha256 "$expected_patch_sha256" >"$work_dir/composition.log"

fixture=$repo_root/tests/fixtures/kdm6_wrapper
test_source=$repo_root/tests/test_pr70_unit_process_integration.f90
build_one() (
  variant=$1
  opt=$2
  build_dir=$work_dir/${variant}_${opt}
  mkdir "$build_dir"
  cp "$fixture/"*.F "$fixture/wrf_debug_stub.f90" "$test_source" "$build_dir/"
  python3 - "$work_dir/composed_module.F" "$build_dir/module_mp_kdm6.F" <<'PY'
from pathlib import Path
import sys
source, output = map(Path, sys.argv[1:])
text = source.read_text()
anchor = "            endif\n            rain_process_alpha=factor\n"
instrumented = (
    "            endif\n"
    "#ifdef PR70_INTEGRATION_TRACE\n"
    "            write(*,'(A,1X,I0,1X,I0,1X,ES24.16)') &\n"
    "                 'PR70_COLD_GATE_ACCEPTED',i,k,factor\n"
    "#endif\n"
    "            rain_process_alpha=factor\n"
)
if text.count(anchor) != 1:
    raise SystemExit("expected one actual cold-gate success anchor")
output.write_text(text.replace(anchor, instrumented, 1))
PY
  cd "$build_dir"
  printf 'BUILD_CWD %s\n' "$PWD" >build.log
  if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  case "$variant" in
    candidate) define=(-DTEST_CANDIDATE) ;;
    direct_volume) define=(-DTEST_DIRECT_VOLUME) ;;
    candidate_fixed_volume) define=(-DTEST_CANDIDATE -DTEST_FIXED_VOLUME_STATE) ;;
    direct_fixed_volume) define=(-DTEST_DIRECT_VOLUME -DTEST_FIXED_VOLUME_STATE) ;;
    *) printf 'unknown variant: %s\n' "$variant" >&2; exit 2 ;;
  esac
  run_compiler() {
    printf 'ARGV' >>build.log
    printf ' %q' "$CLOUD_BAL_FC" "$@" >>build.log
    printf '\n' >>build.log
    "$CLOUD_BAL_FC" "$@" >>build.log 2>&1
  }
  run_compiler "${flags[@]}" -free -fpp -c module_wrf_error.F
  run_compiler "${flags[@]}" -free -fpp -c module_model_constants.F
  run_compiler "${flags[@]}" -free -fpp -c module_mp_radar.F
  run_compiler "${flags[@]}" -free -fpp "${define[@]}" -DPR70_INTEGRATION_TRACE -DRWORDSIZE=4 -convert big_endian -c module_mp_kdm6.F
  run_compiler "${CLOUD_BAL_FIXED_FLAGS[@]}" -fixed -fpp -c libmassv.F
  run_compiler "${flags[@]}" -c wrf_debug_stub.f90
  run_compiler "${flags[@]}" -fpp "${define[@]}" -c test_pr70_unit_process_integration.f90
  run_compiler "${flags[@]}" -o test.exe test_pr70_unit_process_integration.o module_mp_kdm6.o module_mp_radar.o module_model_constants.o libmassv.o wrf_debug_stub.o
  ./test.exe >run.log 2>&1
  grep '^INPUT ' run.log >input_rows.txt
  grep '^PR70_COLD_GATE_ACCEPTED ' run.log >cold_gate_markers.txt
  grep 'KDM6_NUMBER_WRAPPER .* PASS' run.log >pass_marker.txt
)

for opt in O0 O2; do
  for variant in candidate direct_volume candidate_fixed_volume direct_fixed_volume; do
    build_one "$variant" "$opt"
  done
done

python3 - "$work_dir" <<'PY'
import math
import sys
from pathlib import Path

root = Path(sys.argv[1])
densities = (0.25, 0.5, 1.0, 2.0)
variants = ("candidate", "direct_volume", "candidate_fixed_volume", "direct_fixed_volume")

def read_cases(variant, opt):
    directory = root / f"{variant}_{opt}"
    rows = {}
    marker_groups = {}
    pending_markers = []
    for line in (directory / "run.log").read_text().splitlines():
        parts = line.split()
        if parts and parts[0] == "PR70_COLD_GATE_ACCEPTED":
            if len(parts) != 4 or not math.isfinite(float(parts[3])):
                raise SystemExit(f"invalid cold-gate marker in {directory}: {line}")
            pending_markers.append((int(parts[1]), int(parts[2]), float(parts[3])))
        elif parts and parts[0] == "INPUT":
            if len(parts) != 29:
                raise SystemExit(f"unexpected result row in {directory}: {line}")
            rho = float(parts[1])
            inputs = [float(value) for value in parts[2:6]]
            outputs = [float(value) for value in parts[6:]]
            if rho in rows or not all(math.isfinite(value) for value in inputs + outputs):
                raise SystemExit(f"duplicate or non-finite row in {directory}")
            rows[rho] = (inputs, outputs)
            marker_groups[rho] = pending_markers
            pending_markers = []
    if pending_markers:
        raise SystemExit(f"unassociated cold-gate markers in {directory}")
    if tuple(sorted(rows)) != densities:
        raise SystemExit(f"missing density result in {directory}: {sorted(rows)}")
    for rho in densities:
        markers = marker_groups[rho]
        if len(markers) != 3:
            raise SystemExit(f"actual cold gate not observed for rho={rho} in {directory}: {markers}")
        cells = {(i, k) for i, k, _ in markers}
        if cells != {(1, 1), (2, 1), (3, 1)}:
            raise SystemExit(f"unexpected accepted cells for rho={rho} in {directory}: {markers}")
        if any(not (0.0 < alpha <= 1.0) for _, _, alpha in markers):
            raise SystemExit(f"invalid accepted alpha for rho={rho} in {directory}: {markers}")
    if not (directory / "pass_marker.txt").read_text().strip().endswith(" PASS"):
        raise SystemExit(f"missing pass marker in {directory}")
    return rows

def close(a, b, rel=3.0e-5):
    return abs(a-b) <= max(1.0e-12, rel*max(abs(a),abs(b),1.0e-20))

results = {(v, o): read_cases(v, o) for v in variants for o in ("O0", "O2")}
for opt in ("O0", "O2"):
    for candidate, direct in (("candidate", "direct_volume"),
                              ("candidate_fixed_volume", "direct_fixed_volume")):
        for rho in densities:
            left, right = results[candidate, opt][rho][1], results[direct, opt][rho][1]
            for field, (a, b) in enumerate(zip(left, right), 1):
                if not close(a, b):
                    raise SystemExit(f"candidate/direct mismatch {opt} rho={rho} output={field}: {a} vs {b}")
for variant in variants:
    for rho in densities:
        left = results[variant, "O0"][rho][1]
        right = results[variant, "O2"][rho][1]
        for field, (a, b) in enumerate(zip(left, right), 1):
            if not close(a, b, rel=1.0e-4):
                raise SystemExit(f"O0/O2 mismatch {variant} rho={rho} output={field}: {a} vs {b}")
print("WHOLE_MODULE_COLD_GATE O0/O2 candidate/direct-volume PASS")
print("MATCHED_VOLUME_STATE O0/O2 candidate/direct-volume PASS")
print("DRY_DENSITIES 0.25 0.50 1.00 2.00 PASS")
PY

python3 - "$repo_root" "$work_dir" "$source_file" "$patch_file" <<'PY'
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

repo, work, source, patch = map(Path, sys.argv[1:5])
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
files = {
    "selected_source": source,
    "process_patch": patch,
    "composed_module": work / "composed_module.F",
    "density_role_inventory": work / "composed_module.density_roles.json",
    "composer": repo / "tools/pr70_compose_selected_kdm6.py",
    "unit_transformer": repo / "tools/pr69_transform_selected_kdm6.py",
    "composer_tests": repo / "tests/test_pr70_unit_process_composer.py",
    "whole_module_test": repo / "tests/test_pr70_unit_process_integration.f90",
    "runner": repo / "tests/run_pr70_unit_process_integration.sh",
    "intel_profile": repo / "tests/intel_toolchain.sh",
    "composition_log": work / "composition.log",
    "composer_test_log": work / "composer_tests.log",
    "process_search_test_log": work / "process_search_tests.log",
    "process_search_receipt": repo / "docs/evidence/pr70_coupled_process_cutoff_validation_20261008.json",
}
variants = ("candidate", "direct_volume", "candidate_fixed_volume", "direct_fixed_volume")
for opt in ("O0", "O2"):
    for variant in variants:
        build = work / f"{variant}_{opt}"
        for name in ("build.log", "run.log", "input_rows.txt", "cold_gate_markers.txt", "pass_marker.txt", "test.exe",
                     "test_pr70_unit_process_integration.o", "module_mp_kdm6.o"):
            files[f"{variant}_{opt}_{name}"] = build / name
        files[f"{variant}_{opt}_composed_module"] = build / "module_mp_kdm6.F"
role_receipt = json.loads((work / "composed_module.density_roles.json").read_text())
role_counts = {}
for record in role_receipt["density_uses"]:
    role = record["role"]
    role_counts[role] = role_counts.get(role, 0) + int(record["references"])
process_den_references = sum(int(record["references"]) for record in role_receipt["density_uses"])
receipt = {
    "schema": "pr70_unit_process_whole_module_integration_v1",
    "session_day": "2026-10-08",
    "recorded_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "selected_source_sha256": sha(source),
    "process_patch_sha256": sha(patch),
    "composed_module_sha256": sha(work / "composed_module.F"),
    "density_inventory": {
        "captured_KDM62D_DEN_references": 71,
        "process_patched_KDM62D_DEN_references": process_den_references,
        "process_patched_role_counts": role_counts,
        "transformed_routing_counts": role_receipt["routing_counts"],
        "unresolved_qi0_sites": role_counts.get("unresolved_ice_threshold", 0),
    },
    "compiler": subprocess.check_output([os.environ["CLOUD_BAL_FC"], "--version"], text=True, stderr=subprocess.STDOUT).splitlines()[0],
    "compiler_sha256": sha(os.environ["CLOUD_BAL_FC"]),
    "intel_environment_sha256": sha("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/setvars.sh"),
    "runtime_sha256": {
        "libimf.so": sha("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libimf.so"),
        "libintlc.so.5": sha("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libintlc.so.5"),
    },
    "compiler_flags": {
        "O0": ["-stand", "f08", "-warn", "all", "-check", "all", "-fpe0", "-traceback", "-O0", "-fp-model", "strict", "-fimf-arch-consistency=true", "-no-ftz"],
        "O2": ["-stand", "f08", "-warn", "all", "-fpe0", "-traceback", "-O2", "-fp-model", "strict", "-fimf-arch-consistency=true", "-no-ftz"],
    },
    "scratch_work_dir": str(work),
    "files_sha256": {name: sha(path) for name, path in files.items()},
    "fixture": {
        "dry_density_kg_m3": [0.25, 0.5, 1.0, 2.0],
        "temperature_K": 250.0,
        "pressure_Pa": 90000.0,
        "vapor_relative_humidity_over_ice": 0.8,
        "cloud_water_kg_kg": 2.0e-4,
        "cloud_lambda_m_inv": 100000.0,
        "ice_water_kg_kg": 2.0e-5,
        "ice_lambda_m_inv": 20000.0,
        "rain_water_kg_kg": 1.0e-4,
        "rain_lambda_m_inv": 5000.0,
        "snow_water_kg_kg": 2.0e-5,
        "graupel_water_kg_kg": 2.0e-5,
        "graupel_BG_m3_kg_dry": 5.0e-8,
        "manufactured_DEL_T_s": 1.0,
        "native_settings_changed": False,
        "matched_volume_state_scales_mass_and_specific_numbers_by_inverse_dry_density": True,
    },
    "checks": {
        "strict_source_patch_hashes_and_DEN_inventory": "PASS",
        "cutoff_donor_mixed_phase_pending_cleanup_and_stored_endpoint_O0_O2": "PASS",
        "whole_composed_module_source_binding": "PASS",
        "actual_cold_module_gate_and_state_update_O0_O2": "PASS",
        "actual_cold_gate_acceptance_marker": "PASS",
        "cold_gate_acceptance_cells_per_density_case": 3,
        "cold_gate_acceptance_markers_per_binary": 12,
        "candidate_vs_direct_volume_at_each_density": "PASS",
        "matched_physical_volume_state_candidate_vs_direct_volume": "PASS",
        "input_public_number_backconversion": "PASS",
        "Q_N_BG_T_updates_asserted_by_driver": "PASS",
        "qi0_growth_energy_unresolved": "NOT_APPROVED",
        "native_25_cell_acceptance": "NOT_CLAIMED",
    },
}
(work / "integration_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
destination = repo / "docs/evidence/pr70_unit_process_integration_validation_20261008.json"
destination.write_text(json.dumps(receipt, indent=2) + "\n")
print(f"INTEGRATION_RECEIPT {destination}")
PY
printf 'PR70 same-source whole-module unit/process integration passed.\n'
