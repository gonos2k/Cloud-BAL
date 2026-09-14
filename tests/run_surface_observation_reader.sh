#!/usr/bin/env bash
set -euo pipefail

if (( $# > 1 )) || [[ ${1:-} != '' && ${1:-} != --with-real-inputs ]]; then
  printf 'usage: %s [--with-real-inputs]\n' "$0" >&2
  exit 2
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(cd "$repo_root/.." && pwd)
source_file="$repo_root/src/upstream/read_surface_obs.f"
test_source="$repo_root/tests/test_surface_observation_reader.f90"
include_root="$workspace_root/klaps-v5.0_/src/include"

[[ -f "$source_file" && -f "$test_source" && -f "$include_root/lso_formats.inc" ]] || {
  printf 'surface reader source, harness, or lso include is missing\n' >&2
  exit 2
}

. "$repo_root/tests/intel_toolchain.sh"

mkdir -p "$repo_root/scratch"
test_tmp=$(mktemp -d "$repo_root/scratch/surface_observation_reader.XXXXXX")
if [[ ${CLOUD_BAL_KEEP_TEST_OUTPUT:-0} == 1 ]]; then
  trap 'printf "surface observation reader artifacts retained: %s\n" "$test_tmp"' EXIT
else
  trap 'rm -rf -- "$test_tmp"' EXIT
fi

sha256sum "$source_file" "$test_source" "$include_root/lso_formats.inc" \
  "$CLOUD_BAL_FC" "$repo_root/tests/intel_toolchain.sh" "${BASH_SOURCE[0]}" \
  >"$test_tmp/inputs.before.sha256"

awk '
  BEGIN { found = 0 }
  tolower($0) ~ /^[[:space:]]*subroutine[[:space:]]+read_sfc_metadata[[:space:]]*\(/ { exit }
  tolower($0) ~ /^[[:space:]]*subroutine[[:space:]]+read_surface_data[[:space:]]*\(/ { found = 1 }
  { print }
  END { if (!found) exit 1 }
' "$source_file" >"$test_tmp/read_surface_data.f"

compile_one() {
  local fixed_flags_name=$1
  local free_flags_name=$2
  local build=$3
  local log=$4
  local -n fixed_flags=$fixed_flags_name
  local -n free_flags=$free_flags_name
  mkdir -p "$build"
  if ! "$CLOUD_BAL_FC" "${fixed_flags[@]}" \
      -I "$include_root" -module "$build" -c \
      "$test_tmp/read_surface_data.f" -o "$build/read_surface_data.o" >"$log" 2>&1; then
    cat "$log" >&2
    exit 1
  fi
  if ! "$CLOUD_BAL_FC" "${free_flags[@]}" \
      -I "$include_root" -module "$build" -c \
      "$test_source" -o "$build/test_surface_observation_reader.o" >>"$log" 2>&1; then
    cat "$log" >&2
    exit 1
  fi
  if ! "$CLOUD_BAL_FC" "${free_flags[@]}" \
      -I "$include_root" -module "$build" \
      "$build/read_surface_data.o" "$build/test_surface_observation_reader.o" \
      -o "$build/test_surface_observation_reader" >>"$log" 2>&1; then
    cat "$log" >&2
    exit 1
  fi
}

run_one() {
  local label=$1
  local fixed_flags_name=$2
  local free_flags_name=$3
  local build="$test_tmp/$label"
  compile_one "$fixed_flags_name" "$free_flags_name" "$build" \
    "$test_tmp/$label.compile.log"
  local runtime="$build/runtime"
  mkdir -p "$runtime/lso" "$runtime/tmp"
  SURFACE_TEST_LSO_DIR="$runtime/lso/" \
  SURFACE_TEST_TMP_DIR="$runtime/tmp/" \
  "$build/test_surface_observation_reader" >"$build/test.log" 2>&1 || {
    cat "$build/test.log" >&2
    exit 1
  }
  cat "$build/test.log"
}

fixed_o0=("${CLOUD_BAL_FIXED_72_FLAGS[@]}")
free_o0=("${CLOUD_BAL_FREE_FLAGS[@]}")
fixed_o2=("${CLOUD_BAL_FIXED_72_FLAGS[@]/-O0/-O2}")
free_o2=("${CLOUD_BAL_FREE_FLAGS[@]/-O0/-O2}")

run_one o0 fixed_o0 free_o0
run_one o2 fixed_o2 free_o2

if [[ ${1:-} == --with-real-inputs ]]; then
  real_root="$test_tmp/real_inputs"
  mkdir -p "$real_root/lso" "$real_root/tmp"
  declare -A expected_hash=(
    [262281200]=b049868013bfcbcca65aee136dc6558264691482a459ec94aa2c9d60b1732a12
    [262281300]=b70ee7a758bf2d27b938ff346e3fc4c40c4c79be22f746d0f0cb0cf2ce03b9fd
    [262281400]=5897d4ec8d4979a71369f68de95c68f7229ae76fa6104619d893b204b9ad6ec9
    [262281500]=ffb52a5ed4fa24901fea419a44b5ed0cdfe22f1a192ff32b103e5a6dcfd6ed81
  )
  declare -A expected_count=(
    [262281200]=816 [262281300]=816 [262281400]=803 [262281500]=814
  )
  before_real="$test_tmp/real_inputs.before.sha256"
  : >"$before_real"
  for stamp in 262281200 262281300 262281400 262281500; do
    source="$workspace_root/ANAL/NE57/DAOU/00/lapsprd/lso/$stamp.lso"
    [[ -f "$source" && ! -L "$source" ]] || {
      printf 'pinned LSO input is unavailable: %s\n' "$source" >&2
      exit 2
    }
    actual=$(sha256sum "$source" | cut -d' ' -f1)
    [[ $actual == "${expected_hash[$stamp]}" ]] || {
      printf 'pinned LSO hash mismatch: %s\n' "$source" >&2
      exit 2
    }
    printf '%s  %s\n' "$actual" "$source" >>"$before_real"
    cp -- "$source" "$real_root/lso/$stamp.lso"
    printf '%s  %s\n' "$actual" "$real_root/lso/$stamp.lso" | sha256sum -c --quiet
    chmod 400 "$real_root/lso/$stamp.lso"
  done
  for optimization in o0 o2; do
    for stamp in 262281200 262281300 262281400 262281500; do
      log="$real_root/${optimization}-${stamp}.log"
      SURFACE_TEST_LSO_DIR="$real_root/lso/" \
      SURFACE_TEST_TMP_DIR="$real_root/tmp/" \
      SURFACE_TEST_ACTUAL=1 \
      SURFACE_TEST_STAMP="$stamp" \
      "$test_tmp/$optimization/test_surface_observation_reader" \
        >"$log" 2>&1 || {
          cat "$log" >&2
          exit 1
        }
      rg -q "SURFACE_ACTUAL_PASS $stamp ${expected_count[$stamp]}" "$log" || {
        cat "$log" >&2
        exit 1
      }
    done
  done
  after_real="$test_tmp/real_inputs.after.sha256"
  : >"$after_real"
  for stamp in 262281200 262281300 262281400 262281500; do
    sha256sum "$workspace_root/ANAL/NE57/DAOU/00/lapsprd/lso/$stamp.lso" >>"$after_real"
  done
  diff -u "$before_real" "$after_real"
fi

sha256sum "$source_file" "$test_source" "$include_root/lso_formats.inc" \
  "$CLOUD_BAL_FC" "$repo_root/tests/intel_toolchain.sh" "${BASH_SOURCE[0]}" \
  >"$test_tmp/inputs.after.sha256"
diff -u "$test_tmp/inputs.before.sha256" "$test_tmp/inputs.after.sha256"
printf 'surface observation reader tests passed (O0/O2%s)\n' \
  "${1:+ plus real inputs}" 
