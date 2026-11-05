#!/usr/bin/env bash
set -uo pipefail

runner_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
bundle_dir=$(cd "$runner_dir/.." && pwd)
repo_root=$(git -C "$runner_dir" rev-parse --show-toplevel)
scratch_root=$repo_root/runtime/arithmetic_check
mkdir -p "$scratch_root"
run_stamp=$(date -u +%Y%m%dT%H%M%SZ)
run_dir=$scratch_root/attempt_${run_stamp}_$$
mkdir "$run_dir" || exit 2

cp "$bundle_dir/source/rounding_check.f90" "$run_dir/rounding_check.f90"
cp "$bundle_dir/inputs/phi_terms.hex" "$run_dir/phi_terms.hex"

if ! source "$repo_root/tests/intel_toolchain.sh"; then
  printf 'profile initialization failed\n' > "$run_dir/status.txt"
  cp "$run_dir/status.txt" "$bundle_dir/logs/profile_status.txt"
  exit 2
fi

{
  printf 'run_dir=%s\n' "$run_dir"
  printf 'compiler=%s\n' "$CLOUD_BAL_FC"
  printf 'compiler_version=%s\n' "$($CLOUD_BAL_FC --version 2>&1 | sed -n '1p')"
  printf 'free_flags='; printf '%q ' "${CLOUD_BAL_FREE_FLAGS[@]}"; printf '\n'
  printf 'repro_flags='; printf '%q ' "${CLOUD_BAL_REPRO_FLAGS[@]}"; printf '\n'
  printf 'profile_sha256='; sha256sum "$repo_root/tests/intel_toolchain.sh" | cut -d' ' -f1
  printf 'ifx_sha256='; sha256sum "$CLOUD_BAL_FC" | cut -d' ' -f1
  printf 'libimf_sha256='; sha256sum /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libimf.so | cut -d' ' -f1
  printf 'libintlc_sha256='; sha256sum /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libintlc.so.5 | cut -d' ' -f1
} > "$run_dir/toolchain.txt"

set +e
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" "$run_dir/rounding_check.f90" -o "$run_dir/rounding_check_o0" > "$run_dir/compile_o0.log" 2>&1
status_o0_compile=$?
"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" "$run_dir/rounding_check.f90" -o "$run_dir/rounding_check_o2" > "$run_dir/compile_o2.log" 2>&1
status_o2_compile=$?
if [[ $status_o0_compile -eq 0 ]]; then
  (cd "$run_dir" && ./rounding_check_o0) > "$run_dir/o0.stdout" 2> "$run_dir/o0.stderr"
  status_o0_run=$?
else status_o0_run=125; fi
if [[ $status_o2_compile -eq 0 ]]; then
  (cd "$run_dir" && ./rounding_check_o2) > "$run_dir/o2.stdout" 2> "$run_dir/o2.stderr"
  status_o2_run=$?
else status_o2_run=125; fi
if [[ $status_o0_run -eq 0 && $status_o2_run -eq 0 ]]; then
  python3 -B "$runner_dir/validate_results.py" \
    --rows "$bundle_dir/inputs/phi_rows.json" \
    --o0 "$run_dir/o0.stdout" --o2 "$run_dir/o2.stdout" \
    --results "$bundle_dir/results/arithmetic_results.csv" \
    --summary "$bundle_dir/results/arithmetic_summary.json" \
    > "$run_dir/validation.log" 2>&1
  status_validate=$?
else status_validate=125; fi
set -e

{
  printf 'status_o0_compile=%s\n' "$status_o0_compile"
  printf 'status_o2_compile=%s\n' "$status_o2_compile"
  printf 'status_o0_run=%s\n' "$status_o0_run"
  printf 'status_o2_run=%s\n' "$status_o2_run"
  printf 'status_validate=%s\n' "$status_validate"
  printf 'run_dir=%s\n' "$run_dir"
} > "$run_dir/status.txt"
for name in toolchain.txt compile_o0.log compile_o2.log o0.stdout o0.stderr o2.stdout o2.stderr validation.log status.txt; do
  [[ -f "$run_dir/$name" ]] && cp "$run_dir/$name" "$bundle_dir/logs/$name"
done
python3 -B "$runner_dir/write_receipt.py" "$run_dir" "$status_o0_compile" "$status_o2_compile" \
  "$status_o0_run" "$status_o2_run" "$status_validate"

if [[ $status_o0_compile -ne 0 || $status_o2_compile -ne 0 || \
      $status_o0_run -ne 0 || $status_o2_run -ne 0 || $status_validate -ne 0 ]]; then
  exit 1
fi
printf 'PASS O0/O2 arithmetic check: %s\n' "$run_dir"
