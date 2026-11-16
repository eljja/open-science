"""scholar MCP 서버 — 문헌 검색과 '인용 실존 검증'.
핵심 규칙: 모델이 기억으로 만든 인용은 doi_resolve / verify_citations 로 실존을 확인하기 전까지 보고서에 넣지 않는다.
소스: Crossref(키 불필요), OpenAlex(OPENALEX_API_KEY 필요, 없으면 건너뜀), arXiv, PubMed(E-utilities).
"""
from __future__ import annotations
import json, os, re, xml.etree.ElementTree as ET
from difflib import SequenceMatcher
import httpx
from sciharness.mcp_servers._compat import Server as FastMCP

mcp = FastMCP("scholar")
TIMEOUT = float(os.environ.get("SCHOLAR_TIMEOUT", "30"))
MAILTO = os.environ.get("CROSSREF_MAILTO")  # 선택: Crossref polite pool

def _cli():
    return httpx.Client(timeout=TIMEOUT, follow_redirects=True)

def _json(r):
    """JSON 응답만 받는다. 차단/프록시/HTML 응답은 구조화된 오류로 바꿔 상위에서 '검증 실패'로 처리하게 한다."""
    try:
        return r.json()
    except Exception:
        raise RuntimeError(f"비JSON 응답 HTTP {r.status_code} ({r.headers.get('content-type','?')}) — 네트워크 차단 또는 서비스 오류")

def _safe(fn):
    import functools
    @functools.wraps(fn)
    def w(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"[:400], "note": "검색/검증이 실행되지 않음 — 결과를 '확인됨'으로 보고하지 말 것"}, ensure_ascii=False)
    return w

def _cr_item(it: dict) -> dict:
    au = [f"{a.get('family','')}, {a.get('given','')}".strip(", ") for a in it.get("author", [])[:6]]
    yr = None
    for k in ("published-print", "published-online", "issued", "created"):
        dp = (it.get(k) or {}).get("date-parts")
        if dp and dp[0] and dp[0][0]:
            yr = dp[0][0]; break
    return {"doi": it.get("DOI"), "title": (it.get("title") or [""])[0], "authors": au, "year": yr,
            "venue": (it.get("container-title") or [""])[0], "type": it.get("type"),
            "cited_by": it.get("is-referenced-by-count"), "url": it.get("URL")}

@mcp.tool()
@_safe
def crossref_search(query: str, rows: int = 10, from_year: int | None = None, until_year: int | None = None) -> str:
    """Crossref 서지 검색(키 불필요). 결과의 DOI는 실존한다(Crossref 등록)."""
    params = {"query.bibliographic": query, "rows": min(rows, 50),
              "select": "DOI,title,author,issued,published-print,published-online,created,container-title,type,is-referenced-by-count,URL"}
    flt = []
    if from_year: flt.append(f"from-pub-date:{from_year}")
    if until_year: flt.append(f"until-pub-date:{until_year}")
    if flt: params["filter"] = ",".join(flt)
    if MAILTO: params["mailto"] = MAILTO
    with _cli() as c:
        r = c.get("https://api.crossref.org/works", params=params)
    r.raise_for_status()
    return json.dumps([_cr_item(i) for i in _json(r)["message"]["items"]], ensure_ascii=False, indent=1)

@mcp.tool()
@_safe
def doi_resolve(doi: str, bibtex: bool = True) -> str:
    """DOI 실존 확인 + 메타데이터 + (선택) BibTeX. found=false 이면 그 인용은 쓰지 말 것."""
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip())
    with _cli() as c:
        r = c.get(f"https://api.crossref.org/works/{doi}")
        if r.status_code == 404:
            return json.dumps({"doi": doi, "found": False}, ensure_ascii=False)
        r.raise_for_status()
        out = {"found": True, **_cr_item(_json(r)["message"])}
        if bibtex:
            b = c.get(f"https://api.crossref.org/works/{doi}/transform/application/x-bibtex")
            out["bibtex"] = b.text.strip() if b.status_code == 200 else None
    return json.dumps(out, ensure_ascii=False, indent=1)

@mcp.tool()
@_safe
def verify_citations(citations: list[dict]) -> str:
    """인용 목록 일괄 검증. 각 항목 {doi?, title?}. DOI가 있으면 실존+제목 유사도, 없으면 제목으로 Crossref 최상위 결과와 대조.
    status: verified(유사도>=0.85) / mismatch / not_found."""
    res = []
    with _cli() as c:
        for ci in citations:
            doi, title = ci.get("doi"), (ci.get("title") or "").strip()
            rec = None
            if doi:
                r = c.get(f"https://api.crossref.org/works/{doi}")
                rec = _cr_item(_json(r)["message"]) if r.status_code == 200 else None
            elif title:
                r = c.get("https://api.crossref.org/works", params={"query.bibliographic": title, "rows": 1})
                items = _json(r)["message"]["items"] if r.status_code == 200 else []
                rec = _cr_item(items[0]) if items else None
            if rec is None:
                res.append({**ci, "status": "not_found"}); continue
            sim = SequenceMatcher(None, title.lower(), (rec["title"] or "").lower()).ratio() if title else None
            st = "verified" if (sim is None or sim >= 0.85) else "mismatch"
            res.append({**ci, "status": st, "title_similarity": None if sim is None else round(sim, 3), "matched": rec})
    return json.dumps(res, ensure_ascii=False, indent=1)

@mcp.tool()
@_safe
def openalex_search(query: str, per_page: int = 10, from_year: int | None = None) -> str:
    """OpenAlex 검색(인용수/개념 포함). OPENALEX_API_KEY 환경변수가 없으면 실행하지 않고 그 사실을 반환한다."""
    key = os.environ.get("OPENALEX_API_KEY")
    if not key:
        return json.dumps({"skipped": True, "reason": "OPENALEX_API_KEY 없음 — crossref_search 를 사용하세요"}, ensure_ascii=False)
    params = {"search": query, "per-page": min(per_page, 50), "api_key": key}
    if from_year: params["filter"] = f"from_publication_date:{from_year}-01-01"
    with _cli() as c:
        r = c.get("https://api.openalex.org/works", params=params)
    r.raise_for_status()
    out = [{"id": w["id"], "doi": (w.get("doi") or "").replace("https://doi.org/", ""), "title": w.get("title"),
            "year": w.get("publication_year"), "cited_by": w.get("cited_by_count"),
            "venue": ((w.get("primary_location") or {}).get("source") or {}).get("display_name"),
            "oa_url": (w.get("open_access") or {}).get("oa_url")} for w in _json(r).get("results", [])]
    return json.dumps(out, ensure_ascii=False, indent=1)

@mcp.tool()
@_safe
def arxiv_search(query: str, max_results: int = 10) -> str:
    """arXiv 검색(프리프린트). 동료심사 전 문헌임을 보고서에 표시할 것."""
    with _cli() as c:
        r = c.get("https://export.arxiv.org/api/query", params={"search_query": f"all:{query}", "max_results": min(max_results, 50)})
    r.raise_for_status()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(r.text); out = []
    for e in root.findall("a:entry", ns):
        out.append({"id": e.findtext("a:id", "", ns), "title": " ".join(e.findtext("a:title", "", ns).split()),
                    "published": e.findtext("a:published", "", ns)[:10],
                    "authors": [a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)][:6],
                    "summary": " ".join(e.findtext("a:summary", "", ns).split())[:400]})
    return json.dumps(out, ensure_ascii=False, indent=1)

@mcp.tool()
@_safe
def pubmed_search(query: str, retmax: int = 10) -> str:
    """PubMed 검색(E-utilities). PMID, 제목, 저널, 연도, DOI 반환."""
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    with _cli() as c:
        ids = _json(c.get(f"{base}/esearch.fcgi", params={"db": "pubmed", "term": query, "retmax": min(retmax, 50), "retmode": "json"}))["esearchresult"]["idlist"]
        if not ids:
            return "[]"
        s = _json(c.get(f"{base}/esummary.fcgi", params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"}))["result"]
    out = []
    for i in ids:
        d = s.get(i, {})
        doi = next((a["value"] for a in d.get("articleids", []) if a.get("idtype") == "doi"), None)
        out.append({"pmid": i, "title": d.get("title"), "journal": d.get("fulljournalname"), "year": (d.get("pubdate") or "")[:4], "doi": doi})
    return json.dumps(out, ensure_ascii=False, indent=1)

def main():
    mcp.run(transport=os.environ.get("MCP_TRANSPORT", "stdio"))

if __name__ == "__main__":
    main()
