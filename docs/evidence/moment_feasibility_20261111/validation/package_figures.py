#!/usr/bin/env python3
"""Package the report, analytical figure and supporting values without a PDF."""
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = Path('docs/evidence/moment_feasibility_20261111')
REPORT = Path('docs/MOMENT_FEASIBILITY_20261111.md')
REMOTE = 'https://github.com/gonos2k/Cloud-BAL/blob/research/moment-feasibility/'


def main():
    paths = [REPORT,Path('docs/MODEL_MOMENT_HANDOFF.md'), BUNDLE/'FIGURES.md',
             BUNDLE/'figures/01_ice_feasibility.png',BUNDLE/'figures/ice_feasibility_curve.csv',
             BUNDLE/'science/feasibility_recount.json',BUNDLE/'science/README.md',
             BUNDLE/'science/phase_consumer.md',BUNDLE/'validation/validation_receipt.json']
    members = {}
    source_hashes = {}
    for path in paths:
        raw = (ROOT/path).read_bytes()
        source_hashes[str(path)] = hashlib.sha256(raw).hexdigest()
        if path.suffix == '.md':
            def portable(match):
                target = match.group(1)
                if '://' in target or target.startswith('#'):
                    return match.group(0)
                relative = (path.parent/target).as_posix()
                from posixpath import normpath
                relative = normpath(relative)
                return '('+(target if Path(relative) in paths else REMOTE+relative)+')'
            raw = re.sub(r'(?<=\])\(([^\s()]+)\)',portable,raw.decode()).encode()
        members[str(path)] = raw
    output = ROOT/BUNDLE/'all_figures.zip'
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,raw in sorted(members.items()):
            info = zipfile.ZipInfo(name,date_time=(2026,11,11,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info,raw)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(members)
        for name,raw in members.items():
            assert archive.read(name) == raw
    receipt = {'status':'PASS','zip_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
               'source_sha256':source_hashes,'members_sha256':{n:hashlib.sha256(b).hexdigest() for n,b in members.items()},
               'markdown_conversion':'Links to included members remain relative; remaining repository references use the research branch URL.',
               'scope':'One analytical PNG and values; no forecast figure or PDF.'}
    with (ROOT/BUNDLE/'validation/figure_package_receipt.json').open('x') as stream:
        stream.write(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':'PASS','members':len(members)}))


if __name__=='__main__':
    main()
