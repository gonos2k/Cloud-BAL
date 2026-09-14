#!/usr/bin/env bash
# Isolated status/rollback test for the real upstream temperature overlay.
# Every data-producing dependency is replaced by test_upstream_temperature_status.f90.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(cd "$repo_root/.." && pwd)
overlay="$repo_root/src/temp/puttmpanal_drv.f"
stub_source="$repo_root/tests/test_upstream_temperature_status.f90"
include_root="$workspace_root/klaps-v5.0_/src/include"

[[ -f "$overlay" && -f "$stub_source" && -f "$include_root/laps_static_parameters.inc" ]] || {
  printf 'upstream temperature overlay or include is missing\n' >&2
  exit 2
}

. "$repo_root/tests/intel_toolchain.sh"

scratch_root="$repo_root/scratch"
mkdir -p "$scratch_root"
test_tmp=$(mktemp -d "$scratch_root/upstream_temperature_status.XXXXXX")
if [[ ${CLOUD_BAL_KEEP_TEST_OUTPUT:-0} == 1 ]]; then
  trap 'printf "upstream temperature status artifacts retained: %s\n" "$test_tmp"' EXIT
else
  trap 'rm -rf -- "$test_tmp"' EXIT
fi

fixed_common=(-fixed -extend-source 72 -g -traceback -fpe0 -fp-model strict)
free_common=(-stand f08 -warn all -g -traceback -fpe0 -fp-model strict)
fixed_o0=("${fixed_common[@]}" -O0 -check all)
fixed_o2=("${fixed_common[@]}" -O2)
free_o0=("${free_common[@]}" -O0 -check all)
free_o2=("${free_common[@]}" -O2)

sha256sum "$overlay" "$stub_source" "$CLOUD_BAL_FC" \
  "$include_root/laps_static_parameters.inc" \
  "$repo_root/tests/intel_toolchain.sh" "${BASH_SOURCE[0]}" \
  >"$test_tmp/inputs.sha256"

compile() {
  local log=$1
  shift
  if ! "$CLOUD_BAL_FC" "$@" >"$log" 2>&1; then
    cat "$log" >&2
    exit 1
  fi
}

# The main executable links the overlay exactly as supplied by the parent,
# with only the external routines from the test source.
sed '/^PROGRAM test_laps_temp_status$/,$d' "$stub_source" >"$test_tmp/stubs.f90"

build_variant() {
  local tag=$1
  local -n fixed_flags=$2
  local -n free_flags=$3
  local build="$test_tmp/$tag"
  mkdir -p "$build"

  compile "$build/overlay.log" "${fixed_flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" \
    -c "$overlay" -o "$build/overlay.o"
  compile "$build/stubs.log" "${free_flags[@]}" -module "$build" -I "$build" \
    -c "$test_tmp/stubs.f90" -o "$build/stubs.o"
  compile "$build/main-link.log" "${fixed_flags[@]}" \
    "$build/overlay.o" "$build/stubs.o" -o "$build/temperature_main.exe"

  # Extract only the real laps_temp subroutine, leaving its implementation
  # untouched while avoiding a second PROGRAM during harness linking.
  sed -n '/^[[:space:]]*subroutine laps_temp/,/^[[:space:]]*end[[:space:]]*$/p' \
    "$overlay" >"$build/laps_temp_only.f"
  [[ -s "$build/laps_temp_only.f" ]] || {
    printf 'laps_temp extraction failed\n' >&2
    exit 1
  }
  compile "$build/laps_temp.log" "${fixed_flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" \
    -c "$build/laps_temp_only.f" -o "$build/laps_temp.o"
  compile "$build/harness.log" "${free_flags[@]}" -module "$build" -I "$build" \
    -I "$include_root" \
    -c "$stub_source" -o "$build/harness.o"
  compile "$build/harness-link.log" "${free_flags[@]}" \
    "$build/laps_temp.o" "$build/harness.o" -o "$build/laps_temp_status.exe"

  cp "$test_tmp/inputs.sha256" "$build/inputs.sha256"
  printf '%s\n' "$build"
}

build_o0=$(build_variant o0 fixed_o0 free_o0)
build_o2=$(build_variant o2 fixed_o2 free_o2)

run_harness() {
  local build=$1
  local log=$2
  if ! "$build/laps_temp_status.exe" >"$log" 2>&1; then
    cat "$log" >&2
    exit 1
  fi
  rg -q '^LAPS_TEMP_STATUS_TEST_PASS$' "$log" || {
    cat "$log" >&2
    printf 'laps_temp harness did not report success\n' >&2
    exit 1
  }
}

run_harness "$build_o0" "$test_tmp/laps_temp_o0.log"
run_harness "$build_o2" "$test_tmp/laps_temp_o2.log"

assert_trace_order() {
  local log=$1
  shift
  local previous=0 token line
  for token in "$@"; do
    line=$(rg -n "^TRACE $token " "$log" | head -1 | cut -d: -f1 || true)
    [[ -n "$line" && $line -gt $previous ]] || {
      cat "$log" >&2
      printf 'missing/out-of-order trace %s in %s\n' "$token" "$log" >&2
      exit 1
    }
    previous=$line
  done
}

run_main_case() {
  local build=$1
  local case_name=$2
  local expected_status=$3
  local log="$test_tmp/${case_name}_$(basename "$build").log"
  local status

  set +e
  UPSTREAM_TEMPERATURE_CASE="$case_name" "$build/temperature_main.exe" >"$log" 2>&1
  status=$?
  set -e
  [[ $status -eq $expected_status ]] || {
    cat "$log" >&2
    printf 'main case %s returned %s, expected %s\n' \
      "$case_name" "$status" "$expected_status" >&2
    exit 1
  }

  if (( expected_status == 0 )); then
    rg -q '^[[:space:]]+LT1_PRODUCER_SUCCESS[[:space:]]*$' "$log" || {
      cat "$log" >&2
      printf 'main case %s lacked success marker\n' "$case_name" >&2
      exit 1
    }
  else
    rg -q '^[[:space:]]+LT1_PRODUCER_FAILED[[:space:]]*$' "$log" || {
      cat "$log" >&2
      printf 'main case %s lacked failure marker\n' "$case_name" >&2
      exit 1
    }
  fi
  case "$case_name" in
    time)
      ! rg -q '^TRACE get_grid_dim_xy ' "$log" ;;
    dim)
      ! rg -q '^TRACE get_laps_dimensions ' "$log" ;;
    dim_z|invaliddim|invaliddim_y|invaliddim_z)
      ! rg -q '^TRACE get_domain_laps ' "$log" ;;
    lt1)
      ! rg -q '^TRACE ghbry ' "$log" ;;
  esac
  printf 'UPSTREAM_MAIN_CASE_PASS %s %s\n' "$case_name" "$(basename "$build")"
}

for build in "$build_o0" "$build_o2"; do
  run_main_case "$build" time 1
  run_main_case "$build" dim 1
  run_main_case "$build" invaliddim 1
  run_main_case "$build" invaliddim_y 1
  run_main_case "$build" dim_z 1
  run_main_case "$build" invaliddim_z 1
  run_main_case "$build" lt1 1
  run_main_case "$build" success 0

  success_log="$test_tmp/success_$(basename "$build").log"
  assert_trace_order "$success_log" \
    get_systime get_grid_dim_xy get_laps_dimensions get_domain_laps \
    get_laps_cycle_time get_laps_2dgrid_T get_laps_2dgrid_PS put_temp_anal \
    ghbry pres_to_ht put_laps_multi_2d ishow_timer
  ! rg -q '^TRACE ghbry 0$' "$success_log"
done

sha256sum -c --status "$test_tmp/inputs.sha256"
printf '%s\n' 'UPSTREAM_TEMPERATURE_STATUS_TEST_PASS'
