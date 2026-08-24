"""Coordinate frames: map data space to figure space.

A :class:`Frame` is a group with a rectangular plot area and a data-to-world
mapping.  ``frame.pt(x, y)`` turns a data coordinate into a figure point, so
you can mix hand-placed graphics and data-driven ones freely.

The plotting helpers are deliberately thin: they build ordinary figkit
elements you can restyle, anchor to and move afterwards.
"""

from __future__ import annotations

import math

from .colors import colormap
from .core import Element, Group
from .geom import BBox, Point
from .shapes import Box, Line, Marker, Polygon, Polyline
from .style import enum_value
from .svgdoc import Node, RenderContext
from .text import Text

__all__ = ["Frame", "nice_ticks"]


def nice_ticks(lo: float, hi: float, n: int = 5) -> list:
    """Human-friendly tick positions covering ``[lo, hi]``."""
    if hi == lo:
        return [lo]
    if hi < lo:
        lo, hi = hi, lo
    raw = (hi - lo) / max(1, n)
    mag = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5, 10):
        if raw <= mult * mag:
            step = mult * mag
            break
    else:
        step = 10 * mag
    start = math.ceil(lo / step) * step
    out = []
    v = start
    while v <= hi + step * 1e-9:
        out.append(round(v, 12) + 0.0)
        v += step
    return out


def _fmt_tick(v: float) -> str:
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    s = f"{v:.6g}"
    return s


class Frame(Group):
    """A data-space coordinate system with a rectangular plot area.

    >>> fr = Frame(w=320, h=180, xlim=(0, 10), ylim=(0, 1))
    >>> fr.axes(xlabel="epoch", ylabel="accuracy")
    >>> fr.line(xs, ys, stroke="@primary", lw=2)
    >>> arrow(box.e, fr.pt(6, 0.8))     # point at a data coordinate
    """

    role = "group"

    def __init__(self, x: float = 0.0, y: float = 0.0, w: float = 300.0,
                 h: float = 200.0, *, xlim=(0.0, 1.0), ylim=(0.0, 1.0),
                 flip_y: bool = True, xscale: str = "linear",
                 yscale: str = "linear", background=None, border=None,
                 clip_data: bool = False, **kw):
        super().__init__(**kw)
        self.area = BBox(float(x), float(y), float(w), float(h))
        self.xlim = (float(xlim[0]), float(xlim[1]))
        self.ylim = (float(ylim[0]), float(ylim[1]))
        self.flip_y = bool(flip_y)
        scales = {"linear": "linear", "lin": "linear", "log": "log",
                  "log10": "log"}
        self.xscale = enum_value(xscale, "xscale", scales)
        self.yscale = enum_value(yscale, "yscale", scales)
        self._clip_data = bool(clip_data)
        self._bg = None
        self._frame_box = None
        if background is not None:
            self._bg = Box(None, self.area.x, self.area.y, self.area.w,
                           self.area.h, fill=background, stroke="none",
                           padding=0, z=-100, add=False)
            self.add(self._bg)
        if border:
            self._frame_box = Box(
                None, self.area.x, self.area.y, self.area.w, self.area.h,
                fill="none", stroke=border if isinstance(border, str) else "#6b7280",
                padding=0, radius=0, z=50, add=False)
            self.add(self._frame_box)

    # -- the mapping -----------------------------------------------------
    def _sx(self, v: float) -> float:
        lo, hi = self.xlim
        if self.xscale == "log":
            lo, hi, v = math.log10(max(lo, 1e-12)), math.log10(max(hi, 1e-12)), \
                math.log10(max(float(v), 1e-12))
        return 0.5 if hi == lo else (float(v) - lo) / (hi - lo)

    def _sy(self, v: float) -> float:
        lo, hi = self.ylim
        if self.yscale == "log":
            lo, hi, v = math.log10(max(lo, 1e-12)), math.log10(max(hi, 1e-12)), \
                math.log10(max(float(v), 1e-12))
        return 0.5 if hi == lo else (float(v) - lo) / (hi - lo)

    def px(self, x: float) -> float:
        """Data x -> world x."""
        return self.area.x0 + self._sx(x) * self.area.w

    def py(self, y: float) -> float:
        """Data y -> world y (flipped so larger values are higher)."""
        t = self._sy(y)
        return self.area.y1 - t * self.area.h if self.flip_y \
            else self.area.y0 + t * self.area.h

    def pt(self, x: float, y: float) -> Point:
        """Data ``(x, y)`` -> world :class:`~figkit.geom.Point`."""
        return Point(self.px(x), self.py(y))

    def pts(self, xs, ys=None) -> list:
        if ys is None:
            return [self.pt(p[0], p[1]) for p in xs]
        return [self.pt(x, y) for x, y in zip(xs, ys)]

    def data(self, px: float, py: float) -> tuple:
        """World point -> data coordinates (inverse mapping)."""
        tx = (px - self.area.x0) / self.area.w if self.area.w else 0.0
        ty = ((self.area.y1 - py) if self.flip_y else (py - self.area.y0))
        ty = ty / self.area.h if self.area.h else 0.0
        lo, hi = self.xlim
        x = lo + tx * (hi - lo) if self.xscale != "log" else \
            10 ** (math.log10(lo) + tx * (math.log10(hi) - math.log10(lo)))
        lo, hi = self.ylim
        y = lo + ty * (hi - lo) if self.yscale != "log" else \
            10 ** (math.log10(lo) + ty * (math.log10(hi) - math.log10(lo)))
        return x, y

    @property
    def plot_area(self) -> BBox:
        return self.area

    def clip_bbox(self) -> BBox:
        """``clip_data=True`` clips to the plot area, not the axes and labels."""
        return self.area

    def move(self, dx: float = 0.0, dy: float = 0.0) -> "Frame":
        """Move the frame: children *and* the data-space plot area."""
        if dx == 0 and dy == 0:
            return self
        self.area = self.area.translated(dx, dy)
        return super().move(dx, dy)

    @property
    def bbox(self) -> BBox:
        bb = super().bbox
        return bb.union(self.area) if len(self._children) else self.area

    def autoscale(self, xs=None, ys=None, pad: float = 0.05) -> "Frame":
        """Set limits from data with a little breathing room."""
        if xs is not None and len(xs):
            lo, hi = min(xs), max(xs)
            m = (hi - lo) * pad if hi > lo else 1.0
            self.xlim = (lo - m, hi + m)
        if ys is not None and len(ys):
            lo, hi = min(ys), max(ys)
            m = (hi - lo) * pad if hi > lo else 1.0
            self.ylim = (lo - m, hi + m)
        return self

    # -- helpers ---------------------------------------------------------
    def _adopt(self, el, *, data: bool = True):
        el._frame_data = bool(data)
        self.add(el)
        return el

    def at_data(self, element: Element, x: float, y: float,
                anchor: str = "center") -> Element:
        """Position an existing element by data coordinates."""
        p = self.pt(x, y)
        element.at(p.x, p.y, anchor=anchor)
        return self._adopt(element)

    def text(self, label: str, x: float, y: float, anchor: str = "center",
             **kw) -> Text:
        t = Text(label, add=False, **kw)
        p = self.pt(x, y)
        t.at(p.x, p.y, anchor=anchor)
        return self._adopt(t)

    # -- data marks ------------------------------------------------------
    def line(self, xs, ys=None, *, smooth: bool = False, **kw) -> Polyline:
        """A polyline through data points."""
        pts = self.pts(xs, ys)
        kw.setdefault("fill", "none")
        kw.setdefault("stroke", "@primary")
        kw.setdefault("stroke_width", 2.0)
        kw.setdefault("stroke_linejoin", "round")
        kw.setdefault("stroke_linecap", "round")
        if smooth:
            from .connectors import _catmull_rom
            from .shapes import Path
            return self._adopt(Path(_catmull_rom(pts), add=False, **kw))
        return self._adopt(Polyline(pts, add=False, **kw))

    def area_fill(self, xs, ys=None, base: float = None, **kw) -> Polygon:
        """Filled area between a series and a baseline."""
        pts = self.pts(xs, ys)
        if not pts:
            return None
        base = self.ylim[0] if base is None else base
        yb = self.py(base)
        poly = [Point(pts[0].x, yb)] + pts + [Point(pts[-1].x, yb)]
        kw.setdefault("fill", "@primary_soft")
        kw.setdefault("stroke", "none")
        return self._adopt(Polygon(poly, add=False, **kw))

    def scatter(self, xs, ys=None, *, size=7.0, shape: str = "circle",
                colors=None, values=None, cmap="viridis", vmin: float = None,
                vmax: float = None, **kw) -> Group:
        """Scatter markers. ``values`` + ``cmap`` colour-codes them."""
        pts = self.pts(xs, ys)
        kw.setdefault("fill", "@primary")
        kw.setdefault("stroke", "none")
        lo = min(values) if (values and vmin is None) else vmin
        hi = max(values) if (values and vmax is None) else vmax
        out = Group(add=False)
        for i, p in enumerate(pts):
            style = dict(kw)
            if colors:
                style["fill"] = colors[i % len(colors)]
            elif values is not None and i < len(values):
                t = 0.5 if hi == lo else (float(values[i]) - lo) / (hi - lo)
                style["fill"] = colormap(cmap, t)
            s = size[i] if isinstance(size, (list, tuple)) else size
            out.add(Marker(p, s, shape, add=False, **style))
        return self._adopt(out)

    def bars(self, xs, heights, *, width: float = 0.7, base: float = 0.0,
             colors=None, horizontal: bool = False, **kw) -> Group:
        """Bar chart. ``width`` is in data units (or a fraction of the step)."""
        out = Group(add=False)
        step = 1.0
        if len(xs) > 1:
            step = min(abs(float(xs[i + 1]) - float(xs[i]))
                       for i in range(len(xs) - 1)) or 1.0
        bw = width * step if width <= 1.0 else width
        kw.setdefault("fill", "@primary")
        kw.setdefault("stroke", "none")
        for i, (x, hgt) in enumerate(zip(xs, heights)):
            style = dict(kw)
            if colors:
                style["fill"] = colors[i % len(colors)]
            if horizontal:
                x0, x1 = self.px(base), self.px(hgt)
                y0, y1 = self.py(float(x) - bw / 2), self.py(float(x) + bw / 2)
            else:
                x0, x1 = self.px(float(x) - bw / 2), self.px(float(x) + bw / 2)
                y0, y1 = self.py(base), self.py(hgt)
            bar = Box(None, min(x0, x1), min(y0, y1), abs(x1 - x0),
                      abs(y1 - y0), padding=0, add=False, **style)
            out.add(bar)
        return self._adopt(out)

    def region(self, x0: float, x1: float, y0: float, y1: float, **kw) -> Box:
        """A shaded rectangle in data coordinates."""
        a, b = self.pt(x0, y0), self.pt(x1, y1)
        kw.setdefault("fill", "#0000000f")
        kw.setdefault("stroke", "none")
        kw.setdefault("padding", 0)
        return self._adopt(Box(None, min(a.x, b.x), min(a.y, b.y),
                               abs(b.x - a.x), abs(b.y - a.y), add=False, **kw))

    def hline(self, y: float, **kw) -> Line:
        kw.setdefault("stroke", "#9aa1ac")
        return self._adopt(Line(self.pt(self.xlim[0], y),
                                self.pt(self.xlim[1], y), add=False, **kw))

    def vline(self, x: float, **kw) -> Line:
        kw.setdefault("stroke", "#9aa1ac")
        return self._adopt(Line(self.pt(x, self.ylim[0]),
                                self.pt(x, self.ylim[1]), add=False, **kw))

    # -- axes ------------------------------------------------------------
    def gridlines(self, xticks=None, yticks=None, n: int = 5, **kw) -> Group:
        """Light grid lines behind the data."""
        kw.setdefault("stroke", "#e5e7eb")
        kw.setdefault("stroke_width", 1.0)
        g = Group(add=False, z=-50)
        for v in (nice_ticks(*self.xlim, n) if xticks is None else xticks):
            g.add(Line(self.pt(v, self.ylim[0]), self.pt(v, self.ylim[1]),
                       add=False, **kw))
        for v in (nice_ticks(*self.ylim, n) if yticks is None else yticks):
            g.add(Line(self.pt(self.xlim[0], v), self.pt(self.xlim[1], v),
                       add=False, **kw))
        return self._adopt(g)

    def xaxis(self, ticks=None, n: int = 5, labels=None, fmt=_fmt_tick,
              tick_size: float = 5.0, label_gap: float = 5.0,
              title: str = None, title_gap: float = 6.0, side: str = "bottom",
              show_line: bool = True, font_size: float = None, **kw) -> Group:
        """Draw the x axis with ticks and labels."""
        side = enum_value(side, "side", {"bottom": "bottom", "top": "top"})
        kw.setdefault("stroke", "#6b7280")
        kw.setdefault("stroke_width", 1.0)
        g = Group(add=False)
        y = self.area.y1 if side == "bottom" else self.area.y0
        sign = 1 if side == "bottom" else -1
        if show_line:
            g.add(Line((self.area.x0, y), (self.area.x1, y), add=False, **kw))
        vals = nice_ticks(*self.xlim, n) if ticks is None else list(ticks)
        texts = labels if labels is not None else [fmt(v) for v in vals]
        for v, lab in zip(vals, texts):
            px = self.px(v)
            if tick_size:
                g.add(Line((px, y), (px, y + sign * tick_size), add=False, **kw))
            if lab is not None and lab != "":
                t = Text(str(lab), add=False, font_size=font_size or 11,
                         color="#4b5563")
                t.at(px, y + sign * (tick_size + label_gap),
                     anchor="n" if side == "bottom" else "s")
                g.add(t)
        if title:
            t = Text(title, add=False, font_size=font_size or 12)
            gb = g.bbox
            t.at(self.area.cx, (gb.y1 + title_gap) if side == "bottom"
                 else (gb.y0 - title_gap),
                 anchor="n" if side == "bottom" else "s")
            g.add(t)
        return self._adopt(g, data=False)

    def yaxis(self, ticks=None, n: int = 5, labels=None, fmt=_fmt_tick,
              tick_size: float = 5.0, label_gap: float = 5.0,
              title: str = None, title_gap: float = 6.0, side: str = "left",
              show_line: bool = True, font_size: float = None,
              title_rotate: bool = True, **kw) -> Group:
        """Draw the y axis with ticks and labels."""
        side = enum_value(side, "side", {"left": "left", "right": "right"})
        kw.setdefault("stroke", "#6b7280")
        kw.setdefault("stroke_width", 1.0)
        g = Group(add=False)
        x = self.area.x0 if side == "left" else self.area.x1
        sign = -1 if side == "left" else 1
        if show_line:
            g.add(Line((x, self.area.y0), (x, self.area.y1), add=False, **kw))
        vals = nice_ticks(*self.ylim, n) if ticks is None else list(ticks)
        texts = labels if labels is not None else [fmt(v) for v in vals]
        for v, lab in zip(vals, texts):
            py = self.py(v)
            if tick_size:
                g.add(Line((x, py), (x + sign * tick_size, py), add=False, **kw))
            if lab is not None and lab != "":
                t = Text(str(lab), add=False, font_size=font_size or 11,
                         color="#4b5563", align="right" if side == "left" else "left")
                t.at(x + sign * (tick_size + label_gap), py,
                     anchor="e" if side == "left" else "w")
                g.add(t)
        if title:
            t = Text(title, add=False, font_size=font_size or 12)
            gb = g.bbox
            tx = (gb.x0 - title_gap) if side == "left" else (gb.x1 + title_gap)
            t.at(tx, self.area.cy, anchor="e" if side == "left" else "w")
            if title_rotate:
                t.rotate(-90 if side == "left" else 90)
                t.center_at(tx + (-t.bbox.w / 2 if side == "left"
                                  else t.bbox.w / 2), self.area.cy)
            g.add(t)
        return self._adopt(g, data=False)

    def axes(self, xlabel: str = None, ylabel: str = None, n: int = 5,
             grid: bool = False, **kw) -> Group:
        """Convenience: both axes (and optionally grid lines) in one call."""
        out = Group(add=False)
        if grid:
            out.add(self.gridlines(n=n))
        out.add(self.xaxis(n=n, title=xlabel, **kw))
        out.add(self.yaxis(n=n, title=ylabel, **kw))
        return self._adopt(out, data=False)

    # -- rendering ------------------------------------------------------
    def _render_content(self, ctx: RenderContext):
        """Clip data marks without clipping axis labels or other decoration."""
        kids = sorted([c for c in self._children if c.visible],
                      key=lambda c: (getattr(c, "z", 0) or 0))
        nodes = []
        clip_id = None
        for child in kids:
            node = child.render(ctx)
            if node is None:
                continue
            if self._clip_data and getattr(child, "_frame_data", False):
                if clip_id is None:
                    bb = self.area
                    clip = Node("clipPath").add(
                        Node("rect", x=bb.x, y=bb.y, width=bb.w, height=bb.h))
                    clip_id = ctx.add_def(clip)
                node = Node("g", clip_path=f"url(#{clip_id})").add(node)
            nodes.append(node)
        if not nodes:
            return None
        group = Node("g").add(*nodes)
        if self.clip:
            bb = self.clip_bbox()
            clip = Node("clipPath").add(
                Node("rect", x=bb.x, y=bb.y, width=bb.w, height=bb.h))
            group.attrs["clip-path"] = f"url(#{ctx.add_def(clip)})"
        return group
