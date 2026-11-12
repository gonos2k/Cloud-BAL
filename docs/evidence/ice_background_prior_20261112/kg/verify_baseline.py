#!/usr/bin/env python3
"""Verify the maintained roots still match the read-only pre-update inventory."""
import json
from pathlib import Path

from capture_baseline import (GRAPH_FILES, MAINTAINED, SOURCE, WIKI_FILES,
                              dated_inventory, git_state, sha256)


def verify():
    baseline = json.loads((Path(__file__).parent / 'baseline.json').read_text())
    assert baseline['maintained_roots_written'] is False
    for label, root in [('KLAPS50', MAINTAINED), ('Cloud-BAL', MAINTAINED / 'Cloud-BAL')]:
        expected = baseline['maintained_roots'][label]
        assert dated_inventory(root) == expected['dated_snapshots'], f'{label}: dated snapshots changed'
        assert git_state(root) == expected['git_state'], f'{label}: HEAD or status changed'
        actual = {name: sha256(root / 'graphify-out' / name) for name in GRAPH_FILES}
        assert actual == expected['active_graph_trio_sha256'], f'{label}: active graph changed'
    assert {name: sha256(MAINTAINED / 'wiki' / name) for name in WIKI_FILES} == baseline['wiki_mirror_sha256'], 'wiki changed'
    assert sha256(MAINTAINED / 'AGENTS.md') == baseline['agents_sha256'], 'AGENTS.md changed'
    assert {name: sha256(SOURCE / 'graphify-out' / name) for name in GRAPH_FILES} == baseline['source_worktree']['active_graph_trio_sha256'], 'worktree graph changed'
    print(f'PASS: {baseline["dated_snapshot_count_total"]} dated snapshots, active graph trios, statuses, wiki, AGENTS unchanged')


if __name__ == '__main__':
    verify()
