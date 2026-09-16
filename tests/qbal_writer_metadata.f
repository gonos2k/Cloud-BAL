c     Synthetic metadata only; the writer and NetCDF backend are real.
      subroutine get_config(istatus)
      implicit none
      integer istatus,flag
      common /prt/ flag
      include 'lapsparms.cmn'
      include 'grid_fname.cmn'
      grid_fnam_common='nest7grid'
      nk_laps=4
      NX_L_CMN=6
      NY_L_CMN=6
      vertical_grid='PRESSURE'
      flag=1
      istatus=1
      end

      subroutine get_directory(ext,directory,length)
      implicit none
      character*(*) ext,directory
      integer length
      select case(trim(ext))
      case('lw3')
        directory='out/lw3/'
      case('cdl')
        directory='cdl/'
      case('static')
        directory='static/'
      case default
        stop 'unexpected writer metadata directory'
      end select
      length=len_trim(directory)
      end

      subroutine get_pres_1d(i4time,nk,pres,istatus)
      implicit none
      integer i4time,nk,istatus
      real pres(nk)
      if(nk.ne.4) stop 'unexpected writer pressure count'
      pres=(/100000.,90000.,80000.,70000./)
      istatus=1
      end
