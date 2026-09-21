! Geometry-only replay. No inferred wind, area metric, or boundary authority.
program diagnose_qbal_pressure_flux
  use iso_fortran_env, only: real64
  use qbal_pressure_flux, only: pressure_interfaces
  use cloud_bal_grid_geometry, only: pressure_face_segment, partition_pressure_face
  implicit none
  real(real64), allocatable :: p(:),ps(:,:),left(:),right(:)
  type(pressure_face_segment), allocatable :: segments(:)
  real(real64) :: low,high,width,error,coverage_error,unmatched,top_low,top_high
  integer :: nx,ny,nz,i,j,k,ncell,nsegment,nface,nshallow,unit
  logical :: ok
  character(1024) :: path
  call get_command_argument(1,path)
  open(newunit=unit,file=trim(path),access='stream',form='unformatted',status='old')
  read(unit) nx,ny,nz
  if (min(nx,ny,nz)<2.or.max(nx,ny,nz)>10000) error stop 'invalid dimensions'
  allocate(p(nz),ps(nx,ny))
  read(unit) p,ps
  close(unit)
  low=huge(low); high=0; error=0; coverage_error=0; unmatched=0
  top_low=huge(top_low); top_high=0
  ncell=0; nsegment=0; nface=0; nshallow=0
  do j=1,ny; do i=1,nx
    call pressure_interfaces(p,ps(i,j),left,ok)
    if (.not.ok) error stop 'invalid column'
    ncell=ncell+size(left)-1
    if (size(left)==2) nshallow=nshallow+1
    do k=1,size(left)-1
      width=left(k)-left(k+1)
      low=min(low,width); high=max(high,width)
    end do
    top_low=min(top_low,left(size(left)-1)-left(size(left)))
    top_high=max(top_high,left(size(left)-1)-left(size(left)))
    error=max(error,abs(sum(left(:size(left)-1)-left(2:))-(ps(i,j)-p(nz))))
    if (i<nx) call shared_column(ps(i+1,j))
    if (j<ny) call shared_column(ps(i,j+1))
  end do; end do
  print '(a,i0)', 'columns=',nx*ny
  print '(a,i0)', 'cells=',ncell
  print '(a,i0)', 'single_layer_columns=',nshallow
  print '(a,i0)', 'horizontal_column_faces=',nface
  print '(a,i0)', 'shared_pressure_segments=',nsegment
  print '(a,es24.16)', 'minimum_cell_dp_pa=',low
  print '(a,es24.16)', 'maximum_cell_dp_pa=',high
  print '(a,es24.16)', 'minimum_top_dp_pa=',top_low
  print '(a,es24.16)', 'maximum_top_dp_pa=',top_high
  print '(a,es24.16)', 'maximum_column_span_error_pa=',error
  print '(a,es24.16)', 'maximum_shared_span_error_pa=',coverage_error
  print '(a,es24.16)', 'maximum_unmatched_side_span_pa=',unmatched
contains
  subroutine shared_column(neighbor_ps)
    real(real64), intent(in) :: neighbor_ps
    call pressure_interfaces(p,neighbor_ps,right,ok)
    if (.not.ok) error stop 'invalid neighbor'
    call partition_pressure_face(left,right,segments,ok)
    if (.not.ok) error stop 'invalid shared face'
    nface=nface+1; nsegment=nsegment+size(segments)
    coverage_error=max(coverage_error,abs(sum(segments%pressure_thickness)- &
                       (min(left(1),right(1))-p(nz))))
    ! This exposed side interval is NOT automatically a wall or a flux-free
    ! terrain face. A reconstruction of the sloping physical surface is open.
    unmatched=max(unmatched,abs(left(1)-right(1)))
  end subroutine
end program
