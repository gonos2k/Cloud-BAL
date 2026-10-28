# CP02 inner capture analyzer review

**Result: GO, no blockers.** Final frozen analyzer/tests reviewed independently.

## Exact reviewed files

- `docs/evidence/cp02_inner_capture_20261028/analyze_inner.py`
  - SHA-256: `cb6f13aa0fb4d5d694ddf239683f0f9cadd06dc3da64cbdbafbd59c058cd3e83`
- `tests/test_cp02_inner_capture.py`
  - SHA-256: `1949050ad19b95bcef8a13b9c7d3682f4060a10a0acef4b955f3e7d6fc7f2b83`

## Independent validation

- `pytest -q tests/test_cp02_inner_capture.py`: **12 passed**. The final suite covers event order, missing/orphan events, LIQUID call-number swaps, invalid addresses/levels, and prior-capture mismatch behavior. This resolves my earlier note about missing event-order mutation coverage. The follow-up changed-count correction is also covered: unpaired REAL*4 state rows carry null/blank changed_count, while paired candidate pre/post rows report their actual state changes.
- H end-to-end analyzer against the final capture and prior outer capture: `SCOPED_PASS` (`/var/tmp/cp02-inner-review-hydro-final4.json`).
- L end-to-end analyzer against the final capture and prior outer capture: `SCOPED_PASS` (`/var/tmp/cp02-inner-review-liquid-final4.json`).
- Output summaries and CSVs were written under `/var/tmp`; existing artifacts were not overwritten.

## Record-level review

- H arg10 ABI qwords are raw zero pointers; frame reads remain unresolved/unreadable. The analyzer keeps those facts separate and makes no semantic optionality claim. All six L arg10 pointers match readable DWARF evaluation-state addresses.
- H caller brackets have matching caller-frame and workarray addresses, selected point keys, and level order. Publish candidate storage binds to the same nonzero address before/after.
- The publish PRE candidate state matches the first derive input at all selected samples for all eight fields (zero raw32 differences). The publish POST workarrays convert exactly to the candidate POST state from REAL*8 to REAL*4 for all 440 samples in rain, snow, and graupel (zero byte mismatches each).
- Diagnose changed 154 rain and 36 snow samples; graupel was unchanged. Transport and publish workarrays were unchanged across their caller brackets. The CSV labels REAL*8 workarrays separately from REAL*4 state and includes call number and role.
- LIQUID coverage is explicitly `not instrumented`; the empty internal-boundary set is not presented as zero actual calls.
- The outer state matches the prior capture bit-for-bit at both checked endpoints in both arms.

Scope remains selected debugger evidence only: no domain-wide conservation, full-grid budget, or forecast-cause conclusion.
