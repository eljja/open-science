"""블록 다이어그램/아키텍처 회로도(schematic)용 경량 matplotlib DSL.

    from sciharness.schematic import Diagram
    d = Diagram(12, 7)
    d.layer(5.5, 1.3, "클라이언트 계층")
    d.box("ui", 1, 5.8, 2.4, 0.8, "Claude Code")
    d.box("mcp", 5, 3, 2.4, 0.8, "MCP 서버", color="green")
    d.arrow("ui", "mcp", "stdio")
    d.save("outputs/figures/fig_arch")
그래프 레이아웃이 복잡하면 graphviz(dot) / mermaid / TikZ 를 쓰고, 단순한 계층도는 이 모듈을 쓴다.
"""
from __future__ import annotations
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle

PALETTES = {  # (fill, edge)
    "blue": ("#E3EEF9", "#0072B2"), "orange": ("#FDF0DC", "#C47900"), "green": ("#E0F3EC", "#00795A"),
    "purple": ("#F4E6EF", "#A0528A"), "gray": ("#F0F0F0", "#6E6E6E"), "navy": ("#DCE4F0", "#08306B"),
    "sky": ("#E4F3FB", "#2B8CBE"), "red": ("#FBE3D9", "#D55E00"), "white": ("#FFFFFF", "#444444"),
}

class Diagram:
    def __init__(self, width: float = 12, height: float = 7, scale: float = 0.62, fontsize: float = 8):
        self.W, self.H, self.fs = width, height, fontsize
        self.fig, self.ax = plt.subplots(figsize=(width * scale, height * scale))
        self.ax.set_xlim(0, width); self.ax.set_ylim(0, height); self.ax.axis("off")
        self.nodes: dict[str, tuple] = {}

    def box(self, nid, x, y, w, h, text, color="blue", style="round", fontsize=None, bold=False,
            sub: str | None = None, lw=1.0, dashed=False):
        fill, edge = PALETTES.get(color, (color, "#333333"))
        bs = "round,pad=0.02,rounding_size=0.12" if style == "round" else "square,pad=0.02"
        p = FancyBboxPatch((x, y), w, h, boxstyle=bs, fc=fill, ec=edge, lw=lw,
                           ls="--" if dashed else "-", zorder=3)
        self.ax.add_patch(p)
        fs = fontsize or self.fs
        if sub:
            self.ax.text(x + w / 2, y + h * 0.62, text, ha="center", va="center", fontsize=fs,
                         fontweight="bold" if bold else "normal", zorder=4)
            self.ax.text(x + w / 2, y + h * 0.27, sub, ha="center", va="center", fontsize=fs - 1.5,
                         color="#444444", zorder=4)
        else:
            self.ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
                         fontweight="bold" if bold else "normal", zorder=4)
        self.nodes[nid] = (x, y, w, h)
        return nid

    def layer(self, y, h, label, color="gray", x=0.05, w=None, alpha=0.55):
        w = w if w is not None else self.W - 0.1
        fill, edge = PALETTES.get(color, (color, "#999999"))
        self.ax.add_patch(Rectangle((x, y), w, h, fc=fill, ec="none", alpha=alpha, zorder=0))
        self.ax.text(x + 0.12, y + h - 0.12, label, ha="left", va="top", fontsize=self.fs - 0.5,
                     color=edge, fontweight="bold", zorder=1)

    def group(self, ids, label, pad=0.18, color="gray"):
        xs = [self.nodes[i] for i in ids]
        x0 = min(a[0] for a in xs) - pad; y0 = min(a[1] for a in xs) - pad
        x1 = max(a[0] + a[2] for a in xs) + pad; y1 = max(a[1] + a[3] for a in xs) + pad + 0.3
        edge = PALETTES.get(color, ("", "#888888"))[1]
        self.ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0.02,rounding_size=0.15",
                                         fc="none", ec=edge, lw=0.9, ls="--", zorder=2))
        self.ax.text(x0 + 0.1, y1 - 0.08, label, ha="left", va="top", fontsize=self.fs - 1, color=edge, zorder=4)

    def _anchor(self, nid, side):
        x, y, w, h = self.nodes[nid]
        return {"left": (x, y + h / 2), "right": (x + w, y + h / 2), "top": (x + w / 2, y + h),
                "bottom": (x + w / 2, y), "center": (x + w / 2, y + h / 2)}[side]

    def _auto_sides(self, a, b):
        ax_, ay, aw, ah = self.nodes[a]; bx, by, bw, bh = self.nodes[b]
        dx = (bx + bw / 2) - (ax_ + aw / 2); dy = (by + bh / 2) - (ay + ah / 2)
        if abs(dx) * 0.6 > abs(dy):
            return ("right", "left") if dx > 0 else ("left", "right")
        return ("top", "bottom") if dy > 0 else ("bottom", "top")

    def arrow(self, a, b, text=None, src_side=None, dst_side=None, curve=0.0, dashed=False,
              color="#444444", both=False, lw=1.0, text_offset=(0, 0)):
        s1, s2 = self._auto_sides(a, b)
        p1 = self._anchor(a, src_side or s1); p2 = self._anchor(b, dst_side or s2)
        arr = FancyArrowPatch(p1, p2, arrowstyle="<|-|>" if both else "-|>", mutation_scale=9,
                              connectionstyle=f"arc3,rad={curve}", color=color, lw=lw,
                              ls="--" if dashed else "-", zorder=2, shrinkA=2, shrinkB=2)
        self.ax.add_patch(arr)
        if text:
            mx = (p1[0] + p2[0]) / 2 + text_offset[0]; my = (p1[1] + p2[1]) / 2 + text_offset[1]
            self.ax.text(mx, my, text, ha="center", va="center", fontsize=self.fs - 1.5, color="#333333",
                         bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.95), zorder=5)

    def note(self, x, y, text, fontsize=None, color="#333333", ha="left", style="normal"):
        self.ax.text(x, y, text, ha=ha, va="center", fontsize=fontsize or self.fs - 1, color=color,
                     style=style, zorder=5)

    def title(self, text):
        self.ax.set_title(text, loc="left", fontsize=self.fs + 1)

    def save(self, stem, caption=None, formats=("png", "svg")):
        from .figures import save_figure
        return save_figure(self.fig, stem, formats=formats, caption=caption)
