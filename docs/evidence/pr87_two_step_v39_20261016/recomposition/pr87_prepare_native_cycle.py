#!/usr/bin/env python3
"""Create hash-bound v17 source copies for a two-step cloud-state experiment."""
import argparse
import gzip
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = Path('/var/tmp/pr85_native_joint_candidate_20261015v17')
RECEIPT_SHA = 'a2c09db99d3b934a6de677c30901434ce75012fb2fd9020f19c800ee19954353'
ZERO_OUT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/KIM_RDPS_MODL_V2026.2/phys/module_microphysics_zero_out.F')
ZERO_OUT_SHA = 'a57268701b424b07a604ce93f733314183a29bfb39e7e6283f92f8668808fa4f'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'expected exactly one source anchor: {old[:75]}')
    return text.replace(old, new, 1)


def cycle_call(label, full_tile=True):
    west = 'max(ids,grid%i_start(ij))' if full_tile else 'its'
    east = 'min(ide-1,grid%i_end(ij))' if full_tile else 'ite'
    south = 'max(jds,grid%j_start(ij))' if full_tile else 'jts'
    north = 'min(jde-1,grid%j_end(ij))' if full_tile else 'jte'
    top = 'min(k_end,kde-1)' if full_tile else 'k_end'
    return f"""       CALL pr87_cloud_cycle('{label}',grid%itimestep, &
            ims,ime,jms,jme,kms,kme, &
            {west},{east}, &
            {south},{north}, &
            k_start,{top}, &
            moist(ims,kms,jms,P_QC),scalar(ims,kms,jms,P_QNC))
"""


def solve_overlay(text, preserve):
    def tile_stage(label):
        return ('   IF (config_flags%mp_physics==37) THEN\n'
                '     DO ij=1,grid%num_tiles\n' + cycle_call(label) +
                '     ENDDO\n   ENDIF\n')
    anchor='   Runge_Kutta_loop:  DO rk_step = 1, rk_order'
    text=replace_once(text,anchor,tile_stage('STEP_BEGIN')+'\n'+anchor)
    anchor='BENCH_END(micro_driver_tim)'
    text=replace_once(text,anchor,anchor+'\n'+tile_stage('POST_KDM6_FULL_TILE'))
    anchor='       CALL moist_physics_finish_em( grid%t_2, grid%t_1, t0, grid%muts, th_phy,  &'
    text=replace_once(text,anchor,cycle_call('POST_HOST_CLEANUP',False)+'\n'+anchor)
    text=replace_once(text,'   RETURN\n\nEND SUBROUTINE solve_em',
                      tile_stage('STEP_END')+'\n   RETURN\n\nEND SUBROUTINE solve_em')
    if preserve:
        # Only the moisture call preserves fields with independent moments.
        # Vapor, snow, scalar/chem/tracer calls keep their original policies.
        pattern=r'(CALL microphysics_zero_outa\s*\(\s*&\s*moist\s*,\s*num_moist\b.*?k_start\s*,\s*k_end\s*)(\))'
        text,count=re.subn(pattern,r'\1, &\n                      preserve_paired_moisture=(config_flags%mp_physics==37) \2',text,flags=re.S)
        if count!=1:
            raise ValueError('expected one moisture-only cutoff call')
    return text


def zero_out_overlay(text):
    active, boundary = text.split('SUBROUTINE microphysics_zero_outb', 1)
    text = active
    old=',its,ite, jts,jte, kts,kte                         )'
    if text.count(old)!=1:
        raise ValueError('expected one cutoff interface')
    text=text.replace(old,',its,ite, jts,jte, kts,kte, preserve_paired_moisture )')
    old='   INTEGER i,j,k,n'
    if text.count(old)!=1:
        raise ValueError('expected one cutoff declaration block')
    text=text.replace(old,old+'\n   LOGICAL, OPTIONAL, INTENT(IN) :: preserve_paired_moisture')
    old='      DO n = PARAM_FIRST_SCALAR,n_moist'
    if text.count(old)!=2:
        raise ValueError('expected two cutoff field loops')
    skip="""
         ! Paired KDM6 condensates retain their scheme-committed Q/N/B state.
         IF (PRESENT(preserve_paired_moisture)) THEN
            IF (preserve_paired_moisture) THEN
               IF (n==P_QC .OR. n==P_QI .OR. n==P_QR .OR. n==P_QG) CYCLE
            ENDIF
         ENDIF"""
    return text.replace(old,old+skip) + 'SUBROUTINE microphysics_zero_outb' + boundary


def pbl_overlay(text):
    anchor='               CALL bl_fogdes_qn(vdfg,qc_curr,qnc_curr,qv_curr,t_phy,dtbl,rho,dz8w, &'
    addition="""               CALL pr87_cloud_cycle('FOGDES_INPUT',itimestep, &
                    ims,ime,jms,jme,kms,kme, &
                    i_start(ij),i_end(ij),j_start(ij),j_end(ij), &
                    kts,min(kte,kde-1),qc_curr,qnc_curr)
"""
    return replace_once(text,anchor,addition+anchor)


def fog_overlay(text):
    old="""          IF (qc(i,k,j)<=0.0 .OR. qnc(i,k,j)<=0.0) &
            CALL wrf_error_fatal('FogDES paired Stokes settling requires both cloud moments')"""
    new="""          IF (qc(i,k,j)<=0.0 .OR. qnc(i,k,j)<=0.0) THEN
            WRITE(*,'(a,3(1x,i0),2(1x,es24.16))') 'PR87_FOGDES_REJECT', &
                 i,j,k,REAL(qc(i,k,j),real64),REAL(qnc(i,k,j),real64)
            CALL wrf_error_fatal('FogDES paired Stokes settling requires both cloud moments')
          ENDIF"""
    return replace_once(text,old,new)


def quiet_ledgers(text):
    # Omit only formatted cold/warm row writes. All rate/state calculations stay.
    for group in ('cold','warm'):
        start=text.index(f"            write(pr85_{group}_unit,'(a,")
        last=f"            if (pr85_{group}_ios.ne.0) error stop 'PR85 {group} budget write failed'"
        end=text.index(last,start)+len(last)
        text=text[:start]+('            ! Existing full v17 ledgers remain the reference.\n'
                          '            if (.false.) then\n')+text[start:end]+\
             '\n            endif'+text[end:]
    return text


def joint_storage_module(text, components, output, source_first=False, defer_kernel=False):
    """Replace only the hash-bound embedded kernel and native update fragment."""
    parts = {}
    for name in ('transport_kernel', 'native_update_fragment'):
        path = Path(components[name])
        if sha(path) != components[name + '_sha256']:
            raise ValueError(f'parent component hash mismatch: {name}')
        parts[name] = path.read_text()
    kernel = ROOT / 'src/common/cloud_bal_joint_transport.f90'
    composition_kernel=kernel.read_text()
    if defer_kernel:
        # Earlier pinned transforms bind the complete legacy module. Compose
        # those first, then replace only its separately pinned kernel body.
        archive=ROOT/'docs/evidence/pr87_two_step_v22b_20261016/module_em_pr85.F.gz'
        retained=gzip.decompress(archive.read_bytes()).decode()
        end=retained.index('end module cloud_bal_joint_transport\n')+len('end module cloud_bal_joint_transport\n')
        composition_kernel=retained[:end]
        if hashlib.sha256(composition_kernel.encode()).hexdigest()!='19d0259c423a3035a418174292c14d8671d778ebfe48a604cc80923c2f854541':
            raise ValueError('pinned composition kernel differs from V22b')
        (output/'composition_kernel.f90').write_text(composition_kernel)
    patch = ROOT / 'patches/pr87_joint_storage_update.patch'
    fragment = output / 'native_update.f90'
    fragment.write_text(parts['native_update_fragment'])
    result = subprocess.run(['patch', '--batch', '--fuzz=0', str(fragment), str(patch)],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (output / 'native_update.patch.log').write_text(result.stdout)
    if result.returncode:
        raise ValueError('joint storage fragment patch failed: ' + result.stdout)
    source_first_patch = ROOT / 'patches/pr87_source_first_update.patch'
    if source_first:
        result = subprocess.run(['patch', '--batch', '--fuzz=0', str(fragment), str(source_first_patch)],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (output / 'source_first.patch.log').write_text(result.stdout)
        if result.returncode:
            raise ValueError('source-first fragment patch failed: ' + result.stdout)
    text = replace_once(text, parts['transport_kernel'], composition_kernel)
    text = replace_once(text, parts['native_update_fragment'], fragment.read_text())
    return text, {'kernel_path': str(kernel), 'kernel_sha256': sha(kernel),
                  'patch_path': str(patch), 'patch_sha256': sha(patch),
                  'generated_fragment_sha256': sha(fragment),
                  'parent_components': components, 'source_first_donors': source_first,
                  'source_first_patch_sha256': sha(source_first_patch) if source_first else None,
                  'deferred_kernel_replacement':defer_kernel,
                  'composition_kernel_sha256':hashlib.sha256(composition_kernel.encode()).hexdigest()}


def prepare(output, preserve=False, reasons=False, joint_storage=False, source_first=False, joint_rain=False, ng_base_diag=False, rain_diffusion_probe=False, rain_diffusion_precision=False, trace_rain_failure=False, rain_density_storage=False, ice_sublimation_pending=False, cloud_source_contract=False, graupel_source_contract=False, cloud_diffusion_precision=False, pbl_source_probe=False, pbl_source_precision=False, all_pair_diffusion_precision=False, compact_pbl_diagnostics=False, fogdes_source_contract=False, graupel_process_domain=False, process_failure_context=False, progb_failure_context=False, ice_sublimation_cap_order=False):
    if ice_sublimation_cap_order and (not process_failure_context or progb_failure_context):
        raise ValueError('ice sublimation cap order requires the final process source without ProgB diagnostic context')
    if process_failure_context and not graupel_process_domain:
        raise ValueError('exact process failure context requires the selected graupel-domain source')
    if progb_failure_context and not process_failure_context:
        raise ValueError('ProgB failure context requires the selected process-failure source')
    if graupel_process_domain and not fogdes_source_contract:
        raise ValueError('graupel process domain requires the selected V31 source composition')
    if fogdes_source_contract and not pbl_source_precision:
        raise ValueError('FogDES source contract requires the selected explicit PBL payload')
    if compact_pbl_diagnostics and not pbl_source_precision:
        raise ValueError('compact PBL diagnostics requires the selected explicit PBL payload')
    if all_pair_diffusion_precision and not pbl_source_precision:
        raise ValueError('all-pair diffusion precision requires the selected PBL precision baseline')
    if pbl_source_precision and (not cloud_diffusion_precision or pbl_source_probe):
        raise ValueError('PBL precision requires the selected baseline without the diagnostic-only probe')
    if pbl_source_probe and not cloud_diffusion_precision:
        raise ValueError('PBL source probe requires the selected cloud/rain precision baseline')
    if cloud_diffusion_precision and not graupel_source_contract:
        raise ValueError('cloud diffusion precision requires the selected strict-graupel source baseline')
    if (graupel_source_contract or cloud_diffusion_precision) and not cloud_source_contract:
        raise ValueError('strict graupel/cloud diffusion requires the selected cloud source baseline')
    if cloud_source_contract and not ice_sublimation_pending:
        raise ValueError('cloud source contract requires the selected pending-ice baseline')
    if ice_sublimation_pending and not (rain_density_storage and trace_rain_failure):
        raise ValueError('ice sublimation pending requires the selected updated-density and diagnostic baseline')
    if rain_density_storage and not rain_diffusion_precision:
        raise ValueError('updated-density rain storage requires the selected precision overlay')
    if rain_diffusion_precision and (not joint_rain or rain_diffusion_probe):
        raise ValueError('rain diffusion precision requires the selected rain source without the V16-only probe')
    if rain_diffusion_probe and not joint_rain:
        raise ValueError('rain diffusion probe requires the selected paired source')
    if ng_base_diag and not joint_rain:
        raise ValueError("nongraupel base diagnostics require the selected rain overlay")
    if trace_rain_failure and not joint_rain:
        raise ValueError('rain failure diagnostics require the selected paired rain overlay')
    if joint_rain and not (preserve and reasons and source_first):
        raise ValueError('joint rain sedimentation requires the selected cleanup, reason and source-first overlays')
    if source_first and not joint_storage:
        raise ValueError("source-first donors require the joint storage overlay")
    receipt=PARENT/'pr85_native_transport_build.json'
    if sha(receipt)!=RECEIPT_SHA:
        raise ValueError('v17 build receipt hash mismatch')
    parent=json.loads(receipt.read_text())
    records={r['member']:r for r in parent['compiled_objects']+parent['supplemental_replacements']}
    output.mkdir(parents=True,exist_ok=False)
    transforms={}
    if joint_storage:
        transforms['module_em.o']=lambda t:t
    transforms.update({'solve_em.o':lambda t:solve_overlay(t,preserve),
                'module_pbl_driver.o':pbl_overlay,'module_bl_fogdes.o':fog_overlay,
                'module_mp_kdm6.o':quiet_ledgers})
    if source_first:
        transforms['module_first_rk_step_part2.o']=lambda t:t
    sources={}
    provenance={}
    if preserve:
        if sha(ZERO_OUT)!=ZERO_OUT_SHA:
            raise ValueError('generic zero-out source hash mismatch')
        target=output/ZERO_OUT.name
        target.write_text(zero_out_overlay(ZERO_OUT.read_text()))
        sources['module_microphysics_zero_out.o']=str(target.resolve())
        provenance['module_microphysics_zero_out.o']={'parent_source':str(ZERO_OUT),
            'parent_sha256':ZERO_OUT_SHA,'candidate_source':str(target),'candidate_sha256':sha(target)}
    rain_components=None
    rain_failure_diagnostic=None
    ng_diag_components=None
    rain_store_components=None
    for member,transform in transforms.items():
        row=records[member]
        source=Path(row.get('patched_source_path',row['source_path']))
        expected=row.get('patched_source_sha256',row['source_sha256'])
        if sha(source)!=expected:
            raise ValueError(f'parent source mismatch: {member}')
        target=output/source.name
        updated=transform(source.read_text())
        storage_components=None
        if joint_storage and member=='module_em.o':
            updated,storage_components=joint_storage_module(updated,row['source_components'],output,source_first,joint_rain)
        if reasons and member=='module_mp_kdm6.o':
            from pr87_admission_reason_overlay import add_admission_reasons
            updated=add_admission_reasons(updated)
        if joint_rain and member=='module_mp_kdm6.o':
            from pr87_rain_sedimentation import generate_rain_sedimentation
            helper=ROOT/'tools/pr85_kdm6_ice_sedimentation.F90'
            generator=ROOT/'tools/pr87_rain_sedimentation.py'
            before=hashlib.sha256(updated.encode()).hexdigest()
            updated=generate_rain_sedimentation(updated,helper.read_text())
            rain_components={'parent_generated_source_sha256':before,
                'helper_path':str(helper),'helper_sha256':sha(helper),
                'generator_path':str(generator),'generator_sha256':sha(generator),
                'policy':'native distinct mass/number speed proposals; one admitted face fraction; full rain PSD and separate moment/surface/storage budgets'}
        if joint_rain and member=='module_mp_kdm6.o':
            from pr87_rain_process_contract import add_rain_process_contract
            from pr87_rain_storage_contract import extend_kdm6_public_return
            updated=add_rain_process_contract(updated)
            updated=extend_kdm6_public_return(updated)
            rain_store_components={name:{'path':str(ROOT/name),'sha256':sha(ROOT/name)}
                for name in ('tools/pr87_rain_process_contract.py','tools/pr87_rain_storage_contract.py',
                             'tools/pr87_rain_public_store.f90')}
        if ng_base_diag and member=='module_mp_kdm6.o':
            from pr87_kdm6_ng_base_diag import generate_ng_base_diagnostic
            generator=ROOT/'tools/pr87_kdm6_ng_base_diag.py'
            before=hashlib.sha256(updated.encode()).hexdigest()
            updated=generate_ng_base_diagnostic(updated)
            ng_diag_components={'parent_generated_source_sha256':before,
                'generator_path':str(generator),'generator_sha256':sha(generator),
                'policy':'read-only exact state diagnostics immediately before unchanged nongraupel base rejection'}
        if trace_rain_failure and member=='module_mp_kdm6.o':
            from pr87_rain_sedimentation import add_rain_failure_diagnostic
            generator=ROOT/'tools/pr87_rain_sedimentation.py'
            before=hashlib.sha256(updated.encode()).hexdigest()
            updated=add_rain_failure_diagnostic(updated)
            rain_failure_diagnostic={'parent_generated_source_sha256':before,
                'generator_path':str(generator),'generator_sha256':sha(generator),
                'policy':'on rain-helper rejection only, write the failed column Q/N/rho/dz and velocity inputs then flush before the unchanged fatal'}
        target.write_text(updated)
        sources[member]=str(target.resolve())
        provenance[member]={'parent_source':str(source),'parent_sha256':expected,
                            'candidate_source':str(target),'candidate_sha256':sha(target)}
        if storage_components:
            provenance[member]['joint_storage_components']=storage_components
        if joint_rain and member=='module_mp_kdm6.o':
            provenance[member]['joint_rain_sedimentation']=rain_components
    source_capture=None
    if source_first:
        from pr87_physical_source_capture import generate_source_capture
        part2=Path(sources['module_first_rk_step_part2.o'])
        solve=Path(sources['solve_em.o'])
        captured=generate_source_capture(part2.read_text(),solve.read_text())
        part2.write_text(captured['part2'])
        solve.write_text(captured['solve'])
        for member in ('module_first_rk_step_part2.o','solve_em.o'):
            provenance[member]['candidate_sha256']=sha(Path(sources[member]))
        # module_em supplies the joint interface; part2 supplies solve's new source payload.
        order=['module_microphysics_zero_out.o','module_em.o','module_pbl_driver.o',
               'module_bl_fogdes.o','module_mp_kdm6.o','module_first_rk_step_part2.o','solve_em.o']
        sources={member:sources[member] for member in order if member in sources}
        helper=ROOT/'tools/pr87_physical_source_capture.py'
        source_capture={'helper_path':str(helper),'helper_sha256':sha(helper),
                        'interface':'explicit intensive Q/N, current coupled references, source carrier/timestep, and later weighted RK1 non-air additions; no saved cache',
                        'scope':'MP37 single tile; reject changed sources or mismatched source/old carrier'}
    extra_support=None
    if joint_rain:
        from pr87_rain_storage_contract import extend_native_update
        fragment=output/'native_update.f90'
        original=fragment.read_text()
        updated=extend_native_update(original)
        em=Path(sources['module_em.o'])
        em.write_text(replace_once(em.read_text(),original,updated))
        fragment.write_text(updated)
        provenance['module_em.o']['candidate_sha256']=sha(em)
        provenance['module_em.o']['joint_storage_components']['generated_fragment_sha256']=sha(fragment)
        provenance['module_em.o']['strict_rain_storage']=rain_store_components
        support=output/'pr87_cloud_cycle_support.f90'
        observer=ROOT/'tools/pr87_cloud_cycle_observer.f90'
        public_store=ROOT/'tools/pr87_rain_public_store.f90'
        support.write_text(observer.read_text()+'\n'+public_store.read_text())
        extra_support={'path':str(support.resolve()),'sha256':sha(support),
            'components':{str(p):sha(p) for p in (observer,public_store)},
            'scope':'read-only cycle observer plus physical/numerical public rain storage; not observer-only'}
    diffusion_probe=None
    if rain_diffusion_probe:
        from pr87_rain_diffusion_probe import add_rain_diffusion_probe
        em=Path(sources['module_em.o'])
        before=sha(em)
        em.write_text(add_rain_diffusion_probe(em.read_text()))
        provenance['module_em.o']['candidate_sha256']=sha(em)
        helper=ROOT/'tools/pr87_rain_diffusion_probe.py'
        diffusion_probe={'parent_module_sha256':before,'helper_path':str(helper),
                         'helper_sha256':sha(helper),'physical_change':False,
                         'scope':'one selected rain stencil before/after the actual RK1 diffusion call'}
    diffusion_precision=None
    if rain_diffusion_precision:
        from pr87_rain_diffusion_precision import extend_rain_diffusion_precision
        em=Path(sources['module_em.o'])
        solve=Path(sources['solve_em.o'])
        fragment=output/'native_update.f90'
        helper=ROOT/'tools/pr87_horizontal_diffusion64.f90'
        transform=ROOT/'tools/pr87_rain_diffusion_precision.py'
        parent_hashes={p.name:sha(p) for p in (em,solve,fragment)}
        updated=extend_rain_diffusion_precision(em.read_text(),solve.read_text(),
                                               fragment.read_text(),helper.read_text())
        for key,path,member in (('em',em,'module_em.o'),('solve',solve,'solve_em.o')):
            path.write_text(updated[key])
            provenance[member]['candidate_sha256']=sha(path)
        fragment.write_text(updated['fragment'])
        provenance['module_em.o']['joint_storage_components']['generated_fragment_sha256']=sha(fragment)
        diffusion_precision={'parents_sha256':parent_hashes,
            'helper_path':str(helper),'helper_sha256':sha(helper),
            'transform_path':str(transform),'transform_sha256':sha(transform),
            'scope':'RK1 rain diffusion accumulator precision, explicit same-step rate through all RK stages; signed numerical pressure-coordinate ledger'}
    density_storage=None
    if rain_density_storage:
        from pr87_rain_density_storage import extend_rain_density_storage
        solve=Path(sources['solve_em.o'])
        transform=ROOT/'tools/pr87_rain_density_storage.py'
        helper=ROOT/'tools/pr87_rain_density_store.f90'
        before=sha(solve)
        solve.write_text(extend_rain_density_storage(solve.read_text()))
        provenance['solve_em.o']['candidate_sha256']=sha(solve)
        support=Path(extra_support['path'])
        support.write_text(support.read_text()+'\n'+helper.read_text())
        extra_support['sha256']=sha(support)
        extra_support['components'][str(helper)]=sha(helper)
        extra_support['scope']+='; atomic updated-density rain representation storage'
        density_storage={'parent_solve_sha256':before,
            'transform_path':str(transform),'transform_sha256':sha(transform),
            'helper_path':str(helper),'helper_sha256':sha(helper),
            'scope':'MP37 final per-RK density/filter/boundary state before RK observer; public N unchanged; signed numerical representation ledger'}
    ice_sublimation=None
    if ice_sublimation_pending:
        from pr87_ice_sublimation import extend_ice_sublimation_pending
        kdm6=Path(sources['module_mp_kdm6.o'])
        transform=ROOT/'tools/pr87_ice_sublimation.py'
        before=sha(kdm6)
        kdm6.write_text(extend_ice_sublimation_pending(kdm6.read_text()))
        provenance['module_mp_kdm6.o']['candidate_sha256']=sha(kdm6)
        ice_sublimation={'parent_module_sha256':before,
            'transform_path':str(transform),'transform_sha256':sha(transform),
            'scope':'cold pending full-ice sublimation only; NI remains through proposal/caps and positive-QI endpoints; actual full extinction cleared in local approved transaction before strict commit'}
    cloud_contract=None
    if joint_rain:
        em=Path(sources['module_em.o'])
        composition_kernel=(output/'composition_kernel.f90').read_text()
        active_kernel=(ROOT/'src/common/cloud_bal_joint_transport.f90').read_text()
        em.write_text(replace_once(em.read_text(),composition_kernel,active_kernel))
        provenance['module_em.o']['candidate_sha256']=sha(em)
    if cloud_source_contract:
        from pr87_cloud_source_contract import extend_cloud_source_contract,extend_qn_density_call,extend_cloud_public_contract
        em=Path(sources['module_em.o'])
        solve=Path(sources['solve_em.o'])
        fragment=output/'native_update.f90'
        transform=ROOT/'tools/pr87_cloud_source_contract.py'
        helper=ROOT/'tools/pr87_qn_density_store.f90'
        kdm6=Path(sources['module_mp_kdm6.o'])
        original=fragment.read_text()
        parents={p.name:sha(p) for p in (em,solve,fragment,kdm6)}
        updated=extend_cloud_source_contract(original)
        em.write_text(replace_once(em.read_text(),original,updated))
        fragment.write_text(updated)
        solve.write_text(extend_qn_density_call(solve.read_text()))
        kdm6.write_text(extend_cloud_public_contract(kdm6.read_text()))
        for member,path in (('module_em.o',em),('solve_em.o',solve),('module_mp_kdm6.o',kdm6)):
            provenance[member]['candidate_sha256']=sha(path)
        provenance['module_em.o']['joint_storage_components']['generated_fragment_sha256']=sha(fragment)
        support=Path(extra_support['path'])
        support_text=support.read_text()
        if support_text.count('pr87_rain_public_store')!=2:
            raise ValueError('expected one public store procedure to name generically')
        support_text=support_text.replace('pr87_rain_public_store','pr87_number_public_store')
        support.write_text(support_text+'\n'+helper.read_text())
        extra_support['sha256']=sha(support)
        extra_support['components'][str(helper)]=sha(helper)
        extra_support['scope']+='; atomic updated-density cloud/rain representation storage'
        cloud_contract={'parents_sha256':parents,'transform_path':str(transform),
            'transform_sha256':sha(transform),'helper_path':str(helper),'helper_sha256':sha(helper),
            'cloud_pidnc_real32':523.59881591796875,'cloud_lambda':[12000.0,500000.0],
            'scope':'source-derived cloud producer cone and per-pair strict volume storage; invalid continuous updates rejected before representation selection; joint cloud/rain public return; updated-density cloud/rain transaction leaves public N unchanged',
            'support_public_store_symbol':'pr87_number_public_store (same scalar algorithm, shared cloud/rain source coefficients)'}
    graupel_contract=None
    if graupel_source_contract:
        from pr87_graupel_source_contract import extend_graupel_strict_mass
        em=Path(sources['module_em.o'])
        fragment=output/'native_update.f90'
        transform=ROOT/'tools/pr87_graupel_source_contract.py'
        original=fragment.read_text()
        updated=extend_graupel_strict_mass(original)
        em.write_text(replace_once(em.read_text(),original,updated))
        fragment.write_text(updated)
        provenance['module_em.o']['candidate_sha256']=sha(em)
        provenance['module_em.o']['joint_storage_components']['generated_fragment_sha256']=sha(fragment)
        graupel_contract={'transform_path':str(transform),'transform_sha256':sha(transform),
            'strict_mass_pairs':[False,False,False,True], 'bulk_density_bounds':[100.0,900.0],
            'scope':'exact continuous and stored QG/QIB ratio; BG is specific volume, never number; directed Q representation only after valid continuous input'}
    cloud_diffusion=None
    if cloud_diffusion_precision:
        from pr87_cloud_diffusion_precision import extend_cloud_diffusion_precision
        em=Path(sources['module_em.o'])
        solve=Path(sources['solve_em.o'])
        fragment=output/'native_update.f90'
        transform=ROOT/'tools/pr87_cloud_diffusion_precision.py'
        parents={p.name:sha(p) for p in (em,solve,fragment)}
        updated=extend_cloud_diffusion_precision({'em':em.read_text(),'solve':solve.read_text(),
                                                  'fragment':fragment.read_text()})
        for label,path in (('em',em),('solve',solve),('fragment',fragment)):
            path.write_text(updated[label])
        provenance['module_em.o']['candidate_sha256']=sha(em)
        provenance['solve_em.o']['candidate_sha256']=sha(solve)
        provenance['module_em.o']['joint_storage_components']['generated_fragment_sha256']=sha(fragment)
        cloud_diffusion={'parents_sha256':parents,'transform_path':str(transform),
            'transform_sha256':sha(transform),
            'scope':'same original horizontal diffusion call and REAL32 host tendencies; source-defined stencil in REAL64 for QC/QNC and QR/QNR; explicit signed rate correction before each grouped RK consumer; no flux or process cap'}
    pbl_probe=None
    if pbl_source_probe:
        from pr87_pbl_source_probe import extend_pbl_source_probe
        row=records['module_bl_shinhong.o']
        shinhong=Path(row['patched_source_path'])
        expected=row['patched_source_sha256']
        if sha(shinhong)!=expected:
            raise ValueError('selected Shinhong source identity mismatch')
        part2=Path(sources['module_first_rk_step_part2.o'])
        transform=ROOT/'tools/pr87_pbl_source_probe.py'
        updated=extend_pbl_source_probe({'shinhong':shinhong.read_text(),'part2':part2.read_text()})
        target=output/'module_bl_shinhong.F'
        target.write_text(updated['shinhong'])
        part2.write_text(updated['part2'])
        sources['module_bl_shinhong.o']=str(target.resolve())
        order=['module_microphysics_zero_out.o','module_em.o','module_bl_shinhong.o',
               'module_pbl_driver.o','module_bl_fogdes.o','module_mp_kdm6.o',
               'module_first_rk_step_part2.o','solve_em.o']
        sources={member:sources[member] for member in order if member in sources}
        provenance['module_bl_shinhong.o']={'parent_source':str(shinhong),
            'parent_sha256':expected,'candidate_source':str(target),'candidate_sha256':sha(target)}
        provenance['module_first_rk_step_part2.o']['candidate_sha256']=sha(part2)
        from pr87_graupel_diffusion_probe import extend_graupel_diffusion_probe
        em=Path(sources['module_em.o'])
        gprobe=ROOT/'tools/pr87_graupel_diffusion_probe.py'
        em.write_text(extend_graupel_diffusion_probe(em.read_text()))
        provenance['module_em.o']['candidate_sha256']=sha(em)
        pbl_probe={'transform_path':str(transform),'transform_sha256':sha(transform),
            'graupel_diffusion_probe_path':str(gprobe),'graupel_diffusion_probe_sha256':sha(gprobe),
            'scope':'read-only fixed cloud column matrix/RHS/REAL64 replay, actual raw/coupled source, and one G/B diffusion stencil; no rate, operator, gate or state mutation'}
    pbl_precision=None
    if pbl_source_precision:
        from pr87_pbl_source_precision import add_pbl_source_precision
        from pr87_pbl_source_payload import extend_pbl_source_payload
        paths={label:Path(sources[member]) for label,member in (
            ('em','module_em.o'),('solve','solve_em.o'),
            ('part2','module_first_rk_step_part2.o'),('pbl_driver','module_pbl_driver.o'))}
        for label,member in (('shinhong','module_bl_shinhong.o'),
                             ('part1','module_first_rk_step_part1.o')):
            row=records[member]
            path=Path(row.get('patched_source_path',row['source_path']))
            if sha(path)!=row.get('patched_source_sha256',row['source_sha256']):
                raise ValueError(f'selected {label} source identity mismatch')
            paths[label]=path
        paths['fragment']=output/'native_update.f90'
        parents={label:sha(path) for label,path in paths.items()}
        updated=extend_pbl_source_payload(**{label:path.read_text()
            for label,path in paths.items() if label!='shinhong'})
        updated['shinhong']=add_pbl_source_precision(paths['shinhong'].read_text())
        members={'em':'module_em.o','solve':'solve_em.o','part1':'module_first_rk_step_part1.o',
                 'part2':'module_first_rk_step_part2.o','pbl_driver':'module_pbl_driver.o',
                 'shinhong':'module_bl_shinhong.o'}
        for label,text in updated.items():
            target=paths[label] if label not in ('part1','shinhong') else output/paths[label].name
            target.write_text(text)
            if label in members:
                member=members[label]
                sources[member]=str(target.resolve())
                provenance.setdefault(member,{})['candidate_sha256']=sha(target)
        order=['module_microphysics_zero_out.o','module_em.o','module_bl_shinhong.o',
               'module_pbl_driver.o','module_bl_fogdes.o','module_mp_kdm6.o',
               'module_first_rk_step_part1.o','module_first_rk_step_part2.o','solve_em.o']
        sources={member:sources[member] for member in order if member in sources}
        provenance['module_em.o']['joint_storage_components']['generated_fragment_sha256']=sha(paths['fragment'])
        pbl_precision={'parents_sha256':parents,'transforms':{
            name:sha(ROOT/'tools'/name) for name in
            ('pr87_pbl_source_precision.py','pr87_pbl_source_payload.py')},
            'channels':['QC','QNC','QI','QNI'],
            'scope':'shared stored PBL matrix/RHS REAL64 replay; explicit current-step intensive source delta; original packet withholding retained; no floor or relaxed bound'}
    all_pair_diffusion=None
    if all_pair_diffusion_precision:
        from pr87_all_pair_diffusion_precision import extend_all_pair_diffusion_precision
        paths={'em':Path(sources['module_em.o']),'solve':Path(sources['solve_em.o']),
               'fragment':output/'native_update.f90'}
        parents={label:sha(path) for label,path in paths.items()}
        updated=extend_all_pair_diffusion_precision({label:path.read_text() for label,path in paths.items()})
        for label,path in paths.items():
            path.write_text(updated[label])
        provenance['module_em.o']['candidate_sha256']=sha(paths['em'])
        provenance['solve_em.o']['candidate_sha256']=sha(paths['solve'])
        provenance['module_em.o']['joint_storage_components']['generated_fragment_sha256']=sha(paths['fragment'])
        transform=ROOT/'tools/pr87_all_pair_diffusion_precision.py'
        all_pair_diffusion={'parents_sha256':parents,'transform_path':str(transform),
            'transform_sha256':sha(transform),'channels':['QC','QNC','QI','QNI','QR','QNR','QG','QIB'],
            'scope':'same stored stencil and original host calls; RK1 capture, current-step correction consumed once per RK endpoint; BG remains specific bulk volume; strict continuous/stored gates retained'}
    compact_pbl=None
    if compact_pbl_diagnostics:
        from pr87_pbl_compact_diagnostics import extend_pbl_compact_diagnostics
        from pr87_pbl_source_payload import _append_call_args
        paths={label:Path(sources[member]) for label,member in
               (('shinhong','module_bl_shinhong.o'),('pbl_driver','module_pbl_driver.o'))}
        parents={label:sha(path) for label,path in paths.items()}
        updated=extend_pbl_compact_diagnostics({label:path.read_text() for label,path in paths.items()})
        for label,path in paths.items():
            path.write_text(updated[label])
        part1=Path(sources['module_first_rk_step_part1.o'])
        part1.write_text(_append_call_args(part1.read_text(),'pbl_driver',
                                          'PR87_COMPACT_DIAGNOSTICS=.TRUE.'))
        for member in ('module_bl_shinhong.o','module_pbl_driver.o','module_first_rk_step_part1.o'):
            provenance[member]['candidate_sha256']=sha(Path(sources[member]))
        transform=ROOT/'tools/pr87_pbl_compact_diagnostics.py'
        compact_pbl={'parents_sha256':parents,'transform_path':str(transform),
            'transform_sha256':sha(transform),
            'scope':'diagnostic-only opt-in; same packet gate, f3, qtnp and REAL64 source delta; step/pair/column summaries replace per-cell file open/write/close; DEL-weighted rates are not kg'}
    fogdes_contract=None
    if fogdes_source_contract:
        from pr87_fogdes_source_contract import extend_fogdes_source_contract
        fog=Path(sources['module_bl_fogdes.o'])
        driver=Path(sources['module_pbl_driver.o'])
        parents={'fogdes':sha(fog),'pbl_driver':sha(driver)}
        updated=extend_fogdes_source_contract(fog.read_text(),driver.read_text())
        fog.write_text(updated['fogdes'])
        driver.write_text(updated['pbl_driver'])
        for member in ('module_bl_fogdes.o','module_pbl_driver.o'):
            provenance[member]['candidate_sha256']=sha(Path(sources[member]))
        # Rebuild the defining module before its caller sees the new interface.
        order=['module_microphysics_zero_out.o','module_em.o','module_bl_shinhong.o',
               'module_bl_fogdes.o','module_pbl_driver.o','module_mp_kdm6.o',
               'module_first_rk_step_part1.o','module_first_rk_step_part2.o','solve_em.o']
        sources={member:sources[member] for member in order if member in sources}
        transform=ROOT/'tools/pr87_fogdes_source_contract.py'
        fogdes_contract={'parents_sha256':parents,'transform_path':str(transform),
            'transform_sha256':sha(transform),
            'cloud_pidnc_real32':523.59881591796875,'cloud_lambda':[12000.0,500000.0],
            'scope':'same Stokes proposals; common column process fraction approves the combined PBL/FogDES REAL64 source under the selected strict cloud cone; REAL32 tendency pattern retained and correction residual replaced once; original optional-absent path retained'}
    if pbl_source_precision:
        # Finalize the staged payload gate and source-domain contract together.
        fragment=output/'native_update.f90'
        em=Path(sources['module_em.o'])
        original=fragment.read_text()
        from pr87_pbl_source_payload import finalize_source_rate_validation
        updated=finalize_source_rate_validation(original)
        volume_store=("               allow_joint_quantum_absence=.TRUE.,volume_number_bounds=number_bounds(cell,:,p))\n"
                      "        ELSE\n")
        specific_store=("               allow_joint_quantum_absence=.TRUE.,strict_mass_ratio=.TRUE.)\n"
                        "        ELSE\n")
        # This virtual donor feeds specific-Q/N air fluxes, not rho*N.
        # The full grouped endpoint and post-density store retain volume gates.
        updated=replace_once(updated,volume_store,specific_store)
        anchor=("        IF (.NOT.full_valid) &\n"
                "          CALL wrf_error_fatal('PR87 corrected source-stage pair fails strict storage validation')\n")
        diagnostic="""        IF (.NOT.full_valid) THEN
          OPEN(NEWUNIT=u,FILE='pr85_joint_source_failure.raw',STATUS='UNKNOWN',POSITION='APPEND')
          WRITE(u,'(a,6i10,1p,20es26.17)') 'SOURCE_STAGE',itimestep,rk,p,i,j,k, &
            REAL(q1(i,k,j,qindex(p)),real64),REAL(n1(i,k,j,nindex(p)),real64), &
            source_rate64,source_candidate,REAL(drydensity(cell),real64), &
            minmass(p),maxmass(p),number_bounds(cell,:,p),REAL(dt,real64), &
            REAL(pr87_raw_qsrc(i,k,j,p),real64),REAL(pr87_raw_nsrc(i,k,j,p),real64), &
            pr87_pbl_tendency_delta64(i,k,j,:),REAL(oldcarrier(cell),real64),REAL(newcarrier(cell),real64)
          CLOSE(u)
          CALL wrf_error_fatal('PR87 corrected source-stage pair fails strict storage validation')
        END IF
"""
        updated=replace_once(updated,anchor,diagnostic)
        em.write_text(replace_once(em.read_text(),original,updated))
        fragment.write_text(updated)
        provenance['module_em.o']['candidate_sha256']=sha(em)
        provenance['module_em.o']['joint_storage_components']['generated_fragment_sha256']=sha(fragment)
    graupel_process=None
    if graupel_process_domain:
        from pr87_graupel_process_domain import extend_graupel_process_domain
        kdm6=Path(sources['module_mp_kdm6.o'])
        parent_hash=sha(kdm6)
        kdm6.write_text(extend_graupel_process_domain(kdm6.read_text()))
        provenance['module_mp_kdm6.o']['candidate_sha256']=sha(kdm6)
        transform=ROOT/'tools/pr87_graupel_process_domain.py'
        graupel_process={'parent_sha256':parent_hash,'transform_path':str(transform),
            'transform_sha256':sha(transform),
            'scope':'process search and stored endpoint use the existing ProgB graupel activity domain; preserve prognostic BG; graupel melt uses actual donor volume and one admitted Q/N/B/T fraction; strict thresholds retained'}
    process_context=None
    if process_failure_context:
        from pr87_process_failure_context import add_process_failure_context
        kdm6=Path(sources['module_mp_kdm6.o'])
        parent_hash=sha(kdm6)
        kdm6.write_text(add_process_failure_context(kdm6.read_text()))
        provenance['module_mp_kdm6.o']['candidate_sha256']=sha(kdm6)
        transform=ROOT/'tools/pr87_process_failure_context.py'
        process_context={'parent_sha256':parent_hash,'transform_path':str(transform),
            'transform_sha256':sha(transform),
            'scope':'failure-only exact actual G-search operands and coordinates; no source, rate, gate or state mutation'}
    ice_cap_order=None
    if ice_sublimation_cap_order:
        from pr87_ice_sublimation import correct_ice_sublimation_cap_order
        kdm6=Path(sources['module_mp_kdm6.o'])
        parent_hash=sha(kdm6)
        kdm6.write_text(correct_ice_sublimation_cap_order(kdm6.read_text()))
        provenance['module_mp_kdm6.o']['candidate_sha256']=sha(kdm6)
        transform=ROOT/'tools/pr87_ice_sublimation.py'
        ice_cap_order={'parent_sha256':parent_hash,'transform_path':str(transform),
            'transform_sha256':sha(transform),
            'scope':'detect full ice sublimation from the actual post-cap proposal; caps and rate equations unchanged; clear number only at exact approved zero mass'}
    progb_context=None
    if progb_failure_context:
        from pr87_progb_failure_context import add_progb_failure_context
        kdm6=Path(sources['module_mp_kdm6.o'])
        parent_hash=sha(kdm6)
        kdm6.write_text(add_progb_failure_context(kdm6.read_text()))
        provenance['module_mp_kdm6.o']['candidate_sha256']=sha(kdm6)
        transform=ROOT/'tools/pr87_progb_failure_context.py'
        progb_context={'parent_sha256':parent_hash,'transform_path':str(transform),
            'transform_sha256':sha(transform),
            'scope':'failure-only first ProgB unsupported cell and post-rho R32 B rewrite diagnostics; no process, rate, gate or state mutation'}
    result={'schema':'pr87_native_cycle_sources_v1','parent_receipt_sha256':RECEIPT_SHA,
            'preserve_kdm6_joint_cleanup':preserve,'source_overrides':sources,'provenance':provenance,
            'diagnostic_changes':'read-only cloud boundary summaries, fatal coordinates, no repeated cold/warm rows',
            'physical_change':('; '.join(change for change in (
                'preserve scheme-committed paired moisture fields in host cleanup' if preserve else None,
                'atomic rain Q representation after updated density and all RK stage mutations; public N unchanged, strict source-derived conversion limits retained' if rain_density_storage else None,
                'defer ice count extinction until actual approved QI endpoint is zero; cold search pending exception never used for final storage' if ice_sublimation_pending else None,
                'identify pending ice extinction after donor and thermodynamic caps' if ice_sublimation_cap_order else None,
                'bind cloud producer mass/volume bounds to selected KDM6 REAL32 coefficient; strict cloud/rain stores and atomic post-density representation transaction' if cloud_source_contract else None,
                'cloud/rain RK1 diffusion precision and explicit source-rate correction' if cloud_diffusion_precision else None,
                'explicit REAL64 shared-matrix PBL source correction for cloud and ice paired channels' if pbl_source_precision else None,
                'extend the same horizontal stencil precision correction to all four paired categories' if all_pair_diffusion_precision else None,
                'FogDES approves the actual combined PBL/FogDES source under the selected cloud cone' if fogdes_source_contract else None,
                'graupel process search and stored endpoint preserve the next ProgB activation domain; retain prognostic BG and jointly admit graupel melt mass, number, volume and temperature' if graupel_process_domain else None,
                'exact source-derived QG/QIB producer and storage contract' if graupel_source_contract else None,
                'rain RK1 horizontal-diffusion accumulator promoted before rounding; explicit REAL64 numerical rate correction across RK stages' if rain_diffusion_precision else None,
                'retain direct REAL64 common-face air rates for all paired categories' if joint_rain else None,
                'strict source-coefficient rain sedimentation and continuous/stored public-basis completion; original warm pair-only domain with validated zero-step control; signed representation ledger' if joint_rain else None,
                'admissibility-selected RK3 whole-pair intensive R32 source stage then common air transport; explicit source-representation ledger; preserve admissible old map and QR/QG rates' if source_first else None,
                'explicit constrained REAL32 joint storage' if source_first else
                'explicit subnormal joint storage' if joint_storage else None) if change) or None),
            'joint_rain_sedimentation':rain_components,
            'strict_completed_rain_storage':rain_store_components,'extra_support_source':extra_support,
            'nongraupel_base_failure_diagnostics':ng_diag_components,
            'rain_failure_diagnostics':rain_failure_diagnostic,
            'rain_diffusion_probe':diffusion_probe,
            'rain_diffusion_precision':diffusion_precision,
            'rain_updated_density_storage':density_storage,
            'ice_sublimation_pending':ice_sublimation,
            'ice_sublimation_cap_order':ice_cap_order,
            'cloud_source_contract':cloud_contract,
            'graupel_source_contract':graupel_contract,
            'cloud_diffusion_precision':cloud_diffusion,
            'pbl_source_probe':pbl_probe,
            'pbl_source_precision':pbl_precision,
            'all_pair_diffusion_precision':all_pair_diffusion,
            'compact_pbl_diagnostics':compact_pbl,
            'fogdes_source_contract':fogdes_contract,
            'graupel_process_domain':graupel_process,
            'process_failure_context':process_context,
            'progb_failure_context':progb_context,
            'source_stage_failure_operands':pbl_source_precision,
            'source_stage_checks_actual_real64_rate':pbl_source_precision,
            'virtual_cloud_source_domain':('strict specific-Q/N cone; no volume conversion until the completed endpoint' if pbl_source_precision else None),
            'admission_reason_probes':reasons,'joint_subnormal_storage':joint_storage and not source_first,
            'source_first_grouped_donors':source_first,
            'intensive_physical_source_capture':source_capture,
            'source_first_pair_indices':[1,2] if source_first else [],
            'source_first_trigger':'failed baseline full-store candidate, whole pair, single retry; any failed QR/QG forbids retry' if source_first else None,
            'joint_quantum_absence':source_first,
            'joint_storage_policy':('opt-in constrained REAL32 storage, explicit joint quantum absence, and REAL64 rates; signed numerical ledger; not conservation preserving' if source_first else
                'opt-in paired subnormal quantization with signed numerical ledger; not conservation preserving') if joint_storage else None}
    (output/'sources.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'overrides.json').write_text(json.dumps(sources,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--preserve-kdm6-joint-cleanup',action='store_true')
    parser.add_argument('--admission-reasons',action='store_true')
    parser.add_argument('--joint-subnormal-storage',action='store_true')
    parser.add_argument('--source-first-donors',action='store_true')
    parser.add_argument('--joint-rain-sedimentation',action='store_true')
    parser.add_argument('--trace-ng-invalid-base',action='store_true')
    parser.add_argument('--trace-rain-diffusion',action='store_true')
    parser.add_argument('--rain-diffusion-precision',action='store_true')
    parser.add_argument('--trace-rain-failure',action='store_true')
    parser.add_argument('--rain-density-storage',action='store_true')
    parser.add_argument('--ice-sublimation-pending',action='store_true')
    parser.add_argument('--ice-sublimation-cap-order',action='store_true')
    parser.add_argument('--cloud-source-contract',action='store_true')
    parser.add_argument('--graupel-source-contract',action='store_true')
    parser.add_argument('--cloud-diffusion-precision',action='store_true')
    parser.add_argument('--pbl-source-probe',action='store_true')
    parser.add_argument('--pbl-source-precision',action='store_true')
    parser.add_argument('--all-pair-diffusion-precision',action='store_true')
    parser.add_argument('--compact-pbl-diagnostics',action='store_true')
    parser.add_argument('--fogdes-source-contract',action='store_true')
    parser.add_argument('--graupel-process-domain',action='store_true')
    parser.add_argument('--process-failure-context',action='store_true')
    parser.add_argument('--progb-failure-context',action='store_true')
    args=parser.parse_args()
    prepare(
        args.output,
        preserve=args.preserve_kdm6_joint_cleanup,
        reasons=args.admission_reasons,
        joint_storage=args.joint_subnormal_storage,
        source_first=args.source_first_donors,
        joint_rain=args.joint_rain_sedimentation,
        ng_base_diag=args.trace_ng_invalid_base,
        rain_diffusion_probe=args.trace_rain_diffusion,
        rain_diffusion_precision=args.rain_diffusion_precision,
        trace_rain_failure=args.trace_rain_failure,
        rain_density_storage=args.rain_density_storage,
        ice_sublimation_pending=args.ice_sublimation_pending,
        ice_sublimation_cap_order=args.ice_sublimation_cap_order,
        cloud_source_contract=args.cloud_source_contract,
        graupel_source_contract=args.graupel_source_contract,
        cloud_diffusion_precision=args.cloud_diffusion_precision,
        pbl_source_probe=args.pbl_source_probe,
        pbl_source_precision=args.pbl_source_precision,
        all_pair_diffusion_precision=args.all_pair_diffusion_precision,
        compact_pbl_diagnostics=args.compact_pbl_diagnostics,
        fogdes_source_contract=args.fogdes_source_contract,
        graupel_process_domain=args.graupel_process_domain,
        process_failure_context=args.process_failure_context,
        progb_failure_context=args.progb_failure_context,
    )
