"""Pinned Intel source-extracted regression for explicit FogDES PBL rates."""
from __future__ import annotations

import gzip
import hashlib
import struct
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/pr87_two_step_v26c_20261016"


def _read_gzip(path: Path) -> str:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return stream.read()


def test_pr87_fogdes_explicit_pbl_source_on_pinned_intel() -> None:
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import pr87_fogdes_source_contract as transform
    import pr87_pbl_compact_diagnostics as compact

    fogdes = _read_gzip(EVIDENCE / "module_bl_fogdes.F.gz")
    driver = _read_gzip(EVIDENCE / "module_pbl_driver.F.gz")
    generated = transform.extend_fogdes_source_contract(fogdes, driver)
    fog = generated["fogdes"]
    assert "cloud_source_delta64,source_step" in fog
    assert "corrected_base_dq(kk)+scale*dq(kk)" in fog
    assert "stored_dq=REAL(base_dq(kk)+scale*dq(kk))" in fog
    assert "qvalue<strict_mmin*nvalue .OR. qvalue>strict_mmax*nvalue" in fog
    assert "PR87_FOGDES_SOURCE_CORRECTION_RK" in fog
    assert "PR87_FOGDES_SOURCE_CORRECTION_UNITS" in fog
    assert "cloud_source_delta64=pr87_tendency_delta64(:,:,:,1:2)" in generated["pbl_driver"]

    compact_driver = compact._extend_pbl_driver(driver)
    compact_generated = transform.extend_fogdes_source_contract(fogdes, compact_driver)
    assert "pr87_compact_diagnostics" in compact_generated["pbl_driver"]
    assert "cloud_source_delta64=pr87_tendency_delta64(:,:,:,1:2)" in compact_generated["pbl_driver"]

    fixture = ROOT / "tests/test_pr87_fogdes_source_contract.f90"
    constants = ROOT / "tests/test_pr87_fogdes_model_constants.f90"
    scratch = Path(tempfile.mkdtemp(prefix="pr87_fogdes_source_", dir="/var/tmp"))
    generated_path = scratch / "module_bl_fogdes.F90"
    generated_path.write_text(fog, encoding="utf-8")
    fixture_path = scratch / fixture.name
    fixture_path.write_bytes(fixture.read_bytes())
    constants_path = scratch / constants.name
    constants_path.write_bytes(constants.read_bytes())
    generated_sha = hashlib.sha256(fog.encode()).hexdigest()

    for profile in ("O0", "O2"):
        build = scratch / profile
        build.mkdir()
        command = [
            "bash", "-c",
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free -module "$3" -I "$3" '
            '"$4" "$5" "$6" -o "$3/test.exe" && "$3/test.exe"',
            "pr87-fogdes-source-test", str(ROOT), profile, str(build),
            str(constants_path), str(generated_path), str(fixture_path),
        ]
        result = subprocess.run(command, cwd=build, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                check=False)
        assert result.returncode == 0, result.stdout
        assert "PR87 FogDES explicit PBL-source cases PASS" in result.stdout
        budget = build / "pr85_fogdes_budget.raw"
        assert budget.is_file()
        correction_rows = [line.split() for line in budget.read_text().splitlines()
                           if line.startswith("PR87_FOGDES_SOURCE_CORRECTION_RK")]
        assert len(correction_rows) == 1
        theta = float(correction_rows[0][6])
        assert 0.0 < theta < 1.0
        assert struct.unpack("f", struct.pack("f", theta))[0] == theta
        print(f"{profile}: fogdes_sha256={generated_sha}; {result.stdout.strip()}")


if __name__ == "__main__":
    test_pr87_fogdes_explicit_pbl_source_on_pinned_intel()
    print("PR87 FogDES explicit PBL-source Intel test PASS")
