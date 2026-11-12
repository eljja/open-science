"""저장소 내용을 GitHub 에 커밋(REST git-data API). git 실행파일이 없어도 동작한다.
    $env:GITHUB_TOKEN = "<토큰>"   # repo 권한
    python tools/push_to_github.py --repo eljja/open-science --branch main -m "메시지" [--dry-run]
.gitignore 패턴(단순 접두/글롭)과 테스트 실행 폴더는 제외한다. 토큰은 출력하지 않는다.
"""
import argparse, base64, fnmatch, os, sys, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"__pycache__", ".git", "_sandbox", "_install_runs", "_hook_runs", "_install_demo", "dist", ".science"}

def ignored(rel: str, pats: list[str]) -> bool:
    parts = rel.split("/")
    if any(p in SKIP_DIRS or p.endswith(".egg-info") for p in parts):
        return True
    for pat in pats:
        pat = pat.strip()
        if not pat or pat.startswith("#"):
            continue
        if pat.endswith("/") and (rel + "/").startswith(pat):
            return True
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(parts[-1], pat):
            return True
    return False

def files():
    pats = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines() if (ROOT / ".gitignore").exists() else []
    out, skipped = [], []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if ignored(rel, pats):
            continue
        try:
            out.append((rel, p.read_bytes()))
        except OSError as e:
            skipped.append((rel, str(e)[:80]))
    return out, skipped

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="eljja/open-science"); ap.add_argument("--branch", default="main")
    ap.add_argument("-m", "--message", default="open-science harness 업데이트"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    fs, skipped = files()
    print(f"{len(fs)}개 파일, {sum(len(b) for _, b in fs)//1024} KB" + (f", 읽기 실패 {len(skipped)}개: {skipped[:5]}" if skipped else ""))
    if a.dry_run:
        for r, b in fs: print(f"  {len(b):>8}  {r}")
        return
    tok = os.environ.get("GITHUB_TOKEN")
    if not tok:
        sys.exit("GITHUB_TOKEN 환경변수가 필요합니다")
    api = f"https://api.github.com/repos/{a.repo}"
    H = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}
    with httpx.Client(headers=H, timeout=60) as c:
        ref = c.get(f"{api}/git/ref/heads/{a.branch}")
        if ref.status_code == 200:
            parent = ref.json()["object"]["sha"]; base_tree = c.get(f"{api}/git/commits/{parent}").json()["tree"]["sha"]
        else:
            parent, base_tree = None, None
        tree = []
        for i, (rel, b) in enumerate(fs):
            for attempt in range(3):
                r = c.post(f"{api}/git/blobs", json={"content": base64.b64encode(b).decode(), "encoding": "base64"})
                if r.status_code == 201: break
                time.sleep(2 * (attempt + 1))
            r.raise_for_status()
            tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": r.json()["sha"]})
            if (i + 1) % 25 == 0: print(f"  blobs {i+1}/{len(fs)}")
        body = {"tree": tree}
        if base_tree: body["base_tree"] = base_tree
        t = c.post(f"{api}/git/trees", json=body); t.raise_for_status()
        cm = {"message": a.message, "tree": t.json()["sha"], "parents": [parent] if parent else []}
        k = c.post(f"{api}/git/commits", json=cm); k.raise_for_status(); sha = k.json()["sha"]
        if parent:
            u = c.patch(f"{api}/git/refs/heads/{a.branch}", json={"sha": sha})
        else:
            u = c.post(f"{api}/git/refs", json={"ref": f"refs/heads/{a.branch}", "sha": sha})
        u.raise_for_status()
        print("commit", sha[:10], "→", f"https://github.com/{a.repo}/tree/{a.branch}")

if __name__ == "__main__":
    main()
