            if (ieee_is_finite(rain_q_fixed(2))) then
              if (rain_q_fixed(2).gt.0.0) then
                if (ieee_is_finite(rain_g_q_process(2))) then
                  if (rain_g_q_process(2).lt.0.0) then
                    if (rain_g_q_process(2).le.-rain_q_fixed(2)) then
                      ice_full_sublimation_pending(i,k)=.true.
                      ice_extinction_cause(i,k)=ior(ice_extinction_cause(i,k),4)
                    endif
                  endif
                endif
              endif
            endif
