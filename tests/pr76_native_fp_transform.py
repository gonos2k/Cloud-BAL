#!/usr/bin/env python3
"""Instrument a scratch KDM6 source copy for gradual-underflow comparison."""

from __future__ import annotations

from pr75_native_fp_transform import transform as add_failure_capture


KDM6_ENTRY_ANCHOR = "   subroutine kdm6(th, q, qc, qr, qi, qs, qg,             &\n"
KDM6_LAST_DECLARATION = "   real :: z_sum\n"
KDM6_FIRST_STATEMENT = "   pr67_trace_this_call = .not. pr67_trace_complete\n"


def transform(source: str, *, gradual: bool) -> str:
    """Add PR75 failure capture; in treatment, clear FTZ/DAZ at KDM6 entry."""
    source = add_failure_capture(source)
    target_decl = "   integer :: pr75_unit, pr75_open_status\n"
    target_after_call = "         pr75_mxcsr_after = pr75_read_fp_state(pr75_thread_after)\n"
    if source.count(target_decl) != 1 or source.count(target_after_call) != 1:
        raise ValueError("PR75 conversion observer anchors are absent or ambiguous")
    source = source.replace(
        target_decl,
        target_decl + "   integer :: pr76_target_unit, pr76_target_status\n",
        1,
    )
    source = source.replace(
        target_after_call,
        target_after_call + """         if (i == 211 .and. j == 2 .and. k == 15) then
           open(newunit=pr76_target_unit, file='pr76_target_call.raw', status='unknown', &
                position='append', action='write', iostat=pr76_target_status)
           if (pr76_target_status == 0) then
             write(pr76_target_unit,'(A,3(\",\",I0),3(\",\",ES24.16E3),\",\",L1)') &
                  'TARGET_CALL', i, j, k, ni(i,k,j), dry_density(i,k), number_value, number_valid
             write(pr76_target_unit,'(A,4(\",\",Z8.8))') 'TARGET_BITS', &
                  pr75_mxcsr_before, pr75_mxcsr_after, transfer(ni(i,k,j),0), &
                  transfer(dry_density(i,k),0)
             write(pr76_target_unit,'(A,\",\",Z8.8)') 'RESULT_BITS', transfer(number_value,0)
             write(pr76_target_unit,'(A,\",\",I0,\",\",I0)') 'THREAD_IDS', &
                  pr75_thread_before, pr75_thread_after
             close(pr76_target_unit)
           endif
         endif
""",
        1,
    )
    if not gradual:
        return source
    if (source.count(KDM6_ENTRY_ANCHOR) != 1
            or source.count(KDM6_LAST_DECLARATION) != 1
            or source.count(KDM6_FIRST_STATEMENT) != 1):
        raise ValueError("KDM6 entry anchors are absent or ambiguous")
    interface_anchor = "   end interface\n"
    if source.count(interface_anchor) != 1:
        raise ValueError("KDM6 C helper interface anchor is absent or ambiguous")
    source = source.replace(
        interface_anchor,
        """   function pr76_apply_gradual(after, thread_id) bind(C, name='pr76_apply_gradual') result(mxcsr)
     import :: c_int
     integer(c_int) :: after, thread_id
     integer(c_int) :: mxcsr
   end function pr76_apply_gradual
""" + interface_anchor,
        1,
    )
    source = source.replace(
        KDM6_LAST_DECLARATION,
        KDM6_LAST_DECLARATION
        + "   integer(c_int) :: pr76_mxcsr_before, pr76_mxcsr_after, pr76_thread_id\n"
        + "   integer :: pr76_unit, pr76_open_status\n",
        1,
    )
    entry_call = """   pr76_mxcsr_before = pr76_apply_gradual(pr76_mxcsr_after, pr76_thread_id)
   open(newunit=pr76_unit, file='pr76_thread_entry.raw', status='unknown', &
        position='append', action='write', iostat=pr76_open_status)
   if (pr76_open_status == 0) then
     write(pr76_unit,'(A,2(\",\",Z8.8),\",\",I0)') 'KDM6_ENTRY', &
          pr76_mxcsr_before, pr76_mxcsr_after, pr76_thread_id
     close(pr76_unit)
   endif
"""
    source = source.replace(KDM6_FIRST_STATEMENT, entry_call + KDM6_FIRST_STATEMENT, 1)
    return source
