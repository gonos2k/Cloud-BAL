set pagination off
set confirm off
set debuginfod enabled off
catch exec
run
break module_wrf_top_mp_wrf_init_
commands
silent
printf "POLICY_AT_WRF_INIT mxcsr=0x%x\n", $mxcsr
continue
end
continue
printf "TRAP_STATE mxcsr=0x%x\n", $mxcsr
info registers rip xmm0 xmm2 xmm3 xmm4 mxcsr
x/i $pc
bt
