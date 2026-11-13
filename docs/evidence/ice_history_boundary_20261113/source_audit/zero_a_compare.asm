
/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_activation_path_20261110/runtime/native_build/variants/CONTROL/wrf.exe:     file format elf64-x86-64


Disassembly of section .text:

00000000020c95d5 <module_microphysics_zero_out_mp_microphysics_zero_outa_+0x85>:
 20c95d5:	48 8b 5d 58          	mov    0x58(%rbp),%rbx
 20c95d9:	48 89 4d 98          	mov    %rcx,-0x68(%rbp)
 20c95dd:	4c 8d 2c 8d 00 00 00 	lea    0x0(,%rcx,4),%r13
 20c95e4:	00 
 20c95e5:	41 8b 86 64 0e 00 00 	mov    0xe64(%r14),%eax
 20c95ec:	83 f8 01             	cmp    $0x1,%eax
 20c95ef:	0f 84 78 03 00 00    	je     20c996d <module_microphysics_zero_out_mp_microphysics_zero_outa_+0x41d>
 20c95f5:	83 f8 02             	cmp    $0x2,%eax
 20c95f8:	0f 85 bf 0c 00 00    	jne    20ca2bd <module_microphysics_zero_out_mp_microphysics_zero_outa_+0xd6d>
 20c95fe:	bf 1c 60 4c 03       	mov    $0x34c601c,%edi
 20c9603:	be 60 99 65 03       	mov    $0x3659960,%esi
 20c9608:	ba 33 00 00 00       	mov    $0x33,%edx
 20c960d:	31 c0                	xor    %eax,%eax
 20c960f:	e8 2c ef 8f fe       	call   9c8540 <wrf_debug_>
 20c9614:	83 7d 88 02          	cmpl   $0x2,-0x78(%rbp)
 20c9618:	0f 8c 9f 0c 00 00    	jl     20ca2bd <module_microphysics_zero_out_mp_microphysics_zero_outa_+0xd6d>
 20c961e:	48                   	rex.W
 20c961f:	c7                   	.byte 0xc7
