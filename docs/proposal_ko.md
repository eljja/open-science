# OpenCode를 Claude Science급으로 동작시키는 하네스 설계와 구현 (open-science v0.2)

| 항목 | 내용 |
|---|---|
| 작성 | 2026-11-12 · v0.1 / 2026-11-17 · v0.2 (OpenCode 1.x, 오프라인 설치, 실기 검증) |
| 목적 | Claude.ai·Claude Code·Codex·OpenCode에서 Claude Science와 같은 동작(지속 커널 계산, 출판 품질 그림·개념도, 검증된 인용, 논문급 글)을 재현. **주 대상은 OpenCode 2** |
| 산출물 | 하네스 키트 `science-harness/`(→ GitHub `eljja/open-science`), 본 보고서, 그림 5종, 비교 데이터, 데이터 뷰어 |
| 결론 | GUI 앱을 새로 만들지 말고 **지시문·스킬·MCP·플러그인 훅을 주입하는 팩**으로 간다. OpenCode 2의 primary 에이전트 시스템 프롬프트 교체 + 플러그인 훅 + Python MCP 서버 3종으로 핵심 동작을 구현했다. 자동 테스트 82/82를 통과했고, **실제 OpenCode 2.3.0·1.19.5 바이너리**에서 모의 LLM으로 한 턴을 돌려 프롬프트 대체·훅 주입·MCP 도구 왕복·계보 기록을 확인했다(각 9/9). 인터넷·npm 없는 PC용 오프라인 번들(293 MB ZIP)을 제공한다 |

## 요약
- **동작의 원천은 GUI가 아니라 규율이다.** Claude Science 의 차별점은 (1) 결과 충실성 규칙, (2) 지속 커널과 산출물 계보, (3) 그림을 저장한 뒤 눈으로 확인하는 render-then-verify, (4) 실존이 확인된 인용만 쓰는 문헌 규칙, (5) 메모리 회상·스킬 탐색 블록의 자동 주입, (6) 독립 트랙 위임과 deviations 감사다. 이 여섯 가지는 텍스트 지시 + 도구 + 훅으로 옮길 수 있다.
- **공개 대안 16종 비교**(그림 2): GUI 워크벤치 7종의 파일 수 중앙값은 3.6k로 스킬 팩(1.3k)의 약 3배다. 별 수 1·2위는 스킬 팩(56.7k, 56.4k)이고 GUI 최고는 5.5k다. 런타임과 무관하게 행동을 **강제**하는 장치(미검토 그림 차단, 회상 주입, 압축 보존 규칙)를 체계적으로 갖춘 저장소는 없었다.
- **OpenCode 2 구현**(그림 1): `.opencode/agents/science.md`의 본문이 제공자 기본 프롬프트를 대체한다. 플러그인의 `prompt`/`context`/`compaction`/`tool.execute.after` 훅이 Claude Science의 주입 블록을 재현한다. MCP 서버 `science-kernel`·`scholar`·`memory`가 계산·문헌·기억을 맡는다.
- **검증**(7절): 자동 테스트 82/82(MCP 스모크 14, 설치기 59, 훅 9). 실제 OpenCode 1.19.5 설정 로딩 10/10. 모의 LLM 종단 간 테스트 V1 9/9, V2 9/9(네트워크 차단·격리 홈). 실제 LLM으로 장시간 작업, 그림 검토 게이트·압축 훅의 실기 동작, Codex·Claude Code 실기 실행은 **미검증**.
- **오프라인 설치**(6.2절): OpenCode 바이너리를 npm 레지스트리에서 직접 받아(sha512 검증) Python wheel 72개, V1 플러그인 의존성, 모델 카탈로그와 함께 묶는다. OpenCode 1.x는 폐쇄망에서 시작할 때마다 npm 설치를 시도해 명령당 약 72초가 지연되는데, 번들 의존성을 미리 배치하면 1–4초로 줄어든다(실측).

## 1. Claude Science 동작의 분해와 이식 방법

| Claude Science 동작 | 메커니즘 | OpenCode 구현 | 상태 |
|---|---|---|---|
| 결과를 도구로 만든다, 연구 노트 문체 | 시스템 프롬프트 | science 에이전트 본문 1·2절 | 작성 |
| 보고하는 수치는 실행 출력·파일에서만 | 시스템 프롬프트 + 계보 | 3절 + `artifact_lineage` | 작성·테스트 |
| 지속 Python 커널 | 커널 도구 | `science-kernel.python_exec` (Jupyter, 세션별) | 테스트 |
| 저장한 그림을 눈으로 확인 | `view_image` + 강제 | `view_image`(크롭) + 미검토 목록 + context 훅 경고 | 테스트(훅 로직) |
| 산출물 버전·해시·생성 셀 | artifact 저장소 | `artifact_save`(불변 사본, sha256, producing_cells) | 테스트 |
| `[Memory]` 회상 주입 | 메모리 DB + 주입 | `memory` MCP + prompt 훅 | 테스트(훅 로직) |
| `[skill_discovery]` 주입, `search_skills` | 스킬 색인 | BM25 어휘 검색 + prompt 훅 | 테스트 |
| 실존 인용만 | 문헌 API | `scholar.doi_resolve`/`verify_citations` | 오프라인 오류 처리만 테스트 |
| 계획 → 승인 | 계획 파일 | `plan-and-delegate` 스킬, `/plan` | 작성 |
| 독립 트랙 위임 + deviations | 서브에이전트 | 5종 + 출력 계약 | 작성 |
| 압축 후에도 이어가기 | frame 메모장 + 압축 규칙 | `.science/frame.md` + compaction 훅 | 작성 |
| 안전(외부 텍스트=데이터, 비밀값, 파괴적 작업) | 프롬프트 + 권한 | 10절 + permissions(ask) | 작성 |

## 2. 기존 GitHub 시도와의 비교

![그림 2. 공개 Claude Science 대안 16종. (a) 파일 수 대비 별 수: 별 수 1·2위는 스킬 팩이다. (b) 9개 기능 축 커버리지. ● 명시 지원, '부분', · 언급 없음. README 를 자동 추출해 분류한 결과이며 실행 검증이 아니다. 데이터: data/github_비교_기능매트릭스.csv](figures/fig02_github_비교.png)

| 저장소 | 범주 | 파일 | 별 | 라이선스 | 커널 | 계보 | 그림 | 논문 | 인용 | 위임 | 메모리 | Win | 다중런타임 | 합 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| aipoch/open-science | GUI/웹 워크벤치 | 11,417 | 5,510 | Apache-2.0 | · | ● | △ | ● | △ | ● | · | ● | ● | 12 |
| synthetic-sciences/openscience | GUI/웹 워크벤치 | 7,247 | 4,366 | Apache-2.0 | ● | △ | △ | △ | △ | ● | · | ● | · | 10 |
| ai4s-research/open-science | GUI/웹 워크벤치 | 1,119 | 2,087 | NOASSERTION | ● | ● | ● | ● | △ | ● | ● | ● | ● | 17 |
| delibae/claude-prism | GUI/웹 워크벤치 | 254 | 1,848 | MIT | · | ● | △ | ● | · | △ | · | ● | · | 8 |
| xuzhougeng/wisp-science | GUI/웹 워크벤치 | 3,608 | 1,069 | AGPL-3.0 | ● | ● | △ | ● | △ | ● | ● | ● | ● | 16 |
| PKU-YuanGroup/OpenAI4S | GUI/웹 워크벤치 | 6,379 | 662 | MIT | ● | ● | ● | △ | △ | ● | ● | △ | ● | 15 |
| runcell-ai/runcell-science | GUI/웹 워크벤치 | 886 | 25 | Apache-2.0 | ● | △ | △ | · | · | △ | · | · | ● | 7 |
| K-Dense-AI/scientific-agent-skills | 스킬 라이브러리 | 3,497 | 56,730 | MIT | · | △ | ● | ● | △ | △ | · | △ | ● | 10 |
| Imbad0202/academic-research-skills | 스킬 라이브러리 | 3,326 | 56,356 | NOASSERTION | · | ● | ● | ● | ● | ● | · | △ | △ | 12 |
| google-deepmind/science-skills | 스킬 라이브러리 | 362 | 3,445 | Apache-2.0 | · | · | · | · | · | · | · | · | △ | 1 |
| K-Dense-AI/claude-scientific-writer | 스킬 라이브러리 | 2,229 | 2,567 | MIT | · | △ | ● | ● | △ | ● | · | · | · | 8 |
| Boom5426/Nature-Paper-Skills | 스킬 라이브러리 | 420 | 667 | MIT | · | △ | ● | ● | ● | ● | · | △ | ● | 12 |
| ai4s-research/ai4s-skills | 스킬 라이브러리 | 137 | 268 | MIT | · | ● | ● | ● | △ | △ | · | · | ● | 10 |
| openags/paper-search-mcp | MCP 서버 | 146 | 3,048 | MIT | · | △ | · | · | · | · | · | · | ● | 3 |
| datalayer/jupyter-mcp-server | MCP 서버 | 502 | 1,323 | BSD-3-Clause | ● | · | △ | · | · | · | · | △ | ● | 6 |
| K-Dense-AI/claude-skills-mcp | MCP 서버 | 76 | 411 | Apache-2.0 | · | · | · | · | · | · | · | · | ● | 2 |

(●=명시, △=부분, ·=언급 없음. 합 = 9축 × 0–2점. 2026-11-11 GitHub API 메타데이터 + README 자동 분류.)

**읽는 법.** 범주별 커버리지 합의 중앙값은 GUI 12, 스킬 팩 10, MCP 서버 3이다. 가장 넓은 것은 사용자 포크의 원본 `ai4s-research/open-science`(17)로, OpenCode 2 사이드카를 내장한 Tauri 앱이다. 우리 팩은 OpenCode 프로젝트 설정(`.opencode/`)으로 설치되므로 이 앱 안에서도 그대로 쓸 수 있다(단, 앱이 프로젝트 폴더의 `.opencode/`를 읽는지는 실기 확인 필요).

### 2.1 흡수한 요소

| 출처 | 아이디어 | 우리 쪽 구현 |
|---|---|---|
| ai4s-research/open-science | 리뷰어: 읽기 전용, 근거 없으면 침묵, 최대 8개, "옳다"고 단정 금지 | `reviewer` 서브에이전트 |
| ai4s-research/open-science | `present_artifact`: 도구 성공 없이는 "표시했다" 금지 | 시스템 프롬프트 3절 |
| ai4s-research/ai4s-skills | 수치 진본성 라벨 measured/simulated/illustrative | 시스템 프롬프트, `artifact_save(data_status)` |
| Imbad0202/academic-research-skills | 단계별 무결성 게이트 | `scientific-writing` G0–G4 |
| Boom5426/Nature-Paper-Skills | 섹션별 작성 계약, 방어적 문체·AI 문체 제거 | `scientific-writing` |
| Boom5426/Nature-Paper-Skills, PKU-YuanGroup/OpenAI4S | 설치기 해시 매니페스트, 백업, dry-run | `tools/install.py` |
| xuzhougeng/wisp-science | 증거 캡슐(원고 리비전 동결) | `capsule_freeze` |
| K-Dense-AI/claude-skills-mcp | 스킬 검색 도구 | `memory.search_skills` + prompt 훅 |
| synthetic-sciences/openscience | 흡수한 외부 스킬의 출처·라이선스 명시 | 외부 스킬 가져올 때 규칙(로드맵) |
| K-Dense-AI/claude-scientific-writer | 다차원 동료평가 체크리스트 | `reviewer` 확인 순서 6항목 |
| datalayer/jupyter-mcp-server | 커널 MCP 패턴 | 자체 경량 구현(노트북 파일 없이 세션 커널) |

## 3. 배포 형태 결정: Windows GUI 앱 vs 지시문 주입

| 기준 | 자체 GUI 앱 | 주입형 팩(채택) |
|---|---|---|
| 동작 품질의 원천 | UI 와 무관 | 지시·스킬·도구·훅 = 품질의 원천 |
| 유지비 | 큼(포크의 데스크톱 앱만 777개 파일, 진행 기록 622KB) | 작음(Python 패키지 + Markdown) |
| 런타임 이식성 | 한 앱에 묶임 | OpenCode / Claude Code / Codex / Claude.ai |
| Windows | 설치기·서명·업데이트 직접 관리 | OpenCode 가 담당, 팩은 Python |
| GUI 가 필요할 때 | — | OpenCode Desktop 또는 Open Science Desktop 재사용 |

**권고.** 1단계로 팩을 완성하고 실기로 검증한다. GUI 가 꼭 필요하면 새로 만들지 말고 기존 GUI 를 재사용한다. 그래도 부족한 것은 산출물·계보를 보는 얇은 로컬 뷰어(HTML) 정도로 한정한다.

## 4. 아키텍처

![그림 1. OpenCode 중심 하네스 5계층. ① 런타임, ② 텍스트 주입(science 시스템 프롬프트, 프로젝트 AGENTS.md, 스킬 10종, 서브에이전트 5종, 명령 8종), ③ 플러그인 훅, ④ Python MCP 서버 3종, ⑤ 로컬 상태·산출물. 강제 상태(미검토 그림, 계보)는 MCP 서버와 공용 Python 모듈이 기록하므로 Claude Code·Codex 훅도 같은 상태를 쓴다.](figures/fig01_하네스_구조.png)

### 4.1 OpenCode 2 연결 지점 (공식 문서 기준, 2026-11 확인)
- **에이전트**: `.opencode/agents/<id>.md`, frontmatter `description`, `mode: primary|subagent`, `permissions: [{action, resource, effect}]`. 비어 있지 않은 본문은 그 에이전트의 제공자 기본 프롬프트를 대체하고, 프로젝트 지시문·스킬 안내는 그 뒤에 덧붙는다. `default_agent: "science"`.
- **MCP**: `mcp.servers.<이름> = {type: "local", command: [...], environment: {...}}`. 이미지 반환이 모델에 그대로 가도록 `science-kernel`은 `codemode: false`.
- **스킬**: `.opencode/skills/<id>/SKILL.md` (`.claude/skills`, `.agents/skills`도 탐색).
- **명령**: `.opencode/commands/*.md`, 본문 = 프롬프트 템플릿, `$ARGUMENTS`.
- **플러그인**: `.opencode/plugins/` 자동 로드, V2 `export default { id, setup(ctx) }`. `ctx.session.hook("prompt"|"context"|"compaction")`, `ctx.tool.hook("execute.after")`.
- **지시문**: V2 는 `AGENTS.md` 만 인식(CLAUDE.md 폴백 없음).
- V1 필드(`agent`, `prompt`, `tools`, `permission`, `maxSteps`)는 폐기. 플러그인 V1 API 는 V2 에서 실행되지 않으므로 같은 파일에 V1 `server()` 폴백을 함께 두었다(미검증).

### 4.2 Claude Science 주입 블록 ↔ OpenCode 훅

| 블록 | 생성 | 주입 시점 |
|---|---|---|
| `[Memory]` | `sciharness.hooks` → 메모리 검색(한국어 2-gram + 영문 단어, 희소 토큰 가중) | prompt 훅에서 계산 → context 훅에서 system 에 추가 |
| `[skill_discovery]` | SKILL.md frontmatter BM25 | 같음 |
| `[figure_review_pending]` | `python_exec` 가 `outputs/**/figures/*.png` 생성 시 자동 등록, `view_image` 가 해제 | 매 모델 호출(context 훅) |
| `[frame]` | `.science/frame.md` 끝 1,500자 | 매 모델 호출 |
| 압축 보존 규칙 | 고정 문구 | compaction 훅 |
| 계보 | 모든 도구 실행 | tool.execute.after → `.science/lineage.jsonl` |

![그림 3. (a) 한 턴의 작업 루프와 훅 개입 지점. 검증에서 문제가 나오면 실행으로 돌아간다. (b) 논문급 글쓰기 게이트 G0–G4. 리뷰 지적은 대응표와 함께 초안으로 되돌린다.](figures/fig03_턴루프_논문게이트.png)

## 5. 구성요소

### 5.1 MCP 서버 (Python, `sciharness` 패키지, mcp SDK 1.x·2.x 호환)

| 서버 | 도구 | 비고 |
|---|---|---|
| science-kernel | `python_exec`, `kernel_list`, `kernel_restart`, `view_image`, `artifact_save`, `artifact_list`, `artifact_lineage`, `capsule_freeze` | Jupyter 커널(세션별 상태 유지), 출력 6,000자 초과 시 파일로 분리, 인라인 그림 미리보기 반환, 셀 코드 `.science/cells/` 보관 |
| scholar | `crossref_search`, `openalex_search`, `arxiv_search`, `pubmed_search`, `doi_resolve`, `verify_citations` | OpenAlex 는 `OPENALEX_API_KEY` 없으면 건너뜀. 네트워크 실패 시 "검증되지 않음" 오류 반환 |
| memory | `memory_search`, `memory_read`, `memory_write`, `memory_replace`, `memory_remove`, `search_skills` | SQLite, entity(profile / project:<이름>), evidence 태그, 민감정보 패턴 거부 |

### 5.2 스킬·서브에이전트·명령
- 스킬 10종: scientific-figures, schematic-diagrams, figure-review, scientific-writing(템플릿 3종), literature-review, data-analysis, report-html, data-viewer, plan-and-delegate, skill-creator.
- 서브에이전트 5종: reviewer(읽기 전용), figure-critic(읽기 전용), literature-scout, data-analyst, section-writer. 모두 `## 결과` + `## deviations` 출력 계약. 서브에이전트의 추가 위임은 금지.
- 명령 8종: `/plan`, `/figure-check`, `/review`, `/lit-review`, `/report`, `/paper`, `/remember`, `/frame`.

### 5.3 그림·개념도
- `sciharness.figures`: `apply_figure_style()`(한국어 글꼴 자동, 3단 글자 크기, CVD 안전 팔레트, 주인공·비교·경보 색), `save_figure()`(PNG+SVG, 텍스트 겹침 검사, 패널 크롭 좌표, 그림 뒤 데이터 CSV, 사이드카 JSON), `panel_letter()`.
- `sciharness.schematic.Diagram`: 계층·상자·화살표 DSL. 그림 1·3 이 이 모듈로 그려졌다.

![그림 5. science-kernel MCP 의 `python_exec` 로 그린 데모 그림(설명용 합성 데이터). (a) 8회 반복(회색)과 모형(남색). (b) 두 조건, 군당 n=12, 가로선=중앙값. 스타일 적용, 겹침 검사, `view_image` 크롭 확인, `artifact_save` 2회 버전, 계보 조회까지 스모크 테스트에서 수행.](figures/fig05_MCP커널_데모.png)

### 5.4 컨텍스트 예산

![그림 4. 항상 로드되는 텍스트(시스템 프롬프트 6,154자 등 합계 8,855자)와 호출 시에만 로드되는 스킬 본문(합계 11,199자, 중앙값 850자). 문자 수 측정값이며 토큰 수는 모델 토크나이저에 따라 다르다. 데이터: data/컨텍스트_예산_문자수.csv](figures/fig04_컨텍스트_예산.png)

## 6. 다른 런타임 어댑터 (`tools/install.py --target ...`)

| 런타임 | 상시 지시 | 스킬 | 서브에이전트 | MCP | 강제 장치 |
|---|---|---|---|---|---|
| OpenCode 2 (주) | `.opencode/agents/science.md` 본문 + `AGENTS.md`(설정) | `.opencode/skills/` | `.opencode/agents/*.md` | `opencode.jsonc` `mcp.servers` | `.opencode/plugins/science-harness` |
| OpenCode 1.x | 같음(V1 frontmatter `permission` 맵) | `.opencode/skills/` | `.opencode/agents/*.md` | `opencode.json` `mcp.<이름>` | `.opencode/plugins/science-harness.ts` (V1 훅) |
| Claude Code | `CLAUDE.md`(핵심+설정) | `.claude/skills/` | `.claude/agents/*.md` | `.mcp.json` | `.claude/settings.json` hooks → `python -m sciharness.hooks claude <Event>` (Stop 차단 포함) |
| Codex | `AGENTS.md`(핵심+설정) | `.agents/skills/` | `.codex/agents/*.toml` | `.codex/config.toml` | `.codex/hooks.json` + `[features] hooks=true` |
| Claude.ai | 프로젝트 지침(변환본) | 스킬 ZIP 업로드 | — | 원격 배포 시 사용자 지정 커넥터 | 없음(규율은 지침에 의존) |

### 6.1 OpenCode 1.x 지원 (`--target opencode-v1`)
V1 공식 문서(`opencode.ai/v1/docs`), `@opencode-ai/plugin` 1.19.5 타입 정의, OpenCode v1.19.5 소스로 형식을 확인했다.

| 항목 | OpenCode 2 (`--target opencode`) | OpenCode 1.x (`--target opencode-v1`) |
|---|---|---|
| 설정 파일 | `opencode.jsonc` | `opencode.json` |
| MCP | `mcp.servers.<이름>`, `timeout{execution}`, `codemode` | `mcp.<이름>`, `enabled: true`, `timeout`(ms 숫자) |
| 권한 | `permissions: [{action, resource, effect}]` | `permission: {bash: {"git push *": "ask"}, edit: "deny", task: "deny"}` |
| 에이전트 | `.opencode/agents/*.md` 본문 = 시스템 프롬프트(기본 프롬프트 대체) | 같음 — v1.19.5 `llm/request.ts` 에서 `agent.prompt ? [agent.prompt] : SystemPrompt.provider(model)` 확인 |
| 플러그인 | `.opencode/plugins/science-harness/index.ts`, `export default {id, setup(ctx)}` | `.opencode/plugins/science-harness.ts`, `export const ScienceHarness = async (input) => hooks` |
| 회상·탐색 주입 | `session.hook("prompt")` → `session.hook("context")` | `chat.message` → `experimental.chat.system.transform`(system: string[]) |
| 압축 | `session.hook("compaction")` | `experimental.session.compacting`(output.context) |
| 계보·그림 등록 | `tool.hook("execute.after")` | `tool.execute.after`(input.args.filePath) |
| 지시문 | `AGENTS.md` 만 | `AGENTS.md`(없으면 `CLAUDE.md`) |

스킬·명령·서브에이전트 본문·MCP 서버·공용 Python 훅은 두 버전이 같다. V2 가 설치된 폴더에 V1 을 설치하면 설치기가 건너뛴다(테스트됨).

OpenCode 와 Codex 를 한 폴더에 함께 설치하면 핵심 규율이 `AGENTS.md`에 들어가므로, 설치기가 science 에이전트 본문을 "AGENTS.md를 따르라"는 안내문으로 바꿔 중복을 막는다(테스트됨).

### 6.2 오프라인 설치 (인터넷·npm 없는 PC)
인터넷 PC에서 `tools/offline/build_bundle.py`로 번들을 만들고, 대상 PC에서 `install_offline.ps1`(또는 `.sh`)를 실행한다. 관리자 권한은 필요 없다. 자세한 절차는 `tools/offline/OFFLINE_README.md`에 있다.

| 구성 | 내용 (2026-11-17 Windows x64 / Python 3.11 빌드 실측) |
|---|---|
| OpenCode 바이너리 | `@opencode/cli-windows-x64` 2.3.0, `opencode-windows-x64` 1.19.5. npm 레지스트리 tarball을 직접 받아 sha512 무결성 검증(npm 명령 불필요) |
| Python | sciharness + 의존성 71개 + pip = wheel 72개. `pip --no-index --dry-run` 으로 전부 해석됨을 확인 |
| V1 플러그인 의존성 | `@opencode-ai/plugin` 1.19.5 node_modules(파일 3,668개)를 OpenCode 1.x 자신이 설치하게 한 뒤 ZIP(12.4 MB)으로 보관 |
| 모델 카탈로그 | models.dev 스냅샷(V1 `OPENCODE_MODELS_PATH`) |
| 합계 | 170개 파일, 567 MB, ZIP 293 MB, `SHA256SUMS.txt`·`manifest.json` |

`install.py --offline`은 scholar MCP를 끄고(V2 `disabled`, V1 `enabled:false`), V1 `autoupdate:false`를 쓰고, AGENTS.md에 "인용은 제공된 문헌만 쓰고 검증하지 못하면 미검증으로 표시, 패키지 설치 시도 금지" 규칙을 추가하며, `OPENCODE_DISABLE_AUTOUPDATE`·`OPENCODE_DISABLE_MODELS_FETCH`·`OPENCODE_DISABLE_LSP_DOWNLOAD`(+카탈로그가 있으면 `OPENCODE_MODELS_PATH`)를 env 스크립트에 넣는다.

**OpenCode 1.x의 npm 설치.** v1.19.5 소스(`config/config.ts`)를 보면 시작할 때 `.opencode/`와 전역 설정 폴더에 `@opencode-ai/plugin`을 백그라운드로 설치한다. `node_modules`가 있고 `package.json`의 의존성이 `package-lock.json`에 모두 있으면 건너뛴다. 네트워크를 차단하고 측정한 결과는 다음과 같다.

| 조건 (OpenCode 1.19.5, 프록시를 닫힌 포트로) | debug config | mcp list | agent list | 의존성 경고 |
|---|---|---|---|---|
| 의존성 없음 | 71.6 s | 73.8 s | 71.3 s | 2건 |
| 번들 의존성 배치 | 1.4 s | 3.7 s | 1.1 s | 0건 |

OpenCode 2는 프로젝트에 `node_modules`를 만들지 않았다. 두 버전 모두 OpenAI 호환 provider 패키지가 바이너리에 들어 있어, 네트워크를 차단한 상태에서도 사내 OpenAI 호환 엔드포인트(모의 서버로 확인)에 연결된다.

## 7. 검증 결과와 미검증 항목

| 테스트 | 결과 | 범위 |
|---|---|---|
| `tests/smoke_test.py --inproc --offline` | 14/14 | 커널 10(상태 유지, 그림 저장+미리보기, view_image, 버전 2회, 계보, 실패 정직 보고, traceback, 캡슐) + 메모리 4(한국어 검색, 민감정보 거부, 스킬 검색) |
| `tests/test_install.py` | 59/59 | 5개 대상(OpenCode 2·1.x, Claude Code, Codex, Claude.ai) 생성 파일 파싱, 권한, 멱등 재설치, 사용자 수정 보호, 공존 중복 제거, V1/V2 충돌 방지, 오프라인 모드 14건(scholar 비활성, 자동 업데이트 끔, 오프라인 규칙, env 변수, 번들 도구·설치 스크립트 구문) |
| `tests/test_hooks.py` | 9/9 | 회상·탐색 주입, 미검토 그림 Stop 차단 → view_image 후 해제, 무한루프 방지, SessionStart, 계보, 다른 작업 폴더에서 `--root` 기준 스킬 탐색(회귀) |
| `tests/test_opencode_real.py` (OpenCode 1.19.5, 네트워크 차단) | 10/10 | `debug config`: default_agent=science, 에이전트 6, 명령 8, V1 플러그인, MCP 3 / `debug agent science`: 하네스 프롬프트 / `debug skill`: 스킬 10 / `mcp list`: kernel·memory connected, scholar disabled |
| OpenCode 2.3.0 서버 API (`opencode serve`) | 확인 | `/api/agent`: science(primary, 하네스 프롬프트 6,153자)+서브에이전트 5, `/api/skill`: 스킬 10, `/api/mcp`: kernel·memory connected·scholar disabled, `/api/plugin`: `science-harness`(local) active, reviewer `edit deny` |
| `tests/test_e2e_mock_llm.py` V1 / V2 | 9/9 · 9/9 | 실제 바이너리 + 모의 OpenAI 호환 모델 한 턴: 기본 프롬프트 대체, 플러그인 훅의 `[skill_discovery]` 주입, AGENTS.md 포함, MCP 도구 직접 노출, `python_exec` 결과(42) 왕복, 커널 셀·플러그인 도구 계보 기록 |

**실기 검증에서 발견해 고친 것.**
1. 스킬 탐색이 `--root`가 아니라 현재 작업 폴더 기준으로 스킬 폴더를 찾았다. 훅이 다른 폴더에서 호출되면 `[skill_discovery]`가 조용히 비었다. 프로젝트 루트(`--root`, `SCIHARNESS_ROOT`) 기준으로 고치고 회귀 테스트를 추가했다.
2. OpenCode 2.3.0은 MCP 서버의 `codemode` 기본값에서 도구를 `execute`(JavaScript) 안의 `tools.memory.*`로만 노출했다. 프롬프트 설명·V1 동작과 맞추려고 하네스 MCP 3종 모두 `codemode:false`로 설치한다.
3. 계보 기록 시각에 시간대를 붙였다(Python 기록은 로컬 시각, 플러그인 기록은 UTC였다).
4. 오프라인 설치 스크립트: PowerShell 5.1에서 네이티브 명령의 stderr가 예외로 바뀌는 문제(`Invoke-Native`로 종료 코드만 판정), ensurepip가 없는 Python(번들 pip wheel로 부트스트랩), 모델 카탈로그 복사 순서(env 스크립트에 `OPENCODE_MODELS_PATH`가 빠짐).

**미검증(다음 단계).**
1. 실제 LLM으로 장시간 과제: 모의 모델은 도구 호출 형식만 확인한다. 모델이 규율(그림 검증, 인용 검증)을 끝까지 따르는지는 연결한 모델에 달렸다.
2. 그림 검토 게이트(`[figure_review_pending]`)와 압축 훅(compaction)의 실기 동작. 공용 Python 쪽은 테스트했다(test_hooks).
3. scholar 실네트워크 4건(실제 DOI 확인, 가짜 DOI 거부, Crossref 검색, OpenAlex 키 없음 처리).
4. 대상 PC에서 `install_offline.ps1` 전 과정: 이 샌드박스는 중첩 프로세스가 만든 임시 파일에 접근하지 못해 pip 설치 단계를 완주하지 못했다. 체크섬 검증·Python 확인·pip 부트스트랩 시작까지와 각 단계(의존성 해석, `install.py --offline`, V1 의존성 배치, 바이너리 실행)를 따로 확인했다.
5. Codex, Claude Code, Claude.ai 실기 실행.
6. 샌드박스 전용 설정: 커널 테스트에 `JUPYTER_ALLOW_INSECURE_WRITES=1`(사용자 승인, 테스트에서만), OpenCode 2 서버 테스트에 D: 드라이브 PATH 항목 제외(샌드박스가 `D:\Git\cmd\git.exe` 접근을 막아 서버가 500을 반환). 배포 기본값에는 들어가지 않는다.

## 8. 설치와 사용 (Windows PowerShell)
```powershell
git clone https://github.com/eljja/open-science; cd open-science
conda create -n sciharness python=3.11 -y; conda activate sciharness
pip install -e python                       # mcp, jupyter_client, ipykernel, matplotlib, pandas, httpx, markdown
python tools/install.py --doctor
python tools/install.py --target opencode --project D:\research\myproj
npm install -g @opencode/cli                 # OpenCode 2
cd D:\research\myproj; . .\.opencode\sciharness.env.ps1; opencode
```
오프라인 PC: 6.2절의 번들을 만든 뒤 `powershell -ExecutionPolicy Bypass -File .\install_offline.ps1 -Project D:\research\myproj [-Target opencode-v1]`.

설치 확인: `python tests/test_opencode_real.py --opencode <opencode.exe> --project D:\research\myproj`, `python tests/test_e2e_mock_llm.py --opencode <opencode.exe>`(LLM 키 불필요).

첫 확인 순서: `/mcps`에서 서버 3종 connected → "y=sin(x) 그림을 그려 저장하고 검증해" → `outputs/figures/`, `.science/lineage.jsonl`, `artifacts/manifest.jsonl` 생성 여부와 `[figure_review_pending]` 경고가 view_image 후 사라지는지 확인.

## 9. 한계와 로드맵

| 단계 | 내용 | 완료 기준 |
|---|---|---|
| 1 | 팩 v0.1(+OpenCode 1.x 대상), 오프라인 테스트 | 67/67 ✓ |
| 2 (현재) | v0.2: 오프라인 번들, OpenCode 2·1.x 실기 로딩·모의 LLM 종단 간 검증 | 82/82 + 실기 10/10, 9/9, 9/9 ✓ |
| 3 | 실제 LLM 패리티 과제 10개(그림·문헌·논문·위임), 그림 검토 게이트·압축 훅 실기 | 과제별 체크리스트 통과 |
| 4 | 외부 스킬 팩(K-Dense, DeepMind science-skills) 선택적 가져오기(출처·라이선스 명시), Codex/Claude Code 실기 | 동일 과제 런타임 간 비교 |
| 5 | 산출물·계보 로컬 뷰어(HTML), 원격 scholar/memory 배포(Claude.ai 커넥터) | 선택 |

**한계.** 이 하네스는 Claude Science 의 **규율과 도구 표면**을 재현한다. 모델 자체의 능력(장문 추론, 시각 판단 품질)은 OpenCode 에 연결한 모델에 따라 달라진다. 훅 주입은 문맥을 추가할 뿐이고, 모델이 끝까지 따르도록 강제하는 장치는 미검토 그림 경고(OpenCode)와 Stop 차단(Claude Code/Codex)까지다.

## 부록 A. 참고 문서
- OpenCode V2 문서: https://opencode.ai/docs/agents/ , /plugins/ , /build/plugins/server , /mcp-servers/ , /skills/ , /commands/ , /instructions/ , /migrate-v1/
- Codex: https://developers.openai.com/codex/subagents , https://developers.openai.com/codex/config-reference
- Claude Code: https://code.claude.com/docs/en/hooks , /sub-agents , /skills , /plugins
- 비교 저장소 16종: 2절 표(모두 github.com/<저장소>)
