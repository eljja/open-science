"""science-kernel MCP 서버 — 지속(persistent) Jupyter 커널 + 산출물(artifact) 저장소 + 계보 + 이미지 보기.

Claude Science의 python 커널 / save_artifacts / host.view_image / lineage 동작을 표준 MCP 도구로 제공한다.
실행:  python -m sciharness.mcp_servers.kernel_server   (환경변수 SCIHARNESS_ROOT = 프로젝트 루트)
"""
from __future__ import annotations
import base64, io, json, os, re, shutil, sys, time, uuid
from pathlib import Path
from sciharness.mcp_servers._compat import Server as FastMCP, Image
from jupyter_client import KernelManager
from sciharness import lineage as L

mcp = FastMCP("science-kernel")
ROOT = L.project_root()
ST = L.state_dir(ROOT)
(ST / "cells").mkdir(exist_ok=True); (ST / "previews").mkdir(exist_ok=True); (ST / "outputs").mkdir(exist_ok=True)
STORE = ST / "artifact_store"; STORE.mkdir(exist_ok=True)
# Jupyter 연결 파일을 프로젝트 안에 둔다(시스템 임시 폴더 권한 문제 회피, 상태를 한곳에).
(ST / "runtime").mkdir(exist_ok=True)
os.environ.setdefault("JUPYTER_RUNTIME_DIR", str(ST / "runtime"))
MANIFEST = ROOT / "artifacts" / "manifest.jsonl"
KERNELS: dict[str, tuple] = {}
MAX_TEXT = int(os.environ.get("SCIHARNESS_MAX_OUTPUT", "6000"))
WATCH = [p for p in os.environ.get("SCIHARNESS_WATCH", "outputs").split(os.pathsep) if p]
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

BOOT = """
import os, sys
os.chdir(%r)
try:
    import matplotlib
    get_ipython().run_line_magic('matplotlib', 'inline')   # plt.show() -> 인라인 미리보기 이미지
    matplotlib.rcParams['figure.dpi'] = 110
except Exception:
    pass
""" % str(ROOT)

def _kernel(session: str, kernel_name: str = "python3"):
    if session not in KERNELS:
        cf = ST / "runtime" / f"kernel-{session}-{uuid.uuid4().hex[:8]}.json"
        km = KernelManager(kernel_name=kernel_name, connection_file=str(cf))
        km.start_kernel(cwd=str(ROOT))
        kc = km.client(); kc.start_channels(); kc.wait_for_ready(timeout=90)
        KERNELS[session] = (km, kc, kernel_name)
        if kernel_name.startswith("python"):
            _run(kc, BOOT, 60)
    return KERNELS[session]

def _snapshot() -> dict:
    snap = {}
    for w in WATCH:
        base = (ROOT / w)
        if base.exists():
            for p in base.rglob("*"):
                if p.is_file():
                    try:
                        snap[str(p.resolve())] = p.stat().st_mtime
                    except OSError:
                        pass
    return snap

def _run(kc, code: str, timeout: float):
    mid = kc.execute(code, store_history=True)
    text, imgs, err = [], [], None
    t0 = time.time()
    while True:
        try:
            msg = kc.get_iopub_msg(timeout=max(1.0, timeout - (time.time() - t0)))
        except Exception:
            return "".join(text), imgs, f"TIMEOUT after {timeout}s"
        if msg["parent_header"].get("msg_id") != mid:
            continue
        t, c = msg["msg_type"], msg["content"]
        if t == "stream":
            text.append(c["text"])
        elif t in ("execute_result", "display_data"):
            d = c.get("data", {})
            if "image/png" in d:
                imgs.append(base64.b64decode(d["image/png"]))
            elif "text/plain" in d:
                text.append(d["text/plain"] + "\n")
        elif t == "error":
            err = ANSI.sub("", "\n".join(c.get("traceback", [])))[-4000:]
        elif t == "status" and c.get("execution_state") == "idle":
            break
    return "".join(text), imgs, err

@mcp.tool()
def python_exec(code: str, session: str = "main", timeout: float = 900, kernel: str = "python3") -> list:
    """지속 커널에서 코드 실행. 변수/임포트는 같은 session 안에서 호출 간 유지된다.
    - 출력은 '다음 결정을 좌우하는 값'만 print 할 것. 긴 출력은 .science/outputs/ 파일로 저장되고 앞뒤만 반환된다.
    - plt.show()/display 이미지는 미리보기로 반환된다(최종 그림은 save_figure로 파일 저장 후 artifact_save).
    - kernel: 'python3'(서버와 같은 환경) 또는 설치된 다른 kernelspec 이름(예: 'ir', 'conda-env-xyz').
    """
    km, kc, kn = _kernel(session, kernel)
    seq = len(list((ST / "cells").glob("*.py"))) + 1
    cell_id = f"c{seq:05d}"
    (ST / "cells" / f"{cell_id}.py").write_text(code, encoding="utf-8")
    before = _snapshot(); t0 = time.time()
    out, imgs, err = _run(kc, code, timeout)
    if err and err.startswith("TIMEOUT"):
        km.interrupt_kernel()
    after = _snapshot()
    written = sorted(p for p, m in after.items() if before.get(p) != m)
    _add_pending([p for p in written if p.lower().endswith(".png") and "figures" in Path(p).parts])
    L.append_event("cell", ROOT, cell=cell_id, session=session, kernel=kn, seconds=round(time.time() - t0, 2),
                   ok=err is None, files_written=written, code_file=f".science/cells/{cell_id}.py")
    body = out
    if len(body) > MAX_TEXT:
        fp = ST / "outputs" / f"{cell_id}.txt"; fp.write_text(body, encoding="utf-8")
        body = body[: MAX_TEXT // 2] + f"\n... [{len(out)}자 중 생략 — 전체: {fp.relative_to(ROOT)}] ...\n" + body[-MAX_TEXT // 3:]
    parts = [f"[{cell_id} · {session} · {round(time.time()-t0,1)}s]" + ("" if err is None else " ERROR"), body or "(출력 없음)"]
    if err:
        parts.append("Traceback:\n" + err)
    if written:
        parts.append("작성/수정된 파일: " + ", ".join(str(Path(p).relative_to(ROOT)) if p.startswith(str(ROOT)) else p for p in written[:20]))
    res: list = ["\n".join(parts)]
    for i, png in enumerate(imgs[:4]):
        pp = ST / "previews" / f"{cell_id}_{i}.png"; pp.write_bytes(png)
        res.append(Image(data=png, format="png"))
    return res

@mcp.tool()
def kernel_list() -> str:
    """실행 중인 커널 세션 목록."""
    return json.dumps({k: {"kernel": v[2], "alive": v[0].is_alive()} for k, v in KERNELS.items()}, ensure_ascii=False)

@mcp.tool()
def kernel_restart(session: str = "main") -> str:
    """세션 커널 재시작(상태 초기화)."""
    if session in KERNELS:
        km, kc, kn = KERNELS.pop(session)
        kc.stop_channels(); km.shutdown_kernel(now=True)
    return f"{session} 재시작 예정(다음 python_exec에서 새로 시작)"

@mcp.tool()
def view_image(path: str, crop: list[float] | None = None, max_side: int = 1568) -> list:
    """이미지 파일(또는 그 일부)을 모델이 직접 본다. crop=[x0,y0,x1,y1] 픽셀 또는 0~1 비율.
    그림 '렌더 후 검증' 단계에서 반드시 사용: 겹침, 대비, 범례 위치, 잘림을 눈으로 확인."""
    from PIL import Image as PI
    p = (ROOT / path) if not os.path.isabs(path) else Path(path)
    im = PI.open(p).convert("RGB")
    if crop:
        x0, y0, x1, y1 = crop
        if max(crop) <= 1.0:
            W_, H_ = im.size; x0, x1, y0, y1 = x0 * W_, x1 * W_, y0 * H_, y1 * H_
        im = im.crop((int(x0), int(y0), int(x1), int(y1)))
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO(); im.save(buf, format="PNG")
    L.append_event("view_image", ROOT, path=str(p), crop=crop)
    _mark_reviewed(str(p.resolve()))
    return [f"{p.name} {im.size[0]}x{im.size[1]}px" + (f" crop={crop}" if crop else ""), Image(data=buf.getvalue(), format="png")]

def _add_pending(paths: list[str]):
    """새로 저장된 최종 그림(outputs/**/figures/*.png)을 '미검토'로 등록. view_image 가 해제한다."""
    if not paths:
        return
    f = ST / "pending_figure_review.json"
    try:
        pend = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    except Exception:
        pend = []
    for p in paths:
        if p not in pend:
            pend.append(p)
    f.write_text(json.dumps(pend, ensure_ascii=False), encoding="utf-8")

def _mark_reviewed(abs_path: str):
    f = ST / "pending_figure_review.json"
    if f.exists():
        try:
            pend = [x for x in json.loads(f.read_text(encoding="utf-8")) if Path(x).resolve() != Path(abs_path)]
            f.write_text(json.dumps(pend, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

def _manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    return [json.loads(l) for l in MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]

@mcp.tool()
def artifact_save(paths: list[str], description: str = "", version_of: str | None = None,
                  data_status: str = "measured") -> str:
    """파일을 '사용자에게 보이는 영구 산출물'로 등록. 불변 사본 + sha256 + 생성 셀(계보)을 기록한다.
    - version_of: 기존 artifact_id 를 주면 같은 산출물의 새 버전으로 저장.
    - data_status: measured(측정) / simulated(계산·모의) / illustrative(설명용 예시) — 수치 진본성 라벨.
    반환: artifact_id, version_id. 이후 보고서/답변에서 이 id로 참조한다."""
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    man = _manifest(); out = []
    for ps in paths:
        p = (ROOT / ps) if not os.path.isabs(ps) else Path(ps)
        if not p.exists():
            out.append({"path": ps, "error": "파일 없음 — 저장 실패(성공이라고 보고하지 말 것)"}); continue
        rel = str(p.resolve().relative_to(ROOT)) if str(p.resolve()).startswith(str(ROOT)) else str(p)
        aid = version_of or next((m["artifact_id"] for m in man[::-1] if m["path"] == rel), None) or "a_" + uuid.uuid4().hex[:8]
        vers = [m for m in man if m["artifact_id"] == aid]
        vid = "v_" + uuid.uuid4().hex[:8]
        dst = STORE / vid; dst.mkdir(parents=True); shutil.copy2(p, dst / p.name)
        prod = L.producers_of(p, ROOT)
        rec = {"artifact_id": aid, "version_id": vid, "version": len(vers) + 1, "path": rel, "sha256": L.sha256(p),
               "bytes": p.stat().st_size, "description": description, "data_status": data_status, "created": L.now(),
               "producing_cells": [e["cell"] for e in prod[:3]], "stored_copy": str((dst / p.name).relative_to(ROOT))}
        with open(MANIFEST, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        man.append(rec); out.append(rec)
        L.append_event("artifact_save", ROOT, **{k: rec[k] for k in ("artifact_id", "version_id", "path", "sha256")})
    return json.dumps(out, ensure_ascii=False, indent=1)

@mcp.tool()
def artifact_list(search: str = "", limit: int = 50) -> str:
    """등록된 산출물 목록(최신 우선). search 는 경로/설명 부분 문자열."""
    man = [m for m in _manifest() if search.lower() in (m["path"] + m["description"]).lower()]
    return json.dumps(man[::-1][:limit], ensure_ascii=False, indent=1)

@mcp.tool()
def artifact_lineage(path_or_version: str) -> str:
    """산출물(경로 또는 version_id)을 만든 셀 코드와 실행 기록을 반환 — '이 그림은 어떤 코드로 만들었나'에 답한다."""
    man = _manifest()
    rec = next((m for m in man if m["version_id"] == path_or_version), None)
    path = ROOT / (rec["path"] if rec else path_or_version)
    cells = L.producers_of(path, ROOT)
    out = {"record": rec, "cells": []}
    for e in cells[:3]:
        code = (ROOT / e["code_file"]).read_text(encoding="utf-8") if (ROOT / e["code_file"]).exists() else ""
        out["cells"].append({"cell": e["cell"], "t": e["t"], "session": e["session"], "code": code[:6000]})
    return json.dumps(out, ensure_ascii=False, indent=1)

@mcp.tool()
def capsule_freeze(paths: list[str], label: str, note: str = "") -> str:
    """증거 캡슐: 원고/그림/데이터/스크립트 묶음의 해시와 사본을 한 시점으로 동결(투고본, 보고서 v1 등)."""
    cid = f"cap_{time.strftime('%Y%m%d_%H%M%S')}_{re.sub(r'[^A-Za-z0-9가-힣_-]', '_', label)[:40]}"
    d = ROOT / "artifacts" / "capsules" / cid; d.mkdir(parents=True)
    items = []
    for ps in paths:
        p = (ROOT / ps) if not os.path.isabs(ps) else Path(ps)
        files = [p] if p.is_file() else [x for x in p.rglob("*") if x.is_file()] if p.exists() else []
        for f in files:
            rel = f.resolve().relative_to(ROOT) if str(f.resolve()).startswith(str(ROOT)) else Path(f.name)
            (d / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copy2(f, d / rel)
            items.append({"path": str(rel), "sha256": L.sha256(f), "bytes": f.stat().st_size})
    man = {"capsule": cid, "label": label, "note": note, "created": L.now(), "items": items}
    (d / "CAPSULE.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    L.append_event("capsule", ROOT, capsule=cid, n=len(items))
    return json.dumps({"capsule": cid, "n_files": len(items), "dir": str(d.relative_to(ROOT))}, ensure_ascii=False)

def main():
    mcp.run()

if __name__ == "__main__":
    main()
