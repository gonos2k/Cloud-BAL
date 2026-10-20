# C12 source-expression replay with the captured C11 stencil

This standalone O0/O2 fixture reuses the C11d captured REAL32 stencil and geometry, and the embedded native `horizontal_diffusion64` helper extracted from C10 `module_em.F`. It also compiles the existing `cloud_bal_joint_transport` store helper. The extracted source expression is taken verbatim from the generated C12 `solve_em.F` and maps the four before/after tendency channels into `pr87_all_pair_diffusion_nonD64`.

The C11 capture does not contain the C12 decomposition operands. Therefore this fixture explicitly manufactures `nonD64=0` by setting the source and before/after tendencies to zero. It then evaluates the C12 source-rate expression `nonD + Dprepared` and the captured carrier/time update, followed by the existing strict mass-ratio and volume-bound store. It demonstrates that the positive captured prepared Q/N diffusion pair remains positive through this expression and passes that store check. It does not replay C12's full model source chain, establish the actual C12 residual at the captured cell, or approve a native model run.

Intel O0 and O2 outputs are byte-identical. The native helper output bits match the preserved C11 replay. O0 emits an Intel runtime warning that the store helper creates an array temporary for the bounds argument; it does not change the result.
