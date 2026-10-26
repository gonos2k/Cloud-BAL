#!/usr/bin/env python3
"""Run the frozen paired reducer once after the existing postprocessor closes."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

REPO = Path(__file__).resolve().parents[4]
INPUT = Path("/var/tmp/pr104_postclosure_products_20261026")
OUTPUT = Path("/var/tmp/pr105_postclosure_paired_20261026")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUTPUT.mkdir(exist_ok=False)
    sources = [REPO / "tools" / name for name in (
        "pr105_paired_scores.py", "pr104_validtime_observation.py",
        "pr103_surface_temperature_observation.py", "pr87_native_history.py")]
    sources.append(Path(__file__).resolve())
    pins = {str(path): sha(path) for path in sources}
    (OUTPUT / "launch.json").write_text(json.dumps({"state": "WAITING_FOR_CLOSED_DISPATCH",
                                                    "source_pins": pins}, indent=2) + "\n")
    dispatch_path = INPUT / "dispatch_receipt.json"
    while True:
        try:
            dispatch = json.loads(dispatch_path.read_text())
            break
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(30)
    record = {"dispatch_sha256": sha(dispatch_path), "source_pins": pins,
              "observation_skill": "NOT_EVALUATED", "physical_approval": "OPEN"}
    unchanged = all(sha(Path(path)) == digest for path, digest in pins.items())
    if not unchanged:
        record["status"] = "SOURCE_CHANGED_NOT_RUN"
    elif dispatch.get("status") != "POSTPROCESS_CLOSED" or dispatch.get("recipes", {}).get("observation", {}).get("returncode") != 0:
        record["status"] = "SKIPPED_NO_COMPLETE_OBSERVATION_RESULT"
    else:
        command = ["/usr/bin/python", str(sources[0]), "--dispatch", str(dispatch_path),
                   "--closed-result", str(INPUT / "observation_result.json"),
                   "--output", str(OUTPUT / "paired_scores.json")]
        with (OUTPUT / "stdout.log").open("x") as stdout, (OUTPUT / "stderr.log").open("x") as stderr:
            run = subprocess.run(command, cwd=REPO, stdout=stdout, stderr=stderr, check=False)
        record.update(status="CLOSED", command=command, returncode=run.returncode,
                      source_unchanged=all(sha(Path(path)) == digest for path, digest in pins.items()))
        if run.returncode == 0 and record["source_unchanged"]:
            record["result_sha256"] = sha(OUTPUT / "paired_scores.json")
    with (OUTPUT / "receipt.json").open("x") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
