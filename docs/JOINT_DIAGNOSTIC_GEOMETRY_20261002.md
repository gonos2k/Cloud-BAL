# Final candidate diagnostics: numerical and physical scope

## Problem

Required final-state diagnostics must not depend on whether a wind correction
is authorized or has an omega target. Those conditions select controls; they
do not define the physical grid on which the final candidate is evaluated.
The diagnostic and control paths therefore share pressure-interface, partial
face, interpolation, and metric calculations, but select their support
separately. Diagnostic evaluation does not grant additional change authority.

This branch also integrates the already reviewed PR55–PR58 ancestry into
`main`. Their earlier feature-branch merges did not put that ancestry on
`main`. The new changes build on their stored assessment and mask receipts.

## Interior hydrostatic residual

For the six dry-air mixing ratios in canonical species order, use the same
state relation as the existing geopotential increment:

\[
\rho_d=\frac{p}{R_dT(1+r_v/\epsilon)},\qquad
\alpha=\frac{p}{\rho_d(1+\sum_s r_s)}.
\]

For adjacent pressure centers, with pressure decreasing in the vertical,

\[
R_{\Phi,k}=\Phi_{k+1}-\Phi_k
 -\frac{\alpha_k+\alpha_{k+1}}{2}\log(p_k/p_{k+1}).
\]

The signed residual has units `m2 s-2`. It measures the represented interior
thickness relation; its sign and spatial distribution remain available.
An RMS or domain sum alone can hide compensating local errors.
The existing increment preserves the background residual, so a successful
increment does not imply an absolutely hydrostatic initial column.

No universal zero-residual threshold is imposed. Hydrostatic applicability
and its physical uncertainty depend on the regime. Nonhydrostatic convection
can have a physically required vertical acceleration. The surface anchor is
outside this interior assessment: a complete surface composition and datum
must be independently declared before evaluating that boundary relation.

Both endpoint species must be represented, usable, on the declared dry-air
basis, and at the same valid time. Missing hydrometeor storage or support is
not silently interpreted as zero. Unassessable layers retain explicit reason
flags and cannot count as zero physical residuals.

## Remaining mathematical conditions

An endpoint identity records a change; independently specified sources and
physical-time boundary fluxes decide whether that change is permitted.
Copying the endpoint into its own source would make the constraint vacuous.
The existing five-field iteration is a stored-value fixed point. It does not
establish feasibility of all physical constraints or stationarity of a joint
objective. Background/observation error models and their correlations must
define that objective before reporting a constrained optimum.

## Native microphysical initialization

A separately tested research patch selects the private KDM6 source
constant `rho_mid=400 kg m-3` as an explicit missing-volume prior:
`QIB = QGRAUP / 400 kg m-3`. The CP01 execution record documents that
choice; the unmodified routine does not initialize QIB from this constant. The retained startup executable did not
apply that prior. The literal source divides graupel mass by QIB before
clamping density: the positive-mass/zero-QIB probe traps with pinned Intel
`-fpe0`; the nontrapping probe reaches a clamp-derived 900-density state.
Neither behavior defines the 400-density initialization policy, and neither
is a full first-call test of the current candidate.

The selected source has a named CCN initialization profile, but no equivalent
startup initializer for cloud, ice, or rain number. Number thresholds and
particle-size bounds gate calculations using existing moments; they do not
identify an initial particle distribution. In particular, mass alone fixes
neither particle number nor radar reflectivity. These three moments require
a declared producer or a separately specified particle-distribution prior
with uncertainty and sensitivity evidence. A later model timestep is not a
substitute for those initial moments.

The historical periodic 20-second native capture completed under a
separately declared private zero-volume patch using a 900-density fallback.
Only its CCN profile was independently reconstructed; it was not a per-field
first-call trace, and its reflectivity history contained nonfinite values.
That capture, kernel prior tests, and current pressure diagnostics are
separate evidence scopes. None
demonstrates a current coupled candidate's first-call response or reduced
0–60-minute startup shock. The execution checklist retains those gates.

## Validation record

### Current producer execution

The current LAPSPREP producer was rebuilt with the pinned Intel O0 profile
and ran BASE and `LIQUID_RADAR_RH1_PHI` against the same copied NE57 input,
shared configuration and runtime, for 2026-08-16 12 UTC (`262281200`).
The experiment selector and output paths differ explicitly. Wind correction
is disabled by the preserved configuration; changed-domain diagnostics still
evaluate the final state using the same LW3 background omega read. The latter is
a liquid research approximation, not a joint constrained optimum or native
KDM6 equilibrium. No external omega driver was introduced.

The input snapshot contains 122 regular files (470,989,067 bytes). The BASE
WPS bytes reproduce the preserved baseline exactly. The candidate completed
and its 235 WPS records were checked against its own same-run SHADOW values.
Exact input, build, runtime and product identities, verifier results, and
remaining dispositions are recorded in
[evidence/pr59_current_lapsprep.json](evidence/pr59_current_lapsprep.json).
Compiler process closure and upstream analysis-generation lineage were not
established by this ordinary producer build.

On the fixed requested domain, 189,957 continuity cells were assessable:
RMS `8.109281132364312e-5 s-1`, maximum `0.00232086703247293 s-1`.
Only 189,921 requested cells supported geostrophic evaluation; the incomplete
coverage remains unassessed, not a zero residual or a physical pass.

Of 190,054 requested interior layers, 180,756 had usable background and
candidate T, geopotential and all six species; 9,298 were unsupported.
On that identical common domain, candidate hydrostatic residual RMS/maximum
were `14.286910087876636 / 149.67250051910924 m2 s-2`; background values were
`14.286914617622651 / 149.67355409228367 m2 s-2`. Candidate minus background
residual RMS/maximum were `0.0015249400412604985 / 0.013108587852912024 m2 s-2`.
These measurements show the approximate increment nearly preserves the
existing background residual; they do not demonstrate absolute hydrostatic
balance or reduced startup shock. No physical threshold was fitted to them.

### Failures retained and corrected

The first current-producer attempt failed during SHADOW serialization of a
large logical-mask expression passed directly to NetCDF. No candidate WPS
was created. A sequential, allocated int32 mask buffer now avoids that stack
temporary and preserves the existing rollback path. The rejected receipt
and incomplete product remain separate from the complete rerun.

Independent readback also exposed two schema mismatches. A fixed geometry
mask includes the reader's static-terrain constraint, so comparing it with
`p <= PSFC` loses that constraint. The hydro receipt now compares with the
root canonical mask, or the explicit candidate mask for a domain transition.
The writer's optional cloud-analysis provenance is validated as a complete
versioned bundle instead of requiring its presence flag always to be zero.

### Verification and scientific limits

Pinned Intel O0/O2 manufactured constraints, hydrostatic increments, shared
balance operators, partial faces/adjoints and pipeline authority tests pass.
The signed hydrostatic receipt is independently replayed; mutations of local
residuals, summaries, support, metadata and declarations are rejected.
Northern and southern Lambert inverses match isolated pyproj 3.7.1 / PROJ
9.5.1 tests; the southern sign fix retains the northern formula.

The full SHADOW writer/reader suite passes with pinned Intel O0/O2, including
full NE57 writer execution, exact O0/O2 output comparison, legacy schemas and
malformed input/receipt rejection. Final log SHA256:
`ffa8a58d07f427a25a5b75c5d94648f8fbd1f0bbf559ed7e0c379f69eeb4cd78`.
The current-producer standalone validator reports no failures and independently
replays the hydrostatic assessment; its engineering decision retains the
trajectory assumption and no scientific approval. The isolated snapshot passes the trusted verifier, but generation publication
stops at the filesystem's unsupported atomic no-replace rename. No generation
or current pointer was created. Its dirty source is recorded by exact hashes;
the base HEAD is not claimed as the modified code identity. The artifact
remains UNBOUND. These dispositions are recorded in the execution receipt. Team review precedes the PR. Graph snapshots
are maintained separately for KLAPS50 and Cloud-BAL; Fortran cross-file CALL
extraction remains partial, and graph freshness establishes navigation only.

The independent source/boundary conservation contract, full objective and
joint optimality, omega/native mapping, three missing number-moment priors,
current-candidate KDM6 first call and BASE/HYDRO/COUPLED startup comparison
remain open. This research run changes no operational generation and grants
no physical initialization approval.

WRF's native hybrid dry-pressure coordinate and staggered wind locations
require their own consumed-state assessment ([WRF Dynamics](https://www2.mmm.ucar.edu/wrf/site/users_guide/dynamics.html)).
Lambert's northern and southern middle-latitude domains are documented by
[PROJ](https://proj.org/en/stable/operations/projections/lcc.html).


Team review found no unresolved implementation blocker after correcting the
NaN-safe alpha checks, group declaration/support identity and optional cloud
presence semantics. Python validator/cloud tests, compile checks, shell syntax
and `git diff --check` pass. Native scientific gates remain open as listed
above; neither receipt structure nor floating-point agreement closes them.
