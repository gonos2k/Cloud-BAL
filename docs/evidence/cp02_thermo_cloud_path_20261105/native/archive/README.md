The `../capture` directory preserves the exact selected-cell diagnostic streams
used by the full analyzer. `publication_receipt.json` binds every original
stream's SHA-256 and byte count to its ordered compressed parts, the full
analysis receipt, and the analyzer's exact input inventory. Parts are at most
85 MiB. To reconstruct a stream, concatenate its `part_0000`, `part_0001`, …
files in order and decompress the combined gzip stream, for example:

```sh
cat ../capture/B1/cp04_rank3.bin/part_* | gzip -dc > cp04_rank3.bin
sha256sum cp04_rank3.bin
```

Compare that SHA-256 with the corresponding `source_sha256` in the publication
receipt. These are byte-for-byte selected native streams, including missing
conditional records; no absent process record is replaced by zero. First-call
full-domain streams are retained outside Git and inventoried by hash in
`../runs/external_global_streams.json`. The executable and whole history files
are external runtime artifacts, with their hashes and comparison receipts in
`../build` and `../runs`.
