# D2 packet reproduction

The corrected packet is regenerated from the archived seed, raw ledgers, and
receipts with:

```sh
python capture_t7_packet.py t7_target_packet_seed.json warm_ledger.raw.gz \
  producer_trace.raw.gz build_receipt.json run_receipt.json /tmp/t7_packet.json
cmp t7_target_packet.json /tmp/t7_packet.json
```

The parser validates the interleaved BG/T/QV/CCN before/after field order,
checks all 13 warm-state fields against both trace snapshots, and requires each
E24.16 decimal interval to identify a unique source REAL32/REAL64 value. The
result binds the parent physical KDM source separately from the compiled D2
KDM source and its build receipt.

The area-weighted prefix reexecution and its units, coverage, and scope are
documented in [`science/README.md`](science/README.md).
