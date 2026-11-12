"""공용 훅(sciharness.hooks) 검증 — OpenCode 플러그인과 Claude Code/Codex 훅이 호출하는 동작.
    python tests/test_hooks.py
"""
import datetime, io, json, os, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
root = HERE / "_hook_runs" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S"); root.mkdir(parents=True)
env = dict(os.environ, SCIHARNESS_ROOT=str(root), SCIHARNESS_MEMORY_DB=str(root / "mem.db"),
           SCIHARNESS_SKILL_DIRS=str(HERE.parent / "harness" / "skills"), PYTHONIOENCODING="utf-8")
res = []
def chk(n, ok, d=""):
    res.append(bool(ok)); print(("✓" if ok else "✗"), n, str(d)[:140])
def run(args, stdin=""):
    r = subprocess.run([sys.executable, "-m", "sciharness.hooks", *args], input=stdin, capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(root))
    return r.stdout.strip(), r.stderr.strip()

os.environ.update(env)
from sciharness import memory as M
M.write("사용자는 그림 라벨을 한국어(Malgun Gothic)로 원한다.", "profile", "stated")
M.write("CTF 스택 모델의 기본 터널 산화막 두께는 4.5 nm 이다.", "project:" + root.name, "observed")

out, err = run(["context", "--json", "--root", str(root), "--prompt", "논문용 그림 라벨 스타일을 맞춰서 플롯 그려줘"])
j = json.loads(out)
chk("context: [Memory] 회상 블록", "[Memory]" in j["text"] and "Malgun" in j["text"], j["text"][:80])
chk("context: [skill_discovery] 에 scientific-figures", "scientific-figures" in j["text"])

fig = root / "outputs" / "figures" / "f1.png"; fig.parent.mkdir(parents=True); fig.write_bytes(b"\x89PNG\r\n\x1a\n")
post = {"hook_event_name": "PostToolUse", "cwd": str(root), "tool_name": "Write", "tool_input": {"file_path": str(fig)}}
run(["claude", "PostToolUse"], json.dumps(post))
out, _ = run(["claude", "Stop"], json.dumps({"hook_event_name": "Stop", "cwd": str(root), "stop_hook_active": False}))
chk("Stop: 미검토 그림 있으면 차단", out and json.loads(out).get("decision") == "block", out[:90])
out2, _ = run(["claude", "Stop"], json.dumps({"hook_event_name": "Stop", "cwd": str(root), "stop_hook_active": True}))
chk("Stop: stop_hook_active 이면 재차단 안 함(무한루프 방지)", out2 == "")
up, _ = run(["claude", "UserPromptSubmit"], json.dumps({"hook_event_name": "UserPromptSubmit", "cwd": str(root), "prompt": "터널 산화막 두께 다시 알려줘"}))
ctx = json.loads(up)["hookSpecificOutput"]["additionalContext"]
chk("UserPromptSubmit: 회상 + 미검토 그림 경고 주입", "4.5 nm" in ctx and "[figure_review_pending]" in ctx, ctx[:80])
view = {"hook_event_name": "PostToolUse", "cwd": str(root), "tool_name": "mcp__science-kernel__view_image", "tool_input": {"path": str(fig)}}
run(["claude", "PostToolUse"], json.dumps(view))
out3, _ = run(["claude", "Stop"], json.dumps({"hook_event_name": "Stop", "cwd": str(root), "stop_hook_active": False}))
chk("view_image 후 Stop 통과", out3 == "", out3[:80])
ss, _ = run(["claude", "SessionStart"], json.dumps({"hook_event_name": "SessionStart", "cwd": str(root)}))
chk("SessionStart: profile/project 메모리 + 스킬 수", "Malgun" in ss and "스킬 10개" in ss, ss[-80:])
lin = (root / ".science" / "lineage.jsonl").read_text(encoding="utf-8").splitlines()
chk("PostToolUse: 계보 기록", len(lin) >= 2, len(lin))
print(f"\n{sum(res)}/{len(res)} passed"); sys.exit(0 if all(res) else 1)
