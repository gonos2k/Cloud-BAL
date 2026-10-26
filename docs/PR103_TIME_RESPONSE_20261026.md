# PR103 all-saved-time response

This postprocessor adds time summaries to the closed PR102 five-arm history
readback. It does not run the model, reopen histories, or modify the frozen
PR102 response products.

## Definition and scope

For each fixed field, region, and arm, `E_X(t)` is the saved-reader RMS of
`arm X − OFF`. The schedule is frozen at all eleven saved times from 0 through
600 seconds in 60-second increments. The original 613-cell support and
39-level, 196-column buffer are validated by their published counts. Fields
retain their source units: pressure (Pa), geopotential (m²/s²), vertical
velocity W (m/s), and QCLOUD (kg/kg dry). H is HYDRO, C is COUPLED, P is the
projected arm, and N is STRUCTURED. OFF is included as the zero reference.

The primary time summary is

`I_X = (1 / T) × trapezoid(E_X(t)², t), T = 600 s`.

Thus `I_X` retains the field’s squared units; it is not energy. The output also
records each saved maximum and all tied times, the 0-second and 60-second
endpoints, and the raw 0–60-second trapezoid area. The first segment has only
two snapshots (0 and 60 seconds), so it supports no high-frequency claim.
Schedule, fields, units, masks, and arm/control pairings are checked before
calculation; no time or mask is chosen based on the response. RMS summaries
cannot be combined to infer arm-minus-H distances, so H is retained as an
independent arm series.

There is no observation or reference-truth claim. Physical approval remains
`FAIL_OPEN`; observation skill remains `NOT_EVALUATED`.

## PR102 readback summary

The table gives `I_0_600` for H/P/N=HYDRO/PROJECTED/STRUCTURED and the N/P
ratio, separately on each fixed region. Complete C, OFF, saved maxima, 0–60
metrics, and all per-time RMS values are in the JSON evidence.

| Field | Region | H | P | N | N/P | Units |
|---|---|---:|---:|---:|---:|---|
| Pressure | Support | 594.631634 | 702.246010 | 646.945815 | 0.921252 | Pa² |
| Pressure | Buffer | 94.743944 | 105.132705 | 99.819925 | 0.949466 | Pa² |
| Geopotential | Support | 483.374849 | 473.859172 | 464.395025 | 0.980028 | (m²/s²)² |
| Geopotential | Buffer | 79.906205 | 79.320115 | 77.894023 | 0.982021 | (m²/s²)² |
| W | Support | 0.0257884 | 0.0565055 | 0.0372879 | 0.659898 | (m/s)² |
| W | Buffer | 0.00400609 | 0.00678353 | 0.00509144 | 0.750559 | (m/s)² |
| QCLOUD | Support | 2.52649×10⁻⁹ | 2.82005×10⁻⁹ | 2.34690×10⁻⁹ | 0.832219 | (kg/kg dry)² |
| QCLOUD | Buffer | 4.02757×10⁻¹⁰ | 3.73648×10⁻¹⁰ | 3.39623×10⁻¹⁰ | 0.908938 | (kg/kg dry)² |

The integrated ratios vary by field and region. For example, support geopotential
`I_N` is 464.395, below H at 483.375, while at the 600-second endpoint the N
RMS difference is above H (8.790 versus 4.439 m²/s²). These time summaries do
not give an invariant ranking.

The first-segment `I_0_60` ratios N/P are 1.083015 for support geopotential,
1.004522 for support W, and 1.120819 for buffer QCLOUD. Buffer QCLOUD is below
P at 600 seconds despite its larger first-segment mean square. For QCLOUD, the
saved maxima for H/P/N all occur at 0 seconds in both regions; this is the
shared nonzero initial contrast, not a later transient peak. Other maxima also
depend on field and region: support N pressure peaks at 60 seconds, while
support N geopotential and W peak at 0 and 120 seconds respectively. The full
peak values and tied times are retained in JSON.

For example, support N W has saved maximum 0.263846 m/s at 120 seconds; its
0–60 endpoints are 0 and 0.239630 m/s. Its first-segment mean square is
0.0287112 (m/s)² and raw trapezoid area is 1.72267 (m/s)²·s.

## Provenance and rerun

The postprocessor read
[`fivearm_history_readback.json`](evidence/pr102_execution_20261025/fivearm/fivearm_history_readback.json)
and verified its SHA-256 against the COMPLETE five-arm execution manifest.
It also recorded before/after pins for the five-arm readback and execution,
plus the frozen PR102 response, execution, and publication JSONs. The extracted
reader is pinned in that manifest as
`/var/tmp/pr102_fivearm_history_readback_v2_final_20261025.py` with SHA-256
`b7ea35ac1ddd6bdc9d1b87ce6cb7ff39e1bac22c8f91f4de6bec32717685a3b1`. No
source artifact changed during postprocessing.

- [All-saved-time metrics](evidence/pr103_time_response_20261026/allsavedtime_response.json)
  (SHA-256 `5b7550bbde89d1cbe1182295167ad80c36fc7e95843f3683a2226ddf38bc8f6b`)
- [Source and code pins](evidence/pr103_time_response_20261026/source_pins.json)
- Reader: [pr103_time_response.py](../tools/pr103_time_response.py)
- Focused fixtures: [test_pr103_time_response.py](../tests/test_pr103_time_response.py)

Reproduce the saved-data calculation with:

```sh
python3 tools/pr103_time_response.py \
  --input docs/evidence/pr102_execution_20261025/fivearm/fivearm_history_readback.json \
  --receipt docs/evidence/pr102_execution_20261025/fivearm/execution.json \
  --output /var/tmp/pr103_time_response_allsavedtime_rerun.json
```

The CLI requires the PR102 five-arm receipt to report `COMPLETE`, task
`fivearm`, return code 0, and the exact readback SHA-256. RMS values must be
finite and nonnegative. Output creation is exclusive: choose a new path for
each rerun; an existing result is preserved and the command fails.

The focused fixture tests cover nonuniform timestep integration, schedule and
coverage errors, missing and duplicate entries, nonfinite and negative RMS,
unit and shape mismatches, nonzero execution return codes, output overwrite
refusal, and an explicitly receipted A arm. An A readback must
use the same schedule and a `pr103_closed_history_readback_receipt_v1` receipt
binding its path and SHA-256, the explicit closed AMPLITUDE model-run receipt
path and SHA-256, all 11 snapshot paths, SHA-256s, and record indices under that
run's `run/` directory, and the fixed proposal, candidate, executable,
boundary, namelist, and time schedule. Snapshot records may refer to one file
or separate files; each file is hashed once and must be listed in the model
receipt. The model receipt must show COMPLETE, return code 0, step 32, and no
fatal, processing, or input-change errors. A−P/N/H curves are included only when that receipt explicitly names
the pair and the readback supplies native paired RMS values at every saved
time; no pairwise RMS is reconstructed from independent arm-minus-OFF series.

The five-arm saved-data calculation above used no compiler or new model
integration. It establishes postprocessing arithmetic. The separately completed
A640 run and its six-arm readback are recorded below; scientific approval
remains open.

## Closed A history integration

[`pr103_history_response.py`](../tools/pr103_history_response.py) read the closed
AMPLITUDE 640-second run, which completed with return code 0 and 32 steps. It
verified the preserved H/C/P/N−OFF metrics against the actual closed C2 arrays,
then added A−OFF and direct array A−P/N/H RMS values at
the same 11 saved times. It integrates those series through this module's fixed
trapezoid calculation. Pairwise RMS is always computed from the paired native
arrays; it is never derived by subtracting independent RMS metrics.

The postprocessor required a fresh output directory. Its argv, source and data
pins before and after reading, closure receipt, and output hashes are recorded
in the [postclosure supervisor receipt](evidence/pr103_time_response_20261026/postclosure_A640_20261026/supervisor_execution.json).
The bounded [publication manifest](evidence/pr103_time_response_20261026/postclosure_A640_20261026/publication_manifest.json)
lists the readback, integrated response, receipt chain, summary table, and plots.

The N/A ratios of the 0–600s mean-square integrals vary by field and mask. On
support they are 0.984 for pressure, 1.039 for Phi, 0.907 for W, and 0.809 for
QC; in the buffer they are 0.985, 1.024, 0.936, and 0.831 respectively. The
summary table records each arm's I0–600, I0–60, saved-maximum times, and
600-second endpoint; its JSON also gives maximum magnitudes and 0/60-second
endpoint values. Direct A−P/N/H rows give the corresponding native paired
array metrics; they are not derived from RMS subtraction. Early-segment,
saved-maximum, and 600-second endpoint comparisons differ by field and mask,
so these descriptive summaries establish no general N or A ordering. The
0–60-second interval contains only the 0- and 60-second snapshots and supports
no high-frequency claim. See the full [N/A and direct-pair table](evidence/pr103_time_response_20261026/postclosure_A640_20261026/allsavedtime_summary.md).

The same reader can be invoked with a new fresh directory if this closed run
is postprocessed again:

```sh
python3 tools/pr103_history_response.py \
  --a-run-root /path/to/closed/AMPLITUDE_RUN \
  --output-dir /var/tmp/pr103_sixarm_history_response_fresh
```

It validates the COMPLETE/rc0, 32-step A receipt, the candidate-bound 640
preflight, same-run history files and exact 0..600s timestamps, then emits a
closed readback receipt binding the model receipt, preflight, proposal,
candidate, executable, boundary, namelist, and each time record. A single
history file may supply all 11 records; each file is hashed once. Existing
five-arm results remain immutable. If analysis fails, it removes only output
files created in that fresh directory and leaves a FAILED execution receipt;
it never leaves a CLOSED sidecar from an incomplete analysis. The actual
readback completed with all 656 source/data pins unchanged. Fixture tests
separately check arithmetic and rollback; they do not establish forecast skill.

The standalone plotter rendered the completed six-arm response without reading
model histories again. It can be reproduced in a fresh directory with:

```sh
python3 tools/pr103_history_response_plot.py \
  --input /path/to/closed/allsavedtime_response.json \
  --output-dir /var/tmp/pr103_sixarm_plot_fresh
```

It writes [PNG](evidence/pr103_time_response_20261026/postclosure_A640_20261026/pr103_sixarm_alltimes.png)
and [PDF](evidence/pr103_time_response_20261026/postclosure_A640_20261026/pr103_sixarm_alltimes.pdf)
panels for all four fields, all 11 saved times, and both fixed masks. Solid
lines show support; dashed lines show buffer. OFF stays at zero. The chart
covers only saved 0..600 seconds and keeps the original field units; it makes
no energy or observation-skill claim. Physical approval remains FAIL_OPEN and
observation skill remains NOT_EVALUATED.
