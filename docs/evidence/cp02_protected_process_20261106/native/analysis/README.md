# Protected-process collector

`tools/cp02_protected_process_capture.py` reads only the frozen selected-column streams described by `native/schema/cp05_schema.json`.

Run it once per arm with an output directory that does not already exist:

```sh
python tools/cp02_protected_process_capture.py \
  --mode quick \
  --launch-receipt /path/to/runtime/native/quick_gate.json \
  --launch-receipt-sha256 <sealed-quick-gate-sha256> \
  --case-dir /path/to/runtime/native/cases/quick/OLD \
  --output-dir /path/to/runtime/native/analysis/quick/OLD
```

Run it once per arm with a fresh output directory. The required launch-receipt SHA binds the completed run receipt; the receipt must bind the current plan hash, mode and duration, both arm exit/success markers, and exact history parity. Use `--mode full` only for the 900-step call/surface stream and the process windows 1–360 and 721–900. The collector rejects caller-defined step subsets. Quick output is labeled `ONE_STEP_QUICK_GATE_ONLY`; it is not full science evidence.

The parser checks actual timestep/chunk names, all eight call-inventory owners, selected-state coverage and wrapper `TK=TH*PII`, surface return coverage, per-phase schema widths, frame ownership, required phase coverage, conditional phase pairing, and source arithmetic residuals. It preserves missing conditional records as NaN plus presence masks. It does not synthesize records through the uncaptured 361–720 gap.

Outputs retain the 39-level axis and include the 381 native columns, point IDs, four native corner indices and weights, and role metadata. Full mode streams three-step slabs into disk-backed arrays and emits per-channel NPZ files in actual-time blocks. The surface timeline spans all 900 steps; detailed process output uses only actual windows. The raw-stream hashes and mode-plan hash are recorded in `capture_receipt.json`.
