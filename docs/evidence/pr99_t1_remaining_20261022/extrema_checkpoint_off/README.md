# OFF checkpoint follow-up for the v5 extrema

This bounded diagnostic used the retained selected-checkpoint observer for one
OFF first-call replay, with its coordinate predicate changed only to capture
one-based `(i,j)=(169,227)` and `(146,215)`. It was a replay of the active tile
against the retained first-call state, not a forecast. The build used the
pinned Intel profile and ran with the project WRF runtime libraries. The replay
returned successfully, observed the full-tile completion marker, and preserved
all 17 returned fields and XLAND byte-for-byte.

The checkpoint stream contains 1,691 selected records. Its source-ordered
site changes telescope to the native pre/post column water changes within
`1.60e-7 kg` at `(169,227)` and `1.58e-9 kg` at `(146,215)`. The terminal
per-level snapshots are at the last captured site for each level (site 6693
for most levels; other levels retain site 6682, 6686, or 6649). Their weighted
difference to the replay endpoint is only `-9.37e-8 kg` (`L1 4.04e-7 kg`) and
`-3.90e-8 kg` (`L1 3.62e-7 kg`), respectively. The endpoint interval after
each level's last captured site is
therefore negligible in the column sum; it does not account for the v5
remainders.

The same OFF v5 per-column account reports `+22.5885860012 kg` at
`(169,227)`: v4 open `+22.5686566492 kg`, public-store Q change `0`, and
G-sedimentation Q change `-0.0199293520 kg`. At `(146,215)`, it reports
`-20.1782844996 kg`: v4 open `-20.2828640512 kg`, public-store Q change `0`,
and G-sedimentation Q change `-0.1045795516 kg`.

The checkpoint sequence does **not** identify the first source-ordered
interval that creates either remainder. It samples selected assignment sites;
large compensating changes occur between those sites, while the v4/v5 process
terms are aggregated over the whole call. The endpoint telescope validates the
checkpoint stream, but it does not independently partition those intervals
into the same ownership terms. The current evidence therefore leaves the
first contributing interval open. No cause is assigned.

## Evidence files

- `OFF_extrema_replay_manifest.json`: replay completion, byte identity, input,
  executable, stage-stream and checkpoint hashes.
- `OFF_extrema_checkpoint_reduction.json`: per-source-site checkpoint changes
  and endpoint telescope for both extrema.
- `OFF_extrema_endpoint_checkpoint_check.json`: weighted last-checkpoint to
  endpoint comparison and the selected v5 column totals.
- `source_selection.patch`: one-line coordinate-selection change from the
  retained selected-checkpoint source.
- `build_manifest.json`: pinned compiler and executable provenance.
- `provenance.json`: external source/reducer/raw paths and hashes.

The raw checkpoint stream and prepared source remain in `/var/tmp`; their
SHA256 values are recorded in the manifests. The compact v4/v5 artifacts were
not modified.
