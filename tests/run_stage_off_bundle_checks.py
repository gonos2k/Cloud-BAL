#!/usr/bin/env python3
"""Focused DAG and semantic regressions using an explicitly supplied real bundle.

Copies the fixture once; never mutates retained evidence or runs physics.
This data-dependent gate is intentionally separate from the portable test list.
"""
from pathlib import Path
import argparse,copy,json,shutil,sys,tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import verify_stage_off_generation as validator
from verify_stage_off_generation import validate_bundle,check_payload,sha
from netCDF4 import Dataset


def main():
    parser=argparse.ArgumentParser();parser.add_argument('bundle',type=Path);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='off-bundle-tests-') as directory:
        (Path(directory)/'.snapshots').mkdir()
        root=Path(directory)/'.snapshots/fixture';shutil.copytree(args.bundle,root)
        original=json.loads((root/'CHAIN.json').read_text())
        def write(m):
            (root/'CHAIN.json').write_text(json.dumps(m,sort_keys=True))
            context={'products':['CHAIN.json']+['objects/'+h for h in m['objects']],
              'source_commit':m['source_commit'],'configuration':'sha256:'+sha(root/'CHAIN.json'),
              'valid_time':m['valid_time'],'transaction_id':'fixture','require_validation':True}
            (root/'TRANSACTION.json').write_text(json.dumps(context))
        write(original);validate_bundle(root);count=1
        mutations=[
          ('compiler scope omitted',lambda m:m.pop('build_pin_scope')),
          ('compiler scope downgraded',lambda m:m.__setitem__('build_pin_scope','POST_BUILD_OBSERVED_NOT_PREBUILD_ATTESTED')),
          ('compiler audit omitted',lambda m:m['stages']['balance'].pop('compiler_audit')),
          ('runtime manifest substitution',lambda m:m['stages']['export']['manifests'].__setitem__(1,m['stages']['export']['manifests'][0])),
          ('missing runtime manifest',lambda m:m['stages']['balance'].__setitem__('manifests',[])),
          ('missing native lightning dependency',lambda m:m['stages']['producer']['inputs'].pop(next(k for k in m['stages']['producer']['inputs'] if '/lgt/' in k))),
          ('missing compiled source',lambda m:m['stages']['export']['sources'].pop(next(iter(m['stages']['export']['sources'])))),
          ('ncgen runtime substitution',lambda m:m['stages']['producer']['ncgen'].__setitem__('runtime_manifest',m['stages']['producer']['manifests'][0])),
          ('absent controls omitted',lambda m:m['stages']['producer'].__setitem__('absent_environment',[])),
          ('wrong derived role',lambda m:m['derived_products'].__setitem__('wrong',m['derived_products'].pop(next(iter(m['derived_products']))))),
          ('wrong same ELF',lambda m:m['stages']['producer'].__setitem__('executable',m['stages']['balance']['executable']))]
        for label,change in mutations:
            bad=copy.deepcopy(original);change(bad);write(bad)
            try:validate_bundle(root)
            except ValueError:count+=1
            else:raise AssertionError('accepted '+label)
        for field,value in [('status','FAIL'),('full_native_or_cp02_acceptance','FAIL')]:
            bad=copy.deepcopy(original);old=bad['evidence']['original_baseline_receipt']
            receipt=json.loads((root/'objects'/old).read_text());receipt[field]=value
            payload=json.dumps(receipt,sort_keys=True).encode();import hashlib
            key=hashlib.sha256(payload).hexdigest();(root/'objects'/key).write_bytes(payload)
            saved=(root/'objects'/old).read_bytes();(root/'objects'/old).unlink()
            bad['objects'].pop(old);bad['objects'][key]=len(payload);bad['evidence']['original_baseline_receipt']=key;write(bad)
            try:
                try:validate_bundle(root)
                except ValueError as error:
                    assert 'original baseline' in str(error),str(error);count+=1
                else:raise AssertionError('accepted original baseline '+field)
            finally:(root/'objects'/key).unlink();(root/'objects'/old).write_bytes(saved)
        if original.get('build_pin_scope')=='DISCOVERY_PIN_FINAL_LINK_VERIFIED':
            node=original['stages']['producer'];link=json.loads((root/'objects'/node['artifacts']['link_observation']).read_text())
            receipt=json.loads((root/'objects'/node['receipt']).read_text());build=receipt.get('build',receipt.get('base_build'))
            for label,change in [
                ('link manifest substitution',lambda x:x.__setitem__('link_manifest',x['compile_manifest'])),
                ('discovery map substitution',lambda x:x.__setitem__('discovery_map',x['link_manifest'])),
                ('missing resolved LOAD',lambda x:x['resolved_load_paths'].pop(next(iter(x['resolved_load_paths'])))),
                ('link authority downgrade',lambda x:x.__setitem__('scope','POST_BUILD_OBSERVED_NOT_PREBUILD_ATTESTED'))]:
                bad=copy.deepcopy(link);change(bad)
                try:validator.check_link_pins(bad,node,build,original['producer_optimization'],lambda key:root/'objects'/key)
                except ValueError:count+=1
                else:raise AssertionError('accepted '+label)
        node=original['stages']['producer'];audit=json.loads((root/'objects'/node['compiler_audit']).read_text())
        receipt=json.loads((root/'objects'/node['receipt']).read_text());build=receipt.get('build',receipt.get('base_build'))
        def compiler_reject(label,changed,overrides=None,expected=None):
            def obj(key):return (overrides or {}).get(key,root/'objects'/key)
            try:validator.check_compiler_audit(changed,node,build,'derived',original['producer_optimization'],obj)
            except (ValueError,UnicodeError) as error:
                if expected is not None:assert str(error)==expected,str(error)
                return
            else:raise AssertionError('accepted compiler '+label)
        record_names=list(audit['records'])
        for label,change in [
            ('precheck substitution',lambda x:x.__setitem__('precheck',node['executable'])),
            ('missing record',lambda x:x['records'].pop(record_names[0])),
            ('wrong path digest',lambda x:x['records'].__setitem__(record_names[0],x['records'][record_names[1]])),
        ]:
            bad=copy.deepcopy(audit);change(bad)
            compiler_reject(label,bad)
            count+=1
        audit_receipt=json.loads((root/'objects'/audit['receipt']).read_text())
        for field,value in [('status','FAIL'),('accepted_build','/wrong-build'),('producer','lapsprep'),('optimization','O2' if original['producer_optimization']=='O0' else 'O0')]:
            body=copy.deepcopy(audit_receipt);body[field]=value;negative=Path(directory)/'compiler-negative.json';negative.write_text(json.dumps(body))
            compiler_reject(field,audit,{audit['receipt']:negative});count+=1
        final_path=next(r['path'] for r in audit_receipt['evidence'] if r['path'].endswith('/final_receipt.json'))
        final_key=audit['records'][final_path]
        for kind,expected in [('untrusted-kind','compiler observation kind'),
                              ('exec','compiler observation kind/syscall mismatch')]:
            body=json.loads((root/'objects'/final_key).read_text())
            event=next(e for e in body['observations'] if e['kind']=='open' and
                       e['classification']=='external_regular' and e['result']=='success' and e.get('selected',True))
            event['kind']=kind
            body['observed_readable_open_count']-=1
            if kind=='exec':body['observed_exec_count']+=1
            negative=Path(directory)/'compiler-negative.json';negative.write_text(json.dumps(body));del body
            compiler_reject(kind,audit,{final_key:negative},expected);count+=1
        for field,change in [
            ('trace digest mapping',lambda x:x['trace_sha256'].__setitem__(next(iter(x['trace_sha256'])),node['executable'])),
            ('manifest substitution',lambda x:x.__setitem__('manifest_sha256',node['executable'])),
            ('widened generated root',lambda x:x['generated_roots'].append('/')),
            ('wrong syscall source line',lambda x:next(e for e in x['observations'] if e['kind']=='open' and e['classification']=='external_regular' and e['result']=='success').__setitem__('line',1)),
            ('wrong observed canonical path',lambda x:next(e for e in x['observations'] if e['classification']=='external_regular' and e['result']=='success').__setitem__('canonical_path','/wrong-input')),
            ('missing external observation count',lambda x:x.__setitem__('external_path_count',0))]:
            body=json.loads((root/'objects'/final_key).read_text());change(body)
            negative=Path(directory)/'compiler-negative.json';negative.write_text(json.dumps(body));del body
            compiler_reject(field,audit,{final_key:negative});count+=1
        original_link=json.loads((root/'objects'/original['evidence']['original_link_observation']).read_text())
        execution=json.loads((root/'objects'/original['evidence']['original_execution']).read_text())
        for label,change in [
            ('original link scope upgrade',lambda x:x.__setitem__('scope','PREBUILD_ATTESTED')),
            ('original build substitution',lambda x:x.__setitem__('build_root','/wrong-build')),
            ('original manifest substitution',lambda x:x.__setitem__('inputs_manifest',x['runtime_manifest'])),
            ('original LOAD omission',lambda x:x['files'].pop(next(iter(x['files']))))]:
            bad=copy.deepcopy(original_link);change(bad)
            try:validator.check_original_link(bad,original['evidence'],execution,lambda key:root/'objects'/key)
            except ValueError:count+=1
            else:raise AssertionError('accepted '+label)
        for stage in ('export','balance','lapsprep'):
            node=original['stages'][stage];receipt=json.loads((root/'objects'/node['receipt']).read_text())
            helper=next(path for path in receipt['helper_source_observed_sha256'] if path.endswith('/cloud_bal_transaction.py'))
            for label,change in [
                ('wrong helper',lambda x:x['artifacts'].__setitem__(helper,x['artifacts']['coordinator'])),
                ('missing helper',lambda x:x['artifacts'].pop(helper)),
                ('extra helper role',lambda x:x['artifacts'].__setitem__('invented-helper',x['artifacts']['coordinator'])),
                ('wrong coordinator',lambda x:x['artifacts'].__setitem__('coordinator',x['artifacts'][helper]))]:
                bad=copy.deepcopy(node);change(bad)
                try:validator.check_adapter_artifacts(stage,bad,receipt)
                except ValueError:count+=1
                else:raise AssertionError('accepted '+stage+' '+label)
        def swapped_object(role,field,message):
            bad=copy.deepcopy(original);parent=bad
            for part in role[:-1]:parent=parent[part]
            old=parent[role[-1]];body=json.loads((root/'objects'/old).read_text());keys=list(body[field])[:2]
            body[field][keys[0]],body[field][keys[1]]=body[field][keys[1]],body[field][keys[0]]
            payload=json.dumps(body,sort_keys=True).encode();import hashlib
            key=hashlib.sha256(payload).hexdigest();parent[role[-1]]=key;bad['objects'][key]=len(payload);(root/'objects'/key).write_bytes(payload)
            saved=None
            if json.dumps(bad).count(old)==1:
                saved=(root/'objects'/old).read_bytes();(root/'objects'/old).unlink();bad['objects'].pop(old)
            write(bad)
            try:
                try:validate_bundle(root)
                except ValueError as error:assert message in str(error),str(error)
                else:raise AssertionError('accepted swapped '+field)
            finally:
                (root/'objects'/key).unlink()
                if saved is not None:(root/'objects'/old).write_bytes(saved)
        swapped_object(('evidence','original_link_observation'),'files','original logical LOAD digest binding');count+=1
        swapped_object(('stages','producer','artifacts','link_observation'),'resolved_load_paths','logical LOAD canonical path binding');count+=1
        for path,edges,expected in [('/a/link/../file',{'/a/link':'/x/y'},'/x/file'),('/a/link/file',{'/a/link':'../x'},'/x/file')]:
            actual,_=validator.resolve_link_path(path,edges.get);assert actual==expected;count+=1
        try:validator.resolve_link_path('/cycle',{'/cycle':'cycle'}.get)
        except ValueError:count+=1
        else:raise AssertionError('accepted symlink cycle')
        write(original)
        # A semantic PASS cannot be rebound to bytes changed before receipt emission.
        marker=root/'objects'/original['roles']['wps'];saved=marker.read_bytes()
        def change_after_semantics(path):
            result=validate_bundle(path);marker.write_bytes(b'changed after semantic validation');return result
        try:
            with patch.object(validator,'validate_bundle',side_effect=change_after_semantics):
                try:validator.verify_snapshot(root)
                except ValueError as error:
                    assert 'snapshot changed after semantic validation' in str(error),str(error);count+=1
                else:raise AssertionError('accepted semantic-to-receipt mutation')
        finally:marker.write_bytes(saved)
        payload=root/'objects'/original['roles']['pre'];scratch=Path(directory)/'negative.nc'
        for label,name,change in [
          ('malformed validity','pressure_valid',lambda d:d['pressure_valid'].__setitem__((0,0,0,0),2)),
          ('dynamic target authority',None,lambda d:d.setncattr('dynamic_target_authorized',1)),
          ('populated radar LOS',None,lambda d:d.setncattr('radar_los_present',1)),
          ('wrong wind frame',None,lambda d:d.setncattr('wind_coordinate','EARTH_RELATIVE'))]:
            shutil.copyfile(payload,scratch)
            with Dataset(scratch,'r+') as ds:change(ds)
            try:check_payload(scratch,original['valid_time'],'deriv_off')
            except ValueError:count+=1
            else:raise AssertionError('accepted '+label)
        print(f'PASS {count} real-bundle positive/negative checks')

if __name__=='__main__':main()
