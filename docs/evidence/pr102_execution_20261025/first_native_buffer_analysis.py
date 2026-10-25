#!/usr/bin/env python3
"""Read closed PR102 H/P/N native face diagnostics on the frozen 196-column buffer."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr102_wind_structure_20261025/Cloud-BAL")
TOOLS = ROOT / "tools"
COMPOSITION = ROOT / "docs/evidence/pr93_qc_chain_20261020/qc_vertical_composition.json"
ASSESSMENT = ROOT / "docs/evidence/pr102_execution_20261025/first_native/first_native_response.json"
ASSESSMENT_SHA = "9fc8117c5dd46d625ec77d318d5ba8f50d58abb900d457417929bf1708fa6a98"
EXPECTED_CODE = {
    "pr94_cloud_response.py": "a626b22f234b3095202982a4fe32d89d9ab6c200e4a9547f6a06a8b109536537",
    "pr98_native_effect.py": "985b40b93f4cf1f7dc0246efa9f837d621a06b52e6d49171f05f92c5c82459d5",
}
EXPECTED_INPUTS = {
    "H": "46760bdf03e42cbc8e1f5b415e1b304b535d369689f95a421a287d1eb90b679c",
    "P": "10aff32bf15887a43141efbb1b14945234e8bbce741a89904d328fb3b1d75cb3",
    "N": "b26e5f3d712732c3459d59b82a4b44fe53eebd9be1fd450d13640d2d8398343f",
}
EXPECTED_RECEIPTS = {
    "H": "faab04125372e928ff4810f2c478dfad56027d0c1948b1060ae985f717c17d60",
    "P": "01b58bd5253b1c88b92a05afdc7568d6366418f196a925b1047e0f22c1c3eabf",
    "N": "9883aabc4ca5f031b40a119414a78d1f64c14843d2d10e6efe7eafcdd58c169c",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pin_code() -> dict[str, str]:
    rows = {name: sha(TOOLS / name) for name in EXPECTED_CODE}
    if rows != EXPECTED_CODE:
        raise RuntimeError("reviewed native reader/mask source pin changed")
    composition_sha = sha(COMPOSITION)
    if composition_sha != "331eb9837c41a7aa663864c348f8fe18c44f8e55feed736900f5029685b1aa64":
        raise RuntimeError("frozen QC composition pin changed")
    return {**rows, str(COMPOSITION): composition_sha, str(Path(__file__)): sha(Path(__file__))}


def load_capture_roots() -> tuple[dict[str, Path], dict[str, dict], dict[str, str]]:
    if sha(ASSESSMENT) != ASSESSMENT_SHA:
        raise RuntimeError("closed first-native assessment pin changed")
    assessment = json.loads(ASSESSMENT.read_text())
    require_roles = {"H", "P", "N"}
    if set(assessment.get("source_capture_receipts", {})) != require_roles:
        raise RuntimeError("assessment does not bind the full H/P/N cohort")
    roots, receipts, artifact_pins = {}, {}, {str(ASSESSMENT): ASSESSMENT_SHA}
    executable_pins = set()
    for role in ("H", "P", "N"):
        ref = assessment["source_capture_receipts"][role]
        receipt_path = Path(ref["receipt"]["path"])
        receipt_sha = ref["receipt"]["sha256"]
        if receipt_sha != EXPECTED_RECEIPTS[role] or sha(receipt_path) != receipt_sha:
            raise RuntimeError(f"{role} source-capture receipt changed")
        receipt = json.loads(receipt_path.read_text())
        if (receipt.get("schema") != "pr102_native_source_capture_v1"
                or receipt.get("status") != "COMPLETE" or receipt.get("completed_steps") != 1
                or set(receipt.get("captured_sources", [])) != {"RU", "RV", "MUDF"}
                or receipt.get("candidate_wrfinput_sha256") != EXPECTED_INPUTS[role]
                or receipt.get("noninterference", {}).get("status") != "PASS"):
            raise RuntimeError(f"{role} capture is not a closed one-step source record")
        artifact_pins[str(receipt_path)] = receipt_sha
        for artifact in receipt.get("artifacts", []):
            path = Path(artifact["path"])
            expected = artifact["sha256"]
            if sha(path) != expected:
                raise RuntimeError(f"{role} capture artifact pin changed: {path}")
            artifact_pins[str(path)] = expected
        binary_paths = [Path(row["path"]) for row in receipt["artifacts"]
                        if Path(row["path"]).name.startswith("pr98_")
                        and Path(row["path"]).suffix == ".bin"]
        if len(binary_paths) != 57 or len({path.parent for path in binary_paths}) != 1:
            raise RuntimeError(f"{role} does not bind exactly 57 PR98 snapshots in one run directory")
        roots[role] = binary_paths[0].parent
        receipts[role] = {"receipt_sha256": receipt_sha, "input_sha256": EXPECTED_INPUTS[role],
                          "snapshot_count": len(binary_paths),
                          "noninterference": receipt["noninterference"]}
        executable_pins.add(receipt.get("diagnostic_executable_sha256"))
    if len(executable_pins) != 1 or None in executable_pins:
        raise RuntimeError("H/P/N do not share the pinned diagnostic executable")
    return roots, receipts, artifact_pins


def rename_roles(row: dict) -> dict:
    aliases = {"OFF": "H", "HYDRO": "P", "COUPLED": "N",
               "h_H_minus_O": "P_minus_H", "b_C_minus_H": "N_minus_P",
               "net_C_minus_O": "N_minus_H"}
    return {aliases.get(key, key): rename_roles(value) if isinstance(value, dict) else value
            for key, value in row.items()}


def evaluate() -> dict:
    before_code = pin_code()
    roots_hpn, receipts, artifact_pins = load_capture_roots()
    import sys
    sys.path.insert(0, str(TOOLS))
    import pr94_cloud_response as cloud
    import pr98_native_effect as native
    composition = json.loads(COMPOSITION.read_text())["composed_qc_vertical_influence"]
    masks = cloud.make_masks(composition, (39, 280, 232))
    buffer = masks["fixed_5_cell_chebyshev_buffer"]
    if (int(masks["original_613_native_support"].sum()) != 613
            or int(buffer.any(axis=0).sum()) != 196 or int(buffer.sum()) != 39 * 196):
        raise RuntimeError("fixed support/buffer dimensions do not match the predeclared masks")
    # native_face_triplet uses historical OFF/HYDRO/COUPLED keys; here they map H/P/N.
    roots = {"OFF": roots_hpn["H"], "HYDRO": roots_hpn["P"], "COUPLED": roots_hpn["N"]}
    specs = (
        ("assembled_RU_out", "pr98_assembled_ru_tend_out_", "i", None,
         "native RU coupled tendency units"),
        ("assembled_RU_out_minus_in", "pr98_assembled_ru_tend", "i", "assembled_out_minus_in",
         "native RU coupled tendency units"),
        ("assembled_RV_out", "pr98_assembled_rv_tend_out_", "j", None,
         "native RV coupled tendency units"),
        ("assembled_RV_out_minus_in", "pr98_assembled_rv_tend", "j", "assembled_out_minus_in",
         "native RV coupled tendency units"),
        ("horizontal_U_diffusion_out_minus_in", "pr98_hdifu_ru_tendf", "i", "operator_out_minus_in",
         "native RU coupled tendency units"),
        ("horizontal_V_diffusion_out_minus_in", "pr98_hdifv_rv_tendf", "j", "operator_out_minus_in",
         "native RV coupled tendency units"),
    )
    records = {}
    for name, prefix, axis, delta_label, units in specs:
        values = native.native_face_triplet(roots, prefix, axis, buffer,
                                            add_out_minus_in=delta_label)
        if values["support_values"] <= 0:
            raise RuntimeError(f"{name} produced an empty buffer-face union")
        values = rename_roles(values)
        values["units"] = units
        values["fixed_mass_buffer_cells"] = 39 * 196
        values["fixed_buffer_columns"] = 196
        values["native_face_axis"] = axis
        values["scope_note"] = ("Union of native staggered faces adjacent to the predeclared 39-level, "
                                 "196-column buffer; face count is reported separately from mass-cell count.")
        records[name] = values
    after_code = pin_code()
    if before_code != after_code:
        raise RuntimeError("reader, composition, or this assessment script changed during calculation")
    after_artifacts = {path: sha(Path(path)) for path in artifact_pins}
    if after_artifacts != artifact_pins:
        raise RuntimeError("a pinned assessment/capture artifact changed during calculation")
    return {
        "schema": "pr102_first_native_buffer_response_v1",
        "status": "DESCRIPTIVE_ONLY",
        "assessment_sha256": ASSESSMENT_SHA,
        "capture_role_mapping": {"H": "HYDRO", "P": "original projected", "N": "candidate"},
        "capture_pins": receipts,
        "fixed_mask": {"composition_sha256": before_code[str(COMPOSITION)],
                       "mass_support_cells": 613, "buffer_mass_cells": int(buffer.sum()),
                       "buffer_columns": int(buffer.any(axis=0).sum()), "levels": 39,
                       "buffer_was_predeclared": True},
        "metrics": records,
        "source_pins_before_after": {"before": before_code, "after": after_code},
        "artifact_pins_before_after": {"before": artifact_pins, "after": after_artifacts},
        "interpretation_limits": [
            "This adds the predeclared 196-column buffer to the 613-cell first-native source comparison; no mask is fitted to results.",
            "H/P/N alias PR98 OFF/HYDRO/COUPLED only inside the reusable reader; results are renamed H/P/N here.",
            "Face-union counts differ by stagger axis and are not support-column counts.",
            "RU/RV assembled outputs and U/V diffusion tendencies retain native source-coordinate units and are not dry-column kg/s rates.",
            "The separate physical dry-column rate remains restricted to the declared 16 support columns.",
            "No threshold, observation-skill result, causal geometry claim, or physical approval is inferred."],
        "physical_approval": "FAIL_OPEN", "observation_skill": "NOT_EVALUATED",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="fresh JSON output path")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
