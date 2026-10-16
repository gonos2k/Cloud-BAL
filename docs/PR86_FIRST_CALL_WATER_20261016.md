# Frozen v17 first-call water accounting

The research baseline is merged PR85 `743e9f28bdd9f29d039c9b671d7bd24fbfb3ffa9`.
No model equations, executable, initial Q/N/B or T/q are changed for this
accounting. Both original v17 calls completed. This document concerns the
physical-time change within each call, not the OFF–COUPLED analysis difference.

## Measure and support

The saved first-call public pre/post dumps cover 232 × 280 × 39 active cells.
The executed KDM6 DEN is dry density. DEN and DELZ are identical before and
after the call. Static mass-grid metrics come from the hash-bound initial
WRF output. For this diagnostic:

```
A[j,i] = DX * DY / (MAPFAC_MX[j,i] * MAPFAC_MY[j,i])
V[j,k,i] = DELZ[j,k,i] * A[j,i]
m[j,k,i] = DEN[j,k,i] * V[j,k,i]
ΔW = sum_s sum_cells m * (r_s_after - r_s_before)
```

Each REAL32 snapshot is promoted to REAL64 before subtraction. The same fixed
call measure is used for storage, cleanup, and transition storage residuals.
Public number is per dry-air mass and uses `m*N`; internal number per volume
uses `V*n`. Specific bulk volume uses `m*B`. These are separate inventories;
particle count is not required to be conserved through physical reactions.

There is **no same-call hybrid geometry capture** in v17. Initial MU is not
substituted for runtime MU. Consequently this diagnostic does not certify the
host hybrid dry-mass budget or reconcile Shinhong DEL to that carrier.

## Results

All table entries are kg on the stated local KDM6 measure.

| Term | OFF | COUPLED |
|---|---:|---:|
| Six-species atmospheric change | −689,721,301.863 | −689,590,306.003 |
| Source-derived bottom outflow | +689,637,510.078 | +689,506,721.803 |
| Change + bottom outflow | −83,791.785 | −83,584.200 |
| Recorded cutoff change | −43,720.262 | −43,711.228 |
| Ice→snow storage-rounding change | −13.627 | −13.916 |
| Residual after subtracting those numerical changes | **−40,057.896** | **−39,859.056** |
| Remaining residual / bottom outflow | −0.00580854% | −0.00578081% |

The bottom increment is derived from captured `fall(1:4)`, bottom DELZ, and
DTCLD using the source rainncv equation. Species order is rain, snow, graupel,
ice. The millimetre expression `fall*DELZ/DENR*DTCLD*1000` is converted to
mass per area using the same `DENR/1000`. Snow/graupel accumulators are
subsets of total rainncv and are not added again. No initial accumulator is
assumed to be zero.

The cutoff ledger records 228,034 changed rows in OFF; the transition ledger
records 7,065 branch events. The analogous COUPLED counts are retained in its
JSON. Both use actual stored changes; no idealized transfer replaces those
changes. Cutoff leaves the recorded T and vapor unchanged and is therefore a
numerical removal, not evaporation or sublimation. The transition residual
includes the event whose lost ice cannot create a stored snow increment.

The remaining residual is **OPEN**. No rounding tolerance is chosen to absorb
it. Other process storage changes, phase/cutoff details, the host carrier and
boundaries, and complete thermodynamic/precipitation energy accounting remain
to be reconciled. Initial total water is not used as the sole denominator.
No analysis increment is inserted into this physical-time budget.

### Additional stored-water terms

The separate [water-term report](evidence/pr86_water_terms_20261016.json)
reconciles additional nonoverlapping source transactions. Each `C` below is
the signed stored-water change relative to the approved transfer, with
creation positive and loss negative. The balance is `R = R0 - sum(C)`;
the sign is not reversed when a numerical change is a loss.

| Additional signed C (kg) | OFF | COUPLED |
|---|---:|---:|
| Cold stored minus approved | −3,737.465 | −3,763.466 |
| Warm stored minus approved | −19,402.238 | −19,378.939 |
| Ice sedimentation column residual | +37.539 | +33.277 |
| Graupel sedimentation column residual | +6.523 | +1.726 |
| Rain-freezing pair storage change | −0.180 | −0.180 |
| **Remaining partial residual** | **−16,962.076** | **−16,751.475** |

Sedimentation residuals already have units kg/m² and use area only.
The rain-freezing logger includes density in its kg/m³ residual and uses
`DELZ*area`, without multiplying density twice. These numerical terms do not
represent physical phase changes or withheld process mass. The residual
remains unresolved on the stated measure; this is not a complete water or
energy closure.

State validity does not imply a small first-call adjustment. On this measure,
OFF cloud water decreases by approximately 35.1% of its pre-call inventory
and cloud ice by approximately 29.2%. Vapor and other species change at the
same time; these are not losses of total water. The public ice-number
inventory also changes substantially, and its change includes native count
reconstruction rather than exclusively physical nucleation. The JSON keeps
the species and moment inventories separately. These diagnostics require
process attribution and an observation/time-response comparison before any
claim of reduced initialization shock.

## Reproduction and artifacts

```
python3 tools/pr86_water_budget.py \
  --run-root /var/tmp/pr85_same13_OFF_joint_v17_20261015a \
  --output docs/evidence/pr86_water_OFF_20261016.json \
  --map docs/evidence/pr86_water_OFF_20261016.npz
```

Use the corresponding COUPLED run root for the other arm. The tool checks
original run/capture hashes against the retained PR85 integration receipt,
validates call bounds/time, and fails on mismatched coordinates, geometry or
ledger columns. It writes column maps in native i/j coordinates, retaining
latitude and longitude arrays in each NPZ.

- [OFF report](evidence/pr86_water_OFF_20261016.json)
- [COUPLED report](evidence/pr86_water_COUPLED_20261016.json)
- [Water and numerical-removal maps](evidence/pr86_first_call_water_maps_20261016.png)
- [OFF map arrays](evidence/pr86_water_OFF_20261016.npz)
- [COUPLED map arrays](evidence/pr86_water_COUPLED_20261016.npz)

The figure uses identical scales between arms for each term. It describes
call changes, not forecast skill or proof that coupled initialization is
better. The four focused Python tests cover nonunit coordinate mapping,
promotion-before-subtraction, cancellation of an internal transfer versus an
external sink, and invalid measures. They are accounting tests, not another
Fortran/model execution. The existing successful v17 results remain frozen.
