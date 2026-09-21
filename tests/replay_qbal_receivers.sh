#!/usr/bin/env bash
# Run from a bundle made with package_qbal_feasibility.py, not the source tree.
set -euo pipefail
bundle=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python3 - "$bundle" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
manifest = json.loads((root / 'manifest.json').read_text())
for name, item in manifest['artifacts'].items():
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise SystemExit('manifest path outside bundle')
    if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
        raise SystemExit('hash mismatch: ' + name)
print('Bundled artifact hashes verified')
PY
replay=$(mktemp -d "$bundle/replay.XXXXXX")
python3 "$bundle/scripts/diagnose_qbal_receivers.py" \
  --snapshot "$bundle/inputs/operator_snapshot.bin" \
  --rows "$bundle/inputs/rows.O0.bin" \
  --candidate "$bundle/candidates/bounded_candidate.npz" \
  --output "$replay/receivers.json" --arrays "$replay/receivers.npz"
python3 - "$bundle" "$replay" <<'PY'
import json, sys
from pathlib import Path
import numpy as np
root, replay = map(Path, sys.argv[1:])
expected = json.loads((root / 'outputs/receiver_diagnostic.json').read_text())
actual = json.loads((replay / 'receivers.json').read_text())
# ZIP container metadata is not an array identity test; compare every array.
expected.pop('arrays_sha256')
actual.pop('arrays_sha256')
if actual != expected:
    raise SystemExit('receiver report differs from bundled reference')
with np.load(replay / 'receivers.npz', allow_pickle=False) as actual:
    for name in ('receivers/receiver_arrays.npz', 'hypothetical_faces/face_set.npz'):
        with np.load(root / name, allow_pickle=False) as expected:
            for key in expected.files:
                if key not in actual or not np.array_equal(actual[key], expected[key]):
                    raise SystemExit('receiver/face array differs: ' + key)
    with np.load(root / 'inputs/root_omega_controls.npz', allow_pickle=False) as original:
        for old, new in (('source', 'face_active_index'), ('directions', 'face_direction'),
                         ('stored_ijk', 'face_stored_ijk')):
            if not np.array_equal(original[old], actual[new]):
                raise SystemExit('historical control inventory differs: ' + old)
        reconstructed = actual['receiver_ijk'][actual['face_receiver_index']]
        if not np.array_equal(original['receiver_ijk'], reconstructed):
            raise SystemExit('historical control receiver coordinates differ')
print('PASS_SCOPED receiver report and all bundled row/face arrays match')
print('This replays a historical candidate; no production boundary permission is granted.')
PY
printf 'Replay retained: %s\n' "$replay"
