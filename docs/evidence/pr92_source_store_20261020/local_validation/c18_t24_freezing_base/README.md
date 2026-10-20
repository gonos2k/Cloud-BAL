# C18 T24 KDM6 freezing-base classification

Both C18 arms completed 23 timesteps, then ended incomplete at T24 with `PR85 invalid cloud-ice freezing packet base`. The final `PINU` record is the same in both arms at `(i,j,k)=(230,247,20)` and records `FFF`: not accepted, invalid base, and not transient inactive ice.

The replay pins the captured REAL32 inputs by their exact bit patterns: `QI=3623A538`, `NI=441BBBE7`, dry density `3F0938B8`. The source cutoff is exactly `NEAREST(1.e-14,-1.0)` = `9.9999989774837532e-15` (`283424DB`); QI is far above it, so the helper takes its strict active-ice cone check. Source-derived bounds give ice mean particle mass `2.0982771175135736e-9` and maximum `2.0982747187893314e-9`. Their promoted REAL32 encodings are `31103148` and `3110313D`, an 11-encoding distance (about 10.8 ULP). The helper allows 8 ULP, so the gap is about 2.8 ULP beyond tolerance. Cloud cone checks pass.

The archived [replay harness](replay.f90) calls the retained helper using captured proposal rates and source-derived bounds. Pinned Intel O0 and O2 both return `base_valid=F, accepted=F`. Logs, hashes, exact row, and bounds are recorded in [classification.json](classification.json).

This confirms the immediate helper reason and reproduces the failure. It does not establish which upstream operation created the narrowly out-of-cone ice state. Both native receipts remain `INCOMPLETE` (`rc=128`, 23 completed timesteps); this is not a successful model run or a proposed physical fix.
