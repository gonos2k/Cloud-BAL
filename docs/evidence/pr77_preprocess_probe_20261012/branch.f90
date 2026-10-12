program probe
integer :: selected
#ifndef TEST_DIRECT_VOLUME
selected=1
#else
selected=2
#endif
print *,selected
end program
