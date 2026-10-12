"""Add an environment-selected FTZ/DAZ choice to copied PR77 observers."""

from __future__ import annotations

from pr77_native_state_transform import transform as transform_native
from pr77_native_state_transform import transform_host_main as transform_host


def transform_kdm6(source: str) -> str:
    source = transform_native(source)
    interface_end = "   end interface\n"
    apply_call = "   pr76_mxcsr_before = pr76_apply_gradual(pr76_mxcsr_after, pr76_thread_id)\n"
    if source.count(interface_end) != 1 or source.count(apply_call) != 1:
        raise ValueError("unexpected PR77 KDM6 runtime-policy anchors")
    source = source.replace(
        interface_end,
        """      function pr76_read_fp_state(thread_id) bind(C, name='pr76_read_fp_state') result(mxcsr)
        import :: c_int
        integer(c_int) :: thread_id, mxcsr
      end function pr76_read_fp_state
""" + interface_end,
        1,
    )
    source = source.replace(
        "   integer :: pr76_unit, pr76_open_status\n",
        "   integer :: pr76_unit, pr76_open_status\n"
        "   character(len=32) :: pr78_fp_mode\n",
        1,
    )
    source = source.replace(
        apply_call,
        """   pr78_fp_mode = ''
   call get_environment_variable('PR78_FP_MODE', pr78_fp_mode)
   pr76_mxcsr_before = pr76_read_fp_state(pr76_thread_id)
   pr76_mxcsr_after = pr76_mxcsr_before
   if (trim(pr78_fp_mode) == 'CLEAR_FTZ_DAZ') then
     pr76_mxcsr_before = pr76_apply_gradual(pr76_mxcsr_after, pr76_thread_id)
   else if (trim(pr78_fp_mode) /= 'PRESERVE') then
     error stop 'PR78_FP_MODE must be PRESERVE or CLEAR_FTZ_DAZ'
   endif
""",
        1,
    )
    return source


def transform_host_main(source: str) -> str:
    source = transform_host(source)
    interface_end = "   end interface\n"
    policy_call = "    mxcsr_before = pr76_apply_gradual(mxcsr_after, thread_id)\n"
    if source.count(interface_end) != 1 or source.count(policy_call) != 1:
        raise ValueError("unexpected PR77 host-main runtime-policy anchors")
    source = source.replace(
        interface_end,
        """      function pr76_read_fp_state(thread_id) bind(C, name='pr76_read_fp_state') result(mxcsr)
        import :: c_int
        integer(c_int) :: thread_id, mxcsr
      end function pr76_read_fp_state
""" + interface_end,
        1,
    )
    source = source.replace(
        "    INTEGER(c_int) :: thread_id\n",
        "    INTEGER(c_int) :: thread_id\n"
        "    CHARACTER(LEN=32) :: fp_mode\n",
        1,
    )
    source = source.replace(
        policy_call,
        """    fp_mode = ''
    CALL GET_ENVIRONMENT_VARIABLE('PR78_FP_MODE', fp_mode)
    mxcsr_before = pr76_read_fp_state(thread_id)
    mxcsr_after = mxcsr_before
    IF (TRIM(fp_mode) == 'CLEAR_FTZ_DAZ') THEN
      mxcsr_before = pr76_apply_gradual(mxcsr_after, thread_id)
    ELSE IF (TRIM(fp_mode) /= 'PRESERVE') THEN
      ERROR STOP 'PR78_FP_MODE must be PRESERVE or CLEAR_FTZ_DAZ'
    END IF
""",
        1,
    )
    return source
