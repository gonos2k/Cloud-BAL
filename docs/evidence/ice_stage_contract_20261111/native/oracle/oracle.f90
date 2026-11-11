program oracle
use iso_fortran_env, only: int32
implicit none
   real, parameter :: deni    = 500.0
   real, parameter :: bvti    = 1.0 
   real, parameter :: lamdaimax = 1.82e6 
   real, parameter :: lamdaimin = 9.08e3   
   real, parameter :: dmi = 3.0
   real, parameter :: mui = 0.  
real :: den(1,1),qci(1,1,2),nci(1,1,3),qci_tmp(1,1),nci_tmp(1,1),qmin,ncmin
real :: rslope(1,1,4),rslopeb(1,1,4),rsloped(1,1,4),rslope2(1,1,4),rslope3(1,1,4)
double precision :: rslopemu(1,1,4),n0i(1,1)
real :: rslopeimax,rslopeibmax,rslopeidmax,rslopei2max,rslopei3max,rslopeimmax
real :: pi,cmi,mui1,g1pmi,dimui1,g1pdimi,pidni,lamdi_tmp(1,1),x,y,z,lamdai
real :: threshold,qi_in,ni_in,lambda_in
integer :: which,side,branch,failures
integer,parameter :: i=1,k=1
logical :: active
character(8) :: mode
integer :: ios, active_int
integer(int32) :: ni_bits, aux_bits
real :: aux
lamdai(x,y,z)= exp(log(((pidni*z)/(x*y)))*(1./dmi))
   pi = 4.*atan(1.)
   cmi = pi*deni/6.
   mui1 = 1. + mui
   g1pmi = rgmma(mui1)
   dimui1 = 1.+dmi + mui
   g1pdimi = rgmma(dimui1)
   pidni = cmi*g1pdimi/g1pmi
   rslopeimax = 1./lamdaimax
   rslopeibmax = rslopeimax ** bvti
   rslopeidmax = (rslopeimax) ** dmi
   rslopei2max = (rslopeimax) * rslopeimax
   rslopei3max = (rslopei2max) * rslopeimax
rslopeimmax = 1.
do
 read(*,*,iostat=ios) mode,den(1,1),qi_in,ni_in,qmin,ncmin
 if(ios < 0) exit
 if(ios /= 0) error stop 'invalid input'
 qci=0.; nci=0.; qci(1,1,2)=qi_in; nci(1,1,2)=ni_in
 active=.false.; aux=-1.
 select case(trim(mode))
 case('SLOPE')
  qci_tmp=qi_in; nci_tmp=ni_in
  call ice_slope
  active=qi_in>qmin
  aux=rslope(1,1,4)
 case('PSD1')
  call psd(1)
 case('PSD2')
  call psd(2)
 case('PSD3')
  call psd(3)
 case default
  error stop 'invalid mode'
 end select
 if(trim(mode)/='SLOPE' .and. active) aux=lamdi_tmp(1,1)
 active_int=0
 if(active) active_int=1
 ni_bits=transfer(nci(1,1,2),ni_bits)
 aux_bits=transfer(aux,aux_bits)
 write(*,'(a,1x,z8.8,1x,z8.8,1x,i0)') trim(mode),ni_bits,aux_bits,active_int
end do
contains
subroutine ice_slope
          if(qci_tmp(i,k) .le. qmin) then  
            rslope(i,k,4) = rslopeimax
            rslopeb(i,k,4) = rslopeibmax
            rslopemu(i,k,4) = rslopeimmax
            rsloped(i,k,4) = rslopeidmax
            rslope2(i,k,4) = rslopei2max
            rslope3(i,k,4) = rslopei3max
          else
            if(nci_tmp(i,k) .eq. 0.) then
              
              rslope(i,k,4) = 1./lamdaimin
            else
           rslope(i,k,4) =max(min(1./lamdai(qci_tmp(i,k),den(i,k),nci_tmp(i,k)),1./lamdaimin), &
                          1./lamdaimax)
            endif
            rslopeb(i,k,4) = (rslope(i,k,4))**bvti
            rslopemu(i,k,4) = DBLE(rslope(i,k,4))**mui
            rsloped(i,k,4) = (rslope(i,k,4))**dmi
            rslope2(i,k,4) = (rslope(i,k,4))*rslope(i,k,4)
            rslope3(i,k,4) = (rslope2(i,k,4))*rslope(i,k,4)
          endif
end subroutine
subroutine psd(which_psd)
integer,intent(in)::which_psd
select case(which_psd)
case(1)
          if(qci(i,k,2) .ge. 1.e-14 ) then
active=.true.
            if(nci(i,k,2) .eq. 0.) then
              
              lamdi_tmp(i,k) = 0.
            else
            lamdi_tmp(i,k) = exp(log((((pidni)*nci(i,k,2))                       &
                         /(den(i,k)*qci(i,k,2))))*(1./dmi))
            endif
            n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            if(lamdi_tmp(i,k) .le. lamdaimin) then
              lamdi_tmp(i,k) = lamdaimin
              nci(i,k,2) = den(i,k)*qci(i,k,2)*(lamdi_tmp(i,k)**dmi)/pidni
              n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            elseif(lamdi_tmp(i,k) .ge. lamdaimax) then
              lamdi_tmp(i,k) = lamdaimax
              nci(i,k,2) = den(i,k)*qci(i,k,2)*(lamdi_tmp(i,k)**dmi)/pidni
              n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            endif
          endif




case(2)
          if(qci(i,k,2).ge. 1.e-14 ) then
active=.true.
            if(nci(i,k,2) .eq. 0.) then
              
              lamdi_tmp(i,k) = 0.
            else
            lamdi_tmp(i,k) = exp(log((((pidni)*nci(i,k,2))                       &
                         /(den(i,k)*qci(i,k,2))))*(1./dmi))
            endif
            n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            if(lamdi_tmp(i,k) .le. lamdaimin) then
              lamdi_tmp(i,k) = lamdaimin
              nci(i,k,2) = den(i,k)*qci(i,k,2)*(lamdi_tmp(i,k)**dmi)/pidni
              n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            elseif(lamdi_tmp(i,k) .ge. lamdaimax) then
              lamdi_tmp(i,k) = lamdaimax
              nci(i,k,2) = den(i,k)*qci(i,k,2)*(lamdi_tmp(i,k)**dmi)/pidni
              n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            endif
          endif




case(3)
          if(qci(i,k,2).ge. qmin .and. nci(i,k,2) .ge. ncmin ) then
active=.true.
            lamdi_tmp(i,k) = exp(log((((pidni)*nci(i,k,2))                       &
                         /(den(i,k)*qci(i,k,2))))*(1./dmi))
            if(lamdi_tmp(i,k) .le. lamdaimin) then
              lamdi_tmp(i,k) = lamdaimin
              nci(i,k,2) = den(i,k)*qci(i,k,2)*lamdi_tmp(i,k)**dmi/pidni
            elseif(lamdi_tmp(i,k) .ge. lamdaimax) then
              lamdi_tmp(i,k) = lamdaimax
              nci(i,k,2) = den(i,k)*qci(i,k,2)*lamdi_tmp(i,k)**dmi/pidni
            endif
          endif
end select
end subroutine
subroutine limit
            if(lamdi_tmp(i,k) .le. lamdaimin) then
              branch=1
              lamdi_tmp(i,k) = lamdaimin
              nci(i,k,2) = den(i,k)*qci(i,k,2)*(lamdi_tmp(i,k)**dmi)/pidni
              n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            elseif(lamdi_tmp(i,k) .ge. lamdaimax) then
              branch=2
              lamdi_tmp(i,k) = lamdaimax
              nci(i,k,2) = den(i,k)*qci(i,k,2)*(lamdi_tmp(i,k)**dmi)/pidni
              n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            endif
end subroutine
        REAL FUNCTION GAMMLN(x)


      IMPLICIT NONE
      REAL :: x
      DOUBLE PRECISION, PARAMETER:: STP = 2.5066282746310005D0
      DOUBLE PRECISION, DIMENSION(6), PARAMETER:: &
               COF = (/76.18009172947146D0, -86.50532032941677D0, &
                       24.01409824083091D0, -1.231739572450155D0, &
                      .1208650973866179D-2, -.5395239384953D-5/)
      DOUBLE PRECISION:: SER,TMP,XX,Y
      INTEGER:: J

      XX=x
      Y=XX
      TMP=XX+5.5D0
      TMP=(XX+0.5D0)*LOG(TMP)-TMP
      SER=1.000000000190015D0
      DO 11 J=1,6
        Y=Y+1.D0
        SER=SER+COF(J)/Y
11    CONTINUE
      GAMMLN=TMP+LOG(STP*SER/XX)
      END FUNCTION GAMMLN


      REAL function rgmma(x)
      IMPLICIT NONE
      REAL :: x

      rgmma = EXP(GAMMLN(x))

      END FUNCTION rgmma

end program oracle
