import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('water_budget',ROOT/'tools/cp02_first_call_water_budget.py')
budget=importlib.util.module_from_spec(spec);spec.loader.exec_module(budget)


def f32(number):
    raw=struct.pack('<f',number)
    return {'value':struct.unpack('<f',raw)[0],'hex_le':raw.hex()}


def capture():
    records=[]
    bounds={'its':1,'ite':2,'ide':3,'jts':1,'jte':1,'jde':2,'kts':1,'kte':2}
    for i in (1,2):
        for k in (1,2):
            for event in ('entry','return'):
                fields={name:f32(0) for name in (*budget.WATER,*budget.SURFACE)}
                fields.update({name:f32(v) for name,v in [('den',1),('delz',100),('denr',1000)]})
                if event=='entry':
                    fields['qi']=f32(.001)
                    fields['rainncv']=f32(17)  # overwritten call accumulator
                else:
                    fields['qi']=f32(.0005);fields['qs']=f32(.0005)
                    if k==1:
                        fields['qs']=f32(0)
                        fields['qv']=f32(.00025)
                    fields['rainncv']=f32(.025)
                    fields['snowncv']=f32(.025)
                    fields['graupelncv']=f32(0)
                records.append({'kind':'kdm','event':event,'step':1,'rank':3,'cell':[i,1,k],
                                'bounds':bounds,'options':{'diagflag':False},'fields':fields})
    return records


class FirstCallWaterBudgetTest(unittest.TestCase):
    def parse(self,records):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'capture.jsonl'
            path.write_text(''.join(json.dumps(row)+'\n' for row in records))
            return budget.read_pairs(path)

    def test_target_source_and_capture_are_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=root/'source';source.write_bytes(b'target physics')
            capture_path=root/'capture';capture_path.write_bytes(b'captured words')
            receipt_path=root/'receipt'
            source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
            capture_hash=hashlib.sha256(capture_path.read_bytes()).hexdigest()
            receipt={'status':'PASS','source_sha256':source_hash,'capture_sha256':capture_hash}
            receipt_path.write_text(json.dumps(receipt))
            with mock.patch.object(budget,'PHYSICS_SHA256',source_hash):
                self.assertEqual(budget.validate_identity(capture_path,receipt_path,source),capture_hash)
                source.write_bytes(b'other physics')
                with self.assertRaises(ValueError):
                    budget.validate_identity(capture_path,receipt_path,source)
                source.write_bytes(b'target physics')
                capture_path.write_bytes(b'different capture')
                with self.assertRaises(ValueError):
                    budget.validate_identity(capture_path,receipt_path,source)

    def test_frozen_repartition_and_surface_total(self):
        ledgers=budget.column_ledgers(self.parse(capture()),1)
        self.assertEqual(len(ledgers),2)
        for row in ledgers:
            self.assertAlmostEqual(row['raw_column_residual_kg_m2'],0,places=8)
            self.assertAlmostEqual(row['surface_total_kg_m2'],.025,places=8)
            self.assertAlmostEqual(row['snow_subset_mm'],.025,places=8)
            # Adding the snow subset a second time would produce a false loss.
            self.assertNotAlmostEqual(row['raw_column_residual_kg_m2']+row['snow_subset_mm'],0,places=8)

    def test_negative_entry_clip_is_measured_not_rejected(self):
        records=capture()
        for row in records:
            row['fields'].update({q:f32(0) for q in (*budget.WATER,*budget.SURFACE)})
            if row['event']=='entry' and row['cell'][2]==1:
                row['fields']['qi']=f32(-.001)
        ledgers=budget.column_ledgers(self.parse(records),1)
        for row in ledgers:
            self.assertAlmostEqual(row['entry_clip_kg_m2'],.1,places=7)
            self.assertEqual(row['raw_column_residual_kg_m2'],row['entry_clip_kg_m2'])
            self.assertEqual(row['residual_without_entry_clip_kg_m2'],0)

    def test_complete_row_and_ownership_are_required(self):
        for mode in ('column','level','bounds','rank','options','outside'):
            records=copy.deepcopy(capture())
            if mode=='column':records=[r for r in records if r['cell'][0]!=2]
            elif mode=='level':records=[r for r in records if r['cell']!=[2,1,2]]
            elif mode=='bounds':records[-1]['bounds']={**records[-1]['bounds'],'kte':3}
            elif mode=='rank':records[-1]['rank']=4
            elif mode=='options':records[-1]['options']={'diagflag':True}
            else:records[-1]['cell']=[3,1,2]
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                budget.column_ledgers(self.parse(records),1)

    def test_exact_words_duplicates_and_geometry(self):
        for mode in ('rounded','bool','hex','duplicate','geometry'):
            records=copy.deepcopy(capture())
            if mode=='rounded':records[0]['fields']['qi']['value']=.001
            elif mode=='bool':records[0]['fields']['qi']={'value':True,'hex_le':f32(1)['hex_le']}
            elif mode=='hex':records[0]['fields']['qi']['hex_le']=f32(1)['hex_le']
            elif mode=='duplicate':records.append(copy.deepcopy(records[0]))
            else:records[-1]['fields']['den']=f32(2)
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                budget.column_ledgers(self.parse(records),1)


if __name__=='__main__':
    unittest.main()
