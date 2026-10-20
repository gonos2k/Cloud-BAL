"""Bind the source-present FogDES trial to the host's strict joint store."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


FOGDES_SHA256 = "56cf7041973def041db00a27d97085503f587cc6d29834cc74e8d4f40a7803be"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"expected one {label} anchor, found {count}")
    return source.replace(old, new, 1)


def transform_source(source: str) -> str:
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if digest != FOGDES_SHA256:
        raise ValueError(f"unexpected pinned FogDES source: {digest}")

    source = _replace_once(
        source,
        "  USE module_model_constants\n",
        "  USE module_model_constants\n"
        "  USE cloud_bal_joint_transport, ONLY: joint_moment_store\n",
        "joint store module import",
    )
    source = _replace_once(
        source,
        "    REAL :: stored_dq,stored_dn,qstate32,nstate32\n",
        "    REAL :: stored_dq,stored_dn,qstate32,nstate32,stored_q,stored_n,source_store_density\n"
        "    INTEGER :: source_store_adjustment\n"
        "    LOGICAL :: source_store_valid\n",
        "candidate store locals",
    )
    source = _replace_once(
        source,
        "        IF (PRESENT(cloud_source_delta64)) THEN\n"
        "          IF (qvalue<strict_mmin*nvalue .OR. qvalue>strict_mmax*nvalue) RETURN\n"
        "        ELSE\n",
        "        IF (PRESENT(cloud_source_delta64)) THEN\n"
        "          source_store_density=rho(i,kk,j)/(1.0+qv(i,kk,j))\n"
        "          IF (.NOT.ieee_is_finite(source_store_density) .OR. source_store_density<=0.0) RETURN\n"
        "          CALL joint_moment_store(qvalue,nvalue,source_store_density, &\n"
        "              strict_mmin,strict_mmax,.TRUE.,stored_q,stored_n, &\n"
        "              source_store_adjustment,source_store_valid, &\n"
        "              allow_normal_q_adjustment=.TRUE., &\n"
        "              allow_joint_quantum_absence=.TRUE.,strict_mass_ratio=.TRUE.)\n"
        "          IF (.NOT.source_store_valid) RETURN\n"
        "        ELSE\n",
        "source-present candidate predicate",
    )
    return source


def transform_file(source_path: Path, output_path: Path) -> str:
    output = transform_source(source_path.read_text(encoding="utf-8"))
    with output_path.open("x", encoding="utf-8") as stream:
        stream.write(output)
    return hashlib.sha256(output.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(transform_file(args.source, args.output))


if __name__ == "__main__":
    main()
