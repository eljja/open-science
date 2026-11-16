"""MCP 서버 3종 스모크 테스트 — 실제 stdio MCP 클라이언트로 접속해 도구를 호출한다.
    python tests/smoke_test.py [--offline] [--inproc]
프로젝트 루트는 임시 폴더(tests/_sandbox)를 사용한다.
--inproc : 서브프로세스 없이 메모리 내 MCP 전송으로 같은 도구를 호출(mcp>=2, 네임드 파이프가 막힌 샌드박스용)."""
import asyncio, contextlib, importlib, json, os, shutil, sys, tempfile
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent
SANDBOX = HERE / "_sandbox"
OFFLINE = "--offline" in sys.argv
INPROC = "--inproc" in sys.argv
results = []

def rec(name, ok, detail=""):
    ok = bool(ok)
    results.append((name, ok, detail)); print(("✓" if ok else "✗"), name, "-", str(detail)[:160])

@contextlib.asynccontextmanager
async def connect(module, env_extra=None):
    env = dict(os.environ, SCIHARNESS_ROOT=str(SANDBOX), PYTHONIOENCODING="utf-8", **(env_extra or {}))
    if INPROC:
        # 샌드박스는 Windows ACL 변경(SetFileSecurity)을 막는다 → 테스트 모드에서만 jupyter 공식 우회 옵션 사용
        env.setdefault("JUPYTER_ALLOW_INSECURE_WRITES", "1")
        os.environ.update(env)
        from mcp.client import Client
        mod = importlib.import_module(module)
        async with Client(mod.mcp) as c:
            yield c
        return
    params = StdioServerParameters(command=sys.executable, args=["-m", module], env=env, cwd=str(SANDBOX))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            yield s

def is_err(r):
    return bool(getattr(r, "isError", None) or getattr(r, "is_error", None))

def text_of(r):
    return "\n".join(c.text for c in r.content if getattr(c, "type", "") == "text")

async def test_kernel():
    async with connect("sciharness.mcp_servers.kernel_server") as s:
        if True:
            tools = {t.name for t in (await s.list_tools()).tools}
            rec("kernel: tools listed", {"python_exec", "view_image", "artifact_save", "artifact_lineage", "capsule_freeze"} <= tools, sorted(tools))
            a = await s.call_tool("python_exec", {"code": "x = 21\nprint('x set')"})
            b = await s.call_tool("python_exec", {"code": "print(x*2)"})
            rec("kernel: state persists across calls", "42" in text_of(b), text_of(b))
            code = (
                "import numpy as np, pandas as pd, matplotlib.pyplot as plt\n"
                "from sciharness.figures import apply_figure_style, save_figure, panel_letter, FOCAL, NEUTRAL\n"
                "apply_figure_style(lang='ko')\n"
                "rng=np.random.default_rng(0); t=np.linspace(0,10,40)\n"
                "fig,(a1,a2)=plt.subplots(1,2,figsize=(6.6,2.6))\n"
                "for k in range(8): a1.plot(t,np.exp(-t/4)+rng.normal(0,.04,t.size),color=NEUTRAL,lw=.6,alpha=.5)\n"
                "a1.plot(t,np.exp(-t/4),color=FOCAL,lw=1.8); a1.set_xlabel('시간 (s)'); a1.set_ylabel('신호 (a.u.)')\n"
                "a1.set_title('8회 반복 측정의 지수 감쇠'); panel_letter(a1,'a')\n"
                "g=pd.DataFrame({'조건':np.repeat(['대조','처리'],12),'값':np.r_[rng.normal(1,.2,12),rng.normal(1.4,.2,12)]})\n"
                "for i,(k,v) in enumerate(g.groupby('조건',sort=False)['값']):\n"
                "    a2.scatter(np.full(len(v),i)+rng.uniform(-.12,.12,len(v)),v,s=10,color=[NEUTRAL,FOCAL][i]); a2.hlines(v.median(),i-.25,i+.25,color='k')\n"
                "a2.set_xticks([0,1],['대조','처리']); a2.set_ylabel('값'); a2.set_title('처리군 중앙값이 더 높음 (n=12/군)'); panel_letter(a2,'b'); a2.margins(0.08)\n"
                "fig.tight_layout(); meta=save_figure(fig,'outputs/figures/demo_fig',caption='데모',data=g); plt.show()\n"
                "print('overlaps', len(meta['overlaps']))\n")
            c = await s.call_tool("python_exec", {"code": code})
            imgs = [x for x in c.content if getattr(x, "type", "") == "image"]
            rec("kernel: figure saved + inline preview returned", "demo_fig" in text_of(c) and len(imgs) >= 1, text_of(c)[-200:])
            v = await s.call_tool("view_image", {"path": "outputs/figures/demo_fig.png", "crop": [0, 0, 0.5, 1]})
            rec("kernel: view_image returns image", any(getattr(x, "type", "") == "image" for x in v.content), text_of(v))
            sv = json.loads(text_of(await s.call_tool("artifact_save", {"paths": ["outputs/figures/demo_fig.png"], "description": "데모 그림"})))
            rec("kernel: artifact_save version + producing cell", sv[0].get("version") == 1 and sv[0].get("producing_cells"), sv[0])
            sv2 = json.loads(text_of(await s.call_tool("artifact_save", {"paths": ["outputs/figures/demo_fig.png"], "description": "데모 그림 v2"})))
            rec("kernel: second save -> version 2 of same artifact", sv2[0]["artifact_id"] == sv[0]["artifact_id"] and sv2[0]["version"] == 2, sv2[0]["version"])
            ln = json.loads(text_of(await s.call_tool("artifact_lineage", {"path_or_version": sv[0]["version_id"]})))
            rec("kernel: lineage returns generating code", "save_figure" in (ln["cells"][0]["code"] if ln["cells"] else ""), [c_["cell"] for c_ in ln["cells"]])
            bad = json.loads(text_of(await s.call_tool("artifact_save", {"paths": ["outputs/nope.png"]})))
            rec("kernel: missing file reported as error (no false success)", "error" in bad[0], bad[0])
            e = await s.call_tool("python_exec", {"code": "1/0"})
            rec("kernel: traceback surfaced", "ZeroDivisionError" in text_of(e), text_of(e)[-80:])
            cap = json.loads(text_of(await s.call_tool("capsule_freeze", {"paths": ["outputs/figures"], "label": "데모 v1"})))
            rec("kernel: capsule freeze", cap["n_files"] >= 3, cap)

async def test_memory():
    db = SANDBOX / "mem.db"
    async with connect("sciharness.mcp_servers.memory_server", {"SCIHARNESS_MEMORY_DB": str(db),
                       "SCIHARNESS_SKILL_DIRS": str(HERE.parent / "harness" / "skills")}) as s:
        if True:
            mid = text_of(await s.call_tool("memory_write", {"text": "사용자는 모든 보고서를 한국어와 Confluence용 HTML로 받기를 원한다.", "entity": "profile", "evidence": "stated"}))
            rec("memory: write", mid.startswith("mem_"), mid)
            hit = text_of(await s.call_tool("memory_search", {"query": "보고서 HTML 형식"}))
            rec("memory: search (Korean trigram)", mid in hit, hit[:120])
            blk = await s.call_tool("memory_write", {"text": "카드 1234 5678 9012 3456", "entity": "profile"})
            rec("memory: sensitive text rejected", is_err(blk) or "민감" in text_of(blk), text_of(blk)[:80])
            sk = text_of(await s.call_tool("search_skills", {"query": "논문 그림 스타일 figure"}))
            rec("memory: search_skills finds figure skill", "scientific-figures" in sk, sk[:160])

async def test_scholar():
    async with connect("sciharness.mcp_servers.scholar_server") as s:
        if True:
            ok = json.loads(text_of(await s.call_tool("doi_resolve", {"doi": "10.1038/s41586-021-03819-2", "bibtex": True})))
            rec("scholar: real DOI resolves (AlphaFold 2021)", ok.get("found") and "AlphaFold" in (ok.get("title") or ""), ok.get("title"))
            fake = json.loads(text_of(await s.call_tool("doi_resolve", {"doi": "10.1038/fake-doi-000000", "bibtex": False})))
            rec("scholar: fabricated DOI -> found=false", fake.get("found") is False, fake)
            sr = json.loads(text_of(await s.call_tool("crossref_search", {"query": "charge trap flash silicon nitride retention", "rows": 3})))
            rec("scholar: crossref search", len(sr) == 3, [x["title"][:50] for x in sr])
            oa = json.loads(text_of(await s.call_tool("openalex_search", {"query": "x"}))) if not os.environ.get("OPENALEX_API_KEY") else {"skipped": "key"}
            rec("scholar: openalex without key skips cleanly", "skipped" in oa, oa)

async def main():
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX, ignore_errors=True)
    SANDBOX.mkdir(parents=True)
    await test_kernel(); await test_memory()
    if not OFFLINE:
        try:
            await test_scholar()
        except Exception as e:
            rec("scholar: network tests", False, repr(e))
    n_ok = sum(ok for _, ok, _ in results)
    print(f"\n{n_ok}/{len(results)} passed")
    (HERE / "smoke_results.json").write_text(json.dumps([{"test": n, "ok": bool(o), "detail": str(d)[:300]} for n, o, d in results],
                                                       ensure_ascii=False, indent=1), encoding="utf-8")
    sys.exit(0 if n_ok == len(results) else 1)

if __name__ == "__main__":
    asyncio.run(main())
