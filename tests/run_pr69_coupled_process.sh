#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_root/tests/intel_toolchain.sh"
source_file=${PR69_KDM6_SOURCE:-/var/tmp/pr68_velocity_native_20261007/source/module_mp_kdm6_combined_research.f90}
expected_source_sha256=97e9892ff527a318f6266140eecc03238485a68b050c61bbaca7ea94f28bfdaa
if [[ ! -f $source_file ]]; then
  printf 'captured PR68 KDM6 source is required: %s\n' "$source_file" >&2
  exit 2
fi
actual_source_sha256=$(sha256sum "$source_file" | cut -d' ' -f1)
if [[ $actual_source_sha256 != "$expected_source_sha256" ]]; then
  printf 'unexpected captured PR68 source hash: %s\n' "$actual_source_sha256" >&2
  exit 2
fi

work_dir=$(mktemp -d /var/tmp/cloud_bal_pr69_process.XXXXXX)
printf 'WORK_DIR %s\n' "$work_dir"
cp "$source_file" "$work_dir/module_mp_kdm6_combined_research.f90"
patch --fuzz=0 -p0 -d "$work_dir" \
  < "$repo_root/docs/evidence/pr69_coupled_process_20261007.patch" \
  > "$work_dir/patch.log"
python3 - "$work_dir/module_mp_kdm6_combined_research.f90" "$work_dir" <<'PY'
from pathlib import Path
import re
import sys

source_path = Path(sys.argv[1])
work_dir = Path(sys.argv[2])
source = source_path.read_text()

required = (
    "rain_pair_rate_start(i,k,1)=praut(i,k)",
    "rain_pair_rate_start(i,k,2)=nraut(i,k)",
    "rain_pair_rate_start(i,k,3)=praci(i,k)",
    "rain_pair_rate_start(i,k,4)=nraci(i,k)",
    "rain_pair_rate_start(i,k,5)=piacr(i,k)",
    "rain_pair_rate_start(i,k,6)=niacr(i,k)",
    "rain_pair_rate_start(i,k,7)=psacr(i,k)",
    "rain_pair_rate_start(i,k,8)=nsacr(i,k)",
    "rain_pair_rate_start(i,k,9)=pgacr(i,k)",
    "rain_pair_rate_start(i,k,10)=ngacr(i,k)",
    "call kdm6_rain_process_fraction(rain_q_fixed,rain_q_process",
    "rain_q_process(5)=(piacr(i,k)*(1.-delta3)+praci(i,k)*(1.-delta3)",
    "rain_n_process(2)=(-nraci(i,k)-niacr(i,k))*dtcld",
    "call kdm6_mass_volume_rate(pgdep(i,k),rhox(i,k)",
    "rain_bg_fixed=brs(i,k)+(rain_pgdep_bg_rate+rain_pracs_bg_rate",
    "rain_bg_process=(rain_piacr_bg_rate+rain_praci_bg_rate",
    "rain_t_process=xlf*(piacr(i,k)+psacr(i,k)+pgacr(i,k))*dtcld/cpm(i,k)",
    "xlwork2 = -xls*(psdep(i,k)+pgdep(i,k)+pidep(i,k)+pinud(i,k))",
    "qrs(i,k,2) = max(qrs(i,k,2)+(psdep(i,k)+psaut(i,k)+paacw(i,k)",
    "nci(i,k,2) = max(nci(i,k,2)+(-nraci(i,k)-nsaci(i,k)-ngaci(i,k)",
)
for fragment in required:
    if fragment not in source:
        raise SystemExit(f"source coupling check failed: missing {fragment}")
if "rain_bg_fixed=brs(i,k)+(pgdep(i,k)/rhox(i,k)+bracs(i,k)" in source:
    raise SystemExit("graupel-volume preacceptance still reads stale partner-density arrays")
if "source = (-nraut(i,k)+nraci(i,k)+nrcol(i,k)+niacr(i,k)+nsacr(i,k)+ngacr(i,k))*dtcld" in source:
    raise SystemExit("cold limiter still applies a number-only rain rate scale")
if source.count("call kdm6_rain_process_fraction(") != 2:
    raise SystemExit("expected acceptance and stored-endpoint validation calls")
if "KDM6 stored cold endpoint rejected at cell" not in source:
    raise SystemExit("missing validation of exact stored cold endpoint")
for process in ("praut", "praci", "piacr", "psacr", "pgacr"):
    if source.count(f"{process}(i,k)=rain_pair_rate_start") < 1:
        raise SystemExit(f"mass rate {process} is not reconstructed from its raw pair")
if source.count("nrcol(i,k) = nrcol(i,k)*factor") < 1:
    raise SystemExit("rain self-collection is not included in the shared accepted fraction")
for process in ("praut", "praci", "piacr", "psacr", "pgacr",
                "nraut", "nraci", "niacr", "nsacr", "ngacr"):
    if f"{process}(i,k) = {process}(i,k)*factor" not in source:
        raise SystemExit(f"common admissible fraction does not scale {process}")

blocks = []
for name, declaration in (
    ("kdm6_mass_volume_rate", "subroutine"),
    ("kdm6_rain_process_fraction", "subroutine"),
    ("constrain_process_margin", "subroutine"),
    ("kdm6_shared_pair_fraction", "real function"),
):
    match = re.search(
        rf"(?ms)^\s*{declaration} {name}\b.*?^\s*end (?:subroutine|function) {name}\s*$",
        source,
    )
    if not match:
        raise SystemExit(f"missing process helper: {name}")
    blocks.append(match.group().strip())
(work_dir / "pr69_helper.f90").write_text(
    "module pr69_helper\ncontains\n" + "\n\n".join(blocks) + "\nend module pr69_helper\n"
)
print("PR69 source coupling checks passed")
PY
python3 "$repo_root/tests/generate_pr69_source_harness.py" \
  "$work_dir/module_mp_kdm6_combined_research.f90" \
  "$work_dir/pr69_helper.f90" "$work_dir/test_pr69_source_excerpt.f90"

for opt in O0 O2; do
  build_dir="$work_dir/$opt"
  mkdir "$build_dir"
  cp "$work_dir/pr69_helper.f90" "$repo_root/tests/test_pr69_coupled_process.f90" \
    "$repo_root/tests/test_pr69_pair_nonfinite.f90" \
    "$work_dir/test_pr69_source_excerpt.f90" "$build_dir/"
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
  run_logged helper.compile "$CLOUD_BAL_FC" "${flags[@]}" -c pr69_helper.f90
  run_logged helper_test.compile "$CLOUD_BAL_FC" "${flags[@]}" -c test_pr69_coupled_process.f90
  run_logged helper_test.link "$CLOUD_BAL_FC" "${flags[@]}" -o test.exe test_pr69_coupled_process.o pr69_helper.o
  run_logged helper_test.run ./test.exe
  cat helper_test.run.log
  run_logged source_excerpt.compile "$CLOUD_BAL_FC" "${flags[@]}" -c test_pr69_source_excerpt.f90
  run_logged source_excerpt.link "$CLOUD_BAL_FC" "${flags[@]}" -o source_excerpt.exe test_pr69_source_excerpt.o
  run_logged source_excerpt.run ./source_excerpt.exe
  cat source_excerpt.run.log
  run_logged pair_nonfinite.compile "$CLOUD_BAL_FC" "${flags[@]}" -c test_pr69_pair_nonfinite.f90
  run_logged pair_nonfinite.link "$CLOUD_BAL_FC" "${flags[@]}" -o pair_nonfinite.exe test_pr69_pair_nonfinite.o pr69_helper.o
  printf './pair_nonfinite.exe\n' > pair_nonfinite.argv
  set +e
  ./pair_nonfinite.exe > pair_nonfinite.log 2>&1
  pair_status=$?
  set -e
  if [[ $pair_status -eq 0 ]] || ! grep -Fq "paired process limiter received a nonfinite rate" pair_nonfinite.log; then
    cat pair_nonfinite.log >&2
    printf 'nonfinite paired-rate test did not fail through the finite guard\n' >&2
    exit 1
  fi
  if grep -Fq "floating invalid" pair_nonfinite.log; then
    cat pair_nonfinite.log >&2
    printf 'nonfinite paired-rate test trapped before the finite guard\n' >&2
    exit 1
  fi
  printf 'PR69 paired-rate NaN finite guard passed (%s)\n' "$opt"
done

python3 - "$repo_root" "$work_dir" "$source_file" <<'PY'
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

repo, work, source = map(Path, sys.argv[1:])
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
bound_files = {
    "captured_source": source,
    "patched_source": work / "module_mp_kdm6_combined_research.f90",
    "patch": repo / "docs/evidence/pr69_coupled_process_20261007.patch",
    "runner": repo / "tests/run_pr69_coupled_process.sh",
    "intel_profile": repo / "tests/intel_toolchain.sh",
    "helper_test": repo / "tests/test_pr69_coupled_process.f90",
    "paired_nonfinite_test": repo / "tests/test_pr69_pair_nonfinite.f90",
    "source_harness_generator": repo / "tests/generate_pr69_source_harness.py",
    "generated_helper": work / "pr69_helper.f90",
    "generated_source_harness": work / "test_pr69_source_excerpt.f90",
}
for opt in ("O0", "O2"):
    for name in ("helper_test", "source_excerpt", "pair_nonfinite"):
        build = work / opt
        label = {"helper_test": "helper_test.run", "source_excerpt": "source_excerpt.run",
                 "pair_nonfinite": "pair_nonfinite"}[name]
        bound_files[f"{opt}_{name}_argv"] = build / f"{label}.argv"
        bound_files[f"{opt}_{name}_log"] = build / f"{label}.log"
    for name, kinds in (("helper", ("compile",)),
                        ("helper_test", ("compile", "link")),
                        ("source_excerpt", ("compile", "link")),
                        ("pair_nonfinite", ("compile", "link"))):
        for kind in kinds:
            bound_files[f"{opt}_{name}_{kind}_argv"] = work / opt / f"{name}.{kind}.argv"
            bound_files[f"{opt}_{name}_{kind}_log"] = work / opt / f"{name}.{kind}.log"
    for exe in ("test.exe", "source_excerpt.exe", "pair_nonfinite.exe"):
        path = work / opt / exe
        if path.exists():
            bound_files[f"{opt}_{exe}"] = path
receipt = {
    "schema": "pr69_coupled_process_validation_v1",
    "date_utc": "2026-10-07",
    "captured_source": str(source),
    "captured_source_sha256": sha(source),
    "patch": "docs/evidence/pr69_coupled_process_20261007.patch",
    "patch_sha256": sha(repo / "docs/evidence/pr69_coupled_process_20261007.patch"),
    "patched_source_sha256": sha(work / "module_mp_kdm6_combined_research.f90"),
    "compiler": subprocess.check_output(
        [os.environ["CLOUD_BAL_FC"], "--version"], text=True,
        stderr=subprocess.STDOUT).splitlines()[0],
    "compiler_flags": {
        "O0": ["-stand", "f08", "-warn", "all", "-check", "all", "-fpe0", "-traceback", "-O0", "-fp-model", "strict", "-fimf-arch-consistency=true", "-no-ftz"],
        "O2": ["-stand", "f08", "-warn", "all", "-fpe0", "-traceback", "-O2", "-fp-model", "strict", "-fimf-arch-consistency=true", "-no-ftz"],
    },
    "files_sha256": {key: sha(path) for key, path in bound_files.items()},
    "commands_argv": {
        str(path.relative_to(work)): path.read_text().strip()
        for path in bound_files.values() if path.name.endswith(".argv")
    },
    "scratch_work_dir": str(work),
    "checks": {
        "captured_source_identity": "PASS",
        "native_pair_and_update_wiring": "PASS",
        "rain_source_lambda_interval": "PASS",
        "donor_mass_number_volume_and_heat_contract": "PASS",
        "source_extracted_native_cold_update_O0_O2": "PASS",
        "stored_endpoint_validation_after_native_updates": "PASS",
        "source_ordered_BG_partner_rates_and_exact_stored_volume": "PASS",
        "zero_mass_zero_density_volume_rate_supported": "PASS",
        "nonzero_mass_zero_density_rejected": "PASS",
        "exact_zero_number_trial_rejected_by_source_bound": "PASS",
        "density_dependent_admissible_fraction": "PASS",
        "quiet_NaN_and_infinity_finite_first_rejection": "PASS",
        "paired_rate_NaN_finite_guard_expected_failure": "PASS",
        "infeasible_initial_state_rejected": "PASS",
        "intel_ifx_O0": "PASS",
        "intel_ifx_O2": "PASS",
    },
}
(repo / "docs/evidence/pr69_coupled_process_validation_20261007.json").write_text(
    json.dumps(receipt, indent=2) + "\n"
)
PY
printf 'PR69 coupled-process validation passed; receipt: docs/evidence/pr69_coupled_process_validation_20261007.json\n'
