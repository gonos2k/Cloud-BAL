#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
maintained_root=$(cd "$repo_root/../../.." && pwd)
snapshot_default="$maintained_root/scratch/baudit_20260917/run/operator_snapshot.bin"
snapshot=${1:-$snapshot_default}
output_prefix=${2:-$repo_root/scratch/qbal_real_operator_rows}
expected_snapshot_sha256=96932e53e5f30bf3e9c307617765aaa7200750ec01d4ead6b45842faf97fa661
expected_source_sha256=63a8fd2e1f7a0025e02efa91d77bfe576452c83810f7ba676ee936dc97b60e17

[[ -s "$snapshot" ]] || {
  printf 'actual operator snapshot is required: %s\n' "$snapshot" >&2
  exit 2
}
snapshot_sha256=$(sha256sum "$snapshot" | cut -d' ' -f1)
[[ "$snapshot_sha256" == "$expected_snapshot_sha256" ]] || {
  printf 'unexpected actual operator snapshot SHA-256: %s\n' "$snapshot_sha256" >&2
  exit 2
}

. "$repo_root/tests/intel_toolchain.sh"

mkdir -p "$repo_root/scratch"
build_root=$(mktemp -d "$repo_root/scratch/qbal_real_operator.XXXXXX")
keep_output=${CLOUD_BAL_KEEP_TEST_OUTPUT:-0}
cleanup() {
  if [[ "$keep_output" == 1 ]]; then
    printf 'QBAL actual operator build scratch retained: %s\n' "$build_root"
  else
    rm -rf -- "$build_root"
  fi
}
trap cleanup EXIT

source_sha_before=$(sha256sum "$repo_root/src/balance/qbalpe.f" | cut -d' ' -f1)
snapshot_sha_before=$snapshot_sha256
[[ "$source_sha_before" == "$expected_source_sha256" ]] || {
  printf 'unexpected production source SHA-256: %s\n' "$source_sha_before" >&2
  exit 2
}
printf 'QBAL actual operator source SHA256: %s\n' "$source_sha_before"
printf 'QBAL actual operator snapshot SHA256: %s\n' "$snapshot_sha_before"

core_source="$build_root/qbal_real_operator_core.f"
awk '
  /^      subroutine continuity_point\(/ {capture_point=1}
  capture_point && /^      subroutine continuity_metrics\(/ {capture_point=0}
  capture_point {print}
  /^      subroutine qbal_continuity_setup\(/ {capture_core=1}
  capture_core && /^      subroutine leibp3\(/ {capture_core=0}
  capture_core {print}
' "$repo_root/src/balance/qbalpe.f" > "$core_source"
grep -Eq '^      subroutine continuity_point\(' "$core_source"
grep -Eq '^      subroutine qbal_continuity_setup\(' "$core_source"
grep -Eq '^      subroutine qbal_multiplier_increment\(' "$core_source"
grep -Eq '^      subroutine qbal_continuity_row\(' "$core_source"

fixed_o2=()
skip_next=0
for flag in "${CLOUD_BAL_FIXED_72_FLAGS[@]}"; do
  if (( skip_next )); then
    skip_next=0
    continue
  fi
  if [[ "$flag" == -check ]]; then
    skip_next=1
    continue
  fi
  fixed_o2+=("${flag/-O0/-O2}")
done

output_dir=${output_prefix%/*}
if [[ "$output_dir" == "$output_prefix" ]]; then
  output_dir=.
fi
mkdir -p "$output_dir"

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
  output_path="$output_prefix.$level.bin"
  rm -f -- "$output_path"
  (
    cd "$level_root"
    "$CLOUD_BAL_FC" -c "${fixed_flags[@]}" "$core_source" -o qbal_real_operator_core.o
    "$CLOUD_BAL_FC" "${free_flags[@]}" \
      "$repo_root/tests/test_qbal_real_operator.f90" \
      qbal_real_operator_core.o -o test_qbal_real_operator
    ./test_qbal_real_operator "$snapshot" "$output_path"
  )
  printf 'QBAL actual operator Intel %s output: %s\n' "$level" "$output_path"
  sha256sum "$output_path"
done

source_sha_after=$(sha256sum "$repo_root/src/balance/qbalpe.f" | cut -d' ' -f1)
snapshot_sha_after=$(sha256sum "$snapshot" | cut -d' ' -f1)
[[ "$source_sha_after" == "$source_sha_before" ]] || {
  printf 'production source changed during audit\n' >&2
  exit 1
}
[[ "$snapshot_sha_after" == "$snapshot_sha_before" ]] || {
  printf 'actual snapshot changed during audit\n' >&2
  exit 1
}

cmp -s "$output_prefix.O0.bin" "$output_prefix.O2.bin" || {
  printf 'O0/O2 sparse exports differ\n' >&2
  exit 1
}

diagnostic_script="$repo_root/tests/diagnose_qbal_components.py"
[[ -f "$diagnostic_script" ]] || {
  printf 'sparse component diagnostic is required: %s\n' "$diagnostic_script" >&2
  exit 2
}
diagnostic_output="$output_prefix.components.json"
python3 "$diagnostic_script" "$output_prefix.O0.bin" "$diagnostic_output"
python3 - "$diagnostic_output" <<'PY'
import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text())
counts = {}
for component in result['components']:
    key = component['compatibility']
    counts[key] = counts.get(key, 0) + 1
component_count = len(result['components'])
anchored_count = sum(bool(component['anchored']) for component in result['components'])
singleton_count = sum(component['rows'] == 1 for component in result['components'])
component_rows = sorted(component['rows'] for component in result['components'])
expected = {
    'active_rows': 723638,
    'component_count': 8,
    'incompatible': 8,
    'anchored': 0,
    'singleton_zero_rows': 4,
    'component_rows': [1, 1, 1, 1, 135, 453, 670, 722376],
}
actual = {
    'active_rows': result['active_rows'],
    'component_count': component_count,
    'incompatible': counts.get('INCOMPATIBLE', 0),
    'anchored': anchored_count,
    'singleton_zero_rows': singleton_count,
    'component_rows': component_rows,
}
if actual != expected:
    raise SystemExit(f'unexpected component audit result: {actual}')
print('QBAL sparse component audit: 8 INCOMPATIBLE closed components; 0 anchored; 4 singleton zero rows')
print('QBAL sparse component audit is not a physical PASS or after-state acceptance')
PY

printf '%s\n' 'QBAL actual operator audit passed build/run checks; no after-state acceptance performed'
