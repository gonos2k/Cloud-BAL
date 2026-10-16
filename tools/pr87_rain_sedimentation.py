"""Generate the frozen V10 KDM6 rain-pair sedimentation overlay.

The transformation replaces the embedded, pinned PR85 sediment helper with
the extended paired helper and routes rain mass and number through the same
top-down packet limiter.  The input is verified against the closed V10 source
identity before any edits are returned.
"""
from __future__ import annotations

import hashlib
import re


V10_MODULE_SOURCE_SHA256 = "dc0e9c20997f8fb34a6a164a707338a4a5d8817acbaab5a64efcb842e61e38d2"
V10_EMBEDDED_HELPER_SHA256 = "3acda5cb7df3f17976ffa9392a9d1d2a82046814fb57b0fbd919914bf2eb3fb2"
HELPER_NAME = "pr85_kdm6_paired_sediment_column"


def _sha256_text(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"expected one {label} anchor, found {count}")
    return source.replace(old, new, 1)


def _extract_helper(source: str) -> tuple[int, int, str]:
    start_matches = list(re.finditer(
        rf"(?im)^SUBROUTINE\s+{HELPER_NAME}\s*\(", source))
    end_matches = list(re.finditer(
        rf"(?im)^END\s+SUBROUTINE\s+{HELPER_NAME}\s*$", source))
    if len(start_matches) != 1 or len(end_matches) != 1:
        raise ValueError("expected one embedded paired sediment helper body")
    start = start_matches[0].start()
    end = end_matches[0].end()
    if end < start:
        raise ValueError("embedded paired sediment helper ends before it starts")
    if end < len(source) and source[end] == "\n":
        end += 1
    return start, end, source[start:end]


def _validate_extended_helper(helper_text: str) -> str:
    text = helper_text.rstrip() + "\n"
    compact = re.sub(r"[\s&]+", "", text).lower()
    if f"subroutine{HELPER_NAME}(" not in compact:
        raise ValueError("replacement helper has the wrong procedure name")
    if "budget_unit,trace,valid,rain_pidn,rain_power,rain_lambda_min,rain_lambda_max)" not in compact:
        raise ValueError("replacement helper lacks required rain PSD arguments")
    if "pr87_sed_rain=3" not in compact:
        raise ValueError("replacement helper does not declare the RAIN mode as 3")
    return text


def _replace_legacy_rain_updates(source: str) -> str:
    top_block = (
        "           falk(i,k,1) = dend(i,k)*qrs(i,k,1)*mass_velocity_rate(i,k,1)/mstep(i)\n"
        "           falkn(i,k,1) = nrs(i,k,1)*number_velocity_rate(i,k,1)/mstep(i)\n"
        "           fall(i,k,1) = fall(i,k,1)+falk(i,k,1)\n"
        "           falln(i,k,1) = falln(i,k,1)+falkn(i,k,1)\n"
        "           qrs(i,k,1) = max(qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k),0.)\n"
        "           nrs(i,k,1) = max(nrs(i,k,1)-falkn(i,k,1)*dtcld,0.)\n"
    )
    top_replacement = (
        "           falk(i,k,1) = REAL(pr87_rain_qrate(k))\n"
        "           falkn(i,k,1) = REAL(pr87_rain_nrate(k))\n"
        "           fall(i,k,1) = fall(i,k,1)+falk(i,k,1)\n"
        "           falln(i,k,1) = falln(i,k,1)+falkn(i,k,1)\n"
    )
    lower_replacement = (
        "             falk(i,k,1) = REAL(pr87_rain_qrate(k))\n"
        "             falkn(i,k,1) = REAL(pr87_rain_nrate(k))\n"
        "             fall(i,k,1) = fall(i,k,1)+falk(i,k,1)\n"
        "             falln(i,k,1) = falln(i,k,1)+falkn(i,k,1)\n"
    )
    source = _replace_once(source, top_block, top_replacement, "top-level legacy rain update")
    lower_start_marker = "             falk(i,k,1) = dend(i,k)*qrs(i,k,1)*mass_velocity_rate(i,k,1)/mstep(i)\n"
    lower_end_marker = "             fallb(i,k) = fallb(i,k)+falkb(i,k)\n"
    if source.count(lower_start_marker) != 1:
        raise ValueError("expected one lower-level legacy rain update")
    lower_start = source.index(lower_start_marker)
    lower_end = source.find(lower_end_marker, lower_start)
    if lower_end < 0:
        raise ValueError("lower-level rain update lacks the following graupel accumulation")
    return source[:lower_start] + lower_replacement + source[lower_end:]


def _transform_source(source: str, helper_text: str) -> str:
    """Apply the reviewed transformation after identity checks in the caller."""
    helper = _validate_extended_helper(helper_text)
    hstart, hend, old_helper = _extract_helper(source)
    if _sha256_text(old_helper.rstrip() + "\n") != V10_EMBEDDED_HELPER_SHA256:
        raise ValueError("embedded V10 helper does not match the pinned preimage")
    source = source[:hstart] + helper + source[hend:]

    # The helper API now takes two explicit pair bounds.  The existing G and
    # ice calls keep their former mode behavior with inert zero bounds.
    source = _replace_once(
        source,
        "                 pr85_g_unit,pr67_trace_this_call,pr85_g_valid)\n",
        "                 pr85_g_unit,pr67_trace_this_call,pr85_g_valid,0.0,0.0,0.0,0.0)\n",
        "graupel helper call",
    )
    source = _replace_once(
        source,
        "                 pr85_ice_unit,pr67_trace_this_call,pr85_ice_valid)\n",
        "                 pr85_ice_unit,pr67_trace_this_call,pr85_ice_valid,0.0,0.0,0.0,0.0)\n",
        "ice helper call",
    )

    source = _replace_once(
        source,
        "   integer :: pr85_g_unit, pr85_g_ios\n",
        "   integer :: pr85_g_unit, pr85_g_ios\n"
        "   integer :: pr87_rain_unit, pr87_rain_ios\n",
        "rain ledger unit declarations",
    )
    source = _replace_once(
        source,
        "   double precision, dimension(kts:kte) :: pr85_ice_qrate, pr85_ice_nrate\n",
        "   double precision, dimension(kts:kte) :: pr85_ice_qrate, pr85_ice_nrate\n"
        "   double precision, dimension(kts:kte) :: pr87_rain_qrate, pr87_rain_nrate\n",
        "rain rate declarations",
    )
    source = _replace_once(
        source,
        "   logical :: pr85_g_valid\n",
        "   logical :: pr85_g_valid\n"
        "   integer, parameter :: PR87_SED_RAIN = 3\n"
        "   logical :: pr87_rain_valid\n",
        "rain validity declaration",
    )
    source = _replace_once(
        source,
        "   external :: pr85_kdm6_paired_sediment_column\n",
        "   interface\n"
        "      subroutine pr85_kdm6_paired_sediment_column(kts,kte,cell_i,lat,substep,dt,mstep, &\n"
        "           dry_density,delz,mass_rate,second_rate,qstate,second_state,mode,q_active_min, &\n"
        "           second_active_min,density_min,density_max,approved_q_rate,approved_second_rate, &\n"
        "           budget_unit,trace,valid,rain_pidn,rain_power,rain_lambda_min,rain_lambda_max)\n"
        "         integer, intent(in) :: kts,kte,cell_i,lat,substep,mstep,budget_unit\n"
        "         real, intent(in) :: dt,dry_density(kts:kte),delz(kts:kte)\n"
        "         double precision, intent(in) :: mass_rate(kts:kte),second_rate(kts:kte)\n"
        "         real, intent(inout) :: qstate(kts:kte),second_state(kts:kte)\n"
        "         integer, intent(in) :: mode\n"
        "         real, intent(in) :: q_active_min,second_active_min,density_min,density_max\n"
        "         double precision, intent(out) :: approved_q_rate(kts:kte),approved_second_rate(kts:kte)\n"
        "         logical, intent(in) :: trace\n"
        "         logical, intent(out) :: valid\n"
        "         real, intent(in) :: rain_pidn,rain_power,rain_lambda_min,rain_lambda_max\n"
        "      end subroutine pr85_kdm6_paired_sediment_column\n"
        "   end interface\n",
        "paired sediment explicit interface",
    )
    source = _replace_once(
        source,
        "   integer                                , intent(in   ) :: lat\n",
        "   integer                                , intent(in   ) :: lat\n"
        "   integer                                , intent(in   ) :: pr87_model_timestep\n",
        "rain model-step dummy declaration",
    )
    source = _replace_once(
        source,
        "                   ,lat                                           &\n"
        "                   ,slmsk",
        "                   ,lat                                           &\n"
        "                   ,pr87_model_timestep                           &\n"
        "                   ,slmsk",
        "kdm62D model-step signature",
    )
    source = _replace_once(
        source,
        "                ,j                                            &\n"
        "                ,xland(ims,j)",
        "                ,j                                            &\n"
        "                ,itimestep                                   &\n"
        "                ,xland(ims,j)",
        "kdm6 model-step actual argument",
    )
    # Record rain decisions on every model call.  The wider PR67 ledger remains
    # first-call-only, so the new compact rain record owns its own I/O guards.
    source = _replace_once(
        source,
        "      pr85_g_unit = 0\n",
        "      pr87_rain_unit = 0\n"
        "      pr87_rain_ios = 0\n"
        "      open(newunit=pr87_rain_unit,file='pr87_rain_sedimentation_budget.raw', &\n"
        "           form='formatted',status='unknown',position='append',action='write',iostat=pr87_rain_ios)\n"
        "      if (pr87_rain_ios /= 0) error stop 'PR87 rain sedimentation ledger open failed'\n"
        "      write(pr87_rain_unit,'(a)',iostat=pr87_rain_ios) &\n"
        "        '# PR87_RAIN_CALL: model_timestep,wrapper_j,dtcld; PR87_RAIN_SED rows follow'\n"
        "      if (pr87_rain_ios /= 0) error stop 'PR87 rain sedimentation ledger header failed'\n"
        "      write(pr87_rain_unit,'(a,2i10,1p,e24.16)',iostat=pr87_rain_ios) &\n"
        "        'PR87_RAIN_CALL',pr87_model_timestep,lat,dtcld\n"
        "      if (pr87_rain_ios /= 0) error stop 'PR87 rain sedimentation ledger metadata failed'\n"
        "      pr85_g_unit = 0\n",
        "rain ledger open and timestep metadata",
    )

    # The rain helper runs once per active column/substep beside the existing
    # graupel packet. It mutates only rain Q/N and returns rates for the
    # unchanged fall/falln accumulators below.
    graupel_end = (
        "            do k = kts, kte\n"
        "              falk(i,k,3) = REAL(pr85_g_qrate(k))\n"
        "              falkb(i,k) = REAL(pr85_g_brate(k))\n"
        "            enddo\n"
        "          endif\n"
    )
    rain_call = (
        "          pr87_rain_qrate(kts:kte) = 0.0d0\n"
        "          pr87_rain_nrate(kts:kte) = 0.0d0\n"
        "          if (n.le.mstep(i)) then\n"
        "            call pr85_kdm6_paired_sediment_column(kts,kte,i,lat,n,dtcld,mstep(i), &\n"
        "                 dend(i,kts:kte),delz(i,kts:kte),mass_velocity_rate(i,kts:kte,1), &\n"
        "                 number_velocity_rate(i,kts:kte,1),qrs(i,kts:kte,1),nrs(i,kts:kte,1), &\n"
        "                 PR87_SED_RAIN,qcrmin,nrmin,0.0,0.0, &\n"
        "                 pr87_rain_qrate(kts:kte),pr87_rain_nrate(kts:kte), &\n"
        "                 pr87_rain_unit,.true.,pr87_rain_valid, &\n"
        "                 pidnr,dmr,lamdarmin,lamdarmax)\n"
        "            if (.not.pr87_rain_valid) error stop 'PR87 rain sedimentation packet rejected'\n"
        "          endif\n"
    )
    source = _replace_once(source, graupel_end, graupel_end + rain_call, "graupel/rain insertion point")

    source = _replace_legacy_rain_updates(source)

    source = _replace_once(
        source,
        "      if (pr67_trace_this_call) close(pr85_g_unit,iostat=pr85_g_ios)\n",
        "      close(pr87_rain_unit,iostat=pr87_rain_ios)\n"
        "      if (pr87_rain_ios /= 0) &\n"
        "        error stop 'PR87 rain sedimentation ledger close failed'\n"
        "      if (pr67_trace_this_call) close(pr85_g_unit,iostat=pr85_g_ios)\n",
        "rain ledger close",
    )
    return source


def generate_rain_sedimentation(source: str, helper_text: str) -> str:
    """Return source with paired rain transport; reject any source drift."""
    actual_sha = _sha256_text(source)
    if actual_sha != V10_MODULE_SOURCE_SHA256:
        raise ValueError(
            f"V10 KDM6 source identity mismatch: expected {V10_MODULE_SOURCE_SHA256}, got {actual_sha}"
        )
    return _transform_source(source, helper_text)


def add_rain_failure_diagnostic(source: str) -> str:
    """Print one rejected rain column immediately before its unchanged fatal."""
    old = "            if (.not.pr87_rain_valid) error stop 'PR87 rain sedimentation packet rejected'\n"
    diagnostic = (
        "            if (.not.pr87_rain_valid) then\n"
        "              write(pr87_rain_unit,'(a,5i10,1p,7e24.16)') &\n"
        "                'PR87_RAIN_FAIL',pr87_model_timestep,i,lat,n,mstep(i), &\n"
        "                dtcld,pidnr,dmr,lamdarmin,lamdarmax,qcrmin,nrmin\n"
        "              do k=kts,kte\n"
        "                write(pr87_rain_unit,'(a,i10,1p,6e24.16)') &\n"
        "                  'PR87_RAIN_FAIL_LEVEL',k,qrs(i,k,1),nrs(i,k,1),dend(i,k), &\n"
        "                  delz(i,k),mass_velocity_rate(i,k,1),number_velocity_rate(i,k,1)\n"
        "              enddo\n"
        "              flush(pr87_rain_unit)\n"
        "              error stop 'PR87 rain sedimentation packet rejected'\n"
        "            endif\n"
    )
    return _replace_once(source, old, diagnostic, "rain packet rejection fatal")
