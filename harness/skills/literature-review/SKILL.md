---
name: literature-review
description: 문헌 조사, 선행연구 정리, 리뷰 논문, 기술 동향 조사. scholar MCP(Crossref/OpenAlex/arXiv/PubMed)로 실제 레코드를 가져와 evidence DB(CSV)를 만들고 근거 등급을 매긴다. 기억으로 만든 인용 금지, DOI 실존 검증 필수. PRISMA식 포함/배제 기준 기록.
---

# 문헌 조사 (literature-review)

## 원칙
1. **실제 레코드만**: 모든 문헌은 검색 도구 결과 또는 doi_resolve 로 확인된 것. 모델 기억 속 인용은 “후보”일 뿐 → verify_citations 통과 전 사용 금지.
2. **evidence DB 가 단일 출처**: `outputs/literature/evidence.csv`
   열: `id`(L01..), `doi`, `title`, `year`, `venue`, `type`(실험/계산/리뷰/특허/프리프린트), `finding`(핵심 수치 포함 1–2문장, 본인 표현), `conditions`, `evidence_grade`(A 직접측정·동료심사 / B 간접·계산 / C 프리프린트·학회초록 / D 의견), `relevance`, `retrieved`(날짜·도구).
3. 인용 문구는 25단어 미만, 한 출처당 한 번. 나머지는 자기 말로 요약.
4. 프리프린트(arXiv)는 표시하고 등급 C.

## 절차
1. 질문을 3–6개 하위 질문으로 분해 → 질의어(영어 기술 용어 + 동의어) 목록.
2. 소스별 검색: `crossref_search`(기본), `openalex_search`(키 있을 때, 인용수), `arxiv_search`, `pubmed_search`(생의학). 하위 질문당 10–30건.
3. 스크리닝: 포함/배제 기준을 먼저 쓰고(`outputs/literature/criteria.md`) 제목/초록으로 1차, 본문 확인 가능한 것만 2차(전문은 오픈액세스 우선).
4. DB 기록 → 하위 질문별 종합표 → 상충 결과는 조건 차이로 설명.
5. `verify_citations` 일괄 실행, 결과 열 `verified` 추가.
6. 결과물: evidence.csv, 검색 로그(질의/건수/날짜), 종합 메모, BibTeX.

## 병렬화
하위 질문이 독립이면 `literature-scout` 서브에이전트에 하나씩. 각자 같은 CSV 스키마로 반환 → 병합 시 DOI 중복 제거, ID 재부여.
