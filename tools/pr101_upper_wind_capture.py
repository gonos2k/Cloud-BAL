#!/usr/bin/env python3
"""Create the hash-guarded PR101 U/V horizontal-diffusion capture source."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


C2_MODULE_EM_SHA256 = "d82efa15ee1c0a44080a8ef40b8a8aef436661f2093b6f66bef7e666584aa296"
MARKER = "MODULE pr101_upper_wind_capture"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _call(component: str, phase: int, field: str, tendency: str) -> str:
    return f"""      CALL pr101_capture_upper_wind('{component}', {phase}, rk_step, time_step, {field}, {tendency}, mut, c1h, c2h, &
           msfux, msfuy, msfvx, msfvx_inv, msfvy, msftx, msfty, xkmhd, khdif, rdx, rdy, &
           config_flags%diff_opt, config_flags%km_opt, diff_6th_opt, &
           config_flags%open_xs, config_flags%open_xe, config_flags%open_ys, config_flags%open_ye, &
           config_flags%specified, config_flags%nested, config_flags%periodic_x, config_flags%polar, &
           ids, ide, jds, jde, kds, kde, ims, ime, jms, jme, kms, kme, its, ite, jts, jte, kts, kte)
"""


def transform(source: str, helper_source: str) -> str:
    if MARKER in source:
        raise ValueError("source already has PR101 upper-wind capture")
    module_anchor = "\nMODULE module_em\n"
    if source.count(module_anchor) != 1:
        raise ValueError("expected one MODULE module_em anchor")
    use_anchor = "   USE pr87_horizontal_diffusion64, ONLY: horizontal_diffusion64\n"
    if source.count(use_anchor) != 1:
        raise ValueError("expected one module_em USE anchor")
    if helper_source.count("END MODULE pr101_upper_wind_capture") != 1:
        raise ValueError("helper source must define one PR101 module")

    calls = {
        "u": """        CALL horizontal_diffusion ('u', u, ru_tendf, mut,               &
                                        c1h, c2h, config_flags,         &
                                        msfux, msfuy, msfvx, msfvx_inv, &
                                        msfvy,msftx, msfty,             &
                                        khdif, xkmhd, rdx, rdy,         &
                                        ids, ide, jds, jde, kds, kde,   &
                                        ims, ime, jms, jme, kms, kme,   &
                                        its, ite, jts, jte, kts, kte   )
""",
        "v": """        CALL horizontal_diffusion ('v', v, rv_tendf, mut,               &
                                        c1h, c2h, config_flags,         &
                                        msfux, msfuy, msfvx, msfvx_inv, &
                                        msfvy,msftx, msfty,             &
                                        khdif, xkmhd, rdx, rdy,         &
                                        ids, ide, jds, jde, kds, kde,   &
                                        ims, ime, jms, jme, kms, kme,   &
                                        its, ite, jts, jte, kts, kte   )
""",
    }
    transformed = source.replace(module_anchor, "\n" + helper_source.rstrip() + "\n\nMODULE module_em\n")
    transformed = transformed.replace(use_anchor, use_anchor + "   USE pr101_upper_wind_capture, ONLY: pr101_capture_upper_wind\n")
    for component, (field, tendency) in {"u": ("u", "ru_tendf"), "v": ("v", "rv_tendf")}.items():
        call = calls[component]
        if transformed.count(call) != 1:
            raise ValueError(f"expected exactly one native {component.upper()} diffusion call")
        replacement = _call(component, 1, field, tendency) + call + _call(component, 2, field, tendency)
        transformed = transformed.replace(call, replacement)
    return transformed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--helper", type=Path, default=Path(__file__).with_name("pr101_upper_wind_capture.F90"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-source-sha256", default=C2_MODULE_EM_SHA256)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    source_bytes = args.source.read_bytes()
    actual = sha256(source_bytes)
    if actual != args.expected_source_sha256:
        raise SystemExit(f"source SHA256 mismatch: expected {args.expected_source_sha256}, got {actual}")
    helper_bytes = args.helper.read_bytes()
    output = transform(source_bytes.decode("utf-8"), helper_bytes.decode("utf-8"))
    output_bytes = output.encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output_bytes)
    manifest = {
        "schema": "pr101_upper_wind_source_transform_v1",
        "source": {"path": str(args.source), "sha256": actual},
        "helper": {"path": str(args.helper), "sha256": sha256(helper_bytes)},
        "transformed": {"path": str(args.output), "sha256": sha256(output_bytes)},
        "capture": {
            "faces_ijk": {"U": [136, 39, 16], "V": [135, 39, 17]},
            "levels": [37, 38, 39],
            "phases": {"before": 1, "after": 2},
            "raw_file": "pr101_upper_wind.raw",
            "operator_mutated": False,
        },
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
