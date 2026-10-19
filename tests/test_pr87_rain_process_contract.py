from __future__ import annotations

import gzip
import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr87_rain_process_contract import (  # noqa: E402
    add_rain_process_contract,
    add_status1_warm_trace,
    add_valid_zero_step_warm_trial,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/evidence/pr87_two_step_v11b_20261016/module_mp_kdm6.F.gz"
SOURCE_SHA256 = "b14092c4664392804c99b6e068d04456f67c8205fefa1a0e8aaedb93825315e3"
V13_SOURCE = ROOT / "docs/evidence/pr87_two_step_v13_20261016/module_mp_kdm6.F.gz"
V13_SOURCE_SHA256 = "f9652dc7208bb81edd57a23de53c58d3b23a531967ea46c0ec7aa510e0599a98"


def _read_archived_source(path: Path, expected_sha256: str) -> str:
    source = gzip.decompress(path.read_bytes())
    assert hashlib.sha256(source).hexdigest() == expected_sha256
    return source.decode()


def _extract(source: str, name: str) -> str:
    start = list(re.finditer(rf"(?im)^\s*subroutine\s+{name}\s*\(", source))
    end = list(re.finditer(rf"(?im)^\s*end\s+subroutine\s+{name}\s*$", source))
    assert len(start) == len(end) == 1
    return source[start[0].start():end[0].end()]


def test_transform_preserves_pair_only_warm_domain() -> None:
    source = _read_archived_source(SOURCE, SOURCE_SHA256)
    transformed = add_rain_process_contract(source)

    # The fraction search and validator must remain source-identical: warm
    # admission uses the original consumer-pair-only domain, including its
    # sub-cutoff rain transient handling.
    for name in ("kdm6_rain_process_fraction", "kdm6_rain_process_state_valid"):
        assert _extract(transformed, name) == _extract(source, name)
    assert "consumer_pair_only=.true.)" in transformed
    assert "consumer_pair_only=.true.,require_rain_psd=.true." not in transformed
    assert "logical, intent(in), optional :: require_rain_psd" not in transformed

    assert "if (rain_warm_search_status.eq.1) then\n            write(pr85_warm_unit" in transformed
    assert "PR87 NO_POSITIVE_WARM_STEP trace: status 1 only." in transformed
    assert "if (.false.) then\n            write(pr85_cold_unit" in transformed
    with pytest.raises(ValueError):
        add_rain_process_contract(transformed)


def test_v13_zero_step_executes_trial_and_preserves_failure_paths() -> None:
    source = _read_archived_source(V13_SOURCE, V13_SOURCE_SHA256)
    transformed = add_valid_zero_step_warm_trial(source)
    guard = re.search(
        r"(?m)^\s*if \(rain_warm_alpha\.le\.0\.0 \.and\. &\n"
        r"\s*\.not\.\(rain_warm_retry\.eq\.0 \.and\. rain_warm_search_status\.eq\.1\)\) exit$",
        transformed,
    )
    assert guard is not None
    transfer = re.search(
        r"(?m)^\s*if \(rain_full_evap_pending\(i,k\) \.and\. rain_warm_q_after\(3\)\.eq\.0\.0\) then\n"
        r"\s*rain_ccn3_after=rain_ccn3_after\+rain_warm_n_after\(3\)\n"
        r"\s*rain_warm_n_after\(3\)=0\.0\n\s*endif$",
        transformed,
    )
    assert transfer is not None
    # Preserve fatal handling for search failure, invalid base, and exhausted
    # positive-alpha endpoint retries. The sole exception is retry-0 status 1.
    assert "if (rain_warm_search_status.ne.1) &\n                error stop 'KDM6 warm process admission search failed'" in transformed
    assert "if (.not.rain_warm_state_valid .or. rain_qv_before.lt.0.0 .or. &" in transformed
    assert "rain_warm_search_status=2\n              rain_warm_abort=.true." in transformed

    traced = add_status1_warm_trace(transformed)
    assert "if (rain_warm_search_status.eq.1) then\n            write(pr85_warm_unit" in traced
    assert "if (.false.) then\n            write(pr85_cold_unit" in traced
    assert traced.count("PR87 NO_POSITIVE_WARM_STEP trace: status 1 only.") == 1

    # The fixture isolates the extracted retry guard and pending CCN transfer;
    # it is a control-flow test, not the full warm kernel.
    fixture = (ROOT / "tests/fixtures/pr87_warm_zero_step_flow.F90").read_text()
    fixture = fixture.replace("! PR87_RETRY_ZERO_GUARD", guard.group(0).strip())
    fixture = fixture.replace("! PR87_PENDING_CCN_TRANSFER", transfer.group(0).strip())
    assert "PR87_RETRY_ZERO_GUARD" not in fixture and "PR87_PENDING_CCN_TRANSFER" not in fixture
    scratch = Path(tempfile.mkdtemp(prefix="pr87_warm_zero_step_", dir="/var/tmp"))
    source_file = scratch / "zero_step.F90"
    source_file.write_text(fixture)
    for opt in ("O0", "O2"):
        build = scratch / opt
        build.mkdir()
        command = [
            "bash", "-c",
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free "$3" -o "$4/test.exe" && "$4/test.exe"',
            "pr87-warm-zero-step", str(ROOT), opt, str(source_file), str(build),
        ]
        result = subprocess.run(command, cwd=build, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        assert result.returncode == 0, result.stdout
        assert "PR87 warm zero-step flow PASS" in result.stdout
