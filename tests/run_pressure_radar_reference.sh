#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
. "$repo_root/tests/intel_toolchain.sh"

if [[ $# -gt 1 ]]; then
  printf 'usage: %s [OUTPUT_DIR]\n' "$0" >&2
  exit 2
fi

# The caller may provide an owned scratch directory so an independent Python
# checker can consume both compiler artifacts after this script returns.  The
# default is a fresh directory under Cloud-BAL/scratch; only the private build
# directory is removed by this script.
if [[ $# -eq 1 ]]; then
  output_dir=$1
  mkdir -p "$output_dir"
else
  output_dir=$(mktemp -d "$repo_root/scratch/radar_reference.XXXXXX")
fi
build_dir=$(mktemp -d "$repo_root/scratch/radar_reference_build.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT

source_file="$repo_root/tests/test_pressure_radar_reference.f90"
state_source="$repo_root/src/common/cloud_bal_state.f90"
physics_source="$repo_root/src/common/cloud_bal_column_physics.f90"

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$build_dir" -I "$build_dir" \
  "$state_source" "$physics_source" "$source_file" \
  -o "$build_dir/test_pressure_radar_reference_o0"

"$build_dir/test_pressure_radar_reference_o0" \
  "$output_dir/radar_reference_input_o0.txt" \
  "$output_dir/radar_reference_output_o0.txt"
python3 "$repo_root/tests/check_pressure_radar_reference.py" \
  "$output_dir/radar_reference_input_o0.txt" \
  "$output_dir/radar_reference_output_o0.txt"

mkdir -p "$build_dir/o2"
"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" \
  -module "$build_dir/o2" -I "$build_dir/o2" \
  "$state_source" "$physics_source" "$source_file" \
  -o "$build_dir/test_pressure_radar_reference_o2"

"$build_dir/test_pressure_radar_reference_o2" \
  "$output_dir/radar_reference_input_o2.txt" \
  "$output_dir/radar_reference_output_o2.txt"
python3 "$repo_root/tests/check_pressure_radar_reference.py" \
  "$output_dir/radar_reference_input_o2.txt" \
  "$output_dir/radar_reference_output_o2.txt"

printf 'RADAR_REFERENCE_OUTPUT_DIR=%s\n' "$(cd "$output_dir" && pwd)"
printf 'RADAR_REFERENCE_INPUT_O0=%s\n' "$output_dir/radar_reference_input_o0.txt"
printf 'RADAR_REFERENCE_OUTPUT_O0=%s\n' "$output_dir/radar_reference_output_o0.txt"
printf 'RADAR_REFERENCE_INPUT_O2=%s\n' "$output_dir/radar_reference_input_o2.txt"
printf 'RADAR_REFERENCE_OUTPUT_O2=%s\n' "$output_dir/radar_reference_output_o2.txt"
