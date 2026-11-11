import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np

spec=importlib.util.spec_from_file_location('audit',Path(__file__).resolve().parents[1]/'tools/cp02_ice_stage_audit.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
POLICY={'qmin':1e-15,'ncmin_m3':10,'psd12_qi_min':1e-14,'lambda_min_m_inv':9080,'lambda_max_m_inv':1820000}

def row(qi=1e-3,ni=1e6,aux=-1):
    return {'qi':float(np.float32(qi)),'ni':float(np.float32(ni)),'den':1.,'temperature':250.,'aux':float(np.float32(aux))}

class StageAuditTests(unittest.TestCase):
    def test_later_number_is_not_globally_capped(self):
        pre=row();post=row(ni=1.5e6);selected=row(ni=1.5e6,aux=9080)
        self.assertTrue(audit.check_psd('PSD1',pre,post,selected,POLICY))
        # A source-word oracle, not the range check, validates reconstruction.
        expected=f"PSD1 {audit.word(post['ni']):08X} {audit.word(selected['aux']):08X} 1"
        actual={**post,'aux':selected['aux']}
        audit.check_oracle_response('PSD1',actual,expected,True)
        with self.assertRaises(ValueError):
            audit.check_oracle_response('PSD1',{**actual,'ni':1.4e6},expected,True)

    def test_each_stage_uses_its_own_gate(self):
        q=np.float32(1e-14)
        self.assertTrue(audit.active('PSD1',row(qi=q,ni=0),POLICY))
        self.assertTrue(audit.active('PSD2',row(qi=q,ni=0),POLICY))
        self.assertFalse(audit.active('PSD1',row(qi=np.nextafter(q,np.float32(0)),ni=0),POLICY))
        self.assertFalse(audit.active('PSD3',row(qi=q,ni=0),POLICY))
        self.assertTrue(audit.active('PSD3',row(qi=POLICY['qmin'],ni=10),POLICY))
        with self.assertRaises(ValueError):audit.active('PSD4',row(),POLICY)

    def test_inactive_and_active_probe_consistency(self):
        pre=row(qi=0,ni=0)
        self.assertFalse(audit.check_psd('PSD1',pre,pre,None,POLICY))
        with self.assertRaises(ValueError):audit.check_psd('PSD1',pre,row(qi=0,ni=1),None,POLICY)
        with self.assertRaises(ValueError):audit.check_psd('PSD1',row(),row(),None,POLICY)
        with self.assertRaises(ValueError):audit.check_psd('PSD1',row(),row(),row(aux=9000),POLICY)

    def test_bad_record_and_wrapper_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'stages.txt';path.write_text('UNKNOWN 0 1 1 0 0 1 -1 250\n')
            with self.assertRaises(ValueError):audit.records(path)
            path.write_text('ENTRY 0 1 1 0 0 1 -1 250\n'*2)
            with self.assertRaises(ValueError):audit.records(path)
        profiles={'QICE':[1e-3],'den':[.5],'seed':[200.]}
        wrapped={('WRAPPER',0,1):{**row(),'den':.5,'ni':100.}}
        audit.check_wrapper(wrapped,profiles,'seed')
        wrapped[('WRAPPER',0,1)]['ni']=200.
        with self.assertRaises(ValueError):audit.check_wrapper(wrapped,profiles,'seed')

if __name__=='__main__':unittest.main()
