from pathlib import Path
import hashlib,json,os,subprocess
r=Path('/var/tmp/firsthour-runtime-plan-20261030/experiment'); host=r/'host'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def members(path):
 data=path.read_bytes(); assert data[:8]==b'!<arch>\n'; offset=8; out=[]
 while offset<len(data):
  head=data[offset:offset+60]; assert head[58:60]==b'`\n'; size=int(head[48:58]); body=data[offset+60:offset+60+size]; out.append((head[:16].decode('ascii').strip(),hashlib.sha256(body).hexdigest())); offset+=60+size+(size%2)
 return out
links={str(p.relative_to(host)):{'target':os.readlink(p),'resolved':str(p.resolve()),'sha256':sha(p) if p.is_file() else None} for p in host.rglob('*') if p.is_symlink()}
a=members(r/'build_BASE/libwrflib.a'); b=members(r/'build_FIX/libwrflib.a'); assert len(a)==len(b)
changes=[{'position':i,'name':x[0],'base':x[1],'fix':y[1]} for i,(x,y) in enumerate(zip(a,b)) if x!=y]; assert len(changes)==2 and changes[0]['name']=='/' and changes[1]['base']==sha(r/'build_BASE/module_mp_kdm6.o') and changes[1]['fix']==sha(r/'build_FIX/module_mp_kdm6.o'),changes
external=[Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/'+x) for x in ('mpif90','mpiifx','mpirun')]; netcdf=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel'); external += [p for sub in ('include','lib') for p in (netcdf/sub).rglob('*') if p.is_file()]; external={str(p):{'resolved':str(p.resolve()),'sha256':sha(p)} for p in external}
out={'measurement_phase':'post-build; original prebuild external seal unavailable','symlinks':links,'archive_member_count_including_metadata':len(a),'changed_archive_members':changes,'external_files':external}; (r/'dependency_postbuild.json').write_text(json.dumps(out,indent=2)+'\n'); print(len(links),len(a),len(external),changes)
