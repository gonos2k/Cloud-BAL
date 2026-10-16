"""Bind cloud/rain RK producers to the selected KDM6 REAL32 coefficients."""
from __future__ import annotations

import hashlib


FRAGMENT_SHA256 = "e2abb1809b6fa49ab56ebc82ecc205f9fca6f9dba28192ce49ed1136d32b648e"
SOLVE_SHA256 = "fd48e553e12069f33e399d3bce78344a2c8e2b8968390616e23aef7d527c92d4"
KDM6_SHA256 = "245e8a46bf11ba7e85137a81547f7e02b7f2bc429a293cbd3a34f61fc7b4a24d"


def _replace(source: str, old: str, new: str, count: int = 1) -> str:
    if source.count(old) != count:
        raise ValueError(f"unexpected cloud-contract anchor count: {old[:80]!r}")
    return source.replace(old, new)


def extend_cloud_source_contract(fragment: str) -> str:
    """Use source-order bounds for both strict number pairs before storage."""
    if hashlib.sha256(fragment.encode()).hexdigest() != FRAGMENT_SHA256:
        raise ValueError("native fragment differs from frozen V22b")
    source = _replace(fragment, "rain_bounds(:,:)", "number_bounds(:,:,:)")
    source = _replace(
        source,
        "  REAL(real32),PARAMETER :: rain_lambda_min=961.0_real32,rain_lambda_max=35000.0_real32\n",
        "  REAL(real32),PARAMETER :: rain_lambda_min=961.0_real32,rain_lambda_max=35000.0_real32\n"
        "  REAL(real32),PARAMETER :: cloud_pidn=523.59881591796875_real32,cloud_power=3.0_real32\n"
        "  REAL(real32),PARAMETER :: cloud_lambda_min=12000.0_real32,cloud_lambda_max=500000.0_real32\n",
    )
    source = _replace(source, "minmass=[4.188790204786391e-15_real64,",
                      "minmass=[REAL(cloud_pidn,real64)/REAL(cloud_lambda_max,real64)**REAL(cloud_power,real64),")
    source = _replace(source, "maxmass=[3.0300855069345996e-10_real64,",
                      "maxmass=[REAL(cloud_pidn,real64)/REAL(cloud_lambda_min,real64)**REAL(cloud_power,real64),")
    source = _replace(source, "rain_bounds(cells,2))", "number_bounds(cells,2,4))\n  number_bounds=0.0_real64")
    source = _replace(source, "rain_bounds(cell,1)=", "number_bounds(cell,1,3)=")
    source = _replace(source, "rain_bounds(cell,2)=", "number_bounds(cell,2,3)=")
    source = _replace(
        source,
        "    number_bounds(cell,1,3)=REAL(drydensity(cell),real64)* &\n",
        "    number_bounds(cell,1,1)=REAL(drydensity(cell),real64)* &\n"
        "        REAL(cloud_lambda_min,real64)**REAL(cloud_power,real64)/REAL(cloud_pidn,real64)\n"
        "    number_bounds(cell,2,1)=REAL(drydensity(cell),real64)* &\n"
        "        REAL(cloud_lambda_max,real64)**REAL(cloud_power,real64)/REAL(cloud_pidn,real64)\n"
        "    number_bounds(cell,1,3)=REAL(drydensity(cell),real64)* &\n",
    )
    source = _replace(source, "IF (p==3) THEN", "IF (p==1.OR.p==3) THEN")
    source = _replace(source, "IF (pair==3) THEN", "IF (pair==1.OR.pair==3) THEN")
    source = _replace(source, "volume_number_bounds=rain_bounds(cell,:)",
                      "volume_number_bounds=number_bounds(cell,:,p)")
    source = _replace(source, "volume_number_bounds=rain_bounds(c,:)",
                      "volume_number_bounds=number_bounds(c,:,pair)")
    source = _replace(source, "strict_number_pair=3,volume_number_bounds=rain_bounds)",
                      "number_pair_bounds=number_bounds)")
    return source


def extend_qn_density_call(solve: str) -> str:
    """Check both pairs against the final RK density before its observer."""
    if hashlib.sha256(solve.encode()).hexdigest() != SOLVE_SHA256:
        raise ValueError("solve source differs from frozen V22b")
    source = _replace(solve, "pr87_rain_density_store", "pr87_qn_density_store", 2)
    source = _replace(source, "pr87_rain_density_valid", "pr87_qn_density_valid", 3)
    source = _replace(source, "Recheck public rain storage", "Recheck public cloud/rain storage")
    source = _replace(
        source,
        "              moist(ims,kms,jms,P_QR),scalar(ims,kms,jms,P_QNR), &\n"
        "              12566.37109375,3.0,961.0,35000.0,pr87_qn_density_valid)",
        "              moist(ims,kms,jms,P_QC),scalar(ims,kms,jms,P_QNC), &\n"
        "              moist(ims,kms,jms,P_QR),scalar(ims,kms,jms,P_QNR), &\n"
        "              523.59881591796875,3.0,12000.0,500000.0, &\n"
        "              12566.37109375,3.0,961.0,35000.0,pr87_qn_density_valid)",
    )
    return _replace(source, "PR87 rain density storage transaction rejected",
                    "PR87 cloud/rain density storage transaction rejected")


def extend_cloud_public_contract(kdm6: str) -> str:
    """Store a valid internal cloud pair jointly at the public-unit producer."""
    if hashlib.sha256(kdm6.encode()).hexdigest() != KDM6_SHA256:
        raise ValueError("KDM6 source differs from frozen V22b")
    source = _replace(kdm6, "pr87_rain_public_store", "pr87_number_public_store", 3)
    # The procedure name and old ledger filename both contain that token.
    source = _replace(source, "file='pr87_number_public_store.raw'",
                      "file='pr87_qn_public_store.raw'")
    source = _replace(
        source,
        "   pr67_trace_this_call = .not. pr67_trace_complete\n",
        "   if (.not.all(ieee_is_finite([pidnc,dmc,lamdacmin,lamdacmax]))) &\n"
        "     error stop 'PR87 nonfinite cloud coefficient identity'\n"
        "   if (pidnc/=523.59881591796875.or.dmc/=3.0.or. &\n"
        "       lamdacmin/=12000.0.or.lamdacmax/=500000.0) &\n"
        "     error stop 'PR87 grouped/native cloud coefficient identity mismatch'\n"
        "   pr67_trace_this_call = .not. pr67_trace_complete\n",
    )
    anchor = (
        "         call volume_number_to_specific(nci(i,k,1), dry_density(i,k), number_value, number_valid)\n"
        "         if (.not. number_valid) error stop 'KDM6 invalid NC number basis output'\n"
    )
    insertion = (
        "         call pr87_number_public_store(qci(i,k,1),nci(i,k,1),dry_density(i,k), &\n"
        "              pidnc,dmc,lamdacmin,lamdacmax,pr87_rain_q_public,pr87_rain_n_public, &\n"
        "              number_valid,pr87_rain_store_dq,pr87_rain_store_dn,pr87_rain_store_adjustment)\n"
        "         if (.not.number_valid) then\n"
        "           write(*,*) 'PR87_CLOUD_PUBLIC_STORE_REJECT',itimestep,j,i,k, &\n"
        "                qci(i,k,1),nci(i,k,1),dry_density(i,k)\n"
        "           flush(6)\n"
        "           error stop 'PR87 invalid continuous or unrepresentable cloud public pair'\n"
        "         endif\n"
        "         pr87_rain_roundtrip_dn=DBLE(pr87_rain_n_public*dry_density(i,k))-DBLE(nci(i,k,1))\n"
        "         if (pr87_rain_store_adjustment/=0.or.pr87_rain_n_public/=number_value) then\n"
        "           write(pr87_rain_store_unit,'(a,5i10,1p,10es25.16)',iostat=pr87_rain_store_ios) &\n"
        "                'PR87_CLOUD_PUBLIC_STORE',itimestep,j,i,k,pr87_rain_store_adjustment, &\n"
        "                DBLE(qci(i,k,1)),DBLE(nci(i,k,1)),DBLE(number_value), &\n"
        "                DBLE(pr87_rain_q_public),DBLE(pr87_rain_n_public), &\n"
        "                DBLE(dry_density(i,k)),DBLE(delz(i,k,j)),pr87_rain_store_dq, &\n"
        "                pr87_rain_store_dn,pr87_rain_roundtrip_dn\n"
        "           if (pr87_rain_store_ios/=0) error stop 'PR87 cloud public-store ledger write failed'\n"
        "         endif\n"
        "         qc(i,k,j)=pr87_rain_q_public\n"
        "         number_value=pr87_rain_n_public\n"
    )
    return _replace(source, anchor, anchor + insertion)
