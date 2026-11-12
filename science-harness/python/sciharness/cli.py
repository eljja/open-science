"""sciharness 명령행.
  python -m sciharness.cli html <md> [--mode embed|attach] [--out <html>]
  python -m sciharness.cli viewer <out.html> <name=csv> [<name=csv> ...]
  python -m sciharness.cli skills "<질의>"
  python -m sciharness.cli recall "<질의>"
  python -m sciharness.cli doctor
"""
from __future__ import annotations
import argparse, importlib, json, shutil, sys
from pathlib import Path

def main(argv=None):
    ap = argparse.ArgumentParser(prog="sciharness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("html"); h.add_argument("md"); h.add_argument("--mode", default="embed"); h.add_argument("--out")
    v = sub.add_parser("viewer"); v.add_argument("out"); v.add_argument("pairs", nargs="+"); v.add_argument("--title", default="데이터 뷰어")
    s = sub.add_parser("skills"); s.add_argument("query"); s.add_argument("-k", type=int, default=4)
    r = sub.add_parser("recall"); r.add_argument("query")
    sub.add_parser("doctor")
    a = ap.parse_args(argv)
    if a.cmd == "html":
        from .report import build_html
        md = Path(a.md)
        out = Path(a.out) if a.out else md.with_suffix(".html") if a.mode == "embed" else md.parent / "confluence" / (md.stem + ".html")
        print(build_html(md, out, mode=a.mode))
    elif a.cmd == "viewer":
        from .viewer import build_viewer
        ds = dict(p.split("=", 1) for p in a.pairs)
        print(build_viewer(ds, a.out, title=a.title))
    elif a.cmd == "skills":
        from .skills_index import search
        print(json.dumps(search(a.query, k=a.k, min_score=0.0), ensure_ascii=False, indent=1))
    elif a.cmd == "recall":
        from .memory import search, format_recall
        print(format_recall(search(a.query)) or "(없음)")
    elif a.cmd == "doctor":
        ok = True
        for m in ["mcp", "jupyter_client", "ipykernel", "matplotlib", "pandas", "httpx", "markdown"]:
            try:
                importlib.import_module(m); print("✓", m)
            except Exception as e:
                ok = False; print("✗", m, e)
        from .figures import find_korean_font
        f = find_korean_font(); print("✓" if f else "✗", "한국어 글꼴:", f)
        for exe in ["pandoc", "dot", "git", "claude", "codex", "opencode"]:
            print("✓" if shutil.which(exe) else "·", exe, shutil.which(exe) or "(없음 — 선택)")
        sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
