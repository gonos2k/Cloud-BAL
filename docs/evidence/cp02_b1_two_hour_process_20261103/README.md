# 같은 B1 초기장의 첫 두 시간 과정 진단 — 2026-11-03

[핵심 수학·기상학적 해석 보고서](../../CP02_B1_TWO_HOUR_PROCESS_20261103.md) · [전체 그림 즉시 보기](FIGURES.md) · [전체 시간·임계값별 CSI 표](tables/CSI_BY_LEAD_THRESHOLD.md)

두 실행은 같은 B1 초기장·경계장을 사용한다. OLD는 기존 KDM6, FIX는 정확한 0 과정률 분기 수정 KDM6다. 진단 실행의 초기 시각은 2026-08-16 12 UTC이며, 12·13·14 UTC 전체 history 값·메타데이터와 파일 SHA-256이 각각의 보관 예보와 같다. 각 arm의 16개 모서리 × 39층 × 360단계, 224,640개 국지 과정 갱신이 연결됐다. 이는 새로운 6시간 예보 또는 개선 후보의 채택이 아니다.

## 증거 위치

- `native/`: pinned Intel 빌드·두 시간 실행·엄격 history 비교·원시 gzip·압축/이동/실패 시도 기록. 실행파일·NetCDF 원본은 외부 경로와 해시만 기록한다. 디스크 부족으로 잘린 첫 FIX 실행은 거부하고 공유 파일시스템에서 재실행했다.
- `cohorts/`: 원래 아홉 선정/보간/강수 재계산 파일. 사후선택 네 지점이며 전체 3,688점 점수의 대체 자료가 아니다.
- `analysis_gates/`: 원시/압축 파일의 연결을 보존한 분석용 gate, 실제 CLI 명령, 두 번의 분석 및 16개 산출물 바이트 재현 기록, key-matched 잠열 성분 표와 검토.
- `analysis_gates/compact_tables/`: 해제 해시가 원래 산출물과 같은 표. 원시 gzip에서 재생성 가능한 대용량 `phase_records.csv` 두 개는 외부 생성물의 해시·크기를 별도로 기록한다.
- `review/`: 별도 원시 해독과 수치·과학 검토. `POST_STEP`은 국지 과정 갱신 후이며 전체 KDM6 함수 반환이 아니다.
- `figures/`, `tables/`: 본문 그림, 별도 진단 그림, 규준/OLD/FIX의 6시간·6임계값 전체 108행 및 재생성/묶음 영수증.
- `validation/`: 깨끗한 Git export의 관련 시험. 처음 드러난 기존 시험의 상위 디렉터리 이름 의존성은 basename 검사로 고쳤고, 원본·실패 로그를 보존했다. 점수 계산 코드는 바꾸지 않았다.
- `prior_versions/`: PR143의 두 상태 문서와 수정 전 시험을 보존한다. 과거 manifest는 수정하지 않는다.
- `kg/`: KLAPS50·Cloud-BAL의 별도 날짜별 증분 구조 추출과 위키 감사. 그래프 최신성은 실행·과학 검증을 의미하지 않는다.

## 재생성 범위

`analysis_gates/run1.command.txt`와 `run2.command.txt`는 gzip 원시 자료부터 분석하는 명령이다. 출력과 SQLite scratch는 충분한 공간이 있는 파일시스템에서 지정해야 한다. `tools/derive_cp02_b1_components.py`는 분석 receipt의 입력 해시와 전체 키를 확인한 뒤 각 모서리·층·시간의 성분을 만든다. `tools/plot_cp02_b1_process.py --help`는 보존된 표와 receipt에서 그림을 재생성하는 인자를 설명한다. 출력 폴더는 새 경로를 사용하며 실패 시 기존 그림은 보존한다.

보호할 기준은 현재 B1의 +1시간 여섯 임계값 CSI와 시간별 5 mm CSI다. 이번에는 그 조건을 평가할 새 물리 수정 후보를 만들지 않았다. QRAIN/QNRAIN 작성·운반 규약, PSD 초기화, 수분·잠열 이후 동역학 및 강수 위치 연결, 전체 수지, RN1 상류 규약, 독립 사례와 C2 T39는 미완료다. PR142의 과거 ORIGINAL 기반 선정 규칙도 바꾸지 않았다.
