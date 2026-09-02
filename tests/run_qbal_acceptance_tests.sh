#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$repo_root/scratch"
test_tmp=$(mktemp -d "$repo_root/scratch/qbal_gate.XXXXXX")
trap 'rm -rf "$test_tmp"' EXIT
. "$repo_root/tests/intel_toolchain.sh"

awk '
  /^      subroutine qbal_increment_maxima\(/ {capture=1}
  capture && /^      subroutine geostrophic_residual_metrics\(/ {exit}
  capture {print}
' "$repo_root/src/balance/qbalpe.f" > "$test_tmp/qbal_acceptance.f"

"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FIXED_72_FLAGS[@]}" \
  "$test_tmp/qbal_acceptance.f" -o "$test_tmp/qbal_acceptance.o"
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  "$repo_root/tests/test_qbal_acceptance.f90" \
  "$test_tmp/qbal_acceptance.o" -o "$test_tmp/test_qbal_acceptance"
"$test_tmp/test_qbal_acceptance"

awk '
  /if\(delo.eq.0.\)go to 700/ {route=1}
  route && /^ 700  continue/ {common=1}
  route && !common && /bal_status=1/ {bad_success=1}
  common && /if\(delo.eq.0.\)then/ {airdrop_branch=1}
  airdrop_branch && /call move_3d\(u,ucont/ {airdrop_copy=1}
  airdrop_branch && !airdrop_exit && /call leib_sub/ {duplicate_solve=1}
  airdrop_branch && /goto 710/ {airdrop_exit=1}
  airdrop_exit && /call leib_sub/ {normal_projection=1}
  normal_projection && /^ 710  continue/ {common_final=1}
  common_final && /call qbal_candidate_acceptance/ {common_gate=1}
  END {
    if (!route || !common || bad_success || duplicate_solve ||
        !airdrop_branch || !airdrop_copy || !airdrop_exit ||
        !normal_projection || !common_final || !common_gate) exit 1
  }
' "$repo_root/src/balance/qbalpe.f"

for assignment in 't=tworkorig' 'u=uworkorig' 'v=vworkorig' \
                  'om=omworkorig' 'to=torig' 'uo=uorig' \
                  'vo=vorig' 'omo=omorig'; do
  grep -Fq "$assignment" "$repo_root/src/balance/qbalpe.f"
done

printf '%s\n' 'QBAL AIRDROP common-gate and rollback checks passed'
