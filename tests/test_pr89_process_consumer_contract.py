#!/usr/bin/env python3
"""Pinned-Intel regression for packet admission at the actual next NG consumer."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import tempfile
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pr89_process_consumer_contract import (  # noqa: E402
    DEFAULT_KDM6_SOURCE,
    KDM6_SOURCE_SHA256,
    T4_FAILURE_STATE,
    actual_t4_event,
    extract_actual_consumer,
    regression_source,
    connect_freezing_consumer,
)


def test_actual_source_consumer_admits_only_complete_packet() -> None:
    actual = DEFAULT_KDM6_SOURCE.read_text()
    assert hashlib.sha256(actual.encode()).hexdigest() == KDM6_SOURCE_SHA256
    transformed = connect_freezing_consumer(actual)
    consumer = extract_actual_consumer(transformed)
    assert "real(n,8).gt.rain_max*q" in consumer.lower()
    assert "failure_reason=6" in consumer.lower()
    assert "call kdm6_rain_ng_pair_valid(q(3),n(3),rain_min,rain_max" in consumer
    freeze_start = transformed.index("              pr85_rf_qr_before=qrs(i,k,1)")
    freeze_end = transformed.index(
        "              open(newunit=pr85_rf_unit,file='pr85_rain_freezing_budget.raw', &",
        freeze_start,
    )
    freeze = transformed[freeze_start:freeze_end]
    assert freeze.count("call kdm6_rain_ng_pair_valid") == 2
    assert freeze.count("kdm6_progb_density_pair_valid(") == 2
    assert "rain_full_evap_pending(i,k)" in freeze
    assert "ice_full_sublimation_pending(i,k)" not in freeze
    assert freeze.index("call kdm6_rain_ng_pair_valid(pr85_rf_qr_after") < freeze.index(
        "qrs(i,k,1)=pr85_rf_qr_after"
    )
    assert "pr89_rf_gamma=0.5d0*pr89_rf_gamma" in freeze
    assert "pr85_rf_mass_request=DBLE(pfrzdtr)" in freeze

    helper_path = ROOT / "tools/pr85_kdm6_rain_freezing_packet.F90"
    helper_source = helper_path.read_text()
    assert helper_source in actual
    event = actual_t4_event()
    assert event["volume"] == event["mass"] / 1000.0
    generated = regression_source(actual, helper_source)
    assert "T4_INTEGRATED_PRIMITIVES" in generated
    assert all(word in generated for word in T4_FAILURE_STATE.split())
    assert "call pr85_kdm6_rain_freezing_packet" in generated
    assert "call kdm6_rain_process_state_valid" in generated

    for optimization in ("O0", "O2"):
        scratch = Path(tempfile.mkdtemp(prefix=f"pr89_process_consumer_{optimization}_", dir="/var/tmp"))
        source_path = scratch / "pr89_process_consumer.F90"
        executable = scratch / "pr89_process_consumer.exe"
        source_path.write_text(generated)
        command = [
            "bash",
            "-c",
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free "$3" -o "$4" && "$4"',
            "pr89-process-consumer-test",
            str(ROOT),
            optimization,
            str(source_path),
            str(executable),
        ]
        result = subprocess.run(
            command,
            cwd=scratch,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert result.returncode == 0, result.stdout
        assert "T4_EXPLICIT_DEFERRAL next_reason=6" in result.stdout
        assert "T4_TRANSACTION_ROLLBACK QR NR QG BG T approved=0" in result.stdout
        assert "VALID_NONZERO_PACKET_NEXT_NG PASS" in result.stdout
        assert "WRONG_BASE_NEXT_NG_REASON 8" in result.stdout
        assert "PR89 transformed source block cases PASS" in result.stdout
        print(f"{optimization}: {result.stdout.strip()}")
    print("kdm6_source_sha256=" + KDM6_SOURCE_SHA256)
    print("helper_sha256=" + hashlib.sha256(helper_path.read_bytes()).hexdigest())


if __name__ == "__main__":
    test_actual_source_consumer_admits_only_complete_packet()
    print("PR89 process-consumer contract PASS")
