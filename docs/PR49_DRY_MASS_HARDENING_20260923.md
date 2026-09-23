# PR49: dry-mass identity, input pinning, and a conditional gap bound

This read-only follow-up closes two PR48 P2 findings. It does not change
retained LT1/LQ3/LSX, BALCON, WPS, or native fields. The PR47/48 receipts
remain historical evidence of their pinned source. New actual13
[dry-column](evidence/pr49_dry_mass_column.json) and
[surface-bridge](evidence/pr49_surface_mass_bridge.json) receipts bind the
current source and the same original input products.

## No-change pressure cells

The old implementation rebuilt every pressure interface from newly calculated
cell masses. Even when before/after specific humidity was identical, floating
point roundoff could shift an interface by an ulp on a nonuniform grid. The
same dry-mass model can express the width change directly:

```text
delta_width[k] = old_width[k] * (q_after[k] - q_before[k]) / (1 - q_after[k])
new_pressure[k] = old_pressure[k] + sum(delta_width[j], j >= k)
```

Here `q_before/after` are the declared endpoint-mean cell values. A cell with
identical values has exactly zero width change; its vapor mass is copied from
the original cell to avoid a separate one-ulp evaluation difference. Thus an
entire unchanged, nonuniform column retains the pressure interfaces, vapor
masses, and layer thicknesses exactly. Actual drying still moves the lower
edge upward and is not accepted by PR48's downward-edge-only comparison.
Changed-humidity results can differ by ordinary rounding from the historical
evaluation order. In the pinned actual13 column the lower edge changes by
only `1.46e-11 Pa` relative to PR47; the reported vapor increment and total
thickness are unchanged at stored precision.

## Input bytes used by the diagnosis

The dry-column and bridge drivers now hash each main JSON report from the
same bytes they parse, record those captured hashes, and check the input
paths again before writing.
This closes the old dry-receipt comparison of two aliases for the same current
file. It also checks the cloud, geometry, thickness, LSX, and geometry-array
paths at the end. A controlled actual-input run that changed the dry receipt
after parsing was rejected before output creation. These checks detect a
persistent input change during this run; they are not a general concurrent
filesystem transaction or a production writer lock.

## Necessary condition for the missing layer

PR48 measures the unsupported 10 m-to-regular-level interval but does not
assign its composition. If **all** of PS, total-column dry mass, the PR47
regular-column dry masses, and the known PS-to-p10 strip are fixed, the gap's
dry mass must also stay fixed. With gas-only pressure masses `G_old` and
`G_new`, its initial mass-weighted specific humidity must satisfy

```text
q_gap,old >= 1 - G_new / G_old.
```

In the retained column `G_old=40.727624` and `G_new=30.847854 kg/m²`.
The gap would need at least `9.879769 kg/m²` initial vapor, or mean
`q_gap,old >= 0.2425815329688` (approximately 0.242582). This is a
**necessary conditional bound**, not a measurement or estimate of the missing humidity. The supported surface
sample does not establish that gap mean. The result cannot certify or reject
a complete physical candidate until an independently supported lower profile
or changed PS/boundary/mass contract is supplied. No species, energy, or flux
is filled into the gap.

The new actual13 receipts retain `PASS_SCOPED` scope and
`surface_partial_complete=false`. They do not establish full-column
dry-mass/energy closure, physical height datum, BALCON ON, native, or forecast
authority.

Reproduce with current source, writing to fresh paths:

```sh
python3 tests/diagnose_qbal_dry_mass_column.py \
  --cloud-report docs/evidence/pr45_cloud_force.json \
  --output /path/to/new/dry.json
python3 tests/diagnose_qbal_surface_mass_bridge.py \
  --dry-report /path/to/new/dry.json \
  --cloud-report docs/evidence/pr45_cloud_force.json \
  --output /path/to/new/bridge.json
```
