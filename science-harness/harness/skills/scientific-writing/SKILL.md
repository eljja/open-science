---
name: scientific-writing
description: 논문급 글(학술 논문, 기술 보고서, 리뷰, 제안서, 백서)을 작성한다. 개요→그림 우선 설계→섹션 초안→인용 실존 검증→적대적 리뷰→수정→md/HTML/PDF/docx 빌드. 섹션별 계약(Abstract/Introduction/Results/Discussion/Methods), 근거-주장 연결, 무결성 게이트, AI 문체 제거 포함.
---

# 논문급 글 작성 (scientific-writing)

## 파이프라인과 게이트
```
G0 범위   : 한 문장 주장(pitch), 독자, 분량, 형식(저널/사내 보고서) 확정
1 문헌     : literature-review 스킬 → evidence DB(CSV, ID [Lxx]) — 모든 인용의 단일 출처
2 개요     : 섹션별 주장 목록 + 각 주장이 기대는 근거 ID/그림
3 그림 우선 : Figure 1 = pitch 를 데이터로. 그림별 한 메시지. scientific-figures/schematic-diagrams
G1 근거     : 모든 주장 → [Lxx] 또는 산출물(그림/표/계산) 연결. 연결 없는 주장은 삭제 또는 '가설'로 표기
4 초안     : 섹션 병렬 작성 가능(section-writer 서브에이전트, 섹션별 계약 전달)
G2 인용     : scholar.verify_citations 로 전 인용 검증. not_found/mismatch 는 제거·교체(기억으로 만든 인용 금지)
G3 수치     : 본문·표·캡션·초록의 모든 숫자를 산출물 파일과 대조(한 수치 = 한 값). 측정/계산/설명용 라벨
5 리뷰     : reviewer 서브에이전트(읽기 전용) — 최대 8개 지적, 근거 명시
6 수정     : 지적별 대응표(수용/반박+근거)
G4 빌드     : md → HTML(report-html) / PDF / docx, 캡슐 동결(capsule_freeze)
```
게이트를 통과하지 못하면 다음 단계로 가지 않는다. 각 게이트 결과를 `notes/` 일지에 한 줄씩 남긴다.

## 섹션별 계약
| 섹션 | 해야 할 일 | 하지 말 것 |
|---|---|---|
| 초록 | 문제-방법-핵심 수치-의미, 150~250단어 | 근거 없는 수식어, 인용 |
| 서론 | 넓은 맥락→구체적 공백→본 연구의 기여(번호 목록 가능) | 문헌 나열식 서술 |
| 방법 | 재현 가능한 수준: 데이터 출처, 버전, 파라미터, 통계 검정, 코드 위치 | 결과 해석 |
| 결과 | 그림 순서대로, 문단 첫 문장 = 그 문단의 결론, 수치+불확도+n | 과장된 일반화 |
| 고찰 | 선행연구와 비교, 대안 설명, 한계(구체적), 함의 | 결과 반복 |
| 결론 | 3~5문장, 측정된 것과 추론된 것 구분 | 새 데이터 |

## 문체 규칙 (한국어 기술문)
- 한 문장 한 주장. 주어-서술어 거리를 짧게. 수동태 남발 금지.
- 방어적 완곡어(“~할 수도 있을 것으로 사료됨”) 제거 → 근거 강도에 맞는 동사(보인다/시사한다/확인했다).
- AI 문체 제거: “혁신적인”, “획기적인”, “다양한 측면에서”, “결론적으로 말하자면”, 의미 없는 3항 나열, 매 문단 요약 문장.
- 용어는 첫 등장 시 정의, 약어는 한 번 풀어쓰기. 단위는 SI, 숫자와 단위 사이 공백.
- 추론은 추론이라고 쓴다. 측정되지 않은 것을 측정된 것처럼 쓰지 않는다.

## 템플릿
`templates/paper_template.md`(IMRaD), `templates/report_template.md`(사내 기술 보고서), `templates/response_to_reviewers.md`.

## 출력
- 원고 `outputs/manuscript/<slug>.md` + 그림 `outputs/figures/` + `references.bib`(doi_resolve 의 BibTeX).
- HTML: `python -m sciharness.cli html outputs/manuscript/<slug>.md` (Confluence 인라인 스타일)
- PDF: pandoc(+xelatex, 한글 글꼴 지정) 또는 HTML 인쇄. docx: pandoc.
