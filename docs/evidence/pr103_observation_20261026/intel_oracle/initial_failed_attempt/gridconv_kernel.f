      subroutine gdtost(ab,ix,iy,stax,stay,staval,bgmodel)
c
c *** Subroutine to return stations back-interpolated values(staval)
c        from uniform grid points using overlapping-quadratics.
c        gridded values of input array a dimensioned ab(ix,iy), where
c        ix = grid points in x, iy = grid points in y.  Station
c        location given in terms of grid relative station x (stax)
c        and station column.
c *** Values greater than 1.0e30 indicate missing data.
c
      dimension ab(ix,iy),r(4),scr(4)
      integer bgmodel
      logical wrapped ! WNI added
            real missingflag
      parameter (missingflag=1.0e37)
c_______________________________________________________________________________
c
CWNI  Add a section to identify wrapped grid and set the wrapped flag
      wrapped = .FALSE.              ! WNI
      IF (bgmodel .eq. 6 .or.        ! WNI
     .       bgmodel .eq. 8 .or.     ! WNI
     .       bgmodel .eq. 10.) THEN  ! WNI
        wrapped = .true.             ! WNI
      ENDIF                          !WNI
C WNI END ADDITON

      iy1=int(stay)-1
      if(stay.lt.1.0)iy1=1.0
      iy2=iy1+3
      ix1=int(stax)-1
      if(stax.lt.1.0) THEN 
        IF (wrapped) THEN   ! WNI
          ix1 = ix1 + ix
        ELSE ! WNI
          ix1=1.0
        ENDIF ! WNI
      endif ! WNI
      ix2=ix1+3
      staval=missingflag
      fiym2=float(iy1)-1
      fixm2=float(ix1)-1
      ii=0
      do iii=ix1,ix2
         i=iii
c
c ****** Account for wrapping around effect of global data at Greenwich.
c
         if (wrapped) then    ! WNI
            if (i .lt. 1) i=i+ix  
            if (i .gt. ix) i=i-ix
         endif

         ii=ii+1
         if (i .ge. 1 .and. i .le. ix) then 
            jj=0
            do jjj=iy1,iy2
               j=jjj
c
c ************ Account for N-S wrapping effect of global data.
c
               if (wrapped) THEN  !WNI
                  if (j .lt. 1) then
                     j=2-j
                     i=i-ix/2
                     if (i .lt. 1) i=i+ix
                     if (i .gt. ix) i=i-ix
                  endif
                  if (j .gt. iy) then
                     j=2*iy-j
                     i=i-ix/2
                     if (i .lt. 1) i=i+ix
                     if (i .gt. ix) i=i-ix
                  endif
               endif

               jj=jj+1
               if (j .ge. 1 .and. j .le. iy) then
                  r(jj)=ab(i,j)
               else
                  r(jj)=missingflag
               endif
            enddo
            yy=stay-fiym2
            if (yy .eq. 2.0) then
               scr(ii)=r(2)
            else
               call binom(1.,2.,3.,4.,r(1),r(2),r(3),r(4),yy,scr(ii))
            endif
         else 
            scr(ii)=missingflag
         endif
      enddo
      xx=stax-fixm2
      if (xx .eq. 2.0) then
         staval=scr(2)
      else
         call binom(1.,2.,3.,4.,scr(1),scr(2),scr(3),scr(4),xx,staval)
      endif
c
      return
      end
c
c===============================================================================
c
      subroutine binom(x1,x2,x3,x4,y1,y2,y3,y4,xxx,yyy)
c
            real missingflag
      parameter (missingflag=1.0e37)
      yyy=missingflag
      if (x2 .gt. 1.e19 .or. x3 .gt. 1.e19 .or.
     .    y2 .gt. 1.e19 .or. y3 .gt. 1.e19) return
c
      wt1=(xxx-x3)/(x2-x3)
      wt2=1.0-wt1
c
      if (y4 .lt. 1.e19 .and. x4 .lt. 1.e19) then
c        yz22=(xxx-x3)*(xxx-x4)/((x2-x3)*(x2-x4))
         yz22=wt1*(xxx-x4)/(x2-x4)
c        yz23=(xxx-x2)*(xxx-x4)/((x3-x2)*(x3-x4))
         yz23=wt2*(xxx-x4)/(x3-x4)
         yz24=(xxx-x2)*(xxx-x3)/((x4-x2)*(x4-x3))
      else
         yz22=wt1
         yz23=wt2
         yz24=0.0
      end