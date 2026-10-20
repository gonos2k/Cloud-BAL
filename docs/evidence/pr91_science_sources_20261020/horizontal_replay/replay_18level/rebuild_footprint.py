import gzip
import hashlib
import json
import math
import struct
from collections import defaultdict
from pathlib import Path
import numpy as np

root = Path(__file__).resolve().parent
base_path = root.parent / 'laps_qc_horizontal_rows.json'
base = json.loads(base_path.read_text())

def f32_hex(value):
    value = np.float32(value)
    return struct.pack('>f', float(value)).hex().upper()

# Native WPS replay output columns: pressure, target i/j (zero-based), source x/y,
# predicted f32, observed met_em f32, numeric values and met_em pressure index.
rows=[]
for line in (root/'grid_rows_288.out').read_text().splitlines():
    s=line.split()
    rows.append({'pressure_pa':float(s[0]),'target_i0':int(s[1]),'target_j0':int(s[2]),
      'source_x_wps':float(s[3]),'source_y_wps':float(s[4]),
      'prediction_hex':s[5].upper(),'met_em_qc_hex':s[6].upper(),
      'prediction_f32':float(s[7]),'met_em_qc_f32':float(s[8]),'met_em_pressure_index':int(s[9])})
if len(rows)!=288: raise SystemExit(f'expected 288 direct rows, got {len(rows)}')
if any(r['prediction_hex']!=r['met_em_qc_hex'] for r in rows): raise SystemExit('bitwise comparison failed')
wrong_rows=[]
for line in (root/'grid_rows_288_wrong_radius.out').read_text().splitlines():
    wrong_rows.append(line.split())
if len(wrong_rows)!=288: raise SystemExit(f'expected 288 negative-control rows, got {len(wrong_rows)}')
header_levels=[int(float(line.split()[2])) for line in (root/'qc_headers.txt').read_text().splitlines()]
qc_values=np.loadtxt(gzip.open(root/'qc_levels.txt.gz','rt'),dtype=np.float32).reshape((len(header_levels),283,235))
corner_count=0
for r in rows:
    k=header_levels.index(int(r['pressure_pa']))
    x,y=r['source_x_wps'],r['source_y_wps']
    for yy in (math.floor(y)-1,math.ceil(y)-1):
        for xx in (math.floor(x)-1,math.ceil(x)-1):
            corner_count+=1
            v=qc_values[k,yy,xx]
            if not np.isfinite(v) or v == np.float32(-1.e30):
                raise SystemExit(f'invalid four_pt corner at pressure={r["pressure_pa"]}, target={(r["target_i0"],r["target_j0"])}, source={(xx,yy)}')
if corner_count!=1152: raise SystemExit(f'expected 1152 source corners, got {corner_count}')

# Horizontal geometry is invariant across source pressure levels. Ensure the direct
# native operator returned identical coordinates at every pressure for each target.
by_target=defaultdict(list)
for r in rows: by_target[(r['target_i0'],r['target_j0'])].append(r)
if len(by_target)!=16 or any(len(v)!=18 for v in by_target.values()): raise SystemExit('unexpected target/level coverage')
for key, rs in by_target.items():
    xy={(r['source_x_wps'],r['source_y_wps']) for r in rs}
    if len(xy)!=1: raise SystemExit(f'horizontal coordinates vary by level at {key}')

source_cells=[(i,j) for j in (16,17,18) for i in (134,135,136)]
links=defaultdict(list)
weights_by_target={}
for (ti,tj), rs in sorted(by_target.items()):
    x=np.float32(rs[0]['source_x_wps']); y=np.float32(rs[0]['source_y_wps'])
    minx=np.float32(math.floor(float(x))); maxx=np.float32(math.ceil(float(x)))
    miny=np.float32(math.floor(float(y))); maxy=np.float32(math.ceil(float(y)))
    corners=[(int(minx)-1,int(maxy)-1,np.float32((y-miny)*(maxx-x))),
      (int(maxx)-1,int(maxy)-1,np.float32((y-miny)*(x-minx))),
      (int(minx)-1,int(miny)-1,np.float32((maxy-y)*(maxx-x))),
      (int(maxx)-1,int(miny)-1,np.float32((maxy-y)*(x-minx)))]
    weights_by_target[(ti,tj)]={}
    for si,sj,w in corners:
        weights_by_target[(ti,tj)][(si,sj)]=float(w)
        if (si,sj) in source_cells:
            links[(si,sj)].append({'target_i0':ti,'target_j0':tj,'target_lat_f32':None,'target_lon_f32':None,
              'source_x_wps':float(x),'source_y_wps':float(y),'coefficient_f32':float(w),'coefficient_hex':f32_hex(w),
              'fractional_x_wps':float(np.float32(x-minx)),'fractional_y_wps':float(np.float32(y-miny)),
              'source_corner_i0':si,'source_corner_j0':sj})

# Pull target geographic coordinates from the exactly matched 288-target input.
latlon={}
for line in (root/'targets_288.txt').read_text().splitlines():
    p,i,j,lat,lon,exp,mk,obs=line.split()
    latlon[(int(i),int(j))]=(float(lat),float(lon))
for key, ls in links.items():
    for link in ls:
        link['target_lat_f32'],link['target_lon_f32']=latlon[(link['target_i0'],link['target_j0'])]

newlinks=[]
for si,sj in source_cells:
    ls=sorted(links[(si,sj)],key=lambda x:(x['target_j0'],x['target_i0']))
    newlinks.append({'source_i0':si,'source_i_wps':si+1,'source_j0':sj,'source_j_wps':sj+1,
      'source_pressure_k0':list(range(3,21)),'links':ls})
if sum(len(x['links']) for x in newlinks)!=36: raise SystemExit('expected 36 nonzero source-target links')
json_link_bits={(l['target_i0'],l['target_j0'],l['source_corner_i0'],l['source_corner_j0']):l['coefficient_hex'] for c in newlinks for l in c['links']}
scan_rows=[]
for line in (root/'inverse_support_rows.txt').read_text().splitlines():
    f=line.split(); scan_rows.append(((int(f[0]),int(f[1]),int(f[6]),int(f[7])),f[9].upper()))
if len(scan_rows)!=36 or {k for k,_ in scan_rows}!=set(json_link_bits): raise SystemExit('global target scan support differs from coefficient links')
if sum(json_link_bits.get(k)==v for k,v in scan_rows)!=36: raise SystemExit('global target scan coefficient HEX differs')

base['links_by_source_cell']=newlinks
base['union_target_cells']=[{'target_i0':i,'target_j0':j} for i,j in sorted(by_target,key=lambda ij:(ij[1],ij[0]))]
base['claim_scope']='For the preserved candidate LAPS QC field, the actual v5 source projection header and WPS interp_sequence have been replayed at all 16 candidate-supported target columns and all 18 original pressure levels (95,000–10,000 Pa). The 36 source-target REAL32 four_pt coefficient links use direct lltoxy coordinates at 6371229.00390625 m. All 288 source-only predictions match met_em QC bitwise at their exact pressure levels. Native eta composition and generalization to other fields remain open.'
base['index_convention']['source_pressure_mapping']='The preserved candidate mask uses source k0=3..20; the LAPS file stores QC records ascending at xlvl=5000..100000 plus 200100 Pa. These mask levels map to LAPS QC records with xlvl=95000,90000,...,10000 Pa. Met_em PRES has one exact pressure index for each of those 18 levels.'
base['observed_final_qc_comparison']['direct_interp_all_16_affected_targets_bitwise_match']=True
base['observed_final_qc_comparison']['direct_interp_all_288_target_level_rows_bitwise_match']=True
base['observed_final_qc_comparison']['direct_interp_target_count']=16
base['observed_final_qc_comparison']['direct_interp_level_count']=18
base['observed_final_qc_comparison']['direct_interp_comparison_count']=288
base['observed_final_qc_comparison']['finding']='Using the actual v5 source Earth radius, direct four_pt interpolation of the LAPS QC slab alone matches final met_em QC bitwise at all 16 candidate-supported target columns and all 18 original source pressure levels (288 comparisons). This is a field/time/pressure-level-specific horizontal component result; native eta influence remains open.'
base['operator']['classification']='The 36 source-to-target links are REAL32 WPS four_pt source-component rows derived from direct lltoxy with the actual v5 source header. Fresh pinned-ifx interp_sequence matches all 288 met_em QC values at exact pressure levels. This validates horizontal QC source-component influence for these targets and levels, not complete source selection elsewhere, other fields, or native eta influence.'
base['operator']['direct_met_em_95000_validation']={'exact_float32_matches':16,'mismatch_count':0,'target_count':16,'method':'Freshly compiled WPS interp_sequence with four_pt+average_4pt, actual source header radius, target XLAT_M/XLONG_M, actual QC source slabs; direct predictions compared with met_em QC at PRES=95000 Pa.'}
base['operator']['direct_met_em_all_levels_validation']={'exact_float32_matches':288,'mismatch_count':0,'target_count':16,'pressure_level_count':18,'pressure_levels_pa':sorted({r['pressure_pa'] for r in rows},reverse=True),'method':'Freshly compiled WPS interp_sequence with four_pt+average_4pt, actual source header radius, target XLAT_M/XLONG_M, source QC records matched by exact xlvl/PRES; compared with met_em QC at exact pressure levels.'}
base['observed_final_qc_comparison']['direct_interp_call_scope']='Direct WPS interp_sequence replay over all 16 candidate-supported mass-grid targets × 18 original candidate pressure levels, using the exact source QC slab at each level and actual met_em pressure-level values.'
base['source_support']['candidate_qc_valid_5x5x18']=True

# Update coords/weight information in previous sections to exact replay values.
example=next(r for r in rows if (r['target_i0'],r['target_j0'])==(133,15) and r['pressure_pa']==95000)
obs=base['observed_final_qc_comparison']
obs['direct_fresh_ifx_interp_sequence_prediction_f32']=example['prediction_f32']
obs['direct_fresh_ifx_interp_sequence_prediction_hex']=example['prediction_hex']
obs['direct_interp_coordinate_xy_wps_1based_actual_radius']=[example['source_x_wps'],example['source_y_wps']]
obs['direct_interp_sequence_coordinate_xy_wps_1based']=[example['source_x_wps'],example['source_y_wps']]
obs['direct_interp_actual_radius_m']=6371229.00390625
obs['source_laps_qc_four_pt_prediction_f32']=example['prediction_f32']
obs['source_laps_qc_four_pt_prediction_hex']=example['prediction_hex']
obs['observed_met_em_qc_f32']=example['met_em_qc_f32']
obs['observed_met_em_qc_hex']=example['met_em_qc_hex']
obs['moisture_normalization_probe']['ratio_final_to_direct_laps_prediction']=1.0
obs['moisture_normalization_probe']['conclusion']='The prior mismatch came from using an incorrect 6370000 m source radius; the actual v5 header radius reproduces all 288 tested met_em values bitwise.'
obs['moisture_normalization_probe']['finding']='The apparent 1.8% ratio is eliminated when lltoxy uses the source header radius 6371229.00390625 m. No moisture normalization or post-metgrid rewrite is needed to explain it.'
obs['fresh_operator_replay']['scope']='Source-operator replay for 16 affected mass-grid targets × 18 source pressure levels; not full process_domain/metgrid execution or real.exe native eta composition.'
obs['fresh_operator_replay']['output']='Using header radius 6371229.00390625 m, direct interp_sequence matches all 288 source-only QC values against met_em bitwise.'

base_path.write_text(json.dumps(base,indent=2,ensure_ascii=False)+'\n')

# Save full per-level operator predictions and coefficients with explicit provenance.
target_geometry=[]
for i,j in by_target:
    target_row=next(r for r in rows if (r['target_i0'],r['target_j0'])==(i,j))
    x=np.float32(target_row['source_x_wps']); y=np.float32(target_row['source_y_wps'])
    target_geometry.append({'target_i0':i,'target_j0':j,'target_lat_f32':latlon[(i,j)][0],
      'target_lon_f32':latlon[(i,j)][1],'source_x_wps':float(x),'source_y_wps':float(y),
      'fractional_x_wps':float(np.float32(x-np.float32(math.floor(float(x))))),
      'fractional_y_wps':float(np.float32(y-np.float32(math.floor(float(y))))),
      'four_pt_corners':[{'source_i0':si,'source_j0':sj,'weight_f32':float(w),'weight_hex':f32_hex(w)}
       for (si,sj),w in weights_by_target[(i,j)].items()]})
level_doc={'schema':'pr91_wps_horizontal_laps_qc_level_replay_v1',
 'source_record_file':str(base['observed_final_qc_comparison']['laps_source']),
 'source_record_sha256':base['source_support']['sha256'],'source_header_radius_m':6371229.00390625,
 'source_levels_k0':list(range(3,21)),'target_count':16,'level_count':18,'comparison_count':288,
 'comparison_count_bitwise_match':sum(r['prediction_hex']==r['met_em_qc_hex'] for r in rows),
 'comparison_rows':rows,
 'inverse_support':{f'{i},{j}':[{'target_i0':t['target_i0'],'target_j0':t['target_j0'],
   'coefficient_hex':f32_hex(weights_by_target[(t['target_i0'],t['target_j0'])][(i,j)])}
   for t in base['union_target_cells'] if (i,j) in weights_by_target[(t['target_i0'],t['target_j0'])]
   and weights_by_target[(t['target_i0'],t['target_j0'])][(i,j)]!=0] for i,j in source_cells},
 'target_geometry':target_geometry,
 'inverse_support_scan':{'met_em_grid_points_scanned':65988,'positive_support_target_cells':len({k[:2] for k,_ in scan_rows}),'nonzero_source_to_target_links':len(scan_rows),'coefficient_hex_links_matching_persisted_rows':sum(json_link_bits.get(k)==v for k,v in scan_rows),'target_grid_file_sha256':hashlib.sha256((root/'target_grid_234x282.txt.gz').read_bytes()).hexdigest(),'scan_output_sha256':hashlib.sha256((root/'inverse_support_rows.txt').read_bytes()).hexdigest(),'scan_summary':(root/'scan.log').read_text().strip()},
 'negative_control':{'source_header_radius_m':6370000.0,'purpose':'intentional wrong-radius replay; confirms historical mismatch was projection radius, not source-field normalization','comparison_count':len(wrong_rows),'bitwise_match_count':sum(r[5]==r[6] for r in wrong_rows),'mismatch_count':sum(r[5]!=r[6] for r in wrong_rows),'example_95000_i133_j15':next({'source_x_wps':float(r[3]),'source_y_wps':float(r[4]),'prediction_hex':r[5],'met_em_qc_hex':r[6]} for r in wrong_rows if r[0]=='95000.0' and r[1:3]==['133','15']),'output_sha256':hashlib.sha256((root/'grid_rows_288_wrong_radius.out').read_bytes()).hexdigest()},
 'source_qc_levels':{'record_count':21,'record_xlvl_pa':[int(float(line.split()[2])) for line in (root/'qc_headers.txt').read_text().splitlines()],'candidate_k0_3_20_xlvl_pa':list(range(95000,9999,-5000)),'all_288_candidate_four_point_corner_values_finite_and_nonmissing':True,'corners_checked':corner_count},
 'replay_inputs':{'qc_levels_gzip_sha256':hashlib.sha256((root/'qc_levels.txt.gz').read_bytes()).hexdigest(),'qc_headers_text_sha256':hashlib.sha256((root/'qc_headers.txt').read_bytes()).hexdigest(),'targets_288_sha256':hashlib.sha256((root/'targets_288.txt').read_bytes()).hexdigest(),'direct_output_sha256':hashlib.sha256((root/'grid_rows_288.out').read_bytes()).hexdigest(),'wrong_radius_output_sha256':hashlib.sha256((root/'grid_rows_288_wrong_radius.out').read_bytes()).hexdigest(),'source_laps_binary_sha256':base['source_support']['sha256'],'met_em_binary_sha256':base['observed_final_qc_comparison']['source_record_identity']['output_file_sha256']},
 'source_projection_binding':{'source_header_file':str(base['source_grid']['projection_record_path']),'source_record_sha256':base['source_support']['sha256'],'projection_record_earth_radius_km':6371.22900390625,'earth_radius_m_to_push_source_projection':6371229.00390625,'reader_source':'operator_source/read_met_module.F','reader_source_sha256':hashlib.sha256((root/'operator_source/read_met_module.F').read_bytes()).hexdigest(),'reader_v5_record':'Lambert v5 reads earth_radius after truelat2; process_domain passes earth_radius*1000 to push_source_projection.'},
 'active_table_binding':{'source_file':'METGRID.TBL','sha256':hashlib.sha256((root/'METGRID.TBL').read_bytes()).hexdigest(),'QC_method':'four_pt+average_4pt','QC_mask':'none'},
 'operator_build':{'compiler':'ifx (IFX) 2026.0.0 20260331','profile':'Cloud-BAL tests/intel_toolchain.sh CLOUD_BAL_REPRO_FLAGS plus -free -convert big_endian','fresh_operator_source_sha256':{name:hashlib.sha256((root/'operator_source'/name).read_bytes()).hexdigest() for name in ['interp_module.F','llxy_module.F','module_map_utils.F','process_domain_module.F','read_met_module.F']},'reused_support_objects_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'support_objects').glob('*.o'))}} }
(root.parent/'direct_interp_288.json').write_text(json.dumps(level_doc,indent=2)+'\n')
print('updated',base_path)
print('wrote',root.parent/'direct_interp_288.json')
