
/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_activation_path_20261110/runtime/native_build/variants/CONTROL/wrf.exe:     file format elf64-x86-64


Disassembly of section .text:

00000000020c985d <module_microphysics_zero_out_mp_microphysics_zero_outa_+0x30d>:
 20c985d:	43 0f 2f 44 32 e4    	comiss -0x1c(%r10,%r14,1),%xmm0
 20c9863:	77 3b                	ja     20c98a0 <module_microphysics_zero_out_mp_microphysics_zero_outa_+0x350>
 20c9865:	43 0f 2f 44 32 e8    	comiss -0x18(%r10,%r14,1),%xmm0
 20c986b:	77 44                	ja     20c98b1 <module_microphysics_zero_out_mp_microphysics_zero_outa_+0x361>
 20c986d:	43 0f 2f 44 32 ec    	comiss -0x14(%r10,%r14,1),%xmm0
 20c9873:	77 4d                	ja     20c98c2 <module_microphysics_zero_out_mp_microphysics_zero_outa_+0x372>
 20c9875:	43 0f 2f 44 32 f0    	comiss -0x10(%r10,%r14,1),%xmm0
 20c987b:	77 56                	ja     20c98d3 <module_microphysics_zero_out_mp_microphysics_zero_outa_+0x383>
 20c987d:	43 0f 2f 44 32 f4    	comiss -0xc(%r10,%r14,1),%xmm0
 20c9883:	77 5f                	ja     20c98e4 <module_microphysics_zero_out_mp_microphysics_zero_outa_+0x394>
 20c9885:	43 0f 2f 44 32 f8    	comiss -0x8(%r10,%r14,1),%xmm0
 20c988b:	77 68                	ja     20c98f5 <module_microphysics_zero_out_mp_microphysics_zero_outa_+0x3a5>
 20c988d:	43 0f 2f 44 32 fc    	comiss -0x4(%r10,%r14,1),%xmm0
 20c9893:	77 71                	ja     20c9906 <module_microphysics_zero_out_mp_microphysics_zero_outa_+0x3b6>
 20c9895:	43 0f 2f 04 32       	comiss (%r10,%r14,1),%xmm0
 20c989a:	76 b4                	jbe    20c9850 <module_microphysics_zero_out_mp_microphysics_zero_outa_+0x300>
 20c989c:	eb 7c                	jmp    20c991a <module_microphysics_zero_out_mp_microphysics_zero_outa_+0x3ca>
 20c989e:	66 90                	xchg   %ax,%ax
 20c98a0:	43 c7 44 32 e4 00 00 	movl   $0x0,-0x1c(%r10,%r14,1)
 20c98a7:	00 00 
 20c98a9:	43 0f 2f 44 32 e8    	comiss -0x18(%r10,%r14,1),%xmm0
 20c98af:	76 bc                	jbe    20c986d <module_microphysics_zero_out_mp_microphysics_zero_outa_+0x31d>
 20c98b1:	43 c7 44 32 e8 00 00 	movl   $0x0,-0x18(%r10,%r14,1)
 20c98b8:	00 00 
