# C6 archive independent hash verification

Archive manifest: `manifest.json`, SHA-256 `a04153886d70c656f91d4e0dda8afd4198711c14fd083ce82c76d56f20c54186`.
All listed archive files were rehashed from archived bytes and compared with manifest sizes/hashes. Files with absolute source paths were also compared byte-for-byte to their original C6 source artifacts.

- `sources.json`: 2892 bytes, SHA-256 `95a239a529d06c8fed9f464f243eff20ab6424620da9457285ed1cb081b0195b`; copied bytes verified.
- `overrides.json`: 847 bytes, SHA-256 `33204cc4ad13859644a0a62ebc7b4b917908e6ed1e0e964b84f3c9c2061df310`; copied bytes verified.
- `build_receipt.json`: 1518683 bytes, SHA-256 `2b663971a0b9040c8ea7f157ede2e7c529373d7df23263fe443684d1160b7515`; copied bytes verified.
- `OFF_preflight.json`: 13083 bytes, SHA-256 `3157a6746d0b393d12f28ae67921f11b7ddf8f2c0d4e7ce2d2873860904f315b`; copied bytes verified.
- `OFF_run_receipt.json`: 58556 bytes, SHA-256 `90269ded1c1b2d5e1305face195540dcac9c0cc3f91b789440f2f833788b07f8`; copied bytes verified.
- `COUPLED_preflight.json`: 13099 bytes, SHA-256 `da203a70f7bc91b3186d653474b015f933ac34321a745f68239401d2c69cc434`; copied bytes verified.
- `COUPLED_run_receipt.json`: 58559 bytes, SHA-256 `3c0c14fbb1ece6e136ff5838c396b7186b59ba5024b4144b29176cd67fba0b83`; copied bytes verified.
- `OFF_t8_failure_replay.json`: 4061 bytes, SHA-256 `e084d1738cc14a5efe1c581975502f967ecb7464602fa011295e5626c61196b4`; copied bytes verified.
- `failure_excerpt.md`: 1598 bytes, SHA-256 `eea35ebd513559bc2d8b6125b1e13a6b9030ba22e20974d80969a1f0fe7591b7`; diagnostic lines preserved; trailing Markdown blank line normalized before commit.
- `OFF` RSL diagnostics: compressed and decoded payload hashes match `OFF_run_receipt.json`; excerpt lines match decoded payload.
- `COUPLED` RSL diagnostics: compressed and decoded payload hashes match `COUPLED_run_receipt.json`; excerpt lines match decoded payload.

Run status recheck: OFF and COUPLED are `INCOMPLETE`, return code 128, seven completed steps, unchanged candidate build, no changed staged/original inputs, and no receipt processing errors. The T8 excerpt is corroborated against each receipt-bound RSL payload; the OFF replay identifies `(8,222,188,5)` and the recorded QR/NR/density hex words.
