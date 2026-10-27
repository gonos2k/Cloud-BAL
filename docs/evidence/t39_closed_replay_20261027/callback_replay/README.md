# T39 final callback producer replay

`receipt.json` records the final bounded replay for callback cell `(T39, RK2, 2, 219, 13)`. The helper, drivers, and O0/O2 logs are the text evidence copied from a fresh external run directory. No executable, compiler module, or duplicate raw capture is published here.

`run_callback_replay.py` validates the input capture hashes against the closure manifest and closed HYDRO receipt; it also validates the C2 build receipt, source transform proof, compiled `module_em.o` generated-source hash, C2 preprocessed module hash, and pinned Intel profile/compiler. It requires the requested `--run-dir` to be fresh and outside the checkout. For example:

```bash
python docs/evidence/t39_closed_replay_20261027/callback_replay/run_callback_replay.py \
  --run-dir /var/tmp/t39-callback-reproduction-20261027
```

The unmodified `horizontal_diffusion64.f90` helper must reproduce the captured RK1 producer REAL64 bits and captured zero RK2 recomputation at O0 and O2. The separate probe module adds one REAL128 output to the helper and must reproduce the same REAL64 bits. Its four interface/output edits are enumerated in the receipt, and the runner proves reversing them recovers the unmodified helper body.

The RK1 stencil has a single west-neighbor Q of 900 REAL32 minimum-subnormal quanta and B/N of one quantum; center and other Q/N entries are zero. The probe's REAL128 results satisfy `Q=900*B`; the independently rounded REAL64 pair crosses the strict cone. The exact `Fraction` check in the receipt proves `Q64 - 900*B64 > 0` by `125/803469022129495137770981046170581301261101496891396417650688`. The displayed quotient is not used as the proof.

A possible future design to assess is a jointly constrained REAL128-to-REAL64 Q/B rounding step: after nearest rounding, test the strict cone exactly and select a neighboring representable pair under a stated pairwise error and conservation budget. This remains a design question; no tolerance, source policy, or implementation was changed. The replay is local to one captured helper stencil and does not establish full grouped-transaction or forecast causality.
