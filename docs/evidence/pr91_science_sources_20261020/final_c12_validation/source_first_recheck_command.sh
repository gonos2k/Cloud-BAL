#!/usr/bin/env bash
set -euo pipefail
repo=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr91_host_store_20261020/Cloud-BAL
out="$repo/docs/evidence/pr91_science_sources_20261020/final_c12_validation"
runroot=/var/tmp/pr91_c12_source_first_recheck_20261020
mkdir -p "$out" "$runroot/pytest-tmp"
cd "$repo"
source tests/intel_toolchain.sh
export TMPDIR="$runroot/pytest-tmp"
pytest -q tests/test_pr91_source_first_diffusion.py | tee "$out/source_first_test_rerun.log"
