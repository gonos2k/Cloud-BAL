#!/usr/bin/env python3
"""Validate a detached, self-contained cold OFF evidence bundle before commit.

This contract grants no dynamic target, science, or operational authority.
Git HEAD is lineage only; executable/source/runtime/input bytes are mandatory.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import stat
import numpy as np
from netCDF4 import Dataset
from cloud_bal_transaction import _stable_regular_bytes
from compare_baseline import read_wps

CONTRACT = 'MATCHED_CONTROL_COLD_OFF_V4'
CONTROLS = {'GA_REF_THRESH':'25.0','GA_VV_FOR_ST':'0.017','GA_VV_TO_HEIGHT_RATIO_CT':'1.3',
 'GA_VV_TO_HEIGHT_RATIO_CU':'0.5','GA_VV_TO_HEIGHT_RATIO_SC':'0.10',
 'KMP_DETERMINISTIC_REDUCTION':'yes','OMP_DYNAMIC':'false','OMP_MAX_ACTIVE_LEVELS':'1'}
FIELDS3 = dict(pressure='Pa',temperature='K',vapor='kg kg-1 dryair',u='m s-1',v='m s-1',
 omega='Pa s-1',omega_target='Pa s-1',omega_target_sigma='Pa s-1',geopotential='m2 s-2',
 cloud_fraction='1',radar_reflectivity='dBZ',cloud_water='kg kg-1 dryair',cloud_ice='kg kg-1 dryair',
 rain='kg kg-1 dryair',snow='kg kg-1 dryair',graupel='kg kg-1 dryair',vt_z_mean='m s-1',
 vt_z_sigma='m s-1',cloud_omega_evidence='Pa s-1')
FIELDS2 = dict(surface_pressure='Pa',surface_temperature='K',surface_vapor='kg kg-1 dryair',
 surface_height='m',latitude='degree_north',omega_top_boundary='Pa s-1',omega_bottom_boundary='Pa s-1')
CATEGORIES = dict(cloud_type='cloud_type_v1',precipitation_phase='precipitation_phase_v1',lightning_support='binary_v1')
SCALARS = {'longitude':('f4',('y','x'),'degree_east'), 'grid_dx':('f8',('y','x'),'m'),
 'grid_dy':('f8',('y','x'),'m'),'pressure_interface':('f8',('z_interface','y','x'),'Pa'),
 'cell_dp':('f8',('z','y','x'),'Pa'),'level_spacing_dp':('f8',('z_spacing','y','x'),'Pa'),
 'pressure_mass_measure':('f8',('z','y','x'),'kg'),'dry_air_mass_measure':('f8',('z','y','x'),'kg dryair')}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def json_file(path):
    return json.loads(_stable_regular_bytes(path)[0])


def check_payload(path, valid_time, stage):
    with Dataset(path) as ds:
        ds.set_auto_maskandscale(False)
        required={'cloud_bal_exchange_version':1,'cloud_bal_schema_version':5,'stage':stage,
          'valid_time':valid_time,'reference_time':valid_time,'grid_id':'NE57_LAPS_PRESSURE',
          'canonical_vertical_order':'bottom_to_top','wind_coordinate':'GRID_RELATIVE',
          'dynamic_target_authorized':0,'radar_los_present':0,'netcdf_variable_order':'record,z,y,x',
          'longitude_units':'degree_east','canonical_nx':235,'canonical_ny':283,'canonical_nz':22}
        for name,value in required.items():
            require(name in ds.ncattrs() and ds.getncattr(name)==value,f'payload identity {name}')
        require({n:len(v) for n,v in ds.dimensions.items()}==dict(x=235,y=283,z=22,z_interface=23,z_spacing=21,record=1),'payload dimensions')
        expected=set(SCALARS)|{'above_ground','obs_support','hydro_support','balance_beta'}
        for name in (*FIELDS3,*FIELDS2,*CATEGORIES):
            expected.update(name+suffix for suffix in ('','_valid','_quality','_source'))
        require(set(ds.variables)==expected,'payload complete variable inventory')
        for name,(dtype,dims,units) in SCALARS.items():
            variable=ds[name]
            require(variable.dtype==np.dtype(dtype) and variable.dimensions==dims and variable.getncattr('units')==units,f'geometry metadata {name}')
        for name in ds.variables:
            values=ds[name][:]
            require(np.isfinite(values).all(),f'nonfinite payload {name}')
            if name.endswith('_valid') or name=='above_ground':
                require(np.isin(values,[0,1]).all(),f'invalid mask {name}')
            if name.endswith('_source') or name in ('obs_support','hydro_support'):
                require(((values>=0)&(values<=8191)).all(),f'unknown source bits {name}')
            if name.endswith('_quality'):
                require(((values>=0)&(values<=1023)).all(),f'unknown quality bits {name}')
        for fields,dims in ((FIELDS3,('record','z','y','x')),(FIELDS2,('record','y','x')),(CATEGORIES,('record','z','y','x'))):
            for name,units in fields.items():
                variable=ds[name];categorical=name in CATEGORIES
                require(variable.dimensions==dims and variable.dtype==np.dtype('i4' if categorical else 'f4'),f'field layout {name}')
                require(variable.getncattr('valid_time')==valid_time and variable.getncattr('field_kind')==('categorical' if categorical else 'continuous'),f'field clock/kind {name}')
                require(variable.getncattr('code_table' if categorical else 'units')==units,f'field units/code table {name}')
                for suffix,encoding in (('_valid','0=invalid,1=valid'),('_quality','canonical_quality_bits_v1'),('_source','canonical_source_bits_v1')):
                    m=ds[name+suffix]
                    require(m.dimensions==dims and m.dtype==np.dtype('i4') and m.getncattr('mask_encoding')==encoding,f'field metadata {name+suffix}')
        require(not np.any(ds['omega_target_valid'][:]) and not np.any(ds['omega_target_sigma_valid'][:]),'OFF cannot carry dynamic targets/sigma')
        pressure=ds['pressure'][0]
        require(np.array_equal(ds['pressure_valid'][:],ds['above_ground'][:]) and np.all(pressure>0) and np.all(np.diff(pressure,axis=0)<0),'pressure order/support')
        require(np.all(np.diff(ds['pressure_interface'][:],axis=0)<=0),'interface pressure order')
        require(np.array_equal(ds['cell_dp'][:],-np.diff(ds['pressure_interface'][:],axis=0)), 'clipped pressure-cell geometry')
        require(np.array_equal(ds['cell_dp'][:]>0,ds['above_ground'][0].astype(bool)),'below-ground cell support')
        for name in ('grid_dx','grid_dy','level_spacing_dp'):
            require(np.all(ds[name][:]>0),f'positive geometry {name}')
        require(np.all(ds['dry_air_mass_measure'][:]>=0),'dry mass measure')
        require(np.all((ds['balance_beta'][:]>=0)&(ds['balance_beta'][:]<=1)),'balance beta')
        return {n:ds.getncattr(n) for n in ds.ncattrs()}


def compare_payloads(before, after, valid_time):
    a_id=check_payload(before,valid_time,'deriv_off');b_id=check_payload(after,valid_time,'balance_off')
    allowed={'stage','producer_source_sha256','producer_binary_sha256','input_manifest_sha256'}
    require(set(a_id)==set(b_id),'payload global metadata inventory')
    require({k for k in a_id if a_id[k]!=b_id[k]}==allowed,'OFF identity transition')
    with Dataset(before) as a,Dataset(after) as b:
        a.set_auto_maskandscale(False);b.set_auto_maskandscale(False)
        for name in a.variables:
            require(np.array_equal(a[name][:],b[name][:]),f'OFF state changed {name}')
            require({k:str(a[name].getncattr(k)) for k in a[name].ncattrs()}=={k:str(b[name].getncattr(k)) for k in b[name].ncattrs()},f'OFF field metadata changed {name}')
    return a_id,b_id


def check_wps(path, reference, valid_time):
    require(sha(path)==sha(reference),'original WPS bytes differ')
    fields=read_wps(path);date=datetime.fromtimestamp(valid_time,timezone.utc).strftime('%Y-%m-%d_%H:%M:%S')+'.0000'
    levels=set(float(x) for x in range(5000,100001,5000))|{200100.0}
    expected={(name,level,date) for name in ('HGT','RH','TT','UU','VV') for level in levels}
    expected|={('PMSL',201300.0,date),('PSFC',200100.0,date),('SKINTEMP',200100.0,date)}
    require(set(fields)==expected and len(fields)==108,'cold WPS field/time/level inventory')
    for key,(units,shape,slab,metadata) in fields.items():
        require(shape==(235,283) and np.isfinite(slab).all(),'WPS shape/finite values')
        require(metadata['projection']==3 and metadata['wind_grid_relative'],'WPS projection/frame')


def resolve_link_path(path,symlink_target):
    """Resolve POSIX components using only the supplied symlink observations."""
    require(isinstance(path,str) and path.startswith('/') and not any(c in path for c in '\r\n\0'),'absolute link path')
    pending=path.split('/');resolved=[];used=set();redirects=0
    while pending:
        part=pending.pop(0)
        if part in ('','.'):continue
        if part=='..':
            if resolved:resolved.pop()
            continue
        candidate='/'+('/'.join(resolved+[part]));target=symlink_target(candidate)
        if target is None:resolved.append(part);continue
        require(isinstance(target,str) and target and not any(c in target for c in '\r\n\0'),'symlink target')
        redirects+=1;require(redirects<=128,'symlink cycle/limit');used.add(candidate)
        if target.startswith('/'):resolved=[]
        pending=target.split('/')+pending
    return '/'+('/'.join(resolved)),used


def check_link_resolution(link,obj):
    observation=json_file(obj(link['symlink_observation']))
    require(observation['scope']=='POST_BUILD_SYMLINK_OBSERVATION','symlink observation scope')
    edges=observation['links'];require(isinstance(edges,dict),'symlink edge map');used=set()
    for logical,canonical in link['resolved_load_paths'].items():
        resolved,visited=resolve_link_path(logical,edges.get);used.update(visited)
        require(resolved==canonical,'logical LOAD canonical path binding')
    require(used==set(edges),'unused/missing symlink edges')


def check_adapter_artifacts(name,node,receipt):
    expected_helpers={str(Path(__file__).resolve().with_name(filename)) for filename in
        ('cloud_bal_transaction.py','run_bound_executable.py','run_detached_runtime.py','landlock_policy.py')}
    helpers=receipt['helper_source_observed_sha256']
    require(set(helpers)==expected_helpers,'adapter helper role inventory')
    roles={'context','coordinator','link_observation','log'}
    if name in ('export','balance'):roles.add('input_identity_manifest')
    require(set(node['artifacts'])==expected_helpers|roles,'adapter artifact role inventory')
    require({path:node['artifacts'][path] for path in helpers}==helpers,'adapter helper receipt binding')
    require(node['artifacts']['coordinator']==receipt['coordinator_source_sha256'],'adapter coordinator receipt binding')


def check_link_pins(link,node,build,optimization,obj):
    """Verify recorded discovery/pin/final-link ordering and all declared LOAD bytes."""
    require(link['scope']=='DISCOVERY_PIN_FINAL_LINK_VERIFIED','prospective link scope')
    require(link['resolution_scope']=='POST_BUILD_PATH_RESOLUTION_TO_EXACT_PINNED_BYTES','link path resolution scope')
    final=obj(link['link_map']).read_text();discovery=obj(link['discovery_map']).read_text()
    names=lambda text:{line[5:] for line in text.splitlines() if line.startswith('LOAD ')}
    require(names(final)==names(discovery)==set(link['resolved_load_paths']),'discovery/final LOAD inventory')
    require(all(name.startswith('/') for name in names(final)),'absolute LOAD paths')
    require(set(link['resolved_load_paths'].values())==set(link['files']),'resolved LOAD inventory')
    check_link_resolution(link,obj)
    link_bytes=obj(link['link_manifest']).read_bytes();compile_bytes=obj(link['compile_manifest']).read_bytes()
    pinned={line.split('  ',1)[1]:line.split('  ',1)[0] for line in link_bytes.decode().splitlines()}
    require(pinned==link['files'],'prospective link manifest bytes')
    require(obj(node['manifests'][0]).read_bytes()==compile_bytes+link_bytes,'compile/link manifest assembly')
    for key in pinned.values():obj(key)
    require(all(node['sources'].get(path)==key for path,key in pinned.items()),'link leaves bound to launch manifest')
    for suffix in ('/tools/build_upstream_producer.sh','/tools/pin_link_inputs.py'):
        require(sum(path.endswith(suffix) for path in node['sources'])==1,'prospective link recipe/helper source')
    log=obj(link['build_log']).read_text();lines=log.splitlines()
    links=[i for i,line in enumerate(lines) if line=='+ link_stage']
    pin=[i for i,line in enumerate(lines) if line.startswith('+ python3 ') and '/tools/pin_link_inputs.py ' in line and not line.endswith(' --verify')]
    verified=[i for i,line in enumerate(lines) if line.startswith('+ python3 ') and '/tools/pin_link_inputs.py ' in line and line.endswith(' --verify')]
    require(len(links)==2 and len(pin)==len(verified)==1 and links[0]<pin[0]<links[1]<verified[0],'discovery/pin/final/verify ordering')
    build_root=str(Path(build['executable']).parent)
    require(all(build_root+'/link.map '+build_root+'/link_inputs.sha256' in lines[i] for i in pin+verified),'build log link manifest identity')
    require('OPTIMIZATION '+optimization in lines and 'BUILD_AND_LINK_PASS; NOT_EXECUTED; NOT_GENERATION_READY' in lines,'build optimization/completion')


def parse_hash_manifest(path):
    entries={}
    for line in path.read_text().splitlines():
        match=re.fullmatch(r'([0-9a-f]{64})  (/.+)',line)
        require(match is not None,'compiler manifest encoding')
        key,name=match.groups()
        require(name not in entries,'duplicate compiler path digest')
        entries[name]=key
    require(entries,'empty compiler manifest')
    return entries


def compiler_trace_lines(path):
    """Keep original line numbers while joining per-PID unfinished syscalls."""
    lines=path.read_text().splitlines();pending=None;completed={}
    for number,line in enumerate(lines,1):
        if '<unfinished ...>' in line:
            require(pending is None,'overlapping compiler trace syscall')
            pending=(number,line.split('<unfinished ...>',1)[0]);continue
        resumed=re.match(r'^<\.\.\. \w+ resumed>(.*)$',line)
        if resumed:
            require(pending is not None,'unmatched compiler resumed syscall')
            completed[pending[0]]=pending[1]+resumed.group(1);pending=None
        else:completed[number]=line
    require(pending is None,'unfinished compiler trace syscall')
    return completed,len(lines)


def check_compiler_audit(audit,node,build,producer,optimization,obj):
    """Bind the selected exec/open audit to this exact accepted build and ELF.

    Trace bytes and recorded classifications are evidence, not an assertion
    that untraced syscall families or kernel virtual state were snapshotted.
    """
    receipt=json_file(obj(audit['receipt']));records=audit['records']
    require(receipt['status']=='PASS_COMPILER_INPUTS_PINNED_BEFORE_FRESH_BUILD','compiler audit success')
    require(receipt['producer']==producer and receipt['optimization']==optimization,'compiler stage/optimization binding')
    accepted=str(Path(build['executable']).parent);discovery=receipt['discovery_build']
    require(receipt['accepted_build']==accepted and discovery!=accepted,'compiler accepted build binding')
    evidence={r['path']:r['sha256'] for r in receipt['evidence']}
    require(len(evidence)==len(receipt['evidence']),'duplicate compiler evidence role')
    manifests=[p for p in evidence if p.endswith('/compiler_inputs.sha256')]
    require(len(manifests)==1,'compiler manifest role')
    manifest_path=manifests[0];owner=str(Path(manifest_path).parent)
    expected_names={manifest_path,owner+'/discovery_receipt.json',owner+'/final_receipt.json',
        owner+'/discovery/build.log',owner+'/final/build.log',accepted+'/inputs.sha256',accepted+'/executable.sha256'}
    require(set(evidence)==expected_names,'compiler evidence role inventory')
    require(evidence[accepted+'/inputs.sha256']==node['manifests'][0],'compiler launch manifest binding')
    executable=parse_hash_manifest(obj(evidence[accepted+'/executable.sha256']))
    require(executable=={build['executable']:node['executable']},'compiler accepted executable binding')
    tools=Path(__file__).resolve().parent
    expected_sources={str(tools/name) for name in ('build_audited_upstream.py','build_upstream_producer.sh','pin_compiler_inputs.py')}
    require(set(receipt['sources'])==expected_sources,'compiler audit source inventory')
    require(all(node['sources'].get(p)==h for p,h in receipt['sources'].items()),'compiler audit executed source binding')
    pinned=parse_hash_manifest(obj(evidence[manifest_path]))
    require(all(node['sources'].get(p)==h for p,h in pinned.items()),'compiler leaf launch binding')
    require(node['sources'].get(accepted+'/compiler_inputs.sha256')==evidence[manifest_path],'compiler retained manifest binding')
    precheck=obj(audit['precheck']).read_text().splitlines()
    require(precheck==[p+': OK' for p in pinned],'compiler precompile byte-check log')
    expected={**receipt['sources'],**evidence,**pinned,receipt['tracer']['path']:receipt['tracer']['sha256'],accepted+'/compiler_inputs.precheck.log':audit['precheck']}
    require(receipt['tracer']['sha256']=='28f957c227012de0b18d1bd7fff2d396cb693ea60ed8013be68de071e84b5001','compiler tracing tool identity')
    require(all(records.get(p)==h for p,h in expected.items()),'compiler path-specific evidence digest binding')
    graph=json_file(obj(audit['symlink_observation']))
    require(graph['scope']=='POST_BUILD_SYMLINK_OBSERVATION','compiler path observation scope')
    edges=graph['links'];visited=set()
    for phase in ('discovery','final'):
        trace=json_file(obj(evidence[owner+'/'+phase+'_receipt.json']))
        require(trace['schema']=='cloud-bal-compiler-inputs-v1' and not trace['unresolved'] and not trace['truncated'],'compiler trace parse status')
        require(trace['manifest']==manifest_path and trace['manifest_sha256']==evidence[manifest_path],'compiler trace manifest binding')
        require(trace['tracer']==receipt['tracer'],'compiler trace tool binding')
        roots=[owner,discovery]+([accepted] if phase=='final' else [])
        require(trace['generated_roots']==roots,'compiler generated-root boundary')
        trace_dir=owner+'/'+phase+'/trace'
        require(trace['trace_dir']==trace_dir,'compiler trace directory role')
        traces=trace['trace_sha256']
        require(set(trace['trace_files'])==set(traces) and len(trace['trace_files'])==len(traces) and traces,'compiler trace inventory')
        require(all(str(Path(p).parent)==trace_dir and Path(p).name.startswith('events.') for p in traces),'compiler trace path role')
        require(all(records.get(p)==h for p,h in traces.items()),'compiler trace path/digest binding')
        expected.update(traces)
        # Trace bytes are detached under their original per-process identities.
        trace_lines={p:compiler_trace_lines(obj(h)) for p,h in traces.items()}
        observations=trace['observations'];selected={}
        for event in observations:
            require(event['trace_file'] in traces and 1<=event['line']<=trace_lines[event['trace_file']][1],'compiler observation trace binding')
            require(event['syscall'] in ('execve','execveat','open','openat','openat2'),'compiler selected syscall family')
            require(event['kind'] in ('exec','open'),'compiler observation kind')
            require((event['kind']=='exec') == (event['syscall'] in ('execve','execveat')),'compiler observation kind/syscall mismatch')
            if event['result']!='success' or not event.get('selected',True) or event['classification']!='external_regular':continue
            line=trace_lines[event['trace_file']][0].get(event['line'],'')
            raw=event['raw_path']
            require(line.startswith(event['syscall']+'(') and re.search(r'\)\s+=\s+\d+',line),'compiler successful syscall line binding')
            if event['kind']=='exec':
                quoted=re.findall(r'"(?:\\.|[^"\\])*"',line)
                require(quoted and quoted[0]==json.dumps(raw),'compiler executable trace path binding')
            else:
                require('<'+raw+'>' in line and 'O_WRONLY' not in line and 'O_PATH' not in line,'compiler readable trace path binding')
            raw=raw.removesuffix(' (deleted)')
            canonical,used=resolve_link_path(raw,edges.get);visited.update(used)
            require(canonical==event['canonical_path'],'compiler observation canonical path binding')
            require(canonical in pinned,'compiler observed external input omitted')
            selected[canonical]=pinned[canonical]
        require(selected==pinned and trace['external_path_count']==len(pinned),'compiler observed/manifest exact inventory')
        require(trace['generated_observation_count']==sum(e['classification']=='generated' for e in observations),'compiler generated observation count')
        require(trace['observed_exec_count']==sum(e['kind']=='exec' for e in observations),'compiler exec observation count')
        require(trace['observed_readable_open_count']==sum(e['kind']=='open' and e.get('selected',True) for e in observations),'compiler open observation count')
        require(obj(evidence[owner+'/'+phase+'/build.log']).read_text().splitlines()[0]==(discovery if phase=='discovery' else accepted),'compiler phase build log binding')
    require(visited==set(edges),'compiler unused symlink observations')
    require(records==expected,'compiler exact path/digest artifact binding')
    for key in records.values():obj(key)


def check_original_link(link,evidence,execution,obj):
    """Preserve original reference LOAD bytes without retroactive build attestation."""
    require(link['scope']=='POST_BUILD_OBSERVED_NOT_PREBUILD_ATTESTED','original link observation scope')
    require(link['build_root']==execution['build'] and link['invocation']==evidence['original_invocation'],'original link invocation/build binding')
    require(link['inputs_manifest']==evidence['original_build_inputs'] and link['runtime_manifest']==evidence['original_build_runtime'],'original link manifest binding')
    names={line[5:] for line in obj(link['link_map']).read_text().splitlines() if line.startswith('LOAD ')}
    require(names and names==set(link['files']) and all(path.startswith('/') for path in names),'original LOAD inventory')
    require(names==set(link['resolved_load_paths']),'original resolved LOAD inventory')
    check_link_resolution(link,obj)
    canonical={line.split('  ',1)[1]:line.split('  ',1)[0] for line in obj(link['canonical_manifest']).read_text().splitlines()}
    require(set(canonical)==set(link['resolved_load_paths'].values()),'original canonical manifest inventory')
    require(all(key==canonical[link['resolved_load_paths'][path]] for path,key in link['files'].items()),'original logical LOAD digest binding')
    for key in link['files'].values():obj(key)
    sources={line.split('  ',1)[1]:line.split('  ',1)[0] for line in obj(link['inputs_manifest']).read_text().splitlines()}
    require(link['recipe_path'].endswith('/build_original_lapsprep.sh') and sources.get(link['recipe_path'])==link['recipe_sha256'],'original build recipe binding')
    obj(link['recipe_sha256']);obj(link['runtime_manifest']);obj(link['invocation'])
    log=obj(link['build_log']).read_text()
    require('OPTIMIZATION '+execution['optimization'] in log.splitlines() and link['build_root']+'/common' in log,'original build log/optimization binding')
    require('BUILD_AND_LINK_PASS; NOT_EXECUTED; NOT_GENERATION_READY' in log.splitlines(),'original build completion log')


def validate_bundle(root):
    require(root.resolve(strict=True)==root and root.is_dir(), 'canonical bundle root')
    require(not any(p.is_symlink() for p in root.rglob('*')), 'bundle symlink')
    context=json_file(root/'TRANSACTION.json')
    chain_bytes,_=_stable_regular_bytes(root/'CHAIN.json');chain_hash=hashlib.sha256(chain_bytes).hexdigest()
    manifest=json.loads(chain_bytes)
    require(manifest['schema']==1 and manifest['contract']==CONTRACT and manifest['authority']=='EVIDENCE_ONLY_NO_DYNAMIC_AUTHORITY','OFF bundle contract')
    require(context['configuration']=='sha256:'+chain_hash and context['valid_time']==manifest['valid_time'],'configuration/time binding')
    require(manifest['source_commit']==context['source_commit'] and manifest['source_identity_kind']=='HEAD_LINEAGE_PLUS_EXACT_BYTE_DAG','source lineage binding')
    require(manifest['valid_time']==1786881600+(manifest['hour']-12)*3600 and manifest['hour'] in (12,13,14,15),'reviewed case time')
    objects=manifest['objects'];require(objects and all(re.fullmatch('[0-9a-f]{64}',x) for x in objects),'object inventory')
    declared={'CHAIN.json'}|{'objects/'+x for x in objects}
    require(set(context['products'])==declared,'transaction/bundle product inventory')
    found={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    require(found-declared <= {'TRANSACTION.json','MANIFEST.json','COMMITTED'} and declared<=found,'undeclared/missing bundle files')
    for expected,size in objects.items():
        path=root/'objects'/expected;data,status=_stable_regular_bytes(path)
        require(status.st_nlink==1 and len(data)==size and hashlib.sha256(data).hexdigest()==expected,'object bytes/identity')
    used=set()
    def obj(key):
        require(key in objects,'missing dependency object');used.add(key);return root/'objects'/key
    def data(key):return json_file(obj(key))
    require(manifest.get('build_pin_scope')=='DISCOVERY_PIN_FINAL_LINK_VERIFIED','V4 requires prospective compiler/link scope')
    require(all(manifest.get(k) in ('O0','O2') for k in ('producer_optimization','downstream_optimization','reference_optimization')),'explicit optimization contract')
    require(manifest['reference_optimization']==manifest['downstream_optimization'],'original reference optimization')
    controls=data(manifest['control_spec'])['environment'];require(controls==CONTROLS,'missing/different original controls')
    stages=manifest['stages'];require(set(stages)=={'producer','export','balance','lapsprep'},'stage DAG inventory')
    receipts={}
    for name,node in stages.items():
        require('compiler_audit' in node,'V4 requires compiler audit for every stage')
        receipt=data(node['receipt']);receipts[name]=receipt
        life=receipt['lifetime'];require(life['exit_code']==0 and life['leader_exit_code']==0 and life['supervisor_exit_code']==0 and life['closure']['status']=='ECHILD' and not life.get('leader_timeout',False),'stage lifetime failure')
        require(receipt['environment'].items()>=CONTROLS.items(),'missing explicit stage controls')
        absent={'CLOUD_BAL_SHADOW_EXPERIMENT','MOAD_DATAROOT','KMP_AFFINITY','LD_PRELOAD','LD_LIBRARY_PATH'}
        if name=='producer':absent|={'CLOUD_BAL_STAGE_MODE','CLOUD_BAL_STAGE_CONTEXT'}
        require(set(node['absent_environment'])==absent and not absent.intersection(receipt['environment']),'explicit absent controls')
        if name=='producer':
            require(set(node['artifacts'])=={'producer_script','coordinator','ncgen_executable','link_observation','log'},'producer artifact role inventory')
            require(node['artifacts']['ncgen_executable']==node['ncgen']['executable'],'producer ncgen artifact binding')
            require(receipt['environment'].get('KMP_BLOCKTIME')=='0' and receipt['environment'].get('MALLOC_ALIGNMENT')=='64','producer allocation/OpenMP controls')
            require(node['ncgen']['executable']=='b83acc5e06621d9e15c3e92b7c1592ca6fcf5d62593c95d8f87fa76cbcfb549e' and len(node['manifests'])==3 and node['ncgen']['runtime_manifest']==node['manifests'][2],'ncgen identity contract')
            obj(node['ncgen']['executable'])
        else:
            require(receipt['environment'].get('CLOUD_BAL_STAGE_MODE')==('EXPORT_OFF' if name=='export' else 'OFF'),'explicit adapter route')
        require(receipt.get('input_post_hashes')==receipt.get('detached_inputs',receipt.get('input_manifest')),'stage input mutation')
        require(node['inputs']==receipt.get('detached_inputs',receipt.get('input_manifest')),'stage input DAG differs')
        for key in node['inputs'].values():obj(key)
        require(node['sources']==receipt['source_pins'],'compiled source DAG differs')
        for key in node['sources'].values():obj(key)
        executable=receipt.get('executable_sha256',receipt.get('build',{}).get('executable_sha256'))
        require(node['executable']==executable,'stage executable binding');obj(executable)
        build=receipt.get('build',receipt.get('base_build'))
        require(node['manifests'][:2]==[build['inputs_sha256'],build['runtime_sha256']],'build manifest identity')
        source_lines={line.split('  ',1)[1]:line.split('  ',1)[0] for line in obj(node['manifests'][0]).read_text().splitlines()}
        require(source_lines==node['sources'],'build manifest/source closure')
        if name!='producer':
            require(len(node['manifests'])==2,'adapter manifest role inventory')
            check_adapter_artifacts(name,node,receipt)
            require(node['artifacts']['context']==receipt['context_sha256'],'context identity')
            require({x['sha256'] for x in receipt['runtime']}=={line.split('  ',1)[0] for line in obj(node['manifests'][1]).read_text().splitlines()},'detached runtime identity')
        for key in node['manifests']:
            for line in obj(key).read_text().splitlines():
                expected,separator,filename=line.partition('  ')
                require(separator and filename.startswith('/'),'build/runtime manifest syntax');obj(expected)
        log=obj(node['artifacts']['log']).read_text(errors='replace')
        if name=='producer':
            notices=re.findall(r'^\s+(lcp|lwc|lil|lct|lmd|lco|lrp|lty|lmt)\s+(\d+)\s+(\d+)\s*$',log,re.M)
            require(len(notices)==9 and all(status=='1' for role,status,index in notices) and 'LCO_PRODUCER_SUCCESS' in log,'producer notifications/status')
            require(node['artifacts']['producer_script']==receipt['script_sha256'] and node['artifacts']['coordinator']==receipt['coordinator_sha256'],'producer launch source binding')
        else:
            marker={'export':'DERIV_EXPORT_OFF_PAYLOAD_WRITTEN','balance':'BALANCE_CANONICAL_OFF_PAYLOAD_WRITTEN','lapsprep':'LAPSPREP_CANONICAL_PAYLOAD_CONSUMED'}[name]
            require(marker in log,'actual adapter marker missing')
        for key in node['artifacts'].values():obj(key)
    require(stages['producer']['executable']==stages['export']['executable'],'same-ELF producer/export mismatch')
    configuration=data(manifest['configuration']);require(configuration['explicit_original_controls']==CONTROLS and configuration['producer_control_spec_sha256']==manifest['control_spec'],'configuration controls')
    require(configuration['producer_launch_receipt_sha256']==stages['producer']['receipt'],'configuration producer receipt')
    roles=manifest['roles'];require(set(roles)=={'pre','post','wps','reference_wps'},'output role contract')
    chain=data(manifest['evidence']['chain_receipt'])
    before,after=compare_payloads(obj(roles['pre']),obj(roles['post']),manifest['valid_time'])
    for identity,observed in ((chain['pre_identity'],before),(chain['post_identity'],after)):
        aliases={'exchange_version':'cloud_bal_exchange_version','schema_version':'cloud_bal_schema_version','vertical_order':'canonical_vertical_order'}
        for name,value in identity.items():require(observed[aliases.get(name,name)]==value,'expected stage identity '+name)
    for stage,identity in (('export',before),('balance',after)):
        suffix='/src/upstream/laps_deriv.f' if stage=='export' else '/src/balance/qbalpe.f'
        main_hashes=[h for p,h in stages[stage]['sources'].items() if p.endswith(suffix)]
        require(main_hashes==[identity['producer_source_sha256']],'payload main source binding')
        artifact=stages[stage]['artifacts']['input_identity_manifest']
        require(identity['input_manifest_sha256']==artifact and data(artifact)==stages[stage]['inputs'],'payload input manifest binding')
    require(before['producer_binary_sha256']==stages['export']['executable'] and after['producer_binary_sha256']==stages['balance']['executable'],'payload executable identity')
    require(before['configuration_sha256']==manifest['configuration'],'payload configuration identity')
    require(stages['balance']['inputs']=={'payload.nc':roles['pre']} and stages['lapsprep']['inputs']['payload.nc']==roles['post'],'payload stage handoff')
    check_wps(obj(roles['wps']),obj(roles['reference_wps']),manifest['valid_time'])
    products=manifest['derived_products'];stamp=f"26228{manifest['hour']:02d}00"
    expected_products={f'lapsprd/{r}/{stamp}.{r}' for r in ('lco','lcp','lct','lfr','lhe','lil','liw','lmd','lmr','lmt','lrp','lst','lty','lwc')}
    require(set(products)==expected_products,'derived product count/roles')
    require(products==receipts['producer']['products'],'derived product receipt')
    require(not set(products).intersection(stages['producer']['inputs']),'producer outputs preexisted as inputs')
    for name,key in products.items():
        obj(key);require(manifest['original_products'][name]==key,'original derived product mismatch')
        role=name.split('/')[1]
        with Dataset(obj(key)) as ds:
            ds.set_auto_maskandscale(False)
            nz=22 if role in ('lco','lcp','lmd','lrp','lty','lwc') else 1
            require(all(n in ds.dimensions and len(ds.dimensions[n])==v for n,v in {'x':235,'y':283,'z':nz,'record':1}.items()),'derived product grid')
            require(np.all(ds['valtime'][:]==manifest['valid_time']) and np.all(ds['reftime'][:]==manifest['valid_time']),'derived product clocks')
            physical=[v for v in ds.variables.values() if 'x' in v.dimensions and 'y' in v.dimensions]
            require(bool(physical),'derived physical fields missing')
            for variable in physical:require(np.isfinite(variable[:]).all(),'derived nonfinite raw values')
        require(stages['export']['inputs'][name]==key,'derived/export product handoff')
    with Dataset(obj(products[f'lapsprd/lco/{stamp}.lco'])) as source, Dataset(obj(roles['pre'])) as canonical:
        source.set_auto_maskandscale(False);canonical.set_auto_maskandscale(False)
        raw=source['com'][0,::-1,:,:];valid=np.abs(raw)<1e30
        require(np.array_equal(valid,canonical['cloud_omega_evidence_valid'][0].astype(bool)),'direct COM evidence mask')
        require(np.array_equal(raw[valid],canonical['cloud_omega_evidence'][0][valid]),'direct COM evidence values')
    figure=data(manifest['evidence']['figure'])
    require(figure['schema']==1 and figure['hour']==manifest['hour'] and figure['valid_time']==manifest['valid_time'] and figure['authority']==manifest['authority'],'figure scope/time')
    require(figure['input_sha256']=={k:roles[k] for k in ('pre','post')},'figure payload input binding')
    require(obj(figure['output_sha256']).read_bytes().startswith(b'\x89PNG\r\n\x1a\n'),'figure PNG output')
    obj(figure['source_sha256'])
    for key in figure['runtime_files'].values():obj(key)
    reference=data(manifest['evidence']['original_baseline_receipt'])
    require(reference.get('status')=='ORIGINAL_COLD_BASELINE_ONLY_PASS' and reference.get('authority')=='NO_AUTHORITY','original baseline status/authority')
    require(reference.get('full_native_or_cp02_acceptance') is False and reference.get('all_source_inputs_unchanged') is True,'original baseline acceptance scope')
    require(reference.get('cases')==[12,13,14,15] and reference.get('original_positive_runs')==8,'original baseline case contract')
    for role,field in [('original_test','test_sha256'),('original_runner','runner_sha256')]:
        require(manifest['evidence'][role]==reference[field],'original baseline runner/test binding');obj(reference[field])
    invocation=data(manifest['evidence']['original_invocation'])
    matches=[x for x in reference['original_runs'] if x['hour']==manifest['hour'] and x['optimization']==manifest['reference_optimization']]
    require(len(matches)==1 and matches[0]['exit']==0 and matches[0]['wps_sha256']==roles['reference_wps'],'original baseline receipt binding')
    execution=data(manifest['evidence']['original_execution'])
    require(execution=={k:v for k,v in matches[0].items() if k!='wps_sha256'},'original execution receipt binding')
    require(execution['changed']==[] and execution['added']==[f'lapsprd/lapsprep/wps/LAPS:2026-08-16_{manifest["hour"]}:00'],'original execution input/output scope')
    require(matches[0]['build']==invocation['argv'][-2],'original reference build identity')
    original_log=obj(manifest['evidence']['original_run_log']).read_text(errors='replace')
    bound=re.findall(r'BOUND_EXECUTABLE_READY method=sealed_memfd sha256=([0-9a-f]{64}) executable=(\S+)',original_log)
    original_executable=manifest['evidence']['original_executable']
    require(bound==[(original_executable,matches[0]['build']+'/klps_anal_prep.exe')],'original bound executable evidence')
    original_link=data(manifest['evidence']['original_link_observation'])
    check_original_link(original_link,manifest['evidence'],matches[0],obj)
    original_inputs=data(manifest['evidence']['original_input_pre'])
    original_post=data(manifest['evidence']['original_input_post'])
    require(all(original_post.get(k)==v for k,v in original_inputs.items()),'original baseline input mutation')
    for key in original_inputs.values():obj(key)
    runtime=data(manifest['evidence']['validator_runtime'])
    require(runtime['scope']=='POST_VALIDATION_MODULES_AND_MAPPED_ELF_OBSERVED','validator runtime scope')
    for filename,record in runtime['files'].items():obj(record['sha256'])
    for filename in ('verify_stage_off_generation.py','compare_baseline.py','cloud_bal_transaction.py'):
        path=Path(__file__).resolve().with_name(filename)
        require(runtime['files'][str(path)]['sha256']==sha(path),'validator/helper version binding')
    checked_compiler_audits=set()
    for name,node in stages.items():
        link=data(node['artifacts']['link_observation'])
        build=receipts[name].get('build',receipts[name].get('base_build'))
        optimization=manifest['producer_optimization' if name in ('producer','export') else 'downstream_optimization']
        check_link_pins(link,node,build,optimization,obj)
        audit=data(node['compiler_audit'])
        key=(node['compiler_audit'],node['manifests'][0],node['executable'])
        if key not in checked_compiler_audits:
            check_compiler_audit(audit,node,build,'derived' if name in ('producer','export') else name,optimization,obj)
            checked_compiler_audits.add(key)
    require(manifest['evidence']['original_launcher']=='63e01edbc9a1e9e6c06013f6b56fa40cb14334d228780df845c414140adac94f','original launch controls identity')
    for key in manifest['evidence'].values():obj(key)
    require(used==set(objects),'unreferenced dependency objects')
    require(sha(root/'CHAIN.json')==chain_hash,'CHAIN changed during validation')
    manifest['_validated_chain_sha256']=chain_hash
    return context,manifest


def verify_snapshot(snapshot):
    require(not snapshot.is_symlink() and snapshot.parent.name=='.snapshots','expected detached snapshot')
    context,manifest=validate_bundle(snapshot)
    require(context['transaction_id']==snapshot.name and context['require_validation'],'snapshot transaction identity')
    products=[]
    for name in sorted(context['products']):
        payload,status=_stable_regular_bytes(snapshot/name)
        observed=hashlib.sha256(payload).hexdigest()
        expected=manifest['_validated_chain_sha256'] if name=='CHAIN.json' else name.split('/')[-1]
        require(observed==expected and status.st_nlink==1,'snapshot changed after semantic validation')
        products.append({'path':name,'bytes':status.st_size,'sha256':observed})
    return {'schema':1,'status':'PASS','transaction_id':snapshot.name,'snapshot_identity':[snapshot.stat().st_dev,snapshot.stat().st_ino],
      'validator':{'name':'verify_stage_off_generation','source_sha256':sha(Path(__file__).resolve())},'products':products}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--snapshot',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(verify_snapshot(args.snapshot),sort_keys=True))

if __name__=='__main__':main()
