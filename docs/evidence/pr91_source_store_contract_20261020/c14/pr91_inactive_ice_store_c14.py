#!/usr/bin/env python3
"""Apply the bounded inactive-ice Q-quantum policy to the pinned C12 host."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from pr91_host_store_trace import instrument_core


C12_MODULE_SHA256 = "fcdc8f34b523aa83adcf7f60a049e27aba5f1975c264bb7118bb7efe62120a5f"
CORE_SHA256 = "cf1384a06a82e2f3d03b4ca61db8fbfb8ad2e61d889e4290d790d7aa4d3be466"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"expected one {label} anchor, found {count}")
    return source.replace(old, new, 1)


def transform_module(c12_module: str, core: str) -> str:
    if digest(c12_module.encode()) != C12_MODULE_SHA256:
        raise ValueError("unexpected C12 module source")
    if digest(core.encode()) != CORE_SHA256:
        raise ValueError("unexpected joint transport core")
    begin = c12_module.find("module cloud_bal_joint_transport\n")
    end_marker = "end module cloud_bal_joint_transport"
    end = c12_module.find(end_marker, begin)
    if begin < 0 or end < 0:
        raise ValueError("pinned C12 module lacks embedded joint transport core")
    end += len(end_marker)
    instrumented_core = instrument_core(core, expected_sha256=CORE_SHA256)
    source = c12_module[:begin] + instrumented_core.rstrip() + c12_module[end:]
    source = replace_once(
        source,
        "  INTEGER :: storage_adjustments(4),adjustment,full_failures\n",
        "  INTEGER :: storage_adjustments(4),adjustment,full_failures\n"
        "  INTEGER :: inactive_q_quantum_adjustments(4)\n",
        "inactive Q-quantum ledger declaration",
    )
    source = replace_once(
        source,
        "  WRITE(u,*) 'JOINT_STORAGE',itimestep,rk,cells,storage_adjustments\n",
        "  WRITE(u,*) 'JOINT_STORAGE',itimestep,rk,cells,storage_adjustments\n"
        "  WRITE(u,*) 'INACTIVE_Q_QUANTUM_ADJUSTMENTS',inactive_q_quantum_adjustments\n",
        "inactive Q-quantum ledger row",
    )
    source = replace_once(
        source,
        "    INTEGER :: trial_adjustments(4),fallback_count,witness_i,witness_j,witness_k,tiny_bg_count\n",
        "    INTEGER :: trial_adjustments(4),fallback_count,witness_i,witness_j,witness_k,tiny_bg_count\n"
        "    INTEGER :: trial_inactive_q_quantum_adjustments(4)\n",
        "fallback Q-quantum ledger declaration",
    )
    source = replace_once(
        source,
        "    trial_delta_q=0.0_real64; trial_delta_n=0.0_real64; trial_adjustments=0\n",
        "    trial_delta_q=0.0_real64; trial_delta_n=0.0_real64; trial_adjustments=0\n"
        "    trial_inactive_q_quantum_adjustments=0\n",
        "fallback Q-quantum ledger initialization",
    )
    source = replace_once(
        source,
        "                         inactive_mass_limits=[0.0_real64,REAL(NEAREST(1.e-14,-1.0),real64), &\n"
        "                         0.0_real64,0.0_real64], &\n",
        "                         inactive_mass_limits=[0.0_real64,REAL(NEAREST(1.e-14,-1.0),real64), &\n"
        "                         0.0_real64,0.0_real64], &\n"
        "                         inactive_q_quantum_adjustment_pairs=[.FALSE.,.TRUE.,.FALSE.,.FALSE.], &\n"
        "                         inactive_q_quantum_adjustments=inactive_q_quantum_adjustments, &\n",
        "joint update inactive Q-quantum opt-in",
    )
    source = replace_once(
        source,
        "                                 tiny_bg_count,tiny_bg_i,tiny_bg_j,tiny_bg_k,tiny_bg_bits,tiny_bg_rho_bits)\n",
        "                                 tiny_bg_count,tiny_bg_i,tiny_bg_j,tiny_bg_k,tiny_bg_bits,tiny_bg_rho_bits, &\n"
        "                                 inactive_q_quantum_adjustments= &\n"
        "                                     trial_inactive_q_quantum_adjustments)\n",
        "fallback store certification call",
    )
    source = replace_once(
        source,
        "    storage_adjustments=trial_adjustments\n",
        "    storage_adjustments=trial_adjustments\n"
        "    inactive_q_quantum_adjustments=trial_inactive_q_quantum_adjustments\n",
        "fallback Q-quantum ledger commit",
    )
    source = replace_once(
        source,
        "      tiny_bg_count,tiny_bg_i,tiny_bg_j,tiny_bg_k,tiny_bg_bits,tiny_bg_rho_bits,graupel_only)\n",
        "      tiny_bg_count,tiny_bg_i,tiny_bg_j,tiny_bg_k,tiny_bg_bits,tiny_bg_rho_bits,graupel_only, &\n"
        "      inactive_q_quantum_adjustments)\n",
        "fallback certifier optional output",
    )
    source = replace_once(
        source,
        "    LOGICAL,INTENT(IN),OPTIONAL :: graupel_only\n",
        "    LOGICAL,INTENT(IN),OPTIONAL :: graupel_only\n"
        "    INTEGER,INTENT(OUT),OPTIONAL :: inactive_q_quantum_adjustments(4)\n",
        "fallback certifier output declaration",
    )
    source = replace_once(
        source,
        "    adjustments_by_pair=0\n",
        "    adjustments_by_pair=0\n"
        "    IF (PRESENT(inactive_q_quantum_adjustments)) inactive_q_quantum_adjustments=0\n",
        "fallback certifier output initialization",
    )
    for pair_name, count in (("p", 3), ("pair", 1)):
        old = ("inactive_mass_limit=MERGE(REAL(NEAREST(1.e-14,-1.0),real64),"
               f"0.0_real64,{pair_name}==2))")
        new = old[:-1] + ", &\n                 allow_inactive_q_quantum_adjustment=(" + pair_name + "==2))"
        if source.count(old) != count:
            raise ValueError(f"expected {count} {pair_name} inactive-limit store calls")
        source = source.replace(old, new)
    old = "inactive_mass_limit=REAL(NEAREST(1.e-14,-1.0),real64))"
    new = ("inactive_mass_limit=REAL(NEAREST(1.e-14,-1.0),real64), &\n"
           "                  allow_inactive_q_quantum_adjustment=(p==2))")
    source = replace_once(source, old, new, "graupel trial inactive-ice store")
    source = replace_once(
        source,
        "            IF (.NOT.store_valid) THEN\n",
        "            IF (store_valid.AND.PRESENT(inactive_q_quantum_adjustments).AND.adjustment==4) &\n"
        "              inactive_q_quantum_adjustments(p)=inactive_q_quantum_adjustments(p)+1\n"
        "            IF (.NOT.store_valid) THEN\n",
        "fallback adjustment classification",
    )
    return source


def transform_file(source_path: Path, core_path: Path, output_path: Path) -> str:
    generated = transform_module(
        source_path.read_text(encoding="utf-8"), core_path.read_text(encoding="utf-8")
    )
    with output_path.open("x", encoding="utf-8") as stream:
        stream.write(generated)
    return digest(generated.encode())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--c12-module", type=Path, required=True)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(transform_file(args.c12_module, args.core, args.output))


if __name__ == "__main__":
    main()
