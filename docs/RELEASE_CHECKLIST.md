# Cloud-BAL 단일 승인 체크리스트

기준일: 2026-09-02

이 문서가 현재 승인 판단의 한 장짜리 기준이다. 상세 수식과 과거 검토
기록은 `PIPELINE_SIMPLIFICATION_PLAN.md`에 남기되, 실행 권한은 여기서만
판정한다.

## 단일 계약

```text
원본 입력(불변)
  -> SHADOW 진단 후보
  -> 독립 재계산 validator
  -> ACCEPTED 또는 REJECTED
```

- `OFF`: 후보 계산도 하지 않고 원본을 그대로 반환한다.
- `SHADOW`: 후보를 별도 산출하지만 운영장은 항상 원본이다.
- `ACTIVE`: 이 소스 트리에는 존재하지 않는다.
- stage 실패, degraded 또는 gate 실패는 fallback 물리를 선택하지 않고 후보를
  거부한다.

상태 표시는 `DONE`, `ENGINEERING`, `BLOCKED`만 사용한다. `DONE`은 명시된
범위만 닫혔다는 뜻이며 과학·운영 승인을 뜻하지 않는다.

## P0 체크리스트

| 계약 | 상태 | 현재 증거 또는 남은 조건 |
|---|---|---|
| ANAL/MODL 원본 격리, final bigfile 입력 금지 | DONE | 고정 hash inventory와 isolation gate; final/downstream path를 입력 단계에서 거부 |
| 값·valid·quality·source·시간·차원·단위의 단일 field 계약 | DONE | `cloud_bal_state`; 모든 physics가 공통 `cell_is_usable` 사용 |
| pressure mass와 dry-air mass 분리 | DONE | 연속 연산자는 `pressure_mass_measure`, 수상체 질량은 `dry_air_mass_measure` 사용 |
| 수직축 `k=1 bottom`, 압력 단조감소 | DONE | ingest에서 한 방향만 허용; 역방향을 physics 내부에서 추측하지 않음 |
| 결측/비유한 pressure, omega, wind, dBZ, phase의 산술 진입 차단 | DONE | canonical validation과 trajectory fail-closed 시험 |
| 레이더 강수의 상대 낙하 flux 재구성과 interface ledger | ENGINEERING | interface별 경계/지형/관측차단 폐합은 구현; source 제거를 포함한 전역 질량수송이나 root-to-sink 보존을 뜻하지 않음 |
| 강수 trajectory 입력 계약 | DONE | 공개 kernel 입구에서 config·shape·finite·범위·dp·수직순서·domain·phase/species 일관성을 한 번 검사하고 별도 work 배열의 출력/ledger도 재검사한 뒤에만 반환 배열에 commit; 현재 index-space 수송은 균일 dx/dy만 허용하고 비균일 격자는 물리좌표 수송 구현 전 fail-closed |
| radar no-echo의 수송 경계 의미 | BLOCKED | 실자료 adapter는 no-echo와 raw missing을 구분하지만 trajectory의 차단 경계로 아직 전달하지 않음; 관측 부재인지 명시적 무강수인지 정책 고정 전 과학 승격 금지 |
| 총수분·잠열 동시 보존 | ENGINEERING | canonical bounded adjustment 시험 통과; legacy LAPSPREP 전체 transaction 연결은 남음 |
| focused source의 dormant radar evaporation/cloud bogus-w OFF | DONE | Cloud-BAL 복사본은 상수-false guard, literal `.false.` cloud call, `w_3d=0` 초기화와 시험으로 잠금 |
| 현업 linked derived-cloud의 radar evaporation/cloud bogus-w OFF | BLOCKED | 현재 namelist는 evaporation 0이지만 원본 source·binary에 호출이 남고 cloud bogus-w는 활성; `audit_legacy_deriv_safety.py`가 source/binary/ifx provenance를 모두 통과할 때까지 BLOCKED |
| canonical cloud type-only 경험적 `w` 금지 | DONE | 운형은 layer/regime support만 제공; 별도 동역학 driver가 없으면 평균 target은 0 |
| production derived-cloud 경험적 `w` 제거 | BLOCKED | 실제 호출망은 아직 `l_flag_bogus_w=.true.`인 legacy 경로이며 canonical adapter로 교체되지 않음 |
| 동역학 target 권한과 일반 usable 값 분리 | DONE | dynamic bit, 독립 바람 근거, clean quality를 모두 만족해야 solver seed가 됨 |
| 동역학 target의 `R_w`·자료 나이·driver provenance | BLOCKED | 현재 실제자료에는 이 계약이 없어 dynamic authority를 0으로 강제; ACTIVE 전에 field contract 확장 필요 |
| S-band loading pseudo-target의 바람 권한 | BLOCKED | 현재 echo는 phase·fall-speed가 불확실하므로 hydrometeor/ledger 진단만 수행하고 balance support는 0 |
| 하나의 `S`, `D`, `G`, `L=-DSG`를 solve/update/residual에 공용 | DONE | 단위시험과 독립 validator가 같은 게시 배열에서 operator identity를 재계산; exact-head 수치는 immutable generation에만 기록 |
| 요청 `omega_target`과 실제 적용률 분리 | DONE | balance stage는 target 값·mask·quality·source를 bitwise 보존하고 trust-region 적용률은 result에만 기록 |
| target-induced increment만 projection | DONE | compact 영역에서 배경 전장을 재균형하지 않음; target 없는 component는 bitwise no-op |
| support 경계의 배경 flux와 zero-normal increment 분리 | ENGINEERING | uniform-flow compact-support 단위시험 통과; 실제 지형 kinematic lower boundary는 남음 |
| A-grid checkerboard null mode 제어 | ENGINEERING | 수직 omega target의 exact/near-alternating mode는 solve 전 거부; 수평 collocated A-grid parity gauge와 terrain/native-face 문제는 남아 ACTIVE 승격 금지 |
| 비균일 격자의 물리 거리 localization | DONE | `cloud_bal_grid_geometry`의 누적 인접 center 거리와 overflow-safe 탐색반경을 canonical/legacy localization에 공유; 중간 100 km cell 및 거대 유한반경 반례 통과 |
| solver 실패·비수렴 시 원본 rollback | DONE | candidate와 operational state 모두 원본 복사본; 실패 수치만 stage result에 보존 |
| focused legacy QBAL의 background omega 필수성 | DONE | U/V/T/HT/SH와 함께 OM status도 필수이고 solver가 사용하는 분석 surface-pressure domain의 모든 above-ground cell에서 OM coverage를 검사; 누락 OM을 0으로 대체하여 balance를 계속하지 않음 |
| storm motion 및 trajectory frame | BLOCKED | 현재 real SHADOW는 좌표계 미확정 input-native U/V와 zero-translation 가정을 명시; 바람 좌표계·이동벡터 검증 전 과학 승격 금지 |
| physical continuity·geostrophic·증분·방향 gate | DONE | 최종 real32 배열에서 독립 재계산하고 Fortran failure bitset과 정확히 일치시킴 |
| 결과 파일의 단일 세대 transaction | ENGINEERING | real runner를 staging→재검증→manifest→atomic generation으로 연결; 제품별 NetCDF/WPS 재읽기와 full legacy writer 연결은 남음 |
| 증거 세대의 self-contained build/derived provenance | BLOCKED | 현재 build/runtime 절대경로와 figure/audit sidecar가 외부에 남음; 운영 증거 승격 전에 세대 내부 receipt 필요 |
| exact-head·입력 content snapshot | BLOCKED | 현재 trusted single-user check/hash/check runner이며 adversarial path swap을 막는 immutable source/input snapshot은 미구현 |
| publication directory race 방어 | BLOCKED | 현재 lock+atomic rename은 협력 프로세스 crash consistency용; hostile directory replacement를 막는 dirfd/openat 계층은 미구현 |
| focused Intel ifx 2026 단일 toolchain | DONE | strict/reproduction 스크립트에 GNU/ifort fallback 없음 |
| 현업 KLAPS 전체 ifx link | BLOCKED | 3개 현업 binary는 legacy ifort 서명, canonical symbol 0, NetCDF/HDF5 runtime closure 미해결; `audit_intel_integration.py` 결과 38 blocker |
| canonical pipeline이 전체 KLAPS 호출망의 단일 구현 | BLOCKED | qbalpe/derived-cloud/LAPSPREP adapter와 전체 링크가 아직 없음 |
| 원래 QBAL 직접 입력 closure | BLOCKED | 4시각 upstream replay preflight과 41개 독립 read-only copy, VRT 4/4는 완료; 실제 producer는 실행하지 않아 LT1/LQ3/LCO/LSX가 `NOT_PRODUCED` |
| 현업 원본-vs-SHADOW 비교 계약 | ENGINEERING | role·hash·time/grid/unit/stagger/wind-coordinate·정확한 SHADOW profile·단일 Times·내장 source/authority·pair 유일성 검증과 고정 scale 배열 생성기 구현; 현재 완전한 candidate가 없어 `NOT_READY`, 운영 전후 그림 생성 금지 |
| 비교 candidate의 완전한 generation attestation | BLOCKED | 현재 비교기는 local manifest+marker 결속까지만 검사; TRANSACTION context, 전체 입력/build receipt, 검증된 generation membership을 함께 확인하기 전 독립 운영 증거로 승격 금지 |
| 실제 cold-start 0--6 h 과학 검증 | BLOCKED | 준비된 분석자료 SHADOW 진단은 예보 spin-up 검증을 대신하지 않음 |
| ACTIVE 운영 게시 | BLOCKED | ACTIVE API 자체가 없고 모든 과학·통합 gate가 닫히지 않음 |

## 실제자료 전수 증거

고정 manifest는 2026-08-16 12, 13, 14, 15 UTC 네 시각을 포함한다.
`tests/run_real_shadow_cases.sh`는 clean exact HEAD에서 네 시각을 하나도
건너뛰지 않고 하나의 immutable generation으로 게시한다. commit마다 결과가
달라질 수 있으므로 수치를 이 문서에 복사하지 않는다. 승인 증거는 검증된
`current` generation의 `RUN_SUMMARY.json`, 사례별 JSON, `MANIFEST.json`,
`COMMITTED`만 사용한다.

| 항목 | 판정 방법 |
|---|---|
| 준비된 FUA/FSF/pre-QBAL LW3/VRZ/VRT | pinned manifest와 시작·종료 hash가 모두 일치해야 함 |
| radar-only SHADOW artifact | 네 파일 모두 numerical validator에서 `VALID`이고, generation manifest가 각 파일·JSON hash와 exact HEAD를 함께 검증해야 함 |
| 수상체 공학 판정 | 사례별 `hydrometeor_engineering_decision`을 그대로 보고; rejection을 성공으로 바꾸지 않음 |
| 동역학 판정 | 현재 v3 실제자료는 반드시 `NOT_AUTHORIZED`, target/support/wind 변경 0이어야 함 |
| 운영장 변경 | 모든 사례에서 반드시 0 cell |
| 국지성·증분·cellwise target response | 사례별 독립 JSON의 재계산 값을 사용 |
| background/proposal 진단 그림 | 네 시각 각각 동일 규칙의 수평·연직 그림 2개; 현업 원본/개선 비교로 부르지 않음 |

Standalone `numerical VALID`는 파일 내부 수치·연산자·gate 재계산이
일치한다는 뜻일 뿐 provenance가 아니다. Immutable generation 검증까지
통과한 뒤에만 artifact evidence라 부른다. 후보가
과학적으로 좋다는 뜻이 아니다. 실패한 stage는 상태 후보를 게시하지 않고
원인과 수치만 stage result에 남기며, 운영장은 원본 그대로여야 한다.

## 레이더 시선속도 판정

각 시각의 준비된 `v01..v04,v06..v11` 10개 격자를 모두 읽었다.

- usable velocity는 존재한다.
- usable Nyquist 값은 4시각 모두 0 cell이다.
- radar-grid 파일 자체에 검증 가능한 S-band wavelength provenance가 없다.
- LW3 U/V가 grid-relative인지 earth-relative인지 생성계보가 확정되지 않았다.
- 현재 자료만으로 air motion과 reflectivity-weighted terminal fall motion을
  유일하게 분리할 수 없다.
- velocity level은 pressure 값으로 diagnostic level에 대응시켜야 하며, index
  순서만으로 결합한 과거 수치는 사용하지 않는다.

따라서 현재 audit는 valid/echo overlap 수만 게시하고 U/V projection RMS는
`null`로 둔다. 시선속도는 `DIAGNOSTIC_ONLY`이며 balance update, calibration,
held-out acceptance 어느 것에도 권한을 주지 않는다. wind 좌표계, dealiased 표현,
Nyquist/uncertainty, beam geometry, radar wavelength registry와 hydrometeor fall
speed observation operator가 한 계약으로 준비된 뒤 다시 검토한다.

## 운영 승격 전에 반드시 남은 시험

1. 원본 QBAL 입력 LT1/LQ3/LCO/LSX를 원래 upstream 단계에서 재생성한다.
2. 전체 KLAPS를 동일 ifx/NetCDF/HDF5 ABI로 clean link한다.
3. 모든 준비 사례에 대해 legacy와 candidate를 같은 직접 입력에서 독립 실행한다.
4. 청천, 층운/안개, 층상성 비·눈, 혼합상, 대류, 산악·경계, radar 공백을
   포함한 고정 manifest를 사용한다.
5. 0--6 h cold-start에서 강수, 표면기압, 고주파 발산, 중력파/음파,
   수분·엔탈피 budget을 평가한다.
6. calibration 사례와 held-out 사례를 분리하고 threshold를 고정한다.
7. clean exact-head manifest, 필수 CI와 보호 브랜치를 적용한다.
8. production의 cloud bogus-w 및 30--60 km legacy qbal 경로를 canonical
   transaction으로 한 번에 교체한다.
9. radar no-echo 정책, 비균일 격자 physical-coordinate trajectory, 전역
   water/enthalpy source-to-sink ledger를 하나의 column-physics 계약으로 닫는다.
10. comparison candidate가 검증된 generation의 선언 제품임을 transaction,
    input/build receipt와 함께 독립 재검증한다.

이 중 하나라도 빠지면 판정은 계속 `SHADOW / PROMOTION_BLOCKED`다.
