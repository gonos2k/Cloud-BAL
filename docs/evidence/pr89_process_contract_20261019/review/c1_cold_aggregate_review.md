# C1 cold aggregate independent check

Root independently hash-checked both CLOSED-run gzip bindings, decoded all 1,120 data rows per arm directly (without the production parser), and recomputed all 18 metrics for each of four timesteps and the completed prefix using `math.fsum`. Call/transaction counts agree. Maximum normalized difference from the published aggregation is 2.0870354305040574e-15, from summation rounding.

Coverage remains the completed 80-second prefix of INCOMPLETE 120-second attempts. Units are kg m-2 SUM_COLUMNS, not global kilograms or individual reaction throughput. This checks aggregation and bindings, not the underlying process model, full conservation, or scientific acceptance.
