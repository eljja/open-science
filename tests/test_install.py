"""설치기 검증: 임시 프로젝트에 4개 런타임을 설치하고 생성 파일을 JSON/TOML/YAML 로 파싱해 확인한다.
    python tests/test_install.py
"""
import json, re, shutil, sys, tomllib
from pathlib import Path
import yaml
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import install  # noqa: E402

import datetime
proj = HERE / "_install_runs" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
proj.mkdir(parents=True)
res = []
def chk(name, ok, detail=""):
    res.append((name, bool(ok))); print(("✓" if ok else "✗"), name, detail)

def fm(path):
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])

# 1) OpenCode 단독 설치
install.main(["--target", "opencode", "--project", str(proj)])
cfg = json.loads(re.sub(r"^//.*$", "", (proj / "opencode.jsonc").read_text(encoding="utf-8"), flags=re.M))
chk("opencode.jsonc: V2 mcp.servers 3종 + default_agent=science",
    set(cfg["mcp"]["servers"]) == {"science-kernel", "scholar", "memory"} and cfg["default_agent"] == "science")
chk("V2 MCP 3종 codemode=false (직접 호출·이미지 직접 전달)", all(cfg["mcp"]["servers"][n].get("codemode") is False for n in ("science-kernel", "scholar", "memory")))
for f in sorted((proj / ".opencode/agents").glob("*.md")):
    m = fm(f)
    chk(f"OpenCode 에이전트 {f.stem}: V2 frontmatter", m["mode"] in ("primary", "subagent") and isinstance(m["permissions"], list)
        and all({"action", "resource", "effect"} <= set(r) for r in m["permissions"]))
sci = (proj / ".opencode/agents/science.md").read_text(encoding="utf-8")
chk("science 에이전트 본문 = 핵심 프롬프트", "결과 충실성" in sci and len(sci) > 5000, f"{len(sci)}자")
chk("reviewer 읽기 전용(edit deny)", any(r["action"] == "edit" and r["effect"] == "deny" for r in fm(proj / ".opencode/agents/reviewer.md")["permissions"]))
n_sk = len(list((proj / ".opencode/skills").glob("*/SKILL.md"))); chk("스킬 10종 배포", n_sk == 10, n_sk)
chk("스킬 frontmatter name/description", all(fm(p).get("name") and fm(p).get("description") for p in (proj / ".opencode/skills").glob("*/SKILL.md")))
chk("명령 8종", len(list((proj / ".opencode/commands").glob("*.md"))) == 8)
chk("플러그인 배치(.opencode/plugins 자동 로드 위치)", (proj / ".opencode/plugins/science-harness/index.ts").exists())
chk("휴대용 스크립트 동봉", (proj / ".opencode/skills/scientific-figures/scripts/figures.py").exists())
chk("AGENTS.md = 프로젝트 설정만", "사용자 설정" in (proj / "AGENTS.md").read_text(encoding="utf-8") and "결과 충실성" not in (proj / "AGENTS.md").read_text(encoding="utf-8"))

# 2) 재설치: 멱등 + 사용자 수정 보호
(proj / ".opencode/skills/data-analysis/SKILL.md").write_text("---\nname: data-analysis\ndescription: 사용자 수정본\n---\n", encoding="utf-8")
plan = install.Plan(proj, dry=False, force=False); install.install_opencode(plan, sys.executable)
acts = dict((r.split()[0], a) for a, r in plan.log)
chk("재설치: 사용자 수정 파일은 건너뜀", acts.get(".opencode/skills/data-analysis/SKILL.md") == "skip")
chk("재설치: 나머지는 동일(멱등)", sum(a == "same" for a, _ in plan.log) >= 40, sum(a == "same" for a, _ in plan.log))
plan.finish()

# 3) Codex 공존 설치 → 중복 제거
install.main(["--target", "codex", "--project", str(proj)])
t = tomllib.loads((proj / ".codex/config.toml").read_text(encoding="utf-8"))
chk("codex config.toml: TOML + mcp_servers 3종 + hooks", set(t["mcp_servers"]) == {"science-kernel", "scholar", "memory"} and t["features"]["hooks"])
for f in sorted((proj / ".codex/agents").glob("*.toml")):
    a = tomllib.loads(f.read_text(encoding="utf-8"))
    chk(f"codex 에이전트 {f.stem}: name/description/developer_instructions", a["name"] and a["description"] and len(a["developer_instructions"]) > 200)
chk("codex hooks.json 4개 이벤트", set(json.loads((proj / ".codex/hooks.json").read_text(encoding="utf-8"))["hooks"]) == {"SessionStart", "UserPromptSubmit", "PostToolUse", "Stop"})
agm = (proj / "AGENTS.md").read_text(encoding="utf-8")
sci2 = (proj / ".opencode/agents/science.md").read_text(encoding="utf-8")
chk("공존: AGENTS.md 에 핵심 규율 1회", agm.count("## 3. 결과 충실성") == 1)
chk("공존: science 본문은 안내문(중복 없음)", "공존 설치 모드" in sci2 and "## 3. 결과 충실성" not in sci2 and fm(proj / ".opencode/agents/science.md")["mode"] == "primary")

# 4) Claude Code + Claude.ai
install.main(["--target", "claude-code,claude-ai", "--project", str(proj), "--out", str(proj / "dist")])
chk(".mcp.json 3 서버", len(json.loads((proj / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]) == 3)
chk(".claude/settings.json 훅 4개", len(json.loads((proj / ".claude/settings.json").read_text(encoding="utf-8"))["hooks"]) == 4)
chk("Claude Code 에이전트 YAML", all(fm(f)["name"] == f.stem for f in (proj / ".claude/agents").glob("*.md")))
chk("Claude.ai 스킬 ZIP 10개", len(list((proj / "dist/claude-ai/skills").glob("*.zip"))) == 10)

# 5) OpenCode 1.x 설치(별도 폴더) — V1 스키마
p1 = proj.parent / (proj.name + "_v1"); p1.mkdir(parents=True)
install.main(["--target", "opencode-v1", "--project", str(p1)])
c1 = json.loads((p1 / "opencode.json").read_text(encoding="utf-8"))
chk("V1 opencode.json: mcp.<이름> 3종(enabled) + default_agent",
    set(c1["mcp"]) == {"science-kernel", "scholar", "memory"} and all(s.get("enabled") is True for s in c1["mcp"].values())
    and c1["default_agent"] == "science")
chk("V1: V2 전용 키 없음(mcp.servers/permissions/plugins)", "servers" not in c1["mcp"] and "permissions" not in c1 and "plugins" not in c1)
chk("V1 kernel timeout(ms) 숫자", isinstance(c1["mcp"]["science-kernel"]["timeout"], int))
for f in sorted((p1 / ".opencode/agents").glob("*.md")):
    m = fm(f)
    chk(f"V1 에이전트 {f.stem}: permission 맵", m["mode"] in ("primary", "subagent") and isinstance(m["permission"], dict) and "permissions" not in m)
chk("V1 science: bash 맵에 git push ask", fm(p1 / ".opencode/agents/science.md")["permission"]["bash"]["git push *"] == "ask")
chk("V1 reviewer: edit deny + task deny", fm(p1 / ".opencode/agents/reviewer.md")["permission"] == {"edit": "deny", "task": "deny"})
pv1 = (p1 / ".opencode/plugins/science-harness.ts").read_text(encoding="utf-8")
chk("V1 플러그인 단일 파일 + V1 훅 4종", all(h in pv1 for h in ['"chat.message"', '"experimental.chat.system.transform"',
    '"experimental.session.compacting"', '"tool.execute.after"']) and "export const ScienceHarness" in pv1)
chk("V1 스킬 10 · 명령 8", len(list((p1 / ".opencode/skills").glob("*/SKILL.md"))) == 10 and len(list((p1 / ".opencode/commands").glob("*.md"))) == 8)
plan_x = install.Plan(proj, dry=True, force=False); install.install_opencode_v1(plan_x, sys.executable)
chk("V2 설치 폴더에는 V1 설치 건너뜀", any(a == "note" and "OpenCode 2" in r for a, r in plan_x.log) and not any(a == "create" for a, _ in plan_x.log))

# 6) 오프라인 모드(--offline): scholar 비활성 · 자동 업데이트 끔 · 오프라인 규칙 · env 스크립트 · 재설치 멱등
import hashlib, subprocess
def _digest(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*"))
            if p.is_file() and ".science" not in p.parts and "outputs" not in p.parts}
po2, po1 = proj.parent / (proj.name + "_off2"), proj.parent / (proj.name + "_off1")
for d in (po2, po1):
    d.mkdir()
install.main(["--target", "opencode", "--project", str(po2), "--offline"])
install.main(["--target", "opencode-v1", "--project", str(po1), "--offline"])
c2o = json.loads(re.sub(r"^//.*$", "", (po2 / "opencode.jsonc").read_text(encoding="utf-8"), flags=re.M))
c1o = json.loads((po1 / "opencode.json").read_text(encoding="utf-8"))
chk("오프라인 V2: scholar disabled=true, kernel/memory 활성", c2o["mcp"]["servers"]["scholar"].get("disabled") is True
    and not c2o["mcp"]["servers"]["science-kernel"].get("disabled") and not c2o["mcp"]["servers"]["memory"].get("disabled"))
chk("오프라인 V1: scholar enabled=false + autoupdate=false", c1o["mcp"]["scholar"].get("enabled") is False and c1o.get("autoupdate") is False)
for nm, d in (("V2", po2), ("V1", po1)):
    ag = (d / "AGENTS.md").read_text(encoding="utf-8")
    chk(f"오프라인 {nm}: AGENTS.md 오프라인 규칙 1회", ag.count("## 오프라인 환경") == 1 and "미검증" in ag)
    env_ps = (d / ".opencode/sciharness.env.ps1").read_text(encoding="utf-8-sig")
    chk(f"오프라인 {nm}: env 스크립트 OPENCODE_* 3종 + MODELS_PATH 조건부", all(k in env_ps for k in
        ["OPENCODE_DISABLE_AUTOUPDATE", "OPENCODE_DISABLE_MODELS_FETCH", "OPENCODE_DISABLE_LSP_DOWNLOAD", "OPENCODE_MODELS_PATH"]))
before = _digest(po1)
install.main(["--target", "opencode-v1", "--project", str(po1), "--offline"])
chk("오프라인 재설치 멱등(파일 변화 없음)", _digest(po1) == before)
chk("온라인 설치에는 오프라인 규칙 없음", "## 오프라인 환경" not in (proj / "AGENTS.md").read_text(encoding="utf-8")
    and not json.loads(re.sub(r"^//.*$", "", (proj / "opencode.jsonc").read_text(encoding="utf-8"), flags=re.M))["mcp"]["servers"]["scholar"].get("disabled"))
install.OFFLINE = False

# 7) 오프라인 번들 도구: build_bundle 구문 · 설치 스크립트 구문/인코딩 · V1 의존성 배치 로직
import ast
off = HERE.parent / "tools" / "offline"
bsrc = (off / "build_bundle.py").read_text(encoding="utf-8"); ast.parse(bsrc)
chk("build_bundle: npm 무결성 검증 + pip wheel + V1 의존성 준비", all(k in bsrc for k in ["integrity", '"download"', "prime_v1_deps", "--no-v1-deps", '"pip")']))
raw = (off / "install_offline.ps1").read_bytes()
chk("install_offline.ps1: UTF-8 BOM + CRLF (PowerShell 5.1 한글)", raw[:3] == b"\xef\xbb\xbf" and b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b""))
pst = raw.decode("utf-8-sig")
chk("install_offline.ps1: Invoke-Native + pip 부트스트랩 + V1 의존성(기존 package.json 보존)",
    "function Invoke-Native" in pst and "pip-*.whl" in pst and "opencode-plugin-deps.zip" in pst and "덮어쓰지 않음" in pst)
chk("install_offline.ps1: models.json 을 install.py 전에 복사(OPENCODE_MODELS_PATH 반영)",
    pst.index("models.json") < pst.index("install.py"))
if shutil.which("powershell"):
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
        f"$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('{off / 'install_offline.ps1'}', [ref]$null, [ref]$e); $e.Count"],
        capture_output=True, text=True)
    chk("install_offline.ps1: PowerShell 파서 오류 0", r.stdout.strip().splitlines()[-1:] == ["0"], r.stdout.strip()[-20:])
shs = (off / "install_offline.sh").read_text(encoding="utf-8")
chk("install_offline.sh: pip 부트스트랩 + V1 의존성 + models 선복사", "pip-*.whl" in shs and "opencode-plugin-deps.zip" in shs
    and shs.index("models.json") < shs.index("install.py"))

n = sum(ok for _, ok in res); print(f"\n{n}/{len(res)} passed")
(HERE / "install_results.json").write_text(json.dumps([{"test": a, "ok": b} for a, b in res], ensure_ascii=False, indent=1), encoding="utf-8")
sys.exit(0 if n == len(res) else 1)
