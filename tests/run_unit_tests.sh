#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$repo_root/scratch"
test_tmp=$(mktemp -d "$repo_root/scratch/unit_tests.XXXXXX")
trap 'rm -rf "$test_tmp"' EXIT

gfortran -std=f2008 -Wall -Wextra -fcheck=all \
  -J "$test_tmp" -I "$test_tmp" \
  "$repo_root/src/common/cloud_bal_field_contracts.f90" \
  "$repo_root/src/common/cloud_bal_moisture.f90" \
  "$repo_root/src/common/cloud_bal_cloud_profiles.f90" \
  "$repo_root/src/common/cloud_bal_localization.f90" \
  "$repo_root/src/common/cloud_bal_radar_downdraft.f90" \
  "$repo_root/src/common/cloud_bal_wind_modes.f90" \
  "$repo_root/tests/test_cloud_bal_core.f90" \
  -o "$test_tmp/test_cloud_bal_core"

"$test_tmp/test_cloud_bal_core"

gfortran -c -std=f2008 -Wall -Wextra -fcheck=all \
  -J "$test_tmp" -I "$test_tmp" \
  -o "$test_tmp/module_setup.o" "$repo_root/src/lapsprep/module_setup.f90"
gfortran -c -std=f2008 -Wall -Wextra -fcheck=all \
  -J "$test_tmp" -I "$test_tmp" \
  -o "$test_tmp/lwc2vapor.o" "$repo_root/src/lapsprep/lwc2vapor.f90"
gfortran -c -std=f2008 -Wall -Wextra -fcheck=all \
  -J "$test_tmp" -I "$test_tmp" \
  -o "$test_tmp/ice2vapor.o" "$repo_root/src/lapsprep/ice2vapor.f90"
gfortran -c -std=legacy -ffixed-line-length-none -fcheck=all \
  -J "$test_tmp" -I "$test_tmp" \
  -o "$test_tmp/vv_lgt_ct.o" "$repo_root/src/lib/vv_lgt_ct.f"
gfortran -c -std=legacy -ffixed-line-length-none -fdollar-ok \
  -fallow-argument-mismatch -J "$test_tmp" -I "$test_tmp" \
  -I "$repo_root/src/include" -o "$test_tmp/get_cloud_deriv.o" \
  "$repo_root/src/lib/get_cloud_deriv.f"
gfortran -c -std=legacy -ffixed-line-length-none -fdollar-ok \
  -fallow-argument-mismatch -J "$test_tmp" -I "$test_tmp" \
  -I "$repo_root/src/include" -o "$test_tmp/pcpcnc.o" \
  "$repo_root/src/lib/pcpcnc.f"
gfortran -c -std=legacy -ffixed-line-length-none -fdollar-ok \
  -fallow-argument-mismatch -J "$test_tmp" -I "$test_tmp" \
  -I "$repo_root/src/include" -o "$test_tmp/laps_deriv_sub.o" \
  "$repo_root/src/deriv/laps_deriv_sub.f"

# The focused tree does not ship the legacy NetCDF include required by the
# whole lapsio.f file.  Extract the modified COM/wind reader so its status
# interface and fixed-form syntax are still compiled exactly.
awk '
  /^      subroutine get_laps_3d_analysis_data\(/ {capture=1}
  capture && /^cdis/ {exit}
  capture {print}
' "$repo_root/src/lib/bgdata/lapsio.f" > "$test_tmp/lapsio_com_reader.f"
gfortran -c -std=legacy -ffixed-line-length-none \
  -fallow-argument-mismatch -o "$test_tmp/lapsio_com_reader.o" \
  "$test_tmp/lapsio_com_reader.f"

# Extract the production continuity/operator routines so the runtime test uses
# the exact fixed-form implementation without linking the unrelated KLAPS I/O.
awk '
  /^      subroutine leib_sub\(/ {capture=1}
  capture && /^      subroutine analzo\(/ {capture=0}
  capture {print}
  /^      subroutine fthree\(/ {operator=1}
  operator && /^      subroutine leib\(/ {operator=0}
  operator {print}
' "$repo_root/src/balance/qbalpe.f" > "$test_tmp/qbal_operator_core.f"

gfortran -c -std=legacy -ffixed-line-length-none -fcheck=all \
  -o "$test_tmp/qbal_operator_core.o" "$test_tmp/qbal_operator_core.f"
gfortran -std=f2008 -Wall -Wextra -fcheck=all \
  "$repo_root/tests/test_qbal_operator.f90" \
  "$test_tmp/qbal_operator_core.o" -o "$test_tmp/test_qbal_operator"

"$test_tmp/test_qbal_operator"

gfortran -c -std=legacy -ffixed-line-length-none \
  -fallow-argument-mismatch -I "$repo_root/src/include" \
  -J "$test_tmp" -o "$test_tmp/qbalpe.o" \
  "$repo_root/src/balance/qbalpe.f"

printf '%s\n' 'qbalpe fixed-form compile check passed'
