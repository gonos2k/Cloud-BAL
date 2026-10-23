import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr100_qc_process_reducer import parse_event


def test_parse_native_event_wire_row():
    values = " ".join(["1.0E+000", "2.0E+000", "1.0E+000"] + ["0.0E+000"] * 16)
    event = parse_event(f"QCEVENT COLD_COMMIT,9,1,16,2,134,4,1065353216,1073741824 {values}\n")
    assert (event["ordinal"], event["i"], event["j"], event["k"]) == (9, 134, 16, 4)
    assert (event["before_bits"], event["after_bits"]) == (1065353216, 1073741824)
    assert event["delta"] == 1.0
    assert event["proposal"] == [0.0] * 4


@pytest.mark.parametrize("line", [
    "QCEVENT ENTRY,1,1,16,-1,134,1,10,10 1.0 1.0\n",
    "QCEVENT ENTRY,nope,1,16,-1,134,1,10,10 " + " ".join(["0"] * 19) + "\n",
    "QCEVENT ENTRY,1,1,16,-1,134,1,10,10 " + " ".join(["nan"] * 19) + "\n",
])
def test_reject_malformed_or_nonfinite_row(line):
    with pytest.raises(ValueError):
        parse_event(line)
