program probe
 implicit none
 integer :: u
 open(newunit=u,file='stage.raw',access='stream',form='unformatted',status='replace',action='write')
 write(u) 'NEW'
 close(u)
 open(newunit=u,file='driver.raw',access='stream',form='unformatted',status='replace',convert='big_endian')
 write(u) 'NEW'
 close(u)
end program
