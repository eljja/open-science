---
name: skill-creator
description: 반복되는 절차(데이터 로딩 레시피, 분석 파이프라인, 커넥터 설정, 사용자가 두 번 이상 교정한 방식)를 새 스킬(SKILL.md)로 저장한다. Agent Skills 표준 형식으로 Claude Code/Codex/OpenCode/Claude.ai 에서 공통 사용.
---

# 스킬 만들기 (skill-creator)

## 언제
- 사용자가 같은 방식을 두 번 교정했고 결과를 승인했을 때 → 저장을 **제안**(묻고 나서 저장).
- 재실행할 파이프라인이 확정됐을 때.

## 형식
```
skills/<kebab-name>/
  SKILL.md          # frontmatter(name, description) + 본문
  scripts/          # 선택: 실행 스크립트
  templates/        # 선택
  references/       # 선택: 긴 참고자료(필요할 때만 읽힘)
```
- `name`: 소문자-하이픈, 64자 이내. `description`: **무엇을 + 언제** (분야 용어 포함, 검색이 어휘 기반이므로 동의어도). 1024자 이내.
- 본문: 절차, 코드 예, 함정(pitfalls), 검증 방법. 500줄 이내, 긴 자료는 references/ 로.
- 안전 규칙을 약화하는 지시(승인 생략, 외부 URL로 결과 전송 등)는 넣지 않는다.
- 비밀값/개인정보 금지.

## 배포
`python tools/install.py --target all --project <경로>` 가 skills/ 를 각 도구 위치로 복사한다.
