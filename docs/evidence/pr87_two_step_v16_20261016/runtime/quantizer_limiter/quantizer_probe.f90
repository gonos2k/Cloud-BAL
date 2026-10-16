program pr87_v16_quantizer_probe
  use iso_fortran_env, only: real32, real64
  use cloud_bal_joint_transport, only: joint_moment_store, joint_moment_is_valid
  implicit none
  integer, parameter :: count=8
  integer :: cell_i(count),cell_j(count),cell_k(count),idx,adj
  real(real64), parameter :: pidnr=12566.37109375_real64
  real(real64), parameter :: lambda_min=961.0_real64,lambda_max=35000.0_real64,power=3.0_real64
  real(real64) :: lower,upper,bounds(2),q64,n64,rho64,dt64
  real(real32), parameter :: dt32=20.0_real32/3.0_real32
  real(real32), parameter :: rho(count)=[ &
    0.7696942090988159_real32, &
    0.9019019603729248_real32, &
    0.6172311305999756_real32, &
    0.7218068838119507_real32, &
    0.6695162057876587_real32, &
    0.7217721343040466_real32, &
    0.8224080204963684_real32, &
    0.8705090880393982_real32]
  real(real32), parameter :: source_q(count)=[ &
    1.339063164778054E-004_real32,8.444310515187681E-005_real32,0.000000000000000E+000_real32,6.747764564352110E-005_real32,0.000000000000000E+000_real32,1.186701501865173E-005_real32,9.569449503032956E-006_real32,1.076366424968001E-005_real32]
  real(real32), parameter :: source_n(count)=[ &
    456872.843750000_real32,288110.093750000_real32,0.000000000000000E+000_real32,230225.875000000_real32,0.000000000000000E+000_real32,40488.8789062500_real32,32649.8476562500_real32,36724.3710937500_real32]
  real(real64), parameter :: air_q(count)=[ &
    1.257363102525901E-003_real64,2.629031712629745E-003_real64,6.988890565014895E-004_real64,6.041754582572842E-003_real64,3.564805239261134E-005_real64,8.255371954277062E-005_real64,1.570321059621585E-003_real64,5.498285170449682E-004_real64]
  real(real64), parameter :: air_n(count)=[ &
    4289976.94859837_real64,8969951.04728635_real64,2384528.33535210_real64,20613765.3791803_real64,121627.017782582_real64,281663.710292414_real64,5357753.14426136_real64,1875951.08622873_real64]
  real(real32), parameter :: new_carrier(count)=[ &
    93108.765625_real32,92007.53125_real32,95114.484375_real32,95385.171875_real32,95302.03125_real32,95508.109375_real32,95474.953125_real32,95610.8125_real32]
  real(real64), parameter :: printed_q(count)=[ &
    9.961606919207172E-008_real64,1.966125103182674E-007_real64,4.898581216317689E-008_real64,4.269868479884148E-007_real64,2.493689524076157E-009_real64,6.590765463312722E-009_real64,1.103179713454014E-007_real64,3.908847777574592E-008_real64]
  real(real64), parameter :: printed_n(count)=[ &
    339.878467031616_real64,670.819065535788_real64,167.133904940579_real64,1456.82956428045_real64,8.50817926176281_real64,22.4869269305052_real64,376.392110319100_real64,133.365349358072_real64]
  real(real32) :: q0,n0,qout,nout,q1up,q1dn,q2up,q2dn
  logical :: valid,continuous_valid,ordinary_valid,one_up_valid,one_dn_valid,two_up_valid,two_dn_valid
  cell_i=[58,163,180,198,200,205,213,214]
  cell_j=[193,194,60,72,64,60,135,140]
  cell_k=[16,13,19,17,18,17,15,14]
  lower=pidnr/lambda_max**power
  upper=pidnr/lambda_min**power
  dt64=real(dt32,real64)
  do idx=1,count
    rho64=real(rho(idx),real64)
    bounds=[rho64*lambda_min**power/pidnr,rho64*lambda_max**power/pidnr]
    q64=dt64*(real(source_q(idx),real64)+air_q(idx))/real(new_carrier(idx),real64)
    n64=dt64*(real(source_n(idx),real64)+air_n(idx))/real(new_carrier(idx),real64)
    continuous_valid=q64>0.0_real64.and.n64>0.0_real64.and. &
      q64/n64>=lower.and.q64/n64<=upper.and. &
      n64*rho64>=bounds(1)*q64.and.n64*rho64<=bounds(2)*q64
    call joint_moment_store(q64,n64,rho(idx),lower,upper,.true., &
      qout,nout,adj,valid,allow_normal_q_adjustment=.true., &
      allow_joint_quantum_absence=.true.,volume_number_bounds=bounds)
    q0=real(q64,real32); n0=real(n64,real32)
    ordinary_valid=stored_valid(q0,n0,rho(idx),lower,upper,bounds)
    q1up=nearest(q0,1.0_real32); q1dn=nearest(q0,-1.0_real32)
    q2up=nearest(q1up,1.0_real32); q2dn=nearest(q1dn,-1.0_real32)
    one_up_valid=stored_valid(q1up,n0,rho(idx),lower,upper,bounds)
    one_dn_valid=stored_valid(q1dn,n0,rho(idx),lower,upper,bounds)
    two_up_valid=stored_valid(q2up,n0,rho(idx),lower,upper,bounds)
    two_dn_valid=stored_valid(q2dn,n0,rho(idx),lower,upper,bounds)
    write(*,'(i3,1x,3(i4,1x),l1,1x,l1,1x,i1,1x,5(l1,1x),4(es24.16e3,1x))') &
      idx,cell_i(idx),cell_j(idx),cell_k(idx),continuous_valid,valid,adj,ordinary_valid, &
      one_up_valid,one_dn_valid,two_up_valid,two_dn_valid,q64/printed_q(idx)-1.0_real64, &
      n64/printed_n(idx)-1.0_real64,real(q0,real64),real(n0,real64), &
      real(q2up,real64),real(q2dn,real64)
  end do
contains
  logical function stored_valid(q,n,rho,minratio,maxratio,bnd)
    real(real32),intent(in)::q,n,rho
    real(real64),intent(in)::minratio,maxratio,bnd(2)
    real(real64)::v64,mn,mx
    real(real32)::v32
    v64=real(n,real64)*real(rho,real64)
    mn=bnd(1)*real(q,real64); mx=bnd(2)*real(q,real64)
    v32=real(v64,real32)
    stored_valid=joint_moment_is_valid(q,n,rho,minratio,maxratio).and. &
      v64>=mn.and.v64<=mx.and.real(v32,real64)>=mn.and.real(v32,real64)<=mx
  end function stored_valid
end program pr87_v16_quantizer_probe
