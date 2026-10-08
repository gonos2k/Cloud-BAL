#!/usr/bin/env python3
"""Add failure-only runtime FP-state capture to a scratch KDM6 source copy."""

from __future__ import annotations


USE_ANCHOR = "   use, intrinsic :: ieee_arithmetic, only : ieee_is_finite\n"
CALL_ANCHOR = (
    "         call specific_number_to_volume(ni(i,k,j), dry_density(i,k), "
    "number_value, number_valid)\n"
)


def transform(source: str) -> str:
    """Instrument only the NI conversion failure in the supplied source text."""
    if source.count(USE_ANCHOR) != 1 or source.count(CALL_ANCHOR) != 1:
        raise ValueError("KDM6 source does not match the pinned NI adapter anchors")
    source = source.replace(
        USE_ANCHOR,
        USE_ANCHOR + "   use, intrinsic :: iso_c_binding, only : c_int\n",
        1,
    )
    interface = """   interface
      function pr75_read_fp_state(thread_id) bind(C, name='pr75_read_fp_state') result(mxcsr)
        import :: c_int
        integer(c_int) :: thread_id
        integer(c_int) :: mxcsr
      end function pr75_read_fp_state
   end interface
"""
    module_anchor = "   integer, parameter, private :: PROGB_ABSENT = 0\n"
    if source.count(module_anchor) != 1:
        raise ValueError("KDM6 module declaration anchor is ambiguous")
    source = source.replace(module_anchor, interface + module_anchor, 1)
    decl_anchor = "   real :: number_value\n"
    if source.count(decl_anchor) != 1:
        raise ValueError("KDM6 adapter local declaration anchor is ambiguous")
    source = source.replace(
        decl_anchor,
        decl_anchor
        + "   integer(c_int) :: pr75_thread_before, pr75_thread_after\n"
        + "   integer(c_int) :: pr75_mxcsr_before, pr75_mxcsr_after\n"
        + "   integer :: pr75_unit, pr75_open_status\n",
        1,
    )
    diagnostic_call = """         pr75_mxcsr_before = pr75_read_fp_state(pr75_thread_before)
         call specific_number_to_volume(ni(i,k,j), dry_density(i,k), number_value, number_valid)
         pr75_mxcsr_after = pr75_read_fp_state(pr75_thread_after)
         if (.not. number_valid) then
           open(newunit=pr75_unit, file='pr75_native_fp.raw', status='unknown', &
                position='append', action='write', iostat=pr75_open_status)
           if (pr75_open_status == 0) then
             write(pr75_unit,'(A,\",\",I0,\",\",I0,\",\",I0,\",\",ES24.16E3,\",\",ES24.16E3,\",\",ES24.16E3,\",\",L1)') &
                  'NI_ADAPTER_FAILURE', i, j, k, ni(i,k,j), dry_density(i,k), number_value, &
                  number_valid
             write(pr75_unit,'(A,6(\",\",Z8.8))') &
                  'BITS_AND_STATE', pr75_mxcsr_before, pr75_mxcsr_after, &
                  transfer(ni(i,k,j),0), transfer(dry_density(i,k),0), &
                  transfer(number_value,0), pr75_thread_before
             write(pr75_unit,'(A,\",\",I0)') 'THREAD_AFTER', pr75_thread_after
             close(pr75_unit)
           endif
         endif
"""
    return source.replace(CALL_ANCHOR, diagnostic_call, 1)
