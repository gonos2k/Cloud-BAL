#!/usr/bin/env python3
"""Replay only pressure geometry through the Fortran research kernel."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from diagnose_qbal_boundary import read_snapshot


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source = args.snapshot.resolve()
    source_hash = digest(source)
    state = read_snapshot(source)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    repo = Path(__file__).resolve().parents[1]
    prepared = output / "geometry.bin"
    with prepared.open("wb") as stream:
        stream.write(np.asarray(state.dimensions, dtype="<i4").tobytes())
        stream.write(np.asarray(state.p, dtype="<f8").tobytes(order="F"))
        stream.write(np.asarray(state.ps, dtype="<f8").tobytes(order="F"))
    script = output / "run.sh"
    script.write_text('''#!/usr/bin/env bash
set -euo pipefail
repo=$1
output=$2
. "$repo/tests/intel_toolchain.sh"
for level in O0 O2; do
  mkdir "$output/$level"
  if [[ $level == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  (
    cd "$output/$level"
    "$CLOUD_BAL_FC" "${flags[@]}" -convert little_endian \\
      "$repo/src/common/cloud_bal_grid_geometry.f90" \\
      "$repo/tests/qbal_physical_boundary.f90" \\
      "$repo/tests/qbal_pressure_flux.f90" \\
      "$repo/tests/diagnose_qbal_pressure_flux.f90" -o diagnose
    ./diagnose "$output/geometry.bin" > result.txt
  )
done
cmp "$output/O0/result.txt" "$output/O2/result.txt"
''')
    with (output / "intel.log").open("w") as log:
        subprocess.run(["bash", str(script), str(repo), str(output)],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    assert digest(source) == source_hash, "input changed during replay"
    values = {}
    for line in (output / "O0/result.txt").read_text().splitlines():
        key, value = line.split("=", 1)
        values[key] = float(value) if "." in value else int(value)
    sources = ["src/common/cloud_bal_grid_geometry.f90",
               "tests/qbal_physical_boundary.f90", "tests/qbal_pressure_flux.f90",
               "tests/diagnose_qbal_pressure_flux.f90", "tests/diagnose_qbal_pressure_flux.py",
               "tests/diagnose_qbal_boundary.py", "tests/intel_toolchain.sh"]
    report = {"status": "GEOMETRY_ONLY", "snapshot": str(source),
              "snapshot_sha256": source_hash, "prepared_sha256": digest(prepared),
              "source_sha256": {name: digest(repo / name) for name in sources},
              "result_sha256": {level: digest(output / level / "result.txt")
                                for level in ("O0", "O2")},
              "intel_O0_O2_identical": True, "geometry": values,
              "physical_flux_residual": None, "production_authority": False,
              "limitations": ["No wind reconstruction, horizontal area metric, or covariance inferred.",
                              "Exposed side intervals require a sloping-surface reconstruction.",
                              "Support, sentinel, and legacy active components are not physical cells.",
                              "No BALCON candidate, native startup, or forecast executed."]}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
