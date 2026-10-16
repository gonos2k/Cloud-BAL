module progb_test_source
  use, intrinsic :: ieee_arithmetic, only : ieee_is_finite
  implicit none
  integer, parameter :: PROGB_ABSENT=0, PROGB_TRANSIENT=1
  integer, parameter :: PROGB_PSD_ACTIVE=2, PROGB_UNSUPPORTED=3
contains

   SUBROUTINE progb_before(brs,qrs,rhox,its,ite,jts,jte,kts,kte,qcrmin             &
                         ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2&
                         ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax     &
                         ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status)
  use, intrinsic :: ieee_arithmetic, only : ieee_is_finite
  implicit none
  integer           :: i,k,sy, its,ite, jts,jte, kts,kte
  real, intent(in)  ::qcrmin,dmg,mug,pi
  real, intent(in)  ::g1pdgmg,g1pmg,n0g
  real, intent(in)  ::rslopegmax
  REAL, DIMENSION( its:ite , kts:kte,3), INTENT(IN) :: qrs
  REAL, DIMENSION( its:ite , kts:kte), INTENT(INOUT):: brs   
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: rhox    
  INTEGER, DIMENSION( its:ite , kts:kte),INTENT(OUT) :: progb_status
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: cmg,pidn0g
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: avtg,pvtg,precg2
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,&
                                                       g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1
  REAL ::tmp1,tmp2
  DOUBLE PRECISION :: raw_density
  real,dimension(9) :: Tbl,aTbl,bTbl
  real, parameter   :: rho_min = 100.      
  real, parameter   :: rho_max = 900.      
  real, parameter   :: rho_mid = 400.      
  real, parameter   :: brs_min = 1.e-15   

 
  data Tbl /    100.,   200.,   300.,   400.,   500.,   600.,   700., 800., 900./   
  data aTbl   /  54.9153,   74.2262,   88.8313,  101.0411, 111.7359,  121.3625, 130.1841,  138.3714, 146.0422 / 
  data bTbl   / 0.5446,    0.5375,    0.5339,    0.5316, 0.5299,    0.5286, 0.5275,    0.5266, 0.5258 / 
 

      do k = kts, kte
        do i = its, ite
          rhox(i,k) = 0.0
          cmg(i,k) = 0.0
          pidn0g(i,k) = 0.0
          avtg(i,k) = 0.0
          pvtg(i,k) = 0.0
          precg2(i,k) = 0.0
          bvtg(i,k) = 0.0
          bvtg1(i,k) = 0.0
          bvtg2(i,k) = 0.0
          bvtg3(i,k) = 0.0
          bvtg4(i,k) = 0.0
          rslopegbmax(i,k) = 0.0
          g1pbg(i,k) = 0.0
          g3pbg(i,k) = 0.0
          g4pbg(i,k) = 0.0
          g5pbgo2(i,k) = 0.0
          g1pdgbgmg(i,k) = 0.0
          dgbgmug1(i,k) = 0.0
          progb_status(i,k) = PROGB_UNSUPPORTED
          if (.not. ieee_is_finite(qrs(i,k,3)) .or. &
              .not. ieee_is_finite(brs(i,k))) cycle
          if (qrs(i,k,3) == 0.0 .and. brs(i,k) == 0.0) then
            progb_status(i,k) = PROGB_ABSENT
            cycle
          endif
          if (qrs(i,k,3) <= 0.0 .or. brs(i,k) <= 0.0) cycle
          if (qrs(i,k,3) <= qcrmin .and. brs(i,k) <= brs_min) then
            progb_status(i,k) = PROGB_TRANSIENT
            cycle
          endif
          raw_density = dble(qrs(i,k,3))/dble(brs(i,k))
          if (.not. ieee_is_finite(raw_density)) cycle
          if (raw_density < dble(rho_min) .or. &
              raw_density > dble(rho_max)) cycle
          rhox(i,k) = qrs(i,k,3)/brs(i,k)
          cmg(i,k) = pi*rhox(i,k)/6
          if (.not. ieee_is_finite(cmg(i,k)) .or. cmg(i,k) <= 0.0) cycle
          pidn0g(i,k) = cmg(i,k)*n0g*g1pdgmg/g1pmg
         if (cmg(i,k).gt. 0) then
          if (rhox(i,k).ge. Tbl(1) .and. rhox(i,k).lt.Tbl(9)) then
                  do sy = 1,8
                   if (Tbl(sy).le. rhox(i,k) .and. Tbl(sy+1).gt.rhox(i,k)) then
                   tmp2 = 1./(Tbl(sy+1)-Tbl(sy))
                   avtg(i,k)=aTbl(sy)+(rhox(i,k)-Tbl(sy))*(aTbl(sy+1)-aTbl(sy))*tmp2
                   bvtg(i,k)=bTbl(sy)+(rhox(i,k)-Tbl(sy))*(bTbl(sy+1)-bTbl(sy))*tmp2
                   bvtg1(i,k) = 1.+bvtg(i,k)
                   bvtg2(i,k) = 2.5+.5*bvtg(i,k)+mug
                   bvtg3(i,k) = 3.+bvtg(i,k)+mug
                   bvtg4(i,k) = 4.+bvtg(i,k)
                   dgbgmug1(i,k) = 1.+dmg + bvtg(i,k) + mug
                   g1pbg(i,k) = rgmma(bvtg1(i,k))
                   g3pbg(i,k) = rgmma(bvtg3(i,k))
                   g4pbg(i,k) = rgmma(bvtg4(i,k))
                   g5pbgo2(i,k) = rgmma(bvtg2(i,k))
                   g1pdgbgmg(i,k)=rgmma(dgbgmug1(i,k))
                   rslopegbmax(i,k) = rslopegmax ** bvtg(i,k)
                   pvtg(i,k) = avtg(i,k)*g1pdgbgmg(i,k)/g1pdgmg
                   precg2(i,k) = 4.*.31*avtg(i,k)**.5*g5pbgo2(i,k)
                   exit
                   endif
                  enddo
         else if (rhox(i,k).eq. Tbl(9)) then
                   avtg(i,k)=aTbl(9)
                   bvtg(i,k)=bTbl(9)
                   bvtg1(i,k) = 1.+bvtg(i,k)
                   bvtg2(i,k) = 2.5+.5*bvtg(i,k)+mug
                   bvtg3(i,k) = 3.+bvtg(i,k)+mug
                   bvtg4(i,k) = 4.+bvtg(i,k)
                   dgbgmug1(i,k) = 1.+dmg + bvtg(i,k) + mug
                   g1pbg(i,k) = rgmma(bvtg1(i,k))
                   g3pbg(i,k) = rgmma(bvtg3(i,k))
                   g4pbg(i,k) = rgmma(bvtg4(i,k))
                   g5pbgo2(i,k) = rgmma(bvtg2(i,k))
                   g1pdgbgmg(i,k)=rgmma(dgbgmug1(i,k))
                   rslopegbmax(i,k) = rslopegmax ** bvtg(i,k)
                   pvtg(i,k) = avtg(i,k)*g1pdgbgmg(i,k)/g1pdgmg
                   precg2(i,k) = 4.*.31*avtg(i,k)**.5*g5pbgo2(i,k)
         endif
       endif
          if (.not. ieee_is_finite(rhox(i,k)) .or. &
              .not. ieee_is_finite(cmg(i,k)) .or. &
              .not. ieee_is_finite(pidn0g(i,k)) .or. &
              .not. ieee_is_finite(avtg(i,k)) .or. &
              .not. ieee_is_finite(pvtg(i,k)) .or. &
              .not. ieee_is_finite(precg2(i,k)) .or. &
              .not. ieee_is_finite(bvtg(i,k)) .or. &
              .not. ieee_is_finite(bvtg1(i,k)) .or. &
              .not. ieee_is_finite(bvtg2(i,k)) .or. &
              .not. ieee_is_finite(bvtg3(i,k)) .or. &
              .not. ieee_is_finite(bvtg4(i,k)) .or. &
              .not. ieee_is_finite(rslopegbmax(i,k)) .or. &
              .not. ieee_is_finite(g1pbg(i,k)) .or. &
              .not. ieee_is_finite(g3pbg(i,k)) .or. &
              .not. ieee_is_finite(g4pbg(i,k)) .or. &
              .not. ieee_is_finite(g5pbgo2(i,k)) .or. &
              .not. ieee_is_finite(g1pdgbgmg(i,k)) .or. &
              .not. ieee_is_finite(dgbgmug1(i,k))) then
            rhox(i,k) = 0.0
            cmg(i,k) = 0.0
            pidn0g(i,k) = 0.0
            avtg(i,k) = 0.0
            pvtg(i,k) = 0.0
            precg2(i,k) = 0.0
            bvtg(i,k) = 0.0
            bvtg1(i,k) = 0.0
            bvtg2(i,k) = 0.0
            bvtg3(i,k) = 0.0
            bvtg4(i,k) = 0.0
            rslopegbmax(i,k) = 0.0
            g1pbg(i,k) = 0.0
            g3pbg(i,k) = 0.0
            g4pbg(i,k) = 0.0
            g5pbgo2(i,k) = 0.0
            g1pdgbgmg(i,k) = 0.0
            dgbgmug1(i,k) = 0.0
            cycle
          endif
          brs(i,k) = qrs(i,k,3)/rhox(i,k)
          progb_status(i,k) = PROGB_PSD_ACTIVE
        enddo
      enddo
  END subroutine progb_before


   SUBROUTINE progb_after(brs,qrs,rhox,its,ite,jts,jte,kts,kte,qcrmin             &
                         ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2&
                         ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax     &
                         ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status)
  use, intrinsic :: ieee_arithmetic, only : ieee_is_finite
  implicit none
  integer           :: i,k,sy, its,ite, jts,jte, kts,kte
  real, intent(in)  ::qcrmin,dmg,mug,pi
  real, intent(in)  ::g1pdgmg,g1pmg,n0g
  real, intent(in)  ::rslopegmax
  REAL, DIMENSION( its:ite , kts:kte,3), INTENT(IN) :: qrs
  REAL, DIMENSION( its:ite , kts:kte), INTENT(INOUT):: brs   
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: rhox    
  INTEGER, DIMENSION( its:ite , kts:kte),INTENT(OUT) :: progb_status
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: cmg,pidn0g
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: avtg,pvtg,precg2
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,&
                                                       g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1
  REAL ::tmp1,tmp2
  DOUBLE PRECISION :: raw_density
  real,dimension(9) :: Tbl,aTbl,bTbl
  real, parameter   :: rho_min = 100.      
  real, parameter   :: rho_max = 900.      
  real, parameter   :: rho_mid = 400.      
  real, parameter   :: brs_min = 1.e-15   

 
  data Tbl /    100.,   200.,   300.,   400.,   500.,   600.,   700., 800., 900./   
  data aTbl   /  54.9153,   74.2262,   88.8313,  101.0411, 111.7359,  121.3625, 130.1841,  138.3714, 146.0422 / 
  data bTbl   / 0.5446,    0.5375,    0.5339,    0.5316, 0.5299,    0.5286, 0.5275,    0.5266, 0.5258 / 
 

      do k = kts, kte
        do i = its, ite
          rhox(i,k) = 0.0
          cmg(i,k) = 0.0
          pidn0g(i,k) = 0.0
          avtg(i,k) = 0.0
          pvtg(i,k) = 0.0
          precg2(i,k) = 0.0
          bvtg(i,k) = 0.0
          bvtg1(i,k) = 0.0
          bvtg2(i,k) = 0.0
          bvtg3(i,k) = 0.0
          bvtg4(i,k) = 0.0
          rslopegbmax(i,k) = 0.0
          g1pbg(i,k) = 0.0
          g3pbg(i,k) = 0.0
          g4pbg(i,k) = 0.0
          g5pbgo2(i,k) = 0.0
          g1pdgbgmg(i,k) = 0.0
          dgbgmug1(i,k) = 0.0
          progb_status(i,k) = PROGB_UNSUPPORTED
          if (.not. ieee_is_finite(qrs(i,k,3)) .or. &
              .not. ieee_is_finite(brs(i,k))) cycle
          if (qrs(i,k,3) == 0.0 .and. brs(i,k) == 0.0) then
            progb_status(i,k) = PROGB_ABSENT
            cycle
          endif
          if (qrs(i,k,3) <= 0.0 .or. brs(i,k) <= 0.0) cycle
          if (qrs(i,k,3) <= qcrmin .and. brs(i,k) <= brs_min) then
            progb_status(i,k) = PROGB_TRANSIENT
            cycle
          endif
          raw_density = dble(qrs(i,k,3))/dble(brs(i,k))
          if (.not. ieee_is_finite(raw_density)) cycle
          if (raw_density < dble(rho_min) .or. &
              raw_density > dble(rho_max)) cycle
          rhox(i,k) = qrs(i,k,3)/brs(i,k)
          cmg(i,k) = pi*rhox(i,k)/6
          if (.not. ieee_is_finite(cmg(i,k)) .or. cmg(i,k) <= 0.0) cycle
          pidn0g(i,k) = cmg(i,k)*n0g*g1pdgmg/g1pmg
         if (cmg(i,k).gt. 0) then
          if (rhox(i,k).ge. Tbl(1) .and. rhox(i,k).lt.Tbl(9)) then
                  do sy = 1,8
                   if (Tbl(sy).le. rhox(i,k) .and. Tbl(sy+1).gt.rhox(i,k)) then
                   tmp2 = 1./(Tbl(sy+1)-Tbl(sy))
                   avtg(i,k)=aTbl(sy)+(rhox(i,k)-Tbl(sy))*(aTbl(sy+1)-aTbl(sy))*tmp2
                   bvtg(i,k)=bTbl(sy)+(rhox(i,k)-Tbl(sy))*(bTbl(sy+1)-bTbl(sy))*tmp2
                   bvtg1(i,k) = 1.+bvtg(i,k)
                   bvtg2(i,k) = 2.5+.5*bvtg(i,k)+mug
                   bvtg3(i,k) = 3.+bvtg(i,k)+mug
                   bvtg4(i,k) = 4.+bvtg(i,k)
                   dgbgmug1(i,k) = 1.+dmg + bvtg(i,k) + mug
                   g1pbg(i,k) = rgmma(bvtg1(i,k))
                   g3pbg(i,k) = rgmma(bvtg3(i,k))
                   g4pbg(i,k) = rgmma(bvtg4(i,k))
                   g5pbgo2(i,k) = rgmma(bvtg2(i,k))
                   g1pdgbgmg(i,k)=rgmma(dgbgmug1(i,k))
                   rslopegbmax(i,k) = rslopegmax ** bvtg(i,k)
                   pvtg(i,k) = avtg(i,k)*g1pdgbgmg(i,k)/g1pdgmg
                   precg2(i,k) = 4.*.31*avtg(i,k)**.5*g5pbgo2(i,k)
                   exit
                   endif
                  enddo
         else if (rhox(i,k).eq. Tbl(9)) then
                   avtg(i,k)=aTbl(9)
                   bvtg(i,k)=bTbl(9)
                   bvtg1(i,k) = 1.+bvtg(i,k)
                   bvtg2(i,k) = 2.5+.5*bvtg(i,k)+mug
                   bvtg3(i,k) = 3.+bvtg(i,k)+mug
                   bvtg4(i,k) = 4.+bvtg(i,k)
                   dgbgmug1(i,k) = 1.+dmg + bvtg(i,k) + mug
                   g1pbg(i,k) = rgmma(bvtg1(i,k))
                   g3pbg(i,k) = rgmma(bvtg3(i,k))
                   g4pbg(i,k) = rgmma(bvtg4(i,k))
                   g5pbgo2(i,k) = rgmma(bvtg2(i,k))
                   g1pdgbgmg(i,k)=rgmma(dgbgmug1(i,k))
                   rslopegbmax(i,k) = rslopegmax ** bvtg(i,k)
                   pvtg(i,k) = avtg(i,k)*g1pdgbgmg(i,k)/g1pdgmg
                   precg2(i,k) = 4.*.31*avtg(i,k)**.5*g5pbgo2(i,k)
         endif
       endif
          if (.not. ieee_is_finite(rhox(i,k)) .or. &
              .not. ieee_is_finite(cmg(i,k)) .or. &
              .not. ieee_is_finite(pidn0g(i,k)) .or. &
              .not. ieee_is_finite(avtg(i,k)) .or. &
              .not. ieee_is_finite(pvtg(i,k)) .or. &
              .not. ieee_is_finite(precg2(i,k)) .or. &
              .not. ieee_is_finite(bvtg(i,k)) .or. &
              .not. ieee_is_finite(bvtg1(i,k)) .or. &
              .not. ieee_is_finite(bvtg2(i,k)) .or. &
              .not. ieee_is_finite(bvtg3(i,k)) .or. &
              .not. ieee_is_finite(bvtg4(i,k)) .or. &
              .not. ieee_is_finite(rslopegbmax(i,k)) .or. &
              .not. ieee_is_finite(g1pbg(i,k)) .or. &
              .not. ieee_is_finite(g3pbg(i,k)) .or. &
              .not. ieee_is_finite(g4pbg(i,k)) .or. &
              .not. ieee_is_finite(g5pbgo2(i,k)) .or. &
              .not. ieee_is_finite(g1pdgbgmg(i,k)) .or. &
              .not. ieee_is_finite(dgbgmug1(i,k))) then
            rhox(i,k) = 0.0
            cmg(i,k) = 0.0
            pidn0g(i,k) = 0.0
            avtg(i,k) = 0.0
            pvtg(i,k) = 0.0
            precg2(i,k) = 0.0
            bvtg(i,k) = 0.0
            bvtg1(i,k) = 0.0
            bvtg2(i,k) = 0.0
            bvtg3(i,k) = 0.0
            bvtg4(i,k) = 0.0
            rslopegbmax(i,k) = 0.0
            g1pbg(i,k) = 0.0
            g3pbg(i,k) = 0.0
            g4pbg(i,k) = 0.0
            g5pbgo2(i,k) = 0.0
            g1pdgbgmg(i,k) = 0.0
            dgbgmug1(i,k) = 0.0
            cycle
          endif
          progb_status(i,k) = PROGB_PSD_ACTIVE
        enddo
      enddo
  END subroutine progb_after

  real function rgmma(x)
    real, intent(in) :: x
    rgmma = x + 1.0
  end function rgmma
end module progb_test_source

  program test_progb_roundtrip
    use, intrinsic :: iso_fortran_env, only: int32, real64
    use progb_test_source
    implicit none
    real :: q(1,1,3), bg_before(1,1), bg_after(1,1)
    real :: qcrmin, dmg, mug, pi, g1pdgmg, g1pmg, n0g, rslopegmax
    integer :: status_before(1,1), status_after(1,1)
  real :: rhox_before(1,1), rhox_after(1,1)
  real :: cmg_before(1,1), cmg_after(1,1)
  real :: pidn0g_before(1,1), pidn0g_after(1,1)
  real :: avtg_before(1,1), avtg_after(1,1)
  real :: pvtg_before(1,1), pvtg_after(1,1)
  real :: precg2_before(1,1), precg2_after(1,1)
  real :: bvtg_before(1,1), bvtg_after(1,1)
  real :: bvtg1_before(1,1), bvtg1_after(1,1)
  real :: bvtg2_before(1,1), bvtg2_after(1,1)
  real :: bvtg3_before(1,1), bvtg3_after(1,1)
  real :: bvtg4_before(1,1), bvtg4_after(1,1)
  real :: rslopegbmax_before(1,1), rslopegbmax_after(1,1)
  real :: g1pbg_before(1,1), g1pbg_after(1,1)
  real :: g3pbg_before(1,1), g3pbg_after(1,1)
  real :: g4pbg_before(1,1), g4pbg_after(1,1)
  real :: g5pbgo2_before(1,1), g5pbgo2_after(1,1)
  real :: g1pdgbgmg_before(1,1), g1pdgbgmg_after(1,1)
  real :: dgbgmug1_before(1,1), dgbgmug1_after(1,1)
    real(real64) :: density_before, density_after

    q = 0.0
    q(1,1,3) = transfer(int(z'3AD8B31A',int32), 0.0)
    bg_before(1,1) = transfer(int(z'35F68E57',int32), 0.0)
    bg_after = bg_before
    qcrmin=1.0e-9; dmg=3.0; mug=0.0; pi=3.1415927
    g1pdgmg=1.0; g1pmg=1.0; n0g=1.0; rslopegmax=1.0
    density_before=real(q(1,1,3),real64)/real(bg_before(1,1),real64)
    call progb_before(bg_before, &
       q, &
       rhox_before, &
       1, &
       1, &
       1, &
       1, &
       1, &
       1, &
       qcrmin, &
       dmg, &
       mug, &
       cmg_before, &
       pi, &
       pidn0g_before, &
       g1pdgmg, &
       g1pmg, &
       n0g, &
       avtg_before, &
       pvtg_before, &
       precg2_before, &
       bvtg_before, &
       bvtg1_before, &
       bvtg2_before, &
       bvtg3_before, &
       bvtg4_before, &
       rslopegbmax_before, &
       rslopegmax, &
       g1pbg_before, &
       g3pbg_before, &
       g4pbg_before, &
       g5pbgo2_before, &
       g1pdgbgmg_before, &
       dgbgmug1_before, &
       status_before)
    call progb_after(bg_after, &
       q, &
       rhox_after, &
       1, &
       1, &
       1, &
       1, &
       1, &
       1, &
       qcrmin, &
       dmg, &
       mug, &
       cmg_after, &
       pi, &
       pidn0g_after, &
       g1pdgmg, &
       g1pmg, &
       n0g, &
       avtg_after, &
       pvtg_after, &
       precg2_after, &
       bvtg_after, &
       bvtg1_after, &
       bvtg2_after, &
       bvtg3_after, &
       bvtg4_after, &
       rslopegbmax_after, &
       rslopegmax, &
       g1pbg_after, &
       g3pbg_after, &
       g4pbg_after, &
       g5pbgo2_after, &
       g1pdgbgmg_after, &
       dgbgmug1_after, &
       status_after)
    density_after=real(q(1,1,3),real64)/real(bg_after(1,1),real64)
    if (density_before > 900.0_real64 .or. density_after > 900.0_real64) &
      error stop 'preserved ProgB input is outside accepted domain'
    if (transfer(bg_before(1,1),0_int32) /= int(z'35F68E56',int32)) &
      error stop 'baseline ProgB rewrite witness changed'
    if (transfer(bg_after(1,1),0_int32) /= int(z'35F68E57',int32)) &
      error stop 'transformed ProgB did not preserve BG'
    if (status_before(1,1) /= 2 .or. status_after(1,1) /= 2) &
      error stop 'ProgB status changed'
    if (any(rhox_before /= rhox_after) .or. rhox_after(1,1) /= 900.0) &
      error stop 'ProgB density changed'
  if (any(rhox_before /= rhox_after)) error stop 'ProgB property changed: rhox'
  if (any(cmg_before /= cmg_after)) error stop 'ProgB property changed: cmg'
  if (any(pidn0g_before /= pidn0g_after)) error stop 'ProgB property changed: pidn0g'
  if (any(avtg_before /= avtg_after)) error stop 'ProgB property changed: avtg'
  if (any(pvtg_before /= pvtg_after)) error stop 'ProgB property changed: pvtg'
  if (any(precg2_before /= precg2_after)) error stop 'ProgB property changed: precg2'
  if (any(bvtg_before /= bvtg_after)) error stop 'ProgB property changed: bvtg'
  if (any(bvtg1_before /= bvtg1_after)) error stop 'ProgB property changed: bvtg1'
  if (any(bvtg2_before /= bvtg2_after)) error stop 'ProgB property changed: bvtg2'
  if (any(bvtg3_before /= bvtg3_after)) error stop 'ProgB property changed: bvtg3'
  if (any(bvtg4_before /= bvtg4_after)) error stop 'ProgB property changed: bvtg4'
  if (any(rslopegbmax_before /= rslopegbmax_after)) error stop 'ProgB property changed: rslopegbmax'
  if (any(g1pbg_before /= g1pbg_after)) error stop 'ProgB property changed: g1pbg'
  if (any(g3pbg_before /= g3pbg_after)) error stop 'ProgB property changed: g3pbg'
  if (any(g4pbg_before /= g4pbg_after)) error stop 'ProgB property changed: g4pbg'
  if (any(g5pbgo2_before /= g5pbgo2_after)) error stop 'ProgB property changed: g5pbgo2'
  if (any(g1pdgbgmg_before /= g1pdgbgmg_after)) error stop 'ProgB property changed: g1pdgbgmg'
  if (any(dgbgmug1_before /= dgbgmug1_after)) error stop 'ProgB property changed: dgbgmug1'
    print '(a,2(1x,es24.16))', 'PR87 ProgB BG preserved, accepted density:', &
      density_before, density_after
  end program test_progb_roundtrip
