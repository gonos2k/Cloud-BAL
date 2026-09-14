#!/usr/bin/env bash
# Focused trapped-FPE regression for the real upstream lightning reader block.
# The block is extracted from get_cloud_deriv.f; no cloud-physics routine is linked.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
overlay="$repo_root/src/upstream/get_cloud_deriv.f"

[[ -f "$overlay" ]] || {
  printf 'upstream get_cloud_deriv overlay is missing\n' >&2
  exit 2
}

. "$repo_root/tests/intel_toolchain.sh"

scratch_root="$repo_root/scratch"
mkdir -p "$scratch_root"
test_tmp=$(mktemp -d "$scratch_root/get_cloud_deriv_lightning.XXXXXX")
if [[ ${CLOUD_BAL_KEEP_TEST_OUTPUT:-0} == 1 ]]; then
  trap 'printf "get_cloud_deriv lightning artifacts retained: %s\n" "$test_tmp"' EXIT
else
  trap 'rm -rf -- "$test_tmp"' EXIT
fi

# The compiler and the floating-point contract are pinned by intel_toolchain.sh.
fixed_o0=("${CLOUD_BAL_FIXED_72_FLAGS[@]}")
fixed_o2=("${CLOUD_BAL_FIXED_72_FLAGS[@]}" -O2)

sha256sum "$overlay" "$CLOUD_BAL_FC" \
  "$repo_root/tests/intel_toolchain.sh" "${BASH_SOURCE[0]}" \
  >"$test_tmp/inputs.sha256"

fail() {
  printf 'get_cloud_deriv lightning test: %s\n' "$*" >&2
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

# Keep the exact reader block from the overlay.  The surrounding production
# routine is intentionally not linked: this test is about the optional input
# status path and its REAL-to-INTEGER sentinel boundary only.
awk '
  /^!cde Construct file name for LGT file/ {capture=1}
  capture {print}
  capture && /^!cde - End/ {exit}
' "$overlay" >"$test_tmp/lightning_block.f"
[[ -s "$test_tmp/lightning_block.f" ]] || fail 'lightning reader block extraction failed'
rg -q 'iostat=lgt_read_status' "$test_tmp/lightning_block.f" || \
  fail 'extracted block lacks I/O status handling'
rg -q 'n_lgt = lgt_missing' "$test_tmp/lightning_block.f" || \
  fail 'extracted block lacks integer missing fallback'

make_harness() {
  local output=$1
  awk -v block="$test_tmp/lightning_block.f" '
    BEGIN {
      print "      subroutine read_lgt_counts(counts)"
      print "      integer*4 counts(2,2)"
      print "      integer*4 ni,nj,i4time"
      print "      integer*4 n_lgt(2,2)"
      print "      integer*4 lgt_read_status"
      print "      integer*4 lgt_source_missing"
      print "      integer*4 lgt_missing"
      print "      parameter (lgt_missing = -1)"
      print "      logical lgt_unit_open"
      print "      character*150 filename,directory"
      print "      character*31 ext"
      print "      character*13 filename13"
      print "      character*3 lgt_ext"
      print "      data lgt_ext /\047lgt\047/"
      print "      ni=2"
      print "      nj=2"
      print "      i4time=123456789"
      while ((getline line < block) > 0) print line
      print "      counts=n_lgt"
      print "      return"
      print "      end"
      print ""
      print "      subroutine get_i2_missing_data(value,istatus)"
      print "      integer value,istatus"
      print "      value=-99"
      print "      istatus=1"
      print "      end"
      print ""
      print "      subroutine get_directory(ext,directory,len_dir)"
      print "      character*(*) ext"
      print "      character*150 directory"
      print "      integer*4 len_dir"
      print "      directory=\047./\047"
      print "      len_dir=2"
      print "      return"
      print "      end"
      print ""
      print "      character*13 function filename13(i4time,ext)"
      print "      integer*4 i4time"
      print "      character*(*) ext"
      print "      filename13=\047lgt_case0.lgt\047"
      print "      return"
      print "      end"
      print ""
      print "      program test_get_cloud_deriv_lgt"
      print "      integer*4 counts(2,2)"
      print "      call read_lgt_counts(counts)"
      print "      write(6,100) counts(1,1),counts(1,2),"
      print "     1                 counts(2,1),counts(2,2)"
      print "100   format(\047LGT_COUNTS\047,4(1x,i4))"
      print "      end"
    }
  ' >"$output"
}

make_harness "$test_tmp/lightning_harness.f"

build_variant() {
  local tag=$1
  local -n flags=$2
  local build="$test_tmp/$tag"
  mkdir -p "$build"
  compile "$build/harness.log" "${flags[@]}" -module "$build" \
    -I "$build" -c "$test_tmp/lightning_harness.f" \
    -o "$build/lightning_harness.o"
  compile "$build/link.log" "${flags[@]}" \
    "$build/lightning_harness.o" -o "$build/lightning_harness.exe"
  printf '%s\n' "$build"
}

build_o0=$(build_variant o0 fixed_o0)
build_o2=$(build_variant o2 fixed_o2)
case_dir="$test_tmp/input"
mkdir -p "$case_dir"

write_record() {
  local value=$1
  printf '%18s%8s\n' '' "$value" >>"$case_dir/lgt_case0.lgt"
}

prepare_case() {
  local case_name=$1
  rm -f -- "$case_dir/lgt_case0.lgt"
  case "$case_name" in
    absent)
      ;;
    truncated)
      write_record 1
      write_record 2
      write_record 3
      ;;
    validzero)
      write_record 0
      write_record 0
      write_record 0
      write_record 0
      ;;
    positive)
      write_record 1
      write_record 2
      write_record 3
      write_record 4
      ;;
    native_missing_mixed)
      write_record -99
      write_record 0
      write_record 5
      write_record 1
      ;;
    invalid_negative)
      write_record 1
      write_record -98
      write_record 0
      write_record 5
      ;;
    malformed)
      write_record 1
      printf '%18s%8s\n' '' bad >>"$case_dir/lgt_case0.lgt"
      ;;
    *)
      fail "unknown case $case_name"
      ;;
  esac
}

run_case() {
  local build=$1
  local case_name=$2
  local expected=$3
  local log="$test_tmp/${case_name}_$(basename "$build").log"
  prepare_case "$case_name"
  if ! (cd "$case_dir" && "$build/lightning_harness.exe") >"$log" 2>&1; then
    cat "$log" >&2
    fail "$case_name failed under $(basename "$build")"
  fi
  local actual
  actual=$(awk '$1 == "LGT_COUNTS" {print $2,$3,$4,$5}' "$log")
  [[ "$actual" == "$expected" ]] || {
    cat "$log" >&2
    fail "$case_name returned counts '$actual', expected '$expected'"
  }
  case "$case_name" in
    absent|truncated|malformed|invalid_negative)
      rg -q 'No lightning' "$log" || fail "$case_name lacked missing-lightning status" ;;
    validzero|positive|native_missing_mixed)
      ! rg -q 'No lightning' "$log" || fail "$case_name was treated as missing" ;;
  esac
  printf 'GET_CLOUD_DERIV_LIGHTNING_CASE_PASS %s %s\n' \
    "$case_name" "$(basename "$build")"
}

for build in "$build_o0" "$build_o2"; do
  run_case "$build" absent '-1 -1 -1 -1'
  run_case "$build" truncated '-1 -1 -1 -1'
  run_case "$build" validzero '0 0 0 0'
  run_case "$build" positive '1 2 3 4'
  run_case "$build" malformed '-1 -1 -1 -1'
  run_case "$build" invalid_negative '-1 -1 -1 -1'
  run_case "$build" native_missing_mixed '-1 0 5 1'
done

sha256sum -c --status "$test_tmp/inputs.sha256"
printf '%s\n' 'GET_CLOUD_DERIV_LIGHTNING_STATUS_TEST_PASS'
