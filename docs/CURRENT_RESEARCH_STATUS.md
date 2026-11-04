# 현재 연구 상태

## 2026-11-04: 비 입자수 과정 추적과 0.65 mm 대조 — 현재 B1 유지

[최신 보고서](CP02_RAIN_NUMBER_PROCESS_20261104.md)는 PR145 이후 연구 브랜치의 결과다. 현재 B1과 기존 비 입자수 후보를 같은 FIX 계열로 0–3시간 진단했으며 9개 지점·36개 모서리·39층·540단계의 단위 변환, 침강·과정·최종 응결·지상 누적을 연결했다. 두 구성의 전체 +0·+1·+2·+3시간 history 8개가 각각 기존 예보와 같았다. 호출 사이 순변화는 순수 수송으로 해석하지 않는다.

입력 비 질량을 유지하고 공통 질량가중 평균입경만 약 0.862→0.65 mm로 바꾼 단일 대조의 6시간 예보를 완료했다. [전체 144행 점수](evidence/cp02_rain_number_process_20261104/followup/figures/FULLSCORES.md)는 규준실험·현재 B1·기존 후보·조정 후보의 6개 시간과 6개 임계값을 모두 구분한다. 조정 후보는 현재 B1 보호 8/11, 낮은 임계값 회복 2/15, 합계 10/26으로 **NO_QUALIFIED_CANDIDATE**다. 기존 후보의 12/26보다 충족 수가 적으며 두 후보 모두 미채택이다. 후반 낮은 임계값 회복 목표를 달성하지 못했다.

소스 PSD 활성 경계 `>=`와 하한 961을 맞췄고, 공개 입자수 혼합비와 내부 수농도의 DEN 변환을 직접 검증했다. 이 정합성·국지 REAL32 연산 검증은 전체 물·에너지 수지, DEN의 건조·습윤 공기 기준, RN1 상류 규약·독립 사례 검증의 완료를 뜻하지 않는다. C2 T39와 H/A/N 1시간 완료도 별도 미해결이다. 아래는 과거 시점 기록이다.

## 2026-11-04: B1 상태 경계와 비 입자수 후보 — 미채택

[CP02 상태·비 입자수 보고서](CP02_STATE_PATH_AND_RAIN_NUMBER_20261104.md)의 새 실험은 PR144 `ad45471`을 기준으로 한 연구 브랜치의 추가 결과다. 동일 B1 OLD/FIX 0–2시간의 전역 첫 호출 및 8개 지점·32개 모서리·39층의 360단계 진입·반환을 포착했다. 기존 예보의 전체 +0·+1·+2시간 출력은 두 구성 모두 재현됐다. P01 수증기 차이는 두 번째 진입 전에 이미 존재하며, 호출 사이의 순변화를 순수 수송으로 확정하지 않는다.

비 입자수 후보는 감마 입도분포 가정으로 초기 QNRAIN만 채우고 질량·수증기·온도를 유지했다. 실제 첫 호출의 소스 하한·상한 처리와 상태 연결을 검증한 뒤 6시간 적분을 완료했다. [전체 점수표](evidence/cp02_state_path_20261104/candidate/FULL_SCORES.md)는 3,688개 동일 평가점, 6개 예측시간, 6개 임계값을 각각 표시한다. P01의 +2시간 0.1 mm 적중은 회복했지만 FA03의 5 mm 오경보가 재발했다. 사전 고정 조건은 현재 B1 보호 9/11, 규준실험 대비 낮은 임계값 회복 3/15, 합계 12/26으로 **NO_QUALIFIED_CANDIDATE**다. 현재 B1을 대체하지 않는다.

정확한 real 내부 소스 대응, RN1 상류 규약, 전체 물·에너지 수지, 독립 사례 검증, 별도 C2 T39와 H/A/N 1시간 완료는 계속 미해결이다. 아래는 PR143·PR144를 포함한 과거 시점 기록이다.


## 2026-11-03: B1 0–2시간 과정 진단

같은 B1 초기장·경계장의 기존 KDM6와 0 과정률 수정 KDM6를 재실행했다. 두 구성 모두 +0·+1·+2시간의 전체 예보 출력이 보관본과 바이트 단위로 같으며, 선택한 16개 모서리·39층·360개 단계의 과정 기록을 확보했다. 국지 수증기·온도 갱신은 단계별 REAL32 연산으로 재현된다. [과정 진단 보고서](CP02_B1_TWO_HOUR_PROCESS_20261103.md)에서 +2시간 이후 낮은 임계값 악화의 원인을 추적한다. 새 물리 개선 후보를 채택하거나 6시간 성능을 새로 개선한 결과는 아니다. RN1 상류 규약·전체 수지·독립 사례·C2 T39는 계속 미완료다.

아래 내용은 PR143의 상태 기록이며, [당시 원본](evidence/cp02_b1_two_hour_process_20261103/prior_versions/pr143/reconciliation.json)을 보존했다.

## 2026-11-03: 통합 현황 — C2와 CP02는 별도 실험 계열

| 계열 | 비교 기준·범위 | 현재 결과 |
| --- | --- | --- |
| C2 안정성 | 동일 C2 실험의 OFF/HYDRO/COUPLED/PROJECTED/STRUCTURED/AMPLITUDE 6개 설정 | 각 설정의 640초 실험은 완료. H/A/N 1시간 요청은 760초·38단계 T39에서 중단됐다. 14 UTC 예보·관측 점수는 미평가다. 첫 group 거부 `(199,52,21)`은 별도 fatal consumer `(2,219,13)`와 다르다. [재생 기록](evidence/recount_contract_20261103/c2/first_group_replay.json)은 store 거부 뒤 sentinel 소비를 확인하며, 최초 거부 셀의 원래 생성 stencil은 여전히 포착되지 않았다. |
| CP02 B1 강수 | 같은 사례의 규준실험 1.0 (ORIGINAL)과 6시간 지상 총강수 검증 | 기존 36개 lead×임계값 CSI 중 21개 개선·15개 악화. ≥5 mm CSI는 여섯 lead 모두 개선했지만 낮은 임계값은 여러 셀에서 악화됐고 +4시간 RMSE는 더 높다. 이 CP02 결과는 C2 1시간 완주를 뜻하지 않는다. |
| 최신 선택 점검 (PR142) | 8개 추가 6시간 예보, 시간별 공통 3,688 RN1 점 | 56개 history가 검증됐고, 8개 모두 **NO_QUALIFIED_CANDIDATE**. 규준실험 1.0 대비 6개 lead×{0.1, 0.5, 1 mm}의 18개 CSI가 모두 이상이고 +1시간 CSI@10 mm가 엄격히 높아야 한다. 후보·lead·임계값 간 평균은 하지 않았다. |

이 세 비교는 서로 다른 실험과 사전 선택 규칙이다. 개선안을 순차적으로 바꾸며 운영 최적값을 찾은 기록으로 합치지 않는다. 검증 변수는 지상 총강수이고, 초기 `QSNOW`는 대기 중 눈 혼합비다. 최신 저장소 기준은 [main의 PR137 병합본](https://github.com/gonos2k/Cloud-BAL/pull/137), 연구 누적본은 [research의 PR142 병합본](https://github.com/gonos2k/Cloud-BAL/pull/142)이다. 2026-11-03 확인 시 main은 `5f6641f2`, research는 `83804668`이며 research tree는 `5e3bba43`의 tree와 같다. 따라서 PR142는 이 현황에 포함되지만 main에는 아직 통합되지 않았다.

세부 범위와 근거: [C2 종료·실패 및 IR 범위](PR106_CLOSED_FORECAST_AND_IR_SCOPE_20261026.md), [T39 닫힌 replay](T39_CLOSED_REPLAY_20261027.md), [CP02 B1 6시간 결과](SIX_HOUR_IMPROVEMENT_20261030.md), [PR142의 약·강수 선택 분석](WEAK_STRONG_BALANCE_REPORT_20261030.md), [기계 판독 검증 영수증](evidence/weak_strong_balance_20261030/validation.json), [사전 고정 선택 규칙](evidence/weak_strong_balance_20261030/selection_plan.json), [문서·원자료 SHA-256 목록](evidence/recount_contract_20261103/status/source_hashes.json).

다음 미해결 항목은 C2 최초 거부 셀의 producer stencil 연결, 실제 `QRAIN`/`QNRAIN` 작성 경로와 밀도·입도분포 규약, RN1 상류 시각·coverage 및 독립 사례, 전체 물·에너지 수지다. 별도 CP02 P2 재계산 검증 수정은 이 research branch에서 완료됐다. 집중 시험 6개가 통과했고 [통합 검증 receipt](evidence/recount_contract_20261103/validation.json), [빈 scope·전이자료 재현](evidence/recount_contract_20261103/validator/manifest.json), [152행·151개 key 중복 검출](evidence/recount_contract_20261103/validator/duplicate_admission_manifest.json), [원본 배열 전후 동일 row count](evidence/recount_contract_20261103/validator/normal_saved_arrays_before_after.json)이 근거다. main에는 아직 반영되지 않았다. 이 도구 수정은 C2 T39나 물리 검증의 완료를 뜻하지 않는다.

실제 rain-number 경로의 open finding은 [QRAIN/QNRAIN 작성 경로·밀도 근거 조사](evidence/recount_contract_20261103/physics/rain_number_lineage.md)에 기록했다. 현 B1 입력 2,573,532셀 중 202,569셀은 `QRAIN>0`이고 전체 `QNRAIN`은 0이다. 보관된 `met_em`에는 `QR`은 있지만 `QNR`은 없다. 보관된 소스 사본에는 Thompson 전용 rain-number initializer 후보가 있으나 pinned `real.exe`에 연결되지는 않았다. 이는 조사 범위를 좁히며 완료나 물리 검증을 주장하지 않는다.

다음 CP02 진단 초점은 +2~+6시간 낮은 임계값 CSI 회복을 조사하면서, 현재 B1의 +1시간 여섯 임계값 CSI와 매시간 ≥5 mm CSI를 보호하는 것이다. 같은 B1의 OLD/FIX 0~2시간 비교를 다음 진단으로 계획한다. 모델 trace는 아직 시작하거나 완료하지 않았으며, native 준비는 별도 외부 scratch batch에서 진행 중이다. PR142의 ORIGINAL 기준 선택 규칙은 해당 역사 결과에 유지하며 사후 변경하지 않는다.

## 2026-10-30: CP02 +1시간 개선 실험

[1시간 강수예보 원인 분리·개선](FIRST_HOUR_PRECIPITATION_IMPROVEMENT_20261030.md)에서
KDM6의 정확한 0 계산항 처리와 초기 강수 수종 대체의 민감도를 분리했다.
배경 강수 수종 보존 모드의 LAPSPREP→metgrid→real.exe 초기장과 수정 WRF는
3,600초를 정상 완료했다. 같은 3,688점에서 ≥5 mm CSI는 기존 HYDRO 0.214008,
원본 0.275093, 개선 후보 0.283582이며 후보 MAE/RMSE는 1.100693/4.044107 mm다.
여섯 임계값 CSI가 원본보다 높지만 평균 양의 편향과 일부 오경보는 늘었다.
이는 한 사례·+1시간의 연구 결과이며 레이더 강수 동화 이득이나 운영 승인을
뜻하지 않는다. 기본 HYDRO 정책은 유지한다. 아래의 최신 C2 T39 미완료와
RN1 상류 시각·coverage, 전체 물·에너지 수지의 미확정 상태는 별개다.

## 2026-10-30 기록: C2 연구 상태

실행 근거: PR106 종료 기록과 PR107 병합본
`4c290f1fff9c78cbe9967ce312114f0f53a27a43`의 진단 구현.
실제 native 근거는 선택 객체를 교체한 C2 partial-host 구성이다.
전체 WRF·종속 라이브러리 clean rebuild나 운영 승인을 뜻하지 않는다.

| 항목 | 확인된 범위 |
| --- | --- |
| OFF/HYDRO/COUPLED/PROJECTED/STRUCTURED/AMPLITUDE | 같은 C2의 640초 실행 완료 |
| 동일 진폭 대조·0–600초 반응 | 비교 완료; STRUCTURED는 일부 반응을 줄이고 Phi는 증가 |
| H/A/N 1시간 요청 | 모두 38단계·760초 후 INCOMPLETE, 모델 종료코드 1 |
| 실제 14 UTC 관측·paired 점수 | 모델 출력 부재로 건너뜀; NOT_EVALUATED |
| T1 미세물리 회계 | 선언한 한 호출의 source별 설명; 전체 host 수지와 별도 |
| 위성 IR112 원자료 재생 | 9개 LAPS 지원 셀에서 S8A=필터된 최대 BT, S8W=평균 BT 확인 |
| 전체 물·에너지·질량–바람·초기 충격·독립 skill | OPEN / NOT_EVALUATED |

PR107의 HYDRO T39 진단 실행은 38단계 완료 뒤 timestep 39에서 `INCOMPLETE`로 종료됐다.
닫힌 receipt와 후처리 결과는 [T39 종료 포착·재생 인계](T39_CLOSED_REPLAY_20261027.md)에 기록했다.
최초 T39/RK2 group 거부 셀 `(199,52,21)`은 알려진 fatal consumer `(2,219,13)`와 다르다.
prefix 비간섭 비교는 HYDRO의 공통 0–600초 범위에 한정된다. Pinned Intel O0/O2에서
최초 셀의 저장 거부와 별도 fatal 셀의 확산 producer를 국지 재생했다. 최초 후보의 정확 입력식은
Q/B 상한 밖이며, fatal producer에서는 REAL128에서 REAL64로 각각 변환할 때 상한을 넘는다.
최초 셀의 원래 생성 stencil과 수정 실행 검증은 미완료다. 물리 검증은 OPEN, T2는 NOT_EVALUATED다.

PR108에서는 [입력·실행 실패 계약](PR108_INPUT_EXECUTION_CONTRACTS_20261026.md)을
보강했다. PR109에서는 [DOUBLE 입력·출력 검증·portable 격리](PR109_MEMORY_AND_PORTABILITY_20261027.md)의
남은 공백을 수정했다. PR110은 [정적 격자 입력과 portable 잔여 의존성](PR110_STATIC_INPUT_AND_PORTABILITY_20261027.md)을
보강한다. PR111은 [정적 격자의 결측값·좌표 검증](PR111_STATIC_VALUE_VALIDATION_20261027.md)을
실제 reader–WPS 출력 경계에 연결한다. 이 공학적 변경은 예보·관측 판정을 승격하지 않는다.

## 2026-10-30 당시 다음 작업

1. 보존된 T39 결과에서 group 첫 거부와 fatal consumer가 다른 셀임을 유지하고,
   최초 셀 `(199,52,21)`의 source·transport 생성 입력을 추가로 연결한다.
2. 보존된 국지 재생을 기준으로 source 표현의 공동 반올림·보존 계약을 검토한다.
   별도 fatal 셀의 원인을 전체 group으로 일반화하거나 상한·cache를 임의 변경하지 않는다.
3. 원인이 확인된 연산만 수정한다. 모델 정책을 바꾸면 같은 실행파일로 H/A/N의
   기존 640초·T39 이후·원래 1시간 종료점을 다시 검증한다.
4. 완료된 동일 유효시각 자료에 기존 관측·paired 평가를 적용한다. 위성은 실제
   센서 계수·관측기하·집계를 갖춘 한 채널 전방연산자가 별도로 필요하다.

바람 투영·평활화, 허용오차, N/B prior, source cache 정책은 원인 확인 없이
바꾸지 않는다. 극소량이라는 이유만으로 무조건 0 처리하지 않는다.
진단 구현·시험 통과나 이 불완전한 T39 포착은 수정·물리 검증·1시간 완료를 대신하지 않는다.

## 근거

- [PR106 종료·실패·위성 범위](PR106_CLOSED_FORECAST_AND_IR_SCOPE_20261026.md)
- [PR103 동일 진폭 대조](PR103_AMPLITUDE_ATTRIBUTION_20261026.md)
- [PR105 관측 판독·paired 평가](PR105_OBSERVATION_PAIRING_20261026.md)
- [PR84 체크리스트 — 역사 기록](FAST_COMPLETION_CHECKLIST_20261012.md)

기존 과학적·운영 승격 조건은 유지한다. 더 작은 norm이나 정상 종료만으로
관측 적합성·물리적 균형을 승인하지 않는다.

## CP02 강수 소실 지점의 초기 수종 추적

[보관 실행파일 호출 경계 재생](CP02_CALL_BOUNDARY_20261028.md)에서 HYDRO·LIQUID의
20점 × 22층 QR·QS 차이가 `derive_column_physics` 반환 시 이미 나타남을 확인했다.
일반·계측 재생의 WPS와 shadow는 당시 보관본과 바이트 동일하다. 마지막 derive 반환과
pipeline 후보도 포착한 8개 필드에서 같다.
[내부 경계·평가 입력 재생](CP02_INNER_SPECIES_20261028.md)은 첫 HYDRO의 선택 표본에서
레이더 진단 작업 배열이 수송 호출 전후에 유지되고, `publish_hydrometeor_candidate`
호출에서 배경 QR·QS가 이 작업 배열의 REAL32 값으로 바뀜을 확인한다.
HYDRO의 evaluation 인자는 null이며, LIQUID의 실제 평가 상태·설정·반환 budget을 포착했다.
[레이더 입력·publish 조건 재생](CP02_RADAR_INPUTS_20261028.md)은 원래 반사도와
상분할의 값·valid·quality·source, 실제 밀도 피연산자, 190개 위치의 진단·저장 값을
연결한다. refresh 표본 누락은 분석 전에 거부하며 정수 반환 상태도 원시 바이트로 포착한다.
진단 입력과 배경 대체 조건의 물리적 타당성, 전체 물수지와 강수 개선의
인과관계는 아직 미확정이다. CP02 결과는 위 C2 T39 완료와 별개다.

[배경 CSV 계약과 QC·상별 비교](CP02_BACKGROUND_CONTRACT_20261028.md)에서는
캡처의 기준 CSV 해시와 실제 분석 입력을 대조한다. quality 0인 선택 표본에서도
rain·snow 감소가 커서 `0x20`만을 원인으로 지목하지 않는다. 기존 비관측 250개 표본은
배경 수종도 모두 0이므로 비관측 양의 배경 수종 보존을 검증한 것으로 보지 않는다.
진단 total과 배경 생성 규약의 계수·단위·밀도 기준 및 대조 표본 연결이 다음 조사 대상이다.

[공통 밀도 비교와 강수검증 대조 지점](CP02_DENSITY_CONTROLS_20261029.md)은
190개 원시 표본의 진단 농도와 배경 등가 농도를 같은 진단 밀도로 비교한다.
16개 RN1 지점의 실제 WRF 네 모서리·가중치로 첫 시간 48개 강수량을 재현하고,
별도 탐색용 양의 배경 수종 표본을 추가했다. 이는 새로운 예보 성능 개선을
입증한 결과가 아니며, 당시 배경 생성식·과정 수지·강수 영향은 계속 조사한다.
