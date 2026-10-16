# Stored-state gap in the second-step G search

This is one captured failed G-search call, not a full KDM6 or host replay.
V35diag changes only failure reporting relative to V34. Its first timestep is
bitwise identical to V34 OFF across six recorded states and twelve fields.
The call is timestep 2, `call_lat=63`, `i=204`, `k=17`; `call_lat` is not claimed
to be a mapped global coordinate.

## Reproduction and scope

The frozen V34 helper source, exact printed REAL32 inputs promoted to REAL64,
pinned Intel compiler/runtime, generated drivers, and commands are bound in
`provenance.json`. `receipt.json` distinguishes the unchanged helper from the
replay-only diagnostic clone. Both O0 and O2 reproduce `SEARCH_FAILURE`, zero
fraction, a valid base, and an invalid full proposal (rain PSD reason 6).
The original native receipts and diagnostic stdout remain in the V35 archive.

The diagnostic clone locates exhaustion of the 32-ULP walk in the continuous
G-active interval:

```
1.34613922561935325e-6 <= alpha <= 1.51909224907131121e-6
```

At the inward REAL32 endpoint fractions, the actual Fortran updates give the
same stored rain pair at both ends:

```
QR = 1.32635495901922695e-5
NR = 30817.58203125
```

Rounded affine updates are monotone in alpha. The lower bound for stored NR
minus the largest allowed NR at the upper QR enclosure is
`+1.36749170269467868e-3`. Every stored rain pair in this continuous interval
therefore violates the strict rain upper bound. No accepted stored state is
being discarded by excluding this interval.

## Corrective contract

The new full-PSD interval check rounds alpha bounds inward, encloses the same
REAL32 QR/NR expressions, and skips only a provably impossible rain interval.
Finite uncertainty returns without pruning. Positive minimum QR is required,
so absence and pending zero-mass cleanup cases are retained. Pair-only mode is
unchanged. Breakpoint tests and final stored-state validation remain required.

The exact captured case now returns `NO_FEASIBLE_STEP` within the declared
continuous-and-stored search domain. The existing caller may then use its
validated zero-G proposal, withholding all linked G mass, number, volume and
heat terms together. This is not a proof that every physical process
combination is infeasible, nor evidence that withheld physics is negligible.
