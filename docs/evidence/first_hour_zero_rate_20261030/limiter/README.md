# Rain-rate limiter fragment audit

The audit extracts the conditional directly from the retained preprocessed KDM6 source whose SHA-256 is in `receipt.json`. The old and candidate excerpts are included here. The candidate changes only the outer `else` to `else if (prevp(i,k).ne.0.) then`; it leaves either sign of an exactly zero rate untouched. The historical executable's exact source provenance is not established by this comparison.

The pinned Intel profile compiled the extracted old and modified fragments in fresh scratch at O0 and O2. Both builds reproduce all six PR131 observed old rates bit-for-bit from captured operands and return negative zero for those same inputs after the candidate change. Additional cases verify bitwise preservation of positive and negative zero with each saturation sign, and cover finite positive and negative rates, a positive and a zero rain amount, and normal-range values near the smallest positive float. Nonzero finite outputs and associated number changes match the old fragment. NaNs, subnormals and nonfinite or invalid inputs are outside this audit; in particular `-fpe0` means NaN comparisons may trap and cannot be assumed to preserve prior behavior.

For an isolated rain/vapor transfer, the source uses `delta_qv = -prevp * dt`, `delta_qr = prevp * dt`, and `delta_T = Lv / cp * prevp * dt`. The test checks opposite mass increments and the temperature sign and energy relation, including source-order float32 updates away from floors. Other terms, limiting, later clamps, mixed-phase processes and full-model conservation are not covered. Zero rain number with positive rain mass and the runtime writer of the zero double factor remain separate open issues.

Reproduce in a new scratch directory:

```sh
python tools/first_hour_zero_rate_limiter_audit.py --scratch /var/tmp/first-hour-limiter-new --receipt /var/tmp/first-hour-limiter-new-receipt.json
```

The original factor inputs and selected scope are described in `docs/CP02_ZERO_CANDIDATE_20261029.md`. The source alias and this fragment test do not establish a forecast improvement; paired forecast results and observations are required.
