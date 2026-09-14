#!/usr/bin/env bash
# Bounded status and LCO-writer test for the upstream derived producer.
# The main and writer block are mechanically extracted from the real overlays;
# no operational derived-product producer is linked or executed.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(cd "$repo_root/.." && pwd)
main_source="$repo_root/src/upstream/laps_deriv.f"
writer_source="$repo_root/src/upstream/laps_deriv_sub.f"
stub_source="$repo_root/tests/test_upstream_derived_status.f"
adapter_stub="$repo_root/tests/test_upstream_derived_stage_stub.f90"
state_source="$repo_root/src/common/cloud_bal_state.f90"
include_root="$workspace_root/klaps-v5.0_/src/include"

[[ -f "$main_source" && -f "$writer_source" && -f "$stub_source" && \
   -f "$include_root/lapsparms.cmn" && -f "$include_root/bgdata.inc" && \
   -f "$include_root/grid_fname.cmn" ]] || {
  printf 'upstream derived source, test source, or include is missing\n' >&2
  exit 2
}

. "$repo_root/tests/intel_toolchain.sh"

scratch_root="$repo_root/scratch"
mkdir -p "$scratch_root"
test_tmp=$(mktemp -d "$scratch_root/upstream_derived_status.XXXXXX")
if [[ ${CLOUD_BAL_KEEP_TEST_OUTPUT:-0} == 1 ]]; then
  trap 'printf "upstream derived status artifacts retained: %s\n" "$test_tmp"' EXIT
else
  trap 'rm -rf -- "$test_tmp"' EXIT
fi

inputs=(
  "$main_source"
  "$writer_source"
  "$stub_source"
  "$adapter_stub"
  "$state_source"
  "$CLOUD_BAL_FC"
  "$include_root/lapsparms.cmn"
  "$include_root/bgdata.inc"
  "$include_root/grid_fname.cmn"
  "$repo_root/tests/intel_toolchain.sh"
  "${BASH_SOURCE[0]}"
)
sha256sum "${inputs[@]}" >"$test_tmp/inputs.before.sha256"

fail() {
  printf 'upstream derived status test: %s\n' "$*" >&2
  exit 1
}

compile() {
  local log=$1
  shift
  if ! (cd "$(dirname "$log")" && "$CLOUD_BAL_FC" "$@") >"$log" 2>&1; then
    cat "$log" >&2
    exit 1
  fi
}

# Keep only the real program entry point; the production laps_deriv routine is
# deliberately replaced by the controlled stub in the test source.
awk '/^[[:space:]]*[Ss][Uu][Bb][Rr][Oo][Uu][Tt][Ii][Nn][Ee][[:space:]]+laps_deriv[[:space:]]*\(/ { exit } { print }' \
  "$main_source" >"$test_tmp/laps_deriv_main.f"
[[ -s "$test_tmp/laps_deriv_main.f" ]] || fail 'derived main extraction failed'

# Keep only external stubs for the main executable; the test program is linked
# separately into the writer harness below.
awk '/^[[:space:]]*[Pp][Rr][Oo][Gg][Rr][Aa][Mm][[:space:]]+test_upstream_derived_writer[[:space:]]*$/ { exit } { print }' \
  "$stub_source" >"$test_tmp/stubs.f"
[[ -s "$test_tmp/stubs.f" ]] || fail 'derived stub extraction failed'

fixed_o0=("${CLOUD_BAL_FIXED_72_FLAGS[@]}")
fixed_o2=("${CLOUD_BAL_FIXED_72_FLAGS[@]}" -O2)

build_variant() {
  local tag=$1
  local -n flags=$2
  local build="$test_tmp/$tag"
  mkdir -p "$build"

  # Preserve the real main's adapter call while isolating this legacy status
  # fixture from the separately tested full canonical/NetCDF adapter body.
  compile "$build/state.log" "${flags[@]}" -free -module "$build" \
    -I "$build" -c "$state_source" -o "$build/state.o"
  compile "$build/adapter-stub.log" "${flags[@]}" -free -module "$build" \
    -I "$build" -c "$adapter_stub" -o "$build/adapter-stub.o"

  compile "$build/main.log" "${flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" -c "$test_tmp/laps_deriv_main.f" \
    -o "$build/laps_deriv_main.o"
  compile "$build/stubs.log" "${flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" -c "$test_tmp/stubs.f" \
    -o "$build/stubs.o"
  compile "$build/main-link.log" "${flags[@]}" \
    "$build/laps_deriv_main.o" "$build/stubs.o" "$build/adapter-stub.o" \
    -o "$build/derived_main.exe"

  awk '
    BEGIN { in_block = 0 }
    /Write out Cloud derived Omega field/ { in_block = 1 }
    in_block { print }
    in_block && /[Ii]4_elapsed[[:space:]]*=[[:space:]]*ishow_timer/ { exit }
  ' "$writer_source" >"$build/lco_writer_block.f"
  [[ -s "$build/lco_writer_block.f" ]] || fail 'LCO writer block extraction failed'
  rg -q 'j_status[[:space:]]*\([[:space:]]*n_lco[[:space:]]*\)[[:space:]]*=[[:space:]]*sys_abort_prod' \
    "$build/lco_writer_block.f" || fail 'LCO block lacks failure initialization'
  rg -q 'put_laps_multi_3d' "$build/lco_writer_block.f" || fail 'LCO block lacks writer call'
  rg -q 'ishow_timer' "$build/lco_writer_block.f" || fail 'LCO block lacks success timer'

  make_writer_wrapper "$build/lco_writer_probe.f" "$build/lco_writer_block.f"
  compile "$build/writer.log" "${flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" -c "$build/lco_writer_probe.f" \
    -o "$build/lco_writer_probe.o"
  compile "$build/harness.log" "${flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" -c "$stub_source" \
    -o "$build/harness.o"
  compile "$build/harness-link.log" "${flags[@]}" \
    "$build/lco_writer_probe.o" "$build/harness.o" \
    -o "$build/lco_writer_status.exe"
  printf '%s\n' "$build"
}

make_writer_wrapper() {
  local output=$1
  local snippet=$2
  awk -v snippet="$snippet" '
    BEGIN {
      print "      subroutine lco_writer_probe(requested_status,"
      print "     1     observed_status,observed_calls,observed_timer,"
      print "     2     metadata_ok,layout_ok)"
      print "      implicit none"
      print "      integer requested_status,observed_status,observed_calls"
      print "      integer observed_timer,metadata_ok,layout_ok"
      print "      integer i4time,NX_L,NY_L,NZ_L,n_lco,istatus,I4_elapsed"
      print "      integer ishow_timer"
      print "      integer ss_normal,sys_abort_prod"
      print "      parameter(ss_normal=1,sys_abort_prod=4)"
      print "      integer j_status(20),i,j,k"
      print "      real r_missing_data,w_3d(2,3,2)"
      print "      character*31 ext"
      print "      character*3 var"
      print "      character*10 units"
      print "      character*125 comment"
      print "      character*3 var_a(20)"
      print "      character*10 units_a(20)"
      print "      character*125 comment_a(20)"
      print "      integer writer_status_value,writer_calls,timer_calls"
      print "      integer writer_metadata_ok,writer_layout_ok"
      print "      common /derived_writer_control/ writer_status_value,writer_calls,"
      print "     1     timer_calls,writer_metadata_ok,writer_layout_ok"
      print "      i4time=123456789"
      print "      NX_L=2"
      print "      NY_L=3"
      print "      NZ_L=2"
      print "      n_lco=10"
      print "      r_missing_data=-9999.0"
      print "      j_status=3"
      print "      var_a=\"   \""
      print "      units_a=\"          \""
      print "      comment_a=\" \""
      print "      do k=1,NZ_L"
      print "        do j=1,NY_L"
      print "          do i=1,NX_L"
      print "            w_3d(i,j,k)=100.0*real(i)+10.0*real(j)+real(k)"
      print "          enddo"
      print "        enddo"
      print "      enddo"
      print "      call set_writer_status(requested_status)"
      while ((getline line < snippet) > 0) print line
      print "      goto 998"
      print "999   continue"
      print "998   observed_status=j_status(n_lco)"
      print "      observed_calls=writer_calls"
      print "      observed_timer=timer_calls"
      print "      metadata_ok=writer_metadata_ok"
      print "      layout_ok=writer_layout_ok"
      print "      return"
      print "      end"
    }
  ' >"$output"
}

build_o0=$(build_variant o0 fixed_o0)
build_o2=$(build_variant o2 fixed_o2)

run_main_case() {
  local build=$1
  local case_name=$2
  local expected_status=$3
  local expected_driver_calls=$4
  local log="$test_tmp/${case_name}_$(basename "$build").log"
  local status driver_calls

  set +e
  UPSTREAM_DERIVED_CASE="$case_name" "$build/derived_main.exe" >"$log" 2>&1
  status=$?
  set -e
  [[ $status -eq $expected_status ]] || {
    cat "$log" >&2
    fail "main case $case_name returned $status, expected $expected_status"
  }
  if (( expected_status == 0 )); then
    rg -q 'LCO_PRODUCER_SUCCESS' "$log" || fail "main case $case_name lacked success marker"
    ! rg -q 'LCO_PRODUCER_FAILED' "$log" || fail "main case $case_name emitted failure marker"
  else
    rg -q 'LCO_PRODUCER_FAILED' "$log" || fail "main case $case_name lacked failure marker"
    ! rg -q 'LCO_PRODUCER_SUCCESS' "$log" || fail "main case $case_name emitted success marker"
  fi
  driver_calls=$(rg -c '^LCO_STUB_ENTERED$' "$log" || true)
  [[ ${driver_calls:-0} == "$expected_driver_calls" ]] || {
    cat "$log" >&2
    fail "main case $case_name entered stub $driver_calls times, expected $expected_driver_calls"
  }
  printf 'UPSTREAM_DERIVED_MAIN_CASE_PASS %s %s\n' "$case_name" "$(basename "$build")"
}

run_writer_harness() {
  local build=$1
  local log="$test_tmp/writer_$(basename "$build").log"
  if ! "$build/lco_writer_status.exe" >"$log" 2>&1; then
    cat "$log" >&2
    fail "writer harness failed for $(basename "$build")"
  fi
  rg -q '^UPSTREAM_DERIVED_WRITER_TEST_PASS$' "$log" || {
    cat "$log" >&2
    fail 'writer harness did not report success'
  }
}

for build in "$build_o0" "$build_o2"; do
  run_main_case "$build" time_failure 1 0
  run_main_case "$build" grid_failure 1 0
  run_main_case "$build" dim_failure 1 0
  run_main_case "$build" missing_failure 1 0
  run_main_case "$build" invalid_x 1 0
  run_main_case "$build" invalid_y 1 0
  run_main_case "$build" invalid_z 1 0
  run_main_case "$build" untouched 1 1
  run_main_case "$build" other_success 1 1
  run_main_case "$build" lco_failure 1 1
  run_main_case "$build" lco_only 0 1
  run_main_case "$build" full_success 0 1
  run_writer_harness "$build"
done

sha256sum -c --status "$test_tmp/inputs.before.sha256"
sha256sum "${inputs[@]}" >"$test_tmp/inputs.after.sha256"
cmp -s "$test_tmp/inputs.before.sha256" "$test_tmp/inputs.after.sha256" || \
  fail 'source/compiler/runner/include hashes changed during test'

printf '%s\n' 'UPSTREAM_DERIVED_STATUS_TEST_PASS'
