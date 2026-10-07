#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
selected_source=${PR69_SELECTED_KDM6_SOURCE:-/var/tmp/pr67_budget_capture_20261007/source/module_mp_kdm6_combined_research.f90}
source "$script_dir/intel_toolchain.sh"
work_dir=$(mktemp -d /var/tmp/pr69_kdm6_selected_dual_density.XXXXXX)
printf 'WORK_DIR %s\n' "$work_dir"
cp "$script_dir/intel_toolchain.sh" "$work_dir/intel_toolchain.sh"
cp "$script_dir/test_pr69_kdm6_unit_basis.f90" "$work_dir/test.f90"
cp "$script_dir/fixtures/kdm6_wrapper/"*.F "$work_dir/"
cp "$script_dir/fixtures/kdm6_wrapper/wrf_debug_stub.f90" "$work_dir/"
python3 "$repo_root/tools/pr69_transform_selected_kdm6.py" "$selected_source" "$work_dir/selected_candidate.F" | tee "$work_dir/source_transform.log"

build_one() (
  label=$1
  opt=$2
  build_dir="$work_dir/${label}_${opt}"
  mkdir "$build_dir"
  cp "$work_dir/"*.F "$work_dir/wrf_debug_stub.f90" "$work_dir/test.f90" "$build_dir/"
  cp "$work_dir/selected_candidate.F" "$build_dir/module_mp_kdm6.F"
  cd "$build_dir"
  pwd > build_cwd.log
  if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  define=()
  if [[ $label == candidate ]]; then define=(-DTEST_CANDIDATE); else define=(-DTEST_DIRECT_VOLUME); fi
  run_compiler() {
    printf 'ARGV'
    printf ' %q' "$CLOUD_BAL_FC" "$@"
    printf '\n'
    "$CLOUD_BAL_FC" "$@"
  }
  run_compiler "${flags[@]}" -free -fpp -c module_wrf_error.F
  run_compiler "${flags[@]}" -free -fpp -c module_model_constants.F
  run_compiler "${flags[@]}" -free -fpp -c module_mp_radar.F
  run_compiler "${flags[@]}" -free -fpp "${define[@]}" -DRWORDSIZE=4 -convert big_endian -c module_mp_kdm6.F
  run_compiler "${flags[@]}" -fixed -fpp -c libmassv.F
  run_compiler "${flags[@]}" -c wrf_debug_stub.f90
  run_compiler "${flags[@]}" -fpp "${define[@]}" -c test.f90
  run_compiler "${flags[@]}" -o test.exe test.o module_mp_kdm6.o module_mp_radar.o module_model_constants.o libmassv.o wrf_debug_stub.o
  ./test.exe >run.log 2>&1
)
build_one candidate O0 >"$work_dir/candidate_O0.log" 2>&1
build_one candidate O2 >"$work_dir/candidate_O2.log" 2>&1
build_one direct_volume O0 >"$work_dir/direct_volume_O0.log" 2>&1

expect_output_rejection() (
  channel=$1
  build_dir="$work_dir/reject_${channel}_O0"
  mkdir "$build_dir"
  cp "$work_dir/candidate_O0/"*.o "$work_dir/candidate_O0/"*.mod "$build_dir/"
  cp "$work_dir/candidate_O0/"*.F "$work_dir/candidate_O0/"*.f90 "$build_dir/"
  cp "$work_dir/test.f90" "$build_dir/"
  cp "$work_dir/selected_candidate.F" "$build_dir/module_mp_kdm6.F"
  python3 - "$channel" "$build_dir/module_mp_kdm6.F" "$work_dir/selected_candidate.F" <<'PY'
import hashlib
import json
import pathlib
import sys

channel = sys.argv[1]
path = pathlib.Path(sys.argv[2])
original = pathlib.Path(sys.argv[3])
indices = {"NC": 1, "NI": 2, "NN": 3}
index = indices[channel]
anchor = f"         call volume_number_to_specific(nci(i,k,{index}), dry_density(i,k), number_value, number_valid)"
replacement = f"         nci(i,k,{index}) = huge(0.0) ! test-only invalid output injection\n" + anchor
source = path.read_text()
if source.count(anchor) != 1:
    raise SystemExit(f"{channel}: expected one output conversion anchor")
path.write_text(source.replace(anchor, replacement, 1))
record = {
    "channel": channel,
    "original_transformed_source_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
    "mutated_source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    "mutation": replacement.splitlines()[0].strip(),
    "anchor": anchor.strip(),
}
path.with_name("source_mutation.json").write_text(json.dumps(record, indent=2) + "\n")
PY
  cd "$build_dir"
  printf 'BUILD_CWD %s\n' "$PWD" >build.log
  flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  run_compiler() {
    printf 'ARGV' >>build.log
    printf ' %q' "$CLOUD_BAL_FC" "$@" >>build.log
    printf '\n' >>build.log
    "$CLOUD_BAL_FC" "$@" >>build.log 2>&1
  }
  run_compiler "${flags[@]}" -free -fpp -DTEST_CANDIDATE -DRWORDSIZE=4 -convert big_endian -c module_mp_kdm6.F
  run_compiler "${flags[@]}" -fpp -DTEST_CANDIDATE -c test.f90
  run_compiler "${flags[@]}" -o test.exe test.o module_mp_kdm6.o module_mp_radar.o module_model_constants.o libmassv.o wrf_debug_stub.o
  set +e
  ./test.exe >run.log 2>&1
  status=$?
  set -e
  if [[ $status -eq 0 ]] || ! rg -q "KDM6 invalid ${channel} number basis output" run.log; then
    cat run.log >&2
    printf 'invalid %s output did not fail through its explicit guard (status %s)\n' "$channel" "$status" >&2
    exit 1
  fi
  printf 'controlled invalid %s output rejected (exit %s)\n' "$channel" "$status"
)
expect_output_rejection NC >"$work_dir/reject_NC_O0.log" 2>&1
expect_output_rejection NI >"$work_dir/reject_NI_O0.log" 2>&1
expect_output_rejection NN >"$work_dir/reject_NN_O0.log" 2>&1
printf 'selected-source invalid NC/NI/NN output rejection checks PASS\n'

python3 - "$work_dir" <<'PY'
import math
import pathlib
import sys

root=pathlib.Path(sys.argv[1])
densities=(0.25,0.5,1.0,2.0)
fields=23

def cases(path):
    result={}
    for line in path.read_text().splitlines():
        parts=line.split()
        if not parts or parts[0] != 'INPUT':
            continue
        if len(parts) != 2+4+fields:
            raise SystemExit(f'unexpected output width in {path}: {len(parts)}')
        result[float(parts[1])] = [float(x) for x in parts[6:]]
    if set(result) != set(densities):
        raise SystemExit(f'missing density controls in {path}: {sorted(result)}')
    if not all(math.isfinite(x) for row in result.values() for x in row):
        raise SystemExit(f'nonfinite output in {path}')
    return result

def close(a,b):
    return abs(a-b) <= max(1.0e-12, 3.0e-5*max(abs(a),abs(b),1.0e-20))

candidate0=cases(root/'candidate_O0'/'run.log')
candidate2=cases(root/'candidate_O2'/'run.log')
direct=cases(root/'direct_volume_O0'/'run.log')
for density in densities:
    for field,(converted,volume) in enumerate(zip(candidate0[density],direct[density]),1):
        if not close(converted,volume):
            raise SystemExit(f'selected-source converted/direct-volume mismatch rho_dry={density} field={field}: {converted} vs {volume}')
    for field,(o2,o0) in enumerate(zip(candidate2[density],candidate0[density]),1):
        if not close(o2,o0):
            raise SystemExit(f'selected-source O0/O2 mismatch rho_dry={density} field={field}: {o2} vs {o0}')
print('selected combined KDM6 source: converted/direct-volume paired calls match at dry rho .25/.5/1/2')
print('selected-source O0/O2 equivalence and helper edge checks PASS')
print('RESEARCH PROTOTYPE ONLY; qi0, thermodynamic/phase closure, and native-host object lineage remain OPEN')
PY
python3 - "$work_dir" "$selected_source" "$CLOUD_BAL_FC" "$cloud_bal_fc_version" "$repo_root/tools/pr69_transform_selected_kdm6.py" "$script_dir/run_pr69_kdm6_selected_dual_density.sh" "$repo_root/patches/kdm6_unit_basis_pr69.patch" <<'PY'
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
source = pathlib.Path(sys.argv[2])
compiler = pathlib.Path(sys.argv[3])
transformer = pathlib.Path(sys.argv[5])
runner = pathlib.Path(sys.argv[6])
wrapper_only_patch = pathlib.Path(sys.argv[7])

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

artifact_names = [
    "selected_candidate.F", "selected_candidate.density_roles.json",
    "test.f90", "intel_toolchain.sh", "source_transform.log",
    "candidate_O0/run.log", "candidate_O0/test.exe", "candidate_O0/module_mp_kdm6.o",
    "candidate_O2/run.log", "candidate_O2/test.exe", "candidate_O2/module_mp_kdm6.o",
    "direct_volume_O0/run.log", "direct_volume_O0/test.exe", "direct_volume_O0/module_mp_kdm6.o",
    *[f"{build}/{obj}" for build in ("candidate_O0", "candidate_O2", "direct_volume_O0")
      for obj in ("test.o", "module_wrf_error.o", "module_model_constants.o", "module_mp_radar.o", "libmassv.o", "wrf_debug_stub.o")],
    *[f"{build}/{source}" for build in ("candidate_O0", "candidate_O2", "direct_volume_O0")
      for source in ("module_mp_kdm6.F", "test.f90", "module_wrf_error.F", "module_model_constants.F",
                     "module_mp_radar.F", "libmassv.F", "wrf_debug_stub.f90")],
    "candidate_O0/build_cwd.log", "candidate_O2/build_cwd.log", "direct_volume_O0/build_cwd.log",
    "candidate_O0.log", "candidate_O2.log", "direct_volume_O0.log",
    *[f"reject_{channel}_O0/{name}" for channel in ("NC", "NI", "NN")
      for name in ("run.log", "build.log", "source_mutation.json", "module_mp_kdm6.F", "test.exe", "module_mp_kdm6.o", "test.o",
                   "module_mp_radar.o", "module_model_constants.o", "module_wrf_error.o",
                   "libmassv.o", "wrf_debug_stub.o")],
    "reject_NC_O0.log", "reject_NI_O0.log", "reject_NN_O0.log",
    "module_wrf_error.F", "module_model_constants.F", "module_mp_radar.F",
    "libmassv.F", "wrf_debug_stub.f90",
]
artifacts = {name: sha256(root / name) for name in artifact_names}
receipt = {
    "scope": "selected-source dual-density research executable check; not native host closure",
    "source_path": str(source),
    "source_sha256": sha256(source),
    "transformer_path": str(transformer),
    "transformer_sha256": sha256(transformer),
    "runner_path": str(runner),
    "runner_sha256": sha256(runner),
    "wrapper_only_diagnostic_patch_sha256": sha256(wrapper_only_patch),
    "work_dir": str(root),
    "compiler_path": str(compiler),
    "compiler_version": sys.argv[4],
    "compiler_sha256": sha256(compiler),
    "toolchain_profile_sha256": sha256(pathlib.Path(root / "intel_toolchain.sh")),
    "intel_runtime_dependencies": {
        "/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libimf.so": "31f0ab1dcce74417de63e5c6876b5bb078c15efea4c49ca9afc233abbe80fda8",
        "/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libintlc.so.5": "2722b7aba08edf1d37c45b8f90070c87b499404b0888bd1b4150f34e123ef120",
    },
    "test_harness_sha256": sha256(root / "test.f90"),
    "transformed_source_sha256": sha256(root / "selected_candidate.F"),
    "density_roles_sha256": sha256(root / "selected_candidate.density_roles.json"),
    "density_roles": json.loads((root / "selected_candidate.density_roles.json").read_text())["role_counts"],
    "paired_calls": "converted specific-number and direct-volume calls agree at dry density 0.25, 0.5, 1, and 2 kg m-3",
    "paired_field_count": 92,
    "comparison_tolerance": "abs(a-b) <= max(1.0e-12, 3.0e-5*max(abs(a),abs(b),1.0e-20))",
    "optimization_checks": ["candidate O0", "candidate O2", "direct-volume O0"],
    "invalid_output_rejections": {channel: f"explicit {channel} output guard; expected controlled ERROR STOP" for channel in ("NC", "NI", "NN")},
    "invalid_output_test_mutation": "isolated scratch copies receive one exact-anchor huge-value injection immediately before each channel conversion; transformed production source has no test hooks",
    "compiler_argv_record": "each build log begins each actual ifx invocation with an ARGV line",
    "artifacts": artifacts,
    "open_items": ["qi0 meaning", "thermodynamic and phase closure", "historical host object/executable lineage", "native call"],
}
(root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(f"RECEIPT {root / 'receipt.json'}")
PY
printf 'PR69 SELECTED-SOURCE DUAL-DENSITY EXECUTABLE EVIDENCE COMPLETE\n'
