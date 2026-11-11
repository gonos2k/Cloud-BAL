#!/usr/bin/env bash
set +e
cd /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/ice_partition_policy_20261111/Cloud-BAL || exit 2
export TMPDIR="$(cat ../validation/local_tmp_path)"
export CLOUD_BAL_TEST_SCRATCH_ROOT="$PWD/../validation/scratch"
bash tests/run_unit_tests.sh > ../validation/full_suite.log 2>&1
result=$?
printf '%s\n' "$result" > ../validation/full_suite.exit
exit "$result"
