#!/usr/bin/env python3
"""Package the report, native diagnostic PNG and supporting evidence."""
import hashlib
import json
from pathlib import Path
from posixpath import normpath
import re
import zipfile

ROOT=Path(__file__).resolve().parents[4]
BUNDLE=Path('docs/evidence/ice_partition_policy_20261111')
REMOTE='https://github.com/gonos2k/Cloud-BAL/blob/research/ice-partition-policy/'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    paths=[Path('docs/ICE_SNOW_JOINT_INITIALIZATION_20261111.md'),Path('docs/MODEL_MOMENT_HANDOFF.md'),
           BUNDLE/'FIGURES.md',BUNDLE/'contract/policy.json',BUNDLE/'science/partition_authority.md',
           BUNDLE/'science/density_boundary.md',BUNDLE/'analysis/density_recount.json',
           BUNDLE/'figures/native_handoff.png',BUNDLE/'figures/native_handoff.csv',BUNDLE/'figures/provenance.json',
           BUNDLE/'native/README.md',BUNDLE/'native/receipt.json',BUNDLE/'validation/receipt.json']
    sources={}
    members={}
    for path in paths:
        raw=(ROOT/path).read_bytes()
        sources[str(path)]=digest(raw)
        if path.suffix=='.md':
            def portable(match):
                target=match.group(1)
                if '://' in target or target.startswith('#'):
                    return match.group(0)
                base,mark,fragment=target.partition('#')
                relative=normpath(str(path.parent/base))
                return '('+(target if Path(relative) in paths else REMOTE+relative+mark+fragment)+')'
            raw=re.sub(r'(?<=\])\(([^\s()]+)\)',portable,raw.decode()).encode()
        members[str(path)]=raw
    archive_path=ROOT/BUNDLE/'all_figures.zip'
    with zipfile.ZipFile(archive_path,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,raw in sorted(members.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,11,11,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            archive.writestr(info,raw)
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist())==set(members)
        assert all(archive.read(name)==raw for name,raw in members.items())
    receipt={'status':'PASS','zip_sha256':digest(archive_path.read_bytes()),'source_sha256':sources,
             'members_sha256':{name:digest(raw) for name,raw in members.items()},
             'scope':'One historical native diagnostic PNG and supporting values; no forecast chart or PDF.',
             'markdown_conversion':'Included files retain relative links and fragments; other repository targets use the research branch.'}
    with (ROOT/BUNDLE/'validation/figure_package_receipt.json').open('x') as stream:
        json.dump(receipt,stream,indent=2);stream.write('\n')
    print(json.dumps({'status':'PASS','members':len(members)}))


if __name__=='__main__':
    main()
