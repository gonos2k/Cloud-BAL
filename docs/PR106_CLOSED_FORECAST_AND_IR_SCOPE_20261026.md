# PR106 — closed one-hour requests and the single-channel comparison boundary

The original C2 HYDRO, AMPLITUDE and STRUCTURED requests have closed. All three
are **INCOMPLETE**, model return code 1, after 38 completed steps (760 seconds),
through `2026-08-16_13:12:40`. The requested endpoint remains 14:00 / 180 steps;
it has not been shortened. Existing 640-second results remain separate.
No model, input, physics, solver, precision, tolerance or output policy changed.
No request was restarted.

## Closed results and observation gating

| Arm | Model result | Completed steps | Runner wall seconds | Main-step timing median, seconds |
| --- | --- | ---: | ---: | ---: |
| HYDRO | INCOMPLETE / 1 | 38 | 18880.794 | 476.093 |
| AMPLITUDE | INCOMPLETE / 1 | 38 | 17839.270 | 457.089 |
| STRUCTURED | INCOMPLETE / 1 | 38 | 18892.994 | 472.769 |

The cohort closed at `2026-10-26T12:03:03.397276Z`. The child CLI successfully
wrote failure receipts (CLI return code 0); that is **not** model success.
The supervisor reports no changed source pins. The receipts report unchanged
inputs/build and the same expected/executed C2 executable SHA256
`387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a`.

Independent readback verified copied/original receipt hashes, contiguous
receipt-completed steps 1–38, and each closed history hash before and after
reading only `Times`. Each history has 13 records, 13:00 through 13:12.
There is no 14:00 record. No forecast field arrays were opened by this check.
Receipt completion is not a new source-endpoint or generic Q/N/B audit.

The original observation dispatch correctly returned
`SKIPPED_NONCOMPLETE_COHORT`; the paired waiter returned
`SKIPPED_NO_COMPLETE_OBSERVATION_RESULT`. Their hash-linked receipts are
preserved. **There are no 14:00 T2 residuals, paired scores or candidate ranks.**
13:12 forecasts must not be compared to 14:00 observations as valid-time skill.

The table reports observed aggregate timings. Main-step sums are 18808.510,
17772.445 and 18826.865 seconds respectively. They do not separate microphysics,
precision, diagnostic writes or resource contention. Compression/postprocessing
and supervision times are not interchangeable with these model timings. No
causal performance attribution or output-policy change is made here.

## Shared failure event, unresolved grouped cause

All three logs contain the same T39/RK2 per-cell graupel trial rejection:

```text
PR91_GRAUPEL_TRIAL_REJECT_CONTEXT 39 2 6 4 2 219 13
PR87_GRAUPEL_TRIAL_REJECT 6 4 2 219 13 3676D01F0BF49AE5 35D9F4C29CF672CB 3746D5B76A91F326 36A9FB2054D81EE3 8000000000000000 8000000000000000
PR87 full joint moment candidate infeasible; see source/full diagnostics
```

The identical context and bits establish a shared diagnostic event, beyond
merely failing at the same elapsed time. They do not establish identical arm
trajectories: input identities and preceding mixture diagnostics differ.
Local reject reason 6 is not common-store failure stage 6. These callback
records must not be promoted to the first grouped transaction predicate.
The captured PR92 full operands permit exact source-form reconstruction.
For this cell, exact Q*/B* exceeds 900 by `20/292519627949659`; both binary64
reference bit patterns are reproduced by the ordered calculation. This is not
a valid endpoint rejected solely by conservative interval enclosure. The C2
interval conclusion is source-logic classification only: the helper itself was
not executed or compiled in this task. The
source component is itself above the upper cone, while transport terms are
signed zero. The fallback source-identity check sees nonzero recorded source
versus recomputed diffusion +0. No floor, enlarged tolerance, residual
correction or guessed physical fix is introduced. The full grouped failure
is still unresolved: the callback does not capture all transaction inputs.

## Single IR channel: source lineage versus an executable operator

The scoped lineage investigation traces one source-declared window channel:
`gk2a_ami_le1b_ir112_ko020lc_<time>.nc` → wrapper `YYJJJHHMI_11u` link →
`read_gk2a_ami` `image_pixel_values`/13-bit counts → count-to-BT LUT →
`process_ir_satellite` → `satdat2laps_ir` → `S8A`.
The actual 14Z candidate raw file exists and identifies IR112/AMI/GK-2A.
This is stronger than a legacy wavelength label alone, but does not prove its
archived production into this specific LVD without the runtime input binding.

For `r_grid_ratio < 0.5`, the source computes mean, coldest and warmest
**BT pixel** statistics in a rectangular window about navigation LUT coordinates.
The caller argument order and output labels must be traced separately: a
source-level mean/warm output permutation is confirmed at the nine original
LAPS horizontal support cells: S8A matches the twice-filtered window maximum,
and S8W matches the unfiltered arithmetic mean, exactly in the scoped Python
source replay. The A/W comments and metadata are therefore not reliable
aggregation definitions for this archived product. Otherwise the source
uses a spline branch. The saved 2 km satellite / 5 km LAPS configuration implies ratio 0.4;
that is a configuration inference, not a captured historical runtime value.
A preserved navigation LUT is available and decodes to the registered grid.
Its historical deployment and the staged calibration identity remain unreceipted;
the saved-config footprint can be tested without claiming historical identity. Warm/cold
products are not extra independent channels and are not substituted for S8A.

The NWP SAF AMI SRF table identifies IR112 in its channel 14, with central
wavelength about 11.214 microns. This external identification is not proof that
a locally installed RTM coefficient index or the historical LVD calibration
uses that exact response. See [NWP SAF AMI SRF metadata](https://nwp-saf.eumetsat.int/downloads/rtcoef_info/visir_srf/rtcoef_gkompsat2_1_ami_srf.html).

The bounded environment search found legacy NCEP RTM code and external CRTM
2.3.0 source, but no validated runnable GK2A forward path with matching
coefficients. Required NCEP test coefficient/profile files and the searched
CRTM coefficient/build artifacts are missing. Broadband RRTM/RRTMG files do
not supply the sensor operator. The pinned Intel compiler profile itself is
available and verifies; an unsourced shell's `command -v` result is not evidence
of compiler absence. No substitute compiler or synthetic BT calculation was used.

Thus a same-time forward comparison is blocked independently by the missing
14Z model endpoint and by the unfinished sensor/coefficient/footprint binding.
Data availability at the original 16 columns and 196-column buffer remains the
PR105 result; it is not radiative or cloud skill. The next operator needs the
actual observed aggregation and sensor response, valid atmospheric/surface
profiles and viewing geometry, and must leave H/A/N states unchanged.

## Evidence and remaining work

`docs/evidence/pr106_closed_forecast_20261026/` preserves the closed cohort,
three model receipts, skipped dispatches, bounded failure excerpts, reproducible
`verify_closed.py` and its actual output. Source-level channel and environment
investigations are included separately. Root reruns of both local replay
scripts match the agents' result files byte-for-byte: the exact per-cell
callback arithmetic and nine-cell S8A/S8W reproduction remain distinct checks.
Neither is a compiled native replay or a model-to-satellite forward calculation.
The satellite translation omits a prefilter BT range screen; peer review checked
that all QC-valid pixels in this granule are finite and 205.72–295.48 K, within
the source 81.85–330.05 K limits. The omitted screen is a no-op for this input,
not a claim that the script is a general ingest replacement. The first verifier invocation used an
incorrect history parent directory and stopped before field reads/output;
the corrected read-only verifier resolves the runner's `run/` directory and
emits `CLOSED_INCOMPLETE_CONFIRMED`. The model requests remain incomplete.

The useful next execution work is a source-bound local replay of the first
grouped rejection, not another unchanged hour-long request. Any subsequent
model-policy change requires matched controls. The useful satellite work is
one exact channel/calibration/navigation binding and a genuine offline RTM,
not empirical cloud correction or a Planck-only proxy. Full host water/energy,
mass–wind/initial-adjustment approval and independent observation skill remain
**OPEN / NOT_EVALUATED**.

KG session maintenance records this work without rebuilding the graph. No
maintained production code changed; evidence scripts are outside the maintained
extraction corpus. PR105 graph snapshots/reports/index remain untouched. PR106
documents are not indexed, so graph freshness for this work is PARTIAL / NOT
UPDATED and extraction delta is N/A. Graph navigation is not execution or
scientific approval.
