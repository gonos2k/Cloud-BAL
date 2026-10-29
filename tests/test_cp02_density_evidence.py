"""The archived CP02 result must be reproducible from repository evidence."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/evidence/cp02_density_controls_20261029/validation.json"


def test_all_archived_density_evidence_is_present_and_exact():
    artifacts = json.loads(MANIFEST.read_text())["artifacts"]
    assert {
        "path": "docs/evidence/cp02_density_controls_20261029/capture/standard_radar_analyzer_attempt.log",
        "sha256": "7b38e3165cf733ba38a849042a5abe7083189d6ce90b05edcb8c70b302cda405",
        "size_bytes": 1265,
    } in artifacts
    assert len(artifacts) == 50
    assert len({entry["path"] for entry in artifacts}) == len(artifacts)
    for entry in artifacts:
        path = ROOT / entry["path"]
        assert path.is_file(), f"missing archived evidence: {entry['path']}"
        data = path.read_bytes()
        assert len(data) == entry["size_bytes"], entry["path"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["path"]
