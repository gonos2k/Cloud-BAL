program constants_probe
 use module_model_constants, only: g, r_d, cp, p1000mb, t0
 implicit none
 write(*,'(5(ES26.17,1X))') dble(g),dble(r_d),dble(cp),dble(p1000mb),dble(t0)
end program
