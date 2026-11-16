"""계보(lineage)/출처(provenance) 기록: append-only JSONL. 모든 도구가 같은 포맷을 쓴다."""
from __future__ import annotations
import datetime as _dt, hashlib, json, os
from pathlib import Path

def project_root() -> Path:
    return Path(os.environ.get("SCIHARNESS_ROOT") or os.getcwd()).resolve()

def state_dir(root: Path | None = None) -> Path:
    d = (root or project_root()) / ".science"
    d.mkdir(parents=True, exist_ok=True)
    return d

def now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")  # 시간대 포함(플러그인 UTC 기록과 비교 가능)

def sha256(path: str | Path, n: int = 16) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:n]

def append_event(kind: str, root: Path | None = None, **fields) -> dict:
    ev = {"t": now(), "kind": kind, **fields}
    with open(state_dir(root) / "lineage.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return ev

def read_events(root: Path | None = None, kind: str | None = None) -> list[dict]:
    p = state_dir(root) / "lineage.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if kind is None or ev.get("kind") == kind:
            out.append(ev)
    return out

def producers_of(path: str | Path, root: Path | None = None) -> list[dict]:
    """주어진 파일을 쓴 커널 셀 이벤트 목록(최신 우선)."""
    rp = str(Path(path).resolve())
    hits = [e for e in read_events(root, "cell") if rp in e.get("files_written", [])]
    return hits[::-1]
