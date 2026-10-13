# PR84: 같은 13 UTC 모멘트 후보와 실제 첫 RK 상태

PR83의 모멘트 생성 거부는 그대로 보존한다. PR84는 같은 단계의 OFF/COUPLED를 비교하고, 실제 소비 소스에 근거한 별도 v2 정책으로 두 Q/N/B 파일을 생성했다. 두 파일은 WRF 초기화까지 전달됐지만, 첫 KDM6 호출은 NC 변환에서 거부됐다. **초기화의 유효성과 완료된 과정 갱신의 유효성은 별개이며, 과학적 초기장 수용은 OPEN이다.**

## 1. 고얼음량 원인과 표현 선택

실제 `real` 출력의 `REAL32(1/REAL32(AL+ALB))`를 사용한 비교에서 전체 비호환 2,326셀, 내부 2,305셀이 모두 OFF와 COUPLED에 공통이다. 후보에서 새로 생긴 위반과 해소된 위반은 모두 0이며, 같은 carrier로 가중한 초과량 차이도 0이다. 원본 LAPS 제품에도 큰 ICE content가 있다. source→metgrid→real의 서로 다른 격자에서 최대값이 크다는 사실을 동일 입자의 추적으로 확대하지 않는다. [원인 지도](evidence/pr84_ice_cap_pair_20261013.md), [종 의미 추적](PR84_ICE_SPECIES_SOURCE_20261013.md).

LAPS ICE는 별도의 cloud-ice mass content이며 SNO/PIC가 따로 존재한다. 얼음 질량을 임의로 눈이나 싸락눈으로 옮길 근거는 찾지 못했다. 실제 KDM6의 `NI≤1e6`는 입구의 numerical guard이고, 뒤의 PSD 재구성은 같은 질량에서 NI를 다시 계산해 이를 넘을 수 있다. 따라서 이를 지속적인 native 상태 상한으로 취급하지 않는다. PR83 v1의 고정 cap 교집합 거부는 그 정책 범위에서 유효하다. [소비 소스 계약](PR84_NATIVE_ICE_CONTRACT_20261013.md).

v2는 입구 guard를 dry density 계산 뒤로 옮기고, 기존 PSD 하한을 표현하는 최소 REAL32 QNICE만 허용하도록 연결한다. 낮은 얼음량에서는 기존 `1e6` guard를 유지한다. 질량·T/q·Phi·바람·종 분류·PSD 상수·physics·FP 정책은 변경하지 않았다. 큰 얼음량의 관측 PSD를 알아냈다는 뜻은 아니다.

## 2. 실제 후보 생성과 WRF 초기화

같은 [정책](PR84_NATIVE_MOMENT_POLICY_20261013.json)을 두 입력에 적용했다. 전체 수평 격자와 외곽 donor 링을 포함하며, 보존된 80개 Q/N/B/CCN boundary 배열은 모두 0인 원래 forcing으로 유지했다. 실제 구름 유입의 관측 검증은 별도다. [지원영역·경계 계약](PR84_FIRST_CONSUMPTION_SUPPORT_20261013.md).

| 항목 | OFF | COUPLED |
|---|---:|---:|
| QNCLOUD 구성 | 973,831셀 | 973,831셀 |
| QNICE 구성 | 249,167셀 | 249,167셀 |
| QNRAIN 구성 | 207,316셀 | 207,316셀 |
| QIB 구성 | 1,022셀 | 1,010셀 |
| source-compatible high-ice minimum 사용 | 2,326셀 | 2,326셀 |
| 미구성 양의 질량 | 0셀 | 0셀 |
| 최대 derived 내부 NI guard | 1,529,145.875 m⁻³ | 1,529,145.875 m⁻³ |
| 원본 입력·비모멘트 변수 변경 | 없음 | 없음 |
| 초기화 후 QNCLOUD/QNICE/QNRAIN/QIB | 보존 | 보존 |
| 첫 모델 종료코드 | 128 | 128 |
| 첫 KDM6 완료 | 실패 | 실패 |

저장 파일 SHA-256은 OFF `23a948dfbea1cd9f1d69d9aad30531218a4c93ac6a82159e73e5505e39440200`, COUPLED `d10c2b987856586c9b8105a69eaeda03951f85f29be3ec4e7118d4f79b478c2d`이다. 최종 initializer의 policy-hash guard와 diagnostic 수정 뒤에도 새 사본으로 이 두 해시를 재현했다. 모델은 앞선 initializer가 만든 동일 바이트를 사용했으며, 최종 코드로 모델을 재실행했다고 주장하지 않는다.

동일 실행파일·physics·FP 정책·namelist·boundary, 1 rank/1 thread, 13:00 UTC에서 20초를 요청했다. 기존 WPS–metgrid–real 전달을 다시 만들지 않고 같은 real 산출물을 사용했다. `real.exe` v4.6 계열과 WRF v4.8 partial-host 조합의 기존 제한은 유지한다. 초기화 후 W/P/Phi 변화는 기존 경로의 실제 동작이며, 후보와 OFF에 같은 전달 연산자를 적용한 차이를 별도로 저장했다. 주변 QNCCN의 초기화는 구름 입자수 보존과 구분한다.

## 3. 다음 병목은 완료된 RK 상태

두 원래 모델 실행은 `KDM6 invalid NC number basis input`으로 중단됐다. 종료 후 전체 첫-call pre 캡처를 기존 `pr82_native_conversion_scale.py`로 읽었다. 아래는 같은 2,533,440 활성 셀의 **공개 wrapper 입력**, stage 1/timestep 1이다. 물리 post 상태나 특정 fatal 좌표의 관측으로 바꾸지 않는다.

| pre 상태 진단 | OFF | COUPLED |
|---|---:|---:|
| 양의 NC가 REAL32 density 곱 뒤 0으로 반올림 | 4,025셀 | 4,011셀 |
| 음수 NC | 0셀 | 0셀 |
| 음수 QC | 21,859셀 | 21,852셀 |
| QC>0, NC=0 | 9셀 | 9셀 |
| QC=0, NC>0 | 136,782셀 | 136,770셀 |
| QI>0, NI=0 | 594셀 | 589셀 |
| QI=0, NI>0 | 154,756셀 | 154,761셀 |

가장 음수인 QC는 두 arm 모두 `-5.213007057136565e-7 kg/kg dry`다. QC orphan NC 최댓값은 `1.2454168796539307 kg⁻¹`, QI orphan NI 최댓값은 `9.449166297912598 kg⁻¹`이다. 셀 수만으로 물질·입자수 총량이나 과학적 영향을 판정하지 않는다. rain과 graupel의 pre 질량–모멘트 부재 관계에서는 해당 위반을 찾지 못했다.

독립 source-expression scan의 첫 반올림 후보는 [i,j,k]=[2,2,21], NC=`0x00000001`, QC=0, dry density=`0x3EF895E0`이다. 정확한 양의 곱이 최소 양수의 절반보다 작아 gradual-underflow에서도 0으로 반올림된다. 이 좌표는 실행 코드의 loop 순서로 예측한 것이며 별도 on-call 관측과 구분한다. 과거 12 UTC 피연산자를 이번 13 UTC fatal 값으로 재사용하지 않았다.

같은 OFF 입력·namelist·실행파일을 detached 사본에서 1 rank/1 thread로 debugger 재현했다. 실제 helper 입력 NC=`0x00000001`, dry density=`0x3EF895E0`, 반환값=`0x00000000`, valid=`FALSE`를 관측했다. MXCSR=`0x1932`에서 FTZ·DAZ는 해제돼 있다. 실행파일의 실제 NC 호출 뒤 false 분기가 `KDM6 invalid NC number basis input` 메시지로 연결됨도 확인했다. Debugger는 helper 반환점에서 종료했으며 좌표는 관측하지 못했다. 이는 실제 피연산자·반환값의 근거이고, 위 loop-order 좌표 예측이나 완료된 모델 단계와 구분한다. [원본 transcript·script·해시](evidence/pr84_nc_operand_debugger_20261013.json).

현재 선택된 Shinhong PBL과 별도 moist/scalar RK 경로는 조사할 대상이다. 현재 외부 소스의 정적 경로와 실행된 객체의 동일성, 실제 donor/flux/physics tendency 귀속을 완성하지 않았으므로 위반 전부를 PBL로 단정하지 않는다. 입구에서 N을 재생성하거나 floor/clamp로 첫 셀만 지우는 처리는 하지 않았다. **첫 호출 수지 및 10·30·60분 과학적 비교는 NOT_RUN이다.**

## 4. 검증과 범위

실제 `kdm6init` accessor와 별도 parameter dump로 REAL32 PIDNI·lambda·shape 값을 확인했다. pinned Intel ifx 2026.0, 새 `/var/tmp`에서 정확히 추출한 guard의 O0/O2 probe를 통과했다. 373개 archive member의 순서와 중복 member를 유지하고 KDM6 member 한 개만 교체했다. 활성 실행파일의 원래 builder 바이트 미보존과 전체 transitive link closure의 제한은 [build 문서](PR84_NATIVE_ICE_CONTRACT_20261013.md)에 명시한다.

전체 canonical 시험은 고정 snapshot과 최종 변경의 focused 검사를 구분해 [검증 receipt](evidence/pr84_validation_20261013.json)에 기록한다. 첫 metadata 없는 snapshot의 중단을 PASS로 재분류하지 않는다. 최종 팀 검토와 source/receipt SHA, compact 원본 로그는 [통합 receipt](evidence/pr84_integration_20261013.json)에 연결한다. KG 갱신은 따로 날짜를 부여한 KLAPS50/Cloud-BAL 구조 snapshot이며 실행·관측·과학 검증을 대신하지 않는다.

이번 종료 산출물은 **공통 고얼음량 원인 지도, 같은 정책의 저장된 OFF/COUPLED Q/N/B, 초기화 전달 및 실제 첫-RK 실패 캡처**다. `PASS_SCOPED`인 초기 구성과 `REJECTED`인 모델 소비를 동시에 유지한다. 다음 과정 수정은 donor·승인 과정량·carrier·갱신 시각을 연결한 공동 Q/N/B 갱신에서 수행해야 한다.
