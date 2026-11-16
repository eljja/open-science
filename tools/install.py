"""open-science harness 설치기 — 하나의 원본(harness/)을 각 런타임 형식으로 변환해 프로젝트에 설치한다.

    python tools/install.py --target opencode --project D:\work\myproj            # 기본 대상: OpenCode 2
    python tools/install.py --target opencode-v1 --project D:\work\myproj         # OpenCode 1.x
    python tools/install.py --target claude-code,codex --project .               # 보조 런타임
    python tools/install.py --target claude-ai --out dist                         # Claude.ai 업로드용 ZIP/지침
    python tools/install.py --target all --project . --dry-run                    # 미리보기
    python tools/install.py --doctor

안전장치(흡수한 관행): 설치 파일 sha256 매니페스트(.science/harness_manifest.json), 사용자가 고친 파일은 덮어쓰기 전에
.science/backup/<시각>/ 로 백업(--force 없으면 건너뜀), --dry-run 미리보기, --doctor 점검.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, re, shutil, subprocess, sys, zipfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
HARNESS = KIT / "harness"
SERVERS = {"science-kernel": "sciharness.mcp_servers.kernel_server",
           "scholar": "sciharness.mcp_servers.scholar_server",
           "memory": "sciharness.mcp_servers.memory_server"}
PORTABLE = {"scientific-figures": ["figures.py"], "schematic-diagrams": ["figures.py", "schematic.py"],
            "report-html": ["report.py"], "data-viewer": ["viewer.py"]}
Q3 = "'" * 3

def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]

def front(text: str):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1); v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                v = [x.strip() for x in v[1:-1].split(",") if x.strip()]
            meta[k.strip()] = v
    return meta, m.group(2)

def yq(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)

class Plan:
    """파일 쓰기 계획: 매니페스트 비교 → 동일/생성/갱신/건너뜀(사용자 수정) 판정, 갱신 전 백업."""
    def __init__(self, project: Path, dry: bool, force: bool):
        self.project, self.dry, self.force = project, dry, force
        self.mf_path = project / ".science" / "harness_manifest.json"
        self.manifest = json.loads(self.mf_path.read_text(encoding="utf-8")) if self.mf_path.exists() else {}
        self.stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log = []

    def write(self, rel: str, data):
        b = data.encode("utf-8") if isinstance(data, str) else data
        dst = self.project / rel
        act = "create"
        if dst.exists():
            cur = dst.read_bytes()
            if cur == b:
                self.log.append(("same", rel)); self.manifest[rel] = sha(b); return
            recorded = self.manifest.get(rel)
            user_edited = recorded is None or sha(cur) != recorded
            if user_edited and not self.force:
                self.log.append(("skip", rel + "  (설치 후 수정됨/외부 파일 — --force 로 덮어쓰기)")); return
            act = "update"
            if not self.dry:
                bk = self.project / ".science" / "backup" / self.stamp / rel
                bk.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(dst, bk)
        self.log.append((act, rel))
        if not self.dry:
            dst.parent.mkdir(parents=True, exist_ok=True); dst.write_bytes(b)
            self.manifest[rel] = sha(b)

    def copytree(self, src: Path, rel_dst: str):
        for p in sorted(src.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                self.write(f"{rel_dst}/{p.relative_to(src).as_posix()}", p.read_bytes())

    def finish(self, verbose: bool = False):
        if not self.dry:
            self.mf_path.parent.mkdir(parents=True, exist_ok=True)
            self.mf_path.write_text(json.dumps(self.manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        for a, r in self.log:
            if verbose or a != "same":
                print(f"  {a:7s} {r}")
        cnt = {k: sum(a == k for a, _ in self.log) for k in ("create", "update", "same", "skip", "note")}
        print(f"  -> 생성 {cnt['create']}, 갱신 {cnt['update']}, 동일 {cnt['same']}, 건너뜀 {cnt['skip']}" + (" (dry-run)" if self.dry else ""))
        return cnt

def core_prompt() -> str:
    return (HARNESS / "prompts" / "science_system.md").read_text(encoding="utf-8")

def project_settings() -> str:
    return (HARNESS / "templates" / "AGENTS.project.md").read_text(encoding="utf-8")

def agents():
    for p in sorted((HARNESS / "agents").glob("*.md")):
        meta, body = front(p.read_text(encoding="utf-8"))
        yield meta, body.strip()

def skills_dirs():
    return [p for p in sorted((HARNESS / "skills").iterdir()) if (p / "SKILL.md").exists()]

def portable_scripts(plan: Plan, rel_skills: str):
    """sciharness 가 설치되지 않은 환경용: 그림/회로도/보고서 모듈 사본을 스킬 scripts/ 에 동봉."""
    src = KIT / "python" / "sciharness"
    for skill, mods in PORTABLE.items():
        for m in mods:
            t = (src / m).read_text(encoding="utf-8").replace("from .figures import", "from figures import")
            plan.write(f"{rel_skills}/{skill}/scripts/{m}", t)

def env_for(project: Path) -> dict:
    return {"SCIHARNESS_ROOT": str(project), "PYTHONIOENCODING": "utf-8",
            "SCIHARNESS_MEMORY_DB": str(Path.home() / ".sciharness" / "memory.db")}

def scaffold(plan: Plan):
    for d in ["outputs/figures", "outputs/report", "outputs/html", "outputs/data", "outputs/interactive", "notes"]:
        plan.write(f"{d}/.gitkeep", "")
    if not (plan.project / ".science/frame.md").exists():
        plan.write(".science/frame.md", "# 세션 메모장\n- 목표:\n- 완료:\n- 다음:\n")
    gi = plan.project / ".gitignore"
    lines = [".science/cells/", ".science/previews/", ".science/outputs/", ".science/artifact_store/", ".science/backup/"]
    cur = gi.read_text(encoding="utf-8") if gi.exists() else ""
    add = [l for l in lines if l not in cur]
    if add:
        new = cur.rstrip("\n") + ("\n" if cur else "") + "# open-science harness\n" + "\n".join(add) + "\n"
        if not plan.dry:
            gi.write_text(new, encoding="utf-8")
        plan.log.append(("update" if cur else "create", ".gitignore"))

# ---------------- OpenCode (주 런타임, V2 스키마) ----------------
def perms_yaml(rules) -> str:
    return "".join(f"  - action: {r['action']}\n    resource: \"{r['resource']}\"\n    effect: {r['effect']}\n" for r in rules)

def install_opencode(plan: Plan, python: str):
    rules = [{"action": "shell", "resource": "git push *", "effect": "ask"},
             {"action": "shell", "resource": "rm -rf *", "effect": "ask"},
             {"action": "shell", "resource": "Remove-Item *", "effect": "ask"}]
    fm = ("---\ndescription: Claude Science 급 과학 계산 에이전트 — 지속 커널, 출판 품질 그림, 문헌 검증, 논문급 글, 계보 기록\n"
          "mode: primary\ncolor: \"#08306B\"\npermissions:\n" + perms_yaml(rules) + "---\n\n")
    plan.write(".opencode/agents/science.md", fm + core_prompt())
    for meta, b in agents():
        rules = [{"action": "subagent", "resource": "*", "effect": "deny"}]
        if meta.get("access") == "read-only":
            rules.insert(0, {"action": "edit", "resource": "*", "effect": "deny"})
        sk = meta.get("skills", [])
        pre = (f"작업을 시작하면 먼저 다음 스킬을 skill 도구로 로드한다: {', '.join(sk)}.\n\n" if sk else "")
        plan.write(f".opencode/agents/{meta['name']}.md",
                   f"---\ndescription: {yq(meta['description'])}\nmode: subagent\npermissions:\n{perms_yaml(rules)}---\n\n{pre}{b}\n")
    for sd in skills_dirs():
        plan.copytree(sd, f".opencode/skills/{sd.name}")
    portable_scripts(plan, ".opencode/skills")
    for c in sorted((HARNESS / "commands").glob("*.md")):
        plan.write(f".opencode/commands/{c.name}", c.read_text(encoding="utf-8"))
    plan.copytree(HARNESS / "opencode" / "plugins" / "science-harness", ".opencode/plugins/science-harness")
    env = env_for(plan.project)
    servers = {}
    for name, mod in SERVERS.items():
        s = {"type": "local", "command": [python, "-m", mod], "environment": env}
        if name == "science-kernel":
            s["codemode"] = False                      # 이미지 결과를 모델에 직접 전달
            s["timeout"] = {"execution": 1800000}      # 장시간 셀 허용(30분)
        servers[name] = s
    cfg = {"$schema": "https://opencode.ai/config.json", "default_agent": "science",
           "mcp": {"servers": servers},
           "permissions": [{"action": "external_directory", "resource": "*", "effect": "ask"}],
           "experimental": {"todo": True}}
    txt = "// open-science harness — OpenCode V2 설정 (tools/install.py 생성)\n" + json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"
    if (plan.project / "opencode.jsonc").exists() and plan.manifest.get("opencode.jsonc") is None:
        plan.write(".opencode/opencode.science.jsonc", txt)
        plan.log.append(("note", "기존 opencode.jsonc 유지 → .opencode/opencode.science.jsonc 를 참고해 병합"))
    else:
        plan.write("opencode.jsonc", txt)
    if not (plan.project / "AGENTS.md").exists():
        plan.write("AGENTS.md", project_settings())
    plan.write(".opencode/sciharness.env.ps1", f'$env:SCIHARNESS_PYTHON = "{python}"\n')
    scaffold(plan)

# ---------------- OpenCode 1.x (V1 스키마) ----------------
def yaml_perm_v1(perm: dict, indent: int = 2) -> str:
    out = ""
    for k, v in perm.items():
        if isinstance(v, dict):
            out += " " * indent + f"{k}:\n" + "".join(" " * (indent + 2) + f"\"{pk}\": {pv}\n" for pk, pv in v.items())
        else:
            out += " " * indent + f"{k}: {v}\n"
    return out

def install_opencode_v1(plan: Plan, python: str):
    """OpenCode 1.x 용: opencode.json(mcp.<이름>, permission 맵, default_agent), 에이전트 permission 맵, V1 플러그인 단일 파일."""
    if plan.manifest.get("opencode.jsonc") or (plan.project / ".opencode/plugins/science-harness/index.ts").exists():
        plan.log.append(("note", "이 폴더에는 OpenCode 2 용 설치가 있음 → V1 설치를 건너뜀(다른 폴더를 쓰거나 V2 파일을 지운 뒤 다시 실행)"))
        return
    sci_perm = {"bash": {"*": "allow", "git push *": "ask", "rm -rf *": "ask", "Remove-Item *": "ask"},
                "external_directory": "ask"}
    fm = ("---\ndescription: Claude Science 급 과학 계산 에이전트 — 지속 커널, 출판 품질 그림, 문헌 검증, 논문급 글, 계보 기록\n"
          "mode: primary\ncolor: \"#08306B\"\npermission:\n" + yaml_perm_v1(sci_perm) + "---\n\n")
    plan.write(".opencode/agents/science.md", fm + core_prompt())
    for meta, b in agents():
        perm = {"task": "deny"}
        if meta.get("access") == "read-only":
            perm = {"edit": "deny", "task": "deny"}
        sk = meta.get("skills", [])
        pre = (f"작업을 시작하면 먼저 다음 스킬을 skill 도구로 로드한다: {', '.join(sk)}.\n\n" if sk else "")
        plan.write(f".opencode/agents/{meta['name']}.md",
                   f"---\ndescription: {yq(meta['description'])}\nmode: subagent\npermission:\n{yaml_perm_v1(perm)}---\n\n{pre}{b}\n")
    for sd in skills_dirs():
        plan.copytree(sd, f".opencode/skills/{sd.name}")
    portable_scripts(plan, ".opencode/skills")
    for c in sorted((HARNESS / "commands").glob("*.md")):
        plan.write(f".opencode/commands/{c.name}", c.read_text(encoding="utf-8"))
    plan.write(".opencode/plugins/science-harness.ts",
               (HARNESS / "opencode-v1" / "plugins" / "science-harness.ts").read_text(encoding="utf-8"))
    env = env_for(plan.project)
    mcp = {}
    for name, mod in SERVERS.items():
        s = {"type": "local", "command": [python, "-m", mod], "environment": env, "enabled": True}
        if name == "science-kernel":
            s["timeout"] = 1800000      # V1: 요청·도구 호출 타임아웃(ms), 장시간 셀 허용
        mcp[name] = s
    cfg = {"$schema": "https://opencode.ai/config.json", "default_agent": "science", "mcp": mcp,
           "permission": {"external_directory": "ask"}}
    txt = json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"
    if (plan.project / "opencode.json").exists() and plan.manifest.get("opencode.json") is None:
        plan.write(".opencode/opencode.science.v1.json", txt)
        plan.log.append(("note", "기존 opencode.json 유지 → .opencode/opencode.science.v1.json 을 참고해 병합"))
    else:
        plan.write("opencode.json", txt)
    if not (plan.project / "AGENTS.md").exists():
        plan.write("AGENTS.md", project_settings())
    plan.write(".opencode/sciharness.env.ps1", f'$env:SCIHARNESS_PYTHON = "{python}"\n')
    scaffold(plan)

# ---------------- Claude Code ----------------
CC_READONLY = ("Read, Grep, Glob, mcp__science-kernel__view_image, mcp__science-kernel__artifact_lineage, "
               "mcp__science-kernel__artifact_list, mcp__science-kernel__python_exec, mcp__scholar__verify_citations, mcp__scholar__doi_resolve")

def install_claude_code(plan: Plan, python: str):
    plan.write("CLAUDE.md", core_prompt() + "\n\n---\n\n" + project_settings() +
               "\n\n## Claude Code 보충\n- 병렬 위임은 Task 도구로 서브에이전트 여러 개를 한 메시지에서 호출.\n- 계획은 plan mode 또는 /plan.\n")
    for meta, b in agents():
        sk = meta.get("skills", [])
        fm = (f"---\nname: {meta['name']}\ndescription: {meta['description']}\n" +
              (f"tools: {CC_READONLY}\n" if meta.get("access") == "read-only" else "") +
              "model: inherit\n" + (f"skills: [{', '.join(sk)}]\n" if sk else "") + "---\n\n")
        plan.write(f".claude/agents/{meta['name']}.md", fm + b + "\n")
    for sd in skills_dirs():
        plan.copytree(sd, f".claude/skills/{sd.name}")
    portable_scripts(plan, ".claude/skills")
    for c in sorted((HARNESS / "commands").glob("*.md")):
        meta, body = front(c.read_text(encoding="utf-8"))
        plan.write(f".claude/commands/{c.name}", f"---\ndescription: {meta.get('description','')}\n---\n\n{body.strip()}\n")
    env = env_for(plan.project)
    plan.write(".mcp.json", json.dumps({"mcpServers": {n: {"command": python, "args": ["-m", m], "env": env}
                                                        for n, m in SERVERS.items()}}, ensure_ascii=False, indent=2) + "\n")
    hook = lambda ev: [{"type": "command", "command": f'"{python}" -m sciharness.hooks claude {ev}', "timeout": 30}]
    settings = {"hooks": {
        "SessionStart": [{"hooks": hook("SessionStart")}],
        "UserPromptSubmit": [{"hooks": hook("UserPromptSubmit")}],
        "PostToolUse": [{"matcher": "Write|Edit|Read|mcp__science-kernel__.*", "hooks": hook("PostToolUse")}],
        "Stop": [{"hooks": hook("Stop")}]},
        "permissions": {"ask": ["Bash(git push:*)", "Bash(rm -rf:*)"]}}
    if (plan.project / ".claude/settings.json").exists() and plan.manifest.get(".claude/settings.json") is None:
        plan.write(".claude/settings.science.json", json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
        plan.log.append(("note", "기존 .claude/settings.json 유지 → settings.science.json 의 hooks 를 병합"))
    else:
        plan.write(".claude/settings.json", json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
    scaffold(plan)

# ---------------- Codex ----------------
def toml_ml(s: str) -> str:
    return Q3 + "\n" + s.replace(Q3, "' ' '") + "\n" + Q3

OC_STUB = ("# science 에이전트 (공존 설치 모드)\n\n"
           "이 프로젝트는 Codex/Claude Code 와 같은 폴더를 공유한다. 핵심 행동 규율(시스템 프롬프트 12절)은 중복을 피하려고 "
           "AGENTS.md 에 한 번만 들어 있다. AGENTS.md 의 규율을 이 에이전트의 시스템 지시로 취급하고 그대로 따른다.\n")

def _oc_stub_if_coinstalled(plan: Plan):
    """OpenCode 가 이미 설치된 폴더에 Codex 를 추가하면 AGENTS.md 에 핵심 규율이 들어간다 → science 에이전트 본문을 안내문으로 교체."""
    rel = ".opencode/agents/science.md"
    p = plan.project / rel
    if rel in plan.manifest and p.exists():
        txt = p.read_text(encoding="utf-8")
        fm_end = txt.find("---", 3) + 3
        plan.write(rel, txt[:fm_end] + "\n\n" + OC_STUB)
        plan.log.append(("note", "공존 설치: OpenCode science 에이전트 본문을 AGENTS.md 안내문으로 교체(중복 방지)"))

def install_codex(plan: Plan, python: str):
    plan.write("AGENTS.md", core_prompt() + "\n\n---\n\n" + project_settings())
    _oc_stub_if_coinstalled(plan)
    for meta, b in agents():
        sk = meta.get("skills", [])
        pre = (f"작업을 시작하면 먼저 다음 스킬을 로드한다: {', '.join(sk)}.\n\n" if sk else "")
        plan.write(f".codex/agents/{meta['name']}.toml",
                   f'name = {yq(meta["name"])}\ndescription = {yq(meta["description"])}\n'
                   f'model_reasoning_effort = "{"high" if meta.get("model_tier") == "strong" else "medium"}"\n'
                   f"developer_instructions = {toml_ml(pre + b)}\n")
    for sd in skills_dirs():
        plan.copytree(sd, f".agents/skills/{sd.name}")
    portable_scripts(plan, ".agents/skills")
    env = env_for(plan.project)
    lines = ["# open-science harness — Codex 프로젝트 설정 (신뢰된 프로젝트에서만 로드됨)", "[features]", "hooks = true", ""]
    for n, m in SERVERS.items():
        lines += [f'[mcp_servers.{n}]', f"command = {yq(python)}", f'args = ["-m", "{m}"]']
        if n == "science-kernel":
            lines.append("tool_timeout_sec = 1800")
        lines += [f"[mcp_servers.{n}.env]"] + [f"{k} = {yq(v)}" for k, v in env.items()] + [""]
    plan.write(".codex/config.toml", "\n".join(lines) + "\n")
    hook = lambda ev: [{"type": "command", "command": f'"{python}" -m sciharness.hooks claude {ev}', "timeout": 30}]
    plan.write(".codex/hooks.json", json.dumps({"hooks": {
        "SessionStart": [{"hooks": hook("SessionStart")}],
        "UserPromptSubmit": [{"hooks": hook("UserPromptSubmit")}],
        "PostToolUse": [{"hooks": hook("PostToolUse")}],
        "Stop": [{"hooks": hook("Stop")}]}}, ensure_ascii=False, indent=2) + "\n")
    scaffold(plan)

# ---------------- Claude.ai ----------------
def install_claude_ai(out: Path, dry: bool):
    out = out / "claude-ai"
    if not dry:
        (out / "skills").mkdir(parents=True, exist_ok=True)
    src = KIT / "python" / "sciharness"
    for sd in skills_dirs():
        zp = out / "skills" / f"{sd.name}.zip"
        print("  zip  ", zp)
        if dry:
            continue
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sd.rglob("*"):
                if p.is_file():
                    z.write(p, f"{sd.name}/{p.relative_to(sd).as_posix()}")
            for m in PORTABLE.get(sd.name, []):
                z.writestr(f"{sd.name}/scripts/{m}", (src / m).read_text(encoding="utf-8").replace("from .figures import", "from figures import"))
    note = ("> Claude.ai 프로젝트 지침용 변환본. science-kernel(python_exec·view_image·artifact_*)은 Claude.ai 내장 코드 실행과 "
            "Artifacts 로 대체된다. scholar/memory MCP 는 원격(Streamable HTTP)으로 배포한 경우에만 사용자 지정 커넥터로 연결된다.\n\n")
    if not dry:
        (out / "project_instructions.md").write_text(note + core_prompt() + "\n\n---\n\n" + project_settings(), encoding="utf-8")
        (out / "README.md").write_text(
            "# Claude.ai 적용\n1. 설정 → 기능: 코드 실행 활성화.\n2. 사용자 지정 → 스킬: skills/*.zip 업로드.\n"
            "3. 프로젝트 생성 → project_instructions.md 내용을 프로젝트 지침에 붙여넣기.\n"
            "4. (선택) scholar/memory 서버 원격 배포: `MCP_TRANSPORT=streamable-http python -m sciharness.mcp_servers.scholar_server` → "
            "공개 HTTPS URL 을 사용자 지정 → 커넥터 → 추가에 등록. 인증 없는 공개 노출 금지.\n", encoding="utf-8")
    print("  ->", out)

def doctor(python: str):
    print("python:", python)
    r = subprocess.run([python, "-m", "sciharness.cli", "doctor"], capture_output=True, text=True, encoding="utf-8")
    print(r.stdout or r.stderr)
    for n, m in SERVERS.items():
        r = subprocess.run([python, "-c", f"import importlib; importlib.import_module('{m}'); print('ok')"], capture_output=True, text=True)
        print(("✓" if r.returncode == 0 else "✗"), "MCP", n, "" if r.returncode == 0 else r.stderr[-200:])

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default="opencode", help="opencode(=V2),opencode-v1,claude-code,codex,claude-ai,all(V2 기준, v1 제외)")
    ap.add_argument("--project", default=".")
    ap.add_argument("--out", default="dist")
    ap.add_argument("--python", default=sys.executable, help="sciharness 가 설치된 python (MCP/훅 실행용)")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--force", action="store_true")
    ap.add_argument("--pip", action="store_true", help="--python 에 sciharness 를 editable 설치")
    ap.add_argument("--doctor", action="store_true"); ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    python = str(Path(a.python))
    if a.pip and not a.dry_run:
        subprocess.check_call([python, "-m", "pip", "install", "-e", str(KIT / "python")])
    if a.doctor:
        doctor(python); return {}
    targets = ["opencode", "claude-code", "codex", "claude-ai"] if a.target == "all" else a.target.split(",")
    project = Path(a.project).resolve()
    res = {}
    for t in targets:
        print(f"[{t}] {project if t != 'claude-ai' else Path(a.out).resolve()}")
        if t == "claude-ai":
            install_claude_ai(Path(a.out).resolve(), a.dry_run); continue
        plan = Plan(project, a.dry_run, a.force)
        {"opencode": install_opencode, "opencode-v1": install_opencode_v1, "claude-code": install_claude_code, "codex": install_codex}[t](plan, python)
        res[t] = plan.finish(a.verbose)
    return res

if __name__ == "__main__":
    main()
