program replay_c4_ice_call
  use, intrinsic :: iso_fortran_env, only: real32, real64, int32
  implicit none
  interface
    subroutine pr85_kdm6_paired_sediment_column(kts,kte,cell_i,lat,substep,dt,mstep, &
         dry_density,delz,mass_rate,second_rate,qstate,second_state,mode,q_active_min, &
         second_active_min,density_min,density_max,approved_q_rate,approved_second_rate, &
         budget_unit,trace,valid,rain_pidn,rain_power,rain_lambda_min,rain_lambda_max)
      import real32, real64
      integer, intent(in) :: kts,kte,cell_i,lat,substep,mstep,budget_unit
      real(real32), intent(in) :: dt,dry_density(kts:kte),delz(kts:kte)
      real(real64), intent(in) :: mass_rate(kts:kte),second_rate(kts:kte)
      real(real32), intent(inout) :: qstate(kts:kte),second_state(kts:kte)
      integer, intent(in) :: mode
      real(real32), intent(in) :: q_active_min,second_active_min,density_min,density_max
      real(real64), intent(out) :: approved_q_rate(kts:kte),approved_second_rate(kts:kte)
      logical, intent(in) :: trace
      logical, intent(out) :: valid
      real(real32), intent(in) :: rain_pidn,rain_power,rain_lambda_min,rain_lambda_max
    end subroutine pr85_kdm6_paired_sediment_column
  end interface
  integer, parameter :: kts=1, kte=39, ncall=1
  integer :: c, k
  real(real32) :: dt, rho(kts:kte), dz(kts:kte), q(kts:kte), n(kts:kte)
  real(real64) :: mr(kts:kte), nr(kts:kte), qout(kts:kte), nout(kts:kte)
  logical :: valid

  ! source call 1: loop=1, substep=1, mstep=1
  rho(1)=transfer(int(z'3F941B09',int32),0.0_real32)
  dz(1)=real(51.816661834716797,real32)
  mr(1)=0_real64
  nr(1)=0_real64
  rho(2)=transfer(int(z'3F934775',int32),0.0_real32)
  dz(2)=real(66.251548767089844,real32)
  mr(2)=0_real64
  nr(2)=0_real64
  rho(3)=transfer(int(z'3F92254C',int32),0.0_real32)
  dz(3)=real(84.363800048828125,real32)
  mr(3)=7.4153276456211188e-05_real64
  nr(3)=1.8538319114052797e-05_real64
  rho(4)=transfer(int(z'3F90B836',int32),0.0_real32)
  dz(4)=real(106.80961608886719,real32)
  mr(4)=5.8861460964772278e-05_real64
  nr(4)=1.4715365241193069e-05_real64
  rho(5)=transfer(int(z'3F8EF09C',int32),0.0_real32)
  dz(5)=real(134.25677490234375,real32)
  mr(5)=4.712205204099242e-05_real64
  nr(5)=1.1780513010248105e-05_real64
  rho(6)=transfer(int(z'3F8CC7DB',int32),0.0_real32)
  dz(6)=real(167.22262573242188,real32)
  mr(6)=3.812613876158128e-05_real64
  nr(6)=9.53153469039532e-06_real64
  rho(7)=transfer(int(z'3F8A4711',int32),0.0_real32)
  dz(7)=real(205.8370361328125,real32)
  mr(7)=3.1260228291763649e-05_real64
  nr(7)=7.8150570729409122e-06_real64
  rho(8)=transfer(int(z'3F874E5C',int32),0.0_real32)
  dz(8)=real(249.97314453125,real32)
  mr(8)=2.6030047932357044e-05_real64
  nr(8)=6.5075119830892611e-06_real64
  rho(9)=transfer(int(z'3F83DF42',int32),0.0_real32)
  dz(9)=real(298.7354736328125,real32)
  mr(9)=2.2072210414063694e-05_real64
  nr(9)=5.5180526035159234e-06_real64
  rho(10)=transfer(int(z'3F7FCAD9',int32),0.0_real32)
  dz(10)=real(350.7264404296875,real32)
  mr(10)=1.9099394761231104e-05_real64
  nr(10)=4.774848690307776e-06_real64
  rho(11)=transfer(int(z'3F76A28D',int32),0.0_real32)
  dz(11)=real(404.0498046875,real32)
  mr(11)=1.6891884652379744e-05_real64
  nr(11)=4.222971163094936e-06_real64
  rho(12)=transfer(int(z'3F6C475A',int32),0.0_real32)
  dz(12)=real(456.435302734375,real32)
  mr(12)=1.5284178028076698e-05_real64
  nr(12)=3.8210445070191744e-06_real64
  rho(13)=transfer(int(z'3F612626',int32),0.0_real32)
  dz(13)=real(504.923828125,real32)
  mr(13)=1.4160597898894301e-05_real64
  nr(13)=3.5401494747235752e-06_real64
  rho(14)=transfer(int(z'3F5578AF',int32),0.0_real32)
  dz(14)=real(549.81689453125,real32)
  mr(14)=1.3362170998829154e-05_real64
  nr(14)=3.3405427497072886e-06_real64
  rho(15)=transfer(int(z'3F496487',int32),0.0_real32)
  dz(15)=real(597.8818359375,real32)
  mr(15)=0.0011403312777069998_real64
  nr(15)=0.00028508281942674996_real64
  rho(16)=transfer(int(z'3F3CC97C',int32),0.0_real32)
  dz(16)=real(649.7578125,real32)
  mr(16)=0.001084306559823091_real64
  nr(16)=0.00027107663995577276_real64
  rho(17)=transfer(int(z'3F2F983F',int32),0.0_real32)
  dz(17)=real(706.22119140625,real32)
  mr(17)=0.0010182795969918023_real64
  nr(17)=0.00025456989924795058_real64
  rho(18)=transfer(int(z'3F22A95D',int32),0.0_real32)
  dz(18)=real(764.2314453125,real32)
  mr(18)=0.00082841797591141778_real64
  nr(18)=0.00020710449397785444_real64
  rho(19)=transfer(int(z'3F1588DC',int32),0.0_real32)
  dz(19)=real(818.8359375,real32)
  mr(19)=0.0017448828567856523_real64
  nr(19)=0.00043622071419641308_real64
  rho(20)=transfer(int(z'3F0938B8',int32),0.0_real32)
  dz(20)=real(802.2734375,real32)
  mr(20)=0.0022600590858315736_real64
  nr(20)=0.00056501477145789341_real64
  rho(21)=transfer(int(z'3EFC1B71',int32),0.0_real32)
  dz(21)=real(785.2265625,real32)
  mr(21)=0.0021474013443527999_real64
  nr(21)=0.00053685033608819998_real64
  rho(22)=transfer(int(z'3EE82EFE',int32),0.0_real32)
  dz(22)=real(766.572265625,real32)
  mr(22)=0.0021830278856999415_real64
  nr(22)=0.00054575697142498537_real64
  rho(23)=transfer(int(z'3ED5A10B',int32),0.0_real32)
  dz(23)=real(749.0830078125,real32)
  mr(23)=0.0016675061814542325_real64
  nr(23)=0.00041687654536355813_real64
  rho(24)=transfer(int(z'3EC469A3',int32),0.0_real32)
  dz(24)=real(732.5361328125,real32)
  mr(24)=0.0011508047894984439_real64
  nr(24)=0.00028770119737461097_real64
  rho(25)=transfer(int(z'3EB4278B',int32),0.0_real32)
  dz(25)=real(718.1025390625,real32)
  mr(25)=0.00073747287356817545_real64
  nr(25)=0.00018436821839204386_real64
  rho(26)=transfer(int(z'3EA523CC',int32),0.0_real32)
  dz(26)=real(704.4765625,real32)
  mr(26)=0.00041422407897816183_real64
  nr(26)=0.00010355601974454046_real64
  rho(27)=transfer(int(z'3E96C948',int32),0.0_real32)
  dz(27)=real(693.8173828125,real32)
  mr(27)=1.789638374454846e-05_real64
  nr(27)=4.4740959361371149e-06_real64
  rho(28)=transfer(int(z'3E89560F',int32),0.0_real32)
  dz(28)=real(685.0302734375,real32)
  mr(28)=1.8992919361459748e-05_real64
  nr(28)=4.7482298403649369e-06_real64
  rho(29)=transfer(int(z'3E7A4635',int32),0.0_real32)
  dz(29)=real(676.076171875,real32)
  mr(29)=2.0160795381643344e-05_real64
  nr(29)=5.0401988454108359e-06_real64
  rho(30)=transfer(int(z'3E638707',int32),0.0_real32)
  dz(30)=real(668.7568359375,real32)
  mr(30)=2.1376004501056791e-05_real64
  nr(30)=5.3440011252641978e-06_real64
  rho(31)=transfer(int(z'3E4EC8DE',int32),0.0_real32)
  dz(31)=real(661.71484375,real32)
  mr(31)=2.2661134110655329e-05_real64
  nr(31)=5.6652835276638323e-06_real64
  rho(32)=transfer(int(z'3E3BF4B1',int32),0.0_real32)
  dz(32)=real(654.6689453125,real32)
  mr(32)=2.4024925285689132e-05_real64
  nr(32)=6.006231321422283e-06_real64
  rho(33)=transfer(int(z'3E2AA32B',int32),0.0_real32)
  dz(33)=real(648.470703125,real32)
  mr(33)=0_real64
  nr(33)=0_real64
  rho(34)=transfer(int(z'3E18CF86',int32),0.0_real32)
  dz(34)=real(651.1796875,real32)
  mr(34)=0_real64
  nr(34)=0_real64
  rho(35)=transfer(int(z'3E08C69C',int32),0.0_real32)
  dz(35)=real(654.234375,real32)
  mr(35)=0_real64
  nr(35)=0_real64
  rho(36)=transfer(int(z'3DF4D9BD',int32),0.0_real32)
  dz(36)=real(657.29296875,real32)
  mr(36)=0_real64
  nr(36)=0_real64
  rho(37)=transfer(int(z'3DDB2F03',int32),0.0_real32)
  dz(37)=real(660.298828125,real32)
  mr(37)=0_real64
  nr(37)=0_real64
  rho(38)=transfer(int(z'3DC43C5F',int32),0.0_real32)
  dz(38)=real(663.22265625,real32)
  mr(38)=0_real64
  nr(38)=0_real64
  rho(39)=transfer(int(z'3DAFB85A',int32),0.0_real32)
  dz(39)=real(666.0390625,real32)
  mr(39)=0_real64
  nr(39)=0_real64
  dt=real(20,real32)
  q(1)=transfer(int(z'00000000',int32),0.0_real32)
  n(1)=transfer(int(z'00000000',int32),0.0_real32)
  q(2)=transfer(int(z'00000000',int32),0.0_real32)
  n(2)=transfer(int(z'00000000',int32),0.0_real32)
  q(3)=transfer(int(z'00001A3A',int32),0.0_real32)
  n(3)=transfer(int(z'0B926270',int32),0.0_real32)
  q(4)=transfer(int(z'00463DAB',int32),0.0_real32)
  n(4)=transfer(int(z'10421D42',int32),0.0_real32)
  q(5)=transfer(int(z'0504A9C9',int32),0.0_real32)
  n(5)=transfer(int(z'15350E79',int32),0.0_real32)
  q(6)=transfer(int(z'0A11AB5D',int32),0.0_real32)
  n(6)=transfer(int(z'1A43CDD4',int32),0.0_real32)
  q(7)=transfer(int(z'0C885CA1',int32),0.0_real32)
  n(7)=transfer(int(z'1CB408BF',int32),0.0_real32)
  q(8)=transfer(int(z'0F336E5E',int32),0.0_real32)
  n(8)=transfer(int(z'1F67CE6E',int32),0.0_real32)
  q(9)=transfer(int(z'121EA71F',int32),0.0_real32)
  n(9)=transfer(int(z'2247C2D7',int32),0.0_real32)
  q(10)=transfer(int(z'1528B8A9',int32),0.0_real32)
  n(10)=transfer(int(z'254E0893',int32),0.0_real32)
  q(11)=transfer(int(z'1849FFA7',int32),0.0_real32)
  n(11)=transfer(int(z'286DD6D1',int32),0.0_real32)
  q(12)=transfer(int(z'1BCE1F5D',int32),0.0_real32)
  n(12)=transfer(int(z'2BE880FF',int32),0.0_real32)
  q(13)=transfer(int(z'1F6B7ABD',int32),0.0_real32)
  n(13)=transfer(int(z'2F7D1B44',int32),0.0_real32)
  q(14)=transfer(int(z'2310E771',int32),0.0_real32)
  n(14)=transfer(int(z'3313AC3D',int32),0.0_real32)
  q(15)=transfer(int(z'26ADA979',int32),0.0_real32)
  n(15)=transfer(int(z'36A6F75C',int32),0.0_real32)
  q(16)=transfer(int(z'31302A19',int32),0.0_real32)
  n(16)=transfer(int(z'411EC531',int32),0.0_real32)
  q(17)=transfer(int(z'3447534A',int32),0.0_real32)
  n(17)=transfer(int(z'442F66CE',int32),0.0_real32)
  q(18)=transfer(int(z'3572734D',int32),0.0_real32)
  n(18)=transfer(int(z'45A2B92F',int32),0.0_real32)
  q(19)=transfer(int(z'356C4EB5',int32),0.0_real32)
  n(19)=transfer(int(z'43E69C49',int32),0.0_real32)
  q(20)=transfer(int(z'3616C0A1',int32),0.0_real32)
  n(20)=transfer(int(z'44167A96',int32),0.0_real32)
  q(21)=transfer(int(z'36FF2DC1',int32),0.0_real32)
  n(21)=transfer(int(z'4525783B',int32),0.0_real32)
  q(22)=transfer(int(z'385EA1B4',int32),0.0_real32)
  n(22)=transfer(int(z'469A0C8F',int32),0.0_real32)
  q(23)=transfer(int(z'38CF45D7',int32),0.0_real32)
  n(23)=transfer(int(z'47B3E605',int32),0.0_real32)
  q(24)=transfer(int(z'38BB7A5A',int32),0.0_real32)
  n(24)=transfer(int(z'488A10EA',int32),0.0_real32)
  q(25)=transfer(int(z'365525CE',int32),0.0_real32)
  n(25)=transfer(int(z'472552EE',int32),0.0_real32)
  q(26)=transfer(int(z'2D0482C0',int32),0.0_real32)
  n(26)=transfer(int(z'3F207084',int32),0.0_real32)
  q(27)=transfer(int(z'24CAA890',int32),0.0_real32)
  n(27)=transfer(int(z'35BBFA3F',int32),0.0_real32)
  q(28)=transfer(int(z'1CCE195D',int32),0.0_real32)
  n(28)=transfer(int(z'2DE122D8',int32),0.0_real32)
  q(29)=transfer(int(z'14BB5956',int32),0.0_real32)
  n(29)=transfer(int(z'25BA79B7',int32),0.0_real32)
  q(30)=transfer(int(z'0B0A6CD4',int32),0.0_real32)
  n(30)=transfer(int(z'1BFA83B6',int32),0.0_real32)
  q(31)=transfer(int(z'013F7753',int32),0.0_real32)
  n(31)=transfer(int(z'121D7537',int32),0.0_real32)
  q(32)=transfer(int(z'00000023',int32),0.0_real32)
  n(32)=transfer(int(z'084EF5AC',int32),0.0_real32)
  q(33)=transfer(int(z'00000000',int32),0.0_real32)
  n(33)=transfer(int(z'00000000',int32),0.0_real32)
  q(34)=transfer(int(z'00000000',int32),0.0_real32)
  n(34)=transfer(int(z'00000000',int32),0.0_real32)
  q(35)=transfer(int(z'00000000',int32),0.0_real32)
  n(35)=transfer(int(z'00000000',int32),0.0_real32)
  q(36)=transfer(int(z'00000000',int32),0.0_real32)
  n(36)=transfer(int(z'00000000',int32),0.0_real32)
  q(37)=transfer(int(z'00000000',int32),0.0_real32)
  n(37)=transfer(int(z'00000000',int32),0.0_real32)
  q(38)=transfer(int(z'00000000',int32),0.0_real32)
  n(38)=transfer(int(z'00000000',int32),0.0_real32)
  q(39)=transfer(int(z'00000000',int32),0.0_real32)
  n(39)=transfer(int(z'00000000',int32),0.0_real32)
  call pr85_kdm6_paired_sediment_column(kts,kte,230,247,1,dt,1, &
       rho,dz,mr,nr,q,n,1,0.0_real32,0.0_real32,0.0_real32,0.0_real32, &
       qout,nout,0,.false.,valid,0.0_real32,0.0_real32,0.0_real32,0.0_real32)
  write(*,'(a,1x,i0,1x,l1)') 'CALL', 1, valid
  do k=kts,kte
    write(*,'(a,1x,i0,1x,i0,1x,z8.8,1x,z8.8)') 'STATE',1,k, &
         transfer(q(k),0_int32),transfer(n(k),0_int32)
  enddo
end program replay_c4_ice_call
