set pagination off
set confirm off
set debuginfod enabled off
catch signal SIGFPE
commands
  silent
  printf "\n=== FIRST FLOATING-POINT TRAP ===\n"
  info registers rip eflags mxcsr
  info registers xmm0 xmm1 xmm2 xmm3 xmm4 xmm5 xmm6 xmm7
  info registers xmm8 xmm9 xmm10 xmm11 xmm12 xmm13 xmm14 xmm15
  info all-registers
  x/12i $pc-20
  info symbol $pc
  info line *$pc
  list *$pc
  bt 12
  quit
end
run
