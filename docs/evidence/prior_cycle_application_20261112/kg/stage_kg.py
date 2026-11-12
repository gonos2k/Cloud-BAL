#!/usr/bin/env python3
"""Build an isolated selected-path graph stage after final review GO."""
import hashlib
from collections import Counter
import json
import shutil
import subprocess
import sys
from pathlib import Path
from verify_baseline import verify

SOURCE = Path(__file__).resolve().parents[4]
MAINTAINED = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
SNAPSHOT = '2026-11-12-prior-cycle-application'
GRAPH_FILES = ('graph.json', 'GRAPH_REPORT.md', 'manifest.json')

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)

def copy_graph_layer(source: Path, target: Path) -> None:
    target.mkdir(parents=True)
    for item in sorted(source.iterdir()):
        if item.is_dir():
            continue
        require(item.is_file() and not item.is_symlink(), f'unsupported graph layer member: {item}')
        if item.name != '.rebuild.lock':
            shutil.copy2(item, target / item.name)

def update_manifest_subset(manifest_path: Path, selected: list[tuple[Path, str]],
                           scan_corpus: list[Path] | None = None) -> None:
    """Update only selected rows and retain every untouched manifest row."""
    require(scan_corpus is None, 'subset update must not scan or prune the corpus')
    from graphify.detect import _md5_file

    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    original = json.loads(json.dumps(manifest))
    selected_keys = {key for _, key in selected}
    for source_path, manifest_key in selected:
        source_path = source_path.resolve()
        previous = manifest.get(manifest_key, {})
        if isinstance(previous, (int, float)):
            previous = {'mtime': previous, 'ast_hash': '', 'semantic_hash': ''}
        elif isinstance(previous, dict) and 'hash' in previous and 'ast_hash' not in previous:
            previous = {'mtime': previous.get('mtime', 0), 'ast_hash': previous['hash'],
                        'semantic_hash': ''}
        ast_hash = _md5_file(source_path)
        manifest[manifest_key] = {
            'mtime': source_path.stat().st_mtime,
            'ast_hash': ast_hash,
            'semantic_hash': previous.get('semantic_hash', '')
            if ast_hash == previous.get('ast_hash', '') else '',
        }
    require(set(original) <= set(manifest), 'subset manifest update dropped existing rows')
    for key, entry in original.items():
        if key not in selected_keys:
            require(manifest[key] == entry, f'subset manifest update changed untouched row: {key}')
    for source_path, manifest_key in selected:
        require(manifest_key in manifest, f'selected path is missing from manifest: {manifest_key}')
        require(manifest[manifest_key]['ast_hash'] == _md5_file(source_path),
                f'selected manifest hash mismatch: {manifest_key}')
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')

def graph_stats(graph: dict) -> dict:
    nodes = graph.get('nodes', [])
    return {
        'nodes': len(nodes),
        'edges': len(graph.get('links', graph.get('edges', []))),
        'communities': len({n.get('community') for n in nodes if n.get('community') is not None}),
    }

def graph_integrity(graph: dict) -> dict:
    node_list = graph.get('nodes', [])
    nodes = {node['id'] for node in node_list if 'id' in node}
    links = graph.get('links', graph.get('edges', []))
    endpoints = [(link.get('source'), link.get('target')) for link in links]
    endpoint_counts: dict[tuple, int] = {}
    exact_edges = set()
    exact_duplicates = 0
    for link, (source, target) in zip(links, endpoints):
        endpoint_counts[(source, target)] = endpoint_counts.get((source, target), 0) + 1
        encoded = json.dumps(link, sort_keys=True, separators=(',', ':'))
        if encoded in exact_edges:
            exact_duplicates += 1
        exact_edges.add(encoded)
    return {
        'missing_endpoint_edges': sum(source is None or target is None
                                      for source, target in endpoints),
        'dangling_endpoint_edges': sum(
            (source is not None and source not in nodes) or
            (target is not None and target not in nodes)
            for source, target in endpoints),
        'self_loop_edges': sum(source == target for source, target in endpoints),
        'exact_duplicate_edges': exact_duplicates,
        'same_endpoint_group_count': sum(count > 1 for count in endpoint_counts.values()),
    }

def refresh_staged_report(stage_root: Path, extracted_paths: set[str]) -> None:
    subprocess.run(
        ['graphify', 'cluster-only', str(stage_root), '--no-viz', '--no-label',
         '--graph', str(stage_root / 'graphify-out/graph.json')],
        cwd=stage_root, check=True, stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    report = stage_root / 'graphify-out/GRAPH_REPORT.md'
    require(report.is_file(), f'scoped graph report was not generated: {report}')
    with report.open('a') as stream:
        stream.write('\n## prior cycle application scoped update\n')
        stream.write(f'- Only {len(extracted_paths)} frozen source paths are structurally extracted.\n')
        stream.write('- Manifest updates are selected-path-only with scan_corpus=None; no corpus scan or prune occurs.\n')
        stream.write('- Other corpus content is retained; document semantics are not re-extracted.\n')
        stream.write('- Graph structure does not validate runtime behavior, physical assumptions, or scientific approval.\n')
        stream.write('- Fortran parsing is best-effort; cross-file CALL edges are partial.\n')

def write_staged_wiki(run: Path, records: dict, lock: dict) -> dict:
    source_commit = lock['source_commit']
    wiki = run / 'wiki'
    wiki.mkdir()
    for name in ('graph-report.md', 'graph-report-klaps50.md',
                 'graph-report-cloud-bal.md', 'index.md', 'log.md'):
        shutil.copy2(MAINTAINED / 'wiki' / name, wiki / name)
    shutil.copy2(run / 'KLAPS50/graphify-out/GRAPH_REPORT.md',
                 wiki / 'graph-report-klaps50.md')
    shutil.copy2(run / 'Cloud-BAL/graphify-out/GRAPH_REPORT.md',
                 wiki / 'graph-report-cloud-bal.md')

    index = wiki / 'graph-report.md'
    lines = index.read_text().splitlines()
    seen = set()
    for i, line in enumerate(lines):
        for label, directory, mirror in (
            ('KLAPS50', '.', 'graph-report-klaps50'),
            ('Cloud-BAL', 'Cloud-BAL/', 'graph-report-cloud-bal'),
        ):
            if line.startswith(f'| {label} |'):
                stats = records[label]['after']
                lines[i] = (f'| {label} | `{directory}` | {SNAPSHOT} (prior cycle application) | '
                            f'{stats["nodes"]} | {stats["edges"]} | {stats["communities"]} | [[{mirror}]] |')
                seen.add(label)
    require(seen == {'KLAPS50', 'Cloud-BAL'}, 'graph-report index lacks a maintained corpus row')
    index.write_text('\n'.join(lines) + '\n')

    page = wiki / 'index.md'
    content = page.read_text()
    start = content.find('## Graph snapshot')
    require(start >= 0, 'wiki index has no Graph snapshot section')
    end = content.find('\n## ', start + 3)
    if end < 0:
        end = len(content)
    section = '## Graph snapshot\n\n' + '\n'.join(
        f'- {label}: {SNAPSHOT}; {records[label]["after"]["nodes"]} nodes / '
        f'{records[label]["after"]["edges"]} edges / {records[label]["after"]["communities"]} communities.'
        for label in ('KLAPS50', 'Cloud-BAL')
    ) + f'\n- Only {len(records["KLAPS50"]["selected_manifest_keys"])} frozen source paths are extracted; other corpus content is retained; document semantics are not re-extracted.\n'
    section += '- Graph freshness does not establish runtime or scientific validation.\n'
    content = content[:start] + section + content[end:]
    import re
    content, count = re.subn(r'(?m)^(date_modified:\s*)[^\r\n]+',
                             lambda match: match.group(1) + SNAPSHOT[:10], content, count=1)
    require(count == 1, 'wiki index date_modified is missing or ambiguous')
    page.write_text(content)

    with (wiki / 'log.md').open('a') as stream:
        stream.write(f'\n## [{SNAPSHOT[:10]}] kg-update | prior cycle application\n')
        stream.write(f'- Source base `{source_commit}`; mode: selected source AST extraction and staged merge.\n')
        for label in ('KLAPS50', 'Cloud-BAL'):
            record = records[label]
            before, after = record['before'], record['after']
            stream.write(f'- {label}: {SNAPSHOT}; {after["nodes"]} nodes / {after["edges"]} edges / '
                         f'{after["communities"]} communities; delta nodes={after["nodes"] - before["nodes"]}, '
                         f'edges={after["edges"] - before["edges"]}.\n')
        stream.write(f'- {len(records["KLAPS50"]["selected_manifest_keys"])} frozen source paths structurally extracted; manifest update was selected-path-only with scan_corpus=None.\n')
        stream.write('- Other corpus content is retained; document semantics are not re-extracted.\n')
        stream.write(f'- Validation: {lock["validation_summary"]}\n')
        stream.write(f'- Open items: {lock["open_items"]}\n')
        stream.write('- Structural extraction does not establish runtime, physical, or scientific validity; '
                     'Fortran parsing is best-effort; cross-file CALL edges are partial.\n')
    return {name: sha256(wiki / name) for name in (
        'graph-report.md', 'graph-report-klaps50.md', 'graph-report-cloud-bal.md',
        'index.md', 'log.md')}

def stage_selected(lock: dict, extracted_paths: set[str], manifest_paths: set[str],
                   output: Path) -> dict:
    from graphify.build import build_merge
    from graphify.export import to_json
    from graphify.extract import extract

    run = output / f'stage-{lock["freeze_id"]}'
    require(not run.exists(), f'refuse to overwrite existing stage: {run}')
    run.mkdir(parents=True)
    roots = {'KLAPS50': run / 'KLAPS50', 'Cloud-BAL': run / 'Cloud-BAL'}
    maintained = {'KLAPS50': MAINTAINED, 'Cloud-BAL': MAINTAINED / 'Cloud-BAL'}
    for label in roots:
        copy_graph_layer(maintained[label] / 'graphify-out', roots[label] / 'graphify-out')

    records = {}
    for label in ('KLAPS50', 'Cloud-BAL'):
        stage_root = roots[label]
        graph_path = stage_root / 'graphify-out/graph.json'
        old_graph = json.loads(graph_path.read_text())
        old_node_ids = {node['id'] for node in old_graph.get('nodes', []) if 'id' in node}
        prefix = 'Cloud-BAL/' if label == 'KLAPS50' else ''
        staged_files = []
        manifest_rows = []
        for relative in sorted(extracted_paths):
            source_file = SOURCE / relative
            staged_file = stage_root / prefix / relative
            staged_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, staged_file)
            staged_files.append(staged_file)
        for relative in sorted(manifest_paths):
            source_file = SOURCE / relative
            manifest_rows.append((source_file, prefix + relative))
        extracted = extract(staged_files, cache_root=stage_root, parallel=False)
        require(not extracted.get('failed_sources'), f'{label} failed source extraction: {extracted.get("failed_sources")}')
        raw = run / f'{label}_raw_extraction.json'
        raw.write_text(json.dumps(extracted, sort_keys=True, ensure_ascii=False))
        merged = build_merge([extracted], graph_path=graph_path, root=stage_root,
                             directed=old_graph.get('directed', False), dedup=False)
        communities: dict[int, list[str]] = {}
        next_id = max((int(n.get('community', 0)) for n in old_graph.get('nodes', [])), default=0) + 1
        for node, attrs in merged.nodes(data=True):
            community = attrs.get('community')
            if community is None:
                community = next_id
                next_id += 1
            communities.setdefault(community, []).append(node)
        require(to_json(merged, communities, str(graph_path)), f'Graphify merge failed for {label}')
        new_graph = json.loads(graph_path.read_text())
        new_node_ids = {node['id'] for node in new_graph.get('nodes', []) if 'id' in node}
        removed = [node for node in old_graph.get('nodes', [])
                   if node.get('id') not in new_node_ids]
        selected_keys = {key for _, key in manifest_rows}
        require(all(node.get('source_file') in selected_keys for node in removed),
                f'{label} graph update removed nodes outside selected files: {removed}')
        def untouched_edges(graph):
            return Counter(json.dumps(edge, sort_keys=True, separators=(',', ':'))
                           for edge in graph.get('links', graph.get('edges', []))
                           if edge.get('source_file') not in selected_keys)

        before_edges = untouched_edges(old_graph)
        after_edges = untouched_edges(new_graph)
        require(not (before_edges - after_edges), f'{label}: untouched edges lost or changed')
        old_untouched_ids = {node['id'] for node in old_graph.get('nodes', [])
                             if node.get('source_file') not in selected_keys}
        require(old_untouched_ids <= new_node_ids, f'{label}: untouched nodes lost')
        update_manifest_subset(stage_root / 'graphify-out/manifest.json', manifest_rows,
                               scan_corpus=None)
        refresh_staged_report(stage_root, extracted_paths)
        new_graph = json.loads(graph_path.read_text())
        integrity = graph_integrity(new_graph)
        require(all(value == 0 for value in integrity.values()),
                f'{label} staged graph integrity failed: {integrity}')
        snapshot_dir = stage_root / 'graphify-out' / SNAPSHOT
        snapshot_dir.mkdir()
        for filename in GRAPH_FILES:
            shutil.copy2(stage_root / 'graphify-out' / filename, snapshot_dir / filename)
        records[label] = {
            'before': graph_stats(old_graph),
            'after': graph_stats(new_graph),
            'prior_node_ids_preserved': len(old_node_ids & new_node_ids),
            'untouched_edges_preserved': sum(before_edges.values()),
            'removed_selected_node_ids': sorted(node['id'] for node in removed),
            'selected_manifest_keys': [key for _, key in manifest_rows],
            'selected_source_sha256': lock['selected_source_sha256'],
            'raw_extraction_sha256': sha256(raw),
            'snapshot_file_sha256': {
                filename: sha256(snapshot_dir / filename) for filename in GRAPH_FILES
            },
            'integrity_zero_counts': integrity,
        }
    wiki_hashes = write_staged_wiki(run, records, lock)
    return {'stage': str(run), 'corpora': records, 'staged_wiki_sha256': wiki_hashes}

if __name__ == '__main__':
    # The parent supplies a reviewed lock only after all required checks pass.
    if len(sys.argv) != 3 or sys.argv[1] != '--lock':
        raise SystemExit('provide --lock to a final reviewed selection; no default stage')
    lock_path = Path(sys.argv[2])
    lock = json.loads(lock_path.read_text())
    require(lock.get('status') == 'FROZEN' and lock.get('review_status') == 'GO', 'final review GO required')
    require(lock.get('snapshot') == SNAPSHOT, 'wrong snapshot')
    require(subprocess.check_output(['graphify','--version'],text=True).strip() == 'graphify 0.9.53', 'Graphify 0.9.53 required')
    require(lock.get('baseline_sha256') == sha256(Path(__file__).parent / 'baseline.json'), 'baseline pin changed')
    require(lock.get('freeze_id') and all(c in '0123456789abcdef' for c in lock['freeze_id']), 'invalid freeze id')
    require(lock.get('source_commit') == subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip(), 'source HEAD changed')
    require(lock.get('validation_summary') and lock.get('open_items'), 'validation and open items required')
    pins = lock['selected_source_sha256']
    require(len(pins) > 0, 'expected reviewed sources')
    for relative, expected in pins.items():
        path = Path(relative)
        require(not path.is_absolute() and '..' not in path.parts and (SOURCE/path).is_file() and not (SOURCE/path).is_symlink(), 'unsafe source path')
        require(sha256(SOURCE/path) == expected, f'source changed: {relative}')
    for relative, expected in lock.get('hash_only_sha256', {}).items():
        path = Path(relative)
        require(not path.is_absolute() and '..' not in path.parts and (SOURCE/path).is_file() and not (SOURCE/path).is_symlink(), 'unsafe evidence path')
        require(sha256(SOURCE/path) == expected, f'evidence changed: {relative}')
    verify()
    output = MAINTAINED / 'scratch' / 'actual_prior_first_use_20261112' / 'kg_stage'
    result = stage_selected(lock, set(pins), set(pins), output)
    for relative, expected in pins.items():
        require(sha256(SOURCE/relative) == expected, f'source changed during extraction: {relative}')
    verify()
    result.update({'status':'STAGED_ONLY_NO_MAINTAINED_WRITES','snapshot':SNAPSHOT,
                   'selection_lock_sha256':sha256(lock_path),'selected_source_sha256':pins})
    receipt = Path(__file__).parent / 'stage_receipt.json'
    with receipt.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(result, indent=2))
