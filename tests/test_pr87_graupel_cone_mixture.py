from __future__ import annotations

import hashlib
import gzip
from pathlib import Path
import re
import subprocess
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/evidence/pr87_two_step_v42_20261016/module_em_pr85.F.gz"
JOINT_SOURCE = ROOT / "docs/evidence/pr87_two_step_v42_20261016/cloud_bal_joint_transport.f90.gz"
SOLVE_SOURCE = ROOT / "docs/evidence/pr87_two_step_v42_20261016/solve_em.F.gz"
TOOLCHAIN = ROOT / "tests/intel_toolchain.sh"

import sys
sys.path.insert(0, str(ROOT / "tools"))
from pr87_graupel_cone_mixture import (  # noqa: E402
    V42_MODULE_EM_SHA256,
    V42_SOLVE_EM_SHA256,
    extend_graupel_cone_mixture,
    extend_graupel_cone_solve_em,
)


def _routine(source: str, name: str) -> str:
    start = re.search(
        rf"^\s*(?:pure\s+)?(?:logical\s+)?(?:subroutine|function)\s+{name}\s*\(",
        source, re.I | re.M,
    )
    assert start, f"missing {name}"
    end = re.search(
        rf"^\s*end\s+(?:subroutine|function)\s+{name}\s*$",
        source[start.end():], re.I | re.M,
    )
    assert end, f"missing end of {name}"
    return source[start.start():start.end() + end.end()]


def _fixture(source: str) -> str:
    strict = _routine(source, "strict_graupel_pair")
    store = _routine(source, "store_graupel_mixture")
    return f"""module mixture_fixture
  use iso_fortran_env, only: int32,real32,real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
contains
{strict}
{store}
end module mixture_fixture

program test_graupel_mixture
  use iso_fortran_env, only: int32,real32,real64
  use mixture_fixture
  implicit none
  real(real64) :: weights(7),dq,dn
  real(real32) :: qterms(7),nterms(7),stored_q,stored_n,donor_q,donor_n
  real(real64) :: reference_q,reference_n
  logical :: valid
  donor_q=transfer(int(z'398DD8E4',int32),0.0_real32)
  donor_n=transfer(int(z'34A16400',int32),0.0_real32)
  if (.not.strict_graupel_pair(real(donor_q,real64),real(donor_n,real64),100.0_real64,900.0_real64)) &
    error stop 'exact upper-bound donor rejected'
  reference_q=3.456802809170887e-6_real64
  reference_n=3.840892010189874e-9_real64
  if (strict_graupel_pair(reference_q,reference_n,100.0_real64,900.0_real64)) &
    error stop 'printed canonical candidate did not expose boundary roundoff'
  weights=0.0_real64; qterms=0.0_real32; nterms=0.0_real32
  weights(7)=10.0_real64*3.032055185624720e-2_real64/real(donor_q,real64)
  qterms(7)=donor_q; nterms(7)=donor_n
  call store_graupel_mixture(weights,qterms,nterms,87712.70_real32,100.0_real64,900.0_real64, &
       reference_q,reference_n,stored_q,stored_n,dq,dn,valid)
  if (.not.valid) error stop 'valid upper-bound donor mixture rejected'
  if (.not.strict_graupel_pair(real(stored_q,real64),real(stored_n,real64), &
                               100.0_real64,900.0_real64)) error stop 'stored pair is outside strict cone'
  if (.not.ieee_is_finite(dq).or..not.ieee_is_finite(dn)) error stop 'storage residual nonfinite'

  ! Invalid positive-weight donor and negative weight both veto the fallback.
  qterms(7)=nearest(donor_q,1.0_real32)
  call store_graupel_mixture(weights,qterms,nterms,87712.70_real32,100.0_real64,900.0_real64, &
       reference_q,reference_n,stored_q,stored_n,dq,dn,valid)
  if (valid) error stop 'out-of-cone donor accepted'
  qterms(7)=donor_q; weights(7)=-weights(7)
  call store_graupel_mixture(weights,qterms,nterms,87712.70_real32,100.0_real64,900.0_real64, &
       reference_q,reference_n,stored_q,stored_n,dq,dn,valid)
  if (valid) error stop 'negative mixture weight accepted'

  ! Nonzero source is rejected by the transactional caller certificate.
  print '(a)', 'PR87 strict graupel mixture helper PASS'
end program test_graupel_mixture
"""


def _transaction_fixture(source: str, joint_source: str, original_em: str) -> str:
    diffusion = _routine(original_em, "horizontal_diffusion64")
    routines = "\n".join(
        _routine(source, name)
        for name in (
            "try_graupel_mixture_trial",
            "probe_failed_graupel_pair",
            "certify_graupel_storage",
            "graupel_transport_mixture",
            "add_graupel_diffusion_mixture",
            "graupel_diffusion_point",
            "air_tendency",
            "donor_values",
            "strict_graupel_pair",
            "store_graupel_mixture",
        )
    )
    return f"""{joint_source}
module diffusion_reference
  use iso_fortran_env, only: real32,real64,real128
contains
{diffusion}
end module diffusion_reference

module mixture_host
  use iso_fortran_env, only: int32,int64,real32,real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  use diffusion_reference, only: horizontal_diffusion64
  use cloud_bal_joint_transport, only: joint_qnb_update, joint_moment_store
  implicit none
  integer,parameter :: ims=0,ime=3,kms=0,kme=1,jms=0,jme=2
  integer,parameter :: cells=2
  integer :: itimestep=1,rk=2
  integer :: il=1,ih=2,jl=1,jh=1,kl=1,kh=1
  integer :: qindex(4)=[1,2,3,4],nindex(4)=[1,2,3,4]
  real(real32) :: qb(cells,4),nb(cells,4),qc(cells,4),nc(cells,4)
  real(real32) :: qs(cells,4),ns(cells,4),qa(cells,4),na(cells,4)
  real(real32) :: oldcarrier(cells),newcarrier(cells),drydensity(cells),dt
  real(real64) :: minmass(4),maxmass(4),theta,rejected_q(4),rejected_n(4)
  real(real64) :: qs64(cells,4),ns64(cells,4),qa64(cells,4),na64(cells,4)
  real(real64) :: number_bounds(cells,2,4),storage_delta_q(4),storage_delta_n(4)
  integer :: storage_adjustments(4)
  real(real32) :: q1(0:3,0:1,0:2,8),n1(0:3,0:1,0:2,8)
  real(real32) :: ru(0:3,0:1,0:2),rv(0:3,0:1,0:2),ww(0:3,0:1,0:2)
  real(real32) :: msftx(0:3,0:2),msfty(0:3,0:2),rdnw(0:1)
  real(real32) :: c1(0:1),c2(0:1),rdx=1.0_real32,rdy=1.0_real32
  real(real32) :: mut_diff(0:3,0:2),xkmhd_diff(0:3,0:1,0:2)
  real(real32) :: msfux_diff(0:3,0:2),msfuy_diff(0:3,0:2)
  real(real32) :: msfvx_inv_diff(0:3,0:2),msfvy_diff(0:3,0:2)
  logical :: feasible
  logical :: failed_pairs(4)=.FALSE.
  logical :: source_first_pair(2)=.FALSE.
  real(real64) :: donor_q(0:3,0:1,0:2,2),donor_n(0:3,0:1,0:2,2)
contains
{routines}
  subroutine reset_case()
    real(real32) :: donor_q,donor_n
    real(real64) :: rates(2)
    qb=0.0_real32; nb=0.0_real32; qc=0.0_real32; nc=0.0_real32
    qs=0.0_real32; ns=0.0_real32; qa=0.0_real32; na=0.0_real32
    qs64=0.0_real64; ns64=0.0_real64; qa64=0.0_real64; na64=0.0_real64
    number_bounds=0.0_real64; storage_delta_q=0.0_real64; storage_delta_n=0.0_real64
    storage_adjustments=0; q1=0.0_real32; n1=0.0_real32
    ru=0.0_real32; rv=0.0_real32; ww=0.0_real32
    msftx=1.0_real32; msfty=1.0_real32; rdnw=-1.0_real32
    c1=1.0_real32; c2=0.0_real32; rdx=1.0_real32; rdy=1.0_real32
    mut_diff=1.0_real32; xkmhd_diff=1.0_real32
    msfux_diff=1.0_real32; msfuy_diff=1.0_real32
    msfvx_inv_diff=1.0_real32; msfvy_diff=1.0_real32
    oldcarrier=[86592.0_real32,87712.70_real32]
    newcarrier=[87712.70_real32,86592.0_real32]
    drydensity=1.0_real32; dt=0.148487553_real32
    minmass=[1.0e-20_real64,1.0e-20_real64,1.0e-20_real64,100.0_real64]
    maxmass=[1.0e-10_real64,1.0e-10_real64,1.0e-10_real64,900.0_real64]
    donor_q=transfer(int(z'398DD8E4',int32),0.0_real32)
    donor_n=transfer(int(z'34A16400',int32),0.0_real32)
    qb(2,4)=donor_q; nb(2,4)=donor_n
    q1(2,1,1,4)=donor_q; n1(2,1,1,4)=donor_n
    ru(2,1,1)=-112.07_real32
    rates=air_tendency(q1(:,:,:,qindex(4)),n1(:,:,:,nindex(4)),1,1,1,4)
    qa64(1,4)=rates(1); na64(1,4)=rates(2)
    qa(1,4)=real(qa64(1,4),real32); na(1,4)=real(na64(1,4),real32)
    theta=0.0_real64; rejected_q=0.0_real64; rejected_n=0.0_real64; feasible=.false.
  end subroutine reset_case
end module mixture_host

program test_graupel_transaction
  use iso_fortran_env, only: int64,real32,real64,real128
  use, intrinsic :: ieee_arithmetic, only: ieee_value,ieee_quiet_nan
  use mixture_host
  implicit none
  real(real32) :: old_q(cells,4),old_n(cells,4)
  real(real64) :: old_dq(4),old_dn(4)
  real(real64) :: canonical_q,canonical_n,expected_delta_q,expected_delta_n
  real(real64) :: weights(7)
  real(real32) :: q_terms(7),n_terms(7)
  real(real64) :: point_q,point_n,full_increment(0:3,0:1,0:2)
  real(real128) :: face_q(4),face_n(4)
  real(real64) :: source_q,source_n
  real(real64) :: rates(2)
  real(real64) :: old_theta
  logical :: point_valid
  logical :: mixture_valid
  logical :: old_feasible
  integer :: old_adjust(4)
  call reset_case()
  call try_graupel_mixture_trial()
  if (.not.feasible) error stop 'valid boundary mixture transaction rejected'
  if (theta/=1.0_real64) error stop 'accepted mixture did not retain theta one'
  if (.not.strict_graupel_pair(real(qc(1,4),real64),real(nc(1,4),real64),100.0_real64,900.0_real64)) &
    error stop 'accepted receiver pair is outside strict cone'
  canonical_q=(real(oldcarrier(1),real64)*real(qb(1,4),real64)+ &
               real(dt,real64)*(qs64(1,4)+qa64(1,4)))/real(newcarrier(1),real64)
  canonical_n=(real(oldcarrier(1),real64)*real(nb(1,4),real64)+ &
               real(dt,real64)*(ns64(1,4)+na64(1,4)))/real(newcarrier(1),real64)
  expected_delta_q=real(newcarrier(1),real64)*(real(qc(1,4),real64)-canonical_q)
  expected_delta_n=real(newcarrier(1),real64)*(real(nc(1,4),real64)-canonical_n)
  if (storage_adjustments(4)/=1) error stop 'mixture storage adjustment count mismatch'
  if (storage_delta_q(4)/=expected_delta_q.or.storage_delta_n(4)/=expected_delta_n) &
    error stop 'mixture storage residual does not match stored-minus-canonical pair'

  ! The helper owns finite base-weight validation before its sign comparison.
  call reset_case()
  oldcarrier(1)=ieee_value(0.0_real32,ieee_quiet_nan)
  call graupel_transport_mixture(1,1,1,1,weights,q_terms,n_terms,mixture_valid)
  if (mixture_valid) error stop 'NaN mixture base weight accepted'

  ! The point replay must match the unmodified full source helper bit for bit.
  call reset_case()
  rdx=0.8_real32; rdy=1.2_real32; c1=1.3_real32; c2=0.2_real32
  mut_diff=reshape([1.0_real32,1.1_real32,0.9_real32,1.2_real32, &
                    1.0_real32,1.1_real32,0.9_real32,1.2_real32, &
                    1.0_real32,1.1_real32,0.9_real32,1.2_real32],shape(mut_diff))
  xkmhd_diff=reshape([0.8_real32,0.9_real32,1.0_real32,1.1_real32, &
                      1.2_real32,1.3_real32,1.4_real32,1.5_real32, &
                      1.6_real32,1.7_real32,1.8_real32,1.9_real32, &
                      2.0_real32,2.1_real32,2.2_real32,2.3_real32, &
                      2.4_real32,2.5_real32,2.6_real32,2.7_real32, &
                      2.8_real32,2.9_real32,3.0_real32,3.1_real32],shape(xkmhd_diff))
  msftx=1.1_real32; msfty=0.9_real32
  msfux_diff=1.2_real32; msfuy_diff=0.8_real32
  msfvx_inv_diff=0.7_real32; msfvy_diff=1.3_real32
  call graupel_diffusion_point(q1(:,:,:,4),1,1,1,point_q,face_q,point_valid)
  if (.not.point_valid) error stop 'nonunit QG point diffusion rejected'
  call graupel_diffusion_point(n1(:,:,:,4),1,1,1,point_n,face_n,point_valid)
  if (.not.point_valid) error stop 'nonunit BG point diffusion rejected'
  if (any(face_q/=face_n)) error stop 'QG and BG diffusion face coefficients differ'
  call horizontal_diffusion64(q1(:,:,:,4),mut_diff,c1,c2,msfux_diff,msfuy_diff, &
       msfvx_inv_diff,msfvy_diff,msftx,msfty,xkmhd_diff,rdx,rdy, &
       0,3,0,1,0,2,1,1,1,1,1,1,full_increment)
  if (transfer(point_q,0_int64)/=transfer(full_increment(1,1,1),0_int64)) &
    error stop 'point QG replay differs from original full helper'
  call horizontal_diffusion64(n1(:,:,:,4),mut_diff,c1,c2,msfux_diff,msfuy_diff, &
       msfvx_inv_diff,msfvy_diff,msftx,msfty,xkmhd_diff,rdx,rdy, &
       0,3,0,1,0,2,1,1,1,1,1,1,full_increment)
  if (transfer(point_n,0_int64)/=transfer(full_increment(1,1,1),0_int64)) &
    error stop 'point BG replay differs from original full helper'

  ! A nonzero source is eligible only when its total R64 value is the replayed operator.
  call reset_case()
  rates=air_tendency(q1(:,:,:,qindex(4)),n1(:,:,:,nindex(4)),2,1,1,4)
  qa64(2,4)=rates(1); na64(2,4)=rates(2)
  qa(2,4)=real(qa64(2,4),real32); na(2,4)=real(na64(2,4),real32)
  xkmhd_diff=1.0_real32
  call graupel_diffusion_point(q1(:,:,:,4),1,1,1,source_q,face_q,point_valid)
  if (.not.point_valid) error stop 'QG source replay setup failed'
  call graupel_diffusion_point(n1(:,:,:,4),1,1,1,source_n,face_n,point_valid)
  if (.not.point_valid) error stop 'BG source replay setup failed'
  qs64(1,4)=source_q; ns64(1,4)=source_n
  call graupel_transport_mixture(1,1,1,1,weights,q_terms,n_terms,mixture_valid)
  if (.not.mixture_valid) error stop 'nonzero source transport setup failed'
  call add_graupel_diffusion_mixture(1,1,1,1,weights,q_terms,n_terms,mixture_valid)
  if (.not.mixture_valid) error stop 'exact nonzero source mixture rejected'
  if (weights(2)<=0.0_real64) error stop 'diffusion face weight was not combined'
  call try_graupel_mixture_trial()
  if (.not.feasible) error stop 'exact diffusion source certificate rejected'

  ! A later invalid source must roll back an earlier cell's local repair.
  call reset_case()
  qs64(2,4)=1.0e-8_real64
  qs(2,4)=real(qs64(2,4),real32)
  old_q=qc; old_n=nc; old_dq=storage_delta_q; old_dn=storage_delta_n; old_adjust=storage_adjustments
  call try_graupel_mixture_trial()
  if (feasible) error stop 'nonzero-source cone violation accepted'
  if (any(qc/=old_q).or.any(nc/=old_n)) error stop 'failed transaction changed stored moments'
  if (any(storage_delta_q/=old_dq).or.any(storage_delta_n/=old_dn).or. &
      any(storage_adjustments/=old_adjust)) error stop 'failed transaction changed storage ledger'

  ! An infeasible retry cannot change stored moments or expose a theta.
  call reset_case()
  qa64(1,1)=1.0_real64; qa(1,1)=1.0_real32; na64(1,1)=0.0_real64; na(1,1)=0.0_real32
  failed_pairs=[.true.,.false.,.false.,.true.]
  old_q=qc; old_n=nc
  call try_graupel_mixture_trial()
  if (feasible) error stop 'infeasible theta transaction accepted'
  if (theta/=0.0_real64) error stop 'failed transaction left nonzero theta'
  if (any(qc/=old_q).or.any(nc/=old_n)) error stop 'infeasible trial changed stored moments'
  old_dq=storage_delta_q; old_dn=storage_delta_n; old_adjust=storage_adjustments
  old_feasible=feasible; old_theta=theta
  call probe_failed_graupel_pair()
  if (feasible .neqv. old_feasible) error stop 'G probe changed feasibility state'
  if (theta/=old_theta) error stop 'G probe changed theta'
  if (.NOT.failed_pairs(1).OR.failed_pairs(4)) error stop 'G probe cleared wrong failed-pair flags'
  if (any(qc/=old_q).or.any(nc/=old_n)) error stop 'G probe committed candidate fields'
  if (any(storage_delta_q/=old_dq).or.any(storage_delta_n/=old_dn).or. &
      any(storage_adjustments/=old_adjust)) error stop 'G probe changed transaction ledger'
  call try_graupel_mixture_trial()
  if (feasible) error stop 'G-only probe bypassed failed cloud pair'
  if (any(qc/=old_q).or.any(nc/=old_n)) error stop 'cloud rejection changed candidate fields'
  if (any(storage_delta_q/=old_dq).or.any(storage_delta_n/=old_dn).or. &
      any(storage_adjustments/=old_adjust)) error stop 'cloud rejection changed ledger'

  ! A failed G source certificate leaves the G failure set and commits nothing.
  call reset_case()
  failed_pairs=[.true.,.false.,.false.,.true.]
  qs64(2,4)=1.0e-8_real64
  old_q=qc; old_n=nc; old_dq=storage_delta_q; old_dn=storage_delta_n; old_adjust=storage_adjustments
  old_feasible=feasible; old_theta=theta
  call probe_failed_graupel_pair()
  if (feasible .neqv. old_feasible) error stop 'rejected G probe changed feasibility state'
  if (theta/=old_theta) error stop 'rejected G probe changed theta'
  if (.not.failed_pairs(1).or..not.failed_pairs(4)) error stop 'invalid G probe changed failure flags'
  if (any(qc/=old_q).or.any(nc/=old_n)) error stop 'invalid G probe committed fields'
  if (any(storage_delta_q/=old_dq).or.any(storage_delta_n/=old_dn).or. &
      any(storage_adjustments/=old_adjust)) error stop 'invalid G probe changed ledger'

  ! QIB is bulk volume, so the strict-mass pair accepts a positive value
  ! whose generic rho_dry*QIB number-conversion product is below half minsub.
  call reset_case()
  oldcarrier=1.0_real32; newcarrier=1.0_real32; drydensity=0.25_real32
  qb=0.0_real32; nb=0.0_real32
  qa64=0.0_real64; na64=0.0_real64; qa=0.0_real32; na=0.0_real32
  nb(:,4)=nearest(0.0_real32,1.0_real32)
  qb(:,4)=900.0_real32*nb(:,4)
  qc=qb; nc=nb; minmass(4)=100.0_real64; maxmass(4)=900.0_real64
  call try_graupel_mixture_trial()
  if (.not.feasible) error stop 'direct all-pair store rejected bulk graupel control'
  if (.not.strict_graupel_pair(real(qc(1,4),real64),real(nc(1,4),real64), &
                               minmass(4),maxmass(4))) error stop 'tiny bulk graupel pair lost strict cone'
  print '(a)', 'PR87 graupel transaction PASS'
end program test_graupel_transaction
"""


def test_pinned_transform_preserves_strict_primary_kernel_and_requires_witness():
    original = gzip.decompress(SOURCE.read_bytes()).decode()
    assert hashlib.sha256(original.encode()).hexdigest() == V42_MODULE_EM_SHA256
    transformed = extend_graupel_cone_mixture(original)
    assert "strict_mass_pairs=[.FALSE.,.FALSE.,.FALSE.,.TRUE.]" in transformed
    assert "strict_mass_pairs=[.FALSE.,.FALSE.,.FALSE.,.FALSE.]" not in transformed
    assert "CALL joint_qnb_update" not in transformed[transformed.index("SUBROUTINE try_graupel_mixture_trial"):]
    assert "CALL joint_moment_store" in transformed[transformed.index("SUBROUTINE certify_graupel_storage"):]
    assert "CALL add_graupel_diffusion_mixture" in transformed
    assert "CALL probe_failed_graupel_pair()" in transformed
    assert "IF (graupel_only) first_pair=4" in transformed
    assert "TRANSFER(qs64(c,4),0_int64)/=TRANSFER(qdiff,0_int64)" in transformed
    assert "theta=1.0_real64" in transformed
    assert "n_terms(7)=q1" not in transformed
    assert "n_terms(7)=n1(i,k-1,j,nindex(4))" in transformed
    assert "storage_delta_q(4)=storage_delta_q(4)+delta_q" not in transformed
    with pytest.raises(ValueError, match="unexpected pinned module_em source hash"):
        extend_graupel_cone_mixture(original + "\n")


def test_pinned_solve_em_passes_exact_diffusion_references():
    original = gzip.decompress(SOLVE_SOURCE.read_bytes()).decode()
    assert hashlib.sha256(original.encode()).hexdigest() == V42_SOLVE_EM_SHA256
    transformed = extend_graupel_cone_solve_em(original)
    assert transformed.count("pr87_rk1_muts,grid%xkhh,grid%msfux,grid%msfuy,grid%msfvx_inv,grid%msfvy)") == 1
    assert "grid%muts,grid%xkhh,grid%msfux,grid%msfuy,grid%msfvx_inv,grid%msfvy)" not in transformed
    assert transformed.count("CALL rk_update_joint_moments(") == 1
    assert transformed.index("pr87_rk1_muts = grid%muts(ims:ime,jms:jme)") < transformed.index("moist_scalar_advance:")
    assert "pr87_diffusion_capture_rk /= 1" in transformed
    assert "pr87_diffusion_capture_step /= grid%itimestep" in transformed
    with pytest.raises(ValueError, match="unexpected pinned solve_em source hash"):
        extend_graupel_cone_solve_em(original + "\n")


@pytest.mark.parametrize("optimization", ["O0", "O2"])
def test_rk1_geometry_snapshot_survives_live_mutation_and_rejects_stale_identity(optimization: str):
    original = gzip.decompress(SOLVE_SOURCE.read_bytes()).decode()
    transformed = extend_graupel_cone_solve_em(original)
    capture_start = transformed.index("       IF (config_flags%mp_physics == 37 .AND. rk_step == 1) THEN\n         IF (ALLOCATED(pr87_rk1_muts))")
    capture_end = transformed.index("       moist_scalar_advance:", capture_start)
    capture = transformed[capture_start:capture_end]
    guard_start = transformed.index("IF (.NOT.pr87_diffusion_geometry_captured")
    guard_end = transformed.index("         END IF", guard_start) + len("         END IF")
    guard = transformed[guard_start:guard_end]
    fixture = f"""module rk_geometry_fixture
  implicit none
  type :: config_t
    integer :: mp_physics
  end type config_t
  type :: grid_t
    integer :: itimestep
    real, allocatable :: muts(:,:)
  end type grid_t
contains
  subroutine wrf_error_fatal(message)
    character(len=*), intent(in) :: message
    print *, trim(message)
    error stop 9
  end subroutine wrf_error_fatal
  subroutine check_geometry(mode)
    character(len=*), intent(in) :: mode
    type(config_t) :: config_flags
    type(grid_t) :: grid
    integer :: rk_step, ims, ime, jms, jme
    integer :: pr87_diffusion_capture_step, pr87_diffusion_capture_rk
    logical :: pr87_diffusion_geometry_captured
    real, allocatable :: pr87_rk1_muts(:,:)
    ims=1; ime=2; jms=1; jme=2
    config_flags%mp_physics=37
    grid%itimestep=41
    allocate(grid%muts(ims:ime,jms:jme))
    grid%muts=reshape([1.0,2.0,3.0,4.0],shape(grid%muts))
    rk_step=1
{capture}    grid%muts=99.0
    if (mode == 'stale') grid%itimestep=42
    if (mode == 'wrong_producer') pr87_diffusion_capture_rk=2
{guard}
    if (any(pr87_rk1_muts /= reshape([1.0,2.0,3.0,4.0],shape(pr87_rk1_muts)))) then
      error stop 'frozen RK1 geometry changed with live MUTS'
    endif
    print *, 'PR87 RK1 geometry snapshot PASS'
  end subroutine check_geometry
end module rk_geometry_fixture
program test_rk_geometry
  use rk_geometry_fixture
  implicit none
  character(len=32) :: mode
  call get_command_argument(1,mode)
  call check_geometry(trim(mode))
end program test_rk_geometry
"""
    with tempfile.TemporaryDirectory(prefix=f"pr87_geometry_{optimization}_", dir="/var/tmp") as tmp:
        scratch = Path(tmp)
        source_path = scratch / "test_rk_geometry.F90"
        executable = scratch / "test_rk_geometry.exe"
        source_path.write_text(fixture)
        script = f"""
set -euo pipefail
source '{TOOLCHAIN}'
if [[ '{optimization}' == O0 ]]; then flags=("${{CLOUD_BAL_FREE_FLAGS[@]}}"); else flags=("${{CLOUD_BAL_REPRO_FLAGS[@]}}"); fi
"$CLOUD_BAL_FC" -free "${{flags[@]}}" '{source_path}' -o '{executable}'
'{executable}' valid
if '{executable}' stale > stale.log 2>&1; then exit 91; fi
grep -q 'PR87 missing RK1 diffusion geometry' stale.log
if '{executable}' wrong_producer > producer.log 2>&1; then exit 92; fi
grep -q 'PR87 missing RK1 diffusion geometry' producer.log
"""
        result = subprocess.run(["bash", "-lc", script], cwd=scratch, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        assert result.returncode == 0, result.stdout
        assert "PR87 RK1 geometry snapshot PASS" in result.stdout


@pytest.mark.parametrize("optimization", ["O0", "O2"])
def test_boundary_mixture_store_with_pinned_intel(optimization: str):
    transformed = extend_graupel_cone_mixture(gzip.decompress(SOURCE.read_bytes()).decode())
    fixture = _fixture(transformed)
    with tempfile.TemporaryDirectory(prefix=f"pr87_mixture_{optimization}_", dir="/var/tmp") as tmp:
        scratch = Path(tmp)
        source_path = scratch / "test_graupel_mixture.F90"
        executable = scratch / "test_graupel_mixture.exe"
        source_path.write_text(fixture)
        script = f"""
set -euo pipefail
source '{TOOLCHAIN}'
if [[ '{optimization}' == O0 ]]; then flags=("${{CLOUD_BAL_FREE_FLAGS[@]}}"); else flags=("${{CLOUD_BAL_REPRO_FLAGS[@]}}"); fi
"$CLOUD_BAL_FC" -free "${{flags[@]}}" '{source_path}' -o '{executable}'
'{executable}'
"""
        result = subprocess.run(["bash", "-lc", script], cwd=scratch, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        assert result.returncode == 0, result.stdout
        assert "PR87 strict graupel mixture helper PASS" in result.stdout


@pytest.mark.parametrize("optimization", ["O0", "O2"])
def test_source_certified_transaction_with_pinned_intel(optimization: str):
    transformed = extend_graupel_cone_mixture(gzip.decompress(SOURCE.read_bytes()).decode())
    joint_source = gzip.decompress(JOINT_SOURCE.read_bytes()).decode()
    original_em = gzip.decompress(SOURCE.read_bytes()).decode()
    fixture = _transaction_fixture(transformed, joint_source, original_em)
    with tempfile.TemporaryDirectory(prefix=f"pr87_transaction_{optimization}_", dir="/var/tmp") as tmp:
        scratch = Path(tmp)
        source_path = scratch / "test_graupel_transaction.F90"
        executable = scratch / "test_graupel_transaction.exe"
        source_path.write_text(fixture)
        script = f"""
set -euo pipefail
source '{TOOLCHAIN}'
if [[ '{optimization}' == O0 ]]; then flags=("${{CLOUD_BAL_FREE_FLAGS[@]}}"); else flags=("${{CLOUD_BAL_REPRO_FLAGS[@]}}"); fi
"$CLOUD_BAL_FC" -free "${{flags[@]}}" '{source_path}' -o '{executable}'
'{executable}'
"""
        result = subprocess.run(["bash", "-lc", script], cwd=scratch, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        assert result.returncode == 0, result.stdout
        assert "PR87 graupel transaction PASS" in result.stdout
        assert re.search(
            r"PR87_GRAUPEL_TINY_BG_ROLE\s+1\s+2\s+2\s+1\s+1\s+1\s+"
            r"36A0000000000000\s+000000003E800000",
            result.stdout,
        ), result.stdout
        assert re.search(r"PR87_GRAUPEL_MIXTURE\s+1\s+2\s+1\s+1\s+1\s+1\s+",result.stdout), result.stdout
