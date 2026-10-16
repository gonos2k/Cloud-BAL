SUBROUTINE pr85_kdm6_paired_sediment_column(kts,kte,cell_i,lat,substep,dt,mstep, &
dry_density,delz,mass_rate,second_rate,qstate,second_state,mode,q_active_min, &
second_active_min,density_min,density_max,approved_q_rate,approved_second_rate, &
budget_unit,trace,valid,rain_pidn,rain_power,rain_lambda_min,rain_lambda_max)
USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
IMPLICIT NONE
INTEGER, INTENT(IN) :: kts,kte,cell_i,lat,substep,mstep,budget_unit
INTEGER, PARAMETER :: PR85_SED_ICE=1, PR85_SED_GRAUPEL=2, PR87_SED_RAIN=3
REAL(real32), INTENT(IN) :: dt,dry_density(kts:kte),delz(kts:kte)
REAL(real64), INTENT(IN) :: mass_rate(kts:kte),second_rate(kts:kte)
REAL(real32), INTENT(INOUT) :: qstate(kts:kte),second_state(kts:kte)
INTEGER, INTENT(IN) :: mode
REAL(real32), INTENT(IN) :: q_active_min,second_active_min,density_min,density_max
REAL(real64), INTENT(OUT) :: approved_q_rate(kts:kte),approved_second_rate(kts:kte)
LOGICAL, INTENT(IN) :: trace
LOGICAL, INTENT(OUT) :: valid
REAL(real32), INTENT(IN) :: rain_pidn,rain_power,rain_lambda_min,rain_lambda_max

REAL(real32) :: qwork(kts:kte),nwork(kts:kte),second_carrier(kts:kte)
REAL(real32) :: qd_store,nd_store,qr_store,nr_store
REAL(real64) :: qproposal(kts:kte),nproposal(kts:kte)
REAL(real64) :: rain_n_min(kts:kte),rain_n_max(kts:kte)
REAL(real64) :: theta,dt64
REAL(real64) :: proposed_q_sum,proposed_n_sum,approved_q_sum,approved_n_sum
REAL(real64) :: ground_q,ground_n,ground_approved_q,ground_approved_n
REAL(real64) :: stored_delta_q,stored_delta_n,residual_q,residual_n
REAL(real64) :: qd_inventory,nd_inventory
INTEGER :: k,iteration,io_status,nlevels
LOGICAL :: candidate_valid,full_empty_unpaired

valid=.FALSE.
approved_q_rate=0.0_real64
approved_second_rate=0.0_real64
IF (mode/=PR85_SED_ICE .AND. mode/=PR85_SED_GRAUPEL .AND. mode/=PR87_SED_RAIN) RETURN
IF (mode==PR85_SED_GRAUPEL) THEN
  IF (.NOT.ALL(ieee_is_finite([q_active_min,second_active_min,density_min,density_max]))) RETURN
  IF (q_active_min<0.0_real32 .OR. second_active_min<0.0_real32 .OR. &
      density_min<=0.0_real32 .OR. density_max<=density_min) RETURN
ENDIF
IF (mode==PR87_SED_RAIN) THEN
  IF (.NOT.ALL(ieee_is_finite([rain_pidn,rain_power,rain_lambda_min,rain_lambda_max]))) RETURN
  IF (rain_pidn<=0.0_real32 .OR. rain_power<=0.0_real32 .OR. rain_power>8.0_real32 .OR. &
      rain_lambda_min<=0.0_real32 .OR. rain_lambda_max<rain_lambda_min) RETURN
  ! Match NG's d<=8 domain and keep both lambda**d powers in normal R32 range.
  IF (REAL(rain_power,real64)*LOG(REAL(rain_lambda_min,real64))< &
      LOG(REAL(TINY(0.0_real32),real64)) .OR. &
      REAL(rain_power,real64)*LOG(REAL(rain_lambda_max,real64))> &
      LOG(REAL(HUGE(0.0_real32),real64)) ) RETURN
ENDIF
IF (kts>kte .OR. mstep<1 .OR. .NOT.ieee_is_finite(dt) .OR. dt<=0.0_real32) RETURN
nlevels=kte-kts+1
dt64=REAL(dt,real64)
IF (.NOT.ALL(ieee_is_finite(dry_density)) .OR. .NOT.ALL(ieee_is_finite(delz)) .OR. &
.NOT.ALL(ieee_is_finite(mass_rate)) .OR. .NOT.ALL(ieee_is_finite(second_rate)) .OR. &
.NOT.ALL(ieee_is_finite(qstate)) .OR. .NOT.ALL(ieee_is_finite(second_state))) RETURN
IF (ANY(dry_density<=0.0_real32) .OR. ANY(delz<=0.0_real32) .OR. &
ANY(mass_rate<0.0_real64) .OR. ANY(second_rate<0.0_real64)) RETURN
DO k=kts,kte
  second_carrier(k)=1.0_real32
  IF (mode==PR85_SED_GRAUPEL) second_carrier(k)=dry_density(k)
  IF (.NOT.ieee_is_finite(second_carrier(k)) .OR. second_carrier(k)<=0.0_real32) RETURN
  IF (mode==PR87_SED_RAIN) THEN
    rain_n_min(k)=REAL(dry_density(k),real64)* &
         REAL(rain_lambda_min,real64)**REAL(rain_power,real64)/REAL(rain_pidn,real64)
    rain_n_max(k)=REAL(dry_density(k),real64)* &
         REAL(rain_lambda_max,real64)**REAL(rain_power,real64)/REAL(rain_pidn,real64)
    IF (.NOT.ALL(ieee_is_finite([rain_n_min(k),rain_n_max(k)])) .OR. &
        rain_n_min(k)<=0.0_real64 .OR. &
        rain_n_max(k)<rain_n_min(k) .OR. &
        rain_n_max(k)>REAL(HUGE(0.0_real32),real64)) RETURN
    IF (.NOT.rain_state_valid32(qstate(k),second_state(k),rain_n_min(k),rain_n_max(k))) RETURN
  ELSE IF (mode==PR85_SED_GRAUPEL) THEN
    IF (.NOT.graupel_state_valid(qstate(k),second_state(k),q_active_min, &
         second_active_min,density_min,density_max)) RETURN
  ELSE
    IF (.NOT.paired(qstate(k),second_state(k))) RETURN
  ENDIF
ENDDO

qwork=qstate
nwork=second_state
proposed_q_sum=0.0_real64
proposed_n_sum=0.0_real64
approved_q_sum=0.0_real64
approved_n_sum=0.0_real64
ground_q=0.0_real64
ground_n=0.0_real64
ground_approved_q=0.0_real64
ground_approved_n=0.0_real64
qproposal=0.0_real64
nproposal=0.0_real64
! The source passes V/DELZ rates (s-1); multiplying by DELZ below forms
! column packets in kg m-2 and mode-specific second-moment area units.
DO k=kts,kte
qproposal(k)=REAL(dry_density(k),real64)*REAL(qstate(k),real64)*mass_rate(k)* &
REAL(delz(k),real64)*dt64/REAL(mstep,real64)
nproposal(k)=REAL(second_state(k),real64)*second_rate(k)* &
REAL(second_carrier(k),real64)*REAL(delz(k),real64)*dt64/REAL(mstep,real64)
IF (.NOT.ieee_is_finite(qproposal(k)) .OR. .NOT.ieee_is_finite(nproposal(k)) .OR. &
qproposal(k)<0.0_real64 .OR. nproposal(k)<0.0_real64) RETURN
proposed_q_sum=proposed_q_sum+qproposal(k)
proposed_n_sum=proposed_n_sum+nproposal(k)
ENDDO

! Flux proposals are frozen from each level's current R32 state. G faces
! follow the native top-down sweep; ice retains its established bottom-up order.
IF (mode==PR85_SED_GRAUPEL .OR. mode==PR87_SED_RAIN) THEN
  DO k=kte-1,kts,-1
    CALL commit_face(k+1,k,.TRUE.)
    IF (.NOT.candidate_valid) RETURN
  ENDDO
  CALL commit_face(kts,0,.FALSE.)
  IF (.NOT.candidate_valid) RETURN
ELSE
  CALL commit_face(kts,0,.FALSE.)
  IF (.NOT.candidate_valid) RETURN
  DO k=kts,kte-1
    CALL commit_face(k+1,k,.TRUE.)
    IF (.NOT.candidate_valid) RETURN
  ENDDO
ENDIF

stored_delta_q=0.0_real64
stored_delta_n=0.0_real64
DO k=kts,kte
qd_inventory=REAL(dry_density(k),real64)*REAL(delz(k),real64)
nd_inventory=REAL(second_carrier(k),real64)*REAL(delz(k),real64)
stored_delta_q=stored_delta_q+(REAL(qwork(k),real64)-REAL(qstate(k),real64))*qd_inventory
stored_delta_n=stored_delta_n+(REAL(nwork(k),real64)-REAL(second_state(k),real64))*nd_inventory
ENDDO
residual_q=stored_delta_q+ground_approved_q
residual_n=stored_delta_n+ground_approved_n
IF (.NOT.ALL(ieee_is_finite([stored_delta_q,stored_delta_n,residual_q,residual_n]))) RETURN

IF (trace) THEN
IF (mode==PR85_SED_GRAUPEL) THEN
  WRITE(budget_unit,'(a,4i8,1p,12es24.16)',IOSTAT=io_status) &
  'PR85_G_SED',cell_i,lat,substep,nlevels,proposed_q_sum,approved_q_sum, &
  proposed_q_sum-approved_q_sum,proposed_n_sum,approved_n_sum, &
  proposed_n_sum-approved_n_sum,ground_approved_q,ground_approved_n,stored_delta_q,stored_delta_n, &
  residual_q,residual_n
ELSE IF (mode==PR87_SED_RAIN) THEN
  WRITE(budget_unit,'(a,4i8,1p,12es24.16)',IOSTAT=io_status) &
  'PR87_RAIN_SED',cell_i,lat,substep,nlevels,proposed_q_sum,approved_q_sum, &
  proposed_q_sum-approved_q_sum,proposed_n_sum,approved_n_sum, &
  proposed_n_sum-approved_n_sum,ground_approved_q,ground_approved_n,stored_delta_q,stored_delta_n, &
  residual_q,residual_n
  IF (io_status/=0) ERROR STOP 'PR87 paired rain sedimentation ledger write failed'
ELSE
WRITE(budget_unit,'(a,4i8,1p,12es24.16)',IOSTAT=io_status) &
'PR85_ICE_SED',cell_i,lat,substep,nlevels,proposed_q_sum,approved_q_sum, &
proposed_q_sum-approved_q_sum,proposed_n_sum,approved_n_sum, &
proposed_n_sum-approved_n_sum,ground_approved_q,ground_approved_n,stored_delta_q,stored_delta_n, &
residual_q,residual_n
ENDIF
IF (io_status/=0) ERROR STOP 'PR85 paired sedimentation ledger write failed'
ENDIF
qstate=qwork
second_state=nwork
valid=.TRUE.

CONTAINS

PURE LOGICAL FUNCTION paired(q,n)
REAL(real32), INTENT(IN) :: q,n
paired=.FALSE.
IF (.NOT.ieee_is_finite(q) .OR. .NOT.ieee_is_finite(n)) RETURN
IF (q<0.0_real32 .OR. n<0.0_real32) RETURN
paired=(q==0.0_real32 .AND. n==0.0_real32) .OR. &
(q>0.0_real32 .AND. n>0.0_real32)
END FUNCTION paired

PURE LOGICAL FUNCTION graupel_state_valid(q,b,qmin,bmin,rhomin,rhomax)
REAL(real32), INTENT(IN) :: q,b,qmin,bmin,rhomin,rhomax
REAL(real64) :: density
graupel_state_valid=.FALSE.
IF (.NOT.ieee_is_finite(q) .OR. .NOT.ieee_is_finite(b)) RETURN
IF (q<0.0_real32 .OR. b<0.0_real32) RETURN
IF (q==0.0_real32 .AND. b==0.0_real32) THEN
  graupel_state_valid=.TRUE.; RETURN
ENDIF
IF (q<=0.0_real32 .OR. b<=0.0_real32) RETURN
IF (q<=qmin .AND. b<=bmin) RETURN
density=REAL(q,real64)/REAL(b,real64)
graupel_state_valid=ieee_is_finite(density) .AND. &
  density>=REAL(rhomin,real64) .AND. density<=REAL(rhomax,real64)
END FUNCTION graupel_state_valid

PURE LOGICAL FUNCTION rain_state_valid32(q,n,n_min,n_max)
REAL(real32), INTENT(IN) :: q,n
REAL(real64), INTENT(IN) :: n_min,n_max
rain_state_valid32=.FALSE.
IF (.NOT.ieee_is_finite(q) .OR. .NOT.ieee_is_finite(n) .OR. &
    .NOT.ALL(ieee_is_finite([n_min,n_max]))) RETURN
IF (q<0.0_real32 .OR. n<0.0_real32 .OR. n_min<=0.0_real64 .OR. n_max<n_min) RETURN
IF (.NOT.paired(q,n)) RETURN
IF (q==0.0_real32 .AND. n==0.0_real32) THEN
  rain_state_valid32=.TRUE.; RETURN
ENDIF
  ! NG admission uses these strict R64 count bounds; do not add a storage tolerance.
  rain_state_valid32=REAL(n,real64)>=n_min*REAL(q,real64) .AND. &
  REAL(n,real64)<=n_max*REAL(q,real64)
END FUNCTION rain_state_valid32

PURE LOGICAL FUNCTION rain_state_valid64(q,n,n_min,n_max)
REAL(real64), INTENT(IN) :: q,n,n_min,n_max
rain_state_valid64=.FALSE.
IF (.NOT.ALL(ieee_is_finite([q,n,n_min,n_max]))) RETURN
IF (q<0.0_real64 .OR. n<0.0_real64 .OR. n_min<=0.0_real64 .OR. n_max<n_min) RETURN
IF ((q==0.0_real64) .NEQV. (n==0.0_real64)) RETURN
IF (q==0.0_real64 .AND. n==0.0_real64) THEN
  rain_state_valid64=.TRUE.; RETURN
ENDIF
rain_state_valid64=n>=n_min*q .AND. n<=n_max*q
END FUNCTION rain_state_valid64

SUBROUTINE add_partition_point(points,count,base,change,target)
REAL(real64), INTENT(INOUT) :: points(16)
INTEGER, INTENT(INOUT) :: count
REAL(real64), INTENT(IN) :: base,change,target
REAL(real64) :: root
IF (.NOT.ieee_is_finite(base) .OR. .NOT.ieee_is_finite(change) .OR. &
    .NOT.ieee_is_finite(target) .OR. change==0.0_real64) RETURN
root=(target-base)/change
IF (.NOT.ieee_is_finite(root) .OR. root<=0.0_real64 .OR. root>=1.0_real64) RETURN
IF (count>=SIZE(points)) RETURN
count=count+1
points(count)=root
END SUBROUTINE add_partition_point

SUBROUTINE search_graupel_partitions(donor,receiver,pq,pn,has_receiver,factor,qd,nd,qr,nr,ok)
INTEGER, INTENT(IN) :: donor,receiver
REAL(real64), INTENT(IN) :: pq,pn
LOGICAL, INTENT(IN) :: has_receiver
REAL(real64), INTENT(OUT) :: factor
REAL(real32), INTENT(OUT) :: qd,nd,qr,nr
LOGICAL, INTENT(OUT) :: ok
REAL(real64) :: points(16),qchange(2),bchange(2),qbase(2),bbase(2)
REAL(real64) :: qden,bden,left,right,trials(3),trial
REAL(real32) :: qt,nt,rt,st
INTEGER :: count,endpoint,index,j
LOGICAL :: trial_ok,unpaired
points=0.0_real64; count=2; points(1)=0.0_real64; points(2)=1.0_real64
qden=REAL(dry_density(donor),real64)*REAL(delz(donor),real64)
bden=REAL(second_carrier(donor),real64)*REAL(delz(donor),real64)
CALL safe_ratio(pq,qden,qchange(1),trial_ok)
IF (.NOT.trial_ok) THEN
  factor=0.0_real64; qd=qwork(donor); nd=nwork(donor); qr=0.; nr=0.; ok=.FALSE.; RETURN
ENDIF
CALL safe_ratio(pn,bden,bchange(1),trial_ok)
IF (.NOT.trial_ok) THEN
  factor=0.0_real64; qd=qwork(donor); nd=nwork(donor); qr=0.; nr=0.; ok=.FALSE.; RETURN
ENDIF
qbase(1)=REAL(qwork(donor),real64); bbase(1)=REAL(nwork(donor),real64)
IF (has_receiver) THEN
  qden=REAL(dry_density(receiver),real64)*REAL(delz(receiver),real64)
  bden=REAL(second_carrier(receiver),real64)*REAL(delz(receiver),real64)
  CALL safe_ratio(pq,qden,qchange(2),trial_ok)
  IF (.NOT.trial_ok) THEN
    factor=0.0_real64; qd=qwork(donor); nd=nwork(donor); qr=qwork(receiver); nr=nwork(receiver); ok=.FALSE.; RETURN
  ENDIF
  CALL safe_ratio(pn,bden,bchange(2),trial_ok)
  IF (.NOT.trial_ok) THEN
    factor=0.0_real64; qd=qwork(donor); nd=nwork(donor); qr=qwork(receiver); nr=nwork(receiver); ok=.FALSE.; RETURN
  ENDIF
  qbase(2)=REAL(qwork(receiver),real64); bbase(2)=REAL(nwork(receiver),real64)
ENDIF
DO endpoint=1,1+MERGE(1,0,has_receiver)
  IF (endpoint==1) THEN
    qchange(endpoint)=-qchange(endpoint); bchange(endpoint)=-bchange(endpoint)
  ENDIF
  CALL add_partition_point(points,count,qbase(endpoint),qchange(endpoint),REAL(q_active_min,real64))
  CALL add_partition_point(points,count,bbase(endpoint),bchange(endpoint),REAL(second_active_min,real64))
  CALL add_partition_point(points,count,qbase(endpoint)-REAL(density_min,real64)*bbase(endpoint), &
       qchange(endpoint)-REAL(density_min,real64)*bchange(endpoint),0.0_real64)
  CALL add_partition_point(points,count,qbase(endpoint)-REAL(density_max,real64)*bbase(endpoint), &
       qchange(endpoint)-REAL(density_max,real64)*bchange(endpoint),0.0_real64)
  IF (endpoint==1) THEN
    qchange(endpoint)=-qchange(endpoint); bchange(endpoint)=-bchange(endpoint)
  ENDIF
ENDDO
DO index=2,count
  trial=points(index); j=index-1
  DO WHILE (j>=1)
    IF (points(j)<=trial) EXIT
    points(j+1)=points(j); j=j-1
  ENDDO
  points(j+1)=trial
ENDDO
DO index=count-1,1,-1
  left=points(index); right=points(index+1)
  IF (right<=left) CYCLE
  trials(1)=0.75_real64*left+0.25_real64*right
  trials(2)=0.5_real64*(left+right)
  trials(3)=0.25_real64*left+0.75_real64*right
  DO j=1,3
    trial=trials(j)
    IF (trial<=0.0_real64 .OR. trial>=1.0_real64) CYCLE
    CALL candidate(donor,receiver,pq,pn,trial,has_receiver,qt,nt,rt,st,trial_ok,unpaired)
    IF (trial_ok) THEN
      factor=trial; qd=qt; nd=nt; qr=rt; nr=st; ok=.TRUE.; RETURN
    ENDIF
  ENDDO
ENDDO
CALL candidate(donor,receiver,pq,pn,0.0_real64,has_receiver,qd,nd,qr,nr,ok,unpaired)
IF (ok) factor=0.0_real64
END SUBROUTINE search_graupel_partitions

SUBROUTINE commit_face(donor,receiver,has_receiver)
INTEGER, INTENT(IN) :: donor,receiver
LOGICAL, INTENT(IN) :: has_receiver
REAL(real64) :: pq,pn,theta_local
REAL(real32) :: qd,nd,qr,nr
LOGICAL :: accepted,unpaired
pq=qproposal(donor); pn=nproposal(donor)
CALL approve_packet(donor,receiver,pq,pn,has_receiver,theta_local,qd,nd,qr,nr,accepted,unpaired)
IF (.NOT.accepted .AND. mode==PR85_SED_GRAUPEL) THEN
  CALL search_graupel_partitions(donor,receiver,pq,pn,has_receiver,theta_local,qd,nd,qr,nr,accepted)
ELSE IF (.NOT.accepted .AND. unpaired) THEN
  theta_local=0.0_real64; accepted=.TRUE.
  qd=qwork(donor); nd=nwork(donor); qr=0.; nr=0.
  IF (has_receiver) THEN
    qr=qwork(receiver); nr=nwork(receiver)
  ENDIF
ELSE IF (.NOT.accepted) THEN
  CALL backtrack_packet(donor,receiver,pq,pn,has_receiver,theta_local,qd,nd,qr,nr,accepted)
ENDIF
candidate_valid=accepted
IF (.NOT.accepted) RETURN
qwork(donor)=qd; nwork(donor)=nd
approved_q_sum=approved_q_sum+theta_local*pq
approved_n_sum=approved_n_sum+theta_local*pn
approved_q_rate(donor)=theta_local*pq/(dt64*REAL(delz(donor),real64))
approved_second_rate(donor)=theta_local*pn/(dt64*REAL(delz(donor),real64))
IF (has_receiver) THEN
  qwork(receiver)=qr; nwork(receiver)=nr
ELSE
  ground_approved_q=ground_approved_q+theta_local*pq
  ground_approved_n=ground_approved_n+theta_local*pn
ENDIF
END SUBROUTINE commit_face

SUBROUTINE candidate(donor,receiver,pq,pn,factor,has_receiver,qd,nd,qr,nr,ok,empty_receiver_unpaired)
INTEGER, INTENT(IN) :: donor,receiver
REAL(real64), INTENT(IN) :: pq,pn,factor
LOGICAL, INTENT(IN) :: has_receiver
REAL(real32), INTENT(OUT) :: qd,nd,qr,nr
LOGICAL, INTENT(OUT) :: ok,empty_receiver_unpaired
REAL(real64) :: qden,nden,qd64,nd64,qr64,nr64,qchange,nchange,r32max
REAL(real64) :: donor_q_den,donor_n_den,receiver_q_den,receiver_n_den
REAL(real64) :: packet_q,packet_n,donor_q_loss,donor_n_loss,receiver_q_gain,receiver_n_gain
REAL(real64) :: donor_q_tol,donor_n_tol,receiver_q_tol,receiver_n_tol
LOGICAL :: ratio_valid
qd=qwork(donor); nd=nwork(donor)
qr=0.0_real32; nr=0.0_real32
IF (has_receiver) THEN
  qr=qwork(receiver); nr=nwork(receiver)
ENDIF
ok=.FALSE.; empty_receiver_unpaired=.FALSE.
r32max=REAL(HUGE(0.0_real32),real64)
qden=REAL(dry_density(donor),real64)*REAL(delz(donor),real64)
nden=REAL(second_carrier(donor),real64)*REAL(delz(donor),real64)
donor_q_den=qden; donor_n_den=nden
CALL safe_ratio(factor*pq,qden,qchange,ratio_valid)
IF (.NOT.ratio_valid) RETURN
CALL safe_ratio(factor*pn,nden,nchange,ratio_valid)
IF (.NOT.ratio_valid) RETURN
qd64=REAL(qwork(donor),real64)-qchange
nd64=REAL(nwork(donor),real64)-nchange
IF (.NOT.ieee_is_finite(qd64) .OR. .NOT.ieee_is_finite(nd64)) RETURN
IF (qd64<0.0_real64 .OR. nd64<0.0_real64) RETURN
IF (ABS(qd64)>r32max .OR. ABS(nd64)>r32max) RETURN
IF (has_receiver) THEN
qden=REAL(dry_density(receiver),real64)*REAL(delz(receiver),real64)
nden=REAL(second_carrier(receiver),real64)*REAL(delz(receiver),real64)
  receiver_q_den=qden; receiver_n_den=nden
  CALL safe_ratio(factor*pq,qden,qchange,ratio_valid)
  IF (.NOT.ratio_valid) RETURN
  CALL safe_ratio(factor*pn,nden,nchange,ratio_valid)
  IF (.NOT.ratio_valid) RETURN
  IF (qchange>HUGE(0.0_real64)-REAL(qwork(receiver),real64) .OR. &
      nchange>HUGE(0.0_real64)-REAL(nwork(receiver),real64)) RETURN
  qr64=REAL(qwork(receiver),real64)+qchange
  nr64=REAL(nwork(receiver),real64)+nchange
  IF (.NOT.ieee_is_finite(qr64) .OR. .NOT.ieee_is_finite(nr64)) RETURN
  IF (ABS(qr64)>r32max .OR. ABS(nr64)>r32max) RETURN
ENDIF
qd=REAL(qd64,real32); nd=REAL(nd64,real32)
IF (has_receiver) THEN
  qr=REAL(qr64,real32); nr=REAL(nr64,real32)
  IF (qwork(receiver)==0.0_real32 .AND. nwork(receiver)==0.0_real32) &
    empty_receiver_unpaired=(qr>0.0_real32 .NEQV. nr>0.0_real32)
ENDIF
IF (mode==PR85_SED_GRAUPEL) THEN
  IF (.NOT.graupel_state_valid(qd,nd,q_active_min,second_active_min,density_min,density_max)) RETURN
  IF (has_receiver) THEN
    IF (.NOT.graupel_state_valid(qr,nr,q_active_min,second_active_min,density_min,density_max)) RETURN
  ENDIF
ELSE IF (mode==PR87_SED_RAIN) THEN
  IF (.NOT.rain_state_valid64(qd64,nd64,rain_n_min(donor),rain_n_max(donor))) RETURN
  IF (has_receiver) THEN
    IF (.NOT.rain_state_valid64(qr64,nr64,rain_n_min(receiver),rain_n_max(receiver))) RETURN
  ENDIF
  IF (.NOT.rain_state_valid32(qd,nd,rain_n_min(donor),rain_n_max(donor))) RETURN
  IF (has_receiver) THEN
    IF (.NOT.rain_state_valid32(qr,nr,rain_n_min(receiver),rain_n_max(receiver))) RETURN
  ENDIF
ELSE
  IF (.NOT.paired(qd,nd)) RETURN
  IF (has_receiver) THEN
    IF (.NOT.paired(qr,nr)) RETURN
  ENDIF
ENDIF
IF (factor>0.0_real64 .AND. pq>0.0_real64) THEN
  packet_q=factor*pq
  donor_q_loss=(REAL(qwork(donor),real64)-REAL(qd,real64))*donor_q_den
  donor_q_tol=0.5_real64*REAL(ulp32(qd),real64)*donor_q_den + &
              32.0_real64*EPSILON(1.0_real64)*MAX(packet_q,ABS(donor_q_loss))
  IF (donor_q_loss<=0.0_real64 .OR. ABS(donor_q_loss-packet_q)>donor_q_tol) RETURN
  IF (has_receiver) THEN
    receiver_q_gain=(REAL(qr,real64)-REAL(qwork(receiver),real64))*receiver_q_den
    receiver_q_tol=0.5_real64*REAL(ulp32(qr),real64)*receiver_q_den + &
                   32.0_real64*EPSILON(1.0_real64)*MAX(packet_q,ABS(receiver_q_gain))
    IF (receiver_q_gain<=0.0_real64 .OR. ABS(receiver_q_gain-packet_q)>receiver_q_tol) RETURN
  ENDIF
ENDIF
IF (factor>0.0_real64 .AND. pn>0.0_real64) THEN
  packet_n=factor*pn
  donor_n_loss=(REAL(nwork(donor),real64)-REAL(nd,real64))*donor_n_den
  donor_n_tol=0.5_real64*REAL(ulp32(nd),real64)*donor_n_den + &
              32.0_real64*EPSILON(1.0_real64)*MAX(packet_n,ABS(donor_n_loss))
  IF (donor_n_loss<=0.0_real64 .OR. ABS(donor_n_loss-packet_n)>donor_n_tol) RETURN
  IF (has_receiver) THEN
    receiver_n_gain=(REAL(nr,real64)-REAL(nwork(receiver),real64))*receiver_n_den
    receiver_n_tol=0.5_real64*REAL(ulp32(nr),real64)*receiver_n_den + &
                   32.0_real64*EPSILON(1.0_real64)*MAX(packet_n,ABS(receiver_n_gain))
    IF (receiver_n_gain<=0.0_real64 .OR. ABS(receiver_n_gain-packet_n)>receiver_n_tol) RETURN
  ENDIF
ENDIF
IF (mode==PR85_SED_GRAUPEL) THEN
  ok=graupel_state_valid(qd,nd,q_active_min,second_active_min,density_min,density_max)
  IF (has_receiver) ok=ok .AND. graupel_state_valid(qr,nr,q_active_min, &
       second_active_min,density_min,density_max)
ELSE IF (mode==PR87_SED_RAIN) THEN
  ok=rain_state_valid32(qd,nd,rain_n_min(donor),rain_n_max(donor))
  IF (has_receiver) ok=ok .AND. rain_state_valid32(qr,nr,rain_n_min(receiver),rain_n_max(receiver))
ELSE
  ok=paired(qd,nd)
  IF (has_receiver) ok=ok .AND. paired(qr,nr)
ENDIF
END SUBROUTINE candidate

PURE REAL(real32) FUNCTION ulp32(value)
REAL(real32), INTENT(IN) :: value
REAL(real32) :: above,below,up_gap,down_gap
ulp32=NEAREST(0.0_real32,1.0_real32)
IF (value==HUGE(0.0_real32)) THEN
  below=NEAREST(value,-1.0_real32)
  ulp32=value-below
  RETURN
ENDIF
above=NEAREST(value,1.0_real32)
below=NEAREST(value,-1.0_real32)
up_gap=above-value
down_gap=value-below
ulp32=MAX(up_gap,down_gap)
END FUNCTION ulp32

PURE SUBROUTINE safe_ratio(numerator,denominator,ratio,ok)
REAL(real64), INTENT(IN) :: numerator,denominator
REAL(real64), INTENT(OUT) :: ratio
LOGICAL, INTENT(OUT) :: ok
ratio=0.0_real64; ok=.FALSE.
IF (.NOT.ieee_is_finite(numerator) .OR. .NOT.ieee_is_finite(denominator)) RETURN
IF (numerator<0.0_real64 .OR. denominator<=0.0_real64) RETURN
IF (denominator<1.0_real64) THEN
  IF (numerator>HUGE(0.0_real64)*denominator) RETURN
ENDIF
ratio=numerator/denominator
ok=ieee_is_finite(ratio)
END SUBROUTINE safe_ratio

SUBROUTINE approve_packet(donor,receiver,pq,pn,has_receiver,factor,qd,nd,qr,nr,ok,empty_receiver_unpaired)
INTEGER, INTENT(IN) :: donor,receiver
REAL(real64), INTENT(IN) :: pq,pn
LOGICAL, INTENT(IN) :: has_receiver
REAL(real64), INTENT(OUT) :: factor
REAL(real32), INTENT(OUT) :: qd,nd,qr,nr
LOGICAL, INTENT(OUT) :: ok,empty_receiver_unpaired
factor=1.0_real64
CALL candidate(donor,receiver,pq,pn,factor,has_receiver,qd,nd,qr,nr,ok,empty_receiver_unpaired)
END SUBROUTINE approve_packet

SUBROUTINE backtrack_packet(donor,receiver,pq,pn,has_receiver,factor,qd,nd,qr,nr,ok)
INTEGER, INTENT(IN) :: donor,receiver
REAL(real64), INTENT(IN) :: pq,pn
LOGICAL, INTENT(IN) :: has_receiver
REAL(real64), INTENT(OUT) :: factor
REAL(real32), INTENT(OUT) :: qd,nd,qr,nr
LOGICAL, INTENT(OUT) :: ok
REAL(real64) :: lower,upper,middle
REAL(real32) :: qdt,ndt,qrt,nrt
LOGICAL :: trial_ok,empty_receiver_unpaired
lower=0.0_real64; upper=1.0_real64
qd=qwork(donor); nd=nwork(donor)
qr=0.0_real32; nr=0.0_real32
IF (has_receiver) THEN
qr=qwork(receiver); nr=nwork(receiver)
ENDIF
IF (mode==PR85_SED_GRAUPEL) THEN
  CALL search_graupel_partitions(donor,receiver,pq,pn,has_receiver,factor,qd,nd,qr,nr,ok)
  RETURN
ENDIF
factor=0.0_real64; ok=.TRUE.
DO iteration=1,64
middle=0.5_real64*(lower+upper)
CALL candidate(donor,receiver,pq,pn,middle,has_receiver,qdt,ndt,qrt,nrt, &
trial_ok,empty_receiver_unpaired)
IF (trial_ok) THEN
lower=middle; qd=qdt; nd=ndt; qr=qrt; nr=nrt
ELSE
upper=middle
ENDIF
ENDDO
factor=lower
IF (factor>0.0_real64 .AND. qd==qwork(donor) .AND. nd==nwork(donor)) THEN
IF (.NOT.has_receiver) THEN
factor=0.0_real64
ELSE IF (qr==qwork(receiver) .AND. nr==nwork(receiver)) THEN
factor=0.0_real64
ENDIF
ENDIF
END SUBROUTINE backtrack_packet

END SUBROUTINE pr85_kdm6_paired_sediment_column
