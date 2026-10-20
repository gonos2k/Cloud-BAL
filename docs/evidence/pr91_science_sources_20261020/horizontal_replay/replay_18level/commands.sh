#!/usr/bin/env bash
set -euo pipefail
# Reproduce from a fresh scratch directory supplied as the first argument.
# The source bundle is copied to scratch first; all generated data/JSON stays
# in that scratch copy, leaving the archived evidence read-only.
source_bundle=$(cd "$(dirname "$0")/.." && pwd)
scratch=${1:?usage: commands.sh /fresh/scratch/directory}
mkdir -p "$scratch"
scratch_bundle="$scratch/replay_bundle"
if [[ -e "$scratch_bundle" ]]; then
  printf 'scratch replay bundle already exists: %s\n' "$scratch_bundle" >&2
  exit 2
fi
cp -a "$source_bundle" "$scratch_bundle"
bundle="$scratch_bundle/replay_18level"
build="$scratch/build"
mkdir -p "$build" "$build/support_objects" "$build/operator_source"
cp "$bundle/qc_levels.txt.gz" "$bundle/qc_headers.txt" "$bundle/pressures.txt" "$bundle/targets_288.txt" "$bundle/target_grid_234x282.txt.gz" "$bundle/grid_rows_288.f90" "$bundle/grid_rows_288_wrong_radius.f90" "$bundle/enumerate_target_support.f90" "$build/"
cp "$bundle/support_objects/"*.o "$bundle/support_objects/"*.mod "$build/support_objects/"
cp "$bundle/operator_source/"*.F "$build/operator_source/"
cd "$build"
gzip -dc qc_levels.txt.gz > qc_levels.txt
gzip -dc target_grid_234x282.txt.gz > target_grid_234x282.txt
source "$bundle/toolchain/intel_toolchain.sh"
mkdir -p mod
"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" -free -convert big_endian -I support_objects -module mod -c operator_source/module_map_utils.F -o module_map_utils.o
"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" -free -convert big_endian -I mod -I support_objects -module mod -c operator_source/llxy_module.F -o llxy_module.o
"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" -free -convert big_endian -I mod -I support_objects -module mod -c operator_source/interp_module.F -o interp_module.o
"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" -free -convert big_endian -I mod -I support_objects grid_rows_288.f90 llxy_module.o module_map_utils.o interp_module.o support_objects/module_debug.o support_objects/parallel_module.o support_objects/cio.o support_objects/bitarray_module.o support_objects/queue_module.o -o grid_rows_288
"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" -free -convert big_endian -I mod -I support_objects grid_rows_288_wrong_radius.f90 llxy_module.o module_map_utils.o interp_module.o support_objects/module_debug.o support_objects/parallel_module.o support_objects/cio.o support_objects/bitarray_module.o support_objects/queue_module.o -o grid_rows_288_wrong_radius
./grid_rows_288 > grid_rows_288.out
"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" -free -convert big_endian -I mod -I support_objects enumerate_target_support.f90 llxy_module.o module_map_utils.o support_objects/module_debug.o support_objects/parallel_module.o support_objects/cio.o support_objects/bitarray_module.o support_objects/queue_module.o -o enumerate_target_support
./grid_rows_288_wrong_radius > grid_rows_288_wrong_radius.out
./enumerate_target_support > scan.log
cp grid_rows_288.out grid_rows_288_wrong_radius.out inverse_support_rows.txt scan.log "$bundle/"
python "$bundle/rebuild_footprint.py"
printf 'Generated JSON only under scratch copy: %s\n' "$scratch_bundle"
