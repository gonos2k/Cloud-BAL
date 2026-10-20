program enumerate_target_support
 use llxy_module, only: push_source_projection, lltoxy, select_domain, SOURCE_PROJ, PROJ_LC
 implicit none
 integer :: u,ios,i,j,si,sj,nlinks,ntargets
 real :: lat,lon,x,y,minx,maxx,miny,maxy,wx,wy,w
 integer :: corner_i(4),corner_j(4)
 real :: weight(4)
 character(len=64) :: seen(1000)
 integer :: nseen
 call push_source_projection(PROJ_LC,126.0,30.0,60.0,5000.0,5000.0,0.0,0.0, &
   1.0,1.0,31.3445053101,119.79931640625, &
   user_centerlat=0.0,user_centerlon=0.0,user_centeri=118.0,user_centerj=142.0,earth_radius=6371229.00390625)
 call select_domain(SOURCE_PROJ)
 open(newunit=u,file='target_grid_234x282.txt',status='old')
 open(20,file='inverse_support_rows.txt',status='replace')
 nlinks=0; ntargets=0; nseen=0
 do
   read(u,*,iostat=ios) i,j,lat,lon
   if(ios/=0) exit
   call lltoxy(lat,lon,x,y,0)
   minx=real(floor(x)); maxx=real(ceiling(x)); miny=real(floor(y)); maxy=real(ceiling(y))
   corner_i=[int(minx)-1,int(maxx)-1,int(minx)-1,int(maxx)-1]
   corner_j=[int(maxy)-1,int(maxy)-1,int(miny)-1,int(miny)-1]
   weight(1)=(y-miny)*(maxx-x)
   weight(2)=(y-miny)*(x-minx)
   weight(3)=(maxy-y)*(maxx-x)
   weight(4)=(maxy-y)*(x-minx)
   do si=1,4
     if(corner_i(si)<134.or.corner_i(si)>136.or.corner_j(si)<16.or.corner_j(si)>18) cycle
     if(weight(si)==0.0) cycle
     write(20,'(2(i0,1x),2(f14.8,1x),2(f16.9,1x),2(i0,1x),es24.16,1x,z8.8)') &
       i,j,lat,lon,x,y,corner_i(si),corner_j(si),weight(si),transfer(weight(si),0)
     nlinks=nlinks+1
     block
       character(len=64) :: key
       integer :: q
       write(key,'(2(i0,1x))') i,j
       do q=1,nseen
         if(trim(seen(q))==trim(key)) exit
       enddo
       if(q>nseen) then
         nseen=nseen+1; seen(nseen)=key
       endif
     end block
   enddo
 enddo
 close(u);close(20)
 print *, 'target_points_scanned=',234*282
 print *, 'inverse_support_link_rows=',nlinks
 print *, 'affected_target_cells=',nseen
end program
