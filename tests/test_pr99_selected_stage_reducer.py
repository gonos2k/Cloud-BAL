from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pr99_selected_stage_reducer import stage_terms


def test_stage_terms_use_event_level_and_stored_transition_delta() -> None:
    with tempfile.TemporaryDirectory() as directory:
        warm = Path(directory) / "warm.raw"
        warm.write_text("PR85_KDM6_WARM 192 71 2 " + " ".join(["0"] * 10 + ["1"]) + "\n")
        terms, count = stage_terms(warm, "warm", 192, 71,
                                   [2.0, 3.0], [5.0, 7.0], 11.0, 1)
        assert count == 1
        assert terms == [3.0 * 7.0 * 11.0]

        transition = Path(directory) / "transition.raw"
        fields = ["PR85_ICE_TRANSITION", "192", "71", "2"] + ["0"] * 14
        fields[13] = "2.0"
        fields[14] = "5.0"
        transition.write_text(" ".join(fields) + "\n")
        terms, count = stage_terms(transition, "ice_transition", 192, 71,
                                   [2.0, 3.0], [5.0, 7.0], 11.0, 1)
        assert count == 1
        assert terms == [3.0 * 3.0 * 7.0 * 11.0]

        freezing = Path(directory) / "freezing.raw"
        pfrz = ["PFRZ", "192", "71", "2", "FTF"] + ["0"] * 19 + ["11.0"]
        pinu = ["PINU", "192", "71", "2", "FTF"] + ["0"] * 19 + ["11.0"]
        freezing.write_text(" ".join(pinu) + "\n" + " ".join(pfrz) + "\n")
        terms, count = stage_terms(freezing, "freezing", 192, 71,
                                   [2.0, 3.0], [5.0, 7.0], 13.0, 1)
        assert count == 2
        assert terms == [11.0 * 7.0 * 13.0, 11.0 * 7.0 * 13.0]


if __name__ == "__main__":
    test_stage_terms_use_event_level_and_stored_transition_delta()
