#!/usr/bin/env bash
set -euo pipefail
repo=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr91_host_store_20261020/Cloud-BAL
cd "$repo"
source tests/intel_toolchain.sh
python -m unittest -v tests.test_pr91_fogdes_store_contract
