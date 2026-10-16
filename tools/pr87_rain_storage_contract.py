"""Connect completed rain stores to the selected KDM6 consumer's exact domain."""
from __future__ import annotations

import hashlib

V10_FRAGMENT_SHA256 = 'b0a467b8f96728cb0b98cae014edb78df68edc995d5bab40138e8ef405651bf4'


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f'expected one rain-storage anchor: {old[:80]}')
    return source.replace(old, new, 1)


def extend_native_update(source: str) -> str:
    if hashlib.sha256(source.encode()).hexdigest() != V10_FRAGMENT_SHA256:
        raise ValueError('native rain-storage fragment preimage differs from frozen V10')
    source = replace_once(source,
        '  REAL(real32),ALLOCATABLE :: oldcarrier(:),newcarrier(:),drydensity(:)\n',
        '  REAL(real32),ALLOCATABLE :: oldcarrier(:),newcarrier(:),drydensity(:)\n'
        '  REAL(real64),ALLOCATABLE :: rain_bounds(:,:)\n'
        '  ! Default-REAL coefficients of the hash-bound selected KDM6 source.\n'
        '  REAL(real32),PARAMETER :: rain_pidn=12566.37109375_real32,rain_power=3.0_real32\n'
        '  REAL(real32),PARAMETER :: rain_lambda_min=961.0_real32,rain_lambda_max=35000.0_real32\n')
    source = replace_once(source,
        '           2.930931921716425e-10_real64,100.0_real64]',
        '           REAL(rain_pidn,real64)/REAL(rain_lambda_max,real64)**REAL(rain_power,real64),100.0_real64]')
    source = replace_once(source,
        '           1.4159232106169906e-5_real64,900.0_real64]',
        '           REAL(rain_pidn,real64)/REAL(rain_lambda_min,real64)**REAL(rain_power,real64),900.0_real64]')
    source = replace_once(source,
        '  ALLOCATE(qs64(cells,4),ns64(cells,4),qa64(cells,4),na64(cells,4))\n',
        '  ALLOCATE(qs64(cells,4),ns64(cells,4),qa64(cells,4),na64(cells,4),rain_bounds(cells,2))\n')
    source = replace_once(source,
        '      qa(cell,p)=REAL(rate(1),real32); na(cell,p)=REAL(rate(2),real32)\n',
        '      ! Keep the shared-face proposal in its calculation precision.\n'
        '      ! The REAL32 arrays remain diagnostic/API arguments only.\n'
        '      IF (.NOT.ALL(ieee_is_finite(rate))) &\n'
        "        CALL wrf_error_fatal('PR87 nonfinite joint air rate')\n"
        '      IF (ANY(ABS(rate)>REAL(HUGE(0.0_real32),real64))) &\n'
        "        CALL wrf_error_fatal('PR87 joint air diagnostic rate overflow')\n"
        '      qa(cell,p)=REAL(rate(1),real32); na(cell,p)=REAL(rate(2),real32)\n')
    source = replace_once(source,
        '      qa64(cell,p)=REAL(qa(cell,p),real64); na64(cell,p)=REAL(na(cell,p),real64)\n',
        '      qa64(cell,p)=rate(1); na64(cell,p)=rate(2)\n')
    anchor='    IF (.NOT.density_valid) CALL wrf_error_fatal(\'PR85 invalid AL+ALB dry density\')\n'
    source = replace_once(source,anchor,anchor+
        '    rain_bounds(cell,1)=REAL(drydensity(cell),real64)* &\n'
        '        REAL(rain_lambda_min,real64)**REAL(rain_power,real64)/REAL(rain_pidn,real64)\n'
        '    rain_bounds(cell,2)=REAL(drydensity(cell),real64)* &\n'
        '        REAL(rain_lambda_max,real64)**REAL(rain_power,real64)/REAL(rain_pidn,real64)\n')
    source = replace_once(source,
        'q_transport_rate64=qa64,n_transport_rate64=na64,joint_quantum_absence=.TRUE.)',
        'q_transport_rate64=qa64,n_transport_rate64=na64,joint_quantum_absence=.TRUE., &\n'
        '                         strict_number_pair=3,volume_number_bounds=rain_bounds)')
    # Classify a rejected pair with the exact same predicate as the commit.
    anchor=('        CALL joint_moment_store(value(1),value(2),drydensity(c),minmass(pair),maxmass(pair), &\n'
        '             .TRUE.,stored(1),stored(2),local_adjustment,local_valid, &\n'
        '             allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE.)\n')
    source = replace_once(source,anchor,
        '        IF (pair==3) THEN\n'+anchor.replace('allow_joint_quantum_absence=.TRUE.)',
            'allow_joint_quantum_absence=.TRUE., &\n             volume_number_bounds=rain_bounds(c,:))')+
        '        ELSE\n'+anchor+'        END IF\n')
    # The full-failure diagnostic must not silently use the old 8-ULP-only store.
    anchor=('        CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &\n'
        '             minmass(p),maxmass(p),.TRUE.,full_stored(1),full_stored(2),adjustment,full_valid, &\n'
        '             allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE.)\n')
    source = replace_once(source,anchor,
        '        IF (p==3) THEN\n'+anchor.replace('allow_joint_quantum_absence=.TRUE.)',
            'allow_joint_quantum_absence=.TRUE., &\n             volume_number_bounds=rain_bounds(cell,:))')+
        '        ELSE\n'+anchor+'        END IF\n')
    return source


def extend_kdm6_public_return(source: str) -> str:
    source = replace_once(source,'   real :: number_value\n',
        '   real :: number_value\n'
        '   real :: pr87_rain_q_public,pr87_rain_n_public\n'
        '   double precision :: pr87_rain_store_dq,pr87_rain_store_dn,pr87_rain_roundtrip_dn\n'
        '   integer :: pr87_rain_store_adjustment,pr87_rain_store_unit,pr87_rain_store_ios\n'
        '   external :: pr87_rain_public_store\n')
    anchor='     do k = kts,kte\n       do i = its,ite\n         th(i,k,j) = t(i,k)/pii(i,k,j)\n'
    source = replace_once(source,anchor,
        "     open(newunit=pr87_rain_store_unit,file='pr87_rain_public_store.raw', &\n"
        "          status='unknown',position='append',action='write',iostat=pr87_rain_store_ios)\n"
        "     if (pr87_rain_store_ios/=0) error stop 'PR87 rain public-store ledger open failed'\n"+
        anchor)
    anchor=("         if (.not. number_valid) error stop 'KDM6 invalid NR number basis output'\n")
    source=replace_once(source,anchor,anchor+
        '         ! Quantize the completed pair, before its first public host store.\n'
        '         call pr87_rain_public_store(qrs(i,k,1),nrs(i,k,1),dry_density(i,k), &\n'
        '              pidnr,dmr,lamdarmin,lamdarmax,pr87_rain_q_public,pr87_rain_n_public, &\n'
        '              number_valid,pr87_rain_store_dq,pr87_rain_store_dn,pr87_rain_store_adjustment)\n'
        '         if (.not.number_valid) then\n'
        "           write(*,*) 'PR87_RAIN_PUBLIC_STORE_REJECT',itimestep,j,i,k, &\n"
        '                qrs(i,k,1),nrs(i,k,1),dry_density(i,k)\n'
        '           flush(6)\n'
        "           error stop 'PR87 invalid continuous or unrepresentable rain public pair'\n"
        '         endif\n'
        '         pr87_rain_roundtrip_dn=DBLE(pr87_rain_n_public*dry_density(i,k))-DBLE(nrs(i,k,1))\n'
        '         if (pr87_rain_store_adjustment/=0.or.pr87_rain_n_public/=number_value) then\n'
        "           write(pr87_rain_store_unit,'(a,5i10,1p,10es25.16)',iostat=pr87_rain_store_ios) &\n"
        "                'PR87_RAIN_PUBLIC_STORE',itimestep,j,i,k,pr87_rain_store_adjustment, &\n"
        '                DBLE(qrs(i,k,1)),DBLE(nrs(i,k,1)),DBLE(number_value), &\n'
        '                DBLE(pr87_rain_q_public),DBLE(pr87_rain_n_public), &\n'
        '                DBLE(dry_density(i,k)),DBLE(delz(i,k,j)),pr87_rain_store_dq, &\n'
        '                pr87_rain_store_dn,pr87_rain_roundtrip_dn\n'
        "           if (pr87_rain_store_ios/=0) error stop 'PR87 rain public-store ledger write failed'\n"
        '         endif\n'
        '         qr(i,k,j)=pr87_rain_q_public\n'
        '         number_value=pr87_rain_n_public\n')
    # Pin the source constants shared with the native grouped producer. No
    # analytic double-precision PI coefficient is substituted for default REAL.
    anchor='   real :: number_value\n'
    # Assertion belongs after declarations, immediately before wrapper execution.
    first='   pr67_trace_this_call = .not. pr67_trace_complete\n'
    if first in source:
        source=replace_once(source,first,
            '   if (pidnr/=12566.37109375.or.dmr/=3.0.or. &\n'
            '       lamdarmin/=961.0.or.lamdarmax/=35000.0) &\n'
            "     error stop 'PR87 grouped/native rain coefficient identity mismatch'\n"+first)
    else:
        raise ValueError('KDM6 wrapper execution anchor missing')
    anchor='     if ( present (diagflag) ) then\n'
    source=replace_once(source,anchor,'     close(pr87_rain_store_unit)\n\n'+anchor)
    return source
