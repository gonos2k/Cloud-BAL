            if (ieee_is_finite(rain_q_before(2))) then
              if (rain_q_before(2).gt.0.0) then
                if (ieee_is_finite(rain_ng_q_process(2))) then
                  if (rain_ng_q_process(2).lt.0.0) then
                    if (rain_ng_q_process(2).le.-rain_q_before(2)) then
                      ice_full_sublimation_pending(i,k)=.true.
                      ice_extinction_cause(i,k)=ior(ice_extinction_cause(i,k),2)
                    endif
                  endif
                endif
              endif
            endif
