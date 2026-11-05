# Grouped PH operation proof bundle

This bundle packages the minimal native evidence for the single-expression PH grouping change. It excludes executables, object/archive/module binaries, model inputs, and model outputs. Original runtime paths and hashes are recorded in `bundle_manifest.json`.

`PH_GROUPED.patch` is the only model-source delta: it groups `(PHnext-PH)+(PHBnext-PHB)` before division. Build receipts and disassemblies identify the independently compiled OLD_SHAM and GROUPED binaries. Capture JSONL/GDB/rank logs and receipts cover the first captured phi call at target `p=20183, i=144, j=142, k=4`, owner rank 5, vector lane 2 for OLD_SHAM/B1, GROUPED/B1, and GROUPED/DM065.

The B1 operation receipts are retrospective replays over preserved complete captures: original capture runner identity is distinct from the later validator identity. The earlier validator rejection is preserved under `failures/`; the raw captures were not modified. The DM065 operation capture ran with the final frozen capture runner. These are operation-attribution captures, not 6-hour forecast validation or scientific qualification.
