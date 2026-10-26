program test_coupling_schedule
   use mod_coupling_output
   implicit none
   character(len=512) :: file, mode
   call get_command_argument(1, file)
   call get_command_argument(2, mode)
   call coupling_output_initialize(0, trim(file))
   if(trim(mode) == 'legacy') then
      if(.not.coupling_extra_output_due(3599,2)) stop 1
      if(.not.coupling_extra_output_due(3601,2)) stop 2
      if(coupling_extra_output_due(3600,2)) stop 3
      if(coupling_extra_output_due(3599,1)) stop 4
   else if(trim(mode) == 'off') then
      if(coupling_extra_output_due(3599,2)) stop 5
      if(coupling_extra_output_due(3601,2)) stop 6
   else if(trim(mode) == 'custom') then
      if(.not.coupling_extra_output_due(9,2)) stop 7
      if(coupling_extra_output_due(3599,2)) stop 8
   else
      stop 9
   end if
   print *, 'PASS coupling schedule'
end program test_coupling_schedule
