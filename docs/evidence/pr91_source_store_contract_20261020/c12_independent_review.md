# C12 independent source review

Reviewed the maintained transform `tools/pr91_source_first_diffusion.py` at
SHA-256 `80b654e32bcda6207aa69825f1ff5bfad4410ad681bdcaa67e53b68e14322796`,
its focused tests at SHA-256
`4345b29f9243b99b95158bccb089b4b3d7a1a64c93abae0ba3fba8f13e86f3ae`, and
the frozen C12c generated sources:

- `module_em.F`: `fcdc8f34b523aa83adcf7f60a049e27aba5f1975c264bb7118bb7efe62120a5f`
- `solve_em.F`: `d0ff9110811811c01ad13709bf5b538f7b92a49739211b0519aac55a81bc04a6`

## Source and cache review

The producer captures the old REAL64 diffusion increment and the before/after
REAL32 tendency fields for the four Q/N channels. It checks finiteness over
each channel's active diffusion footprint before setting that channel's valid
flag. The solve path resets the cache each step, validates timestep, RK stage,
and footprint, and requires all four channel flags before deriving the
non-diffusion residual. Each residual is formed before the original coupled
source fields are overwritten. The channel order is QC, QNC, QI, QNI.

The consumer initializes source rates from the separated non-diffusion
residual and adds the full prepared-field diffusion increment once. The
prepared-minus-old diffusion delta is accumulated only in the diagnostic
ledger. The source update remains virtual through the existing final joint
store and rollback path; I found no intermediate volume-number gate in the
temporary endpoint path.

## Boundary and validation scope

For this scoped one-domain/tile operator, the active source-prepared interior
uses the unchanged boundary donor ring as explicit stencil data. This review
accepts that declared operator policy; it does not establish closed boundary
flux or whole-domain conservation. No source update is inferred for the ring.

The focused suite includes the embedded native REAL128 helper with the C11
captured stencil at O0/O2. In addition,
`c12/native_replay/driver.f90` applies the extracted C12 non-diffusion source
expression to that stencil, adds the prepared REAL128 diffusion result, forms
the donor with captured carrier/time words, and runs the existing strict final
store with captured bounds. This fixture explicitly manufactures `nonD=0`:
the C11 capture lacks the C12 before/after decomposition operands. It verifies
the new arithmetic path preserves positive Q/N and the final store accepts
that result; it does not reconstruct the actual C12 residual for the captured
model cell or replay the full C12 model source chain.

## Result

`python -m unittest -v tests/test_pr91_source_first_diffusion.py` passed 7/7
with the pinned Intel profile. The standalone captured-stencil C12 expression
fixture also passed Intel O0/O2 with byte-identical output and strict final
store stage 0. No source-level blocker was found in the reviewed C12 transform.
This is not a native model-run approval or a claim of full boundary
conservation.
