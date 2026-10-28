# CP02 WPS의 실제 OFF 기준군 실패 판정 보강

**실제 OFF WPS와 shadow 배경이 다르면 이제 PASS receipt를 생성하지 않는다.** 기존 HYDRO·LIQUID 비교와 OFF 비교를 모두 모은 뒤 같은 `exact_equal` 조건으로 검사한다. 실패 메시지에는 해당 비교군을 표시한다. 입력, 물리, 점수식은 변경하지 않았다.

기준 커밋은 PR116 병합본 `723e7f4036300523e529d0cbd9fbe696c78f01a1`이다. 이전 도구는 후보 불일치를 거절하지만 OFF 불일치는 기록만 하고 전체 상태를 PASS로 만들 수 있었다. 현재 보존된 자료에는 불일치가 없으므로, 이 결함과 기존 분석 결과의 유효성을 구분한다.

## 직접 검증

| 검사 | 결과 |
|---|---|
| 실제 형식의 합성 WPS·NetCDF, 세 비교군 동일 | PASS, 3×40개 비교 모두 정확히 일치 |
| OFF의 QR 한 기압면·한 셀만 변경 | 오류, receipt 미생성 |
| HYDRO의 QR 한 기압면·한 셀만 변경 | 오류, receipt 미생성 |
| 같은 OFF 음성시험을 이전 도구에 적용 | 기대한 거절이 발생하지 않아 시험 실패 |
| 유지 pytest | **3 passed** |
| 실제 연구 호스트 보관 파일 재판독 | **OFF 40개 + HYDRO 40개 + LIQUID 40개 모두 일치** |

시험은 `compare()`나 `read_wps()`를 대체하지 않고, 실제 Fortran record 형식 WPS와 실제 NetCDF 파일을 읽는다. 외부 연구 경로만 임시 fixture로 지정한다. 새 시험은 자동 발견으로 portable에 등록됐으며 전체 등록 수는 314개다. 등록 확인은 portable 전체 실행 통과를 뜻하지 않는다.

실제 archive 재실행은 기존 [120개 비교 기록](evidence/cp02_initial_species_20261027/final/wps/readback.json)과 비교값·입력 해시·상태가 동일하다. 새 [readback](evidence/wps_off_readback_20261028/readback.json)은 reader의 checkout 경로만 다르다. 과거 receipt와 manifest는 덮어쓰지 않았다. 과거 manifest의 수정 전 tracer 해시는 당시 PR116 소스에 대한 기록이며, 현재 수정본은 새 [validation](evidence/wps_off_readback_20261028/validation.json)에 별도로 연결한다.

## 당시 소스 확보의 진척과 한계

실제 scratch·소스 보관 영역에서 세 파일의 정확한 basename을 검색하고 내용 해시를 대조했다. [검색 범위와 일치 경로](evidence/wps_off_readback_20261028/source_search.json)를 보존했다.

| 당시 빌드 입력 | 조사한 파일 수 | 정확한 SHA-256 일치 |
|---|---:|---:|
| `cloud_bal_column_physics.f90` | 74 | 0 |
| `cloud_bal_pipeline.f90` | 87 | **14개 보관본** |
| `lapsprep.f90` | 61 | 0 |

회수한 pipeline 내용의 SHA-256은 `188a2e1b9f467c6fa28e8f317e493975ddaf8dfbf5100398867666bbb6f2b478`로 당시 빌드 입력 기록과 같다. 이는 **정확한 소스 내용의 부분 확보**이며, 어느 복사본 경로가 실제 빌드에 사용됐는지나 전체 실행파일의 재빌드를 입증하지 않는다. 이름이 달라진 파일·압축 archive 내부·검색 영역 밖의 사본까지 부재라고 주장하지 않는다.

실제 `compile_inputs.sha256`도 다시 읽어 기존 digest `de587929…e78`과 pipeline 항목의 일치를 확인했다. 회수본은 `derive_column_physics`를 호출하고(266–272행), 성공한 후보를 받은 뒤(282행) 선택적 압력 처리와 balance 경로를 진행한다. 이 호출 순서만으로 내부 수종 변경을 특정할 수 없다. 해당 정보와 검사한 파일 경로는 새 validation에 기록했다. 별도의 `inputs.sha256` 집계 파일과 `compile_inputs.sha256`을 혼동하지 않는다.

**QR·QS가 분석 배경→후보에서 처음 달라지는 내부 연산은 여전히 OPEN이다.** 핵심 물리 모듈과 LAPSPREP 소스의 정확한 내용이 미확보인 상태에서 유사한 최신 코드를 당시 연산으로 대체하지 않았다. 새 예보, Fortran 컴파일, 물리 변경은 수행하지 않았다. 첫 미세물리 과정량, 물수지, RN1 실제 입력 시각·coverage, 최신 C2 T39와 1시간 완료도 별도 미완료 항목이다.
