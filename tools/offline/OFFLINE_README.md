# open-science 오프라인 설치

인터넷이나 npm 이 막힌 PC 에서 OpenCode(2 또는 1.x) + open-science 하네스를 설치하는 방법이다. 관리자 권한은 필요 없다.

## 1. 번들 만들기 (인터넷이 되는 PC, 1회)
```powershell
git clone https://github.com/eljja/open-science; cd open-science
python -m pip install httpx                      # 빌더 의존성
python tools\offline\build_bundle.py --platform windows-x64 --py 3.11 --opencode both --models --zip
```
- OpenCode 바이너리는 npm **레지스트리에서 직접** 내려받는다(npm 명령 불필요). 패키지의 sha512 무결성 값으로 검증한다.
- `--py` 는 **대상 PC 의 Python 버전**과 같아야 한다(wheel 태그). 대상 PC 가 3.12 면 `--py 3.12`.
- Linux 대상: `--platform linux-x64` (pip 태그 manylinux2014_x86_64 자동).
- V1 이 포함되면 빌드 PC 에서 OpenCode 1.x 를 한 번 실행해 `@opencode-ai/plugin` 의존성(node_modules)을 받아 `v1-deps/opencode-plugin-deps.zip` 으로 묶는다(빌드 PC 와 대상 플랫폼이 같을 때만. 다르면 건너뜀 — 아래 4절).
- 결과: `dist/offline/open-science-offline-windows-x64-py311.zip` (+ `SHA256SUMS.txt`, `manifest.json`).

번들 구성 (2026-11-17 빌드 실측: 170개 파일, 567 MB, ZIP 293 MB)
| 폴더 | 내용 |
|---|---|
| `bin/opencode2/` | OpenCode 2.3.0 (`@opencode/cli-windows-x64`) |
| `bin/opencode1/` | OpenCode 1.19.5 (`opencode-windows-x64`) |
| `wheels/` | sciharness + 의존성 71개 + pip (72개 wheel, `pip --no-index` 로 전부 해석됨) |
| `v1-deps/` | `@opencode-ai/plugin` 1.19.5 node_modules ZIP (12.4 MB, 파일 3,668개) |
| `models/` | models.dev 카탈로그 스냅샷(V1 `OPENCODE_MODELS_PATH`) |
| `kit/` | 하네스 키트(이 저장소) |

## 2. 대상 PC 에서 설치 (오프라인)
1. ZIP 을 옮겨 압축 해제.
2. PowerShell:
```powershell
cd open-science-offline-windows-x64-py311
powershell -ExecutionPolicy Bypass -File .\install_offline.ps1 -Project D:\research\myproj               # OpenCode 2
powershell -ExecutionPolicy Bypass -File .\install_offline.ps1 -Project D:\research\myproj -Target opencode-v1
```
3. 실행: `& D:\research\myproj\.opencode\opencode-offline.ps1`

설치 스크립트 순서: 체크섬 검증 → Python 확인 → `%LOCALAPPDATA%\open-science\venv` 생성(ensurepip 가 없으면 번들 pip wheel 로 부트스트랩) → wheel 오프라인 설치(`pip --no-index`) → OpenCode 바이너리 배치 → 키트 복사 → 모델 카탈로그 복사 → `install.py --offline` → (V1) 플러그인 의존성 배치 → 실행기 생성.
Linux/macOS: `./install_offline.sh /path/to/project [opencode|opencode-v1] [python3.11]`.

## 3. 오프라인 모드에서 달라지는 점 (`install.py --offline`)
| 항목 | 동작 |
|---|---|
| scholar MCP(문헌 검색·DOI 검증) | 비활성(V2 `disabled: true`, V1 `enabled: false`). AGENTS.md 에 "인용은 제공된 문헌만, 미검증 표시" 규칙 추가 |
| OpenCode 업데이트 확인 | V1: `autoupdate: false` + `OPENCODE_DISABLE_AUTOUPDATE=1`. V2: 전역 설정 `"update": "disable"`(설치 시 `-SetGlobalNoUpdate`) |
| 모델 카탈로그 | V1: `OPENCODE_DISABLE_MODELS_FETCH=1`, 번들 스냅샷이 있으면 `OPENCODE_MODELS_PATH` 지정 |
| LSP 자동 다운로드 | `OPENCODE_DISABLE_LSP_DOWNLOAD=1` |
| 하네스 플러그인 | 외부 npm 패키지를 쓰지 않음(`node:` 내장 모듈만) |
| science-kernel·memory MCP | 로컬 Python 만 사용 — 변화 없음 |

## 4. OpenCode 1.x 의 npm 설치 문제와 대응
OpenCode 1.x 는 시작할 때마다 `.opencode/` 와 전역 설정 폴더(`~/.config/opencode`)에 `@opencode-ai/plugin` 을 npm 으로 설치하려 한다(v1.19.5 `config/config.ts` → `Npm.install`). 백그라운드 작업이라 실패해도 실행은 되지만, **폐쇄망에서는 명령마다 약 71–74초 지연**이 생긴다(실측, 아래 표).
`node_modules` 가 있고 `package.json` 의 의존성이 `package-lock.json` 에 모두 잠겨 있으면 설치를 건너뛰므로, 설치 스크립트가 번들의 `v1-deps` ZIP 을 두 폴더에 펼친다. 이미 `package.json` 이 있는 폴더는 덮어쓰지 않고 경고만 낸다(수동 병합).
OpenCode 2 는 이 단계가 없다(실측: 프로젝트에 `node_modules` 를 만들지 않음).

| 조건 (네트워크 차단, OpenCode 1.19.5) | debug config | mcp list | agent list | 의존성 경고 |
|---|---|---|---|---|
| 의존성 없음 | 71.6 s | 73.8 s | 71.3 s | 2건 |
| 번들 의존성 배치 | 1.4 s | 3.7 s | 1.1 s | 0건, package-lock 변화 없음 |

## 5. 사내 LLM 연결 (OpenAI 호환 엔드포인트)
두 버전 모두 OpenAI 호환 provider 패키지가 바이너리에 들어 있어 추가 설치가 필요 없다(네트워크 차단 상태에서 모의 엔드포인트로 실측).

OpenCode 2 (`opencode.jsonc`):
```jsonc
{
  "providers": {
    "company": {
      "name": "사내 LLM",
      "env": ["COMPANY_LLM_KEY"],
      "package": "@opencode/ai/providers/openai-compatible",
      "settings": { "baseURL": "https://llm.company.local/v1" },
      "models": { "model-id": { "name": "사내 모델" } }
    }
  }
}
```
OpenCode 1.x (`opencode.json`):
```json
{
  "provider": {
    "company": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "사내 LLM",
      "options": { "baseURL": "https://llm.company.local/v1", "apiKey": "{env:COMPANY_LLM_KEY}" },
      "models": { "model-id": { "name": "사내 모델", "tool_call": true } }
    }
  },
  "model": "company/model-id"
}
```
사내 프록시/인증서: `HTTPS_PROXY`, `NO_PROXY=localhost,127.0.0.1,::1`, `NODE_EXTRA_CA_CERTS=<사내 CA PEM>`.
도구 호출(function calling)을 지원하는 모델이어야 하네스 MCP 도구를 쓸 수 있다.

## 6. 검증
```powershell
$VPY = "$env:LOCALAPPDATA\open-science\venv\Scripts\python.exe"
$KIT = "$env:LOCALAPPDATA\open-science\kit"
& $VPY -m sciharness.cli doctor
# 설정·에이전트·스킬·MCP 연결 (실제 OpenCode)
& $VPY "$KIT\tests\test_opencode_real.py" --opencode "$env:LOCALAPPDATA\open-science\bin\opencode1\opencode.exe" --project D:\research\myproj
# 모의 LLM 으로 한 턴 실행: 시스템 프롬프트 대체·훅 주입·MCP 도구 왕복·계보 기록 (LLM 키 불필요)
& $VPY "$KIT\tests\test_e2e_mock_llm.py" --opencode "$env:LOCALAPPDATA\open-science\bin\opencode2\opencode.exe" --python $VPY --offline
```
2026-11-17 실측(OpenCode 2.3.0·1.19.5, 네트워크 차단, 격리 홈): `test_opencode_real.py` V1 10/10, `test_e2e_mock_llm.py` V1 9/9 · V2 9/9.
