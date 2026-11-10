#!/usr/bin/env python3
"""Compare every WRF archive object and linked libraries to the MP10 parent."""
import hashlib,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
RUNTIME=ROOT.parent/'runtime/nn_end'
PARENT=ROOT.parent.parent/'b1_pulse_path_20261110/runtime/native_build/variants/MP10'
CANDIDATE=RUNTIME/'native_build/variants/MP10_NN_END'

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def members(path):
    result=[];longnames=b''
    with path.open('rb') as f:
        if f.read(8)!=b'!<arch>\n':raise ValueError('not an ar archive')
        while head:=f.read(60):
            if len(head)!=60 or head[58:]!=b'`\n':raise ValueError('invalid ar header')
            size=int(head[48:58]);name=head[:16].decode('ascii').strip();data=f.read(size)
            if len(data)!=size:raise ValueError('truncated archive')
            if size%2:f.read(1)
            if name=='//':longnames=data;continue
            if name in ('/','/SYM64/'):continue
            if name.startswith('/') and name[1:].isdigit():
                offset=int(name[1:]);end=longnames.find(b'/\n',offset)
                if end<0:raise ValueError('invalid ar long name')
                name=longnames[offset:end].decode('utf-8')
            else:name=name.removesuffix('/')
            result.append((name,hashlib.sha256(data).hexdigest()))
    return result

def main():
    a=json.loads((CANDIDATE/'build_receipt.json').read_text());b=json.loads((PARENT/'build_receipt.json').read_text())
    if a['status']!='PASS' or b['status']!='PASS' or a['input_manifest_sha256']!=b['input_manifest_sha256']:raise ValueError('build or frozen inputs differ')
    if a['compiler']['sha256']!=b['compiler']['sha256'] or a['linker']['sha256']!=b['linker']['sha256'] or a['ldd']['resolved_libraries']!=b['ldd']['resolved_libraries']:raise ValueError('compiler, linker or linked libraries differ')
    old=members(PARENT/'libwrflib.a');new=members(CANDIDATE/'libwrflib.a')
    if [x[0] for x in old]!=[x[0] for x in new]:raise ValueError('archive member inventory differs')
    differences=[name for (name,oldhash),(_,newhash) in zip(old,new) if oldhash!=newhash]
    if differences!=['module_mp_kdm6.o']:raise ValueError(f'unexpected changed objects: {differences}')
    result={'status':'PASS','parent_build_receipt_sha256':sha(PARENT/'build_receipt.json'),'candidate_build_receipt_sha256':sha(CANDIDATE/'build_receipt.json'),'input_manifest_sha256':a['input_manifest_sha256'],'compiler_sha256':a['compiler']['sha256'],'linker_sha256':a['linker']['sha256'],'linked_libraries':a['ldd']['resolved_libraries'],'archive_members':len(old),'changed_members':differences,'unchanged_members':len(old)-1,'candidate_module_sha256':next(h for name,h in new if name==differences[0]),'parent_module_sha256':next(h for name,h in old if name==differences[0]),'method':'hash every member from both GNU ar archives and compare ordered inventories, including duplicate member names; compare pinned compiler/linker and resolved shared libraries'}
    (HERE/'proof/build_comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
