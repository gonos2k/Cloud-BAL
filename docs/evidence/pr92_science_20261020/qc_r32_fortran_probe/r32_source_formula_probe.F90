program sixteen
 implicit none
 integer :: i,j,ios,k,above,nlev,nlist,idx(21),left,lev
 real :: psfc_in,terrain,tavgsfc,ptop,psfc,tv,delz,intq,rhobar,qbar,dz,p1,p2,t1,t2,q1,q2,z1,z2
 real :: p(21),q(21),t(21),z(21),qc(21),pd(21),c3(39),c4(39),obs(39),mu0,pnew
 real :: xx(0:1),yy(0:1),pred
 real, parameter :: g=9.81,rd=287.0
 open(10,file='sixteen_columns.dat',status='old')
 do
  read(10,*,iostat=ios) i,j,psfc_in,terrain,tavgsfc,ptop,c3,c4,obs,p,q,t,z,qc
  if(ios/=0) exit
  tv=tavgsfc*(1.0+0.608*q(1)); delz=z(1)-terrain
  psfc=psfc_in*exp(g*delz/(rd*tv))
  above=-1
  do k=2,20
   if(p(k-1)-psfc>=0.0 .and. p(k)<psfc) then
    above=k;exit
   endif
  enddo
  if(above<0) stop 21
  intq=0.0;pd(21)=p(21)
  do k=20,above,-1
   rhobar=(p(k)/(rd*t(k))+p(k+1)/(rd*t(k+1)))*0.5
   qbar=(q(k)+q(k+1))*0.5;dz=z(k+1)-z(k)
   intq=intq+g*qbar*rhobar/(1.0+qbar)*dz
   pd(k)=p(k)-intq
  enddo
  if(p(above-1)-psfc>=0.0 .and. p(above)<psfc .and. above>1) then
   p1=psfc;p2=p(above);t1=t(1);t2=t(above);q1=q(1);q2=q(above);z1=z(1);z2=z(above)
   rhobar=(p1/(rd*t1)+p2/(rd*t2))*0.5;qbar=(q1+q2)*0.5;dz=z2-z1
   if(dz>0.1) intq=intq+g*qbar*rhobar/(1.0+qbar)*dz
   do k=above-1,2,-1
    pd(k)=p(k)-intq
   enddo
  endif
  pd(1)=psfc-intq
  mu0=psfc-intq-ptop
  nlist=1;idx(1)=1
  do k=2,21
   if(pd(idx(nlist))-pd(k)<500.0 .and. k<21) cycle
   nlist=nlist+1;idx(nlist)=k
  enddo
  do lev=1,39
   pnew=c3(lev)*mu0+c4(lev)+ptop
   left=-1
   if(pnew>pd(idx(1))) then
    left=1
   else
    do k=1,nlist-1
     if(pnew<=pd(idx(k)) .and. pnew>=pd(idx(k+1))) then
      left=k;exit
     endif
    enddo
   endif
   if(left<1 .or. left>=nlist) then
    print *, 'NO BRACKET',i,j,lev,pnew
    stop 22
   endif
   xx(0)=log(pd(idx(left)));xx(1)=log(pd(idx(left+1)))
   yy(0)=qc(idx(left));yy(1)=qc(idx(left+1))
   call lagrange_interp(xx,yy,1,log(pnew),pred)
   print '(3(I4,1X),2(Z8.8,1X),I3,1X)',i,j,lev,transfer(pred,0),transfer(obs(lev),0),left
  enddo
 enddo
end program
