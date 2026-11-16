"""오프라인 설치 번들 빌더 — 인터넷이 되는 PC 에서 한 번 실행한다(npm 불필요, Python 만 있으면 됨).

    python tools/offline/build_bundle.py                                   # Windows x64, OpenCode 2+1, Python 3.11 wheel
    python tools/offline/build_bundle.py --opencode v2 --py 3.12 --platform windows-x64 --zip
    python tools/offline/build_bundle.py --platform linux-x64 --pip-platform manylinux2014_x86_64

번들 구성
  bin/opencode2/opencode(.exe)   OpenCode 2 바이너리 (npm 레지스트리 @opencode/cli-<platform>, sha512 무결성 검증)
  bin/opencode1/opencode(.exe)   OpenCode 1.x 바이너리 (opencode-<platform>)
  wheels/                        sciharness + 의존성 wheel (대상 플랫폼/파이썬 버전용)
  kit/                           open-science 키트(harness, python, tools, tests, docs)
  models/models.json             (선택) models.dev 카탈로그 스냅샷 — V1 OPENCODE_MODELS_PATH 용
  install_offline.ps1 / install_offline.sh / OFFLINE_README.md
  manifest.json, SHA256SUMS.txt
"""
from __future__ import annotations
import argparse, os, base64, hashlib, io, json, platform, shutil, subprocess, sys, tarfile, time, zipfile
from pathlib import Path
import httpx

KIT = Path(__file__).resolve().parents[2]
REG = "https://registry.npmjs.org"
PKGS = {"v2": ("@opencode/cli", "@opencode/cli-{plat}"), "v1": ("opencode-ai", "opencode-{plat}")}
PIP_PLAT = {"windows-x64": "win_amd64", "windows-arm64": "win_arm64", "linux-x64": "manylinux2014_x86_64",
            "linux-arm64": "manylinux2014_aarch64", "darwin-arm64": "macosx_11_0_arm64", "darwin-x64": "macosx_10_9_x86_64"}
REQS = ["mcp>=1.2", "jupyter_client>=8", "ipykernel>=6", "matplotlib>=3.7", "numpy", "pandas", "httpx>=0.25", "markdown>=3.4", "pyyaml"]

def npm_meta(name: str) -> dict:
    return httpx.get(f"{REG}/{name.replace('/', '%2f')}", timeout=60).json()

def fetch_opencode(track: str, plat: str, version: str | None, dest: Path) -> dict:
    main, platpkg = PKGS[track]
    m = npm_meta(main)
    ver = version or m["dist-tags"]["latest"]
    if track == "v1" and not ver.startswith("1."):
        ver = sorted([v for v in m["versions"] if v.startswith("1.") and "-" not in v], key=lambda v: tuple(map(int, v.split("."))))[-1]
    pname = platpkg.format(plat=plat)
    od = m["versions"][ver].get("optionalDependencies", {})
    if pname not in od:
        raise SystemExit(f"{main}@{ver} 에 {pname} 없음. 가능한 플랫폼: {sorted(od)}")
    pm = httpx.get(f"{REG}/{pname.replace('/', '%2f')}/{od[pname]}", timeout=60).json()
    url, integ = pm["dist"]["tarball"], pm["dist"]["integrity"]
    print(f"  {pname}@{od[pname]} 다운로드 ...", flush=True)
    data = httpx.get(url, timeout=600, follow_redirects=True).content
    algo, b64 = integ.split("-", 1)
    if base64.b64encode(hashlib.new(algo, data).digest()).decode() != b64:
        raise SystemExit(f"무결성 불일치: {pname}")
    tf = tarfile.open(fileobj=io.BytesIO(data))
    exe = [n for n in tf.getnames() if n.startswith("package/bin/") and Path(n).name in ("opencode", "opencode.exe")]
    if not exe:
        raise SystemExit(f"{pname} 안에 bin/opencode 가 없음: {tf.getnames()[:10]}")
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / Path(exe[0]).name
    out.write_bytes(tf.extractfile(exe[0]).read())
    if not out.suffix:
        out.chmod(0o755)
    return {"track": track, "package": pname, "version": od[pname], "main": f"{main}@{ver}", "integrity": integ,
            "binary": str(out.relative_to(dest.parents[1])).replace("\\", "/"), "bytes": out.stat().st_size}

def pip(*args):
    r = subprocess.run([sys.executable, "-m", "pip", *args], capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-2000:]); raise SystemExit("pip 실패")
    return r

def build_wheels(dest: Path, pyver: str, pip_plat: str):
    dest.mkdir(parents=True, exist_ok=True)
    pip("wheel", str(KIT / "python"), "--no-deps", "-w", str(dest))
    pip("download", "--dest", str(dest), "--only-binary=:all:", "--platform", pip_plat,
        "--python-version", pyver.replace(".", ""), "--implementation", "cp", *REQS)
    # ensurepip 가 없는 대상 Python 대비 pip 자체 wheel 도 포함
    pip("download", "--dest", str(dest), "--only-binary=:all:", "--no-deps", "pip")
    return sorted(p.name for p in dest.iterdir())

def kit_files():
    sys.path.insert(0, str(KIT / "tools"))
    import push_to_github as P
    return P.files()[0]

def _retry(fn, *a, tries=8):
    # Windows 백신/인덱서가 방금 만든 파일을 잠깐 잠그는 경우 대비
    for i in range(tries):
        try:
            return fn(*a)
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.5 * (i + 1))

def _sha256(p: Path):
    h = hashlib.sha256(); n = 0
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c); n += len(c)
    return h.hexdigest(), n

def sha256(p: Path) -> str:
    return _retry(_sha256, p)[0]

def prime_v1_deps(exe: Path, dest: Path, work: Path) -> str:
    """OpenCode 1.x 는 시작 시 .opencode/ 와 전역 설정 폴더에 @opencode-ai/plugin 을 npm 으로 설치한다.
    node_modules + package-lock.json 이 이미 있으면 설치를 건너뛰므로, 빌드 PC 에서 OpenCode 자신이
    설치한 결과를 ZIP 으로 묶어 둔다(플랫폼별 네이티브 모듈 포함)."""
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    proj = work / "proj"; target = proj / ".opencode"; target.mkdir(parents=True)
    home = work / "home"
    env = dict(os.environ, XDG_CONFIG_HOME=str(home / "config"), XDG_DATA_HOME=str(home / "data"),
               XDG_CACHE_HOME=str(home / "cache"), XDG_STATE_HOME=str(home / "state"),
               OPENCODE_DISABLE_AUTOUPDATE="1", OPENCODE_DISABLE_LSP_DOWNLOAD="1")
    # debug config 같은 짧은 명령은 백그라운드 npm 설치가 끝나기 전에 종료된다 →
    # 응답하지 않는 더미 MCP 를 설정해 `mcp list` 가 연결을 기다리는 동안 설치가 끝나게 한다(빌드용 임시 설정).
    (proj / "opencode.json").write_text(json.dumps({"$schema": "https://opencode.ai/config.json", "mcp": {"hold": {
        "type": "local", "command": [sys.executable, "-c", "import time; time.sleep(600)"], "timeout": 600000}}}), encoding="utf-8")

    def _exists(p: Path) -> bool:
        try:
            return p.exists()
        except OSError:  # 쓰는 중인 파일
            return False
    done = lambda: _exists(target / "node_modules" / "@opencode-ai" / "plugin" / "package.json") and _exists(target / "package-lock.json")
    proc = subprocess.Popen([str(exe), "mcp", "list"], cwd=str(proj), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    while not done() and proc.poll() is None and time.time() - t0 < 300:
        time.sleep(1)
    time.sleep(5)  # 잠금/마무리 쓰기 여유
    if proc.poll() is None:
        proc.kill(); proc.wait()
    if not done():
        raise SystemExit("V1 플러그인 의존성 준비 실패(네트워크/npm 레지스트리 확인)")
    ver = json.loads((target / "node_modules" / "@opencode-ai" / "plugin" / "package.json").read_text(encoding="utf-8"))["version"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    files = [target / "package.json", target / "package-lock.json"] + sorted(p for p in (target / "node_modules").rglob("*") if p.is_file())
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files:
            _retry(z.write, p, p.relative_to(target).as_posix())
    shutil.rmtree(work, ignore_errors=True)
    return ver

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", default="windows-x64", help="OpenCode 플랫폼 이름(windows-x64, linux-x64, darwin-arm64 …)")
    ap.add_argument("--pip-platform", default=None, help="pip --platform 태그(기본: 플랫폼에서 유추)")
    ap.add_argument("--py", default="3.11", help="대상 PC 의 Python 버전(wheel 태그)")
    ap.add_argument("--opencode", default="both", choices=["v2", "v1", "both", "none"])
    ap.add_argument("--v2-version"); ap.add_argument("--v1-version")
    ap.add_argument("--models", action="store_true", help="models.dev 카탈로그 스냅샷 포함(V1 OPENCODE_MODELS_PATH)")
    ap.add_argument("--out", default=str(KIT / "dist" / "offline"))
    ap.add_argument("--zip", action="store_true")
    ap.add_argument("--no-v1-deps", action="store_true", help="V1 플러그인 node_modules 미포함(대상 PC 가 npm 레지스트리에 접근 가능할 때)")
    a = ap.parse_args()
    out = Path(a.out) / f"open-science-offline-{a.platform}-py{a.py.replace('.', '')}"
    if out.exists():
        try:
            shutil.rmtree(out)
        except PermissionError as e:  # 잠긴 파일이 있으면 지우지 않고 새 폴더로
            print("  기존 폴더 삭제 실패, 새 폴더 사용:", e.filename)
            out = out.with_name(out.name + "-" + time.strftime("%Y%m%d-%H%M%S"))
    out.mkdir(parents=True)
    man = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "platform": a.platform, "python": a.py, "opencode": [], "wheels": []}
    tracks = {"both": ["v2", "v1"], "v2": ["v2"], "v1": ["v1"], "none": []}[a.opencode]
    print("[1/5] OpenCode 바이너리")
    for tr in tracks:
        man["opencode"].append(fetch_opencode(tr, a.platform, a.v2_version if tr == "v2" else a.v1_version,
                                              out / "bin" / ("opencode2" if tr == "v2" else "opencode1")))
    print("[2/5] Python wheels")
    man["wheels"] = build_wheels(out / "wheels", a.py, a.pip_platform or PIP_PLAT[a.platform])
    print("[3/5] 키트")
    for rel, b in kit_files():
        p = out / "kit" / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b)
    for f in ["install_offline.ps1", "install_offline.sh", "OFFLINE_README.md"]:
        shutil.copy2(KIT / "tools" / "offline" / f, out / f)
    if "v1" in tracks and not a.no_v1_deps:
        exe = next((p for p in (out / "bin" / "opencode1").rglob("*") if p.is_file() and p.name in ("opencode", "opencode.exe")), None)
        host = {"win32": "windows", "linux": "linux", "darwin": "darwin"}.get(sys.platform, sys.platform)
        if exe and a.platform.startswith(host):
            print("  V1 플러그인 의존성(@opencode-ai/plugin) 준비 ...")
            man["v1_deps"] = {"zip": "v1-deps/opencode-plugin-deps.zip",
                              "plugin_version": prime_v1_deps(exe, out / "v1-deps" / "opencode-plugin-deps.zip",
                                                              out.parent / f".{out.name}-v1deps-work")}
        else:
            print("  V1 플러그인 의존성 건너뜀(빌드 PC 와 대상 플랫폼이 달라 V1 바이너리를 실행할 수 없음)")
            man["v1_deps"] = None
    if a.models:
        print("[4/5] models.dev 스냅샷")
        try:
            r = httpx.get("https://models.dev/api.json", timeout=60); r.raise_for_status()
            (out / "models").mkdir(); (out / "models" / "models.json").write_bytes(r.content); man["models"] = "models/models.json"
        except Exception as e:
            print("  건너뜀:", repr(e)[:120]); man["models"] = None
    print("[5/5] 체크섬")
    (out / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    lines, size = [], 0
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name != "SHA256SUMS.txt":
            hx, n = _retry(_sha256, p); size += n
            lines.append(f"{hx}  {p.relative_to(out).as_posix()}")
    (out / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {out}  ({len(lines)}개 파일, {size/1e6:.0f} MB)")
    if a.zip:
        zp = out.with_suffix(".zip")
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for p in sorted(out.rglob("*")):
                if p.is_file():
                    _retry(z.write, p, f"{out.name}/{p.relative_to(out).as_posix()}")
        zh, zn = _retry(_sha256, zp)
        print(f"ZIP: {zp} ({zn/1e6:.0f} MB)  sha256={zh}")

if __name__ == "__main__":
    main()
