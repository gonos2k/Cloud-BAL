# PR75 Native FP State Capture

## Finding

The diagnostics-only O0 partialhost run reproduced the PR74 fatal in the NI
specific-to-volume adapter. The first failing cell was `(i,j,k)=(211,2,15)`;
`j=2` is the wrapper `call_lat_index`, and no global-j mapping is claimed:

- Public NI: `1.3563386438760339e-38 kg^-1` (binary32 `0x0093B134`)
- Dry density: `0.76804977655410767 kg m^-3` (binary32 `0x3F449EE9`)
- Adapter output: positive zero (binary32 `0x00000000`), `valid=F`
- MXCSR immediately before and after the conversion: `0x00009FFD`
- OS thread ID before and after: `4081559` (both reads match)

MXCSR bits 15 (FTZ) and 6 (DAZ) were both set on the same thread at the exact
failing adapter call. The public NI input itself is normal; multiplying it by
the normal dry density produces a positive subnormal binary32 result, which
the adapter observed as zero. FTZ is sufficient to explain that result. DAZ
was also enabled, but neither multiplication operand is subnormal. The direct
observation identifies the runtime floating-point state at failure. The
original PR74 final link argv still carries `-ftz`, but the conclusion rests
on the captured MXCSR and value, not on that option alone.
The helper reads MXCSR with `_mm_getcsr`; it contains no control-register
write. Low MXCSR exception-status bits are sticky and were not used to infer
the cause; only the FTZ and DAZ control bits were decoded.

The failing coordinates match the first source-order underflow recorded by the
PR74 pretrace and independent conversion replay. Those earlier artifacts
showed the mathematical product is a nonzero subnormal under strict no-FTZ
execution and becomes zero in the `-ftz` replay.
The diagnostic-run pretrace hash equals the PR74 O0 pretrace hash
`a6d5667850f5712982d5980b0292ee876b21cab6010efd18ade75cce5dfa1eaa`; the
selected-driver capture also matches its PR74 O0 hash
`a208b817d9061b44eeeb0ba25b46ed7296a68d801033dc6dd14d5c2180b03d44`.

## Scope and preservation

The run rebuilt only a scratch copy of `module_mp_kdm6` with the failure-only
observer. Its C helper reads MXCSR and the OS thread ID; it does not change the
floating-point control state. The run retained the PR74 O0 partialhost link
flags and same staged model inputs. It stopped with the existing expected
`KDM6 invalid NI number basis input` fatal (exit 128); no model timestep
completed.

All 100 staged inputs remained hash-identical. The incoming PR74 O0 archive
remained hash-identical. No maintained WRF/KDM6/private source was written.
The run retained the O0 KDM6 compile byte-order option and records both the
PR74 reference pretrace and the diagnostic-run pretrace hashes. The actual
selected-driver capture is also hash-bound to the PR74 O0 capture. The exact
compiler, source, transformed source, archive, input and runtime capture hashes are in
[`pr75_native_fp_O0_20261008.json`](evidence/pr75_native_fp_O0_20261008.json).
The preserved exact-coordinate runtime lines are in
[`pr75_native_fp_O0_20261008.raw`](evidence/pr75_native_fp_O0_20261008.raw).

The first direct capture attempt is preserved in
[`pr75_native_fp_first_attempt_20261008.json`](evidence/pr75_native_fp_first_attempt_20261008.json)
with its raw trace. It omitted the original `-convert big_endian` KDM6 compile
option, so its binary pretrace differed; the final O0 run restored and asserted
that compile option and reproduced the exact PR74 pretrace hash.

This O0 capture resolves the runtime-mode ambiguity needed to explain the
adapter fatal, so no O2 diagnostic replay was run. Main-startup MXCSR and
states on other worker threads were not captured; the failure-time state and
same-thread identity were captured directly. Physical validation remains
fail-open and the native change remains rejected.
