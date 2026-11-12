# 프로젝트 설정 (AGENTS.md)

> 이 파일은 프로젝트별 설정이다. 핵심 행동 규율은 science 에이전트 시스템 프롬프트(`harness/prompts/science_system.md`)에 있다.
> OpenCode 외 런타임(Claude Code, Codex)에서는 설치기가 핵심 규율을 이 파일 앞부분에 합쳐 넣는다.

## 사용자 설정
- 산출물 언어: **한국어**(그림 라벨, 표, 요약, 작업 기록 포함). 참고문헌 제목은 원어 유지.
- 보고서 형식: 항상 Markdown + Confluence 용 HTML(인라인 스타일, 그림 내장형과 첨부형 두 벌). 원자료 탐색용 데이터 뷰어 HTML 별도.
- 그림: 한국어 라벨, Malgun Gothic. PNG(300 dpi) + SVG.
- 저장 위치: `outputs/` 아래. 사용자가 지정한 로컬 폴더가 있으면 그곳에도 복사.

## 프로젝트
- 이름: <프로젝트 이름>
- 목적: <한 문장>
- 데이터 위치: <경로>
- 계산 환경: <conda env / venv 이름>, R 필요 여부
- 도메인 용어집: <용어=정의>

## 검증 명령
- `python -m sciharness.cli doctor`
