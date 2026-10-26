# PR103 final team review — 2026-10-26

## Review scope

This read-only review covered the frozen amplitude-control builder and proposal,
the archived-consumer and execution-preflight gates, the A20 close-pair helper,
the A640 receipt and bridge package, the six-arm history response and plotter,
the final attribution and observation docs, and the bounded postclosure
publication manifests. No model, compiler, or Graphify operation was run by the
reviewer.

The final A640 run receipt is SHA-256
`76792551d703e5e05af778b39482269dcb09ed16b83a5780514e920fcd1e5296`:
COMPLETE, return code 0, and 32/32 steps, with the approved A input, base C2
executable, boundary, and namelist. The supervisor closed with all 1,349
launch-time pins unchanged. The 20-second-to-640-second bridge passes its 30
T0 fields, first POST_KDM6 record, and 18 T1 fields.

The six-arm readback binds the same A640 run and the fixed 11-time schedule.
Its supervisor completed with 656/656 source/data pins unchanged. The existing
five-arm metrics are recomputed from receipt-bound arrays and checked before
preservation; A−P, A−N, and A−H curves use direct paired arrays. The publication
manifest `a6a41977a718094b6f50572f910b9378ed031af4715b475ea846083ddd546395`
matches all 14 artifact hashes and byte counts between source and destination.
The separate execution postclosure manifest
`1ce9725626be9961e2b0f9deef3b0ca46278d9a17ad742765b0995f9ab8d9a1c` matches
all 6 listed artifacts. The earlier preforecast manifest remains historical.

The standalone plot receipt binds the response SHA-256
`ab81f6866b3b5166e8f841bded1dc330f686dcf4c8c13fe38749157aaa4018ea`, plotter
SHA-256 `00ccda5f208089398e0c6815d607962afd4e414cfc996e400478ead434ac6b1d`,
all 11 saved times, four fields, six arms, both masks, and the published PNG/PDF
hashes. The plot labels the series as RMS(arm − OFF), keeps support and buffer
styles distinct, and makes no energy or observation-skill claim.

## Findings and resolution

During review, a failure-path issue was found in the history postprocessor: a
late source-pin failure could leave a `CLOSED` sidecar alongside a failed
execution. The final source tracks newly created products and removes them on
failure, preserving only a `FAILED` execution receipt. A focused regression
now forces failure after creating a CLOSED sidecar and verifies that the
sidecar is removed and cannot be consumed downstream. The recorded focused
validation receipt `b11a72d77561aac584fb35051843629e8682d5372aa6a8200fd8f4049fac445d`
reports 146 passing items with no source changes.

The A640 T0 observation sidecar is separately pinned and scoped to same-cycle
T2 input consistency. Its run receipt binds the completed A640 run and the T0
history hash, and records 21 unchanged input pins. It reports a null residual
comparison because A640 T0 T2 is bitwise identical to the reference arm. This
does not claim forecast skill; the observation docs state that no exact 13:10
LSO reports are available.

The final attribution table agrees with the integrated response: the N/A
0–600-second integral ratios are 0.984/0.985 for pressure, 1.039/1.024 for
Phi, 0.907/0.936 for W, and 0.809/0.831 for QC on support/buffer. This is a
mixed result. The amplitude-only A/P QC integrals rise by 2.81%/9.39%; there is
no uniform response ordering. Initial native RU/RV contrasts remain
descriptive only.

## Review outcome and remaining limits

No code or provenance blocker remains for the scoped PR103 implementation and
readback. Procedural completion is distinct from physical acceptance. The
generic Q/N/B audit retains 173 state-level findings among 192 retained states
(161 pair and 93 field finding rows can overlap); exact source endpoint and
active-ice policy checks pass under their existing criteria. Physical approval
remains `FAIL_OPEN`, and observation skill remains `NOT_EVALUATED`. Full-host
water/energy closure, a clean production rebuild, and transfer to other cases
remain open.
