"""런타임 공용 훅 로직. OpenCode 플러그인 / Claude Code hooks / Codex hooks 가 모두 이 모듈을 호출한다.

Claude Science 가 대화에 주입하는 블록을 재현한다:
  [Memory] <memory_recall>     — 요청과 관련된 저장 기록
  [skill_discovery]            — 요청과 어휘가 겹치는 스킬 후보
  [figure_review_pending]      — 저장됐지만 아직 눈으로 확인하지 않은 그림
  [frame]                      — 세션 메모장(.science/frame.md) 발췌 (컨텍스트 압축 후 연속성)

사용:
  python -m sciharness.hooks context --prompt "<사용자 요청>" [--json]     # OpenCode 플러그인
  python -m sciharness.hooks claude <EventName>  < stdin(JSON)             # Claude Code / Codex hooks
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path

def _root(cwd: str | None = None) -> Path:
    return Path(os.environ.get("SCIHARNESS_ROOT") or cwd or os.getcwd()).resolve()

def project_entity(root: Path) -> str:
    return "project:" + root.name

def pending_figures(root: Path) -> list[str]:
    f = root / ".science" / "pending_figure_review.json"
    if not f.exists():
        return []
    try:
        return [p for p in json.loads(f.read_text(encoding="utf-8")) if Path(p).exists()]
    except Exception:
        return []

def add_pending(root: Path, paths: list[str]):
    if not paths:
        return
    d = root / ".science"; d.mkdir(parents=True, exist_ok=True)
    cur = pending_figures(root)
    for p in paths:
        ap = str(Path(p).resolve())
        if ap not in cur:
            cur.append(ap)
    (d / "pending_figure_review.json").write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")

def clear_pending(root: Path, path: str):
    cur = [p for p in pending_figures(root) if Path(p).resolve() != Path(path).resolve()]
    d = root / ".science"; d.mkdir(parents=True, exist_ok=True)
    (d / "pending_figure_review.json").write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")

def recall_block(prompt: str, root: Path, limit: int = 6) -> str:
    try:
        from . import memory as M
        rows = M.search(prompt, limit=limit)
        return M.format_recall(rows, "[Memory] <memory_recall> 요청과 관련된 과거 기록 — 수치는 맥락일 뿐, 사용 전 파일로 확인")
    except Exception as e:  # 메모리 DB 문제로 대화가 막히면 안 된다
        return f"[Memory] (회상 실패: {e!r})"

def discovery_block(prompt: str, k: int = 4) -> str:
    try:
        from . import skills_index as S
        return S.format_discovery(S.search(prompt, k=k))
    except Exception:
        return ""

def pending_block(root: Path) -> str:
    pend = pending_figures(root)
    if not pend:
        return ""
    rel = [str(Path(p).relative_to(root)) if str(p).startswith(str(root)) else p for p in pend][:10]
    return ("[figure_review_pending] 저장됐지만 아직 이미지로 확인하지 않은 그림 " + str(len(pend)) + "개: " + ", ".join(rel) +
            "\n→ 보고서에 넣거나 완료를 보고하기 전에 view_image 로 각 그림(패널별 크롭 포함)을 확인할 것.")

def frame_block(root: Path, max_chars: int = 1500) -> str:
    f = root / ".science" / "frame.md"
    if not f.exists():
        return ""
    t = f.read_text(encoding="utf-8").strip()
    return "[frame] 세션 메모장(.science/frame.md) — 진행 상태:\n" + (t[-max_chars:] if len(t) > max_chars else t)

def context_text(prompt: str, root: Path | None = None, include_frame: bool = True) -> str:
    root = root or _root()
    parts = [recall_block(prompt, root), discovery_block(prompt), pending_block(root)]
    if include_frame:
        parts.append(frame_block(root))
    return "\n\n".join(p for p in parts if p)

def session_start_text(root: Path) -> str:
    try:
        from . import memory as M, skills_index as S
        prof = M.read("profile", 40); proj = M.read(project_entity(root), 40)
        lines = ["## Memory (자동 주입)", "### Profile"] + [f"- [{r['evidence']}] {r['text']}" for r in prof]
        lines += [f"### {project_entity(root)}"] + [f"- [{r['age']}] [{r['evidence']}] {r['text']}  [{r['id']}]" for r in proj[:15]]
        n = len(S.load())
        lines.append(f"\n(설치된 스킬 {n}개 — search_skills 로 검색. 작업 전 memory_search 로 관련 기록 확인.)")
        pb = pending_block(root)
        return "\n".join(lines) + ("\n\n" + pb if pb else "")
    except Exception as e:
        return f"(sciharness session start: {e!r})"

# ---------------- Claude Code / Codex hooks (stdin JSON → stdout JSON) ----------------
def _figure_paths_from_tool(data: dict, root: Path) -> list[str]:
    ti = data.get("tool_input") or {}
    cands = []
    for k in ("file_path", "path", "filePath"):
        if isinstance(ti.get(k), str):
            cands.append(ti[k])
    return [str((root / c).resolve()) if not os.path.isabs(c) else c for c in cands
            if c.lower().endswith(".png") and "figures" in Path(c).parts]

def claude_hook(event: str, data: dict) -> dict | None:
    root = _root(data.get("cwd"))
    if event == "SessionStart":
        return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": session_start_text(root)}}
    if event == "UserPromptSubmit":
        txt = context_text(data.get("prompt", ""), root)
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": txt}} if txt else None
    if event == "PostToolUse":
        from . import lineage as L
        tool = data.get("tool_name", "")
        L.append_event("tool", root, tool=tool, input_keys=sorted((data.get("tool_input") or {}).keys())[:8])
        if tool.endswith("view_image") or tool == "Read":
            p = (data.get("tool_input") or {}).get("path") or (data.get("tool_input") or {}).get("file_path")
            if p and str(p).lower().endswith(".png"):
                clear_pending(root, str((root / p).resolve()) if not os.path.isabs(p) else p)
        figs = _figure_paths_from_tool(data, root) if tool in ("Write", "Edit", "apply_patch") else []
        add_pending(root, figs)
        pb = pending_block(root)
        if pb and tool.endswith("python_exec"):
            return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": pb}}
        return None
    if event == "Stop":
        if data.get("stop_hook_active"):
            return None
        pend = pending_figures(root)
        if pend:
            return {"decision": "block", "reason": pending_block(root)}
        return None
    return None

def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print(__doc__); return
    if argv[0] == "context":
        import argparse
        ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("--prompt", default="")
        ap.add_argument("--prompt-file"); ap.add_argument("--root"); ap.add_argument("--json", action="store_true")
        ap.add_argument("--no-frame", action="store_true")
        a = ap.parse_args(argv)
        prompt = Path(a.prompt_file).read_text(encoding="utf-8") if a.prompt_file else a.prompt
        root = Path(a.root).resolve() if a.root else _root()
        txt = context_text(prompt, root, include_frame=not a.no_frame)
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps({"text": txt, "pending": pending_figures(root)}, ensure_ascii=False) if a.json else txt)
    elif argv[0] == "session-start":
        sys.stdout.reconfigure(encoding="utf-8"); print(session_start_text(_root()))
    elif argv[0] == "claude":
        sys.stdin.reconfigure(encoding="utf-8"); sys.stdout.reconfigure(encoding="utf-8")
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        out = claude_hook(argv[1] if len(argv) > 1 else data.get("hook_event_name", ""), data)
        if out:
            print(json.dumps(out, ensure_ascii=False))
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
