# 2026-11-04 B1 상태 경계·비 입자수 연구 KG 갱신

이 폴더는 Graphify의 **범위를 고정한 증분 추출**과 KG 보고서·감사 로그 동기화를 기록한다. 코드·시험·패치 생성기·KG 준비 도구 19개만 Python AST로 추출했다. 나머지 확정 자료 403개는 해시로만 연결했으며, 캡처와 native 소스의 의미를 그래프가 검증했다고 해석하지 않는다.

- [선택 고정 기록](selection_lock.json): 검토된 19개 소스, 403개 자료, 검증 요약과 미완료 항목.
- [격리 stage](stage_receipt.json): 유지 저장소에 쓰기 전의 실제 그래프·manifest·wiki 결과.
- [독립 stage 검사](stage_validation.json), [검토](stage_review.json).
- [게시 및 읽기 대조](publish_receipt.json), [현재 연구 worktree·wiki 사본 대조](postpublish_copy_receipt.json).

KLAPS50와 Cloud-BAL의 snapshot 이름은 각각의 저장소 안에서 `2026-11-04-b1-state-path`다. 기존 234개 snapshot을 보존하고 두 개를 추가한다. KLAPS50의 구조 변화는 **노드 +255, 간선 +618**, Cloud-BAL은 **노드 +255, 간선 +612**다. 기존 노드 ID는 보존하며 dangling endpoint·중복 간선·self-loop 검사 수는 모두 0이다. 커뮤니티 개수 변화는 추출 구조의 변화이며 연구 성능의 척도가 아니다.

갱신 대상은 각 저장소의 현재 graph/report/manifest와 새 날짜 snapshot, wiki의 파생 보고서·index·append-only log다. 기존의 다른 수정 파일과 과거 snapshot은 보존한다. 이 연구 worktree에는 Cloud-BAL 현재 파일·snapshot과 wiki 사본을 별도로 복사한다.

Fortran 파일 사이 CALL 추출은 여전히 부분적이다. 그래프의 최신성은 WRF 실행의 정확성, 물·에너지 보존, 입도분포 가정의 타당성 또는 강수예측 성능을 입증하지 않는다. 해당 근거는 [실험 자료 안내](../README.md)와 독립 재계산·실행 receipt에 구분해 보존했다.
