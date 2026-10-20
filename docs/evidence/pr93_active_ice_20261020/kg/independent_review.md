# PR93 KG post-apply review

**Result: PASS; no preservation or publication blockers found.** This review is
read-only with respect to source, runtime evidence, graphs, and wiki content.

## Guarded apply and source binding

- The private apply receipt is `PASS`, bound to frozen source commit
  `475062cc04deb42af8f008aa2901e69383d23d08`, PR #93, base
  `984cbf9a3b658c218448912d6b3e25100d72e1f3`, and PR92 receipt SHA-256
  `0cee86c3128b49b1317c4107537c3fd92470e819e409fc7d7ec332fbfd790030`.
- The apply helper hash matches the pinned
  `ac1b58b00227aa2a3e15e8567b3a6c3cc21815fb38fd533be14c539ce1e462af`.
  The final check plan is `CHECK_ONLY_NO_WRITES` for the same commit and PR.
  GitHub reports PR #93 open at that exact head. The source checkout HEAD is
  frozen; its only current untracked addition is the expected bounded KG
  publication directory.
- The maintained source inventory independently recomputes to 627 entries
  and SHA-256
  `0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f`.
  All 197 inherited immutable pins match.

## Corpus and preservation checks

- The KLAPS50 `2026-10-20-active-ice` graph matches SHA-256
  `7f8cd28bdefaeef9d386fb2240cfaddee7e2f329a6246b2159a608464fb3490f` and
  has 39,220 nodes, 81,934 edges, and 3,207 communities. The Cloud-BAL graph
  matches SHA-256
  `d173f3de7d98b74e3c5ae3fac3f8e4abfda68617de6421c9fd9c7e551b93b2fb` and
  has 13,392 nodes, 23,483 edges, and 1,210 communities. Graph hashes, node
  and edge totals, and community totals match the receipt and public summary.
  Structural checks found no duplicate node IDs, duplicate edges, missing
  endpoints, or self-loops; the receipt's pinned Graphify diagnostics report
  zero unverified nodes.
- The prior `2026-10-20-source-store` snapshots remain byte-identical to their
  receipt hashes. Both `2026-10-19` and `2026-10-20` historical snapshot
  directories in each corpus retain their recorded membership and file hashes.
- The 627-entry maintained-source digest and protected wiki-content digests
  match the PR92 baseline. The private profile preservation counts remain
  unchanged (KLAPS50: 0 nodes/0 incident links; Cloud-BAL: 134 nodes/133
  incident links). The wiki index changes only inside its Graph snapshot
  section, and the log is append-only. All five derived wiki-file hashes match
  the KG receipt; corpus report mirrors match their generated reports.

## Bounded public bundle

- The bundle contains only `README.md`, `public_summary.json`, and
  `SHA256SUMS`, plus this review after publication packaging. It contains no
  full graph, private receipt contents, private profile, or protected wiki
  content. README and summary SHA-256 entries verify. The public summary's
  private-receipt digest matches the unchanged private receipt.
- Public counts, deltas, snapshot names, selected extraction totals, 627/197
  preservation figures, and integrity fields match the private receipt and
  graph files. Evidence links resolve. The document distinguishes frozen
  extraction source commit from its separate documentation-only publication
  commit without embedding a self-referential commit hash.
- Runtime pointers remain scoped: paired runs completed 600 seconds / 30
  timesteps per arm; generic policy remains `FAIL`; physical approval remains
  `FAIL_OPEN`. Graph freshness is explicitly not runtime or scientific
  validation.

The graph extraction and wiki bookkeeping preserve separate KLAPS50 and
Cloud-BAL snapshots. No source, runtime, graph, private-profile, or protected
wiki edits were made by this review.
