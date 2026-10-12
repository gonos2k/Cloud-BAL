"""Post-run verifier shim: expand comma-separated status logs only."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

repo, run_root, original_tool, archived_helper = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("original_cp06a_receipt", original_tool)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load original receipt verifier")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def read_log(path: Path) -> tuple[str, dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        fields[key] = value  # Keep original first-field value unchanged.
        scope = key.split("_", 1)[0]
        for token in value.split(",")[1:]:
            if "=" not in token:
                continue
            subkey, subvalue = token.split("=", 1)
            subkey, subvalue = subkey.strip(), subvalue.strip()
            qualified = f"{scope}_{subkey}" if scope in {"OFF", "HYDRO", "COUPLED"} else subkey
            fields[qualified] = subvalue
    return text, fields


module.read_log = read_log
receipt = module.verify_run(run_root, repo)
helper_bytes = Path(__file__).read_bytes()
helper_sha = hashlib.sha256(helper_bytes).hexdigest()
receipt["verification_correction"] = {
    "helper_path": str(archived_helper),
    "helper_sha256": helper_sha,
    "original_tool_path": str(original_tool),
    "original_tool_sha256": hashlib.sha256(original_tool.read_bytes()).hexdigest(),
    "scope": "comma-separated run-log key extraction only; no verification criteria, source, or physics changes",
}
output = run_root / "producer_receipt.json"
output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(f"producer_receipt={output}")
print(f"decision={receipt['decision']}")
print(f"verification_helper_sha256={helper_sha}")
