# PR71 team resolution — 2026-10-08

Base: merged PR70 `0ef49d1770db6d9ed0d35f60e35dcbd5d3e0db15`.
This is a selected-source research change. Overall physical initialization
approval remains **FAIL/OPEN**.

## Changes and their scope

The process-fraction description now promises a conservative valid float32
fraction within computed continuous admissible intervals. The original
algorithm and physical tolerances are unchanged. Pinned Intel O0/O2 reproduce
the reported neighboring valid fraction; no global float32 maximum is claimed.
See [fraction scope and fixture correction](PR71_CONSERVATIVE_FRACTION_20261008.md).

The particle-property contract defines all 18 `ProgB_param` outputs and
classifies the current QG/BG pair. Exact absence has defined neutral outputs;
these placeholders do not authorize a particle-property calculation. Every
one of seven call paths passes the status to the following slope calculation.
Unsupported or transient states terminate before consuming invalid properties.
Terminal extinction also invalidates property-derived diagnostics.

Raw QG/BG outside the selected 100–900 kg/m³ interval is rejected rather than
using the legacy density clamp and BG rewrite. This changes research admission
behavior. It is not a proof that the physical density interval is universal,
or a semantics-preserving repair for every legacy input.

## Why physical approval remains open

The existing freezing rule creates QG and BG using a material density of
1000 kg/m³. The property table admits 100–900 kg/m³ and excludes some tiny
pairs from its active branch. No source-backed replacement generation,
transient growth/sublimation or extinction policy was identified. Explicit
status and rejection expose this mismatch; they do not supply the missing
physical transition. See [freezing-domain audit](PR71_FREEZING_DOMAIN_AUDIT_20261008.md).

Completed host transport still requires dry-carrier, PBL/RK, Q/N/BG and
boundary accounting. Water and energy closure, an actual joint mass/wind
candidate and its native time response are separate unfinished gates.
The all-hydrometeor-absent full-module attempt also exposed an inherited
ice-intercept division by zero; its failure is retained and not counted as
a passing property-contract test.

## Validation and execution identities

The final composed selected-source SHA is
`6245969c87f6568cad3b6c6afddc0d1bdfe84a31baa1cee10a465b663c88d716`.
Pinned Intel O0/O2 whole-module comparisons pass for four unit-density fixtures
and an EOS-consistent active state. The EOS graupel-absent fixture remains
BLOCKED at the inherited zero-ice `n0i` division; it is not a passing absence test.
The focused exact-absence slope and diagnostic branches are separate evidence.

The fresh partial-host native execution rejects at the ice count guard:
`i=107, k=5`, rate `829940373.290303 s^-1`, `dtcld=20 s`. The numeric
argument exceeds default-integer representability and is rejected before
`NINT` and the dependent ice loop. All 100 staged inputs retain their hashes.
Required post-call outputs are missing, so no accepted endpoint or budget
closure exists. The retained host objects and external libraries prevent a
complete clean-host claim. See [integrated execution](PR71_INTEGRATED_EXECUTION_20261008.md).

The original PR70 volume observer, PR71 v1 bounded timeout, PR71 v2 stopped
diagnostic observation, and final guarded rejection are distinct executions.
The first guarded runner also produced a misclassified receipt because the
Fortran diagnostic wrapped across lines. Its receipt is preserved; the
corrected multiline parser and fresh run have separate evidence. Controlled
termination does not roll back preceding updates.

## Additional observer finding

The PR68 velocity split left the PR67 stage-0 observer writing legacy
`work1(:,:,4)`, although that channel has no assignment in the composed
source. It has no remaining model consumer, but serializing undefined data
is an implementation defect in the observer. Its historical values are
untrusted and cannot establish an ice velocity or substep count.

The default selected-source output-contract patch replaces that write with the actual named
`mass_velocity_rate(:,:,4)` in s⁻¹ and adds measured substep diagnostics.
This changes the recorded field's meaning and observer identity; it does
not change the physical transport calculation. Historical streams remain
preserved. Stage record existence identifies a written checkpoint, not the
routine currently executing.

## Review and remaining work

The four-agent review covers output consumers, freezing-domain policy,
same-source integration/native lineage, and independent arithmetic/evidence
checks. The [ordered checklist](PR71_PHYSICAL_CLOSURE_CHECKLIST_20261008.md)
keeps resolved implementation items separate from physical completion.
Review found and resolved the undefined observer field, signed integer
conversion hazard, composer output preflight, test harness coefficient/basis
comparison issues, and native runner import/multiline-parser issues. The
conservative fraction reproduction and the final guarded composition were
independently checked. No additional implementation blocker remains for
publication as a research change; the scientific OPEN items remain unchanged.

Historical PR70 receipts, maintained native source and operational inputs
are preserved. Graphify navigation and the later separate KLAPS50/Cloud-BAL
structural updates do not establish runtime or scientific validation.

## Integer guard and unresolved physical rates

The guard checks both liquid and ice count expressions. Nonfinite inputs,
nonpositive timestep, multiplication overflow and out-of-range signed NINT
arguments reject before conversion. Accepted arguments use the original
expression, including finite negative-rate minimum-one behavior. No rate
floor/cap, CFL limit, maximum loop policy or density substitution was added.

The diagnostic observation measured an extreme number rate at `(i=78,k=2)`
and a separate maximum stored step result at `i=149`. Their causal relation
was not captured. The final guarded run instead rejects its first offending
point `(i=107,k=5)`; source construction alone does not explain the physical
cause of these extreme rates. That investigation is the next gate.

## Evidence corrections

The new rain fixture uses the source Gamma coefficient `cmr*24` for
`mur=1, dmr=3`. The inherited PR70 fixture used 6, so its claimed lambda
5000 was actually approximately 7937; its conversion comparison remains
historical evidence, and its arrays and receipts were not rewritten.
Configured source-test entrypoints pass. A root attempt at generic unittest
discovery lacked the required source environment/CLI arguments and failed at
setup; it is not a numerical or whole-suite result.

Old property/count patches and failed or incomplete runs are preserved with
their original source identities. Final checks bind current files separately
from these historical receipts. No scattered scoped PASS is combined into a
full-suite PASS, native acceptance, or scientific approval.
