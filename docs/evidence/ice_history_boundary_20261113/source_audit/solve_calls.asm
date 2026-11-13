
/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_activation_path_20261110/runtime/native_build/variants/CONTROL/wrf.exe:     file format elf64-x86-64


Disassembly of section .text:

00000000013fddd0 <solve_em_+0x3fd40>:
 13fddd0:	00 4c 89 fe          	add    %cl,-0x2(%rcx,%rcx,4)
 13fddd4:	48 8b 93 e0 0d 00 00 	mov    0xde0(%rbx),%rdx
 13fdddb:	48 8b 8b e8 0d 00 00 	mov    0xde8(%rbx),%rcx
 13fdde2:	4c 8b 83 28 07 00 00 	mov    0x728(%rbx),%r8
 13fdde9:	4c 8b 8b 90 0b 00 00 	mov    0xb90(%rbx),%r9
 13fddf0:	e8 ab 24 cc 00       	call   20c02a0 <module_microphysics_driver_mp_microphysics_driver_>
 13fddf5:	48 81 c4 20 0c 00 00 	add    $0xc20,%rsp
 13fddfc:	f6 83 a8 0e 00 00 01 	testb  $0x1,0xea8(%rbx)
 13fde03:	74 0f                	je     13fde14 <solve_em_+0x3fd84>
 13fde05:	4c 89 ff             	mov    %r15,%rdi
 13fde08:	48 8b b3 e8 12 00 00 	mov    0x12e8(%rbx),%rsi
 13fde0f:	e8 8c 78 02 02       	call   34256a0 <for_array_copy_out>
 13fde14:	f6 83 e0 0a 00 00 01 	testb  $0x1,0xae0(%rbx)
 13fde1b:	0f                   	.byte 0xf
 13fde1c:	85 6c 45 00          	test   %ebp,0x0(%rbp,%rax,2)
