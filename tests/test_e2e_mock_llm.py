"""모의 LLM 종단 간 테스트 — 실제 OpenCode(1.x / 2) 바이너리로 한 턴을 돌려 하네스 동작을 확인한다. LLM 키 불필요.

    python tests/test_e2e_mock_llm.py --opencode <opencode 실행파일> [--python <sciharness 가 설치된 python>]
                                       [--offline] [--isolated-home --v1-deps <opencode-plugin-deps.zip>]

동작: 로컬 OpenAI 호환 모의 서버(127.0.0.1:<port>)를 띄우고, 임시 프로젝트에 하네스를 설치한 뒤 mock provider 를 추가한다.
모의 모델은 첫 호출에 science-kernel python_exec(print(6*7)) 도구 호출을, 도구 결과를 받으면 최종 텍스트를 돌려준다.
OpenCode 가 모델에 보낸 요청을 기록해 아래를 검사한다.
  - 시스템 프롬프트가 하네스 science 프롬프트로 대체됨 / 플러그인 훅의 [skill_discovery] 주입 / AGENTS.md 포함
  - MCP 도구(kernel·memory) 직접 노출, 도구 결과(42) 왕복, .science/lineage.jsonl 에 커널 셀·플러그인 도구 기록
V1 은 `opencode run`, V2 는 `opencode serve` + HTTP API(session/prompt) 로 실행한다.
결과: tests/_e2e_runs/<시각>/e2e_result.json
"""
import argparse, datetime, http.server, json, os, re, socketserver, subprocess, sys, threading, time, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent; KIT = HERE.parent
ANSI = re.compile(r"\x1b\[[0-9;]*m")
MARK = "[skill_discovery] 요청과 어휘가 겹치는 스킬"
PROMPT = "논문용 그림으로 사인파를 그려서 저장해줘"
REQS: list = []

class Mock(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, obj):
        b = json.dumps(obj).encode(); self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        self._json({"object": "list", "data": [{"id": "m1", "object": "model"}]})
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}"); REQS.append(req)
        msgs = req.get("messages", []); last = msgs[-1] if msgs else {}
        pe = [t["function"]["name"] for t in req.get("tools", []) if t.get("type") == "function" and t["function"]["name"].endswith("python_exec")]
        base = {"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": "m1"}
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        if last.get("role") == "tool" or not pe:
            delta = {"role": "assistant", "content": "계산 결과를 확인했습니다: 42" if last.get("role") == "tool" else "제목"}; fin = "stop"
        else:
            delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                     "function": {"name": pe[0], "arguments": json.dumps({"code": "print(6*7)"})}}]}; fin = "tool_calls"
        if req.get("stream"):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            for c in (base | {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                      base | {"choices": [{"index": 0, "delta": {}, "finish_reason": fin}], "usage": usage}):
                self.wfile.write(("data: " + json.dumps(c, ensure_ascii=False) + "\n\n").encode()); self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            m = {"role": "assistant", "content": delta.get("content")}
            if "tool_calls" in delta: m["tool_calls"] = delta["tool_calls"]
            self._json({"id": "c1", "object": "chat.completion", "created": 0, "model": "m1",
                        "choices": [{"index": 0, "message": m, "finish_reason": fin}], "usage": usage})

class TS(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

def sys_text(req):
    return "\n".join(x["content"] if isinstance(x.get("content"), str) else json.dumps(x.get("content"), ensure_ascii=False)
                     for x in req.get("messages", []) if x.get("role") == "system")

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--opencode", required=True); ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--port", type=int, default=4300); ap.add_argument("--server-port", type=int, default=4194)
    ap.add_argument("--offline", action="store_true", help="install.py --offline 로 설치(scholar 비활성)")
    ap.add_argument("--isolated-home", action="store_true", help="XDG_* 를 임시 폴더로(사용자 전역 설정과 분리)")
    ap.add_argument("--v1-deps", help="V1 + --isolated-home 일 때 배치할 opencode-plugin-deps.zip(오프라인 번들 v1-deps/)")
    ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args(argv)
    exe = str(Path(a.opencode).resolve())
    ver = subprocess.run([exe, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip().split()[-1].lstrip("v")
    v1 = ver.startswith("1.")
    run_dir = HERE / "_e2e_runs" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S"); proj = run_dir / "proj"; proj.mkdir(parents=True)
    target = "opencode-v1" if v1 else "opencode"
    r = subprocess.run([a.python, str(KIT / "tools" / "install.py"), "--target", target, "--project", str(proj), "--python", a.python]
                       + (["--offline"] if a.offline else []), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        print(r.stdout[-800:], r.stderr[-800:]); return 2
    env = dict(os.environ, SCIHARNESS_PYTHON=a.python, OPENCODE_DISABLE_AUTOUPDATE="1", MOCK_API_KEY="x",
               NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
    if a.isolated_home:
        hm = run_dir / "home"
        env.update(XDG_CONFIG_HOME=str(hm / "config"), XDG_DATA_HOME=str(hm / "data"), XDG_CACHE_HOME=str(hm / "cache"), XDG_STATE_HOME=str(hm / "state"))
        if v1 and a.v1_deps:
            for d in (proj / ".opencode", hm / "config" / "opencode"):
                d.mkdir(parents=True, exist_ok=True); zipfile.ZipFile(a.v1_deps).extractall(d)
    url = f"http://127.0.0.1:{a.port}/v1"
    if v1:
        cfgp = proj / "opencode.json"; cfg = json.loads(cfgp.read_text(encoding="utf-8"))
        cfg["provider"] = {"mock": {"npm": "@ai-sdk/openai-compatible", "name": "Mock", "options": {"baseURL": url, "apiKey": "x"},
                                    "models": {"m1": {"name": "m1", "tool_call": True, "limit": {"context": 128000, "output": 4096}}}}}
        cfg["model"] = cfg["small_model"] = "mock/m1"
    else:
        cfgp = proj / "opencode.jsonc"; cfg = json.loads(re.sub(r"^//.*$", "", cfgp.read_text(encoding="utf-8"), flags=re.M))
        cfg["providers"] = {"mock": {"name": "Mock", "env": ["MOCK_API_KEY"], "package": "@opencode/ai/providers/openai-compatible",
                                     "settings": {"baseURL": url}, "models": {"m1": {"name": "m1"}}}}
    cfgp.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    mock = TS(("127.0.0.1", a.port), Mock); threading.Thread(target=mock.serve_forever, daemon=True).start()
    final, err = "", ""
    t0 = time.time()
    try:
        if v1:
            for _ in range(3):  # 첫 실행이 데이터 폴더 생성 경합으로 실패하는 경우 재시도
                REQS.clear()
                p = subprocess.run([exe, "run", PROMPT, "-m", "mock/m1"], cwd=str(proj), env=env, capture_output=True, timeout=a.timeout)
                final = ANSI.sub("", p.stdout.decode("utf-8", "replace")).strip(); err = ANSI.sub("", p.stderr.decode("utf-8", "replace"))
                if p.returncode == 0:
                    break
                time.sleep(2)
        else:
            import base64, urllib.request
            pw = "e2e-" + os.urandom(6).hex(); env["OPENCODE_SERVER_PASSWORD"] = pw
            srv = subprocess.Popen([exe, "serve", "--hostname", "127.0.0.1", "--port", str(a.server_port)], cwd=str(proj), env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            auth = "Basic " + base64.b64encode(f"opencode:{pw}".encode()).decode()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            def api(method, path, body=None):
                rq = urllib.request.Request(f"http://127.0.0.1:{a.server_port}{path}", method=method,
                                            data=json.dumps(body).encode() if body is not None else None,
                                            headers={"Authorization": auth, "Content-Type": "application/json"})
                with opener.open(rq, timeout=60) as resp:
                    return json.loads(resp.read())
            try:
                mcp_state = {}
                for _ in range(60):  # 모든 MCP 상태가 확정(connected/disabled/failed)될 때까지
                    try:
                        mcp_state = {m["name"]: m["status"]["status"] for m in api("GET", "/api/mcp")["data"]}
                        if mcp_state and all(s in ("connected", "disabled", "failed", "needs_auth") for s in mcp_state.values()):
                            break
                    except Exception:
                        pass
                    time.sleep(1.5)
                print("  MCP:", mcp_state)
                REQS.clear()
                sid = api("POST", "/api/session", {"agent": "science", "model": {"id": "m1", "providerID": "mock"}})["data"]["id"]
                api("POST", f"/api/session/{sid}/prompt", {"text": PROMPT})
                while time.time() - t0 < a.timeout:
                    data = api("GET", f"/api/session/{sid}/message")["data"]
                    done = [m for m in data if m.get("type") == "idle"]
                    texts = [c.get("text", "") for m in data if m.get("type") == "assistant" and "42" in json.dumps(m, ensure_ascii=False) for c in m.get("content", []) if c.get("type") == "text"]
                    if done and texts:
                        final = texts[0]; break
                    time.sleep(1.5)
            finally:
                srv.kill()
    finally:
        mock.shutdown()
    main_reqs = [q for q in REQS if q.get("tools")]
    s0 = sys_text(main_reqs[0]) if main_reqs else ""
    tools = [t["function"]["name"] for t in (main_reqs[0]["tools"] if main_reqs else [])]
    lin = (proj / ".science" / "lineage.jsonl")
    lines = [json.loads(l) for l in lin.read_text(encoding="utf-8").splitlines()] if lin.exists() else []
    res = []
    def chk(n, ok, d=""):
        res.append({"test": n, "ok": bool(ok), "detail": str(d)[:200]}); print(("✓" if ok else "✗"), n, str(d)[:120])
    chk(f"OpenCode {ver}: 모의 모델로 한 턴 완료", "42" in final, final[:60] or err[-200:])
    chk("시스템 프롬프트 = 하네스 science 프롬프트", "open-science harness" in s0, f"{len(s0)}자")
    chk("기본 OpenCode 프롬프트 대체", s0 and "You are opencode" not in s0 and "You are OpenCode" not in s0)
    chk("플러그인 훅: [skill_discovery] 주입", MARK in s0)
    chk("AGENTS.md 가 시스템에 포함", "검증 명령" in s0 or "sciharness" in s0)
    chk("MCP 직접 노출: python_exec·view_image", any(t.endswith("python_exec") for t in tools) and any(t.endswith("view_image") for t in tools))
    chk("MCP 직접 노출: memory_search", any(t.endswith("memory_search") for t in tools), [t for t in tools if "memory" in t][:3])
    chk("도구 결과(42) 가 모델에 전달", any("42" in json.dumps(x, ensure_ascii=False) for q in REQS for x in q.get("messages", []) if x.get("role") == "tool"))
    chk("계보: 커널 셀 + 플러그인 도구 기록", any(e.get("kind") == "cell" for e in lines) and any(e.get("kind") == "tool" for e in lines), len(lines))
    out = run_dir / "e2e_result.json"
    out.write_text(json.dumps({"opencode": ver, "offline": a.offline, "requests": len(REQS), "results": res}, ensure_ascii=False, indent=1), encoding="utf-8")
    n = sum(x["ok"] for x in res); print(f"\n{n}/{len(res)} passed  →  {out}")
    return 0 if n == len(res) else 1

if __name__ == "__main__":
    sys.exit(main())
