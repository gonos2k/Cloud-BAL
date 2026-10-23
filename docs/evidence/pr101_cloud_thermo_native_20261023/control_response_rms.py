"""Read-only RMS comparison of four receipt-closed C2 histories."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

SOURCE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SOURCE / "tools"))
from pr86_compare_response import load_history, UNITS
from pr94_cloud_response import make_masks, pattern_metrics

RUNS = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee")
ROOTS = {arm: RUNS / "pr99_c2_matched640_20261022" / arm
         for arm in ("OFF", "HYDRO", "COUPLED")}
ROOTS["PROJECTED"] = RUNS / "pr101_projected_c2_640_20261023"
PINS = dict(zip(("OFF", "HYDRO", "COUPLED", "PROJECTED"), (
    "c4174b0363dc3b6eb5117ae1e011e9bee0f4f70d090036c607331fac7b0d1f8d",
    "1440db5a0178af11ac4d92854b3284cc35cb5a74e5e6f6a14cc59dcac3a00a64",
    "0a7e1c3bcce58dea8433e9bffa615395d923cd05377c5068469af5dba29759cb",
    "d0a7920687aecbef15b91f2641638918f00beea67de5fb2af6e5597175bc5da2")))
FIELDS = ("pressure", "geopotential", "W", "QCLOUD", "T", "QVAPOR",
          "QICE", "QRAIN", "QSNOW", "QGRAUP", "U", "V")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    composition = SOURCE / "docs/evidence/pr93_qc_chain_20261020/qc_vertical_composition.json"
    if sha(composition) != "331eb9837c41a7aa663864c348f8fe18c44f8e55feed736900f5029685b1aa64":
        raise ValueError("fixed support composition changed")
    masks = make_masks(json.loads(composition.read_text())["composed_qc_vertical_influence"], (39, 280, 232))
    masks = {name: masks[name] for name in ("original_613_native_support", "fixed_5_cell_chebyshev_buffer")}
    artifacts = {}
    for arm, root in ROOTS.items():
        receipt = root / "receipt.json"
        if sha(receipt) != PINS[arm]:
            raise ValueError(f"{arm}: closed receipt changed")
        doc = json.loads(receipt.read_text())
        if doc["status"] != "COMPLETE" or doc["returncode"] != 0 or doc["final_completed_step"] != 32:
            raise ValueError(f"{arm}: not closed at 640 seconds")
        row, = (x for x in doc["generated_files"] if x["path"].startswith("wrfout_d01_"))
        path = root / "run" / row["path"]
        if sha(path) != row["sha256"]:
            raise ValueError(f"{arm}: history differs from receipt")
        artifacts[arm] = {"path": str(path), "sha256": row["sha256"], "receipt_sha256": PINS[arm]}
    records, initial_qc = {}, {}
    for seconds in (0, 60, 120, 600):
        expected = f"2026-08-16_13:{seconds // 60:02d}:00"
        loaded = {}
        for arm, artifact in artifacts.items():
            stamp, fields, _ = load_history(Path(artifact["path"]), seconds // 60)
            if stamp != expected:
                raise ValueError(f"{arm}: wrong stored timestamp")
            loaded[arm] = fields
        records[seconds] = {}
        for arm in ("HYDRO", "COUPLED", "PROJECTED"):
            item = {}
            for field in FIELDS:
                delta = loaded[arm][field] - loaded["OFF"][field]
                item[field] = {name: float(np.sqrt(np.mean(delta[mask] ** 2)))
                               for name, mask in masks.items()}
            qc = loaded[arm]["QCLOUD"] - loaded["OFF"]["QCLOUD"]
            if seconds == 0:
                initial_qc[arm] = qc.copy()
            item["QC_pattern"] = {name: pattern_metrics(initial_qc[arm][mask], qc[mask])
                                  for name, mask in masks.items()}
            records[seconds][arm + "_minus_OFF"] = item
    for artifact in artifacts.values():
        if sha(Path(artifact["path"])) != artifact["sha256"]:
            raise ValueError("history changed during analysis")
    result = {"schema": "pr101_c2_control_response_rms_v1", "history_artifacts": artifacts,
              "regions": {name: int(mask.sum()) for name, mask in masks.items()},
              "units": {name: UNITS[name] for name in FIELDS}, "records": records,
              "scope": "Unweighted Eulerian RMS on fixed support and buffer at actual common saved times; U/V/W are mass-point destaggered. OFF is a reference, not truth. No energy or observation skill claim.",
              "script_sha256": sha(Path(__file__)), "physical_approval": "FAIL_OPEN",
              "observation_skill": "NOT_EVALUATED"}
    output = Path(__file__).with_name("control_response_rms.json")
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(output)


if __name__ == "__main__":
    main()
