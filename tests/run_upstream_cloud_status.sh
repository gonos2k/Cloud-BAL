#!/usr/bin/env bash
# Bounded status and LC3 writer test for the upstream cloud producer.
# Real main/helper source is mechanically extracted; no cloud science producer
# or operational output path is linked.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(cd "$repo_root/.." && pwd)
main_source="$repo_root/src/upstream/laps_cloud.f"
sub_source="$repo_root/src/upstream/laps_cloud_sub.f"
stub_source="$repo_root/tests/test_upstream_cloud_status.f"
include_root="$workspace_root/klaps-v5.0_/src/include"

[[ -f "$main_source" && -f "$sub_source" && -f "$stub_source" && \
   -f "$include_root/cloud.inc" && -f "$include_root/laps_cloud.inc" && \
   -f "$include_root/trigd.inc" ]] || {
  printf 'upstream cloud source, test source, or include is missing\n' >&2
  exit 2
}

. "$repo_root/tests/intel_toolchain.sh"

scratch_root="$repo_root/scratch"
mkdir -p "$scratch_root"
test_tmp=$(mktemp -d "$scratch_root/upstream_cloud_status.XXXXXX")
if [[ ${CLOUD_BAL_KEEP_TEST_OUTPUT:-0} == 1 ]]; then
  trap 'printf "upstream cloud status artifacts retained: %s\n" "$test_tmp"' EXIT
else
  trap 'rm -rf -- "$test_tmp"' EXIT
fi

inputs=(
  "$main_source" "$sub_source" "$stub_source" "$CLOUD_BAL_FC"
  "$include_root/cloud.inc" "$include_root/laps_cloud.inc" "$include_root/trigd.inc"
  "$repo_root/tests/intel_toolchain.sh" "${BASH_SOURCE[0]}"
)
sha256sum "${inputs[@]}" >"$test_tmp/inputs.before.sha256"

fail() {
  printf 'upstream cloud status test: %s\n' "$*" >&2
  exit 1
}

lc3_call_line=$(rg -n -m1 'call[[:space:]]+put_clouds_3d' "$sub_source" | cut -d: -f1 || true)
lc3_status_line=$(rg -n -m1 'j_status[[:space:]]*\([[:space:]]*n_lc3[[:space:]]*\)[[:space:]]*=[[:space:]]*ss_normal' \
  "$sub_source" | cut -d: -f1 || true)
[[ -n "$lc3_call_line" && -n "$lc3_status_line" &&
   $lc3_status_line -gt $lc3_call_line ]] || fail 'LC3 status anchors missing or out of order'
sed -n "${lc3_call_line},${lc3_status_line}p" "$sub_source" |
  rg -q 'istatus[[:space:]]*\.ne\.[[:space:]]*1' ||
  fail 'LC3 status is not conditional on put_clouds_3d success'

compile() {
  local log=$1
  shift
  if ! "$CLOUD_BAL_FC" "$@" >"$log" 2>&1; then
    cat "$log" >&2
    exit 1
  fi
}

awk '/^[[:space:]]*[Ss][Uu][Bb][Rr][Oo][Uu][Tt][Ii][Nn][Ee][[:space:]]+/ { exit } { print }' \
  "$main_source" >"$test_tmp/laps_cloud_main.f"
[[ -s "$test_tmp/laps_cloud_main.f" ]] || fail 'cloud main extraction failed'
awk '/^[[:space:]]*[Pp][Rr][Oo][Gg][Rr][Aa][Mm][[:space:]]+test_upstream_cloud_writer[[:space:]]*$/ { exit } { print }' \
  "$stub_source" >"$test_tmp/stubs.f"
[[ -s "$test_tmp/stubs.f" ]] || fail 'cloud stub extraction failed'

fixed_o0=("${CLOUD_BAL_FIXED_72_FLAGS[@]}")
fixed_o2=("${CLOUD_BAL_FIXED_72_FLAGS[@]}" -O2)

make_writer_wrapper() {
  local output=$1
  awk '
    BEGIN {
      print "      subroutine cloud_writer_probe(nk,ni,nj,requested_status,"
      print "     1     observed_status,observed_calls,metadata_ok)"
      print "      implicit none"
      print "      integer nk,ni,nj,requested_status,observed_status"
      print "      integer observed_calls,metadata_ok,istatus"
      print "      integer i,j,k"
      print "      character*31 ext"
      print "      real clouds_3d(2,3,43),cld_hts(43),cld_pres_1d(43)"
      print "      integer cloud_writer_status,cloud_writer_calls,cloud_writer_ok"
      print "      common /cloud_writer_control/ cloud_writer_status,"
      print "     1     cloud_writer_calls,cloud_writer_ok"
      print "      do k=1,43"
      print "        cld_hts(k)=1000.0*real(k)"
      print "        cld_pres_1d(k)=900.0-real(k)"
      print "        do j=1,3"
      print "          do i=1,2"
      print "            clouds_3d(i,j,k)=100.0*real(i)+10.0*real(j)+real(k)"
      print "          enddo"
      print "        enddo"
      print "      enddo"
      print "      call set_cloud_writer_status(requested_status)"
      print "      ext=\"lc3\""
      print "      call put_clouds_3d(123456789,ext,clouds_3d,"
      print "     1     cld_hts,cld_pres_1d,ni,nj,nk,istatus)"
      print "      observed_status=istatus"
      print "      observed_calls=cloud_writer_calls"
      print "      metadata_ok=cloud_writer_ok"
      print "      return"
      print "      end"
    }
  ' >"$output"
}

build_variant() {
  local tag=$1
  local -n flags=$2
  local build="$test_tmp/$tag"
  mkdir -p "$build"
  compile "$build/main.log" "${flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" -c "$test_tmp/laps_cloud_main.f" \
    -o "$build/laps_cloud_main.o"
  compile "$build/stubs.log" "${flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" -c "$test_tmp/stubs.f" \
    -o "$build/stubs.o"
  compile "$build/main-link.log" "${flags[@]}" \
    "$build/laps_cloud_main.o" "$build/stubs.o" -o "$build/cloud_main.exe"

  awk '
    BEGIN { in_helper = 0 }
    /^[[:space:]]*[Ss][Uu][Bb][Rr][Oo][Uu][Tt][Ii][Nn][Ee][[:space:]]+put_clouds_3d[[:space:]]*\(/ { in_helper = 1 }
    in_helper { print }
    in_helper && /^[[:space:]]*[Ee][Nn][Dd][[:space:]]*$/ { exit }
  ' "$sub_source" >"$build/put_clouds_3d.f"
  [[ -s "$build/put_clouds_3d.f" ]] || fail 'put_clouds_3d extraction failed'
  rg -q 'WRITE_LAPS_DATA' "$build/put_clouds_3d.f" || fail 'helper lacks writer call'
  compile "$build/put_clouds_3d.log" "${flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" -c "$build/put_clouds_3d.f" \
    -o "$build/put_clouds_3d.o"
  make_writer_wrapper "$build/cloud_writer_probe.f"
  compile "$build/helper.log" "${flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" -c "$build/cloud_writer_probe.f" \
    -o "$build/cloud_writer_probe.o"
  compile "$build/harness.log" "${flags[@]}" -module "$build" \
    -I "$build" -I "$include_root" -c "$stub_source" -o "$build/harness.o"
  compile "$build/harness-link.log" "${flags[@]}" \
    "$build/put_clouds_3d.o" "$build/cloud_writer_probe.o" \
    "$build/harness.o" \
    -o "$build/cloud_writer_status.exe"
  printf '%s\n' "$build"
}

build_o0=$(build_variant o0 fixed_o0)
build_o2=$(build_variant o2 fixed_o2)

run_main_case() {
  local build=$1 case_name=$2 expected_status=$3 expected_calls=$4
  local log="$test_tmp/${case_name}_$(basename "$build").log" status calls
  set +e
  UPSTREAM_CLOUD_CASE="$case_name" "$build/cloud_main.exe" >"$log" 2>&1
  status=$?
  set -e
  [[ $status -eq $expected_status ]] || { cat "$log" >&2; fail "main case $case_name status $status expected $expected_status"; }
  if (( expected_status == 0 )); then
    rg -q 'CLOUD_PRODUCER_SUCCESS' "$log" || fail "missing success marker: $case_name"
    ! rg -q 'CLOUD_PRODUCER_FAILED' "$log" || fail "unexpected failure marker: $case_name"
  else
    rg -q 'CLOUD_PRODUCER_FAILED' "$log" || fail "missing failure marker: $case_name"
    ! rg -q 'CLOUD_PRODUCER_SUCCESS' "$log" || fail "unexpected success marker: $case_name"
  fi
  calls=$(rg -c '^CLOUD_STUB_ENTERED$' "$log" || true)
  [[ ${calls:-0} == "$expected_calls" ]] || fail "stub entry count for $case_name: $calls"
  printf 'UPSTREAM_CLOUD_MAIN_CASE_PASS %s %s\n' "$case_name" "$(basename "$build")"
}

run_writer_harness() {
  local build=$1
  local log="$test_tmp/writer_$(basename "$build").log"
  "$build/cloud_writer_status.exe" >"$log" 2>&1 || { cat "$log" >&2; fail 'cloud writer harness failed'; }
  rg -q '^UPSTREAM_CLOUD_WRITER_TEST_PASS$' "$log" || { cat "$log" >&2; fail 'writer pass marker missing'; }
}

for build in "$build_o0" "$build_o2"; do
  run_main_case "$build" time_failure 1 0
  run_main_case "$build" grid_failure 1 0
  run_main_case "$build" dim_failure 1 0
  run_main_case "$build" pirep_failure 1 0
  run_main_case "$build" maxstns_failure 1 0
  run_main_case "$build" invalid_x 1 0
  run_main_case "$build" invalid_y 1 0
  run_main_case "$build" invalid_z 1 0
  run_main_case "$build" negative_pirep 1 0
  run_main_case "$build" zero_pirep 0 1
  run_main_case "$build" zero_maxstns 1 0
  run_main_case "$build" sum_overflow 1 0
  run_main_case "$build" untouched 1 1
  run_main_case "$build" only_lc3 1 1
  run_main_case "$build" only_lcb 1 1
  run_main_case "$build" only_lcv 1 1
  run_main_case "$build" optional_only 1 1
  run_main_case "$build" missing_lc3 1 1
  run_main_case "$build" missing_lcb 1 1
  run_main_case "$build" missing_lcv 1 1
  run_main_case "$build" required_triple 0 1
  run_main_case "$build" full_success 0 1
  run_writer_harness "$build"
done

sha256sum -c --status "$test_tmp/inputs.before.sha256"
sha256sum "${inputs[@]}" >"$test_tmp/inputs.after.sha256"
cmp -s "$test_tmp/inputs.before.sha256" "$test_tmp/inputs.after.sha256" || fail 'test inputs changed'
printf '%s\n' 'UPSTREAM_CLOUD_STATUS_TEST_PASS'
