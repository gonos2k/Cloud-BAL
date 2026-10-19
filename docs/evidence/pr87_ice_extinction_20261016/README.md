# V39 cold ice aggregate extinction completion

This archive binds the aggregate completion overlay to the V39 KDM6 source
SHA-256 `6a7f6e154390ad6d5da8ca18ea4115ad66effa5b1dbdbf73754edd357b6b4293`.
The prior cap-order transform remains separately archived at
`../pr87_ice_cap_order_20261016`; its output SHA is
`faa81931252f6f28cc74ca3367a5c721668fe9ca0f01225641fb495a93ca6959`.
Applying `complete_cold_ice_extinction` yields source SHA
`bdb1882afed860068cecbb6c7b958eef0938cadbd4225222ba7522e28ecc071a`.

Before each NG or G search, the overlay enables the existing pending exact-zero
ice endpoint only if that process proposal has a finite positive fixed ice mass,
a finite negative mass change, and a proposed decrease at least as large as the
fixed mass. NG cause bit 2 is tested against the entry Q; G cause bit 4 is tested
against the Q after the accepted NG/AUT updates. PIDEp cap cause bit 1 remains
separate. The existing process fraction and composite REAL32 endpoint determine
the actual accepted state. Number is cleared only when the composite candidate is
valid and its stored ice mass is exactly zero. Positive ice mass retains number.
Invalid, negative, NaN, and infinite candidate number values do not enter the
clear branch.

Aggregate authorization is written under the distinct `PR87_ICE_EXTINCTION`
tag to `pr87_ice_extinction.raw`, before the transaction commit and only after
the composite REAL32 candidate passes its existing validation. Its cause bits
identify PIDEp/NG/G contributors, and the row includes pre/post ice Q/N, raw and
capped PIDEp, process fractions, retries, and the number actually cleared. The
row may describe an authorized candidate with positive final Q; `extinctions=1`
indicates actual number clearing.

The extracted Intel O0/O2 fixture compiles the exact NG/G eligibility blocks,
existing process fraction/state helpers, and exact-zero commit block. It checks
three NG source contributions exhausting Q, partial NG followed by exhausting
G, partial Q retaining N, a full NG proposal limited to a positive-Q endpoint,
the V41 observed approximate pre-state QI `4.2936549e-15` / NI `8.823875`, an
invalid negative base, and negative/NaN/infinite or invalid composite endpoints.
Both profiles print `PR87 V39 aggregate ice extinction cases PASS` under `-fpe0`.
This is a pinned source-fragment regression, not a full KDM6 runtime reproduction.
No executable is archived.
