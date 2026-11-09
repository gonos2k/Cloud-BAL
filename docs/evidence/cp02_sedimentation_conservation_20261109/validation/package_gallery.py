#!/usr/bin/env python3
"""Package all per-threshold curves, hourly maps and P01 timing without editing images."""
import hashlib,html,json,zipfile
from pathlib import Path
B=Path(__file__).resolve().parents[1]
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 names=[('p01_return_and_surface.png','P01 반환 비와 지상 강수의 시간 분포')]
 names += [(f'candidate_csi_{t}mm.png',f'{t} mm 이상 CSI: 모든 예측시간') for t in ('0.1','0.5','1','2.5','5','10')]
 names += [(f'candidate_rn1_hour_{h}_maps.png',f'+{h-12}시간: {h-1:02d}–{h:02d} UTC 한 시간 강수와 차이') for h in range(13,19)]
 targets=[B/n for n in ('FIGURES.md','gallery.html','all_figures.zip','gallery_receipt.json')]
 if any(p.exists() or p.is_symlink() for p in targets):raise FileExistsError('preserve the existing gallery')
 p01=json.loads((B/'science/p01_timing_receipt.json').read_text())
 maps=json.loads((B/'evaluation/maps_metadata.json').read_text())
 scores=json.loads((B/'evaluation/results/receipt.json').read_text())
 for name,_ in names:
  p=B/'figures'/name
  if p.read_bytes()[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError(name)
  expected=(p01['outputs'].get('figures/'+name) or maps['outputs'].get(name) or scores['outputs'].get('figures/'+name))
  if sha(p)!=expected:raise ValueError('figure hash differs from scientific receipt: '+name)
 md=['# 보존 침강 후보: 전체 그림 모음','','초기시각 2026-08-16 12 UTC. 규준실험은 ORIGINAL, 현재 B1은 FIX이며 보존 침강 후보는 미채택(19/26)입니다. 시간·임계값·실험을 평균하지 않습니다.','','[학술 보고서](../../CP02_SEDIMENTATION_CONSERVATION_20261109.md) · [전체 H/M/F·CSI 표](evaluation/results/FULL_SCORES.md) · [그림·표 ZIP](all_figures.zip)','']
 body=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>보존 침강 후보 전체 그림</title><style>body{font-family:sans-serif;max-width:1400px;margin:2rem auto;padding:0 1rem;line-height:1.5}img{width:100%;height:auto}figure{margin:2rem 0}</style><h1>보존 침강 후보: 시간·임계값별 비교</h1><p>19/26으로 미채택, 현재 B1 유지. 지도는 같은 3,688개 평가점의 한 시간 강수입니다.</p>']
 for name,title in names:
  md += ['## '+title,'',f'![{title}](figures/{name})','']
  body += [f'<figure><h2>{html.escape(title)}</h2><img src="figures/{name}" alt="{html.escape(title)}"></figure>']
 md += ['[이전 OLD/FIX 과정 그림](../cp02_protected_process_20261106/FIGURES.md)은 기존 경로에서 확인할 수 있습니다.','']
 body += ['<p><a href="evaluation/results/FULL_SCORES.md">모든 시간·임계값별 수치표</a></p></html>']
 targets[0].write_text('\n'.join(md));targets[1].write_text('\n'.join(body)+'\n')
 members=['FIGURES.md','gallery.html','evaluation/results/FULL_SCORES.md']+['figures/'+n for n,_ in names]
 identities={n:{'sha256':sha(B/n),'size_bytes':(B/n).stat().st_size} for n in members}
 with zipfile.ZipFile(targets[2],'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for n in members:
   i=zipfile.ZipInfo(n,(1980,1,1,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=0o644<<16;z.writestr(i,(B/n).read_bytes())
 with zipfile.ZipFile(targets[2]) as z:
  if z.testzip() is not None or z.namelist()!=members:raise ValueError('ZIP CRC/inventory differs')
  for n in members:
   if hashlib.sha256(z.read(n)).hexdigest()!=identities[n]['sha256']:raise ValueError(n)
 receipt={'status':'PASS','png_count':13,'members':identities,'archive_sha256':sha(targets[2]),'archive_size_bytes':targets[2].stat().st_size,'tool_sha256':sha(Path(__file__))}
 targets[3].write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'status':'PASS','png_count':13,'zip_bytes':receipt['archive_size_bytes']}))
if __name__=='__main__':main()
