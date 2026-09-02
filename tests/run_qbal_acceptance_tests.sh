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

if grep -Eiq 'airdrop|advance_grids|delo\.eq\.0|readprg|readpig' \
    "$repo_root/src/balance/qbalpe.f"; then
  printf '%s\n' 'retired experimental QBAL path is still present' >&2
  exit 1
fi

awk '
  /^       call leib_sub\(/ {projection_count++}
  /^       call qbal_candidate_acceptance\(/ {common_gate=1}
  END {if (projection_count<2 || !common_gate) exit 1}
' "$repo_root/src/balance/qbalpe.f"

for assignment in 't=tworkorig' 'u=uworkorig' 'v=vworkorig' \
                  'om=omworkorig' 'to=torig' 'uo=uorig' \
                  'vo=vorig' 'omo=omorig'; do
  grep -Fq "$assignment" "$repo_root/src/balance/qbalpe.f"
done

awk '
  /call get_modelfg_3d\(i4time_sys,'\''OM '\'',nx,ny,nz,omb,istat_bg\(6\)\)/ {omega=1}
  omega && /do i=1,6/ {required=1; exit}
  END {if (!omega || !required) exit 1}
' "$repo_root/src/balance/qbalpe.f"

awk '
  /^      call get_laps_2d\(i4time_sys,sfcext,'\''PS '\''/ {analysis_surface=NR}
  /^      call qbal_mark_valid_omega\(omb,omb_valid/ {omega_refresh=NR}
  /^      if\(.not.background_omega_complete\(omb_valid,ps,p/ {omega_gate=NR}
  /^      call build_compact_influence_3d\(omo_valid/ {localization=NR}
  END {
    if (!analysis_surface || !omega_refresh || !omega_gate || !localization ||
        omega_refresh<=analysis_surface || omega_gate<=omega_refresh ||
        localization<=omega_gate) exit 1
  }
' "$repo_root/src/balance/qbalpe.f"

printf '%s\n' 'QBAL single-path, background-omega, common-gate and rollback checks passed'
