# PR98 closed-640 KG publication review — 2026-10-22

## Decision

**GO for the bounded public KG package.** The second-phase publication summary, checksums, and independent post-apply review are present and consistent with the private receipt. No runtime was rerun and no graph was applied during this review.

## Public package pins

- Outer `kg/README.md`: `e0303f2efa1d9c4ef783e77739769043f401182ca1d2db7697e1e19ab03abe48`
- Outer `kg/SHA256SUMS`: `10a1c20a17938020179f9d409140d5d59a4c918225d465a3bd332aaa26847dbf`
- Nested `kg/closed640/README.md`: `9677f69f0c153ef5f285e9d77d70d9f35b425cde0c39d68baedaf44b8e1e02f8`
- Nested `kg/closed640/SHA256SUMS`: `3e852cea619dfafab57eb784c7a241ac28f54ef984599225eaa25c0379b0decb`
- Nested independent post-apply review: `006f725ac065e78483187ff80dc3d609ca68e86d03a14747572fa1e51c0d10e7`

Every entry in both checksum manifests verified. Relative links in both public README files resolve. The nested independent review is included and bound by both checksum manifests.

## Receipt and summary consistency

- Private second-phase receipt SHA-256 `6483bca8400f8ced959f23cde9a71208e8a525284fecfae843eb7e46730f2c06` matches the receipt file and reports `PASS`, source commit `aea142c3df602e3ac339953507dc7f691743ddb8`, and prior receipt SHA-256 `ce651957174ff90cf9ea104fafc9e407fa39590c6825d29ca3910ccf640eaf4d`.
- Both corpora report the separate `2026-10-22-pr98-closed640` snapshot, +6 net nodes, +16 edges, 12 added / 6 removed node IDs, and graph hashes matching the published table.
- Preservation claims match the receipt and post-apply review: 108 pre-existing dated snapshots preserved, 197 immutable pins verified, maintained-source inventory 627 entries with the stated SHA-256, and private profiles unchanged. Graph integrity counts contain no unverified nodes, malformed/missing/dangling edges, self-loops, exact duplicates, or post-build error.
- The public package contains bounded Markdown summaries/reviews, checksum manifests, and the two helper sources. It does not include the full private receipt, graph JSON payloads, profiles, or protected content.
- The package retains the execution limits: all three C1 640-second requests ended `INCOMPLETE` at 620 seconds / step 31, rc=1; generic Q/N/B validation `FAIL`; exact source endpoint and active-ice checks `PASS`; first grouped rejection subpredicate open; physical approval `FAIL_OPEN`; observation skill `NOT_EVALUATED`. Extraction limits are stated, and graph freshness is not presented as runtime or scientific approval.
- The parent science assessment links the new closed-640 README and identifies source `aea142c3df602e3ac339953507dc7f691743ddb8`, the separate snapshot name, and the +6 / +16 re-extraction delta without changing scientific status.

No publication-scope blocker remains in the reviewed package.
