"""스킬 탐색: SKILL.md frontmatter(name/description)에 대한 어휘(BM25) 검색.
Claude Science의 search_skills / skill_discovery 동작을 재현한다."""
from __future__ import annotations
import math, os, re
from collections import Counter
from pathlib import Path

def _front(text: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    out = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1); out[k.strip()] = v.strip().strip('"').strip("'")
    return out

def default_dirs(base: Path | None = None) -> list[Path]:
    """스킬 폴더 후보. base(프로젝트 루트) 기준 — 훅이 다른 작업 폴더에서 호출돼도 같은 결과.
    base 가 없으면 SCIHARNESS_ROOT, 그다음 현재 작업 폴더."""
    env = os.environ.get("SCIHARNESS_SKILL_DIRS")
    if env:
        return [Path(p) for p in env.split(os.pathsep)]
    cwd = Path(base or os.environ.get("SCIHARNESS_ROOT") or Path.cwd()); home = Path.home()
    return [cwd / ".claude/skills", cwd / ".agents/skills", cwd / ".opencode/skills", cwd / "skills",
            home / ".claude/skills", home / ".agents/skills", home / ".config/opencode/skills"]

def load(dirs=None, base: Path | None = None) -> list[dict]:
    seen, out = set(), []
    for d in dirs or default_dirs(base):
        if not Path(d).exists():
            continue
        for p in Path(d).rglob("SKILL.md"):
            fm = _front(p.read_text(encoding="utf-8", errors="replace"))
            name = fm.get("name") or p.parent.name
            if name in seen:
                continue
            seen.add(name)
            out.append({"name": name, "description": fm.get("description", ""), "path": str(p)})
    return out

def _tok(s: str) -> list[str]:
    s = s.lower()
    words = re.findall(r"[a-z0-9][a-z0-9\-]{1,}|[가-힣]{2,}", s)
    grams = []
    for w in re.findall(r"[가-힣]{2,}", s):  # 한국어: 2-gram 보강
        grams += [w[i:i + 2] for i in range(len(w) - 1)]
    return words + grams

def search(query: str, k: int = 4, dirs=None, min_score: float = 0.8, base: Path | None = None) -> list[dict]:
    docs = load(dirs, base)
    if not docs:
        return []
    toks = [_tok(d["name"].replace("-", " ") + " " + d["description"]) for d in docs]
    N = len(docs); avg = sum(map(len, toks)) / N
    df = Counter(t for ts in toks for t in set(ts))
    q = _tok(query); res = []
    for d, ts in zip(docs, toks):
        tf = Counter(ts); s = 0.0
        for t in set(q):
            if t in tf:
                idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * len(ts) / avg))
        if s >= min_score:
            res.append(d | {"score": round(s, 2)})
    return sorted(res, key=lambda r: -r["score"])[:k]

def format_discovery(hits: list[dict]) -> str:
    if not hits:
        return ""
    lines = ["[skill_discovery] 요청과 어휘가 겹치는 스킬(필요할 때만 로드):"]
    lines += [f"- {h['name']} — {h['description'][:220]}" for h in hits]
    return "\n".join(lines)
