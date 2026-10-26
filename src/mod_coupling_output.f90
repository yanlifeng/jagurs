! Coupling/output policy only: no changes to the scientific time integrator.
#include "real.h"
module mod_coupling_output
   implicit none
   private
   integer, parameter :: max_extra_steps = 16
   integer :: extra_output_count = 2
   integer :: extra_output_steps(max_extra_steps) = &
      [3599, 3601, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
   public :: coupling_output_initialize, coupling_extra_output_due
#if defined(MPI) && defined(ONEFILE) && !defined(NCDIO) && !defined(PIXELOUT) && !defined(DIROUT)
   public :: coupling_write_raw_fields
#endif
contains
   subroutine coupling_output_initialize(rank, filename)
#ifdef MPI
      use mpi
#ifdef MULTI
      use mod_multi, only : MPI_MEMBER_WORLD
#endif
#endif
      integer, intent(in) :: rank
      character(len=*), optional, intent(in) :: filename
      character(len=512) :: path
      integer :: unit, ios, status, i, j
#ifdef MPI
      integer :: ierr
#endif
      logical :: exists
      namelist /coupling_output/ extra_output_count, extra_output_steps

      ! Missing file reproduces fddf609 exactly. New cases should specify
      ! their own steps (or count=0); these legacy defaults are not physics.
      extra_output_count = 2
      extra_output_steps = 0
      extra_output_steps(1:2) = [3599, 3601]
      path = 'coupling_output.nml'
      if(present(filename)) path = filename
      status = 0
      if(rank == 0) then
         inquire(file=trim(path), exist=exists)
         if(exists) then
            open(newunit=unit, file=trim(path), status='old', action='read', iostat=ios)
            if(ios /= 0) then
               status = 1
            else
               read(unit, nml=coupling_output, iostat=ios)
               if(ios /= 0) status = 1
               close(unit)
            end if
         end if
         if(extra_output_count < 0 .or. extra_output_count > max_extra_steps) status = 1
         if(status == 0) then
            do i = 1, extra_output_count
               if(extra_output_steps(i) < 1) status = 1
               do j = 1, i-1
                  if(extra_output_steps(i) == extra_output_steps(j)) status = 1
               end do
            end do
         end if
         if(status /= 0) write(0,'(a,a)') 'Invalid coupling output configuration: ', trim(path)
      end if
#ifdef MPI
      call MPI_Bcast(status, 1, MPI_INTEGER, 0, __MPICOMM__, ierr)
      if(status /= 0) call MPI_Abort(__MPICOMM__, 91, ierr)
      call MPI_Bcast(extra_output_count, 1, MPI_INTEGER, 0, __MPICOMM__, ierr)
      call MPI_Bcast(extra_output_steps, max_extra_steps, MPI_INTEGER, 0, __MPICOMM__, ierr)
#else
      if(status /= 0) stop 91
#endif
      if(rank == 0) then
         write(6,'(a,i0)') 'COUPLING_OUTPUT extra_count=', extra_output_count
         do i = 1, extra_output_count
            write(6,'(a,i0)') 'COUPLING_OUTPUT extra_step=', extra_output_steps(i)
         end do
      end if
   end subroutine coupling_output_initialize

   logical function coupling_extra_output_due(istep, velgrd) result(due)
      integer, intent(in) :: istep, velgrd
      integer :: k
      due = .false.
      if(velgrd /= 2) return
      do k = 1, extra_output_count
         if(istep == extra_output_steps(k)) then
            due = .true.
            return
         end if
      end do
   end function coupling_extra_output_due

#if defined(MPI) && defined(ONEFILE) && !defined(NCDIO) && !defined(PIXELOUT) && !defined(DIROUT)
   subroutine coupling_write_raw_fields(dg, istep, rank)
      use mod_grid, only : data_grids
      use mod_newsubs, only : maxgrd_write_gmt
      type(data_grids), target, intent(inout) :: dg
      integer, intent(in) :: istep, rank
      integer :: nx, ny
      character(len=512) :: name
      nx = dg%my%nx
      ny = dg%my%ny
      ! Preserve order, native staggering/time levels, signs, output precision
      ! and existing writer. This is not a velocity conversion or regridding.
      write(name,'(a,a,i8.8,a)') trim(dg%my%base_name),'.eta_raw.',istep,'.grd'
      call maxgrd_write_gmt(dg%wave_field%hz(1:nx,1:ny),nx,ny, &
         dg%my%mlon0,dg%my%mlat0,dg%my%dh,name,.false.,dg,rank)
      write(name,'(a,a,i8.8,a)') trim(dg%my%base_name),'.qx_raw.',istep,'.grd'
      call maxgrd_write_gmt(dg%wave_field%fx(1:nx,1:ny),nx,ny, &
         dg%my%mlon0,dg%my%mlat0,dg%my%dh,name,.false.,dg,rank)
      write(name,'(a,a,i8.8,a)') trim(dg%my%base_name),'.qy_south_raw.',istep,'.grd'
      call maxgrd_write_gmt(dg%wave_field%fy(1:nx,1:ny),nx,ny, &
         dg%my%mlon0,dg%my%mlat0,dg%my%dh,name,.false.,dg,rank)
      write(name,'(a,a,i8.8,a)') trim(dg%my%base_name),'.depth_raw.',istep,'.grd'
      call maxgrd_write_gmt(dg%depth_field%dz(1:nx,1:ny),nx,ny, &
         dg%my%mlon0,dg%my%mlat0,dg%my%dh,name,.false.,dg,rank)
   end subroutine coupling_write_raw_fields
#endif
end module mod_coupling_output
