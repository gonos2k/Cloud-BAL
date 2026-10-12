# CP06-A joint thermodynamics–Phi and WRF initialization linkage

Source base: `624bb3d920b373430825fe64b478f8e70f0b4f1c` (PR80).
The validated modified source identities are individual hashes in the producer
and unit archives; the base commit alone is not their identity.

## Implemented path

The existing pipeline now supports an explicitly enabled background-alpha
research prior between its saturation/retrieval stage and its Phi reconstruction.
For the same pressure and five unchanged condensate mixing ratios, it targets

`alpha_target = (1 - weight) alpha_column + weight alpha_background`,

where `alpha = Rd T (1 + rv/epsilon) / (1 + sum(r_s))`.
The fixed experiment declares `weight=0.5`, a 5 K temperature increment limit
and a 0.005 kg/kg vapor increment limit before running the trial. These are
research controls, not validated observation covariances. The helper solves
T/q together where liquid or ice saturation applies. For an empty condensate
reservoir, subsaturation is permitted; vapor becomes an analysis control only
when the saturation inequality binds. It neither creates condensate nor deletes
or attenuates the retrieval condensate mixing ratios.

Phi is reconstructed from the resulting thermodynamic state. The changed dry
air fraction is then used to rebuild the continuity operator before projecting
winds and applying the existing force-prior refinement. T-dependent column
diagnostics are also rebuilt from the final state. The new analysis ledger is
separate from the internal saturation/phase ledger. The writer persists the
immediate pre-prior T/q, five condensates and dry mass; it replays the producer
and refuses a mismatched or nonfinite budget/witness. Failures roll the complete
candidate back to the immutable background. The default remains disabled.

The force refinement retains all prior external gates and tries the analytic
step first, followed by at most 20 halvings against stored REAL32 states. It
requires a strict objective decrease and never accepts a zero-step fallback.
The fixed experiment tightens its internal continuity solver fraction from
0.002 to 0.001 to leave storage/refinement headroom; the final 0.002 acceptance
gate is unchanged. The accepted actual case uses zero halvings.

## Same 13 UTC candidate: scoped results

The unchanged actual input is `2026-08-16T13:00:00Z`, epoch `1786885200`, full
235×283×22 grid. The existing masks remain fixed: material 162, saturation 69,
Phi 180, wind 500, continuity 980, and force 900 cells. This is one Intel O2
actual run; no actual-case O0/O2 byte identity is claimed.

| Quantity | Result |
|---|---:|
| PR80 final force RMS, same 900 cells | 0.006666653881 m/s² |
| Joint candidate force RMS, same 900 cells | 0.003308423595 m/s² |
| Background force RMS | 0.000653318286 m/s² |
| Candidate/background force RMS | 5.064 |
| Dry-flux prior RMS | 1.17786210324e-10 s⁻¹ |
| Unchanged final RMS gate | 2.33959149145e-10 s⁻¹ |
| Maximum total horizontal wind increment | 9.500000289 m/s; hard cap 10 |
| Prior temperature/vapor increments | 0.761077881 K / 0.000730615109 kg/kg |
| Maximum Phi increment | 71.26953125 m²/s² |

The static force RMS is about 50.4% lower than PR80 while continuity passes.
The result is still about five times the background force residual. It is not
an observation-fit, full momentum closure, or shock-reduction result.
Condensate **mixing ratios** equal their immediate pre-prior values exactly;
absolute species masses and volumetric observation equivalents can change with
the dry-mass measure. Observation inputs and their metadata remain unchanged,
but observation fit and covariance were not independently assessed.

The independent readback recomputes alpha/saturation roots, the full-domain
analysis accounting (1,294,696 above-ground cells), and force/shared-face flux
from persisted state and geometry. It does not use the stored divergence as its
flux input. The internal phase ledger is producer-replayed, not independently
rederived by this new tool. Missing separate wind-pressure coordinate and wind
observation covariance metadata remain explicit limitations.

Candidate SHA-256:
`135c2315d0953182d248ff650ad50fcab7c0b21075b208e693a04fd7f8487ef1`.
The private NetCDF is not included in the repository.

## Rejected experiments retained

The frozen specifications V1–V4 remain unchanged. V1 was correctly rejected
because retaining vapor while cooling an empty-reservoir cell violates its
saturation upper inequality. V2 adds the active inequality policy; an early
fixture compared a fresh pre-prior state to the stale prior candidate and was
corrected. A subsequent V2 actual trial still failed the unchanged force-stage
stored-state continuity gate. V3 added the bounded halving search and remained
rejected. V4 then declared the stricter internal continuity solve and passed.
The V4 specification's short V2 history does not supersede the separately
preserved later V2 force rejection. None of these rejected trials is relabeled
as acceptance, and the preserved source/log hashes distinguish them.

## WRF initialization and first-step linkage

The separate native control remains the PR80 **12 UTC** case. In its selected
cold-start source, `start_em.F` calls `set_w_surface` when `use_input_w` is false;
the pinned namelist leaves that option at its false default. The PR80 readback
shows W changing at initialization (1,476,306 values, maximum 0.6027584 m/s),
with QNCCN also initialized. An actual readback of the new nine-object
candidate confirms that same W change;
[its receipt](evidence/pr81_wrf_initialization_readback_20261012.json) binds
the candidate executable, inputs and initialization output. No namelist policy was changed merely to preserve
analyzed W. Input omega and native W do not have interchangeable meanings.
The initialized W difference alone does not identify a first-step failure.

A safe baseline replay reproduces the first `calc_ww_cp` packed-lane exception.
Selective pinned strict O0/no-vector diagnostic objects subsequently expose
an actual scalar KSAS division: `dtconv = tfac*tem/wc` for `cnvflg=false`, with
numerator -631.03125 and denominator zero. The source patch avoids both the
inactive divide and inactive cloud-index reads. Active columns retain their
formula/clamps, and active nonpositive `wc` is explicitly fatal. A focused test
extracts the patched source loop and passes at Intel O0/O2. The diagnostic
compiler options change together; success is not attributed to `-no-vec` alone.

The nine-object candidate reaches the first RK path but stops at the existing
`KDM6 invalid NC number basis input` check. The first microphysics call is still
incomplete. The policy was not relaxed and no particle floor was added. See
[the native evidence](PR81_NATIVE_FIRST_STEP_EVIDENCE_20261012.md) for exact
scope, pinned source and build/run audits, and the executable-copy correction.
The original PR80 executable was restored exactly after the early hardlink bug;
subsequent safe controls and candidates preserve all 109 source-case files.

## Validation and remaining integration

The full canonical unit launcher exits 0 once, under the pinned Intel profile,
in an external detached worktree with a frozen 23-path overlay. Its 551 src/tests
files are byte-identical before and after. The new thermodynamic helper and
force storage-feasibility fixtures pass at O0/O2; the readback fixtures pass
5/5 and native copy fixtures 2/2. Later native builder/GDB/runner changes are
outside that full-suite snapshot and have separate focused checks and runtime
audits. This is not a whole-host clean rebuild or thread-policy certification.

Evidence:
[producer archive](evidence/pr81_thermo_producer_20261012/manifest.json),
[independent readback](evidence/pr81_thermo_density_readback_20261012.json),
[rejected trials](evidence/pr81_rejected_thermo_trials_20261012.json),
[unit archive](evidence/pr81_unit_20261012/manifest.json), and
[validation receipt](evidence/pr81_validation_20261012.json).

The same-13-UTC WPS/metgrid/real/wrf_init handoff has not been run. It requires
an authentic matched background and pinned consumer configuration, then actual
post-initialization W/Q/N/B/T/q/pressure/Phi validation. The failed source predicate covers nonfinite/negative NC and conversion
overflow/underflow. The preceding density validation at the same loop cell
has already established finite positive dry density. Initial
QNCLOUD in this separate run is finite (0 to 1.5973472e9 kg⁻¹), but exact failed
call operands and coordinates were not captured. The remaining native NC
predicate needs operand/cell/stage tracing and an origin fix before accepting a
first call. Same-candidate carrier/time/domain accounting and BASE/HYDRO/COUPLED
10/30/60-minute response remain OPEN. Science approval and promotion remain
false. Graph freshness records source navigation only, not these validations.

## Structural maintenance

Selected-path Graphify/KG update is bound to frozen source `064cdda8ef989b221717651859677655e900d95f`.
Separate `2026-10-12-thermo-firststep` snapshots contain KLAPS50 35,213 nodes
(+176), 75,505 edges (+277), and Cloud-BAL 9,386 nodes (+176), 17,077 edges
(+276). The 627 active maintained source/doc/config entries, private profile,
protected wiki content, and all 110 previous immutable pins are preserved.
AST/Markdown-heading extraction does not refresh semantics; Fortran cross-file
CALL coverage is partial and six opaque selected files are hash-bound only.
[Receipt](evidence/pr81_kg_20261012.json) and
[independent review](evidence/pr81_kg_review_20261012.json) bind the compact
archive and separate derived wiki reports/index/log. Approval stays `FAIL_OPEN`;
this maintenance establishes neither runtime nor scientific acceptance.
