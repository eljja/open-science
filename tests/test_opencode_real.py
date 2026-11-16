"""실제 OpenCode 바이너리로 하네스 설치 결과를 검증한다(사용자 PC 용).

    python tests/test_opencode_real.py --opencode <opencode 실행파일> --project <설치된 프로젝트> [--v1|--v2]

- OpenCode 1.x: `debug config`(기본 에이전트·MCP·플러그인·명령), `debug agent science`(시스템 프롬프트),
  `debug skill`(스킬 10종), `mcp list`(science-kernel·memory 연결) 를 확인한다.
- OpenCode 2: `debug config`, `mcp list` 를 실행해 출력에 하네스 항목이 있는지 확인한다(백그라운드 서비스 필요).
- --block-network: HTTP(S)_PROXY 를 닫힌 포트로 돌려 폐쇄망을 흉내 내고 명령별 소요 시간을 잰다.
결과는 <project>/.science/opencode_real_test.json 에 저장한다.
"""
import argparse, json, os, re, subprocess, sys, time
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;]*m")
SKILLS = {"scientific-figures", "schematic-diagrams", "figure-review", "scientific-writing", "literature-review",
          "data-analysis", "report-html", "data-viewer", "plan-and-delegate", "skill-creator"}

def run(exe, args, cwd, env, timeout=300):
    t0 = time.time()
    try:
        r = subprocess.run([exe, *args], cwd=cwd, env=env, capture_output=True, timeout=timeout)
        return r.returncode, ANSI.sub("", r.stdout.decode("utf-8", "replace")), ANSI.sub("", r.stderr.decode("utf-8", "replace")), time.time() - t0
    except subprocess.TimeoutExpired:
        return "timeout", "", "", time.time() - t0

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--opencode", required=True); ap.add_argument("--project", required=True)
    g = ap.add_mutually_exclusive_group(); g.add_argument("--v1", action="store_true"); g.add_argument("--v2", action="store_true")
    ap.add_argument("--block-network", action="store_true")
    a = ap.parse_args(argv)
    proj = Path(a.project).resolve(); exe = str(Path(a.opencode).resolve())
    rc, o, e, _ = run(exe, ["--version"], proj, os.environ.copy(), 60)
    ver = (o + e).strip().splitlines()[-1] if (o + e).strip() else "?"
    v1 = a.v1 or (not a.v2 and re.match(r"^1\.", ver.split()[-1].lstrip("v")) is not None)
    env = os.environ.copy()
    env.update({"OPENCODE_DISABLE_AUTOUPDATE": "1", "OPENCODE_DISABLE_MODELS_FETCH": "1", "OPENCODE_DISABLE_LSP_DOWNLOAD": "1"})
    mp = proj / ".science" / "models.json"
    if mp.exists():
        env["OPENCODE_MODELS_PATH"] = str(mp)
    if a.block_network:
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            env[k] = "http://127.0.0.1:9"
        env["npm_config_registry"] = "http://127.0.0.1:9/"; env["NO_PROXY"] = "127.0.0.1,localhost"
    res = []
    def chk(name, ok, detail=""):
        res.append({"test": name, "ok": bool(ok), "detail": detail}); print(("✓" if ok else "✗"), name, detail)
    chk(f"OpenCode 실행 ({'1.x' if v1 else '2'})", rc == 0, ver)
    rc, o, e, dt = run(exe, ["debug", "config"], proj, env)
    if v1:
        try:
            c = json.loads(o)
        except Exception:
            c = {}
        chk("debug config: default_agent=science", c.get("default_agent") == "science", f"{dt:.1f}s")
        chk("debug config: 에이전트 6종", {"science", "reviewer", "figure-critic", "literature-scout", "data-analyst", "section-writer"} <= set(c.get("agent", {})))
        chk("debug config: 명령 8종", len(c.get("command", {})) >= 8, str(sorted(c.get("command", {}))))
        chk("debug config: V1 플러그인 인식", any("science-harness" in str(p) for p in c.get("plugin", [])))
        chk("debug config: MCP 3종 정의", {"science-kernel", "scholar", "memory"} <= set(c.get("mcp", {})))
        rc, o, e, dt = run(exe, ["debug", "agent", "science"], proj, env)
        chk("debug agent science: 하네스 시스템 프롬프트", rc == 0 and "open-science harness" in o, f"{len(o)}자")
        rc, o, e, dt = run(exe, ["debug", "skill"], proj, env)
        names = set(re.findall(r'"name":\s*"([^"]+)"', o))
        chk("debug skill: 하네스 스킬 10종", SKILLS <= names, f"{len(names)}개")
    else:
        chk("debug config 실행", rc == 0, (e.strip().splitlines() or [""])[-1][:120])
        chk("debug config: science 에이전트/MCP 노출", "science" in o and "science-kernel" in o)
    rc, o, e, dt = run(exe, ["mcp", "list"], proj, env)
    st = dict((n, s) for _, n, s in re.findall(r"([✓✗○●•])\s+(?:[✓✗○]\s+)?(\S+)\s+(connected|failed|disabled|needs_auth)", o))
    st.update({n: s for m, n, s in re.findall(r"([✓✗○])\s+(\S+)\s+(connected|failed|disabled)", o)})
    chk("mcp list: science-kernel 연결", st.get("science-kernel") == "connected", f"{dt:.1f}s {st}")
    chk("mcp list: memory 연결", st.get("memory") == "connected")
    out = proj / ".science" / "opencode_real_test.json"; out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"opencode": ver, "block_network": a.block_network, "results": res}, ensure_ascii=False, indent=1), encoding="utf-8")
    n = sum(r["ok"] for r in res); print(f"\n{n}/{len(res)} passed  →  {out}")
    return 0 if n == len(res) else 1

if __name__ == "__main__":
    sys.exit(main())
