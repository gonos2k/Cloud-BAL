
/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_activation_path_20261110/runtime/native_build/variants/CONTROL/wrf.exe:     file format elf64-x86-64


Disassembly of section .text:

00000000013feaf0 <solve_em_+0x40a60>:
 13feaf0:	43 30 4c 8d 4b       	xor    %cl,0x4b(%r13,%r9,4)
 13feaf5:	34 48                	xor    $0x48,%al
 13feaf7:	8d 83 94 00 00 00    	lea    0x94(%rbx),%eax
 13feafd:	50                   	push   %rax
 13feafe:	48 8d 83 a4 00 00 00 	lea    0xa4(%rbx),%rax
 13feb05:	50                   	push   %rax
 13feb06:	48 8d 83 9c 05 00 00 	lea    0x59c(%rbx),%rax
 13feb0d:	50                   	push   %rax
 13feb0e:	48 8d 83 98 05 00 00 	lea    0x598(%rbx),%rax
 13feb15:	50                   	push   %rax
 13feb16:	48 8d 83 94 05 00 00 	lea    0x594(%rbx),%rax
 13feb1d:	50                   	push   %rax
 13feb1e:	48 8d 83 90 05 00 00 	lea    0x590(%rbx),%rax
 13feb25:	50                   	push   %rax
 13feb26:	48 8d 43 44          	lea    0x44(%rbx),%rax
 13feb2a:	50                   	push   %rax
 13feb2b:	48 8d 43 1c          	lea    0x1c(%rbx),%rax
 13feb2f:	50                   	push   %rax
 13feb30:	48 8d 43 3c          	lea    0x3c(%rbx),%rax
 13feb34:	50                   	push   %rax
 13feb35:	48 8d 43 18          	lea    0x18(%rbx),%rax
 13feb39:	50                   	push   %rax
 13feb3a:	48 8d 43 38          	lea    0x38(%rbx),%rax
 13feb3e:	50                   	push   %rax
 13feb3f:	48 8d 43 14          	lea    0x14(%rbx),%rax
 13feb43:	50                   	push   %rax
 13feb44:	48 8d 43 40          	lea    0x40(%rbx),%rax
 13feb48:	50                   	push   %rax
 13feb49:	48 8d 43 48          	lea    0x48(%rbx),%rax
 13feb4d:	50                   	push   %rax
 13feb4e:	48 8d 43 2c          	lea    0x2c(%rbx),%rax
 13feb52:	50                   	push   %rax
 13feb53:	e8 f8 a9 cc 00       	call   20c9550 <module_microphysics_zero_out_mp_microphysics_zero_outa_>
 13feb58:	48 81 c4 80 00 00 00 	add    $0x80,%rsp
 13feb5f:	83 bb 88 02 00 00 00 	cmpl   $0x0,0x288(%rbx)
 13feb66:	0f 8e a7 01 00 00    	jle    13fed13 <solve_em_+0x40c83>
 13feb6c:	48 83 ec 08          	sub    $0x8,%rsp
