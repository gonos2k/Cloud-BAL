# PR102 archived consumer driver review

- Reviewed driver: `tools/pr102_archived_consumer.py`
- Driver SHA-256: `7b702f443073fee219d9e0e2c1940ce3185bc5ad6fe35e0653b6287228ac97a1`
- Scope: source review only; no native call executed.
- Decision: **BLOCK pending two provenance-pin fixes.**

The call construction is otherwise bounded as intended: the retained standalone
executable, IFX profile, MPI setup, archived member proof, C1/C2 build receipts,
canonical HYDRO WW hash, staged input, and the producer source are checked. Each
arm gets a new scratch directory; return code, finite active WW array, zero
bottom/top faces, and unchanged input/staged bytes are checked. The candidate
result is marked `COMPLETE` only for this native call, while the aggregate
explicitly keeps `physical_approval` at `FAIL_OPEN`.

Before native calls, fix these provenance gaps:

1. `pr86_time_response.py` is imported as `runner` and supplies the `sha256`
   function and `_wind_structure_input_binding` used by this driver, but its
   source path is absent from `run_case`'s before/after `bindings`.
2. The proposal receipt is read once to derive artifact rows, copied to the
   output directory, and hashed only after both calls. Pin its bytes before
   deriving the binding; require the source proposal and staged copy to retain
   that same hash through completion.

These changes do not alter the candidate or physical policy. Re-review the
driver and its new SHA before any archived consumer calls. This review does not
authorize or imply any 20-step/640-second WRF gate.
