program probe
 implicit none
 integer :: u
 open(newunit=u,file='existing.raw',access='stream',form='unformatted',status='replace',action='write')
 write(u) 'NEW'
 close(u)
end program
