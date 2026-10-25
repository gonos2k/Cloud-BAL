#!/usr/bin/env python3
"""Regenerate the PR101 four-arm summary from pinned guarded captures."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

from pr101_cloud_thermo_reducer import contrast, read_stream


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _key(row: dict) -> tuple[int, int, int, int, int]:
    return row["timestep"], row["loop"], row["i"], row["j"], row["k"]


def verify_hash(path: Path, expected: str, label: str) -> None:
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"{label}: hash mismatch")


def _validate_arm(root: Path, arm: str, pin: dict) -> tuple[list[dict], dict]:
    manifest_path = root / pin["manifest"]["path"]
    receipt_path = root / pin["receipt"]["path"]
    verify_hash(manifest_path, pin["manifest"]["sha256"], f"{arm}: guarded manifest")
    verify_hash(receipt_path, pin["receipt"]["sha256"], f"{arm}: guarded receipt")
    manifest, receipt = json.loads(manifest_path.read_text()), json.loads(receipt_path.read_text())
    if receipt.get("status") != "COMPLETE" or receipt.get("returncode") != 0:
        raise ValueError(f"{arm}: guarded receipt is not COMPLETE")
    if receipt.get("preservation_issues") or not all(receipt.get("completion_markers", {}).values()):
        raise ValueError(f"{arm}: guarded receipt has preservation/marker failure")
    if receipt.get("manifest_sha256") != pin["manifest"]["sha256"]:
        raise ValueError(f"{arm}: receipt does not bind the pinned guarded manifest")
    if not receipt.get("expected_outputs") or not all(receipt["expected_outputs"].values()):
        raise ValueError(f"{arm}: guarded receipt lacks successful expected-output checks")
    if "REPLAY COMPLETED FULL ACTIVE TILE" not in receipt.get("completion_markers", {}):
        raise ValueError(f"{arm}: full-active-tile completion marker is absent")
    if manifest["executable"]["sha256"] != pin["executable_sha256"]:
        raise ValueError(f"{arm}: executable identity mismatch")
    required_plan_path = Path(__file__).resolve().parents[1] / "docs/evidence/pr101_cloud_thermo_20261023/build_r64/build_plan.json"
    plan_bindings = [entry for entry in manifest.get("bindings", [])
                     if Path(entry.get("path", "")) == required_plan_path]
    if (len(plan_bindings) != 1
            or plan_bindings[0]["sha256"] != "65478f6d00648fc62cd36734a49e4445571d92920f7bf561aa8f5aa510210a69"):
        raise ValueError(f"{arm}: fixed guarded build-plan binding is absent or changed")
    for section in (manifest.get("inputs", {}).values(), manifest.get("bindings", [])):
        for item in section:
            verify_hash(Path(item["path"]), item["sha256"], f"{arm}: guarded manifest input binding")
    for name, expected in manifest.get("expected_outputs", {}).items():
        if receipt.get("artifacts", {}).get(name, {}).get("sha256") != expected:
            raise ValueError(f"{arm}: receipt output differs from guarded manifest hash")
    raw_path = Path(pin["capture"]["path"])
    verify_hash(raw_path, pin["capture"]["sha256"], f"{arm}: capture")
    artifact = receipt.get("artifacts", {}).get("pr101_cloud_thermo.raw", {})
    if artifact.get("sha256") != pin["capture"]["sha256"]:
        raise ValueError(f"{arm}: receipt does not bind this capture")
    if manifest.get("directory") != receipt.get("directory"):
        raise ValueError(f"{arm}: manifest and receipt run directories differ")
    return read_stream(raw_path), receipt


def _sign_counts(rows: list[dict]) -> dict:
    return {
        "evaporation_positive_extent": sum(row["source_extent"] > 0 for row in rows),
        "condensation_negative_extent": sum(row["source_extent"] < 0 for row in rows),
        "zero_extent": sum(row["source_extent"] == 0 for row in rows),
    }


def _branch_counts(rows: list[dict]) -> dict:
    positive = [row for row in rows if row["qc_before"] > 0]
    result = {
        "rows": len(rows),
        "full_evaporation_rows": sum(row["full_evaporation"] for row in rows),
        "general_branch_rows": sum(not row["full_evaporation"] for row in rows),
        "qc_before_positive": len(positive),
        "qc_before_zero": sum(row["qc_before"] == 0 for row in rows),
        "qc_before_negative": sum(row["qc_before"] < 0 for row in rows),
        "qc_positive_liquid_RH_counts": {},
        "extent_sign_by_branch": {},
    }
    for label, selected in (("rh_branch_lt_1", [r for r in positive if r["rh_branch"] < 1]),
                            ("rh_branch_ge_1", [r for r in positive if r["rh_branch"] >= 1])):
        result["qc_positive_liquid_RH_counts"][label] = {
            "count": len(selected),
            "full_evaporation": sum(r["full_evaporation"] for r in selected),
            "general_branch": sum(not r["full_evaporation"] for r in selected),
            "extent_sign": _sign_counts(selected),
        }
    for label, selected in (("full_evaporation", [r for r in rows if r["full_evaporation"]]),
                            ("general_branch", [r for r in rows if not r["full_evaporation"]])):
        result["extent_sign_by_branch"][label] = _sign_counts(selected)
    return result


def _arm_absolute(rows: list[dict]) -> dict:
    sums = ("unbounded_evaporation", "bounded_evaporation", "source_extent",
            "stored_dqv", "stored_dqc", "stored_dt")
    ulps = [value for row in rows for value in row["saturation_oracle_ulp_differences"].values()]
    return {
        "rows": len(rows),
        "full_rows": sum(row["full_evaporation"] for row in rows),
        "general_rows": sum(not row["full_evaporation"] for row in rows),
        "sum": {name: math.fsum(row[name] for row in rows) for name in sums},
        "python_saturation_oracle": {
            "disposition": "advisory only",
            "max_ulp_difference": max(ulps, default=0),
            "over_one_ulp": sum(value > 1 for value in ulps),
        },
    }


def _selected(row: dict) -> dict:
    names = ("full_evaporation", "t_before", "pressure", "qv_before", "qc_before",
             "es_liquid", "qs_liquid", "work1", "pcond", "dtcld", "xl", "cpm",
             "cpm_basis_q", "xl_basis_t", "es_initial", "qs_initial", "es_after",
             "qs_after", "rh_initial", "rh_branch", "rh_after", "unbounded_evaporation",
             "bounded_evaporation", "source_extent", "qv_after", "qc_after", "t_after",
             "stored_dqv", "stored_dqc", "stored_dt")
    return {name: row[name] for name in names}


def _rank(rows: dict[str, list[dict]], predicate, rule: str, *, smallest=False,
          arm_names=("OFF", "COUPLED", "P20"), mismatch=False) -> dict:
    maps = {arm: {_key(row): row for row in values} for arm, values in rows.items()}
    off, coupled = maps["OFF"], maps["COUPLED"]
    eligible = sorted(key for key in off.keys() & coupled.keys() if predicate(off[key], coupled[key]))
    if not eligible:
        raise ValueError(f"ranking has no eligible rows: {rule}")
    def delta(key):
        return coupled[key]["stored_dqc"] - off[key]["stored_dqc"]
    chosen = sorted(eligible, key=lambda key: (abs(delta(key)) if smallest else -abs(delta(key)), key))[0]
    ref, cur = off[chosen], coupled[chosen]
    delta_fields = ("unbounded_evaporation", "bounded_evaporation", "source_extent",
                    "stored_dqv", "stored_dqc", "stored_dt", "rh_initial", "rh_branch", "rh_after")
    if mismatch:
        fields = ("full_evaporation", "t_before", "pressure", "qv_before", "qc_before",
                  "es_liquid", "qs_liquid", "work1", "unbounded_evaporation", "pcond",
                  "bounded_evaporation", "source_extent", "stored_dqv", "stored_dqc",
                  "stored_dt", "rh_initial", "rh_branch", "rh_after", "xl", "cpm")
        selected = lambda r: {name: r[name] for name in fields}
    else:
        selected = _selected
    arms = {name: selected(next(r for r in rows[name] if _key(r) == chosen)) for name in arm_names}
    result = {
        "rank_rule": rule,
        "identity": dict(zip(("timestep", "loop", "i", "j", "k"), chosen)),
        "signed_delta_C_minus_OFF": {name: cur[name] - ref[name] for name in delta_fields},
        "arms": arms,
    }
    if mismatch:
        result["mismatch_count"] = len(eligible)
    return result


def _metadata_from_template(template: dict) -> dict:
    allowed = ("schema", "source_sha256", "executable_sha256", "lineage", "diagnostics",
               "branch_count_semantics", "rh_scope_note")
    return {name: copy.deepcopy(template[name]) for name in allowed}


def aggregate(root: Path, pins_path: Path, template_path: Path) -> dict:
    pins = json.loads(pins_path.read_text())
    arm_order = ("OFF", "HYDRO", "COUPLED", "P20")
    if tuple(pins.get("arms", {})) != arm_order:
        raise ValueError(f"expected exactly four arms in canonical order: {arm_order}")
    arms = {name: _validate_arm(root, name, pins["arms"][name])[0] for name in arm_order}
    if any(len(rows) != 613 for rows in arms.values()):
        raise ValueError("expected exactly 613 unique events in every arm")
    keysets = [{_key(row) for row in rows} for rows in arms.values()]
    if any(keys != keysets[0] for keys in keysets[1:]):
        raise ValueError("arm event keys differ")
    template = json.loads(template_path.read_text())
    metadata = _metadata_from_template(template)
    result = {name: metadata[name] for name in ("schema", "source_sha256", "executable_sha256", "lineage")}
    result["support"] = {"all_arms_same_613_event_keys": True, "events": len(keysets[0])}
    result["arm_absolutes"] = {arm: _arm_absolute(rows) for arm, rows in arms.items()}
    result["signed_contrasts"] = {
        "HYDRO_minus_OFF": contrast(arms["HYDRO"], arms["OFF"])["field_signed_differences"],
        "COUPLED_minus_OFF": contrast(arms["COUPLED"], arms["OFF"])["field_signed_differences"],
        "P20_minus_COUPLED": contrast(arms["P20"], arms["COUPLED"])["field_signed_differences"],
    }
    for name, left, right in (("HYDRO_minus_OFF", "HYDRO", "OFF"),
                              ("COUPLED_minus_OFF", "COUPLED", "OFF"),
                              ("P20_minus_COUPLED", "P20", "COUPLED")):
        lm, rm = ({_key(row): row for row in arms[left]}, {_key(row): row for row in arms[right]})
        result["signed_contrasts"][name]["full_flag_mismatches"] = sum(
            lm[key]["full_evaporation"] != rm[key]["full_evaporation"] for key in lm)
    result["ranked_cells"] = {
        "COUPLED_minus_OFF_general": _rank(arms,
            lambda a, b: not a["full_evaporation"] and not b["full_evaporation"],
            "largest absolute COUPLED−OFF stored_dqc difference among rows full_evaporation=false in both arms"),
        "COUPLED_minus_OFF_full": _rank(arms,
            lambda a, b: a["full_evaporation"] and b["full_evaporation"],
            "largest absolute COUPLED−OFF stored_dqc difference among rows full_evaporation=true in both arms"),
        "COUPLED_minus_OFF_substantial_process_control": _rank(arms,
            lambda a, b: a["qc_before"] >= 1e-4 and b["qc_before"] >= 1e-4
            and a["unbounded_evaporation"] >= 1e-4 and b["unbounded_evaporation"] >= 1e-4,
            "smallest absolute COUPLED−OFF stored_dqc contrast with qc_before and unbounded request >=1e-4 in both arms",
            smallest=True),
        "COUPLED_minus_OFF_branch_mismatch": _rank(arms,
            lambda a, b: a["full_evaporation"] != b["full_evaporation"],
            "largest absolute stored_dqc difference among full_evaporation-flag mismatches in the aligned 613 keys",
            mismatch=True, arm_names=("OFF", "COUPLED")),
    }
    result["diagnostics"] = metadata["diagnostics"]
    result["private_raws"] = {arm: {"directory": pin["directory"],
                                      "capture_sha256": pin["capture"]["sha256"],
                                      "receipt_sha256": pin["receipt"]["sha256"]}
                              for arm, pin in pins["arms"].items()}
    result["arm_branch_counts"] = {arm: _branch_counts(rows) for arm, rows in arms.items()}
    result["branch_count_semantics"] = metadata["branch_count_semantics"]
    result["rh_scope_note"] = metadata["rh_scope_note"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pins", type=Path)
    parser.add_argument("template", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = aggregate(args.root, args.pins, args.template)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"events": result["support"]["events"], "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
