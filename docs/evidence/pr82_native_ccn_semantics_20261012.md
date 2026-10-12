# KDM6 NN/CCN source binding

Inspected pinned KDM6 source `module_mp_kdm6.F` SHA-256 `a5e8ce7a05d147b05556aa7521c22c0991812711fe675409feec889e43a761e7` and the source-bound number-trace derivative SHA-256 `63feb4bac7ca7ae60a77ddbcba74319502f094a1ec4d11b3ae403a24e38615b6`.

In `module_mp_kdm6.F:932–953`, on the first timestep, `nn(i,k,j)` is initialized from `ccn0*qnn_land_mult` or `ccn0*qnn_sea_mult`, with an optional height decay. In `module_mp_kdm6.F:993–1004`, that ambient CCN reservoir is converted with `specific_number_to_volume(nn(i,k,j), dry_density(i,k), ...)` and assigned to `nci(i,k,3)`. No condensate mass field is paired with this NN reservoir. `QS` is snow mass and must not be used to report NN positive-number/zero-mass counts.

The offline conversion summary therefore reports conversion representability counts for NN, but reports `mass_pair: null` and no orphan mass/number metrics. NC/QC, NI/QI, and NR/QR retain their documented condensate pair metrics.
