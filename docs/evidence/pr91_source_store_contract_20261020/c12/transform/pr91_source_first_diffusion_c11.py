#!/usr/bin/env python3
"""Add failed virtual-donor operand capture to the pinned C10 host overlay."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

C10_MODULE_SHA256 = "af54a8bd951e47407f6900dbfd4b16396cd6fc30753bb32437fd46c45b86be4c"
C10_SOLVE_SHA256 = "dd3d8436ec6e7712ea8b62a33502acf89832f2d8a9f45969f84968f06ff78ca6"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def transform_c10_module(source: str) -> str:
    if sha256(source) != C10_MODULE_SHA256:
        raise ValueError("input is not the pinned C10 module")
    from pr91_virtual_donor_capture import inject_failed_virtual_donor_capture
    return inject_failed_virtual_donor_capture(source)


def transform_files(module_path: Path, solve_path: Path,
                    module_output: Path, solve_output: Path) -> dict[str, str]:
    source = module_path.read_text()
    module = transform_c10_module(source)
    solve = solve_path.read_text()
    if sha256(solve) != C10_SOLVE_SHA256:
        raise ValueError("input is not the pinned C10 solve source")
    if module_output.exists() or solve_output.exists():
        raise FileExistsError("C11 outputs exist; refusing to overwrite")
    module_output.parent.mkdir(parents=True, exist_ok=True)
    solve_output.parent.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for path, content in ((module_output, module), (solve_output, solve)):
            with path.open("x") as stream:
                created.append(path)
                stream.write(content)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return {"module_sha256": sha256(module), "solve_sha256": sha256(solve),
            "module_output": str(module_output), "solve_output": str(solve_output)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True, type=Path)
    parser.add_argument("--solve", required=True, type=Path)
    parser.add_argument("--module-output", required=True, type=Path)
    parser.add_argument("--solve-output", required=True, type=Path)
    args = parser.parse_args()
    for key, value in transform_files(args.module, args.solve, args.module_output, args.solve_output).items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
