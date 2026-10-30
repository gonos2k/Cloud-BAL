if(prevp(i,k).lt.0.) then
              prevp(i,k) = max(prevp(i,k),-(qrs(i,k,1))/dtcld)
              prevp(i,k) = max(prevp(i,k),(satdt)/2)




              if(prevp(i,k).eq.-qrs(i,k,1)/dtcld) then
                nci(i,k,3) = nci(i,k,3)+nrs(i,k,1)
                nrs(i,k,1) = 0.
              endif
            else
              prevp(i,k) = min(prevp(i,k),(satdt)/2)
            endif
