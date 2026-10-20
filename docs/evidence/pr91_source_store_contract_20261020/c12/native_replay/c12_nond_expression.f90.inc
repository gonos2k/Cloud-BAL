                 pr87_all_pair_diffusion_nonD64(1,1,1,1) = &
                     (REAL(moist_tend(1,1,1,P_QC),real64)- &
                      REAL(pr87_all_pair_diffusion_tendency32(1,1,1,5),real64)) + &
                     (REAL(pr87_all_pair_diffusion_tendency32(1,1,1,1),real64)- &
                      REAL(pr87_coupled_qsrc(1,1,1,1),real64))
                 pr87_all_pair_diffusion_nonD64(1,1,1,2) = &
                     (REAL(scalar_tend(1,1,1,P_QNC),real64)- &
                      REAL(pr87_all_pair_diffusion_tendency32(1,1,1,6),real64)) + &
                     (REAL(pr87_all_pair_diffusion_tendency32(1,1,1,2),real64)- &
                      REAL(pr87_coupled_nsrc(1,1,1,1),real64))
                 pr87_all_pair_diffusion_nonD64(1,1,1,3) = &
                     (REAL(moist_tend(1,1,1,P_QI),real64)- &
                      REAL(pr87_all_pair_diffusion_tendency32(1,1,1,7),real64)) + &
                     (REAL(pr87_all_pair_diffusion_tendency32(1,1,1,3),real64)- &
                      REAL(pr87_coupled_qsrc(1,1,1,2),real64))
                 pr87_all_pair_diffusion_nonD64(1,1,1,4) = &
                     (REAL(scalar_tend(1,1,1,P_QNI),real64)- &
                      REAL(pr87_all_pair_diffusion_tendency32(1,1,1,8),real64)) + &
                     (REAL(pr87_all_pair_diffusion_tendency32(1,1,1,4),real64)- &
                      REAL(pr87_coupled_nsrc(1,1,1,2),real64))
