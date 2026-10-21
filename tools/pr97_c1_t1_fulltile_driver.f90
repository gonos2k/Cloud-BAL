program pr97_c1_kdm6_fulltile_replay
  use module_mp_kdm6, only: kdm6,kdm6init
  use module_model_constants, only: g,cp,cpv,r_d,r_v,svpt0,ep_1,ep_2,epsilon, &
    xls,xlv,xlf,rhoair0,rhowater,rhosnow,cliq,cice,psat
  implicit none
  integer :: b(20),ierr,n,ios,u,stage,timestep
  integer :: ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte
  real :: params(5),dt,ccn,scale_h,land_mult,sea_mult
  real, allocatable, target :: state(:,:,:,:)
  real, pointer, contiguous :: th(:,:,:),pii(:,:,:),den(:,:,:),p(:,:,:),delz(:,:,:)
  real, pointer, contiguous :: q(:,:,:),qc(:,:,:),qr(:,:,:),qi(:,:,:),qs(:,:,:),qg(:,:,:)
  real, pointer, contiguous :: nn(:,:,:),nc(:,:,:),ni(:,:,:),nr(:,:,:),bg(:,:,:),diag_rhog(:,:,:)
  real, allocatable :: xland(:,:),rain(:,:),rainncv(:,:),snow(:,:),snowncv(:,:),sr(:,:),graupel(:,:),graupelncv(:,:)
  real, allocatable :: refl(:,:,:),re_cloud(:,:,:),re_ice(:,:,:),re_snow(:,:,:)
  character(len=8) :: name
  character(len=1024) :: input_path
  character(len=8), parameter :: expected(17)=[character(len=8) :: &
    'TH','PII','DEN','P','DELZ','Q','QC','QR','QI','QS','QG','NN','NC','NI','NR','BG','DIAGRHOG']
  call get_command_argument(1,input_path)
  if (len_trim(input_path)==0) error stop 'usage: replay.exe kdm6_first_call_pre.raw'
  open(newunit=u,file=trim(input_path),access='stream',form='unformatted',status='old',convert='big_endian')
  read(u) name
  if (name/='KDM6TRC1') error stop 'wrong raw trace signature'
  read(u) b
  stage=b(1);timestep=b(2)
  ids=b(3);ide=b(4);jds=b(5);jde=b(6);kds=b(7);kde=b(8)
  ims=b(9);ime=b(10);jms=b(11);jme=b(12);kms=b(13);kme=b(14)
  its=b(15);ite=b(16);jts=b(17);jte=b(18);kts=b(19);kte=b(20)
  read(u) params
  dt=params(1);ccn=params(2);scale_h=params(3);land_mult=params(4);sea_mult=params(5)
  if (stage/=1 .or. timestep<1) error stop 'expected first-call pre trace'
  allocate(state(ims:ime,kms:kme,jms:jme,17))
  do n=1,17
    read(u) name
    if (name/=expected(n)) then
      write(*,*) 'FIELD_ORDER',n,trim(expected(n)),trim(name)
      error stop 'raw field order mismatch'
    endif
    read(u) state(:,:,:,n)
  enddo
  read(u) name
  if (name/='XLAND') error stop 'expected XLAND field'
  allocate(xland(ims:ime,jms:jme));read(u)xland
  close(u)
  th=>state(:,:,:,1);pii=>state(:,:,:,2);den=>state(:,:,:,3);p=>state(:,:,:,4);delz=>state(:,:,:,5)
  q=>state(:,:,:,6);qc=>state(:,:,:,7);qr=>state(:,:,:,8);qi=>state(:,:,:,9);qs=>state(:,:,:,10);qg=>state(:,:,:,11)
  nn=>state(:,:,:,12);nc=>state(:,:,:,13);ni=>state(:,:,:,14);nr=>state(:,:,:,15);bg=>state(:,:,:,16);diag_rhog=>state(:,:,:,17)
  allocate(rain(ims:ime,jms:jme),rainncv(ims:ime,jms:jme),snow(ims:ime,jms:jme),snowncv(ims:ime,jms:jme))
  allocate(sr(ims:ime,jms:jme),graupel(ims:ime,jms:jme),graupelncv(ims:ime,jms:jme))
  allocate(refl(ims:ime,kms:kme,jms:jme),re_cloud(ims:ime,kms:kme,jms:jme),re_ice(ims:ime,kms:kme,jms:jme),re_snow(ims:ime,kms:kme,jms:jme))
  rain=0.;rainncv=0.;snow=0.;snowncv=0.;sr=0.;graupel=0.;graupelncv=0.
  refl=-777.;re_cloud=-777.;re_ice=-777.;re_snow=-777.
  ! Retain the receipt-bound complete active T1 tile; no spatial narrowing.
  call kdm6init(rhoair0,rhowater,rhosnow,cliq,cpv,ccn,0,.true.)
  call kdm6(th=th,q=q,qc=qc,qr=qr,qi=qi,qs=qs,qg=qg,nn=nn,nc=nc,ni=ni,nr=nr,bg=bg,diag_rhog=diag_rhog, &
    den=den,pii=pii,p=p,delz=delz,delt=dt,g=g,cpd=cp,cpv=cpv,ccn0=ccn,rd=r_d,rv=r_v,t0c=svpt0, &
    ep1=ep_1,ep2=ep_2,qmin=epsilon,xls=xls,xlv0=xlv,xlf0=xlf,den0=rhoair0,denr=rhowater,scale_h=scale_h, &
    qnn_land_mult=land_mult,qnn_sea_mult=sea_mult,ncmin_land=10.,ncmin_sea=10.,cliq=cliq,cice=cice,psat=psat, &
    xland=xland,rain=rain,rainncv=rainncv,snow=snow,snowncv=snowncv,sr=sr,refl_10cm=refl,diagflag=.true., &
    do_radar_ref=1,graupel=graupel,graupelncv=graupelncv,itimestep=timestep,has_reqc=1,has_reqi=1,has_reqs=1, &
    re_cloud=re_cloud,re_ice=re_ice,re_snow=re_snow,ids=ids,ide=ide,jds=jds,jde=jde,kds=kds,kde=kde, &
    ims=ims,ime=ime,jms=jms,jme=jme,kms=kms,kme=kme,its=its,ite=ite,jts=jts,jte=jte,kts=kts,kte=kte)
  open(newunit=u,file='replay_post.raw',access='stream',form='unformatted',status='replace',convert='big_endian')
  write(u) 'KDM6TRC1'
  write(u) 2,timestep,ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte
  write(u) params
  do n=1,17
    write(u) expected(n)
    write(u) state(:,:,:,n)
  enddo
  write(u) 'XLAND   ';write(u)xland
  close(u)
  write(*,'(A,6I8)') 'REPLAY COMPLETED FULL ACTIVE TILE',its,ite,jts,jte,kts,kte
end program
