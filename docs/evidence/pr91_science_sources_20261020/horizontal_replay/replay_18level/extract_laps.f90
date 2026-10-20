program extract_laps
 implicit none
 integer :: u, ios, ver, nx, ny, iproj, qn
 real :: xfcst, xlvl, startlat,startlon,dx,dy,xlonc,t1,t2,earth
 real, allocatable :: a(:,:)
 character(len=24) :: hdate
 character(len=32) :: map_source
 character(len=9) :: field
 character(len=25) :: units
 character(len=46) :: desc
 character(len=8) :: startloc
 logical :: windrel
 open(newunit=u,file='/var/tmp/pr82_same13_metgrid_candidate.final20261012/LAPS:2026-08-16_13',form='unformatted',convert='big_endian',status='old',action='read')
 open(20,file='qc_levels.txt',status='replace')
 open(21,file='qc_headers.txt',status='replace')
 qn=0
 do
   read(u,iostat=ios) ver
   if(ios/=0) exit
   if(ver/=5) error stop 'expected WPS version 5'
   read(u) hdate,xfcst,map_source,field,units,desc,xlvl,nx,ny,iproj
   if(iproj/=3) error stop 'expected Lambert projection'
   read(u) startloc,startlat,startlon,dx,dy,xlonc,t1,t2,earth
   read(u) windrel
   allocate(a(nx,ny))
   read(u) a
   if(trim(field)=='QC') then
      qn=qn+1
      write(21,'(i0,1x,a,1x,f16.5,1x,i0,1x,i0,1x,a,1x,a,1x,es24.16)') qn,trim(hdate),xlvl,nx,ny,trim(field),trim(units),earth
      write(20,'(es24.16)') a
   endif
   deallocate(a)
 enddo
 close(u); close(20); close(21)
 if(qn/=21) then
   write(*,*) 'QC records=',qn
   error stop 'expected 21 QC levels'
 endif
 print *, 'QC_records=',qn
end program
