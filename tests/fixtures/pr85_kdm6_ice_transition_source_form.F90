program pr85_ice_transition_regression
  implicit none
  real, parameter :: pidni=1570.79638671875, dmi=3.0, lamdaimin=9.08e3, lamdaimax=1.82e6
  real, parameter :: qmin=1.0e-14
  integer :: failures
  failures=0
  call exercise(9080.0, .true., 'lambda_min')
  call exercise(9085.5, .true., 'inside reachable interval')
  call exercise(9085.61, .false., 'above reachable endpoint')
  if (failures /= 0) error stop 1
  print '(a)', 'PR85 source-form ice transition cases PASS'
contains
  subroutine exercise(lambda_target, should_transfer, label)
    real, intent(in) :: lambda_target
    logical, intent(in) :: should_transfer
    character(len=*), intent(in) :: label
    real :: qci(1,2,2), nci(1,2,2), qrs(1,2,3), rslope(1,2,4), avedia(1,2,3)
    real :: den(1,2), falk(1,2,4), falkn(1,2,2), falln(1,2,2), dend(1,2), delz(1,2)
    real :: dqi(1,2), dni(1,2), dtcld, t(1,2), g4pmi, g1pmi
    real :: qi_before, qs_before, ni_before, diameter_um
    integer :: i,k
    i=1; k=1; dtcld=1.0; qci=0.0; nci=0.0; qrs=0.0
    den=1.0; falk=0.0; falkn=0.0; falln=0.0; dend=1.0; delz=1.0
    t=260.0; g1pmi=1.0; g4pmi=6.0
    qci(i,k,2)=1.0e-3
    nci(i,k,2)=qci(i,k,2)*lambda_target**3/pidni
    qrs(i,k,2)=2.0e-4
    ! Sedimentation is active before the transition: remove 10% of each ice moment.
    falk(i,k,4)=0.1*qci(i,k,2); falkn(i,k,2)=0.1*nci(i,k,2)
    falk(i,k+1,4)=0.0; falkn(i,k+1,2)=0.0
    dqi=0.0; dni=0.0
                 dqi(i,k) = min(falk(i,k,4)*dtcld/dend(i,k),qci(i,k,2))
             dqi(i,k+1) = min(falk(i,k+1,4)*delz(i,k+1)/delz(i,k)              &
                          *dtcld/dend(i,k),qci(i,k+1,2))
             falln(i,k,2) = falln(i,k,2)+falkn(i,k,2)
             dni(i,k) = min(falkn(i,k,2)*dtcld,nci(i,k,2))
             dni(i,k+1) = min(falkn(i,k+1,2)*delz(i,k+1)/delz(i,k)*dtcld,      &
                          nci(i,k+1,2))
             nci(i,k,2) = max(nci(i,k,2)-dni(i,k)+dni(i,k+1),0.)
             qci(i,k,2) = max(qci(i,k,2)-dqi(i,k)+dqi(i,k+1),0.)
    qi_before=qci(i,k,2); qs_before=qrs(i,k,2); ni_before=nci(i,k,2)

    ! slope_kdm6 uses rank-2 QI/NI arrays for this same ice category.
    call source_slope(qci(:,:,2),nci(:,:,2),den,rslope,pidni)
              avedia(i,k,3) = rslope(i,k,4)*((g4pmi/g1pmi)**(.3333333))
    diameter_um=avedia(i,k,3)*1.0e6
            if (qci(i,k,2).ge. qmin .and.t(i,k).lt.273.15) then
        if (avedia(i,k,3).ge. 200.e-6) then
           qrs(i,k,2) = qrs(i,k,2) + qci(i,k,2)
           qci(i,k,2) = 0.
           nci(i,k,2) = 0.
        end if
        end if
    if (abs(qi_before-9.0e-4)>2.0e-7 .or. abs(qs_before-2.0e-4)>1.0e-8 .or. &
        abs(ni_before-0.9*(1.0e-3*lambda_target**3/pidni))>max(1.0e-7,abs(ni_before)*2.0e-6)) then
      print '(a,3(es15.7,1x))', 'FAIL sedimentation before transition: ',qi_before,qs_before,ni_before
      failures=failures+1
    endif
    if (should_transfer) then
      if (diameter_um < 200.0 .or. qci(i,k,2)/=0.0 .or. nci(i,k,2)/=0.0 .or. &
          abs(qrs(i,k,2)-(qs_before+qi_before))>1.0e-8) then
        print '(a,a,a,es15.7)', 'FAIL transfer ',label,' diameter_um=',diameter_um
        failures=failures+1
      endif
    else
      if (diameter_um >= 200.0 .or. qci(i,k,2)/=qi_before .or. nci(i,k,2)/=ni_before .or. &
          qrs(i,k,2)/=qs_before) then
        print '(a,a,a,es15.7)', 'FAIL no-transfer ',label,' diameter_um=',diameter_um
        failures=failures+1
      endif
    endif
    print '(a,a,a,es15.7,a,3(es15.7,1x),a,3(es15.7,1x))', &
      'CASE ',label,' diameter_um=',diameter_um,' before(QI,QS,NI)=',qi_before,qs_before,ni_before, &
      ' after(QI,QS,NI)=',qci(i,k,2),qrs(i,k,2),nci(i,k,2)
  end subroutine exercise
  subroutine source_slope(qci,nci,den,rslope,pidni)
    real, intent(in) :: qci(:,:),nci(:,:),den(:,:),pidni
    real, intent(out) :: rslope(:,:,:)
    real, parameter :: dmi=3.0,lamdaimin=9.08e3,lamdaimax=1.82e6
    real :: lamdai,x,y,z
    integer :: i,k
          lamdai(x,y,z)= exp(log(((pidni*z)/(x*y)))*(1./dmi))
    i=1; k=1; x=den(i,k); y=qci(i,k); z=nci(i,k)
               rslope(i,k,4) =max(min(1./lamdai(qci(i,k),den(i,k),nci(i,k)),1./lamdaimin), &
                          1./lamdaimax)
  end subroutine source_slope
end program
