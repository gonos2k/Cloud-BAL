program cap_rounding
 implicit none
 real :: q,rho,dt,flux,dq
 q=1.8335029675076164e-13; rho=6.418061256408691; dt=0.01687532663345337
 flux=(rho*q)/dt
 dq=(flux*dt)/rho
 print *, 'q, rho, dt, flux, dq, q-dq:',q,rho,dt,flux,dq,q-dq
 if (dq<=q) stop 1
end program
