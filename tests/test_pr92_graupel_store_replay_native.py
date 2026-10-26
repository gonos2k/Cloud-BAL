from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr92_graupel_store_replay as replay  # noqa: E402


def test_source_bound_replay_o0_o2_and_manufactured_helper_contracts(tmp_path: Path) -> None:
    output = tmp_path / "replay.json"
    subprocess.run(
        [sys.executable, str(ROOT / "tools/pr92_graupel_store_replay.py"),
         "--output", str(output)],
        cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    result = json.loads(output.read_text())
    assert result["donor_mixture"]["manufactured_contract_cases_only"] is True
    assert "unknown" in result["donor_mixture"]["status"]
    for run in result["replays"]:
        rows = run["rows"]
        assert rows["CORE_CANDIDATE"][:2] == ["F", "6"]
        assert rows["MIXTURE_ABSENT"][:3] == ["T", "00000000", "00000000"]
        assert rows["MIXTURE_MIN_POSITIVE"][:3] == ["T", "00000064", "00000001"]
        assert rows["MIXTURE_NORMAL"] == ["T", "398DD8E4", "34A16400"]
    assert result["replays"][0]["rows"] == result["replays"][1]["rows"]
