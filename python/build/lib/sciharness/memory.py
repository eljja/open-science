"""영속 메모리(SQLite FTS5). Claude Science의 profile / project / artifact / frame 엔티티 모델을 따른다.
- evidence: stated(사용자가 말함) / observed(도구 결과에서 확인) / inferred(추론)
- 민감정보(건강, 금융, 신분번호 등)는 저장 거부.
"""
from __future__ import annotations
import datetime as _dt, os, re, sqlite3, uuid
from pathlib import Path

_DB = None
_BLOCK = [r"\b\d{6}-\d{7}\b", r"\b\d{3}-\d{2}-\d{4}\b", r"\b(?:\d[ -]?){13,16}\b",
          r"(?i)password\s*[:=]", r"(?i)api[_-]?key\s*[:=]\s*\S{8,}", r"(?i)\bsk-[A-Za-z0-9]{16,}"]

def db_path() -> Path:
    p = os.environ.get("SCIHARNESS_MEMORY_DB")
    if p:
        return Path(p)
    return Path.home() / ".sciharness" / "memory.db"

def _conn():
    global _DB
    if _DB is None:
        p = db_path(); p.parent.mkdir(parents=True, exist_ok=True)
        _DB = sqlite3.connect(p, check_same_thread=False)
        _DB.execute("CREATE TABLE IF NOT EXISTS mem(id TEXT PRIMARY KEY, entity TEXT, text TEXT, evidence TEXT,"
                    " category TEXT, created TEXT, updated TEXT)")
        _DB.execute("CREATE VIRTUAL TABLE IF NOT EXISTS mem_fts USING fts5(id UNINDEXED, entity, text, tokenize='trigram')")
        _DB.commit()
    return _DB

def _guard(text: str):
    for pat in _BLOCK:
        if re.search(pat, text):
            raise ValueError("민감정보(식별번호/카드번호/비밀값)로 보이는 내용은 메모리에 저장하지 않습니다.")
    if len(text) > 1000:
        raise ValueError("메모리 항목은 1000자 이하의 단일 사실이어야 합니다.")

def write(text: str, entity: str = "project", evidence: str = "observed", category: str | None = None) -> str:
    _guard(text)
    if evidence not in ("stated", "observed", "inferred"):
        raise ValueError("evidence는 stated/observed/inferred 중 하나")
    c = _conn(); mid = "mem_" + uuid.uuid4().hex[:12]; t = _dt.datetime.now().isoformat(timespec="seconds")
    c.execute("INSERT INTO mem VALUES(?,?,?,?,?,?,?)", (mid, entity, text, evidence, category, t, t))
    c.execute("INSERT INTO mem_fts VALUES(?,?,?)", (mid, entity, text)); c.commit()
    return mid

def replace(mid: str, text: str, evidence: str | None = None) -> bool:
    _guard(text); c = _conn(); t = _dt.datetime.now().isoformat(timespec="seconds")
    n = c.execute("UPDATE mem SET text=?, updated=?, evidence=COALESCE(?,evidence) WHERE id=?", (text, t, evidence, mid)).rowcount
    c.execute("UPDATE mem_fts SET text=? WHERE id=?", (text, mid)); c.commit()
    return n > 0

def remove(mid: str) -> bool:
    c = _conn(); n = c.execute("DELETE FROM mem WHERE id=?", (mid,)).rowcount
    c.execute("DELETE FROM mem_fts WHERE id=?", (mid,)); c.commit()
    return n > 0

def _age(ts: str) -> str:
    try:
        d = _dt.datetime.now() - _dt.datetime.fromisoformat(ts)
    except Exception:
        return "?"
    if d.days >= 1:
        return f"{d.days}일 전"
    h = d.seconds // 3600
    return f"{h}시간 전" if h else "방금"

def read(entity: str, limit: int = 200) -> list[dict]:
    rows = _conn().execute("SELECT id,entity,text,evidence,category,updated FROM mem WHERE entity=? ORDER BY updated DESC LIMIT ?",
                           (entity, limit)).fetchall()
    return [dict(zip(["id", "entity", "text", "evidence", "category", "updated"], r)) | {"age": _age(r[5])} for r in rows]

def _qtokens(s: str) -> list[str]:
    s = s.lower()
    toks = re.findall(r"[a-z0-9][a-z0-9.\-_]{2,}", s)              # 영문/숫자 단어(3자 이상)
    for w in re.findall(r"[가-힣]{2,}", s):                           # 한국어: 2-gram (조사 붙은 어형도 매칭)
        toks += [w[k:k + 2] for k in range(len(w) - 1)]
    return list(dict.fromkeys(toks))

_STOP = {"해줘", "주세요", "그려", "려줘", "해서", "에서", "으로", "하고", "있는", "the", "and", "for", "with"}

def search(query: str, limit: int = 8, entities: list[str] | None = None, min_score: float = 2.0) -> list[dict]:
    """한국어 2-gram + 영문 단어 겹침 점수(희소 토큰 가중). 수천 행 규모를 가정한 단순·견고한 검색."""
    import math
    q = [t for t in _qtokens(query) if t not in _STOP]
    if not q:
        return []
    sql = "SELECT id,entity,text,evidence,category,updated FROM mem"
    args: list = []
    if entities:
        sql += " WHERE entity IN (%s)" % ",".join("?" * len(entities)); args += entities
    rows = _conn().execute(sql + " ORDER BY updated DESC LIMIT 5000", args).fetchall()
    if not rows:
        return []
    texts = [r[2].lower() for r in rows]
    N = len(rows)
    df = {t: sum(t in x for x in texts) for t in q}
    out = []
    for r, x in zip(rows, texts):
        s = sum((1.0 + math.log(1 + N / (1 + df[t]))) * (2.0 if re.match(r"[a-z0-9]", t) else 1.0) for t in q if t in x)
        if s >= min_score:
            out.append(dict(zip(["id", "entity", "text", "evidence", "category", "updated"], r)) | {"score": round(s, 2), "age": _age(r[5])})
    return sorted(out, key=lambda d: -d["score"])[:limit]

def format_recall(rows: list[dict], header: str = "[Memory] 회상된 기록 (오래되었을 수 있음 — 사용 전 확인)") -> str:
    if not rows:
        return ""
    lines = [header] + [f"- [{r['age']}] [{r['evidence']}] ({r['entity']}) {r['text']}  [{r['id']}]" for r in rows]
    return "\n".join(lines)
