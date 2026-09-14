#!/usr/bin/env bash
# O0/O2 status tests for the previous-hour surface QC boundary.
# The QC executable links the real qc_data.f; its reader and directory lookup
# are controlled stubs, so no operational producer or LSO file is accessed.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
qc_source="$repo_root/src/sfc/qc_data.f"
reader_source="$repo_root/src/upstream/read_surface.f"
test_source="$repo_root/tests/test_previous_surface_qc.f90"
caller_source="$repo_root/src/sfc/laps_sfc.f"

[[ -f "$qc_source" && -f "$reader_source" && -f "$test_source" && \
   -f "$caller_source" ]] || {
  printf 'previous surface QC, reader, caller, or test source is missing\n' >&2
  exit 2
}

. "$repo_root/tests/intel_toolchain.sh"

scratch_root="$repo_root/scratch"
mkdir -p "$scratch_root"
test_tmp=$(mktemp -d "$scratch_root/previous_surface_qc.XXXXXX")
if [[ ${CLOUD_BAL_KEEP_TEST_OUTPUT:-0} == 1 ]]; then
  trap 'printf "previous surface QC artifacts retained: %s\n" "$test_tmp"' EXIT
else
  trap 'rm -rf -- "$test_tmp"' EXIT
fi

fail() {
  printf 'previous surface QC test: %s\n' "$*" >&2
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

# These checks keep the harness tied to the status contract being tested,
# including cleanup and the caller's fatal path for an unexpected QC status.
rg -q 'istatus[[:space:]]*=[[:space:]]*-2' "$qc_source" || \
  fail 'qcdata no longer initializes failure status'
rg -q 'istatus[[:space:]]*=[[:space:]]*0' "$qc_source" || \
  fail 'qcdata no longer exposes no-data status'
rg -q 'close\(60,iostat=io_status\)' "$qc_source" || \
  fail 'qcdata close status check is missing'
rg -q 'if\(io_status[[:space:]]*\.ne\.[[:space:]]*0\)[[:space:]]*istatus[[:space:]]*=[[:space:]]*-2' \
  "$qc_source" || fail 'qcdata close failure does not map to -2'
# Source-only caller guard: the full surface caller turns unexpected QC
# failures into a fatal stop; its data pipeline is intentionally not run here.
caller_anchor=$(rg -n -m1 'jstatus\(2\)[[:space:]]*=[[:space:]]*-2' "$caller_source" | cut -d: -f1 || true)
[[ -n "$caller_anchor" ]] || fail 'caller lacks fatal QC status assignment'
sed -n "$caller_anchor,$((caller_anchor + 8))p" "$caller_source" | \
  rg -q 'stop[[:space:]]+1' || fail 'caller does not stop on unexpected QC status'

hash_inputs=(
  "$qc_source"
  "$reader_source"
  "$test_source"
  "$caller_source"
  "$CLOUD_BAL_FC"
  "$repo_root/tests/intel_toolchain.sh"
  "${BASH_SOURCE[0]}"
)
sha256sum "${hash_inputs[@]}" >"$test_tmp/inputs.before.sha256"

build_qc() {
  local label=$1
  local fixed_flags_name=$2
  local free_flags_name=$3
  local -n fixed_flags=$fixed_flags_name
  local -n free_flags=$free_flags_name
  local build="$test_tmp/qc-$label"
  mkdir -p "$build/runtime/logs"

  compile "$build/qc.compile.log" "${fixed_flags[@]}" \
    -c "$qc_source" -o "$build/qc_data.o"
  compile "$build/test.compile.log" "${free_flags[@]}" -fpp -DQC_DRIVER \
    -c "$test_source" -o "$build/test.o"
  compile "$build/link.log" "${free_flags[@]}" \
    "$build/qc_data.o" "$build/test.o" -o "$build/test_previous_surface_qc"
  (
    cd "$build/runtime"
    "$build/test_previous_surface_qc" >"$build/runtime.log" 2>&1
  ) || {
    cat "$build/runtime.log" >&2
    exit 1
  }
  rg -q '^QC_TEST_PASS$' "$build/runtime.log" || {
    cat "$build/runtime.log" >&2
    fail "QC harness did not pass ($label)"
  }
  for case_name in reader_missing reader_corrupt reader_unknown current_missing \
                   previous_missing normal_with_background log_open_failure; do
    rg -q "^QC_CASE_PASS $case_name " "$build/runtime.log" || {
      cat "$build/runtime.log" >&2
      fail "missing QC case marker $case_name ($label)"
    }
  done
  cat "$build/runtime.log"
}

fixed_o0=("${CLOUD_BAL_FIXED_72_FLAGS[@]}")
fixed_o2=("${CLOUD_BAL_FIXED_72_FLAGS[@]/-O0/-O2}")
free_o0=("${CLOUD_BAL_FREE_FLAGS[@]}")
free_o2=("${CLOUD_BAL_REPRO_FLAGS[@]}")

build_qc o0 fixed_o0 free_o0
build_qc o2 fixed_o2 free_o2

build_reader() {
    local label=$1
    local fixed_flags_name=$2
    local free_flags_name=$3
    local -n fixed_flags=$fixed_flags_name
    local -n free_flags=$free_flags_name
    local build="$test_tmp/reader-$label"
    mkdir -p "$build"

    awk 'tolower($0) ~ /^[[:space:]]*subroutine[[:space:]]+read_surface_old[[:space:]]*\(/ { found=1 } found { print }' \
      "$reader_source" >"$build/read_surface.f"
    [[ -s "$build/read_surface.f" ]] || fail 'read_surface_old extraction failed'
    compile "$build/reader.compile.log" "${fixed_flags[@]}" \
      -c "$build/read_surface.f" -o "$build/read_surface.o"
    compile "$build/test.compile.log" "${free_flags[@]}" -fpp -DLSO_DRIVER \
      -c "$test_source" -o "$build/test.o"
    compile "$build/link.log" "${free_flags[@]}" \
      "$build/read_surface.o" "$build/test.o" -o "$build/test_previous_lso_reader"
    "$build/test_previous_lso_reader" >"$build/runtime.log" 2>&1 || {
      cat "$build/runtime.log" >&2
      exit 1
    }
    rg -q '^LSO_TEST_PASS$' "$build/runtime.log" || {
      cat "$build/runtime.log" >&2
      fail "LSO harness did not pass ($label)"
    }
    for case_name in data_success data_missing data_corrupt data_unknown short_filename; do
      rg -q "^LSO_CASE_PASS $case_name " "$build/runtime.log" || {
        cat "$build/runtime.log" >&2
        fail "missing LSO case marker $case_name ($label)"
      }
    done
    cat "$build/runtime.log"
}

build_reader o0 fixed_o0 free_o0
build_reader o2 fixed_o2 free_o2

# Execute the actual caller status branch, without the surface data pipeline.
awk '
  BEGIN {
    print "      program qc_caller_test"
    print "      integer istatus,jstatus(3)"
    print "      character*16 argument"
    print "      call get_command_argument(1,argument)"
    print "      read(argument,*) istatus"
  }
  /call qcdata\(/ { seen=1 }
  seen && /if\(istatus \.eq\. 1\) then/ { copying=1 }
  copying { print }
  copying && /endif/ { found=1; exit }
  END {
    if (!found) exit 1
    print " 521  continue"
    print "      print *, \"QC_CALLER_CONTINUED\""
    print "      end"
  }
' "$caller_source" >"$test_tmp/qc_caller.f"
for optimization in o0 o2; do
  flags=("${fixed_o0[@]}")
  [[ $optimization != o2 ]] || flags=("${fixed_o2[@]}")
  compile "$test_tmp/caller-$optimization.compile.log" "${flags[@]}" \
    "$test_tmp/qc_caller.f" -o "$test_tmp/caller-$optimization"
  for status in 1 0 -1 -2 77; do
    log="$test_tmp/caller-$optimization-$status.log"
    result=0
    "$test_tmp/caller-$optimization" "$status" >"$log" 2>&1 || result=$?
    if [[ $status == 1 || $status == 0 ]]; then
      [[ $result == 0 ]] && rg -q QC_CALLER_CONTINUED "$log" || \
        fail "caller rejected status $status ($optimization)"
    else
      [[ $result == 1 ]] && ! rg -q QC_CALLER_CONTINUED "$log" || \
        fail "caller failed to reject status $status ($optimization)"
    fi
  done
  printf 'QC_CALLER_TEST_PASS %s\n' "$optimization"
done

sha256sum "${hash_inputs[@]}" >"$test_tmp/inputs.after.sha256"
diff -u "$test_tmp/inputs.before.sha256" "$test_tmp/inputs.after.sha256"
printf 'previous surface QC and LSO reader tests passed (O0/O2)\n'
