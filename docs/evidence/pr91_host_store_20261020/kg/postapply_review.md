# PR91 post-apply KG integrity review

Result: **PASS for structural maintenance and preservation**. This review verifies only the KG refresh; it does not approve model physics.

- Apply receipt SHA-256: `63ac1b4469a2baaf37c22b0f97e5eed5b5d50f03a18502be23b69ed4f74ba91d`; source commit `d34c6db9279275efe41af449dc9bda95975ea493`; exact selected paths `451`, of which `23` were structurally extracted and `428` are hash-only.
- Prior PR90 receipt SHA-256: `42ed1de1e363f9eb2a8a584b3ed52de3487ee95157d3b15717b0748f9e50040a`; all `197` pinned prior artifacts re-hash to their recorded values.
- The maintained-source inventory is `627` entries with digest `0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f` and `verified_pre_post_equal=true`. Protected wiki content/pages match the pre-apply hashes. The Cloud-BAL private host profile remains unchanged; the graph records 134 nodes/133 incident links for that profile, with no private profile contents included in this bundle.
- Both corpora remain separate. KLAPS50: `38960` nodes / `81530` edges; delta +`150` nodes / +`244` edges. Cloud-BAL: `13132` nodes / `23080` edges; same delta. ID comparison finds 150 added and zero removed nodes in each; receipt integrity counts show zero dangling, duplicate, or self-loop edges. Dated snapshots are `2026-10-20-host-store`.
- Wiki updates are limited to three derived reports, `index.md#Graph snapshot`, and append-only `log.md`. Independent byte comparison shows the index prefix and suffix are unchanged; the log begins with the exact prior bytes.
- Native evidence remains `240s COMPLETE` and `600s INCOMPLETE` in both arms (600s rc=1 after 14/30 steps). `physical_approval=FAIL_OPEN`; observation-fit, matched response, mass/wind, water/energy, number-budget and remaining source/event gates remain open. Graph freshness is navigation evidence only.

The integration manifest deliberately keeps `source_commit: null` and readiness flags false because it was frozen before the publication commit to avoid a self-hash. This KG receipt binds the actual final source commit and full selected path set. The KG refresh does not promote the incomplete 600-second run or any physical/scientific gate.

Pre-apply helper review SHA-256: `08b0bb8a9c6bd5142fef8c4d28403d43c03ca0de98f1068c0a9ef4a0493a3e57`. Check-only SHA-256: `33861eefe12df75935c875e4647369865418767335a73d93b8e97940be1c3c98`. Frozen helper SHA-256: `a2b4de3e7941e3d0cf2cf8d60ee3956338fe2471df960c1f93c04bcf554ea9cf`. Apply log SHA-256: `460f933495e78e16f0b8f963dd672c190497baa053711e4204bc9561ae116ea1`.
