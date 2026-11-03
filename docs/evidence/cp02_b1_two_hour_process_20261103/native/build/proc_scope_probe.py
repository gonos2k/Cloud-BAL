from __future__ import annotations
import importlib.util,json,tempfile
from pathlib import Path

ROOT=Path('/var/tmp/b1-two-hour-probe-20261103')
spec=importlib.util.spec_from_file_location('probe_run_pair',ROOT/'run_pair.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

def proc_entry(proc_root:Path,pid:str,cwd:Path,exe:Path,cpus:str)->None:
    entry=proc_root/pid;entry.mkdir()
    (entry/'cwd').symlink_to(cwd,target_is_directory=True)
    (entry/'exe').symlink_to(exe)
    (entry/'status').write_text(f'Name:\twrf.exe\nCpus_allowed_list:\t{cpus}\n')

def main()->None:
    with tempfile.TemporaryDirectory(prefix='b1-proc-scope-') as tmp:
        root=Path(tmp);proc=root/'proc';proc.mkdir()
        cases={name:root/name for name in ('OLD','FIX','OTHER')}
        for case in cases.values():
            case.mkdir();(case/'wrf.exe').write_text(case.name)
        proc_entry(proc,'1101',cases['OLD'],cases['OLD']/'wrf.exe','32')
        proc_entry(proc,'1102',cases['FIX'],cases['FIX']/'wrf.exe','40')
        proc_entry(proc,'1103',cases['OTHER'],cases['OLD']/'wrf.exe','63')
        proc_entry(proc,'1104',cases['OLD'],cases['OTHER']/'wrf.exe','44')
        old=runner.rank_affinities(cases['OLD'],cases['OLD']/'wrf.exe',proc)
        fix=runner.rank_affinities(cases['FIX'],cases['FIX']/'wrf.exe',proc)
        assert old=={'1101':[32]},old
        assert fix=={'1102':[40]},fix
        result={'status':'PASS','old_case_rank_pids':old,'fix_case_rank_pids':fix,'off_case_same_exe_pid_filtered':'1103','wrong_exe_same_case_pid_filtered':'1104','scope':'exact resolved process cwd and executable path'}
        out=ROOT/'review'/'proc_scope_probe.json';out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
