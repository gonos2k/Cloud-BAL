#!/usr/bin/env bash
# Bounded status/cleanup test for the upstream OpenMP wind main.
# Only the real main and controlled external stubs are linked; Barnes and the
# real wind producer are deliberately excluded.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(cd "$repo_root/.." && pwd)
main_source="$repo_root/src/upstream/wind_openmp/main.f"
sub_source="$repo_root/src/upstream/wind_openmp/main_sub.f"
stub_source="$repo_root/tests/test_upstream_wind_status.f"
include_root="$workspace_root/klaps-v5.0_/src/include"

[[ -f "$main_source" && -f "$sub_source" && -f "$stub_source" && \
   -f "$include_root/windparms.inc" && -f "$include_root/main_sub.inc" ]] || {
  printf 'upstream wind source, test source, or include is missing\n' >&2
  exit 2
}

. "$repo_root/tests/intel_toolchain.sh"

scratch_root="$repo_root/scratch"
mkdir -p "$scratch_root"
test_tmp=$(mktemp -d "$scratch_root/upstream_wind_status.XXXXXX")
if [[ ${CLOUD_BAL_KEEP_TEST_OUTPUT:-0} == 1 ]]; then
  trap 'printf "upstream wind status artifacts retained: %s\n" "$test_tmp"' EXIT
else
  trap 'rm -rf -- "$test_tmp"' EXIT
fi

inputs=(
  "$main_source" "$sub_source" "$stub_source" "$CLOUD_BAL_FC"
  "$include_root/windparms.inc" "$include_root/main_sub.inc"
  "$repo_root/tests/intel_toolchain.sh" "${BASH_SOURCE[0]}"
)
sha256sum "${inputs[@]}" >"$test_tmp/inputs.before.sha256"

fail() {
  printf 'upstream wind status test: %s\n' "$*" >&2
  exit 1
}

lw3_line=$(rg -n -m1 'istat_lw3[[:space:]]*\.eq\.[[:space:]]*1' "$sub_source" |
  cut -d: -f1 || true)
lw3_status_line=$(rg -n -m1 'j_status[[:space:]]*\([[:space:]]*n_lw3[[:space:]]*\)[[:space:]]*=[[:space:]]*ss_normal' \
  "$sub_source" | cut -d: -f1 || true)
[[ -n "$lw3_line" && -n "$lw3_status_line" && $lw3_status_line -gt $lw3_line ]] ||
  fail 'LW3 acceptance anchors missing or out of order'

compile() {
  local log=$1
  shift
  if ! "$CLOUD_BAL_FC" "$@" >"$log" 2>&1; then
    cat "$log" >&2
    exit 1
  fi
}

awk '/^[[:space:]]*[Ss][Uu][Bb][Rr][Oo][Uu][Tt][Ii][Nn][Ee][[:space:]]+/ { exit } { print }' \
  "$main_source" >"$test_tmp/wind_main.f"
[[ -s "$test_tmp/wind_main.f" ]] || fail 'wind main extraction failed'
awk '/^[[:space:]]*[Pp][Rr][Oo][Gg][Rr][Aa][Mm][[:space:]]+wind_status_test[[:space:]]*$/ { exit } { print }' \
  "$stub_source" >"$test_tmp/stubs.f"
[[ -s "$test_tmp/stubs.f" ]] || fail 'wind stub extraction failed'

fixed_o0=("${CLOUD_BAL_FIXED_72_FLAGS[@]}" -qopenmp)
fixed_o2=("${CLOUD_BAL_FIXED_72_FLAGS[@]}" -O2 -qopenmp)

build_variant() {
  local tag=$1
  local -n flags=$2
  local build="$test_tmp/$tag"
  mkdir -p "$build"
  compile "$build/main.log" "${flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" -c "$test_tmp/wind_main.f" \
    -o "$build/wind_main.o"
  compile "$build/stubs.log" "${flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" -c "$test_tmp/stubs.f" \
    -o "$build/stubs.o"
  compile "$build/link.log" "${flags[@]}" -qopenmp \
    "$build/wind_main.o" "$build/stubs.o" -o "$build/wind_main.exe"
  awk '/^[[:space:]]*[Ss][Uu][Bb][Rr][Oo][Uu][Tt][Ii][Nn][Ee][[:space:]]+wind_post_process[[:space:]]*\(/ { in_sub = 1 }
       in_sub { print }
       in_sub && /^[[:space:]]*[Ee][Nn][Dd][[:space:]]*$/ { exit }' \
    "$sub_source" >"$build/wind_post_process.f"
  [[ -s "$build/wind_post_process.f" ]] || fail 'wind_post_process extraction failed'
  compile "$build/post.log" "${flags[@]}" -qopenmp -module "$build" \
    -I "$build" -I "$include_root" -c "$build/wind_post_process.f" \
    -o "$build/wind_post_process.o"
  compile "$build/post-harness.log" "${flags[@]}" -qopenmp -module "$build" \
    -I "$build" -I "$include_root" -c "$stub_source" \
    -o "$build/post_harness.o"
  compile "$build/post-link.log" "${flags[@]}" -qopenmp \
    "$build/wind_post_process.o" "$build/post_harness.o" \
    -o "$build/wind_post_status.exe"
  printf '%s\n' "$build"
}

build_o0=$(build_variant o0 fixed_o0)
build_o2=$(build_variant o2 fixed_o2)

run_case() {
  local build=$1 case_name=$2 expected_status=$3 expected_calls=$4 expect_log=$5
  local case_dir="$test_tmp/${case_name}_$(basename "$build")"
  local log="$test_tmp/${case_name}_$(basename "$build").log"
  local status calls wind_log
  mkdir -p "$case_dir"
  if [[ $case_name == logopenfail ]]; then
    case_dir="$test_tmp/no-such-parent/$case_name"
  fi
  set +e
  UPSTREAM_WIND_CASE="$case_name" UPSTREAM_WIND_LOG_DIR="$case_dir" \
    "$build/wind_main.exe" >"$log" 2>&1
  status=$?
  set -e
  [[ $status -eq $expected_status ]] || { cat "$log" >&2; fail "$case_name status $status expected $expected_status"; }
  if (( expected_status == 0 )); then
    rg -q 'WIND_PRODUCER_SUCCESS' "$log" || fail "missing wind success: $case_name"
    ! rg -q 'WIND_PRODUCER_FAILED' "$log" || fail "unexpected wind failure: $case_name"
  else
    rg -q 'WIND_PRODUCER_FAILED' "$log" || fail "missing wind failure: $case_name"
    ! rg -q 'WIND_PRODUCER_SUCCESS' "$log" || fail "unexpected wind success: $case_name"
  fi
  calls=$(rg -c '^WIND_STUB_ENTERED$' "$log" || true)
  [[ ${calls:-0} == "$expected_calls" ]] || fail "$case_name stub entries $calls"
  wind_log="$case_dir/wind_stats.log"
  if (( expect_log == 1 )); then
    [[ -f "$wind_log" ]] || fail "$case_name did not create controlled log"
    if (( expected_calls == 1 )); then
      rg -q '^WIND_STUB_LOG$' "$wind_log" || fail "$case_name log lacks stub marker"
    fi
  else
    [[ ! -e "$wind_log" ]] || fail "$case_name opened log unexpectedly"
  fi
  printf 'UPSTREAM_WIND_CASE_PASS %s %s\n' "$case_name" "$(basename "$build")"
}

for build in "$build_o0" "$build_o2"; do
  run_case "$build" time_failure 1 0 0
  run_case "$build" grid_failure 1 0 0
  run_case "$build" dim_failure 1 0 0
  run_case "$build" invalid_x 1 0 0
  run_case "$build" invalid_y 1 0 0
  run_case "$build" invalid_z 1 0 0
  run_case "$build" logopenfail 1 0 0
  run_case "$build" logunset 1 0 0
  run_case "$build" maxradars_failure 1 0 1
  run_case "$build" obs_failure 1 0 1
  run_case "$build" missing_failure 1 0 1
  run_case "$build" i2_missing_failure 1 0 1
  run_case "$build" negative_metadata 1 0 1
  run_case "$build" negative_radars 1 0 1
  run_case "$build" zero_radars 0 1 1
  run_case "$build" untouched 1 1 1
  run_case "$build" lwm_only 1 1 1
  run_case "$build" wrong_time 1 1 1
  run_case "$build" no_products 1 1 1
  run_case "$build" lw3_only 0 1 1
  run_case "$build" full 0 1 1
  post_log="$test_tmp/post_$(basename "$build").log"
  "$build/wind_post_status.exe" >"$post_log" 2>&1 || {
    cat "$post_log" >&2
    fail "wind_post_process harness failed for $(basename "$build")"
  }
  rg -q '^UPSTREAM_WIND_POST_TEST_PASS$' "$post_log" || {
    cat "$post_log" >&2
    fail 'wind_post_process pass marker missing'
  }
done

sha256sum -c --status "$test_tmp/inputs.before.sha256"
sha256sum "${inputs[@]}" >"$test_tmp/inputs.after.sha256"
cmp -s "$test_tmp/inputs.before.sha256" "$test_tmp/inputs.after.sha256" || fail 'test inputs changed'
printf '%s\n' 'UPSTREAM_WIND_STATUS_TEST_PASS'
