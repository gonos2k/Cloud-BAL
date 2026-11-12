program row
 use module_mp_kdm6, only: kdm6,kdm6init
 implicit none
 real :: a(118:233,1:39,72:72,21),b(118:233,72:72,8),c(24)
 integer :: rank
 open(20,file='input.bin',access='stream',form='unformatted',status='old')
 read(20) a,b,c
 close(20)
 ! Host rhosnow=100; hail_opt defaults to 0 in the frozen namelist.
 call kdm6init(c(15),c(16),100.,c(22),c(4),c(5),0,.false.)
 call kdm6(a(:,:,:,1),a(:,:,:,2),a(:,:,:,3),a(:,:,:,4),a(:,:,:,5),a(:,:,:,6),a(:,:,:,7), &
 a(:,:,:,8),a(:,:,:,9),a(:,:,:,10),a(:,:,:,11),a(:,:,:,12),a(:,:,:,13), &
 a(:,:,:,14),a(:,:,:,15),a(:,:,:,16),a(:,:,:,17), &
 c(1),c(2),c(3),c(4),c(5),c(6),c(7),c(8),c(9),c(10),c(11),c(12),c(13),c(14), &
 c(15),c(16),c(17),c(18),c(19),c(20),c(21),c(22),c(23),c(24), &
 b(:,:,1),b(:,:,2),b(:,:,3),b(:,:,4),b(:,:,5),b(:,:,6),a(:,:,:,18),.true.,0, &
 b(:,:,7),b(:,:,8),1,1,1,1,a(:,:,:,19),a(:,:,:,20),a(:,:,:,21), &
 1,235,1,283,1,40,118,233,72,72,1,39,118,233,72,72,1,39)
 open(21,file='terminal.bin',access='stream',form='unformatted',status='replace')
 write(21) a,b,c
 close(21)
end program
subroutine wrf_get_myproc(rank)
 integer :: rank
 rank=3
end subroutine
