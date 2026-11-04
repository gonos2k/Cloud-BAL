# CP02 비 입자수 과정 및 단일 입경 대조

## 핵심 결과

[학회논문 형식 보고서](../../CP02_RAIN_NUMBER_PROCESS_20261104.md), [23개 그림 모음](FIGURES.md), [예측시간·임계값별 144행 전체 표](followup/figures/FULLSCORES.md)를 함께 제공한다. 초기시각은 **2026-08-16 12 UTC**, +1∼+6시간은 각각의 **한 시간 강수량**이다. 규준실험은 `ORIGINAL`, 유지 중인 구성은 현재 B1이다.

- 현재 B1과 기존 0.862 mm 입자수 후보를 같은 FIX 계열로 0–3시간 진단했다. 9개 지점·36개 고유 모서리·39층·540단계가 연결되며 두 구성의 전체 정시 history 8개는 각 구성의 기존 예보와 동일하다.
- 후속 0.65 mm 후보는 초기 비 질량·수증기·온도를 유지하고 QNRAIN만 바꾼 단일 탐색 대조다. 표준 FIX 실행파일로 6시간 정상 완료했다.
- [독립 재계산](followup/independent_recount.json)은 범주형 144행·연속형 24행·조건 26개를 확인했다. 조정 후보는 현재 B1 보호 8/11, 낮은 임계값 회복 2/15로 **10/26, 미채택**이다. 현재 B1을 유지하며 후반 낮은 임계값 회복 목표는 미달성이다.

## 자료와 계산의 연결

| 자료 | 내용·한계 |
|---|---|
| `newcohorts/` | 사후 진단 지점 9개, 서로 겹치지 않는 36개 WRF 모서리와 가중치. 전체 점수 표본과 별도 |
| `native/source/`, `native/build/` | 고정 FIX 소스에서의 계측 생성, pinned Intel ifx scratch 빌드와 링크 기록 |
| `native/runs/`, `native/quick/` | 실제 8-rank 실행·입력 해시·시간별 출력 대조. 원래 NetCDF·실행파일은 외부 해시 식별 |
| `native/capture/` | 선택 과정·진입/반환·호출의 56개 원시 스트림을 독립 gzip 청크로 보존. manifest는 압축·비압축 크기와 SHA-256을 모두 연결 |
| `input_manifest.json`, `analysis/coverage_receipt.json` | 원래 외부 캡처 경로, 전체 선택 영역 검사와 국지 연산 검산 결과 |
| `analysis/selected_*_parts/` | 원래 큰 NPZ의 논리 배열을 손실 없이 분리한 작은 NPZ와 각 NPY 원시 해시. 기존 과학 분석 영수증은 유지 |
| `science/` | 별도 NetCDF 성분 대조와 국지 과정항 재계산. 층별 시간 합은 총수종 질량·실제 온도 변화·인과 기여율이 아님 |
| `followup/policy.json`, `evaluation_plan.json`, `forecast_freeze.json` | 0.65 mm 가정, 원시 실제 진입 사전검증, 6시간 실행 전 고정한 입력·소스·평가 규약 |
| `followup/runtime/`, `analysis_dm065/` | 89개 입력 동일성, 7개 정시 history 검증, 6개 시간별 점 자료·점수·조건·미채택 판정 |
| `validation/`, `kg/` | 집중 시험·독립 팀 검토·과거 증거 대조 및 범위가 제한된 구조 그래프 갱신. 과학적 보존 검증과 별도 |

공개 수 혼합비와 내부 수농도는 `REAL32(N×DEN)` 변환과 소스의 기존 제한을 적용해 비교한다. 공개값을 내부값에서 바로 빼면 밀도 변환을 초기화 효과로 오해한다. 비·눈·싸락눈 침강 경계만 분해했으며 별도 구름얼음 침강을 모두 분해하지 않았다. 조건부 지상 유출 기록의 부재를 0으로 대체하지 않는다. KDM6 RAINNC와 대류 RAINC를 구분하며 총강수에는 둘을 합한다.

## 저장 자료로 재검증

저장소 루트에서 아래 명령을 실행한다. 각 출력은 새 경로여야 한다. 전체 관련 시험 목록·실행 환경·실제 결과는 `validation/`에 별도 보존한다. 전체 portable suite를 수행했다는 뜻은 아니다.

```bash
python tools/recount_cp02_rain_dm065.py \
  --analysis docs/evidence/cp02_rain_number_process_20261104/followup/analysis_dm065 \
  --plan docs/evidence/cp02_rain_number_process_20261104/followup/evaluation_plan.json \
  --plan-sha256 bf57b08377138a7e0e3554a6f314e8f8a58bb4dcf722fc30c9c1a046d76e31fe \
  --output /tmp/cp02_dm065_independent_recount.json
python tools/plot_cp02_rain_dm065.py \
  --analysis docs/evidence/cp02_rain_number_process_20261104/followup/analysis_dm065 \
  --plan docs/evidence/cp02_rain_number_process_20261104/followup/evaluation_plan.json \
  --output /tmp/cp02_dm065_figures
```

선택 과정 분석 전체를 재생하려면 `native/capture/{B1,NR_PRIOR}/manifest.json`의 `files[].chunks`를 이름순대로 압축 해제·연결해 원래 파일을 복원한다. 청크와 전체 파일의 크기·해시를 먼저 확인한다. [분석 방법](ANALYSIS_METHOD.md)에 따라 `input_manifest.json`의 두 `root`와 표면 기준자료 경로만 옮긴 사본을 만들고 원래 파일별 해시·schema·모서리·표면 자료 핀을 유지한다. 원래 경로가 바뀌면 manifest 자체 및 경로가 포함된 영수증의 해시는 달라진다. 분석기는 gzip을 직접 읽지 않는다.

```bash
python tools/cp02_rain_number_process.py \
  --manifest /tmp/cp02_relocated_manifest.json \
  --schema docs/evidence/cp02_rain_number_process_20261104/native/schema/cp03_schema.json \
  --corners docs/evidence/cp02_rain_number_process_20261104/newcohorts/point_corners.csv \
  --output /tmp/cp02_process_replay
python tools/pack_cp02_selected_npz.py \
  /tmp/cp02_process_replay/selected_B1.npz /tmp/cp02_selected_B1_parts
python tools/pack_cp02_selected_npz.py \
  /tmp/cp02_process_replay/selected_NR_PRIOR.npz /tmp/cp02_selected_NR_PRIOR_parts
```

분리 전 논리 NPZ와 분리 후 각 배열의 dtype·shape·순서·원시 비트가 같은지 검사했으며, 분리본 재생은 바이트 동일했다. 전 영역 첫 호출 스트림 전체는 외부 보관·해시만 연결하며 이 저장소에 모두 복제하지 않았다. WRF 재적분·초기화 NetCDF 재작성·원래 history에서의 재보간은 고정된 외부 실행파일·입력·Intel/NetCDF/MPI 환경을 요구한다. 저장 점 자료의 점수 재계산과 구분한다.

## 과거 증거와 미완료 항목

P3 helper는 **이번에 대조한 PSD 재구성 구간**의 `>=` 활성 경계와 하한 961에 맞췄다. 다른 KDM6 함수의 모든 임계 조건이 같다는 뜻은 아니다. 기본 정책의 QNRAIN 원시 배열은 기존 후보와 동일하다. PR145의 원래 helper·시험·보고 상태 및 당시 그래프는 `prior_versions/` 및 기존 날짜별 스냅숏으로 보존해 이전 manifest를 대조한다. 초기 분석 게시 실패와 이후 정상 재시도는 `attempts/`에 구분했다.

RN1 상류 시간 구간·coverage/QC, DEN의 건조·습윤 기준, real 내부 작성 분기의 정확한 소스 대응, 호출 시점의 질량·전체 물·에너지 수지, 독립 기상 사례, 별도 C2 T39와 H/A/N 1시간 완료는 미완료다. 구조 그래프 갱신이나 국지 산술 잔차 0을 이 항목들의 완료 근거로 사용하지 않는다.
