program grid_rows_288
 use interp_module, only: interp_array_from_string, interp_options_from_string, interp_sequence
 use llxy_module, only: push_source_projection, lltoxy, select_domain, SOURCE_PROJ, PROJ_LC
 implicit none
 integer, parameter :: nt=288
 real :: a(1:235,1:283,1:1), rx, ry, val, lat, lon, expected, p, pgrid
 integer :: i,j,ios,k,idx, mindex
 integer, pointer :: methods(:), options(:)
 real :: tp(nt), tlat(nt), tlon(nt), tval(nt)
 integer :: ti(nt), tj(nt), tmk(nt)
 a=0.0
 open(10,file='qc_levels.txt',status='old')
 open(11,file='pressures.txt',status='old')
 open(12,file='targets_288.txt',status='old')
 do idx=1,nt
   read(12,*) tp(idx),ti(idx),tj(idx),tlat(idx),tlon(idx),tval(idx),tmk(idx),pgrid
 enddo
 close(12)
 call push_source_projection(PROJ_LC,126.0,30.0,60.0,5000.0,5000.0,0.0,0.0, &
   1.0,1.0,31.3445053101,119.79931640625, &
   user_centerlat=0.0,user_centerlon=0.0,user_centeri=118.0,user_centerj=142.0,earth_radius=6371229.00390625)
 call select_domain(SOURCE_PROJ)
 methods=>interp_array_from_string('four_pt+average_4pt')
 options=>interp_options_from_string('four_pt+average_4pt')
 do k=1,21
   read(11,*) p
   ! qc_levels.txt stores each REAL32 value as one text record, in Fortran array order.
   read(10,*) a
   do idx=1,nt
     if(tp(idx)/=p) cycle
     call lltoxy(tlat(idx),tlon(idx),rx,ry,0)
     val=interp_sequence(rx,ry,1,a,1,235,1,283,1,1,-1.e30,methods,options,1)
     write(*,'(f10.1,1x,2(i0,1x),2(es24.16,1x),2(z8.8,1x),2(es24.16,1x),i0)') p,ti(idx),tj(idx),rx,ry,transfer(val,0),transfer(tval(idx),0),val,tval(idx),tmk(idx)
   enddo
 enddo
 close(10); close(11)
end program
