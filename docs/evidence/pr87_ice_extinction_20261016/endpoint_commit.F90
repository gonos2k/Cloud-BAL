            pr87_ice_sublimation_extinctions=0
            pr87_ice_sublimation_n_preclear=rain_n_after(2)
            pr87_ice_sublimation_dn=0.0
            if (rain_composite_valid) then
              if (ieee_is_finite(rain_n_after(2))) then
                if (rain_n_after(2).ge.0.0) then
                  if (ice_full_sublimation_pending(i,k) .and. &
                      rain_q_after(2).eq.0.0) then
                    if (rain_n_after(2).gt.0.0) then
                      pr87_ice_sublimation_extinctions=1
                      pr87_ice_sublimation_dn=-rain_n_after(2)
                    endif
                    rain_n_after(2)=0.0
                  endif
                endif
              endif
            endif
