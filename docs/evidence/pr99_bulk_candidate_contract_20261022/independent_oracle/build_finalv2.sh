#!/usr/bin/env bash
set -euo pipefail
profile=$1
work=/var/tmp/pr99_bulk_oracle_finalv2_20261022/$profile
src=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr99_native_contract_20261022/Cloud-BAL/src/common/cloud_bal_joint_transport.f90
harness=/var/tmp/pr99_bulk_oracle_finalv2_20261022/bulk_absence_harness.f90
mkdir -p "$work/mod" "$work/obj" "$work/bin"
cd "$work"
source /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr99_native_contract_20261022/Cloud-BAL/tests/intel_toolchain.sh
if [[ $profile == free ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
{ printf 'profile=%s\n' "$profile"; printf 'compiler=%s\n' "$CLOUD_BAL_FC"; printf 'compiler_sha256='; sha256sum "$CLOUD_BAL_FC" | cut -d' ' -f1; printf 'flags='; printf ' %q' "${flags[@]}"; printf '\n'; printf 'core_sha256='; sha256sum "$src" | cut -d' ' -f1; printf 'harness_sha256='; sha256sum "$harness" | cut -d' ' -f1; } > build_inputs.txt
"$CLOUD_BAL_FC" "${flags[@]}" -module "$work/mod" -I"$work/mod" -c "$src" -o "$work/obj/cloud_bal_joint_transport.o" > compile_core.log 2>&1
"$CLOUD_BAL_FC" "${flags[@]}" -module "$work/mod" -I"$work/mod" "$harness" "$work/obj/cloud_bal_joint_transport.o" -o "$work/bin/bulk_absence_harness" > compile_harness.log 2>&1
"$work/bin/bulk_absence_harness" > harness_output.txt 2> harness_stderr.log
python3 /var/tmp/pr99_bulk_oracle_finalv2_20261022/check_results_v2.py "$work/harness_output.txt" > oracle_check.json
sha256sum "$work/bin/bulk_absence_harness" "$src" > hashes.txt
