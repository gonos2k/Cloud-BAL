#!/usr/bin/env bash
# Focused status/rollback test for the real upstream surface overlays.
# Only the upstream main and writer-status control flow are executed.  All
# data-producing dependencies are controlled stubs; no operational files are
# read or written.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(cd "$repo_root/.." && pwd)
surface_overlay="$repo_root/src/sfc/laps_sfc.f"
vanl_overlay="$repo_root/src/sfc/lapsvanl.f"
stub_source="$repo_root/tests/test_upstream_surface_status.f90"
include_root="$workspace_root/klaps-v5.0_/src/include"

[[ -f "$surface_overlay" && -f "$vanl_overlay" && -f "$stub_source" && \
   -f "$include_root/lapsparms.cmn" && -f "$include_root/bgdata.inc" ]] || {
  printf 'upstream surface overlay, test source, or include is missing\n' >&2
  exit 2
}

. "$repo_root/tests/intel_toolchain.sh"

scratch_root="$repo_root/scratch"
mkdir -p "$scratch_root"
test_tmp=$(mktemp -d "$scratch_root/upstream_surface_status.XXXXXX")
if [[ ${CLOUD_BAL_KEEP_TEST_OUTPUT:-0} == 1 ]]; then
  trap 'printf "upstream surface status artifacts retained: %s\n" "$test_tmp"' EXIT
else
  trap 'rm -rf -- "$test_tmp"' EXIT
fi

sha256sum "$surface_overlay" "$vanl_overlay" "$stub_source" \
  "$CLOUD_BAL_FC" "$include_root/lapsparms.cmn" "$include_root/bgdata.inc" \
  "$repo_root/tests/intel_toolchain.sh" "${BASH_SOURCE[0]}" \
  >"$test_tmp/inputs.before.sha256"

fail() {
  printf 'upstream surface status test: %s\n' "$*" >&2
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

assert_followed_by() {
  local source=$1
  local first_pattern=$2
  local second_pattern=$3
  local first_line
  first_line=$(rg -n -m1 "$first_pattern" "$source" | cut -d: -f1 || true)
  [[ -n "$first_line" ]] || fail "missing source guard anchor: $first_pattern"
  sed -n "${first_line},$((first_line + 12))p" "$source" | \
    rg -q "$second_pattern" || \
    fail "missing source guard after: $first_pattern"
}

# These are source-level assertions for the real laps_sfc_sub branches.  The
# complete data pipeline is deliberately not mocked or executed here.
assert_followed_by "$surface_overlay" \
  'call get_config\(istatus\)' 'stop[[:space:]]+1'
assert_followed_by "$surface_overlay" \
  'call find_domain_name' 'if\(istatus[[:space:]]+\.ne\.[[:space:]]+1\)[[:space:]]+stop[[:space:]]+1'
assert_followed_by "$surface_overlay" \
  'bad istatus from read_surface_data' 'stop[[:space:]]+1'
assert_followed_by "$surface_overlay" \
  'From MDAT_LAPS:.*Error Return' 'stop[[:space:]]+1'
assert_followed_by "$surface_overlay" \
  'if\(jstatus\(3\)[[:space:]]+\.ne\.[[:space:]]+1\)[[:space:]]+then' \
  'stop[[:space:]]+1'

rg -q 'jstatus\(3\)[[:space:]]*=[[:space:]]*-1' "$vanl_overlay" || \
  fail 'lapsvanl no longer initializes jstatus(3) to -1'
assert_followed_by "$vanl_overlay" \
  'jstatus\(3\)[[:space:]]*=[[:space:]]*istatus' \
  'if\(jstatus\(3\)[[:space:]]+\.ne\.[[:space:]]+1\)[[:space:]]+return'

# Extract the real main before laps_sfc_sub.  This keeps the test tied to the
# upstream entry-point control flow while stubbing only its dependencies.
awk '/^[[:space:]]*subroutine[[:space:]]+laps_sfc_sub[[:space:]]*\(/ { exit } { print }' \
  "$surface_overlay" >"$test_tmp/laps_sfc_main.f"
[[ -s "$test_tmp/laps_sfc_main.f" ]] || fail 'laps_sfc main extraction failed'

# Extract only the writer acceptance interval, preserving its original fixed
# form.  The wrapper below supplies all declarations and a no-IO writer.
awk '
  BEGIN { in_block = 0 }
  /^[[:space:]]*[Cc][Aa][Ll][Ll][[:space:]]+write_laps_data[[:space:]]*\(/ { in_block = 1 }
  in_block { print }
  in_block && /I4_elapsed[[:space:]]*=[[:space:]]*ishow_timer[[:space:]]*\(\)/ { exit }
' "$vanl_overlay" >"$test_tmp/writer_status_snippet.f"
[[ -s "$test_tmp/writer_status_snippet.f" ]] || fail 'writer status extraction failed'
rg -q 'jstatus\(3\)[[:space:]]*=[[:space:]]*istatus' \
  "$test_tmp/writer_status_snippet.f" || fail 'writer snippet lacks status assignment'

# Keep the supplied stub source free-form, but compile the real fixed-form
# extracted main and writer interval with the same pinned ifx toolchain.
awk '/^[[:space:]]*PROGRAM[[:space:]]+test_upstream_surface_status[[:space:]]*$/ { exit } { print }' \
  "$stub_source" >"$test_tmp/stubs.f90"

# The common block is fixed-form upstream source.  Keep its initialization in
# a matching fixed-form helper instead of forcing the free-form stubs to parse
# the legacy include.
awk '
  BEGIN {
    print "      SUBROUTINE initialize_surface_common"
    print "      INCLUDE '\''lapsparms.cmn'\''"
    print "      nx_l_cmn = 2"
    print "      ny_l_cmn = 2"
    print "      nk_laps = 2"
    print "      maxstns_cmn = 4"
    print "      laps_cycle_time_cmn = 3600"
    print "      grid_spacing_m_cmn = 1000.0"
    print "      RETURN"
    print "      END"
  }
' >"$test_tmp/common_init.f"

make_writer_wrapper() {
  local output=$1
  local snippet=$2
  awk -v snippet="$snippet" '
    BEGIN {
      print "      SUBROUTINE writer_status_probe(requested_status,jstatus,"
      print "     & elapsed_calls,continued)"
      print "      USE upstream_surface_status_control"
      print "      IMPLICIT NONE"
      print "      INTEGER requested_status,jstatus(20),elapsed_calls"
      print "      INTEGER continued"
      print "      INTEGER i4time,imax,jmax,num_var,len,istatus,I4_elapsed"
      print "      INTEGER ishow_timer"
      print "      INTEGER lvl(24)"
      print "      REAL data(2,2,24)"
      print "      CHARACTER*256 dir"
      print "      CHARACTER*31 ext"
      print "      CHARACTER*3 var(24)"
      print "      CHARACTER*4 lvl_coord(24)"
      print "      CHARACTER*10 units(24)"
      print "      CHARACTER*125 comment(24)"
      print "      i4time = 2026010100"
      print "      imax = 2"
      print "      jmax = 2"
      print "      num_var = 24"
      print "      data = 0.0"
      print "      lvl = 0"
      print "      var = \"   \""
      print "      lvl_coord = \"    \""
      print "      units = \"          \""
      print "      comment = \" \""
      print "      CALL set_writer_status(requested_status)"
      print "      elapsed_calls = timer_calls"
      print "      continued = 0"
      while ((getline line < snippet) > 0) print line
      print "      elapsed_calls = timer_calls"
      print "      continued = 1"
      print "      RETURN"
      print "      END"
    }
  ' >"$output"
}

build_variant() {
  local tag=$1
  local fixed_flags_name=$2
  local free_flags_name=$3
  local -n fixed_flags=$fixed_flags_name
  local -n free_flags=$free_flags_name
  local build="$test_tmp/$tag"
  mkdir -p "$build"

  compile "$build/stubs.log" "${free_flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" -c "$test_tmp/stubs.f90" \
    -o "$build/stubs.o"
  compile "$build/main.log" "${fixed_flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" -c "$test_tmp/laps_sfc_main.f" \
    -o "$build/laps_sfc_main.o"
  compile "$build/common-init.log" "${fixed_flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" -c "$test_tmp/common_init.f" \
    -o "$build/common_init.o"
  compile "$build/main-link.log" "${fixed_flags[@]}" \
    "$build/laps_sfc_main.o" "$build/stubs.o" "$build/common_init.o" \
    -o "$build/surface_main.exe"

  make_writer_wrapper "$build/writer_wrapper.f" "$test_tmp/writer_status_snippet.f"
  compile "$build/writer.log" "${fixed_flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" -c "$build/writer_wrapper.f" \
    -o "$build/writer.o"
  compile "$build/harness.log" "${free_flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" -c "$stub_source" \
    -o "$build/harness.o"
  compile "$build/harness-link.log" "${free_flags[@]}" \
    "$build/writer.o" "$build/harness.o" "$build/common_init.o" \
    -o "$build/writer_status.exe"

  printf '%s\n' "$build"
}

fixed_o0=("${CLOUD_BAL_FIXED_72_FLAGS[@]}")
fixed_o2=("${CLOUD_BAL_FIXED_72_FLAGS[@]}" -O2)
free_o0=("${CLOUD_BAL_FREE_FLAGS[@]}")
free_o2=("${CLOUD_BAL_REPRO_FLAGS[@]}")

build_o0=$(build_variant o0 fixed_o0 free_o0)
build_o2=$(build_variant o2 fixed_o2 free_o2)

run_main_case() {
  local build=$1
  local case_name=$2
  local expected_status=$3
  local log="$test_tmp/${case_name}_$(basename "$build").log"
  local status

  set +e
  UPSTREAM_SURFACE_MAIN_CASE="$case_name" "$build/surface_main.exe" >"$log" 2>&1
  status=$?
  set -e
  [[ $status -eq $expected_status ]] || {
    cat "$log" >&2
    fail "main case $case_name returned $status, expected $expected_status"
  }

  if (( expected_status == 0 )); then
    rg -q '^SURFACE_MAIN_SUB ' "$log" || fail "main success did not call laps_sfc_sub"
  else
    ! rg -q '^SURFACE_MAIN_SUB ' "$log" || fail "main failure called laps_sfc_sub"
  fi
  case "$case_name" in
    config_failure)
      rg -q '^SURFACE_GET_CONFIG 0$' "$log" || fail 'missing config failure'
      ! rg -q '^SURFACE_FIND_DOMAIN ' "$log" || fail 'continued after config failure' ;;
    domain_failure)
      rg -q '^SURFACE_GET_CONFIG 1$' "$log" || fail 'config did not succeed'
      rg -q '^SURFACE_FIND_DOMAIN 0$' "$log" || fail 'missing domain failure' ;;
  esac
  printf 'UPSTREAM_SURFACE_MAIN_CASE_PASS %s %s\n' "$case_name" "$(basename "$build")"
}

run_writer_harness() {
  local build=$1
  local log="$test_tmp/writer_$(basename "$build").log"
  if ! "$build/writer_status.exe" >"$log" 2>&1; then
    cat "$log" >&2
    exit 1
  fi
  rg -q '^UPSTREAM_SURFACE_STATUS_TEST_PASS$' "$log" || {
    cat "$log" >&2
    fail "writer harness did not report success"
  }
}

for build in "$build_o0" "$build_o2"; do
  run_main_case "$build" config_failure 1
  run_main_case "$build" domain_failure 1
  run_main_case "$build" success 0
  run_writer_harness "$build"
done

sha256sum -c --status "$test_tmp/inputs.before.sha256"
sha256sum "$surface_overlay" "$vanl_overlay" "$stub_source" \
  "$CLOUD_BAL_FC" "$include_root/lapsparms.cmn" "$include_root/bgdata.inc" \
  "$repo_root/tests/intel_toolchain.sh" "${BASH_SOURCE[0]}" \
  >"$test_tmp/inputs.after.sha256"
cmp -s "$test_tmp/inputs.before.sha256" "$test_tmp/inputs.after.sha256" || \
  fail 'source/toolchain hashes changed during test'

printf '%s\n' 'UPSTREAM_SURFACE_STATUS_TEST_PASS'
