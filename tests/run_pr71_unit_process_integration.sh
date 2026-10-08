#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source_file=${PR71_KDM6_SOURCE:-/var/tmp/pr68_velocity_native_20261007/source/module_mp_kdm6_combined_research.f90}
validity_patch=${PR71_VALIDITY_PATCH:-$repo_root/docs/evidence/pr71_particle_output_contract_20261008.patch}
validity_patch_sha256=${PR71_VALIDITY_PATCH_SHA256:-94ea6189c85cd0856a28aac2663ad70091c3259fc448d48bd021adf42ff9ae45}
step_count_patch=${PR71_STEP_COUNT_PATCH:-$repo_root/docs/evidence/pr71_step_count_contract_20261008_v2.patch}
step_count_patch_sha256=${PR71_STEP_COUNT_PATCH_SHA256:-7bc37047bf616b50ebb506f130a2f1f0535e0a5afc26bb26183a27ee188ebb24}
composed_source_sha256=${PR71_COMPOSED_SOURCE_SHA256:-6245969c87f6568cad3b6c6afddc0d1bdfe84a31baa1cee10a465b663c88d716}
evidence_path=${PR71_EVIDENCE_PATH:-$repo_root/docs/evidence/pr71_unit_process_guarded_integration_20261008.json}
process_patch=$repo_root/docs/evidence/pr70_coupled_process_cutoff_search_20261008.patch
expected_source_sha256=97e9892ff527a318f6266140eecc03238485a68b050c61bbaca7ea94f28bfdaa
expected_process_sha256=5f1b75925ec803838f5b3cfa81012336f4d21727073c5d8c0703fb70ddc37670

if [[ $validity_patch_sha256 == TO_BE_FROZEN ]]; then
  printf '%s\n' 'PR71_VALIDITY_PATCH_SHA256 must be frozen in this runner' >&2
  exit 2
fi
if [[ $composed_source_sha256 == TO_BE_FROZEN ]]; then
  printf '%s\n' 'PR71_COMPOSED_SOURCE_SHA256 must be frozen in this runner' >&2
  exit 2
fi
if [[ -e $evidence_path || -L $evidence_path ]]; then
  printf 'refusing to overwrite PR71 evidence: %s\n' "$evidence_path" >&2
  exit 2
fi
source "$repo_root/tests/intel_toolchain.sh"
work_dir=$(mktemp -d /var/tmp/pr71_unit_process_integration.XXXXXX)
printf 'WORK_DIR %s\n' "$work_dir"
[[ $(sha256sum "$source_file" | cut -d' ' -f1) == "$expected_source_sha256" ]]
[[ $(sha256sum "$process_patch" | cut -d' ' -f1) == "$expected_process_sha256" ]]
[[ $(sha256sum "$validity_patch" | cut -d' ' -f1) == "$validity_patch_sha256" ]]
[[ $(sha256sum "$step_count_patch" | cut -d' ' -f1) == "$step_count_patch_sha256" ]]

composed_source=$work_dir/composed_pr71.F
python3 "$repo_root/tools/pr71_compose_guarded_kdm6.py" \
  "$source_file" "$process_patch" "$validity_patch" "$step_count_patch" "$composed_source" \
  --expected-validity-patch-sha256 "$validity_patch_sha256" \
  --expected-step-count-patch-sha256 "$step_count_patch_sha256" >"$work_dir/composition.log"
python3 "$repo_root/tests/test_pr71_composer.py" \
  --source "$source_file" --validity-patch "$validity_patch" \
  --expected-validity-patch-sha256 "$validity_patch_sha256" \
  --expected-composed-source-sha256 5de1884ab59e3de30a3e4ef1d8317405f1ba0591cf7ed9aa6fbca574d5233f41 >"$work_dir/composer_tests.log" 2>&1
python3 "$repo_root/tests/test_pr71_guarded_composer.py" >"$work_dir/guarded_composer_tests.log" 2>&1

fixture=$repo_root/tests/fixtures/kdm6_wrapper
test_source=$repo_root/tests/test_pr71_unit_process_integration.f90
build_one() (
  variant=$1
  opt=$2
  build_dir=$work_dir/${variant}_${opt}
  mkdir "$build_dir"
  cp "$fixture/"*.F "$fixture/wrf_debug_stub.f90" "$test_source" "$build_dir/"
  python3 - "$composed_source" "$build_dir/module_mp_kdm6.F" <<'PY'
from pathlib import Path
import sys
source, output = map(Path, sys.argv[1:])
text = source.read_text()
anchor = "            endif\n            rain_process_alpha=factor\n"
instrumented = (
    "            endif\n"
    "#ifdef PR71_INTEGRATION_TRACE\n"
    "            write(*,'(A,1X,I0,1X,I0,1X,ES24.16)') &\n"
    "                 'PR71_COLD_GATE_ACCEPTED',i,k,factor\n"
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
    eos_candidate) define=(-DTEST_CANDIDATE -DTEST_EOS_CONSISTENT) ;;
    eos_direct_volume) define=(-DTEST_DIRECT_VOLUME -DTEST_EOS_CONSISTENT) ;;
    eos_absent_candidate) define=(-DTEST_CANDIDATE -DTEST_EOS_CONSISTENT -DTEST_ABSENT_GRAUPEL) ;;
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
  run_compiler "${flags[@]}" -free -fpp "${define[@]}" -DPR71_INTEGRATION_TRACE -DRWORDSIZE=4 -convert big_endian -c module_mp_kdm6.F
  run_compiler "${CLOUD_BAL_FIXED_FLAGS[@]}" -fixed -fpp -c libmassv.F
  run_compiler "${flags[@]}" -c wrf_debug_stub.f90
  run_compiler "${flags[@]}" -fpp "${define[@]}" -c test_pr71_unit_process_integration.f90
  run_compiler "${flags[@]}" -o test.exe test_pr71_unit_process_integration.o module_mp_kdm6.o module_mp_radar.o module_model_constants.o libmassv.o wrf_debug_stub.o
  if [[ $variant == eos_absent_candidate ]]; then
    if ./test.exe >run.log 2>&1; then
      printf '%s\n' 'unexpected fullmodule graupel-absent completion' >&2
      exit 1
    else
      status=$?
    fi
    if [[ $status -ne 134 ]] || ! grep -q 'forrtl: error (73): floating divide by zero' run.log || \
       ! grep -Eq 'kdm62d[[:space:]]+2106' run.log; then
      printf 'unexpected graupel-absent failure status=%s\n' "$status" >&2
      exit 1
    fi
    printf 'PR71_GRAUPEL_ABSENT_BLOCKED inherited_n0i_divide status=%s\n' "$status" >pass_marker.txt
    : >input_rows.txt
    : >cold_gate_markers.txt
    return 0
  fi
  ./test.exe >run.log 2>&1
  grep '^INPUT ' run.log >input_rows.txt
  if ! grep '^PR71_COLD_GATE_ACCEPTED ' run.log >cold_gate_markers.txt; then
    if [[ $variant != eos_absent_candidate ]]; then exit 1; fi
    : >cold_gate_markers.txt
  fi
  grep 'KDM6_NUMBER_WRAPPER .* PASS' run.log >pass_marker.txt
)

for opt in O0 O2; do
  for variant in candidate direct_volume candidate_fixed_volume direct_fixed_volume eos_candidate eos_direct_volume eos_absent_candidate; do
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

def close(a, b, rel=3.0e-5):
    return abs(a-b) <= max(1.0e-12, rel*max(abs(a),abs(b),1.0e-20))

def read_unit_case(variant, opt):
    directory = root / f"{variant}_{opt}"
    rows, grouped, pending = {}, {}, []
    for line in (directory / "run.log").read_text().splitlines():
        parts = line.split()
        if parts and parts[0] == "PR71_COLD_GATE_ACCEPTED":
            if len(parts) != 4 or not math.isfinite(float(parts[3])):
                raise SystemExit(f"invalid acceptance marker in {directory}: {line}")
            pending.append((int(parts[1]), int(parts[2]), float(parts[3])))
        elif parts and parts[0] == "INPUT":
            if len(parts) != 29 or not all(math.isfinite(float(value)) for value in parts[1:]):
                raise SystemExit(f"invalid unit fixture result in {directory}: {line}")
            rho = float(parts[1])
            if rho in rows:
                raise SystemExit(f"duplicate density in {directory}: {rho}")
            rows[rho] = [float(value) for value in parts[2:]]
            grouped[rho], pending = pending, []
    if pending or tuple(sorted(rows)) != densities:
        raise SystemExit(f"missing unit fixture density or markers in {directory}")
    for rho in densities:
        markers = grouped[rho]
        if {(i,k) for i,k,_ in markers} != {(1,1),(2,1),(3,1)} or any(not (0 < a <= 1) for _,_,a in markers):
            raise SystemExit(f"actual cold gate not observed for rho={rho} in {directory}")
    if not (directory / "pass_marker.txt").read_text().strip().endswith(" PASS"):
        raise SystemExit(f"missing unit fixture pass marker in {directory}")
    # Compare model outputs only; candidate and direct fixtures intentionally present different number bases.
    return {rho: values[4:] for rho, values in rows.items()}

unit = {(v,o): read_unit_case(v,o) for v in variants for o in ("O0","O2")}
for opt in ("O0","O2"):
    for left_name,right_name in (("candidate","direct_volume"),("candidate_fixed_volume","direct_fixed_volume")):
        for rho in densities:
            for field,(a,b) in enumerate(zip(unit[left_name,opt][rho],unit[right_name,opt][rho]),1):
                if not close(a,b):
                    raise SystemExit(f"unit candidate/direct mismatch {opt} rho={rho} field={field}")
for variant in variants:
    for rho in densities:
        for field,(a,b) in enumerate(zip(unit[variant,"O0"][rho],unit[variant,"O2"][rho]),1):
            if not close(a,b,rel=1.0e-4):
                raise SystemExit(f"unit O0/O2 mismatch {variant} rho={rho} field={field}")

def read_eos_case(variant,opt,expect_gate=True):
    directory=root/f"{variant}_{opt}"
    lines=(directory/"run.log").read_text().splitlines()
    input_rows=[line.split() for line in lines if line.startswith("INPUT ")]
    eos_rows=[line.split() for line in lines if line.startswith("EOS_INPUT ")]
    markers=[line.split() for line in lines if line.startswith("PR71_COLD_GATE_ACCEPTED ")]
    expected_markers=3 if expect_gate else 0
    if len(input_rows)!=1 or len(input_rows[0])!=29 or len(eos_rows)!=1 or len(eos_rows[0])!=6 or len(markers)!=expected_markers:
        raise SystemExit(f"missing EOS result or markers in {directory}")
    p,t,qv,rho_dry,rho_moist=map(float,eos_rows[0][1:])
    expected_dry=p/(287.04*t*(1.0+qv/0.622))
    if not all(math.isfinite(x) for x in (p,t,qv,rho_dry,rho_moist)) or not close(rho_dry,expected_dry) or not close(rho_moist,rho_dry*(1+qv)):
        raise SystemExit(f"EOS source equation mismatch in {directory}")
    if not close(float(input_rows[0][1]),rho_dry):
        raise SystemExit(f"reported EOS dry density mismatch in {directory}")
    if expect_gate and {(int(row[1]),int(row[2])) for row in markers}!={(1,1),(2,1),(3,1)}:
        raise SystemExit(f"actual EOS cold gate not observed in {directory}")
    if not (directory/"pass_marker.txt").read_text().strip().endswith(" PASS"):
        raise SystemExit(f"missing EOS pass marker in {directory}")
    return [float(value) for value in input_rows[0][6:]],rho_dry

for opt in ("O0","O2"):
    candidate,rho_candidate=read_eos_case("eos_candidate",opt)
    direct,rho_direct=read_eos_case("eos_direct_volume",opt)
    if not close(rho_candidate,rho_direct):
        raise SystemExit(f"EOS dry densities differ at {opt}")
    for field,(a,b) in enumerate(zip(candidate,direct),1):
        if not close(a,b):
            raise SystemExit(f"EOS candidate/direct mismatch {opt} field={field}")

    absent_dir=root/f"eos_absent_candidate_{opt}"
    absent_log=(absent_dir/"run.log").read_text()
    absent_marker=(absent_dir/"pass_marker.txt").read_text().strip()
    if "forrtl: error (73): floating divide by zero" not in absent_log or \
       "kdm62d                   2106" not in absent_log or \
       not absent_marker.startswith("PR71_GRAUPEL_ABSENT_BLOCKED inherited_n0i_divide"):
        raise SystemExit(f"graupel-absent failure was not the recorded inherited n0i blocker at {opt}")
print("PR71_UNIT_FIXTURE O0/O2 candidate/direct-volume PASS")
print("PR71_EOS_CONSISTENT_FIXTURE O0/O2 candidate/direct-volume PASS")
print("PR71_EOS_GRAUPEL_ABSENT O0/O2 FULL_MODULE BLOCKED_INHERITED_N0I")
print("PR71_DRY_DENSITIES 0.25 0.50 1.00 2.00 PASS")
PY

python3 - "$repo_root" "$work_dir" "$source_file" "$process_patch" "$validity_patch" "$step_count_patch" "$evidence_path" <<'PY'
from datetime import datetime,timezone
import hashlib,json,os,subprocess,sys
from pathlib import Path
repo,work,source,process,validity,step_count,evidence=map(Path,sys.argv[1:])
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
files={
 "source":source,"process_patch":process,"validity_patch":validity,"step_count_patch":step_count,
 "composed_source":work/"composed_pr71.F",
 "composition_receipt":work/"composed_pr71.F.composition.json",
 "composer":repo/"tools/pr71_compose_guarded_kdm6.py",
 "output_contract_generator":repo/"tools/pr71_particle_output_contract.py",
 "composer_tests":repo/"tests/test_pr71_composer.py",
 "guarded_composer_tests":repo/"tests/test_pr71_guarded_composer.py",
 "integration_test":repo/"tests/test_pr71_unit_process_integration.f90",
 "count_contract_generator":repo/"tools/pr71_step_count_contract.py",
 "count_contract_tests":repo/"tests/test_pr71_step_count_contract.py",
 "count_contract_receipt":repo/"docs/evidence/pr71_step_count_contract_20261008_v3.json",
 "runner":repo/"tests/run_pr71_unit_process_integration.sh",
 "intel_profile":repo/"tests/intel_toolchain.sh",
}
for opt in ("O0","O2"):
 for variant in ("candidate","direct_volume","candidate_fixed_volume","direct_fixed_volume","eos_candidate","eos_direct_volume","eos_absent_candidate"):
  build=work/f"{variant}_{opt}"
  for name in ("build.log","run.log","input_rows.txt","cold_gate_markers.txt","pass_marker.txt","test.exe","module_mp_kdm6.o"):
   files[f"{variant}_{opt}_{name}"]=build/name
receipt={
 "schema":"pr71_unit_process_guarded_integration_v1",
 "recorded_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
 "scratch_work_dir":str(work),
 "compiler":subprocess.check_output([os.environ["CLOUD_BAL_FC"],"--version"],text=True,stderr=subprocess.STDOUT).splitlines()[0],
 "compiler_sha256":sha(os.environ["CLOUD_BAL_FC"]),
 "files_sha256":{name:sha(path) for name,path in files.items()},
 "composition":json.loads((work/"composed_pr71.F.composition.json").read_text()),
 "fixture":{
  "preserved_density_cases_kg_m3":[0.25,0.5,1.0,2.0],
  "eos_state":{"pressure_pa":90000.0,"temperature_k":250.0,"vapor_source":"0.8 RH for active EOS case; 1.2 RH for graupel-absent consumer isolation, relative to the same KDM6 fpvs saturation pressure","dry_density_equation":"p/[Rd*T*(1+qv/epsilon)]","Rd":287.04,"epsilon":0.622,"moist_DEN_equation":"rho_d*(1+qv)"},
  "rain_public_number_coefficient":{"expression":"cmr*Gamma(1+dmr+mur)/Gamma(1+mur)","fixture_parameters":{"mur":1.0,"dmr":3.0},"value_over_cmr":24.0,"note":"Corrected PR71 fixture coefficient; earlier PR70 conversion receipts remain historical."},
  "cold_gate_acceptance_cells":[[1,1],[2,1],[3,1]],
  "unit_fixture":"PASS","eos_fixture":"PASS",
  "eos_graupel_absent_fixture":"BLOCKED_INHERITED_N0I_DIVIDE (rain=0, qg=0, bg=0; cloud and ice positive; RHice=1.2; failure at kdm62d line 2106 before fixture outputs)",
 },
 "compiler_flags":{"O0":["-stand","f08","-warn","all","-check","all","-fpe0","-traceback","-O0","-fp-model","strict","-fimf-arch-consistency=true","-no-ftz"],"O2":["-stand","f08","-warn","all","-fpe0","-traceback","-O2","-fp-model","strict","-fimf-arch-consistency=true","-no-ftz"]},
}
out=evidence
out.parent.mkdir(parents=True,exist_ok=True)
with out.open("x",encoding="utf-8") as stream:json.dump(receipt,stream,indent=2,sort_keys=True);stream.write("\n")
print(f"PR71_EVIDENCE {out}")
PY
