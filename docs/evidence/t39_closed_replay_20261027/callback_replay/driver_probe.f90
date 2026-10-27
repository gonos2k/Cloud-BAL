program replay
 use iso_fortran_env, only: int32,int64,real32,real64,real128
 use pr87_horizontal_diffusion64, only: horizontal_diffusion64
 implicit none
 real(real32) :: q1(1:3,1:1,1:3),n1(1:3,1:1,1:3),q2(1:3,1:1,1:3),n2(1:3,1:1,1:3)
 real(real32) :: x(1:3,1:1,1:3),mut(1:3,1:3),c1(1:1),c2(1:1)
 real(real32) :: ux(1:3,1:3),uy(1:3,1:3),vx(1:3,1:3),vy(1:3,1:3),tx(1:3,1:3),ty(1:3,1:3),rdx,rdy
 real(real64) :: oq(1:3,1:1,1:3),on(1:3,1:1,1:3),oq2(1:3,1:1,1:3),on2(1:3,1:1,1:3)
 real(real128) :: xq(1:3,1:1,1:3),xn(1:3,1:1,1:3),xq2(1:3,1:1,1:3),xn2(1:3,1:1,1:3)
 q1=0.0_real32; n1=0.0_real32; q2=0.0_real32; n2=0.0_real32; x=0.0_real32; mut=0.0_real32
 ux=0.0_real32; uy=0.0_real32; vx=0.0_real32; vy=0.0_real32; tx=0.0_real32; ty=0.0_real32
   q1(1,1,1)=transfer(int(z'00000000',int32),0.0_real32)
  q1(2,1,1)=transfer(int(z'00000000',int32),0.0_real32)
  q1(3,1,1)=transfer(int(z'00000000',int32),0.0_real32)
  q1(1,1,2)=transfer(int(z'00000384',int32),0.0_real32)
  q1(2,1,2)=transfer(int(z'00000000',int32),0.0_real32)
  q1(3,1,2)=transfer(int(z'00000000',int32),0.0_real32)
  q1(1,1,3)=transfer(int(z'00000000',int32),0.0_real32)
  q1(2,1,3)=transfer(int(z'00000000',int32),0.0_real32)
  q1(3,1,3)=transfer(int(z'00000000',int32),0.0_real32)
   n1(1,1,1)=transfer(int(z'00000000',int32),0.0_real32)
  n1(2,1,1)=transfer(int(z'00000000',int32),0.0_real32)
  n1(3,1,1)=transfer(int(z'00000000',int32),0.0_real32)
  n1(1,1,2)=transfer(int(z'00000001',int32),0.0_real32)
  n1(2,1,2)=transfer(int(z'00000000',int32),0.0_real32)
  n1(3,1,2)=transfer(int(z'00000000',int32),0.0_real32)
  n1(1,1,3)=transfer(int(z'00000000',int32),0.0_real32)
  n1(2,1,3)=transfer(int(z'00000000',int32),0.0_real32)
  n1(3,1,3)=transfer(int(z'00000000',int32),0.0_real32)
   x(1,1,1)=transfer(int(z'00000000',int32),0.0_real32)
  mut(1,1)=transfer(int(z'47AAAFB7',int32),0.0_real32)
  x(2,1,1)=transfer(int(z'44348B89',int32),0.0_real32)
  mut(2,1)=transfer(int(z'47A920E4',int32),0.0_real32)
  x(3,1,1)=transfer(int(z'44319493',int32),0.0_real32)
  mut(3,1)=transfer(int(z'47A6711C',int32),0.0_real32)
  x(1,1,2)=transfer(int(z'00000000',int32),0.0_real32)
  mut(1,2)=transfer(int(z'47AB4CF5',int32),0.0_real32)
  x(2,1,2)=transfer(int(z'44836389',int32),0.0_real32)
  mut(2,2)=transfer(int(z'47AA6467',int32),0.0_real32)
  x(3,1,2)=transfer(int(z'442C4C23',int32),0.0_real32)
  mut(3,2)=transfer(int(z'47A84FCA',int32),0.0_real32)
  x(1,1,3)=transfer(int(z'00000000',int32),0.0_real32)
  mut(1,3)=transfer(int(z'47AB8A26',int32),0.0_real32)
  x(2,1,3)=transfer(int(z'43DDBF05',int32),0.0_real32)
  mut(2,3)=transfer(int(z'47ABBD40',int32),0.0_real32)
  x(3,1,3)=transfer(int(z'43973D5B',int32),0.0_real32)
  mut(3,3)=transfer(int(z'47AB2488',int32),0.0_real32)
   ux(2,2)=transfer(int(z'3F77E651',int32),0.0_real32)
  ux(3,2)=transfer(int(z'3F77E5FA',int32),0.0_real32)
  uy(2,2)=transfer(int(z'3F77E651',int32),0.0_real32)
  uy(3,2)=transfer(int(z'3F77E5FA',int32),0.0_real32)
  vx(2,2)=transfer(int(z'3F842DCF',int32),0.0_real32)
  vx(2,3)=transfer(int(z'3F842FCF',int32),0.0_real32)
  vy(2,2)=transfer(int(z'3F77E808',int32),0.0_real32)
  vy(2,3)=transfer(int(z'3F77E448',int32),0.0_real32)
  tx(2,2)=transfer(int(z'3F77E626',int32),0.0_real32)
  ty(2,2)=transfer(int(z'3F77E626',int32),0.0_real32)
   c1(1)=transfer(int(z'3FD6BB00',int32),0.0_real32)
  c2(1)=transfer(int(z'C77B7245',int32),0.0_real32)
  rdx=transfer(int(z'3951B717',int32),0.0_real32)
  rdy=transfer(int(z'3951B717',int32),0.0_real32)
   q2(1,1,1)=0.0_real32; n2(1,1,1)=0.0_real32
  q2(1,1,2)=0.0_real32; n2(1,1,2)=0.0_real32
  q2(1,1,3)=0.0_real32; n2(1,1,3)=0.0_real32
  q2(2,1,1)=0.0_real32; n2(2,1,1)=0.0_real32
  q2(2,1,2)=0.0_real32; n2(2,1,2)=0.0_real32
  q2(2,1,3)=0.0_real32; n2(2,1,3)=0.0_real32
  q2(3,1,1)=0.0_real32; n2(3,1,1)=0.0_real32
  q2(3,1,2)=0.0_real32; n2(3,1,2)=0.0_real32
  q2(3,1,3)=0.0_real32; n2(3,1,3)=0.0_real32
 call horizontal_diffusion64(q1,mut,c1,c2,ux,uy,vx,vy,tx,ty,x,rdx,rdy,1,3,1,1,1,3,2,2,2,2,1,1,oq,xq)
 call horizontal_diffusion64(n1,mut,c1,c2,ux,uy,vx,vy,tx,ty,x,rdx,rdy,1,3,1,1,1,3,2,2,2,2,1,1,on,xn)
 call horizontal_diffusion64(q2,mut,c1,c2,ux,uy,vx,vy,tx,ty,x,rdx,rdy,1,3,1,1,1,3,2,2,2,2,1,1,oq2,xq2)
 call horizontal_diffusion64(n2,mut,c1,c2,ux,uy,vx,vy,tx,ty,x,rdx,rdy,1,3,1,1,1,3,2,2,2,2,1,1,on2,xn2)
 write(*,'(A,1X,ES45.35E4,1X,Z16.16)') 'RK1_Q',xq(2,1,2),transfer(oq(2,1,2),0_int64)
 write(*,'(A,1X,ES45.35E4,1X,Z16.16)') 'RK1_B',xn(2,1,2),transfer(on(2,1,2),0_int64)
 write(*,'(A,1X,ES45.35E4,1X,Z16.16)') 'RK2_Q',xq2(2,1,2),transfer(oq2(2,1,2),0_int64)
 write(*,'(A,1X,ES45.35E4,1X,Z16.16)') 'RK2_B',xn2(2,1,2),transfer(on2(2,1,2),0_int64)
 write(*,'(A,1X,L1,1X,ES45.35E4)') 'RK1_RATIO_EXACT_900',xq(2,1,2)==900.0_real128*xn(2,1,2),xq(2,1,2)/xn(2,1,2)-900.0_real128
end program replay
