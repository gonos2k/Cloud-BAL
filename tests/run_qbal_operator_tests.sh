#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo_root/tests/intel_toolchain.sh"

mkdir -p "$repo_root/scratch"
build_root=$(mktemp -d "$repo_root/scratch/qbal_operator.XXXXXX")
keep_output=${CLOUD_BAL_KEEP_TEST_OUTPUT:-0}
cleanup() {
  if [[ "$keep_output" == 1 ]]; then
    printf 'QBAL operator test scratch retained: %s\n' "$build_root"
  else
    rm -rf -- "$build_root"
  fi
}
trap cleanup EXIT

qbal_source="$repo_root/src/balance/qbalpe.f"
core_source="$build_root/qbal_operator_core.f"
qbal_source_hash=$(sha256sum "$qbal_source" | awk '{print $1}')

# Keep the exact production fixed-form routines needed by both tests.  The
# qbal_continuity_setup marker is required so a stale/partial extraction cannot
# silently exercise a different operator.  Two source blocks avoid pulling in
# the unrelated legacy/nonlinear routines between the diagnostic and operator
# implementations.
extract_core() {
  local source_path=$1
  local output_path=$2
  awk '
    /^[[:space:]]*subroutine leib_sub\(/ {block=1; capture=1}
    block == 1 && /^[[:space:]]*subroutine analzo\(/ {capture=0}
    block == 1 && capture {print}
    /^[[:space:]]*subroutine qbal_continuity_setup\(/ {block=2; capture=1; found=1}
    block == 2 && /^[[:space:]]*subroutine leib\(/ {capture=0}
    block == 2 && capture {print}
    END {if (!found) exit 1}
  ' "$source_path" > "$output_path"
  test -s "$output_path"
}

extract_core "$qbal_source" "$core_source"

fixed_o2=()
skip_next=0
for flag in "${CLOUD_BAL_FIXED_72_FLAGS[@]}"; do
  if ((skip_next)); then
    skip_next=0
    continue
  fi
  if [[ "$flag" == -check ]]; then
    skip_next=1
    continue
  fi
  fixed_o2+=("${flag/-O0/-O2}")
done

for level in O0 O2; do
  if [[ "$level" == O0 ]]; then
    fixed_flags=("${CLOUD_BAL_FIXED_72_FLAGS[@]}")
    free_flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  else
    fixed_flags=("${fixed_o2[@]}")
    free_flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi

  level_root="$build_root/$level"
  mkdir -p "$level_root"
  (
    cd "$level_root"
    "$CLOUD_BAL_FC" -c "${fixed_flags[@]}" "$core_source" -o qbal_operator_core.o
    "$CLOUD_BAL_FC" "${free_flags[@]}" \
      "$repo_root/tests/test_qbal_operator.f90" qbal_operator_core.o \
      -o test_qbal_operator
    "$CLOUD_BAL_FC" "${free_flags[@]}" \
      "$repo_root/tests/test_qbal_operator_identity.f90" qbal_operator_core.o \
      -o test_qbal_operator_identity
    ./test_qbal_operator
    ./test_qbal_operator_identity
  )
  printf 'QBAL operator Intel %s tests passed\n' "$level"
done

# Focused negative controls ensure that the tests detect the two easy-to-miss
# algebra regressions: weighting the physical RHS by beta and shifting the
# east-face row lookup.  Mutants live only in the disposable scratch tree.
python3 - "$qbal_source" "$build_root/rhs_beta_mutant.f" \
  "$build_root/row_lookup_mutant.f" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
mutations = [
    (Path(sys.argv[2]),
     "     &                                    dx,dy,dp,i,j,k)",
     "     &                                    dx,dy,dp,i,j,k)*beta(i,j,k)",
     "beta-weighted RHS"),
    (Path(sys.argv[3]),
     "c(1)=cx(i,j-1,k-1)/dble(dx(i,j))",
     "c(1)=cx(i,j,k-1)/dble(dx(i,j))",
     "shifted row lookup"),
]
for path, old, new, name in mutations:
    if source.count(old) != 1:
        raise SystemExit(f"{name} mutation target count is not one")
    path.write_text(source.replace(old, new), encoding="utf-8")
PY

for mutation in rhs_beta row_lookup; do
  mutation_source="$build_root/${mutation}_mutant.f"
  mutation_root="$build_root/mutation_${mutation}"
  mkdir -p "$mutation_root"
  extract_core "$mutation_source" "$mutation_root/qbal_operator_core.f"
  (
    cd "$mutation_root"
    "$CLOUD_BAL_FC" -c "${CLOUD_BAL_FIXED_72_FLAGS[@]}" \
      qbal_operator_core.f -o qbal_operator_core.o
    "$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
      "$repo_root/tests/test_qbal_operator_identity.f90" \
      qbal_operator_core.o -o test_qbal_operator_identity
    set +e
    ./test_qbal_operator_identity > mutation.log 2>&1
    mutation_status=$?
    set -e
    if ((mutation_status == 0)) || ! rg -F -q \
      'QBAL independent operator tests failed' mutation.log; then
      printf 'operator identity mutation was not detected: %s\n' "$mutation" >&2
      exit 1
    fi
  )
  printf 'QBAL operator mutation detected: %s\n' "$mutation"
done

if [[ "$(sha256sum "$qbal_source" | awk '{print $1}')" != "$qbal_source_hash" ]]; then
  printf 'production qbal source changed during focused tests\n' >&2
  exit 1
fi

python3 "$repo_root/tests/test_qbal_component_diagnostics.py"
python3 "$repo_root/tests/test_qbal_boundary_diagnostics.py"
