"""Load receipt-bound, losslessly packaged analysis arrays."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ANALYSIS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools'))
from pack_cp02_selected_npz import load_partarrays

MANIFESTS = {
    'B1_native_wrapper': '2d6a6fb716de26f7abb4428d85137c92b33a242e7d35b1e83c796e21163dff09',
    'DM065_native_wrapper': '5bc658ead82af6b75984c7c5af365ecb0c3fad80afcdd0209b51c0ff44b209fd',
    'B1_point_timeseries': '6e01155be21deff6070ee609185f1a87f9766caa51d905e96397546248ceb324',
    'DM065_point_timeseries': '2965aa78547d1cd58c47cbd5efdc080a67b2187bd734f1c907602777915b36d0',
    'paired_differences': 'ecc4729ce321510e93aaef118e9b578464cb46776b8f5c3fbca74c55dd851440',
}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(stem, source_sha256, names):
    if sha(ROOT / 'tools/pack_cp02_selected_npz.py') != '3c929e783856119daebf5b35487a0b10330d368db201024e5e57e7b37c34fb4d':
        raise ValueError('parts loader differs')
    path = ANALYSIS / (stem + '_parts') / (stem + '.parts.json')
    if sha(path) != MANIFESTS[stem]:
        raise ValueError('parts manifest differs')
    if json.loads(path.read_text())['source_sha256'] != source_sha256:
        raise ValueError('original array identity differs from capture receipt')
    return load_partarrays(path, names=names)
