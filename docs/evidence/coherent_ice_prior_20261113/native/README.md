# Native KDM wrapper-return evidence

This packet preserves the eight compressed rank snapshots, metadata, manifest and every context-linked verification file byte for byte. `launch.sh`, `rank_wrapper.sh`, `make_packet.py`, the run namelist, CPU affinity records, assembly receipt and coverage recount document the original run and packaging; their machine-specific absolute paths are historical, not a portable launch recipe. The manifest and context use relative references within this directory. The raw uncompressed rank binaries, assembled NPZ, WRF executable and full NetCDF files are intentionally excluded.

From the Cloud-BAL source root, assemble in a fresh directory **outside the source tree** (Python with NumPy is required):

```sh
work=$(mktemp -d)
python tools/assemble_ice_prior_snapshot.py \
  docs/evidence/coherent_ice_prior_20261113/native/manifest.json \
  "$work/snapshot.npz" "$work/receipt.json"
sha256sum "$work/snapshot.npz"
```

The reproduced snapshot SHA-256 is `0d0e9f134df4df557c3a22d74f84fc01ae8b2ffc65f7320a4bf0172437501479`. The fixed application mask selects 294,792 cells, of which 6,047 are uncovered; the full application gate therefore stops. The capture contains 2,533,440 of 2,573,532 mass-grid cells; uncovered array values are NaN. No history values fill the perimeter.

The snapshot records the first matching KDM wrapper return per rank at step 1080, not a directly observed model clock. Its nominal 12 UTC time follows the 20-second step and schedule, and the replayed full 12 UTC history matches the baseline hash. This is execution parity evidence, not independent source-to-object provenance, a proof of capture of every possible tile call, an independent NI scalar-base or density-basis audit, or scientific/forecast validation. The launch uses GDB and the historical pinned CPU setup; hashes and successful output do not by themselves establish identical runtime environments.
