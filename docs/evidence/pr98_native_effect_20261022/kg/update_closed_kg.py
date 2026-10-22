#!/usr/bin/env python3
"""Run the guarded follow-up KG overlay after PR98's 640-second audit closes."""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[4]
ROOT = SOURCE.parents[2]
MAINT = ROOT / 'Cloud-BAL'
BASE = '4d0baf151cd2669437f0341307c095fa95fb92e5'
FIRST_RECEIPT = MAINT / 'scratch/pr98_native_effect_20261022/kg/kg_receipt.json'
FIRST_RECEIPT_SHA = 'ce651957174ff90cf9ea104fafc9e407fa39590c6825d29ca3910ccf640eaf4d'
FIRST_HELPER = ROOT / 'scratch/pr98_kg_source_frozen_20261022/Cloud-BAL/docs/evidence/pr98_native_effect_20261022/kg/update_kg.py'
FIRST_HELPER_SHA = 'd3e54ce6929b9e8fa0857e2a63a2cf4c595b642f5c09173d6956e1925b9733d2'
HELPER = Path(__file__).with_name('update_kg.py')
HELPER_SHA = '92ca3f6aa630807dfde2e7fbb1559b87a1ba0d3f746e211a993be963be01d685'
SNAPSHOT = '2026-10-22-pr98-closed640'
OUT = MAINT / 'scratch/pr98_native_effect_closed_20261022/kg'
RESULTS_AUDIT_STATE = (
    'C1 600-second baseline closed; all three PR98 C1 640-second runs INCOMPLETE '
    'at 620 seconds/31 steps (rc=1); generic audit FAIL; physical approval FAIL_OPEN; '
    'observation skill NOT_EVALUATED'
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def engine():
    require(digest(FIRST_RECEIPT) == FIRST_RECEIPT_SHA, 'first PR98 KG receipt hash drift')
    receipt = json.loads(FIRST_RECEIPT.read_text())
    require(receipt['status'] == 'PASS' and receipt['source_commit'] == BASE,
            'first PR98 KG receipt identity/status drift')
    require(digest(FIRST_HELPER) == FIRST_HELPER_SHA, 'frozen first-phase helper hash drift')
    frozen_root = FIRST_HELPER.parents[4]
    frozen_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=frozen_root, text=True).strip()
    require(frozen_head == BASE and not subprocess.check_output(
        ['git', 'status', '--porcelain'], cwd=frozen_root, text=True),
        'first-phase helper worktree is not clean at its pinned commit')
    require(digest(HELPER) == HELPER_SHA, 'current guarded helper hash drift')
    spec = importlib.util.spec_from_file_location('pr98_closed_kg_base', HELPER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.PRIOR, module.PRIOR_SHA = FIRST_RECEIPT, FIRST_RECEIPT_SHA
    module.PRIOR_HELPER, module.PRIOR_HELPER_SHA = FIRST_HELPER, FIRST_HELPER_SHA
    module.BASE, module.OUT, module.SNAPSHOT = BASE, OUT, SNAPSHOT
    module.EXPECTED_DATED_SNAPSHOTS = 108
    module.RESULTS_AUDIT_STATE = RESULTS_AUDIT_STATE
    module.GRAPH_PINS = {name: receipt['corpora'][name]['sha256'] for name in ('KLAPS50', 'Cloud-BAL')}
    return module


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--pr-url', required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--check-only', action='store_true')
    modes.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    updater = engine()
    require(not OUT.exists(), 'refuse existing closed-640 KG output directory')
    plan = updater.preflight(args.commit, args.pr_url)
    if args.check_only:
        print(json.dumps({'status': 'CHECK_ONLY_NO_WRITES', **plan}, indent=2))
    else:
        updater.apply(plan)


if __name__ == '__main__':
    main()
