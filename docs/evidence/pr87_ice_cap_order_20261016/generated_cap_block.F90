              if(pidep(i,k).lt.0.) then



                pr87_ice_raw_pidep_before_caps=pidep(i,k)
                pidep(i,k) = max(pidep(i,k),-(qci(i,k,2))/dtcld)
                pidep(i,k) = max(max(pidep(i,k),(satdt)/2),supice)
                if (pidep(i,k).eq.-(qci(i,k,2))/dtcld) then
                  ice_full_sublimation_pending(i,k) = .true.
                  ice_sublimation_raw_pidep(i,k) = pr87_ice_raw_pidep_before_caps
                  ice_sublimation_q_before(i,k) = qci(i,k,2)
                  ice_sublimation_n_before(i,k) = nci(i,k,2)
                  ice_sublimation_event_count(i,k) = &
                       ice_sublimation_event_count(i,k) + 1
                  ice_sublimation_capped_pidep(i,k) = pidep(i,k)
                endif
              else
                pidep(i,k) = min(min(pidep(i,k),(satdt)/2),supice)
              endif
