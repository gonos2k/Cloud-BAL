"""Compare the Python adapter with standalone IFX gdtost output logs."""

import argparse
import importlib.util
import json
import re
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location(
    "pr103_surface_temperature_observation",
    Path(__file__).resolve().parents[1] / "tools/pr103_surface_temperature_observation.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
MISSING_FLAG, gdtost = module.MISSING_FLAG, module.gdtost


def ulp_distance(a: float, b: float) -> int:
    left = int(np.asarray(np.float32(a)).view(np.uint32))
    right = int(np.asarray(np.float32(b)).view(np.uint32))
    return abs(left - right)


def read_outputs(path: Path) -> dict[str, float]:
    values = {}
    for name, value in re.findall(r"^(\w+)=\s*([+\-0-9.Ee]+)$", path.read_text(), re.M):
        values[name] = float(value)
    return values


def cases() -> dict[str, float | None]:
    y, x = np.mgrid[1:9, 1:9]
    linear = 7.0 + 3.0 * x + 2.0 * y
    quadratic = x * x + 2 * y * y + 3 * x * y - 4 * x + 5 * y + 7
    missing_outer = quadratic.astype(np.float64)
    missing_outer[:, 1] = MISSING_FLAG
    missing_inner = np.full((8, 8), 2.0)
    missing_inner[3, 3] = MISSING_FLAG
    edge = np.ones((8, 8))
    return {
        "fractional": gdtost(linear, 3.5, 3.25)[0],
        "integral": gdtost(linear, 3.0, 3.0)[0],
        "quadratic_mixed": gdtost(quadratic, 4.5, 3.25)[0],
        "missing_outer_stencil": gdtost(missing_outer, 3.5, 3.25)[0],
        "missing_inner_stencil": None,
        "near_edge_source_kernel": gdtost(edge, 1.5, 4.5)[0],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("o0", type=Path)
    parser.add_argument("o2", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    o0, o2 = read_outputs(args.o0), read_outputs(args.o2)
    python_values = cases()
    results = {}
    for name, expected in python_values.items():
        source0, source2 = o0[name], o2[name]
        py_value = float(np.float32(MISSING_FLAG)) if expected is None else float(expected)
        results[name] = {
            "python_value_r64_or_mask": expected,
            "python_value_rounded_r32": py_value,
            "ifx_o0_r32": source0,
            "ifx_o2_r32": source2,
            "ifx_o0_minus_python_r32": source0 - py_value,
            "ifx_o2_minus_python_r32": source2 - py_value,
            "ifx_o0_python_ulp_distance": ulp_distance(source0, py_value),
            "ifx_o2_python_ulp_distance": ulp_distance(source2, py_value),
            "ifx_o0_o2_ulp_distance": ulp_distance(source0, source2),
        }
    args.output.write_text(json.dumps({
        "comparison": "REAL32 ULP distance after rounding Python REAL64 result to binary32; actual differences only, no fitted pass tolerance",
        "case_sources": "tests/pr103_gdtost_oracle_program.f90 + exact pinned gridconv.f gdtost/binom bodies",
        "cases": results,
        "mask_interpretation": "Fortran returns missingflag for the missing inner stencil; Python wrapper reports invalid_model_stencil and maps that to float32(missingflag) for numeric ULP comparison.",
        "boundary_interpretation": "i=1.5 is in-domain: source gdtost uses its partial edge stencil; Python reproduces it. Positions <1 or >domain are excluded before interpolation to prevent out-of-domain extrapolation.",
    }, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
