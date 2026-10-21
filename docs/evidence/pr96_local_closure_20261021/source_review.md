# PR96 source review

Independent agent reviews found no remaining source blockers in:

- the map/coordinate reader change and its actual-C4 unchanged-value check;
- the exact two-column liquid-store reducer, diagnostic-only source patch,
  17-field byte comparisons, and pinned Intel scratch compilation;
- the shared strict ice NG predicate, three PSD completion blocks, existing
  directed-bound helper, unchanged freezing tolerance and inactive policy;
- the configurable three-arm response reader, including its unchanged C4
  defaults, executable, timestamp, boundary, namelist and input-chain gates;
- the bounded publication of already closed C4 longrun/HYDRO results.

The independent native build review is in
[native_build_review.md](native_build_review.md). It verifies all nine
overrides, the eight unchanged C4 sources, the exact transformed KDM6
source, cycle support, compiler profile, executable and HYDRO input chain.

Root review addressed these findings before publication:

1. Finite positive fill sentinels are tested, rather than relying on a
   negative fill that the positivity gate would already reject.
2. The liquid-store reducer uses the wider adjacent spacing for its
   conservative half-ULP bound at binade boundaries and checks that full
   evaporation's approved extent exactly clears QC.
3. The HYDRO diagnosis uses the receipt-bound stdout hex row and
   `REAL32(public_NI * DEN)` for internal volume number concentration.
4. Each PSD completion test starts with the same original failing number;
   the second and third blocks cannot inherit an already repaired input.
   Lower/upper neighbor misses also pass independently through all three
   blocks, and helper `intent(out)` arguments do not alias.
5. The private closed-audit queue reads actual run preflights, distinguishes
   the old template executable from C1, verifies real source/build/profile
   hashes, and uses fields actually emitted by the runner. It waits for
   all three receipts before opening model outputs.

The local full-checkout Graphify refreshes attempted during development
were discarded. Maintained graph/wiki updates are a separate guarded,
selected-source operation. They do not establish runtime or scientific
validation.

At source-review completion, C1 native runs and their closed audits remain
pending. Local/source/build GO does not claim a completed three-arm
forecast, global water closure, mass–wind balance, or observation skill.
