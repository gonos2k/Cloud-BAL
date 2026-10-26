# PR108: 입력과 실행 결과의 실패 계약

기준은 PR107 병합본 `4c290f1fff9c78cbe9967ce312114f0f53a27a43`이다.
이번 변경은 입력 거부, 셸 오류 전달, 게시 복구, 회귀시험 실행 범위를 다룬다.
C2 모델 물리, 바람 후보, 허용오차, source cache 정책을 변경하지 않는다.

## 수정 범위

- `cloud_bal_current_evidence`는 command substitution 안에서도 generation 조회,
  HEAD 조회, Python 검증 실패를 호출자에게 반환한다. 검증에 성공한 경우에만
  generation 경로를 출력한다.
- 두 real runner의 EXIT 처리기는 게시 전 staging만 격리한다. 게시 불확실
  상태나 이미 생성된 generation이 있으면 staging과 owner를 보존해 같은 ID로
  복구할 수 있게 한다.
- LAPSPREP는 첫 순회에서 모든 사용 입력의 격자와 metadata를 검사하고,
  두 번째 순회에서도 재검사한 뒤 payload를 읽는다.
  오류 종료는 nonzero로 전달한다.
- native W 소비자는 전체 필드의 결측·유효범위 metadata를 검사한 후 갱신한다.
- 지상관측 비교는 지원 투영과 좌표 격자의 일치성을 점수 계산 전에 확인한다.
- Python 회귀는 portable/Linux/native/실자료 계층을 구분한다. 실제 source와
  binary의 해시 검증은 실자료 계층에 보존한다.

## 입력 계약의 범위

LAPSPREP의 단위 문자열은 현재 생산자 metadata와 일치해야 한다. 기존 LSX는
`rh:units="meters"`, `mr:units="grams/kikogram"`라는 legacy label을 기록한다.
이는 물리 단위를 승인하는 뜻이 아니다. 내부 field contract의 RH percent,
MR g/kg 의미를 유지하며, 생산자 label 호환성과 물리 의미를 구분한다. 확인한
자료는 유지된 `Cloud-BAL/scratch/cp02_maintained_derived_O0_qej27s72/`
`matched_control_chain14_O0.8oosid20/prepared/lapsprd/lsx/262281400.lsx`다.

관측 격자 판정은 binary32 좌표 half-ULP를 역변환한 변동량과
`32 * eps32 * (6370000 / DX + max(nx,ny))`의 source 산술 allowance를 더한다.
전체 allowance가 0.01 격자를 넘는 구성은 지원 범위 밖으로 거부한다. 이는
명시적인 수치 허용 정책이며 엄밀한 최대 반올림오차 증명이나 관측오차 모델이
아니다. 기존 5 km H 격자의 허용치는 약 0.00612043 격자이며 실제 최대
역변환 잔차는 i=0.000749295, j=0.000481687이다. 이 검사는 모델 예보의
정확도나 관측의 품질을 승인하지 않는다.

## 검증

새 detached checkout과 독립 venv에서 portable Python 215개 파일과 셸 2개를
완주했다(exit 0). pytest 208개 파일에서 1,390개 사례가 통과했고 선택적
pyproj reference 1개는 skip됐다. 나머지 Python 7개는 script 시험이다.
전체 skip 파일은 0개다. 개별 사례의 skip과 파일 PASS를 구분한다. 등록된 293개 파일은 portable 215, Linux 4, native 63,
실자료 11개로 분리된다. 이는 293개 파일 전체를 실행했다는 뜻이 아니다.

고정 Intel 프로필의 fresh scratch에서 LAPSPREP와 native W의 O0/O2 검증을
통과했다. 최종 LAPSPREP O2 실행파일에도 층수 증가·감소, 역순 level, X/Y
순서, 시각, level 차원·결측, 단위·자료형, namelist 및 필수 파일 누락의
12개 음성 사례를 실행해 nonzero와 출력 미생성을 확인했다. 셸 검증은 직접
호출과 command substitution의 실패 전달, generation rename 이후 실패,
current 교체 이후 fsync 실패 및 같은 ID 복구를 실제 EXIT 처리와 연결했다.
기존 transaction recovery 25개 시험도 통과했다.

팀 검토에서 지적한 LAPSPREP 변수 자료형·level 결측 metadata 검사와
전체 skip 계층의 성공 오인 경로를 수정한 뒤 다시 검증했다. native W,
게시 복구, 투영 선행검사와 테스트 계층 분리를 서로 다른 담당자가 검토했다.

전체 native 계층은 PASS로 주장하지 않는다. 기존 PR89 source 시험의
transport pin은 변경 전 기준 소스와도 다르다(기대 `c8ecedde…`, 실제
`6c844fe8…`). 이 역사적 pin을 현재 해시로 덮어쓰지 않고 해당 검증의 남은
문제로 기록한다. 전체 Linux·실자료 계층과 WRF 예보는 이번 묶음에서
재실행하지 않았다.

명령·소스 해시·환경·로그 식별자는
[evidence/validation.json](evidence/pr108_input_execution_20261026/validation.json)에,
O2 음성 결과와 실제 보존 격자 판독은 같은 폴더에 보존한다.

## 연구 상태와 제한

기존 여섯 C2 구성의 640초 성공은 유지한다. H/A/N 1시간 요청은 760초 후
INCOMPLETE이며 실제 14 UTC 점수는 NOT_EVALUATED다. PR107의 단일 HYDRO
T39 진단은 재시작하거나 설정을 변경하지 않는다. 이 문서의 입력·실행 계약
시험은 T39 원인 규명, 1시간 완료, 전체 host 수지 또는 관측 skill을 대신하지 않는다.

Graphify 갱신은 코드 관계와 파생 wiki의 최신화이며 실행·과학적 검증이 아니다.
