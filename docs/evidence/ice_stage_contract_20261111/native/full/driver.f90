program column
 use module_mp_kdm6, only: kdm6, kdm6init
 use module_mp_radar, only: xam_g
 use module_model_constants, only: epsilon,r_d,r_v,cp,cpv,cliq,cice,psat,xls,xlv,xlf,ep_1,ep_2
 implicit none
 integer, parameter :: nk=39
 integer :: k
 real :: th(1, nk, 1),q(1,nk,1),qc(1,nk,1),qr(1,nk,1),qi(1,nk,1),qs(1,nk,1),qg(1,nk,1)
 real :: nn(1,nk,1),nc(1,nk,1),ni(1,nk,1),nr(1,nk,1),bg(1,nk,1),diag_rhog(1,nk,1)
 real :: den(1,nk,1),pii(1,nk,1),p(1,nk,1),delz(1,nk,1),xland(1,1)
 real :: rain(1,1),rainncv(1,1),snow(1,1),snowncv(1,1),sr(1,1),graupel(1,1),graupelncv(1,1)
 real :: refl(1,nk,1),rec(1,nk,1),rei(1,nk,1),res(1,nk,1),tk
 open(89,file='stages.txt',status='replace')
 read(*,*) xland
 do k=1,nk
  read(*,*) th(1,k,1),tk,p(1,k,1),den(1,k,1),delz(1,k,1),q(1,k,1),qc(1,k,1),qr(1,k,1), &
       qi(1,k,1),qs(1,k,1),qg(1,k,1),nn(1,k,1),nc(1,k,1),ni(1,k,1),nr(1,k,1),bg(1,k,1)
  pii(1,k,1)=tk/th(1,k,1)
 enddo
 rain=0.; rainncv=0.; snow=0.; snowncv=0.; sr=0.; graupel=0.; graupelncv=0.
 refl=0.; rec=0.; rei=0.; res=0.; diag_rhog=0.
 xam_g=acos(-1.0)*500.0/6.0
 call kdm6init(1.28,1000.,100.,cliq,cpv,2.e8,0,.false.)
 call kdm6(TH=th,Q=q,QC=qc,QR=qr,QI=qi,QS=qs,QG=qg,NN=nn,NC=nc,NI=ni,NR=nr,BG=bg,DIAG_RHOG=diag_rhog, &
 DEN=den,PII=pii,P=p,DELZ=delz,DELT=20.,G=9.81,CPD=cp,CPV=cpv,CCN0=2.e8,RD=r_d,RV=r_v, &
 T0C=273.15,EP1=ep_1,EP2=ep_2,QMIN=epsilon,XLS=xls,XLV0=xlv,XLF0=xlf,DEN0=1.28,DENR=1000., &
 SCALE_H=0.,QNN_LAND_MULT=1.,QNN_SEA_MULT=1.,NCMIN_LAND=10.,NCMIN_SEA=10.,CLIQ=cliq,CICE=cice, &
 PSAT=psat,XLAND=xland,RAIN=rain,RAINNCV=rainncv,SNOW=snow,SNOWNCV=snowncv,SR=sr,REFL_10CM=refl, &
 DIAGFLAG=.false.,DO_RADAR_REF=0,GRAUPEL=graupel,GRAUPELNCV=graupelncv,ITIMESTEP=2,HAS_REQC=1, &
 HAS_REQI=1,HAS_REQS=1,RE_CLOUD=rec,RE_ICE=rei,RE_SNOW=res,IDS=1,IDE=1,JDS=1,JDE=1,KDS=1,KDE=nk, &
 IMS=1,IME=1,JMS=1,JME=1,KMS=1,KME=nk,ITS=1,ITE=1,JTS=1,JTE=1,KTS=1,KTE=nk)
 close(89)
 open(90,file='terminal.bin',access='stream',form='unformatted',status='replace')
 write(90) th,q,qc,qr,qi,qs,qg,nn,nc,ni,nr,bg,diag_rhog,den,pii,p,delz,xland, &
 rain,rainncv,snow,snowncv,sr,graupel,graupelncv,refl,rec,rei,res
 close(90)
end program column

subroutine wrf_get_myproc(rank)
 integer :: rank
 rank=0
end subroutine wrf_get_myproc
