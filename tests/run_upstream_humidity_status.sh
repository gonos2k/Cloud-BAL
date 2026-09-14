#!/usr/bin/env bash
# Bounded status/rollback test for the upstream humidity overlay.
#
# The real lq3driver main is compiled unchanged.  Its data-producing
# lq3_driver1a dependency is never linked: test_upstream_humidity_status.f
# supplies only controlled external stubs and uses scratch systime.dat files.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(cd "$repo_root/.." && pwd)
overlay="$repo_root/src/humid/lq3driver.f"
stub_source="$repo_root/tests/test_upstream_humidity_status.f"
include_root="$workspace_root/klaps-v5.0_/src/include"

[[ -f "$overlay" && -f "$stub_source" && \
   -f "$include_root/lapsparms.cmn" && -f "$include_root/bgdata.inc" && \
   -f "$include_root/grid_fname.cmn" ]] || {
  printf 'upstream humidity overlay, test source, or include is missing\n' >&2
  exit 2
}

. "$repo_root/tests/intel_toolchain.sh"

scratch_root="$repo_root/scratch"
mkdir -p "$scratch_root"
test_tmp=$(mktemp -d "$scratch_root/upstream_humidity_status.XXXXXX")
if [[ ${CLOUD_BAL_KEEP_TEST_OUTPUT:-0} == 1 ]]; then
  trap 'printf "upstream humidity status artifacts retained: %s\n" "$test_tmp"' EXIT
else
  trap 'rm -rf -- "$test_tmp"' EXIT
fi

inputs=(
  "$overlay"
  "$stub_source"
  "$CLOUD_BAL_FC"
  "$include_root/lapsparms.cmn"
  "$include_root/bgdata.inc"
  "$include_root/grid_fname.cmn"
  "$repo_root/tests/intel_toolchain.sh"
  "${BASH_SOURCE[0]}"
)
sha256sum "${inputs[@]}" >"$test_tmp/inputs.before.sha256"

fail() {
  printf 'upstream humidity status test: %s\n' "$*" >&2
  exit 1
}

compile() {
  local log=$1
  shift
  if ! "$CLOUD_BAL_FC" "$@" >"$log" 2>&1; then
    cat "$log" >&2
    exit 1
  fi
}

fixed_o0=("${CLOUD_BAL_FIXED_72_FLAGS[@]}")
fixed_o2=("${CLOUD_BAL_FIXED_72_FLAGS[@]}" -O2)

build_variant() {
  local tag=$1
  local -n flags=$2
  local build="$test_tmp/$tag"
  mkdir -p "$build"
  compile "$build/build.log" "${flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" "$overlay" "$stub_source" \
    -o "$build/lq3driver_status.exe"
  printf '%s\n' "$build"
}

build_o0=$(build_variant o0 fixed_o0)
build_o2=$(build_variant o2 fixed_o2)

write_systime() {
  local input_dir=$1
  local mode=$2
  rm -f -- "$input_dir/systime.dat"
  case "$mode" in
    valid)
      printf '%s\n %s\n' 123456789 123456789 >"$input_dir/systime.dat" ;;
    malformedheader)
      printf '%s\n %s\n' not-an-integer 123456789 >"$input_dir/systime.dat" ;;
    truncatedtime)
      printf '%s\n' 123456789 >"$input_dir/systime.dat" ;;
    *)
      fail "unknown systime mode: $mode" ;;
  esac
}

run_case() {
  local build=$1
  local case_name=$2
  local expected_status=$3
  local file_mode=$4
  local expected_driver_calls=$5
  local input_dir="$test_tmp/input_$(basename "$build")"
  local log="$test_tmp/${case_name}_$(basename "$build").log"
  local status before_hash after_hash driver_calls

  mkdir -p "$input_dir"
  if [[ $file_mode == missing ]]; then
    rm -f -- "$input_dir/systime.dat"
  else
    write_systime "$input_dir" "$file_mode"
  fi
  before_hash=''
  if [[ -f "$input_dir/systime.dat" ]]; then
    before_hash=$(sha256sum "$input_dir/systime.dat" | cut -d' ' -f1)
  fi

  set +e
  UPSTREAM_HUMIDITY_CASE="$case_name" \
    UPSTREAM_HUMIDITY_INPUT_DIR="$input_dir" \
    "$build/lq3driver_status.exe" >"$log" 2>&1
  status=$?
  set -e
  [[ $status -eq $expected_status ]] || {
    cat "$log" >&2
    fail "case $case_name returned $status, expected $expected_status"
  }

  if (( expected_status == 0 )); then
    rg -q 'LQ3_PRODUCER_SUCCESS' "$log" || {
      cat "$log" >&2
      fail "case $case_name lacked success marker"
    }
    ! rg -q 'LQ3_PRODUCER_FAILED' "$log" || fail "case $case_name emitted failure marker"
  else
    rg -q 'LQ3_PRODUCER_FAILED' "$log" || {
      cat "$log" >&2
      fail "case $case_name lacked failure marker"
    }
    ! rg -q 'LQ3_PRODUCER_SUCCESS' "$log" || fail "case $case_name emitted success marker"
  fi
  if [[ $file_mode == missing && -e "$input_dir/systime.dat" ]]; then
    fail "missing-file case created systime.dat"
  fi
  if [[ -n $before_hash ]]; then
    after_hash=$(sha256sum "$input_dir/systime.dat" | cut -d' ' -f1)
    [[ $after_hash == "$before_hash" ]] || \
      fail "case $case_name changed existing systime.dat"
  fi
  driver_calls=$(rg -c '^LQ3_STUB_ENTERED$' "$log" || true)
  [[ ${driver_calls:-0} == "$expected_driver_calls" ]] || {
    cat "$log" >&2
    fail "case $case_name entered producer $driver_calls times, expected $expected_driver_calls"
  }
  printf 'UPSTREAM_HUMIDITY_CASE_PASS %s %s\n' "$case_name" "$(basename "$build")"
}

for build in "$build_o0" "$build_o2"; do
  run_case "$build" configbad 1 valid 0
  run_case "$build" griddim0 1 valid 0
  run_case "$build" cycle0 1 valid 0
  run_case "$build" missingfile 1 missing 0
  run_case "$build" malformedheader 1 malformedheader 0
  run_case "$build" truncatedtime 1 truncatedtime 0
  run_case "$build" parsefail 1 valid 0
  run_case "$build" timemismatch 1 valid 0
  run_case "$build" untouchedjstatus 1 valid 1
  run_case "$build" onlyLH3 1 valid 1
  run_case "$build" onlyLH4 1 valid 1
  run_case "$build" lq3only 0 valid 1
  run_case "$build" fullsuccess 0 valid 1
done

sha256sum -c --status "$test_tmp/inputs.before.sha256"
sha256sum "${inputs[@]}" >"$test_tmp/inputs.after.sha256"
cmp -s "$test_tmp/inputs.before.sha256" "$test_tmp/inputs.after.sha256" || \
  fail 'source/compiler/runner/include hashes changed during test'

printf '%s\n' 'UPSTREAM_HUMIDITY_STATUS_TEST_PASS'
