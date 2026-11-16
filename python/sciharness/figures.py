"""출판 품질 그림 스타일과 '렌더 후 검증(render-then-verify)' 도구.

사용 예:
    from sciharness.figures import apply_figure_style, save_figure, panel_letter
    apply_figure_style(lang="ko")
    fig, ax = plt.subplots()
    ...
    info = save_figure(fig, "outputs/figures/fig01_result", caption="...", data=df)
"""
from __future__ import annotations
import datetime as _dt, hashlib, json, os
from pathlib import Path
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import font_manager

# 색각이상(CVD) 안전 팔레트 (Okabe–Ito 기반). 경보색(ALARM)은 데이터 계열에 쓰지 않는다.
CATEGORICAL = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#F0E442", "#7F7F7F"]
FOCAL = "#08306B"      # 주인공 계열: 범주형 팔레트와 겹치지 않는 진한 남색
NEUTRAL = "#9E9E9E"    # 비교 대상(저강조)
ALARM = "#D55E00"      # 오류/이상치 전용
SEQUENTIAL = "viridis"
DIVERGING = "RdBu_r"   # 반드시 의미 있는 0(또는 1.0)에 중심을 맞출 것

_KO_FONTS = ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR",
             "Noto Sans KR", "UnDotum", "Gulim"]

def find_korean_font() -> str | None:
    names = {f.name for f in font_manager.fontManager.ttflist}
    for n in _KO_FONTS:
        if n in names:
            return n
    return None

def apply_figure_style(sizes=(8, 7, 6), lang: str = "ko", font: str | None = None,
                       dpi: int = 300, frame: str = "open") -> dict:
    """전역 rcParams 설정. sizes=(기본, 범례/주석, 눈금) 3단 글자 크기 사다리."""
    base, mid, small = sizes
    fam = font
    if fam is None and lang == "ko":
        fam = find_korean_font()
    rc = {
        "font.size": base, "axes.titlesize": base, "axes.labelsize": base,
        "legend.fontsize": mid, "xtick.labelsize": small, "ytick.labelsize": small,
        "figure.titlesize": base, "axes.titlelocation": "left", "axes.titleweight": "regular",
        "axes.spines.top": frame != "open", "axes.spines.right": frame != "open",
        "axes.linewidth": 0.7, "lines.linewidth": 1.4, "lines.markersize": 4,
        "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "legend.frameon": False, "axes.prop_cycle": mpl.cycler(color=CATEGORICAL),
        "savefig.dpi": dpi, "figure.dpi": 110, "savefig.bbox": "tight", "savefig.pad_inches": 0.05,
        "svg.fonttype": "none", "pdf.fonttype": 42, "ps.fonttype": 42,
        "axes.unicode_minus": False, "image.cmap": SEQUENTIAL,
    }
    if fam:
        rc["font.family"] = [fam, "DejaVu Sans"]
    mpl.rcParams.update(rc)
    return {"font": fam, "sizes": sizes, "dpi": dpi}

def panel_letter(ax, letter: str, case: str = "lower", dx: float = -0.10, dy: float = 1.02, size=None):
    """패널 문자: 굵게, 축 박스 바깥 좌상단."""
    s = letter.lower() if case == "lower" else letter.upper()
    size = size or mpl.rcParams["font.size"] + 2
    ax.text(dx, dy, s, transform=ax.transAxes, fontsize=size, fontweight="bold",
            va="bottom", ha="right")

def check_overlaps(fig) -> list[dict]:
    """보이는 텍스트끼리, 텍스트와 축선(spine)의 겹침, 그림 밖으로 나간 텍스트를 찾는다."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    texts = [(t, t.get_window_extent(r)) for t in fig.findobj(mpl.text.Text)
             if t.get_visible() and t.get_text().strip() and t.figure is fig]
    tick = set()
    for ax in fig.axes:
        tick |= set(ax.get_xticklabels(which="both") + ax.get_yticklabels(which="both"))
    spines = [(s, s.get_window_extent(r)) for ax in fig.axes for s in ax.spines.values() if s.get_visible()]
    out = []
    for i, (a, ba) in enumerate(texts):
        for b, bb in texts[i + 1:]:
            if ba.overlaps(bb) and ba.width > 0 and bb.width > 0:
                out.append({"kind": "text-text", "a": a.get_text()[:40], "b": b.get_text()[:40]})
    for t, bt in texts:
        if t in tick:
            continue
        for s, bs in spines:
            if bt.overlaps(bs) and bs.width > 1 and bs.height > 1:
                out.append({"kind": "text-spine", "a": t.get_text()[:40]})
    return out

def panel_crops(fig, dpi: int | None = None, pad_inches: float | None = None) -> dict:
    """bbox='tight'로 저장된 PNG 기준, 각 축의 픽셀 크롭 상자 (x0, y0, x1, y1)."""
    dpi = dpi or mpl.rcParams["savefig.dpi"]
    pad = mpl.rcParams["savefig.pad_inches"] if pad_inches is None else pad_inches
    fig.canvas.draw(); r = fig.canvas.get_renderer()
    tb = fig.get_tightbbox(r).padded(pad)
    inv = fig.dpi_scale_trans.inverted()
    crops = {}
    for i, ax in enumerate(fig.axes):
        if not ax.get_visible():
            continue
        bb = ax.get_tightbbox(r).transformed(inv)
        crops[chr(97 + i)] = (int(max(0, (bb.x0 - tb.x0) * dpi)), int(max(0, (tb.y1 - bb.y1) * dpi)),
                              int((bb.x1 - tb.x0) * dpi), int((tb.y1 - bb.y0) * dpi))
    return crops

def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]

def save_figure(fig, stem: str | os.PathLike, formats=("png", "svg"), caption: str | None = None,
                data=None, source: str | None = None, check: bool = True) -> dict:
    """그림 저장 + 겹침 검사 + 사이드카 JSON(캡션/해시/검사결과) + (선택) 그림 뒤 데이터 CSV."""
    stem = Path(stem); stem.parent.mkdir(parents=True, exist_ok=True)
    files = []
    for fmt in formats:
        p = stem.with_suffix("." + fmt)
        fig.savefig(p)
        files.append(str(p))
    issues = check_overlaps(fig) if check else []
    meta = {"files": files, "caption": caption, "created": _dt.datetime.now().isoformat(timespec="seconds"),
            "sha256": {f: _sha(Path(f)) for f in files}, "overlaps": issues, "source": source,
            "review_status": "pending"}
    if data is not None:
        try:
            csvp = stem.with_name(stem.name + "_data.csv")
            data.to_csv(csvp, index=False, encoding="utf-8-sig")
            meta["data_csv"] = str(csvp)
        except Exception as e:  # noqa
            meta["data_csv_error"] = repr(e)
    if "png" in formats:
        meta["panel_crops"] = panel_crops(fig)
    stem.with_name(stem.name + ".figure.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[save_figure] {stem.name}: {len(files)} files, overlaps={len(issues)}"
          + ("" if not issues else f" -> {issues[:3]}"))
    return meta
