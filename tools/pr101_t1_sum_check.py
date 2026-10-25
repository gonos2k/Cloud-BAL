#!/usr/bin/env python3
"""Independently audit the frozen PR100 final per-column totals by exact summation."""
from __future__ import annotations

import ast
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT = ROOT / "docs/evidence/pr100_t1_snow_melt_20261022/direct_transfers_and_ground/final_three_arm_account.json"
PRIVATE_REDUCER = Path("/var/tmp/pr100_ground_boundary_final_account_20261022.py")
PRIVATE_REDUCER_SHA256 = "2df5f1e2729395d137cde03e908459d35d87f48245a110b9ae675fa3b368c728"
PRIVATE_ACCOUNT = Path("/var/tmp/pr100_ground_boundary_final_account_20261022.json")
PRIVATE_ACCOUNT_SHA256 = "de02ca7cb7a91ba957f23d932b0f9a0d3a75d691397b2f2c7bd8b458343d0bf1"
RUNS = {
    "OFF": Path("/var/tmp/pr100_unowned_diag_replay_clean_20261022/OFF"),
    "HYDRO": Path("/var/tmp/pr100_unowned_root_guarded_20261022/HYDRO"),
    "COUPLED": Path("/var/tmp/pr100_unowned_root_guarded_20261022/COUPLED"),
}
EXPECTED_REMAINDER_SHA256 = {
    "OFF": "eb7c8f2addb76cb0780e5f8dac89b833dbe5769826227087ac12b67e9363fb10",
    "HYDRO": "90dd7a749971985e2b48e2b3bffe2ef1bd0fc2004580abf4e46592faa3eb66b0",
    "COUPLED": "43d4f135071fe4c617b35897d6ab19988fc044ec412f21635ecbb4de947ac98a",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact_sum(values: np.ndarray) -> float:
    """Sum the exact rational values represented by the binary64 operands."""
    return float(sum((Fraction.from_float(float(value)) for value in values.flat), Fraction()))


class CaptureFinalRemainder(ast.NodeTransformer):
    def __init__(self) -> None:
        self.matches = 0

    def visit_Dict(self, node: ast.Dict) -> ast.AST:
        self.generic_visit(node)
        for key, value in zip(node.keys, node.values):
            if (isinstance(key, ast.Constant) and key.value == "remaining_after_ground_boundary_term"
                    and isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                    and value.func.id == "stats" and len(value.args) == 2
                    and isinstance(value.args[0], ast.Name) and value.args[0].id == "final"
                    and isinstance(value.args[1], ast.Name) and value.args[1].id == "b"):
                self.matches += 1
                value.func = ast.Name(id="capture_final_stats", ctx=ast.Load())
                value.args.insert(0, ast.Constant("remaining_after_ground_boundary_term"))
        return node


def load_reducer_namespace(captured: dict[str, np.ndarray]) -> dict:
    if sha256(PRIVATE_REDUCER) != PRIVATE_REDUCER_SHA256:
        raise ValueError("private reducer does not match the frozen source pin")
    tree = ast.parse(PRIVATE_REDUCER.read_text(encoding="utf-8"), filename=str(PRIVATE_REDUCER))
    # The private file's final top-level statements run all arms and write to
    # /var/tmp. Omit those statements; call only the existing read-only arm().
    definitions = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "summary" for target in node.targets
        ):
            break
        definitions.append(node)
    isolated = ast.Module(body=definitions, type_ignores=[])
    selector = CaptureFinalRemainder()
    isolated = selector.visit(isolated)
    if selector.matches != 1:
        raise ValueError(f"expected one named final remainder stats call, found {selector.matches}")
    isolated = ast.fix_missing_locations(isolated)
    namespace = {"__name__": "pr100_final_reducer_readonly", "__file__": str(PRIVATE_REDUCER)}
    exec(compile(isolated, str(PRIVATE_REDUCER), "exec"), namespace)

    original_stats = namespace["stats"]

    def capture_final_stats(key: str, values: np.ndarray, bounds: dict) -> dict:
        if key in captured:
            raise ValueError(f"duplicate captured remainder call: {key}")
        captured[key] = np.array(values, dtype=np.float64, copy=True)
        return original_stats(values, bounds)

    namespace["capture_final_stats"] = capture_final_stats
    return namespace


def run() -> dict:
    if sha256(PRIVATE_ACCOUNT) != PRIVATE_ACCOUNT_SHA256:
        raise ValueError("private final account does not match its frozen hash")
    frozen_json = json.loads(ACCOUNT.read_text(encoding="utf-8"))
    private = json.loads(PRIVATE_ACCOUNT.read_text(encoding="utf-8"))
    arms = {}
    for arm in ("OFF", "HYDRO", "COUPLED"):
        captured: dict[str, np.ndarray] = {}
        namespace = load_reducer_namespace(captured)
        computed = namespace["arm"](arm, RUNS[arm])
        if set(captured) != {"remaining_after_ground_boundary_term"}:
            raise ValueError(f"{arm}: named final remainder was not captured exactly once")
        reference = private["arms"][arm]["stages"]["remaining_after_ground_boundary_term"]
        values = captured["remaining_after_ground_boundary_term"]
        expected = frozen_json["arms"][arm]["stages"]["remaining_after_ground_boundary_term"]
        if any(reference[key] != expected[key] for key in ("signed_kg", "L1_column_kg", "max_abs_column_kg")):
            raise ValueError(f"{arm}: public and private frozen summaries differ")
        if values.shape != (280, 232) or not np.isfinite(values).all():
            raise ValueError(f"{arm}: invalid final per-column remainder array")
        array_sha = hashlib.sha256(values.tobytes(order="C")).hexdigest()
        if array_sha != EXPECTED_REMAINDER_SHA256[arm]:
            raise ValueError(f"{arm}: final per-column remainder changed")
        if computed["reducer_inputs"] != frozen_json["arms"][arm]["reducer_inputs"]:
            raise ValueError(f"{arm}: source-owned reducer input hashes differ from frozen account")
        signed_exact, l1_exact = exact_sum(values), exact_sum(np.abs(values))
        if signed_exact != reference["signed_kg"] or l1_exact != reference["L1_column_kg"]:
            raise ValueError(f"{arm}: exact independent sum differs from the frozen account")
        arms[arm] = {
            "columns": int(values.size),
            "column_remainder_binary64_sha256": array_sha,
            "signed_kg": {"frozen_math_fsum": reference["signed_kg"], "independent_exact_fraction": signed_exact,
                          "numpy_sum": float(np.sum(values, dtype=np.float64)),
                          "numpy_minus_exact_kg": float(np.sum(values, dtype=np.float64)) - signed_exact},
            "L1_column_kg": {"frozen_math_fsum": reference["L1_column_kg"], "independent_exact_fraction": l1_exact,
                             "numpy_sum": float(np.sum(np.abs(values), dtype=np.float64)),
                             "numpy_minus_exact_kg": float(np.sum(np.abs(values), dtype=np.float64)) - l1_exact},
            "max_abs_column_kg": {"frozen": reference["max_abs_column_kg"],
                                  "independent_array_max": float(np.max(np.abs(values)))},
            "source_owned_reducer_inputs": computed["reducer_inputs"],
        }
    return {
        "schema": "pr101_t1_independent_sum_check_v1",
        "scope": "one read-only compensated-sum check of frozen PR100 final per-column residuals; diagnostic only",
        "private_reducer_sha256": PRIVATE_REDUCER_SHA256,
        "private_account_sha256": PRIVATE_ACCOUNT_SHA256,
        "arms": arms,
    }


if __name__ == "__main__":
    result = run()
    output = ROOT / "docs/evidence/pr101_t1_sum_20261023/independent_sum_check.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)
