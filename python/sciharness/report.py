"""Markdown → Confluence 친화 HTML.
- mode="embed": 그림을 base64로 내장한 단일 HTML (메일/공유용)
- mode="attach": 그림을 images/ 로 복사하고 상대경로 참조 (Confluence 첨부 업로드용)
Confluence 본문은 <style> 블록을 버리므로 모든 스타일을 인라인 style 속성으로 넣는다.
"""
from __future__ import annotations
import base64, html, re, shutil
from pathlib import Path
import markdown

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp"}
FONT = "'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif"
STY = {
    "h1": f"font-family:{FONT};font-size:24px;color:#0B2545;border-bottom:2px solid #0B2545;padding-bottom:4px;margin:28px 0 12px",
    "h2": f"font-family:{FONT};font-size:19px;color:#13315C;border-bottom:1px solid #C9D3E0;padding-bottom:3px;margin:24px 0 10px",
    "h3": f"font-family:{FONT};font-size:16px;color:#13315C;margin:18px 0 8px",
    "h4": f"font-family:{FONT};font-size:14px;color:#333;margin:14px 0 6px",
    "p": f"font-family:{FONT};font-size:14px;line-height:1.7;color:#222;margin:6px 0 10px",
    "li": f"font-family:{FONT};font-size:14px;line-height:1.65;color:#222",
    "table": "border-collapse:collapse;margin:10px 0 16px;font-size:13px;width:auto",
    "th": f"font-family:{FONT};border:1px solid #B8C4D6;background:#E8EEF6;padding:5px 8px;text-align:left;vertical-align:top",
    "td": f"font-family:{FONT};border:1px solid #D0D7E2;padding:5px 8px;vertical-align:top",
    "code": "font-family:Consolas,'D2Coding',monospace;font-size:12.5px;background:#F3F5F8;padding:1px 4px;border-radius:3px",
    "pre": "font-family:Consolas,'D2Coding',monospace;font-size:12.5px;background:#F6F8FA;border:1px solid #E1E4E8;padding:10px;overflow-x:auto;line-height:1.45",
    "blockquote": f"font-family:{FONT};border-left:4px solid #8FA9C8;background:#F5F8FC;margin:10px 0;padding:6px 12px;color:#333",
    "img": "max-width:100%;height:auto;border:1px solid #E3E7ED;margin:6px 0",
    "a": "color:#0B5FA5;text-decoration:none",
    "hr": "border:none;border-top:1px solid #D0D7E2;margin:20px 0",
}

def _inline_styles(h: str) -> str:
    for tag, st in STY.items():
        h = re.sub(rf"<{tag}(\s[^>]*)?>", lambda m: _add_style(m.group(0), tag, st), h)
    # <pre><code> 내부 code 는 배경 중복 제거
    h = re.sub(r'(<pre[^>]*>)<code style="[^"]*"', r'\1<code style="font-family:Consolas,monospace;background:none"', h)
    return h

def _add_style(tag_html: str, tag: str, st: str) -> str:
    if "style=" in tag_html:
        return tag_html.replace('style="', f'style="{st};', 1)
    return tag_html[:-1] + f' style="{st}">' if not tag_html.endswith("/>") else tag_html[:-2] + f' style="{st}"/>'

def build_html(md_path: str | Path, out_html: str | Path, mode: str = "embed", title: str | None = None,
               toc: bool = True) -> Path:
    md_path = Path(md_path); out_html = Path(out_html); out_html.parent.mkdir(parents=True, exist_ok=True)
    text = md_path.read_text(encoding="utf-8")
    exts = ["tables", "fenced_code", "toc", "footnotes", "attr_list", "sane_lists"]
    body = markdown.markdown(text, extensions=exts, extension_configs={"toc": {"toc_depth": "2-3"}})
    img_dir = out_html.parent / "images"

    def fix_img(m):
        src = html.unescape(m.group(2))
        if src.startswith(("http:", "https:", "data:")):
            return m.group(0)
        p = (md_path.parent / src).resolve()
        if not p.exists():
            return m.group(0)
        if mode == "embed":
            mt = _MIME.get(p.suffix.lower(), "application/octet-stream")  # mimetypes 는 Windows 레지스트리를 읽어 권한 오류가 날 수 있음
            return f'{m.group(1)}data:{mt};base64,{base64.b64encode(p.read_bytes()).decode()}{m.group(3)}'
        img_dir.mkdir(exist_ok=True); shutil.copy2(p, img_dir / p.name)
        return f"{m.group(1)}images/{p.name}{m.group(3)}"
    body = re.sub(r'(<img[^>]*?src=")([^"]+)(")', fix_img, body)
    body = _inline_styles(body)
    t = title or (re.search(r"^#\s+(.+)$", text, re.M).group(1) if re.search(r"^#\s+(.+)$", text, re.M) else md_path.stem)
    doc = (f'<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>{html.escape(t)}</title></head>'
           f'<body style="max-width:980px;margin:24px auto;padding:0 18px;font-family:{FONT}">{body}</body></html>')
    out_html.write_text(doc, encoding="utf-8")
    return out_html
