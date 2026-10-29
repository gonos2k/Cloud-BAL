# Independent analyzer review

Reviewed `tools/cp02_zero_candidate.py` and its focused tests against the final native helper and raw event schema. The review identified three issues: distinguishing access-watch writes from value changes (including same-value stores); accepting nonfinite raw bits in uninitialized temporal state; and linking the B minimum inputs to the indexed array and multiplication constant. The author addressed all three. The corrected analyzer checks the ordered observed access PCs, reconstructs the B store arithmetic, and preserves raw-bit decoding for uninitialized contents. A same-value-store regression now checks that the observed writer remains identified even when bytes do not change.

Reviewed analyzer SHA-256: `f161305a5cddb68f47a9f5bca5fec3d84780f08fd3b79bc34b73556c05d20e78`.
Reviewed test SHA-256: `79405796cf009b8b0d75d9ccd042f1ba626a969b385621469a4845a82631b8b6`.

Validation: `python -m unittest discover -s tests -p test_cp02_zero_candidate.py`: 5 tests passed. The review is scoped to six selected first-outer paths and does not establish physical aliases, completed forecast behavior, or scientific validity.
